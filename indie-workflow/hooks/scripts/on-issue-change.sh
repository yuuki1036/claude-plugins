#!/usr/bin/env bash
# FileChanged: Issue ファイルの外部変更を検知して通知

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "indie-workflow:on-issue-change"

safe_hook_emit "Issue ファイルが外部で変更されました。最新の内容を Read して確認してください。"
