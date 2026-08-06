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

# パスは `diff --git a/X b/Y` の $4 から取らない。git はヘッダでスペースをクォートせず、
# rename は `{old => new}` の圧縮表記になるため、空白入り・rename のパスを取りこぼす。
# `+++ b/<path>` は行末までが 1 パスなので、こちらを正本にする
# （新規/削除で `+++ /dev/null` になる側は `--- a/<path>` で補う）。
list_paths() {
  awk '
    /^--- / { p=substr($0,5); sub(/^a\//,"",p); if (p != "/dev/null") a=p; next }
    /^\+\+\+ / { p=substr($0,5); sub(/^b\//,"",p); print (p == "/dev/null") ? a : p }
  ' "$DIFF"
}

if [ "${1:-}" = "--list" ]; then
  list_paths
  exit 0
fi

[ $# -gt 0 ] || { echo "usage: diff-slice.sh <diff-file> <path>... | --list" >&2; exit 2; }

MATCHED=$(
  printf '%s\n' "$@" | awk -v diff="$DIFF" '
    NR==FNR { want[$0]=1; next }
    /^diff --git / { on=0; hdr=$0; buf=""; getline_ok=1 }
    { lines[++n]=$0 }
    END {
      # 2 パス目: ヘッダ単位に分割し、+++/--- からパスを決めて出力可否を決める
      out=0; cnt=0
      for (i=1; i<=n; i++) {
        l=lines[i]
        if (l ~ /^diff --git /) {
          # 直後の ---/+++ を先読みしてパスを確定する
          p=""; a=""
          for (j=i+1; j<=n && j<=i+6; j++) {
            if (lines[j] ~ /^--- /) { t=substr(lines[j],5); sub(/^a\//,"",t); if (t != "/dev/null") a=t }
            else if (lines[j] ~ /^\+\+\+ /) { t=substr(lines[j],5); sub(/^b\//,"",t); p=(t=="/dev/null")?a:t; break }
            else if (lines[j] ~ /^diff --git /) break
          }
          out = (p in want)
          if (out) cnt++
        }
        if (out) print l
      }
      exit (cnt > 0 ? 0 : 3)
    }
  ' - "$DIFF"
)
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "WARN: 指定パスにマッチするハンクが 0 件（diff に含まれていない）: $*" >&2
  echo "      含まれるファイル一覧は 'diff-slice.sh \"$DIFF\" --list' で確認できる" >&2
  exit 3
fi
printf '%s\n' "$MATCHED"
