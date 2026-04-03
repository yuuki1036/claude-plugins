---
description: Follow-up タスクの作成・一覧・Issue昇格
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Bash
  - AskUserQuestion
argument-hint: "[new|list|promote [FILE]]"
---

indie-follow-up スキルを使って、follow-up タスクの管理を行ってください。引数に応じてサブコマンドを選択します:
- 引数なし または "new": 新規 follow-up を作成
- "list": 未処理の follow-up 一覧を表示
- "promote [ファイル名]": 指定した follow-up を Issue に昇格
