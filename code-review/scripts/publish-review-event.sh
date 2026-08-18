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
          # **遅れて publish した回は窓に修正作業が混ざる**ので別の名前で出す。
          # 集計側は `since-t0` だけを使う契約なので、混ざった回は自動的に外れる
          if [ "$LATE_PUBLISH" = "1" ]; then TOKENS_WINDOW="since-t0-late"; else TOKENS_WINDOW="since-t0"; fi
        fi
        ;;
    esac
    TOKENS_JSON=$(bash "$HERE/measure-tokens.sh" --json ${TOK_ARGS[@]+"${TOK_ARGS[@]}"} 2>/dev/null)
    ;;
esac

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
    if isinstance(d, dict) and "fired" not in d:
        gaps.append("payload:%s.fired" % field)

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
            "schema": 1,
            # 窓の種類。`session` は t0 を撮れずセッション全体を集計した回で、レビュー外の
            # 作業が混ざる。**集計側は since-t0 だけを使う**（混ぜると体数との対応が消える）
            "window": os.environ.get("REVIEW_TOKENS_WINDOW") or "session",
            # **どの transcript のどこからを数えたか**を残す（セッションの選択は「候補 dir の
            # 最新 .jsonl」という推定で、worktree 並列運用では取り違えうる）。値そのものは
            # もっともらしいので、この 2 つが無いと取り違えを事後に検出する手段が消える
            "session": tok.get("session"), "first_ts": tok.get("first_ts"),
            "main_output_k": _k("main", "output"),
            "main_cache_write_k": _k("main", "cache_write"),
            "sub_output_k": _k("sub", "output"),
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

    # **発行パターンは tokens とは独立に載せる**（GitHub issue #142）。窓が空振りして
    # `tokens` が欠測になった回でも、agent の起動時刻は拾えていることがある。
    # `duration_fleet_min` だけでは「9 体を逐次で回した 89 分」と「1 体が 89 分かかった」を
    # 区別できず、実測ではその区別が最大の改善余地だった（16 回中 13 回が逐次 / 累計 431 分）
    disp = tok.get("dispatch") if isinstance(tok, dict) else None
    if isinstance(disp, dict) and disp.get("verdict") not in (None, "unknown"):
        payload["dispatch"] = disp
        if disp.get("verdict") in ("serial", "mixed"):
            label = "逐次発行" if disp["verdict"] == "serial" else "分割発行"
            sys.stderr.write(
                "WARN: agent を%s している（%s 体 / 最大間隔 %s 秒）。一括発行なら fleet は"
                "**最長 1 体ぶん**で済む — orchestration-guide.md `## 0`「並列発行の明示」\n"
                "  → **レポート末尾に 1 行追記すること**: "
                "`⚠️ 計測: agent を%s した（一括発行の規約違反 / #142）`\n"
                % (label, disp.get("agents"), disp.get("max_gap_sec"), label)
            )
    else:
        # 判定できなかった（agent 0〜1 体 / transcript を引けない）。**「一括だった」に
        # 倒さない** — 規約が守られたことの証拠が無い回として残す
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
if gaps:
    sys.stderr.write(
        "WARN: 計測マーカーの欠測: %s（打点由来は対応する duration_* が -1 / "
        "`payload:*` は payload 側の欠落 / `tokens` は transcript を引けなかった回）\n" % ", ".join(gaps)
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
