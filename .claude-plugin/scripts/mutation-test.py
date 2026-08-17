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
  mutation-test.py --file a.py b.sh    # ファイル全体を対象にする（差分ではなく全行）
  mutation-test.py --max 40            # 変異の上限（既定 25。超過分は件数を報告する）
  mutation-test.py --strict            # 生存変異があれば exit 1（CI / gate 用）
  mutation-test.py --test-cmd "..."    # テストコマンドを差し替える

出力: 生存した変異（= テストが検証していない挙動）を file:line と変異内容つきで列挙する。
Exit code: 0（既定。`--strict` 指定時のみ生存で 1）/ 2（引数エラー・テストが最初から赤）
  外部編集を検知したときは**そこまでの結果を出してから** 1 で終わる（残りは未実行）。
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import tokenize
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEST_CMD = "python3 -m unittest discover -s .claude-plugin/scripts/tests"
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
COMMENT_ONLY = re.compile(r"^\s*(#|//)")
# 変異を意図的に除外する印（等価変異・到達不能な分岐に付ける）。理由を必ず書かせる
SKIP_MARK = re.compile(r"#\s*mutation-ok:\s*\S")


@dataclass
class Mutant:
    path: Path
    lineno: int          # 1-origin
    original: str
    mutated: str
    rule: str


