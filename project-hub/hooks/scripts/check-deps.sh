#!/usr/bin/env bash
# check-deps.sh — SessionStart hook
# 外部依存の存在チェック。python3 が無いと状態ファイルの読み書きと注入が動かないので、そのときだけ知らせる。
# gh と Linear MCP は tracker の種類で片方だけ要る任意依存で、hub status が取れなかった source を
# 取得失敗として残すので黙る

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "project-hub:check-deps"

errors=""

check_cli() {
  local name="$1" required="$2" desc="$3"
  if ! command -v "$name" >/dev/null 2>&1; then
    if [ "$required" = "true" ]; then
      errors="${errors}\n- [ERROR] ${desc}（${name}）がインストールされていません"
    fi
  fi
}

check_mcp() {
  # 任意依存。未設定でも警告しない（毎セッション鳴らさない）。_requirements との対応を保つためにだけ呼ぶ
  local name="$1" required="$2" desc="$3"
  return 0
}

# --- チェック実行 ---
check_cli "python3" "true" "状態ファイルの読み書き・宛先の照合（scripts/hub.py）と注入 hook で使用"
check_cli "gh" "false" "GitHub の Issue・PR の取得（hub status。tracker が github のとき）"
check_mcp "linear" "false" "Linear MCP サーバー（hub status。tracker が linear のとき）"

# --- 結果出力 ---
if [ -n "$errors" ]; then
  echo "## 依存チェック (project-hub)"
  echo -e "$errors"
  echo ""
fi
