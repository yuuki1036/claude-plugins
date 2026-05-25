# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [2.13.0] - 2026-05-25

### Added
- `self-review` skill に `--focus <観点>` / `--exclude <観点1,観点2>` 引数を追加（GitHub issue #40）。同一セッションで既に reviewer agent を走らせた後の再実行時に、既検証の観点を再報告しないようレビュー対象を絞り込み・除外できる
  - `--focus`: Phase 0 で該当観点の reviewer のみ構成（最小保証も focus に含まれない限り起動しない）
  - `--exclude`: 該当観点の reviewer を構成から外す
  - reviewer プロンプトに `review focus:` / `already verified (do not re-report):` を注入
- `commands/self-review.md` の `argument-hint` と本文に `--focus` / `--exclude` を反映

## [2.12.0] - 2026-05-19

### Added
- **Red-flag pattern による specialist 自動起動**（Idea 3-a）。triage-guide.md の `## 3 Red-flag pattern による specialist 自動起動` で diff の危険パターンを検出し、対応する specialist reviewer を Phase 0 で自動追加起動する
  - `specialist-injection`: `eval(` / `child_process` / `exec(` / `subprocess.run` / `shell=True` 等のコード/コマンドインジェクション
  - `specialist-destructive-op`: `fs.unlink` / `rm -rf` / `DROP TABLE` / `TRUNCATE` / WHERE 句なし DELETE/UPDATE 等の破壊的操作
  - `specialist-secret-handling`: `password =` / `BEGIN PRIVATE KEY` / `Bearer` / `console.log(.*token)` 等のシークレット漏洩
  - `specialist-input-validation`: `JSON.parse(req.*)` / `RegExp(user_input)` 等の信頼境界
  - specialist の指摘は大半が BLOCKER/CRITICAL になる前提で、2軸マトリクスにより低 confidence でも人間に届く設計
- **Phase 5.5 Adaptive deepening (追加 explorer ラウンド)**（Idea 1）。reviewer の `unmet_information` 申告をトリガーに、対応する re-explore explorer を 1 ラウンドだけ起動して該当 reviewer のみ再実行する
  - reviewer-prompts.md 共通指示に `## unmet_information` 出力フィールド仕様を追加。「BLOCKER 候補で context 不足」「呼び出し元全件確認が必要」等のケースのみ申告
  - explorer-prompts.md に `re-explore` フォーカステンプレートを追加。元 reviewer の why に直接回答する形式
  - 上限 3 体ずつ。失敗時は best-effort で続行
- **Phase 5.6 Meta-reviewer ラウンド**（Idea 1+3 統合）。BLOCKER または CRITICAL 検出時に、別 reviewer が「他の reviewer の見落とし観点」を探すメタレビューを 1 ラウンド実行
  - 観点の偏り検出、指摘の盲点、複合リスク、正常系の見落としを重点的に検証
  - 重複指摘禁止、追加指摘なしも健全
- **explorer 配置条件の緩和**（Idea 3-b）。共通モジュール（`utils/` / `shared/` / `lib/` / `common/` / `helpers/` / `core/`）の変更は **行数・関数数に関わらず必ず shared-module-impact explorer を 1 体起動**。小規模変更で依存元への波及を見落とすリスクを構造的に解消
- `plugin.json` の userConfig に `enable_adaptive_rounds` (boolean, default: true) と `enable_meta_reviewer` (boolean, default: true) を追加。トークンコスト・レイテンシを抑えたい場合は false に

### Changed
- `triage-guide.md` の `## 7 最小保証とフェーズ上限` に specialist 上限 6 体を追加（reviewer 枠 10 体とは別カウント）
- `triage-guide.md` に `## 8 動的ラウンド (Phase 5.5 / 5.6)` セクションを新設、effort 適応ルール表 (low/medium はスキップ、high は 5.5 のみ条件付き、xhigh/max は両方) を明文化
- `review` skill / `self-review` skill にレポート出力時の動的ラウンド可観測性を追加 (`Round 2 探索 N 体起動 / Meta-reviewer {実行 | スキップ理由}`)
- skill description / `marketplace.json` の説明を 2.12 機能反映に更新