def run(cmd: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def clear_pycache() -> None:
    """**毎回消す**。stale bytecode は「全部検知した」という嘘の結果を返す（実測）."""
    for d in ROOT.rglob("__pycache__"):
        if ".git" not in d.parts:
            shutil.rmtree(d, ignore_errors=True)


def is_test_file(path: Path) -> bool:
    try:
        rel = path.relative_to(ROOT).as_posix()
    except ValueError:
        rel = path.as_posix()
    return bool(TEST_PATH_RE.search(rel))


def changed_lines(base: str) -> dict[Path, set[int]]:
    """`git diff` の**追加行**の行番号を新ファイル側で拾う（変更していない行は変異させない）."""
    out = run(["git", "diff", "--unified=0", base], ROOT).stdout
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


def _looks_quoted(line: str, start: int) -> bool:
    """一致位置が引用符の内側か（近似）. 手前の未閉じクォートを数える."""
    head = line[:start]
    return head.count('"') % 2 == 1 or head.count("'") % 2 == 1


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
    spans: dict[int, list[tuple[int, int]]] = {}
    try:
        with open(path, "rb") as f:
            for tok in tokenize.tokenize(f.readline):
                if tok.type not in (tokenize.STRING, tokenize.COMMENT):
                    continue
                (srow, scol), (erow, ecol) = tok.start, tok.end
                for ln in range(srow, erow + 1):
                    lo = scol if ln == srow else 0
                    hi = ecol if ln == erow else 10 ** 9
                    spans.setdefault(ln, []).append((lo, hi))
    except (OSError, SyntaxError, tokenize.TokenError, UnicodeDecodeError):
        return None          # 取れないときは下の近似へフォールバック（黙って全許可にしない）
    return spans


def build_mutants(targets: dict[Path, set[int]]) -> list[Mutant]:
    mutants: list[Mutant] = []
    for path in sorted(targets):
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        masked = _py_masked_spans(path) if path.suffix == ".py" else None
        for lineno in sorted(targets[path]):
            if lineno < 1 or lineno > len(lines):
                continue
            line = lines[lineno - 1]
            if COMMENT_ONLY.match(line) or SKIP_MARK.search(line):
                continue
            code_end = len(line) if masked is not None else _code_end(line)
            line_spans = (masked or {}).get(lineno, [])
            for pattern, repl, desc in RULES:
                for m in re.finditer(pattern, line):
                    if masked is not None:
                        if any(lo <= m.start() < hi for lo, hi in line_spans):
                            continue     # 文字列 / コメントの中（tokenize で確定）
                    elif m.start() >= code_end or _looks_quoted(line, m.start()):
                        continue         # 近似（.sh とトークナイズ不能な .py）
                    mutated = line[:m.start()] + repl + line[m.end():]
                    if mutated == line:
                        continue
                    mutants.append(Mutant(path, lineno, line, mutated, desc))
                    break        # **1 規則につき最初の 1 箇所だけ**。外側の RULES ループは回るので
                                 # 1 行から規則数ぶんの変異が出る（実測 4 個 / 規則は 20 本）。
                                 # 同じ行に同一規則が 2 回あると 2 個目は未検証になる
    return mutants


class ExternalEditError(RuntimeError):
    """変異中に対象ファイルが外部から変更された（復元すると他所の編集を消すので中断する）."""


def _atomic_write(path: Path, data: bytes) -> None:
    """同一ディレクトリの一時ファイルへ書いて `os.replace` で差し替える.

    `write_text` は先に truncate するので, **書き込み途中で失敗すると原本が切り詰まった
    まま残る**（権限 / ENOSPC）。このツールは未コミットの作業が入ったファイルを触るので、
    部分書き込みで原本を壊す経路を構造的に消しておく。
    """
    tmp = path.with_name(path.name + ".mutant.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def apply_and_test(mutant: Mutant, test_cmd: list[str], timeout: int) -> str:
    """変異を当ててテストを走らせ, `killed` / `survived` / `invalid` / `timeout` を返す.

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
    verdict = "invalid"
    try:
        _atomic_write(mutant.path, mutated_bytes)
        wrote = True
        clear_pycache()
        try:
            proc = run(test_cmd, ROOT, timeout=timeout)
        except subprocess.TimeoutExpired:
            # **hang は想定内**: 変異規則に `break` → `continue`（打ち切りを外す）があり、
            # 終端が `break` だけのループに当てると無限ループになる。1 個の hang で run 全体を
            # 落とすと残りの変異が未実行のままサマリも出ない
            verdict = "timeout"
        else:
            if proc.returncode == 0:
                verdict = "survived"
            else:
                # 構文エラーで落ちた変異は「テストが殺した」とは言えないので分けて数える
                blob = proc.stdout + proc.stderr
                verdict = "invalid" if ("SyntaxError" in blob or "syntax error" in blob) else "killed"
    finally:
        if wrote:
            if mutant.path.read_bytes() == mutated_bytes:
                _atomic_write(mutant.path, original_bytes)
            else:
                tampered = True
        clear_pycache()
    if tampered:
        # **復旧に必要な情報を全部書く**。「`git diff` で確認」だけだと、実際に見落として
        # 変異が残ったまま次の run の baseline を壊した（実測）。行番号と前後の実テキストを出す
        raise ExternalEditError(
            f"変異中に {mutant.path.relative_to(ROOT)} が外部から変更された。\n"
            "  復元すると他所の編集を消すので**書き戻していない**。\n"
            f"  **{mutant.path.relative_to(ROOT)}:{mutant.lineno} に変異が当たったままの可能性がある**"
            f"（{mutant.rule}）:\n"
            f"    元:   {mutant.original.strip()}\n"
            f"    変異: {mutant.mutated.strip()}\n"
            "  上の「元」に戻してから再実行すること。**実行中は対象ファイルを編集しない**。"
        )
    return verdict


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--file", nargs="*", default=None)
    ap.add_argument("--max", type=int, default=25)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--test-cmd", default=DEFAULT_TEST_CMD)
    ap.add_argument("--timeout", type=int, default=0,
                    help="1 変異あたりの秒数（既定 0 = baseline 実測の 5 倍・最低 30 秒）")
    args = ap.parse_args()

    test_cmd = args.test_cmd.split()
    if args.file:
        targets: dict[Path, set[int]] = {}
        for f in args.file:
            p = (ROOT / f).resolve()
            if p.suffix not in TARGET_SUFFIXES or not p.is_file():
                print(f"FATAL: 対象外か不在: {f}", file=sys.stderr)
                return 2
            if is_test_file(p):
                print(f"FATAL: テストファイルは変異対象にしない（判定者であって被験者ではない）: {f}",
                      file=sys.stderr)
                return 2
            targets[p] = set(range(1, len(p.read_text(errors='replace').splitlines()) + 1))
    else:
        targets = changed_lines(args.base)

    if not targets:
        print(f"変異対象の変更行が無い（base={args.base}）。"
              "**テストファイルの変更のみでも同じ表示になる**（テストは変異対象外）。")
        return 0

    # **最初にテストが緑であることを確認する**。赤い状態で変異させると全部 killed に見える
    clear_pycache()
    t0 = time.monotonic()
    try:
        baseline = run(test_cmd, ROOT)
    except subprocess.TimeoutExpired:
        print("FATAL: 変異前のテストがタイムアウトした（この状態では生存判定に意味がない）",
              file=sys.stderr)
        return 2
    baseline_sec = time.monotonic() - t0
    # **固定 600 秒だと 1 個の hang に 10 分払う**。実測の 5 倍を既定にする
    timeout = args.timeout or max(30, int(baseline_sec * 5) + 1)
    if baseline.returncode != 0:
        print("FATAL: 変異前のテストが失敗している（この状態では生存判定に意味がない）",
              file=sys.stderr)
        print((baseline.stdout + baseline.stderr)[-800:], file=sys.stderr)
        return 2

    mutants = build_mutants(targets)
    dropped = max(0, len(mutants) - args.max)
    mutants = mutants[: args.max]
    print(f"変異 {len(mutants)} 個を実行する"
          + (f"（上限 --max={args.max} により **{dropped} 個を対象外にした**）" if dropped else "")
          + f" / テスト: {args.test_cmd}（baseline {baseline_sec:.1f}s / timeout {timeout}s）")

    survived: list[Mutant] = []
    timed_out: list[Mutant] = []
    killed = invalid = 0
    aborted = False
    for i, m in enumerate(mutants, 1):
        try:
            verdict = apply_and_test(m, test_cmd, timeout)
        except ExternalEditError as e:
            # **ここまでの結果は捨てない**（残りが実行できないだけで、集計は意味を持つ）
            print(f"\nFATAL: {e}", file=sys.stderr)
            print(f"  実行済み {i - 1}/{len(mutants)} 件までの結果を出す", file=sys.stderr)
            aborted = True
            break
        mark = {"survived": "SURVIVED", "killed": "killed",
                "invalid": "invalid", "timeout": "TIMEOUT"}[verdict]
        print(f"  [{i}/{len(mutants)}] {mark:9s} {m.path.relative_to(ROOT)}:{m.lineno} — {m.rule}")
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
          + (f" / 上限で未実行 {dropped}" if dropped else ""))
    if timed_out:
        print("タイムアウトした変異（**無限ループ化した可能性**。`--timeout` を延ばすか"
              "`# mutation-ok:` で外す）:")
        for m in timed_out:
            print(f"  {m.path.relative_to(ROOT)}:{m.lineno}  {m.rule}")
    if scored:
        print(f"生存率 {100.0 * len(survived) / scored:.0f}%"
              "（**テストが検証していない挙動の割合**。0% を目標にはしない — "
              "等価変異は `# mutation-ok: <理由>` で明示的に外す）")
    if survived:
        print()
        print("生存した変異（テストがこの変更を検知しない）:")
        for m in survived:
            print(f"  {m.path.relative_to(ROOT)}:{m.lineno}  {m.rule}")
            print(f"    - {m.original.strip()}")
            print(f"    + {m.mutated.strip()}")
    # **中断した回は必ず非ゼロ**（`--strict` 無しでも「全部走った」と読ませない）
    return 1 if (aborted or (survived and args.strict)) else 0


if __name__ == "__main__":
    sys.exit(main())
