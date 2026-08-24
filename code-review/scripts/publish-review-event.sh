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

# ---- 計測フィールドの収集 --------------------------------------------------
# **並び順に依存がある**（GitHub issue #161）: `durations` が `measure-tokens.sh` の結果を
# 必要とするため、**トークン計測 → 補完値の算出 → durations → late-publish 判定 →
# 窓の命名**の順に並べる（並べ替えると補完が効かない）。
PR_ARGS=(); [ -n "$PR" ] && PR_ARGS=(--pr "$PR")

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

# ---- トークン消費と発行パターン（issue #126 / #142 / #143） -----------------
# 体数削減が確実に効くのは壁時計ではなくトークン（triage-guide.md `## 7`）なのに、payload は
# 時間しか持っていなかった＝主要レバーの効果が自動集計の外にあった。publish はレポートの後
# ＝ transcript 確定後なので、ここでなら自分の回の消費量を読める。
#
# **self-review も載せる**（issue #143 で除外を撤回）。旧版は「self-review は publish の後に
# Step 7 の修正作業が続くので窓の外に本作業が続く」として除外していたが、`measure-tokens.sh` は
# **publish 時点の transcript を読む**ので、その時点で `t0 → publish` は閉じている（後続の修正は
# まだ transcript に存在しない）。除外が正当なのは**遅れて publish した回だけ**で、そこは
# `LATE_PUBLISH`（t2 から 10 分以上）で既に判定できているので `window` を分けて表現する。
# 実測: 除外していた間、このマシンの review:completed 37 件すべてで `tokens` が欠測だった。
TOKENS_JSON=""; TOKENS_WANTED=0; TOKENS_WINDOW="session"
TOK_ARGS=()
case "$PLUGIN" in
  *:review|*self-review)
    TOKENS_WANTED=1
    T0=$(bash "$HERE/review-timing.sh" t0 ${PR_ARGS[@]+"${PR_ARGS[@]}"} 2>/dev/null)
    case "$T0" in
      ''|*[!0-9]*) : ;;   # t0 欠測。窓を絞れないので --since なしで呼ぶ（下の window で区別する）
      *)
        # **末尾の `Z` を付けない**。transcript の timestamp は小数秒つき（`...:33.123Z`）で
        # measure-tokens.sh の絞り込みは文字列比較なので、`...:33Z` は同秒のメッセージより
        # 大きくなり境界の 1 秒ぶんを落とす。秒までの接頭辞なら常に手前に来る
        SINCE_ISO=$(python3 -c 'import sys,datetime;print(datetime.datetime.fromtimestamp(int(sys.argv[1]),datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"))' "$T0" 2>/dev/null)
        if [ -n "$SINCE_ISO" ]; then
          TOK_ARGS=(--since "$SINCE_ISO")
          # **窓の名前は late-publish 判定の後で確定させる**（判定は下の `durations` に
          # 依存し、その durations がこの計測結果に依存するため。`since-t0-late` への
          # 書き換えは LATE_PUBLISH の確定直後に行う）
          TOKENS_WINDOW="since-t0"
        fi
        ;;
    esac
    TOKENS_JSON=$(bash "$HERE/measure-tokens.sh" --json ${TOK_ARGS[@]+"${TOK_ARGS[@]}"} 2>/dev/null)
    ;;
esac

