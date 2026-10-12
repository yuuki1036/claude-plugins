"""前回の self-review で修正を選んだ指摘を記録し、次の self-review の diff と照合する（GitHub issue #298）.

self-review を `--focus` や共通ブロックのスコープで「前回以降」に絞ると、前回の指摘を受けて入れた修正も
「前回以前」に入り、検証済みとして外れる。指摘されたケースだけに合わせた狭い修正になりやすく、最も見直しが
要る行なのに、どのレビューにも見られない（実測: 5 回の self-review で報告 0 件まで解消した PR が、外部の
レビューで、修正したフラグが同じ形の別の 2 ケースを拾っていないと指摘された）。

記録は作業ツリーに 1 ファイルで、中をブランチ別に持つ（ブランチを行き来しても、他のブランチの分を消さない）。

- `record`: Step 7 で修正を選んだ指摘（`file` / `line` / `focus` / `title`）の JSON 配列を stdin から受け、
  今のブランチの分として書く（そのブランチの前回の分は置き換える）。空の配列はそのブランチの分を消す
- `match`: 今のブランチの記録のうち、今回の diff が触ったファイルの分を `## prior-fixes` として出す。
  出すものが無ければ何も出さない
- `clear`: 今のブランチの記録から、今回の diff が触ったファイルの分だけを消す（publish が呼ぶ。その分は
  この回の Step 1 が照合して reviewer に渡した）。diff に入らなかった分は reviewer に渡っていないので残す

使い方: `prior_fixes.py record <記録> <ブランチ> <repo のルート>` / `match <記録> <ブランチ> <diff>` /
`clear <記録> <ブランチ> <diff>`。呼び出し口は `scripts/prior-fixes.sh`（記録と diff のパスを導出する）。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys

sys.dont_write_bytecode = True    # mutation-ok: 配布物の `lib/` に `__pycache__` を作らせないだけで、判定にも出力にも効かない

#: 2 でブランチ別に持つ形にした（1 は作業ツリーに 1 ブランチ分だけ。読むときに 2 の形へ直す）
SCHEMA = 2
#: 1 回の Step 7 で記録する上限。超えた分は捨てる（reviewer の共通ブロックに全件並ぶので、長くしない）
MAX_FIXES = 50
_TITLE_MAX = 200
_FOCUS_MAX = 40
#: diff のファイルのパスは `--- a/` と `+++ b/` の行から取る。`diff --git a/X b/X` の行から取ると、パスが
#: ` b/` を含む回に区切りを取り違える。特殊文字を含むパスは git が `"b/..."` と引用符で囲む
_PATH_RE = re.compile(r'^(?:---|\+\+\+) (?:"[ab]/(.*)"|[ab]/(.*))$')


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


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path: str):
    """記録を読む。無ければ空の記録、壊れていれば None。schema 1（1 ブランチ分）は 2 の形に直す."""
    if not os.path.exists(path):
        return {"schema": SCHEMA, "branches": {}}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema") == 1 and isinstance(data.get("fixes"), list) and isinstance(data.get("branch"), str):
        return {"schema": SCHEMA, "branches": {data["branch"]: {"recorded_at": data.get("recorded_at"),
                                                                  "fixes": data["fixes"]}}}
    branches = data.get("branches")
    if data.get("schema") != SCHEMA or not isinstance(branches, dict):
        return None
    if not all(isinstance(v, dict) and isinstance(v.get("fixes"), list) for v in branches.values()):
        return None
    return data


def _save(path: str, data: dict) -> None:
    """ブランチが 1 つも残らなければファイルを消す。書くときは書き終えてから置き換える."""
    if not data["branches"]:
        if os.path.exists(path):
            os.remove(path)
        return
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


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
    # 壊れた記録は読めないので作り直す（照合できない記録を残しても使い道が無い）
    data = _load(path) or {"schema": SCHEMA, "branches": {}}
    if fixes:
        data["branches"][branch] = {"recorded_at": _now(), "fixes": fixes}
    else:
        # 修正しなかった回・渡した全件が無効だった回は、このブランチの前回の分も残さない
        data["branches"].pop(branch, None)
    _save(path, data)
    print("recorded=%d" % len(fixes))
    return 0


def _unquote(path: str) -> str:
    """git が引用符で囲んだパスのエスケープを戻す（`core.quotePath=false` なので非 ASCII は生のまま来る）."""
    return re.sub(r'\\(["\\tn])', lambda m: {"t": "\t", "n": "\n"}.get(m.group(1), m.group(1)), path)


def _diff_files(diff: str):
    files = set()
    with open(diff, encoding="utf-8", errors="replace") as f:
        for line in f:
            # 空白を含むパスの後ろには git がタブを付ける
            m = _PATH_RE.match(line.rstrip("\n").rstrip("\t"))
            if m:
                files.add(_unquote(m.group(1)) if m.group(1) is not None else m.group(2))
    return files


def _branch_fixes(path: str, branch: str):
    """今のブランチの記録（無ければ空）と記録全体。読めなければ WARN を出して (None, None)."""
    data = _load(path)
    if data is None:
        print("WARN: 前回の指摘への修正の記録を読めない（%s）。照合せずに続ける" % path, file=sys.stderr)
        return None, None
    entry = data["branches"].get(branch) or {}
    return [f for f in entry.get("fixes") or [] if isinstance(f, dict)], data


def match(path: str, branch: str, diff: str) -> int:
    fixes, _ = _branch_fixes(path, branch)
    if not fixes:
        return 0
    try:
        files = _diff_files(diff)
    except OSError:
        print("WARN: diff を読めない（%s）。triage-signals.sh の後に呼ぶ" % diff, file=sys.stderr)
        return 0
    hits = [f for f in fixes if f.get("file") in files]
    if not hits:
        return 0
    print("## prior-fixes")
    print("recorded=%d in_diff=%d" % (len(fixes), len(hits)))
    for f in hits:
        print("%s:%s\t%s\t%s" % (f["file"], f.get("line") or "?", f.get("focus") or "?", f.get("title") or ""))
    return 0


def clear(path: str, branch: str, diff: str) -> int:
    if not os.path.exists(path):
        return 0
    fixes, data = _branch_fixes(path, branch)
    if data is None:
        # 壊れた記録は消す（次の回も読めず、WARN を出し続けるだけ）
        os.remove(path)
        return 0
    if not fixes:
        return 0  # mutation-ok: 消す分が無い回の早期 return。外しても記録を同じ内容で書き直すだけで、出力も記録も変わらない
    try:
        files = _diff_files(diff)
    except OSError:
        # 照合できなかった回は、どの分も reviewer に渡っていないので消さない
        return 0
    rest = [f for f in fixes if f.get("file") not in files]
    if rest:
        data["branches"][branch]["fixes"] = rest
    else:
        data["branches"].pop(branch, None)
    _save(path, data)
    return 0


def main(argv) -> int:
    if len(argv) >= 4 and argv[0] == "record":
        return record(argv[1], argv[2], argv[3], sys.stdin.read())
    if len(argv) >= 4 and argv[0] == "match":
        return match(argv[1], argv[2], argv[3])
    if len(argv) >= 4 and argv[0] == "clear":
        return clear(argv[1], argv[2], argv[3])
    print("usage: prior_fixes.py record <path> <branch> <root> | match <path> <branch> <diff> | "
          "clear <path> <branch> <diff>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
