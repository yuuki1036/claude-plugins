#!/usr/bin/env bash
# transcript-count-guard.sh
#
# transcript を grep で数えて、system prompt のツール定義・スキル一覧に当たる書き方を PreToolUse で
# 知らせる（GitHub issue #342）。判定は `detect-transcript-count.py`（当たる形・黙る形の根拠はその docstring）。
#
# 止めない。transcript の素の grep には正当な用途（語の出現を見る・ファイルを探す）があり、
# 誤るのは件数を呼び出し回数として読んだときだけなので、コンテキストに注意を出して通す。
# 実測で 5 日に 3 回、呼び出し 0 回を 116 / 204 件と数えた。CLAUDE.md の「未知のデータは 1 件ダンプ
# して構造を確かめる」は、見慣れた transcript では引き金が引かれなかった。
#
# 黙る条件: `.claude/projects` と grep / rg の両方を含まない / 検出器が何も返さない。
#
# fail-open: jq / python3 が無ければ Unexpected を通知して通す（守るのは集計の正しさで、安全性ではない）。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "guardrail-protect:transcript-count-guard"

command -v jq      >/dev/null 2>&1 || safe_hook_error Unexpected "jq not installed; transcript-count-guard skipped"
command -v python3 >/dev/null 2>&1 || safe_hook_error Unexpected "python3 not installed; transcript-count-guard skipped"

input=$(safe_hook_input)
tool_name=$(jq -r '.tool_name // empty' <<< "$input" 2>/dev/null || true)
cmd=$(jq -r '.tool_input.command // empty' <<< "$input" 2>/dev/null || true)

# **matcher 単独に依存しない**（CLAUDE.md Gotchas の二重ゲート規約）
if [ -n "$tool_name" ] && [ "$tool_name" != "Bash" ]; then
  safe_hook_error Validation "not a Bash tool: ${tool_name}"
fi
[ -z "$cmd" ] && safe_hook_error Validation "no command in tool_input"

# 安価な事前フィルタ: 全 Bash 呼び出しに効くので、当たりえないコマンドでは python を起動しない
case "$cmd" in
  *.claude/projects*) ;;
  *) exit 0 ;;
esac
case "$cmd" in
  *grep*|*rg*) ;;
  *) exit 0 ;;
esac

detection=$(printf '%s' "$cmd" | python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/detect-transcript-count.py") && rc=0 || rc=$?
if [ "$rc" -ne 0 ]; then
  safe_hook_error Unexpected "transcript count detector failed (rc=${rc})"
fi
[ -n "$detection" ] || exit 0

segment=$(cut -f2- <<< "$detection")

safe_hook_emit_context PreToolUse "[guardrail-protect] transcript-count-guard: transcript を grep で数えている（\`${segment}\`）。transcript には system prompt のツール定義（\`\"name\":\"<tool>\"\` を含む）とスキル一覧も入っているので、素の名前でも \`\"name\":\"<tool>\"\` の形でも、呼び出しが 0 回の transcript に当たる。呼び出しを数えるなら jq で \`select(.type==\"assistant\") | .message.content[]? | select(.type==\"tool_use\")\` に絞る（スキルは \`.name==\"Skill\"\` の \`.input.skill\`）。\`type==\"assistant\"\` を外すと、会話履歴の写し（\`api-request-blob\`）の分も数えて二重になる。"
exit 0
