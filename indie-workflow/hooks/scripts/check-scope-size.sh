#!/usr/bin/env bash
# check-scope-size.sh — PostToolUse hook (Edit|Write|MultiEdit)
# .claude/indie/*/issues/*.md の進捗チェックリスト数が scope_size 上限を超えたら警告
# 上限: small:3 / medium:7 / large:15（Issue #30 参照）
# indie-issue-maintain の膨張閾値（5/8/16）とは別物で、こちらはリアルタイム初動警告

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "indie-workflow:check-scope-size"

INPUT=$(safe_hook_input)

if command -v jq &>/dev/null; then
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
else
  TOOL_NAME=$(echo "$INPUT" | grep -oE '"tool_name"[[:space:]]*:[[:space:]]*"[^"]+"' | sed 's/.*"\([^"]*\)"$/\1/' | head -1)
  FILE_PATH=$(echo "$INPUT" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]+"' | sed 's/.*"\([^"]*\)"$/\1/' | head -1)
fi

case "$TOOL_NAME" in
  Edit|Write|MultiEdit) ;;
  *) safe_hook_error Validation "not an edit tool: $TOOL_NAME" ;;
esac

[[ -z "$FILE_PATH" ]] && safe_hook_error Validation "empty file_path"

# .claude/indie/*/issues/*.md にマッチするか（相対/絶対どちらでも）
if ! echo "$FILE_PATH" | grep -qE '\.claude/indie/[^/]+/issues/[^/]+\.md$'; then
  safe_hook_error Validation "not an indie issue file: $FILE_PATH"
fi

[[ ! -f "$FILE_PATH" ]] && safe_hook_error NotFound "issue file missing: $FILE_PATH"

# frontmatter から scope_size と id を抽出
SCOPE_SIZE=$(awk '/^---$/{c++; next} c==1 && /^scope_size:/ {sub(/^scope_size:[[:space:]]*/, ""); print; exit}' "$FILE_PATH")
ISSUE_ID=$(awk '/^---$/{c++; next} c==1 && /^id:/ {sub(/^id:[[:space:]]*/, ""); print; exit}' "$FILE_PATH")

[[ -z "$SCOPE_SIZE" ]] && safe_hook_error Validation "scope_size not found"

case "$SCOPE_SIZE" in
  small)  LIMIT=3 ;;
  medium) LIMIT=7 ;;
  large)  LIMIT=15 ;;
  *) safe_hook_error Validation "unknown scope_size: $SCOPE_SIZE" ;;
esac

# ## 進捗 セクションのチェックリスト行数をカウント
# 次の ## セクションが来るまでの範囲で `- [ ]` / `- [x]` を数える
COUNT=$(awk '
  /^## 進捗[[:space:]]*$/ { in_section=1; next }
  /^## / && in_section { exit }
  in_section && /^[[:space:]]*-[[:space:]]*\[[[:space:]xX]\]/ { n++ }
  END { print n+0 }
' "$FILE_PATH")

if [[ "$COUNT" -le "$LIMIT" ]]; then
  safe_hook_error Validation "within limit: $COUNT <= $LIMIT ($SCOPE_SIZE)"
fi

# 警告注入（Issue ID 付きで文脈を残す）
safe_hook_emit "[scope-size] ${ISSUE_ID:-$(basename "$FILE_PATH")}: タスク ${COUNT} 件が scope_size=${SCOPE_SIZE} の上限 ${LIMIT} を超過しました。別 Issue 切り出しか scope_size 引き上げを検討してください（/indie-issue-maintain で整理可能）。"
