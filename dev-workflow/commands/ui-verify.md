---
description: "Web UI の動作確認・スタイル調整・スクリーンショット取得を chrome-devtools MCP で自動化する トリガー: 「動作確認」「UIチェック」「スクリーンショット」「スタイル調整」「見た目確認」「レスポンシブ確認」「/ui-verify」「visual check」「screenshot」「UI verification」「responsive check」 引数: [verify|tune|snap] [target-url-or-path]"
allowed-tools:
  - Bash
  - Read
  - Edit
  - mcp__plugin_dev-workflow_chrome-devtools__navigate_page
  - mcp__plugin_dev-workflow_chrome-devtools__new_page
  - mcp__plugin_dev-workflow_chrome-devtools__take_screenshot
  - mcp__plugin_dev-workflow_chrome-devtools__take_snapshot
  - mcp__plugin_dev-workflow_chrome-devtools__list_console_messages
  - mcp__plugin_dev-workflow_chrome-devtools__list_network_requests
  - mcp__plugin_dev-workflow_chrome-devtools__resize_page
  - mcp__plugin_dev-workflow_chrome-devtools__emulate
  - mcp__plugin_dev-workflow_chrome-devtools__click
  - mcp__plugin_dev-workflow_chrome-devtools__hover
  - mcp__plugin_dev-workflow_chrome-devtools__fill
  - mcp__plugin_dev-workflow_chrome-devtools__press_key
  - mcp__plugin_dev-workflow_chrome-devtools__wait_for
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/ui-verify/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `dev-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

ui-verify スキルを使用して、Web UI の動作確認・スタイル調整・スクリーンショット取得を実行してください。

引数が渡されていればそれも考慮してください（例: `verify`, `tune`, `snap`, 対象 URL やパス）。
引数がなければユーザーに使用モードを確認してください。
