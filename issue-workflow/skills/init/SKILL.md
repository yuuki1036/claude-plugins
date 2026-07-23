---
name: init
description: >
  プロジェクトの初期セットアップ。backend（local / linear）を選択し、
  対応するデータディレクトリ構造とテンプレートファイルを作成する。
  トリガー: 「プロジェクト初期化」「issue 管理セットアップ」「プロジェクトセットアップ」「/init」
effort: low
allowed-tools:
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

### Phase 5: 完了報告と次のアクション案内

1. 作成されたファイル一覧を報告する
2. プロジェクトの概要を確認する
3. 次のアクションを案内する:
   - `/issue-workflow:start` でセッション開始
   - `/issue-workflow:issue-create {slug}` で最初の Issue を作成
   - BACKEND=local: `backlog.md` にアイデアを書き溜める
