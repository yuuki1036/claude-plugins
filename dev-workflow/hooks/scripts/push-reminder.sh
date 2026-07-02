#!/usr/bin/env bash
# push-reminder.sh — PreToolUse hook (Bash: git push)
# push 前にセルフレビュー（/self-review）の実行を促す
#
# 注意: PreToolUse の plain stdout は Claude への到達保証が弱いため、
# additionalContext（safe_hook_emit_context）で確実に注入する（block しない）。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "dev-workflow:push-reminder"

# stdin を消費（safe_hook_init が実施済み。参照はしない）
safe_hook_emit_context "PreToolUse" \
  "push 前にセルフレビュー（/self-review）の実行を検討してください。"
