#!/usr/bin/env bash
# chrome-profile-lock.sh — chrome-devtools-mcp のプロファイルを掴んでいる既存のブラウザを検知・停止する。
#
# なぜ要るか:
#   chrome-devtools-mcp は既定で 1 つのプロファイル（~/.cache/chrome-devtools-mcp/chrome-profile）を
#   全セッションで共有し、同時に 1 ブラウザしか使えない。別セッションの MCP が開いたブラウザが残って
#   いると、こちらの最初のツール呼び出しが `The browser is already running for <dir>` で失敗する
#   （GitHub issue #306）。ui-verify は chrome-devtools の最初のツール呼び出しの前に status を見て、
#   止めるのは利用者が選択 UI で「止めて続行」を選んだときだけ。ここはその判断材料（誰のブラウザか）を
#   出し、止める直前に lock を確かめ直す。
#
# 使い方:
#   chrome-profile-lock.sh status [--dir <dir>]
#   chrome-profile-lock.sh stop --pid <pid> [--dir <dir>]
#
#   --dir を省くと、launch-chrome-devtools.sh と共有する scripts/lib/browser-connect.sh で接続方式を読む
#   （DEV_WORKFLOW_BROWSER_CONNECT → .claude/dev-workflow.json の browser_connect）。userDataDir=<path> なら
#   その path、autoConnect なら見ない（実 Chrome につなぐだけでプロファイルを起動しない）、それ以外は既定の dir。
#   ui-verify が Bash tool から呼ぶ回は DEV_WORKFLOW_BROWSER_CONNECT が無い（.mcp.json の env が渡るのは
#   MCP プロセスだけ）。userConfig だけで設定した接続方式は見えず、既定の dir を見る。
#   dir は絶対パスで渡す / 書く。相対・`~` は MCP の cwd を起点に解決されるので、ここからは照合できない（unknown）
#
# 出力（KEY=VALUE を 1 行ずつ）:
#   PROFILE_DIR=<dir>（autoConnect は空）  DIR_SOURCE=arg|userDataDir|autoConnect|default
#   LOCK=none|stale|held|foreign-host|unknown
#     none         = SingletonLock が無い（autoConnect も含む）
#     stale        = lock の pid が生きていないか、その pid が --user-data-dir=<dir> を持たない（pid の再利用）
#     held         = lock の pid が生きていて <dir> を使っている
#     foreign-host = lock の hostname がこの機と違う（pid を照合できない）
#     unknown      = 照合できない（dir が絶対パスでない / lock が symlink でない / `<host>-<pid>` の形でない）
#   REASON=<1 行>  LOCK=unknown の理由（ほかは空）
#   HOLDER_PID / HOLDER_STARTED / HOLDER_MCP_PID / HOLDER_MCP_STARTED / HOLDER_SESSION（held 以外は空）
#     HOLDER_SESSION=self     CLAUDE_PID（Bash tool の環境にある、このセッションの claude の pid）が祖先にいる
#                    other    祖先に chrome-devtools-mcp がいて、CLAUDE_PID はいない（別セッションの MCP）
#                    orphan   祖先に chrome-devtools-mcp がいない（MCP の終了後に残った / 手動で起動した）
#                    unknown  祖先に chrome-devtools-mcp がいるが CLAUDE_PID が無効で、self か other か判定できない
#   stop は続けて STOPPED=yes|no を出し、止めなかったときは
#   REFUSED=not-held|pid-mismatch|self|session-unknown|signal-failed も出す（signal-failed = SIGTERM を送れなかった）
#
# exit: status は 0（引数不正・同梱の lib を読めないときは 2）。stop は 0 = 止めた / 1 = 待ち時間
#       （CHROME_PROFILE_LOCK_WAIT 秒、既定 10）内に終わらない（SIGKILL は送らない）/ 2 = 引数不正 / 3 = REFUSED

set -uo pipefail

usage() { sed -n '2,41p' "$0" | sed 's/^# \{0,1\}//'; }

CMD="${1:-}"
case "$CMD" in
  status|stop) shift ;;
  -h|--help) usage; exit 0 ;;
  *) echo "FATAL: サブコマンドは status か stop: ${CMD}" >&2; exit 2 ;;
esac

DIR=""; DIR_GIVEN=0; PID_ARG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) [ $# -ge 2 ] || { echo "FATAL: --dir に値が無い" >&2; exit 2; }
           DIR="$2"; DIR_GIVEN=1; shift 2 ;;
    --pid) [ $# -ge 2 ] || { echo "FATAL: --pid に値が無い" >&2; exit 2; }
           PID_ARG="$2"; shift 2 ;;
    *) echo "FATAL: 未知の引数: $1" >&2; exit 2 ;;
  esac
done
if [ "$CMD" = stop ] && ! [[ "$PID_ARG" =~ ^[0-9]+$ ]]; then
  echo "FATAL: stop には数値の --pid が要る: ${PID_ARG}" >&2; exit 2
