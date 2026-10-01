#!/usr/bin/env bash
# branch-drift-record.sh — PostToolUse(Bash)。コマンドの実行後のブランチをセッションごとに記録する
#
# branch-drift-guard.sh が、次の git 書き込みの前に「自分の直前のコマンド以降にブランチが
# 変わったか」を見るための記録（GitHub issue #270）。このセッション自身の checkout は実行直後に
# ここで記録されるので、guard が止めるのは別セッション・手動の切り替えだけになる。
# 何も出力しない。記録できないとき（git でない・session_id が無い）は黙って終わる。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "guardrail-protect:branch-drift-record"
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/session-branch.sh"

command -v jq >/dev/null 2>&1 || safe_hook_error Dependency "jq not installed"

input=$(safe_hook_input)
tool_name=$(jq -r '.tool_name // empty' <<< "$input" 2>/dev/null || true)
if [ -n "$tool_name" ] && [ "$tool_name" != "Bash" ]; then
  safe_hook_error Validation "not a Bash tool: ${tool_name}"
fi
sid=$(jq -r '.session_id // empty' <<< "$input" 2>/dev/null || true)
dir=$(jq -r '.cwd // empty' <<< "$input" 2>/dev/null || true)
[ -n "$dir" ] || dir=$PWD

file=$(session_branch_file "$dir" "$sid")
[ -n "$file" ] || safe_hook_error Validation "no session id or not a git work tree"
branch=$(session_branch_current "$dir")
[ -n "$branch" ] || safe_hook_error Validation "branch unresolved"
session_branch_write "$file" "$branch"
exit 0