### Notes
- effort 適応により、デフォルト effort=high では Phase 5.5 (unmet 起動時のみ) のみ動作し、Phase 5.6 はスキップ。深掘りが必要な場合は effort=xhigh / max で実行
- 動的ラウンド全体のトークンコスト増分は「unmet 申告がない場合 0」「申告ありでも追加 explorer 最大 3 + 再 reviewer 最大 3」「meta-reviewer +1」のため、保守的設計
- 本リリースは Phase B (Idea 1 + Idea 3 統合) に該当。Phase A (2軸スコアリング) は v2.11.0

## [2.11.0] - 2026-05-19

### Added
- **2 軸スコアリング** (confidence × severity) を導入。`scoring-guide.md` を全面改訂し、severity 4 段階 (BLOCKER / CRITICAL / MAJOR / MINOR) と報告マトリクスを定義。「重大だが不確実」(race condition 疑い 等) と「軽微だが確実」(typo 等) を従来の単一軸 confidence では区別できなかった構造的ジレンマを解消
  - 報告マトリクス: BLOCKER は confidence ≥ 60 で報告、CRITICAL は ≥ 80、MAJOR / MINOR は ≥ 95
  - これにより「疑わしい重大問題は人間判断を促す」「ノイズ的 nitpick は自動除外される」の非対称運用が可能に
- `reviewer-prompts.md` の共通指示に severity 必須付与を追加、出力フォーマットに `[severity: XXX]` ラベルを追加。各 Focus テンプレート (bug-detection / security / migration / performance / api-design / cross-cutting 等) に severity 目安を追加
- `plugin.json` の userConfig に `review_severity_threshold` を追加 (デフォルト: `MAJOR`)。ユーザーが報告閾値を `BLOCKER` (厳しめ) / `MINOR` (緩め) に変更可能

### Changed
- `review` skill / `self-review` skill の Phase 6 / 5 のフィルタリングロジックを 2 軸マトリクスベースに変更
- `review` skill の Step 7 出力フォーマットを severity 別グルーピング (🚨 BLOCKER / ⚠️ CRITICAL / 📋 MAJOR) に変更
- `review:completed` event payload に `blocker_count` / `major_count` / `minor_count` を追加。`critical_count` は subscriber 互換のため維持
- `self-review` skill の修正方針 AskUserQuestion を「BLOCKER/CRITICAL のみ」に変更 (旧: `confidence >= 90 のみ`)。BLOCKER 指摘を残したままコミットしようとした場合は再確認
- `review` skill の返答ドラフト生成の「重要のみ」を severity ベース (BLOCKER または CRITICAL) に変更
- `review` / `self-review` skill の description を 2 軸スコアリング対応に更新

### Notes
- **後方互換性**: severity が付与されていない reviewer 出力は CRITICAL とみなして処理されるため、移行期間中も既存挙動が維持される (旧 confidence ≥ 80 と等価)
- userConfig の `review_confidence_threshold` は後方互換のため残置 (CRITICAL severity 以下のフィルタに使用)
- 本リリースは Phase A (スコア再定義) に該当。Phase B (Idea 1+3 統合: 動的ラウンド + 検出ミス対策) は別リリース予定

## [2.10.0] - 2026-05-19

