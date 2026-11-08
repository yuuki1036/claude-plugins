#!/usr/bin/env bash
# check-deps.sh — SessionStart hook
# 外部依存（プラグイン）の存在チェック。feature-dev v2.0.0 以降、Phase 6 は code-review:self-review に委譲される

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "feature-dev:check-deps"

warnings=""
errors=""

check_plugin() {
  local name="$1" required="$2" desc="$3" impact="$4"
  local state
  # 有効かは同梱の複製（正本 .claude-plugin/lib/plugin-enabled.sh）で決める。キーの有無だけでは false の無効化と project / local の有効化を読めない
  state=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-enabled.sh" "$name" 2>/dev/null) || state=0
  if [ "$state" = 1 ]; then
    return 0
  fi
  if [ "$required" = "true" ]; then
    errors="${errors}\n- [ERROR] ${desc}（${name}）が未導入か無効です"
  else
    warnings="${warnings}\n- [WARN] ${desc}（${name}）が未導入か無効です。${impact} \`claude plugin install ${name}@yuuki1036-claude-plugins\` でインストール（導入済みなら settings で有効化）推奨"
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

# --- チェック実行 ---
# 未導入・無効時の影響は連携先ごとに異なる（fail-fast は code-review のみ）
check_plugin "code-review" "false" "code-review プラグイン（Phase 6 品質レビュー委譲先）" "Phase 6 (Quality Review) は fail-fast します。"
check_plugin "bdd-spec" "false" "bdd-spec プラグイン（Phase 1.3 BDD spec 入力契約）" "Phase 1.3 は skip され、既存の Issue 解釈フローに fallback します。"
check_plugin "design-doc" "false" "design-doc プラグイン（Phase 4.5 design doc export）" "Phase 4.5 (Design Doc Export) は skip されます。"
# kvault は Phase 1.6 Vault Recall で使う任意の外部 CLI（未導入時は skip）
check_cli "kvault" "false" "knowledge vault CLI（Phase 1.6 Vault Recall。未導入時は skip）"

# kvault はあるのに KNOWLEDGE_VAULT_ROOT 未設定 → Phase 1.6 が黙って skip される（設定漏れの気づき）。
# 環境変数は ~/.zshenv に書く必要がある（.zshrc は非対話 shell で読まれず hook / spawn shell に効かない）。
if command -v kvault >/dev/null 2>&1 && [ -z "${KNOWLEDGE_VAULT_ROOT:-}" ]; then
  warnings="${warnings}\n- [WARN] kvault CLI はありますが KNOWLEDGE_VAULT_ROOT が未設定のため、MCP ツール search_knowledge が無いセッションでは Phase 1.6 (Vault Recall) が skip されます。\`~/.zshenv\` に \`export KNOWLEDGE_VAULT_ROOT=<vault パス>\` を設定してください（\`.zshrc\` は非対話 shell で読まれず効きません）"
fi

# --- 結果出力 ---
if [ -n "$errors" ] || [ -n "$warnings" ]; then
  echo "## 依存チェック (feature-dev)"
  [ -n "$errors" ] && echo -e "$errors"
  [ -n "$warnings" ] && echo -e "$warnings"
  echo ""
fi
