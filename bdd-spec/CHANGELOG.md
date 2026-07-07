# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [0.2.0] - 2026-07-07

### Added
- **`evaluate-spec` スキル + `bdd-spec-evaluate` コマンドを新設**（Phase 2 予約分の実装。GitHub issue #78）。埋めた spec.md / epic.md を 4 観点で静的レビューする品質ゲート:
  - **Gherkin 構文妥当性**（機械・ファネル第 1 段）: Feature/Scenario の Given-When-Then 構造・Scenario Outline の Examples・`<placeholder>` と列見出しの対応・フェンス開閉を grep で確定判定
  - **粒度一貫性**（意味）: When の単一アクション性・Then が実装詳細に踏み込んでいないか・1 Scenario 1 振る舞い
  - **網羅性**: 同値分割表 ⇔ Scenario の**双方向トレース**（表にあるのに未カバーの同値クラス / 表にない orphan scenario を検出）
  - **トレーサビリティ**: epic の AC ⇔ Scenario リンク解決・未カバー AC 検出・Why が Scenario 群で満たされるかの意味判断
- severity（🔴/🟡/🔵）× confidence（機械判定は 100、意味判断は不確実性に応じて 0-100）でフィルタ。機械判定をファネル第 1 段に置き、意味判断（LLM）を後段に回す（コスト×精度原則 1/8/10）
- **`${CLAUDE_EFFORT}` 実行時分岐**: low/medium=機械判定に絞る、high=全 4 観点、xhigh/max=依存 spec 横断・境界値精査・Why 十分性まで
- **scaffold ゲート**: プレースホルダだらけの空骨格は観点 1 のみ評価し、観点 2-4 は「埋めてから再実行」と案内（空骨格に網羅性を問うノイズを防ぐ）
- 修正は confidence 100 の機械確定分のみ AskUserQuestion 承認後に自動化（over-correction 抑制）
- `feature-dev` Phase 1.4 への dormant 連携用に安定 API（`spec=<path>` / `--embed`）を提供
- `create-spec`（Generator）と `evaluate-spec`（Evaluator）を責務分離（生成時の思い込みに引きずられず独立に穴を見つける）

## [0.1.2] - 2026-07-02

### Fixed
- **`allowed-tools` に `Bash` を復帰**（v0.1.1 で削除したが、全テンプレが `last-validated: {CREATED_DATE}` を要求しており日付取得手段が無くなっていた）。Phase 4 で `date +%Y-%m-%d` を取得して epic.md / spec.md の `last-validated` に入れる手順を明記。姉妹プラグイン adr-keeper / design-doc と同じ「日付は Bash で取得、擬似日付を作らない」規律に統一（command / skill のペアで一致）
- **`spec-template.md` / `common-spec-template.md` の外側フェンスをチルダ (`~~~`) 化**。内側の ```` ```gherkin ```` バッククォートフェンスがネストし、CommonMark 上で外側の ```` ```markdown ```` が早期に閉じてテンプレ本文の境界が壊れていた不具合を修正
- 未使用の `Grep` を `allowed-tools` から削除（scaffold は Read / Write / Edit / Glob / Bash で完結。allowed-tools 最小性 #14b）

### Changed
- scaffold 直後の stale 回避を SKILL.md Phase 5 に明記: epic.md / spec.md は `phase: current` で開始するが doc-freshness の grace period（新規 doc 保護、デフォルト 7 日）で守られる。spec は「埋めて育てる生きた文書」なので ADR のような `append_only` 免除は付けない
- 将来の評価系スキルの名称を `bdd-spec-evaluate` に統一（SKILL.md 内の `evaluate-spec` 表記を解消）。プラグインロードマップの「Phase 2」と処理フローの「Phase 2」の紛らわしさを注記で明確化
- README のスコープ記述を実態に統一（現状は scaffold のみ。静的構文レビューは `bdd-spec-evaluate` として将来リリースで追加予定）

## [0.1.1] - 2026-06-01

### Changed

- `skills/create-spec/SKILL.md` と `commands/bdd-spec-create.md` の `allowed-tools` から未使用の `Bash` を削除（allowed-tools 最小性 #14b）。scaffold は Read/Write/Edit/Glob で完結し、ディレクトリ作成は Write が親 dir を生成するため Bash 不要

## [0.1.0] - 2026-05-29

### Added
- **初版リリース** (#49)。Phase 1 として `bdd-spec-create` command + `create-spec` skill のみ実装。`bdd-spec-evaluate` は Phase 2 で別途検討
- `commands/bdd-spec-create.md`: user story dir + epic.md + spec.md scaffold
- `skills/create-spec/SKILL.md`: ヒアリング → dir 名決定 → template 流し込み → all_spec.md 用語整合チェックの処理フロー
- `references/story-naming.md`: 日本語フルパス / 短縮モード（`{role}-{verb}-{object}`）の切替と命名規約
- `references/epic-template.md`: Why / What を散文で書く 〜2KB 想定の epic.md テンプレ
- `references/spec-template.md`: BDD Feature / Scenario / Examples + 同値分割表 を含む 〜13KB 想定の spec.md テンプレ
- `references/glossary-ssot.md`: 用語 SSoT（`all_spec.md`）と別名禁止メタルール
- `references/common-spec-template.md`: 横断 Background / 権限・閾値・エラーメッセージのデフォルトを記述する `common_spec.md` テンプレ

### Notes
- 短縮モード（`.claude/bdd-spec.json` で `shortPath: true`）は Windows MAX_PATH / CI 互換のため
- 既存の評価系 skill（spec-evaluator など）とは責務分離。本 plugin は scaffold に専念
- `feature-dev` からの `Skill bdd-spec:create-spec` 呼び出しに対応する API を安定化
