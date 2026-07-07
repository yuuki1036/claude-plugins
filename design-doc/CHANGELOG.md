# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [0.4.1] - 2026-07-07

### Changed
- `design-review` SKILL.md に **コスト×精度パイプライン 10 原則の採用/不採用宣言を追加**（ルート CLAUDE.md 規約への準拠）。採用: 2（severity × confidence）/ 3（effort→視点数）/ 4（design-reviewer:opus）/ 7（Phase 4.5 独立反証）/ 10（confidence 必須）。捨てた: 1 / 5 / 6 / 8（単一 doc 対象・単発レビュー・機械オラクル不在のため）。実装済みの挙動を宣言として明文化したもので挙動の変更なし

## [0.4.0] - 2026-07-02

### Added
- `design-reviewer` agent に **verification mode（反証）の入出力契約**を明記。従来は perspective（minimal/clean/pragmatic/risk）モードの契約しか無く、design-review Phase 4.5 が渡す「perspective なし・中立プロンプト・支持/反証/保留 で返す」反証モードが agent 定義に未対応だった。2 モード（perspective / verification）を明示し、それぞれの Input contract / Output format / Rules を定義。description も 2 モード対応に更新
- `plugin.json` `_requirements` に `doc-freshness`（`required: false`）を宣言。design doc の鮮度 lint を委譲する soft 依存を明示（他の soft 依存 bdd-spec/adr-keeper/writing-polish は宣言済みだった。hooks 非所持プラグインのため check-deps.sh は不要）

### Changed
- **export の指定方法を `mode=export` に一本化**（Phase 0 サブコマンド表・`commands/design-doc.md`）。呼び出し元の feature-dev / issue-design が `mode=export` を渡すのに対し、Phase 0 表は先頭語 `export` 形式を併記していた齟齬を解消。先頭語 `export ...` も後方互換で受理する旨を明記
- **Phase 6 の ADR 相互リンク追記を「Write/Edit は `.claude/designs/` のみ」規律の明示的な例外として許可**。切り出した ADR ファイル（`.claude/adr/*.md`）の「関連」該当行のみ Edit してよいと SKILL 本文・注意事項に追記（規律文との矛盾を解消）
- `commands/design-review.md` の処理フローを skill 実装（Phase 4.5 反証 + confidence フィルタ）に同期。design-review Phase 3 / 4.5 に agent 起動モード（perspective / verification）を明示
- README の design-review 節に **confidence フィルタ + 反証 phase（v0.3.0+）** の説明を追記

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
