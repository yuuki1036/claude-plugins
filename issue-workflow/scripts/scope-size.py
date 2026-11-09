#!/usr/bin/env python3
"""Issue ファイルのタスク数を数え、scope_size の上限と比べて判定する（GitHub issue #425）。

scope_size の上限と判定（超過・過大見積もり・推奨サイズ）の正本はこのスクリプトだけに置く。
hook（check-scope-size.sh）・issue-maintain・retrospective はこれを呼んで結果だけを使い、
散文には値を書き写さない（以前は 4 か所が別々の値で書いていて、同じ Issue が hook では
警告され、issue-maintain では警告されず、retrospective では「適正」になっていた）。

  scope-size.py limits
      上限を `small=3` の形で 1 行ずつ出す
  scope-size.py check [--basis all|done] PATH...
      PATH ごとに `file=<PATH>` で始まるブロックを出す（次の `file=` までがそのファイルの値）:
        id=<frontmatter の id。無ければ linear。どちらも無ければ空>
        scope_size=<frontmatter の値。無ければ空>
        total=<チェックリストの全件>
        done=<そのうち [x] / [X] の件数>
        count=<--basis で選んだ方（all なら total、done なら done。既定は all）>
        limit=<scope_size の上限。scope_size が無い・不明な値なら空>
        verdict=over|under|ok|skip
        recommended=<count が収まる最小のサイズ。large の上限も超えたら split。skip なら空>
      verdict が skip のときだけ `reason=no_scope_size|unknown_scope_size|no_tasks` が続く

判定:
  over   count が上限を超える
  under  count が 1 つ小さいサイズの上限を超えない（medium なら 3 件まで、large なら 7 件まで。small には無い）
  ok     どちらでもない
  skip   scope_size が無い・不明な値、またはチェックリストが 1 件も無い（入力の誤りではなくデータの状態なので exit 0。
         タスクを書いていない Issue を過大見積もりに数えない）

hook と issue-maintain は all（予定の膨張を早く出す）、retrospective は done（実際にやった量で
見積もりの精度を測る）で呼ぶ。under を使うのは retrospective だけ（作業中の Issue は増えていく途中にある）。

数え方: `## 進捗` に項目が 1 件以上あればその節、無ければ `## 完了条件` の節を数える。
2 つを足し合わせない（同じタスクが両節に現れる移行途中のファイルで二重に数え、超過を誤って出す）。
テンプレ系統が 2 つあるため両方を見る（issue-create の型別テンプレは `## 進捗`、issue-design の
9 セクションテンプレは `## 完了条件` / GitHub issue #179）。項目は行頭（インデント可）の `- [ ]` / `- [x]`。
frontmatter は 1 行目の `---` から次の `---` までだけを読み、値の行末の ` # 注釈` と囲みの引用符を外す
（テンプレの frontmatter は `scope_size: small   # 必須。…` と注釈を持つ）。先頭の BOM は外して読む。
行は `\n` と `\r\n` で分ける。

issue-workflow/hooks/issue-band-lib.ts（帯の mod）は python を呼べないため、上限の値・数え方・超過判定を
TS で複製している。一致は test_issue_workflow_scope_size.py（上限の値）と、両方の実装が読む共有 fixture
`.claude-plugin/scripts/tests/mods/issue-workflow/tests/scope-size-cases.ts`（数え方と超過判定）が検証する。

PATH が無い・ファイルでないときは `missing=<PATH>` を出し、残りの PATH は処理したうえで exit 2。
exit 0 成功 / 2 入力不正・PATH が無い。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LIMITS = {"small": 3, "medium": 7, "large": 15}
ORDER = ["small", "medium", "large"]

ITEM = re.compile(r"^\s*-\s*\[([ xX])\]")
KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
QUOTED = re.compile(r"""^(["'])(.*?)\1(\s+#.*)?$""")
COMMENT = re.compile(r"\s+#(\s.*)?$")


def frontmatter(lines: list[str]) -> dict[str, str]:
    if lines[0].strip() != "---":   # check() は re.split で読むので lines は空にならない
        return {}
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = KEY.match(line)
        if not m:
            continue
        raw = m.group(2).strip()
        q = QUOTED.match(raw)
        out[m.group(1)] = q.group(2) if q else COMMENT.sub("", raw).strip()
    return out


def count_tasks(lines: list[str]) -> tuple[int, int]:
    counts = {"p": [0, 0], "d": [0, 0]}
    sec = None
    for line in lines:
        if re.match(r"^## 進捗\s*$", line):
            sec = "p"
        elif re.match(r"^## 完了条件\s*$", line):
            sec = "d"
        elif line.startswith("## "):
            sec = None
        elif sec:
            m = ITEM.match(line)
            if m:
                counts[sec][0] += 1
                if m.group(1) != " ":
                    counts[sec][1] += 1
    total, done = counts["p"] if counts["p"][0] > 0 else counts["d"]
    return total, done


def recommended(count: int) -> str:
    for size in ORDER:
        if count <= LIMITS[size]:
            return size
    return "split"


def verdict(size: str, count: int) -> str:
    if count > LIMITS[size]:
        return "over"
    i = ORDER.index(size)
    if i > 0 and count <= LIMITS[ORDER[i - 1]]:
        return "under"
    return "ok"


def check(path: Path, basis: str) -> list[str]:
    # utf-8-sig: 先頭の BOM を外す（外さないと 1 行目が `---` に一致せず frontmatter を読めない。mod の trim() は外す）。
    # 行は `\n` と `\r\n` だけで分ける（mod の split(/\r?\n/) と同じ。splitlines() は単独の `\r`・U+2028 などでも分けて食い違う）
    lines = re.split(r"\r?\n", path.read_text(encoding="utf-8-sig", errors="replace"))
    fm = frontmatter(lines)
    size = fm.get("scope_size", "")
    total, done = count_tasks(lines)
    count = total if basis == "all" else done
    out = [
        f"id={fm.get('id') or fm.get('linear', '')}",
        f"scope_size={size}",
        f"total={total}",
        f"done={done}",
        f"count={count}",
    ]
    if size not in LIMITS:
        out += ["limit=", "verdict=skip", "recommended=",
                f"reason={'unknown_scope_size' if size else 'no_scope_size'}"]
        return out
    if total == 0:
        out += [f"limit={LIMITS[size]}", "verdict=skip", "recommended=", "reason=no_tasks"]
        return out
    out += [f"limit={LIMITS[size]}", f"verdict={verdict(size, count)}",
            f"recommended={recommended(count)}"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("limits")
    p_check = sub.add_parser("check")
    p_check.add_argument("--basis", choices=["all", "done"], default="all")
    p_check.add_argument("paths", nargs="+")
    args = ap.parse_args()

    if args.cmd == "limits":
        for size in ORDER:
            print(f"{size}={LIMITS[size]}")
        return 0

    missing = False
    for raw in args.paths:
        path = Path(raw)
        if not path.is_file():
            print(f"missing={raw}")
            missing = True
            continue
        print(f"file={raw}")
        for line in check(path, args.basis):
            print(line)
    return 2 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
