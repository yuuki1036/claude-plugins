# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.3.0] - 2026-03-29

### Added
- 全スキルに effort frontmatter を追加（git-commit-helper/pr-creator: medium）
- PreToolUse conditional hook: git push 前にセルフレビューを推奨

## [1.2.1] - 2026-03-25

### Added
- 同一ファイル内の hunk 分割ステージング手法を追加（git diff + パッチ編集 + git apply --cached）

## [1.2.0] - 2026-03-23

### Added
- SessionStart hook で外部依存チェック（gh CLI、Linear MCP）を実行
- plugin.json に `_requirements` フィールドを追加（依存メタデータ宣言）

## [1.1.1] - 2026-03-23

### Fixed
- スキル description のトリガーフレーズを「トリガー:」形式に統一

## [1.1.0] - 2026-03-21

### Fixed
- プラグイン品質改善
- プロジェクト固有の情報を汎用的な例に置換
- 全プラグインの品質問題を一括修正

## [1.0.0] - 2026-03-20

### Added
- dev-workflow プラグインを新規作成
- Git コミット・PR 作成の開発ワークフロー
