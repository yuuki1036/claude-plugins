#!/usr/bin/env python3
"""repo 内の文書（仕様書・規約）の所在を決定的に出す（GitHub issue #352 / #365）.

正本は `.claude-plugin/lib/doc_locate.py`。`code-review/scripts/lib/` と `issue-workflow/scripts/lib/` に
byte 一致で複製している（プラグイン間依存禁止のため。`validate_plugin_quality.py` の BYTE_REPLICAS が検査する）。
判定（文書と実装が食い違うか）は持たない。持つのは「どれが文書か」と「diff・参照のどこに出てくるか」だけ。

Usage:
  doc_locate.py [--root DIR] [--diff-file PATH | --base REF|auto] [--ref FILE]... [--list] [--kind spec|rule]

出力（TSV。パスは root からの相対・POSIX 形式）:
  base=<解決した ref>          --base のときだけ
  touched<TAB><kind><TAB><rel>  diff が触った文書（削除したものは除く）
  ref<TAB><kind><TAB><rel><TAB><参照元>  --ref のファイルの本文が言及している文書
  doc<TAB><kind><TAB><rel>      --list のときだけ。repo の文書の一覧

終了コード: 0 = 正常（0 件でも 0）/ 2 = 引数の誤り（ファイルを読めない・root や base を決められない）
"""

from __future__ import annotations

import argparse
import codecs
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True    # mutation-ok: 配布物の `lib/` に `__pycache__` を作らせないだけで、判定にも出力にも効かない

#: パスの要素がこのどれかと（小文字で）完全一致する文書を仕様書とみなす。部分一致は採らない
#: （`design-notes/`・`mydocs/` は対象外）
SPEC_DIRS = frozenset(("docs", "doc", "spec", "specs", "design", "designs", "adr", "adrs",
                       "decisions", "rfcs", "requirements", "features"))
DOC_EXTS = frozenset((".md", ".mdx", ".markdown", ".rst", ".adoc", ".txt"))
#: 置き場所によらず規約とみなすファイル名（code-review は使わない。規約は claude-md-compliance の担当）
RULE_NAMES = frozenset(("CLAUDE.md", "AGENTS.md", "CONTRIBUTING.md"))

# 文書の拡張子で終わるパスらしい字句。前後が ASCII のパス文字（英数字・`_`・`.`・`/`・`-`）でなければ区切りとみなす
# （`#節` へのリンク・バッククォート・日本語の文字や句読点・文末の `.` の直前でも拾い、`a.md.bak` は拾わない）。
# 本体を ASCII に絞った式と Unicode を許す式の 2 本で拾う。前者は「docs/a.mdとdocs/b.md」の両方を、後者は `docs/仕様.md` を拾う
# （Unicode の 1 本だけだと、日本語の文字でつながった言及が 1 つの字句になり、実在しないので両方落ちる）。
# 後者の字句は前の日本語の文（「新しい節はdocs/仕様.md」）まで含むので、`_mention_candidates` が取り直す
_MENTION_EXT = r"\.(?:md|mdx|markdown|rst|adoc|txt|feature)"
_MENTION_RES = tuple(
    re.compile(r"(?<![A-Za-z0-9_./-])((?:\.{1,2}/|/)?" + body + _MENTION_EXT + r")(?=\.?(?:$|[^A-Za-z0-9_./-]))",
               re.IGNORECASE)
    for body in (r"[A-Za-z0-9_.\-][A-Za-z0-9_.\-/]*", r"[\w.\-][\w.\-/]*"))


class UsageError(Exception):
    pass


def classify(rel):
    """root からの相対パスを `"spec"` / `"rule"` / None に分ける."""
    parts = rel.replace("\\", "/").split("/")
    name = parts[-1]
    if name in RULE_NAMES:
        return "rule"
    if name.upper().startswith("CHANGELOG"):
        return None
    lower = name.lower()
    if lower.endswith(".feature"):
        return "spec"
    if os.path.splitext(lower)[1] not in DOC_EXTS:
        return None
    if any(p.lower() in SPEC_DIRS for p in parts[:-1]):
        return "spec"
    return None


def _unquote_git_path(path):
    """git が引用したパス（`"b/docs/\\346..."`・`"b/docs/\\"q\\"仕様.md"`）を戻す。引用されていなければそのまま、戻せなければ None.

    8 進の引用と生の UTF-8 が混ざりうるので、バイト列のまま escape を解いてから UTF-8 として読む。
    """
    if len(path) < 2 or not (path.startswith('"') and path.endswith('"')):
        return path
    try:
        return codecs.escape_decode(path[1:-1].encode("utf-8"))[0].decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def _has_control(text):
    """改行・タブなどの制御文字を含むか（出力の TSV の行を壊す名前を弾く）."""
    return any(ord(c) < 0x20 or ord(c) == 0x7f for c in text)


