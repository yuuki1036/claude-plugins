---
description: "NotebookLM のノートに URL / PDF / YouTube / Google Drive のソースを追加"
argument-hint: "[ノート名] <source-url-or-path>"
allowed-tools:
  - Bash
  - AskUserQuestion
  - mcp__plugin_notebooklm-workflow_notebooklm-mcp__notebook_list
  - mcp__plugin_notebooklm-workflow_notebooklm-mcp__source_add
---

notebook-source-adder スキルを使用して、NotebookLM のノートにソースを追加してください。

引数が渡されていればそれも考慮してください（例: 対象ノート名、追加する URL / ファイルパス）。
引数がなければユーザーに対象ノートと追加するソースを確認してください。

ノートが複数候補ある場合は AskUserQuestion で選択 UI を必ず提示してください。
