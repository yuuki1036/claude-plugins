---
description: "NotebookLM の既存ノートに質問・要約を実行"
argument-hint: "[ノート名] <質問文 | --summarize>"
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
  - mcp__plugin_notebooklm-workflow_notebooklm-mcp__notebook_list
  - mcp__plugin_notebooklm-workflow_notebooklm-mcp__notebook_query
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/notebook-query-assistant/SKILL.md` を Read し、その手順に従う**（command 名と skill 名が違うので、`/notebook-query` でも `Skill` tool の `notebooklm-workflow:notebook-query` でもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `notebooklm-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

notebook-query-assistant スキルを使用して、NotebookLM ノートに対する Q&A・要約を実行してください。

引数が渡されていればそれも考慮してください（例: 対象ノート名、質問文、`--summarize` フラグ）。質問内容が分からなければユーザーに確認する。対象ノートの決め方は SKILL.md の手順に従う。

`--summarize` フラグが含まれている場合は、定型の全体要約クエリ（references/query-patterns.md 参照）を使ってください。
