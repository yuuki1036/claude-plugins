#!/usr/bin/env bash
# branch-drift-guard.sh — PreToolUse(Bash)。git の書き込みの前に、ブランチが自分の知らない間に
# 変わっていないかを確かめる（GitHub issue #270）
#
# 1 つのチェックアウトを複数のセッションで共有していると、別セッションのブランチ切り替えに
# 気づかないまま merge / commit / push を打つ。実例では、別セッションが切り替えたブランチに
# 自分の Issue ブランチのつもりで merge を打ち、未コミットの変更があったので中断して済んだ。
#
# 照合元は branch-drift-record.sh が記録した「このセッションの直前のコマンドの後のブランチ」。
# 記録が無い（セッションの最初の git 書き込み・別の作業ツリー）ときは何もしない。
# 止めたときは記録を今のブランチに更新する — 意図を確かめたうえでの再実行は通す。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "guardrail-protect:branch-drift-guard"
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/session-branch.sh"

command -v jq >/dev/null 2>&1 || safe_hook_error Unexpected "jq not installed; guard cannot inspect command"

input=$(safe_hook_input)
tool_name=$(jq -r '.tool_name // empty' <<< "$input" 2>/dev/null || true)
cmd=$(jq -r '.tool_input.command // empty' <<< "$input" 2>/dev/null || true)
if [ -n "$tool_name" ] && [ "$tool_name" != "Bash" ]; then
  safe_hook_error Validation "not a Bash tool: ${tool_name}"
fi
[ -n "$cmd" ] || safe_hook_error Validation "no command in tool_input"

# git の書き込み（ブランチの履歴・remote を動かすもの）。`git -C <dir>` は別の作業ツリーを
# 指しうるので対象にしない（照合元はこの作業ツリーの記録だけ）
WRITE_RE='(^|[;&|({[:space:]])git([[:space:]]+-c[[:space:]]+[^[:space:]]+)*[[:space:]]+(commit|merge|push|pull|rebase|reset|cherry-pick|revert|am)([[:space:]]|$)'
printf '%s\n' "$cmd" | grep -qE -e "$WRITE_RE" || exit 0

sid=$(jq -r '.session_id // empty' <<< "$input" 2>/dev/null || true)
dir=$(jq -r '.cwd // empty' <<< "$input" 2>/dev/null || true)
[ -n "$dir" ] || dir=$PWD
file=$(session_branch_file "$dir" "$sid")
[ -n "$file" ] || exit 0
[ -f "$file" ] || exit 0
known=$(head -1 "$file" 2>/dev/null || true)
now=$(session_branch_current "$dir")
if [ -z "$known" ] || [ -z "$now" ] || [ "$known" = "$now" ]; then
  exit 0
fi

session_branch_write "$file" "$now"
cat >&2 <<MSG
[guardrail-protect] このセッションの直前のコマンドの後で、ブランチが切り替わっています

  直前: ${known}
  現在: ${now}

このセッションは切り替えていないので、別のセッションか手動の操作で変わった可能性があります。
git の書き込み（merge / commit / push 等）を止めました。

- 現在のブランチで合っていれば、そのまま同じコマンドをもう一度実行してください（記録は更新済み）
- 別のブランチで作業したいなら、共有のチェックアウトを切り替えず、一時 worktree を使ってください:
    git worktree add ../<dir> <branch>
MSG
exit 2
