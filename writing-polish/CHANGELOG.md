# Changelog

このプロジェクトのすべての注目すべき変更を記録する。

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に準拠し、
[Semantic Versioning](https://semver.org/lang/ja/) に従う。

## [0.3.0] - 2026-06-09

### Added

- textlint 実行連携（任意・required:false）。`references/linter-integration.md` に連携手順、`references/textlintrc.json` に同梱 config。`command -v textlint` で存在チェックし未導入時は LLM 判定にフォールバック。SKILL/command の allowed-tools に Bash 追加、plugin.json に `_requirements`（textlint, required:false）

### Changed

- tone-guide「委譲境界」を textlint 実行委譲に合わせて更新（未導入時の LLM フォールバックを明記）

## [0.2.0] - 2026-06-09

### Added

- tone-guide カテゴリ 7「平易性 / 過剰抽象（over-abstraction）」: 語彙の抽象度を見る検出軸。具体例が並ぶ文脈の抽象漢語・動作を隠す名詞化（軽動詞構文）・借り物の荘厳さ・density 判定で発火を構造的に絞り、専門用語を残す 3 条件で over-correction を回避（GitHub Issue #70。既存カテゴリ 2 は口語曖昧、4 は「語彙を縛らない」、5 は測定可能性に閉じており抽象漢語がどのレバーにも掛からなかった穴を埋める）
- カテゴリ 4（AI っぽさ）に構文 tell を追加: negative parallelism（「〜ではなく〜だ」の濫用）・三点強迫・総括の宣言
- 「textlint / Vale 委譲境界」セクション: 決定的に拾える観点（表記・文法・確実な冗長構文・しきい値・差別語）は linter、文脈判断（名詞化の良性/悪性・衒学語の言い換え・ヘッジ採否・AI っぽさの density 判断）は LLM が担う棲み分けを明文化

### Changed

- カテゴリ 7 と構文 tell は high/xhigh/max effort 限定で発火（low/medium の速度・安全性を維持し、over-correction リスクの高い観点を浅い effort で暴発させない）

## [0.1.0] - 2026-06-03

### Added

- `writing-polish` スキル: 文章を語句レベルで推敲・添削する。最小差分の diff 提示 → 採否フロー。RFC / Issue / PR 本文 / コミットメッセージ / レビューコメント対応、日英両対応
- `/writing-polish` コマンド: スキルのスラッシュコマンド版。`--embed` / `--tone` / `--aggressive` オプション対応
- `references/tone-guide.md`（校正ルール正本 / SSOT）: textlint（preset-ja-technical-writing / japanese / ai-writing / JTF-style）と Vale の 11 チェックタイプ、Google / Microsoft style guide を統合したカテゴリ分類。文体メタルール（文書種別で敬体/常体を使い分け）、6 カテゴリ、過剰修正アンチパターンを収録
- 中核原則として over-correction（過剰修正）抑制を採用（一次研究 arXiv 2512.12544 HyperEdit / 2502.13358 FineEdit 由来）
- `--embed` による他プラグインからの soft 委譲インターフェース（POLISH_RESULT マーカー付き機械可読返却）
