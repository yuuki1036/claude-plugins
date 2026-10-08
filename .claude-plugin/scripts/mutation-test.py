#!/usr/bin/env python3
"""変更行に限定した変異テスト（テストが「検証していない挙動」を炙り出す）.

**なぜ必要か**: このリポジトリで直近 3 回のセルフレビューが報告した MAJOR 33 件のうち
**22 件（67%）が「新しいガードが自分の宣言した守備範囲を満たさない」「テストが空振り」**
の 2 種だった。どちらも根は同じで、**検証コードの検証が無い** — ガードを書いて正常系が
動くことは確認するが、「静かに効かなくなる経路」は誰も確かめない。

テストの充実度を**件数**で測ると「増やしたのに同じ型が出続ける」になる。**生存変異率**で
測れば「テストが何を検証していないか」が直接出る。本スクリプトはその測定を自動化する。

**手動でやると嘘の結果が出る**（実測）: `__pycache__` の stale bytecode を実行していて
「変異 5 種すべて検知した」と出たことがある。`inspect.getsource` はソースを読むので
「コードは正しいのに挙動が違う」という紛らわしい形で現れる。毎回キャッシュを消す。

**復元に `git checkout` を使わない**（実測で事故った）: 未コミット変更があるファイルを
checkout すると作業が飛ぶ。元のバイト列をメモリに持ち `try/finally` で書き戻す。

**実行中は対象ファイルを編集しないこと**（これも実測で事故った）: バックグラウンド実行
したまま同じファイルを編集すると、復元が編集を上書きして**黙って作業を消す**。
復元前に「自分が書いた変異体のまま残っているか」を確認し、違えば書き戻さず落とす。

使い方:
  mutation-test.py                     # HEAD との差分の追加行を変異させる
  mutation-test.py --base origin/main  # 起点を変える
  mutation-test.py --file a.py b.sh    # **ファイル全体**を対象にする（差分ではなく全行）。
                                       # 変異のうち --base との差分の追加行に当たる件数を冒頭に出す
  mutation-test.py --max 40            # 変異の上限（既定 25。超過分は件数を報告する）
  mutation-test.py --strict            # 生存変異があれば exit 1（CI / gate 用）
  mutation-test.py --test-cmd "..."    # テストコマンドを差し替える
  mutation-test.py --summary-json s.json  # 集計を JSON でも書く（nightly の起票判定が読む）

**`--test-cmd` は shell を通さず `split()` で直接 spawn する。** `cd x && ...` や `|` を
書くと先頭コマンドだけが実行され（`cd` は exit 0）、baseline が緑・全変異 SURVIVED という
**嘘の結果**になる（実測 2026-09-11）。shell 演算子と先頭 `cd` は exit 2 で弾く。
ディレクトリ移動やテスト絞り込みは unittest の引数で表す:
  --test-cmd "python3 -m unittest discover -s .claude-plugin/scripts/tests -p test_x.py -k SomeTest"

**実行の冒頭に対象のモードと、baseline で走ったテストの件数を出す**（GitHub issue #256）。
CLI の読み違えが 30 日で 5 回あった — `--file` を差分だと思い、上限が既存行に使われて変更行を
1 件も検証しなかった回 / `-k` の部分一致が狙ったテストに当たらず、カバー済みの行が SURVIVED に
見えた回。どちらも結果の数字だけでは気づけない。テストが 1 件も走らなかったら exit 2。

出力: 生存した変異（= テストが検証していない挙動）を file:line と変異内容つきで列挙する。
Exit code: 0（既定。`--strict` 指定時のみ生存で 1）/ 2（引数エラー・テストが最初から赤）
  外部編集を検知したときは**そこまでの結果を出してから** 1 で終わる（残りは未実行）。
"""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import io
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
import tokenize
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# **`-f`（failfast）を付ける**。落ちる変異は最初の失敗で止まり、判定は killed のまま変わらない（生存は
# スイート全体が緑のときだけ）。1 変異 = フルスイートなので所要がスイートの伸びに比例する（nightly の
# 10-07 は 1 変異 約 428 秒・1 晩 19 個 / #288）。代償は、出力が最初の失敗の分だけになるので構文エラーの
# 判定（invalid）を取りこぼし、killed に入りうること
DEFAULT_TEST_CMD = "python3 -m unittest discover -s .claude-plugin/scripts/tests -f"
# baseline（変異前のフルスイート）の timeout。手元（macOS）のフルスイートは約 650 秒、CI は 280〜457 秒で
# 伸び続けている。600 秒だと既定のテストコマンドの baseline が手元で FATAL になり、CI でも push 側の
# スモークが近く赤くなる（#288）。`--budget-sec` を指定した回は予算まで延ばす
BASELINE_TIMEOUT = 1800
TARGET_SUFFIXES = {".py", ".sh"}
# **テストファイルは変異させない**。テストは判定者であって被験者ではなく、fixture を
# 書き換えて「テストが通った」ことには意味がない（初回実行の生存 8 件が全部これだった）。
# **空振りテストは本体側の変異が生き残る形で必ず現れる**ので、除外しても信号は失われない。
TEST_PATH_RE = re.compile(r"(^|/)(tests?|__tests__)/|(^|/)test_[^/]+\.py$|_test\.py$|\.test\.")

# 変異規則: (正規表現, 置換, 説明).
# **境界と分岐の反転に絞る**（今回のセルフレビューで実際に生き残った欠陥の型）:
#   fail-open ゲート / 後勝ち上書き / 閾値の単位違い / 早期 return の欠落。
# 文字列リテラルの中身は避けたいが完全な判定は言語パーサが要る。実用上は
# **コメント行を除外**し、`_looks_quoted` で行内の引用符に挟まれた一致を捨てる近似で足りる。
RULES: list[tuple[str, str, str]] = [
    (r"(?<![<>=!])>=(?!=)", ">", ">= を > に（境界を 1 つ狭める）"),
    (r"(?<![<>=!])<=(?!=)", "<", "<= を < に（境界を 1 つ狭める）"),
    (r"(?<![<>=!])==(?!=)", "!=", "== を != に（判定を反転）"),
    (r"(?<![<>=!])!=(?!=)", "==", "!= を == に（判定を反転）"),
    (r"\bnot in\b", "in", "not in を in に（包含判定を反転）"),
    (r"\bis not\b", "is", "is not を is に（同一性判定を反転）"),
    (r"\bTrue\b", "False", "True を False に"),
    (r"\bFalse\b", "True", "False を True に"),
    (r"\band\b", "or", "and を or に（条件の結合を緩める）"),
    (r"\bbreak\b", "continue", "break を continue に（打ち切りを外す）"),
    (r"-ge\b", "-gt", "-ge を -gt に（bash の境界を 1 つ狭める）"),
    (r"-le\b", "-lt", "-le を -lt に（bash の境界を 1 つ狭める）"),
    (r"-eq\b", "-ne", "-eq を -ne に（bash の判定を反転）"),
    (r"&&", "||", "&& を || に（bash の結合を緩める）"),
    # **緩める方向も要る**。fail-open は「ゲートが広すぎる」形で現れるので、狭める側だけでは
    # 片側しか覆えない（実測: この repo の bash で最頻の `while [ $# -gt 0 ]` は
    # `-gt` の規則が無く 1 個も変異が出なかった）
    (r"-gt\b", "-ge", "-gt を -ge に（bash の境界を 1 つ広げる）"),
    (r"-lt\b", "-le", "-lt を -le に（bash の境界を 1 つ広げる）"),
    (r"-ne\b", "-eq", "-ne を -eq に（bash の判定を反転）"),
    (r"\bor\b", "and", "or を and に（条件の結合を狭める）"),
    (r"(?<![<>=!\-])>(?![>=])", ">=", "> を >= に（境界を 1 つ広げる）"),
    (r"(?<![<>=!])<(?![<=])", "<=", "< を <= に（境界を 1 つ広げる）"),
]
# **言語ごとの規則**。上の RULES は .py / .sh の別なく当てるが、ここから下は綴りが同じでも
# 言語によって意味が違うので、`.py` と `.sh` に埋め込まれた python には PY_RULES、それ以外の
# `.sh` には SH_RULES を当てる。上の RULES だけだった頃は `if not x:` / `any(...)` /
# `continue` / 条件式のどれにも変異が出ず、Python の分岐 55 行に「変異 0 個」を返した
# （実測 2026-10-07。手製の変異体 34 個を当てるとテストの穴が 4 個見つかった）。
# `not` / 条件式 / `any` を .sh 全体に当てると jq の `if ... else` や `find -not` に当たる。
# 導入前の実測（2026-09-30〜10-07 の差分・フルスイート）: 増える変異 81 個のうち生存 14、
# 等価はそのうち 3（キャッシュの早期 return / 読む前の間引きの continue / 後段のガードが拾う
# continue）。残り 11 はテストの穴だった。条件式の規則は 24 個とも殺された
PY_RULES: list[tuple[str, str, str]] = [
    # `not in` / `is not` は上の RULES が持つ（ここで外すと二重になる）。`-not` は find の述語
    (r"(?<![-\w.])(?<!\bis )not\b(?!\s+in\b)\s*", "", "not を外す（条件を反転）"),
    (r"(?<![.\w])any\(", "all(", "any を all に（存在を全称に）"),
    (r"(?<![.\w])all\(", "any(", "all を any に（全称を存在に）"),
    (r"\bcontinue\b", "pass", "continue を pass に（読み飛ばしを外す）"),
    # 条件式 `a if c else b` の `c` を反転する。`if not` は上の not の規則が持つ。
    # 直前が「非空白 + 空白」の `if` だけを見るので、行頭の if 文には当たらない
    (r"(?<=\S )if\b(?!\s+not\b)(?=.*\belse\b)", "if not", "条件式の条件を反転（if → if not）"),
]
SH_RULES: list[tuple[str, str, str]] = [
    (r"\bcontinue\b", ":", "continue を : に（読み飛ばしを外す）"),
]
EARLY_RETURN_RULE = "if 直下の return を pass に（早期 return を外す）"
COMMENT_ONLY = re.compile(r"^\s*(#|//)")
# 変異を意図的に除外する印（等価変異・到達不能な分岐に付ける）。理由を必ず書かせる。
# **変異させたいコード行と同じ行に置く**（直前の行に書いても効かない）
SKIP_MARK = re.compile(r"#\s*mutation-ok:\s*\S")


