#!/usr/bin/env bash
# pre-commit-guard.sh
#
# Bash で git commit を実行する際、--no-verify / -n フラグの使用を検出して
# exit 2 でブロックする。commit message 内の文字列（heredoc body / quoted
# string）は剥がしてから検査するため、justify を書きたいケースは誤検知しない。
#
# 検出ロジック:
#   1. heredoc (<<'EOF' .. EOF, <<EOF .. EOF) のボディを除去
#   2. シングルクォート / ダブルクォート文字列を除去
#   3. 残ったコマンド本体に対して --no-verify / -n を境界マッチ

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "guardrail-protect:pre-commit-guard"

input=$(safe_hook_input)
tool_name=$(jq -r '.tool_name // empty' <<< "$input" 2>/dev/null)
cmd=$(jq -r '.tool_input.command // empty' <<< "$input" 2>/dev/null)

[ -z "$cmd" ] && safe_hook_error Validation "no command in tool_input"

# git commit でないなら no-op
case "$cmd" in
  *"git commit"*) ;;
  *) exit 0 ;;
esac

# heredoc body を剥がす（<<'TAG' ... TAG / <<TAG ... TAG / <<-TAG ... TAG）
stripped=$(perl -0777 -pe "s/<<-?\\s*['\"]?(\w+)['\"]?\\s*\n.*?\n\\1//gs" <<< "$cmd")

# シングルクォート / ダブルクォート文字列を剥がす
stripped=$(perl -pe "s/'([^'\\\\]|\\\\.)*'//g; s/\"([^\"\\\\]|\\\\.)*\"//g" <<< "$stripped")

# --no-verify / -n フラグの境界マッチ
# (^| ) で前境界、( |$) で後境界。-n は -m と区別するため厳密マッチ
if grep -qE '(^| )(--no-verify|-n)( |$)' <<< "$stripped"; then
  cat >&2 <<EOF
[guardrail-protect] Refusing to bypass git hooks

Detected: --no-verify or -n flag in git commit command.
Bypassing pre-commit / commit-msg hooks weakens the project's quality guardrails.

If hooks fail, fix the underlying issue rather than bypassing.
If bypass is genuinely required:
  1. Justify in commit body (why bypassing is necessary, what was checked manually)
  2. Temporarily disable this hook via Claude Code permissions, NOT --no-verify
  3. Document the bypass in CHANGELOG / commit log

Tool: $tool_name
Stripped command: $stripped
EOF
  exit 2
fi

exit 0
