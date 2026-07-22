#!/usr/bin/env bash
# FileChanged: Issue ファイルの外部変更を検知して通知 + issue:completed イベント発行
# 注意: matcher 単独に依存せず、payload の file_path で発火条件を自己判定する（二重ゲート）

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "linear-workflow:on-issue-change"

payload=$(safe_hook_input)

# Claude Code の FileChanged hook payload から変更ファイルパスを抽出
file_path=$(printf '%s' "$payload" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*:[[:space:]]*"([^"]+)"/\1/')

# Issue ファイル以外（matcher 暴発時の任意ファイル）では何もしない
if [ -z "$file_path" ] || [ ! -f "$file_path" ] \
  || ! echo "$file_path" | grep -qE '\.claude/linear/[^/]+/issues/[^/]+\.md$'; then
  safe_hook_error Validation "not an issue file: ${file_path:-<empty>}"
fi

# status: completed が立った場合に Event Bus へ発行
if grep -qE '^status:[[:space:]]*completed' "$file_path"; then
  issue_id=$(basename "$file_path" .md | tr -d '"\\')
  slug=$(echo "$file_path" | sed -E 's|.*\.claude/linear/([^/]+)/issues/.*|\1|' | tr -d '"\\')
  # payload は生補間のため JSON を壊す文字を除去してから埋め込む
  safe_path=$(printf '%s' "$file_path" | tr -d '"\\')
  event_bus_publish "issue:completed" "{\"issue_id\":\"${issue_id}\",\"slug\":\"${slug}\",\"file\":\"${safe_path}\"}"
fi

safe_hook_emit_context "FileChanged" "Issue ファイルが外部で変更されました。最新の内容を Read して確認してください。"
