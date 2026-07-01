# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [0.3.0] - 2026-07-01

### Added
- `design-review` に **Phase 4.5「反証（敵対的独立検証）」**を新設（`high` effort 以上）。集約後の BLOCKER / MAJOR finding を、元 reviewer の suggestion / rationale を渡さず独立 agent に反証させ、過剰指摘（偽陽性）を落とす（Clearwing 原則 7）。反証された finding は severity を下げるかレポートで明示、BLOCKER は fail-closed で消さず「反証あり（要判断）」注記。反証 agent は 1 体・1 ラウンドの暴走ガード付き
- `design-reviewer` agent の finding schema に `confidence: 0-100` を追加。Phase 4 集約で confidence < 50 を MINOR 降格（過剰指摘の抑制。BLOCKER は例外で残す）。複数視点が独立に同じ指摘を挙げたら confidence 引き上げ

### Changed
- `design-reviewer` agent に `model: opus` を明示（従来は親から継承＝指定漏れ。モデルルーティング規約: レビュー役は強モデル。ルート CLAUDE.md「コスト×精度パイプライン設計指針」準拠）
- Phase 4 集約表に confidence 列・反証列を追加

## [0.2.3] - 2026-06-25

### Changed
- CHANGELOG.md 冒頭に Keep a Changelog 宣言行を追加（他プラグインと形式統一）

## [0.2.2] - 2026-06-15

### Changed

- supersede フローに **実行前の最終確認 (AskUserQuestion)** を追加。旧 doc の id / title / 現 status を提示してから実行し、誤った old-id 指定による別 doc の巻き込みを防ぐ（新規作成フローの既存 doc 検出時の確認とあった非対称を解消）

## [0.2.1] - 2026-06-11

### Changed

- README の export API 説明を「想定」から実呼び出し元（feature-dev v2.7.0+ Phase 4.5 / indie・linear issue-design の昇格導線）に更新

## [0.2.0] - 2026-06-11

### Added

- `design-review` スキル + `/design-review` コマンド（design doc の複数視点静的レビュー）
- `design-reviewer` agent（minimal / clean / pragmatic / risk の 1 視点を担当、evidence-first で findings を返す）
- 視点定義の正本 `references/review-perspectives.md`（effort 別構成: low/medium → メイン 2 視点 / high → agent ×3 / xhigh,max → agent ×4、`--focus` で単一視点指定）
- findings の doc 反映フロー（open 追記 / 設計判断ログ追記 / 本文修正 + last-validated 更新、採否は AskUserQuestion）

## [0.1.0] - 2026-06-11

### Added

- `design-doc` スキル + `/design-doc` コマンド（new / list / supersede / export）
- grill 3 原則による前提確定（grill-protocol.md は feature-dev 正本の byte-identical 複製）
- 代替案トレードオフ比較 → 採用案を `.claude/designs/<YYYYMMDD>-<slug>.md` に永続化
- 実装ブリッジ (Implementation Bridge) セクション必須化（死に文書化防止）
- supersede 機械化（新規作成 + 旧 doc 4 箇所更新 + 相互参照検証、adr-keeper と同機構）
- doc-freshness 互換 frontmatter（last-validated / phase: target→current→superseded）
- dormant 連携: bdd-spec（spec.md を WHAT 入力に）/ adr-keeper（[→ADR候補] 切り出し）/ writing-polish（散文推敲）
- export 非対話 API（他プラグインからの doc 化、feature-dev 連携想定）
