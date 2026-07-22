#!/usr/bin/env bash
# safe-hook.sh — Claude Code hook 共通ラッパーライブラリ（正本）
#
# 目的:
#   - stdin 消費忘れによるハング防止
#   - stdout 汚染の予防（期待したときだけ Claude に注入）
#   - エラー分類による振る舞い統一
#
# 使い方:
#   #!/usr/bin/env bash
#   source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
#   safe_hook_init "my-hook-name"
#
#   # stdin を参照したい場合
#   payload=$(safe_hook_input)
#
#   # Claude のコンテキストに注入
#   safe_hook_emit "メッセージ"
#
#   # 期待通りの失敗（silent exit 0）
#   safe_hook_error Validation "foo is empty"
#   safe_hook_error Dependency "jq not installed"
#   safe_hook_error Auth "gh not authenticated"
#   safe_hook_error NotFound ".claude/linear missing"
#
#   # 予期しない失敗（stderr に通知して exit 0）
#   safe_hook_error Unexpected "unknown branch layout"
#
# 正本の配布:
#   - 正本: .claude-plugin/lib/safe-hook.sh（このファイル）
#   - 複製: {plugin}/hooks/lib/safe-hook.sh（各プラグインに byte-identical に配布）
#   - quality-check で同期を検証する

# 多重 source 防止
if [ -n "${__SAFE_HOOK_SOURCED:-}" ]; then
  return 0 2>/dev/null || exit 0
fi
__SAFE_HOOK_SOURCED=1

set -euo pipefail

SAFE_HOOK_NAME="unknown"
__SAFE_HOOK_INPUT=""
__SAFE_HOOK_INPUT_READ=0

# 初期化: フック名を登録し、stdin を消費してバッファに格納
# Usage: safe_hook_init "hook-name"
safe_hook_init() {
  SAFE_HOOK_NAME="${1:-unknown}"
  __SAFE_HOOK_INPUT="$(cat || true)"
  __SAFE_HOOK_INPUT_READ=1
  trap '__safe_hook_trap $? $LINENO' ERR
}

# stdin バッファを取得（safe_hook_init 呼び出し後に使う）
safe_hook_input() {
  if [ "$__SAFE_HOOK_INPUT_READ" -ne 1 ]; then
    __safe_hook_log Unexpected "safe_hook_input called before safe_hook_init"
    return 1
  fi
  printf '%s' "$__SAFE_HOOK_INPUT"
}

# Claude のコンテキストに出力（改行付き）
safe_hook_emit() {
  printf '%s\n' "$*"
}

# エラー分類と終了処理
# $1: カテゴリ (Validation|Dependency|Auth|NotFound|Unexpected)
# $2: 理由（省略可）
safe_hook_error() {
  local category="${1:-Unexpected}"
  local reason="${2:-}"
  case "$category" in
    Validation|Dependency|Auth|NotFound)
      __safe_hook_log "$category" "$reason"
      exit 0
      ;;
    Unexpected)
      __safe_hook_log "$category" "$reason"
      echo "[${SAFE_HOOK_NAME}] Unexpected: ${reason}" >&2 || true
      exit 0
      ;;
    *)
      __safe_hook_log Unknown "$category: $reason"
      exit 0
      ;;
  esac
}

# 情報ログ（stderr、Claude のコンテキストには入らない）
safe_hook_log() {
  __safe_hook_log Info "$*"
}

# v2.1.141+: terminalSequence で端末ベルを鳴らす（OSC/BEL JSON 出力）
# Usage: safe_hook_emit_bell
# 注意: terminalSequence 出力は単独で行うこと。safe_hook_emit と混在不可
safe_hook_emit_bell() {
  printf '{"terminalSequence":"\\u0007"}\n'
}

# v2.1.141+: terminalSequence でウィンドウタイトルを更新（OSC 2）
# Usage: safe_hook_emit_window_title "Claude: review session"
# 注意: title に " や \ は含めないこと（JSON エスケープ簡素化のため除去）
safe_hook_emit_window_title() {
  local title="${1:-Claude Code}"
  title="${title//\\/}"
  title="${title//\"/}"
  printf '{"terminalSequence":"\\u001b]2;%s\\u0007"}\n' "$title"
}

