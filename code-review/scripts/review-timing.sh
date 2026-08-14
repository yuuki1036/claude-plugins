#!/usr/bin/env bash
# レビュー所要時間の区間マーカーを記録・集計する。
#
# 区間の意味と設計意図の正本: references/orchestration-measurement.md `## 14`
# パス導出の正本: scripts/lib/review-paths.sh（式をここに複製しない）
#
# シェル変数は Bash 呼び出し間で消えるため、マーカーは必ずファイルで受け渡す。
#
# 使い方:
#   review-timing.sh start [--pr N]                        # t0 を記録（新規作成）
#   review-timing.sh mark t1 [--pr N]                      # 最初の一括発行の直前（二重記録しない）
#   review-timing.sh mark wave [--explorer] [--pr N]       # agent wave を回収するたび
#   review-timing.sh mark t2 [--pr N]                      # 初回レポート出力の直後
#   review-timing.sh durations [--pr N]                    # "DUR TRIAGE FLEET CLOSING EXPLORE SYNTHESIS"
#   review-timing.sh t0 [--pr N]                           # t0 の epoch（無ければ空行）
#   review-timing.sh waves [--pr N]                        # explorer wave の発行回数
#   review-timing.sh gaps [--pr N]                         # 欠測マーカーの識別子（空白区切り。無ければ空行）
#   review-timing.sh cleanup [--pr N]                      # t2 がある場合のみ削除
#
# **打点の規約は 1 本にまとめてある**（v2.62.0 / GitHub issue #123 B）: 「agent wave を
# 回収したら `mark wave` を打つ。explorer wave なら `--explorer` を付ける」だけ。旧来の
# `mark t1b`（explorer 回収）/ `mark t1c`（その他の wave 回収）は **エイリアスとして受理**
# するが、規約としては `wave` に一本化した。打点の種類を毎回判断させると落ちるため。
#
# ファイル中の行は `t0` / `t1` / `we`（explorer wave）/ `w`（その他の agent wave）/ `t2`。
# `we` と `w` は wave ごとに追記され、durations は**それぞれ最後の行**を採る。
# **`we` を synthesis 側に混ぜないこと** — explorer 回収だけ打って reviewer wave の打点を
# 落とした場合、混ぜると synthesis が reviewer wave を丸ごと含む「もっともらしい過大値」
# になる。縮退先は欠測（-1）であって誤値ではない。
#
# **`mark` は失敗しない**（v2.62.0）: `start` 未実行・一時ファイル消失でもファイルを作り直し、
# stderr に警告を出して exit 0 で返す。マーカー 1 個の失敗でレビュー本体を止めないため。
set -uo pipefail

CMD="${1:-}"; shift || true
KEY=""
case "$CMD" in
  mark) KEY="${1:-}"; shift || true ;;
esac
PR=""
IS_EXPLORER=0
while [ $# -gt 0 ]; do
  case "$1" in
    --pr) [ $# -ge 2 ] || { echo "FATAL: --pr に値が必要" >&2; exit 2; }; PR="$2"; shift 2 ;;
    --explorer) IS_EXPLORER=1; shift ;;
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

# 欠測マーカーの識別子を列挙する（duration_* が -1 になる原因だけを出す）。
# `we` の欠測は explorer 未起動でも起きるので**ここには含めない** — explorer を起動したか
# どうかは publish 側だけが知っている（publish-review-event.sh が判定して足す）。
emit_gaps() {
  local gaps=""
  grep -q '^t0 ' "$TS_FILE" 2>/dev/null || gaps="$gaps start"
  grep -q '^t1 ' "$TS_FILE" 2>/dev/null || gaps="$gaps t1"
  grep -q '^w '  "$TS_FILE" 2>/dev/null || gaps="$gaps wave"
  grep -q '^t2 ' "$TS_FILE" 2>/dev/null || gaps="$gaps t2"
  echo "${gaps# }"
}

