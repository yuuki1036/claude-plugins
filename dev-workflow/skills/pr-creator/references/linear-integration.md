# Linear Issue連携

## Issue ID抽出

ブランチ名からパターン `[A-Z]+-[0-9]+` でIssue IDを抽出する。

例:
- `feat/CPL-123-add-login` → `CPL-123`
- `fix/CPLFE-456` → `CPLFE-456`

## 情報取得

### Linear MCP
```
mcp__linear__get_issue(issue_id: "CPL-123")
→ タイトル、説明、ステータス等を取得
```

### タスク詳細ファイル
```
.claude/plans/{linearIssueId}.md
```

存在する場合、以下の情報をdescription生成に活用:
- 概要・課題の説明
- 実装計画・調査結果
- 進捗チェックリスト
- 技術的な決定事項

## タイトル生成

Linear Issueが取得できた場合、**Issueのタイトルをそのまま**PRタイトルとして使用する。