@dataclass
class Mutant:
    path: Path
    lineno: int          # 1-origin
    original: str
    mutated: str
    rule: str


OWNER_ENV = "MUTATION_TEST_OWNER_PID"

# **`--test-cmd` は shell を通さず `split()` して直接 spawn する**（`run` / `run_group`）。
# `cd foo && pytest` のような shell 構文を渡すと、先頭の `cd`（macOS の `/usr/bin/cd`）が
# 引数を無視して **exit 0** で終わり、baseline が 0.0s で緑・全変異 SURVIVED という嘘の
# 結果が出る（実測 2026-09-11）。**shell 演算子と先頭 cd を弾く** — split したトークンに
# 単独で現れるものだけを見る（`>>foo` のような連結は spawn しても無害に失敗して baseline が
# 赤になり既存のガードが拾う）。ディレクトリ移動は `--test-cmd "python3 -m unittest
# discover -s <dir> ..."` の `-s` で表す。
SHELL_OPERATOR_TOKENS = frozenset({"&&", "||", ";", "|", "&", ">", ">>", "<", "<<"})


def shell_cmd_reason(tokens: list[str]) -> str | None:
    """`--test-cmd` に shell を要する構文があれば理由を返す（無ければ None）."""
    if not tokens:
        return "空"
    bad = sorted({t for t in tokens if t in SHELL_OPERATOR_TOKENS})
    if bad:
        return "shell 演算子 %s を含む" % " ".join(bad)
    if tokens[0] == "cd":
        return "先頭が cd（ディレクトリ移動は discover の -s で表す）"
    return None


def run(cmd: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    # 所有者 pid を環境に載せる。テストコマンドがこのツール自身のテストを含むとき,
    # 子プロセスは「今まさに変異が当たっている最中」だと env だけで判定できる
    env = dict(os.environ, **{OWNER_ENV: str(os.getpid())})
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)


def run_group(cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    """テストコマンドを**独立したプロセスグループ**で走らせ、timeout ではグループごと殺す.

    **`subprocess.run(timeout=...)` は直接の子だけを殺す。** テストランナーが起動した
    孫（`bash <被験スクリプト>` 等）は生き残るので、**変異で無限ループ化した孫が
    そのまま回り続ける**。実測: `dirname .` が `.` を返し続ける変異体の
    `triage-signals.sh` が **12 本・4 時間**、各 14% CPU で残っていた（timeout した変異
    2 回ぶんの取りこぼしが積み上がったもの）。timeout は想定内の結果なので、
    後始末まで含めて想定内にする。

    `start_new_session=True` で子を新しいプロセスグループのリーダーにし、
    負の pid へシグナルを送ってグループ全体（孫・ひ孫を含む）を回収する。
    """
    env = dict(os.environ, **{OWNER_ENV: str(os.getpid())})
    with subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, env=env, start_new_session=True) as proc:
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            # グループを畳んでから残りの出力を回収する（`communicate` を呼ばないと
            # パイプが閉じられず ResourceWarning になる）
            try:
                out, err = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                out, err = "", ""
            raise subprocess.TimeoutExpired(cmd, timeout, output=out, stderr=err)
        return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def _kill_group(proc: subprocess.Popen) -> None:
    """プロセスグループへ TERM → （猶予後に）KILL を送る."""
    for sig, grace in ((signal.SIGTERM, 2.0), (signal.SIGKILL, 0.0)):
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, PermissionError):
            return          # 既に終了している / 送れない（グループが無い）
        if grace:
            try:
                proc.wait(timeout=grace)
                return      # TERM で畳めた
            except subprocess.TimeoutExpired:
                continue    # KILL へ進む


def clear_pycache() -> None:
    """**毎回消す**。stale bytecode は「全部検知した」という嘘の結果を返す（実測）."""
    for d in ROOT.rglob("__pycache__"):
        if ".git" not in d.parts:
            shutil.rmtree(d, ignore_errors=True)


def _rel(path: Path) -> str:
    """表示用の相対パス（ROOT 外でも落ちない）.

    `relative_to` は ROOT 外で `ValueError` を投げる。**tamper 経路のメッセージ組み立てで
    落ちると「復元していない / 元はこの行」という復旧情報が丸ごと消える**ので、
    表示は必ずここを通す。
    """
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def is_test_file(path: Path) -> bool:
    return bool(TEST_PATH_RE.search(_rel(path)))


def changed_lines(base: str) -> dict[Path, set[int]] | None:
    """`git diff` の**追加行**の行番号を新ファイル側で拾う（変更していない行は変異させない）.

    git diff が失敗したら None。**「変更行が無い」（空の dict）と区別する**: 範囲 0 個で exit 0 すると、
    nightly は範囲を回し切ったと判定して持ち越していた変異を捨てる（push 側のスモークも黙って緑になる）。
    """
    res = run(["git", "diff", "--unified=0", base], ROOT)
    if res.returncode != 0:
        return None
    out = res.stdout
    result: dict[Path, set[int]] = {}
    path: Path | None = None
    lineno = 0
    for line in out.splitlines():
        if line.startswith("+++ b/"):
            candidate = ROOT / line[6:]
            path = (candidate if candidate.suffix in TARGET_SUFFIXES
                    and not is_test_file(candidate) else None)
        elif line.startswith("@@") and path is not None:
            m = re.search(r"\+(\d+)", line)
            lineno = int(m.group(1)) if m else 0
        elif path is not None and line.startswith("+") and not line.startswith("+++"):
            result.setdefault(path, set()).add(lineno)
            lineno += 1
    return result


def untracked(path: Path) -> bool:
    """git 管理下のリポジトリで、まだ追跡されていないファイルか（全行が新規として数える）."""
    return run(["git", "ls-files", "--error-unmatch", "--", _rel(path)], ROOT).returncode != 0


def file_mode_breakdown(mutants: list[Mutant], base: str) -> str:
    """`--file` の変異のうち、`base` との差分の追加行に当たる数（GitHub issue #256）."""
    if run(["git", "rev-parse", "--is-inside-work-tree"], ROOT).returncode != 0:
        return "変更行: 判定できない（git 管理外）"
    changed = changed_lines(base)
    if changed is None:
        return f"変更行: 判定できない（git diff {base} が失敗）"
    new_files = {m.path for m in mutants if untracked(m.path)}
    hit = sum(1 for m in mutants if m.path in new_files or m.lineno in changed.get(m.path, ()))
    line = (f"変更行（--base {base} との差分の追加行・未追跡ファイル）{hit} 個 / "
            f"既存行 {len(mutants) - hit} 個")
    if not hit:
        line += ("\n  **変更行に当たる変異が 0 個**。変更を検証したいなら --file を外して"
                 f"差分モード（--base {base}）で回す")
    return line


