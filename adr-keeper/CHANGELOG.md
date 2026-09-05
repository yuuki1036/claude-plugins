# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [0.3.1] - 2026-09-05

### Fixed

- **同名 command の description に `トリガー:` を複製した**（GitHub issue #206）。command 名と skill 名が
  同名だと、スキル選択の一覧に載るのは `commands/*.md` の description だけで **`SKILL.md` 側は
  router に届かない**。`トリガー:` 必須の規約は SKILL.md にだけ掛かっていたので、字面は通るが
  ルーティングには効いていなかった。対象: `adr`。
  - **移動ではなく複製**（SKILL.md 側は残す） — `check_router_trigger_drift` が SKILL.md の
    `トリガー:` を入力にしており、移動するとその機械ガードが沈黙する
  - 引用符なしの description に `トリガー:` を足すと YAML の `key: value` と解釈されて frontmatter が
    壊れるので、二重引用符で囲んだ（既存の書式に揃えた）
  - `validate_plugin_quality.py` が同名ペアの commands 側にも `トリガー:` 必須を error で強制する
    （`[trigger-cmd]`）

## [0.3.0] - 2026-07-29

### Added
- **Phase 3 (new) に記録価値の 3 条件セルフゲートを追加**（mattpocock/skills の domain-modeling「Offer ADRs sparingly」を翻案）。①覆すコストが大きい ②文脈なしでは不可解 ③実在したトレードオフの結果 — の 3 条件を書く前に自問し、1 つでも欠けたら AskUserQuestion で 1 回だけ確認する（推奨は「記録しない」= design doc の決定事項・knowledge 等の軽い置き場）。従来 `/adr new` 直接起動には抑止が一切なく、ゲートは spec-advisor の WHY 軸ルーティング判定と design-doc の `[→ADR候補]` マーカーに外在していた。supersede（Phase 4）経由の新 ADR 作成にはゲートを適用しない（覆される決定の存在自体が 3 条件の充足を示すため）。目的は ADR の希釈防止

## [0.2.2] - 2026-07-23

### Fixed
- **SKILL.md の doc-freshness 閾値参照から具体値（5 日）を除去**（doc-freshness 0.5.0 で current 閾値が 60 日 warn に変わり数値が stale 化するため、閾値非依存の記述に変更。append_only 免除の論旨は不変）

## [0.2.1] - 2026-07-23

### Changed
- **allowed-tools から未使用の Grep を削除**（skill / command の両方。全フロー（list / new / supersede）が Glob + Read + Bash + Write + Edit で完結しており内容検索の場面がない。/quality-check の最小性チェックで検出）

## [0.2.0] - 2026-07-02

### Added
- **テンプレに `append_only: true` frontmatter を追加**。ADR は決定時点の記録を append-only で残す履歴文書のため、doc-freshness v0.2.0+ にこのマーカーで stale 判定を免除させる。`phase: current` の stale 閾値（5 日）を当てると作成 5 日後から恒常 stale error になり鮮度 lint 委譲が破綻していた構図を解消（`references/template.md` / `references/examples.md` の記入例にも反映）
- `plugin.json` `_requirements` に `doc-freshness`（`required: false`）を宣言。ADR の鮮度 lint を委譲する soft 依存を明示（hooks 非所持プラグインのため check-deps.sh は不要）
- `references/template.md` の「## 関連」に **design doc 行**を追加（design-doc Phase 6 が ADR 側に元 doc パスを相互リンクする想定と整合）

### Changed
- supersede 時の旧 ADR 更新の記述を「2 箇所更新」→「4 フィールド更新（status / phase / superseded-by / last-validated）」に統一（SKILL.md 複数箇所・commands/adr.md・plugin.json description。実手順は当初から 4 フィールドで、記述だけが古い「2 箇所」のままだった不整合を修正）
- `SKILL.md` の ADR id 例を T 区切り（`20260529T143012`）から `references/naming.md` 正の T なし（`20260529143012`）に修正

## [0.1.2] - 2026-06-15

### Changed

- `skills/adr/SKILL.md` Phase 4 に **supersede 実行前の最終確認 (AskUserQuestion)** を追加。旧 ADR の id / title / 現 status を提示してから実行し、誤った old-id 指定による別 ADR の巻き込みを防ぐ（後戻りしにくい破壊的操作の安全ガード）

## [0.1.1] - 2026-06-01

### Changed

- `skills/adr/SKILL.md` Phase 3 に **AskUserQuestion の inline 呼び出し仕様**を追記（allowed-tools 最小性 #14b の規約準拠）。ADR の status（accepted / proposed）確定を素のプロンプトから選択 UI に変更し、宣言済みツールと実装を一致させる

## [0.1.0] - 2026-05-29

### Added
- **初版リリース** (#46)。設計判断 (ADR) を append-only で蓄積する command + skill を実装
- `commands/adr.md`: `list` / `new <title>` / `supersede <old-id> <new-title>` の 3 サブコマンド
- `skills/adr/SKILL.md`: 保存先確認 / サブコマンド判定 / 一覧表示 / 新規作成 / supersede（新規作成 + 旧 ADR 2 箇所更新 + 相互参照確認）
- `skills/adr/references/template.md`: ADR 本文テンプレ + frontmatter 雛形（適用方法 (Enforcement) セクション必須）
- `skills/adr/references/naming.md`: `YYYYMMDDhhmmss` 秒精度命名規約と衝突回避の理由
- `skills/adr/references/examples.md`: 機械強制できる / できない決定の記入例

### Notes
- タイムスタンプは Bash `date +%Y%m%d%H%M%S` で取得（秒精度で衝突回避）
- frontmatter は doc-freshness と互換（`last-validated` / `phase`）。鮮度 lint は doc-freshness 側が担う
- 適用方法 (Enforcement) セクション必須化により死に文書化を予防
