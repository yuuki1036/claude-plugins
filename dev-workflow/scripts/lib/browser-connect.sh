# shellcheck shell=bash
# browser_connect（chrome-devtools-mcp の接続方式）の読み取り（正本）。scripts/launch-chrome-devtools.sh
# （MCP の起動引数）と scripts/chrome-profile-lock.sh（起動前に見るプロファイル）が source する。
# **他所へ複製しない**: 読む順か値の解釈が片方だけ変わると、MCP が使うのと違うプロファイルの lock を見る
# （複製していた頃、`userDataDir=`（path が空）の扱いが既にずれていた / GitHub issue #306）。
#
# browser_connect_resolve: cwd の .claude/dev-workflow.json も読み、次の 2 つを設定する
#   BROWSER_CONNECT_MODE=autoConnect|userDataDir|default
#   BROWSER_CONNECT_DIR=<path>     userDataDir のときだけ。値は加工しない（相対・`~` もそのまま）
# 読む順: DEV_WORKFLOW_BROWSER_CONNECT（.mcp.json の env が ${user_config.browser_connect} を展開して
# MCP プロセスに渡す。userConfig は MCP config で展開される: code.claude.com/docs/en/plugins-reference）
# → .claude/dev-workflow.json の browser_connect（展開されなかった機体向けの fallback。jq があるときだけ）。
# 展開されずに残ったリテラル `${user_config...}` は値として扱わない。
# `userDataDir=`（path が空）と未知の値は default: chrome-devtools-mcp も空の userDataDir は既定の
# プロファイルにする（1.11.0 の BrowserManager で確認）ので、空の `--userDataDir=` を渡さずに揃える。
browser_connect_resolve() {
  local raw="${DEV_WORKFLOW_BROWSER_CONNECT:-}"
  case "$raw" in *'${user_config'*) raw="" ;; esac
  if [ -z "$raw" ] && [ -f ".claude/dev-workflow.json" ] && command -v jq >/dev/null 2>&1; then
    raw="$(jq -r '.browser_connect // empty' .claude/dev-workflow.json 2>/dev/null || true)"
  fi
  BROWSER_CONNECT_DIR=""
  case "$raw" in
    autoConnect) BROWSER_CONNECT_MODE=autoConnect ;;
    userDataDir=?*) BROWSER_CONNECT_MODE=userDataDir; BROWSER_CONNECT_DIR="${raw#userDataDir=}" ;;
    *) BROWSER_CONNECT_MODE=default ;;
  esac
}
