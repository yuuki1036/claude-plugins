---
name: start
description: >
  セッション開始時の作業準備。main ブランチではダッシュボードモード（全プロジェクト状況表示）、
  feature ブランチでは Issue コンテキスト読み込み。
  トリガー: 「作業開始」「セッション開始」「今日の作業」「/start」
effort: high
allowed-tools:
  - Agent
  - Skill
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
main/master ブランチではダッシュボードモードで全プロジェクトの状況を表示し、
feature ブランチではブランチ名から Issue を特定して関連ファイルを読み込む。

## ワークフロー

### Phase 0: backend 検出（全スキル共通）

1. Glob で `.claude/indie/*/` と `.claude/linear/*/` を確認する。「dir が存在し、かつプロジェクト slug サブディレクトリを 1 つ以上持つ」場合のみ有効な backend とみなす（空 dir・残骸は無効）
2. `.claude/indie` のみ有効 → `BACKEND=local` / `DATA_DIR=.claude/indie`。`.claude/linear` のみ有効 → `BACKEND=linear` / `DATA_DIR=.claude/linear`。無効な残骸 dir がもう一方にある場合は警告を一言添えて継続する
3. **両方有効** → エラーとして停止する。両 dir の slug 一覧・issues 件数・最終更新日を並べて提示し、どちらを正とするか決めて他方を退避（rename）または削除する片寄せを案内する
4. **どちらも無効** → `/issue-workflow:init` の実行を案内して終了する

以後の `{DATA_DIR}` は検出したデータディレクトリ、`BACKEND` は判定結果を指す。

### Phase 0.7: Linear MCP 利用可能性チェック（BACKEND=linear のみ）

1. 軽量な Linear MCP 呼び出し（`mcp__linear__get_issue` など）を試みる
2. ツールが見つからない・接続エラーの場合:
   - **AskUserQuestion** で続行/中断を確認する:
     - question: "Linear MCP が利用できません。MCP なしで続行するとローカルファイルの情報のみでセッションを開始します（Linear からの Issue 取得・同期は不可）。"
     - header: "Linear MCP 未検出"
     - options:
       1. label: "続行" / description: "ローカルファイルのみでセッション開始する"
       2. label: "中断" / description: "スキルを中断する"
   - 「中断」選択時: スキルを終了する
   - 「続行」選択時: Linear MCP を使う Phase（1.5, Q2, P1〜P2, F3.5 の Linear Sync Agent）をスキップし、ローカルファイルのみで進行する
3. 正常に応答が返った場合: そのまま Phase 1 に進む

### Phase 1: ブランチ名の取得と分岐

1. `git branch --show-current` でカレントブランチ名を取得する（Bash）
2. **BACKEND=local の場合:**
   - ブランチ名が `main` または `master` → **ダッシュボードモード**（Phase D1〜D4）へ進む
   - それ以外 → **Feature ブランチモード**（Phase F1〜F7）へ進む
3. **BACKEND=linear の場合:**
   - ブランチ名から Issue ID（正規表現 `[A-Z]+-\d+`）を抽出できない（main, develop 等）→ **Quick Pick モード**（Phase Q1〜Q3）へ進む
   - Issue ID を抽出できた → **Phase 1.5** へ進む

### Phase 1.5: 子 Issue 有無チェック（BACKEND=linear のみ）

1. `mcp__linear__list_issues(parentId={issueId}, limit=1)` を呼び出す
   - `limit: 1` で1件だけ取得（存在チェックのみ）
2. 結果が1件以上: **親 Issue 軽量サマリーモード**（Phase P1〜P2）へ進む
3. 結果が0件: **Feature ブランチモード**（Phase F1〜F7）へ進む

---

## Quick Pick モード（BACKEND=linear・Issue ID なしブランチ）

最小限の情報で素早く次のタスクを選べるようにする。

### Phase Q1: アクティブ Issue クイックチェック

1. Grep で `{DATA_DIR}/` 配下の `status: in-progress` を一括検索する
   - `Grep(pattern="status: in-progress", path="{DATA_DIR}/", file_pattern="*.md")`
2. マッチしたファイル数をカウントする（内容は読まない）
3. `{DATA_DIR}/*/follow-ups/*.md` を Glob で列挙し、各ファイルの frontmatter `status: open` をカウントする
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

## 親 Issue 軽量サマリーモード（BACKEND=linear・子 Issue あり）

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

