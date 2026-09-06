---
description: "プロジェクトの knowledge の健全性をチェックする（broken link / 孤立知見 / index 不整合 / tags 表記ゆれ / 重複概念） トリガー: 「knowledge lint」「ナレッジ点検」「リンク切れチェック」「リンク切れ」「孤立した知見」「knowledge の健全性」「knowledge を整理」「knowledge の鮮度」「stale な知見」「/knowledge-lint」"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Edit
  - AskUserQuestion
argument-hint: "[slug]"
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/knowledge-lint/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `issue-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

knowledge-lint スキルを使って、プロジェクトの knowledge グラフの健全性をチェックしてください。
broken wikilink・孤立知見・index 不整合・tags 表記ゆれ・重複概念を検出し、機械的に直せるものは承認制で修正してください。
引数でスラッグが指定されていればそのプロジェクトを対象にしてください。
