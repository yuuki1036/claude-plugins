#!/bin/bash
# SessionTitle: feature ブランチから Issue タイトルを取得してセッション名に設定
cat > /dev/null

BRANCH=$(git branch --show-current 2>/dev/null)
[[ -z "$BRANCH" || "$BRANCH" == "main" || "$BRANCH" == "master" ]] && exit 0

ISSUE_ID=$(echo "$BRANCH" | grep -oE '[A-Z]+-[0-9]+' | head -1)
[[ -z "$ISSUE_ID" ]] && exit 0

ISSUE_FILE=$(find .claude/indie -name "${ISSUE_ID}.md" 2>/dev/null | head -1)
[[ -z "$ISSUE_FILE" ]] && exit 0

TITLE=$(grep '^title:' "$ISSUE_FILE" | head -1 | sed 's/^title:[[:space:]]*//' | sed 's/^"//;s/"$//')
[[ -z "$TITLE" ]] && exit 0

ESCAPED=$(printf '%s' "$TITLE" | sed 's/\\/\\\\/g; s/"/\\"/g')
printf '{"hookSpecificOutput":{"sessionTitle":"%s: %s"}}' "$ISSUE_ID" "$ESCAPED"