## ダッシュボードモード（BACKEND=local・main/master ブランチ時）

### Phase D1: 全プロジェクトスキャン

1. `{DATA_DIR}/*/project.md` を Glob で列挙する
2. 各プロジェクトの `project.md` を Read で読み込む
3. プロジェクト一覧をサマリー表示する

### Phase D2: アクティブ Issue サマリー

1. `{DATA_DIR}/*/issues/*.md` を Glob でスキャンする
2. 各 Issue ファイルを Read し、`status: in-progress` の Issue をプロジェクト別にリスト表示する
3. 放置 Issue（`last_active` フィールドが7日以上前）を警告付きで表示する
4. `{DATA_DIR}/*/follow-ups/*.md` を Glob で列挙し、各ファイルを Read して frontmatter の `status: open` を抽出する
5. open な follow-up があるプロジェクトのみ、件名・滞留日数付きで表示する（各プロジェクト最新 5 件まで、`created` が古い順に並べる）:
   ```
   **Follow-up:**
   - {slug}: {N}件
     - {件名}（{M}日前）
     - {件名}（{M}日前）
     - ...（残り {X}件）
   ```
   - 件名は frontmatter の `title` または先頭 H1 から取得
   - 滞留日数 = 現在日 - frontmatter の `created`
   - 5 件を超える場合は「...（残り {X}件）」を末尾に表示
6. プロジェクト横断で open な follow-up の合計が 5 件を超える場合は警告を追加表示する:
   ```
   WARNING: open な follow-up が合計 {total}件あります。棚卸しを推奨します。
   `/follow-up list` で一覧、`/follow-up promote` で Issue 化できます。
   ```

### Phase D2.5: Knowledge サマリー

1. `{DATA_DIR}/*/knowledge/index.md` を Glob で列挙する
2. 各 index.md を Read で読み込み、プロジェクト別の knowledge 件数を表示する
3. index.md が存在しないプロジェクトは `{DATA_DIR}/*/knowledge/*.md` を Glob でカウントする
4. 表示形式:
   ```
   **Knowledge:**
   - {project}: {件数}件（最新: {直近の knowledge ファイル名}）
   ```
5. knowledge が全プロジェクトで0件の場合はこのセクションをスキップする

### Phase D3: 技術的負債サマリー

1. Phase D2 で読み込んだ Issue のうち、`type: debt` の件数をプロジェクト別に表示する

### Phase D4: 次のアクション提案

以下を状況に応じて提案する:

- 放置 Issue がある場合:
  - 「放置 Issue に対応しませんか？ブランチ: `{type}/{SLUG-N}-{desc}`」
- 新規タスクを作りたい場合:
  - 「`/issue-create` で新しいタスクを作成」
- メンテナンスが必要な場合:
  - 「`/maintain` でプロジェクト棚卸し」

---

## Feature ブランチモード

### Phase F1: ブランチ名から Issue ID 抽出

1. ブランチ名から Issue ID を抽出する
   - パターン例: `feat/TEAM-12` → `TEAM-12`、`build/PROJ-345-update-node` → `PROJ-345`
   - 正規表現: `[A-Z]+-\d+` にマッチする部分を抽出
2. Issue ID が抽出できない場合:
   - 「Issue なしの通常作業」としてユーザーに通知する
   - 「ブランチ名に Issue ID が見つかりませんでした。通常の作業として開始します。」と報告して終了

### Phase F2: プロジェクトスラッグ特定

1. Issue ID のプレフィックスを小文字化してスラッグとする
   - 例: `TEAM-12` → `team`、`PROJ-345` → `proj`

### Phase F3: 関連ファイル読み込み

1. **プロジェクト doc の読み込み**
   - BACKEND=local: `{DATA_DIR}/{slug}/project.md` の存在を確認（Read）し、存在する場合は内容を読み込む
   - BACKEND=linear: Glob で `{DATA_DIR}/{slug}/projects/*.md` を検索し、存在するファイルを Read で全て読み込む

2. **Issue ファイルの確認**
   - `{DATA_DIR}/{slug}/issues/{ISSUE-ID}.md` の存在を確認（Read）
   - 存在する場合:
     - 内容を読み込む
     - 「前回の作業状態」としてユーザーにサマリーを報告する（Phase F6 へ）
   - 存在しない場合:
     - Phase F4 へ進む

