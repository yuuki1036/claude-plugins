#!/usr/bin/env bash
# FileChanged: Issue ファイルの外部変更を検知して通知 + issue:completed イベント発行

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "linear-workflow:on-issue-change"

payload=$(safe_hook_input)

# Claude Code の FileChanged hook payload から変更ファイルパスを抽出
file_path=$(printf '%s' "$payload" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*:[[:space:]]*"([^"]+)"/\1/')

# Issue ファイルへの変更で status: completed が立った場合に Event Bus へ発行
if [ -n "$file_path" ] && [ -f "$file_path" ]; then
  if echo "$file_path" | grep -qE '\.claude/linear/[^/]+/issues/[^/]+\.md$'; then
    if grep -qE '^status:[[:space:]]*completed' "$file_path"; then
      issue_id=$(basename "$file_path" .md)
      slug=$(echo "$file_path" | sed -E 's|.*\.claude/linear/([^/]+)/issues/.*|\1|')
      event_bus_publish "issue:completed" "{\"issue_id\":\"${issue_id}\",\"slug\":\"${slug}\",\"file\":\"${file_path}\"}"
    fi
  fi
fi

safe_hook_emit_context "FileChanged" "Issue ファイルが外部で変更されました。最新の内容を Read して確認してください。"