def _dedup(items):
    seen, out = set(), []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _exists(root, rel):
    """root の中に実体がある文書か。symlink は、辿った先が root の中の文書（`.git` の外）のときだけ通す.

    第三者の diff が置いた `docs/x.md -> ~/.ssh/...` や `docs/x.md -> ../.git/config` を、読む・書き換える対象に
    渡さないため。名前だけ文書の symlink が repo の中の非文書（`.git/config`・gitignore した `.env`）を指す型もここで落とす。
    """
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        return False
    root_abs = os.path.realpath(root)
    real = os.path.realpath(path)
    if not real.startswith(root_abs + os.sep):
        return False
    real_rel = os.path.relpath(real, root_abs).replace(os.sep, "/")
    if ".git" in real_rel.split("/"):
        return False
    # 辿った先も文書の拡張子を持つこと（置き場所は問わない。`AGENTS.md -> .github/copilot-instructions.md` は通す）
    return real_rel.lower().endswith(".feature") or os.path.splitext(real_rel.lower())[1] in DOC_EXTS


def touched_docs(diff_text, root):
    """unified diff のファイルヘッダ（`--- ` の次の行の `+++ b/<path>`）から触った文書を返す。戻り値は [(kind, rel)].

    hunk の本文の `+++ ...` 行（追加した行が `++ ` で始まる）はヘッダと読まない。rel は git が出す正規の形
    （`..` も `.` も先頭の `/` も無い）だけを受け、検査したパスと呼び出し側が組み立てるパスを一致させる。
    """
    out = []
    prev = ""
    # ヘッダの区間は `diff --git` の行から最初の `@@` まで。hunk の中で `-- ` の行を消した直後に `++ ` の行を
    # 足すと `--- ` / `+++ ` が並ぶので、区間の外ではヘッダと読まない（`diff --git` の無い diff は先頭を区間とみなす）
    in_header = True
    for line in diff_text.split("\n"):
        if line.startswith("diff --git "):
            in_header = True
        elif line.startswith("@@"):
            in_header = False
        header, prev = in_header and prev.startswith("--- ") and line.startswith("+++ "), line
        if not header:
            continue
        path = _unquote_git_path(line[4:].rstrip("\t").strip())
        if path is None or path == "/dev/null" or not path.startswith("b/"):
            continue
        rel = path[2:]
        if not rel or _has_control(rel) or os.path.isabs(rel) or os.path.normpath(rel).replace(os.sep, "/") != rel:
            continue
        kind = classify(rel)
        if kind and _exists(root, rel):
            out.append((kind, rel))
    return _dedup(out)


def _normalize(token, root):
    """言及の字句を root からの相対パスにする。字面で root の外を指すもの（`..`・別の絶対パス）は None。

    symlink はここでは辿らない（言及した名前のまま返す）。辿った先が root の外かは `_exists` が見る。
    root は字面と実体の両方で比べる（macOS の `/var` → `/private/var` のように、言及が片方の形で書かれうる）。
    """
    base = os.path.normpath(os.path.abspath(root))
    cand = os.path.normpath(token if os.path.isabs(token) else os.path.join(base, token))
    # 言及の側もディレクトリ部分だけ実体の形にした候補を足す（root を実体の形で受け、言及が字面の形の回）。
    # 最後の要素は辿らない（文書の symlink の扱いは `_exists` に任せる）
    cands = (cand, os.path.join(os.path.realpath(os.path.dirname(cand)), os.path.basename(cand)))
    for c in dict.fromkeys(cands):
        for r in dict.fromkeys((base, os.path.realpath(root))):
            if c.startswith(r + os.sep):
                return os.path.relpath(c, r).replace(os.sep, "/")
    return None


_EXT_END_RE = re.compile(r"\.(?:md|mdx|markdown|rst|adoc|txt|feature)(?=[^\x00-\x7f]|$)", re.IGNORECASE)