### Added
- `references/reply-tone-guide.md` を新規追加 (#37 軽量版)。レビュー後の返答ドラフトのトーン・テンプレ・禁則・パターン別ガイド（完全対応/部分対応/据置/意図確認/反証/レビュアー再返信）を集約
- `review` skill の Step 7 にレポート出力後の **返答ドラフト生成** ステップを追加（AskUserQuestion で `不要 / 重要のみ / 全件 / 個別選択` を選択、reply-tone-guide.md に従いドラフトのみ生成、投稿は手動）
- `review` skill と `commands/review.md` の allowed-tools に `AskUserQuestion` を追加

### Notes
- Issue #37 の thread skill 構想（check / reply / status）からスコープを大幅に縮小。状態管理・GitHub 投稿自動化・未対応スレッド一覧は本リリースに含めず、将来 skill 化が必要になった時点で再検討する（退路確保）
- `self-review` skill は PR コメントの返答対象がないため変更なし

## [2.9.0] - 2026-05-18

### Added
- `review` skill の Step 7（レポート出力後）に `review:completed` イベント発行を追加 (#33)。payload は `{"pr":"<number>","critical_count":<n>,"warning_count":<n>,"missing_coverage":[...]}`
  - publisher は `safe-hook.sh` の `event_bus_publish` を `SAFE_HOOK_NAME="code-review:review"` 上書きで呼び出す形式（fire-and-forget、失敗してもレポートは成功扱い）
  - retrospective / instinct-memory 等の subscriber がレビュー傾向（critical 数推移・missing_coverage の偏り）を集計できるようにするための土台

## [2.8.1] - 2026-05-18

### Changed
- `hooks/lib/safe-hook.sh` を v2026-05-18+ に同期。`event_bus_publish` / `event_bus_tail` / `event_bus_clear` API を取得（正本由来、内部ライブラリ拡張）。code-review 自身は現時点で event を発行しないが、将来 `review:completed` イベント発行用の土台として整備

## [2.8.0] - 2026-05-15

### Added
- 公式 skill 連携を 2 系統追加。
  - `ui-quality` reviewer Focus を新設し、`web-design-guidelines` 公式 skill（`~/.agents/skills/web-design-guidelines/`）のチェックリストに準拠した WCAG 違反 / セマンティック HTML 違反 / フォーカス管理 / 状態フィードバック欠落の指摘を confidence ≥ 80 で報告
  - `triage-guide.md` に UI/フロントエンド観点判定ルールを追加（`.tsx`/`.jsx`/`.vue`/`.svelte`/`components/`/`pages/`/`app/` の変更、または diff の `aria-`/`role=`/`tabindex`/`<button`/`onClick`/`onKeyDown` を検出）
- reviewer 共通指示に外部ライブラリ最新仕様確認（公式 skill `context7` 経由）を opt-in で追加。モデル学習データ cutoff を越える破壊的変更による誤判定を防止し、裏付け不能な仕様ベース指摘は confidence ≤ 75 に下げて自動除外させる

## [2.7.0] - 2026-05-15

### Added
- review SKILL.md に `${CLAUDE_EFFORT}` 適応分岐を追加（CC 2.1.120+）。実行時 effort に応じて explorer/reviewer の上限体数を自動調整（low/medium: 速度優先、high: 既定、xhigh/max: 深掘り）

### Changed
- `hooks/hooks.json` を `args[]` exec 形式へ移行（CC 2.1.139+）。シェル解釈なしでスクリプトを直接 spawn し、起動オーバーヘッドとパース起因のエッジケースを削減
- `safe-hook.sh` に `safe_hook_emit_bell` / `safe_hook_emit_window_title` を追加（CC 2.1.141+ terminalSequence 対応、opt-in 利用）

## [2.6.2] - 2026-05-13

### Added
- `code-review/scripts/fetch-pr-context.sh` を追加。PR メタ・issue コメント・レビューサマリ・行単位 review コメント（返信チェーン込み）を一括取得し、SKILL.md Step 2.5 の構造化フォーマットで markdown 出力する

### Changed
- review SKILL.md Step 1 を更新: PR 会話コンテキスト取得を `fetch-pr-context.sh` の **必須実行** に変更。LLM が個別 `gh` コマンドで組み立てる方式を禁止し、PR コメントの取りこぼしを防止
- review SKILL.md Step 2.5 を更新: スクリプト出力をそのまま PR コンテキストブロックとして使用するよう簡略化（LLM による再構築・要約・編集を禁止）

### Fixed
- review スキルで PR コメント取得がスキップされるケースを解消（取得手順をスクリプトに集約することで決定的に取得保証）

### Removed
- review / self-review の allowed-tools から未使用ツールを削除（Permission Pruning 原則に基づく最小化）
  - review: `Glob`, `Grep`, `mcp__github__pull_request_read`
  - self-review: `Glob`, `Grep`
  - 対応する commands/*.md の allowed-tools も同期

## [2.6.1] - 2026-04-25

### Changed
- `reviewer-prompts.md` の Confidence スコアリングに段階的思考誘導を追加（Opus 4.7 対応）。境界値（75-85）や他 reviewer との矛盾時に diff 意図確認・既存問題誤検知チェック・証拠裏付け確認の 3 ステップを明記

## [2.6.0] - 2026-04-24

### Added
- review スキルに PR 会話コンテキストの reviewer プロンプト注入を追加
  - `gh api repos/{owner}/{repo}/pulls/<PR>/comments` で行単位レビューコメントを取得
  - `gh pr view --json reviews` でレビューサマリを取得
  - PR 説明・issue コメントと合わせて PR コンテキストブロックとして構造化（SKILL.md Step 2.5）
- reviewer-prompts.md に「PR コンテキスト注入テンプレート」(#2.5) を追加
  - 検出ルールはタグベース: `[re-flag: @<user>]` / `[resolved: @<user>]` / `[intent-conflict]` / `[scope:out]`
  - 重複指摘の回避（既指摘かつ diff で修正済みは出力除外）
  - 著者意図の尊重（PR 説明のスコープ・意図と照合）
- scoring-guide.md にタグベースの加減算ルールを追加（正本）
  - `[re-flag: ...]`: +15（既指摘かつ diff で未修正の押し戻し）
  - `[intent-conflict]`: -20（spec-compliance の仕様違反は対象外）
  - `[resolved: ...]`: -30（PR 会話で LGTM/resolved）
  - `[scope:out]`: -50（PR 説明で明示されたスコープ外）
  - 行単位 review comment で既指摘 かつ diff で修正済み: 報告対象外
- triage-guide.md の Stage 1 に PR コンテキストによる観点追加・冗長化ロジックを追記（review skill のみ）

### Changed
- scoring-guide.md と reviewer-prompts.md の責務分離を明確化: reviewer は検出・タグ付けに集中、confidence 数値の加減算は scoring-guide.md を正本として Step 6 で適用

## [2.5.0] - 2026-04-22

### Added
- review / self-review スキルに部分失敗耐性ロジックを追加。explorer / reviewer が並列実行中に失敗しても成功した結果で合成継続し、欠損観点を最終レポートに明示する（最小保証 reviewer-bugs + reviewer-claude-md の両方失敗時のみ中止） (#25)
- self-review スキルに「Generator と分離された Evaluator」設計原則セクションを追加。dev-workflow:git-commit-helper との連携フローを明示 (#27)

## [2.4.2] - 2026-04-19

### Changed
- `check-deps.sh` を `safe-hook.sh` 共通ラッパー経由に移行（stdin 消費・エラー分類・名前付きログの統一） (#21)

## [2.4.1] - 2026-04-17

### Changed
- review/self-review の skill frontmatter effort を `max` → `xhigh` に変更（Opus 4.7 のコーディング向け新推奨設定）
- reviewer subagent の起動を `effort: max` 明示指定に変更（深い推論を優先、偽陽性は Confidence ≥80 フィルタで除去）
- effort 設計意図を SKILL.md に明文化（orchestrator: xhigh、reviewer: max の役割分担）

## [2.4.0] - 2026-04-13

### Added
- review: EnterWorktree/ExitWorktree による worktree 分離実行（レビュー中の並行作業を可能に）

### Changed
- review: `gh pr checkout` を worktree 内で実行するよう変更（作業ブランチへの影響を排除）

## [2.3.3] - 2026-04-04

### Fixed
- review/self-review スキルの description を 250 文字以内に短縮（v2.1.86 の上限対応）

## [2.3.2] - 2026-03-31

### Changed
- SessionStart check-deps.sh に `once: true` 追加（セッション中1回のみ実行）

## [2.3.1] - 2026-03-30

### Changed
- explorer のモデルを opus → sonnet に変更（情報収集タスクの effort 最適化、reviewer は opus 維持）

## [2.3.0] - 2026-03-29

### Changed
- self-review: AskUserQuestion の呼び出し仕様を SKILL.md に直接埋め込み（修正方針選択 + 後処理）

### Removed
- rules/self-review-interaction.md を削除（間接参照では LLM が AskUserQuestion を呼ばない問題の修正）

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
