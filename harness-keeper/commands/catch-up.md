---
description: Claude Code の最新アップデートをキャッチアップしてプラグインを改善する
allowed-tools:
  - WebSearch
  - WebFetch
  - Read
  - Write
  - Edit
  - Bash
  - AskUserQuestion
  - Agent
argument-hint: "[version-range]"
---

**まず `${CLAUDE_PLUGIN_ROOT}/skills/cc-catch-up/SKILL.md` を Read し、その手順に従う**（command 名と skill 名が違うので、`/catch-up` でも `Skill` tool の `harness-keeper:catch-up` でもこの本文が返り、SKILL.md には到達しない。`${CLAUDE_PLUGIN_ROOT}` が展開されていなければ `~/.claude/plugins/installed_plugins.json` の `harness-keeper@…` の `installPath` を使う — cache を `ls` して選ばない（辞書順で旧版を掴む）。記憶から手順を再現しない / GitHub issue #219）。

Claude Code の最新アップデートからプラグイン開発に関連する新機能を抽出し、開発中の全プラグインへの改善を提案・適用する。

引数でバージョン範囲を渡したら（例: `/catch-up 2.1.80-2.1.86`）、SKILL.md の Phase 0 のモード選択は「特定バージョン範囲」で確定する。省略時は Phase 0 のとおりにモードを選ぶ。
