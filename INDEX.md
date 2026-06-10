# claude-plugins INDEX

Claude Code プラグインのマーケットプレイスリポジトリ。各プラグインは独立して動作する（プラグイン間依存なし）。

- 生成日: 2026-06-10
- プラグイン数: 15
- マニフェスト: `.claude-plugin/marketplace.json`（各 `plugin.json` から派生・SSoT 検証あり）

> 詳細な運用規約・設計判断は [CLAUDE.md](CLAUDE.md) を参照。本ファイルは各プラグインのコンポーネント構成の早見表。

## プラグイン一覧

| プラグイン | version | cmd | skill | agent | hooks | mcp | 概要 |
|-----------|---------|----:|------:|-------|-------|-----|------|
| [adr-keeper](#adr-keeper) | 0.1.1 | 1 | 1 | - | - | - | 設計判断 (ADR) を append-only 蓄積 |
| [bdd-spec](#bdd-spec) | 0.1.1 | 1 | 1 | - | - | - | BDD spec 駆動の user story scaffold |
| [claude-meta](#claude-meta) | 1.11.0 | 2 | 5 | - | - | - | CC 設定管理・CLAUDE.md 監査・eval 回帰 |
| [code-review](#code-review) | 2.25.0 | 2 | 2 | - | SessionStart | - | Phase 0 トリアージ + 動的構成コードレビュー |
| [dev-workflow](#dev-workflow) | 1.21.0 | 3 | 5 | - | Pre/PostToolUse, SessionStart | ✓ | Git コミット・PR・UI 確認・worktree |
| [doc-freshness](#doc-freshness) | 0.1.0 | 1 | 1 | - | - | - | frontmatter による doc 鮮度機械強制 |
| [failure-journal](#failure-journal) | 0.1.0 | 2 | 2 | - | SessionStart | - | 再発失敗の fingerprint 集計・retro 還流 |
| [feature-dev](#feature-dev) | 2.6.0 | 1 | - | 2 | SessionStart | - | 8 phase 機能開発ワークフロー |
| [guardrail-protect](#guardrail-protect) | 0.1.0 | - | - | - | PreToolUse | - | 設定骨抜き・--no-verify を機械ブロック |
| [indie-workflow](#indie-workflow) | 1.29.0 | 10 | 10 | 2 | 5 events | - | 個人開発向けローカル Issue 管理 |
| [linear-workflow](#linear-workflow) | 1.28.1 | 10 | 10 | 3 | 4 events | - | Linear MCP 連携の Issue/プロジェクト管理 |
| [notebooklm-workflow](#notebooklm-workflow) | 0.2.3 | 2 | 2 | - | SessionStart | ✓ | NotebookLM 連携（ソース追加・Q&A） |
| [plugin-feedback](#plugin-feedback) | 1.2.6 | 1 | 1 | - | SessionStart | - | プラグイン改善要望を GitHub Issue 化 |
| [plugin-manager](#plugin-manager) | 1.7.0 | 1 | - | - | SessionStart | - | プラグイン一括更新・後発追加通知 |
| [writing-polish](#writing-polish) | 0.3.1 | 1 | 1 | - | - | - | 文章を語句レベルで推敲・添削 |

排他関係: `indie-workflow` と `linear-workflow` は同系統（ローカル / Linear）で排他利用想定。

---

## 各プラグイン詳細

### adr-keeper
設計判断 (ADR) を append-only で蓄積。YYYYMMDDhhmmss 秒精度命名 + 適用方法 (Enforcement) セクション必須。supersede 時は新規作成 + 旧 ADR 2 箇所更新を機械化。doc-freshness と frontmatter 互換。
- **commands**: `adr`
- **skills**: `adr`

### bdd-spec
BDD spec 駆動の scaffold。user story dir + epic.md（Why/What 散文）+ spec.md（Feature/Scenario/Examples + 同値分割表）を生成。
- **commands**: `bdd-spec-create`
- **skills**: `create-spec`

### claude-meta
Claude Code 自体の設定管理・改善ツール。CLAUDE.md 監査改善、CC アップデート追従、eval 回帰テスト、新コンポーネント追加前の退路確保判断。
- **commands**: `catch-up`, `revise-claude-md`
- **skills**: `cc-catch-up`, `claude-code-setup`, `claude-md-improver`, `component-addition-advisor`, `eval-runner`

### code-review
Phase 0 トリアージ + 動的エージェント構成のコードレビュー。confidence × severity 2 軸スコアリング、red-flag specialist 自動起動、high severity 検出時の meta-reviewer ラウンド。事実主張のツール接地 (claim grounding) と over-correction ガード（issue #71）。self-review は `--embed` で他プラグインから委譲可能。
- **commands**: `review`, `self-review`
- **skills**: `review`, `self-review`
- **hooks**: SessionStart
- **publishes**: `review:completed`（Event Bus）

### dev-workflow
Git 操作・PR 作成・UI 動作確認・git worktree 並列環境セットアップ。原子性重視コミット、Linear Issue 連携 PR、chrome-devtools MCP による UI 自動化、PostToolUse 自動 lint チェーン（opt-in）。
- **commands**: `commit`, `pr`, `ui-verify`
- **skills**: `git-commit-helper`, `pr-creator`, `ui-verify`, `worktree-setup`, `worktree-teardown`
- **hooks**: PreToolUse, PostToolUse, SessionStart
- **mcp**: chrome-devtools（同梱）
- **publishes**: `commit:created`（Event Bus）

### doc-freshness
ドキュメント鮮度の機械強制。last-validated / phase frontmatter による stale 検出、行数ガード、internal link 検証、新規 doc grace period。
- **commands**: `doc-freshness-check`
- **skills**: `doc-freshness`

### failure-journal
再発する失敗を JSON Lines に append し、30 日 × 3 回閾値超のパターンを retro で抽出して AGENTS.md/hook/skill へ還流。
- **commands**: `log-failure`, `retro`
- **skills**: `log-failure`, `retro`
- **hooks**: SessionStart
- **publishes**: `failure:logged`（Event Bus）

### feature-dev
コードベース理解・アーキテクチャ設計・runtime smoke test・品質レビューを 8 phase で進める機能開発ワークフロー。Phase 1.3 で bdd-spec から spec.md 生成、Phase 6 は code-review:self-review に `--embed` 委譲。
- **commands**: `feature-dev`
- **agents**: `code-explorer`, `code-architect`
- **hooks**: SessionStart
- **publishes**: `feature:implemented`（Event Bus）
- **依存**: code-review（Phase 6、未インストール時 fail-fast）

### guardrail-protect
lint/hook/static check 設定の骨抜き編集と `git commit --no-verify` を PreToolUse hook で機械ブロック（opt-in 設定）。
- **hooks**: PreToolUse

### indie-workflow
個人開発向けローカル Issue 管理。放置検知、スコープ管理、技術的負債トラッキング、振り返りまで一貫サポート。knowledge は source/concept 2 層 + wikilink + lint。issue-design で 9 セクション設計 + grill。
- **commands / skills**（同名ペア 10）: `indie-init`, `indie-start`, `indie-issue-create`, `indie-issue-maintain`, `indie-maintain`, `indie-follow-up`, `issue-design`, `knowledge`, `knowledge-lint`, `retrospective`
- **agents**: `code-context`, `doc-resolver`
- **hooks**: SessionStart, PostCompact, UserPromptSubmit, FileChanged, PostToolUse
- **subscribes**: `issue:completed`（retrospective）

### linear-workflow
Linear MCP 連携のプロジェクト・Issue 管理。セッション開始から Issue 作成・メンテ・Linear 同期まで一貫管理。
- **commands / skills**（同名ペア 10）: `init`, `session-start`, `issue-create`, `issue-maintain`, `issue-design`, `linear-maintain`, `follow-up`, `dashboard`, `knowledge`, `knowledge-lint`
- **agents**: `code-context`, `doc-resolver`, `linear-sync`
- **hooks**: SessionStart, PostCompact, UserPromptSubmit, FileChanged
- **publishes**: `issue:completed`（Event Bus）

### notebooklm-workflow
NotebookLM 連携。URL/PDF/YouTube/Drive のソース追加と既存ノートへの Q&A・要約を自然言語で操作。
- **commands**: `notebook-add-source`, `notebook-query`
- **skills**: `notebook-source-adder`, `notebook-query-assistant`
- **hooks**: SessionStart
- **mcp**: jacob-bd/notebooklm-mcp-cli（.mcp.json 同梱）

### plugin-feedback
プラグインへの改善要望・バグ報告を GitHub Issue として作成。コマンドと自然言語の両方で起動。
- **commands**: `feedback`
- **skills**: `feedback-issue`
- **hooks**: SessionStart

### plugin-manager
インストール済みプラグインの一括更新と、マーケットプレイスの後発追加プラグイン取りこぼし通知。
- **commands**: `update-all`
- **hooks**: SessionStart

### writing-polish
文章を語句レベルで推敲・添削する汎用スキル。最小差分 diff → 採否フロー。校正ルールは textlint（preset-ja-technical-writing/japanese/ai-writing/JTF-style）と Vale 由来のカテゴリを tone-guide 正本に内蔵、日英両対応。over-correction 抑制を中核原則に。
- **commands**: `writing-polish`
- **skills**: `writing-polish`
- **soft 連携**: pr-creator / git-commit-helper / issue-design が `--embed` で dormant 委譲

---

## 共通基盤

| 要素 | 配置 | 役割 |
|------|------|------|
| marketplace マニフェスト | `.claude-plugin/marketplace.json` | plugin.json から派生（SSoT 検証） |
| hook 共通ラッパー（正本） | `.claude-plugin/lib/safe-hook.sh` | 各プラグインへ byte-identical 複製 |
| JSON Schema | `.claude-plugin/schema/` | plugin.json / marketplace.json / hooks.json |
| SSoT 検証 | `.claude-plugin/scripts/validate-ssot.sh`, `validate_ssot.py` | バージョン・description・_requirements 同期 |
| 自動品質チェック | `.claude-plugin/scripts/auto-quality-check.sh` | Stop hook で非ブロッキング通知 |
| pre-commit | `.githooks/pre-commit` | バージョンバンプ・CHANGELOG・SSoT 同期 |
| eval 回帰テスト | `evals/`（runner.py / cases / reports） | トリガーフレーズ → スキル起動を pass^k=3 で検証 |

### Event Bus（`.claude/events.jsonl`）

`safe-hook.sh` の `event_bus_publish` / `event_bus_tail` で Pub/Sub。命名は `<domain>:<verb-past>`。

| イベント | publisher | 主な subscriber |
|---|---|---|
| `issue:completed` | linear-workflow / indie-workflow | indie-workflow:retrospective |
| `feature:implemented` | feature-dev | - |
| `commit:created` | dev-workflow | - |
| `review:completed` | code-review | - |
| `failure:logged` | failure-journal | - |

### Shared State（frontmatter で producer/consumer 明示）

| type | 配置 | producer |
|---|---|---|
| `session` | `.claude/session-context.md` | linear / indie-workflow |
| `follow-up` | `.claude/{linear\|indie}/{slug}/follow-ups/*.md` | linear / indie-workflow |
| `knowledge` | `.claude/{linear\|indie}/{slug}/knowledge/**/*.md` | linear / indie-workflow |
