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
check_plugin "bdd-spec" "false" "bdd-spec プラグイン（issue-design bilayer モード）"
check_plugin "design-doc" "false" "design-doc プラグイン（issue-design の design doc 昇格 / indie-issue-create の spec 選択）"
check_plugin "adr-keeper" "false" "adr-keeper プラグイン（indie-issue-create の spec 選択で ADR 記録）"
check_plugin "writing-polish" "false" "writing-polish プラグイン（散文成果物の確定前 embed 推敲）"

# --- 結果出力 ---
if [ -n "$warnings" ]; then
  echo "## 依存チェック (indie-workflow)"
  echo -e "$warnings"
  echo ""
fi
