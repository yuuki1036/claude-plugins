---
description: Claude Code の最新アップデートをキャッチアップしてプラグインを改善する
allowed-tools:
  - WebSearch
  - WebFetch
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
  - Agent
argument-hint: "[version-range]"
---

Claude Code の最新アップデートからプラグイン開発に関連する新機能を抽出し、開発中の全プラグインへの改善を提案・適用する。

引数でバージョン範囲を指定可能（例: `/catch-up 2.1.80-2.1.86`）。省略時は前回キャッチアップ以降の差分を対象とする。

`cc-catch-up` スキルのワークフローに従って実行すること。
