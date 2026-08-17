#!/usr/bin/env bash
# 保存済み diff から指定パスぶんだけを切り出す。
#
# 目的: reviewer / explorer agent が「自分の担当ファイルの diff だけ」を読めるようにする。
# diff 全文を各 agent のプロンプトへ転記しないための道具（orchestration-guide.md `## 3.5`）。
#
# 使い方:
#   diff-slice.sh <diff-file> <path> [<path> ...]   # 指定パスの diff ハンクのみ出力
#   diff-slice.sh <diff-file> --list                # 含まれるファイル一覧のみ出力
#
# **マッチ 0 件は exit 3 で落とす。** 空出力 + exit 0 だと、agent 側は「切り出しに
# 失敗した」と「担当ファイルに変更が無い」を区別できず、未レビューのまま
# 「問題なし」を返す（reviewer-common.md のフォールバックガードが機能しなくなる）。
set -uo pipefail

DIFF="${1:-}"
shift || true
[ -n "$DIFF" ] && [ -f "$DIFF" ] || { echo "usage: diff-slice.sh <diff-file> <path>... | --list" >&2; exit 2; }

# ---- パス確定（`--list` と切り出しで**同一実装**）--------------------------
# 別実装にすると両者が食い違い、「一覧に出たのに切り出せない（exit 3）」が起きる。
# agent 側はそれを「担当ファイルの diff が取れない」と報告するので 1 体ぶん空振りする。
#
# パスは `diff --git a/X b/Y` の $4 から取らない。git はヘッダでスペースをクォートせず、
# rename は a/old b/new になるため取り違える。優先順は:
#   1. `+++ b/<path>`（行末までが 1 パス。`/dev/null` 側は `--- a/<path>` で補う）
#   2. `rename to <path>`（**内容変更を伴わない rename は ---/+++ を持たない**）
#   3. `diff --git a/P b/P` の対称形（mode 変更のみ・binary。両側同一のときだけ確定できる）
#
# **ヘッダ行の判定はブロック先頭からハンクが始まるまでに限る。** 行全体に `^\+\+\+ `
# を当てると、`++ foo` という**追加行**（diff 上は `+++ foo`）が幻のパスとして一覧に載る。
#
# 欲しいパスの集合は ENVIRON で渡す（`-v` は値のエスケープを解釈するため、
# `a\tb.txt` のようなパスが壊れる）。
AWK_SLICER='
function sym_path(line,   s, n, half) {
  # `diff --git a/P b/P` の対称形からのみ復元する（非対称な rename には使わない）
  if (substr(line, 1, 13) != "diff --git a/") return ""
  s = substr(line, 14)
  n = length(s)
  if ((n - 3) % 2 != 0) return ""
  half = (n - 3) / 2
  if (substr(s, half + 1, 3) != " b/") return ""
  if (substr(s, 1, half) != substr(s, half + 4)) return ""
  return substr(s, 1, half)
}
function hdr_path(field,   p) {
  # `--- a/<path>` / `+++ b/<path>` の右辺。**git は空白を含むパスの後ろにタブを 1 つ付ける**
  # （区切りのため。実測: `--- a/sp ace.txt<TAB>`）。落とさないと呼び出し側が渡すパスと
  # 一致せず、空白入りファイルが必ず 0 件マッチ（exit 3）になる。
  # なお非 ASCII パスは git が `"a/\346..."` と C クォートする（`core.quotePath` 既定 true）。
  # ここでは戻さない — 生成側で `-c core.quotePath=false` を付けて生の UTF-8 で保存する
  # （awk の `%c` はロケールとバージョンでバイト/文字が変わり、8 進復元が移植できない）
  p = field
  sub(/\t$/, "", p)
  return p
}
function block_path() {
  if (plus   != "") return plus
  if (minus  != "") return minus
  if (rename != "") return rename
  return sym_path(git_line)
}
function flush(   i, p) {
  if (nb == 0) return                      # 先頭のコミットメッセージ等（ブロック外）
  p = block_path()
  if (mode == "list") { if (p != "") print p; return }
  if (p != "" && (p in want)) { cnt++; for (i = 1; i <= nb; i++) print buf[i] }
}
BEGIN {
  n = split(ENVIRON["DIFF_SLICE_WANT"], raw, "\n")
  for (i = 1; i <= n; i++) if (raw[i] != "") want[raw[i]] = 1
}
/^diff --git / { flush(); nb = 0; hdr = 1; plus = ""; minus = ""; rename = ""; git_line = $0 }
{ buf[++nb] = $0 }
hdr && /^--- /      { t = hdr_path(substr($0, 5)); sub(/^a\//, "", t); if (t != "/dev/null") minus = t; next }
hdr && /^\+\+\+ /   { t = hdr_path(substr($0, 5)); sub(/^b\//, "", t); if (t != "/dev/null") plus  = t; hdr = 0; next }
hdr && /^rename to / { rename = substr($0, 11); next }
/^@@ /              { hdr = 0 }
END { flush(); if (mode != "list") exit (cnt > 0 ? 0 : 3) }
'

if [ "${1:-}" = "--list" ]; then
  DIFF_SLICE_WANT="" awk -v mode=list "$AWK_SLICER" "$DIFF"
  exit 0
fi

[ $# -gt 0 ] || { echo "usage: diff-slice.sh <diff-file> <path>... | --list" >&2; exit 2; }

DIFF_SLICE_WANT=$(printf '%s\n' "$@") awk -v mode=slice "$AWK_SLICER" "$DIFF"
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "WARN: 指定パスにマッチするハンクが 0 件（diff に含まれていない）: $*" >&2
  echo "      含まれるファイル一覧は 'diff-slice.sh \"$DIFF\" --list' で確認できる" >&2
  exit 3
fi
