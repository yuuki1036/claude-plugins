---
name: indie-maintain
description: >
  全プロジェクトの棚卸し。放置 Issue の対処、技術的負債サマリー、
  frozen Issue の再評価、completed ファイルのクリーンアップを行う。
  トリガー: 「プロジェクト整理」「棚卸し」「メンテナンス」「/indie-maintain」
effort: medium
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
---

# Indie メンテナンス

## 概要

ローカルの `.claude/indie/` 内のプロジェクト管理ファイル群を棚卸しし、放置 Issue の検出・技術的負債の可視化・frozen Issue の再評価・completed ファイルのクリーンアップを行う。

## コマンド

| コマンド | 動作 |
|----------|------|
| `/indie-maintain` | 全プロジェクトを棚卸し |
| `/indie-maintain {slug}` | 指定プロジェクトのみ棚卸し |

---

## 処理内容

### 1. プロジェクトサマリー生成

`.claude/indie/` 内の全プロジェクトについて、`issues/` 内のファイルを走査し、ステータス別の Issue 件数を集計する。

- 各 Issue ファイルの frontmatter `status` を読み取り（`backlog` / `in-progress` / `frozen` / `completed`）
- frontmatter `type: debt` の Issue は debt としてもカウント
- 集計結果を各プロジェクトの `project.md` に反映

### 2. 放置 Issue 棚卸し

`status: in-progress` の Issue のうち、`last_active` が **7日以上前** のものを検出する。

- 検出した Issue をユーザーに提示し、以下の対処を確認:
  - **継続**: `last_active` を今日に更新して作業を続行
  - **凍結**: `status: frozen` に変更、`frozen_date` を記録
  - **破棄**: `status: canceled` に変更

### 3. frozen Issue 再評価

`status: frozen` の Issue のうち、`frozen_date` が **30日以上前** のものを検出する。

- 検出した Issue をユーザーに提示し、以下の対処を確認:
  - **再開**: `status: in-progress` に変更、`last_active` を今日に更新
  - **破棄**: `status: canceled` に変更

### 4. debt サマリー

`type: debt` の Issue 一覧を表示する。

- 作成日（`created`）からの経過日数を算出
- 経過日数の長い順にソート

### 5. completed Issue メンテナンス

`issues/` 内の `status: completed` ファイルを走査し、**indie-issue-maintain の処理フロー**に従って品質整理を行う。

#### メンテナンス処理

- Issue ファイルの圧縮（冗長な記録の整理）
- knowledge への切り出し（再利用可能な知見の抽出）
- 整理済みファイルの削除提案

**メンテナンス済みの判定**: 更新履歴に `メンテナンス:` で始まるエントリがあればスキップ。

**承認フロー**: completed Issue メンテナンスの結果は他の変更と合わせてレポートに含め、**一括でユーザー承認を得る**。

### 6. backlog.md 整理

各プロジェクトの `backlog.md` を確認し、Issue ファイルに昇格すべき項目がないかユーザーに提示する。

- 優先度や緊急性が高そうな項目をハイライト
- 昇格する場合は Issue ファイルを作成し、backlog.md から削除

### 7. project.md 更新

ステータスサマリー（件数テーブル）と関連 Issue テーブルを最新化する。

> **プロジェクト doc テンプレート**: `${CLAUDE_PLUGIN_ROOT}/skills/indie-maintain/references/project-doc-template.md` を Read で参照すること。

---

## 処理フロー

```
1. .claude/indie/ 内の全プロジェクトを列挙（slug 指定時はそれだけ）
2. 各プロジェクトについて:
   a. issues/ 内の全ファイルを走査しステータス集計
   b. 放置 Issue（in-progress + 7日以上未更新）を検出
   c. frozen Issue（30日以上凍結）を検出
   d. debt Issue を収集
   e. completed Issue にメンテナンス処理を実行
   f. backlog.md を確認
   g. project.md のステータスサマリー・関連 Issue テーブルを更新
3. 結果レポートをユーザーに提示
4. 承認を得てから実行
```

## 出力レポート形式

```md
## Indie Maintain レポート

### プロジェクトサマリー
| プロジェクト | backlog | in-progress | frozen | debt | completed |
|-------------|---------|-------------|--------|------|-----------|

### 放置 Issue (7日以上未更新)
| Issue | 最終更新 | 経過日数 |
|-------|---------|---------|

### 技術的負債
| Issue | 作成日 | 経過日数 |
|-------|--------|---------|

### frozen Issue (30日以上)
| Issue | 凍結日 | 経過日数 |
|-------|--------|---------|

### completed Issue メンテナンス
| Issue | 処理 | knowledge 切り出し | 削除提案 |
|-------|------|-------------------|---------|

### backlog.md 確認
| プロジェクト | 昇格候補 |
|-------------|---------|

### project.md 更新
| プロジェクト | 更新内容 |
|-------------|---------|
```

---

## 注意事項

- 全ての変更はレポート提示後、**ユーザーの承認を得てから実行**する
- knowledge/ は**いかなる場合も自動削除しない**
- `last_active` の更新は Issue ファイルの frontmatter を直接編集する
