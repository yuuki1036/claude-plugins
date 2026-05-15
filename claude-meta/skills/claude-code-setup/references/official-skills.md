# Claude Code 公式 Skill インベントリ

Anthropic / Vercel 公式が同梱・配布している skill のレコメンド用カタログ。プロジェクト特性からマッチする skill を提案するときに参照する。

## 取得元

| 配布元 | 実体パス | 提供方法 |
|---|---|---|
| ユーザーレベル同梱（Vercel/Anthropic） | `~/.agents/skills/` | デフォルトで利用可 |
| Anthropic Agent Skills marketplace | `~/.claude/plugins/marketplaces/anthropic-agent-skills/skills/` | `/plugin install` で有効化 |
| Claude Code ハーネス組み込み | （SKILL.md 実体なし、CLI 内部） | デフォルトで利用可 |

## カテゴリ: フロントエンド / UI

| skill | 検出シグナル | 推奨用途 |
|---|---|---|
| `frontend-design` | React / Vue / Next.js / 「UI 作って」「ランディングページ」 | 本格的フロントエンドの新規構築。AI 臭を避けたデザイン |
| `web-design-guidelines` | UI 変更 / アクセシビリティ言及 | レビュー時のガイドライン照合（Vercel labs リポジトリから最新版を fetch） |
| `vercel-react-best-practices` | `react` / `next` 依存検出 | 57 ルールの最適化チェックリスト（Server Component, Suspense, バンドル等） |
| `web-artifacts-builder` | React + Tailwind + shadcn/ui を使った複合 artifact が必要 | Vite/Parcel ベースの artifact ビルドスクリプト同梱 |

## カテゴリ: ブラウザ自動化 / テスト

| skill | 検出シグナル | 推奨用途 |
|---|---|---|
| `chrome-devtools` | `playwright` 未導入 / 単発の DOM 検証で十分 | Puppeteer CLI、スクリーンショット、network/console 監視 |
| `webapp-testing` | `playwright` / `@playwright/test` / E2E 必要 | Playwright 同期 API、`with_server.py` でローカルサーバ起動込み |

## カテゴリ: ドキュメント検索 / ライブラリ

| skill | 検出シグナル | 推奨用途 |
|---|---|---|
| `context7` | 主要 OSS ライブラリの API を叩くコードがある | ライブラリの最新ドキュメント取得（モデル cutoff 越え対策） |

## カテゴリ: ドキュメント / オフィス系

| skill | 検出シグナル | 推奨用途 |
|---|---|---|
| `pdf` | `.pdf` ファイル操作 | 抽出 / 結合 / 分割 / OCR / フォーム |
| `docx` | Word 文書生成 / 変更追跡 | docx-js、XML パターン |
| `xlsx` | `.xlsx`/`.csv` 操作 / 財務モデル | openpyxl + pandas + recalc |
| `pptx` | プレゼン生成 | markitdown / pptxgenjs ベース |
| `doc-coauthoring` | 提案書・仕様書・意思決定文書の段階的執筆 | Context Gathering → Refinement → Reader Testing |

## カテゴリ: 開発者ツール / Claude 系

| skill | 検出シグナル | 推奨用途 |
|---|---|---|
| `claude-api` | `anthropic` / `@anthropic-ai/sdk` 依存 | Claude API / Agent SDK 統合、prompt caching、tool use |
| `mcp-builder` | MCP サーバー自作 | Python (FastMCP) / TypeScript SDK の実装ガイド |
| `skill-creator` | skill 単体の新規作成・改善 | Draft → Test → Evaluate のループ |
| `seo-audit` | 公開 Web サイト / マーケ系 | テクニカル SEO 監査 |

## カテゴリ: アート / ブランド

| skill | 検出シグナル | 推奨用途 |
|---|---|---|
| `canvas-design` | 静止画ポスター / アート | デザイン哲学 → PDF/PNG |
| `algorithmic-art` | ジェネラティブアート / p5.js | シード管理、パラメータ操作 |
| `slack-gif-creator` | Slack 用 GIF | PIL ベース、寸法・色数最適化 |
| `theme-factory` | artifact のテーマ適用 | 10 プリセット + カスタム |
| `brand-guidelines` | Anthropic ブランド資産 | カラー / フォント / ロゴ規定 |
| `internal-comms` | 社内アップデート文書 | 3P updates / FAQ / ニュースレター |

## カテゴリ: Claude Code ハーネス組み込み（SKILL.md 実体なし）

| skill | 推奨用途 |
|---|---|
| `update-config` | settings.json 編集 / hooks 配置 / 権限ルール / env 変数 |
| `keybindings-help` | `~/.claude/keybindings.json` カスタマイズ |
| `simplify` | 変更コードの簡素化 / 不要分削除 |
| `fewer-permission-prompts` | 自分の transcript から allowlist 生成し権限プロンプト削減 |
| `loop` | スラッシュコマンドを定期実行（cron 相当） |
| `init` | CLAUDE.md 初期生成 |
| `review` | PR レビュー（ハーネス組み込み） |
| `security-review` | 現在ブランチの差分を対象としたセキュリティ監査 |
| `claude-api` | （marketplace の `claude-api` と内容が重複、本質は同じ） |

## レコメンド意思決定フロー

```
コードベース解析
  │
  ├─ React/Next.js?
  │   ├─ Yes → vercel-react-best-practices（必須）
  │   │       + frontend-design（新規UI開発時）
  │   │       + web-design-guidelines（レビュー時）
  │   │       + webapp-testing（E2E が要る時）
  │   └─ No
  │
  ├─ 公開Webサイト/マーケ系?
  │   └─ Yes → seo-audit
  │
  ├─ Anthropic SDK 利用?
  │   └─ Yes → claude-api
  │
  ├─ MCP サーバー自作?
  │   └─ Yes → mcp-builder
  │
  ├─ ライブラリ仕様確認が頻発?
  │   └─ Yes → context7
  │
  ├─ ブラウザ操作必要?
  │   ├─ E2E 込み → webapp-testing
  │   └─ 単発検証 → chrome-devtools
  │
  └─ ハーネス設定の最適化?
      ├─ 権限プロンプト多い → fewer-permission-prompts
      ├─ 設定見直し → update-config
      └─ キー操作カスタム → keybindings-help
```

## 既存内製プラグインとの関係

| 内製プラグイン | 連携先公式 skill | 連携方法 |
|---|---|---|
| `code-review` | `web-design-guidelines`, `vercel-react-best-practices`, `context7` | reviewer-prompts.md の Focus テンプレート内で参照 |
| `plugin-dev:skill-development` | `skill-creator` | プラグイン文脈で SKILL.md 構造を、汎用部分は公式へ委譲 |
| `plugin-dev:mcp-integration` | `mcp-builder` | プラグイン文脈で MCP 取込みを、サーバー実装は公式へ委譲 |
| `dev-workflow:ui-verify` | `chrome-devtools`, `webapp-testing` | smoke は ui-verify、E2E は webapp-testing |
| `feature-dev:code-architect` | `context7` | Phase 1 で外部ライブラリ採用判断時に必須参照 |
| `claude-meta:claude-code-setup` | （本カタログを参照する側） | Phase 1/2 で検出シグナル ↔ skill レコメンド |

## 更新ポリシー

- 公式 skill は Anthropic / Vercel が随時更新する。本ファイルは「検出シグナル ↔ skill 名」のマッピングを正本として持つ
- 実体パス（`~/.agents/skills/` 等）は環境依存なので、レコメンド時は skill 名のみを提示し、利用者が呼び出す
- 新しい公式 skill が追加されたら本ファイルに追記し、`claude-meta` の version を bump する
