#!/usr/bin/env bash
# ui-change-reminder.sh — PostToolUse hook (Edit|Write)
# UI ファイル変更を検知して pending flag を立て、ui-verify の利用を促す

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "dev-workflow:ui-change-reminder"

STATE_DIR=".claude"
ENABLED_FLAG="${STATE_DIR}/.ui-verify-enabled"
PENDING_FLAG="${STATE_DIR}/.ui-verify-pending"

# Web PJ でなければ何もしない
[[ ! -f "$ENABLED_FLAG" ]] && safe_hook_error NotFound "ui-verify not enabled"

INPUT=$(safe_hook_input)

# tool_name と file_path を抽出
if command -v jq &>/dev/null; then
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
else
  TOOL_NAME=$(echo "$INPUT" | grep -oE '"tool_name"[[:space:]]*:[[:space:]]*"[^"]+"' | sed 's/.*"\([^"]*\)"$/\1/' | head -1)
  FILE_PATH=$(echo "$INPUT" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]+"' | sed 's/.*"\([^"]*\)"$/\1/' | head -1)
fi

# Edit/Write 以外は無視
case "$TOOL_NAME" in
  Edit|Write|MultiEdit) ;;
  *) safe_hook_error Validation "not an edit tool: $TOOL_NAME" ;;
esac

[[ -z "$FILE_PATH" ]] && safe_hook_error Validation "empty file_path"

# UI 関連拡張子の判定
if ! echo "$FILE_PATH" | grep -qiE '\.(tsx|jsx|vue|svelte|css|scss|sass|less|html|astro|mdx|module\.css|module\.scss)$'; then
  safe_hook_error Validation "not a UI file: $FILE_PATH"
fi

# pending flag を立てる（タイムスタンプを記録）
mkdir -p "$STATE_DIR"
date -u +%Y-%m-%dT%H:%M:%SZ > "$PENDING_FLAG"

# reminder 注入（短め）
BASENAME=$(basename "$FILE_PATH")
safe_hook_emit "[ui-verify] UI ファイル変更を検知（${BASENAME}）。動作未確認なら /ui-verify snap で現状 screenshot + console チェック推奨。"
