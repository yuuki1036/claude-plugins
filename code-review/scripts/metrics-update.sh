#!/usr/bin/env bash
# metrics-update.sh — 計測の更新（`/code-review:metrics-update`）の決定的な部分。GitHub issue #480
#
# Usage:
#   metrics-update.sh [report] [--logs <path>...] [--store <dir> | --no-store] [--state <file>] [--record]
#                     [--json] [--split-version <版>] [--generation <世代>]
#   metrics-update.sh retro [--logs <path>...] [--store <dir> | --no-store] [review-retro.sh の引数...]
#   metrics-update.sh workdir    # 本文ファイルと --json の出力を置く作業用 dir を作り、`dir=<path>` を出す
#
# report（既定）は見た範囲・前回からの差分・比較表・`## 15` の更新条件・語彙落ちを出す。既定は読むだけで、
# `--record` を付けたときだけ前回の実行時点を状態ファイルに書く。retro は report と同じ母集団
# （計測ストアの events と手元のログ）を `review-retro.sh --logs` に渡す。本体は lib/metrics_update.py。
# workdir は毎回新しい名前で 0700 の dir を作る（mktemp -d）。固定の名前にすると、共有の /tmp で他の利用者が
# 先に置いた symlink の先へ書きうる（mkdir -p・chmod・[ -O ] はどれも symlink をたどる）。
#
# 計測ストアの既定は REVIEW_METRICS_DIR（未設定なら ~/.claude/review-metrics）。無ければ手元のログだけで回す。
# `--logs` を渡さなければ、このリポジトリの events.jsonl（review_event_logs）を手元のログにする。
#
# 終了コード: 0 = 正常 / 2 = 判定不能（引数の誤り・明示したパスが読めない・状態ファイルが壊れている・
# python3 が無い・集計の異常終了・workdir で dir を作れない）
set -uo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/review-paths.sh
# review_paths_init（レビュー用の一時 dir の作成）は呼ばない。この skill の作業用 dir は workdir が作る
. "$HERE/lib/review-paths.sh"

if [ "${1:-}" = "workdir" ]; then
  WD=$(mktemp -d "${TMPDIR:-/tmp}/claude-metrics-update.XXXXXX") || { echo "FATAL: 作業用 dir を作れない" >&2; exit 2; }
  echo "dir=${WD}"
  exit 0
fi

command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 が必要" >&2; exit 2; }

MODE=report
case "${1:-}" in
  report|retro) MODE="$1"; shift ;;
esac

LOGS=(); LOGS_GIVEN=0; SRC_ARGS=(); REST=()
while [ $# -gt 0 ]; do
  case "$1" in
    # 後続の非フラグ引数をすべて取る（シェルの glob をそのまま渡せる形。retro の --logs と同じ）
    --logs)
      shift; LOGS_GIVEN=1
      while [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; do LOGS+=("$1"); shift; done
      [ ${#LOGS[@]} -gt 0 ] || { echo "FATAL: --logs にパスが必要" >&2; exit 2; }
      ;;
    --store) [ $# -ge 2 ] || { echo "FATAL: --store に値が必要" >&2; exit 2; }; SRC_ARGS+=("$1" "$2"); shift 2 ;;
    --no-store) SRC_ARGS+=("$1"); shift ;;
    *) REST+=("$1"); shift ;;
  esac
done

if [ "$LOGS_GIVEN" = "0" ] && review_event_logs; then
  LOGS=("${REVIEW_EVENT_LOGS[@]}")
fi
# 空の --logs は argparse の nargs='*' が [] にする。空配列の展開は bash 3.2 の set -u で落ちるので + の形で書く
LOG_ARGS=(--logs ${LOGS[@]+"${LOGS[@]}"})

REPO=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

if [ "$MODE" = "retro" ]; then
  SOURCES=()
  LISTED=$(python3 "$HERE/lib/metrics_update.py" --list-sources \
    ${SRC_ARGS[@]+"${SRC_ARGS[@]}"} ${LOG_ARGS[@]+"${LOG_ARGS[@]}"}) && RC=0 || RC=$?
  [ "$RC" = "0" ] || exit 2
  while IFS= read -r _p; do
    [ -n "$_p" ] && SOURCES+=("$_p")
  done <<< "$LISTED"
  if [ ${#SOURCES[@]} -gt 0 ]; then
    exec bash "$HERE/review-retro.sh" --logs "${SOURCES[@]}" ${REST[@]+"${REST[@]}"}
  fi
  exec bash "$HERE/review-retro.sh" ${REST[@]+"${REST[@]}"}
fi

exec python3 "$HERE/lib/metrics_update.py" --repo "$REPO" \
  ${SRC_ARGS[@]+"${SRC_ARGS[@]}"} ${LOG_ARGS[@]+"${LOG_ARGS[@]}"} ${REST[@]+"${REST[@]}"}
