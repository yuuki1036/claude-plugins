# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

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
