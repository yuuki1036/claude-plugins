---
name: init
description: >
  プロジェクトの初期セットアップ。backend（local / linear）を選択し、
  対応するデータディレクトリ構造とテンプレートファイルを作成する。
  トリガー: 「プロジェクト初期化」「issue 管理セットアップ」「プロジェクトセットアップ」「/issue-workflow:init」
effort: low
allowed-tools:
  - mcp__linear__list_projects
  - mcp__linear__get_project
  - Read
  - Write
  - Glob
  - AskUserQuestion
---

# Init

プロジェクトの初期セットアップを行い、backend に応じたディレクトリ構造とテンプレートファイルを生成する。

## ワークフロー

### Phase 0: backend の決定

1. Glob で `.claude/indie/*/` と `.claude/linear/*/` を確認する。「dir が存在し、かつプロジェクト slug サブディレクトリを 1 つ以上持つ」場合のみ有効な backend とみなす（空 dir・残骸は無効）
2. **片方が有効** → その backend を採用する（既存プロジェクトと同じ backend に新しい slug を追加する。質問しない）。indie → `BACKEND=local` / `DATA_DIR=.claude/indie`、linear → `BACKEND=linear` / `DATA_DIR=.claude/linear`
3. **両方有効** → エラーとして停止する。両 dir の slug 一覧・issues 件数・最終更新日（`ls -lt` 相当）を並べて提示し、どちらを正とするか決めて他方を退避（rename）または削除する片寄せを案内する
4. **どちらも無効** → **AskUserQuestion** で backend を選択する:
   - question: "Issue 管理の backend を選択してください（データディレクトリの場所と Linear 連携の有無が決まります）"
   - header: "backend"
   - options:
     1. label: "local" / description: "ローカル完結の Issue 管理（.claude/indie/ に保存。外部サービス不要）"
     2. label: "linear" / description: "Linear 連携の Issue 管理（.claude/linear/ に保存。Linear MCP と同期）"
   - 選択に応じて `BACKEND` / `DATA_DIR` を設定する

### Phase 0.7: Linear MCP 利用可能性チェック（BACKEND=linear のみ）

1. `mcp__linear__list_projects` の呼び出しを試みる（Phase 3.5 でも使うため兼用）
2. ツールが見つからない・接続エラーの場合:
   - **AskUserQuestion** で続行/中断を確認する:
     - question: "Linear MCP が利用できません。MCP なしで続行するとディレクトリ構造のみ作成されます（プロジェクト doc の生成はスキップ）。"
     - header: "Linear MCP 未検出"
     - options:
       1. label: "続行" / description: "ディレクトリ構造のみ作成する（Linear 情報なし）"
       2. label: "中断" / description: "スキルを中断する"
   - 「中断」選択時: スキルを終了する
   - 「続行」選択時: Phase 3.5 の Linear 取得をスキップし、Phase 4 に直接進む
3. 正常に応答が返った場合: 結果を Phase 3.5 で再利用し、そのまま Phase 1 に進む

### Phase 1: プロジェクトスラッグの特定

1. コマンド引数で指定されていればそれを使う
2. 未指定ならユーザーに確認する
   - BACKEND=linear の場合、スラッグは Linear の Issue ID プレフィックスを小文字化したもの（例: `TEAM` → `team`）
3. スラッグは小文字の英数字とハイフンのみ（例: `my-app`）

### Phase 2: プロジェクト名の確認

1. ユーザーにプロジェクト名を確認する（例: 「My App」）
2. 既にユーザーが説明している場合はそれを使い、重複して聞かない

### Phase 3: 既存チェック

1. `{DATA_DIR}/{slug}/` が既に存在するか Glob で確認する
2. 存在する場合はエラーメッセージを出して中止する:
   - 「プロジェクト `{slug}` は既に存在します。」
   - 上書きや再初期化は行わない

### Phase 3.5: Linear プロジェクト情報の取得（BACKEND=linear のみ・任意）

