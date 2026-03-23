---
name: session-start
description: >
  セッション開始時の作業準備。ブランチ名から Linear Issue を特定し、
  関連プロジェクト doc と Issue ファイルを読み込む。
  main ブランチではフルダッシュボード、親 Issue ブランチではスコープドダッシュボードを表示する。
  トリガー: 「作業開始」「セッション開始」「タスク開始」「今日の作業を始める」
  「コンテキスト読み込み」「Linear ダッシュボード」「プロジェクト状況確認」
  「子 Issue の進捗」「/session-start」
allowed-tools:
  - mcp__linear__get_issue
  - mcp__linear__list_issues
  - Read
  - Write
  - Glob
  - Grep
  - Bash
---

# Session Start

セッション開始時にブランチ名に応じて作業準備を行う。
ブランチの状態に応じて3つのモードに分岐する:

- **フルダッシュボード**: Issue ID のないブランチ（main 等）→ 全プロジェクト俯瞰
- **スコープドダッシュボード**: Issue ID ありで子 Issue を持つ → 親 Issue の進捗表示
- **通常セッション**: Issue ID ありで子 Issue なし → 既存の作業コンテキスト読み込み

## ワークフロー

### Phase 1: ブランチ名から Issue ID 抽出 & モード判定

1. `git branch --show-current` でカレントブランチ名を取得する（Bash）
2. ブランチ名から Linear Issue ID を抽出する
   - パターン例: `feat/TEAM-12` → `TEAM-12`、`build/PROJ-345-update-node` → `PROJ-345`
   - 正規表現: `[A-Z]+-\d+` にマッチする部分を抽出
3. Issue ID が抽出できない場合（main, develop, Issue ID を含まない feature ブランチ等）:
   - **フルダッシュボードモード**（Phase D1〜D4）へ進む
4. Issue ID が抽出できた場合:
   - Phase 1.5 へ進む

### Phase 1.5: 子 Issue 有無チェック

1. `mcp__linear__list_issues(parentId={issueId}, limit=1)` を呼び出す
   - `limit: 1` で1件だけ取得（存在チェックのみ）
2. 結果が1件以上:
   - **スコープドダッシュボードモード**（Phase S1〜S4）へ進む
3. 結果が0件:
   - **通常セッションモード**（Phase N2〜N6）へ進む

---

## フルダッシュボードモード

Issue ID のないブランチ（main/master、develop、その他）でのセッション開始時に実行する。
全チームの状況を俯瞰し、次に着手すべき Issue を提案する。

出力フォーマットは `${CLAUDE_PLUGIN_ROOT}/skills/session-start/references/dashboard-full.md` を参照すること。

### Phase D1: 全プロジェクトスキャン

1. `.claude/linear/` 配下のディレクトリ一覧を Glob で取得する
   - `.claude/linear/*/projects/*.md` を Glob で列挙
2. 各プロジェクト doc を Read で読み込む
3. プロジェクト一覧をサマリー表示する

### Phase D2: アクティブ Issue サマリー

1. `.claude/linear/*/issues/*.md` を Glob でスキャンする
2. 各 Issue ファイルを Read し、`status: in-progress` の Issue をプロジェクト別にリスト表示する
3. `last_active` フィールドが7日以上前の Issue を警告付きで表示する

### Phase D2.5: Knowledge サマリー

1. `.claude/linear/*/knowledge/index.md` を Glob で列挙する
2. 各 index.md を Read で読み込み、プロジェクト別の knowledge 件数を表示する
3. index.md が存在しないプロジェクトは `.claude/linear/*/knowledge/*.md` を Glob でカウントする
4. 表示形式:
   ```
   **Knowledge:**
   - {slug}: {件数}件（最新: {直近の knowledge ファイル名}）
   ```
5. knowledge が全プロジェクトで0件の場合はこのセクションをスキップする

### Phase D3: Next Issue ピック

1. `mcp__linear__list_issues(assignee="me", state="unstarted", limit=10)` を呼び出す
   - 自分にアサインされた未着手 Issue を取得
2. 取得結果を priority フィールドで並べ替える（1=Urgent → 4=Low の順）
3. 上位5件を優先度順に提示する:
   ```
   **次に着手できる Issue（優先度順）:**
   1. [{ISSUE-ID}] [{priority}] {title}
   2. ...
   ```
4. ユーザーが選択した場合:
   - ブランチ作成コマンドを提案: `git checkout -b feat/{ISSUE-ID}-{desc}`
   - `issue-create` スキルの実行を提案する

### Phase D4: 次のアクション提案

状況に応じて以下を提案する:
- 放置 Issue がある場合: 「`{ISSUE-ID}` の作業を再開しますか？」
- Next Issue を選択した場合: 「ブランチを作成して `/issue-create` を実行しますか？」
- プロジェクト doc が古い場合: 「`/linear-maintain` で同期しますか？」

