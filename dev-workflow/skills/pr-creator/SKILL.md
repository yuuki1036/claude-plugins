---
name: pr-creator
description: |
  PRを作成し、差分とコミット履歴からdescriptionを自動生成する。
  ドラフトPRとして作成し、リポジトリのPRテンプレートがあれば自動準拠する。
  Linear Issue連携: ブランチ名からIssue IDを抽出し、タイトル・説明を取得する。
  使用タイミング: ユーザーが「PR作って」「/pr-creator」「プルリクエスト作成」と言った時。
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
  - mcp__linear__get_issue
---

# PR Creator

## 実行手順

### 1. PRテンプレートを確認

以下の場所を順にチェックし、見つかればそのフォーマットに従う：
`.github/PULL_REQUEST_TEMPLATE.md`, `.github/pull_request_template.md`, `PULL_REQUEST_TEMPLATE.md`

### 2. 状態確認

```bash
git status
git branch -vv
git remote show origin | grep "HEAD branch"
git log <base-branch>..HEAD --oneline
git diff <base-branch>...HEAD
```

### 3. Linear Issue連携（該当する場合）

ブランチ名からIssue ID（`[A-Z]+-[0-9]+`パターン）を抽出し：
- `mcp__linear__get_issue` でタイトル・説明を取得
- `.claude/plans/{issueId}.md` があれば参照

**Linear MCP が利用できない場合のフォールバック:**
Linear MCP が未設定または接続エラーの場合は、以下の情報のみからPR情報を生成する：
- ブランチ名（Issue IDやタスク名を抽出）
- `git log <base-branch>..HEAD` のコミット履歴
- `git diff <base-branch>...HEAD` の差分内容

Linear連携なしでも基本的なPR作成は問題なく動作する。

詳細は [references/linear-integration.md](references/linear-integration.md) を参照。

### 4. PR情報を生成

- **タイトル**: Linear Issueがあればそのタイトルを使用。なければ変更の要約（50文字以内）
- **Description**: テンプレートまたはデフォルトフォーマットに従う

Description生成の詳細は [references/description-guide.md](references/description-guide.md) を参照。

### 5. PRを作成

```bash
git push -u origin <current-branch>
gh pr create --draft --title "<title>" --body "<description>"
```

作成後はURLを表示する。

## 厳守ルール

- 常にドラフトPRとして作成
- テンプレートのセクションは空欄にせず必ず内容を埋める
- AI署名（Generated with等）は付けない
