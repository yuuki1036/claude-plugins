#!/usr/bin/env bash
# session-start-init.sh — SessionStart / PostCompact hook
# failure-journal 専用 journal ディレクトリの初期化 + 自己訂正の候補記録ルール注入
#
# 設計方針:
#   - 失敗の大半（実測 ~97.5%）は Claude の自己訂正で人間の目に触れず、手動 /log-failure
#     では拾えない。検知できる唯一の主体（Claude 自身）に、検知した瞬間 candidates.jsonl へ
#     1 行書かせる ambient ルールを毎セッション注入する（spec-advisor と同型のパターン）
#   - PostCompact でも同一スクリプトを再実行し、compaction でルールが失われるのを防ぐ

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "failure-journal:session-start-init"

# journal ディレクトリと jsonl を用意（無ければ作成）
# Event Bus 正本（events.jsonl）と基準を揃えるため CLAUDE_PROJECT_DIR を優先
journal_dir="${CLAUDE_PROJECT_DIR:-$PWD}/.claude/failure-journal"
if ! mkdir -p "$journal_dir" 2>/dev/null; then
  safe_hook_error NotFound ".claude/failure-journal を作成できません"
fi
[ -f "$journal_dir/journal.jsonl" ] || : > "$journal_dir/journal.jsonl"
[ -f "$journal_dir/candidates.jsonl" ] || : > "$journal_dir/candidates.jsonl"
# 還流の実施記録（GitHub issue #193）。retro の閾値判定がこの記録以降の発生だけを
# 分子に取る。無いときは「還流ゼロ」＝従来どおりの集計になる
[ -f "$journal_dir/remediations.jsonl" ] || : > "$journal_dir/remediations.jsonl"
# umbrella tag の分割宣言（GitHub issue #195）。log-failure Phase 2 が寄せ先候補として
# 読む唯一の機械可読な宣言。無いときは「分割なし」＝従来どおりの起票になる
[ -f "$journal_dir/splits.jsonl" ] || : > "$journal_dir/splits.jsonl"

# 自己訂正の候補記録ルールを注入
RULES_DIR="${CLAUDE_PLUGIN_ROOT}/rules"
[ -f "${RULES_DIR}/self-report-rule.md" ] || safe_hook_error NotFound "self-report-rule.md missing"

cat "${RULES_DIR}/self-report-rule.md"
