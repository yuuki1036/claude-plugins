---
name: dashboard
description: >
  Linear プロジェクトのダッシュボード表示。引数なしでフルダッシュボード（全プロジェクト俯瞰）、
  Issue ID 指定でスコープドダッシュボード（親 Issue の子 Issue 進捗表示）。
  セッション中いつでも呼び出し可能。
  トリガー: 「ダッシュボード」「プロジェクト状況」「全体確認」「進捗確認」
  「子Issueの進捗」「エピック進捗」「状況を見せて」「/dashboard」
effort: low
allowed-tools:
  - mcp__linear__get_issue
  - mcp__linear__list_issues
  - Read
  - Glob
  - AskUserQuestion
---

# Dashboard

Linear プロジェクトのダッシュボードを表示する。
引数の有無でモードが分岐する:

- **引数なし**: フルダッシュボード（全プロジェクト俯瞰）
- **Issue ID 指定**: スコープドダッシュボード（親 Issue の子 Issue 進捗表示）

---

## Phase 0: Linear MCP 利用可能性チェック（両モード共通）

1. 軽量な Linear MCP 呼び出し（`mcp__linear__list_issues` など）を試みる
2. ツールが見つからない・接続エラーの場合:
   - **AskUserQuestion** で続行/中断を確認する:
     - question: "Linear MCP が利用できません。MCP なしで続行するとローカルファイルの情報のみ表示されます（Linear からのリアルタイム情報は取得不可）。"
     - header: "Linear MCP 未検出"
     - options:
       1. label: "続行" / description: "ローカルファイルの情報のみで表示する"
       2. label: "中断" / description: "スキルを中断する"
   - 「中断」選択時: スキルを終了する
   - 「続行」選択時: Linear MCP を使う Phase（D3, S1〜S3 等）をスキップし、ローカルファイルのみで表示する
3. 正常に応答が返った場合: そのまま通常フローに進む

---

## フルダッシュボードモード（引数なし）

全チームの状況を俯瞰し、次に着手すべき Issue を提案する。

出力フォーマットは `${CLAUDE_SKILL_DIR}/references/dashboard-full.md` を参照すること。

### Phase D1: 全プロジェクトスキャン

1. `.claude/linear/` 配下のディレクトリ一覧を Glob で取得する
   - `.claude/linear/*/projects/*.md` を Glob で列挙
2. 各プロジェクト doc を Read で読み込む
3. プロジェクト一覧をサマリー表示する

### Phase D2: アクティブ Issue サマリー

1. `.claude/linear/*/issues/*.md` を Glob でスキャンする
2. 各 Issue ファイルを Read し、`status: in-progress` の Issue をプロジェクト別にリスト表示する
3. `last_active` フィールドが7日以上前の Issue を警告付きで表示する

### Phase D2.5: Follow-up サマリー

1. `.claude/linear/*/follow-ups/*.md` を Glob で列挙する
2. 各ファイルを Read し、`status: open` の follow-up をプロジェクト別に集計する
3. 表示形式:
   ```
   **Follow-up:**
   - {slug}: {N}件（最古: {created日}）
   ```
4. 全プロジェクトで0件の場合はこのセクションをスキップする

### Phase D2.7: Knowledge サマリー

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

## スコープドダッシュボードモード（Issue ID 指定時）

親 Issue の進捗と子 Issue の状況を表示する。

出力フォーマットは `${CLAUDE_SKILL_DIR}/references/dashboard-scoped.md` を参照すること。

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
