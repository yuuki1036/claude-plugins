# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.13.0] - 2026-03-29

### Changed
- issue-create: AskUserQuestion の呼び出し仕様を SKILL.md に直接埋め込み（テンプレート選択・feature-dev 連携）

### Removed
- rules/issue-create-interaction.md を削除（間接参照では LLM が AskUserQuestion を呼ばない問題の修正）
- inject-rules.sh から interaction.md の注入を削除

## [1.12.1] - 2026-03-29

### Fixed
- plugin.json から無効な agents フィールドを削除し manifest バリデーションエラーを修正

## [1.12.0] - 2026-03-29

### Added
- 全スキルに effort frontmatter を追加（session-start: high, dashboard: low, init: low, 他: medium）
- PostCompact hook: コンテキスト圧縮後にプロジェクトルールを再注入
- agents/ ディレクトリ: Context Recovery Agent Team を独立エージェント定義ファイルとして抽出（doc-resolver, code-context, linear-sync）
- plugin.json に agents フィールドを追加

## [1.11.0] - 2026-03-25

### Added
- dashboard: 新規スキル/コマンドとして切り出し（フルダッシュボード + スコープドダッシュボード）
- session-start: main ブランチ用 Quick Pick モード（軽量タスク選択）
- session-start: 親 Issue 軽量サマリーモード（詳細は `/dashboard` に委譲）

### Changed
- session-start: ダッシュボード機能を `/dashboard` に分離し、session-start を軽量化
- session-start: Context Recovery Agent Team に model: opus を明示指定

## [1.10.0] - 2026-03-24

### Added
- session-start: セッションコンテキスト書き出し（Phase CTX）を追加。Issue の設計判断を `.claude/session-context.md` に書き出し、code-review との連携を実現

## [1.9.0] - 2026-03-24

### Added
- session-start: Context Recovery Agent Team を追加（既存 Issue 再開時の深いコンテキスト復元）
- session-start: Doc Resolver エージェント（親 Issue・関連 Issue・Knowledge 参照解決）
- session-start: Code Context エージェント（ソースファイル参照解決 + Git 状態取得）
- session-start: Linear Sync エージェント（Linear API 最新状態との差分検出）
- session-start: allowed-tools に Agent, mcp__linear__list_comments を追加

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