# ---- 打点が落ちた区間を agent の実測時刻で埋める（GitHub issue #161） -------
# 区間打点はオーケストレーターの記憶に依存しており、実測で **v2.62.0 以降の 10 件中
# 5 件が 1 つ以上落としていた**（`t1` 1 / `wave` 2 / `explorer-wave` 2 / `t2` 1）。
# 打ち手を決めるための #156 / #153 のサンプルが、どちらも打点漏れで区間内訳を欠いていた。
#
# **`## 14` の「逆算による補完はしない」には当たらない**。あの禁止の射程は *publish
# 時刻からの推定* で、それは誤値になる。ここで使うのは `measure-tokens.sh` が
# `wave_clock` に出す **agent transcript の実測時刻**で、#142 が `dispatch` で確立した
# 「wave は推定しない」経路と同じもの。**打点が有る区間には触らない**（review-timing 側で担保）。
#
# **`t2` は埋めない** — 初回レポート出力はメイン文脈のイベントで agent transcript に
# 現れない。publish 時刻から逆算すれば欠測は消えるが、それが禁止されている当のもの。
#
# **`t0` にアンカーされた窓の回だけ補完する**（セルフレビューで検出 / #161）。`t0` 打点が
# 欠けると `measure-tokens.sh` は `--since` なし＝**セッション全体**を窓にするので、
# `wave_clock` に同一セッションの無関係な agent が混ざる。しかも下の `ok()` は `t0` が
# 欠測だと下限チェックを飛ばすため、**何時間も前の別作業の agent 起動時刻**がそのまま
# `t1` の補完値になり、`duration_fleet_min` が「もっともらしい過大値」として publish される
# （実測: 本来 10 分の回が 120 分）。**この機構が守ろうとした原則そのものを破る経路**。
# `wave_clock` が「この回の agent だけ」であることの担保は窓しか無いので、窓の名前で判定する。
DERIVED_ARGS=(); DERIVED_MARKERS=""
if [ -n "$TOKENS_JSON" ] && [ "$TOKENS_WINDOW" = "since-t0" ]; then
  DERIVED=$(
    REVIEW_TOKENS="$TOKENS_JSON" \
    REVIEW_EPOCHS="$(bash "$HERE/review-timing.sh" epochs ${PR_ARGS[@]+"${PR_ARGS[@]}"} 2>/dev/null)" \
    python3 - "$PAYLOAD" <<'PY'
import json, os, sys


def _num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _emit(t1=None, we=None, w=None):
    """`T1 WE W MARKERS`（欠測は `-`）。**識別子は `measurement_gaps` と同じ語彙**に揃える."""
    names = {"t1": "t1", "we": "explorer-wave", "w": "wave"}
    got = [k for k, v in (("t1", t1), ("we", we), ("w", w)) if v is not None]
    print("%s %s %s %s" % (t1 if t1 is not None else "-", we if we is not None else "-",
                           w if w is not None else "-",
                           ",".join(names[k] for k in got) or "-"))
    sys.exit(0)


try:
    tok = json.loads(os.environ.get("REVIEW_TOKENS") or "null")
except ValueError:
    tok = None
clock = tok.get("wave_clock") if isinstance(tok, dict) else None
# `wave_clock` は **`unresolved` が無い回にだけ**入る（wave 構成が信用できない回は出ない）
if not isinstance(clock, list) or not clock:  # mutation-ok: `wave_clock` は `None` か非空リストしか来ない（`measure-tokens.sh` は `waves_by_msg` が空なら `None` を出す）ので and/or の差が観測できない
    _emit()

raw = ((os.environ.get("REVIEW_EPOCHS") or "").split() + ["-"] * 5)[:5]
t0, t1, we, w, t2 = (_num(x) for x in raw)

# `agents.explorer` は SKILL の自己申告。**explorer wave の同定には突合としてしか使わない**
# （体数が一致しなければ埋めない ＝ 推定に落とさない / #142 の原則）
#
# **`agents` は truthy な非 dict になりうる**（`{"agents": 12}` 等。SKILL テンプレートを
# LLM が埋めるフィールドなので現実的な入力）。`or {}` は falsy しか吸収しないため、
# 旧版は `.get()` が try の**外**にあり未捕捉 `AttributeError` で補完が丸ごと no-op に
# なっていた。**同ファイルの payload 構築側は元から `isinstance` で正規化しており**、
# 新規ブロックだけがその不変条件を落としていた（セルフレビューで検出 / #161）
try:
    agents = (json.loads(sys.argv[1]) or {}).get("agents")
except (ValueError, AttributeError, IndexError):
    agents = None
if not isinstance(agents, dict):
    agents = {}
explorer_n = agents.get("explorer")
if not isinstance(explorer_n, int) or isinstance(explorer_n, bool) or explorer_n < 0:
    explorer_n = 0


def ok(v, lo):
    """`v` が**取れている**下限・上限（`t0` / `lo` / `t2`）に矛盾しないときだけ採る.

    **矛盾する補完はしない** — 順序が崩れた値を入れると区間が負や過大になり、
    「もっともらしい誤値」を publish することになる（`## 13.1` と同じ原則）。

    **欠測した側は制約なしとして扱う**（打点漏れが前提の機構なので `t0` / `t2` / `lo` は
    欠けうる）。`t0` が欠ける回そのものは呼び出し側が窓で弾いているので、ここに来る時点で
    `t0` は在る。実効条件は「`v` が `max(t0, lo)` 以上、かつ `t2` 以下」。
    """
    if v is None:
        return False  # mutation-ok: 呼び出し側は `ok(X)` が真のとき同じ `X` を代入するので、`None` を通しても代入されるのは `None`（出力が変わらない）
    if t0 is not None and v < t0:  # mutation-ok: 窓を `since-t0` に限定したので publish 経路からは到達しない防御（`wave_clock` の agent は必ず t0 以降に起動している）
        return False  # mutation-ok: 上の行と同じ理由で到達しない
    if t2 is not None and v > t2:
        return False
    return not (lo is not None and v < lo)


d_t1 = d_we = d_w = None

# t1 = **最初の agent の起動時刻**。打点の定義は「最初の一括発行の直前」で、差は agent 起動の
# オーバーヘッドぶん（秒オーダー）。区間は分で持つので丸めに吸収される
if t1 is None and ok(_num(clock[0].get("start")), t0):
    d_t1 = _num(clock[0].get("start"))

eff_t1 = t1 if t1 is not None else d_t1

# w = **最終 wave** の終了時刻。`end` は wave 内の全体の終了が取れたときだけ入るので、
# 1 体でも欠ければここも埋まらない（#153 の縮退方向）
if w is None and ok(_num(clock[-1].get("end")), eff_t1):
    d_w = _num(clock[-1].get("end"))

# we = 先頭から累積して `agents.explorer` に**ちょうど一致**する wave 群の終了時刻。
# 一致しない回（explorer を複数 wave に割った回・Round 2 の追加 explorer が混ざった回）は
# 埋めない。**「先頭 wave = explorer」と決め打たない**のがこの突合の目的
if we is None and explorer_n > 0:
    acc = 0
    for i, wave in enumerate(clock):
        acc += _num(wave.get("n")) or 0
        if acc > explorer_n:
            break  # mutation-ok: `n` は 1 以上（`measure-tokens.sh` の `len(w)`）なので acc は狭義単調増加。一度超えたら二度と一致しない
        if acc == explorer_n:
            ends = [_num(x.get("end")) for x in clock[:i + 1]]
            if all(e is not None for e in ends) and ok(max(ends), eff_t1):
                d_we = max(ends)
            break  # mutation-ok: 同上（次の周回で必ず acc が explorer_n を超え、上の break に落ちる）

# **explorer wave が最終 wave より後に終わっていたら explorer 側を落とす**。`clock` は
# **start でソート**されているので `clock[-1]` は「最後に起動した wave」であって「最後に
# 終わった wave」とは限らない。`we > w` のまま通すと `duration_explore_min` と
# `duration_synthesis_min` が重なり、`review-timing.sh` 冒頭が名指しで禁じている
# 「もっともらしい過大値」になる。**縮退させるのは we 側**（`w` は synthesis の起点で
# 影響が大きく、explorer 区間は fleet の内数なので落としても和は壊れない）
_last = w if w is not None else d_w
if d_we is not None and _last is not None and d_we > _last:
    d_we = None

_emit(d_t1, d_we, d_w)
PY
  # **異常終了は「補完対象が無かった」と区別する**（セルフレビューで検出 / #161）。
  # 両方を `DERIVED_MARKERS=""` に潰すと、機構が落ちた回が retro の「補完条件を満たさなかった
  # 回」に紛れ、**効果測定の当のフィールドが失敗を成功と同じ形で記録する**。このリポジトリは
  # 同型の状況で一貫して gap を立てている（`dispatch` / `diff-digest` / `tokens`）
  ) || { DERIVED=""; MEASUREMENT_GAPS="${MEASUREMENT_GAPS:+$MEASUREMENT_GAPS }derived"; }
  read -r _D_T1 _D_WE _D_W DERIVED_MARKERS <<< "${DERIVED:-"- - - -"}"
  [ "$_D_T1" = "-" ] || DERIVED_ARGS+=(--derived-t1 "$_D_T1")
  [ "$_D_WE" = "-" ] || DERIVED_ARGS+=(--derived-explore "$_D_WE")
  [ "$_D_W"  = "-" ] || DERIVED_ARGS+=(--derived-wave "$_D_W")
  [ "$DERIVED_MARKERS" = "-" ] && DERIVED_MARKERS=""
