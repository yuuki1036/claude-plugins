---
description: "Web UI の動作確認・スタイル調整・スクリーンショット取得を chrome-devtools MCP で自動化する"
allowed-tools:
  - Bash
  - Read
  - Edit
  - mcp__chrome-devtools__navigate_page
  - mcp__chrome-devtools__new_page
  - mcp__chrome-devtools__take_screenshot
  - mcp__chrome-devtools__take_snapshot
  - mcp__chrome-devtools__list_console_messages
  - mcp__chrome-devtools__list_network_requests
  - mcp__chrome-devtools__resize_page
  - mcp__chrome-devtools__click
  - mcp__chrome-devtools__hover
  - mcp__chrome-devtools__fill
  - mcp__chrome-devtools__press_key
  - mcp__chrome-devtools__wait_for
---

ui-verify スキルを使用して、Web UI の動作確認・スタイル調整・スクリーンショット取得を実行してください。

引数が渡されていればそれも考慮してください（例: `verify`, `tune`, `snap`, 対象 URL やパス）。
引数がなければユーザーに使用モードを確認してください。
