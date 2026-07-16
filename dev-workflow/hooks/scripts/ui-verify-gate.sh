#!/usr/bin/env bash
# ui-verify-gate.sh — PreToolUse hook (Bash: git commit)
# pending flag があれば commit 前に ui-verify 実行を促す

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "dev-workflow:ui-verify-gate"

# hooks.json の `if:` は実行環境によって評価されないことがある（push-reminder で実測）。
# 同型リスクの予防として、スクリプト内でも command を自己判定する（二重ゲート）
INPUT=$(safe_hook_input)
if command -v jq &>/dev/null; then
  COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
else
  COMMAND=$(echo "$INPUT" | grep -oE '"command"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*"command"[[:space:]]*:[[:space:]]*"([^"]+)"/\1/')
fi
[ -z "$COMMAND" ] && safe_hook_error Validation "empty command"
# クオート内文字列を除去してから判定（push-reminder.sh と同方式）
CMD_STRIPPED=$(printf '%s' "$COMMAND" | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g")
if ! printf '%s\n' "$CMD_STRIPPED" | grep -qE '(^|[^[:alnum:]_])git[[:space:]]+((-C|-c)[[:space:]]+[^[:space:]]+[[:space:]]+|--?[^[:space:]]+[[:space:]]+)*commit([[:space:]]|$)'; then
  safe_hook_error Validation "not a git commit command"
fi

STATE_DIR=".claude"
PENDING_FLAG="${STATE_DIR}/.ui-verify-pending"
ENABLED_FLAG="${STATE_DIR}/.ui-verify-enabled"

[[ ! -f "$ENABLED_FLAG" ]] && safe_hook_error NotFound "ui-verify not enabled"
[[ ! -f "$PENDING_FLAG" ]] && safe_hook_error NotFound "no pending ui change"

# 3 値仕様: 1 行目が verify ステータス、2 行目以降がタイムスタンプ
PENDING_STATUS=$(head -1 "$PENDING_FLAG" 2>/dev/null || echo "unverified")
PENDING_SINCE=$(sed -n '2p' "$PENDING_FLAG" 2>/dev/null || echo "unknown")

# verified-* なら reminder を出さない
case "$PENDING_STATUS" in
  verified-local|verified-snap) safe_hook_error NotFound "ui change already verified ($PENDING_STATUS)" ;;
esac

cat <<EOF
[ui-verify] UI 変更（${PENDING_SINCE}）後、動作確認が記録されていません（status: ${PENDING_STATUS}）。
コミット前に /ui-verify snap で screenshot + console チェックを検討してください。
（既に確認済みなら、git-commit-helper の Step 4.5 で「ローカル目視済み」を選択するか、rm ${PENDING_FLAG} で無視可能）
EOF
