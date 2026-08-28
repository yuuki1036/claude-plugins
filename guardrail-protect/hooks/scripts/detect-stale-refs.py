#!/usr/bin/env python3
"""外向き書き込みの本文から「実在しない見出しへの参照」を検出する.

`gh issue create|comment` などで公開する本文には、しばしば
``` `<file>.md ## <見出し>` ``` の形で典拠が書かれる。**ファイルは実在するのに
その見出しが無い**（節番号を取り違える / 分冊先を間違える）という誤りが
failure-journal の `claimed-fact-without-source` として繰り返し記録されている。

**ファイルパスの実在は検証しない。** 実測でパス実在検証は真の検出 0 件・偽陽性 41 件
だった（正当なプラグインルート相対参照 / placeholder / 他リポジトリのパス / 実行時
生成ファイル / `React/Next.js` のような非パス）。**測定の一次記録と母集団の限界は
`docs/session-reports/2026-08-28-gh-ref-guard-measurement.md`**（数値をここに複製しない）。

判定できない条件では**必ず黙る**（偽陽性 0 を維持する側に倒す）:
  - ファイル名が repo 内の複数ファイルに一致する（どれを指すか決められない）
  - ファイルが repo 内に見つからない（＝パス実在検証はしない）
  - repo が git 管理下でない

stdin: 検査する本文 / argv[1]: repo root
stdout: 検出 1 件につき 1 行 `<参照テキスト>\t<解決したファイル>` / 無検出なら空
常に exit 0（呼び出し側の `set -e` を踏まない）
"""

from __future__ import annotations

import re
import subprocess
import sys

#: ``` `<path>.md ## <見出し>` ``` / ``` `<path>.md#<見出し>` ```
#: `#` は 6 個まで受ける（H4 以上を 3 個で打ち切ると 4 個目が anchor 側に漏れ、
#: **正しい参照が必ず検出される**偽陽性になる）
ANCHOR_RE = re.compile(r"`([\w./-]+\.md)\s*#{1,6}\s*([^`\n]+)`")

#: 1 つのバッククォート内で複数の節をまとめて指す書き方（`f.md ## 6 / ## 8`）。
#: anchor が「6 / ## 8」のような見出しになりえない文字列になるため判定しない
COMPOUND_RE = re.compile(r"#{1,6}")


