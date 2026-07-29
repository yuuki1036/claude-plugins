---
description: "コミット前のセルフレビューを実行する（2フェーズ構成・PR不要・ローカル完結）"
allowed-tools:
  - Bash
  - Read
  - Agent
  - AskUserQuestion
  - Skill
argument-hint: "[--staged | base branch] [--focus <観点>] [--exclude <観点1,観点2>] [--embed] (省略時はデフォルトブランチとの差分)"
---

self-review スキルを使用して、現在の変更のセルフレビューを実行してください。

引数に `--staged` が指定されている場合は、ステージ済みの変更のみを対象にしてください。
引数にブランチ名が指定されている場合は、それをbase branchとして使用してください。
引数に `--focus <観点>` / `--exclude <観点1,観点2>` が指定されている場合は、レビュー対象観点を絞り込み・除外してください（同一セッションで既検証の観点を再報告しないため）。
引数に `--embed` が指定されている場合は、他 plugin からの呼び出しと判断し、終端の修正方針確認 AskUserQuestion を skip してください（呼び出し元側で findings を集約する想定）。
