# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.4.1] - 2026-04-19

### Changed
- `eval-runner`: `expected_skill` が inline list `[a, b]` を受け付けるように拡張。command と skill のどちらに解決されても PASS と判定可能に
- eval-runner の allowed-tools から未使用の `Glob` を除去（Bash / Read / AskUserQuestion の 3 件に）

## [1.4.0] - 2026-04-19

### Added
- `eval-runner` スキル追加。`evals/` 配下の YAML ケースを実行し、トリガーフレーズ → 期待スキル起動の回帰テストを pass^k 基準で検証する（#18）

## [1.3.7] - 2026-04-19

### Changed
- cc-catch-up の state ファイルを `${CLAUDE_PLUGIN_DATA}/catch-up-state.json` から `${CLAUDE_PLUGIN_ROOT}/skills/cc-catch-up/state.json` へ移動。git 管理下に置くことでマシン間/再インストール時の履歴消失を防ぐ
- SKILL.md の Phase 0 / Phase 7 のパス参照を更新

## [1.3.6] - 2026-04-19

### Changed
- plugin-features.md カタログ更新: v2.1.106-v2.1.114 の新機能を反映
  - `xhigh` effort レベル（v2.1.111、Opus 4.7 専用）を Agent/Skill/Command フロントマター説明に追記
  - Runtime & CLI セクションに `plugin_errors` in stream-json (v2.1.111)、Built-in slash via Skill tool (v2.1.108)、subagent stall fail (v2.1.113)、plugin install range-conflict (v2.1.113) を追加
  - 環境変数セクションに `ENABLE_PROMPT_CACHING_1H` / `FORCE_PROMPT_CACHING_5M` (v2.1.108)、`OTEL_LOG_RAW_API_BODIES` (v2.1.111)、`CLAUDE_CODE_USE_POWERSHELL_TOOL` (v2.1.111) を追加
  - カバー範囲を v2.1.114 に更新

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
