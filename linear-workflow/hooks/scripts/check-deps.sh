#!/usr/bin/env bash
# check-deps.sh — SessionStart hook
# 外部依存（MCP サーバー、プラグイン、CLI ツール）の存在チェック

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "linear-workflow:check-deps"

warnings=""
errors=""

check_mcp() {
  local name="$1" required="$2" desc="$3"
  local found=false
  # user スコープ（claude mcp add -s user → ~/.claude.json の .mcpServers）を jq で厳密確認
  if command -v jq >/dev/null 2>&1 && [ -f "$HOME/.claude.json" ] \
     && jq -e --arg n "$name" '(.mcpServers // {}) | has($n)' "$HOME/.claude.json" >/dev/null 2>&1; then
    found=true
  fi
  if [ "$found" = false ]; then
    for cfg in "$HOME/.claude/mcp.json" ".mcp.json"; do
      if [ -f "$cfg" ] && grep -q "\"${name}\"" "$cfg" 2>/dev/null; then
        found=true
        break
      fi
    done
  fi
  if [ "$found" = false ]; then
    if [ "$required" = "true" ]; then
      errors="${errors}\n- [ERROR] ${desc}（${name}）が設定されていません"
    else
      warnings="${warnings}\n- [WARN] ${desc}（${name}）が未設定です（オプション）"
    fi
  fi
}

check_plugin() {
  local name="$1" required="$2" desc="$3"
  local found=false
  if [ -f "$HOME/.claude/settings.json" ] && grep -q "\"${name}@" "$HOME/.claude/settings.json" 2>/dev/null; then
    found=true
  fi
  if [ "$found" = false ]; then
    if [ "$required" = "true" ]; then
      errors="${errors}\n- [ERROR] ${desc}（${name}）がインストールされていません"
    else
      warnings="${warnings}\n- [WARN] ${desc}（${name}）が未インストールです（オプション）"
    fi
  fi
}

# --- チェック実行 ---
check_mcp "linear" "true" "Linear MCP サーバー"
check_plugin "feature-dev" "false" "feature-dev プラグイン"
check_plugin "bdd-spec" "false" "bdd-spec プラグイン（issue-design bilayer モード）"
check_plugin "design-doc" "false" "design-doc プラグイン（issue-design の design doc 昇格 / issue-create の spec 選択）"
check_plugin "adr-keeper" "false" "adr-keeper プラグイン（issue-create の spec 選択で ADR 記録）"

# --- 結果出力 ---
if [ -n "$errors" ] || [ -n "$warnings" ]; then
  echo "## 依存チェック (linear-workflow)"
  [ -n "$errors" ] && echo -e "$errors"
  [ -n "$warnings" ] && echo -e "$warnings"
  echo ""
fi
