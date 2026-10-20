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
  TOOL_NAME=$(echo "$INPUT" | grep -oE '"tool_name"[[:space:]]*:[[:space:]]*"[^"]+"' | sed 's/.*"\([^"]*\)"$/\1/' | head -1 || true)
  FILE_PATH=$(echo "$INPUT" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]+"' | sed 's/.*"\([^"]*\)"$/\1/' | head -1 || true)
fi

# Edit/Write 以外は無視
case "$TOOL_NAME" in
  Edit|Write|MultiEdit) ;;
  *) safe_hook_error Validation "not an edit tool: $TOOL_NAME" ;;
esac

[[ -z "$FILE_PATH" ]] && safe_hook_error Validation "empty file_path"

# UI 関連拡張子の判定（式の正本は scripts/lib/ui-paths.sh。ui-impact.sh と共有する）
# 読めるかを先に見る: bash 3.2（macOS の /bin/bash）は set -e 下で `. <無いファイル> || …` の
# `||` に入らず、その場で exit 1 する（ERR trap を通らないので safe-hook の分類も Unexpected も出ず、
# bash の No such file だけが stderr に残る）
UI_PATHS_LIB="${CLAUDE_PLUGIN_ROOT}/scripts/lib/ui-paths.sh"
if [[ ! -r "$UI_PATHS_LIB" ]]; then
  safe_hook_error Dependency "ui-paths.sh missing"
fi
# shellcheck source=../../scripts/lib/ui-paths.sh
. "$UI_PATHS_LIB"
if ! echo "$FILE_PATH" | grep -qiE "$UI_PATH_ERE"; then
  safe_hook_error Validation "not a UI file: $FILE_PATH"
fi

# pending flag を立てる（3 値仕様: unverified | verified-local | verified-snap）
# 既存値が verified-* なら上書きしない（後続の編集は未確認扱いに戻すべき判断もあるが、
# 1 セッション中の小修正で毎回 verified を消すと UX が悪いため、初回のみ書き込む）
mkdir -p "$STATE_DIR"
if [[ ! -f "$PENDING_FLAG" ]]; then
  printf 'unverified\n%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$PENDING_FLAG"
fi

# reminder 注入（短め）
BASENAME=$(basename "$FILE_PATH")
safe_hook_emit "[ui-verify] UI ファイル変更を検知（${BASENAME}）。動作未確認なら /ui-verify snap で現状 screenshot + console チェック推奨。"
