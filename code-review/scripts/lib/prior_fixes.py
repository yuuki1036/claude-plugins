"""前回の self-review で修正を選んだ指摘を記録し、次の self-review の diff と照合する（GitHub issue #298）.

self-review を `--focus` や共通ブロックのスコープで「前回以降」に絞ると、前回の指摘を受けて入れた修正も
「前回以前」に入り、検証済みとして外れる。指摘されたケースだけに合わせた狭い修正になりやすく、最も見直しが
要る行なのに、どのレビューにも見られない（実測: 5 回の self-review で報告 0 件まで解消した PR が、外部の
レビューで、修正したフラグが同じ形の別の 2 ケースを拾っていないと指摘された）。

- `record`: Step 7 で修正を選んだ指摘（`file` / `line` / `focus` / `title`）の JSON 配列を stdin から受け、
  ブランチ名と一緒に書く。空の配列は記録を消す
- `match`: 記録のうち、今回の diff が触ったファイルの分を `## prior-fixes` として出す。別ブランチの記録と、
  diff に入っていないファイルの分は出さない。出すものが無ければ何も出さない
- `clear`: 同じブランチの記録を消す（publish が呼ぶ。その回の Step 1 が照合して reviewer に渡したので、
  次の回へ持ち越さない）

使い方: `prior_fixes.py record <記録> <ブランチ> <repo のルート>` / `match <記録> <ブランチ> <diff>` /
`clear <記録> <ブランチ>`。呼び出し口は `scripts/prior-fixes.sh`（記録のパスを導出する）。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys

sys.dont_write_bytecode = True    # mutation-ok: 配布物の `lib/` に `__pycache__` を作らせないだけで、判定にも出力にも効かない

SCHEMA = 1
#: 1 回の Step 7 で記録する上限。超えた分は捨てる（reviewer の共通ブロックに全件並ぶので、長くしない）
MAX_FIXES = 50
_TITLE_MAX = 200
_FOCUS_MAX = 40
_DIFF_RE = re.compile(r"^diff --git a/.* b/(.*)$")


def _clean(entry, root: str):
    """1 件を検証して整える。`file` が無いものは捨てる（照合の鍵にならない）."""
    if not isinstance(entry, dict):
        return None
    path = entry.get("file")
    if not isinstance(path, str) or not path.strip():
        return None
    path = path.strip()
    # 絶対パスで渡されたら repo のルート相対に直す（diff の `b/` 側のパスと突き合わせるため）
    if os.path.isabs(path) and root:
        rel = os.path.relpath(path, root)
        if rel.startswith(".."):
            return None
        path = rel
    if path.startswith("./"):
        path = path[2:]
    line = entry.get("line")
    # bool は int の部分型なので先に弾く（`true` が 1 行目に化ける）
    if isinstance(line, bool) or not isinstance(line, int) or line < 1:
        line = None
    focus = entry.get("focus")
    focus = re.sub(r"\s+", "", focus)[:_FOCUS_MAX] if isinstance(focus, str) else ""
    title = entry.get("title")
    # 改行・タブを潰す（`## prior-fixes` は 1 件 1 行・タブ区切りで出す）
    title = " ".join(title.split())[:_TITLE_MAX] if isinstance(title, str) else ""
    return {"file": path, "line": line, "focus": focus or "?", "title": title}


def record(path: str, branch: str, root: str, text: str) -> int:
    try:
        items = json.loads(text)
    except ValueError:
        print("FATAL: stdin が JSON ではない（[{\"file\": ..., \"line\": ..., \"focus\": ..., \"title\": ...}]）",
              file=sys.stderr)
        return 2
    if not isinstance(items, list):
        print("FATAL: stdin は JSON の配列で渡す", file=sys.stderr)
        return 2
    fixes = [c for c in (_clean(e, root) for e in items) if c is not None][:MAX_FIXES]
    if not fixes:
        # 修正しなかった回・渡した全件が無効だった回は、前回の記録も残さない（古い修正を次の回に出さない）
        if os.path.exists(path):
            os.remove(path)
        print("recorded=0")
        return 0
    body = {"schema": SCHEMA, "branch": branch,
            "recorded_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fixes": fixes}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(body, f)
    # 書き終えてから置き換える（途中のファイルを次の self-review が読まない）
    os.replace(tmp, path)
    print("recorded=%d" % len(fixes))
    return 0


def _load(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("fixes"), list):
        return None
    return data


def _diff_files(diff: str):
    files = set()
    with open(diff, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = _DIFF_RE.match(line.rstrip("\n"))
            if m:
                files.add(m.group(1))
    return files


def match(path: str, branch: str, diff: str) -> int:
    if not os.path.exists(path):
        return 0
    data = _load(path)
    if data is None:
        print("WARN: 前回の指摘への修正の記録を読めない（%s）。照合せずに続ける" % path, file=sys.stderr)
        return 0
    if data.get("branch") != branch:
        return 0
    try:
        files = _diff_files(diff)
    except OSError:
        print("WARN: diff を読めない（%s）。triage-signals.sh の後に呼ぶ" % diff, file=sys.stderr)
        return 0
    fixes = [f for f in data["fixes"] if isinstance(f, dict) and f.get("file") in files]
    if not fixes:
        return 0
    print("## prior-fixes")
    print("recorded=%d in_diff=%d" % (len(data["fixes"]), len(fixes)))
    for f in fixes:
        print("%s:%s\t%s\t%s" % (f["file"], f.get("line") or "?", f.get("focus") or "?", f.get("title") or ""))
    return 0


def clear(path: str, branch: str) -> int:
    if not os.path.exists(path):
        return 0
    data = _load(path)
    # 別ブランチの記録は残す（そのブランチへ戻ったときの self-review が読む）。壊れた記録は消す
    if data is None or data.get("branch") == branch:
        os.remove(path)
    return 0


def main(argv) -> int:
    if len(argv) >= 4 and argv[0] == "record":
        return record(argv[1], argv[2], argv[3], sys.stdin.read())
    if len(argv) >= 4 and argv[0] == "match":
        return match(argv[1], argv[2], argv[3])
    if len(argv) >= 3 and argv[0] == "clear":
        return clear(argv[1], argv[2])
    print("usage: prior_fixes.py record <path> <branch> <root> | match <path> <branch> <diff> | "
          "clear <path> <branch>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
