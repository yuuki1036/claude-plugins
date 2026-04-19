#!/usr/bin/env bash
# check-deps.sh — SessionStart hook
# 外部依存（MCP サーバー、プラグイン、CLI ツール）の存在チェック

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "indie-workflow:check-deps"

warnings=""

check_plugin() {
  local name="$1" required="$2" desc="$3"
  local found=false
  if [ -f "$HOME/.claude/settings.json" ] && grep -q "\"${name}@" "$HOME/.claude/settings.json" 2>/dev/null; then
    found=true
  fi
  if [ "$found" = false ]; then
    if [ "$required" = "true" ]; then
      warnings="${warnings}\n- [ERROR] ${desc}（${name}）がインストールされていません"
    else
      warnings="${warnings}\n- [WARN] ${desc}（${name}）が未インストールです（オプション）"
    fi
  fi
}

# --- チェック実行 ---
check_plugin "feature-dev" "false" "feature-dev プラグイン"

# --- 結果出力 ---
if [ -n "$warnings" ]; then
  echo "## 依存チェック (indie-workflow)"
  echo -e "$warnings"
  echo ""
fi