case "$CMD" in
  start)
    echo "t0 $(date +%s)" > "$TS_FILE"
    echo "$TS_FILE"
    ;;
  mark)
    # start を踏んでいない / 一時ファイルが消えた場合でも打点を捨てない。
    # t0 が無いぶん t0 起点の区間は -1（欠測）になるが、それは誤値より望ましい
    if [ ! -f "$TS_FILE" ]; then
      : > "$TS_FILE" 2>/dev/null || true
      echo "WARN: 計測ファイルが無いので作り直した（start 未実行 / 別 slug の可能性）: $TS_FILE" >&2
    fi
    case "$KEY" in
      t1)
        # explorer / reviewer の両起動点に同じ呼び出しを置き、先に到達した方だけが書く
        grep -q '^t1 ' "$TS_FILE" 2>/dev/null || echo "t1 $(date +%s)" >> "$TS_FILE"
        ;;
      wave)
        if [ "$IS_EXPLORER" = "1" ]; then
          echo "we $(date +%s)" >> "$TS_FILE"
        else
          echo "w $(date +%s)" >> "$TS_FILE"
        fi
        ;;
      # 旧キー（v2.61.0 以前の呼び出し）。規約は `wave` に一本化したが受理は続ける
      t1b) echo "we $(date +%s)" >> "$TS_FILE" ;;
      t1c) echo "w $(date +%s)" >> "$TS_FILE" ;;
      t2)
        echo "t2 $(date +%s)" >> "$TS_FILE"
        # レポートを出した時点で agent wave の打点が 1 つも無いのは打ち忘れ。
        # ここで言えば「まだ publish 前」なので次回以降の是正には間に合う
        grep -q '^w ' "$TS_FILE" 2>/dev/null || \
          echo "WARN: agent wave の打点（mark wave）が 1 つも無い。duration_synthesis_min が欠測になる" >&2
        ;;
      *) echo "FATAL: mark のキーは t1 / wave / t2（旧: t1b / t1c）のいずれか（受領: '$KEY'）" >&2; exit 2 ;;
    esac
    ;;
  durations)
    # 欠測はすべて -1（0 と区別する）。t3（全体の終わり）は呼び出し時刻を使う。
    # `we` / `w` が複数行あるときはそれぞれ後勝ち（= 最後の explorer wave / 最後の agent wave）
    NOW=$(date +%s)
    awk -v now="$NOW" '{t[$1]=$2} END {
      printf "%d %d %d %d %d %d\n",
        ("t0" in t) ? int((now - t["t0"])/60) : -1,
        ("t0" in t && "t1" in t) ? int((t["t1"] - t["t0"])/60) : -1,
        ("t1" in t && "t2" in t) ? int((t["t2"] - t["t1"])/60) : -1,
        ("t2" in t) ? int((now - t["t2"])/60) : -1,
        ("t1" in t && "we" in t) ? int((t["we"] - t["t1"])/60) : -1,
        ("w"  in t && "t2" in t) ? int((t["t2"] - t["w"])/60)  : -1
    }' "$TS_FILE" 2>/dev/null || echo "-1 -1 -1 -1 -1 -1"
    ;;
  t0)
    # レビュー開始の epoch。トークン計測の窓を「この回のレビュー」に絞るために publish が使う
    # （GitHub issue #126）。**欠測は空行**で返す — 0 や現在時刻へ倒すと窓が全セッション /
    # 空区間に化けるので、呼び出し側が「窓を絞れなかった」と判定できるようにする
    awk '$1=="t0" {print $2; found=1} END {if (!found) print ""}' "$TS_FILE" 2>/dev/null || echo ""
    ;;
  waves)
    # explorer wave の本数 = `we` の行数。一括発行が守られていれば 1（explorer 未起動なら 0）。
    # 2 以上は「explorer を複数メッセージに分けて発行した」＝ wave 1 本ぶんの損失を意味する
    # `grep -c` は 0 件でも "0" を出したうえで exit 1 するので `||` で足すと 2 行出る。
    # 代入で受けて空（ファイル無し）だけを 0 に倒す
    N_WE=$(grep -c '^we ' "$TS_FILE" 2>/dev/null)
    echo "${N_WE:-0}"
    ;;
  gaps)
    emit_gaps
    ;;
  cleanup)
    # t2 の存在確認は所有権チェックではなく、万一パスが衝突したときに
    # 「掃除より他セッションの計測を優先する」ための二段目
    { grep -q '^t2 ' "$TS_FILE" 2>/dev/null && rm -f "$TS_FILE"; } || true
    ;;
  *)
    echo "usage: review-timing.sh <start|mark|durations|t0|waves|gaps|cleanup> [--pr N]" >&2; exit 2 ;;
esac
exit 0
