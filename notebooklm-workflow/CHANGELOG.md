# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
