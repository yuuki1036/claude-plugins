---
description: "全プロジェクトの棚卸し。放置 Issue・frozen Issue・技術的負債の検出とクリーンアップを行う トリガー: 「プロジェクト整理」「棚卸し」「メンテナンス」「/maintain」"
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
argument-hint: "[project-slug]"
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/maintain/SKILL.md` を Read し、その手順に従う**（同名の command と skill は `Skill` tool で呼んでもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `issue-workflow@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

maintain スキルを使ってプロジェクトの棚卸しを実行してください。
