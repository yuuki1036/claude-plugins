#!/usr/bin/env bash
# plan-reviewers.sh — reviewer の構成を決め（plan）、確定したテーブルを起動前に検算する（check）。GitHub issue #351
#
# Usage:
#   plan-reviewers.sh plan --effort <low|medium|high|xhigh|max> --size-tier <small|medium|large|unknown> \
#     [--activated <観点,...>] [--prior <観点,...>] [--delta] [--focus <観点,...> | --exclude <観点,...>] \
#     [--spec <path>]... [--spec-source pr-issue:#N | knowledge:<path>]... [--issue-id <ID>]... [--pr <N>]
#   <確定テーブル> | plan-reviewers.sh check [--pr <N>]
#
# plan は構成（実効上限・単独 / 束ねの reviewer 行・落とした観点と理由）を stdout に出し、セッションの
# 一時ファイル（`review_path plan`）に保存する。check は stdin の確定テーブルをその plan と突き合わせる。
# 仕様ソース（session-context の branch 一致・ブランチ名の Issue ID の Issue ファイル・--spec の実在）は
# plan が自分で探す。作業ツリーとメインのチェックアウトの両方を見る。本体は lib/reviewer_plan.py。
#
# 終了コード: 0 = 正常 / 1 = check が規則違反を見つけた（NG 行に直し方）・plan を書けない /
# 2 = 引数・入力の誤り・plan が無いのに check を呼んだ
set -uo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/review-paths.sh
. "$HERE/lib/review-paths.sh"

CMD="${1:-}"
[ $# -gt 0 ] && shift
PR=""; ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --pr) [ $# -ge 2 ] || { echo "FATAL: --pr に値が必要" >&2; exit 2; }; PR="$2"; shift 2 ;;
    # 下の 4 つはこのスクリプトが解決して渡す。呼び出し側の値を通すと、argparse の後勝ちで plan の保存先や
    # 仕様ソースを探す場所が差し替わる（check は既定の保存先を読むので、別の plan で通る経路になる）
    --plan-file|--wt|--main-root|--branch|--plan-file=*|--wt=*|--main-root=*|--branch=*)
      echo "FATAL: $1 は plan-reviewers.sh が解決する（渡さない）" >&2; exit 2 ;;
    *) ARGS+=("$1"); shift ;;
  esac
done
review_paths_init "$PR" || exit 2
PLAN_FILE=$(review_path plan) || exit 2

case "$CMD" in
  plan)
    # detached HEAD では "HEAD"。rev-parse に失敗した回（コミットの無いブランチ）も同じに扱う
    BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || BRANCH=HEAD
    MAIN_ROOT=$(review_main_root) || MAIN_ROOT=""
    exec python3 "$HERE/lib/reviewer_plan.py" plan --plan-file "$PLAN_FILE" \
      --wt "$REVIEW_WT" --main-root "$MAIN_ROOT" --branch "$BRANCH" ${ARGS[@]+"${ARGS[@]}"} ;;
  check)
    if [ "${#ARGS[@]}" -ne 0 ]; then
      echo "usage: plan-reviewers.sh check [--pr <N>]（確定テーブルは stdin）" >&2
      exit 2
    fi
    exec python3 "$HERE/lib/reviewer_plan.py" check --plan-file "$PLAN_FILE" ;;
  *) echo "usage: plan-reviewers.sh plan|check ..." >&2; exit 2 ;;
esac
