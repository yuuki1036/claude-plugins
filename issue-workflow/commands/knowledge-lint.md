---
description: "プロジェクトの knowledge の健全性をチェックする（broken link / 孤立知見 / index 不整合 / tags 表記ゆれ / 重複概念）"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Edit
  - AskUserQuestion
argument-hint: "[slug]"
---

knowledge-lint スキルを使って、プロジェクトの knowledge グラフの健全性をチェックしてください。
broken wikilink・孤立知見・index 不整合・tags 表記ゆれ・重複概念を検出し、機械的に直せるものは承認制で修正してください。
引数でスラッグが指定されていればそのプロジェクトを対象にしてください。
