# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [0.1.0] - 2026-05-29

### Added
- **初版リリース** (#48)。Phase 1 として command + skill のみ実装。hook 連動は Phase 2 で別途検討
- `commands/doc-freshness-check.md`: プロジェクト全体または指定ファイルの鮮度走査
- `skills/doc-freshness/SKILL.md`: frontmatter スキーマ検証 / phase 別 stale 判定 / 行数ガード / internal link 検証 / superseded 参照禁止 / 新規 doc grace period
- `references/frontmatter-spec.md`: `last-validated` / `phase` の定義と運用ルール
- `references/thresholds.md`: 閾値のデフォルト値と上書き方法

### Notes
- PreToolUse hook は採用しない設計（新規 doc 作成時の failure mode を回避）
- knowledge-lint との責務分離（broken wikilink / orphan は knowledge-lint 側）
