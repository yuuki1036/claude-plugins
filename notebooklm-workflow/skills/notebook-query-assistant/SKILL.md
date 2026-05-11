---
name: notebook-query-assistant
description: |
  NotebookLM の既存ノートに質問したり要約を取得する。
  Claude Code セッション中に「あのノートに何が書いてあったか」を聞きたいときや、ノート全体を要約させたいときに使う。
  トリガー: 「NotebookLM に質問」「NotebookLM のノートに質問」「NotebookLM に聞く」「ノートに質問」「ノートに対して質問」「ノートを要約」「ノートをサマリ」「ノートに対して Q&A」「ノートについて聞いて」「リサーチノートを要約」「notebooklm に問い合わせ」「NotebookLM のノートを要約」「/notebook-query」
  引数: [notebook] <question> [--summarize]
effort: low
allowed-tools:
  - Bash
  - AskUserQuestion
  - mcp__plugin_notebooklm-workflow_notebooklm-mcp__notebook_list
  - mcp__plugin_notebooklm-workflow_notebooklm-mcp__notebook_query
---

# notebook-query-assistant

NotebookLM のノートに対して Q&A や要約を実行するスキル。

## 前提

- `nlm login` で認証済み
- 対象ノートに既にソースが追加されている（無ければ `notebook-source-adder` を先に実行）

## ワークフロー

### Step 1: 質問の整形

ユーザーから受け取った質問文をそのまま使う。

要約モード（コマンド `--summarize` フラグまたは「要約して」「サマリ」等のトリガー）の場合は、質問文を以下のテンプレートに乗せる：

```
このノートの全ソースを要約してください。主要なポイントを 5 つまでに絞り、各ポイントは 2 文以内で簡潔にまとめてください。
```

質問パターンの参考定型は `references/query-patterns.md` を参照。

### Step 2: ノート選択

ノートが指定されていない場合：

1. `mcp__plugin_notebooklm-workflow_notebooklm-mcp__notebook_list` でノート一覧を取得
2. AskUserQuestion で選択 UI を提示（ノート名・最終更新日を併記）
3. 候補が 1 件の場合はそのまま採用
4. 候補が 0 件の場合は「先にノートを作成・ソース追加してください」と案内して終了

### Step 3: クエリ実行

`mcp__plugin_notebooklm-workflow_notebooklm-mcp__notebook_query` を呼ぶ。

### Step 4: 応答提示とフォローアップ

応答をユーザーに提示する。応答が長い場合（概ね 1500 字超）は要点のみ抽出して提示し、「全文表示しますか？」と確認する。

応答後、ユーザーが追加で深堀りしたい場合に備え、応答中の「未確定」「不明」「言及されていない」といった語をフックに次の質問候補を 1〜3 個提示する（任意、必須ではない）。

## エラー対処

### 認証エラー（cookie expired）

```
NotebookLM への認証が失敗しました。以下を実行して再ログインしてください:
  nlm login
  nlm login --check
```

ユーザーから許可があれば `nlm login --check` を Bash で代行実行して状況を確認してよい。それ以外の Bash 実行（`nlm login` 本体等）は副作用が大きいためユーザー側で実行してもらう。

### ソース未追加のノート

`notebook_query` が「ソースがない」エラーを返したら `notebook-source-adder` の利用を案内する。

### MCP 未起動

`mcp__plugin_notebooklm-workflow_notebooklm-mcp__*` tool が見つからない場合は SessionStart の依存チェック（[ERROR]）を確認するよう案内する。

## 絶対厳守ルール

- ユーザーが指定していないノートに勝手にクエリしない（候補が複数なら必ず AskUserQuestion）
- 応答内容を要約・改変する場合は、その旨を明示する（NotebookLM の出力をそのまま提示しているのか、加工しているのかを区別）
- NotebookLM の応答に含まれる引用元情報（ソース番号・章名等）は省略せず保持する

## Additional Resources

- **`references/query-patterns.md`** — 要約・Q&A の定型クエリパターン