def _mention_candidates(token):
    """字句から言及の候補を切り出す。日本語の文でつながった字句（「新しい節はdocs/仕様.mdとdocs/設計.md」）を想定し、
    始まりは先頭か「非 ASCII の直後で ASCII に切り替わる位置」、終わりは「文書の拡張子の直後が非 ASCII か末尾」の組を全部出す."""
    starts = [0] + [i for i in range(1, len(token)) if ord(token[i - 1]) > 127 and ord(token[i]) < 128]
    ends = [m.end() for m in _EXT_END_RE.finditer(token)]
    for start in starts:
        for end in ends:
            if end > start:
                yield token[start:end]


def mentioned_docs(text, root):
    """本文が言及している repo 内の文書を返す（実在するものだけ）。戻り値は [(kind, rel)]."""
    out = []
    hits = sorted((m.start(1), m.group(1)) for pattern in _MENTION_RES for m in pattern.finditer(text))
    for _, whole in hits:
        for token in _mention_candidates(whole):
            rel = _normalize(token, root)
            kind = classify(rel) if rel is not None else None
            if kind and _exists(root, rel):
                out.append((kind, rel))
    return _dedup(out)


def _git(root, *args):
    # core.quotePath=false: 既定のままだと非 ASCII の名前（`docs/仕様.md`）が `"docs/\\344..."` と引用されて分類から漏れる
    proc = subprocess.run(["git", "-c", "core.quotePath=false", "-C", root, *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise UsageError("git %s に失敗: %s" % (" ".join(args), proc.stderr.strip()))
    return proc.stdout


def list_docs(root):
    """追跡済みと、gitignore されていない未追跡の文書を返す。戻り値は [(kind, rel)]."""
    out = []
    for rel in sorted(set(_git(root, "ls-files", "--cached", "--others", "--exclude-standard").splitlines())):
        kind = classify(rel)
        if kind and _exists(root, rel):
            out.append((kind, rel))
    return out


def resolve_base(root, base):
    if base != "auto":
        _git(root, "rev-parse", "--verify", "--quiet", base + "^{commit}")
        return base
    proc = subprocess.run(["git", "-C", root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
                          capture_output=True, text=True)
    candidates = [proc.stdout.strip()] if proc.returncode == 0 and proc.stdout.strip() else []
    candidates += ["main", "master"]
    for cand in candidates:
        ok = subprocess.run(["git", "-C", root, "rev-parse", "--verify", "--quiet", cand + "^{commit}"],
                            capture_output=True, text=True)
        if ok.returncode == 0:
            return cand
    raise UsageError("base を解決できない（origin/HEAD・main・master のどれも無い）")


def changed_docs(root, base):
    """分岐点から作業ツリーまで（コミット済み・staged・unstaged）と未追跡で触った文書（削除は除く）."""
    merge_base = _git(root, "merge-base", base, "HEAD").strip()
    names = _git(root, "diff", "--name-only", "--no-renames", "--diff-filter=d", merge_base).splitlines()
    names += _git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    out = []
    for rel in names:
        kind = classify(rel)
        if kind and _exists(root, rel):
            out.append((kind, rel))
    return _dedup(out)


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError as exc:
        raise UsageError("読めない: %s（%s）" % (path, exc.strerror))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="doc_locate.py", description="repo 内の文書の所在を出す")
    ap.add_argument("--root")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--diff-file")
    src.add_argument("--base")
    ap.add_argument("--ref", action="append", default=[])
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--kind", choices=("spec", "rule"))
    ns = ap.parse_args(argv)
    try:
        root = ns.root
        if not root:
            proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
            if proc.returncode != 0:
                raise UsageError("git の外では --root が要る")
            root = proc.stdout.strip()
        if not os.path.isdir(root):
            raise UsageError("--root が無い: %s" % root)
        lines = []
        if ns.base:
            base = resolve_base(root, ns.base)
            lines.append("base=%s" % base)
            touched = changed_docs(root, base)
        elif ns.diff_file:
            touched = touched_docs(_read(ns.diff_file), root)
        else:
            touched = []
        refs = [(r, _read(r)) for r in ns.ref]
        listed = list_docs(root) if ns.list else []
    except UsageError as exc:
        print("doc_locate: %s" % exc, file=sys.stderr)
        return 2

    def keep(kind):
        return ns.kind is None or kind == ns.kind

    lines += ["touched\t%s\t%s" % (k, rel) for k, rel in touched if keep(k)]
    for ref_path, text in refs:
        lines += ["ref\t%s\t%s\t%s" % (k, rel, ref_path) for k, rel in mentioned_docs(text, root) if keep(k)]
    lines += ["doc\t%s\t%s" % (k, rel) for k, rel in listed if keep(k)]
    if lines:
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
