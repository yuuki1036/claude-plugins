#!/usr/bin/env bash
# check-deps.sh — SessionStart hook
# 外部依存（MCP サーバー、プラグイン、CLI ツール）の存在チェック

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "dev-workflow:check-deps"

warnings=""
errors=""

check_mcp() {
  local name="$1" required="$2" desc="$3"
  local found=false
  for cfg in "$HOME/.claude/mcp.json" ".mcp.json"; do
    if [ -f "$cfg" ] && grep -q "\"${name}\"" "$cfg" 2>/dev/null; then
      found=true
      break
    fi
  done
  if [ "$found" = false ]; then
    if [ "$required" = "true" ]; then
      errors="${errors}\n- [ERROR] ${desc}（${name}）が設定されていません"
    else
      warnings="${warnings}\n- [WARN] ${desc}（${name}）が未設定です（オプション）"
    fi
  fi
}

check_cli() {
  local name="$1" required="$2" desc="$3"
  if ! command -v "$name" &>/dev/null; then
    if [ "$required" = "true" ]; then
      errors="${errors}\n- [ERROR] ${desc}（${name}）がインストールされていません"
    fi
  fi
}

# --- チェック実行 ---
check_cli "gh" "true" "GitHub CLI"
check_mcp "linear" "false" "Linear MCP サーバー"
check_mcp "chrome-devtools" "false" "chrome-devtools MCP サーバー（ui-verify で使用）"
check_cli "node" "false" "Node.js（chrome-devtools-mcp を npx 起動するため）"

# --- 結果出力 ---
if [ -n "$errors" ] || [ -n "$warnings" ]; then
  echo "## 依存チェック (dev-workflow)"
  [ -n "$errors" ] && echo -e "$errors"
  [ -n "$warnings" ] && echo -e "$warnings"
  echo ""
fi
