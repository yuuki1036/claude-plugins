# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

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