---

## スコープドダッシュボードモード

Issue ID がブランチに含まれ、かつその Issue が子 Issue を持つ場合（エピック / 親 Issue）に実行する。
親 Issue の進捗と子 Issue の状況を表示する。

出力フォーマットは `${CLAUDE_PLUGIN_ROOT}/skills/session-start/references/dashboard-scoped.md` を参照すること。

### Phase S1: 親 Issue 情報取得

1. `mcp__linear__get_issue(id={issueId})` で親 Issue の詳細を取得する
2. Issue ID のプレフィックスを小文字化してスラッグとする
3. `.claude/linear/{slug}/projects/*.md` を Glob で検索し、存在すれば Read で読み込む

### Phase S2: 子 Issue 一覧取得

1. `mcp__linear__list_issues(parentId={issueId}, limit=50)` で子 Issue 一覧を取得する
2. 子 Issue をステータス別に分類して表示する:
   - In Progress / Todo / Done / Canceled
3. 進捗サマリーを表示する（完了率: N/M 件）

### Phase S3: Next Issue ピック（子 Issue 内）

1. Phase S2 で取得した子 Issue のうちステータスが未着手のものを priority フィールドで並べ替える（1=Urgent → 4=Low の順）
2. すでにローカルの `.claude/linear/{slug}/issues/` にファイルがある子 Issue には `[ファイルあり]` のマークを付ける
3. 候補を提示する:
   ```
   **未着手の子 Issue（優先度順）:**
   1. [{CHILD-ID}] [{priority}] {title}
   ```
4. ユーザーが選択した場合:
   - ブランチ作成コマンドを提案: `git checkout -b feat/{CHILD-ID}-{desc}`
   - `issue-create` スキルの実行を提案する

### Phase S4: 次のアクション提案

- In Progress の子 Issue がある場合: 「{CHILD-ID} の作業を継続しますか？」
- Todo の子 Issue がある場合: Phase S3 の提案を再掲する
- 全子 Issue が Done の場合: 「全子 Issue 完了。親 Issue のクローズを検討してください。」

---

## 通常セッションモード

Issue に子 Issue がない場合の通常作業フロー。

### Phase N2: プロジェクトスラッグ特定

1. Issue ID のプレフィックスを小文字化してスラッグとする
   - 例: `TEAM-12` → `team`、`PROJ-345` → `proj`

### Phase N3: 関連ファイル読み込み

1. **プロジェクト doc の読み込み**
   - Glob で `.claude/linear/{slug}/projects/*.md` を検索
   - 存在するファイルがあれば Read で全て読み込む

2. **Issue ファイルの確認**
   - `.claude/linear/{slug}/issues/{ISSUE-ID}.md` の存在を確認（Read）
   - 存在する場合:
     - 内容を読み込む
     - 「前回の作業状態」としてユーザーにサマリーを報告する（Phase N5 へ）
   - 存在しない場合:
     - Phase N4 へ進む

### Phase N3.5: 関連 Knowledge の検索

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
   - 関連する knowledge が見つかった場合、Phase N5 の報告に含める:
     ```
     **関連 Knowledge:**
     - `knowledge/{topic}.md` — {概要}（tags: {tags}）
     ```
   - knowledge が0件の場合は何も表示しない

### Phase N4: Issue ファイル新規作成

Issue ファイルが存在しない場合:

1. `issue-create` スキルを使った新規作成をユーザーに提案する
   - 「Issue ファイルが見つかりません。`issue-create` スキルで新規作成しますか？」と確認
2. ユーザーの承認を得てから `issue-create` スキルを実行する
3. ユーザーが不要と判断した場合はスキップして Phase N5 へ

### Phase N5: 作業準備完了報告

読み込んだ情報のサマリーをユーザーに報告する:

- **Issue 情報**: タイトル・ステータス
- **未完了タスク一覧**: Issue ファイルのチェックリストから未完了項目を抽出（あれば）
- **前回セッションからの継続ポイント**: 更新履歴の最新エントリや進行中の作業内容
- **関連 Knowledge**: Phase N3.5 で見つかった関連 knowledge の一覧（あれば）
- **読み込んだプロジェクト doc**: 読み込んだファイル名の一覧

### Phase N6: feature-dev 連携案内

Issue ファイルの「進捗」セクションがプレースホルダのまま（`- [ ] タスク` / `- [ ] 調査項目` など、具体的なタスクが定義されていない）の場合、feature-dev による実装計画の策定を案内する:

```
> `feature-dev` で実装計画を立てますか？
```

ユーザーが承諾したら、feature-dev スキルの実行を提案する（直接実行はしない。案内のみ）。
既に具体的なタスクが定義されている場合はこの案内をスキップする。
