#!/usr/bin/env bash
# check-deps.sh — SessionStart hook
# 外部依存（MCP サーバー、プラグイン、CLI ツール）の存在チェック

set -euo pipefail
cat > /dev/null

errors=""

check_cli() {
  local name="$1" required="$2" desc="$3"
  if ! command -v "$name" &>/dev/null; then
    if [ "$required" = "true" ]; then
      errors="${errors}\n- [ERROR] ${desc}（${name}）がインストールされていません"
    fi
  fi
}

# --- チェック実行 ---
check_cli "gh" "true" "GitHub CLI"

# --- 結果出力 ---
if [ -n "$errors" ]; then
  echo "## 依存チェック (plugin-feedback)"
  echo -e "$errors"
  echo ""
fi
