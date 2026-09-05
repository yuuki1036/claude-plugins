---
description: "Linear MCP と全件同期して、ローカルに既にある Issue/プロジェクト管理ファイルを最新化する（更新のみ。新規 1 件の作成は issue-create） トリガー: 「/linear-maintain」「Linear同期」「Linearステータス同期」「プロジェクトdoc最新化」「プロジェクト整理」 引数: [プロジェクトスラッグ（省略時は .claude/linear/ 配下の全スラッグ対象）]"
allowed-tools:
  - mcp__linear__list_issues
  - mcp__linear__list_projects
  - mcp__linear__get_issue
  - mcp__linear__get_project
  - mcp__linear__list_issue_statuses
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
---

linear-maintain スキルを使って Linear 同期を実行してください。
