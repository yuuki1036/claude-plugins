#!/usr/bin/env bash
# detect-external-ids.sh — diff で追加されたコード内コメント中の「git 外の参照 ID」を検出する
#
# 目的: コードコメントに残った Linear Issue ID / Linear URL を機械的に拾う。これらは git 外の
#   通し ID で、コード本体には不要なノイズになりやすい。検出だけを決定的に行い、除去は
#   comment-polish skill（人間承認つき）が行う。commit 前 hook は非ブロッキング通知に使う。
#   設計: .claude/designs/20260912-e2e-verify-comment-polish-pr-flow.md (B-2)
#
# 対象: diff の追加行（先頭 +）のうちコメント構文を含む行。Refs/Closes/Fixes 行は除外。
# GitHub #N は既定で拾わない（本 repo 実測で 100% 偽陽性。--github で opt-in）。
# 出力: file:line:match の JSON Lines。exit: 0=なし / 1=あり / 2=判定不能。
#
# 使い方: detect-external-ids.sh [base-ref] [--staged] [--github]

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

command -v git >/dev/null 2>&1 || { echo "detect-external-ids: git not found" >&2; exit 2; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "detect-external-ids: not a git repository" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "detect-external-ids: python3 not found" >&2; exit 2; }

BASE=""
STAGED=0
PYARGS=()
for a in "$@"; do
  case "$a" in
    --staged) STAGED=1 ;;
    --github) PYARGS+=(--github) ;;
    *) BASE="$a" ;;
  esac
done

if [ "$STAGED" -eq 1 ]; then
  DIFF_CMD=(git diff --cached --unified=0)
else
  if [ -z "$BASE" ]; then
    BASE="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@')"
    [ -z "$BASE" ] && { git rev-parse --verify --quiet main >/dev/null 2>&1 && BASE=main || BASE=master; }
  fi
  DIFF_CMD=(git diff --unified=0 "${BASE}...HEAD")
fi

# 空配列の "${PYARGS[@]}" は set -u 下の bash 3.2 で unbound になるので ${arr[@]+...} で守る
"${DIFF_CMD[@]}" 2>/dev/null | python3 "${HERE}/lib/detect_external_ids.py" ${PYARGS[@]+"${PYARGS[@]}"}