fi

# ---- 所要時間フィールドを注入 ----------------------------------------------
DURS=$(bash "$HERE/review-timing.sh" durations ${PR_ARGS[@]+"${PR_ARGS[@]}"} \
       ${DERIVED_ARGS[@]+"${DERIVED_ARGS[@]}"} 2>/dev/null)
read -r DUR DUR_TRIAGE DUR_FLEET DUR_CLOSING DUR_EXPLORE DUR_SYNTHESIS <<< "${DURS:--1 -1 -1 -1 -1 -1}"

# self-review は publish が「修正方針確認」より前にあり closing 区間が構造上 ≒0 になるため
# -1（測定不能）を入れる。0 を publish すると「人間待ちが無かった」と誤読される（`## 14`）
#
# **遅れて publish した回（t2 から 10 分以上）は `duration_min` を欠測に倒す**（GitHub issue #133）。
# self-review の `duration_min` は「t0 → Step 6.4」という契約なので、publish 脱落に後から気づいて
# 修正作業の後に踏むと、契約と違う区間を**もっともらしい大きい値**として載せてしまう。t2→publish の
# 生値（closing を -1 に潰す前）でしか判定できないのでここで見る。**review には掛けない** — あちらは
# 締めフロー（人間待ち）を含むのが契約なので、大きいこと自体は正常
LATE_PUBLISH=0
case "$PLUGIN" in
  *self-review)
    case "$DUR_CLOSING" in
      ''|-1|*[!0-9-]*) : ;;
      *) [ "$DUR_CLOSING" -ge 10 ] && LATE_PUBLISH=1 ;;
    esac
    DUR_CLOSING=-1
    ;;
esac
[ "$LATE_PUBLISH" = "1" ] && DUR=-1

# **遅れて publish した回は窓に修正作業が混ざる**ので別の名前で出す（判定が上の
# `DUR_CLOSING` に依存するのでここで確定させる）。集計側は `since-t0` だけを使う契約
# なので、混ざった回は自動的に外れる
if [ "$LATE_PUBLISH" = "1" ] && [ "$TOKENS_WINDOW" = "since-t0" ]; then
  TOKENS_WINDOW="since-t0-late"
fi

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
  REVIEW_DERIVED_MARKERS="$DERIVED_MARKERS" \
  REVIEW_DIFF_DIGEST="$DIFF_DIGEST" \
  REVIEW_DIFF_FILES="$DIFF_FILES" \
  REVIEW_TOKENS="$TOKENS_JSON" \
  REVIEW_TOKENS_WANTED="$TOKENS_WANTED" \
  REVIEW_TOKENS_WINDOW="$TOKENS_WINDOW" \
  REVIEW_LATE_PUBLISH="$LATE_PUBLISH" \
  python3 - "$PAYLOAD" <<'PY'
import json, os, re, sys
try:
    payload = json.loads(sys.argv[1])
except ValueError as e:
    sys.stderr.write("payload が valid JSON でない: %s\n" % e)
    sys.exit(1)
if not isinstance(payload, dict):
    sys.stderr.write("payload が JSON オブジェクトでない\n")
    sys.exit(1)

# ---- `missing_coverage` の語彙検証（GitHub issue #132） ---------------------
# 規約は「識別子のみ」（正本: references/orchestration-measurement.md `## 16` の
# 「`missing_coverage` の記法」）なのに検証が無く、実データに理由つき自由文が 12 種混入して
# **同一観点が別項目として数えられていた**（`adversarial-verify` が 4 項目に分裂）。欠損観点の
# 偏りを見るのが本フィールドの唯一の用途なので、綴りが割れると計測目的そのものが消える。
#
# **JSON 妥当性検証と同じ位置で fail-fast する**（黙って正規化しない）。理由・補足はレポート
# 本文の「⚠️ 欠損観点」に書く規約なので、落として直させても情報は失われない。
#
# **`fullmatch` を使う（`match` + `$` ではない）**: Python の `$` は文字列末尾の改行 1 個の直前にも
# マッチするため、`match` だと `"recall-skeptic\n"` が通る。`json.dumps` が `\n` をエスケープして
# 1 行 JSON は壊れないので**下流のどの検証にも引っかからず**、塞いだはずの綴り割れが復活する。
# publish 全体を落とす代償を払う検証なので、緩い一致で妥協しない。
MC_RE = re.compile(r"[a-z0-9-]+(:[a-z0-9-]+)?")
mc = payload.get("missing_coverage")
if mc is not None:
    if not isinstance(mc, list):
        sys.stderr.write("missing_coverage が配列でない（空なら [] を渡す）\n")
        sys.exit(1)
    bad = [x for x in mc if not (isinstance(x, str) and MC_RE.fullmatch(x))]
    if bad:
        sys.stderr.write(
            "missing_coverage に識別子以外が混ざっている: %s\n"
            "許容形は `<focus 名>` / `<phase 名>` / `<phase 名>:<focus 名>`（小文字・数字・`-` のみ。"
            "例 `error-handling` / `recall-skeptic` / `explorer:value-flow-trace`）。\n"
            "**理由・件数・finding id はレポート本文の「⚠️ 欠損観点」に書く**（payload は集計用）。\n"
            "**フィールドごと落として通さないこと** — 欠落は measurement_gaps に記録される。\n"
            % json.dumps(bad, ensure_ascii=False)
        )
        sys.exit(1)

