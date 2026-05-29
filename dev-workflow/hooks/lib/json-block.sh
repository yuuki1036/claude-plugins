#!/usr/bin/env bash
# json-block.sh — block 出力 JSON の共通フォーマッタ
#
# hook が PostToolUse などで decision:"block" を返すときの JSON を一元生成する。
# 長大なエラー全文を返すと Claude が要約に context を浪費するため、呼び出し側で
# head -20 + 総行数注記に丸めてから reason に渡すこと。
#
# 使い方（safe-hook.sh の source 後に source する）:
#   source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/json-block.sh"
#   emit_block_json "残った違反:\n..." "PostToolUse" "lint check failed for foo.ts"
#
# 出力は stdout に 1 行 JSON。これが block シグナルになるため、他の stdout と混在させない。

# 多重 source 防止
if [ -n "${__JSON_BLOCK_SOURCED:-}" ]; then
  return 0 2>/dev/null || exit 0
fi
__JSON_BLOCK_SOURCED=1

# emit_block_json <reason> [event] [additionalContext]
emit_block_json() {
  local reason="${1:-}" event="${2:-PostToolUse}" ctx="${3:-}"
  if command -v jq &>/dev/null; then
    jq -nc \
      --arg r "$reason" \
      --arg e "$event" \
      --arg c "$ctx" \
      '{decision:"block", reason:$r, hookSpecificOutput:{hookEventName:$e, additionalContext:$c}}'
  else
    # jq 無しフォールバック（最小限のエスケープ: \ " 改行）
    reason="${reason//\\/\\\\}"; reason="${reason//\"/\\\"}"; reason="${reason//$'\n'/\\n}"
    ctx="${ctx//\\/\\\\}"; ctx="${ctx//\"/\\\"}"; ctx="${ctx//$'\n'/\\n}"
    printf '{"decision":"block","reason":"%s","hookSpecificOutput":{"hookEventName":"%s","additionalContext":"%s"}}\n' \
      "$reason" "$event" "$ctx"
  fi
}
