#!/usr/bin/env python3
"""回帰テストを**新しいセッションで**起動し、終わったあとに生き残った子孫を回収する.

**なぜ要るか**（GitHub issue #140 事例 2）: テストが全件 green でも、テストが起動した
プロセスが生き残ることがある。実測では `mutation-test.py` の timeout が直接の子しか
殺さず、無限ループ化した孫が **12 本 × 4 時間 × 各 14% CPU** で回り続けた。
**テストは緑のまま**で、発覚は「PC が重い」というユーザーの体感だった。
既存のどの層（pre-commit / CI / Stop hook / self-review 前段）にも掛からない型なので、
**テストを起動する場所**に置く。原因側の対処（プロセスグループごと回収）は済んでいるが、
それは同じ原因を塞いだだけで、**次に同種の後始末漏れを入れたときには効かない**。

契約:
  - 終了コードは**テストのものをそのまま返す**（緑判定を変えない）。唯一の例外が
    「1 件も収集されなかった」で、これは 5（測れなかった）に倒す — unittest 自身が 5 を
    返すのは Python 3.12 以降で、それ以前は 0 なので**古い開発機だけ緑に見える**（#176）
  - 残留プロセスは stderr に **`[run-tests:leak]`** で警告して kill する。
    **exit code には反映しない** —
    残留は「テストの失敗」ではなく後始末の漏れで、ここで赤にすると commit が通らない
  - `pgrep` が無い環境では残留判定だけを skip する（テスト自体は走らせる）

**セッションではなくプロセスグループだけを分ける**（`process_group=0`）:
  グループを分けるのは「テストが起動したものだけ」を数えるため。**セッションまで分けると
  上位層の `killpg` が届かなくなり、自分が殺された回のリークを誰も回収できない**
  （実測: `mutation-test.py` が timeout でグループごと回収した際、別セッションに逃げた孫が
  3 本 ppid=1 で残った。#140 の原因である mutation-test 経路そのものが対象外になっていた）。
  同一セッションに留まれば上位の `killpg` は自分に届くので、シグナルを受けたら
  **自分のグループを回収してから死ぬ**（下の `_install_signal_forwarding`）。

**子の出力はパイプではなく一時ファイルへ向ける**:
  呼び出し側は `OUT="$(run-tests.py 2>&1)"` の形で使う（`machine-layer.sh` / `.githooks/pre-commit`）。
  子の stdio をそのまま継承させると**残留した孫がそのパイプの write 端を握り続け**、
  こちらが終了してもコマンド置換が EOF を待って**無言でハングする**（＝`git commit` が固まる）。
  ファイルなら握られても EOF は待たれない。回収後に本文をこちらの stderr へ流す。

使い方:
  python3 .claude-plugin/scripts/run-tests.py [unittest への追加引数...]
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = ".claude-plugin/scripts/tests"

sys.path.append(str(ROOT / TESTS_DIR))
from git_env import scrub   # noqa: E402  （テスト側と同じ正本を使う。複製しない）

#: SIGTERM を送ってから SIGKILL に上げるまでの猶予（秒）
GRACE_SEC = 2.0

#: SIGKILL を送ってから生死を確かめるまでの猶予（秒）
KILL_CONFIRM_SEC = 0.5


def list_group(pgid: int) -> list[int] | None:
    """プロセスグループ `pgid` に残っている pid（判定できなければ None）."""
    try:
        res = subprocess.run(["pgrep", "-g", str(pgid)], capture_output=True, text=True)
    except (FileNotFoundError, OSError):
        return None
    # pgrep は「該当なし」で 1 を返す。それ以外の非ゼロは使い方が違う＝判定不能
    if res.returncode not in (0, 1):
        return None
    return [int(pid) for pid in res.stdout.split() if pid.isdigit()]


def _signal(pid: int, sig: int) -> str:
    """`pid` にシグナルを送る（`gone` / `sent` / `denied`）.

    **`PermissionError` を捕まえること**: 捕まえないと `main` を貫通して traceback で
    exit 1 になり、「終了コードはテストのものをそのまま返す」という契約を後始末の側が破る
    （＝緑のテストが pre-commit のブロックに化ける）。
    """
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return "gone"
    except PermissionError:
        return "denied"
    return "sent"


def reap(pgid: int, pids: list[int]) -> list[int]:
    """`pids` を落とす。**本当に生き残ったものだけ**を返す。

    - **SIGKILL を送れたことを「落とせた」と読まない**: 送出の成否と生死は別で、
      再確認しないと回収成功を「回収できなかった（手動で kill しろ）」と誤報する。
      唯一のエスカレーション経路がノイズになるので、最後にもう一度生死を見る
    - **昇格の前にグループ再列挙で pid の同一性を確かめる**: SIGTERM 直後は対象が死ぬ
      確率が最も高く、`GRACE_SEC` はその pid が別プロセスに再利用されうる窓。
      `os.kill(pid, 0)` は「別プロセスが同じ pid を取った」場合も成功するので同一性の
      保証にならない。**まだ自分のグループに居ること**を条件にする
    """
    denied = {pid for pid in pids if _signal(pid, signal.SIGTERM) == "denied"}
    time.sleep(GRACE_SEC)

    still = list_group(pgid)
    if still is None:
        # 再列挙できない＝同一性を確認できない。**撃たない側に倒す**（無関係な
        # プロセスを殺すより、残留を報告して人に渡す方が安全）
        return sorted(set(pids))
    hard = [pid for pid in pids if pid in set(still)]
    for pid in hard:
        if _signal(pid, signal.SIGKILL) == "denied":
            denied.add(pid)
    time.sleep(KILL_CONFIRM_SEC)

    final = list_group(pgid)
    survivors = set(hard) if final is None else set(hard) & set(final)
    return sorted(survivors | denied)


def sweep(pgid: int, exclude: int | None = None) -> None:
    """`pgid` の残留を報告して回収する（**何度呼んでも安全**）.

    `exclude` はテスト本体の pid。**正常終了の経路でだけ渡す**（既に wait 済みなので
    残っていれば別物）。シグナルで死ぬ経路では `None` を渡してテスト本体ごと回収する
    — 自分が死んだあとテストだけが走り続けるのが、回収したい状態そのものだから。
    """
    leaked = list_group(pgid)
    if leaked is None:
        print("[run-tests] pgrep が使えないため残留プロセスの判定を skip した", file=sys.stderr)
        return
    leaked = [pid for pid in leaked if pid != exclude]
    if not leaked:
        return
    print("[run-tests:leak] テスト終了後に %d 個のプロセスが残っている: %s"
          % (len(leaked), ", ".join(str(p) for p in leaked)), file=sys.stderr)
    print("[run-tests] テストが起動したプロセスの後始末が漏れている"
          "（timeout は直接の子しか殺さない）。回収してから続行する", file=sys.stderr)
    stubborn = reap(pgid, leaked)
    if stubborn:
        print("[run-tests:leak] 回収できなかった: %s（手動で kill すること）"
              % ", ".join(str(p) for p in stubborn), file=sys.stderr)


def _install_signal_forwarding(pgid: int) -> None:
    """自分が止められた回も、**死ぬ前にテストのグループを回収する**.

    上位層（`mutation-test.py` の timeout 回収など）は自分のプロセスグループ宛に
    シグナルを撃つ。同一セッションに留まっているのでこちらには届くが、既定動作のまま
    即死するとテスト側のグループが孤児になる（実測: 孫が 3 本 ppid=1 で残った）。
    """
    def handler(signum, _frame):
        sweep(pgid)   # exclude なし = テスト本体ごと落とす
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):   # メインスレッド以外・未対応シグナル
            pass


def _spawn(cmd: list[str], log) -> subprocess.Popen:
    """テストを**別プロセスグループ・同一セッション**で起動する（出力は `log` へ）.

    **git hook 由来の環境変数はここで落とす**（GitHub issue #158）。この起動口は
    pre-commit から呼ばれるので、linked worktree で commit すると `GIT_DIR` に
    **実リポジトリの絶対パス**が入って渡ってくる。個々のテストも `git_env.scrub()` を
    通す規約だが（`python3 -m unittest discover` で直に走らせる経路が残るため）、
    **壊れ方が実リポジトリの破壊**なので、強制される経路は入口でも落とす。
    """
    kwargs = {"cwd": str(ROOT), "stdout": log, "stderr": log, "env": scrub()}
    if sys.version_info >= (3, 11):  # mutation-ok: 境界をずらしても fallback が同じグループを作る
        kwargs["process_group"] = 0
    else:  # 3.10 以下には process_group が無い
        kwargs["preexec_fn"] = os.setpgrp   # noqa: PLW1509
    return subprocess.Popen(cmd, **kwargs)


#: unittest の集計行（`Ran 12 tests in 0.4s`）。**版差を吸収するために自分で数える**
_RAN_RE = re.compile(rb"^Ran (\d+) tests? in ", re.M)


def _ran_count(out: bytes) -> int:
    """走ったテスト件数を出力から読む（集計行が無ければ 0 とみなす）."""
    m = _RAN_RE.search(out)
    return int(m.group(1)) if m else 0


def _exit_code(rc: int, out: bytes) -> int:
    """返す終了コードを決める.

    **「1 件も収集されなかった」を Python の版差に任せない**（GitHub issue #176）:
    unittest が no-tests で 5 を返すのは 3.12 以降で、それ以前は 0（実測: 3.9 は 0 /
    3.14 は 5）。古い python3 の開発機では収集ゼロが緑に見えるので自分で 5 に倒す。

    **失敗した実行の rc は握り潰さない**: `rc` が非ゼロなら、収集数に関わらず
    そのまま返す（失敗の理由を 5 に塗り潰すと直しどころが分からなくなる）。
    """
    if rc == 0 and _ran_count(out) == 0:
        return 5
    return rc


#: `mutation-test.py` が「変異を当てている区間」を示す状態ファイル（正本はあちら側）。
#: **パスを複製しているのは依存を作らないため** — run-tests は mutation-test を import せず、
#: ファイルの有無と pid の生存だけを見る
MUTATION_JOURNAL = ".mutation-test-journal.json"


def mutation_in_progress() -> str | None:
    """変異テストが対象ファイルを書き換えている最中なら、その説明を返す.

    **変異が乗っている間に走らせたテスト結果は緑にも赤にも化ける。** 実測では、
    別セッションが `mutation-test.py` を回している 48 分の間、作業ツリーはほぼ 100% の
    時間 mutant 状態で、3 秒間隔 44 サンプルすべてが変異体だった。そこで測った結果は
    「テスト間の干渉」に見え、順序の二分探索に時間を溶かす（実測: 誤診 1 件）。

    journal が残っていても**書いた run が既に死んでいれば**変異は復元済みか、
    次回の `mutation-test.py` 起動時に復旧される。生存している pid のときだけ止める。
    """
    j = ROOT / MUTATION_JOURNAL
    try:
        data = json.loads(j.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None            # 無い / 壊れている journal では止めない（fail-open）
    if not isinstance(data, dict):
        return None            # 形が違う journal でも止めない（書式が変わっただけで
                               # テストが走らなくなる方が高くつく）
    pid = data.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool):
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None            # 書いた run は終了済み
    except PermissionError:
        pass                   # 別ユーザーの生存プロセス。止める側に倒す
    return "pid %d が %s に変異を当てている" % (pid, data.get("path") or "?")


def main(argv: list[str]) -> int:
    busy = mutation_in_progress()
    if busy:
        print("[run-tests] **変異テストの実行中**（%s）。\n"
              "  この状態で測った結果は緑にも赤にも化けるので走らせない。\n"
              "  完走を待つか、index の内容を使い捨てクローンへ取り出して測ること:\n"
              "    git checkout-index -a --prefix=/tmp/clone/\n"
              "  **Ctrl-C で殺さないこと** — 復元が飛んで変異が作業ツリーに残る。"
              % busy, file=sys.stderr)
        return 2               # 判定不能（machine-layer と同じ流儀）
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", TESTS_DIR, *argv]
    out = b""
    with tempfile.TemporaryFile("w+b") as log:
        proc = _spawn(cmd, log)
        pgid = proc.pid   # グループリーダーなので pgid == pid
        _install_signal_forwarding(pgid)
        try:
            rc = proc.wait()
        finally:
            # **回収は必ず通す**（例外・中断で飛ばさない）。出力も必ず流す
            log.seek(0)
            out = log.read()
            sys.stderr.buffer.write(out)
            sys.stderr.flush()
            try:
                sweep(pgid, proc.pid)
            except Exception as exc:   # noqa: BLE001
                # **後始末の失敗を rc に載せない**。ここで例外を通すと traceback + exit 1 に
                # なり、緑のテストが pre-commit のブロックに化ける（実測で 1 度踏んだ）
                print("[run-tests] 残留の回収に失敗した: %r"
                      "（テストの結果には影響させない）" % (exc,), file=sys.stderr)
    # 判定は `_exit_code`（版差の吸収。machine-layer はこの 5 を「判定不能」として扱う）
    #
    # **`rc != 5` で通知を絞らないこと**: unittest 自身が 5 を返す Python 3.12 以降では
    # その条件が常に偽になり、**通知が一度も出ない**（「測れていない」を黙って返すのは
    # この 5 を入れた目的そのものに反する）
    final = _exit_code(rc, out)
    if final == 5:
        print("[run-tests] テストが 1 件も収集されなかった（緑ではなく『測れていない』）",
              file=sys.stderr)
    return final


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
