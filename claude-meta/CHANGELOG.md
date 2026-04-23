# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

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
