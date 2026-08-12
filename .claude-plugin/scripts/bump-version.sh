#!/usr/bin/env bash
# プラグインのバージョンバンプを 4 ファイル同時に行う（GitHub issue #90）。
#
# `.githooks/pre-commit` は「バンプされたか」「CHANGELOG が更新されたか」「marketplace が
# 同期しているか」を**検証**するが、**実行はしない**。その手作業を機械化する。
#
# 毎回同じ 4 ファイルを触る:
#   {plugin}/.claude-plugin/plugin.json   version
#   .claude-plugin/marketplace.json       plugins[].version
#   INDEX.md                              一覧テーブルの version セル
#   {plugin}/CHANGELOG.md                 見出し `## [x.y.z] - YYYY-MM-DD`
#
# 使い方:
#   bump-version.sh <plugin> --sync              # CHANGELOG 先頭の版を正として他 3 つを揃える（主経路）
#   bump-version.sh <plugin> major|minor|patch   # 次版を計算し、CHANGELOG に見出しだけ挿入する
#   bump-version.sh <plugin> ... --dry-run       # 差分を表示するだけ
#
# **CHANGELOG の本文は書かない。** 何が変わったかは人間 / LLM が書く。本スクリプトが持つのは
# 「版番号の算術」と「4 ファイルの同時更新」だけ（決定的に検証できる部分）。
set -uo pipefail

PLUGIN=""; MODE=""; LEVEL=""; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --sync)    MODE="sync"; shift ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    major|minor|patch) MODE="next"; LEVEL="$1"; shift ;;
    -*) echo "FATAL: 未知の引数: $1" >&2; exit 2 ;;
    *) [ -z "$PLUGIN" ] || { echo "FATAL: プラグイン名が複数指定された" >&2; exit 2; }; PLUGIN="$1"; shift ;;
  esac
done
[ -n "$PLUGIN" ] || { echo "FATAL: プラグイン名が必要（例: bump-version.sh code-review --sync）" >&2; exit 2; }
[ -n "$MODE" ]   || { echo "FATAL: --sync か major|minor|patch のどちらかが必要" >&2; exit 2; }

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "FATAL: git リポジトリ外" >&2; exit 2; }
cd "$ROOT" || exit 2
[ -f "$PLUGIN/.claude-plugin/plugin.json" ] || { echo "FATAL: プラグインが無い: $PLUGIN" >&2; exit 2; }

command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 が必要" >&2; exit 2; }

# bump 種別の助言（CLAUDE.md「バージョニング規約」の判定基準）。
# **ブロックしない** — 著者の方が事情を知っている場合があるので警告に留める。
# 今日の実測で誤ったのはこの 1 パターンだけ（docs-only なのに MINOR を当てた）。
CHANGED=$(git diff --cached --name-only -- "$PLUGIN"; git diff --name-only -- "$PLUGIN")
DOC_ONLY=1
while IFS= read -r f; do
  [ -n "$f" ] || continue
  case "$f" in
    *.md|"$PLUGIN"/.claude-plugin/plugin.json) ;;
    *) DOC_ONLY=0; break ;;
  esac
done <<< "$CHANGED"
[ -n "$CHANGED" ] || DOC_ONLY=0   # 変更が無いなら助言しない

PLUGIN="$PLUGIN" MODE="$MODE" LEVEL="$LEVEL" DRY="$DRY" DOC_ONLY="$DOC_ONLY" python3 <<'PY'
import json, os, re, sys, datetime, pathlib

plugin, mode, level = os.environ["PLUGIN"], os.environ["MODE"], os.environ["LEVEL"]
dry, doc_only = os.environ["DRY"] == "1", os.environ["DOC_ONLY"] == "1"

pj_path  = pathlib.Path(plugin) / ".claude-plugin" / "plugin.json"
mk_path  = pathlib.Path(".claude-plugin") / "marketplace.json"
idx_path = pathlib.Path("INDEX.md")
cl_path  = pathlib.Path(plugin) / "CHANGELOG.md"
for p in (pj_path, mk_path, idx_path, cl_path):
    if not p.exists():
        sys.exit("FATAL: 見つからない: %s" % p)

pj_text = pj_path.read_text()
m = re.search(r'"version"\s*:\s*"(\d+)\.(\d+)\.(\d+)"', pj_text)
if not m:
    sys.exit("FATAL: plugin.json から version を読めない")
