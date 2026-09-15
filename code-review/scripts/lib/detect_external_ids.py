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

--markdown を付けると、コメント内の Markdown 太字（**...**）も kind=markdown で拾う。コードコメントは
レンダリングされず記号がそのまま残る（GitHub issue #231）。commit 前 hook は付けない — 本 repo は
コメントで太字を多用しており（HEAD~80 の追加コメントで 299 件）、hook に載せると鳴りっぱなしになる。
md 系ファイルでは太字が正当な記法なので対象外。

出力: file / line / match / kind（id|markdown）の JSON Lines。exit 1=検出あり / 0=なし。
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
# 前後を ASCII 英数字・* ・/ で挟まれた ** は除外する: JSDoc の /** 、指数演算子 2**3 、**kwargs
# （閉じが無い）を巻き込まないため。\w は日本語にも一致し「を**重要**」を落とすので使わない。
# 内側の先頭末尾が空白の `a ** b` も除外する。
MD_BOLD = re.compile(r"(?<![A-Za-z0-9_*/])\*\*(?=[^\s*])[^*\n]*?[^\s*]\*\*(?![A-Za-z0-9_*])")
MARKDOWN_FILE = re.compile(r"\.(md|markdown|mdx)$", re.I)


def main() -> int:
    patterns = [LINEAR_ID, LINEAR_URL]
    if "--github" in sys.argv[1:]:
        patterns.append(GH_REF)
    markdown = "--markdown" in sys.argv[1:]

    cur_file: str | None = None
    new_line = 0
    found: list[tuple[str, int, str, str]] = []

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
            if cur_file and COMMENT.search(content):
                if not SAFE_REF.search(content):
                    for pat in patterns:
                        for mt in pat.finditer(content):
                            tok = mt.group(0)
                            # 規格トークン（UTF-8 等）の誤検出を弾く。prefix が stopword のものだけ落とす
                            if pat is LINEAR_ID and tok.split("-", 1)[0] in ID_STOPWORDS:
                                continue
                            found.append((cur_file, new_line, tok, "id"))
                # SAFE_REF はコミット規約の参照を守るための除外で、装飾とは無関係なので掛けない
                if markdown and not MARKDOWN_FILE.search(cur_file):
                    for mt in MD_BOLD.finditer(content):
                        found.append((cur_file, new_line, mt.group(0), "markdown"))
            new_line += 1

    for f, ln, tok, kind in found:
        # 太字の中身は日本語を含む。comment-polish は生の stdout を読むので \uXXXX にしない
        print(json.dumps({"file": f, "line": ln, "match": tok, "kind": kind}, ensure_ascii=False))

    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
