---
description: "PRのコードレビューを実行する（専門エージェント並列起動）"
allowed-tools: ["Bash", "Read", "Glob", "Grep", "mcp__github__pull_request_read"]
argument-hint: "[PR番号] (省略時は現在のブランチのPRを自動取得)"
---

review スキルを使用して、指定されたPR（または現在のブランチに紐づくPR）のコードレビューを実行してください。

引数が指定されている場合はそれをPR番号として使用してください。
