---
description: "Linear プロジェクトのダッシュボード表示（引数なしでフル、Issue ID 指定でスコープド） トリガー: 「ダッシュボード」「プロジェクト状況」「全体確認」「進捗確認」 「子Issueの進捗」「エピック進捗」「状況を見せて」「/dashboard」"
allowed-tools:
  - mcp__linear__get_issue
  - mcp__linear__list_issues
  - Read
  - Glob
  - AskUserQuestion
argument-hint: "[ISSUE-ID]"
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/dashboard/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `issue-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

dashboard スキルを使って、ダッシュボードを表示してください。
引数が指定された場合はスコープドダッシュボードモードで実行してください。
