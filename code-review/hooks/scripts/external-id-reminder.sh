#!/usr/bin/env bash
# external-id-reminder.sh — PreToolUse hook (Bash: git commit)
# staged なコード内コメントに git 外の参照 ID（Linear ID / Linear URL）が残っていたら
# 非ブロッキングで通知する。ブロックはしない（除去は comment-polish skill が人間承認で行う）。
# 設計: .claude/designs/20260912-e2e-verify-comment-polish-pr-flow.md (B-3)

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "code-review:external-id-reminder"

# hooks.json の if: は実行環境によって評価されないことがある（dev-workflow で実測）。
# スクリプト内でも command を自己判定する二重ゲート。
INPUT=$(safe_hook_input)
if command -v jq &>/dev/null; then
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
  COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
else
  TOOL_NAME=$(echo "$INPUT" | grep -oE '"tool_name"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*:[[:space:]]*"([^"]+)"/\1/' || true)
  COMMAND=$(echo "$INPUT" | grep -oE '"command"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*"command"[[:space:]]*:[[:space:]]*"([^"]+)"/\1/' || true)
fi

[ "$TOOL_NAME" != "Bash" ] && safe_hook_error Validation "not a Bash tool"
[ -z "$COMMAND" ] && safe_hook_error Validation "empty command"

# クオート内を除去してから git commit 判定（コミットメッセージ中の言及での誤発火防止）
CMD_STRIPPED=$(printf '%s' "$COMMAND" | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g")
if ! printf '%s\n' "$CMD_STRIPPED" | grep -qE '(^|[^[:alnum:]_])git[[:space:]]+((-C|-c)[[:space:]]+[^[:space:]]+[[:space:]]+|--?[^[:space:]]+[[:space:]]+)*commit([[:space:]]|$)'; then
  safe_hook_error Validation "not a git commit command"
fi

git rev-parse --git-dir >/dev/null 2>&1 || safe_hook_error NotFound "not a git repository"

DETECT="${CLAUDE_PLUGIN_ROOT}/scripts/detect-external-ids.sh"
[ -f "$DETECT" ] || safe_hook_error NotFound "detector missing"

# staged diff に対して検出（exit 1 = 検出あり）。set -e 下で非ゼロを握り潰す。
COUNT=0
OUT="$(bash "$DETECT" --staged 2>/dev/null)" && RC=0 || RC=$?
if [ "$RC" = 1 ] && [ -n "$OUT" ]; then
  COUNT=$(printf '%s\n' "$OUT" | grep -c . || true)
fi
[ "$COUNT" -eq 0 ] && safe_hook_error NotFound "no external id in staged comments"

safe_hook_emit_context "PreToolUse" "[comment] staged なコメントに git 外の参照 ID が ${COUNT} 件あります（Linear ID / URL）。コミット前に /comment-polish --staged で精査・除去できます（背景の文は残し ID だけ落とします）。"
