# Changelog

spec-advisor の変更履歴。[Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) 形式、[SemVer](https://semver.org/lang/ja/) に従う。

## [0.1.3] - 2026-07-16

### Changed
- `spec-advise` skill の description から over-suggestion guard / dormant 判定の内部機構説明を削除し SKILL.md 本文へ集約（常駐コンテキスト削減）。判断軸（WHAT/HOW/WHY/Issue粒度/実装）+ トリガーは維持（eval pass^k=3 で非退行を確認）。

## [0.1.2] - 2026-07-14

### Fixed
- **`allowed-tools` をカンマ区切り文字列から YAML リスト形式に修正**（`commands/spec-advise.md` / `skills/spec-advise/SKILL.md`）。ルート CLAUDE.md の記法規約（YAML リスト形式）に反しており、`/quality-check` の「allowed-tools フォーマット統一チェック」で Warning となっていた。ツール構成（`Skill` / `AskUserQuestion` / `Bash` / `Read` / `Grep`）は変更なく、command ↔ skill のペア一致も維持。挙動に影響しない記法の正規化

## [0.1.1] - 2026-07-08

### Changed
- `routing-rubric.md` の signal 表を再構成: WHAT/HOW/WHY の 3 軸コアを `ROUTING-AXES:START/END` マーカー区間として正本 `.claude-plugin/lib/routing-axes.md` と同期（quality-check が dedent 比較で Critical 検証）。Issue 粒度 / 実装の 2 軸は「spec-advisor 固有の拡張軸」表に分離（同期対象外）。冒頭の「SSoT の現状」注記を新機構（正本 + byte-identical 複製）の説明に更新（設計判断: `.claude/designs/20260708-spec-routing-ssot.md`）

## [0.1.0] - 2026-07-08

### Added
- 初版。開発タスクから設計・計画系成果物（WHAT=bdd-spec / HOW=design-doc / WHY=adr-keeper / Issue粒度=issue-design / 実装一気通貫=feature-dev）を判定する `spec-advise` skill と `/spec-advise` command。
- 判定の SSoT `skills/spec-advise/references/routing-rubric.md`（5 軸モデル + over-suggestion guard を先頭に置くファネル + signal 表 + 組み合わせ例 + dormant 判定 + effort 分岐）。
- SessionStart hook（`hooks/scripts/inject-advisor-rule.sh`）で ambient ルール（`rules/advisor-rule.md`）を注入。対象の設計プラグインが 1 つも未導入なら inert（noise 抑制）。
- 連携先はすべて optional（`_requirements` を持たず、skill / hook 内の grep で dormant 判定）。プラグイン独立。
