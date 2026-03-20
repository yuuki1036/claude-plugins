---
name: session-start
description: >
  セッション開始時の作業準備。ブランチ名から Linear Issue を特定し、
  関連プロジェクト doc と Issue ファイルを読み込む。
  トリガー: 「作業開始」「セッション開始」「タスク開始」「今日の作業を始める」「コンテキスト読み込み」「/session-start」
allowed-tools: mcp__linear__get_issue, Read, Write, Glob, Grep, Bash
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
- **読み込んだプロジェクト doc**: 読み込んだファイル名の一覧
