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
  # user スコープ（claude mcp add -s user → ~/.claude.json の .mcpServers）を jq で厳密確認
  if command -v jq >/dev/null 2>&1 && [ -f "$HOME/.claude.json" ] \
     && jq -e --arg n "$name" '(.mcpServers // {}) | has($n)' "$HOME/.claude.json" >/dev/null 2>&1; then
    found=true
  fi
  if [ "$found" = false ]; then
    # 同梱 .mcp.json（本プラグインが alwaysLoad で配布する MCP）も探索対象に含める
    for cfg in "$HOME/.claude/mcp.json" ".mcp.json" "${CLAUDE_PLUGIN_ROOT}/.mcp.json"; do
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

check_cli() {
  local name="$1" required="$2" desc="$3"
  if ! command -v "$name" &>/dev/null; then
    if [ "$required" = "true" ]; then
      errors="${errors}\n- [ERROR] ${desc}（${name}）がインストールされていません"
    else
      warnings="${warnings}\n- [WARN] ${desc}（${name}）がインストールされていません（オプション）"
    fi
  fi
}

# 同梱 .mcp.json が宣言する MCP は check_mcp から見れば必ず「設定済み」になる
# （探索対象に ${CLAUDE_PLUGIN_ROOT}/.mcp.json が入っているため found が恒真）。
# 設定の有無と起動可能性は別物で、launcher が PATH に無ければ MCP は ENOENT で
# 落ちる。実際 npx 不在の機体で chrome-devtools が起動せず、依存チェックは
# ERROR も WARN も 0 件だった。設定とは独立に launcher の実在を見る。
check_bundled_mcp_launcher() {
  local name="$1" desc="$2"
  local cfg="${CLAUDE_PLUGIN_ROOT}/.mcp.json"
  [ -f "$cfg" ] || return 0
  command -v jq >/dev/null 2>&1 || return 0
  local cmd=""
  cmd="$(jq -r --arg n "$name" '(.mcpServers[$n].command) // empty' "$cfg" 2>/dev/null)" || return 0
  [ -n "$cmd" ] || return 0
  if ! command -v "$cmd" &>/dev/null; then
    warnings="${warnings}\n- [WARN] ${desc}（${name}）は同梱設定されていますが、起動コマンド ${cmd} が PATH に無いため起動できません"
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
check_cli "gh" "true" "GitHub CLI"
check_mcp "linear" "false" "Linear MCP サーバー"

# ui-verify 系は Web プロジェクトでのみ検査する。node の無い機体で毎セッション
# 鳴らしても行動に繋がらず、「WARN が出たときだけ行動する」契約を壊すため
# （docs/rule-placement.md）。フラグは detect-web-project.sh が立てるが、それは
# 本スクリプトの後に走るので、新規 Web プロジェクトでは 1 セッション遅れて有効になる
# （package.json 削除でフラグが消える無効化方向も同じく 1 セッション遅れる）。
if [ -f ".claude/.ui-verify-enabled" ]; then
  check_mcp "chrome-devtools" "false" "chrome-devtools MCP サーバー（ui-verify で使用）"
  check_bundled_mcp_launcher "chrome-devtools" "chrome-devtools MCP サーバー"
  check_cli "node" "false" "Node.js（chrome-devtools-mcp を npx 起動するため）"
fi

check_plugin "writing-polish" "false" "writing-polish プラグイン（PR 本文・コミットメッセージの提示前推敲。未インストール時は skip）"

# --- 結果出力 ---
if [ -n "$errors" ] || [ -n "$warnings" ]; then
  echo "## 依存チェック (dev-workflow)"
  [ -n "$errors" ] && echo -e "$errors"
  [ -n "$warnings" ] && echo -e "$warnings"
  echo ""
fi
