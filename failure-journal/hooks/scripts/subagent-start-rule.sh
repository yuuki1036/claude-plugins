#!/usr/bin/env bash
# subagent-start-rule.sh — SubagentStart hook
# 永続成果物に書く具体値の規約（concrete-value-rule.md）を subagent の文脈へ注入する（GitHub issue #428）
#
# 設計方針:
#   - subagent は SessionStart / PostCompact の注入を受けない。認識系の失敗（出典なき主張・
#     API の形の推測・CLI の読み違い）の多くは explorer / reviewer が返す事実主張から入るので、
#     SubagentStart の additionalContext で同じ規約を届ける
#   - self-report-rule.md（candidates.jsonl への自己申告）は注入しない。subagent に journal を
#     書かせるかは別の判断で、ここでは事実主張の規約だけを届ける
#   - journal ディレクトリは作らない（subagent の起動ごとに書き込みを増やさない。作るのは
#     session-start-init.sh の役目）

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "failure-journal:subagent-start-rule"

INPUT=$(safe_hook_input)

# hooks.json のイベント指定だけに頼らず、payload のイベント名で自己判定する（CLAUDE.md Gotchas）
EVENT=""
if command -v jq >/dev/null 2>&1; then
  EVENT=$(jq -r '.hook_event_name // empty' <<< "$INPUT" 2>/dev/null || true)
elif command -v python3 >/dev/null 2>&1; then
  EVENT=$(printf '%s' "$INPUT" | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    print(d.get("hook_event_name", "") if isinstance(d, dict) else "")
except Exception:
    pass' 2>/dev/null || true)
fi
if [ "$EVENT" != "SubagentStart" ]; then
  safe_hook_error Validation "not SubagentStart"
fi

RULE="${CLAUDE_PLUGIN_ROOT}/rules/concrete-value-rule.md"
if [ ! -f "$RULE" ]; then
  safe_hook_error NotFound "concrete-value-rule.md missing"
fi

safe_hook_emit_context "SubagentStart" "$(cat "$RULE")"
