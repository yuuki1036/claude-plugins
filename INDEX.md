# claude-plugins INDEX

Claude Code プラグインのマーケットプレイスリポジトリ。各プラグインは独立して動作する（プラグイン間依存なし）。

- 生成日: 2026-06-25
- プラグイン数: 19
- マニフェスト: `.claude-plugin/marketplace.json`（各 `plugin.json` から派生・SSoT 検証あり）

> 詳細な運用規約・設計判断は [CLAUDE.md](CLAUDE.md) を参照。本ファイルは各プラグインのコンポーネント構成の早見表。

## プラグイン一覧

| プラグイン | version | cmd | skill | agent | hooks | mcp | 概要 |
|-----------|---------|----:|------:|-------|-------|-----|------|
| [adr-keeper](#adr-keeper) | 0.2.2 | 1 | 1 | - | - | - | 設計判断 (ADR) を append-only 蓄積 |
| [bdd-spec](#bdd-spec) | 0.3.1 | 2 | 2 | - | - | - | BDD spec 駆動の scaffold + 5 観点評価 |
| [claude-meta](#claude-meta) | 1.13.0 | 2 | 5 | - | - | - | CC 設定管理・CLAUDE.md 監査・eval 回帰 |
| [code-review](#code-review) | 2.38.0 | 2 | 2 | - | SessionStart | - | Phase 0 トリアージ + 動的構成コードレビュー |
| [design-doc](#design-doc) | 0.4.3 | 2 | 2 | 1 | - | - | 技術設計書を実装に入らず作成・永続化 + 4視点レビュー |
| [dev-workflow](#dev-workflow) | 1.24.0 | 3 | 5 | - | Pre/PostToolUse, SessionStart | ✓ | Git コミット・PR・UI 確認・worktree |
| [doc-freshness](#doc-freshness) | 0.5.0 | 1 | 1 | - | PostToolUse, SessionStart | - | frontmatter による doc 鮮度機械強制 |
| [failure-journal](#failure-journal) | 0.3.1 | 2 | 2 | - | SessionStart, PostCompact | - | 再発失敗の fingerprint 集計・retro 還流 |
| [feature-dev](#feature-dev) | 2.11.3 | 1 | - | 2 | SessionStart | - | 8 phase 機能開発ワークフロー |
| [guardrail-protect](#guardrail-protect) | 0.2.1 | - | - | - | PreToolUse | - | 設定骨抜き・--no-verify を機械ブロック |
| [indie-workflow](#indie-workflow) | 1.40.7 | 11 | 11 | 3 | 5 events | - | **deprecated** → issue-workflow へ移行 |
| [issue-workflow](#issue-workflow) | 1.3.0 | 13 | 13 | 4 | 5 events | - | Issue 管理（linear/indie 統合後継・backend 自動判定） |
| [linear-workflow](#linear-workflow) | 1.37.6 | 10 | 10 | 3 | 4 events | - | **deprecated** → issue-workflow へ移行 |
| [living-spec-workflow](#living-spec-workflow) | 0.3.1 | 2 | 2 | - | - | - | Issue 化前の設計収束ドキュメントを append-only 運用 |
| [notebooklm-workflow](#notebooklm-workflow) | 0.2.7 | 2 | 2 | - | SessionStart | ✓ | NotebookLM 連携（ソース追加・Q&A） |
| [plugin-feedback](#plugin-feedback) | 1.2.9 | 1 | 1 | - | SessionStart | - | プラグイン改善要望を GitHub Issue 化 |
| [plugin-manager](#plugin-manager) | 1.8.1 | 1 | - | - | SessionStart | - | プラグイン一括更新・deprecated 自動移行・後発追加通知 |
| [spec-advisor](#spec-advisor) | 0.1.4 | 1 | 1 | - | SessionStart | - | 開発タスクから設計・計画系 spec をルーティング提案 |
| [writing-polish](#writing-polish) | 0.8.1 | 1 | 1 | - | - | - | 文章を語句レベルで推敲・添削 |

排他関係: `indie-workflow` / `linear-workflow` は **deprecated**（後継 = `issue-workflow`）。issue-workflow と旧 2 プラグインの同一マシン併存は禁止（uninstall → install を連続実行。移行チェックリスト: `docs/issue-workflow-migration.md`）。

---

## 各プラグイン詳細

### adr-keeper
設計判断 (ADR) を append-only で蓄積。YYYYMMDDhhmmss 秒精度命名 + 適用方法 (Enforcement) セクション必須。supersede 時は新規作成 + 旧 ADR 4フィールド更新（status/phase/superseded-by/last-validated）を機械化。append_only frontmatter で doc-freshness の stale 判定を免除。
- **commands**: `adr`
- **skills**: `adr`

### bdd-spec
BDD spec 駆動の scaffold + 評価。create で user story dir + epic.md（Why/What 散文）+ spec.md（Feature/Scenario/Examples + 同値分割表 + 状態遷移表（stateful のみ・任意））を生成、evaluate で構文/粒度/網羅性（同値分割表⇔Scenario 双方向トレース）/トレーサビリティ/遷移カバレッジ（状態遷移表⇔Scenario、stateful のみ dormant）の 5 観点を severity×confidence で静的レビュー。
- **commands**: `bdd-spec-create`, `bdd-spec-evaluate`
- **skills**: `create-spec`, `evaluate-spec`

### claude-meta
Claude Code 自体の設定管理・改善ツール。CLAUDE.md 監査改善、CC アップデート追従、eval 回帰テスト、新コンポーネント追加前の退路確保判断。
- **commands**: `catch-up`, `revise-claude-md`
- **skills**: `cc-catch-up`, `claude-code-setup`, `claude-md-improver`, `component-addition-advisor`, `eval-runner`

### code-review
Phase 0 トリアージ + 動的エージェント構成のコードレビュー。confidence × severity 2 軸スコアリング、red-flag specialist 自動起動、high severity 検出時の meta-reviewer ラウンド、冷や読み skeptic（Phase 5.8/4.8: high-risk surface で findings 非注入の独立 opus が fleet 共通盲点を破る recall 補強）、反証レイヤー（Phase 5.9/4.9: 指摘を独立エージェントが反証、高 severity は消さず係争注記、specialist 除外）、high-risk surface に限る surface-aware 報告閾値。事実主張のツール接地 (claim grounding) と over-correction ガード（issue #71）。self-review は `--embed` で他プラグインから委譲可能。
- **commands**: `review`, `self-review`
- **skills**: `review`, `self-review`
- **hooks**: SessionStart
- **publishes**: `review:completed`（Event Bus）

### design-doc
技術設計書 (design doc) を実装に入らず作成・永続化。grill で前提確定 → 代替案トレードオフ比較 → 採用案を `.claude/designs/<YYYYMMDD>-<slug>.md` に保存。実装ブリッジ必須化 + supersede 機械化で死に文書化を防ぐ。doc-freshness と frontmatter 互換。export 非対話 API で他プラグインから doc 化可能。design-review で minimal/clean/pragmatic/risk 4 視点の静的レビュー（effort 別に agent 数をトリアージ、evidence-first）。
- **commands**: `design-doc`, `design-review`
- **skills**: `design-doc`, `design-review`
- **agents**: `design-reviewer`
- **soft 連携**: bdd-spec（WHAT 入力）/ adr-keeper（[→ADR候補] 切り出し）/ writing-polish（散文推敲）が dormant

### dev-workflow
Git 操作・PR 作成・UI 動作確認・git worktree 並列環境セットアップ。原子性重視コミット、Linear Issue 連携 PR、chrome-devtools MCP による UI 自動化、PostToolUse 自動 lint チェーン（opt-in）。
- **commands**: `commit`, `pr`, `ui-verify`
- **skills**: `git-commit-helper`, `pr-creator`, `ui-verify`, `worktree-setup`, `worktree-teardown`
- **hooks**: PreToolUse, PostToolUse, SessionStart
- **mcp**: chrome-devtools（同梱）
- **publishes**: `commit:created`（Event Bus）

### doc-freshness
ドキュメント鮮度の機械強制。last-validated / phase frontmatter による stale 検出、行数ガード、internal link 検証、新規 doc grace period。手動走査（skill）に加え、PostToolUse hook で frontmatter 必須の project doc（.claude/designs・.claude/adr）への frontmatter 欠落を非ブロッキング検知、SessionStart hook（opt-in）で stale を一括通知。
- **commands**: `doc-freshness-check`
- **skills**: `doc-freshness`
- **hooks**: PostToolUse（frontmatter-guard）, SessionStart（stale-check, opt-in）

### failure-journal
再発する失敗を JSON Lines に append し、30 日 × 3 回閾値超のパターンを retro で抽出して AGENTS.md/hook/skill へ還流。SessionStart hook が自己申告ルールを注入し、Claude が自己訂正した瞬間に candidates.jsonl へ候補を 1 行 append → retro が承認レビューで journal に昇格（verdict 書き戻しで却下候補の再浮上を防止）。候補が無い期間は transcript サルベージにフォールバック（実測値と測定条件は `skills/retro/references/transcript-salvage.md`）。
- **commands**: `log-failure`, `retro`
- **skills**: `log-failure`, `retro`
- **hooks**: SessionStart, PostCompact（自己申告ルール再注入）
- **publishes**: `failure:logged`（Event Bus）

### feature-dev
コードベース理解・アーキテクチャ設計・runtime smoke test・品質レビューを 8 phase で進める機能開発ワークフロー。Phase 1.3 で bdd-spec から spec.md 生成、Phase 1.4 で bdd-spec:evaluate-spec に品質ゲート委譲（dormant）、Phase 4.5 で採用設計を design-doc に export（dormant）、Phase 6 は code-review:self-review に `--embed` 委譲。
- **commands**: `feature-dev`
- **agents**: `code-explorer`, `code-architect`
- **hooks**: SessionStart
- **publishes**: `feature:implemented`（Event Bus）
- **依存**: code-review（Phase 6、未インストール時 fail-fast）

### guardrail-protect
`git commit` の hook 迂回（`--no-verify`/`-n`・git 省略形・`-c core.hooksPath` 上書き・変数間接・`sh -c` スクリプト内）を常時ブロック + lint/hook/static check 設定ファイルの骨抜き編集を opt-in でブロック。config 自己保護・fail-loud（jq/perl 不在時に無言で無効化しない）付き。
- **hooks**: PreToolUse

### indie-workflow
**deprecated**（後継 = issue-workflow。移行手順は `docs/issue-workflow-migration.md`）。個人開発向けローカル Issue 管理。放置検知、スコープ管理、技術的負債トラッキング、振り返りまで一貫サポート。knowledge は source/concept 2 層 + wikilink + lint。issue-design で 9 セクション設計 + grill。
- **commands / skills**（同名ペア 11）: `indie-init`, `indie-start`, `indie-issue-create`, `indie-issue-discover`, `indie-issue-maintain`, `indie-maintain`, `indie-follow-up`, `issue-design`, `knowledge`, `knowledge-lint`, `retrospective`
- **agents**: `code-context`, `doc-resolver`, `discover-verifier`
- **hooks**: SessionStart, PostCompact, UserPromptSubmit, FileChanged, PostToolUse
- **publishes**: `issue:completed`（Event Bus）
- **subscribes**: `issue:completed`（retrospective）

### issue-workflow
Issue 管理ワークフロー（linear-workflow / indie-workflow の統合後継）。backend（local: `.claude/indie/` / linear: `.claude/linear/`）をデータディレクトリの存在で自動判定し、単一のスキル群で両方を扱う。旧 indie 専用機能（discover / retrospective / scope_size）は両 backend に開放。
- **commands / skills**（同名ペア 13）: `init`, `start`, `issue-create`, `issue-design`, `issue-maintain`, `follow-up`, `knowledge`, `knowledge-lint`, `maintain`, `discover`, `retrospective`, `dashboard`（linear 専用）, `linear-maintain`（linear 専用）
- **agents**: `code-context`, `doc-resolver`, `discover-verifier`, `linear-sync`（linear 専用）
- **hooks**: SessionStart, PostCompact, UserPromptSubmit, FileChanged, PostToolUse
- **publishes**: `issue:completed`（Event Bus）
- **subscribes**: `issue:completed`（retrospective）
- **移行**: 旧 2 プラグインとの同一マシン併存は禁止（uninstall → install を連続実行）

### linear-workflow
**deprecated**（後継 = issue-workflow。移行手順は `docs/issue-workflow-migration.md`）。Linear MCP 連携のプロジェクト・Issue 管理。セッション開始から Issue 作成・メンテ・Linear 同期まで一貫管理。
- **commands / skills**（同名ペア 10）: `init`, `session-start`, `issue-create`, `issue-maintain`, `issue-design`, `linear-maintain`, `follow-up`, `dashboard`, `knowledge`, `knowledge-lint`
- **agents**: `code-context`, `doc-resolver`, `linear-sync`
- **hooks**: SessionStart, PostCompact, UserPromptSubmit, FileChanged
- **publishes**: `issue:completed`（Event Bus）

### living-spec-workflow
Issue 化前の設計収束ドキュメント (living spec) を `.claude/living-specs/` にフラット配置で運用。OQ 台帳と Decision log を両方 append-only の表として持ち、情報の move を設計から除いて消失を構造的に防ぐ。確度ラベル（確定 / 方向性(仮) / 未定）と since 日付でセクション粒度の収束を追跡。
- **commands / skills**（同名ペア 2）: `living-spec`（サブコマンド: `init` / `oq` / `oq list` / `decision` / `spec` / `status`）, `living-spec-maintain`（整合・鮮度の 8 段検証。`--spec` / `--all`）
- **references**: `living-spec/format-spec.md`（対象ファイル特定・表スキーマ・確度ラベル・採番規約・パース正規表現の正本）, `living-spec/template.md`, `living-spec-maintain/check-rules.md`（段 1-8 の判定内容・severity・修正方針の正本）
- **dormant 連携**: `doc-freshness` 0.4.0+（ファイル単位の鮮度 lint を委譲。未導入時は縮退 warning を出して動作）
- **設計の核心**: 採番は HTML コメント除去後の数値 max+1。`decision` が双方向参照（OQ の `関連 D#` ↔ Decision の `関連 OQ`）を 1 コマンドで書き、直後に Read で検証して片方向ならその場で直す。maintain は段 1-7 の機械判定を先頭に置き段 8 の LLM 判断は通過分にだけ当てる（`${CLAUDE_EFFORT}` 分岐）

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

### spec-advisor
開発タスクの内容から、実装着手前に書くべき設計・計画系成果物（WHAT=bdd-spec / HOW=design-doc / WHY=adr-keeper / Issue粒度=issue-design / 実装一気通貫=feature-dev）を判断して提案。判定の SSoT を `routing-rubric.md` に一元化。over-suggestion guard を先頭に置くファネルで bugfix/typo/設定変更には黙り、確信度が高い時だけ 1 文根拠で提案・迷う時のみ AskUserQuestion。dormant 判定で未導入プラグインは提案肢から除外、全て未導入なら沈黙。
- **commands**: `spec-advise`
- **skills**: `spec-advise`
- **hooks**: SessionStart（inject-advisor-rule、ambient ルール注入・対象プラグイン未導入時 inert）
- **dormant 連携**: bdd-spec / design-doc / adr-keeper / feature-dev / issue-design（linear・indie）— すべて optional

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
| spec ルーティング 3 軸コア（正本） | `.claude-plugin/lib/routing-axes.md` | ROUTING-AXES 区間を spec-advisor / linear / indie に複製（dedent 比較で同期検証） |
| JSON Schema | `.claude-plugin/schema/` | plugin.json / marketplace.json / hooks.json |
| SSoT 検証 | `.claude-plugin/scripts/validate-ssot.sh`, `validate_ssot.py` | バージョン・description・_requirements 同期 |
| 自動品質チェック | `.claude-plugin/scripts/auto-quality-check.sh` | Stop hook で非ブロッキング通知 |
| pre-commit | `.githooks/pre-commit` | バージョンバンプ・CHANGELOG・SSoT 同期・プラグイン品質 (errors)・indie/linear drift |
| eval 回帰テスト | `evals/`（runner.py / cases / reports） | トリガーフレーズ → スキル起動を pass^k=3 で検証 |

### Event Bus（`.claude/events.jsonl`）

`safe-hook.sh` の `event_bus_publish` / `event_bus_tail` で Pub/Sub。命名は `<domain>:<verb-past>`。

| イベント | publisher | 主な subscriber |
|---|---|---|
| `issue:completed` | issue-workflow（移行中は旧 linear/indie-workflow も） | issue-workflow:retrospective |
| `feature:implemented` | feature-dev | -（fire-and-forget） |
| `commit:created` | dev-workflow | issue-workflow:issue-maintain |
| `review:completed` | code-review | issue-workflow:issue-maintain |
| `failure:logged` | failure-journal | issue-workflow:retrospective |

### Shared State（frontmatter で producer/consumer 明示）

| type | 配置 | producer |
|---|---|---|
| `session` | `.claude/session-context.md` | issue-workflow |
| `follow-up` | `.claude/{linear\|indie}/{slug}/follow-ups/*.md` | issue-workflow |
| `knowledge` | `.claude/{linear\|indie}/{slug}/knowledge/**/*.md` | issue-workflow |
