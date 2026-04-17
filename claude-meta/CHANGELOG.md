# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.3.5] - 2026-04-17

### Added
- improvement-patterns: P-11 「Opus 4.7 向け effort 調整 (`max` → `xhigh`)」パターンを追加

## [1.3.4] - 2026-04-15

### Changed
- plugin-features.md カタログ更新: PreCompact hook（v2.1.105）、monitors manifest key（v2.1.105）、description cap 250→1536（v2.1.105）、/reload-plugins スキル反映ノート追加
- catch-up-state.json 初期作成（v2.1.109 時点）

## [1.3.3] - 2026-04-08

### Changed
- plugin-features.md カタログ更新: UserPromptSubmit イベント、sessionTitle、hook model パラメータ、スキル name フロントマター、コマンド effort/keep-coding-instructions を追記

## [1.3.2] - 2026-04-04

### Fixed
- claude-md-improver スキルの description を 250 文字以内に短縮（v2.1.86 の上限対応）

### Changed
- plugin-features.md カタログ更新: SessionEnd, SubagentStart/Stop, PermissionRequest, bin/, git-subdir, description 上限, disableSkillShellExecution, defer, MCP tool result persistence 等を追記

## [1.3.1] - 2026-03-31

### Changed
- plugin-features.md カタログ更新: PermissionDenied hook、last_assistant_message、initialPrompt バージョン修正

## [1.3.0] - 2026-03-29

### Added
- cc-catch-up スキル: Claude Code アップデートの自動追従ワークフロー
- /catch-up コマンド: スキルとペアリング（引数でバージョン範囲指定可）
- references/plugin-features.md: CC プラグイン関連機能カタログ
- references/improvement-patterns.md: 機能→改善のデシジョンツリーと before/after パターン集
- `${CLAUDE_PLUGIN_DATA}` による前回キャッチアップ状態の永続追跡

## [1.2.0] - 2026-03-29

### Added
- 全スキルに effort frontmatter を追加（claude-code-setup/claude-md-improver: high）

## [1.1.1] - 2026-03-23

### Fixed
- スキル description のトリガーフレーズを「トリガー:」形式に統一

## [1.1.0] - 2026-03-21

### Fixed
- プラグイン品質改善
- 全プラグインの品質問題を一括修正

## [1.0.0] - 2026-03-20

### Added
- claude-meta プラグインを新規作成
- Claude Code 設定管理・CLAUDE.md 監査改善機能
