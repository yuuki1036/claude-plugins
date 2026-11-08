#!/usr/bin/env python3
"""inject-rules.sh の出力を注入の上限に収める.

Claude Code は hook の plain stdout を 10,000 字で打ち切り、超えると先頭 2,000 字の
プレビューとファイルのパスだけを Claude に渡す（読むようには促さない）。超えた回は
規約の後半も knowledge も届かず、hook の側では検出できないので、出す前に収める
（GitHub issue #424）。

使い方: python3 inject-budget.py <上限> [<slug> <index.md> ...]
  stdin  : 必ず出す部分（冒頭の注意書き・backend の行・規約の本文）
  IW_STALE: 放置 Issue の行（`- **ID**: N日間未更新` を改行区切り）。無ければ空

入れる順: stdin の全文 → 放置 Issue → knowledge の index（slug ごと、行ごとに残りへ
入る分だけ）。出す順は stdin → knowledge → 放置 Issue で、上限を入れる前と同じ。
knowledge を省いた案内 1 行だけは、入らなくても上限を超えて出す（黙って消さない）。
字数は str の len（コードポイント数）で数える。バイト数では数えない。
"""

from __future__ import annotations

import os
import re
import sys

KNOWLEDGE_LEAD = "以下の知見が蓄積されている。実装時に関連する knowledge があれば Read して活用すること。"
SEPARATOR_ROW = re.compile(r"^\|\s*:?-+")
# 例外の経路の案内。見出しは inject-rules.sh の python3 で数えられない回と同じにし、理由だけを
# 実際に起きたことにする（同じ文言だと、index が壊れた回も「python3 が無い」と読まれる）
UNREAD_NOTE = ("\n---\n## Knowledge\n\nknowledge の index は注入していない（index の読み込みか"
               "注入の処理に失敗した）。`/knowledge` で一覧を見る。\n")


def knowledge_head(slug: str) -> str:
    return f"\n---\n## Knowledge（{slug}）\n\n{KNOWLEDGE_LEAD}\n\n"


def is_entry(line: str, next_line: str) -> bool:
    """表の 1 行が knowledge 1 件か（見出し行・区切り行は数えない）."""
    if not line.startswith("|") or SEPARATOR_ROW.match(line):
        return False
    return not SEPARATOR_ROW.match(next_line)


def count_entries(lines: list[str]) -> int:
    return sum(is_entry(line, lines[i + 1] if i + 1 < len(lines) else "")
               for i, line in enumerate(lines))


def omitted_note(n: int) -> str:
    rest = f"残り {n} 件" if n else "残り"
    return f"\n（index の{rest}は注入の上限で省いた。`/knowledge` で一覧を見る）\n"


def omitted_slugs_section(slugs: list[tuple[str, int]]) -> str:
    """丸ごと省いた slug の節. slugs は (slug, 件数) の並び."""
    names = "・".join(f"{slug}（{n} 件）" for slug, n in slugs)
    return (f"\n---\n## Knowledge（省略）\n\n{names}の index は注入の上限で省いた。"
            "`/knowledge` で一覧を見る。\n")


def stale_section(lines: list[str], budget: int) -> str:
    """放置 Issue の節。入りきらない行は件数にまとめる."""
    head = "\n---\n## 放置 Issue 検知\n\n"
    full = head + "".join(f"{line}\n" for line in lines)
    if not lines or len(full) <= budget:
        return full if lines else ""
    out = head
    for i, line in enumerate(lines):
        tail = f"- ほか {len(lines) - i} 件（`/maintain` で確かめる）\n"
        if len(out) + len(line) + 1 + len(tail) > budget:
            return out + tail if len(out) + len(tail) <= budget else ""
        out += f"{line}\n"
    return out


def partial_section(slug: str, body: str, budget: int) -> str:
    """index を行ごとに入る分だけ出し、残りの件数を案内に置き換える. 見出しも入らなければ空."""
    lines = body.splitlines(keepends=True)
    out = knowledge_head(slug)
    for i, line in enumerate(lines):
        note = omitted_note(count_entries(lines[i:]))
        if len(out) + len(line) + len(note) > budget:
            return out + note if len(out) + len(note) <= budget else ""
        out += line
    return out


def knowledge_sections(pairs: list[tuple[str, str]], budget: int) -> str:
    full = [knowledge_head(slug) + body for slug, body in pairs]
    if sum(map(len, full)) <= budget:
        return "".join(full)
    counts = [(slug, count_entries(body.splitlines(keepends=True))) for slug, body in pairs]
    # 全部は入らない。丸ごと省く slug の一覧の行を、全 slug を並べた最大の長さで先に取っておく
    reserve = len(omitted_slugs_section(counts))
    if budget < reserve:
        # 案内も入らない（規約が上限に近い）。上限を超えても案内だけは出し、knowledge が黙って消えないようにする
        return omitted_slugs_section(counts)
    budget -= reserve
    out = ""
    for i, (slug, body) in enumerate(pairs):
        if len(out) + len(full[i]) <= budget:
            out += full[i]
            continue
        part = partial_section(slug, body, budget - len(out))
        rest = counts[i + (1 if part else 0):]
        out += part
        if rest:
            out += omitted_slugs_section(rest)
        return out
    return out


def read_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    prefix = sys.stdin.read()
    stale_lines = [line for line in os.environ.get("IW_STALE", "").split("\n") if line]
    try:
        limit = int(sys.argv[1])
        args = sys.argv[2:]
        pairs = [(args[i], read_text(args[i + 1])) for i in range(0, len(args) - 1, 2)]
        remaining = limit - len(prefix)
        stale = stale_section(stale_lines, max(remaining, 0))
        knowledge = knowledge_sections(pairs, max(remaining - len(stale), 0))
    except Exception as e:  # 規約だけは必ず届ける。knowledge を落として続ける
        print(f"issue-workflow:inject-rules: inject-budget failed: {e}", file=sys.stderr)
        try:
            remaining = int(sys.argv[1]) - len(prefix)
        except (IndexError, ValueError):  # 上限そのものが読めない回だけ無制限にする
            remaining = 10**9
        # 通常の経路と同じく、案内は上限を超えても出す（knowledge を黙って消さない）。放置 Issue は残りに収める
        knowledge = UNREAD_NOTE if len(sys.argv) > 3 else ""
        stale = stale_section(stale_lines, max(remaining - len(knowledge), 0))
    sys.stdout.write(prefix + knowledge + stale)


if __name__ == "__main__":
    main()
