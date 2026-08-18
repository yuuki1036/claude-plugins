#!/usr/bin/env bash
# プロジェクトが宣言した「安いオラクル」を agent 起動前に 1 本だけ走らせ、digest を出す。
#
# **なぜプラグイン側でコマンドを決めないか**（GitHub issue #137 / ADR-20260817170000）:
# self-review は任意のプロジェクトで動くので、lint / 型 / テストの起動コマンドを
# プラグインの知識として持てない（`package.json` から推測すると誤検出時に任意の
# コマンドを走らせることになる）。**何を安いオラクルとみなすかはプロジェクトの判断**なので、
# リポジトリルートの `.claude/review-oracles.sh` の**存在そのもの**を宣言として扱う。
#
# 使い方:
#   run-oracles.sh [--timeout <秒>] [--max-lines <行>]
#
# 出力（宣言が無ければ**何も出さず exit 0**。no-op を報告させない）:
#   ## machine-layer
#   status=green|red|timeout|error     … green 以外は「緑ではない」ことだけを意味する
#   exit_code=<N>
#   elapsed_sec=<N>
#   log=<全文のパス>
#   （以下、出力の先頭 max-lines 行）
#
# **縮退先は green ではなく欠測。** タイムアウト・実行エラーを「緑」に倒すと、
# 機械層が死んでいる状態と通っている状態が区別できなくなる（reviewer は「既知」の
# 空リストを見て「機械層は何も検出しなかった」と読む）。
set -uo pipefail

LIMIT=300; MAX_LINES=40
while [ $# -gt 0 ]; do
  case "$1" in
    --timeout)   [ $# -ge 2 ] || { echo "FATAL: --timeout に値が必要" >&2; exit 2; }; LIMIT="$2"; shift 2 ;;
    --max-lines) [ $# -ge 2 ] || { echo "FATAL: --max-lines に値が必要" >&2; exit 2; }; MAX_LINES="$2"; shift 2 ;;
    *) echo "usage: run-oracles.sh [--timeout <秒>] [--max-lines <行>]" >&2; exit 2 ;;
  esac
done
for v in LIMIT MAX_LINES; do
  eval "val=\$$v"
  case "$val" in ''|*[!0-9]*) echo "FATAL: $v は数値のみ（受領: '$val'）" >&2; exit 2 ;; esac
done

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -n "$ROOT" ] || exit 0
ORACLE="$ROOT/.claude/review-oracles.sh"
# 宣言が無いプロジェクトでは完全に no-op（後方互換）
[ -f "$ORACLE" ] || exit 0

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/review-paths.sh
. "$HERE/lib/review-paths.sh"
review_paths_init "" || exit 2
LOG=$(review_path oracles) || exit 2
# 前回の残骸を残さない（配る前に消す規約）。書けないときだけ TMPDIR 直下へ退避する
: > "$LOG" 2>/dev/null || LOG="${TMPDIR:-/tmp}/review-oracles-$$.log"

# **job control を有効にして子をプロセスグループのリーダーにする**（macOS に `timeout` が無い）。
# グループごと kill しないと、テストランナーの孫プロセスがタイムアウト後も走り続ける
set -m
STATUS=green; RC=0
SECONDS=0
# **リポジトリルートで実行する**。self-review は worktree に入らないので cwd は
# セッション起動 dir のままで、サブディレクトリから起動されるとプロジェクト側の
# script が相対パスを解決できない（triage-signals.sh の起動 dir 依存と同じ失敗モード）
( cd "$ROOT" && bash "$ORACLE" ) >"$LOG" 2>&1 &
pid=$!
waited=0
# **条件は while の見出しに置く**（`|| break` で抜ける形にすると、打ち切りを外す変異が
# 「`$waited` が増えないまま回り続ける」無限ループになり、テストで殺せなくなる）。
while kill -0 "$pid" 2>/dev/null && [ "$waited" -lt "$LIMIT" ]; do  # mutation-ok: 境界を広げても待ちが 1 秒延びるだけ（秒単位の実時間はテストで固定しない）
  sleep 1
  waited=$((waited+1))
done
if kill -0 "$pid" 2>/dev/null; then
  kill -TERM -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
  sleep 1
  kill -KILL -"$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null
  STATUS=timeout; RC=-1
else
  wait "$pid"; RC=$?
  # 126/127 は「実行できなかった」なので red（=検出した）と区別する
  case "$RC" in
    0)         STATUS=green ;;
    # **2 は「判定不能」**（機械層の契約 / `.claude/review-oracles.sh` の宣言）。
    # red に落とすと「検査が問題を検出した」として提示され、直せないもの
    # （jsonschema 未導入等）に「直しますか？」と聞くことになる
    2|126|127) STATUS=error ;;
    *)         STATUS=red ;;
  esac
fi
set +m
ELAPSED=$SECONDS

echo "## machine-layer"
echo "status=$STATUS"
echo "exit_code=$RC"
echo "elapsed_sec=$ELAPSED"
echo "log=$LOG"
# 空／不在の判定は `-s` で行う（`total -gt 0` だと「常に真」に変異させても
# `head` が無出力で挙動が変わらず、偽の生存として一覧に残る）
total=$(grep -c '' "$LOG" 2>/dev/null || echo 0)
if [ -s "$LOG" ]; then
  head -n "$MAX_LINES" "$LOG"
  [ "$total" -gt "$MAX_LINES" ] && printf '... (+%d 行省略。全文は %s)\n' "$((total - MAX_LINES))" "$LOG"
fi
exit 0
