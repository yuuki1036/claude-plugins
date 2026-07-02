#!/usr/bin/env bash
# session-start-init.sh — SessionStart hook
# failure-journal 専用 journal ディレクトリの初期化

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "failure-journal:session-start-init"

# journal ディレクトリと journal.jsonl を用意（無ければ作成）
# Event Bus 正本（events.jsonl）と基準を揃えるため CLAUDE_PROJECT_DIR を優先
journal_dir="${CLAUDE_PROJECT_DIR:-$PWD}/.claude/failure-journal"
if ! mkdir -p "$journal_dir" 2>/dev/null; then
  safe_hook_error NotFound ".claude/failure-journal を作成できません"
fi
[ -f "$journal_dir/journal.jsonl" ] || : > "$journal_dir/journal.jsonl"

# 副作用は dir 初期化のみ。stdout は出さない（silent exit 0）
