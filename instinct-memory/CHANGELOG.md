# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.2.3] - 2026-04-22

### Changed
- instinct-learning スキルおよび learn / instinct-promote コマンドに「Generator / Evaluator 分離」設計原則を明記。パターン抽出と MEMORY.md 昇格判定を別コンテキストで実行する意図を明示 (#27)

## [1.2.2] - 2026-04-19

### Changed
- hook スクリプトを `safe-hook.sh` 共通ラッパー経由に移行（stdin 消費・エラー分類・名前付きログの統一） (#21)

## [1.2.1] - 2026-03-31

### Changed
- Stop hook（session-review.sh）に `async: true` 追加（セッション終了をブロックしない非同期実行）

## [1.2.0] - 2026-03-29

### Added
- PostCompact hook: コンテキスト圧縮後に instincts を再注入し、長いセッションでのパターン学習を維持
- 全スキルに effort frontmatter を追加（instinct-learning: medium）

## [1.1.1] - 2026-03-23

### Fixed
- スキル description のトリガーフレーズを「トリガー:」形式に統一

## [1.1.0] - 2026-03-21

### Fixed
- プラグイン品質改善
- 全プラグインの品質問題を一括修正

## [1.0.0] - 2026-03-20

### Added
- instinct-memory プラグインを新規作成
- セッション中のパターン学習と auto memory 管理機能
