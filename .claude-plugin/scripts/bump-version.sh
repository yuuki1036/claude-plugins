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
#
# **`vNEXT` プレースホルダの解決（5 つ目の仕事）**: プラグイン配下の md / sh / py に書かれた
# `vNEXT` を新版へ一括置換する。doc に「この変更が入った版」を書くとき、**書く時点では正しい
# 値が確定していない**（bump は後）ため、手書きの版ラベルは構造的に古くなる — 実測で 3 回
# 再発し、検出側の機械化も 2 度失敗した（履歴参照と区別できない / CC の版と表記が衝突する。
# 経緯: code-review/references/design-notes/pending-optimizations.md `## 9`）。
# **確定していない値を書かせない**のが解。`vNEXT` は履歴参照と曖昧にならないトークンなので
# 置換も検出も偽陽性ゼロで済む。
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

# 変更の集約。**同じファイルに 2 つの変更が乗ることがある** — CHANGELOG の見出し挿入（4）と、
# その本文に書かれた `vNEXT` の解決（5）。リストに 2 エントリ積むと書き込みループが後勝ちになり、
# 先に積んだ見出し挿入が**「挿入した」と表示したまま消える**（issue #174）。パスをキーに
# (原本, 最新) で畳んで 1 ファイル 1 エントリを保つ
changes = {}

def stage(path, before, after):
    """path の変更を積む。既にあれば「最新」だけ差し替え、原本は最初のものを保つ。"""
    if path in changes:
        changes[path][1] = after
    else:
        changes[path] = [before, after]

# 1) plugin.json — 書式を保つため生テキストを 1 箇所だけ置換する
pj_new = pj_text[:m.start()] + '"version": "%s"' % new_s + pj_text[m.end():]
stage(pj_path, pj_text, pj_new)

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
stage(mk_path, mk_text, mk_new)

# 3) INDEX.md — 一覧テーブルの version セル
idx_text = idx_path.read_text()
idx_pat = re.compile(r'(\| \[%s\]\(#%s\) \| )\d+\.\d+\.\d+( \|)' % (re.escape(plugin), re.escape(plugin)))
if not idx_pat.search(idx_text):
    sys.exit("FATAL: INDEX.md に %s の行が無い（SSoT 検証で落ちるので中止）" % plugin)
idx_new = idx_pat.sub(r'\g<1>%s\g<2>' % new_s, idx_text, count=1)
stage(idx_path, idx_text, idx_new)

# 4) CHANGELOG — next モードで見出しが無いときだけ挿入する。**本文は書かない**
cl_heading_inserted = False
if mode == "next" and top != new_s:
    today = datetime.date.today().isoformat()
    entry = "## [%s] - %s\n\n" % (new_s, today)
    anchor = re.search(r'^## \[', cl_text, re.M)
    if anchor:
        cl_new = cl_text[:anchor.start()] + entry + cl_text[anchor.start():]
    else:
        cl_new = cl_text.rstrip() + "\n\n" + entry
    stage(cl_path, cl_text, cl_new)
    cl_heading_inserted = True

# 5) `vNEXT` プレースホルダの解決（プラグイン配下のみ）.
# **repo 直下の共通スクリプト / doc は対象外** — あれらはプラグイン版に属さないので、
# 版ラベルではなく issue 番号で参照する（複数プラグインを同時に bump したとき
# どちらの版に解決すべきか決まらない）。
#
# **起点はディスクの原本ではなく 1〜4 の適用後テキスト**。CHANGELOG のように 4 までで既に
# 書き換わっているファイルを読み直すと、その変更を巻き戻したテキストを積むことになる（#174）
placeholder_hits = []
for f in sorted(pathlib.Path(plugin).rglob("*")):
    if f.suffix not in (".md", ".sh", ".py") or not f.is_file():
        continue
    if f in changes:
        orig, text = changes[f]
    else:
        orig = text = f.read_text(encoding="utf-8", errors="replace")
    if "vNEXT" not in text:
        continue
    # **行内コード / フェンス内の `vNEXT` は置換しない**（SSoT pin と同じ規約 /
    # CLAUDE.md「doc に記法例を書くときはフェンスか行内コードに入れる」）。
    # 規約そのものを説明している文章まで書き換えてしまうため（実測で踏んだ）。
    # 生きたプレースホルダは**裸で書く**: 「この挙動は vNEXT で入った」
    out_lines, fence, hits = [], None, 0
    for line in text.splitlines(keepends=True):
        m = re.match(r"^\s*(`{3,}|~{3,})", line)
        if m:
            tok = m.group(1)
            if fence is None:
                fence = tok
            elif tok[0] == fence[0] and len(tok) >= len(fence):
                fence = None
            out_lines.append(line)
            continue
        if fence is not None:
            out_lines.append(line)
            continue
        # 行内コード（`...`）を退避してから置換し、戻す
        spans = []
        def _stash(mo):
            spans.append(mo.group(0))
            return "\x00%d\x00" % (len(spans) - 1)
        masked = re.sub(r"`[^`\n]*`", _stash, line)
        hits += masked.count("vNEXT")
        masked = masked.replace("vNEXT", "v" + new_s)
        out_lines.append(re.sub(r"\x00(\d+)\x00", lambda mo: spans[int(mo.group(1))], masked))
    if hits == 0:
        continue
    placeholder_hits.append((f, hits))
    stage(f, orig, "".join(out_lines))

# **打ち切りの判定は 5 まで済ませてから**。ここより前で「変更なし」と決めると、4 ファイルが
# 既に同期しているプラグインでは `--sync` が `vNEXT` を永久に解決できない（issue #174）
touched = [(p, a, b) for p, (a, b) in changes.items() if a != b]
if not touched:
    print("変更なし（%s は既に %s）" % (plugin, new_s))
    sys.exit(0)

if new_s != cur_s:
    print("%s: %s → %s%s" % (plugin, cur_s, new_s, "  [dry-run]" if dry else ""))
else:
    print("%s: %s（版は据え置き。vNEXT の解決のみ）%s" % (plugin, new_s, "  [dry-run]" if dry else ""))
for p, _, _ in touched:
    print("  %s" % p)
if cl_heading_inserted:
    print("  ↑ CHANGELOG は見出しのみ挿入した。本文は自分で書くこと")

# **全部読み終えてから書く**（two-phase）。1〜4 と 5 で書き込み位置が分かれていると,
# 途中の失敗（権限 / ディスク / 読めないファイル）で「版は上がったが vNEXT は残った」
# 半端な状態が残り, しかも次回の bump は差分無しで素通りする。
if not dry:
    for p, _, new_text in touched:
        p.write_text(new_text, encoding="utf-8")

if placeholder_hits:
    total = sum(n for _, n in placeholder_hits)
    print("  vNEXT を v%s に解決: %d 箇所 / %d ファイル%s"
          % (new_s, total, len(placeholder_hits), "  [dry-run]" if dry else ""))
    for f, n in placeholder_hits:
        print("    %s (%d)" % (f, n))
PY