# ---- `findings_class` の検証（v2.68.0） --------------------------------------
# **このフィールドは「次に何を機械化すべきか」を決めるメーター**なので、汚染時の損失が
# 他のフィールドより大きい。にもかかわらず正本（`## 16`）の「合計は報告件数と一致させる」は
# 規約だけで強制力が無かった — `missing_coverage` が「規約だけでは守られず実データに自由文が
# 12 種混入していた」（issue #132）のと同じ型。同じ位置で fail-fast する。
fc = payload.get("findings_class")
if fc is not None:
    if not isinstance(fc, dict):
        sys.stderr.write("findings_class が JSON オブジェクトでない\n")
        sys.exit(1)
    bad = [k for k in ("lint", "test", "judgement")
           if not isinstance(fc.get(k), int) or isinstance(fc.get(k), bool) or fc.get(k) < 0]
    if bad:
        sys.stderr.write(
            "findings_class の %s が非負整数でない（lint / test / judgement の 3 つとも必須）\n"
            % ", ".join(bad)
        )
        sys.exit(1)
    counts = [payload.get(k) for k in
              ("blocker_count", "critical_count", "major_count", "minor_count")]
    # **件数フィールドが揃っている回だけ突合する**（揃っていない回を落とすと、
    # 契約の範囲外まで publish を止めることになる）
    if all(isinstance(c, int) and not isinstance(c, bool) for c in counts):
        total = fc["lint"] + fc["test"] + fc["judgement"]
        if total != sum(counts):
            sys.stderr.write(
                "findings_class の合計 %d が報告件数 %d と一致しない"
                "（blocker %d / critical %d / major %d / minor %d）。"
                "**分類は報告した指摘だけを数える** — 閾値を割った指摘は含めない\n"
                % (total, sum(counts), *counts)
            )
            sys.exit(1)

# ---- `below_threshold_counts` の検証（v2.71.0 / GitHub issue #146） ------------
# **`pre_adjust_counts` に足し込んだぶんの再掲**なので、元より大きい値は定義上ありえない
# （足し忘れか二重計上のどちらか）。合算しか残っていないと **(a) 本文を書いてから捨てた**
# （出力トークンの純損失）と **(b) 件数だけ返した**（既に節約できている）が分離できず、
# 閾値注入（#117）の効果を判定できない。**分離がこのフィールドの唯一の用途**なので、
# 汚染を通すと足した意味がそのまま消える。`findings_class` と同じ位置・流儀で fail-fast する。
SEVS = ("blocker", "critical", "major", "minor")
bt = payload.get("below_threshold_counts")
if bt is not None:
    if not isinstance(bt, dict):
        sys.stderr.write("below_threshold_counts が JSON オブジェクトでない\n")
        sys.exit(1)
    bad = [k for k in SEVS
           if not isinstance(bt.get(k), int) or isinstance(bt.get(k), bool) or bt.get(k) < 0]
    if bad:
        sys.stderr.write(
            "below_threshold_counts の %s が非負整数でない（%s の 4 つとも必須。"
            "0 件でもキーを省かない — 「閾値未満が無かった」と「数えなかった」を潰さないため）\n"
            % (", ".join(bad), " / ".join(SEVS))
        )
        sys.exit(1)
    pre = payload.get("pre_adjust_counts")
    # **`pre_adjust_counts` が揃っている回だけ突合する**（揃っていない回を落とすと契約の
    # 範囲外まで publish を止めることになる / `findings_class` の合計突合と同じ理由）
    if isinstance(pre, dict) and all(
            isinstance(pre.get(k), int) and not isinstance(pre.get(k), bool) for k in SEVS):
        over = ["%s（%d > %d）" % (k, bt[k], pre[k]) for k in SEVS if bt[k] > pre[k]]
        if over:
            sys.stderr.write(
                "below_threshold_counts が pre_adjust_counts を超えている: %s\n"
                "**`pre_adjust_counts` は `## below-threshold` を足し込んだ合算**で、"
                "`below_threshold_counts` はそのうち足し込んだぶんの再掲。超えるのは "
                "pre 側への足し忘れか below 側の二重計上（orchestration-measurement.md `## 16`）\n"
                % ", ".join(over)
            )
            sys.exit(1)

# ---- 降格の型別内訳の検証（GitHub issue #150） --------------------------------
# **件数だけでは打ち手が決まらない**。`severity_inflated` がどの降格典型で落ちたかが残らないと、
# 上流較正が「型が的外れ」なのか「そもそも上流で直せない」のかを切り分けられない
# （実測: 同一版・同一 effort・同一ゲートで review 側だけ 84-90% / self-review は 50%）。
# 合計の突合まで見るのは `findings_class` と同じ理由 — **内訳が本体とずれた時点で
# 「型が取れなかった件」と「数え漏らした件」が混ざり、切り分けという唯一の用途が消える**。
DEMOTE_TYPES = ("base_derived", "misread", "overstated_impact", "miscategorized", "unknown")


def check_demote_types(d, parent, field):
    """5 キーの非負整数を要求して合計を返す（0 件でもキーを省かせない）。"""
    bad = [k for k in DEMOTE_TYPES
           if not isinstance(d.get(k), int) or isinstance(d.get(k), bool) or d.get(k) < 0]
    if bad:
        sys.stderr.write(
            "%s.%s の %s が非負整数でない（%s の 5 つとも必須。0 件でもキーを省かない — "
            "「その型が無かった」と「数えなかった」を潰さないため）\n"
            % (parent, field, ", ".join(bad), " / ".join(DEMOTE_TYPES))
        )
        sys.exit(1)
    return sum(d[k] for k in DEMOTE_TYPES)


av = payload.get("adversarial_verify")
if isinstance(av, dict) and isinstance(av.get("inflated_axes"), dict):
    axes_total = check_demote_types(av["inflated_axes"], "adversarial_verify", "inflated_axes")
    infl = av.get("severity_inflated")
    if isinstance(infl, int) and not isinstance(infl, bool) and axes_total != infl:
        sys.stderr.write(
            "inflated_axes の合計 %d が severity_inflated %d と一致しない\n"
            "**軸が返らなかった・語彙外だった件は `unknown` に落とす**（型が取れなくても件数は"
            "落とさない）。反証プロンプトの axis 語彙は prompts/adversarial-verify.md\n"
            % (axes_total, infl)
        )
        sys.exit(1)

