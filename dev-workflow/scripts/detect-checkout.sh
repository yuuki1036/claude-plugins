#!/usr/bin/env bash
# detect-checkout.sh — ui-verify の実行対象が main の clone か git worktree かを判定し、
# dev server の port と「その port で LISTEN している process がこの checkout のものか」を返す。
#
# なぜ要るか:
#   worktree で ui-verify を起動すると、`lsof -i :3000` は main の clone（や別 worktree）が
#   立てた dev server も拾う。port が生きているだけで「起動中 → そのまま使う」と判定すると、
#   **別のコードを検証して pass を書く**。port の占有だけでは区別できないので、LISTEN している
#   process の cwd をこの checkout の toplevel と突き合わせる。
#
# 使い方:
#   detect-checkout.sh [--port N]
#
# 出力（KEY=VALUE を 1 行ずつ。skill 本文はこれを読んで分岐する）:
#   CHECKOUT=main|worktree
#   WORKTREE_STATE=main|worktree-ready|worktree-unconfigured   # worktree-setup と同じ 3 値
#   TOPLEVEL=<path>  BRANCH=<name>
#   DEV_PORT=<n>  PORT_SOURCE=arg|worktree-env|package.json|default
#   SERVER_PID=<pid|空>  SERVER_CWD=<path|空>
#   SERVER_MATCH=none|ours|foreign|unknown
#     none    = その port で LISTEN していない
#     ours    = LISTEN している process の cwd が TOPLEVEL 配下（monorepo の subdir 起動も含む）
#     foreign = 別 checkout の server。**流用も kill もしない**
#     unknown = cwd が取れない（lsof / procfs が無い）
#
# exit: 0 判定できた / 2 git リポジトリ外・引数不正

set -uo pipefail

PORT_ARG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --port) [ $# -ge 2 ] || { echo "FATAL: --port に値が無い" >&2; exit 2; }
            PORT_ARG="$2"; shift 2 ;;
    -h|--help) sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "FATAL: 未知の引数: $1" >&2; exit 2 ;;
  esac
done
if [ -n "$PORT_ARG" ] && ! [[ "$PORT_ARG" =~ ^[0-9]+$ ]]; then
  echo "FATAL: --port は数値: ${PORT_ARG}" >&2; exit 2
fi

TOPLEVEL=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "FATAL: git リポジトリ外" >&2; exit 2; }
GIT_DIR=$(git rev-parse --path-format=absolute --git-dir 2>/dev/null || git rev-parse --git-dir)
GIT_COMMON=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || git rev-parse --git-common-dir)
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")

# worktree-setup の Step 1 と同じ判定式。相対パスで返る古い git 向けに toplevel 基準で正規化する
abs() { case "$1" in /*) printf '%s\n' "$1" ;; *) printf '%s/%s\n' "$TOPLEVEL" "$1" ;; esac; }
GIT_DIR=$(cd "$(abs "$GIT_DIR")" 2>/dev/null && pwd -P || abs "$GIT_DIR")
GIT_COMMON=$(cd "$(abs "$GIT_COMMON")" 2>/dev/null && pwd -P || abs "$GIT_COMMON")

MARKER="$TOPLEVEL/envs/.frontend.env.worktree"
if [ "$GIT_DIR" = "$GIT_COMMON" ]; then
  CHECKOUT="main"; WORKTREE_STATE="main"
elif [ -f "$MARKER" ]; then
  CHECKOUT="worktree"; WORKTREE_STATE="worktree-ready"
else
  CHECKOUT="worktree"; WORKTREE_STATE="worktree-unconfigured"
fi

# port の解決。worktree-setup が割り当てた FRONTEND_PORT を package.json より優先する
# （package.json の値は main と共有なので、worktree ではそのまま使うと main と衝突する）
DEV_PORT=""; PORT_SOURCE=""
if [ -n "$PORT_ARG" ]; then
  DEV_PORT="$PORT_ARG"; PORT_SOURCE="arg"
elif [ "$WORKTREE_STATE" = "worktree-ready" ] \
     && p=$(sed -n 's/^FRONTEND_PORT=\([0-9][0-9]*\).*/\1/p' "$MARKER" | head -1) && [ -n "$p" ]; then
  DEV_PORT="$p"; PORT_SOURCE="worktree-env"
elif [ -f "$TOPLEVEL/package.json" ] && command -v jq >/dev/null 2>&1 \
     && p=$(jq -r '.scripts.dev // empty' "$TOPLEVEL/package.json" 2>/dev/null \
            | grep -oE -- '(--port[= ]|-p |PORT=)[0-9]+' | grep -oE '[0-9]+$' | head -1) && [ -n "$p" ]; then
  DEV_PORT="$p"; PORT_SOURCE="package.json"
else
  DEV_PORT="3000"; PORT_SOURCE="default"
fi

# LISTEN している process とその cwd
SERVER_PID=""; SERVER_CWD=""; SERVER_MATCH="none"
if command -v lsof >/dev/null 2>&1; then
  SERVER_PID=$(lsof -nP -iTCP:"$DEV_PORT" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)
fi
if [ -n "$SERVER_PID" ]; then
  SERVER_MATCH="unknown"
  if [ -r "/proc/$SERVER_PID/cwd" ]; then
    SERVER_CWD=$(readlink "/proc/$SERVER_PID/cwd" 2>/dev/null || true)
  fi
  if [ -z "$SERVER_CWD" ]; then
    SERVER_CWD=$(lsof -a -p "$SERVER_PID" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1 || true)
  fi
  if [ -n "$SERVER_CWD" ]; then
    # symlink 差（macOS の /private/tmp など）で偽 foreign にしないため両方を物理パスに揃える
    top_p=$(cd "$TOPLEVEL" 2>/dev/null && pwd -P || printf '%s' "$TOPLEVEL")
    cwd_p=$(cd "$SERVER_CWD" 2>/dev/null && pwd -P || printf '%s' "$SERVER_CWD")
    case "$cwd_p" in
      "$top_p"|"$top_p"/*) SERVER_MATCH="ours" ;;
      *) SERVER_MATCH="foreign" ;;
    esac
  fi
fi

printf 'CHECKOUT=%s\n' "$CHECKOUT"
printf 'WORKTREE_STATE=%s\n' "$WORKTREE_STATE"
printf 'TOPLEVEL=%s\n' "$TOPLEVEL"
printf 'BRANCH=%s\n' "$BRANCH"
printf 'DEV_PORT=%s\n' "$DEV_PORT"
printf 'PORT_SOURCE=%s\n' "$PORT_SOURCE"
printf 'SERVER_PID=%s\n' "$SERVER_PID"
printf 'SERVER_CWD=%s\n' "$SERVER_CWD"
printf 'SERVER_MATCH=%s\n' "$SERVER_MATCH"
