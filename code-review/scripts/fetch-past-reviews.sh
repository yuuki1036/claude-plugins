#!/usr/bin/env bash
# fetch-past-reviews.sh — 同じファイルを触った過去の merged PR のレビューコメントを集める（GitHub issue #286）
#
# Usage:
#   fetch-past-reviews.sh --base <ref> [--pr <N>]          # stdout に出力
#   fetch-past-reviews.sh --base <ref> [--pr <N>] --save   # ファイルに保存しパスを stdout に出す
#
# 入力は `triage-signals.sh` が書く core の変更ファイルの一覧（`review_path corelist`）なので、
# **triage-signals.sh の後に呼ぶ**。`--base` は `## meta` の `diff_base=`（無ければ `base=`）。
# 本体は lib/past_reviews.py。
#
# 終了コード: 0 = 取得した / 3 = 取得できないので飛ばした（理由は stderr。レビューは続ける）/
# 2 = 引数の誤り。`--save` はコメントが 1 件以上あったときだけファイルを作ってパスを出す
# （0 件のファイルを agent に読ませない）。一時ファイルに書いて成功時だけ mv する
# （空・途中のファイルが「読める」状態で残ると、古い過去指摘でレビューすることになる）。
set -uo pipefail

BASE=""; PR=""; SAVE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --base) [ $# -ge 2 ] || { echo "FATAL: --base に値が必要" >&2; exit 2; }; BASE="$2"; shift 2 ;;
    --pr)   [ $# -ge 2 ] || { echo "FATAL: --pr に値が必要" >&2; exit 2; }; PR="$2"; shift 2 ;;
    --save) SAVE=1; shift ;;
    *) echo "FATAL: 未知の引数: $1" >&2; exit 2 ;;
  esac
done
[ -n "$BASE" ] || { echo "FATAL: --base が必須" >&2; exit 2; }

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/review-paths.sh
. "$HERE/lib/review-paths.sh"
review_paths_init "$PR" || exit 2

for cmd in python3 gh git; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "skip: ${cmd} が無い" >&2
    exit 3
  fi
done

ARGS=(--core-list "$(review_path corelist)" --base "$BASE")
if [ -n "$PR" ]; then ARGS+=(--exclude-pr "$PR"); fi

if [ "$SAVE" != "1" ]; then
  exec python3 "$HERE/lib/past_reviews.py" "${ARGS[@]}"
fi

OUT=$(review_path pastrev)
trap 'rm -f "$OUT.tmp"' EXIT
rm -f "$OUT"
python3 "$HERE/lib/past_reviews.py" "${ARGS[@]}" > "$OUT.tmp" && RC=0 || RC=$?
if [ "$RC" -ne 0 ]; then
  exit "$RC"
fi
if [ -s "$OUT.tmp" ]; then
  mv "$OUT.tmp" "$OUT"
  echo "$OUT"
fi
exit 0
