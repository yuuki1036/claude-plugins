#!/usr/bin/env bash
# launch-chrome-devtools.sh — 同梱 chrome-devtools MCP の起動ラッパ
#
# なぜラッパを噛ませるか:
#   GUI アプリ（Claude Desktop）の PATH には mise / nvm の shim が乗らず、素の
#   command: "npx" は ENOENT で落ちる（実測。node が mise 管理の機体で再現）。
#   npx の在り処を複数のバージョンマネージャ経路から探して exec する。
#   あわせて browser_connect（認証あり画面で実 Chrome のログイン状態を使う設定）を
#   引数に展開する。設計: .claude/designs/20260912-e2e-verify-comment-polish-pr-flow.md (A-5)

set -euo pipefail

# --- npx 解決 ---
# GUI app PATH では mise 本体すら引けないことがあるので、mise も既知 install 先まで探す。
resolve_mise() {
  if command -v mise >/dev/null 2>&1; then command -v mise; return 0; fi
  for c in "$HOME/.local/bin/mise" "/opt/homebrew/bin/mise" "/usr/local/bin/mise"; do
    [ -x "$c" ] && { printf '%s\n' "$c"; return 0; }
  done
  return 1
}

resolve_npx() {
  if command -v npx >/dev/null 2>&1; then command -v npx; return 0; fi
  local mise
  if mise=$(resolve_mise); then
    local p
    p="$("$mise" which npx 2>/dev/null)" && [ -n "$p" ] && { printf '%s\n' "$p"; return 0; }
  fi
  # nvm / volta の install 済み bin を直接探す（最初に見つかったものを使う。版は問わない）
  local d
  for d in "$HOME/.nvm/versions/node"/*/bin/npx "$HOME/.volta/bin/npx"; do
    [ -x "$d" ] && { printf '%s\n' "$d"; return 0; }
  done
  return 1
}

# --check: npx を解決できるかだけを見て exit（依存チェック用。MCP は起動しない）
if [ "${1:-}" = "--check" ]; then
  resolve_npx >/dev/null 2>&1 && exit 0 || exit 1
fi

NPX="$(resolve_npx)" || {
  echo "launch-chrome-devtools: npx が見つかりません（mise / nvm / volta いずれの経路でも解決できず）。Node.js を入れるか PATH を通してください。" >&2
  exit 1
}

# --- browser_connect 設定の読み取り ---
# .mcp.json の env で ${user_config.browser_connect} を DEV_WORKFLOW_BROWSER_CONNECT に
# 展開して渡す（userConfig は MCP config で展開される。code.claude.com/docs/en/plugins-reference）。
# 展開されなかった機体向けに .claude/dev-workflow.json も fallback で読む。
CONNECT="${DEV_WORKFLOW_BROWSER_CONNECT:-}"
# 未展開リテラルが来たら無視する
case "$CONNECT" in *'${user_config'*) CONNECT="" ;; esac
if [ -z "$CONNECT" ] && [ -f ".claude/dev-workflow.json" ] && command -v jq >/dev/null 2>&1; then
  CONNECT="$(jq -r '.browser_connect // empty' .claude/dev-workflow.json 2>/dev/null || true)"
fi

EXTRA_ARGS=()
case "$CONNECT" in
  autoConnect)
    # 実 Chrome のログイン状態を使う。Chrome 144+ 前提。
    # @latest がキャッシュの旧版（autoConnect 非対応）に解決すると黙殺されるので
    # 解決版を一度確認し、満たさなければ autoConnect を付けず既定プロファイルに落とす。
    VER="$("$NPX" -y chrome-devtools-mcp@latest --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
    if [ -n "$VER" ] && [ "$(printf '%s\n1.7.0\n' "$VER" | sort -V | head -1)" = "1.7.0" ]; then
      EXTRA_ARGS+=(--autoConnect)
    else
      echo "launch-chrome-devtools: chrome-devtools-mcp が ${VER:-不明} で autoConnect（1.7.0+ 必須）に満たないため既定プロファイルで起動します。" >&2
    fi
    ;;
  userDataDir=*)
    EXTRA_ARGS+=("--userDataDir=${CONNECT#userDataDir=}")
    ;;
esac

# 空配列の "${EXTRA_ARGS[@]}" は set -u 下の bash 3.2（macOS /bin/bash）で unbound になる。
# 既定 browser_connect=default では EXTRA_ARGS が空なので ${arr[@]+...} でガードする。
exec "$NPX" -y chrome-devtools-mcp@latest ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
