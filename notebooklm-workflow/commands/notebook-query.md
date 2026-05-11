---
description: "NotebookLM の既存ノートに質問・要約を実行"
allowed-tools:
  - Bash
  - AskUserQuestion
  - mcp__plugin_notebooklm-workflow_notebooklm-mcp__notebook_list
  - mcp__plugin_notebooklm-workflow_notebooklm-mcp__notebook_query
---

notebook-query-assistant スキルを使用して、NotebookLM ノートに対する Q&A・要約を実行してください。

引数が渡されていればそれも考慮してください（例: 対象ノート名、質問文、`--summarize` フラグ）。
引数がなければユーザーに対象ノートと質問内容を確認してください。

`--summarize` フラグが含まれている場合は、定型の全体要約クエリ（references/query-patterns.md 参照）を使ってください。
