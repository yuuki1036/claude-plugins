---
name: session-start
description: >
  セッション開始時の作業準備。ブランチ名から Linear Issue を特定し、
  関連プロジェクト doc と Issue ファイルを読み込む。
  トリガー: 「作業開始」「セッション開始」「タスク開始」「今日の作業を始める」「コンテキスト読み込み」「/session-start」
allowed-tools:
  - mcp__linear__get_issue
  - Read
  - Write
  - Glob
  - Grep
  - Bash
---

# Session Start

セッション開始時にブランチ名から Linear Issue を特定し、関連ファイルを読み込んで作業準備を行う。

## ワークフロー

### Phase 1: ブランチ名から Issue ID 抽出

1. `git branch --show-current` でカレントブランチ名を取得する（Bash）
2. ブランチ名から Linear Issue ID を抽出する
   - パターン例: `feat/TEAM-12` → `TEAM-12`、`build/PROJ-345-update-node` → `PROJ-345`
   - 正規表現: `[A-Z]+-\d+` にマッチする部分を抽出
3. Issue ID が抽出できない場合:
   - 「Issue なしの通常作業」としてユーザーに通知する
   - 「ブランチ名に Issue ID が見つかりませんでした。通常の作業として開始します。」と報告して終了

### Phase 2: プロジェクトスラッグ特定

1. Issue ID のプレフィックスを小文字化してスラッグとする
   - 例: `TEAM-12` → `team`、`PROJ-345` → `proj`

### Phase 3: 関連ファイル読み込み

1. **プロジェクト doc の読み込み**
   - Glob で `.claude/linear/{slug}/projects/*.md` を検索
   - 存在するファイルがあれば Read で全て読み込む

2. **Issue ファイルの確認**
   - `.claude/linear/{slug}/issues/{ISSUE-ID}.md` の存在を確認（Read）
   - 存在する場合:
     - 内容を読み込む
     - 「前回の作業状態」としてユーザーにサマリーを報告する（Phase 5 へ）
   - 存在しない場合:
     - Phase 4 へ進む

### Phase 3.5: 関連 Knowledge の検索

Issue ファイルが存在し、内容を読み込めた場合に実行する。

1. `.claude/linear/{slug}/knowledge/index.md` の存在を確認（Read）
2. **index.md が存在する場合:**
   - index.md を Read で読み込む
   - Issue のタイトル・概要・タスク内容からキーワードを抽出する
   - index.md の tags 列とキーワードを照合し、関連する knowledge を特定する
   - 関連する knowledge ファイルがあれば Read で内容を読み込む
3. **index.md が存在しない場合:**
   - `.claude/linear/{slug}/knowledge/*.md` を Glob で列挙する
   - knowledge ファイルが存在すれば、各ファイルのフロントマター（tags）と Issue のキーワードを照合する
4. **報告:**
   - 関連する knowledge が見つかった場合、Phase 5 の報告に含める:
     ```
     **関連 Knowledge:**
     - `knowledge/{topic}.md` — {概要}（tags: {tags}）
     ```
   - knowledge が0件の場合は何も表示しない

### Phase 4: Issue ファイル新規作成

Issue ファイルが存在しない場合:

1. `issue-create` スキルを使った新規作成をユーザーに提案する
   - 「Issue ファイルが見つかりません。`issue-create` スキルで新規作成しますか？」と確認
2. ユーザーの承認を得てから `issue-create` スキルを実行する
3. ユーザーが不要と判断した場合はスキップして Phase 5 へ

### Phase 5: 作業準備完了報告

読み込んだ情報のサマリーをユーザーに報告する:

- **Issue 情報**: タイトル・ステータス
- **未完了タスク一覧**: Issue ファイルのチェックリストから未完了項目を抽出（あれば）
- **前回セッションからの継続ポイント**: 更新履歴の最新エントリや進行中の作業内容
- **関連 Knowledge**: Phase 3.5 で見つかった関連 knowledge の一覧（あれば）
- **読み込んだプロジェクト doc**: 読み込んだファイル名の一覧

### Phase 6: feature-dev 連携案内

Issue ファイルの「進捗」セクションがプレースホルダのまま（`- [ ] タスク` / `- [ ] 調査項目` など、具体的なタスクが定義されていない）の場合、feature-dev による実装計画の策定を案内する:

```
> `feature-dev` で実装計画を立てますか？
```

ユーザーが承諾したら、feature-dev スキルの実行を提案する（直接実行はしない。案内のみ）。
既に具体的なタスクが定義されている場合はこの案内をスキップする。