# v2.1.163+: additionalContext で Claude にコンテキストを注入する（block しない）
# Usage: safe_hook_emit_context <hook-event-name> <message>
# 例: safe_hook_emit_context "PostToolUse" "scope が大きすぎます。Issue 分割を検討してください"
# 注意:
#   - additionalContext は単独 JSON 出力。safe_hook_emit / terminalSequence と混在不可
#   - JSON エンコードは python3 → jq に委譲。どちらも無ければ最小エスケープでフォールバック
#   - message が空なら何も出力しない（呼び出し側の条件分岐を簡素化）
#   - plain stdout（safe_hook_emit）より Claude への到達保証が高い。FileChanged /
#     PostToolUse 等で「確実に届けたい」通知に使う
safe_hook_emit_context() {
  local event="${1:-PostToolUse}" msg="${2:-}"
  if [ -z "$msg" ]; then
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf '%s' "$msg" | EVENT="$event" python3 -c 'import json,os,sys; print(json.dumps({"hookSpecificOutput":{"hookEventName":os.environ.get("EVENT","PostToolUse"),"additionalContext":sys.stdin.read()}}))'
  elif command -v jq >/dev/null 2>&1; then
    printf '%s' "$msg" | jq -Rsc --arg e "$event" '{hookSpecificOutput:{hookEventName:$e,additionalContext:.}}'
  else
    local m="$msg"
    m="${m//\\/\\\\}"; m="${m//\"/\\\"}"; m="${m//$'\n'/\\n}"
    printf '{"hookSpecificOutput":{"hookEventName":"%s","additionalContext":"%s"}}\n' "$event" "$m"
  fi
}

# 内部: 名前付き stderr ログ
__safe_hook_log() {
  local level="$1" msg="$2"
  echo "[${SAFE_HOOK_NAME}:${level}] ${msg}" >&2 || true
}

# 内部: ERR trap — 予期しない失敗時の最後の砦
__safe_hook_trap() {
  local exit_code="$1" line="$2"
  echo "[${SAFE_HOOK_NAME}:Unexpected] exit ${exit_code} at line ${line}" >&2 || true
  exit 0
}

# ============================================================
# Event Bus（v2026-05-18+）
# ============================================================
#
# Claude Code の hook を Pub/Sub Message Bus として運用するための
# 軽量イベント発行・読み出し API。
#
# 永続化: $CLAUDE_PROJECT_DIR/.claude/events.jsonl（プロジェクトローカル、
#         gitignored）。1 行 = 1 イベントの JSON Lines 形式。
#
# 利用例 (publisher):
#   event_bus_publish "issue:completed" '{"issue_id":"PROJ-123"}'
#
# 利用例 (subscriber):
#   event_bus_tail "issue:completed" 5   # 直近 5 件
#
# イベント命名規約:
#   <domain>:<verb-past>  例: issue:completed / feature:implemented / commit:created
#   プラグインプレフィックスは付けない（subscriber が publisher を意識しない設計）
#
# JSON 形式:
#   {"ts":"<ISO8601>","plugin":"<safe_hook_name>","event":"<name>","payload":<obj>}

__EVENT_BUS_LOG=""

__event_bus_init_log() {
  local project_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
  __EVENT_BUS_LOG="${project_dir}/.claude/events.jsonl"
  mkdir -p "$(dirname "$__EVENT_BUS_LOG")" 2>/dev/null || true
}

# イベントを発行する
# Usage: event_bus_publish <event-name> <json-payload>
# 例: event_bus_publish "issue:completed" '{"issue_id":"PROJ-123"}'
event_bus_publish() {
  local event_name="${1:-}"
  # ${2:-{\}} は {} でなく文字列 {\} に展開され invalid JSON を書くため 2 段で既定値を入れる
  local payload="${2:-}"
  [ -n "$payload" ] || payload='{}'
  if [ -z "$event_name" ]; then
    __safe_hook_log Validation "event_bus_publish called with empty event name"
    return 1
  fi
  __event_bus_init_log
  local ts plugin
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  plugin="${SAFE_HOOK_NAME:-unknown}"
  # JSON エスケープを最小限に（payload は信頼前提、特殊文字は呼び出し側で除去）
  printf '{"ts":"%s","plugin":"%s","event":"%s","payload":%s}\n' \
    "$ts" "$plugin" "$event_name" "$payload" >> "$__EVENT_BUS_LOG" 2>/dev/null || \
    __safe_hook_log Unexpected "event_bus_publish: failed to write to $__EVENT_BUS_LOG"
}

# 直近 N 件のイベントを取得する（オプションで event 名フィルタ）
# Usage: event_bus_tail [event-name] [N]
# 例: event_bus_tail "issue:completed" 5
# 例: event_bus_tail "" 20  # 全イベント直近 20 件
event_bus_tail() {
  local filter="${1:-}"
  local n="${2:-10}"
  __event_bus_init_log
  if [ ! -f "$__EVENT_BUS_LOG" ]; then
    return 0
  fi
  if [ -z "$filter" ]; then
    tail -n "$n" "$__EVENT_BUS_LOG"
  else
    grep -F "\"event\":\"$filter\"" "$__EVENT_BUS_LOG" | tail -n "$n"
  fi
}

# イベントログを空にする（テスト用・再起動時用）
# Usage: event_bus_clear
event_bus_clear() {
  __event_bus_init_log
  : > "$__EVENT_BUS_LOG" 2>/dev/null || true
}
