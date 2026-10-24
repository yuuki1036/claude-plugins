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
- `match` に `<extra> <repo のルート>` を足すと、self-review の `--prior-findings` で渡された前回の対象
  （形は `record` の stdin と同じ）も合わせて出す。記録には書かず、`clear` でも消さない。記録分と同じ
  `file:line:focus` の分は捨てる。diff では絞らない — 修正が base の状態へ戻したファイルは diff 全体から
  外れるが、そのファイルの対象こそ確かめる（GitHub issue #313）
- `check`: `--prior-findings` のファイルを使えるかだけを確かめる（triage-signals.sh が `--since` を
  効かせるかを決める。読めない・形が違うなら exit 2）

使い方: `prior_fixes.py record <記録> <ブランチ> <repo のルート>` / `match <記録> <ブランチ> <diff>
[<extra> <repo のルート>]` / `clear <記録> <ブランチ> <diff>` / `check <extra> <repo のルート>`。
`match` はブランチが空なら記録を読まない（prior-fixes.sh が detached HEAD で `--extra` の分だけを出すときに
空で呼ぶ）。record / match / clear の呼び出し口は `scripts/prior-fixes.sh`（記録と diff のパスを導出する）。
`check` は triage-signals.sh が直接呼ぶ。
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
#: 1 回の Step 7 で記録する上限と、`--prior-findings` から読む上限。超えた分は捨てる（`## prior-fixes` の行は
#: reviewer のプロンプトにそのまま並ぶので、長くしない）
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
    # 表示できない文字を含むパスは捨てる（`## prior-fixes` は 1 件 1 行で出す。改行や U+2028 などの行区切りで
    # 偽の節を作れる。ASCII の制御文字だけを見ると U+2028 / U+0085 が通る）
    if not path.isprintable():
        return None
    # 絶対パスで渡されたら repo のルート相対に直す（diff の `b/` 側のパスと突き合わせるため）
    if os.path.isabs(path) and root:
        rel = os.path.relpath(path, root)
        if rel.startswith(".."):
            return None
        path = rel
    if path.startswith("./"):
        path = path[2:]
    if os.path.normpath(path).startswith(".."):
        return None
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
    try:
        _save(path, data)
    except OSError as e:
        # 一時ディレクトリを作れない・書けない回。記録が無いだけで次の回は照合を飛ばすので、レビューは止めない
        print("WARN: 前回の指摘への修正を記録できない（%s: %s）" % (path, e), file=sys.stderr)
        return 1
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


def _load_extra(path: str, root: str):
    """`--prior-findings` のファイルを読む。使えなければ WARN を出して None（空の配列は使える）."""
    try:
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
    except (OSError, ValueError):
        print("WARN: --prior-findings を読めない（%s）" % path, file=sys.stderr)
        return None
    if not isinstance(items, list):
        print("WARN: --prior-findings は JSON の配列で渡す（%s）" % path, file=sys.stderr)
        return None
    extra = [c for c in (_clean(e, root) for e in items) if c is not None]
    if items and not extra:
        print("WARN: --prior-findings に使える項目が無い（%s）" % path, file=sys.stderr)
        return None
    if len(extra) < len(items):
        print("WARN: --prior-findings の %d 件は形が違うので捨てた" % (len(items) - len(extra)), file=sys.stderr)
    # 入力は古い順（後ろほど新しい / prior-fixes-guide.md 4 節）。上限を超えたら後ろを残す
    if len(extra) > MAX_FIXES:
        print("WARN: --prior-findings の古い %d 件を捨てた（上限 %d 件）" % (len(extra) - MAX_FIXES, MAX_FIXES),
              file=sys.stderr)
    return extra[-MAX_FIXES:]


def check(path: str, root: str) -> int:
    return 0 if _load_extra(path, root) is not None else 2


def _key(f: dict):
    return (f.get("file"), f.get("line"), f.get("focus"))


def match(path: str, branch: str, diff: str, extra_path: str = "", root: str = "") -> int:
    # ブランチが空（detached HEAD）なら記録を読まない。--prior-findings の分は記録に頼らないので出す
    fixes = (_branch_fixes(path, branch)[0] or []) if branch else []
    extra = (_load_extra(extra_path, root) or []) if extra_path else []
    if not fixes and not extra:
        return 0
    try:
        files = _diff_files(diff)
    except OSError:
        # 記録分は照合できないので出さない。--prior-findings の分は diff で絞らないので出す
        print("WARN: diff を読めない（%s）。triage-signals.sh の後に呼ぶ" % diff, file=sys.stderr)
        files = set()
    hits = [f for f in fixes if f.get("file") in files]
    recorded, seen = {_key(f) for f in hits}, set()
    # 記録分を先に並べ、同じ file:line:focus の --prior-findings の分は捨てる。記録分どうしは畳まない。
    # 行の無い指摘も畳まない（鍵が粗く、別の指摘が 1 件に潰れる）
    for f in extra:
        k = _key(f)
        if k[1] is not None and (k in recorded or k in seen):
            continue
        seen.add(k)
        hits.append(f)
    if not hits:
        return 0
    print("## prior-fixes")
    if extra_path:
        print("recorded=%d extra=%d in_diff=%d" % (len(fixes), len(extra), len(hits)))
    else:
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
    try:
        _save(path, data)
    except OSError as e:
        print("WARN: 前回の指摘への修正の記録を書き換えられない（%s: %s）" % (path, e), file=sys.stderr)
        return 1
    return 0


def main(argv) -> int:
    if len(argv) >= 4 and argv[0] == "record":
        return record(argv[1], argv[2], argv[3], sys.stdin.read())
    if len(argv) in (4, 6) and argv[0] == "match":
        return match(*argv[1:])
    if len(argv) >= 4 and argv[0] == "clear":
        return clear(argv[1], argv[2], argv[3])
    if len(argv) == 3 and argv[0] == "check":
        return check(argv[1], argv[2])
    print("usage: prior_fixes.py record <path> <branch> <root> | match <path> <branch> <diff> [<extra> <root>] | "
          "clear <path> <branch> <diff> | check <extra> <root>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
