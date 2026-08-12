#!/usr/bin/env bash
# レビュー所要時間の区間マーカーを記録・集計する。
#
# 区間の意味と設計意図の正本: references/orchestration-measurement.md `## 14`
# パス導出の正本: scripts/lib/review-paths.sh（式をここに複製しない）
#
# シェル変数は Bash 呼び出し間で消えるため、マーカーは必ずファイルで受け渡す。
#
# 使い方:
#   review-timing.sh start [--pr N]                   # t0 を記録（新規作成）
#   review-timing.sh mark <t1|t1b|t1c|t2> [--pr N]    # マーカー追記（t1 は二重記録しない）
#   review-timing.sh durations [--pr N]               # "DUR TRIAGE FLEET CLOSING EXPLORE SYNTHESIS" を出力
#   review-timing.sh cleanup [--pr N]                 # t2 がある場合のみ削除
#
# t1c は **agent wave を回収するたびに追記してよい**（durations は最後の値を採る）。
# 「どの wave が最後か」をオーケストレーターに予測させないための設計。
set -uo pipefail

CMD="${1:-}"; shift || true
KEY=""
case "$CMD" in
  mark) KEY="${1:-}"; shift || true ;;
esac
PR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --pr) [ $# -ge 2 ] || { echo "FATAL: --pr に値が必要" >&2; exit 2; }; PR="$2"; shift 2 ;;
    # 未知引数を黙殺しない。`--PR` のような綴り違いを黙って無視すると start と mark が
    # 別ファイルを掴み、durations が全欠測(-1)になる（計測が silent に壊れる）
    *) echo "FATAL: 未知の引数: $1" >&2; exit 2 ;;
  esac
done

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/review-paths.sh
. "$HERE/lib/review-paths.sh"
review_paths_init "$PR" || exit 2
TS_FILE=$(review_path timing)

case "$CMD" in
  start)
    echo "t0 $(date +%s)" > "$TS_FILE"
    echo "$TS_FILE"
    ;;
  mark)
    case "$KEY" in
      t1)
        # explorer / reviewer の両起動点に同じ呼び出しを置き、先に到達した方だけが書く
        grep -q '^t1 ' "$TS_FILE" 2>/dev/null || echo "t1 $(date +%s)" >> "$TS_FILE"
        ;;
      t1b|t1c|t2)
        # t1c は複数回追記されうる（wave ごと）。durations 側の awk が後勝ちで
        # 最後の値を採るため、「最後の wave だったか」を呼び出し側が判断しなくてよい
        echo "$KEY $(date +%s)" >> "$TS_FILE"
        ;;
      *) echo "FATAL: mark のキーは t1 / t1b / t1c / t2 のいずれか（受領: '$KEY'）" >&2; exit 2 ;;
    esac
    ;;
  durations)
    # 欠測はすべて -1（0 と区別する）。t3（全体の終わり）は呼び出し時刻を使う
    NOW=$(date +%s)
    # t1c が複数行あるときは後勝ち（= 最後の agent wave の回収時刻）になる
    awk -v now="$NOW" '{t[$1]=$2} END {
      printf "%d %d %d %d %d %d\n",
        ("t0" in t) ? int((now - t["t0"])/60) : -1,
        ("t0" in t && "t1" in t) ? int((t["t1"] - t["t0"])/60) : -1,
        ("t1" in t && "t2" in t) ? int((t["t2"] - t["t1"])/60) : -1,
        ("t2" in t) ? int((now - t["t2"])/60) : -1,
        ("t1" in t && "t1b" in t) ? int((t["t1b"] - t["t1"])/60) : -1,
        ("t1c" in t && "t2" in t) ? int((t["t2"] - t["t1c"])/60) : -1
    }' "$TS_FILE" 2>/dev/null || echo "-1 -1 -1 -1 -1 -1"
    ;;
  cleanup)
    # t2 の存在確認は所有権チェックではなく、万一パスが衝突したときに
    # 「掃除より他セッションの計測を優先する」ための二段目
    { grep -q '^t2 ' "$TS_FILE" 2>/dev/null && rm -f "$TS_FILE"; } || true
    ;;
  *)
    echo "usage: review-timing.sh <start|mark|durations|cleanup> [--pr N]" >&2; exit 2 ;;
esac
exit 0
