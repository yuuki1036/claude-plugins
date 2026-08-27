# notebooklm-workflow

NotebookLM と Claude Code を連携するワークフロープラグイン。
URL / PDF / YouTube / Google Drive のソース追加と、既存ノートへの Q&A・要約取得を、自然言語またはスラッシュコマンドで実行できる。

MCP server は [jacob-bd/notebooklm-mcp-cli](https://github.com/jacob-bd/notebooklm-mcp-cli) を `.mcp.json` で同梱配布する。

## できること

- 検索や Web 巡回中に見つけた記事 / 動画 / ドキュメントを、対話の流れを止めずに NotebookLM のノートへ放り込む
- 既存ノートに対して Q&A や要約を実行し、Claude Code セッション内で結果を活用する

## 前提条件

- Python 3.11 以降
- `pip` または `pipx`
- Google アカウント（NotebookLM の利用権限）

## セットアップ

### 1. notebooklm-mcp-cli をインストール

```bash
# pipx 推奨（環境分離）
pipx install notebooklm-mcp-cli

# pip でも可
pip install notebooklm-mcp-cli
```

### 2. NotebookLM への認証

```bash
nlm login            # ブラウザが開いて Google ログイン
nlm login --check    # 認証確認
```

cookie は `~/.notebooklm-mcp-cli/` に保存され、約 2〜4 週間有効。期限切れ時は再度 `nlm login`。

### 3. MCP server の登録

このプラグインは `.mcp.json` で `notebooklm-mcp` を同梱しているため、追加設定は不要。
プラグインをインストールすると同梱 `.mcp.json` が有効になり、MCP サーバーが自動的に起動する。

`nlm setup add claude-code` を実行している場合は二重登録になるため、いずれか片方を選ぶこと（推奨: 同梱版を使う＝何もしない）。

## 使い方

### スラッシュコマンド

```
/notebook-add-source https://example.com/article
/notebook-add-source "Research" https://www.youtube.com/watch?v=...

/notebook-query "Layer 7 ロードバランサの仕組みは?"
/notebook-query "Research" "結論はなんですか?"
/notebook-query "Research" --summarize
```

### 自然言語

スキルがトリガーフレーズを検知して自動起動する：

- 「NotebookLM にこの URL を追加して」
- 「Research ノートを要約して」
- 「あのノートに質問したい」

ノート名が省略・曖昧な場合は AskUserQuestion で選択 UI が出る。

## トラブルシューティング

### 依存チェックで [ERROR] が出る

SessionStart 時に以下が表示された場合：

```
- [ERROR] notebooklm-mcp-cli ... がインストールされていません
- [ERROR] NotebookLM MCP サーバー（notebooklm-mcp）が起動できません（nlm バイナリが PATH 上に見つかりません）
```

→ セットアップ手順 1〜3 を再確認。

### tool 呼び出しで認証エラー

cookie 期限切れの可能性：

```bash
nlm login
nlm login --check
```

### 複数の Google アカウントを使い分けたい

```bash
nlm login --profile work
nlm login --profile personal
```

詳しくは jacob-bd/notebooklm-mcp-cli の README を参照。

## スコープ外（v1）

以下は現バージョンに含まれない（将来拡張候補）：

- Audio Overview の生成・ダウンロード
- ノート自体の新規作成
- Claude Code セッション成果物の自動保存

## ライセンス・注意

- jacob-bd/notebooklm-mcp-cli は Google の内部 API（非公開）を利用するため、Google 側の仕様変更で動作しなくなる可能性がある
- 連携利用は NotebookLM の利用規約の範囲内で各自の責任で行う