TESTS_RAN_RE = re.compile(r"^Ran (\d+) tests? in ", re.M)


def tests_ran(output: str) -> int | None:
    """unittest の出力から走ったテストの件数を拾う（unittest 以外なら None）."""
    m = TESTS_RAN_RE.search(output)
    return int(m.group(1)) if m else None


def k_patterns(test_cmd: list[str]) -> list[str]:
    """`--test-cmd` の `-k` の値（unittest の -k は部分一致・大小区別あり）."""
    return [test_cmd[i + 1] for i, t in enumerate(test_cmd[:-1]) if t == "-k"]


def _looks_quoted(line: str, start: int) -> bool:
    """一致位置が引用符の内側か（近似）. 手前の未閉じクォートを数える."""
    head = line[:start]
    return head.count('"') % 2 == 1 or head.count("'") % 2 == 1


# シェルの `>` `<` はほぼ全部**リダイレクト**で、比較ではない（`2>/dev/null` `>>log` `&>`）。
# これを境界変異させると `2>=/dev/null` のような**構文的に別物**が生まれ、テストが落ちないので
# 「生存 = 未検証」の一覧に混ざる。生存リストは行動を促す信号なので、偽の生存を出さない。
# 比較として書けるのは `[[ a > b ]]` / `(( a > b ))` の中だけなので、そこだけ許可する。
SHELL_COMPARE_CONTEXT = re.compile(r"\[\[|\(\(")

# `-lt` / `-gt` / `-le` / `-ge` / `-eq` / `-ne` は**コマンドのフラグとしても同じ綴りで現れる**
# （`ls -lt` / `sort -n` 系）。フラグを変異させると `ls -le` のような**構文的には有効な別コマンド**が
# でき、テストは当然落ちないので「生存 = 未検証」の一覧に偽の行が並ぶ（実測: `measure-tokens.sh`
# の `ls -lt` が生存として報告された）。生存リストは行動を促す信号なので偽陽性を出さない。
# 比較として書けるのは `[ ... ]` / `[[ ... ]]` / `(( ... ))` / `test ...` の中だけなので、
# **同一行にそのいずれかが先行することを要求する**近似で絞る。
SHELL_TEST_CONTEXT = re.compile(r"\[\[?|\(\(|\btest\b")
SHELL_NUMERIC_OPS = frozenset({"-lt", "-le", "-gt", "-ge", "-eq", "-ne"})


def _is_shell_redirect(path: Path, line: str, start: int) -> bool:
    if path.suffix != ".sh":
        return False
    return not SHELL_COMPARE_CONTEXT.search(line[:start])


def _is_numeric_op_outside_a_test(line: str, start: int) -> bool:
    """`-lt` 等が test 式の外（コマンドのフラグ・文字列の一部）に現れているか.

    **ファイル種別で分岐しない。** `-lt` が比較演算子になるのは shell の test 式だけで、
    `.py` に現れる `-lt` は文字列の一部（shell コマンドを組む配列等）なので、
    どちらの言語でも「test 式の中でなければ変異させない」で正しい。
    種別で分けると `.py` 側の分岐が**どちらに倒しても結果が変わらない**行になり、
    その変異が生き残って偽の未検証として一覧に出る（実測でそうなった）。
    """
    return not SHELL_TEST_CONTEXT.search(line[:start])


def _code_end(line: str) -> int:
    """行末コメントの開始位置を返す（コメント内は変異させない）.

    初回実行で `FC_MIN_SCHEMA = 1    # …「>=」で前方互換…` の**コメント内の `>=`**を
    変異させ、当然テストが落ちない＝「生存」として報告した（等価変異のノイズ）。
    引用符の外に出た最初の `#` をコード終端とする近似で足りる。
    """
    in_s = in_d = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d and (i == 0 or line[i - 1].isspace()):
            # **直前が空白でない `#` はコメントではない**: bash の `$#`（位置パラメータ数）や
            # `${#arr[@]}`、`doc.md#anchor` が該当する。実測で `while [ $# -gt 0 ]` の `-gt` が
            # 丸ごと変異対象から外れており、**bash の fail-open ゲートの典型形が未計測**だった
            return i
    return len(line)


def _py_masked_spans(path: Path) -> dict[int, list[tuple[int, int]]] | None:
    """`.py` の文字列 / コメントの桁範囲を行ごとに返す（取れなければ None）.

    **複数行文字列は行内の近似では追えない**。docstring の散文にある `>=` や `True` を
    変異させると, 書き換えてもテストが落ちるはずがないので**定義上 100% 生存**し、
    唯一の指標である生存率を汚染する（実測で 2 個混入）。`tokenize` は stdlib なので
    依存を増やさずに正確に取れる。
    """
    try:
        with open(path, "rb") as f:
            return _masked_spans(tokenize.tokenize(f.readline))
    except (OSError, SyntaxError, tokenize.TokenError, UnicodeDecodeError):
        return None          # 取れないときは下の近似へフォールバック（黙って全許可にしない）


# **Python 3.12 以降の f-string は STRING ではなく START / MIDDLE / END に分かれて出る**ので、
# STRING だけを見ると f-string の中身（散文・正規表現）が変異対象に残る（3.14 で実測。CI は 3.12）。
# 開始から終了までを丸ごと伏せる。`{式}` の部分も伏せる側に倒す（散文を変異させる偽の生存より、
# 式の変異を取りこぼす方を選ぶ）。t-string（3.14）も同じ形で出る
_FSTRING_START = {getattr(tokenize, n) for n in ("FSTRING_START", "TSTRING_START") if hasattr(tokenize, n)}
_FSTRING_END = {getattr(tokenize, n) for n in ("FSTRING_END", "TSTRING_END") if hasattr(tokenize, n)}


def _masked_spans(tokens) -> dict[int, list[tuple[int, int]]]:
    spans: dict[int, list[tuple[int, int]]] = {}
    opened: list[tuple[int, int]] = []       # 開いている f-string の開始位置（入れ子があるので積む）
    for tok in tokens:
        if tok.type in _FSTRING_START:
            opened.append(tok.start)
        elif tok.type in _FSTRING_END:
            start = opened.pop()
            if not opened:                   # 入れ子の内側は外側の範囲に含まれる
                _add_span(spans, start, tok.end)
        elif tok.type in (tokenize.STRING, tokenize.COMMENT) and not opened:
            _add_span(spans, tok.start, tok.end)
    return spans


def _add_span(spans: dict[int, list[tuple[int, int]]],
              start: tuple[int, int], end: tuple[int, int]) -> None:
    (srow, scol), (erow, ecol) = start, end
    for ln in range(srow, erow + 1):
        lo = scol if ln == srow else 0
        hi = ecol if ln == erow else 10 ** 9
        spans.setdefault(ln, []).append((lo, hi))


# `.sh` に埋め込まれた python の始まり。ヒアドキュメント（`python3 - <<'PY'`）と、
# 同じ行で閉じない `python3 -c '`（閉じる `'` のある行まで）の 2 形だけを見る。
# `<<<`（here-string）は 1 行で終わるので対象外
SH_PY_HEREDOC = re.compile(r"\bpython3?\b.*?(?<!<)<<(?!<)-?\s*(['\"]?)(\w+)\1")
SH_PY_DASH_C = re.compile(r"\bpython3?\b[^'#]*\s-c\s+'(?=[^']*$)")


def _sh_python_lines(lines: list[str]) -> dict[int, list[tuple[int, int]] | None]:
    """`.sh` に埋め込まれた python の行 → その行の文字列 / コメントの桁範囲.

    **docstring の散文を変異させない**ためと、**python の規則を python にだけ当てる**ため。
    行内の近似（`_code_end` / `_looks_quoted`）は複数行文字列を追えないので、ヒアドキュメントの
    docstring にある `>=` や `not` が変異して定義上 100% 生存する（CLAUDE.md Gotchas
    「散文に `>=` / `<=` を書かない」の原因）。埋め込み部分を切り出して tokenize する。

    `python3 -c '...'` の開始行・終了行は bash と python が同居するので python の行に
    数えない（近似のまま bash 側の規則だけが当たる）。tokenize できない塊（unquoted の
    ヒアドキュメントで `$x` を展開している等）は値を None にして近似へ落とす。
    """
    result: dict[int, list[tuple[int, int]] | None] = {}
    i = 0
    while i < len(lines):
        region = _python_region_at(lines, i)
        if region is None:
            i += 1
        else:
            body, offset, end = region
            try:
                spans = _masked_spans(tokenize.generate_tokens(
                    io.StringIO("".join(b + "\n" for b in body)).readline))
            except (SyntaxError, tokenize.TokenError):
                spans = None
            for j in range(i + 1, end):
                # body 内の行番号は j - offset（heredoc は次の行が 1 行目、-c は開始行が 1 行目）
                result[j + 1] = None if spans is None else spans.get(j - offset, [])
            i = end + 1
    return result


