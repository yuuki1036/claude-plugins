---
description: "Issue を 1 件 新規作成 + ブランチ自動作成。Linear 連携時は既存 Issue 1 件を取り込んでファイル化する トリガー: 「タスク作成」「Issue起票」「新しいタスク」「Issueファイル作成」「Linear の Issue をローカルに取り込む」「/issue-create」"
allowed-tools:
  - mcp__linear__get_issue
  - mcp__linear__list_comments
  - Read
  - Write
  - Glob
  - Grep
  - Bash
  - Skill
  - AskUserQuestion
argument-hint: "[PROJECT-SLUG]"
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/issue-create/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `issue-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

issue-create スキルを使って、Issue ファイルを新規作成してください。引数でプロジェクトスラッグが指定されていればそれを使用し、未指定ならブランチ名から推定するかユーザーに確認してください。
