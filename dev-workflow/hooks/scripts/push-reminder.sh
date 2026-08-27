#!/usr/bin/env bash
# push-reminder.sh — PreToolUse hook (Bash: git push)
# push 前にセルフレビュー（/code-review:self-review）の実行を促す
#
# 注意: PreToolUse の plain stdout は Claude への到達保証が弱いため、
# additionalContext（safe_hook_emit_context）で確実に注入する（block しない）。
#
# hooks.json の `if: "Bash(git push *)"` は実行環境によって評価されない
# ことが実測されている（全 Bash 呼び出しで発火する暴発）。if:/matcher に
# 単独依存せず、スクリプト内で command を自己判定する（二重ゲート）。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "dev-workflow:push-reminder"

INPUT=$(safe_hook_input)
if command -v jq &>/dev/null; then
  COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
else
  COMMAND=$(echo "$INPUT" | grep -oE '"command"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*"command"[[:space:]]*:[[:space:]]*"([^"]+)"/\1/' || true)
fi
[ -z "$COMMAND" ] && safe_hook_error Validation "empty command"

# git push が単語境界で出現する場合のみ通す（if: 不発時の暴発防止）。
# クオート内文字列を除去してから判定し（コミットメッセージ中の "git push" 等での
# 誤発火防止）、-C <dir> / -c <k=v> / --no-pager 等のグローバルオプション経由も拾う
CMD_STRIPPED=$(printf '%s' "$COMMAND" | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g")
if ! printf '%s\n' "$CMD_STRIPPED" | grep -qE '(^|[^[:alnum:]_])git[[:space:]]+((-C|-c)[[:space:]]+[^[:space:]]+[[:space:]]+|--?[^[:space:]]+[[:space:]]+)*push([[:space:]]|$)'; then
  safe_hook_error Validation "not a git push command"
fi

safe_hook_emit_context "PreToolUse" \
  "push 前にセルフレビュー（/code-review:self-review）の実行を検討してください。"
