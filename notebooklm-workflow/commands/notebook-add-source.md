---
description: "NotebookLM のノートに URL / PDF / YouTube / Google Drive のソースを追加"
argument-hint: "[ノート名] <source-url-or-path>"
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
  - mcp__plugin_notebooklm-workflow_notebooklm-mcp__notebook_list
  - mcp__plugin_notebooklm-workflow_notebooklm-mcp__source_add
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/notebook-source-adder/SKILL.md` を Read し、その手順に従う**（command 名と skill 名が違うので、`/notebook-add-source` でも `Skill` tool の `notebooklm-workflow:notebook-add-source` でもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `notebooklm-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

notebook-source-adder スキルを使用して、NotebookLM のノートにソースを追加してください。

引数が渡されていればそれも考慮してください（例: 対象ノート名、追加する URL / ファイルパス）。追加するソースが分からなければユーザーに確認する。対象ノートの決め方（一覧を取り、複数候補なら AskUserQuestion で選ばせる）は SKILL.md の Step 2 に従う。