def _python_region_at(lines: list[str], i: int) -> tuple[list[str], int, int] | None:
    """`lines[i]` が埋め込み python の開始行なら (tokenize に渡す行, 行番号の差, 終端の添字)."""
    code = lines[i][:_code_end(lines[i])]
    heredoc = SH_PY_HEREDOC.search(code)
    if heredoc:
        end = next((j for j in range(i + 1, len(lines))
                    if lines[j].strip() == heredoc.group(2)), len(lines))
        return lines[i + 1:end], i, end
    dash_c = SH_PY_DASH_C.search(code)
    end = next((j for j in range(i + 1, len(lines)) if "'" in lines[j]), None) if dash_c else None
    if end is None:
        return None
    # 開始行の残りと終了行の `'` より前も tokenize には渡す（文の途中で切ると落ちる）
    return [lines[i][dash_c.end():], *lines[i + 1:end], lines[end][:lines[end].index("'")]], i - 1, end


def spread(mutants: list[Mutant]) -> list[Mutant]:
    """ファイルを丸に並べ替える（`--max` で切ったときに 1 ファイルへ偏らせないため）.

    `build_mutants` はファイル順・行順に積むので、先頭から `--max` 件を採ると
    **アルファベット順で先に来るファイルだけ**を見た結果になる。変更が複数ファイルに
    またがる回ほど偏りが効くので、ファイル横断で 1 個ずつ拾う順序に直す。
    **決定的**（`sorted` のみ。乱択にすると CI の再現性が消える）。
    """
    by_file: dict[Path, list[Mutant]] = {}
    for m in mutants:
        by_file.setdefault(m.path, []).append(m)
    out: list[Mutant] = []
    while any(by_file.values()):
        for path in sorted(by_file):
            if by_file[path]:
                out.append(by_file[path].pop(0))
    return out


RETURN_LINE = re.compile(r"^(\s*)return\b")
IF_HEADER = re.compile(r"^\s*(?:if|elif)\b.*:$")
INLINE_IF_RETURN = re.compile(r"^(\s*(?:if|elif)\b.*:\s*)return\b")
BRACKET_DEPTH = {"(": 1, "[": 1, "{": 1, ")": -1, "]": -1, "}": -1}


def _code_only(line: str, spans: list[tuple[int, int]] | None) -> str:
    """文字列 / コメントを空白に潰した行（括弧の数え上げ用。spans が無ければ近似）."""
    if spans is None:
        return line[:_code_end(line)]
    chars = list(line)
    for lo, hi in spans:
        for k in range(lo, min(hi, len(chars))):
            chars[k] = " "
    return "".join(chars)


def _early_return(lines: list[str], lineno: int,
                  py_spans: dict[int, list[tuple[int, int]] | None]) -> str | None:
    """if 直下の `return` を `pass` にした行を返す（当たらなければ None）.

    正規表現 1 本では書けない（直前の行が if であることを見る）ので RULES の外に置く。
    **return の文がその行で閉じていることを要求する** — 複数行にまたがる return の
    1 行目だけを `pass` にすると構文エラーの変異（invalid）になり、CI で 1 変異ぶんの
    スイート実行（実測 約 5 分）を捨てる。
    """
    line = lines[lineno - 1]
    code = _code_only(line, py_spans.get(lineno))
    if sum(BRACKET_DEPTH.get(c, 0) for c in code) != 0 or code.rstrip().endswith("\\"):
        return None
    inline = INLINE_IF_RETURN.match(code)
    if inline:
        return line[:inline.end(1)] + "pass"     # `code` は文字列を潰してあるので元の行から切る
    m = RETURN_LINE.match(code)
    prev = next((k for k in range(lineno - 1, 0, -1)
                 if lines[k - 1].strip() and not COMMENT_ONLY.match(lines[k - 1])), None)
    if not m or prev is None:
        return None
    # インデントは比べない: 妥当な Python なら if ヘッダの次の文は必ずその本体
    if not IF_HEADER.match(_code_only(lines[prev - 1], py_spans.get(prev)).rstrip()):
        return None
    return m.group(1) + "pass"


def build_mutants(targets: dict[Path, set[int]]) -> list[Mutant]:
    mutants: list[Mutant] = []
    for path in sorted(targets):
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        # 行番号 → python の行ならその行の文字列 / コメントの桁範囲（tokenize できなければ None）。
        # **キーに無い行は python ではない**（`.sh` の bash 部分）
        if path.suffix == ".py":
            masked = _py_masked_spans(path)
            py_spans = {ln: None if masked is None else masked.get(ln, [])
                        for ln in range(1, len(lines) + 1)}
        else:
            py_spans = _sh_python_lines(lines)
        for lineno in sorted(targets[path]):
            if lineno < 1 or lineno > len(lines):
                continue
            line = lines[lineno - 1]
            if COMMENT_ONLY.match(line) or SKIP_MARK.search(line):
                continue
            is_py = lineno in py_spans
            line_spans = py_spans.get(lineno)
            code_end = len(line) if line_spans is not None else _code_end(line)
            for pattern, repl, desc in RULES + (PY_RULES if is_py else SH_RULES):
                for m in re.finditer(pattern, line):
                    if line_spans is not None:
                        if any(lo <= m.start() < hi for lo, hi in line_spans):
                            continue     # 文字列 / コメントの中（tokenize で確定）
                    elif m.start() >= code_end or _looks_quoted(line, m.start()):
                        continue         # 近似（bash とトークナイズ不能な python）
                    if (m.group(0) in ("<", ">") and not is_py
                            and _is_shell_redirect(path, line, m.start())):
                        continue
                    if (m.group(0) in SHELL_NUMERIC_OPS
                            and _is_numeric_op_outside_a_test(line, m.start())):
                        continue
                    mutated = line[:m.start()] + repl + line[m.end():]
                    if mutated == line:
                        continue
                    mutants.append(Mutant(path, lineno, line, mutated, desc))
                    break        # **1 規則につき最初の 1 箇所だけ**。外側の規則のループは回るので
                                 # 1 行から規則数ぶんの変異が出る（実測 4 個 / RULES は 20 本）。
                                 # 同じ行に同一規則が 2 回あると 2 個目は未検証になる
            mutated = _early_return(lines, lineno, py_spans) if is_py else None
            if mutated is not None:
                mutants.append(Mutant(path, lineno, line, mutated, EARLY_RETURN_RULE))
    return mutants


BLAME_HEADER = re.compile(r"^([0-9a-f]{40}) (\d+) (\d+)(?: \d+)?$")


def _blame_origins(path: Path) -> dict[int, tuple[str, str, str]]:
    """行番号 → (その行を入れたコミット, そのコミットでのパス, そのコミットでの行番号)。未コミットの行は含めない."""
    res = run(["git", "blame", "--line-porcelain", "--", _rel(path)], ROOT)
    if res.returncode != 0:
        print(f"WARN: {_rel(path)} を blame できない（未追跡など）。行番号と内容で同定する（行がずれると"
              "回し直しになる）", file=sys.stderr)
        return {}
    origins: dict[int, tuple[str, str, str]] = {}
    header: tuple[str, str, int] | None = None
    for line in res.stdout.splitlines():
        m = BLAME_HEADER.match(line)
        if m:
            header = (m.group(1), m.group(2), int(m.group(3)))
        elif line.startswith("filename ") and header is not None:
            sha, orig, final = header
            if sha.strip("0"):           # 全桁 0 は未コミットの行
                origins[final] = (sha, line[len("filename "):], orig)
    return origins


def mutant_keys(mutants: list[Mutant]) -> dict[int, str]:
    """id(変異) → 晩をまたいで同じ変異を同定するキー（nightly の持ち越し / GitHub issue #288）.

    **行の由来（blame）で同定する**。行番号は上に行が足されるとずれ、行の内容は同じ文字列の行が複数
    あると衝突する（片方を回すと残りが未検証のまま済み扱いになる）。由来のコミット・パス・行番号は行ごとに
    一意で、ファイルの rename も blame が追う。行を書き換えた・整形した・履歴を書き換えたときは新しいキーに
    なって再実行される（安全側）。未コミットの行（手元の実行）と blame できない行は行番号と内容で同定する
    （内容だけだと同じ文字列の行が衝突する）。規則の説明文はキーに入れない（文言を直しただけで持ち越しが
    全部回し直しになる）。
    """
    origins: dict[Path, dict[int, tuple[str, str, str]]] = {}
    keys: dict[int, str] = {}
    for m in mutants:
        if m.path not in origins:
            origins[m.path] = _blame_origins(m.path)
        origin = origins[m.path].get(m.lineno) or ("worktree", _rel(m.path), str(m.lineno), m.original)
        keys[id(m)] = hashlib.sha1("\0".join((*origin, m.mutated)).encode("utf-8")).hexdigest()[:16]
    return keys


