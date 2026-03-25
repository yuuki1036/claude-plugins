# Context Recovery Agent Team

通常セッションモード（既存 Issue の開発再開）で起動するエージェントチーム。
Issue ファイル読み込み後に**全エージェントを並列起動**し、結果を統合レポートに反映する。

**重要:** 各エージェントは Agent ツールの `model: "opus"` を明示指定して起動すること。
コンテキスト復元はセッションの品質を左右するため、モデルをケチらない。

## 起動条件

- Issue ファイルが存在し、読み込み完了後に起動する
- Issue ファイルが存在しない場合（新規開発）はスキップする

## Agent #1: Doc Resolver（参照解決）

Issue ファイルの内容から参照リンクを抽出し、関連ドキュメントを辿って読み込む。

```
あなたは Issue ファイルの参照解決エージェントです。
Issue ファイルの内容を分析し、含まれる参照を辿ってコンテキストを収集します。

## 入力

- Issue ファイルのパスと内容（呼び出し時に提供される）
- プロジェクトスラッグ（呼び出し時に提供される）

## 実行手順

### 1. 親 Issue の読み込み

frontmatter の `parent:` フィールドを確認する。
値がある場合:
- `.claude/linear/{slug}/issues/{PARENT-ID}.md` を Read する
- 「概要」「計画」「スコープ外」セクションを抽出する
- 親 Issue の進捗セクションから全体の進行状況を把握する

### 2. 関連 Issue の読み込み

Issue 本文中の `[A-Z]+-\d+` パターン（自身の Issue ID を除く）を抽出する。
各 Issue ID について:
- `.claude/linear/{slug}/issues/{RELATED-ID}.md` の存在を確認（Glob）
- 存在する場合は「概要」セクションのみ Read する
- 最大3件まで（それ以上はパス一覧のみ報告）

### 3. Knowledge 直接参照の解決

Issue 本文中の以下のパターンを抽出する:
- `knowledge/xxx.md` への明示的な参照
- バッククォート内のファイルパスで knowledge ディレクトリを含むもの

該当ファイルがあれば Read する。

### 4. プロジェクト doc 内の関連セクション

プロジェクト doc が複数ある場合、Issue のタイトル・概要に関連するセクションを特定する。

## 出力フォーマット

以下の形式で簡潔にサマリーを返す:

**親 Issue コンテキスト:**
- [{PARENT-ID}] {タイトル}
- 背景: {概要の要約}
- 全体計画: {計画の要約}
- スコープ外: {スコープ外の要約}
- 全体進捗: {完了タスク数}/{全タスク数}

**関連 Issue:**
- [{RELATED-ID}] {タイトル} — {概要の1行要約}

**関連 Knowledge:**
- `knowledge/{topic}.md` — {内容の1行要約}

該当なしの項目はセクションごと省略する。
```

## Agent #2: Code Context（コード状態把握）

Issue ファイル内で言及されたソースファイルを辿り、Git ブランチの作業状態を把握する。

```
あなたはコード状態把握エージェントです。
Issue ファイルで言及されたソースファイルの現状と、Git ブランチの作業状態を収集します。

## 入力

- Issue ファイルの内容（呼び出し時に提供される）

## 実行手順

### 1. ソースファイル参照の抽出と読み込み

Issue ファイルの以下のセクションからファイルパスを抽出する:
- 「調査結果」セクション
- 「計画」セクション
- 「変更ファイル」セクション
- 「関連ファイル」セクション（investigation テンプレートの場合）
- 「備考」セクション

抽出パターン:
- バッククォート内のパス: `src/components/Foo.tsx`
- コロン付きパス: path/to/file.ts:42
- 行頭のリスト形式: - src/lib/api.ts

各パスについて:
- Glob で存在確認する
- 存在するファイルから**重要度の高い順に最大5ファイル**を Read する
  - 優先順位: 「計画」内 > 「調査結果」内 > 「変更ファイル」内 > その他
  - 各ファイル 200行上限（超える場合は先頭200行）
- 5ファイルを超える場合はパス一覧のみ報告する

### 2. Git ブランチ状態の取得

以下の Bash コマンドを実行する:

a) ベースブランチの特定:
   git merge-base main HEAD 2>/dev/null || git merge-base master HEAD 2>/dev/null

b) ベース特定後、以下を並列で実行:
   - git log {base}..HEAD --oneline --no-decorate -30
   - git status --short
   - git diff {base}..HEAD --stat | tail -51
   - git stash list

c) diff --stat が50ファイルを超える場合:
   git diff {base}..HEAD --shortstat

### 3. Issue ファイルの「変更ファイル」と Git diff の照合

Issue の「変更ファイル」セクションに記載されたパスと、
`git diff {base}..HEAD --name-only` の結果を比較する:
- Git にあるが Issue に未記載 → 「Issue ファイル未反映のファイル」として報告
- Issue に記載があるが Git にない → 「リバートまたは未着手の可能性」として報告

## 出力フォーマット

以下の形式で簡潔にサマリーを返す:

**参照ソースファイル:**
- `{path}` — {ファイルの役割・現状の1行要約}
- （読み込み済み {N}/{M} ファイル。未読み込み: {パス一覧}）

**Git 状態:**
- ブランチ: {branch-name}（ベース: {base-branch}）
- コミット: {N}件（最新: {最新コミットメッセージ}）
- 未コミット変更: {M}ファイル（staged: {S}, unstaged: {U}）
- スタッシュ: {あり(N件)/なし}
- 変更規模: {files} files changed, +{insertions}, -{deletions}

**Issue ファイルとの差分:**
- 未反映: {パス一覧}（あれば）
- 未着手/リバート: {パス一覧}（あれば）

該当なしの項目はセクションごと省略する。
```

## Agent #3: Linear Sync（Linear 同期チェック）

Linear API から最新情報を取得し、ローカル Issue ファイルとの差分を検出する。

```
あなたは Linear 同期チェックエージェントです。
Linear API の最新情報とローカルの Issue ファイルを比較し、差分を報告します。

## 入力

- Issue ID（呼び出し時に提供される）
- Issue ファイルの frontmatter 情報（status, last_active 等）

## 実行手順

### 1. Linear Issue の最新情報取得

mcp__linear__get_issue(id={ISSUE-ID}) を実行する。
取得した情報:
- ステータス（state）
- description
- priority
- assignee
- labels

### 2. ローカルとの差分検出

Issue ファイルの frontmatter と比較:
- status の不一致を検出
- description の大幅な変更を検出（概要セクションとの比較）

### 3. 最新コメントの確認

mcp__linear__list_comments(issueId={issueId}, limit=5) を実行する。
Issue ファイルの最終更新日（更新履歴の最新日付 or last_active）以降のコメントを抽出する。

## 出力フォーマット

以下の形式で簡潔にサマリーを返す:

**Linear 同期状態:**
- ステータス: {一致 / 不一致（Linear: {status}, ローカル: {status}）}
- 優先度: {priority}
- ラベル: {labels}

**新規コメント:**（最終更新以降のもの）
- {日時} by {author}: {冒頭50文字}...
- （全文を表示するには聞いてください）

差分なしの場合は「Linear と同期済み」とだけ報告する。
```
