# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

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
