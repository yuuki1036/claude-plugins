---
name: session-start
description: >
  セッション開始時の作業準備。ブランチ名から Linear Issue を特定し、関連ファイルを読み込む。
  main: Quick Pick、親 Issue: 軽量サマリー、feature: Context Recovery Agent Team。
  トリガー: 「作業開始」「セッション開始」「タスク開始」「コンテキスト読み込み」「/session-start」
effort: high
allowed-tools:
  - Agent
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

- **Quick Pick**: Issue ID のないブランチ（main 等）→ 素早くタスク選択
- **親 Issue 軽量サマリー**: Issue ID ありで子 Issue を持つ → 概要表示 + `/dashboard` 案内
- **通常セッション**: Issue ID ありで子 Issue なし → Context Recovery で完全なコンテキスト復元

## ワークフロー

### Phase 0: Linear MCP 利用可能性チェック

1. 軽量な Linear MCP 呼び出し（`mcp__linear__get_issue` など）を試みる
2. ツールが見つからない・接続エラーの場合:
   - **AskUserQuestion** で続行/中断を確認する:
     - question: "Linear MCP が利用できません。MCP なしで続行するとローカルファイルの情報のみでセッションを開始します（Linear からの Issue 取得・同期は不可）。"
     - header: "Linear MCP 未検出"
     - options:
       1. label: "続行" / description: "ローカルファイルのみでセッション開始する"
       2. label: "中断" / description: "スキルを中断する"
   - 「中断」選択時: スキルを終了する
   - 「続行」選択時: Linear MCP を使う Phase（1.5, Q2, P1〜P2, N3.5 の Linear Sync Agent）をスキップし、ローカルファイルのみで進行する
3. 正常に応答が返った場合: そのまま Phase 1 に進む

### Phase 1: ブランチ名から Issue ID 抽出 & モード判定

1. `git branch --show-current` でカレントブランチ名を取得する（Bash）
2. ブランチ名から Linear Issue ID を抽出する
   - パターン例: `feat/TEAM-12` → `TEAM-12`、`build/PROJ-345-update-node` → `PROJ-345`
   - 正規表現: `[A-Z]+-\d+` にマッチする部分を抽出
3. Issue ID が抽出できない場合（main, develop, Issue ID を含まない feature ブランチ等）:
   - **Quick Pick モード**（Phase Q1〜Q3）へ進む
4. Issue ID が抽出できた場合:
   - Phase 1.5 へ進む

### Phase 1.5: 子 Issue 有無チェック

1. `mcp__linear__list_issues(parentId={issueId}, limit=1)` を呼び出す
   - `limit: 1` で1件だけ取得（存在チェックのみ）
2. 結果が1件以上:
   - **親 Issue 軽量サマリーモード**（Phase P1〜P2）へ進む
3. 結果が0件:
   - **通常セッションモード**（Phase N2〜N6）へ進む

---

## Quick Pick モード

Issue ID のないブランチ（main/master、develop 等）でのセッション開始時に実行する。
最小限の情報で素早く次のタスクを選べるようにする。

### Phase Q1: アクティブ Issue クイックチェック

1. Grep で `.claude/linear/` 配下の `status: in-progress` を一括検索する
   - `Grep(pattern="status: in-progress", path=".claude/linear/", file_pattern="*.md")`
2. マッチしたファイル数をカウントする（内容は読まない）
3. `.claude/linear/*/follow-ups/*.md` を Glob で列挙し、各ファイルの frontmatter `status: open` をカウントする
4. 表示:
   ```
   アクティブ Issue: {N}件（詳細は `/dashboard`）
   open な follow-up: {M}件
   ```
   - follow-up が0件の場合は行を省略する

### Phase Q2: Next Issue ピック

1. `mcp__linear__list_issues(assignee="me", state="unstarted", limit=5)` を呼び出す
   - 自分にアサインされた未着手 Issue を取得
2. 取得結果を priority フィールドで並べ替える（1=Urgent → 4=Low の順）
3. 候補を提示する:
   ```
   **次に着手できる Issue（優先度順）:**
   1. [{ISSUE-ID}] [{priority}] {title}
   2. ...
   ```

### Phase Q3: アクション提案

- Issue を選択 → ブランチ作成: `git checkout -b feat/{ISSUE-ID}-{desc}` + `/issue-create`
- 詳細を確認 → `/dashboard`
- プロジェクト同期 → `/linear-maintain`

---

## 親 Issue 軽量サマリーモード

Issue ID がブランチに含まれ、かつその Issue が子 Issue を持つ場合に実行する。
最小限の情報を表示し、詳細は `/dashboard` に委譲する。

### Phase P1: 親 Issue の基本情報取得

1. `mcp__linear__get_issue(id={issueId})` で親 Issue のタイトル・ステータスを取得する
2. `mcp__linear__list_issues(parentId={issueId}, limit=50)` で子 Issue 件数とステータス内訳を取得する

### Phase P2: サマリー表示 + 案内

1. 以下の軽量サマリーを表示する:
   ```
   **親 Issue**: [{ISSUE-ID}] {title}
   **ステータス**: {status}
   **子 Issue**: {total}件（完了: {done}, 進行中: {in_progress}, 未着手: {todo}）
   ```
