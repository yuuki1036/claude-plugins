---
description: "セッション開始。main ではダッシュボード、feature ブランチでは Issue コンテキスト読み込み トリガー: 「作業開始」「セッション開始」「今日の作業」「/start」"
allowed-tools:
  - Agent
  - Skill
  - mcp__linear__get_issue
  - mcp__linear__list_issues
  - Read
  - Write
  - Glob
  - Grep
  - Bash
argument-hint: ""
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/start/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `issue-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

start スキルを使って、セッション開始時の作業準備をしてください。
