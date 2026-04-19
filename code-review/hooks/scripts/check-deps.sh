#!/usr/bin/env bash
# check-deps.sh — SessionStart hook
# 外部依存（MCP サーバー、プラグイン、CLI ツール）の存在チェック

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "code-review:check-deps"

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
    fi
  fi
}

# --- チェック実行 ---
check_mcp "github" "true" "GitHub MCP サーバー"

# --- 結果出力 ---
if [ -n "$errors" ]; then
  echo "## 依存チェック (code-review)"
  echo -e "$errors"
  echo ""
fi