fi

# --- 見る dir ---
if [ "$DIR_GIVEN" = 1 ]; then
  DIR_SOURCE=arg
else
  LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/browser-connect.sh"
  if [ ! -r "$LIB" ]; then
    echo "FATAL: 同梱の lib を読めない: ${LIB}" >&2; exit 2
  fi
  # shellcheck source=lib/browser-connect.sh
  . "$LIB"
  browser_connect_resolve
  case "$BROWSER_CONNECT_MODE" in
    # autoConnect が版落ちした回（起動ラッパが chrome-devtools-mcp の版を 1.7.0 未満か不明と見て、既定の
    # プロファイルで起動する）は見ない。同じ判定には npx で版を引き直す（数秒・ネットワーク）必要がある。
    # 既定の dir を見る側に倒すと、autoConnect が効いている大半の回に、使わないプロファイルを掴む
    # 別セッションのブラウザを止める確認が出て、「止めない」を選ぶと動く chrome-devtools まで基盤から外れる。
    # 版落ちの回は最初の呼び出しが `already running for <既定の dir>` で失敗し、その dir を --dir に渡す
    # ui-verify の保険で拾う
    autoConnect) DIR_SOURCE=autoConnect; DIR="" ;;
    userDataDir) DIR_SOURCE=userDataDir; DIR="$BROWSER_CONNECT_DIR" ;;
    *) DIR_SOURCE=default; DIR="${HOME}/.cache/chrome-devtools-mcp/chrome-profile" ;;
  esac
fi
# chrome-devtools-mcp は dir を加工せずに puppeteer へ渡し、puppeteer は絶対パスなら無加工で、それ以外は
# MCP の cwd を起点に絶対化して --user-data-dir=<dir> を作る（`~` は展開しない。1.11.0 の実物で確認）。
# 絶対パスの末尾の / はコマンド行に残るので、ここで落として uses_profile が / の有無の両方を当てる。
# symlink は解決しない
if [ "$DIR" != "/" ]; then
  DIR="${DIR%/}"
fi

# --- プロセスの観測（ps は macOS / Linux procps の共通部分だけを使う） ---
proc_stat() { ps -o stat= -p "$1" 2>/dev/null | tr -d ' '; }
proc_ppid() { ps -o ppid= -p "$1" 2>/dev/null | tr -d ' '; }
proc_cmd() { ps -ww -o command= -p "$1" 2>/dev/null; }
proc_started() { ps -o lstart= -p "$1" 2>/dev/null | sed 's/^ *//; s/ *$//'; }

# kill -0 は zombie にも成功するので使わない（SIGTERM の後、親が wait するまで zombie で残る）
alive() {
  case "$(proc_stat "$1")" in
    ''|Z*) return 1 ;;
  esac
  return 0
}

# lock の pid の再利用を見分ける: その pid が --user-data-dir=<dir> か --user-data-dir=<dir>/ を 1 語として
# 持つか（<dir>-beta のような前方一致は別プロファイル）
uses_profile() {
  case " $(proc_cmd "$1") " in
    *" --user-data-dir=${DIR} "*|*" --user-data-dir=${DIR}/ "*) return 0 ;;
  esac
  return 1
}

# chrome-devtools-mcp 本体: node が process.title を書き換えた形と、build/ を直接指す node の形。
# `npm exec chrome-devtools-mcp@latest`（起動ラッパの親）も同じ MCP の一部として拾う
is_mcp() {
  local cmd first
  cmd=$(proc_cmd "$1")
  first="${cmd%% *}"
  if [ "${first##*/}" = chrome-devtools-mcp ]; then
    return 0
  fi
  case "$cmd" in
    *"/chrome-devtools-mcp/build/"*|*"chrome-devtools-mcp@"*) return 0 ;;
  esac
  return 1
}

LOCK=""; REASON=""; HOLDER_PID=""; HOLDER_STARTED=""; HOLDER_MCP_PID=""; HOLDER_MCP_STARTED=""; HOLDER_SESSION=""

judge_session() {
  local claude="${CLAUDE_PID:-}" claude_ok=0 self=0 p n=0
  # 0 / 1 は全プロセスの祖先側なので「このセッション」の印にならない
  if [[ "$claude" =~ ^[0-9]+$ ]] && [ "$claude" -gt 1 ] && alive "$claude"; then
    claude_ok=1
  fi
  p=$(proc_ppid "$HOLDER_PID")
  while [[ "$p" =~ ^[0-9]+$ ]] && [ "$p" -gt 1 ] && [ "$n" -lt 64 ]; do  # mutation-ok: 打ち切り（pid 1 以下・64 段）をどれだけ緩めても、pid 0 / 1 は MCP にも有効な CLAUDE_PID にもならず結果は同じ（64 段の祖先を作るテストは置かない）
    if [ "$claude_ok" = 1 ] && [ "$p" -eq "$claude" ]; then
      self=1
    fi
    if [ -z "$HOLDER_MCP_PID" ] && is_mcp "$p"; then
      HOLDER_MCP_PID="$p"
    fi
    p=$(proc_ppid "$p")
    n=$((n + 1))
  done
  if [ -n "$HOLDER_MCP_PID" ]; then
    HOLDER_MCP_STARTED=$(proc_started "$HOLDER_MCP_PID")
  fi
  if [ "$self" = 1 ]; then
    HOLDER_SESSION=self
  elif [ -z "$HOLDER_MCP_PID" ]; then
    HOLDER_SESSION=orphan
  elif [ "$claude_ok" = 1 ]; then
    HOLDER_SESSION=other
  else
    HOLDER_SESSION=unknown
  fi
}

