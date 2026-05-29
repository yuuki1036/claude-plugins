#!/usr/bin/env bash
# path-guard.sh — ファイルパスの除外判定 / 拡張子抽出ヘルパー
#
# PostToolUse lint チェーン等で「無関係ファイルは即 exit」するための path guard。
# 各 hook は冒頭でこれを呼び、生成物・vendor・lock ファイルを早期に弾く。
#
# 使い方（safe-hook.sh の source 後に source する）:
#   source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/path-guard.sh"
#   path_guard_is_excluded "$FILE_PATH" && safe_hook_error Validation "excluded path"
#   ext=$(path_guard_ext "$FILE_PATH")

# 多重 source 防止
if [ -n "${__PATH_GUARD_SOURCED:-}" ]; then
  return 0 2>/dev/null || exit 0
fi
__PATH_GUARD_SOURCED=1

# path_guard_is_excluded <path>
# 生成物・依存・lock 等の lint 対象外パスなら 0(true)、それ以外は 1(false)
path_guard_is_excluded() {
  case "$1" in
    */node_modules/*|*/.git/*|*/dist/*|*/build/*|*/.next/*|*/out/*|*/coverage/*|\
    */vendor/*|*/__generated__/*|*/.venv/*|*/target/*|\
    *.min.js|*.min.css|*.lock|*-lock.json|*.lock.json|*.snap)
      return 0 ;;
  esac
  return 1
}

# path_guard_ext <path>
# 小文字の拡張子（ドット無し）を echo。拡張子が無ければ空文字
path_guard_ext() {
  local base ext
  base="${1##*/}"
  case "$base" in
    *.*) ext="${base##*.}" ;;
    *)   ext="" ;;
  esac
  printf '%s' "$ext" | tr '[:upper:]' '[:lower:]'
}
