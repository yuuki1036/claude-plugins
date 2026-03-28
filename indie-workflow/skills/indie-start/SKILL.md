---
name: indie-start
description: >
  セッション開始時の作業準備。main ブランチではダッシュボードモード（全プロジェクト状況表示）、
  feature ブランチでは Issue コンテキスト読み込み。
  トリガー: 「作業開始」「個人開発開始」「今日の作業」「/indie-start」
effort: high
allowed-tools:
  - Agent
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

### Phase 1: ブランチ名の取得と分岐

1. `git branch --show-current` でカレントブランチ名を取得する（Bash）
2. ブランチ名が `main` または `master` の場合:
   - **ダッシュボードモード**（Phase D1〜D4）へ進む
3. それ以外の場合:
   - **Feature ブランチモード**（Phase F1〜F7）へ進む

---

## ダッシュボードモード（main/master ブランチ時）

### Phase D1: 全プロジェクトスキャン

1. `.claude/indie/*/project.md` を Glob で列挙する
2. 各プロジェクトの `project.md` を Read で読み込む
3. プロジェクト一覧をサマリー表示する

### Phase D2: アクティブ Issue サマリー

1. `.claude/indie/*/issues/*.md` を Glob でスキャンする
2. 各 Issue ファイルを Read し、`status: in-progress` の Issue をプロジェクト別にリスト表示する
3. 放置 Issue（`last_active` フィールドが7日以上前）を警告付きで表示する

### Phase D2.5: Knowledge サマリー

1. `.claude/indie/*/knowledge/index.md` を Glob で列挙する
2. 各 index.md を Read で読み込み、プロジェクト別の knowledge 件数を表示する
3. index.md が存在しないプロジェクトは `.claude/indie/*/knowledge/*.md` を Glob でカウントする
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
  - 「`/indie-issue-create` で新しいタスクを作成」
- メンテナンスが必要な場合:
  - 「`/indie-maintain` でプロジェクト棚卸し」

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
   - `.claude/indie/{slug}/project.md` の存在を確認（Read）
   - 存在する場合は内容を読み込む

2. **Issue ファイルの確認**
   - `.claude/indie/{slug}/issues/{ISSUE-ID}.md` の存在を確認（Read）
   - 存在する場合:
     - 内容を読み込む
     - 「前回の作業状態」としてユーザーにサマリーを報告する（Phase F6 へ）
   - 存在しない場合:
     - Phase F4 へ進む

### Phase F3.5: Context Recovery Agent Team（並列起動）

Issue ファイルが存在し、内容を読み込めた場合に実行する。
Issue ファイルが存在しない場合（Phase F4 へ進む場合）はスキップする。

エージェントプロンプトの詳細は `${CLAUDE_PLUGIN_ROOT}/skills/indie-start/references/context-agents.md` を参照すること。

**以下の2エージェントを並列起動する:**

| Agent | 役割 | 入力 |
|-------|------|------|
| #1 Doc Resolver | 関連 Issue・Knowledge 直接参照を辿る | Issue ファイル内容、スラッグ |
| #2 Code Context | Issue 内のソースファイル参照を辿る + Git 状態取得 | Issue ファイル内容 |

**起動手順:**

1. `${CLAUDE_PLUGIN_ROOT}/skills/indie-start/references/context-agents.md` を Read する
2. 2つの Agent を**同時に**起動する（Agent ツールを2つ並列で呼び出す）
   - 各エージェントは **`model: "opus"` を明示指定**する
   - 各エージェントのプロンプトに Issue ファイルの内容とメタ情報を含める
3. 全エージェントの完了を待つ
4. 各エージェントの結果を Phase F6 の報告に統合する

**注意:** Agent #1 が Knowledge を解決するため、Phase F3.7 の keyword ベース検索と結果が重複する場合がある。重複は Phase F6 でマージする。

### Phase F3.7: 関連 Knowledge の検索

Issue ファイルが存在し、内容を読み込めた場合に実行する。

