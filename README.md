# claude-plugins

Claude Code 用プラグインの個人用マーケットプレイス。10 プラグインで Issue 管理から PR レビューまでをカバーする。Linear / 個人開発の両対応、Conventional Commits 準拠のコミット、Phase 0 トリアージ付きコードレビュー、chrome-devtools MCP による UI 動作確認、NotebookLM 連携など。

- 対象: Claude Code
- 言語: プラグイン本体・スキル説明・コマンドは日本語

## 目次

- [インストール](#インストール)
  - [A. Claude Code 標準（推奨）](#a-claude-code-標準推奨)
  - [B. ローカルディレクトリから](#b-ローカルディレクトリから)
  - [C. Microsoft APM 経由（lockfile・ガバナンス重視）](#c-microsoft-apm-経由lockfileガバナンス重視)
- [プラグイン一覧](#プラグイン一覧)
- [1 セッションの典型フロー](#1-セッションの典型フロー)
- [各プラグインの入口](#各プラグインの入口)
- [更新](#更新)

## インストール

普段使いは **A**、開発時は **B**、APM を使う場合は **C**。

### A. Claude Code 標準（推奨）

Claude Code 内のスラッシュコマンドでマーケットプレイスを登録してから個別プラグインをインストールする。

```text
/plugin marketplace add yuuki1036/claude-plugins
/plugin install linear-workflow@yuuki1036-claude-plugins
/plugin install dev-workflow@yuuki1036-claude-plugins
/plugin install code-review@yuuki1036-claude-plugins
```

CLI から直接叩く場合:

```bash
claude plugin marketplace add yuuki1036/claude-plugins
claude plugin install linear-workflow@yuuki1036-claude-plugins
```

- マーケットプレイス名（`@` の後ろ）は `yuuki1036-claude-plugins` で固定
- インストール済みプラグインの確認は `/plugin list`
- アンインストールは `/plugin uninstall <name>@yuuki1036-claude-plugins`

### B. ローカルディレクトリから

リポジトリを clone し、ディレクトリを直接指定する。プラグイン自体に手を入れながら使う / マーケットプレイスを介さずに試したい場合向け。

```bash
git clone git@github.com:yuuki1036/claude-plugins.git
cd claude-plugins

# Claude Code CLI から個別にインストール
claude plugin install ./linear-workflow
claude plugin install ./dev-workflow
```

`.claude-plugin/plugin.json` を更新したら手動で再インストールが必要。

<details>
<summary><b>C. Microsoft APM 経由（lockfile・ガバナンス重視）</b></summary>

[Microsoft APM (Agent Package Manager)](https://github.com/microsoft/apm) は AI エージェント向けの汎用パッケージマネージャ。このリポジトリは Claude Code 標準形式の `marketplace.json` をそのまま公開しているので、APM から **書き換えなし** で利用できる。

得られるもの:
- `apm.lock.yaml` による厳密なバージョン固定（チーム内で同一構成を保証）
- ref-swap 攻撃検知（過去にインストールしたバージョンの参照先が書き換わっていないか自動検査）
- 同名プラグイン衝突（shadow plugin）警告
- GitHub Copilot / Cursor / Codex / Gemini 等と同じマニフェストで Claude Code 用プラグインも管理できる

```bash
# APM 本体をインストール（macOS / Linux / Windows x86_64 にバイナリ配布）
# 詳細: https://microsoft.github.io/apm/quickstart/

# マーケットプレイス登録
apm marketplace add github.com/yuuki1036/claude-plugins

# 個別プラグインのインストール
apm install linear-workflow@yuuki1036-claude-plugins
apm install dev-workflow@yuuki1036-claude-plugins
```

`apm.yml` で宣言的に管理する場合の最小例:

```yaml
plugins:
  - linear-workflow@yuuki1036-claude-plugins
  - dev-workflow@yuuki1036-claude-plugins
  - code-review@yuuki1036-claude-plugins
```

その後 `apm install` で `apm.lock.yaml` が生成され、`.claude/` 配下に展開される。

</details>

## プラグイン一覧

カテゴリ別に整理。詳細は各プラグインディレクトリの README / CHANGELOG を参照。

### Issue / プロジェクト管理（**排他**: どちらか一方を選ぶ）

| プラグイン | 用途 |
|---|---|
| [`linear-workflow`](./linear-workflow) | Linear MCP と連携した Issue / プロジェクト管理。ブランチから Issue 特定、ダッシュボード、knowledge 切り出し |
| [`indie-workflow`](./indie-workflow) | Linear を使わない個人開発向け。ローカル Markdown ファイルで Issue 管理 |

### 開発ワークフロー

| プラグイン | 用途 |
|---|---|
| [`dev-workflow`](./dev-workflow) | Git コミット（原子性重視・Conventional Commits）/ PR 作成 / chrome-devtools MCP による UI 動作確認 |
| [`code-review`](./code-review) | Phase 0 トリアージ + 動的エージェント構成のコードレビュー / セルフレビュー。Confidence ≥80 の指摘のみ報告 |
| [`feature-dev`](./feature-dev) | 8 phase の機能開発フロー（探索 → 設計 → 実装 → レビュー → runtime smoke test まで） |

### メタ / プラグイン管理

| プラグイン | 用途 |
|---|---|
| [`claude-meta`](./claude-meta) | Claude Code 設定管理・CLAUDE.md 監査改善・CC アップデート追従・eval 回帰テスト |
| [`plugin-manager`](./plugin-manager) | インストール済みプラグインを一括更新 |
| [`plugin-feedback`](./plugin-feedback) | プラグインへの改善要望・バグ報告を GitHub Issue 化 |

### 学習 / メモリ

| プラグイン | 用途 |
|---|---|
| [`instinct-memory`](./instinct-memory) | セッション中の訂正・好みパターンを instinct として記録、確信度の高いものを auto memory に昇格 |

### 外部サービス連携

| プラグイン | 用途 |
|---|---|
| [`notebooklm-workflow`](./notebooklm-workflow) | NotebookLM への URL/PDF/YouTube/Drive ソース追加と Q&A。`notebooklm-mcp-cli` を `.mcp.json` で同梱 |

## 1 セッションの典型フロー

Linear で管理している Issue を 1 つ実装するときのコマンド遷移例。

```text
/session-start    # ブランチから Issue 特定、関連ファイル読み込み (linear-workflow)
/feature-dev      # 探索 → 設計 → 実装の 8 phase ワークフロー (feature-dev)
/self-review      # コミット前に Phase 0 トリアージ付きでセルフレビュー (code-review)
/commit           # Conventional Commits 準拠の原子性コミット (dev-workflow)
/pr               # 差分とコミット履歴から PR description 自動生成 (dev-workflow)
```

個人開発（Linear なし）は `linear-workflow` の代わりに `indie-workflow` を使う。`/indie-start` → `/indie-issue-create` → 以下同様。

## 各プラグインの入口

インストール後にまず叩くコマンド / 呼ぶスキル。

| プラグイン | はじめの一歩 |
|---|---|
| `linear-workflow` | `/init` でプロジェクトセットアップ → `/session-start` で作業開始 |
| `indie-workflow` | `/indie-init` で初期化 → `/indie-start` でダッシュボード表示 |
| `dev-workflow` | `/commit` でコミット / `/pr` で PR 作成 / `/ui-verify` で UI 確認 |
| `code-review` | `/self-review` でコミット前チェック / `/review` で PR レビュー |
| `feature-dev` | `/feature-dev` でガイド付き機能開発開始 |
| `claude-meta` | `/catch-up` で CC 最新機能を確認 / 「CLAUDE.md 監査」で品質チェック |
| `plugin-manager` | `/update-all` で全プラグイン一括更新 |
| `plugin-feedback` | `/feedback` で改善要望を GitHub Issue 化 |
| `instinct-memory` | 自動で動く（セッション開始時 / Stop / PostCompact）。手動で `/learn`、`/instinct-status`、`/instinct-promote` |
| `notebooklm-workflow` | `/notebook-add-source <url>` でソース追加 / `/notebook-query <question>` で質問。`nlm login` で事前認証 |

> linear-workflow と indie-workflow は **同時に有効化しない**。両方有効だとスキル選択が衝突する。

## 更新

- **A / B でインストールした場合**: `/plugin update <name>@yuuki1036-claude-plugins`、または `plugin-manager` プラグイン経由で `/update-all`
- **C (APM) でインストールした場合**: `apm update`（`apm.lock.yaml` 経由でバージョン解決）

各プラグインは Semantic Versioning に従う:
- MAJOR: 破壊的変更（スキル / コマンドの削除・リネーム）
- MINOR: 機能追加（新スキル / コマンド、既存機能拡張）
- PATCH: 修正（バグ修正、ドキュメント、リファクタ）

変更履歴は各プラグインの `CHANGELOG.md` を参照。
