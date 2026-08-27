#!/usr/bin/env bash
# UserPromptSubmit（once）: feature ブランチから Issue タイトルを取得し、
# hookSpecificOutput.sessionTitle でセッション名に設定する。
# （`SessionTitle` というイベントは存在しない — hooks.schema.json の enum を参照）

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "issue-workflow:set-session-title"
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/detect-backend.sh"

BRANCH=$(git branch --show-current 2>/dev/null || true)
[[ -z "$BRANCH" || "$BRANCH" == "main" || "$BRANCH" == "master" ]] && safe_hook_error NotFound "no feature branch"

ISSUE_ID=$(echo "$BRANCH" | grep -oE '[A-Z]+-[0-9]+' | head -1 || true)
[[ -z "$ISSUE_ID" ]] && safe_hook_error NotFound "no issue id in branch name"

# backend を判定し、有効な側の dir だけを find する（存在しない dir を find に渡すと
# ファイルが見つかっても exit 1 になり、pipefail + ERR trap で hook 全体が silent exit する）
iw_detect_backend
case "$IW_BACKEND" in
  none) safe_hook_error NotFound "no valid backend data dir" ;;
  both) safe_hook_error Validation "backend conflict (.claude/indie and .claude/linear both valid)" ;;
esac
ISSUE_FILE=$(find "$IW_DATA_DIR" -name "${ISSUE_ID}.md" 2>/dev/null | head -1 || true)
[[ -z "$ISSUE_FILE" ]] && safe_hook_error NotFound "issue file not found: $ISSUE_ID"

# **`|| true` は必須**（GitHub issue #179）: `title:` 行を欠く issue ファイルで grep が
# exit 1 を返し、ERR trap を踏んで下の Validation へ到達しない。同ファイルの他の grep
# （:8 / :11 / :21）は付与済みで、この 1 行だけ漏れていた
TITLE=$(grep '^title:' "$ISSUE_FILE" | head -1 | sed 's/^title:[[:space:]]*//' | sed 's/^"//;s/"$//' || true)
[[ -z "$TITLE" ]] && safe_hook_error Validation "title empty in $ISSUE_FILE"

ESCAPED=$(printf '%s' "$TITLE" | sed 's/\\/\\\\/g; s/"/\\"/g')
printf '{"hookSpecificOutput":{"sessionTitle":"%s: %s"}}' "$ISSUE_ID" "$ESCAPED"
