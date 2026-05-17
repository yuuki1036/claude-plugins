# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.10.0] - 2026-05-18

### Added
- `hooks/scripts/on-commit.sh`（PostToolUse Bash matcher）を追加 (#33)。`git commit *` が成功した直後に `commit:created` イベントを Event Bus へ発行する。payload は `{"sha":"<short>","type":"<conventional commit type>","files":<count>}`。`--amend` / `--dry-run` / `--help` 系は除外、git リポジトリ外は no-op
- `hooks/hooks.json` の `PostToolUse` に `Bash` matcher + `if: "Bash(git commit *)"` 条件を追加し、上記スクリプトを駆動

## [1.9.3] - 2026-05-18

### Changed
- `hooks/lib/safe-hook.sh` を v2026-05-18+ に同期。`event_bus_publish` / `event_bus_tail` / `event_bus_clear` API を取得（正本由来、内部ライブラリ拡張）。将来 `commit:created` / `pr:created` イベント発行用の土台として整備

## [1.9.2] - 2026-05-15

### Changed
- `ui-verify` SKILL.md に「E2E への昇格（webapp-testing 委譲）」セクションを追加。複数ページ跨ぎシナリオ / 認証フロー / データ永続化テスト / 既存 Playwright プロジェクトでは公式 skill `webapp-testing`（`~/.claude/plugins/marketplaces/anthropic-agent-skills/skills/webapp-testing/`）を採用する判定基準を明示。`ui-verify` は単一ページ smoke test に責務を絞る

## [1.9.1] - 2026-05-15

### Changed
- `hooks/hooks.json` を `args[]` exec 形式へ移行（CC 2.1.139+）。シェル解釈なしでスクリプトを直接 spawn し、起動オーバーヘッドとパース起因のエッジケースを削減
- `safe-hook.sh` に `safe_hook_emit_bell` / `safe_hook_emit_window_title` を追加（CC 2.1.141+ terminalSequence 対応、opt-in 利用）

## [1.9.0] - 2026-05-12

### Changed
- **`ui-verify` snap モードのデフォルトを desktop 1 枚に変更** (#32 最優先 1)。従来は mobile/tablet/desktop の 3 viewport 一括撮影だったが、検証 PR で過剰だったため。複数 viewport が必要な場合は `--viewports=mobile,desktop` 等の opt-in 引数で指定する
- **PR タイプ別ガイドラインを `ui-verify` SKILL.md に追加** (#32 最優先 2)。検証 PR / リファクタ / UI 新機能 / レイアウト変更 / Theme 変更 / バグ修正の 6 タイプについて推奨枚数・viewport を明示
- **`git-commit-helper` Step 4.5 AskUserQuestion を 4 択化** (#32 次優先 3)。「撮る / スキップ」二択を「desktop 1 枚 / 複数 viewport / ローカル目視済み / スキップ」の 4 択に拡張
- **`.claude/.ui-verify-pending` を 3 値仕様に拡張** (#32 次優先 3)。`unverified` / `verified-local` / `verified-snap` の 3 値で verify 状態を表現する。`ui-change-reminder.sh` は `unverified` を書き込み、`ui-verify-gate.sh` は `verified-*` の場合 reminder をスキップ、ui-verify スキルは `verified-snap` で上書き
- **`pr-creator` に PR タイプ判定ロジックを追加** (#32 最優先 2)。ブランチ名・コミット message・差分シグナル（`@media`, breakpoint utility, `theme` トークン等）から PR タイプを推定し、`ui-verify` の `--viewports=...` 引数を組み立てて撮影枚数を最適化
- **`pr-creator` Screenshots の 1 枚レイアウトを追加**。1 枚のみの場合は table 形式ではなく単独画像で添付する

### Added
- **`git-commit-helper` probe / spike fast path** (#32 次優先 4)。ブランチ名に `probe|spike|stage1|compat|verify|poc|experiment` を含む場合、AskUserQuestion の default 選択肢を「ローカル目視済み」に倒す（撮影せずに verified-local としてマーク）
- **`pr-creator` 機密 UI チェックリスト** (#32 🟢 6)。`cc-screenshots` release は public のため、ログイン画面 / 顧客データ / 社内 URL / 機密 UI / 環境変数値が撮影に含まれていないかを撮影前にチェック。判定不能時は AskUserQuestion で「アップロード / ローカルパスのみ / Screenshots 省略」の 3 択
- `pr-creator` SKILL.md / `commands/pr.md` の allowed-tools に `AskUserQuestion` を追加（機密チェック・撮影方針確認のため）

## [1.8.1] - 2026-04-25

### Changed
- `git-commit-helper` コミット分割判定に段階的思考誘導を追加（Opus 4.7 対応）。分割単位決定前に `git diff` 全体の俯瞰・依存関係把握・論理的作業単位の identify を経由するステップを明記

## [1.8.0] - 2026-04-23

### Added
- opt-in の TDD Phase Gate hook を追加（`hooks/scripts/tdd-phase-gate.sh`）。`.claude/.tdd-phase-gate-enabled` 有効化時に PreToolUse (Edit|Write|MultiEdit) で実装ファイルに対応するテストファイルの存在をチェックし、Red phase 逸脱を警告（ブロックなし）(#26)
- README に「TDD Phase Gate（opt-in）」セクションを追加し有効化/無効化方法と検知ロジックを記載

## [1.7.4] - 2026-04-22

### Changed
- git-commit-helper スキルに「Generator として動作する」設計原則セクションを追加。品質判定は code-review:self-review を別コンテキストで実行する推奨フローを明示 (#27)

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
