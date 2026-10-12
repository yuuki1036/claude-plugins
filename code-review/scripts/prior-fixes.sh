#!/usr/bin/env bash
# prior-fixes.sh — 前回の self-review で修正を選んだ指摘を記録し、次の self-review で照合する（GitHub issue #298）
#
# Usage:
#   prior-fixes.sh record   # stdin: [{"file": ..., "line": ..., "focus": ..., "title": ...}, ...]（self-review Step 7）
#   prior-fixes.sh match    # 記録のうち今回の diff に入った分を `## prior-fixes` で出す（Step 1。triage-signals.sh の後）
#   prior-fixes.sh clear    # 今回の diff に入った分を記録から消す（publish-review-event.sh が呼ぶ）
#
# 記録は作業ツリー単位（`review_path priorfix`）なので、次のセッションの self-review からも読める。
# match は triage-signals.sh が書いた diff（`review_path diff`）を読む。本体は lib/prior_fixes.py。
#
# 終了コード: 0 = 正常（記録が無い・別ブランチ・diff に入っていない回は何も出さずに 0）/
# 2 = 引数・入力の誤り
set -uo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/review-paths.sh
. "$HERE/lib/review-paths.sh"
review_paths_init "" || exit 2
FILE=$(review_path priorfix) || exit 2
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || BRANCH=""
# detached HEAD ではどのコミットでも "HEAD" になり、無関係な作業の記録と一致してしまうので何もしない
if [ "$BRANCH" = "HEAD" ]; then
  if [ "${1:-}" = "record" ]; then
    echo "recorded=0（detached HEAD では記録しない）"
  fi
  exit 0
fi

case "${1:-}" in
  record) exec python3 "$HERE/lib/prior_fixes.py" record "$FILE" "$BRANCH" "$REVIEW_WT" ;;
  match)  exec python3 "$HERE/lib/prior_fixes.py" match "$FILE" "$BRANCH" "$(review_path diff)" ;;
  clear)  exec python3 "$HERE/lib/prior_fixes.py" clear "$FILE" "$BRANCH" "$(review_path diff)" ;;
  *) echo "usage: prior-fixes.sh record|match|clear" >&2; exit 2 ;;
esac