judge_lock() {
  local lock target host pid
  if [ -z "$DIR" ]; then
    LOCK=none
    return
  fi
  case "$DIR" in
    /*) ;;
    *) LOCK=unknown; REASON="dir が絶対パスでない（userDataDir は絶対パスで書く）"; return ;;
  esac
  lock="${DIR}/SingletonLock"
  if [ ! -L "$lock" ]; then
    if [ -e "$lock" ]; then
      LOCK=unknown
      REASON="SingletonLock が symlink でない"
    else
      LOCK=none
    fi
    return
  fi
  # Chrome は SingletonLock を `<hostname>-<pid>` を指す symlink として作る（hostname 自体に - を含む）
  target=$(readlink "$lock" 2>/dev/null || true)
  case "$target" in
    ?*-*) ;;
    *) LOCK=unknown; REASON="SingletonLock の指す先が <host>-<pid> の形でない"; return ;;
  esac
  host="${target%-*}"
  pid="${target##*-}"
  if ! [[ "$pid" =~ ^[0-9]+$ ]]; then
    LOCK=unknown
    REASON="SingletonLock の指す先が <host>-<pid> の形でない"
    return
  fi
  if [ "$host" != "$(uname -n)" ]; then
    LOCK=foreign-host
    return
  fi
  if ! alive "$pid" || ! uses_profile "$pid"; then
    LOCK=stale
    return
  fi
  LOCK=held
  HOLDER_PID="$pid"
  HOLDER_STARTED=$(proc_started "$pid")
  judge_session
}

print_status() {
  printf 'PROFILE_DIR=%s\nDIR_SOURCE=%s\nLOCK=%s\nREASON=%s\n' "$DIR" "$DIR_SOURCE" "$LOCK" "$REASON"
  printf 'HOLDER_PID=%s\nHOLDER_STARTED=%s\n' "$HOLDER_PID" "$HOLDER_STARTED"
  printf 'HOLDER_MCP_PID=%s\nHOLDER_MCP_STARTED=%s\n' "$HOLDER_MCP_PID" "$HOLDER_MCP_STARTED"
  printf 'HOLDER_SESSION=%s\n' "$HOLDER_SESSION"
}

judge_lock
print_status
if [ "$CMD" = status ]; then
  exit 0
fi

# --- stop: 確認の後に lock が変わっていないか（pid の再利用・別ブラウザへの入れ替わり）を確かめ直してから送る ---
REFUSED=""
if [ "$LOCK" != held ]; then
  REFUSED=not-held
elif [ "$HOLDER_PID" != "$PID_ARG" ]; then
  REFUSED=pid-mismatch
elif [ "$HOLDER_SESSION" = self ]; then
  REFUSED=self
elif [ "$HOLDER_SESSION" = unknown ]; then
  REFUSED=session-unknown
fi
if [ -n "$REFUSED" ]; then
  printf 'REFUSED=%s\nSTOPPED=no\n' "$REFUSED"
  exit 3
fi

# SIGTERM だけを lock の holder（ブラウザ本体）に送る。renderer 等の子は本体の終了に連れて終わる。
# SIGKILL はプロファイルの書き出しと lock の解放を飛ばすので送らない。
# 送れずに相手が生きている（EPERM など）ときは待たない: 待ち切った exit 1 は「SIGTERM で終わらない」と読まれる。
# 送れなくても相手が既に終わっていた（ESRCH）なら、下の待ちで STOPPED=yes になる
if ! kill -TERM "$PID_ARG" 2>/dev/null && alive "$PID_ARG"; then
  printf 'REFUSED=signal-failed\nSTOPPED=no\n'
  exit 3
fi
WAIT="${CHROME_PROFILE_LOCK_WAIT:-10}"
if ! [[ "$WAIT" =~ ^[0-9]+$ ]]; then
  WAIT=10
fi
TICKS=$((WAIT * 5))
i=0
while alive "$PID_ARG"; do
  if [ "$i" -ge "$TICKS" ]; then  # mutation-ok: -gt にしても 0.2 秒 1 回ぶん待つだけで結果は同じ
    printf 'STOPPED=no\n'
    exit 1
  fi
  sleep 0.2
  i=$((i + 1))
done
printf 'STOPPED=yes\n'
exit 0
