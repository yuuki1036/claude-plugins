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
  - 終了コードは**テストのものをそのまま返す**（緑判定を変えない）
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

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = ".claude-plugin/scripts/tests"

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
    """テストを**別プロセスグループ・同一セッション**で起動する（出力は `log` へ）."""
    kwargs = {"cwd": str(ROOT), "stdout": log, "stderr": log}
    if sys.version_info >= (3, 11):  # mutation-ok: 境界をずらしても fallback が同じグループを作る
        kwargs["process_group"] = 0
    else:  # 3.10 以下には process_group が無い
        kwargs["preexec_fn"] = os.setpgrp   # noqa: PLW1509
    return subprocess.Popen(cmd, **kwargs)


def main(argv: list[str]) -> int:
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", TESTS_DIR, *argv]
    with tempfile.TemporaryFile("w+b") as log:
        proc = _spawn(cmd, log)
        pgid = proc.pid   # グループリーダーなので pgid == pid
        _install_signal_forwarding(pgid)
        try:
            rc = proc.wait()
        finally:
            # **回収は必ず通す**（例外・中断で飛ばさない）。出力も必ず流す
            log.seek(0)
            sys.stderr.buffer.write(log.read())
            sys.stderr.flush()
            try:
                sweep(pgid, proc.pid)
            except Exception as exc:   # noqa: BLE001
                # **後始末の失敗を rc に載せない**。ここで例外を通すと traceback + exit 1 に
                # なり、緑のテストが pre-commit のブロックに化ける（実測で 1 度踏んだ）
                print("[run-tests] 残留の回収に失敗した: %r"
                      "（テストの結果には影響させない）" % (exc,), file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
