---
name: indie-start
description: >
  セッション開始時の作業準備。main ブランチではダッシュボードモード（全プロジェクト状況表示）、
  feature ブランチでは Issue コンテキスト読み込み。
  トリガー: 「作業開始」「個人開発開始」「今日の作業」「/indie-start」
allowed-tools:
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
   - **Feature ブランチモード**（Phase F1〜F6）へ進む

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

読み込んだ情報のサマリーをユーザーに報告する:

- **Issue 情報**: タイトル・ステータス
- **未完了タスク一覧**: Issue ファイルのチェックリストから未完了項目を抽出（あれば）
- **前回セッションからの継続ポイント**: 更新履歴の最新エントリや進行中の作業内容
- **読み込んだプロジェクト doc**: 読み込んだファイル名
- **放置 Issue 警告**: 該当があれば表示（Phase F5）
- **debt サマリー**: `type: debt` の Issue 件数
