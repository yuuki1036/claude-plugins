# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.5] - 2026-07-02

### Fixed

- `hooks/scripts/check-deps.sh` の `check_mcp` が同梱 `.mcp.json` を検査対象に含めていたため `found` が常に true になり、MCP サーバー未導入でも ERROR が発火しない dead check だった問題を修正。設定ファイルの grep をやめ、同梱 `.mcp.json` の `command`（＝MCP サーバーバイナリ名 `notebooklm-mcp`）が PATH 上に実在するかを `command -v` で検査する実効チェックに変更（`_requirements` ↔ `check_mcp "notebooklm-mcp"` の形式同期は維持）
- `README.md` セットアップ手順の「プロジェクトルートにチェックアウトされた状態で」という誤記を修正（同梱 `.mcp.json` はプラグインインストールで有効になる）

### Changed

- `references/source-types.md` の `source_add` 呼び出し例を現行 notebooklm-mcp シグネチャに更新（`source_add(source_type=url|text|drive|file, url=/text=/document_id=/file_path=...)`）。旧位置引数例・「ローカルパス対応は実装次第」の記述を廃し、file/text/drive/複数 URL/`wait` を追記
- `commands/notebook-add-source.md` / `commands/notebook-query.md` に `argument-hint` を追加

## [0.2.4] - 2026-06-15

### Changed

- `hooks/lib/safe-hook.sh` を正本に同期（additionalContext 注入 helper `safe_hook_emit_context` 追加に伴う byte-identical 複製の更新）

## [0.2.3] - 2026-06-05

### Fixed
- `check-deps.sh` の `check_mcp` が user スコープ（`claude mcp add -s user` で `~/.claude.json` の `.mcpServers` に書かれる MCP）を検知できず、設定・接続済みでも「未設定」と誤検知していた問題を修正。既存の cfg ファイル（`~/.claude/mcp.json` / `.mcp.json` / 同梱 `.mcp.json`）の grep 近似チェックの前に、`jq` で `~/.claude.json` の `.mcpServers` を厳密に確認する処理を前置（grep ではなく `has($n)` を使うのは、`~/.claude.json` に会話ログ等が含まれ単純 grep だと無関係箇所に誤マッチするため）。dev-workflow / code-review / linear-workflow と共通の修正

## [0.2.2] - 2026-05-18

### Changed
- `hooks/lib/safe-hook.sh` を v2026-05-18+ に同期。`event_bus_publish` / `event_bus_tail` / `event_bus_clear` API を取得（正本由来、内部ライブラリ拡張）

## [0.2.1] - 2026-05-15

### Changed

- `hooks/hooks.json` を `args[]` exec 形式へ移行（CC 2.1.139+）
- `safe-hook.sh` に `safe_hook_emit_bell` / `safe_hook_emit_window_title` を追加（CC 2.1.141+ terminalSequence 対応）

## [0.2.0] - 2026-05-12

### Changed

- `.mcp.json` の notebooklm-mcp に `alwaysLoad: true` を追加（Claude Code v2.1.121 新機能）。SessionStart 時に MCP サーバーを即時ロードし、初回 tool 呼び出しのレイテンシを削減する。NotebookLM への問い合わせ・ソース追加が「最初の 1 回だけ遅い」体験を改善

## [0.1.1] - 2026-05-11

### Fixed

- skills / commands の MCP tool 参照を `mcp__notebooklm-mcp__*` から `mcp__plugin_notebooklm-workflow_notebooklm-mcp__*` に修正（プラグイン同梱 MCP の正式プレフィックス対応）
- SessionStart hook の依存チェックがプラグイン同梱の `${CLAUDE_PLUGIN_ROOT}/.mcp.json` を見ておらず false positive ERROR を出していた問題を修正

## [0.1.0] - 2026-05-10

### Added

- `notebook-add-source` コマンド: URL / YouTube / Google Drive / PDF を NotebookLM ノートに追加
- `notebook-query` コマンド: 既存ノートへの Q&A・要約取得（`--summarize` フラグ対応）
- `notebook-source-adder` スキル: 自然言語トリガーによるソース追加フロー
- `notebook-query-assistant` スキル: 自然言語トリガーによる Q&A・要約フロー
- SessionStart hook: `nlm` CLI と `notebooklm-mcp` MCP の依存チェック
- `.mcp.json`: `notebooklm-mcp`（[jacob-bd/notebooklm-mcp-cli](https://github.com/jacob-bd/notebooklm-mcp-cli) 製）を同梱配布
