# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.2.9] - 2026-07-22

### Fixed
- **safe-hook.sh: `event_bus_publish` の payload 省略時デフォルトが壊れた JSON になるバグを修正**（`${2:-{\}}` が `{}` でなく文字列 `{\}` に展開され invalid JSON 行が書かれていた。正本 `.claude-plugin/lib/safe-hook.sh` の修正を全プラグインへ同期）

## [1.2.8] - 2026-07-02

### Changed

- `commands/feedback.md` Phase 2 の対象プラグイン一覧ハードコード（7 件で化石化）を廃止し、`claude plugin list` / `marketplace.json` からの動的取得に変更（一覧更新忘れの構造的解消）
- Issue 本文テンプレを `references/issue-template.md`（正本）に一本化。`commands/feedback.md` Phase 5 の重複本文定義を参照指示に置き換え（プレビューの「## 種別」セクションと references の乖離を解消）

### Fixed

- `skills/feedback-issue/SKILL.md` Step 5 にラベル不存在時の `--label` 省略フォールバックを追記（command のみに存在していた挙動を skill にも反映）
- `commands/feedback.md` / `skills/feedback-issue/SKILL.md` に `--repo yuuki1036/claude-plugins` 固定値の意図（CWD 非依存で常にマーケットプレイス本体を指す）を明記

## [1.2.7] - 2026-06-15

### Changed

- `hooks/lib/safe-hook.sh` を正本に同期（additionalContext 注入 helper `safe_hook_emit_context` 追加に伴う byte-identical 複製の更新）

## [1.2.6] - 2026-06-01

### Changed

- `skills/feedback-issue/SKILL.md` Step 2 に **AskUserQuestion の inline 呼び出し仕様**を追記（allowed-tools 最小性 #14b の規約準拠）。Issue 種別（enhancement / bug / question）判定を素のプロンプトから選択 UI に変更し、宣言済みツールと実装を一致させる

## [1.2.5] - 2026-05-25

### Changed
- 対象プラグイン一覧（`commands/feedback.md`）と README の使用例から instinct-memory を除去（instinct-memory プラグイン廃止に伴う参照除去）

## [1.2.4] - 2026-05-18

### Changed
- `hooks/lib/safe-hook.sh` を v2026-05-18+ に同期。`event_bus_publish` / `event_bus_tail` / `event_bus_clear` API を取得（正本由来、内部ライブラリ拡張）

## [1.2.3] - 2026-05-15

### Changed
- `hooks/hooks.json` を `args[]` exec 形式へ移行（CC 2.1.139+）
- `safe-hook.sh` に `safe_hook_emit_bell` / `safe_hook_emit_window_title` を追加（CC 2.1.141+ terminalSequence 対応）

## [1.2.2] - 2026-04-19

### Changed
- `check-deps.sh` を `safe-hook.sh` 共通ラッパー経由に移行（stdin 消費・エラー分類・名前付きログの統一） (#21)

## [1.2.1] - 2026-03-31

### Changed
- SessionStart check-deps.sh に `once: true` 追加（セッション中1回のみ実行）

## [1.2.0] - 2026-03-29

### Added
- 全スキルに effort frontmatter を追加（feedback-issue: low）

## [1.1.0] - 2026-03-23

### Added
- SessionStart hook で外部依存チェック（gh CLI）を実行
- plugin.json に `_requirements` フィールドを追加（依存メタデータ宣言）

## [1.0.0] - 2026-03-21

### Added
- plugin-feedback プラグインを新規作成
- 改善要望・バグ報告を GitHub Issue として作成する機能