if isinstance(bt, dict) and isinstance(bt.get("demoted_types"), dict):
    dem_total = check_demote_types(bt["demoted_types"], "below_threshold_counts", "demoted_types")
    # **SEVS の型は上のブロックで検証済み**（`bt` が dict なら 4 キーとも非負整数を通っている）。
    # ここで再判定を挟むと**通らない分岐**になり、壊しても誰も気づかない
    below_total = sum(bt[k] for k in SEVS)
    if dem_total > below_total:
        sys.stderr.write(
            "demoted_types の合計 %d が below_threshold_counts の合計 %d を超えている\n"
            "**跨ぐ降格で落ちた指摘は `## below-threshold` に計上されている**ので、"
            "内訳が本体を超えるのは二重計上か本体への足し忘れ"
            "（orchestration-measurement.md `## 16`）\n"
            % (dem_total, below_total)
        )
        sys.exit(1)

# ---- 動的層の `skip_reason` の語彙検証（v2.79.0 / `missing_coverage` と同型） ----
# **正本（`## 16`）は層ごとに語彙を決めているのに検証が無かった** — `missing_coverage` が
# 「規約だけでは守られず実データに自由文が 12 種混入していた」（issue #132）のとまったく
# 同じ型で、実測でも `no-surface` が `surface-none` / `surface-not-detected` に割れていた
# （全リポジトリ 91 件のうち 3 件。うち 1 件は #132 の対策より後）。retro の skip 理由集計は
# `group_by` なので、**綴りが割れると「どのゲートで落ちているか」という唯一の用途が
# その件数ぶん消える**。しかも消えたことが `unknown` ではなく別バケツとして出るので、
# 集計を見ても欠測に見えない。
#
# **語彙外は fail-fast**（`missing_coverage` と同じ理由 — 正しい値は呼び出し側が知っており、
# 落として直させても情報は失われない。黙って正規化はしない＝どれに寄せるかを推測すると
# 別の綴り割れを作る）。**`fired=false` なのに `skip_reason` が無い回は gap に倒す**
# （下の `payload:<field>.fired` と同じ流儀。書き忘れは寄せ先を推測できないので、
# 落とす側ではなく可視化する側に置く）。
SKIP_REASONS = {
    "adversarial_verify": ("effort", "config", "scope", "emergency", "no-eligible-findings"),
    "recall_skeptic":     ("effort", "config", "no-surface", "emergency", "scope"),
    "meta_reviewer":      ("effort", "config", "no-high-severity", "size-tier",
                           "emergency", "scope"),
}
for field, allowed in SKIP_REASONS.items():
    d = payload.get(field)
    # **`fired` が厳密に False の回だけ見る**。層ごとの欠落・`fired` の欠落は下の gap 側の
    # 担当で、ここで拾うと同じ欠落に 2 つの是正先が立つ
    if not isinstance(d, dict) or d.get("fired") is not False:
        continue
    sr = d.get("skip_reason")
    if sr is not None and sr not in allowed:
        sys.stderr.write(
            "%s.skip_reason が語彙外: %s\n"
            "許容値は %s（正本: references/orchestration-measurement.md `## 16`）。\n"
            "**理由の補足はレポート本文に書く** — payload は集計用で、綴りが割れると "
            "group_by が成立しない。**フィールドごと落として通さないこと**（欠落は "
            "measurement_gaps に記録される）\n"
            % (field, json.dumps(sr, ensure_ascii=False), " / ".join(allowed))
        )
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

# 上の語彙検証を「フィールドを消す」で回避されると、綴り割れの代わりに**静かな全欠測**になる。
# 欠落は空配列（＝欠損観点なし）と区別して可視化する（issue #132）
if mc is None:
    gaps.append("payload:missing_coverage")

# 遅れて publish した self-review（issue #133）。`duration_min` は -1 に倒してあるので、
# **なぜ欠測なのか**をここで残す（打点漏れと区別できないと是正先が分からない）
if os.environ.get("REVIEW_LATE_PUBLISH") == "1":
    gaps.append("late-publish")

# ---- 版マーカー（定数）の注入（GitHub issue #125） --------------------------
# 版マーカーは「常に N を入れる」定数なのに **LLM が手書きする 15 フィールドの一部**だった。
# テンプレート追従は version drift 中に漏れうる（実測: `recall_skeptic.gate_schema` に
# 導入後の miss / `calibration_schema` はテンプレ更新の 2 版跨ぎで落ちた）。落ちると
# サンプルが**逆の版バケツに入って集計を汚す**ので、単なる欠測より悪い。
#
# 本スクリプトは版付きディレクトリ（`.../code-review/<version>/scripts/`）配下にあり
# **自分の版の定数を知っている**ので、ここで上書きすれば手書き失敗モードが構造的に消える
# （`duration_*` / `explorer_waves` / `measurement_gaps` / `diff_digest` と同じ方式）。
#
# **正本は references/orchestration-measurement.md `## 16`。値を変えるときは両方を直す。**
SCHEMA_MARKERS = {
    "findings_class":     {"schema": 1},
    "pre_adjust_counts":  {"schema": 2},
    "below_threshold_counts": {"schema": 1},
    "adversarial_verify": {"calibration_schema": 2, "gate_schema": 2},
    "recall_skeptic":     {"attribution_schema": 2, "gate_schema": 2},
    "meta_reviewer":      {"gate_schema": 3},
}
for field, marks in SCHEMA_MARKERS.items():
    d = payload.get(field)
    if isinstance(d, dict):
        d.update(marks)          # 呼び出し側が渡していてもスクリプト側が勝つ
    else:
        # 層のオブジェクトごと落ちた回。版マーカーだけ作っても中身が無いので**注入しない**
        # （空の dict は retro の母集団に「起動記録なし」として混ざる）。可視化だけする
        gaps.append("payload:%s" % field)

# 発火記録（`fired` / `skip_reason`）は実行時の事実なのでスクリプトからは注入できない。
# **落ちたことだけは検知する** — `fired` が無いと retro は「走らなかった」と「走れる対象が
# 無かった」を区別できず、ゲート設計の妥当性を計測で判断できなくなる（issue #129）
for field in ("adversarial_verify", "recall_skeptic", "meta_reviewer"):
    d = payload.get(field)
    if not isinstance(d, dict):
        continue
    if "fired" not in d:
        gaps.append("payload:%s.fired" % field)
    # **`fired=false` なのに理由が無い回**（v2.79.0 / 実測 8/49 件）。retro の skip 理由集計では
    # `unknown` に化けるが、それだけでは「書き忘れ」と「その層に語彙が無い」を区別できない。
    # 上の語彙検証が語彙外を落とすので、**残る汚染はこの経路だけ**になる
    elif d.get("fired") is False and d.get("skip_reason") is None:
        gaps.append("payload:%s.skip_reason" % field)

