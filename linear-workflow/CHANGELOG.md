# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.8.0] - 2026-03-23

### Added
- SessionStart hook で外部依存チェック（Linear MCP、feature-dev プラグイン）を実行
- plugin.json に `_requirements` フィールドを追加（依存メタデータ宣言）

## [1.7.1] - 2026-03-23

### Fixed
- Linear API の書き込み（save_issue 等）をユーザーの明示的な指示なしに実行しないようルールを追加
- 「Issue更新」がローカル Issue ファイルの更新を意味することをスキル説明に明記

## [1.7.0] - 2026-03-23

### Added
- issue-create: テンプレート選択を AskUserQuestion による選択 UI に変更
- issue-create: feature-dev 連携案内を AskUserQuestion による選択 UI に変更
- rules/issue-create-interaction.md を新規追加（SessionStart hook で注入）

## [1.6.0] - 2026-03-23

### Added
- session-start: ダッシュボードモードを追加（フル / スコープド）
- session-start: Next Issue ピック機能を追加
- session-start: allowed-tools に mcp__linear__list_issues を追加

## [1.5.0] - 2026-03-22

### Added
- knowledge retrieval フローを追加
- feature-dev 連携案内と Agent Team ルールを追加

## [1.4.0] - 2026-03-21

### Added
- init コマンドを追加

## [1.3.0] - 2026-03-20

### Added
- SessionStart hook によるプロジェクト管理ルール自動注入を追加

## [1.2.0] - 2026-03-20

### Added
- CLAUDE.md 軽量化に向けたスキル強化

### Fixed
- プラグイン品質改善
- プロジェクト固有の情報を汎用的な例に置換
- スキルのトリガーフレーズを改善
- 全プラグインの品質問題を一括修正

## [1.0.0] - 2026-03-20

### Added
- linear-workflow プラグインを新規作成
- Linear MCP 連携の Issue/プロジェクト管理機能
