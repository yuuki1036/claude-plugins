# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-10

### Added

- `notebook-add-source` コマンド: URL / YouTube / Google Drive / PDF を NotebookLM ノートに追加
- `notebook-query` コマンド: 既存ノートへの Q&A・要約取得（`--summarize` フラグ対応）
- `notebook-source-adder` スキル: 自然言語トリガーによるソース追加フロー
- `notebook-query-assistant` スキル: 自然言語トリガーによる Q&A・要約フロー
- SessionStart hook: `nlm` CLI と `notebooklm-mcp` MCP の依存チェック
- `.mcp.json`: `notebooklm-mcp`（[jacob-bd/notebooklm-mcp-cli](https://github.com/jacob-bd/notebooklm-mcp-cli) 製）を同梱配布
