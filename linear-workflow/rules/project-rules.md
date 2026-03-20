# Linear プロジェクト管理ルール

このプロジェクトは `.claude/linear/` で Linear Issue を管理している。以下のルールに従うこと。

## セッション開始時

1. `/session-start` を実行して作業コンテキストを読み込む
2. ブランチ名から Issue ID を自動特定し、関連ファイルを読み込む

## ブランチ命名規則

- `{type}/{TEAM-ID}-{description}` 形式を使う
- 例: `feat/TEAM-123-add-login`, `fix/TEAM-456-null-check`

## Issue ファイル管理

- Issue ファイル: `.claude/linear/{slug}/issues/{ISSUE-ID}.md`
- プロジェクト doc: `.claude/linear/{slug}/projects/*.md`
- 作業の進捗は Issue ファイルのチェックリストに反映する
- セッション終了前に `/issue-maintain` で Issue ファイルを更新する

## Linear MCP 連携

- `/linear-maintain` で Linear → ローカルの一方向同期を実行する（プロジェクト doc、Issue ステータスの取得・更新）
- Linear 側のステータス変更は Linear UI で行う

## 作業フロー

1. セッション開始 → `/session-start`
2. 新規 Issue 作成が必要 → `/issue-create`
3. 作業中の進捗更新 → Issue ファイルのチェックリストを更新
4. セッション終了前 → `/issue-maintain` で Issue ファイルを整理
5. 定期的な同期 → `/linear-maintain` でプロジェクト doc を最新化
