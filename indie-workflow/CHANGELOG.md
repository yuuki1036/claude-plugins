# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.14.0] - 2026-04-09

### Added
- knowledge スキル/コマンドを新規追加（`/knowledge [search <kw> | related]`）
- inject-rules.sh: SessionStart/PostCompact で knowledge/index.md をコンテキストに自動注入
- FileChanged hook: knowledge ファイルの変更を検知して通知
- project-rules.md に knowledge 活用ガイドを追加

## [1.13.0] - 2026-04-08

### Added
- UserPromptSubmit hook: feature ブランチから Issue タイトルを取得しセッション名に自動設定
- FileChanged hook: `.claude/indie/*/issues/*.md` の外部変更を検知して通知

## [1.12.0] - 2026-04-08

### Added
- indie-maintain: スキャンモード選択機能を追加（通常 / フルスキャン）
- フルスキャンモード: in-progress 含む全 Issue に indie-issue-maintain の全処理フローを一括適用
- knowledge 重複排除ロジック（複数 Issue からの同一トピック候補をマージ）
- レポートに「Issue 品質整理」セクションを追加

## [1.11.0] - 2026-04-03

### Added
- indie-follow-up スキル/コマンドを新規追加（`/indie-follow-up new|list|promote`）
- 開発中の follow-up タスクを低摩擦で記録し、後から Issue に昇格する仕組み
- project-rules.md に follow-up 自動検知ルールを追加
- indie-start: ダッシュボードモードに follow-up 件数表示を追加
- indie-start: Feature ブランチモードに follow-up 通知を追加
- indie-issue-maintain: タスク完了時に follow-up 棚卸し通知を追加
- indie-maintain: Follow-up 棚卸しフェーズを追加（14日以上放置の警告）

## [1.10.2] - 2026-03-31

### Changed
- SessionStart check-deps.sh に `once: true` 追加（セッション中1回のみ実行）
- 全エージェント（code-context, doc-resolver）に `maxTurns: 15` 追加（暴走防止）
- スキル内パス参照を `${CLAUDE_PLUGIN_ROOT}/skills/*/references/` → `${CLAUDE_SKILL_DIR}/references/` に最適化（6箇所）

## [1.10.1] - 2026-03-30

### Changed
- doc-resolver, code-context エージェントのモデルを opus → sonnet、effort を high → medium に変更（情報収集タスクの effort 最適化）

## [1.10.0] - 2026-03-29

### Changed
- indie-issue-create: AskUserQuestion の呼び出し仕様を SKILL.md に直接埋め込み（テンプレート選択・scope_size・feature-dev 連携）

### Removed
- rules/issue-create-interaction.md を削除（間接参照では LLM が AskUserQuestion を呼ばない問題の修正）
- inject-rules.sh から interaction.md の注入を削除

## [1.9.1] - 2026-03-29

### Fixed
- plugin.json から無効な agents フィールドを削除し manifest バリデーションエラーを修正

## [1.9.0] - 2026-03-29

### Added
- 全スキルに effort frontmatter を追加（indie-start/retrospective: high, indie-init: low, 他: medium）
- PostCompact hook: コンテキスト圧縮後にプロジェクトルールを再注入
- agents/ ディレクトリ: Context Recovery Agent Team を独立エージェント定義ファイルとして抽出（doc-resolver, code-context）
- plugin.json に agents フィールドを追加

## [1.8.1] - 2026-03-25

### Changed
- indie-start: Context Recovery Agent Team に model: opus を明示指定

## [1.8.0] - 2026-03-24

### Added
- indie-start: セッションコンテキスト書き出し（Phase CTX）を追加。Issue の設計判断を `.claude/session-context.md` に書き出し、code-review との連携を実現

## [1.7.0] - 2026-03-24

### Added
- indie-start: Context Recovery Agent Team を追加（既存 Issue 再開時の深いコンテキスト復元）
- indie-start: Doc Resolver エージェント（関連 Issue・Knowledge 参照解決）
- indie-start: Code Context エージェント（ソースファイル参照解決 + Git 状態取得）
- indie-start: allowed-tools に Agent を追加

## [1.6.0] - 2026-03-23

### Added
- SessionStart hook で外部依存チェック（feature-dev プラグイン）を実行
- plugin.json に `_requirements` フィールドを追加（依存メタデータ宣言）

## [1.5.0] - 2026-03-23

### Added
- indie-issue-create: テンプレート選択を AskUserQuestion による選択 UI に変更
- indie-issue-create: scope_size 選択を AskUserQuestion による選択 UI に変更
- indie-issue-create: feature-dev 連携案内を AskUserQuestion による選択 UI に変更
- rules/issue-create-interaction.md を新規追加（SessionStart hook で注入）

## [1.4.0] - 2026-03-22

### Added
- knowledge retrieval フローを追加
- feature-dev 連携案内と Agent Team ルールを追加

## [1.3.0] - 2026-03-21

### Added
- init コマンドを追加

## [1.2.0] - 2026-03-21

### Changed
- スキル名をリネームし linear-workflow との競合を解消

## [1.0.0] - 2026-03-20

### Added
- indie-workflow プラグインを新規作成
- 個人開発向けローカル Issue 管理機能
