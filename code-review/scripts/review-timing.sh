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
#   review-timing.sh mark published [--pr N]               # publish 成功の直後（publish スクリプトが呼ぶ）
#   review-timing.sh durations [--pr N]                    # "DUR TRIAGE FLEET CLOSING EXPLORE SYNTHESIS"
#            [--derived-t1 E] [--derived-explore E] [--derived-wave E]
#                                                          # 打点が**無い**区間だけを実測値で埋める（#161）
#   review-timing.sh epochs [--pr N]                       # "t0 t1 we w t2"（欠測は `-`）
#   review-timing.sh t0 [--pr N]                           # t0 の epoch（無ければ空行）
#   review-timing.sh waves [--pr N]                        # explorer wave の発行回数
#   review-timing.sh gaps [--pr N]                         # 欠測マーカーの識別子（空白区切り。無ければ空行）
#   review-timing.sh publish-pending [--pr N]              # t2 あり & pub なしなら警告（それ以外は無言）
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
D_T1=""; D_WE=""; D_W=""
while [ $# -gt 0 ]; do
  case "$1" in
    --pr) [ $# -ge 2 ] || { echo "FATAL: --pr に値が必要" >&2; exit 2; }; PR="$2"; shift 2 ;;
    --explorer) IS_EXPLORER=1; shift ;;
    # **打点が落ちた区間を agent transcript の実測時刻で埋める**（GitHub issue #161）。
    # 値は `publish-review-event.sh` が `measure-tokens.sh --json` の `wave_clock` から
    # 算出して渡す（どの wave が explorer かの突合は `agents` を持つあちら側の責務）。
    # **打点が有る区間には触らない** — 補完は欠測の穴埋めであって上書きではない
    --derived-t1)      [ $# -ge 2 ] || { echo "FATAL: --derived-t1 に値が必要" >&2; exit 2; }; D_T1="$2"; shift 2 ;;
    --derived-explore) [ $# -ge 2 ] || { echo "FATAL: --derived-explore に値が必要" >&2; exit 2; }; D_WE="$2"; shift 2 ;;
    --derived-wave)    [ $# -ge 2 ] || { echo "FATAL: --derived-wave に値が必要" >&2; exit 2; }; D_W="$2"; shift 2 ;;
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
        # publish の脱落を「その場で見える」ようにする（GitHub issue #133）。publish は計測ファイル
        # への副作用が本体で**レポートには何も足さない**ため、踏み忘れても実行中は誰も気づかない
        # （成功時に `published to ...` の 1 行を出すが、それは踏んだときにしか出ないので脱落の
        # 検知には使えない）。**次にやることではなく「締めの終点」として言う** — ここで「次は
        # publish」と書くと review の締めフロー 1〜3（精査・解説・ドラフト）を飛ばす誘導になる
        echo "t2 記録。レポート後の締めは **publish（self-review Step 6.4 / review 締めフロー 4）で終わる**。"
        echo "publish を踏まずに次のフェーズ（指摘の修正 / worktree 掃除）へ進まないこと。"
        ;;
      # publish 成功の記録（v2.66.0 / GitHub issue #133）。**`publish-pending` の判定根拠**で、
      # `publish-review-event.sh` が `event_bus_publish` に成功したときだけ打つ。
      # 掃除でファイルごと消えるのが通常経路なので、この行が效くのは `--keep-temp` の回
      published) echo "pub $(date +%s)" >> "$TS_FILE" ;;
      *) echo "FATAL: mark のキーは t1 / wave / t2 / published（旧: t1b / t1c）のいずれか（受領: '$KEY'）" >&2; exit 2 ;;
    esac
    ;;
  durations)
    # 欠測はすべて -1（0 と区別する）。t3（全体の終わり）は呼び出し時刻を使う。
    # `we` / `w` が複数行あるときはそれぞれ後勝ち（= 最後の explorer wave / 最後の agent wave）
    NOW=$(date +%s)
    # **数値以外は黙って捨てる**。呼び出し側の算出が失敗して空文字や `-` が来たとき、
    # awk が 0 に coerce して「1970 年に wave を回収した」ような巨大な区間を作るのを防ぐ
    case "$D_T1" in ''|*[!0-9]*) D_T1="" ;; esac
    case "$D_WE" in ''|*[!0-9]*) D_WE="" ;; esac
    case "$D_W"  in ''|*[!0-9]*) D_W=""  ;; esac
    awk -v now="$NOW" -v d_t1="$D_T1" -v d_we="$D_WE" -v d_w="$D_W" '
    function span(a, b,   d) {
      if (!(a in t) || !(b in t)) return -1
      d = int((t[b] - t[a]) / 60)
      # **負の区間は誤値**（補完値の矛盾 / 時計のずれ）。打点だけなら時刻は単調増加なので
      # 起こりえない。`## 14` の原則どおり**縮退先は欠測であって誤値ではない**
      return (d < 0) ? -1 : d
    }
    { t[$1] = $2 }
    END {
      t["t3"] = now
      # **打点が有る側が常に勝つ**（issue #161）
      if (!("t1" in t) && d_t1 != "") t["t1"] = d_t1
      if (!("we" in t) && d_we != "") t["we"] = d_we
      if (!("w"  in t) && d_w  != "") t["w"]  = d_w
      printf "%d %d %d %d %d %d\n",
        span("t0", "t3"), span("t0", "t1"), span("t1", "t2"),
        span("t2", "t3"), span("t1", "we"), span("w", "t2")
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
  epochs)
    # 打点の**生の epoch**（`t0 t1 we w t2` / 欠測は `-`）。`durations` が分を返すのに対し、
    # こちらは publish 側が **①どのマーカーが落ちているか（＝補完対象）** と
    # **②補完値が下限・上限（`t0` / `t1` / `t2`）に矛盾しないか**を判定するために出す。
    # `we` / `w` は①の存在判定に使い、値は比較に入れない（相互順序は publish 側が別途見る）。
    # `we` / `w` は複数行あるとき **後勝ち**（`durations` の awk と同じ規約）
    awk '{t[$1]=$2} END {
      printf "%s %s %s %s %s\n",
        ("t0" in t) ? t["t0"] : "-", ("t1" in t) ? t["t1"] : "-",
        ("we" in t) ? t["we"] : "-", ("w"  in t) ? t["w"]  : "-",
        ("t2" in t) ? t["t2"] : "-"
    }' "$TS_FILE" 2>/dev/null || echo "- - - - -"
    ;;
  gaps)
    emit_gaps
    ;;
  publish-pending)
    # publish（`review:completed`）を踏んだかを判定する（GitHub issue #133）。
    # 「**`t2` があって `pub` が無い**」＝レポートは出したが publish が成っていない。
    #
    # **`pub` を見る（ファイルの有無だけで判定しない）**: `publish-review-event.sh` は publish に
    # 成功したときだけ `mark published` を打ってから掃除する。ファイル不在で判定していた版は
    # ①publish が失敗した回（掃除は成否に関わらず走っていた）②`--keep-temp` の回、の 2 つを
    # 取り違えていた。**取りこぼしていたのは「イベントが書かれず打点も消えた」最悪の回**。
    #
    # 縮退の向き: ファイル不在は「publish 済みで掃除された」と「そもそも計測していない /
    # TMPDIR ごと消えた」の両方を含むので**無言で抜ける**。ここで警告すると publish 済みの回でも
    # 毎回鳴り、「⚠️ が出たときだけ行動する」という契約が壊れる
    if grep -q '^t2 ' "$TS_FILE" 2>/dev/null && ! grep -q '^pub ' "$TS_FILE" 2>/dev/null; then
      echo "WARN: publish（review:completed）が未実施のまま次のフェーズへ進もうとしている。" >&2
      echo "  → 先に publish を実行する（self-review Step 6.4 / review 締めフロー 4）。" >&2
      echo "  → **t2 直後に戻れば損失はない**が、修正作業などで時間が経っていると" >&2
      echo "     duration_min が伸びる（self-review は 10 分以上で -1 = 欠測に倒れる）。" >&2
      echo "  → publish を試みて失敗した回もここで鳴る（一時ファイルを残してある）。" >&2
    fi
    ;;
  cleanup)
    # t2 の存在確認は所有権チェックではなく、万一パスが衝突したときに
    # 「掃除より他セッションの計測を優先する」ための二段目
    { grep -q '^t2 ' "$TS_FILE" 2>/dev/null && rm -f "$TS_FILE"; } || true
    ;;
  *)
    echo "usage: review-timing.sh <start|mark|durations|t0|epochs|waves|gaps|publish-pending|cleanup> [--pr N]" >&2; exit 2 ;;
esac
exit 0
