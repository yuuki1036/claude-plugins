#!/usr/bin/env bash
# ui-verify-gate.sh — PreToolUse hook (Bash: git commit)
# pending flag があれば commit 前に ui-verify 実行を促す

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "dev-workflow:ui-verify-gate"

STATE_DIR=".claude"
PENDING_FLAG="${STATE_DIR}/.ui-verify-pending"
ENABLED_FLAG="${STATE_DIR}/.ui-verify-enabled"

[[ ! -f "$ENABLED_FLAG" ]] && safe_hook_error NotFound "ui-verify not enabled"
[[ ! -f "$PENDING_FLAG" ]] && safe_hook_error NotFound "no pending ui change"

PENDING_SINCE=$(cat "$PENDING_FLAG" 2>/dev/null || echo "unknown")

cat <<EOF
[ui-verify] UI 変更（${PENDING_SINCE}）後、動作確認が記録されていません。
コミット前に /ui-verify snap で screenshot + console チェックを検討してください。
（確認済みで不要なら rm ${PENDING_FLAG} で無視可能）
EOF
