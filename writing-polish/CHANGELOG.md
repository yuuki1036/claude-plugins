# Changelog

このプロジェクトのすべての注目すべき変更を記録する。

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に準拠し、
[Semantic Versioning](https://semver.org/lang/ja/) に従う。

## [0.1.0] - 2026-06-03

### Added

- `writing-polish` スキル: 文章を語句レベルで推敲・添削する。最小差分の diff 提示 → 採否フロー。RFC / Issue / PR 本文 / コミットメッセージ / レビューコメント対応、日英両対応
- `/writing-polish` コマンド: スキルのスラッシュコマンド版。`--embed` / `--tone` / `--aggressive` オプション対応
- `references/tone-guide.md`（校正ルール正本 / SSOT）: textlint（preset-ja-technical-writing / japanese / ai-writing / JTF-style）と Vale の 11 チェックタイプ、Google / Microsoft style guide を統合したカテゴリ分類。文体メタルール（文書種別で敬体/常体を使い分け）、6 カテゴリ、過剰修正アンチパターンを収録
- 中核原則として over-correction（過剰修正）抑制を採用（一次研究 arXiv 2512.12544 HyperEdit / 2502.13358 FineEdit 由来）
- `--embed` による他プラグインからの soft 委譲インターフェース（POLISH_RESULT マーカー付き機械可読返却）
