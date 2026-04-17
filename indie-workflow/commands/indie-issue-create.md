---
description: Issue 作成 + ブランチ自動作成
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
  - Bash
  - Agent
  - AskUserQuestion
argument-hint: "[PROJECT-SLUG]"
---

indie-issue-create スキルを使って、Issue ファイルを新規作成してください。引数でプロジェクトスラッグが指定されていればそれを使用し、未指定ならブランチ名から推定するかユーザーに確認してください。
