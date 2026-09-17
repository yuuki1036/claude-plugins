#!/usr/bin/env bash
# check-deps.sh — SessionStart hook
# textlint 本体と、同梱 textlintrc が参照するルールパッケージの解決可否を検査する。
#
# `command -v textlint` だけでは足りない。textlint v15 は config のルールが 1 つでも
# 解決できないと全ルールを黙って drop し、stdout に "== No rules found ==" を出して
# exit 0 する（stderr は空）。writing-polish の決定的チェックは「stdout が valid JSON か」で
# 成否を判定するので、この状態は skill 実行時まで気づけない（実測: 開発機で
# ja-no-redundant-expression 1 つの欠落により 4 preset 全部が数か月効いていなかった）。
# ここで config 全体を 1 回 probe し、失敗したらルールごとに切り分けて欠落パッケージ名を出す。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "writing-polish:check-deps"

warnings=""
CONFIG="${CLAUDE_PLUGIN_ROOT}/skills/writing-polish/references/textlintrc.json"

check_cli() {
  local name="$1" required="$2" desc="$3"
  if ! command -v "$name" &>/dev/null; then
    if [ "$required" = "true" ]; then
      warnings="${warnings}\n- [ERROR] ${desc}（${name}）がインストールされていません"
    else
      warnings="${warnings}\n- [WARN] ${desc}（${name}）がインストールされていません（オプション。未導入時は LLM 判定にフォールバック）"
    fi
  fi
}

# 空 stdin だと textlint は usage を出すので 1 文字流す
probe() {
  # 引数: textlint に渡す追加オプション（--config <path> か --rule <key>）
  # lint 指摘があると exit 1 になるが、ここで見るのは stdout の形だけ
  printf '。' | textlint --stdin --stdin-filename probe.md "$@" --format json 2>/dev/null || true
}

is_json() {
  printf '%s' "$1" | python3 -c 'import json,sys; json.load(sys.stdin)' >/dev/null 2>&1
}

# ルールキー → npm パッケージ名（textlint の解決規則）
#   preset-foo          → textlint-rule-preset-foo
#   @scope/preset-foo   → @scope/textlint-rule-preset-foo
pkg_name() {
  case "$1" in
    @*/*) printf '%s/textlint-rule-%s' "${1%%/*}" "${1#*/}" ;;
    *)    printf 'textlint-rule-%s' "$1" ;;
  esac
}

check_textlint_rules() {
  command -v textlint &>/dev/null || return 0
  command -v python3 &>/dev/null || return 0
  [ -f "$CONFIG" ] || return 0
  local out
  out="$(probe --config "$CONFIG")"
  if is_json "$out"; then
    return 0
  fi
  local missing="" key
  for key in $(python3 -c 'import json,sys; print("\n".join(json.load(open(sys.argv[1]))["rules"].keys()))' "$CONFIG"); do
    out="$(probe --rule "$key")"
    if ! is_json "$out"; then
      missing="${missing} $(pkg_name "$key")"
    fi
  done
  if [ -z "$missing" ]; then
    # 個別には解決できるのに config 全体で失敗 = config 側の問題（構文等）。導入案内は出せない
    warnings="${warnings}\n- [WARN] textlint は導入済みですが同梱 textlintrc（${CONFIG}）が JSON を返しません。config を確認してください"
    return 0
  fi
  warnings="${warnings}\n- [WARN] textlint は導入済みですが、同梱 textlintrc が参照するルールパッケージが未解決です（textlint v15 は 1 つ欠けると全ルールを drop するため、決定的チェックが丸ごと効いていません）。未解決:${missing}\n  導入: npm i -g${missing}（mise 環境は続けて mise reshim）"
}

# --- チェック実行 ---
check_cli "textlint" "false" "日本語文章の決定的チェック"
check_textlint_rules

# --- 結果出力 ---
if [ -n "$warnings" ]; then
  echo "## 依存チェック (writing-polish)"
  echo -e "$warnings"
  echo ""
fi
