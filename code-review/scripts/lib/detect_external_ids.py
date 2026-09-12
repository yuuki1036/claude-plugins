#!/usr/bin/env python3
"""git diff（unified=0）を stdin で受け、追加されたコード内コメント中の git 外参照 ID を検出する.

detect-external-ids.sh が `git diff ... | python3 この_ファイル` の形で呼ぶ。
ロジックを .py に分けるのは、`python3 - <<'HEREDOC'` とパイプ stdin を同時に使うと
python がプログラムを stdin（＝diff）から読んでしまう事故を避けるため。

検出パターン（設計 B-2 / 実測で確定した初版）:
  - Linear Issue ID: [A-Z]{2,10}-[0-9]{1,6}
  - Linear URL: https://linear.app/...
GitHub #N は既定から外す。本 repo の HEAD~80 範囲で 759 件すべてが正当な why 参照で、
100% 偽陽性だった（code-review は本 repo 自身にも掛かるため、既定にすると commit 前 hook が
ノイズを撒き「⚠️ が出たときだけ行動」契約を壊す）。#N を拾いたい repo は --github で opt-in する。

出力: file:line:match の JSON Lines。exit 1=検出あり / 0=なし。
"""

from __future__ import annotations

import json
import re
import sys

LINEAR_ID = re.compile(r"\b[A-Z]{2,10}-[0-9]{1,6}\b")
# 規格・エンコーディング名は LINEAR_ID の形（英大文字-数字）に一致するが Linear ID ではない。
# コメントに頻出する（本 repo の CLAUDE.md も C.UTF-8 等を多用）ので除外しないと hook が誤発火する。
ID_STOPWORDS = frozenset(
    {"UTF", "SHA", "ISO", "RFC", "UTC", "RGB", "RGBA", "AES", "CRC", "MD", "PEP", "ES", "HTTP"}
)
LINEAR_URL = re.compile(r"https://linear\.app/[^\s)]+")
GH_REF = re.compile(r"(?<![&\w])#[0-9]{2,6}\b")
# 正当な参照（コミット規約の closing keyword）は行ごと除外する
SAFE_REF = re.compile(r"\b(Refs|Closes|Fixes|Close|Fix|Resolves|Resolve)\b", re.I)
# コメント構文シグナル（行のどこかに出ればコメント行とみなす軽量判定）
COMMENT = re.compile(r"(//|/\*|\*/|<!--|\"\"\"|'''|(^|\s)#)")
HUNK = re.compile(r"^@@ .*\+(\d+)(?:,(\d+))? @@")


def main() -> int:
    patterns = [LINEAR_ID, LINEAR_URL]
    if "--github" in sys.argv[1:]:
        patterns.append(GH_REF)

    cur_file: str | None = None
    new_line = 0
    found: list[tuple[str, int, str]] = []

    for raw in sys.stdin:
        line = raw.rstrip("\n")
        if line.startswith("+++ "):
            p = line[4:]
            cur_file = p[2:] if p.startswith("b/") else p
            if cur_file == "/dev/null":
                cur_file = None
            continue
        if line.startswith("--- "):
            continue
        m = HUNK.match(line)
        if m:
            new_line = int(m.group(1))
            continue
        if line.startswith("+") and not line.startswith("+++"):
            content = line[1:]
            if cur_file and COMMENT.search(content) and not SAFE_REF.search(content):
                for pat in patterns:
                    for mt in pat.finditer(content):
                        tok = mt.group(0)
                        # 規格トークン（UTF-8 等）の誤検出を弾く。prefix が stopword のものだけ落とす
                        if pat is LINEAR_ID and tok.split("-", 1)[0] in ID_STOPWORDS:
                            continue
                        found.append((cur_file, new_line, tok))
            new_line += 1

    for f, ln, tok in found:
        print(json.dumps({"file": f, "line": ln, "match": tok}, ensure_ascii=False))

    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
