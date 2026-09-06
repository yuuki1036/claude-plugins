---
description: "Issue ファイルの品質整理・knowledge 切り出し トリガー: 「Issue整理」「Issue更新」「セッション終了前にIssue更新」「/issue-maintain」"
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Bash
  - Skill
  - AskUserQuestion
argument-hint: ""
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/issue-maintain/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `issue-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

issue-maintain スキルを使って Issue ファイルのメンテナンスを実行してください。
