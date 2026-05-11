---
name: notebook-source-adder
description: |
  NotebookLM のノートに URL / PDF / YouTube / Google Drive のソースを追加する。
  Claude Code セッション中に見つけた記事や参考資料を、後で読み返したり Q&A の材料にしたいときに使う。
  トリガー: 「NotebookLM にソース追加」「NotebookLM に URL 追加」「ノートに URL 追加」「ノートに資料を追加」「ノートに資料を投入」「リサーチノートに追加」「PDF/YouTube/Drive を NotebookLM へ」「notebooklm に追加」「NotebookLM にこの URL」「NotebookLM にこの記事」「/notebook-add-source」
  引数: [notebook] <source-url-or-path>
effort: low
allowed-tools:
  - Bash
  - AskUserQuestion
  - mcp__plugin_notebooklm-workflow_notebooklm-mcp__notebook_list
  - mcp__plugin_notebooklm-workflow_notebooklm-mcp__source_add
---

# notebook-source-adder

NotebookLM のノートにソース（URL / YouTube / Google Drive / PDF）を追加するスキル。

## 前提

- `notebooklm-mcp-cli` が PATH に存在し、`nlm login` で認証済み
- `.mcp.json` で `notebooklm-mcp` が登録されている（このプラグイン同梱）
- 追加先のノートが NotebookLM 上に既に存在する

## ワークフロー

### Step 1: 入力の確認

ユーザーから以下を取得する。引数で渡されていない場合は AskUserQuestion で補完する。

- ソース URL またはファイルパス（必須）
- 対象ノート名 or ノート ID（任意）

### Step 2: ノート選択

ノートが指定されていない場合：

1. `mcp__plugin_notebooklm-workflow_notebooklm-mcp__notebook_list` でノート一覧を取得
2. 候補が複数ある場合は AskUserQuestion で選択 UI を提示（ノート名・最終更新日を表示）
3. 候補が 1 件の場合はそのまま採用
4. 候補が 0 件の場合は「先に NotebookLM でノートを作成してください」と案内して終了

ノート名で曖昧マッチした場合（部分一致が複数）も AskUserQuestion で確認する。

### Step 3: ソース追加

`mcp__plugin_notebooklm-workflow_notebooklm-mcp__source_add` を呼ぶ。

ソースタイプ別の挙動・入力形式の差は `references/source-types.md` を参照。

### Step 4: 結果報告

追加されたソース名と対象ノート名をユーザーに報告する。NotebookLM の web UI URL は MCP の応答に含まれていれば併せて提示する。

## エラー対処

### 認証エラー（cookie expired）

tool 呼び出しが認証関連エラー（401 / unauthorized / cookie expired 等）を返した場合は以下を提示する：

```
NotebookLM への認証が失敗しました。以下を実行して再ログインしてください:
  nlm login
  nlm login --check
```

ユーザーから許可があれば `nlm login --check` を Bash で代行実行して状況を確認してよい。それ以外の Bash 実行（`nlm login` 本体や `pip install` 等）は副作用が大きいためユーザー側で実行してもらう。

### MCP 未起動

`mcp__plugin_notebooklm-workflow_notebooklm-mcp__*` tool が見つからない場合は SessionStart 時の依存チェック（[ERROR] メッセージ）を再確認するよう案内する。`pip install notebooklm-mcp-cli` 未実行の可能性が高い。

## 絶対厳守ルール

- ユーザーが指定していないノートに勝手に追加しない（複数候補時は必ず AskUserQuestion）
- ローカルファイルを読み取る場合、機密情報（鍵、パスワード等）が含まれていないかパスから推察し、疑わしければユーザーに確認する

## Additional Resources

- **`references/source-types.md`** — URL / YouTube / Drive / PDF それぞれの入力形式と注意点
