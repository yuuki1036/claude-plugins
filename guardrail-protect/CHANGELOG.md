# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [0.1.1] - 2026-06-15

### Changed

- `hooks/lib/safe-hook.sh` を正本に同期（additionalContext 注入 helper `safe_hook_emit_context` 追加に伴う byte-identical 複製の更新）

## [0.1.0] - 2026-05-28

### Added
- 初期リリース（#45）
- PreToolUse hook `pre-config-guard.sh`: 保護対象 basename への Edit/Write/MultiEdit を `exit 2` でブロック
- PreToolUse hook `pre-commit-guard.sh`: `git commit --no-verify` / `-n` を heredoc/quoted string 剥がし後に検出してブロック（message 内文字列は誤検知しない）
- 設定ファイル `<project>/.claude/guardrail-protect.json` で `protected_basenames` を opt-in 宣言
- references: メタルール本文（骨抜き禁止）と推奨保護対象リスト
