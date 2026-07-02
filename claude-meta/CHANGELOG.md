# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.11.2] - 2026-07-02

### Fixed
- `cc-catch-up` の state.json をプラグイン本体ディレクトリ（`skills/cc-catch-up/state.json`）から `${CLAUDE_PROJECT_DIR:-$HOME}/.claude/claude-meta/cc-catch-up-state.json` に移設。marketplace 更新でキャッシュごと消える問題と、個人の実行状態が git commit される問題を解消。リポジトリにコミット済みの `state.json` を削除（schema は `references/state-schema.json` に残置）。SKILL.md / README / `pruning-heuristics.md` のパス参照を新パスに更新し、`validate-state.py` の既定 state パスも環境変数ベースに変更
- `cc-catch-up/SKILL.md` のパス変数を `${CLAUDE_PLUGIN_ROOT}` 基準に統一（`${CLAUDE_SKILL_DIR}` → `${CLAUDE_PLUGIN_ROOT}/skills/cc-catch-up/`）
- `claude-md-improver/SKILL.md` の Phase 4 から孤立していた `references/update-guidelines.md` への参照を追加
- `commands/revise-claude-md.md` を日本語化（fork 由来の英語を他 command / skill と統一）

### Changed
- plugin.json の description に `eval-runner`（eval 回帰テスト）と `component-addition-advisor`（新コンポーネント追加前判断）を反映（5 skill を網羅）

## [1.11.1] - 2026-06-15

### Changed
- README を全 command（catch-up / revise-claude-md）/ skill（cc-catch-up / claude-code-setup / claude-md-improver / component-addition-advisor / eval-runner）構成に同期し、Version 行を撤去（plugin.json を SSoT 化）
- cc-catch-up カタログ（`plugin-features.md`）を CC v2.1.163 までの新 hook 機能に追随。args[] exec 形式（v2.1.139）/ terminalSequence helpers（v2.1.141）/ `${CLAUDE_EFFORT}` skill 適応分岐（v2.1.120）/ additionalContext での Stop hook 注入（v2.1.163）を追記し、カバー範囲を v2.1.163 に更新

## [1.11.0] - 2026-06-02

### Added
- `cc-catch-up` に **state.json の JSON Schema 化 + 決定的バリデータ** を追加（Workflow 監査 2026-06-01 の rollout Step3-A）。`references/state-schema.json`（draft-07、run 間差分照合に使う状態構造の single source）と `scripts/validate-state.py`（標準ライブラリのみ・外部 jsonschema 非依存。type / required / enum / pattern / additionalProperties / anyOf のサブセットを照合）を新規追加。Phase 7 の state.json 書き込み後に実行して structure drift を機械的に弾く
- `cc-catch-up` Phase 3 の frontmatter 生抽出を **決定的 pre-pass 化**。`scripts/scan-frontmatter.sh`（grep / jq）が全プラグインの manifest / hooks / skills / agents / commands の使用フィールドを機械抽出し、Agent fan-out を判断・要約層に限定（全プラグイン一律の 5 並列 fan-out を廃止し「決定的 hook > LLM 判定」に整合）
- SKILL.md の Phase 3 / Phase 7 / Reference Files を上記スクリプト前提に更新

### Notes
- Workflow ランタイム導入は見送り。state.json は既に構造化され差分照合が成立済みで、実行モデル変更（本リポジトリは Workflow 前提プラグインゼロ）の不可逆コストに見合う増分便益なしと判断。schema lint + grep/jq pre-pass の決定的強化のみ採用

## [1.10.0] - 2026-05-28

