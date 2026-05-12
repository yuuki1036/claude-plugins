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
  - AskUserQuestion
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

#### PR タイプ判定（撮影枚数の調整）

ブランチ名・コミットメッセージ・差分内容から PR タイプを推定し、`ui-verify/SKILL.md` の「PR タイプ別ガイドライン」表に従って撮影枚数を決定する。

| PR タイプ | 判定シグナル | 撮影方針 |
|-----------|------------|---------|
| 検証 PR（probe / spike / stage1 / compat） | ブランチ名に `probe\|spike\|stage1\|compat\|verify\|poc` を含む | **撮影スキップを default**。Screenshots セクション自体を省略 |
| リファクタ（UI 変更なし） | 差分が `.test.` / 設定ファイル / 純粋な型変更のみ | スキップ |
| Theme / Token 変更 | 差分に `tokens` / `theme` / `tailwind.config` 等を含む | light + dark の 2 枚 |
| レイアウト / レスポンシブ変更 | 差分に `@media` / `md:` `lg:` `sm:` 等の breakpoint utility / `grid-template` / `flex-direction` を含む | desktop + mobile（必要なら tablet）の 2–3 枚 |
| UI 新機能 | 上記いずれにも当てはまらず UI ファイル差分が一定以上 | desktop 1 枚を default。1–3 枚 |
| バグ修正（UI レンダリング） | コミット message に `fix` を含み UI ファイル差分あり | 修正対象 viewport 1–2 枚 |

判別不能な場合は **desktop 1 枚** を default とし、`AskUserQuestion` で 「desktop 1 枚 / 複数 viewport / スキップ」を確認する。

#### 撮影フローと PR body 添付

1. `.claude/screenshots/` 内の最新 snap ディレクトリを特定。見つからなければ ui-verify スキルを `snap` モードで起動して新規撮影（PR タイプ判定結果に応じた `--viewports=...` を渡す）

   ```bash
   # ui-verify が作る snap-* / git-commit-helper が作る commit-* の両方を対象
   LATEST=$(ls -1dt .claude/screenshots/{snap,commit}-* 2>/dev/null | head -1)
   ```
2. **撮影内容の機密チェック**（次節「機密 UI チェックリスト」を実施）。問題があれば中止
3. `${CLAUDE_PLUGIN_ROOT}/hooks/scripts/upload-screenshots.sh <dir>` を実行して画像を GitHub Release (`cc-screenshots` タグ) にアップロード
4. 標準出力の `<filename><TAB><url>` を解析
5. PR body に以下を追記（テンプレート既存セクションの末尾 or 新規 `## Screenshots` として）。**1 枚のみの場合は table ではなく単独画像で添付する**:

   ```markdown
   <!-- 1 枚の場合 -->
   ## Screenshot

   ![desktop](<url>)

   <!-- 複数枚の場合 -->
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

#### 機密 UI チェックリスト（撮影前必須）

`cc-screenshots` release は public release のため、アップロードした画像は誰でも閲覧可能。以下のいずれかに該当する撮影は **アップロードしない**:

- ログイン画面・認証画面（OAuth プロバイダ名・社内 SSO ボタン等のメタ情報を含む）
- 顧客データ・実名ユーザー情報・実メールアドレス・実電話番号
- 社内 URL / 社内 API エンドポイント / 社内サービス名
- 機密 UI（権限管理画面、課金画面、管理者ダッシュボード等）
- 環境変数値・API キー・トークン文字列（DevTools 開いた状態等）

判定不能な場合は AskUserQuestion でユーザーに確認:

- question: "撮影内容に機密情報は含まれていない？（public release にアップロード）"
- header: "機密チェック"
- options:
  1. label: "問題なし、アップロード" / description: "撮影内容を確認済み"
  2. label: "アップロードせずローカルパスのみ" / description: "PR body にはローカルパスのみ記載、PR レビュー時に手動添付"
  3. label: "Screenshots を省略" / description: "PR body から Screenshots セクション自体を削除"

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
