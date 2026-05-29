# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

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