2. 案内を表示する:
   - 「`/dashboard {ISSUE-ID}` で子 Issue の詳細進捗を確認できます」
   - In Progress の子 Issue がある場合: 「`git checkout -b feat/{CHILD-ID}-{desc}` で作業を継続」
   - 全子 Issue が Done の場合: 「全子 Issue 完了。親 Issue のクローズを検討してください。」

---

## 通常セッションモード

Issue に子 Issue がない場合の通常作業フロー。
Context Recovery Agent Team で前回のコンテキストを完全復元する。

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

### Phase N3.5: Context Recovery Agent Team（並列起動）

Issue ファイルが存在し、内容を読み込めた場合に実行する。
Issue ファイルが存在しない場合（Phase N4 へ進む場合）はスキップする。

エージェントプロンプトの詳細は `${CLAUDE_SKILL_DIR}/references/context-agents.md` を参照すること。

**以下の3エージェントを並列起動する:**

| Agent | 役割 | 入力 |
|-------|------|------|
| #1 Doc Resolver | 親 Issue・関連 Issue・Knowledge 直接参照を辿る | Issue ファイル内容、スラッグ |
| #2 Code Context | Issue 内のソースファイル参照を辿る + Git 状態取得 | Issue ファイル内容 |
| #3 Linear Sync | Linear API の最新状態との差分検出 | Issue ID、frontmatter 情報 |

**起動手順:**

1. `${CLAUDE_SKILL_DIR}/references/context-agents.md` を Read する
2. **必須**: 以下 3 つの Agent を**同一メッセージ内で並列起動する**（Agent tool call を 3 つ、1 つのレスポンスに含める）。逐次起動は禁止（待ち時間が 3 倍になる）
   - Agent #1 Doc Resolver: Issue ファイル内容 + スラッグを渡す
   - Agent #2 Code Context: Issue ファイル内容を渡す
   - Agent #3 Linear Sync: Issue ID + frontmatter を渡す
3. 全エージェントの完了を待つ（並列起動していれば最長エージェントの時間で揃う）
4. 各エージェントの結果を Phase N5 の報告に統合する

**注意:** Agent #1 が Knowledge を解決するため、Phase N3.7 の keyword ベース検索と結果が重複する場合がある。重複は Phase N5 でマージする。

### Phase N3.7: 関連 Knowledge の検索

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

Phase N3〜N3.7 で収集した全情報を統合し、ユーザーに報告する:

- **Issue 情報**: タイトル・ステータス
- **未完了タスク一覧**: Issue ファイルのチェックリストから未完了項目を抽出（あれば）
- **前回セッションからの継続ポイント**: 更新履歴の最新エントリや進行中の作業内容
- **親 Issue コンテキスト**: Agent #1 の結果（親 Issue の背景・計画・スコープ外）（あれば）
- **関連 Issue**: Agent #1 の結果（関連 Issue の概要一覧）（あれば）
- **関連 Knowledge**: Agent #1 の直接参照結果 + Phase N3.7 の keyword 検索結果をマージ（あれば）
- **参照ソースファイル**: Agent #2 の結果（読み込んだファイルの役割サマリー）（あれば）
- **Git 状態**: Agent #2 の結果（コミット数・最新コミット・未コミット変更・変更規模）
- **Linear 同期**: Agent #3 の結果（ステータス差分・新規コメント）（あれば）
- **読み込んだプロジェクト doc**: 読み込んだファイル名の一覧

### Phase N6: feature-dev 連携案内

Issue ファイルの状態と Git 状態に応じて案内を分岐する:

1. **進捗がプレースホルダ + コミット0件**（ブランチ作成直後）:
   - 「`feature-dev` で実装計画を立てますか？」と案内する
2. **進捗がプレースホルダ + コミット1件以上**（計画未記入のまま作業が進行）:
   - 「コミットがありますが計画が未記入です。`/issue-maintain` で Issue ファイルを更新しますか？」と案内する
3. **具体的なタスクが定義済み**:
   - この案内をスキップする

ユーザーが承諾したら、該当スキルの実行を提案する（直接実行はしない。案内のみ）。

---

## セッションコンテキスト書き出し（全モード共通）

### Phase CTX: session-context.md 書き出し

通常セッションモードで Issue ファイルの読み込みに成功した場合に実行する。
Quick Pick モード、親 Issue 軽量サマリーモード、および Issue ファイルが存在しない場合はスキップする。

1. 以下の情報を `.claude/session-context.md` に Write で書き出す:

```yaml
---
branch: {現在のブランチ名}
issue_id: {Issue ID}
updated_at: {現在の ISO 8601 タイムスタンプ}
source: linear-workflow
---
```

2. YAML frontmatter の後に以下のセクションを追記する:

```markdown
# セッションコンテキスト

## Issue サマリー
{Issue ファイルの frontmatter（title, status, type）と概要セクションの要約}

## 設計判断・スコープ外
{Issue ファイルから「設計判断」「スコープ外」「方針」「意図的」に関する記述を抽出}
{該当する記述がない場合はこのセクションを省略}

## 関連プロジェクト
{読み込んだプロジェクト doc の要約（プロジェクト名と概要のみ）}
```

3. このファイルは毎回上書きする（前回のセッションの内容は不要）

**注意:**
- `.claude/session-context.md` はセッション固有のファイルであり、git にコミットしない
- Write ツールで `.claude/session-context.md` に書き出す
