#!/usr/bin/env bash
# `review:completed` を Event Bus に publish する（fire-and-forget）。
#
# 呼び出し側（SKILL）は **意味のある数値だけ**を payload で渡す。所要時間フィールドは
# 本スクリプトが `review-timing.sh durations` から取って注入する（LLM に計算させない）。
#
# payload 契約の正本: references/orchestration-measurement.md `## 16`
# publish 先固定の理由: 同 `## 13`
#
# 使い方:
#   publish-review-event.sh --plugin code-review:review --pr 123 --payload '<json object>'
#   publish-review-event.sh --plugin code-review:self-review --payload-file /path/to.json
set -uo pipefail

PLUGIN=""; PR=""; PAYLOAD=""; PAYLOAD_FILE=""; KEEP=0
while [ $# -gt 0 ]; do
  case "$1" in
    --plugin)       [ $# -ge 2 ] || { echo "FATAL: --plugin に値が必要" >&2; exit 2; }; PLUGIN="$2"; shift 2 ;;
    --pr)           [ $# -ge 2 ] || { echo "FATAL: --pr に値が必要" >&2; exit 2; }; PR="$2"; shift 2 ;;
    --payload)      [ $# -ge 2 ] || { echo "FATAL: --payload に値が必要" >&2; exit 2; }; PAYLOAD="$2"; shift 2 ;;
    --payload-file) [ $# -ge 2 ] || { echo "FATAL: --payload-file に値が必要" >&2; exit 2; }; PAYLOAD_FILE="$2"; shift 2 ;;
    --keep-temp)    KEEP=1; shift ;;
    *) echo "FATAL: 未知の引数: $1" >&2; exit 2 ;;
  esac
done
[ -n "$PLUGIN" ] || { echo "FATAL: --plugin が必須" >&2; exit 2; }
if [ -n "$PAYLOAD_FILE" ]; then PAYLOAD=$(cat "$PAYLOAD_FILE" 2>/dev/null); fi
[ -n "$PAYLOAD" ] || { echo "FATAL: --payload か --payload-file が必須" >&2; exit 2; }

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/review-paths.sh
. "$HERE/lib/review-paths.sh"
review_paths_init "$PR" || exit 2

# python3 は必須。JSON の組み立てと検証を担うので、無い環境で「黙って検証をスキップ」
# させない（壊れた 1 行は events.jsonl 全体の集計を壊す）
command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 が必要（payload の検証・整形に使う）" >&2; exit 2; }

# ---- 書込先をメインリポジトリのルートに固定する -----------------------------
# review は EnterWorktree 後に呼ばれるため、cwd 相対のままだと worktree 側の
# events.jsonl に書かれ、直後の ExitWorktree(remove) で計測ごと消える。
# --git-common-dir は linked worktree からもメインの .git を返すので進入後でも導出できる。
GCD=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
# GCD が空のときに無条件で cd "$GCD/.." すると `/` に降りてしまうので必ず分岐する
MAIN_ROOT=$([ -n "$GCD" ] && (cd "$GCD/.." && pwd) || pwd)

# ---- 所要時間フィールドを注入 ----------------------------------------------
PR_ARGS=(); [ -n "$PR" ] && PR_ARGS=(--pr "$PR")
DURS=$(bash "$HERE/review-timing.sh" durations ${PR_ARGS[@]+"${PR_ARGS[@]}"} 2>/dev/null)
read -r DUR DUR_TRIAGE DUR_FLEET DUR_CLOSING DUR_EXPLORE <<< "${DURS:--1 -1 -1 -1 -1}"

# self-review は publish が「修正方針確認」より前にあり closing 区間が構造上 ≒0 になるため
# -1（測定不能）を入れる。0 を publish すると「人間待ちが無かった」と誤読される（`## 14`）
case "$PLUGIN" in *self-review) DUR_CLOSING=-1 ;; esac

# ---- payload をパース → duration_* を上書き → **1 行**に再シリアライズ -------
# テキスト合成（sed による除去 + 文字列連結）はやめた。以下 3 つを同時に踏んでいたため:
#   ① SKILL のテンプレートは複数行なので、改行がそのまま events.jsonl へ流れて
#      「1 行 = 1 イベント」が壊れる。json.load は改行を許すので検証をすり抜ける
#   ② duration_* の除去 sed が値の書式（整数リテラル）に依存し、漏れると重複キーの
#      「後勝ち」で注入値が負ける
#   ③ カンマ正規化 sed が JSON の文字列値の中身まで書き換える
# 再シリアライズなら 3 つとも構造的に起きない。
MERGED=$(
  REVIEW_DURS="{\"duration_min\":$DUR,\"duration_triage_min\":$DUR_TRIAGE,\"duration_fleet_min\":$DUR_FLEET,\"duration_closing_min\":$DUR_CLOSING,\"duration_explore_min\":$DUR_EXPLORE}" \
  python3 - "$PAYLOAD" <<'PY'
import json, os, sys
try:
    payload = json.loads(sys.argv[1])
except ValueError as e:
    sys.stderr.write("payload が valid JSON でない: %s\n" % e)
    sys.exit(1)
if not isinstance(payload, dict):
    sys.stderr.write("payload が JSON オブジェクトでない\n")
    sys.exit(1)
# duration_* は常にスクリプト側の値で上書きする（呼び出し側が渡していても勝つ）
payload.update(json.loads(os.environ["REVIEW_DURS"]))
# separators で空白・改行を排除し、1 行に収める
sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
PY
) || { echo "FATAL: payload を整形できない（publish 中止）" >&2; exit 1; }

# 念のための最終ガード。event_bus_publish は 1 行 1 イベント前提で追記する
case "$MERGED" in
  *$'\n'*) echo "FATAL: payload に改行が残っている（publish 中止）" >&2; exit 1 ;;
esac

# ---- publish（best-effort。失敗してもレビュー自体は成功扱い） ---------------
# shellcheck disable=SC1091
if source "${CLAUDE_PLUGIN_ROOT:-$HERE/..}/hooks/lib/safe-hook.sh" 2>/dev/null; then
  if CLAUDE_PROJECT_DIR="$MAIN_ROOT" SAFE_HOOK_NAME="$PLUGIN" \
       event_bus_publish "review:completed" "$MERGED"; then
    echo "published to $MAIN_ROOT/.claude/events.jsonl ($PLUGIN)"
  else
    echo "WARN: event_bus_publish に失敗した（計測データは欠測になる）" >&2
  fi
else
  echo "WARN: safe-hook.sh を読み込めず publish をスキップした" >&2
fi

# ---- 一時ファイルの掃除 -----------------------------------------------------
if [ "$KEEP" = "0" ]; then
  bash "$HERE/review-timing.sh" cleanup ${PR_ARGS[@]+"${PR_ARGS[@]}"}
  rm -f "$(review_path prctx)" "$(review_path diff)"
fi
exit 0