1. Linear MCP `list_projects` でプロジェクト一覧を取得する
2. スラッグに対応するプロジェクトを特定する
   - チーム識別子（スラッグの大文字版）に関連するプロジェクトを探す
3. 対応するプロジェクトが見つかった場合:
   - `get_project` で詳細情報を取得する
4. 取得できなかった場合（MCP 未接続・プロジェクト未発見など）:
   - 「Linear からプロジェクト情報を取得できませんでした。ディレクトリ構造のみ作成します。」と通知する
   - Phase 4 に進む（Phase 4.5 のプロジェクト doc 作成はスキップ）

### Phase 4: ディレクトリ・ファイル作成

#### BACKEND=local の場合

以下の構造を作成する:

```
.claude/indie/{slug}/
  project.md            # プロジェクト概要
  counter.txt           # Issue 番号カウンター（初期値: 1）
  backlog.md            # バックログ一覧
  issues/               # Issue ファイル格納ディレクトリ（.gitkeep で作成）
  knowledge/            # 知見格納ディレクトリ（個別知見 = source、.gitkeep で作成）
    concepts/           # 概念ページ（横断統合 = concept、.gitkeep で作成）
```

1. **counter.txt**
   - 内容: `1`（改行なし）

2. **project.md**

```md
---
project: {SLUG大文字}
created: {今日の日付}
---
# {SLUG大文字}: {プロジェクト名}

## 概要
{ユーザーに入力してもらう or 「TODO: プロジェクトの概要を記入」}

## ステータスサマリー
| ステータス | 件数 |
|-----------|------|
| backlog | 0 |
| in-progress | 0 |
| frozen | 0 |
| completed | 0 |
| canceled | 0 |

## タイプ別サマリー
| タイプ | 件数 |
|--------|------|
| feature | 0 |
| bugfix | 0 |
| investigation | 0 |
| debt | 0 |

## 関連 Issue
| ID | タイトル | ステータス | タイプ |
|----|---------|-----------|--------|
```

3. **backlog.md**

```md
# Backlog

## 未分類
-

## 次にやりたい
-
```

4. **issues/.gitkeep** と **knowledge/.gitkeep** と **knowledge/concepts/.gitkeep**
   - 空ファイルを Write で作成してディレクトリを確保する（`knowledge/concepts/.gitkeep` で概念ページ用ディレクトリも保持する）

#### BACKEND=linear の場合

以下の構造を作成する（Issue 採番・バックログは Linear 側が持つため counter.txt / backlog.md は作らない）:

```
.claude/linear/{slug}/
  projects/             # プロジェクト doc 格納ディレクトリ（.gitkeep で作成）
  issues/               # Issue ファイル格納ディレクトリ（.gitkeep で作成）
  knowledge/            # 知見格納ディレクトリ（個別知見 = source、.gitkeep で作成）
    concepts/           # 概念ページ（横断統合 = concept、.gitkeep で作成）
```

各ディレクトリに `.gitkeep` を配置して空ディレクトリを保持する。

### Phase 4.5: プロジェクト doc の生成（BACKEND=linear のみ）

Phase 3.5 で Linear プロジェクト情報を取得できた場合のみ実行する:

1. テンプレートを読み込む（Read）
   - `${CLAUDE_SKILL_DIR}/../linear-maintain/references/project-doc-template.md`
2. テンプレートの形式に従ってプロジェクト doc を生成する
   - 配置先: `.claude/linear/{slug}/projects/{プロジェクト名のスラッグ}.md`
   - Linear から取得した情報（プロジェクト名、description、ステータス、リード、優先度）を反映する
   - 「関連 Issue」テーブルは空の状態にする
3. 生成した内容をユーザーに提示し、承認を得てから書き込む

### Phase 5: 完了報告と次のアクション案内

1. 作成されたファイル一覧を報告する
2. プロジェクトの概要を確認する
3. 次のアクションを案内する:
   - `/issue-workflow:start` でセッション開始
   - `/issue-workflow:issue-create {slug}` で最初の Issue を作成
   - BACKEND=local: `backlog.md` にアイデアを書き溜める