def repo_files(root: str) -> list[str]:
    # `core.quotePath=false` + NUL 区切り。既定のままだと非 ASCII パスが
    # `"docs/\350\250\255..."` とエスケープされて**永久に解決できず黙って無検査**になり、
    # 空白入りパスは `split()` で 2 つに割れて無関係な参照の検出まで殺す
    proc = subprocess.run(
        ["git", "-c", "core.quotePath=false", "ls-files", "-z"],
        cwd=root, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return []
    return [f for f in proc.stdout.split("\0") if f]


def resolve(path: str, files: list[str]) -> str | None:
    """参照されたパスを repo 内の 1 ファイルに解決する.

    プラグインルート相対の参照（`scripts/review-retro.sh` で
    `code-review/scripts/review-retro.sh` を指す）が慣習として定着しているため、
    末尾一致も許容する。**複数に一致したら None**（曖昧なものは判定しない）。
    """
    if path in files:
        return path
    tail = "/" + path.lstrip("./")
    matched = [f for f in files if f.endswith(tail)]
    if len(matched) == 1:
        return matched[0]
    return None


def _fence_marker(line: str) -> str:
    """行がコードフェンスの開始・終了マーカーならその記号列を返す（そうでなければ空）.

    **行内で閉じているインラインコードスパンはフェンスにしない** — 行頭から
    ``` `` `x` `` ``` と書く記法があり、これをフェンスとして数えると以降の
    フェンス状態が丸ごと反転する（本リポジトリの README がこの形を持つ）。
    """
    stripped = line.strip()
    for ch in ("`", "~"):
        if stripped.startswith(ch * 3):
            run = len(stripped) - len(stripped.lstrip(ch))
            rest = stripped[run:]
            if ch in rest:      # 行内に同じ記号が再登場 = 行内で閉じている
                return ""
            return ch * run
    return ""


def headings(root: str, path: str) -> list[str]:
    """markdown の見出しを集める.

    **コードフェンスの中は見出しにしない。** `# 合算するログの一覧を作る` のような
    シェルコメントを見出しとして採ると、`## <番号>` 参照がそれに前方一致して
    **検出が黙って無効化される**（本リポジトリの `orchestration-measurement.md` は
    フェンス内に 2 本持っており、実際に採取されていた）。
    """
    out = []
    fence = ""          # 開いているフェンスの文字と長さ（空 = フェンス外）
    try:
        with open(f"{root}/{path}", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                marker = _fence_marker(line)
                if fence:
                    # 同種で同じ長さ以上のマーカーだけが閉じる
                    if marker and marker[0] == fence[0] and len(marker) >= len(fence):
                        fence = ""
                    continue
                if marker:
                    fence = marker
                    continue
                if not line.startswith("#"):
                    continue
                text = line.lstrip("#").strip()
                if text:
                    out.append(text)
    except OSError:
        return []
    if fence:
        # 閉じないまま EOF。以降の見出しを落とした一覧を「正しい一覧」として使うと
        # 実在する見出しへの参照を弾く。**判定不能として黙る**（呼び出し側が skip する）
        return []
    return out


def _slugify(text: str) -> str:
    """GitHub の見出し anchor 相当に正規化する（小文字化・空白をハイフン・記号除去）.

    `` `README.md#installation` `` のような GitHub 標準形式は、生の見出し
    `## Installation` とは大小文字が違うため素の前方一致では一致しない。
    """
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_":
            out.append("-")
    return "".join(out).strip("-")


def heading_matches(anchor: str, heads: list[str]) -> bool:
    """見出しの前方一致.

    節番号の取り違えを拾うため、**数字の途中で切れる一致は認めない** —
    `## 1` が `## 13. Event Bus publish` に一致してしまうと、番号違いが
    素通りする。前方一致した直後の文字が英数字なら別の見出しとみなす。

    両方向の前方一致に同じ境界条件を課す。片方（`anchor.startswith(head)`）に
    条件が無いと**空文字の見出しに全参照が一致して検出が丸ごと死ぬ**ため、
    `headings()` の空行除去と合わせて二重に塞いでいる。
    """
    slug = _slugify(anchor)
    for head in heads:
        if slug and _slugify(head) == slug:
            return True        # GitHub 標準の anchor slug（`README.md#installation`）
        # 完全一致の専用分岐は置かない。下の前方一致（次文字が英数字でない）が
        # 同じ入力を必ず拾うので、早期 return を足すと**そこで打ち切られる死んだ分岐**
        # になり、変異が生存する（＝テストで守れない）だけになる
        if head.startswith(anchor) and not head[len(anchor):len(anchor) + 1].isalnum():
            return True
        if anchor.startswith(head) and not anchor[len(head):len(head) + 1].isalnum():
            return True
    return False


def detect(body: str, root: str) -> list[tuple[str, str]]:
    files = repo_files(root)
    if not files:
        return []
    out = []
    for match in ANCHOR_RE.finditer(body):
        span = match.group(0)
        if "://" in span:          # URL 内の fragment は対象外
            continue
        path, anchor = match.group(1), match.group(2).strip()
        if COMPOUND_RE.search(anchor):
            continue           # 複数節をまとめて指す書き方は判定しない
        resolved = resolve(path, files)
        if resolved is None:       # 未解決・曖昧はどちらも黙る
            continue
        heads = headings(root, resolved)
        if not heads:
            continue
        if not heading_matches(anchor, heads):
            out.append((f"{path} ## {anchor}", resolved))
    return out


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    body = sys.stdin.read()
    for ref, resolved in detect(body, root):
        print(f"{ref}\t{resolved}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
