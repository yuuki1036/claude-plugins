# MCP Server推奨パターン

MCP（Model Context Protocol）サーバーは外部ツール・サービスへの接続でClaudeの機能を拡張する。

**注意**: 一般的なMCPサーバーのリスト。コードベース固有のサービス・統合に特化したMCPサーバーも検索すること。

## 接続方法と共有

1. **プロジェクト設定** (`.mcp.json`) - そのディレクトリでのみ有効
2. **ユーザー設定** (`~/.claude/mcp.json`) - 全プロジェクトで有効
3. **リポジトリ共有** (`.mcp.json` をgit管理) - チーム全体で利用（推奨）

## ドキュメント・知識

### context7
**対象**: 人気ライブラリ/SDKを使うプロジェクトで最新ドキュメントを参照したい場合

| 推奨シグナル | 例 |
|-------------|-----|
| React, Vue, Angular | フロントエンドフレームワーク |
| Express, FastAPI, Django | バックエンドフレームワーク |
| Prisma, Drizzle | ORM |
| Stripe, Twilio | サードパーティAPI |
| AWS SDK, Google Cloud | クラウドSDK |

## ブラウザ・フロントエンド

### Playwright MCP
**対象**: ブラウザ自動化、テスト、スクリーンショットが必要なフロントエンドプロジェクト

### Puppeteer MCP
**対象**: ヘッドレスブラウザ自動化、Webスクレイピング

## データベース

| 推奨シグナル | MCP Server |
|-------------|-----------|
| `@supabase/supabase-js` | Supabase MCP |
| PostgreSQL直接利用 | PostgreSQL MCP |
| Neon利用 | Neon MCP |
| Turso/libSQL | Turso MCP |

## バージョン管理・DevOps

| 推奨シグナル | MCP Server |
|-------------|-----------|
| GitHubリモート | GitHub MCP |
| GitLab利用 | GitLab MCP |
| Linear参照 | Linear MCP |

## クラウドインフラ

| 推奨シグナル | MCP Server |
|-------------|-----------|
| `@aws-sdk/*` | AWS MCP |
| Cloudflare Workers/Pages | Cloudflare MCP |
| Vercel利用 | Vercel MCP |

## モニタリング

| 推奨シグナル | MCP Server |
|-------------|-----------|
| `@sentry/*` | Sentry MCP |
| Datadog利用 | Datadog MCP |

## コミュニケーション

| 推奨シグナル | MCP Server |
|-------------|-----------|
| Slack利用 | Slack MCP |
| Notion利用 | Notion MCP |

## コンテナ・DevOps

| 推奨シグナル | MCP Server |
|-------------|-----------|
| docker-compose.yml | Docker MCP |
| K8sマニフェスト | Kubernetes MCP |

## クイックリファレンス

| 検出パターン | 推奨MCP |
|-------------|---------|
| 人気npmパッケージ | context7 |
| React/Vue/Next.js | Playwright MCP |
| `@supabase/supabase-js` | Supabase MCP |
| `pg` or `postgres` | PostgreSQL MCP |
| GitHubリモート | GitHub MCP |
| Linear参照 | Linear MCP |
| `@aws-sdk/*` | AWS MCP |
| `@sentry/*` | Sentry MCP |
| `docker-compose.yml` | Docker MCP |
| `@anthropic-ai/sdk` | context7 |