# 型別内訳の記録漏れ（issue #150）。**「その型が無かった」と「数えなかった」を潰さない**ため、
# 内訳が要る回（降格が実際に起きた回）に限って gap を立てる。層ごとスキップした回や
# 閾値未満が 0 件の回まで gap にすると、記録漏れの信号がノイズに埋もれる
if isinstance(av, dict) and "inflated_axes" not in av:
    infl = av.get("severity_inflated")
    if isinstance(infl, int) and not isinstance(infl, bool) and infl > 0:
        gaps.append("payload:adversarial_verify.inflated_axes")
if isinstance(bt, dict) and "demoted_types" not in bt and sum(bt[k] for k in SEVS) > 0:
    gaps.append("payload:below_threshold_counts.demoted_types")

# ---- トークン消費と発行パターン（issue #126 / #142 / #143） -----------------
if os.environ.get("REVIEW_TOKENS_WANTED") == "1":
    try:
        tok = json.loads(os.environ.get("REVIEW_TOKENS") or "")
    except ValueError:
        tok = None
    main_n = (tok.get("main") or {}).get("n") if isinstance(tok, dict) else None
    if isinstance(tok, dict) and isinstance(main_n, int) and main_n > 0:
        def _k(side, key):
            v = (tok.get(side) or {}).get(key)
            return round(v / 1000.0, 1) if isinstance(v, (int, float)) else None
        payload["tokens"] = {
            # schema 2: `cache_read` 系を追加（GitHub issue #156）。**重み付けコスト
            # （output×5 / cache_write×1.25 / cache_read×0.1）では cache_read が最大**
            # （`pending-optimizations.md ## 計測の基準値` で 45%）なのに、schema 1 は
            # output と main の cache_write しか載せていなかった＝主要項が観測の外にあった。
            # `measure-tokens.sh --json` は元から返しているので取得経路の追加は無い
            "schema": 2,
            # 窓の種類。`session` は t0 を撮れずセッション全体を集計した回で、レビュー外の
            # 作業が混ざる。**集計側は since-t0 だけを使う**（混ぜると体数との対応が消える）
            "window": os.environ.get("REVIEW_TOKENS_WINDOW") or "session",
            # **どの transcript のどこからを数えたか**を残す（セッションの選択は「候補 dir の
            # 最新 .jsonl」という推定で、worktree 並列運用では取り違えうる）。値そのものは
            # もっともらしいので、この 2 つが無いと取り違えを事後に検出する手段が消える
            "session": tok.get("session"), "first_ts": tok.get("first_ts"),
            "main_output_k": _k("main", "output"),
            "main_cache_write_k": _k("main", "cache_write"),
            "main_cache_read_k": _k("main", "cache_read"),
            "sub_output_k": _k("sub", "output"),
            "sub_cache_write_k": _k("sub", "cache_write"),
            "sub_cache_read_k": _k("sub", "cache_read"),
            # 窓内に usage を持つ subagent の本数（`sub_files` = glob 総数は窓非適用なので
            # 載せない。同じオブジェクトに窓ありと窓なしを混在させない）
            "sub_agents": tok.get("sub_agents"),
        }
    else:
        # **`main.n == 0` は「トークンが 0 だった」ではない。** review は必ずメインループの
        # メッセージを出してから publish するので、0 は「transcript を引けなかった」か
        # 「窓が空振りした」を意味する。ゼロを実測値として載せると retro の中央値と
        # 体数相関を壊す（実測: 相関 r が 1.00 → 0.18）。**欠測は誤値より望ましい**
        gaps.append("tokens")

    # **モデル世代**（GitHub issue #169）。`effort` / `size_tier` / `reviewer_effort_profile` で
    # 層別する設計だが、Opus 5 と 4.8 が混ざるとその層別が成立しない（実測: 2026-08-24 の
    # 1 日で 3 サンプル中 2 件が 4.8）。世代はユーザーが実行時に選ぶもので（エイリアスは
    # 親世代を継ぐ / `docs/pipeline-design.md`）、**事故ではなく層別キー**として扱う。
    # **tokens とは独立に載せる**（窓が空振りしても世代は拾えることがある / dispatch と同じ流儀）。
    # 自己申告は無い — `measure-tokens.sh` が transcript の `message.model` から機械計測する
    # **呼び出し側が渡した値は捨てる**（`SKILL からは渡さない` 契約の fail-closed 側）。
    # 残すと、transcript を引けなかった回に **LLM が書いた世代が機械計測のふりをして残る**。
    # `models` は「自己申告は無い」ことが値の意味そのものなので、ここは黙って上書きしない
    payload.pop("models", None)
    mdl = tok.get("models") if isinstance(tok, dict) else None
    if isinstance(mdl, dict) and (mdl.get("main_distinct") or mdl.get("sub_distinct")):
        payload["models"] = mdl
    else:
        # 世代が引けない回を黙って落とさない。**「単一世代だった」に倒さない**のが要点で、
        # 倒すと交絡したサンプルが単一世代の分布に混ざる（`tokens` の 0 と同じ理由）
        gaps.append("models")

    # **軸を寄せ損ねた回を可視化する**（GitHub issue #167）。`inflated_axes` / `demoted_types` は
    # 反証 agent・reviewer が返す語彙を 4 型へ寄せて数える契約だが、**寄せ漏れは静かに通る** —
    # 合計の突合（上の fail-fast）は `unknown` に落としても一致するので検出できない。
    # 実測: `intended` 2 件が `base_derived` に寄らず `unknown` に落ち、review 側の唯一の
    # 型付きサンプルで `base_derived` を 8% と読むか 23% と読むかが変わった（#150 の判断材料）。
    #
    # **fail-fast にしない**。`unknown` は「軸が返らなかった」正当な回にも立つ値で、止めると
    # その回の計測が丸ごと消える（`agents-mismatch` と同じ判断。合計不一致を落とすのとは非対称で、
    # あちらは内訳が本体とずれた時点で切り分けという用途自体が消えるので落とす側）
    for _parent, _field, _gap in (("adversarial_verify", "inflated_axes", "axis-unknown"),
                                  ("below_threshold_counts", "demoted_types", "demoted-unknown")):
        _d = payload.get(_parent)
        _d = _d.get(_field) if isinstance(_d, dict) else None
        if isinstance(_d, dict) and isinstance(_d.get("unknown"), int) and _d["unknown"] > 0:
            gaps.append(_gap)

    # **発行パターンは tokens とは独立に載せる**（GitHub issue #142 / 判定単位は #149）。
    # 窓が空振りして `tokens` が欠測になった回でも、agent の発行元は拾えていることがある。
    # `duration_fleet_min` だけでは「9 体を逐次で回した 89 分」と「1 体が 89 分かかった」を
    # 区別できない。**判定単位は wave**（同一メッセージから出た agent の束）で、層をまたぐ
    # 逐次実行（explorer → reviewer → 反証）は設計上正当なので違反に数えない
    disp = tok.get("dispatch") if isinstance(tok, dict) else None
    if isinstance(disp, dict) and disp.get("verdict") not in (None, "unknown"):
        payload["dispatch"] = disp
        # **警告は `serial` だけ**。`layered`（層ごとの wave）は設計上正当な形なので、
        # 警告すると「⚠️ が出たときだけ行動する」契約が壊れる
        if disp.get("verdict") == "serial":
            sys.stderr.write(
                "WARN: agent を逐次発行している（%s 体 / %s wave / 単独 wave が %s 連続）。"
                "同一フェーズは 1 メッセージで一括発行すれば fleet は**wave 内最長の 1 体**で"
                "済む — orchestration-guide.md `## 0`「並列発行の明示」\n"
                "  → **レポート末尾に 1 行追記すること**: "
                "`⚠️ 計測: agent を逐次発行した（一括発行の規約違反 / #142）`\n"
                % (disp.get("agents"), disp.get("waves"), disp.get("max_solo_run"))
            )
        # ---- 自己申告（`agents`）と機械計測（`dispatch.agents`）の突合（issue #154） ----
        # **review 側だけ内訳合計が合わない**（実測: dispatch 28 に対し内訳 19 / 別の回は
        # 27 対 20。self-review は 6/6 件で完全一致）。`agents` は**体数中央値・体数 vs
        # fleet の相関・sub_output_k との相関**すべての分母なので、片方の skill で 3 割
        # 取りこぼしていると **review と self-review を並べた比較が成立しない**。
        #
        # **fail-fast にしない** — 差の存在自体が観測対象で、publish を止めると計測が丸ごと
        # 消える（`inflated_axes` の合計不一致を落とすのと非対称に扱う理由がここ。あちらは
        # 「内訳が本体とずれたら用途が消える」ので落とす側）。まず発生率を測る。
        #
        # **`agents` は動的層を含まない契約**（`## 16`: meta / skeptic は専用フィールドで
        # 観測する）なので、突合の前に `fired` の数を足す。この補正なしで比べると
        # self-review まで恒常的にずれ、**review 固有の欠陥という信号がノイズに埋もれる**。
        declared = sum(v for k, v in agents.items()
                       if k in ("explorer", "reviewer", "specialist", "round2", "verify")
                       and isinstance(v, int) and not isinstance(v, bool))
        declared += sum(1 for f in ("recall_skeptic", "meta_reviewer")
                        if isinstance(payload.get(f), dict) and payload[f].get("fired") is True)
        measured = disp.get("agents")
        # **差の大きさは gap に載せない**（`measurement_gaps` は識別子の配列という契約）。
        # 両フィールドが payload に残っているので、下流はいつでも引き算し直せる
        if isinstance(measured, int) and not isinstance(measured, bool) and measured != declared:
            gaps.append("agents-mismatch")

        # ---- wave 本数の期待値との突合（一括発行違反の全層検出 / GitHub issue #153 の続き） ----
        # 上の `serial` 判定は**単独 wave が 3 連続**を要求するので、「reviewer 5 体のうち
        # 1 体だけ先に出した」型を取り逃す（実測: fleet span の 20% ＝ 9 分を失った回が
        # `layered`（正常）と判定されていた）。`agents.explorer_waves` は explorer 層しか
        # 数えないので、こちらも同じ回を検出しない。**規約は全 agent に掛かる**（`## 0`）
        # のに、機械検出は 2 経路とも一部しか見ていなかった。
        #
        # **層の同定はしない。** `subagents/*.meta.json` の `description` は LLM の自由文で
        # 書式が安定しておらず（実測 25 セッションで大半が分類不能。日英混在・命名バラバラ）、
        # 分類器を置くと**静かに何も検出しない**方向に倒れる。既存フィールドの算術だけで見る。
        #
        # 期待本数は**保守側**（見込みを増やす方向）に倒す。取り逃しは出るが偽陽性は出にくい。
        # ただし skeptic の fallback 起動（`triage-dynamic-gates.md ## 8.5` / 真に単独 wave に
        # なる唯一の正規経路）は見込まない — 見込むと実測済みの違反 2 件を両方取り逃す。
        # **その偽陽性がどれだけ混ざるかを測るのが本 gap の目的**なので、まだ WARN は出さない
        # （`agents-mismatch` と同じ「まず発生率を測る」段階）。
        #
        # `waves_expected` は**常に載せる**ので、フィールドの存在自体が版マーカーになる
        # （`derived_markers` と同じ流儀。`dispatch.schema` は `measure-tokens.sh` が持つ
        # 版なので、publish 側の追加で上げると出所が 2 つに割れる）。
        def _agents_n(key):
            v = agents.get(key)
            return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else 0

        # **meta が指摘を足した回は反証 wave が 1 本増える**（GitHub issue #166）。
        # meta 由来の `[meta]` タグ付き指摘を反証にかける追加バッチは、**meta の出力が
        # 存在しない時点では発行できない**ので構造的な直列であって一括発行違反ではない。
        # `meta_reviewer` は `agents` に計上しない契約（`## 16`）なので、この 1 本は
        # 既存の式のどの項にも現れず、実運用で初めて `wave-split` が立ったとき偽陽性だった。
        #
        # **`findings_added` が 1 以上**を条件にする。実際の追加バッチは「足した指摘のうち
        # 反証ゲートに該当する分があるとき」だけ起動するので、これは見込みの上側（保守側）。
        # 本ブロックの方針どおり、取り逃しを許して偽陽性を出さない方へ倒す
        def _meta_added_findings():
            m = payload.get("meta_reviewer")
            if not isinstance(m, dict) or m.get("fired") is not True:
                return False
            n = m.get("findings_added")
            return isinstance(n, int) and not isinstance(n, bool) and n > 0

        expected = ((1 if _agents_n("explorer") > 0 else 0) + 1
                    + (1 if _agents_n("verify") > 0 else 0)
                    + (2 if _agents_n("round2") > 0 else 0)
                    + (1 if _meta_added_findings() else 0))
        payload["dispatch"] = dict(disp, waves_expected=expected)
        waves = disp.get("waves")
        # **`agents-mismatch` の回では判定しない** — 期待本数は `agents` の自己申告から作るので、
        # 申告が壊れている回に重ねると**原因の違う 2 つの信号**が混ざって是正先を指せなくなる
        if ("agents-mismatch" not in gaps and isinstance(waves, int)
                and not isinstance(waves, bool) and waves > expected):
            gaps.append("wave-split")
    else:
        # 判定できなかった（agent 0 体 / transcript や meta.json を引けない）。**「一括だった」
        # にも「逐次だった」にも倒さない** — 規約が守られたことの証拠が無い回として残す
        gaps.append("dispatch")

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
# **打点漏れを実測時刻で埋めたマーカー**（GitHub issue #161）。`measurement_gaps` の側は
# **消さない** — 打点漏れ率そのものが観測対象（#123 B）で、補完で消すと「打点規約が守られて
# いるか」が見えなくなる。2 つを別フィールドに分けることで「欠測率」と「打点漏れ率」が
# 分離して読める。**常に載せる**（フィールドの存在自体が補完機構の版マーカーになる）
payload["derived_markers"] = [m for m in (os.environ.get("REVIEW_DERIVED_MARKERS") or "").split(",") if m]

