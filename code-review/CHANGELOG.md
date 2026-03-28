# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [2.2.1] - 2026-03-29

### Fixed
- userConfig.review_confidence_threshold に type/title を追加し manifest バリデーションエラーを修正

## [2.2.0] - 2026-03-29

### Added
- 全スキルに effort frontmatter を追加（review/self-review: max）
- userConfig: review_confidence_threshold でレビュー閾値をカスタマイズ可能に

## [2.1.0] - 2026-03-26

### Added
- Phase 0 トリアージ: diff 分析による動的エージェント構成決定（Stage 1 タイプ判定 → Stage 2 体数・フォーカス・冗長度決定）
- explorer エージェントタイプ: 事実収集特化（function-flow, dependency-trace, branch-impact, history-context, shared-module-impact）、上限 6 体
- reviewer 冗長化: 対象コードの複雑さに応じて同一観点を複数体（angle 違い）で起動、上限 10 体
- spec-compliance 観点: session-context / Issue / knowledge との仕様整合性チェック
- references/triage-guide.md: Phase 0 判定ロジック・パターンマトリクス・フォールバック構成
- references/explorer-prompts.md: explorer プロンプトテンプレート集
- references/reviewer-prompts.md: 観点別 reviewer プロンプトテンプレート集（現行 #1-#16 から移行・再構成）
- scoring-guide: explorer 裏付け (+10)、冗長ペア合意 (+10)、冗長ペア片方のみ (-5) ルール追加

### Changed
- 固定2フェーズ構成（Phase 1 固定6+条件2 → Phase 2 動的8）を廃止し、Phase 0 トリアージ → 探索 → レビューの動的3フェーズ構成に移行
- CLAUDE.md 準拠チェック: 冗長2体 → Phase 0 判断で 1-2 体（複雑さに応じた冗長化）
- diff-first 原則を改訂: 変更箇所を含む関数の全体確認・類似名称の確認を Read 許可用途に追加

### Removed
- references/agent-prompts.md: 3ファイル（triage-guide, explorer-prompts, reviewer-prompts）に分割移行

## [2.0.0] - 2026-03-25

### Added
- 2フェーズレビュー構成: Phase 1 (コアレビュー) → Phase 2 (専門レビュー動的起動)
- Phase 2 専門エージェント8種: セキュリティ(OWASP)、パフォーマンス、API設計、依存関係、マイグレーション、設定、クロスカッティング影響、パターン統一
- Phase 2 起動判定: diff パターンマッチ（静的）+ Phase 1 結果からの動的判定
- Phase 2 スキップ条件: 小規模かつ懸念なしの場合は Phase 1 のみで完了

### Changed
- 全エージェントを `model: opus` で起動（品質最大化）
- scoring-guide: 複数エージェント同一指摘の加算を +10 → +15 に引き上げ
- scoring-guide: Phase 2 専門エージェント関連のスコアリングルールを追加

## [1.5.0] - 2026-03-25

### Changed
- review: diff 取得を `git diff` から `gh pr diff` に変更（ローカル状態に依存しない）
- review: 全エージェントを `isolation: "worktree"` で起動（PR ブランチの正しい状態でファイルを読む）
- review: diff-first 原則を追加（diff が真のソース、ファイル Read はコンテキスト確認のみ）
- Agent #3: ファイル全文分析→依存先の仕様確認のみに限定

## [1.4.0] - 2026-03-24

### Added
- self-review/review: セッションコンテキスト読み込み（Step 2.5）を追加。`.claude/session-context.md` から Issue の設計判断を取得し、エージェントプロンプトに注入
- scoring-guide: セッションコンテキストによるスコア減算ルールを追加（設計判断一致: -30、スコープ外: -50）

## [1.3.0] - 2026-03-23

### Added
- SessionStart hook で外部依存チェック（GitHub MCP）を実行
- plugin.json に `_requirements` フィールドを追加（依存メタデータ宣言）

## [1.2.0] - 2026-03-23

### Added
- self-review: レポート出力後に修正方針選択ステップ（Phase 6）を追加
- rules/self-review-interaction.md を新規追加

## [1.1.1] - 2026-03-23

### Fixed
- スキル description のトリガーフレーズを「トリガー:」形式に統一

## [1.1.0] - 2026-03-21

### Fixed
- プラグイン品質改善
- 全プラグインの品質問題を一括修正

## [1.0.0] - 2026-03-20

### Added
- code-review プラグインを新規作成
- 並列エージェントによる PR レビュー / セルフレビュー機能
