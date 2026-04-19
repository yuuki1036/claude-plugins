#!/usr/bin/env bash
# FileChanged: Knowledge ファイルの外部変更を検知して通知

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "linear-workflow:on-knowledge-change"

safe_hook_emit "Knowledge ファイルが外部で更新されました。内容を Read して活用してください。"
