# Changelog

spec-advisor の変更履歴。[Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) 形式、[SemVer](https://semver.org/lang/ja/) に従う。

## [0.1.0] - 2026-07-08

### Added
- 初版。開発タスクから設計・計画系成果物（WHAT=bdd-spec / HOW=design-doc / WHY=adr-keeper / Issue粒度=issue-design / 実装一気通貫=feature-dev）を判定する `spec-advise` skill と `/spec-advise` command。
- 判定の SSoT `skills/spec-advise/references/routing-rubric.md`（5 軸モデル + over-suggestion guard を先頭に置くファネル + signal 表 + 組み合わせ例 + dormant 判定 + effort 分岐）。
- SessionStart hook（`hooks/scripts/inject-advisor-rule.sh`）で ambient ルール（`rules/advisor-rule.md`）を注入。対象の設計プラグインが 1 つも未導入なら inert（noise 抑制）。
- 連携先はすべて optional（`_requirements` を持たず、skill / hook 内の grep で dormant 判定）。プラグイン独立。
