#!/usr/bin/env bash
# SessionTitle: feature ブランチから Issue タイトルを取得してセッション名に設定

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "linear-workflow:set-session-title"

BRANCH=$(git branch --show-current 2>/dev/null || true)
[[ -z "$BRANCH" || "$BRANCH" == "main" || "$BRANCH" == "master" ]] && safe_hook_error NotFound "no feature branch"

ISSUE_ID=$(echo "$BRANCH" | grep -oE '[A-Z]+-[0-9]+' | head -1 || true)
[[ -z "$ISSUE_ID" ]] && safe_hook_error NotFound "no issue id in branch name"

ISSUE_FILE=$(find .claude/linear -name "${ISSUE_ID}.md" 2>/dev/null | head -1)
[[ -z "$ISSUE_FILE" ]] && safe_hook_error NotFound "issue file not found: $ISSUE_ID"

TITLE=$(grep '^title:' "$ISSUE_FILE" | head -1 | sed 's/^title:[[:space:]]*//' | sed 's/^"//;s/"$//')
[[ -z "$TITLE" ]] && safe_hook_error Validation "title empty in $ISSUE_FILE"

ESCAPED=$(printf '%s' "$TITLE" | sed 's/\\/\\\\/g; s/"/\\"/g')
printf '{"hookSpecificOutput":{"sessionTitle":"%s: %s"}}' "$ISSUE_ID" "$ESCAPED"
