# linear-workflow

Linear MCP 連携のプロジェクト・Issue 管理ワークフロープラグイン。

## スキル一覧

### session-start

セッション開始時の作業準備。ブランチ名から Linear Issue を特定し、関連ファイルを読み込む。

- トリガー: 「作業開始」「セッション開始」「/session-start」

### issue-create

Issue ファイルの新規作成。bugfix / feature / investigation テンプレートから選択。

- トリガー: 「Issue作成」「/issue-create」
- 引数: `[ISSUE-ID]`

### linear-maintain

Linear MCP と同期してプロジェクト doc・Issue ステータスを最新化。completed Issue の自動メンテナンスも実行。

- トリガー: 「Linear同期」「/linear-maintain」
- 引数: `[プロジェクトスラッグ]`（省略時は全スラッグ）

### issue-maintain

Issue ファイルの品質整理・knowledge 切り出し・completed 管理。

- トリガー: 「Issue整理」「/issue-maintain」
- 引数: `[Issue ID]`（省略時は現在のブランチから抽出）

## 前提条件

- Linear MCP が設定済みであること
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
4. `/session-start` でセッション開始時に作業コンテキストを自動読み込み
5. `/issue-create [ISSUE-ID]` で新規 Issue ファイルをテンプレートから作成
6. `/linear-maintain` で Linear との同期を実行
7. `/issue-maintain` で Issue ファイルの整理・knowledge 切り出しを実行

## SessionStart hook

`.claude/linear/` ディレクトリが存在するプロジェクトでは、セッション開始時にプロジェクト管理ルールが自動注入されます。
これにより CLAUDE.md に管理ルールを手書きする必要がなくなります。

- ルール内容: `rules/project-rules.md`
- 条件: `.claude/linear/` ディレクトリの存在
