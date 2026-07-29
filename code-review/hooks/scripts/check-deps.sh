#!/usr/bin/env bash
# check-deps.sh — SessionStart hook
# 外部依存（MCP サーバー、プラグイン、CLI ツール）の存在チェック

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "code-review:check-deps"

errors=""
warnings=""

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
    fi
  fi
}

check_cli() {
  local name="$1" required="$2" desc="$3"
  if ! command -v "$name" >/dev/null 2>&1; then
    if [ "$required" = "true" ]; then
      errors="${errors}\n- [ERROR] ${desc}（${name}）がインストールされていません"
    fi
  fi
}

check_plugin() {
  local name="$1" required="$2" desc="$3"
  # settings.json の enabled plugins（"name@marketplace" 形式）を確認
  if [ -f "$HOME/.claude/settings.json" ] && grep -q "\"${name}@" "$HOME/.claude/settings.json" 2>/dev/null; then
    return 0
  fi
  if [ "$required" = "true" ]; then
    errors="${errors}\n- [ERROR] ${desc}（${name}）がインストールされていません"
  else
    warnings="${warnings}\n- [WARN] ${desc}（${name}）が未インストールです（オプション）"
  fi
}

# --- チェック実行 ---
check_mcp "github" "true" "GitHub MCP サーバー"
# kvault は self-review Step 1.5 の Vault 照合で使う任意の外部 CLI（未導入時は skip）
check_cli "kvault" "false" "knowledge vault CLI（self-review Vault 照合。未導入時は skip）"
# writing-polish は review 締めフロー 3 のドラフト推敲で使う dormant 連携（未導入時は skip）
check_plugin "writing-polish" "false" "writing-polish プラグイン（返答ドラフトの提示前推敲。未インストール時は skip）"
check_plugin "dev-workflow" "false" "dev-workflow プラグイン（self-review 完了後の worktree-teardown 起動。未インストール時は skip）"

# --- 結果出力 ---
if [ -n "$errors" ] || [ -n "$warnings" ]; then
  echo "## 依存チェック (code-review)"
  [ -n "$errors" ] && echo -e "$errors"
  [ -n "$warnings" ] && echo -e "$warnings"
  echo ""
fi