### Phase F3.5: Context Recovery Agent Team（並列起動）

Issue ファイルが存在し、内容を読み込めた場合に実行する。
Issue ファイルが存在しない場合（Phase F4 へ進む場合）はスキップする。

エージェントプロンプトの詳細は `${CLAUDE_SKILL_DIR}/references/context-agents.md` を参照すること。

**以下のエージェントを並列起動する（#3 は BACKEND=linear のみ）:**

| Agent | 役割 | 入力 |
|-------|------|------|
| #1 Doc Resolver | 親 Issue・関連 Issue・Knowledge 直接参照を辿る | Issue ファイル内容、スラッグ |
| #2 Code Context | Issue 内のソースファイル参照を辿る + Git 状態取得 | Issue ファイル内容 |
| #3 Linear Sync（BACKEND=linear のみ） | Linear API の最新状態との差分検出 | Issue ID、frontmatter 情報 |

**起動手順:**

1. `${CLAUDE_SKILL_DIR}/references/context-agents.md` を Read する
2. **必須**: 対象の Agent（local: 2 つ / linear: 3 つ）を**同一メッセージ内で並列起動する**（Agent tool call を 1 つのレスポンスに含める）。逐次起動は禁止（待ち時間が倍になる）。各 Agent call に `run_in_background: false` を明示する（CC 2.1.198 で既定が background になり、省略すると完了を待たずに進んで結果を取りこぼす）
   - Agent #1 Doc Resolver: Issue ファイル内容 + スラッグを渡す
   - Agent #2 Code Context: Issue ファイル内容を渡す
   - Agent #3 Linear Sync（BACKEND=linear のみ、Phase 0.7 で MCP 利用可の場合のみ）: Issue ID + frontmatter を渡す
3. 全エージェントの完了を待つ（並列起動していれば最長エージェントの時間で揃う）
4. 各エージェントの結果を Phase F6 の報告に統合する

**注意:** Agent #1 が Knowledge を解決するため、Phase F3.7 の keyword ベース検索と結果が重複する場合がある。重複は Phase F6 でマージする。

### Phase F3.7: 関連 Knowledge の検索

Issue ファイルが存在し、内容を読み込めた場合に実行する。

1. `{DATA_DIR}/{slug}/knowledge/index.md` の存在を確認（Read）
2. **index.md が存在する場合:**
   - index.md を Read で読み込む
   - Issue のタイトル・概要・タスク内容からキーワードを抽出する
   - index.md の tags 列とキーワードを照合し、関連する knowledge を特定する
   - 関連する knowledge ファイルがあれば Read で内容を読み込む
3. **index.md が存在しない場合:**
   - `{DATA_DIR}/{slug}/knowledge/*.md` を Glob で列挙する
   - Grep でファイル本文からキーワードと一致する箇所を検索し、各ファイルのフロントマター（tags）と Issue のキーワードを照合する
4. **鮮度判定（stale チェック）:**
   - 関連する各 knowledge ファイルの frontmatter から `updated` フィールドを読み取る
   - 当日との差分を計算し、**60 日以上経過** している場合は `⚠️ stale?` マーカーを付与する
   - `updated` フィールドが存在しないファイルは、stale 判定をスキップ（マーカーなしで通常表示）
5. **報告:**
   - 関連する knowledge が見つかった場合、Phase F6 の報告に含める:
     ```
     **関連 Knowledge:**
     - `knowledge/{topic}.md` — {概要}（tags: {tags}, updated: 2026-04-30）
     - `knowledge/{stale-topic}.md` — {概要}（tags: {tags}, updated: 2026-01-15）⚠️ stale?
     - `knowledge/{legacy-topic}.md` — {概要}（tags: {tags}）
     ```
     - `updated` あり & 60 日以内: `updated: YYYY-MM-DD` を併記
     - `updated` あり & 60 日超過: `updated: YYYY-MM-DD` + `⚠️ stale?` マーカー
     - `updated` なし: 従来通り tags のみ表示
   - knowledge が0件の場合は何も表示しない

**stale 判定の意図:** 古い knowledge に引きずられて誤った設計を採るリスクを減らす。ユーザーに「これは古い情報の可能性がある」シグナルを出すのみで、自動的に除外はしない（最終判断はユーザー）。

### Phase F4: Issue ファイル新規作成

Issue ファイルが存在しない場合:

