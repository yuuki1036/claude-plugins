# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

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
