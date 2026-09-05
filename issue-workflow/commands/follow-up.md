---
description: "Follow-up タスクの作成・一覧・Issue昇格 トリガー: 「follow-up」「後でやる」「別タスク」「切り出し」「todo メモ」 「フォローアップ記録」「/follow-up」「/follow-up list」「/follow-up promote」"
allowed-tools:
  - mcp__linear__save_issue
  - mcp__linear__get_issue
  - Read
  - Write
  - Edit
  - Glob
  - Bash
  - Skill
  - AskUserQuestion
argument-hint: "[new|list|promote [FILE]]"
---

follow-up スキルを使って、follow-up タスクの管理を行ってください。引数に応じてサブコマンドを選択します:
- 引数なし または "new": 新規 follow-up を作成
- "list": 未処理の follow-up 一覧を表示
- "promote [ファイル名]": 指定した follow-up を Issue に昇格