# 並列発行の担保と打点は**どちらもオーケストレーターの自己申告**で、破っても実行中は何も
# 起きない（GitHub issue #135）。しかも打点漏れは違反の証拠自体を消すので、`explorer-wave`
# gap は「打ち忘れ」であると同時に「直列発行だったかもしれないが確かめられない」を意味する。
# **独立した観測者（Agent の PostToolUse hook）が本命の解**だが未検証なので、当面は
# 「気づかず通過する」のを止める側に倒す — レポートへの追記を明示的に指示する
# （→ design-notes/pending-optimizations.md `## 8`）
if waves >= 2:
    sys.stderr.write(
        "WARN: explorer wave が %d 本ある（一括発行が破られた）。1 メッセージにまとめていれば "
        "wave 内最長の 1 本で済む — orchestration-guide.md `## 0`\n"
        "  → **レポート末尾に 1 行追記すること**: "
        "`⚠️ 計測: explorer を %d wave に分けて発行した（一括発行の規約違反 / #135）`\n" % (waves, waves)
    )
elif "explorer-wave" in gaps:
    sys.stderr.write(
        "WARN: explorer を %s 体起動したのに explorer wave の打点が無い（explorer_waves が欠測）。"
        "回収直後の `review-timing.sh mark wave --explorer` を打ち忘れている\n"
        "  → **打点漏れは一括発行違反の証拠も同時に消す**（#135）。レポート末尾に 1 行追記すること: "
        "`⚠️ 計測: explorer wave の打点漏れ（一括発行が守られたか事後に検証できない / #135）`\n" % launched
    )
