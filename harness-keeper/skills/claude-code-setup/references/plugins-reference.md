# Plugin推奨パターン

プラグインはskills, commands, agents, hooksのインストール可能なコレクション。
`/plugin install` でインストール。

## 公式 Anthropic Agent Skills marketplace

`~/.claude/plugins/marketplaces/anthropic-agent-skills/` にバンドルされた公式 marketplace。skills 一覧は [official-skills.md](official-skills.md) を参照。

主要な公式プラグイン:

| プラグイン / marketplace | 用途 |
|---|---|
| anthropic-agent-skills | PDF/Word/Excel/PPTX、claude-api、mcp-builder、webapp-testing、frontend-design 等 22 skill 集約 |
| plugin-dev | プラグイン開発（コマンド/スキル/エージェント/hook/MCP 統合の足場） |
| code-review | 自動コードレビュー |
| feature-dev | 機能開発ワークフロー |

## サードパーティ / 言語サーバー (LSP)

| プラグイン | 言語 |
|---|---|
| typescript-lsp | TypeScript/JavaScript |
| pyright-lsp | Python |
| gopls-lsp | Go |
| rust-analyzer-lsp | Rust |
| clangd-lsp | C/C++ |
| jdtls-lsp | Java |

## クイックリファレンス

| コードベースシグナル | 推奨プラグイン / skill |
|---|---|
| プラグイン開発 | plugin-dev |
| PR レビュー | code-review |
| 機能開発フロー | feature-dev |
| React/Vue/Angular | anthropic-agent-skills の frontend-design / web-design-guidelines |
| オフィス文書処理 | anthropic-agent-skills の pdf/docx/xlsx/pptx |
| Anthropic SDK 開発 | anthropic-agent-skills の claude-api |
| MCP サーバー実装 | anthropic-agent-skills の mcp-builder |
| TypeScript | typescript-lsp |
| Python | pyright-lsp |

詳細な skill ↔ シグナル マッピングは [official-skills.md](official-skills.md) を参照。
