# linear-workflow

Linear MCP 連携の Issue・プロジェクト管理プラグイン。Linear 上のステータス同期と Issue ファイルのメンテナンスを自動化する。

## 含まれるスキル

### linear-maintain

Linear MCP と同期してローカルの管理ファイルを最新化するスキル。

- プロジェクト doc（`projects/*.md`）のステータス・Issue テーブル同期
- Issue ファイルの `linear_status` 自動更新
- 新規プロジェクトの検出・doc 作成提案
- 不整合検出（Linear と手動ステータスの乖離）

呼び出し: `/linear-maintain`、「Linear同期」、「ステータス更新」、「プロジェクト整理」

### issue-maintain

Issue ファイルのセッション内容反映・品質整理・knowledge 切り出しを行うスキル。

- セッション作業内容の Issue ファイルへの反映
- 品質整理（完了サブタスクの圧縮、重複除去、テンプレート準拠チェック）
- 汎用知見の `knowledge/` ディレクトリへの切り出し

呼び出し: `/issue-maintain`、「Issue整理」、「Issueファイルのメンテナンス」

## 前提条件

- Linear MCP が設定済みであること（`list_issues`, `list_projects`, `get_issue`, `get_project` などのツールが利用可能）
- `.claude/linear/{slug}/` ディレクトリ構造が存在すること

## Linear MCP の設定

このプラグインを使用するには、Linear MCP サーバーの設定が必要です。

### 1. Linear API キーの取得

[Linear Settings > API](https://linear.app/settings/api) から Personal API Key を発行してください。

### 2. MCP サーバーの追加

以下のコマンドで Linear MCP サーバーを Claude に登録します:

```bash
claude mcp add linear -- npx @anthropic/linear-mcp
```

API キーを環境変数で渡す場合:

```bash
claude mcp add linear -e LINEAR_API_KEY=<your-api-key> -- npx @anthropic/linear-mcp
```

### 3. 動作確認

Claude Code で `list_projects` や `list_issues` などの Linear MCP ツールが利用可能になっていることを確認してください。

## 使い方

1. このプラグインをインストールする
2. 上記の手順で Linear MCP を設定する
3. `.claude/linear/{slug}/` 配下に Issue ファイルやプロジェクト doc を配置する
4. `/linear-maintain` で Linear との同期、`/issue-maintain` で Issue ファイルの整理を実行する
