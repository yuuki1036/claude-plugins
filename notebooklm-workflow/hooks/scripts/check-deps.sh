#!/usr/bin/env bash
# check-deps.sh — SessionStart hook
# 外部依存（MCP サーバー、CLI ツール）の存在チェック

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "notebooklm-workflow:check-deps"

warnings=""
errors=""

check_mcp() {
  local name="$1" required="$2" desc="$3"
  # MCP サーバーの設定（.mcp.json）は同梱配布で常に存在するため、設定の有無を見ても
  # 実効性がない（found が必ず true になり ERROR 分岐が発火しない dead check）。
  # 同梱 .mcp.json の command は MCP サーバーバイナリ名そのもの（notebooklm-mcp）なので、
  # バイナリが PATH 上に実在するか（＝実際に起動できるか）を検査する。
  local bin="$name"
  if command -v jq >/dev/null 2>&1 && [ -f "${CLAUDE_PLUGIN_ROOT}/.mcp.json" ]; then
    # 同梱 .mcp.json から起動コマンド名を引く（name とズレる将来変更にも追従）
    local cmd
    cmd=$(jq -r --arg n "$name" '(.mcpServers[$n].command) // empty' "${CLAUDE_PLUGIN_ROOT}/.mcp.json" 2>/dev/null)
    [ -n "$cmd" ] && bin="$cmd"
  fi
  if ! command -v "$bin" >/dev/null 2>&1; then
    if [ "$required" = "true" ]; then
      errors="${errors}\n- [ERROR] ${desc}（${name}）が起動できません（${bin} バイナリが PATH 上に見つかりません）"
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
check_cli "nlm" "true" "notebooklm-mcp-cli（pip install notebooklm-mcp-cli でインストール後、nlm login で認証）"
check_mcp "notebooklm-mcp" "true" "NotebookLM MCP サーバー（.mcp.json で同梱配布）"

# --- 結果出力 ---
if [ -n "$errors" ] || [ -n "$warnings" ]; then
  echo "## 依存チェック (notebooklm-workflow)"
  [ -n "$errors" ] && echo -e "$errors"
  [ -n "$warnings" ] && echo -e "$warnings"
  echo ""
fi
