# 個人開発プロジェクト管理ルール

このプロジェクトは `.claude/indie/` で Issue をローカル管理している。以下のルールに従うこと。

## セッション開始時

1. `/session-start` を実行して作業コンテキストを読み込む
2. ブランチ名から Issue ID を自動特定し、関連ファイルを読み込む

## ブランチ命名規則

- `{type}/{PROJECT-N}-{description}` 形式を使う
- 例: `feat/MYAPP-3-add-auth`, `fix/BLOG-2-typo`

## Issue ファイル管理

- Issue ファイル: `.claude/indie/{project}/issues/{PROJECT-N}.md`
- プロジェクト概要: `.claude/indie/{project}/project.md`
- 作業の進捗は Issue ファイルのチェックリストに反映する
- `last_active` を作業のたびに更新する
- セッション終了前に `/issue-maintain` で Issue ファイルを更新する

## スコープ管理

- Issue の `scope_size` で宣言したサイズを守る（small: 3個以下, medium: 7個以下, large: 15個以下）
- タスクが増えてきたら分割を検討する
- 「スコープ外」セクションに除外理由を明記する

## 作業フロー

1. セッション開始 → `/session-start`
2. 新規 Issue 作成 → `/issue-create`
3. 作業中の進捗更新 → Issue ファイルのチェックリストを更新
4. セッション終了前 → `/issue-maintain` で Issue ファイルを整理
5. 定期的な棚卸し → `/indie-maintain` でプロジェクト全体を整理
6. 振り返り → `/retrospective` で学びを抽出
