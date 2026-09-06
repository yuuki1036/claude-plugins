---
description: "プロジェクトの初期セットアップ（backend 選択 + データディレクトリ作成） トリガー: 「プロジェクト初期化」「issue 管理セットアップ」「プロジェクトセットアップ」「/issue-workflow:init」"
allowed-tools:
  - mcp__linear__list_projects
  - mcp__linear__get_project
  - Read
  - Write
  - Glob
  - AskUserQuestion
argument-hint: "[PROJECT-SLUG]"
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/init/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `issue-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

init スキルを使って、プロジェクトの初期セットアップを行ってください。引数でプロジェクトスラッグが指定されていればそれを使用してください。
