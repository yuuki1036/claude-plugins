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
check_plugin "bdd-spec" "false" "bdd-spec プラグイン（Phase 1.3 BDD spec 入力契約。未インストール時は既存 Issue 解釈フローに fallback）"
check_plugin "design-doc" "false" "design-doc プラグイン（Phase 4.5 design doc export。未インストール時は skip）"

# --- 結果出力 ---
if [ -n "$errors" ] || [ -n "$warnings" ]; then
  echo "## 依存チェック (feature-dev)"
  [ -n "$errors" ] && echo -e "$errors"
  [ -n "$warnings" ] && echo -e "$warnings"
  echo ""
fi
