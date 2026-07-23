# プロジェクト概要テンプレート

## フロントマター

```yaml
---
project: {PROJECT}
created: YYYY-MM-DD
---
```

## 構造

```md
# {PROJECT}: {プロジェクト名}

## 概要
{プロジェクトの目的・ゴール}

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
| {PROJECT-N} | タイトル | in-progress | feature |
```

> ステータスサマリーは frontmatter の `status`（5 値）を集計する。`debt` は type であって status ではないため、タイプ別サマリー（type: feature / bugfix / investigation / debt を集計）に分離する。

## 更新ルール

- `/maintain` 実行時にステータスサマリー・タイプ別サマリーと関連 Issue テーブルを自動更新
- ソート順: ステータス順（in-progress > backlog > frozen > completed > canceled）
