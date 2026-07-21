# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [0.2.0] - 2026-07-21

### Added

- **retro に Phase 0.5「未起票失敗のサルベージ」を追加**。transcript (`~/.claude/projects/<slug>/*.jsonl`) を集計窓と同じ期間で走査し、Claude の自己訂正シグナルを grep 検知 → LLM で REAL/NOISE 分類 → 承認を経て journal に append する。手動起票の取りこぼしを retro 実行時にまとめて回収する
- `skills/retro/references/transcript-salvage.md` — 走査手順・precision・重複排除・制約（無言修正は拾えない / 日本語正規表現前提 / マシンローカル）を記述
- `/retro --no-salvage` 引数でサルベージをスキップ可能に

### Changed

- retro の Phase 0 が journal 空でも終了しなくなった（Phase 0.5 で起票される可能性があるため）
- Phase 3 で閾値超え 0 件かつサルベージ候補 0 件の場合、「失敗が少ない」ではなく「検知できていない」可能性に触れるようにした

> **背景**: 2026-07-21 の実測で、log-failure の起票率が約 2.5% であることが判明した（3 週間で「再発しうる失敗」が 35〜40 件発生したのに対し journal 起票は 1 件）。原因は閾値ではなく起票導線で、失敗の大半は Claude が自己訂正するためユーザーの目に触れず手動起票に乗らない。新規 hook 追加ではなく既存 retro の拡張を選択（`claude-meta:component-addition-advisor` の退路確保判定による。新規コンポーネント 0）。

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
