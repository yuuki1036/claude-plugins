---
description: "Web UI の動作確認・スタイル調整・スクリーンショット取得を chrome-devtools MCP で自動化する"
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
  - Glob
  - Grep
  - mcp__chrome-devtools__navigate_page
  - mcp__chrome-devtools__new_page
  - mcp__chrome-devtools__select_page
  - mcp__chrome-devtools__list_pages
  - mcp__chrome-devtools__close_page
  - mcp__chrome-devtools__take_screenshot
  - mcp__chrome-devtools__take_snapshot
  - mcp__chrome-devtools__list_console_messages
  - mcp__chrome-devtools__list_network_requests
  - mcp__chrome-devtools__get_console_message
  - mcp__chrome-devtools__get_network_request
  - mcp__chrome-devtools__resize_page
  - mcp__chrome-devtools__emulate
  - mcp__chrome-devtools__click
  - mcp__chrome-devtools__hover
  - mcp__chrome-devtools__fill
  - mcp__chrome-devtools__fill_form
  - mcp__chrome-devtools__press_key
  - mcp__chrome-devtools__type_text
  - mcp__chrome-devtools__wait_for
  - mcp__chrome-devtools__evaluate_script
  - mcp__chrome-devtools__handle_dialog
---

ui-verify スキルを使用して、Web UI の動作確認・スタイル調整・スクリーンショット取得を実行してください。

引数が渡されていればそれも考慮してください（例: `verify`, `tune`, `snap`, 対象 URL やパス）。
引数がなければユーザーに使用モードを確認してください。
