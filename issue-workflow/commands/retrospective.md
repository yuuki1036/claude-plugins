---
description: "個人開発の振り返り・見積もり精度分析 トリガー: 「振り返り」「ふりかえり」「retrospective」「レトロ」「/retrospective」"
allowed-tools:
  - Read
  - Write
  - Glob
  - Bash
  - Skill
  - AskUserQuestion
argument-hint: "[期間: 2w, 1m, etc.]"
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/retrospective/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `issue-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

retrospective スキルを使って、個人開発の振り返りをしてください。引数が指定された場合はその期間で振り返りを行ってください。
