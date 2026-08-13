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
read -r DUR DUR_TRIAGE DUR_FLEET DUR_CLOSING DUR_EXPLORE DUR_SYNTHESIS <<< "${DURS:--1 -1 -1 -1 -1 -1}"

# explorer wave の発行回数（`we` マーカーの行数）。一括発行が破られたことを事後に検知する
# ための計測で、LLM の自己申告ではなくマーカーから導出する（GitHub issue #122）
EXPLORER_WAVES=$(bash "$HERE/review-timing.sh" waves ${PR_ARGS[@]+"${PR_ARGS[@]}"} 2>/dev/null)
case "$EXPLORER_WAVES" in ''|*[!0-9]*) EXPLORER_WAVES=0 ;; esac

# 欠測マーカーの識別子（`measurement_gaps`）。区間フィールドが -1 になった理由を
# 「打ち忘れ」と「そもそも該当しない」に分けて事後集計できるようにする（issue #123 B）。
# 値は review-timing.sh が持つ（打点の正本はあちら側なので判定式を複製しない）
MEASUREMENT_GAPS=$(bash "$HERE/review-timing.sh" gaps ${PR_ARGS[@]+"${PR_ARGS[@]}"} 2>/dev/null)

# 同一 diff への重複レビューを事後に突合するためのキー（issue #123 D）。
# diff ファイルは publish 後の掃除で消えるので、ここで撮っておく。
# **強弱 2 本ある**（算出と使い分けの正本: lib/review-paths.sh の `review_diff_keys`）
DIFF_FILE_PATH=$(review_path diff)
DIFF_DIGEST=""; DIFF_FILES=""
if KEYS=$(review_diff_keys "$DIFF_FILE_PATH"); then
  read -r DIFF_DIGEST DIFF_FILES <<< "$KEYS"
fi

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
  REVIEW_DURS="{\"duration_min\":$DUR,\"duration_triage_min\":$DUR_TRIAGE,\"duration_fleet_min\":$DUR_FLEET,\"duration_closing_min\":$DUR_CLOSING,\"duration_explore_min\":$DUR_EXPLORE,\"duration_synthesis_min\":$DUR_SYNTHESIS}" \
  REVIEW_EXPLORER_WAVES="$EXPLORER_WAVES" \
  REVIEW_MEASUREMENT_GAPS="$MEASUREMENT_GAPS" \
  REVIEW_DIFF_DIGEST="$DIFF_DIGEST" \
  REVIEW_DIFF_FILES="$DIFF_FILES" \
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

# agents.explorer_waves も同じくマーカー由来の値で上書きする（自己申告させない）。
# 一括発行が守られていれば explorer 起動時 1 / 未起動 0。2 以上は wave 1 本ぶんの損失
waves = int(os.environ.get("REVIEW_EXPLORER_WAVES") or 0)
agents = payload.get("agents")
if not isinstance(agents, dict):
    agents = {}
    payload["agents"] = agents
agents["explorer_waves"] = waves
launched = agents.get("explorer")

# 欠測マーカーの識別子。explorer wave の欠測だけは「起動したのに打点が無い」ときのみ
# gap であり、explorer 未起動なら該当なしなので、体数を知っているここで足す
gaps = [g for g in os.environ.get("REVIEW_MEASUREMENT_GAPS", "").split() if g]
if isinstance(launched, int) and launched >= 1 and waves == 0:
    gaps.append("explorer-wave")

digest = os.environ.get("REVIEW_DIFF_DIGEST") or ""
files_key = os.environ.get("REVIEW_DIFF_FILES") or ""
if digest:
    payload["diff_digest"] = digest
    if files_key:
        payload["diff_files"] = files_key
else:
    # 突合キーを作れなかった＝重複検出が事後に効かない。**該当なしと区別できるよう
    # gap を立てる**（この経路を黙らせると「検出できなかった」が「重複が無かった」に潰れる）
    gaps.append("diff-digest")

# gaps の確定はここ（append する経路をすべて通した後に代入する）
payload["measurement_gaps"] = gaps

if waves >= 2:
    sys.stderr.write(
        "WARN: explorer wave が %d 本ある（一括発行が破られた可能性）。"
        "1 メッセージにまとめていれば wave 内最長の 1 本で済む — orchestration-guide.md `## 0`\n" % waves
    )
elif "explorer-wave" in gaps:
    sys.stderr.write(
        "WARN: explorer を %s 体起動したのに explorer wave の打点が無い（explorer_waves が欠測）。"
        "回収直後の `review-timing.sh mark wave --explorer` を打ち忘れている\n" % launched
    )
if gaps:
    sys.stderr.write(
        "WARN: 計測マーカーの欠測: %s（対応する duration_* が -1 で publish される）\n" % ", ".join(gaps)
    )
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
