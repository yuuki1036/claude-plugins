---
name: pr-creator
description: |
  PRを作成し、差分とコミット履歴からdescriptionを自動生成する。
  ドラフトPRとして作成し、リポジトリのPRテンプレートがあれば自動準拠する。
  Linear Issue連携: ブランチ名からIssue IDを抽出し、タイトル・説明を取得する。
  トリガー: ユーザーが「PR作って」「/pr-creator」「プルリクエスト作成」と言った時。
effort: medium
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

### 4.5 Screenshots 添付（UI PR のみ）

以下すべてを満たす場合のみ実行する:

- `.claude/.ui-verify-enabled` が存在
- PR 差分（`git diff <base>...HEAD --name-only`）に UI 拡張子ファイル（tsx/jsx/vue/svelte/css/scss/html/astro/mdx）が含まれる
- `gh` が認証済み
- ユーザー引数に `--no-screenshots` が含まれない

手順:

1. `.claude/screenshots/` 内の最新 snap ディレクトリを特定。見つからなければ ui-verify スキルを `snap` モードで起動して新規撮影

   ```bash
   # ui-verify が作る snap-* / git-commit-helper が作る commit-* の両方を対象
   LATEST=$(ls -1dt .claude/screenshots/{snap,commit}-* 2>/dev/null | head -1)
   ```
2. `${CLAUDE_PLUGIN_ROOT}/hooks/scripts/upload-screenshots.sh <dir>` を実行して画像を GitHub Release (`cc-screenshots` タグ) にアップロード
3. 標準出力の `<filename><TAB><url>` を解析
4. PR body に以下を追記（テンプレート既存セクションの末尾 or 新規 `## Screenshots` として）:

   ```markdown
   ## Screenshots

   | viewport | preview |
   |----------|---------|
   | mobile   | ![mobile](<url>) |
   | desktop  | ![desktop](<url>) |
   ```

   viewport 名はファイル名から推定（`mobile.png` / `desktop.png` 等）。不明なものは `<name> | ![<name>](<url>)` 形式。

**アップロード失敗時のフォールバック:**
- `gh` 未認証、ネットワークエラー、権限なし等で失敗したら `## Screenshots` セクションに「ローカルパス: `.claude/screenshots/...`」のみ記載し、ユーザーに手動でドラッグ&ドロップを促す注記を入れる
- PR 作成自体は継続する

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
- Screenshots は `cc-screenshots` release にアップロードする専用運用。他の release と混ぜない
- 機密情報（ログイン画面、社内 URL、実データ等）が写っていないか撮影前に確認する。アップロードは public release なので漏洩リスクあり