class ExternalEditError(RuntimeError):
    """変異中に対象ファイルが外部から変更された（復元すると他所の編集を消すので中断する）."""


# 変異中の原本をディスクへ退避する場所。**プロセスメモリだけでは足りない** —
# 復元は `try/finally` に閉じているので Python 例外は全部通るが、**SIGTERM / SIGHUP では
# `finally` が走らない**。露出窓は狭いレースではなく実行時間のほぼ全体（実測 baseline 9 秒 ×
# 既定 25 = 約 4 分）で、対象は既定で**未コミットの作業ファイル**なので `git checkout` で
# 戻せない。しかも変異は意図的に fail-open 方向なので、残っても **survived 型はテストが
# 定義上検知しない**（緑のまま commit される）。
JOURNAL = ".mutation-test-journal.json"


def _journal_path() -> Path:
    return ROOT / JOURNAL


def _journal_write(path: Path, original: bytes) -> None:
    _journal_path().write_text(json.dumps({
        "path": _rel(path), "mode": stat.S_IMODE(path.stat().st_mode),
        "original_b64": base64.b64encode(original).decode("ascii"),
        "pid": os.getpid(),
    }), encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # 別ユーザー所有の生存プロセス。反転すると「他人の run を生存扱いしない」＝
        # 安全側から危険側に倒れるが、単一ユーザーの作業ツリーでは到達しない分岐
        return True  # mutation-ok: 別ユーザー所有の生存 pid をテストから用意できない
    return True


def _journal_clear() -> None:
    _journal_path().unlink(missing_ok=True)


def recover_from_journal() -> bool:
    """前回の run が中断して変異が残っていれば戻す（戻したら True）."""
    # **親 run の実行中は何もしない**（env は変異の影響を受けないので, 復旧述語そのものが
    # 変異している最中でも成立する。pid 生存判定は SIGKILL 経路のための第 2 の網）
    owner_env = os.environ.get(OWNER_ENV)
    if owner_env and owner_env != str(os.getpid()):
        return False
    jp = _journal_path()
    if not jp.is_file():
        return False
    try:
        data = json.loads(jp.read_text(encoding="utf-8"))
        target = ROOT / data["path"]
        original = base64.b64decode(data["original_b64"])
    except (ValueError, KeyError, OSError) as e:
        print(f"FATAL: ジャーナルを読めない（手で確認すること）: {jp} ({e})", file=sys.stderr)
        return False
    # **実行中の run が置いたジャーナルには触らない**。テストコマンドがこのツール自身の
    # テストを含む場合（このリポジトリがまさにそう）、子プロセスの起動時復旧が
    # **親が今まさに当てている変異を横から戻す** — 親からは「外部編集」に見えて計測が中断する。
    owner = data.get("pid")
    if isinstance(owner, int) and owner != os.getpid() and _pid_alive(owner):
        return False
    if not target.is_file():
        print(f"WARN: ジャーナルの対象が無い: {data['path']}", file=sys.stderr)
        _journal_clear()
        return False
    if target.read_bytes() == original:
        _journal_clear()          # 既に戻っている（正常終了直後にジャーナルだけ残った等）
        return False
    _atomic_write(target, original)
    os.chmod(target, data.get("mode", 0o644))
    _journal_clear()
    print(f"前回の中断で残っていた変異を {data['path']} から復元した", file=sys.stderr)
    return True


def _atomic_write(path: Path, data: bytes) -> None:
    """同一ディレクトリの一時ファイルへ書いて `os.replace` で差し替える.

    `write_text` は先に truncate するので, **書き込み途中で失敗すると原本が切り詰まった
    まま残る**（権限 / ENOSPC）。このツールは未コミットの作業が入ったファイルを触るので、
    部分書き込みで原本を壊す経路を構造的に消しておく。
    """
    tmp = path.with_name(path.name + ".mutant.tmp")
    # **モードを引き継ぐ**（実測: 引き継がないと 0o755 → 0o644）。`write_bytes` は新しい inode を
    # umask 既定で作り `os.replace` がメタデータごと差し替えるので、**バイト列は戻るがモードは戻らない**。
    # `.sh` の実行ビットが落ちると `.githooks/pre-commit` の `-x` ゲートが**無言で**素通りする＝
    # 「新しいガードを足す作業そのものが既存のガードを外す」
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    try:
        tmp.write_bytes(data)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def apply_and_test(mutant: Mutant, test_cmd: list[str], timeout: int) -> str:
    """変異を当ててテストを走らせ, `killed` / `survived` / `invalid` / `timeout` を返す（1 段だけの judge）."""
    return judge(mutant, [(test_cmd, timeout)], None)[0]


def judge(mutant: Mutant, stages: list[tuple[list[str], int]],
          deadline: float | None) -> tuple[str, int, bool]:
    """変異を 1 回当てたまま `stages` を順に回し、(判定, 決めた段, その段の timeout を予算で削ったか) を返す.

    **前の段は落ちたときだけ決着させる**（関連テストを先に回す 2 段判定 / GitHub issue #288）。テストが
    決定的で他モジュールの副作用に依存しなければ「関連テストで落ちる ⇒ フルスイートでも落ちる」ので killed は
    確定する（invalid と killed の分かれ方は、最初に落ちるテストが段で違うので変わりうる）。前の段が通った・
    1 件も走らなかった（`-k` が当たらない）・時間切れのときは次の段へ進み、生存と timeout は最後の段
    （フルスイート）でだけ確定する。構文エラーはどの段でも invalid で確定する。
    `deadline`（monotonic）があれば、各段の timeout をその時点の残りで頭打ちにする。

    **復元は元バイト列の書き戻し**（`git checkout` は未コミット変更を飛ばす / 実測で事故）。

    **書き込みの成否を分けて扱う**: 書けていない回に「外部から変更された」と報告すると
    **原因を誤って断定し、真の例外（PermissionError 等）を握り潰す**（`SystemExit` は
    CPython が特別扱いするので `__context__` も表示されない / 実測）。`wrote` が真の
    ときだけ整合を見る。

    **`finally` からは例外を投げない**: 投げると `try` 側の保留中の return（確定済みの
    verdict）や進行中の例外を静かに置き換える。フラグに退避して `finally` を抜けてから送出する。
    """
    original_bytes = mutant.path.read_bytes()
    lines = original_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
    idx = mutant.lineno - 1
    eol = "\n" if lines[idx].endswith("\n") else ""
    lines[idx] = mutant.mutated + eol
    mutated_bytes = "".join(lines).encode("utf-8")
    wrote = tampered = False
    verdict, decided, capped = "invalid", 0, False   # mutation-ok: 段は 1 つ以上あり、ループで必ず上書きする
    try:
        _journal_write(mutant.path, original_bytes)   # **書く前に**退避する（順序が肝）
        _atomic_write(mutant.path, mutated_bytes)
        wrote = True
        clear_pycache()
        for decided, (test_cmd, timeout) in enumerate(stages):
            last = decided == len(stages) - 1
            effective = timeout if deadline is None else min(timeout, max(1, int(deadline - time.monotonic())))
            capped = effective < timeout
            try:
                # **プロセスグループごと起動する**（timeout 時に孫まで回収するため。`run` では
                # 直接の子だけが死に、無限ループ化した被験スクリプトが残る — `run_group` の注記）
                proc = run_group(test_cmd, ROOT, timeout=effective)
            except subprocess.TimeoutExpired:
                # **hang は想定内**: 変異規則に `break` → `continue`（打ち切りを外す）があり、
                # 終端が `break` だけのループに当てると無限ループになる。1 個の hang で run 全体を
                # 落とすと残りの変異が未実行のままサマリも出ない
                verdict = "timeout"
                if capped:
                    break    # 予算で切った。次の段に進んでも残りが無い
                continue
            blob = proc.stdout + proc.stderr
            if proc.returncode == 0:
                verdict = "survived"
                continue
            # 構文エラーで落ちた変異は「テストが殺した」とは言えないので分けて数える
            if "SyntaxError" in blob or "syntax error" in blob:
                verdict = "invalid"
                break
            if not last and tests_ran(blob) == 0:
                continue     # 関連テストが 1 件も走らなかった（unittest は 0 件で exit 5）
            verdict = "killed"
            break
    finally:
        if wrote:
            if mutant.path.read_bytes() == mutated_bytes:
                _atomic_write(mutant.path, original_bytes)
            else:
                tampered = True
        if not tampered:
            _journal_clear()      # 復元できた回だけ消す（残れば次回の起動時に拾う）
        clear_pycache()
    if tampered:
        # **復旧に必要な情報を全部書く**。「`git diff` で確認」だけだと、実際に見落として
        # 変異が残ったまま次の run の baseline を壊した（実測）。行番号と前後の実テキストを出す
        raise ExternalEditError(
            f"変異中に {_rel(mutant.path)} が外部から変更された。\n"
            "  復元すると他所の編集を消すので**書き戻していない**。\n"
            f"  **{_rel(mutant.path)}:{mutant.lineno} に変異が当たったままの可能性がある**"
            f"（{mutant.rule}）:\n"
            f"    元:   {mutant.original.strip()}\n"
            f"    変異: {mutant.mutated.strip()}\n"
            "  上の「元」に戻してから再実行すること。**実行中は対象ファイルを編集しない**。"
        )
    return verdict, decided, capped


def discover_dir(test_cmd: list[str]) -> str | None:
    """`--test-cmd` が素の `<python> -m unittest discover -s <dir> [-f]` なら dir、それ以外は None.

    **絞り込み（`-p` / `-k` / `-t` / pattern）があるときは使わない**: 1 段目は `-k <関連モジュール>` で組み直すので、
    利用者の絞り込みの外にあるテストまで回す。そこで落ちた変異を killed と確定すると、絞り込んだフルスイート
    では生存するはずの変異が消える（unittest の `-k` は複数指定で OR になり、AND で足せない）。
    """
    core = [t for t in test_cmd if t != "-f"]
    if len(core) == 6 and core[1:5] == ["-m", "unittest", "discover", "-s"]:
        return core[5]
    return None


def _strings_of(text: str) -> str:
    """python のソースから、docstring を除いた文字列定数を連結して返す（読めなければ空）.

    テストがスクリプトを叩くときはパスを文字列で持つ（`ROOT / "scripts" / "x.py"`）。docstring とコメントの
    言及（「実行: python3 x.py」）まで数えると、関係の無いモジュールを関連テストに入れて 1 段目が遅くなる。
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ""
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docs.add(id(first.value))
    return "\n".join(n.value for n in ast.walk(tree)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs)


def _imports(stem: str) -> re.Pattern[str]:
    """`stem` を import する行（`from x import` / `import x` / `from pkg.x import` / `from pkg import x`）."""
    s = re.escape(stem)
    return re.compile(rf"(?m)^[ \t]*(?:from[ \t]+(?:[\w.]+\.)?{s}[ \t]+import\b|import[ \t]+(?:[\w.]+\.)?{s}\b"
                      rf"|from[ \t]+[\w.]+[ \t]+import[ \t]+[^\n]*\b{s}\b)")


def related_modules(path: Path, strings: dict[str, str], raws: dict[str, str] | None = None) -> list[str]:
    """`path` を参照するテストモジュール（`strings` は モジュール名 → docstring を除いた文字列定数、
    `raws` は モジュール名 → ソース全体。import の照合に使う）.

    参照はファイル名と（`.py` なら）import で探し、同じ最上位ディレクトリ（プラグイン）の中で `path` を
    参照しているファイルを 1 段たどる（`detect-backend.sh` はテストから直接は呼ばれず、`inject-rules.sh`
    経由で効く。`lib/report_counts.py` は `review-retro.sh` の埋め込み python が import する）。
    **外れても生存か killed かは変わらない** — 関連テストで落ちなければフルスイートで確かめる。外れると遅くなるだけ。
    """
    via = [path]
    parts = path.relative_to(ROOT).parts if path.is_relative_to(ROOT) else ()
    own = _imports(path.stem) if path.suffix == ".py" else None
    for other in sorted((ROOT / parts[0]).rglob("*")) if parts else []:
        if other.suffix not in TARGET_SUFFIXES or is_test_file(other):
            continue
        try:
            text = other.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue       # 拡張子が .sh のディレクトリなど
        if path.name in text or (own is not None and own.search(text)):
            via.append(other)
    names = {v.name for v in via}
    imports = [_imports(v.stem) for v in via if v.suffix == ".py"]
    raws = raws or {}
    return sorted(mod for mod, text in strings.items()
                  if any(n in text for n in names) or any(r.search(raws.get(mod, "")) for r in imports))


class Related:
    """変異したファイルごとの 1 段目（関連テストだけを -f で回すコマンドと timeout）を、初めて要るときに組む.

    **関連テストの組ごとに、変異前に 1 回回して緑を確かめる**（赤い・1 件も走らない組を 1 段目に使うと、
    どの変異も「落ちた」に見える）。**フルスイートの半分を超える組は使わない**（生存する変異は 1 段目と
    フルスイートの両方を払うので、ほぼ 2 倍かかる）。予算で手が届かないファイルの分まで先払いしないよう、
    組むのは初めてそのファイルの変異を回す直前にする。使えないファイルはフルスイートだけで判定する。
    """

    def __init__(self, test_cmd: list[str], full_sec: float, timeout: int, deadline: float | None) -> None:
        self.tests_rel = discover_dir(test_cmd)
        self.python, self.full_sec, self.timeout, self.deadline = test_cmd[0], full_sec, timeout, deadline
        self.strings: dict[str, str] = {}
        self.raws: dict[str, str] = {}
        self.by_path: dict[Path, tuple[list[str], int] | None] = {}
        self.by_set: dict[tuple[str, ...], tuple[list[str], int] | None] = {}
        if self.tests_rel is None:
            print("WARN: --related-first は --test-cmd が素の unittest discover -s <dir>（-f は可）のときだけ効く。"
                  "フルスイートで判定する")
            return
        for f in sorted((ROOT / self.tests_rel).glob("test_*.py")):
            try:
                raw = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            self.raws[f.stem], self.strings[f.stem] = raw, _strings_of(raw)

    def stage(self, path: Path) -> tuple[list[str], int] | None:
        if self.tests_rel is None:
            return None
        if path not in self.by_path:
            self.by_path[path] = self._build(path)
        return self.by_path[path]

    def _build(self, path: Path) -> tuple[list[str], int] | None:
        mods = tuple(related_modules(path, self.strings, self.raws))
        if not mods:
            print(f"  関連テスト {_rel(path)}: 見つからない。フルスイートで判定する")
            return None
        if mods in self.by_set:
            return self.by_set[mods]
        cmd = [self.python, "-m", "unittest", "discover", "-s", self.tests_rel, "-f"]
        for mod in mods:
            cmd += ["-k", mod + ".*"]
        limit = BASELINE_TIMEOUT if self.deadline is None else \
            min(BASELINE_TIMEOUT, max(1, int(self.deadline - time.monotonic())))
        t0 = time.monotonic()
        try:
            res = run_group(cmd, ROOT, timeout=limit)    # timeout で孫まで回収する（`run_group` の注記）
        except subprocess.TimeoutExpired:
            res = None
        sec = time.monotonic() - t0
        n = tests_ran(res.stdout + res.stderr) if res is not None else None
        if res is None or res.returncode != 0 or not n:
            got = None
            print(f"  関連テスト {', '.join(mods)}: 変異前に緑でない・走らない。フルスイートで判定する")
        elif sec > self.full_sec / 2:     # mutation-ok: 実測の秒数がちょうど半分に一致する境界は意味を持たない
            got = None
            print(f"  関連テスト {', '.join(mods)}: baseline {sec:.1f}s がフルスイートの半分を超える。"
                  "フルスイートだけで判定する")
        else:
            got = (cmd, self.timeout or max(30, int(sec * 5) + 1))
            print(f"  関連テスト {', '.join(mods)}: baseline {sec:.1f}s・{n} 件")
        self.by_set[mods] = got
        return got


def over_budget(elapsed: float, durations: list[float], baseline_sec: float,
                budget: float) -> bool:
    """次の 1 変異を始めると時間予算を超えるか（`budget` が 0 以下なら無制限）.

    1 変異の見積もりは実行済みの平均、まだ無ければ baseline。**予算は起動からの経過で測る**
    （baseline も含む）— 呼び出し側の上限（CI の job timeout）は壁時計で効くため。
    """
    if budget <= 0:
        return False
    estimate = sum(durations) / len(durations) if durations else baseline_sec
    return elapsed + estimate > budget


def _install_signal_handlers() -> None:
    """SIGTERM / SIGHUP で復元してから既定の終了に落とす.

    SIGINT は `KeyboardInterrupt` になるので `finally` が走る＝この経路は要らない。
    足りないのはハンドラ既定が「即死」の 2 つだけ。
    """
    def _handler(signum, _frame):
        recover_from_journal()
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)      # 既定の終了ステータス（128+N）を保つ

    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _handler)


def write_summary(path: str | None, *, generated: int, executed: int = 0, killed: int = 0,
                  survived: int = 0, invalid: int = 0, timeout: int = 0, unexecuted_max: int = 0,
                  unexecuted_budget: int = 0, aborted: bool = False, keys_all: list[str] | None = None,
                  keys_executed: list[str] | None = None, skipped_done: int = 0, related_decided: int = 0,
                  full_runs: int = 0) -> None:
    """集計を JSON で書く（GitHub issue #288）.

    `keys_all` は範囲内の全変異（済みで除外した分を含む）、`keys_executed` はこの回に判定まで回した変異の
    キー（`mutant_keys`）。nightly はこの 2 つで「済み」の集合を晩をまたいで持ち越す。
    変異が 1 個も無い早期 return では両方とも空（範囲を回し切った）。

    **未実行を件数として残す**のが目的。予算や上限で打ち切った変異は、生存が無ければ exit 0 で終わり、
    件数はログの 1 行にしか出ない。持ち越さなければ翌晩の範囲（この晩の head より後の変更行）からも外れ、誰も気づかないまま
    検証されずに消える。中断（外部編集）で回らなかった分は `generated - executed - 未実行` に残る。
    """
    if not path:
        return
    Path(path).write_text(json.dumps({
        "schema": 2, "generated": generated, "executed": executed, "killed": killed,
        "survived": survived, "invalid": invalid, "timeout": timeout,
        "unexecuted_max": unexecuted_max, "unexecuted_budget": unexecuted_budget, "aborted": aborted,
        "keys_all": keys_all or [], "keys_executed": keys_executed or [], "skipped_done": skipped_done,
        "related_decided": related_decided, "full_runs": full_runs,
    }, ensure_ascii=False) + "\n", encoding="utf-8")  # mutation-ok: 値は数と真偽値だけで非 ASCII を含まない


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--base", default="HEAD",
                    help="差分の起点（既定 HEAD）。この差分の追加行だけを変異させる。"
                         "--file と併用したときは、変更行に当たる変異の数を数える起点になる")
    ap.add_argument("--file", nargs="*", default=None,
                    help="差分ではなくファイル全体を対象にする。既存行にも --max の枠が使われる")
    ap.add_argument("--max", type=int, default=25,
                    help="実行する変異の上限（既定 25）。超えた分は「上限で未実行」として数える")
    ap.add_argument("--strict", action="store_true", help="生存した変異があれば exit 1（CI 用）")
    ap.add_argument("--test-cmd", default=DEFAULT_TEST_CMD,
                    help="テストコマンド。shell を通さず split して直接 spawn する（&& / | / 先頭の cd は "
                         "exit 2）。-k は unittest の部分一致なので、走った件数を baseline で確かめる")
    ap.add_argument("--timeout", type=int, default=0,
                    help="1 変異あたりの秒数（既定 0 = baseline 実測の 5 倍・最低 30 秒）")
    ap.add_argument("--budget-sec", type=float, default=0,
                    help="起動からの経過秒数の上限（既定 0 = 無制限）。次の 1 変異で超える見込みになったら"
                         "打ち切り、残りを「予算で未実行」として数える。1 変異の timeout は予算の残りで"
                         "頭打ちにし、baseline の timeout は予算まで延ばす")
    ap.add_argument("--related-first", action="store_true",
                    help="変異ごとに、変異したファイルを参照するテストモジュールだけを先に -f で回し、落ちれば killed と"
                         "確定する。通ったら --test-cmd で確かめる（テストが決定的で他モジュールの副作用に依存しなければ、"
                         "生存か killed かはフルスイートだけのときと同じ。--test-cmd が素の unittest discover -s のときだけ"
                         "効く / #288）")
    ap.add_argument("--skip-keys", default=None,
                    help="済みの変異のキー（1 行 1 つ）。範囲内でこれに当たる変異は回さない（nightly の"
                         "持ち越し / #288）")
    ap.add_argument("--summary-json", default=None,
                    help="集計（生成・実行・未実行の内訳）を JSON でこのパスに書く。exit 0 で終わる回は"
                         "必ず書く（nightly が「打ち切りで検証しなかった変異」を起票する判定に使う / #288）")
    args = ap.parse_args(argv)
    t_start = time.monotonic()

    # **変更行を数える前に**戻す（残った変異は diff に混ざり、対象行そのものを歪める）
    recover_from_journal()

    test_cmd = args.test_cmd.split()
    # **shell 構文は spawn では効かず、嘘の緑を返す**（上の SHELL_OPERATOR_TOKENS を参照）。
    # baseline チェックの前に弾く — 通すと baseline が 0.0s で緑になり全変異 SURVIVED になる
    _shell_reason = shell_cmd_reason(test_cmd)
    if _shell_reason is not None:
        print(f"FATAL: --test-cmd が {_shell_reason}。shell を通さず直接 spawn するので、"
              "shell 構文は静かに空振りして「全変異が生存」という嘘の結果になる。\n"
              '  例: --test-cmd "python3 -m unittest discover -s .claude-plugin/scripts/tests '
              '-p test_foo.py -k SomeTest"', file=sys.stderr)
        return 2
    if args.file:
        targets: dict[Path, set[int]] = {}
        for f in args.file:
            p = (ROOT / f).resolve()
            if p.suffix not in TARGET_SUFFIXES or not p.is_file():
                print(f"FATAL: 対象外か不在: {f}", file=sys.stderr)
                return 2
            if not p.is_relative_to(ROOT):
                # **ROOT 外を対象にしない**: テストコマンドは repo 固定なので全件 survived になり
                # 「生存率 100%」という無意味な指標が出るうえ、表示・復旧経路が ROOT 前提
                print(f"FATAL: リポジトリ外は対象にしない: {f}", file=sys.stderr)
                return 2
            if is_test_file(p):
                print(f"FATAL: テストファイルは変異対象にしない（判定者であって被験者ではない）: {f}",
                      file=sys.stderr)
                return 2
            targets[p] = set(range(1, len(p.read_text(errors='replace').splitlines()) + 1))
    else:
        targets = changed_lines(args.base)
        if targets is None:
            print(f"FATAL: git diff --unified=0 {args.base} が失敗した（起点が無い・git 管理外など）。"
                  "変更行なしとは読まない", file=sys.stderr)
            return 2

    if not targets:
        print(f"変異対象の変更行が無い（base={args.base}）。"
              "**テストファイルの変更のみでも同じ表示になる**（テストは変異対象外）。")
        write_summary(args.summary_json, generated=0)
        return 0
    every = build_mutants(targets)
    # キーは持ち越す回（nightly）にだけ要る。blame を 1 ファイル 1 回呼ぶ
    keys = mutant_keys(every) if (args.summary_json or args.skip_keys) else {}
    skipped_done = 0
    if args.skip_keys:
        try:
            done = set(Path(args.skip_keys).read_text(encoding="utf-8").split())
        except OSError as e:
            print(f"FATAL: --skip-keys を読めない: {e}", file=sys.stderr)
            return 2
        left = [m for m in every if keys[id(m)] not in done]
        skipped_done = len(every) - len(left)
    else:
        left = every
    keys_all = sorted(set(keys.values()))
    # **ファイル横断で丸めてから切る**。先頭から切ると変更が複数ファイルにまたがる回で
    # 1 ファイルに偏る（push 側の CI は `--max` を小さくしてあるので特に効く）
    mutants = spread(left)
    n_lines = sum(len(v) for v in targets.values())
    n_hit = len({(m.path, m.lineno) for m in every})
    if args.file:
        print(f"対象: ファイル全体（--file。差分ではない）— {n_lines} 行のうち変異規則に当たった行 {n_hit}")
    else:
        print(f"対象: 差分（--base {args.base}）の追加行 — {len(targets)} ファイル・"
              f"{n_lines} 行のうち変異規則に当たった行 {n_hit}")
    if skipped_done:
        print(f"済みで除外: {skipped_done} 個（前の晩までに実行した変異 / --skip-keys）")
    if not mutants and skipped_done:
        print("未実行の変異は無い（範囲内の変異はすべて前の晩までに実行した）")
        write_summary(args.summary_json, generated=0, keys_all=keys_all, skipped_done=skipped_done)
        return 0
    if not mutants:
        # **0 個を「殺した 0 / 生存 0」とだけ出すと検証済みに見える**（実測 2026-10-07: Python の
        # 分岐 55 行が変異 0 個のまま exit 0 で通った / PY_RULES の注記）。
        # 変異が無ければ baseline を回す意味も無い（CI では 1 回 約 5 分）
        print("変異 0 個: 対象の行はあるが、どの変異規則にも当たらなかった。"
              "**生存 0 ではなく未計測** — この変更をテストが検証しているかは分からない")
        write_summary(args.summary_json, generated=0)
        return 0

    # **最初にテストが緑であることを確認する**。赤い状態で変異させると全部 killed に見える
    clear_pycache()
    t0 = time.monotonic()
    try:
        # **予算があれば baseline の timeout も予算まで延ばす**。固定のままだと、スイートが伸びて timeout を
        # 超えた晩から毎晩 FATAL になり、変異を 1 個も回せない（BASELINE_TIMEOUT の注記）
        baseline = run(test_cmd, ROOT, timeout=max(BASELINE_TIMEOUT, int(args.budget_sec)))
    except subprocess.TimeoutExpired:
        print("FATAL: 変異前のテストがタイムアウトした（この状態では生存判定に意味がない）",
              file=sys.stderr)
        return 2
    baseline_sec = time.monotonic() - t0
    # **固定 600 秒だと 1 個の hang に 10 分払う**。実測の 5 倍を既定にする
    timeout = args.timeout or max(30, int(baseline_sec * 5) + 1)
    # **失敗判定より先に見る** — Python 3.12 以降の unittest は 0 件で exit 5 を返すので、
    # 後に置くと「テストが失敗している」という別の原因の表示になる
    n_ran = tests_ran(baseline.stdout + baseline.stderr)
    patterns = k_patterns(test_cmd)
    if n_ran == 0:
        print("FATAL: 変異前のテストが 1 件も走っていない（この状態では全変異が生存に見える）"
              + (f"。-k {' / '.join(patterns)} は unittest の部分一致で、どのテストにも当たらなかった"
                 if patterns else ""), file=sys.stderr)
        return 2
    if baseline.returncode != 0:
        print("FATAL: 変異前のテストが失敗している（この状態では生存判定に意味がない）",
              file=sys.stderr)
        print((baseline.stdout + baseline.stderr)[-800:], file=sys.stderr)
        return 2

    _install_signal_handlers()   # ここから先が変異を書く区間
    dropped = max(0, len(mutants) - args.max)
    mutants = mutants[: args.max]
    print(f"変異 {len(mutants)} 個を実行する"
          + (f"（上限 --max={args.max} により **{dropped} 個を対象外にした**）" if dropped else "")
          + f" / テスト: {args.test_cmd}（baseline {baseline_sec:.1f}s"
          + (f"・{n_ran} 件" if n_ran is not None else "") + f" / timeout {timeout}s）")
    if patterns:
        print(f"  テストの絞り込み: -k {' / '.join(patterns)}（部分一致）で {n_ran} 件。"
              "狙ったテストが入っていなければ、生存はテストの不足ではなく絞り込みの外れ")
    if args.file:
        print("  " + file_mode_breakdown(mutants, args.base))
    deadline = t_start + args.budget_sec if args.budget_sec > 0 else None
    related = Related(test_cmd, baseline_sec, args.timeout, deadline) if args.related_first else None

    survived: list[Mutant] = []
    timed_out: list[Mutant] = []
    executed_keys: list[str] = []
    related_decided = full_runs = 0
    killed = invalid = 0
    aborted = False
    # **CI の job timeout に殺されると結果が 1 件も残らない**（実測: nightly が 180 分で cancelled、
    # ログも空）。予算内で回せた分の結果を出して終わる
    durations: list[float] = []
    budget_left = 0
    for i, m in enumerate(mutants, 1):
        if over_budget(time.monotonic() - t_start, durations, baseline_sec, args.budget_sec):
            budget_left = len(mutants) - (i - 1)
            break
        first = related.stage(m.path) if related else None     # 組の baseline は 1 変異の所要に数えない
        t_m = time.monotonic()
        # **1 変異の timeout を予算の残りで頭打ちにする**。見積もりは平均なので、最後の 1 個が hang すると
        # 予算 + timeout（baseline の 5 倍）まで走り、CI の job timeout に当たって cancelled になる
        # （結果もログも残らない。180 分 / 9000 秒の設定では余裕が 1 分も無かった / #288）
        stages = ([first] if first else []) + [(test_cmd, timeout)]
        try:
            verdict, decided, capped = judge(m, stages, deadline)
        except ExternalEditError as e:
            # **ここまでの結果は捨てない**（残りが実行できないだけで、集計は意味を持つ）
            print(f"\nFATAL: {e}", file=sys.stderr)
            print(f"  実行済み {i - 1}/{len(mutants)} 件までの結果を出す", file=sys.stderr)
            aborted = True
            break
        if verdict == "timeout" and capped:
            # 予算の残りで切った回は本来の timeout に届いていない（無限ループ化とは言えない）。
            # 判定せず、この変異から後を予算で未実行に数える。どの変異で切ったかは回し直しの手がかりに残す
            print(f"  [{i}/{len(mutants)}] {'予算切れ':9s} {_rel(m.path)}:{m.lineno} — {m.rule}"
                  "（予算の残りで切った。未実行に数える）")
            budget_left = len(mutants) - (i - 1)
            break
        durations.append(time.monotonic() - t_m)
        if keys:
            executed_keys.append(keys[id(m)])
        if decided == len(stages) - 1:
            full_runs += 1
        else:
            related_decided += 1
        mark = {"survived": "SURVIVED", "killed": "killed",
                "invalid": "invalid", "timeout": "TIMEOUT"}[verdict]
        where = "（関連テスト）" if decided < len(stages) - 1 else ""
        print(f"  [{i}/{len(mutants)}] {mark:9s} {_rel(m.path)}:{m.lineno} — {m.rule}{where}")
        if verdict == "survived":
            survived.append(m)
        elif verdict == "killed":
            killed += 1
        elif verdict == "timeout":
            timed_out.append(m)
        else:
            invalid += 1

    scored = killed + len(survived)
    print()
    print(f"殺した {killed} / 生存 {len(survived)} / 構文エラーで対象外 {invalid}"
          + (f" / タイムアウト {len(timed_out)}" if timed_out else "")
          + (f" / 上限で未実行 {dropped}" if dropped else "")
          + (f" / 予算で未実行 {budget_left}" if budget_left else ""))
    if args.related_first:
        print(f"関連テストで決着 {related_decided} 個 / フルスイートで判定 {full_runs} 個")
    if budget_left:
        print(f"時間予算 --budget-sec={args.budget_sec:g} で打ち切った（未実行の {budget_left} 個は"
              "検証していない。予算を延ばすか --max を下げる）")
    if timed_out:
        print("タイムアウトした変異（**無限ループ化した可能性**。`--timeout` を延ばすか"
              "`# mutation-ok:` で外す）:")
        for m in timed_out:
            print(f"  {_rel(m.path)}:{m.lineno}  {m.rule}")
    if scored:
        print(f"生存率 {100.0 * len(survived) / scored:.0f}%"
              "（**テストが検証していない挙動の割合**。0% を目標にはしない — "
              "等価変異は `# mutation-ok: <理由>` で明示的に外す）")
    if survived:
        print()
        print("生存した変異（テストがこの変更を検知しない）:")
        for m in survived:
            print(f"  {_rel(m.path)}:{m.lineno}  {m.rule}")
            print(f"    - {m.original.strip()}")
            print(f"    + {m.mutated.strip()}")
    write_summary(args.summary_json, generated=len(mutants) + dropped,
                  executed=killed + len(survived) + invalid + len(timed_out),
                  killed=killed, survived=len(survived), invalid=invalid, timeout=len(timed_out),
                  unexecuted_max=dropped, unexecuted_budget=budget_left, aborted=aborted,
                  keys_all=keys_all, keys_executed=sorted(set(executed_keys)), skipped_done=skipped_done,
                  related_decided=related_decided, full_runs=full_runs)
    # **中断した回は必ず非ゼロ**（`--strict` 無しでも「全部走った」と読ませない）
    return 1 if (aborted or (survived and args.strict)) else 0


if __name__ == "__main__":
    sys.exit(main())
