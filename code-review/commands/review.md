---
description: "PRのコードレビューを実行する（2フェーズ構成・専門エージェント動的起動）"
allowed-tools:
  - Bash
  - Read
  - Write
  - Agent
  - EnterWorktree
  - ExitWorktree
  - AskUserQuestion
  - Skill
argument-hint: "[PR番号] [--emergency] (省略時は現在のブランチのPRを自動取得。--emergency は本番ホットフィックス向けの最小構成レビュー)"
---

review スキルを使用して、指定されたPR（または現在のブランチに紐づくPR）のコードレビューを実行してください。

引数が指定されている場合はそれをPR番号として使用してください。
