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
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
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
        elif ch == "#" and not in_s and not in_d:
            return i
    return len(line)


def build_mutants(targets: dict[Path, set[int]]) -> list[Mutant]:
    mutants: list[Mutant] = []
    for path in sorted(targets):
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for lineno in sorted(targets[path]):
            if lineno < 1 or lineno > len(lines):
                continue
            line = lines[lineno - 1]
            if COMMENT_ONLY.match(line) or SKIP_MARK.search(line):
                continue
            code_end = _code_end(line)
            for pattern, repl, desc in RULES:
                for m in re.finditer(pattern, line):
                    if m.start() >= code_end or _looks_quoted(line, m.start()):
                        continue
                    mutated = line[:m.start()] + repl + line[m.end():]
                    if mutated == line:
                        continue
                    mutants.append(Mutant(path, lineno, line, mutated, desc))
                    break        # 1 行 1 規則まで（同じ行の全組み合わせは費用倒れ）
    return mutants


def apply_and_test(mutant: Mutant, test_cmd: list[str]) -> str:
    """変異を当ててテストを走らせ, `killed` / `survived` / `invalid` を返す.

    **復元は元バイト列の書き戻し**（`git checkout` は未コミット変更を飛ばす / 実測で事故）。
    """
    original_bytes = mutant.path.read_bytes()
    lines = original_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
    idx = mutant.lineno - 1
    eol = "\n" if lines[idx].endswith("\n") else ""
    lines[idx] = mutant.mutated + eol
    mutated_text = "".join(lines)
    try:
        mutant.path.write_text(mutated_text, encoding="utf-8")
        clear_pycache()
        proc = run(test_cmd, ROOT)
        if proc.returncode == 0:
            return "survived"
        # 構文エラーで落ちた変異は「テストが殺した」とは言えないので分けて数える
        blob = proc.stdout + proc.stderr
        if "SyntaxError" in blob or "syntax error" in blob:
            return "invalid"
        return "killed"
    finally:
        # **他所が同じファイルを編集していたら書き戻さない**（実測で事故った）:
        # バックグラウンドで走らせたまま同じファイルを編集すると, 復元が編集を上書きして
        # **黙って作業を消す**。復元前に「自分が書いた変異体のまま残っているか」を確認し、
        # 違えば触らずに loud に落とす。
        current = mutant.path.read_bytes()
        if current == mutated_text.encode("utf-8"):
            mutant.path.write_bytes(original_bytes)
        else:
            raise SystemExit(
                f"FATAL: 変異中に {mutant.path.relative_to(ROOT)} が外部から変更された。\n"
                "  復元すると他所の編集を消すので**書き戻していない**。"
                f"このファイルには {mutant.rule} の変異が当たったままの可能性がある。\n"
                "  `git diff` で確認すること。**変異テストの実行中は対象ファイルを編集しないこと**。"
            )
        clear_pycache()


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--file", nargs="*", default=None)
    ap.add_argument("--max", type=int, default=25)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--test-cmd", default=DEFAULT_TEST_CMD)
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
    baseline = run(test_cmd, ROOT)
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
          + f" / テスト: {args.test_cmd}")

    survived: list[Mutant] = []
    killed = invalid = 0
    for i, m in enumerate(mutants, 1):
        verdict = apply_and_test(m, test_cmd)
        mark = {"survived": "SURVIVED", "killed": "killed", "invalid": "invalid"}[verdict]
        print(f"  [{i}/{len(mutants)}] {mark:9s} {m.path.relative_to(ROOT)}:{m.lineno} — {m.rule}")
        if verdict == "survived":
            survived.append(m)
        elif verdict == "killed":
            killed += 1
        else:
            invalid += 1

    scored = killed + len(survived)
    print()
    print(f"殺した {killed} / 生存 {len(survived)} / 構文エラーで対象外 {invalid}"
          + (f" / 上限で未実行 {dropped}" if dropped else ""))
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
    return 1 if (survived and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
