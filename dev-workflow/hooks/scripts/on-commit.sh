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
  COMMAND=$(echo "$INPUT" | grep -oE '"command"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*"command"[[:space:]]*:[[:space:]]*"([^"]+)"/\1/' || true)
  TOOL_NAME=$(echo "$INPUT" | grep -oE '"tool_name"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*"tool_name"[[:space:]]*:[[:space:]]*"([^"]+)"/\1/' || true)
fi

# Bash 以外は無視
[ "$TOOL_NAME" != "Bash" ] && safe_hook_error Validation "not a Bash tool: $TOOL_NAME"
[ -z "$COMMAND" ] && safe_hook_error Validation "empty command"

# git commit 系のみ反応（rebase/amend/--dry-run/--help 等は除外）
# 「git commit」が単語境界で出現し、かつ除外フラグを含まない場合のみ通す。
# クオート内文字列を除去してから判定（コミットメッセージ中の "git commit" や
# "--amend" 言及での誤判定防止。push-reminder.sh と同方式）
CMD_STRIPPED=$(printf '%s' "$COMMAND" | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g")
if ! printf '%s\n' "$CMD_STRIPPED" | grep -qE '(^|[^[:alnum:]_])git[[:space:]]+((-C|-c)[[:space:]]+[^[:space:]]+[[:space:]]+|--?[^[:space:]]+[[:space:]]+)*commit([[:space:]]|$)'; then
  safe_hook_error Validation "not a git commit command"
fi
if printf '%s\n' "$CMD_STRIPPED" | grep -qE -- '--dry-run|--help|--amend'; then
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
# **`|| true` が要る**: 型なしメッセージだと grep が exit 1 を返し, safe-hook の ERR trap が
# 発火して**イベントを publish せずに exit 0 する**（型なしコミットで publish が丸ごと落ちる）
TYPE=$(printf '%s' "$SUBJECT" | grep -oE '^(feat|fix|refactor|chore|docs|test|perf|ci|build|style|revert)' | head -1 || true)
[ -z "$TYPE" ] && TYPE="other"

# 変更ファイル数（diff-tree -m --first-parent でマージコミットでも第一親との差分を数える）。
# --root: 親の無い最初のコミットでも空にならない（無いと 0 件になる）
#
# `|| echo 0` は使わない。**grep -c は 0 件でも "0" を出したうえで exit 1 する**ので、
# フォールバックが二重に出て "00" になり、payload が invalid JSON になる
# （event log の 1 行が壊れると、読み手が丸ごとパースできなくなる）
FILES_COUNT=$(git diff-tree --root --no-commit-id --name-only -r -m --first-parent HEAD 2>/dev/null | grep -cvE '^$' || true)
FILES_COUNT=$(printf '%s' "$FILES_COUNT" | tr -d '[:space:]')
# 数値以外が入り込んだら 0 に落とす（payload の JSON 妥当性は publisher の責務）
case "$FILES_COUNT" in ''|*[!0-9]*) FILES_COUNT=0 ;; esac

# 同じ HEAD に対する dedup は subscriber 側の責務（CLAUDE.md 規約）。ここでは fire-and-forget
event_bus_publish "commit:created" "{\"sha\":\"${SHA}\",\"type\":\"${TYPE}\",\"files\":${FILES_COUNT}}"

# PostToolUse なので stdout 注入は不要（無音 exit）
exit 0
