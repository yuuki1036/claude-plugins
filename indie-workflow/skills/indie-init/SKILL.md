---
name: indie-init
description: >
  プロジェクトの初期セットアップ。ディレクトリ構造、project.md、
  backlog.md、counter.txt を作成する。
  トリガー: 「個人プロジェクト初期化」「indie init」「ローカルプロジェクトセットアップ」「/indie-init」
effort: low
allowed-tools:
  - Read
  - Write
  - Glob
  - Bash
---

# Init

プロジェクトの初期セットアップを行い、ディレクトリ構造とテンプレートファイルを生成する。

## ワークフロー

### Phase 1: プロジェクトスラッグの特定

1. コマンド引数で指定されていればそれを使う
2. 未指定ならユーザーに確認する
3. スラッグは小文字の英数字とハイフンのみ（例: `my-app`）

### Phase 2: プロジェクト名の確認

1. ユーザーにプロジェクト名を確認する（例: 「My App」）
2. 既にユーザーが説明している場合はそれを使い、重複して聞かない

### Phase 3: 既存チェック

1. `.claude/indie/{slug}/` が既に存在するか Glob で確認する
2. 存在する場合はエラーメッセージを出して中止する:
   - 「プロジェクト `{slug}` は既に存在します。」

### Phase 4: ディレクトリ・ファイル作成

以下の構造を作成する:

```
.claude/indie/{slug}/
  project.md         # プロジェクト概要
  counter.txt        # Issue 番号カウンター（初期値: 1）
  backlog.md         # バックログ一覧
  issues/            # Issue ファイル格納ディレクトリ（.gitkeep で作成）
  knowledge/         # 知見格納ディレクトリ（.gitkeep で作成）
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
| debt | 0 |
| completed | 0 |

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

4. **issues/.gitkeep** と **knowledge/.gitkeep**
   - 空ファイルを作成してディレクトリを確保する

### Phase 5: 完了報告と次のアクション案内

1. 作成されたファイル一覧を報告する
2. プロジェクトの概要を確認する
3. 次のアクションを案内する:
   - `/indie-issue-create {slug}` で最初の Issue を作成
   - `backlog.md` にアイデアを書き溜める
