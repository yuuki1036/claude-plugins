#!/usr/bin/env bash
# prior-fixes.sh — 前回の self-review で修正を選んだ指摘を記録し、次の self-review で照合する（GitHub issue #298）
#
# Usage:
#   prior-fixes.sh record   # stdin: [{"file": ..., "line": ..., "focus": ..., "title": ...}, ...]（self-review Step 7）
#   prior-fixes.sh match    # 記録のうち今回の diff に入った分を `## prior-fixes` で出す（Step 1。triage-signals.sh の後）
#   prior-fixes.sh match --extra <path>   # self-review の `--prior-findings` の分も合わせて出す（GitHub issue #313）
#   prior-fixes.sh clear    # 今回の diff に入った分を記録から消す（publish-review-event.sh が呼ぶ）
#
# 記録は作業ツリー単位（`review_path priorfix`）なので、次のセッションの self-review からも読める。
# match は triage-signals.sh が書いた diff（`review_path diff`）を読む。本体は lib/prior_fixes.py。
# `--extra` の分は記録に書かず、clear でも消さない（呼び出し元が毎回渡す）。
#
# 終了コード: 0 = 正常（記録が無い・別ブランチ・diff に入っていない回は何も出さずに 0）/
# 1 = 記録を書けない（WARN を出す。レビューは続けてよい）/ 2 = 引数・入力の誤り
set -uo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/review-paths.sh
. "$HERE/lib/review-paths.sh"
review_paths_init "" || exit 2
FILE=$(review_path priorfix) || exit 2
CMD="${1:-}"
EXTRA=""
# 想定外の形の引数は捨てずに止める（`--extra=<path>` や 1 語に潰れた `--extra <path>` を黙って無視すると、
# 前回の対象が reviewer に届かないまま delta だけを見るレビューになる）
if [ "$CMD" = "match" ] && [ "$#" -ne 1 ]; then
  if [ "$#" -eq 3 ] && [ "$2" = "--extra" ] && [ -n "$3" ]; then
    EXTRA="$3"
  else
    echo "usage: prior-fixes.sh match [--extra <path>]" >&2
    exit 2
  fi
fi
# rev-parse に失敗した回（コミットの無いブランチなど）も detached HEAD と同じに扱う（空のブランチ名を記録の鍵にしない）
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || BRANCH=HEAD
# detached HEAD ではどのコミットでも "HEAD" になり、無関係な作業の記録と一致してしまうので記録は使わない。
# `--extra` の分は記録に頼らないので、detached HEAD でも出す
if [ "$BRANCH" = "HEAD" ]; then
  if [ "$CMD" = "record" ]; then
    echo "recorded=0（detached HEAD では記録しない）"
  fi
  if [ "$CMD" = "match" ] && [ -n "$EXTRA" ]; then
    exec python3 "$HERE/lib/prior_fixes.py" match "$FILE" "" "$(review_path diff)" "$EXTRA" "$REVIEW_WT"
  fi
  exit 0
fi

case "$CMD" in
  record) exec python3 "$HERE/lib/prior_fixes.py" record "$FILE" "$BRANCH" "$REVIEW_WT" ;;
  match)
    if [ -n "$EXTRA" ]; then
      exec python3 "$HERE/lib/prior_fixes.py" match "$FILE" "$BRANCH" "$(review_path diff)" "$EXTRA" "$REVIEW_WT"
    fi
    exec python3 "$HERE/lib/prior_fixes.py" match "$FILE" "$BRANCH" "$(review_path diff)" ;;
  clear)  exec python3 "$HERE/lib/prior_fixes.py" clear "$FILE" "$BRANCH" "$(review_path diff)" ;;
  *) echo "usage: prior-fixes.sh record|match [--extra <path>]|clear" >&2; exit 2 ;;
esac
