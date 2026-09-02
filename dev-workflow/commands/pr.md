---
description: "差分とコミット履歴からPRを自動作成する"
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
  - Skill
  - mcp__linear__get_issue
  - mcp__linear__list_comments
  - mcp__github__create_pull_request
  - mcp__github__update_pull_request
---

pr-creator スキルを使用して、現在のブランチの差分とコミット履歴から PR を作成してください（既定はドラフト。リポジトリ規約が draft 以外を指定する場合はそちらに従う）。PR 本文はユーザーの承認を得てから作成してください。

Linear Issue連携が可能であればIssue情報も活用してください。
