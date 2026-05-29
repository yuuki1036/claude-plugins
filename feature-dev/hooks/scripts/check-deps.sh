#!/usr/bin/env bash
# check-deps.sh — SessionStart hook
# 外部依存（プラグイン）の存在チェック。feature-dev v2.0.0 以降、Phase 6 は code-review:self-review に委譲される

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "feature-dev:check-deps"

warnings=""
errors=""

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
      warnings="${warnings}\n- [WARN] ${desc}（${name}）が未インストールです。Phase 6 (Quality Review) は fail-fast します。\`claude plugin install ${name}@yuuki1036-claude-plugins\` でインストール推奨"
    fi
  fi
}

# --- チェック実行 ---
check_plugin "code-review" "false" "code-review プラグイン（Phase 6 品質レビュー委譲先）"

# --- 結果出力 ---
if [ -n "$errors" ] || [ -n "$warnings" ]; then
  echo "## 依存チェック (feature-dev)"
  [ -n "$errors" ] && echo -e "$errors"
  [ -n "$warnings" ] && echo -e "$warnings"
  echo ""
fi
