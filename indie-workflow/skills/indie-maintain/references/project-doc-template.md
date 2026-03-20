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
| debt | 0 |
| completed | 0 |

## 関連 Issue
| ID | タイトル | ステータス | タイプ |
|----|---------|-----------|--------|
| {PROJECT-N} | タイトル | in-progress | feature |
```

## 更新ルール

- `/indie-maintain` 実行時にステータスサマリーと関連 Issue テーブルを自動更新
- ソート順: ステータス順（in-progress > backlog > frozen > completed）
