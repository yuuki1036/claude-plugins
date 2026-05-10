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
