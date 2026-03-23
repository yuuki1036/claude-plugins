---
description: "コミット前のセルフレビューを実行する（PR不要・ローカル完結）"
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
  - AskUserQuestion
argument-hint: "[--staged | base branch] (省略時はデフォルトブランチとの差分)"
---

self-review スキルを使用して、現在の変更のセルフレビューを実行してください。

引数に `--staged` が指定されている場合は、ステージ済みの変更のみを対象にしてください。
引数にブランチ名が指定されている場合は、それをbase branchとして使用してください。
