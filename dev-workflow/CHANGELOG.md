# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.7.3] - 2026-04-20

### Changed
- ui-verify: allowed-tools を 28 → 15 に削減（Permission Pruning）。本文で使用されていない chrome-devtools MCP ツール（select_page / list_pages / close_page / get_console_message / get_network_request / emulate / fill_form / type_text / evaluate_script / handle_dialog）と未使用 Write / Glob / Grep を除去 (#28)

## [1.7.2] - 2026-04-19

### Changed
- hook スクリプト全般を `safe-hook.sh` 共通ラッパー経由に移行（check-deps / detect-web-project / ui-change-reminder / ui-verify-gate） (#21)

## [1.7.1] - 2026-04-19

### Fixed
- `git-commit-helper` スキルおよび `/commit` コマンドの `allowed-tools` に `AskUserQuestion` を追加（本文で使用しているが未宣言だったため実行時拒否の可能性があった）
- `check-deps.sh` に `chrome-devtools` MCP と `node` CLI のチェックを追加（`_requirements` との不整合を解消）

## [1.7.0] - 2026-04-19

### Added
- `hooks/scripts/upload-screenshots.sh` を追加。`.claude/screenshots/` 内の画像を GitHub Release（`cc-screenshots` タグ）に一括アップロードし public URL を返す
- `git-commit-helper` スキルに UI 統合セクション追加。UI 差分時に ui-verify snap を対話的に実行し `.claude/.ui-verify-pending` をクリア
- `pr-creator` スキルに Screenshots 添付セクション追加。UI PR で最新 snap を upload-screenshots.sh で GitHub Release にアップロード後、PR body に `## Screenshots` テーブルを自動埋め込み
- PR Screenshots のフォールバック対応（gh 未認証・アップロード失敗時はローカルパス記載）

## [1.6.0] - 2026-04-19

### Added
- SessionStart hook に `detect-web-project.sh` を追加。Web フレームワーク依存を検出してプロジェクト単位で ui-verify 連携を有効化（`.claude/.ui-verify-enabled` フラグ）
- PostToolUse hook（Edit/Write/MultiEdit）に `ui-change-reminder.sh` を追加。UI 関連ファイル（tsx/jsx/vue/svelte/css/scss/html/astro/mdx）の変更時に ui-verify 利用を促すリマインダーを注入
- PreToolUse hook の `git commit` 前 gate を追加。UI 変更後に動作確認が記録されていない場合に reminder を表示
- ui-verify スキル実行後の後処理に `.claude/.ui-verify-pending` フラグクリアを追加

### Changed
- Web プロジェクト以外では UI 自動化 hook が一切発火しない設計（非 Web プロジェクトでのノイズゼロ）

## [1.5.0] - 2026-04-18

### Added
- `ui-verify` スキルを追加。chrome-devtools MCP を使った Web UI の動作確認・スタイル調整・スクリーンショット取得を自動化（verify / tune / snap の3モード）
- `/ui-verify` スラッシュコマンドを追加
- `.mcp.json` で chrome-devtools-mcp を同梱配布（プラグインインストールで自動的に MCP サーバーが有効化）
- plugin.json の `_requirements` に chrome-devtools MCP と node を追加

## [1.4.0] - 2026-04-08

### Added
- `userConfig` でコミットメッセージ言語を設定可能に（`commit_language`: ja/en、デフォルト: ja）
- README に `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS` 環境変数の案内を追加

## [1.3.1] - 2026-03-31

### Changed
- SessionStart check-deps.sh に `once: true` 追加（セッション中1回のみ実行）

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