### Added
- `claude-md-improver` に **運用パターン 6 セクション診断** を追加（GitHub issue #55）。ガードレール骨抜き禁止 / 三段防御 / AGENTS.md 階層 / `@AGENTS.md` 1 行参照 / ドキュメント優先度規約 / 静的検査優先の充足度を診断して suggest
- `claude-md-improver` Phase 1.5 に **階層化判定 AskUserQuestion** を追加。小規模プロジェクトに過剰設計を suggest しないための分岐
- `claude-md-improver` Phase 2 のチェックリストに 4 項目追加（Guardrail anti-bypass / Three-tier defense / Priority resolution / Static check preference）
- `claude-md-improver` Phase 3 に **三段防御チェックリスト**（CLAUDE.md / Skill / Hook の 3 層充足度表）と **静的検査化候補抽出**（CLAUDE.md の「禁止」行から linter 化候補を抽出する自己問い）を追加
- references 新規 4 ファイル: `meta-rules.md`（骨抜き禁止 + 静的検査優先）、`three-tier-defense.md`（規範→推奨手順→機械強制の 3 層パターン）、`hierarchical-agents-md.md`（階層化のしきい値と AskUserQuestion テンプレート）、`priority-template.md`（ドキュメント優先度 3 要素テンプレ）
- `claude-md-improver` allowed-tools に `AskUserQuestion` を追加（Phase 1.5 で利用）

## [1.9.1] - 2026-05-25

### Changed
- `eval-runner/SKILL.md` の command↔skill 曖昧性パターン例から `instinct-memory` 関連を削除（instinct-memory プラグイン廃止に伴う参照除去）

## [1.9.0] - 2026-05-22

### Added
- `claude-md-improver/references/diataxis-framework.md` を新規作成。Diátaxis（Tutorial / How-to / Reference / Explanation）を CLAUDE.md セクションにマップする補助診断レンズを提供。スコアには加算せず、Phase 3 の Quality Report に "Structural Observations" として併記する位置づけ
- `claude-md-improver/SKILL.md` Phase 2 に Diátaxis 補助観点の適用ガイドを追加（100 行超の CLAUDE.md のみ対象、混在・Why 欠落・順序喪失を検出）
- `claude-md-improver/references/quality-criteria.md` Red Flags に Diátaxis 観点（Gotchas の Why 欠落 / Setup の順序喪失 / 1 セクション内 3 タイプ以上混在）を追加
- `claude-md-improver/references/templates.md` の各セクション見出しに Diátaxis タイプ注記を追加（Commands=Reference, Architecture=Reference+Explanation, Gotchas=Explanation+Reference, Skill Coordination=How-to）。Gotchas テンプレに "Why:" 列を追加し再発防止を強化

## [1.8.1] - 2026-05-18

### Changed
- `commands/catch-up.md` の `allowed-tools` から `Glob` / `Grep` を削除（10 → 8 ツール）。これらは Phase 3 / P.1 の subagent (Agent ツール経由) 内部で使用されるため、親 command レベルでは不要。`skills/cc-catch-up/SKILL.md` の 8 ツールと一致させ、CLAUDE.md ルール「command/skill の allowed-tools 一致」に整合。Permission Pruning 原則に従い宣言ツールを必要最小限に絞ることで Claude の判定精度を上げる

## [1.8.0] - 2026-05-15

### Added
- `claude-code-setup/references/official-skills.md` を新規作成。Anthropic / Vercel 公式 skill 22 件 + Claude Code ハーネス組み込み 8 件のインベントリと、コードベース検出シグナル ↔ skill マッピング、レコメンド意思決定フローを提供
- `claude-code-setup` SKILL.md Phase 2 / 3 に「公式 skill レコメンド」セクションを追加。新規スキル提案より公式同等品の利用を優先する判定フローを導入（保守責任を Anthropic / Vercel に委譲）

### Changed
- `claude-code-setup/references/skills-reference.md` の古い「公式プラグイン経由で利用可能なスキル」表を削除し、`official-skills.md` への誘導に置換。本ファイルはカスタムスキル作成パターンに絞った
- `claude-code-setup/references/plugins-reference.md` を最新化。古い公式プラグイン情報（pr-review-toolkit / code-simplifier / security-guidance 等の参照）を anthropic-agent-skills marketplace 中心の構成に更新