1. `.claude/indie/{slug}/knowledge/index.md` の存在を確認（Read）
2. **index.md が存在する場合:**
   - index.md を Read で読み込む
   - Issue のタイトル・概要・タスク内容からキーワードを抽出する
   - index.md の tags 列とキーワードを照合し、関連する knowledge を特定する
   - 関連する knowledge ファイルがあれば Read で内容を読み込む
3. **index.md が存在しない場合:**
   - `.claude/indie/{slug}/knowledge/*.md` を Glob で列挙する
   - knowledge ファイルが存在すれば、各ファイルのフロントマター（tags）と Issue のキーワードを照合する
4. **報告:**
   - 関連する knowledge が見つかった場合、Phase F6 の報告に含める:
     ```
     **関連 Knowledge:**
     - `knowledge/{topic}.md` — {概要}（tags: {tags}）
     ```
   - knowledge が0件の場合は何も表示しない

### Phase F4: Issue ファイル新規作成

Issue ファイルが存在しない場合:

1. `indie-issue-create` スキルを使った新規作成をユーザーに提案する
   - 「Issue ファイルが見つかりません。`/indie-issue-create` で新規作成しますか？」と確認
2. ユーザーの承認を得てから `indie-issue-create` スキルを実行する
3. ユーザーが不要と判断した場合はスキップして Phase F6 へ

### Phase F5: 放置 Issue 検知

1. Glob で `.claude/indie/*/issues/*.md` を検索し、全 Issue ファイルを列挙する
2. 各 Issue ファイルを Read し、以下の条件に合致するものを抽出する:
   - `status: in-progress` である
   - `last_active` フィールドが7日以上前である
3. 該当する Issue があれば警告を表示する:
   - 「以下の Issue が7日以上放置されています:」
   - Issue ID、タイトル、最終アクティブ日を一覧表示

### Phase F6: 作業準備完了報告

Phase F3〜F5 で収集した全情報を統合し、ユーザーに報告する:

- **Issue 情報**: タイトル・ステータス
- **未完了タスク一覧**: Issue ファイルのチェックリストから未完了項目を抽出（あれば）
- **前回セッションからの継続ポイント**: 更新履歴の最新エントリや進行中の作業内容
- **関連 Issue**: Agent #1 の結果（関連 Issue の概要一覧）（あれば）
- **関連 Knowledge**: Agent #1 の直接参照結果 + Phase F3.7 の keyword 検索結果をマージ（あれば）
- **参照ソースファイル**: Agent #2 の結果（読み込んだファイルの役割サマリー）（あれば）
- **Git 状態**: Agent #2 の結果（コミット数・最新コミット・未コミット変更・変更規模）
- **読み込んだプロジェクト doc**: 読み込んだファイル名
- **放置 Issue 警告**: 該当があれば表示（Phase F5）
- **debt サマリー**: `type: debt` の Issue 件数

### Phase F7: feature-dev 連携案内

Issue ファイルの状態と Git 状態に応じて案内を分岐する:

1. **進捗がプレースホルダ + コミット0件**（ブランチ作成直後）:
   - 「`feature-dev` で実装計画を立てますか？」と案内する
2. **進捗がプレースホルダ + コミット1件以上**（計画未記入のまま作業が進行）:
   - 「コミットがありますが計画が未記入です。`/indie-issue-maintain` で Issue ファイルを更新しますか？」と案内する
3. **具体的なタスクが定義済み**:
   - この案内をスキップする

ユーザーが承諾したら、該当スキルの実行を提案する（直接実行はしない。案内のみ）。

---

## セッションコンテキスト書き出し（Feature ブランチモード共通）

### Phase CTX: session-context.md 書き出し

Feature ブランチモードで Issue ファイルの読み込みに成功した場合に実行する。
ダッシュボードモード（main/master）および Issue ファイルが存在しない場合はスキップする。

1. 以下の情報を `.claude/session-context.md` に Write で書き出す:

```yaml
---
branch: {現在のブランチ名}
issue_id: {Issue ID}
updated_at: {現在の ISO 8601 タイムスタンプ}
source: indie-workflow
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