# 補完できた回は「打点漏れ ＝ 欠測」ではないので、警告と同じ行で言う（issue #161）。
# **打点漏れの警告自体は消さない** — 埋まったかどうかと、規約が守られたかは別の話
derived_note = ("。うち %s は agent の実測時刻で補完済み（derived_markers）"
                % ", ".join(payload["derived_markers"])) if payload["derived_markers"] else ""
if gaps:
    sys.stderr.write(
        "WARN: 計測マーカーの欠測: %s（打点由来は agent の実測時刻で埋まらなければ "
        "duration_* が -1 / `payload:*` は payload 側の欠落 / `tokens` は transcript を"
        "引けなかった回）%s\n" % (", ".join(gaps), derived_note)
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
PUBLISHED=0
# shellcheck disable=SC1091
if source "${CLAUDE_PLUGIN_ROOT:-$HERE/..}/hooks/lib/safe-hook.sh" 2>/dev/null; then
  if CLAUDE_PROJECT_DIR="$MAIN_ROOT" SAFE_HOOK_NAME="$PLUGIN" \
       event_bus_publish "review:completed" "$MERGED"; then
    PUBLISHED=1
    echo "published to $MAIN_ROOT/.claude/events.jsonl ($PLUGIN)"
  else
    echo "WARN: event_bus_publish に失敗した（計測データは欠測になる）" >&2
  fi
else
  echo "WARN: safe-hook.sh を読み込めず publish をスキップした" >&2
fi

# ---- 一時ファイルの掃除（**publish に成功したときだけ** / GitHub issue #133） -
# 旧版は成否に関わらず掃除していたため、**イベントが書かれなかった回ほど痕跡が残らない**という
# 逆向きの縮退になっていた（打点ごと消えるので後から publish し直せず、`publish-pending` も
# ファイル不在で無言になる）。失敗回は一時ファイルを残し、次のフェーズ冒頭のガードに拾わせる。
if [ "$PUBLISHED" = "1" ]; then
  # 掃除より先に成功マーカーを打つ（`--keep-temp` でファイルが残る回のため。KEEP=0 なら直後に消える）
  bash "$HERE/review-timing.sh" mark published ${PR_ARGS[@]+"${PR_ARGS[@]}"}
  if [ "$KEEP" = "0" ]; then
    bash "$HERE/review-timing.sh" cleanup ${PR_ARGS[@]+"${PR_ARGS[@]}"}
    rm -f "$(review_path prctx)" "$(review_path diff)" "$(review_path agentctx)" \
          "$(review_path oracles)"
  fi
else
  echo "WARN: publish に失敗したので一時ファイルを残した（同じ引数で再実行すれば復旧できる。" >&2
  echo "      次フェーズ冒頭の \`review-timing.sh publish-pending\` もこの回を検知する）" >&2
fi
exit 0