1. `issue-create` スキルを使った新規作成をユーザーに提案する
   - 「Issue ファイルが見つかりません。`/issue-create` で新規作成しますか？」と確認
2. ユーザーの承認を得てから **Skill ツール**で `issue-create` スキルを実行する
3. ユーザーが不要と判断した場合はスキップして Phase F6 へ

### Phase F5: 放置 Issue 検知 + Follow-up 通知

1. Glob で `{DATA_DIR}/*/issues/*.md` を検索し、全 Issue ファイルを列挙する
2. 各 Issue ファイルを Read し、以下の条件に合致するものを抽出する:
   - `status: in-progress` である
   - `last_active` フィールドが7日以上前である
3. 該当する Issue があれば警告を表示する:
   - 「以下の Issue が7日以上放置されています:」
   - Issue ID、タイトル、最終アクティブ日を一覧表示
4. `{DATA_DIR}/{slug}/follow-ups/*.md` を Glob で列挙し、`status: open` の件数をカウントする
5. open な follow-up があれば通知:
   - 「open な follow-up が {N}件あります。`/follow-up list` で確認できます」

### Phase F6: 作業準備完了報告

Phase F3〜F5 で収集した全情報を統合し、ユーザーに報告する:

- **Issue 情報**: タイトル・ステータス
- **未完了タスク一覧**: Issue ファイルのチェックリストから未完了項目を抽出（あれば）
- **前回セッションからの継続ポイント**: 更新履歴の最新エントリや進行中の作業内容
- **親 Issue コンテキスト**: Agent #1 の結果（親 Issue の背景・計画・スコープ外）（あれば）
- **関連 Issue**: Agent #1 の結果（関連 Issue の概要一覧）（あれば）
- **関連 Knowledge**: Agent #1 の直接参照結果 + Phase F3.7 の keyword 検索結果をマージ（あれば）
- **参照ソースファイル**: Agent #2 の結果（読み込んだファイルの役割サマリー）（あれば）
- **Git 状態**: Agent #2 の結果（コミット数・最新コミット・未コミット変更・変更規模）
- **Linear 同期**: Agent #3 の結果（ステータス差分・新規コメント）（BACKEND=linear のみ・あれば）
- **読み込んだプロジェクト doc**: 読み込んだファイル名
- **放置 Issue 警告**: 該当があれば表示（Phase F5）
- **debt サマリー**: `type: debt` の Issue 件数

### Phase F7: feature-dev 連携案内

Issue ファイルの状態と Git 状態に応じて案内を分岐する:

1. **進捗がプレースホルダ + コミット0件**（ブランチ作成直後）:
   - 「`feature-dev` で実装計画を立てますか？」と案内する
2. **進捗がプレースホルダ + コミット1件以上**（計画未記入のまま作業が進行）:
   - 「コミットがありますが計画が未記入です。`/issue-maintain` で Issue ファイルを更新しますか？」と案内する
3. **具体的なタスクが定義済み**:
   - この案内をスキップする

ユーザーが承諾したら、該当スキルの実行を提案する（直接実行はしない。案内のみ）。

> ブランチ作成直後（コミット0件）で実装前に仕様を固めたい場合は、仕様系プラグインの利用も案内できる（導入済みのもののみ・案内のみ）: bdd-spec=振る舞い仕様 (WHAT) / design-doc=技術設計 (HOW) / adr-keeper=設計判断 (WHY)。詳細なルーティングは `issue-create` の spec 選択フェーズに従う。

---

## セッションコンテキスト書き出し（Feature ブランチモード共通）

### Phase CTX: session-context.md 書き出し

Feature ブランチモードで Issue ファイルの読み込みに成功した場合に実行する。
ダッシュボードモード・Quick Pick モード・親 Issue 軽量サマリーモード、および Issue ファイルが存在しない場合はスキップする。

1. 以下の情報を `.claude/session-context.md` に Write で書き出す:

```yaml
---
shared_state_type: session
producer: issue-workflow
consumers: [code-review]
schema_version: 1
last_updated: {現在の ISO 8601 タイムスタンプ}
branch: {現在のブランチ名}
issue_id: {Issue ID}
---
```

> Shared State 規約（CLAUDE.md 参照）に従い、producer / consumers / schema_version / last_updated を付与する。consumer 側プラグインは frontmatter 不在のファイルも読めるが、新規書き出しは必ず付与する。

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