cur = tuple(int(x) for x in m.groups())
cur_s = "%d.%d.%d" % cur

cl_text = cl_path.read_text()
heads = re.findall(r'^## \[(\d+\.\d+\.\d+)\]', cl_text, re.M)
top = heads[0] if heads else None

if mode == "sync":
    if top is None:
        sys.exit("FATAL: CHANGELOG に `## [x.y.z]` の見出しが無い（--sync は CHANGELOG を正とする）")
    new_s = top
    if new_s == cur_s:
        print("既に同期済み: %s は %s" % (plugin, cur_s))
    def key(v): return tuple(int(x) for x in v.split("."))
    if key(new_s) < key(cur_s):
        sys.exit("FATAL: CHANGELOG 先頭 %s が plugin.json %s より古い（取り違え防止のため中止）" % (new_s, cur_s))
else:
    major, minor, patch = cur
    new = {"major": (major + 1, 0, 0), "minor": (major, minor + 1, 0), "patch": (major, minor, patch + 1)}[level]
    new_s = "%d.%d.%d" % new
    if top == new_s:
        print("注意: CHANGELOG に既に %s の見出しがある（見出しの挿入はスキップする）" % new_s)
    elif top is not None and tuple(int(x) for x in top.split(".")) >= new:
        sys.exit("FATAL: CHANGELOG 先頭 %s が計算結果 %s 以上（--sync のつもりでは？）" % (top, new_s))
    if doc_only and level != "patch":
        print("⚠️  変更が *.md のみだが %s bump を指定している。CLAUDE.md の規約では PATCH（続行する）" % level.upper())

changes = []

# 1) plugin.json — 書式を保つため生テキストを 1 箇所だけ置換する
pj_new = pj_text[:m.start()] + '"version": "%s"' % new_s + pj_text[m.end():]
changes.append((pj_path, pj_text, pj_new))

# 2) marketplace.json — 該当プラグインのエントリ内だけを置換する（全体の再整形を避ける）
mk_text = mk_path.read_text()
name_m = re.search(r'"name"\s*:\s*"%s"' % re.escape(plugin), mk_text)
if not name_m:
    sys.exit("FATAL: marketplace.json に %s のエントリが無い" % plugin)
ver_m = re.search(r'"version"\s*:\s*"\d+\.\d+\.\d+"', mk_text[name_m.end():])
if not ver_m:
    sys.exit("FATAL: marketplace.json の %s エントリに version が無い" % plugin)
s0 = name_m.end() + ver_m.start(); s1 = name_m.end() + ver_m.end()
mk_new = mk_text[:s0] + '"version": "%s"' % new_s + mk_text[s1:]
changes.append((mk_path, mk_text, mk_new))

# 3) INDEX.md — 一覧テーブルの version セル
idx_text = idx_path.read_text()
idx_pat = re.compile(r'(\| \[%s\]\(#%s\) \| )\d+\.\d+\.\d+( \|)' % (re.escape(plugin), re.escape(plugin)))
if not idx_pat.search(idx_text):
    sys.exit("FATAL: INDEX.md に %s の行が無い（SSoT 検証で落ちるので中止）" % plugin)
idx_new = idx_pat.sub(r'\g<1>%s\g<2>' % new_s, idx_text, count=1)
changes.append((idx_path, idx_text, idx_new))

# 4) CHANGELOG — next モードで見出しが無いときだけ挿入する。**本文は書かない**
if mode == "next" and top != new_s:
    today = datetime.date.today().isoformat()
    entry = "## [%s] - %s\n\n" % (new_s, today)
    anchor = re.search(r'^## \[', cl_text, re.M)
    if anchor:
        cl_new = cl_text[:anchor.start()] + entry + cl_text[anchor.start():]
    else:
        cl_new = cl_text.rstrip() + "\n\n" + entry
    changes.append((cl_path, cl_text, cl_new))

touched = [(p, a, b) for p, a, b in changes if a != b]
if not touched:
    print("変更なし（%s は既に %s）" % (plugin, new_s))
    sys.exit(0)

print("%s: %s → %s%s" % (plugin, cur_s, new_s, "  [dry-run]" if dry else ""))
for p, _, _ in touched:
    print("  %s" % p)
if mode == "next" and any(p == cl_path for p, _, _ in touched):
    print("  ↑ CHANGELOG は見出しのみ挿入した。本文は自分で書くこと")

if not dry:
    for p, _, new_text in touched:
        p.write_text(new_text)
PY
