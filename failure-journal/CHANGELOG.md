# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [0.1.2] - 2026-07-02

### Fixed

- log-failure の `failure:logged` publish スニペットが `SAFE_HOOK_NAME` 未設定で `"plugin":"unknown"` を書いていた問題を修正（source 直後に `SAFE_HOOK_NAME="failure-journal"` を設定するよう `skills/log-failure/SKILL.md` / `references/journal-schema.md` を修正）
- `hooks/scripts/session-start-init.sh` の journal ディレクトリ基準を Event Bus 正本と揃え、相対パス `.claude/failure-journal` を `${CLAUDE_PROJECT_DIR:-$PWD}/.claude/failure-journal` に変更
- `README.md` の「並行 install 可能」と「混ぜると壊れる」が矛盾していた編集残骸を修正

### Changed

- tag 長さ規約を「20 文字以内」から「30 文字以内」に緩和し、正準例 `spec-skipped-without-rationale`（30 字）と整合させた。`journal-schema.md` の自己矛盾（修正例が 20 字超で「※20字超なら更に短縮」と自己言及）も解消（`SKILL.md` / `README.md` / `commands/log-failure.md` / `references/journal-schema.md`）
- retro の allowed-tools から未使用の `Grep` を削除（`skills/retro/SKILL.md` / `commands/retro.md` のペア一致）

## [0.1.1] - 2026-06-15

### Changed

- `hooks/lib/safe-hook.sh` を正本に同期（additionalContext 注入 helper `safe_hook_emit_context` 追加に伴う byte-identical 複製の更新）

## [0.1.0] - 2026-05-29

### Added
- **初版リリース** (#47)。再発する失敗の fingerprint 集計 + retro 自動還流を提供する Phase 1 実装
- `commands/log-failure.md` + `skills/log-failure/SKILL.md`: 再発しうる失敗を JSON Lines に append（単一基準「再発しうるか」/ tag は kebab-case 20 字以内・固有名詞禁止・現象主体 / append-only / `failure:logged` event publish）
- `commands/retro.md` + `skills/retro/SKILL.md`: 直近 30 日で同一 tag が 3 回以上再発したパターンを抽出し、AGENTS.md/CLAUDE.md・hook・skill への還流先を提案
- `skills/log-failure/references/journal-schema.md`: JSON Lines スキーマ / append 手順 / tag 規約
- `skills/retro/references/aggregation-rules.md`: 集計窓・閾値・jq 集計コマンド（macOS/Linux 両対応）/ 還流先判定ルール
- `hooks/`: SessionStart hook で journal ディレクトリ（`.claude/failure-journal/`）と `journal.jsonl` を初期化

### Notes
- `indie-workflow:retrospective`（主観的なセッション振り返り）とは責務が異なり、並行 install 可能
- journal (`.claude/failure-journal/journal.jsonl`) は gitignore 推奨。journal の Read は retro 実行中のみ（fingerprint の AI 出力汚染を回避）
