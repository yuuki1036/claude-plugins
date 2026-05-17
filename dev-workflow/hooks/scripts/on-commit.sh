#!/usr/bin/env bash
# on-commit.sh — PostToolUse hook (Bash matcher)
# git commit が成功した直後に `commit:created` イベントを Event Bus へ発行する

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "dev-workflow:on-commit"

INPUT=$(safe_hook_input)

# tool_input.command を抽出
if command -v jq &>/dev/null; then
  COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
else
  COMMAND=$(echo "$INPUT" | grep -oE '"command"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*"command"[[:space:]]*:[[:space:]]*"([^"]+)"/\1/')
  TOOL_NAME=$(echo "$INPUT" | grep -oE '"tool_name"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*"tool_name"[[:space:]]*:[[:space:]]*"([^"]+)"/\1/')
fi

# Bash 以外は無視
[ "$TOOL_NAME" != "Bash" ] && safe_hook_error Validation "not a Bash tool: $TOOL_NAME"
[ -z "$COMMAND" ] && safe_hook_error Validation "empty command"

# git commit 系のみ反応（rebase/amend/--dry-run/--help 等は除外）
# 「git commit」が単語境界で出現し、かつ除外フラグを含まない場合のみ通す
if ! echo "$COMMAND" | grep -qE '(^|[^[:alnum:]_])git[[:space:]]+commit([[:space:]]|$)'; then
  safe_hook_error Validation "not a git commit command"
fi
if echo "$COMMAND" | grep -qE -- '--dry-run|--help|--amend'; then
  # --amend は HEAD を上書きする系なので、新規 commit イベントとは扱わない（dedup の責務をこちらに寄せる）
  safe_hook_error Validation "skipped commit flavor"
fi

# git リポジトリ外なら無視
git rev-parse --git-dir >/dev/null 2>&1 || safe_hook_error NotFound "not a git repository"

# 直近 commit の情報を取得（commit が成功していることが前提。失敗していたら HEAD が変わらず古いコミットを拾うので、payload に lastModified を含めて冪等性キーにする）
SHA=$(git log -1 --format=%h 2>/dev/null || true)
[ -z "$SHA" ] && safe_hook_error NotFound "no HEAD commit"

SUBJECT=$(git log -1 --format=%s 2>/dev/null || true)
# Conventional Commits の type を先頭から抽出（feat / fix / refactor / chore / docs / test / perf / ci / build / style / revert）
TYPE=$(printf '%s' "$SUBJECT" | grep -oE '^(feat|fix|refactor|chore|docs|test|perf|ci|build|style|revert)' | head -1)
[ -z "$TYPE" ] && TYPE="other"

# 変更ファイル数（git show --name-only は空行 + 各ファイル名で出力されるので 0 でない行を数える）
FILES_COUNT=$(git show --name-only --format= HEAD 2>/dev/null | grep -cvE '^$' || echo 0)
FILES_COUNT=$(printf '%s' "$FILES_COUNT" | tr -d '[:space:]')
[ -z "$FILES_COUNT" ] && FILES_COUNT=0

# 同じ HEAD に対する dedup は subscriber 側の責務（CLAUDE.md 規約）。ここでは fire-and-forget
event_bus_publish "commit:created" "{\"sha\":\"${SHA}\",\"type\":\"${TYPE}\",\"files\":${FILES_COUNT}}"

# PostToolUse なので stdout 注入は不要（無音 exit）
exit 0
