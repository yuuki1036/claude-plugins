---
description: "プロジェクトの蓄積された知見を検索・参照する（引数なし: 一覧、search kw: 検索、related: 関連表示） トリガー: 「知見」「過去に似た」「前にもやった」「ナレッジを検索」「/knowledge」"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
argument-hint: "[search KEYWORD | related]"
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/knowledge/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `issue-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

knowledge スキルを使って、プロジェクトの知見を検索・参照してください。
引数に応じてモードを切り替えてください。
