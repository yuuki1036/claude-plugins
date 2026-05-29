# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.25.0] - 2026-05-29

### Added
- **Shared State 規約に準拠した frontmatter を `session-context.md` と follow-up ファイルに付与** (#35)。`shared_state_type` / `producer` / `consumers` / `schema_version` / `last_updated` を必須化し、cross-plugin で読み書きされる永続ファイルの producer-consumer 関係を明示化
- `session-start` の Phase CTX で `.claude/session-context.md` 書き出し時に `shared_state_type: session` / `producer: linear-workflow` / `consumers: [code-review, feature-dev, dev-workflow]` を付与
- `follow-up` の N5（ファイル生成）で `shared_state_type: follow-up` / `producer: linear-workflow` を付与
- consumer 側は frontmatter 不在のファイルも読める後方互換を維持（既存ファイルは段階移行）

### Notes
- Classmethod「Claude Code マルチエージェントオーケストレーションパターン」記事の Shared State パターンを軽量実装。flat な `.claude/shared/` への移行は slug-scoped 構造との衝突回避のため見送り、配置はそのままで frontmatter のみで producer/consumer を明示するアプローチを採用
- 規約定義は `CLAUDE.md` の「Shared State 規約」セクションを参照

## [1.24.0] - 2026-05-26

### Added
- **`issue-design` スキル / コマンドを新設**。Issue 本文を 9 セクションテンプレ（Why / 成果物 / 対応内容 / 完了条件 / 依存・ブロッカー / 決定事項 / 判断ポイント(open) / 参考資料 / スコープ外）と設計判断ルール（決定 vs open の境界、現時点の方向性マーカー、後続の双方向記述、確定タイミング明示）に沿って設計・構造化・リライトする。新規起票（`issue-create`）・品質チェック（`issue-maintain`）と責務分離し、トリガーは規範・設計系に限定して create との誤起動を回避
- `references/template-9sections.md`（9 セクション定義・コピペ雛形）/ `references/design-rules.md`（設計判断ルール）を普遍 references として追加。両者は indie-workflow と byte-identical で共有する正本
- `references/linear-syntax.md`（collapsible `+++` / `<issue id>` リンク / インライン pros/cons）を Linear 固有 references として追加

## [1.23.1] - 2026-05-26

### Changed
- `knowledge` / `knowledge-lint` の description を「検索・参照（読み取り専用）」と「点検・修復（lint）」に分離し、トリガー精度を改善。`knowledge` の単独トリガー「knowledge」を外して検索文脈に限定、`knowledge-lint` に「リンク切れ」「孤立した知見」「knowledge を整理」を追加。eval（pass^k=3）で knowledge-lint を狙うプロンプトが検索用 knowledge に誤誘導される問題（2/6 → 6/6）を解消

## [1.23.0] - 2026-05-25

### Added
- **概念ページ（concept）と wikilink** を knowledge に導入。複数の個別知見（source）を `[[name]]` で横断統合する `knowledge/concepts/*.md`（`kind: concept`）を追加し、繋いで初めて見える構造を蓄積できるようにした
- **`knowledge-lint` スキル / コマンドを新設**。broken wikilink・index 不整合（stale / 未登録）・orphan concept・isolated source・tags 表記ゆれ・重複概念の 7 項目を検出し、機械的に直せるもの（index 同期・確定 broken link 張替）を承認制で修正する。意味の統合は提案に留める
- `issue-maintain` に**概念ページへの波及（concept 統合）**を追加。source 切り出し後、同テーマの source が 2 件以上あれば concept の新規作成 / 既存 concept への `[[ ]]` 追加を提案する
- `knowledge` スキルを concept 対応に拡張（一覧の concept/source 分離、検索・関連の `concepts/` 走査、関連表示の `[[ ]]` 1 ホップ辿り）
- `quality-checklist.md` §6 frontmatter 表に `kind` を追加、§6.1「概念ページ（concept）と wikilink」を新設
- FileChanged hook に `.claude/linear/*/knowledge/concepts/*.md` matcher を追加（concept ファイルの外部変更検知）
- `init` の生成ディレクトリに `knowledge/concepts/` を追加

### Changed
- `issue-maintain` 処理フローを 12 → 13 ステップに拡張（概念ページ波及判定を追加）

## [1.22.0] - 2026-05-18

### Added
- `hooks/scripts/on-issue-change.sh` を Event Bus パターンに対応。FileChanged hook payload から変更ファイルを抽出し、`.claude/linear/*/issues/*.md` に `status: completed` が立った瞬間に `issue:completed` イベントを Event Bus（`.claude/events.jsonl`）に発行する
- `hooks/lib/safe-hook.sh` を v2026-05-18+ に同期。`event_bus_publish` / `event_bus_tail` / `event_bus_clear` API を取得（正本 `.claude-plugin/lib/safe-hook.sh` 由来）

### Notes
- Classmethod「Claude Code マルチエージェントオーケストレーションパターン」記事の Message Bus パターンをローカル実装する PoC publisher。将来 `retrospective` / `instinct-memory` 等の subscriber を追加できる土台

## [1.21.1] - 2026-05-15

### Changed
- `hooks/hooks.json` を `args[]` exec 形式へ移行（CC 2.1.139+）
- `safe-hook.sh` に `safe_hook_emit_bell` / `safe_hook_emit_window_title` を追加（CC 2.1.141+ terminalSequence 対応）

## [1.21.0] - 2026-05-12

### Added
- `issue-maintain` に**レビューガード**を追加 (#31 C)。Issue を `in-progress` → `completed` に遷移させる時、または完了サブタスク `[x]` が 3 件以上ある時に、本文・更新履歴に `self-review` / `code-review` 等のキーワードが含まれていない場合は `/self-review` 起動を提案する。feature-dev を経由しないケースでのレビュー素通り防止。type が `investigation` の Issue は実装を伴わないためスキップ
- `issue-maintain` に**スコープ外差分検出**を追加 (#31 D)。`git diff` で「スコープ外」「後続 Issue 候補」「やらないこと」セクションの追加箇条書き行を検出し、`/follow-up new` 候補として一括 / 個別 / スキップの 3 択で提示する。既存の follow-up 自動検知（会話中シグナル）とは独立した Issue ファイル更新タイミングでの差分検出軸
- `quality-checklist.md` §8「レビューガード」と §9「スコープ外差分検出」を新規追加（発火条件、検出キーワード、提示フォーマット、注意事項）

### Changed
- `issue-maintain` SKILL.md の処理フローを 11 → 12 ステップに拡張（スコープ外差分検出ステップを knowledge 切り出し直後に追加、タスク完了時フローにレビューガード適用判定を追記）
- `issue-maintain` SKILL.md / `commands/issue-maintain.md` の allowed-tools に `AskUserQuestion` を追加（レビューガード / スコープ外差分検出のユーザー提示のため）

## [1.20.0] - 2026-05-05

### Added
- `issue-maintain` の knowledge 切り出しに**破壊的変更パターン検出**を追加 (#31 A)。Issue 本文・進捗・更新履歴から「破壊的変更 / breaking change」「rename された / renamed to」「deprecated / 非推奨」「v\d+ → v\d+」「dead element / 空振り / lint は通るが」「衝突する / 配列順序」「実機テストで判明 / ランタイムで発覚」を Grep ベースで検出し、tags 候補（`library-compat`, `breaking-change`, `migration`, `gotcha`, `runtime-only`, `static-check-blind-spot` など）と共に y/n 提案する。ライブラリのバージョン跨ぎや実機検知バグといった再利用価値の高い知見の取りこぼしを防ぐ
- `quality-checklist.md` §5.1「破壊的変更パターンの自動検出」を新規追加（検出キーワード一覧、tags 対応表、ユーザー提示フォーマット）
- knowledge frontmatter に `updated: YYYY-MM-DD` フィールドを必須化 (#31 B 前提)。新規切り出し時は当日、編集時は必ず書き換える運用ルールを `quality-checklist.md` §6 に明記
- `session-start` Phase N3.7 に**鮮度判定（stale チェック）**を追加 (#31 B)。関連 knowledge の `updated` フィールドを読み取り、60 日以上経過していれば `⚠️ stale?` マーカーを付与して報告する。古い knowledge に引きずられて誤った設計を採るリスクを下げる（自動除外はせず、最終判断はユーザー）

### Changed
- `issue-maintain` SKILL.md の knowledge 切り出しフローを 6 ステップ → 7 ステップに拡張（破壊的変更検出を最優先ステップとして追加）。処理フローも 10 → 11 ステップに更新
- `quality-checklist.md` §6 の knowledge frontmatter 仕様に `updated` フィールドを追加。既存ファイルに `updated` がない場合は次回編集時に追加するルールに統一（遡及修正は不要）

## [1.19.0] - 2026-04-25

### Added
- Issue frontmatter に `related_knowledge:` / `feature_dev_plan:` フィールドを追加（feature / bugfix / investigation の 3 テンプレート、`feature_dev_plan:` は feature のみ）。Phase 2.5 で参照した knowledge と feature-dev が生成した計画ファイルへの逆リンクを保持する
- `issue-create` Phase 4 の feature-dev 連携を upfront 化。「はい」選択時に Issue メタデータ + Linear URL + Phase 2.5 関連 knowledge + 親 Issue サマリーを feature-dev に明示的に引き継ぐ prompt テンプレートを定義（Opus 4.7 の upfront specification 原則に整合）

## [1.18.4] - 2026-04-25

### Changed
- `session-start` Phase N3.5: Context Recovery Agent Team の起動指示を imperative 化（Opus 4.7 対応）。「同一メッセージ内で 3 エージェントを並列起動（逐次起動は禁止）」を明示し、各エージェントの入力も箇条書きで明示化

## [1.18.3] - 2026-04-20

### Changed
- Permission Pruning に基づく allowed-tools 削減 (#28)
  - `session-start`: 9 → 8（`mcp__linear__list_comments` を除去。該当処理は Agent subagent 側で完結）
  - `linear-maintain`: 11 → 10（`Write` を除去。既存ファイル更新のみで新規作成なし）
  - `linear-maintain`: 本文に `get_issue` / `list_issue_statuses` の明示参照を追加（14b 検証のため）

## [1.18.2] - 2026-04-19

### Changed
- hook スクリプト全般を `safe-hook.sh` 共通ラッパー経由に移行（check-deps / set-session-title / inject-rules / on-issue-change / on-knowledge-change） (#21)

## [1.18.1] - 2026-04-19

### Fixed
- `dashboard` スキル/コマンドの `allowed-tools` に `AskUserQuestion` を追加（本文で使用しているが未宣言だった）
- `knowledge` スキル/コマンドの `allowed-tools` に `AskUserQuestion` と `Bash` を追加（`git branch --show-current` と選択 UI のため）

## [1.18.0] - 2026-04-09

### Added
- knowledge スキル/コマンドを新規追加（`/knowledge [search <kw> | related]`）
- inject-rules.sh: SessionStart/PostCompact で knowledge/index.md をコンテキストに自動注入
- FileChanged hook: knowledge ファイルの変更を検知して通知
- project-rules.md に knowledge 活用ガイドを追加

## [1.17.0] - 2026-04-08

### Added
- UserPromptSubmit hook: feature ブランチから Issue タイトルを取得しセッション名に自動設定
- FileChanged hook: `.claude/linear/*/issues/*.md` の外部変更を検知して通知

## [1.16.0] - 2026-04-08

### Added
- linear-maintain: スキャンモード選択機能を追加（通常 / フルスキャン）
- フルスキャンモード: in-progress 含む全 Issue に issue-maintain の全処理フローを一括適用
- knowledge 重複排除ロジック（複数 Issue からの同一トピック候補をマージ）
- レポートに「Issue 品質整理」セクションを追加

## [1.15.1] - 2026-04-04

### Fixed
- session-start/issue-maintain スキルの description を 250 文字以内に短縮（v2.1.86 の上限対応）
- init スキルのパス参照を `${CLAUDE_PLUGIN_ROOT}` → `${CLAUDE_SKILL_DIR}` に最適化

## [1.15.0] - 2026-04-03

### Added
- follow-up スキル/コマンドを新規追加（`/follow-up new|list|promote`）
- 開発中の follow-up タスクを低摩擦で記録し、後から Issue に昇格する仕組み
- project-rules.md に follow-up 自動検知ルールを追加
- session-start: Quick Pick モードに follow-up 件数表示を追加
- dashboard: Phase D2.5 Follow-up サマリーを追加
- issue-maintain: タスク完了時に follow-up 棚卸し通知を追加
- linear-maintain: Follow-up 棚卸しフェーズを追加（14日以上放置の警告）

## [1.14.1] - 2026-03-31

### Changed
- SessionStart check-deps.sh に `once: true` 追加（セッション中1回のみ実行）
- 全エージェント（code-context, doc-resolver, linear-sync）に `maxTurns: 15` 追加（暴走防止）
- スキル内パス参照を `${CLAUDE_PLUGIN_ROOT}/skills/*/references/` → `${CLAUDE_SKILL_DIR}/references/` に最適化（7箇所）

## [1.14.0] - 2026-03-30

### Added
- 全 Linear MCP 使用スキル（init, dashboard, linear-maintain, issue-create, session-start）に Phase 0: MCP 利用可能性チェックを追加
- MCP 未検出時に AskUserQuestion で「続行 / 中断」を提示し、ユーザーが選択できるように

## [1.13.1] - 2026-03-30

### Changed
- doc-resolver, code-context, linear-sync エージェントのモデルを opus → sonnet に変更（情報収集タスクの effort 最適化）
- doc-resolver, code-context の effort を high → medium に変更

## [1.13.0] - 2026-03-29

### Changed
- issue-create: AskUserQuestion の呼び出し仕様を SKILL.md に直接埋め込み（テンプレート選択・feature-dev 連携）

### Removed
- rules/issue-create-interaction.md を削除（間接参照では LLM が AskUserQuestion を呼ばない問題の修正）
- inject-rules.sh から interaction.md の注入を削除

## [1.12.1] - 2026-03-29

### Fixed
- plugin.json から無効な agents フィールドを削除し manifest バリデーションエラーを修正

## [1.12.0] - 2026-03-29

### Added
- 全スキルに effort frontmatter を追加（session-start: high, dashboard: low, init: low, 他: medium）
- PostCompact hook: コンテキスト圧縮後にプロジェクトルールを再注入
- agents/ ディレクトリ: Context Recovery Agent Team を独立エージェント定義ファイルとして抽出（doc-resolver, code-context, linear-sync）
- plugin.json に agents フィールドを追加

## [1.11.0] - 2026-03-25

### Added
- dashboard: 新規スキル/コマンドとして切り出し（フルダッシュボード + スコープドダッシュボード）
- session-start: main ブランチ用 Quick Pick モード（軽量タスク選択）
- session-start: 親 Issue 軽量サマリーモード（詳細は `/dashboard` に委譲）

### Changed
- session-start: ダッシュボード機能を `/dashboard` に分離し、session-start を軽量化
- session-start: Context Recovery Agent Team に model: opus を明示指定

## [1.10.0] - 2026-03-24

### Added
- session-start: セッションコンテキスト書き出し（Phase CTX）を追加。Issue の設計判断を `.claude/session-context.md` に書き出し、code-review との連携を実現

## [1.9.0] - 2026-03-24

### Added
- session-start: Context Recovery Agent Team を追加（既存 Issue 再開時の深いコンテキスト復元）
- session-start: Doc Resolver エージェント（親 Issue・関連 Issue・Knowledge 参照解決）
- session-start: Code Context エージェント（ソースファイル参照解決 + Git 状態取得）
- session-start: Linear Sync エージェント（Linear API 最新状態との差分検出）
- session-start: allowed-tools に Agent, mcp__linear__list_comments を追加

## [1.8.0] - 2026-03-23

### Added
- SessionStart hook で外部依存チェック（Linear MCP、feature-dev プラグイン）を実行
- plugin.json に `_requirements` フィールドを追加（依存メタデータ宣言）

## [1.7.1] - 2026-03-23

### Fixed
- Linear API の書き込み（save_issue 等）をユーザーの明示的な指示なしに実行しないようルールを追加
- 「Issue更新」がローカル Issue ファイルの更新を意味することをスキル説明に明記

## [1.7.0] - 2026-03-23

### Added
- issue-create: テンプレート選択を AskUserQuestion による選択 UI に変更
- issue-create: feature-dev 連携案内を AskUserQuestion による選択 UI に変更
- rules/issue-create-interaction.md を新規追加（SessionStart hook で注入）

## [1.6.0] - 2026-03-23

### Added
- session-start: ダッシュボードモードを追加（フル / スコープド）
- session-start: Next Issue ピック機能を追加
- session-start: allowed-tools に mcp__linear__list_issues を追加

## [1.5.0] - 2026-03-22

### Added
- knowledge retrieval フローを追加
- feature-dev 連携案内と Agent Team ルールを追加

## [1.4.0] - 2026-03-21

### Added
- init コマンドを追加

## [1.3.0] - 2026-03-20

### Added
- SessionStart hook によるプロジェクト管理ルール自動注入を追加

## [1.2.0] - 2026-03-20

### Added
- CLAUDE.md 軽量化に向けたスキル強化

### Fixed
- プラグイン品質改善
- プロジェクト固有の情報を汎用的な例に置換
- スキルのトリガーフレーズを改善
- 全プラグインの品質問題を一括修正

## [1.0.0] - 2026-03-20

### Added
- linear-workflow プラグインを新規作成
- Linear MCP 連携の Issue/プロジェクト管理機能
