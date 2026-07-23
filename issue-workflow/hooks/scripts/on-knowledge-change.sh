#!/usr/bin/env bash
# FileChanged: Knowledge ファイルの外部変更を検知して通知
# 注意: matcher 単独に依存せず、payload の file_path で発火条件を自己判定する（二重ゲート）

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "issue-workflow:on-knowledge-change"

payload=$(safe_hook_input)

file_path=$(printf '%s' "$payload" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*:[[:space:]]*"([^"]+)"/\1/')

# knowledge ファイル以外（matcher 暴発時の任意ファイル）では何もしない
if [ -z "$file_path" ] \
  || ! echo "$file_path" | grep -qE '\.claude/(indie|linear)/[^/]+/knowledge/([^/]+/)?[^/]+\.md$'; then
  safe_hook_error Validation "not a knowledge file: ${file_path:-<empty>}"
fi

safe_hook_emit_context "FileChanged" "Knowledge ファイルが外部で更新されました。内容を Read して活用してください。"