## [1.7.0] - 2026-05-15

### Added
- `cc-catch-up` Phase 0 に `${CLAUDE_EFFORT}` 適応分岐を追加（CC 2.1.120+）。実行時 effort に応じて既定モードと提案優先度の絞り込みを自動調整（low/medium: High のみ、high: Medium まで、xhigh/max: Low まで深掘り）

### Removed
- `cc-catch-up` の allowed-tools から未使用ツールを削除（Permission Pruning 原則）: `Glob`, `Grep`（本文で直接参照なし、Agent 経由のスキャンで利用するため不要）

## [1.6.2] - 2026-04-25

### Changed
- `cc-catch-up` Phase 3: プラグインスキャンの 5 エージェント起動を imperative 化（Opus 4.7 対応）。「同一メッセージ内で並列起動、逐次起動は禁止」を明示
- `cc-catch-up` Phase 4: Gap 分析に段階的思考誘導を追加（「この Phase は設計判断を含むため段階的に検討」＋各改善提案の根拠を 1 文で書けるか確認ステップ）

## [1.6.1] - 2026-04-23

### Changed
- `cc-catch-up/state.json` を v2.1.117 に更新。v2.1.115-117 の新機能は本 marketplace に即時適用可能な差分なしと判断し、skipped に記録（agent main-thread `mcpServers`/`hooks:`、Pro/Max default effort `high`、plugin install deps 自動補完ほか）

## [1.6.0] - 2026-04-22

### Added
- `component-addition-advisor` skill 追加（#24）: 新 skill / agent / hook / command 追加前の「退路確保」判断をガイド
  - 既存拡張で解けないかを最初に検証、ブロッカー発生時のみ新規追加する判断フロー
  - `_requirements` にフォールバック手順 / blocker 理由を記録する規約
  - AskUserQuestion で既存拡張 vs 新規追加を対話的に選択
- `claude-md-improver`: Skill Coordination 監査項目追加（#23）
  - スコアリングルーブリック再配分（Commands/Architecture 20→15、Actionability 15→10、新規 Skill Coordination 15 点）
  - Phase 3 レポートに「Skill Invocation Guidance Audit」セクション追加（診断のみ、自動挿入禁止）
  - `references/templates.md` に「Skill Coordination」セクションのテンプレート追加
  - Vercel eval 知見（Skill 56% 未呼出、人間作成 +4% / 自動生成 -3%）を反映

### Changed
- CLAUDE.md: プラグイン開発ルールに `component-addition-advisor` 参照を追加

## [1.5.0] - 2026-04-22

### Added
- `cc-catch-up`: モデル世代ごとの hook/skill 剪定レビュー機能（#22）
  - Phase 0 にモデル世代変更検知を追加し、検知時に「剪定モード」を推奨
  - 新 Phase P（剪定モード）: C-1〜C-5 カテゴリで候補抽出 → レポート → AskUserQuestion で対話的に削除/hook化/保留/保持を選択
  - `references/pruning-heuristics.md` 追加: 剪定カテゴリ定義、判定フロー、レポート形式、対話仕様
  - `state.json` に `lastCatchUpModel` / `lastPruningDate` / `prunedConstraints` / `preservedConstraints` フィールド追加

## [1.4.2] - 2026-04-19

### Changed
- eval-runner スキルに「同名の command + skill ペア」の gotcha と inline list による両名義許容パターンを追記（knowledge 切り出し）

## [1.4.1] - 2026-04-19

### Changed
- `eval-runner`: `expected_skill` が inline list `[a, b]` を受け付けるように拡張。command と skill のどちらに解決されても PASS と判定可能に
- eval-runner の allowed-tools から未使用の `Glob` を除去（Bash / Read / AskUserQuestion の 3 件に）

## [1.4.0] - 2026-04-19

