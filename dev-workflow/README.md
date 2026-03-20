# dev-workflow

Git操作とPR作成の開発ワークフロープラグイン。原子性重視のコミットとLinear Issue連携PR作成をサポートする。

## 含まれるスキル

### git-commit-helper

原子性を重視した高品質なGitコミットを作成するスキル。変更を分析して論理的な作業単位に分割し、Conventional Commits準拠の日本語メッセージでコミットする。

- Protected branchの安全性チェック
- 変更の自動分割判定（1コミット = 1作業単位）
- `git add -p` によるhunk単位のステージング
- Conventional Commits準拠の日本語コミットメッセージ生成

### pr-creator

差分とコミット履歴からdescriptionを自動生成してPRを作成するスキル。Linear Issue連携にも対応。

- リポジトリのPRテンプレート自動検出・準拠
- ブランチ名からLinear Issue IDを抽出して情報を取得
- タスク詳細ファイル（`.claude/plans/`）の活用
- 常にドラフトPRとして作成

## 使い方

- コミット作成: 「コミットして」「変更をコミット」と伝える
- PR作成: 「PR作って」「プルリクエスト作成」と伝える
