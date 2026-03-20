# プロジェクト doc テンプレート

プロジェクト doc は以下の形式で作成・更新する。

```md
---
source: linear
project_id: {Linear Project ID}
last_updated: YYYY-MM-DD
---
# {プロジェクト名}

## 概要
{Linear プロジェクトの description}

## ステータス
{ステータス}（リード: {リード名} / 優先度: {優先度}）

## 関連 Issue

| Issue | タイトル | Linear | PR |
|-------|---------|--------|-----|
| CFP-XXX | タイトル | Done | #XX |

## 備考
{共通コンポーネント、仕様メモ等}
```

## 関連 Issue テーブルの更新ルール

- **ソート順**: Linear ステータス順（In Progress > In Review > Todo > Done）、同一ステータス内は Issue ID 昇順
- **Linear 列**: Linear 上の最新ステータスを反映（`list_issues` の state で取得）
- **PR 列**: Issue ファイル（`issues/*.md`）の frontmatter `pr` フィールドから取得。なければ `-`
- **自分にアサインされた Issue**: `issues/` にファイルがあるもの。テーブルの Linear 列と issues ファイルの `linear_status` を同期
- **他メンバーの Issue**: テーブルのみで管理（issues ファイルは作らない）
- **完了プロジェクト**: ステータスを `Done` に更新し、全 Issue が Done であることを確認

## Issue ファイルとの同期ルール

Issue ファイル（`issues/{ISSUE-ID}.md`）が存在する場合:
- frontmatter の `linear_status` を Linear 上のステータスで更新
- frontmatter の `status` は手動管理（`in-progress` / `completed`）なので Linear ステータスで自動変更しない
- ただし Linear が `Done` かつ Issue ファイルの status が `in-progress` の場合、ユーザーに確認を促す