### Added
- `eval-runner` スキル追加。`evals/` 配下の YAML ケースを実行し、トリガーフレーズ → 期待スキル起動の回帰テストを pass^k 基準で検証する（#18）

## [1.3.7] - 2026-04-19

### Changed
- cc-catch-up の state ファイルを `${CLAUDE_PLUGIN_DATA}/catch-up-state.json` から `${CLAUDE_PLUGIN_ROOT}/skills/cc-catch-up/state.json` へ移動。git 管理下に置くことでマシン間/再インストール時の履歴消失を防ぐ
- SKILL.md の Phase 0 / Phase 7 のパス参照を更新

## [1.3.6] - 2026-04-19

### Changed
- plugin-features.md カタログ更新: v2.1.106-v2.1.114 の新機能を反映
  - `xhigh` effort レベル（v2.1.111、Opus 4.7 専用）を Agent/Skill/Command フロントマター説明に追記
  - Runtime & CLI セクションに `plugin_errors` in stream-json (v2.1.111)、Built-in slash via Skill tool (v2.1.108)、subagent stall fail (v2.1.113)、plugin install range-conflict (v2.1.113) を追加
  - 環境変数セクションに `ENABLE_PROMPT_CACHING_1H` / `FORCE_PROMPT_CACHING_5M` (v2.1.108)、`OTEL_LOG_RAW_API_BODIES` (v2.1.111)、`CLAUDE_CODE_USE_POWERSHELL_TOOL` (v2.1.111) を追加
  - カバー範囲を v2.1.114 に更新

## [1.3.5] - 2026-04-17

### Added
- improvement-patterns: P-11 「Opus 4.7 向け effort 調整 (`max` → `xhigh`)」パターンを追加

## [1.3.4] - 2026-04-15

### Changed
- plugin-features.md カタログ更新: PreCompact hook（v2.1.105）、monitors manifest key（v2.1.105）、description cap 250→1536（v2.1.105）、/reload-plugins スキル反映ノート追加
- catch-up-state.json 初期作成（v2.1.109 時点）

## [1.3.3] - 2026-04-08

### Changed
- plugin-features.md カタログ更新: UserPromptSubmit イベント、sessionTitle、hook model パラメータ、スキル name フロントマター、コマンド effort/keep-coding-instructions を追記

## [1.3.2] - 2026-04-04

### Fixed
- claude-md-improver スキルの description を 250 文字以内に短縮（v2.1.86 の上限対応）

### Changed
- plugin-features.md カタログ更新: SessionEnd, SubagentStart/Stop, PermissionRequest, bin/, git-subdir, description 上限, disableSkillShellExecution, defer, MCP tool result persistence 等を追記

## [1.3.1] - 2026-03-31

### Changed
- plugin-features.md カタログ更新: PermissionDenied hook、last_assistant_message、initialPrompt バージョン修正

## [1.3.0] - 2026-03-29

### Added
- cc-catch-up スキル: Claude Code アップデートの自動追従ワークフロー
- /catch-up コマンド: スキルとペアリング（引数でバージョン範囲指定可）
- references/plugin-features.md: CC プラグイン関連機能カタログ
- references/improvement-patterns.md: 機能→改善のデシジョンツリーと before/after パターン集
- `${CLAUDE_PLUGIN_DATA}` による前回キャッチアップ状態の永続追跡

## [1.2.0] - 2026-03-29

### Added
- 全スキルに effort frontmatter を追加（claude-code-setup/claude-md-improver: high）

## [1.1.1] - 2026-03-23

### Fixed
- スキル description のトリガーフレーズを「トリガー:」形式に統一

## [1.1.0] - 2026-03-21

### Fixed
- プラグイン品質改善
- 全プラグインの品質問題を一括修正

## [1.0.0] - 2026-03-20

### Added
- claude-meta プラグインを新規作成
- Claude Code 設定管理・CLAUDE.md 監査改善機能
