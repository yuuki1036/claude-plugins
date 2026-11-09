#!/usr/bin/env bash
# check-scope-size.sh — PostToolUse hook (Edit|Write|MultiEdit)
# .claude/{indie,linear}/*/issues/*.md のチェックリスト数が scope_size 上限を超えたら警告
# 数え方・上限・判定は scripts/scope-size.py が持つ（issue-maintain / retrospective と同じ判定 / GitHub issue #425）。
# ここは入力の絞り込みと、verdict=over のときの通知だけを持つ

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "issue-workflow:check-scope-size"

INPUT=$(safe_hook_input)

if command -v jq &>/dev/null; then
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
else
  TOOL_NAME=$(echo "$INPUT" | grep -oE '"tool_name"[[:space:]]*:[[:space:]]*"[^"]+"' | sed 's/.*"\([^"]*\)"$/\1/' | head -1 || true)
  FILE_PATH=$(echo "$INPUT" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]+"' | sed 's/.*"\([^"]*\)"$/\1/' | head -1 || true)
fi

case "$TOOL_NAME" in
  Edit|Write|MultiEdit) ;;
  *) safe_hook_error Validation "not an edit tool: $TOOL_NAME" ;;
esac

[[ -z "$FILE_PATH" ]] && safe_hook_error Validation "empty file_path"

# .claude/{indie,linear}/*/issues/*.md にマッチするか（相対/絶対どちらでも）
if ! echo "$FILE_PATH" | grep -qE '\.claude/(indie|linear)/[^/]+/issues/[^/]+\.md$'; then
  safe_hook_error Validation "not an issue file: $FILE_PATH"
fi

[[ ! -f "$FILE_PATH" ]] && safe_hook_error NotFound "issue file missing: $FILE_PATH"

# python3 が PATH にあっても起動に失敗する環境がある（CLT の無い macOS のスタブ・pyenv の shim）。
# 判定できない回は黙る（警告を出さないだけで、編集は止めない）
command -v python3 >/dev/null 2>&1 || safe_hook_error Dependency "python3 not found"
OUT="$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/scope-size.py" check --basis all -- "$FILE_PATH" 2>/dev/null)" \
  || safe_hook_error Dependency "scope-size.py failed"

# grep は 0 件で非ゼロを返し pipefail で落ちるので sed で取り出す
VERDICT=$(printf '%s\n' "$OUT" | sed -n 's/^verdict=//p')
SCOPE_SIZE=$(printf '%s\n' "$OUT" | sed -n 's/^scope_size=//p')
COUNT=$(printf '%s\n' "$OUT" | sed -n 's/^count=//p')
LIMIT=$(printf '%s\n' "$OUT" | sed -n 's/^limit=//p')
ISSUE_ID=$(printf '%s\n' "$OUT" | sed -n 's/^id=//p')

[[ "$VERDICT" == "over" ]] || safe_hook_error Validation "not over: verdict=${VERDICT} (${SCOPE_SIZE} ${COUNT}/${LIMIT})"

# 警告注入（Issue ID 付きで文脈を残す）
safe_hook_emit_context "PostToolUse" "[scope-size] ${ISSUE_ID:-$(basename "$FILE_PATH")}: タスク ${COUNT} 件が scope_size=${SCOPE_SIZE} の上限 ${LIMIT} を超過しました。別 Issue 切り出しか scope_size 引き上げを検討してください（/issue-maintain で整理可能）。"
