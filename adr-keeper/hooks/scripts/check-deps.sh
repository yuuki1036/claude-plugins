#!/usr/bin/env bash
# check-deps.sh — SessionStart hook
# 外部依存の存在チェック。任意依存（doc-freshness）は未導入でも黙る（鮮度 lint が無いだけで ADR の作成は動く）。
# jq が無いと adr-write-guard.sh が黙って素通しになるので、そのときだけ知らせる。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "adr-keeper:check-deps"

warnings=""

check_cli() {
  local name="$1" required="$2" desc="$3"
  if ! command -v "$name" &>/dev/null; then
    warnings="${warnings}\n- [WARN] ${desc}（${name}）がインストールされていません"
  fi
}

check_plugin() {
  # 任意依存。未導入でも警告しない（毎セッション鳴らさない）。_requirements との対応を保つためにだけ呼ぶ
  local name="$1" required="$2" desc="$3"
  return 0
}

# --- チェック実行 ---
check_cli "jq" "false" "jq（ADR 新規作成の検査 adr-write-guard が使う。無いと検査せずに通す）"
check_plugin "doc-freshness" "false" "doc-freshness プラグイン（ADR の鮮度 lint）"

# --- 結果出力 ---
if [ -n "$warnings" ]; then
  echo "## 依存チェック (adr-keeper)"
  echo -e "$warnings"
  echo ""
fi
