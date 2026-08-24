#!/usr/bin/env bash
# `review:completed` の蓄積イベントを集計して、レビュー基盤自体の振り返りを出す
# （GitHub issue #123 E）。
#
# **なぜスクリプトなのか**: ロールバック条件・再監視条件は比率と件数で決まる決定的な計算な
# ので、LLM に毎回 jq を組ませない（CLAUDE.md「決定的 hook > LLM 判定」/ 経緯と出力の読み方の
# 正本は references/orchestration-measurement.md `## 18`）。
#
# 使い方:
#   review-retro.sh                     # 全期間 + 直近 30 日を集計
#   review-retro.sh --since 2026-07-01  # 起点を指定
#   review-retro.sh --last 20           # 直近 N 件だけ
#   review-retro.sh --json              # 機械可読（**0 件・ログ不在でも必ず JSON を返す**）
#   review-retro.sh --logs ~/Projects/*/.claude/events.jsonl   # 複数ログを合算（issue #160）
#
# **`--logs` は明示指定のみ**（探索はしない）。指定したファイルが読めなければ exit 2 で止める
# — 手作業の連結を置き換えるのが目的なので、**タイプミスを「サンプルが少ない」に化けさせない**。
# 同一イベントが複数ファイルに現れる（worktree のコピー等）場合は `ts` + `plugin` + payload 全体
# で dedup する。**どのログから何件採ったかは必ず出力する**（母集団が言えないと
# 「⚠️ が出たときだけ行動する」契約が成立しない）。
#
# **層別の原則**: 版マーカー（`pre_adjust_counts.schema` / `*.gate_schema` /
# `attribution_schema` / `calibration_schema`）で切り、日付では切らない。マーケットプレイス
# 配布のため未更新マシンが旧仕様で publish し続けるため。**累計で読むと施策の効果が薄まる**
# ので、版マーカーを持つ指標は必ず層別してから判定する（比較演算子は `>=` で前方互換にする。
# `== N` にすると次の版 bump でセクションが無音で消える）。
set -uo pipefail

SINCE=""; LAST=""; AS_JSON=0; EXPLICIT_LOGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --since) [ $# -ge 2 ] || { echo "FATAL: --since に値が必要" >&2; exit 2; }; SINCE="$2"; shift 2 ;;
    --last)  [ $# -ge 2 ] || { echo "FATAL: --last に値が必要" >&2; exit 2; }; LAST="$2"; shift 2 ;;
    --json)  AS_JSON=1; shift ;;
    # **後続の非フラグ引数をすべて取る**（`--logs ~/Projects/*/.claude/events.jsonl` のように
    # シェルの glob をそのまま渡せる形にする。`--log` の繰り返しだと glob が使えない）
    --logs)
      shift
      while [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; do EXPLICIT_LOGS+=("$1"); shift; done
      [ ${#EXPLICIT_LOGS[@]} -gt 0 ] || { echo "FATAL: --logs にパスが必要" >&2; exit 2; }
      ;;
    *) echo "FATAL: 未知の引数: $1" >&2; exit 2 ;;
  esac
done
case "${LAST:-0}" in ''|*[!0-9]*) echo "FATAL: --last は数値のみ（受領: '$LAST'）" >&2; exit 2 ;; esac

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/review-paths.sh
# 読み取り専用なので `review_paths_init`（一時 dir の作成）は呼ばない。使うのは
# `review_event_logs` / `review_main_root` だけで、どちらも init に依存しない
. "$HERE/lib/review-paths.sh"

if [ ${#EXPLICIT_LOGS[@]} -gt 0 ]; then
  # **明示指定は黙って捨てない**。探索（下）と違い、読めないパスはユーザーの誤りなので
  # 「サンプルが少ない」に化けさせず判定不能（exit 2）で止める
  for _log in "${EXPLICIT_LOGS[@]}"; do
    [ -f "$_log" ] || { echo "FATAL: --logs のパスが読めない: $_log" >&2; exit 2; }
  done
  REVIEW_EVENT_LOGS=("${EXPLICIT_LOGS[@]}")
elif ! review_event_logs; then
  # **`--json` でも必ず JSON を返す**（機械可読の契約は「データがある場合だけ」ではない）
  if [ "$AS_JSON" = "1" ]; then
    echo '{"n":0,"reason":"no-events-log","signals":[]}'
  else
    echo "## レビュー振り返り"
    echo "計測データ（.claude/events.jsonl）がまだ無い。レビューを数回回すと集計が出る。"
  fi
  exit 0
fi

command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 が必要" >&2; exit 2; }

REVIEW_SINCE="$SINCE" REVIEW_LAST="${LAST:-0}" REVIEW_JSON="$AS_JSON" \
  python3 - ${REVIEW_EVENT_LOGS[@]+"${REVIEW_EVENT_LOGS[@]}"} <<'PY'
import json, os, sys
from datetime import datetime, timedelta, timezone

since_raw = os.environ.get("REVIEW_SINCE") or ""
last_n = int(os.environ.get("REVIEW_LAST") or 0)
as_json = os.environ.get("REVIEW_JSON") == "1"

since = None
if since_raw:
    try:
        since = datetime.fromisoformat(since_raw.replace("Z", "+00:00"))
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
    except ValueError:
        sys.stderr.write("WARN: --since を解釈できないので無視する: %s\n" % since_raw)

events, seen = [], set()
#: どのログから何件採ったか（母集団の再現性 / issue #160）。dedup で落ちた件数も数える
#
# **同一ファイルの重複指定は先に畳む**（glob が重なる / `.` 付きパスを混ぜる）。畳まないと
# 2 回読んで 2 回目が全部イベント重複になり、`ログ 2 本 … 3 件 / 3 件` と**合計が n を超える
# 表示**になる。ファイルが違えば（worktree へコピーされた events.jsonl 等）ここは通り、
# 下のイベント単位の dedup が拾う
source_paths, _seen_real, dup_paths = [], set(), 0
for _path in sys.argv[1:]:
    _real = os.path.realpath(_path)
    if _real in _seen_real:
        dup_paths += 1
        continue
    _seen_real.add(_real)
    source_paths.append(_path)
dup_dropped = 0
for path in source_paths:
    try:
        # errors="replace" は必須。既定の strict だと UnicodeDecodeError（OSError ではなく
        # ValueError 系）が下の except を貫通し、**非 UTF-8 バイト 1 つで恒久クラッシュ**する。
        # 壊れたバイトはその行の json パースが下の except ValueError で落ちて設計どおり縮退する
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        continue
    for line in lines:
        line = line.strip()
        if not line or '"review:completed"' not in line:
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue              # 壊れた 1 行で集計全体を落とさない
        if ev.get("event") != "review:completed":
            continue
        ts = ev.get("ts") or ""
        key = (ts, ev.get("plugin"), json.dumps(ev.get("payload"), sort_keys=True))
        if key in seen:           # 同一イベントが複数ログに現れる場合の重複除去
            dup_dropped += 1        # （候補パスの重なり / worktree へコピーされた events.jsonl）
            continue
        seen.add(key)
        try:
            when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except ValueError:
            when = None
        events.append({"ts": ts, "when": when, "plugin": ev.get("plugin", "?"),
                       "p": ev.get("payload") or {}, "src": path})

events.sort(key=lambda e: e["ts"])
if since:
    events = [e for e in events if e["when"] and e["when"] >= since]
if last_n:
    events = events[-last_n:]

def source_rows(rows):
    """**集計に実際に入った件数**をログごとに返す（0 件のログも母集団の一部として残す）."""
    counted = {path: 0 for path in source_paths}
    for e in rows:
        counted[e["src"]] = counted.get(e["src"], 0) + 1
    return [{"path": path, "n": counted[path]} for path in source_paths]


def sources_line():
    extra = "（同一ファイルの重複指定 %d 本を除外）" % dup_paths if dup_paths else ""
    return ("**母集団**: ログ %d 本%s / 重複イベント除外 %d 件"
            % (len(source_paths), extra, dup_dropped))


if not events:
    if as_json:
        print(json.dumps({"n": 0, "reason": "no-samples-in-range", "signals": [],
                          "sources": source_rows(events),
                          "sources_dropped_duplicates": dup_dropped,
                          "sources_dropped_paths": dup_paths},
                         ensure_ascii=False))
    else:
        print("## レビュー振り返り")
        print("対象サンプルが 0 件。")
        print()
        print(sources_line())
        for row in source_rows(events):
            print("- `%s` … %d 件" % (row["path"], row["n"]))
    sys.exit(0)

now = datetime.now(timezone.utc)
recent = [e for e in events if e["when"] and e["when"] >= now - timedelta(days=30)]


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def schema_of(d, key):
    """版マーカーを int に寄せる（欠落・解釈不能は 1 = 最古の版として扱う）。"""
    try:
        return int(d.get(key) or 1)
    except (TypeError, ValueError):
        return 1


def measured(rows, key):
    """欠測（-1）と未収録（None）を除いた実測値だけを返す。"""
    out = []
    for e in rows:
        v = num(e["p"].get(key))
        if v is not None and v >= 0:
            out.append(v)
    return out


def median(xs):
    if not xs:
        return None
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return cov / (vx ** 0.5 * vy ** 0.5)


def total_agents(p):
    """fleet の実体数。1 体固定の検証層（meta / skeptic）も起動していれば足す。"""
    a = p.get("agents")
    if not isinstance(a, dict):
        return None
    vals = [num(a.get(k)) for k in ("explorer", "reviewer", "specialist", "round2", "verify")]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    extra = 0
    for field in ("meta_reviewer", "recall_skeptic"):
        d = p.get(field)
        if isinstance(d, dict) and d.get("fired") is True:
            extra += 1
    return sum(vals) + extra


def pct(part, whole):
    return (100.0 * part / whole) if whole else 0.0


# 「設計上そもそも起動しない」スキップ理由。**価値率とゲート判定の分母から外す**。
# これを分母に入れると、既定 effort で回しただけのサンプルが「起動していない」として
# 積み上がり、ゲートの実装バグと運用上の非該当を区別できなくなる
OUT_OF_SCOPE_SKIPS = {"effort", "config", "emergency", "scope"}

report, signals = [], []

# ---- 1. サンプル数 ---------------------------------------------------------
by_plugin = {}
for e in events:
    by_plugin[e["plugin"]] = by_plugin.get(e["plugin"], 0) + 1
report.append(("サンプル", "全 %d 件（直近 30 日 %d 件） / %s"
               % (len(events), len(recent),
                  " ".join("%s=%d" % kv for kv in sorted(by_plugin.items())))))

# ---- モデル世代の層別キー（GitHub issue #169） ------------------------------
# `effort` / `size_tier` / `reviewer_effort_profile` の層別は、Opus 5 と 4.8 が混ざった
# 瞬間に成立しなくなる（実測: 2026-08-24 の 1 日で 3 サンプル中 2 件が 4.8 で、
# `sub_cache_read_k / sub_agents` の 7,853k と 3,7xx k の差が tier と世代で完全に交絡していた）。
# 世代はユーザーが実行時に選ぶもの（エイリアスは親世代を継ぐ / `docs/pipeline-design.md`）
# なので、**事故ではなく層別キー**として扱う。
def gen_of(p):
    """payload → 世代ラベル。`unrecorded`（旧版）と `mixed`（切替・引き当て失敗）は
    どちらも既知の世代と同じバケツに入れない。「たぶん opus-5 だった」は観測ではない。"""
    m = p.get("models")
    if not isinstance(m, dict):
        return "unrecorded"
    v = m.get("main")
    if not isinstance(v, str) or not v:
        return "mixed"
    return v[len("claude-"):] if v.startswith("claude-") else v


# **母集団に 2 種以上あるときだけキーへ足す**。1 種しか無い期間まで割ると、既存の
# `effort/size_tier` バケツが n=1 に砕けて中央値が読めなくなる。分割の目的は交絡を切ることで
# あって、キーを増やすことではない
GEN_COUNTS = {}
for _e in events:
    _g = gen_of(_e["p"])
    GEN_COUNTS[_g] = GEN_COUNTS.get(_g, 0) + 1
GEN_KINDS = sorted(GEN_COUNTS)
GEN_SPLIT = len(GEN_KINDS) > 1


def with_gen(p, key):
    """世代が 2 種以上ある母集団でだけ層別キーへ世代を足す。"""
    return key + "/" + gen_of(p) if GEN_SPLIT else key


# ---- 2. effort × size_tier 別の fleet 時間・体数 ---------------------------
buckets = {}
for e in events:
    p = e["p"]
    fleet = num(p.get("duration_fleet_min"))
    if fleet is None or fleet < 0:
        continue
    key = with_gen(p, "%s/%s" % (p.get("effort", "?"), p.get("size_tier", "?")))
    buckets.setdefault(key, {"fleet": [], "agents": []})
    buckets[key]["fleet"].append(fleet)
    ta = total_agents(p)
    if ta is not None:
        buckets[key]["agents"].append(ta)

tier_rows = []
for key in sorted(buckets, key=lambda k: -len(buckets[k]["fleet"])):
    b = buckets[key]
    tier_rows.append((key, len(b["fleet"]), median(b["fleet"]), median(b["agents"])))

# ---- 3. 体数 vs 壁時計の相関（size_tier 内で計算する）----------------------
# `size_tier` は体数（triage-guide.md `## 7` の体数表）と fleet 時間の**両方**を決めるので、
# 層別しない相関は tier の効果を体数の効果として計上する。実測 n=48 で層別なし r=0.592 に
# 対し、最大サンプルの medium（n=30）は r=0.315 まで落ちた（GitHub issue #151）。
# **発火条件は層別後の r だけで判定する** — 層別なしの r は交絡を含む参考値として出すだけ。
# 相関の式（Pearson）は変えていない。層別の単位だけの変更
xs, ys = [], []
tier_xy = {}
for e in events:
    p = e["p"]
    fleet, ta = num(p.get("duration_fleet_min")), total_agents(p)
    if fleet is not None and fleet >= 0 and ta is not None:
        xs.append(ta)
        ys.append(fleet)
        tx, ty = tier_xy.setdefault(str(p.get("size_tier", "?")), ([], []))
        tx.append(ta)
        ty.append(fleet)
r = pearson(xs, ys)
R_MIN_N = 10          # これ未満では結論を書かない（標本が小さすぎる）
R_FLAT = 0.3          # |r| < これ なら「レバーではない」を支持
R_STRONG = 0.6        # |r| >= これ なら再監視条件に該当
# tier ごとの (tier, n, r)。**下限は層別なしと同じ `R_MIN_N`**（層別で n が割れるぶん
# 判定不能に倒れる tier が増えるが、緩めると単発の tier が点灯する側に倒れる）
tier_r_rows = [(t, len(v[0]), pearson(v[0], v[1]))
               for t, v in sorted(tier_xy.items(), key=lambda kv: -len(kv[1][0]))]
tier_r_judged = [(t, n_t, rr) for t, n_t, rr in tier_r_rows
                 if rr is not None and n_t >= R_MIN_N]

# ---- 4. 区間の中央値 -------------------------------------------------------
spans = [(k, median(measured(events, "duration_%s_min" % k)), len(measured(events, "duration_%s_min" % k)))
         for k in ("triage", "explore", "fleet", "synthesis", "closing")]

# ---- 5. pre_adjust → 報告の歩留まり（版マーカー × 閾値で層別） --------------
# `>= 2` にするのは前方互換のため（`== 2` だと schema 3 でセクションが無音で消える）
yields = {}
for e in events:
    p = e["p"]
    pre = p.get("pre_adjust_counts")
    if not isinstance(pre, dict) or schema_of(pre, "schema") < 2:
        continue
    key = "schema>=%d/threshold=%s" % (schema_of(pre, "schema"), p.get("severity_threshold") or "?")
    y = yields.setdefault(key, {"n": 0, "pre": 0, "post": 0})
    y["n"] += 1
    for sev in ("blocker", "critical", "major", "minor"):
        v = num(pre.get(sev))
        if v:
            y["pre"] += v
    for sev in ("blocker_count", "critical_count", "major_count", "minor_count"):
        v = num(p.get(sev))
        if v:
            y["post"] += v

# ---- 5.1 「本文を書いてから捨てた」率（GitHub issue #146） -------------------
# 上の歩留まりは **(a) 本文を書いてから捨てた**（出力トークンの純損失）と
# **(b) `## below-threshold` で件数だけ返した**（既に節約できている）を合算しているので、
# #117（閾値注入）が効いたのかを判定できない。`below_threshold_counts` を持つ回**だけ**を
# 別に集計する — 持たない回を混ぜると `pre` の母数だけが増えて (a) が過大に出る。
splits = {}
for e in events:
    p = e["p"]
    pre = p.get("pre_adjust_counts")
    bt = p.get("below_threshold_counts")
    if not isinstance(pre, dict) or schema_of(pre, "schema") < 2 or not isinstance(bt, dict):
        continue
    key = "schema>=%d/threshold=%s" % (schema_of(pre, "schema"), p.get("severity_threshold") or "?")
    sp = splits.setdefault(key, {"n": 0, "pre": 0, "below": 0, "post": 0})
    sp["n"] += 1
    for sev in ("blocker", "critical", "major", "minor"):
        sp["pre"] += num(pre.get(sev)) or 0
        sp["below"] += num(bt.get(sev)) or 0
    for sev in ("blocker_count", "critical_count", "major_count", "minor_count"):
        sp["post"] += num(p.get(sev)) or 0


# ---- 6. 反証 verdict 分布（calibration_schema で層別） ---------------------
verdict_layers = {}
for e in events:
    av = e["p"].get("adversarial_verify")
    if not isinstance(av, dict):
        continue
    total = sum(num(av.get(k)) or 0 for k in
                ("confirmed", "refuted", "uncertain", "severity_inflated", "contested"))
    if total <= 0:
        continue
    layer = schema_of(av, "calibration_schema")
    L = verdict_layers.setdefault(layer, {"n": 0, "total": 0, "confirmed": 0, "refuted": 0,
                                          "uncertain": 0, "severity_inflated": 0, "contested": 0})
    L["n"] += 1
    L["total"] += total
    for k in ("confirmed", "refuted", "uncertain", "severity_inflated", "contested"):
        L[k] += num(av.get(k)) or 0

# ---- 6.1 降格の型別内訳（skill 別 / GitHub issue #150）---------------------
# **どの型で落ちたか**が分かれば打ち手が決まる。`base_derived` が支配的なら直すのは
# プロンプトの表現ではなく **reviewer に渡る base 側の情報**（review は PR diff から復元する
# しかなく、self-review は変更意図をメインコンテキストが知っている）。**skill 別に出す**のは
# 非対称そのものが観測対象だから（実測: 同一版・同一 effort・同一 tier で review 84-90% /
# self-review 50%）。上流（reviewer の閾値跨ぎ降格）と下流（反証）を**同じ語彙**で並べる
DEMOTE_TYPES = ("base_derived", "misread", "overstated_impact", "miscategorized", "unknown")


def demote_rows(field, key):
    """`{plugin: {n, total, <type>...}}`。内訳を持たない回は分母にも入れない。"""
    rows = {}
    for e in events:
        parent = e["p"].get(field)
        d = parent.get(key) if isinstance(parent, dict) else None
        if not isinstance(d, dict):
            continue
        row = rows.setdefault(with_gen(e["p"], e["plugin"]),
                              dict({"n": 0, "total": 0}, **{k: 0 for k in DEMOTE_TYPES}))
        row["n"] += 1
        for k in DEMOTE_TYPES:
            v = num(d.get(k)) or 0
            row[k] += v
            row["total"] += v
    return rows


inflated_axes = demote_rows("adversarial_verify", "inflated_axes")
demoted_types = demote_rows("below_threshold_counts", "demoted_types")

# ---- 7. 動的層の発火率と skip 理由（版マーカー + スコープで層別） -----------
def verdict_total(d):
    """反証レイヤーの「価値」は verdict が返った件数（findings_added を持たない層）。"""
    return sum(num(d.get(k)) or 0 for k in
               ("confirmed", "refuted", "uncertain", "severity_inflated", "contested"))


def layer_stats(field, schema_key, min_schema, value_of=None):
    """版マーカーで濾し、設計上非該当のスキップを分母から外して集計する。

    `n_raw` は全サンプル、`n` は判定に使える母集団（層別後 × スコープ内）。
    両方返すのは「まだサンプルが貯まっていない」と「絞った結果 0 件」を区別するため。

    `value_of` は「その回に価値が出たか」を測る関数（既定は `findings_added`）。
    **層ごとに価値の定義が違う**ので固定しない — 反証は指摘を足す層ではないため
    `findings_added` を持たず、既定のままだと価値率が恒常 0% に潰れる。
    """
    if value_of is None:
        value_of = lambda d: num(d.get("findings_added")) or 0  # noqa: E731
    st = {"n_raw": 0, "n": 0, "fired": 0, "valuable": 0,
          "skips": {}, "dropped_schema": 0, "dropped_scope": 0, "dropped_unrecorded": 0,
          "schema_key": schema_key, "min_schema": min_schema}
    for e in events:
        d = e["p"].get(field)
        if not isinstance(d, dict):
            continue
        st["n_raw"] += 1
        if schema_of(d, schema_key) < min_schema:
            st["dropped_schema"] += 1
            continue
        # **版マーカーだけでは記録漏れを落とせない**（v2.65.0 / issue #125 と #129 の相互作用）。
        # 版マーカーは publish-review-event.sh が注入するので、`fired` を落とした payload にも
        # 最新版が入る。「フィールドの有無が版マーカー」という層別が現行版に対しては効かず、
        # 記録漏れが `skip_reason=unknown` として分母に混ざる（= 発火率が実態より薄まり、
        # 「1 度も起動していない」という偽のロールバックシグナルまで点灯しうる）。
        # publish が立てた gap をそのまま使って外す（判定式を二重管理しない）
        if ("payload:%s.fired" % field) in (e["p"].get("measurement_gaps") or []):
            st["dropped_unrecorded"] += 1
            continue
        reason = d.get("skip_reason") or None
        if d.get("fired") is not True and reason in OUT_OF_SCOPE_SKIPS:
            st["dropped_scope"] += 1
            st["skips"][reason] = st["skips"].get(reason, 0) + 1
            continue
        st["n"] += 1
        if d.get("fired") is True:
            st["fired"] += 1
            if value_of(d) > 0:
                st["valuable"] += 1
        else:
            key = reason or "unknown"
            st["skips"][key] = st["skips"].get(key, 0) + 1
    return st


# ロールバック条件の層別要件の正本: triage-dynamic-gates.md `## 8`（meta） / `## 8.5`（skeptic）
# / `## 9`（反証）
skeptic = layer_stats("recall_skeptic", "attribution_schema", 2)
meta = layer_stats("meta_reviewer", "gate_schema", 3)
# 反証も他 2 層と同じ流儀で絞る（issue #129）。**旧版は `fired` を持たない**ので
# `gate_schema >= 2` で落ちる — 「起動しなかった」ではなく「発火を記録していない版」
adversarial = layer_stats("adversarial_verify", "gate_schema", 2, value_of=verdict_total)
# round2 は専用オブジェクトを持たないので `agents.round2` の**キー存在**を版プロキシにする
# （`agents` を持たない旧サンプルを分母に入れると発火率が構造的に薄まる。#127 と同型）
round2_scope = [e for e in events
                if num((e["p"].get("agents") or {}).get("round2")) is not None]
round2_fired = sum(1 for e in round2_scope
                   if (num((e["p"]["agents"]).get("round2")) or 0) > 0)

# ---- 8. 計測の欠測率 -------------------------------------------------------
n_all = len(events)
gap_counts = {}
for e in events:
    gaps = e["p"].get("measurement_gaps")
    if isinstance(gaps, list):
        for g in gaps:
            gap_counts[str(g)] = gap_counts.get(str(g), 0) + 1
have_synthesis = len(measured(events, "duration_synthesis_min"))
have_waves = sum(1 for e in events
                 if num((e["p"].get("agents") or {}).get("explorer_waves")) is not None)
split_waves = sum(1 for e in events
                  if (num((e["p"].get("agents") or {}).get("explorer_waves")) or 0) >= 2)
# **打点漏れのうち実測時刻で埋まった分**（GitHub issue #161）。`measurement_gaps` と
# **排他ではない** — 補完できた回は両方に載る。「打点規約が守られているか」（gap 側）と
# 「区間が使えるか」（`duration_*` 側）は別の量なので混ぜない。
# **分母はフィールドを持つ回**（不在は旧版の identification であって欠測ではない / #127）
derived_counts = {}
n_derivedfield = 0
for e in events:
    dm = e["p"].get("derived_markers")
    if not isinstance(dm, list):
        continue
    n_derivedfield += 1
    for m in dm:
        derived_counts[str(m)] = derived_counts.get(str(m), 0) + 1

n_gapfield = sum(1 for e in events if isinstance(e["p"].get("measurement_gaps"), list))
# `tokens` gap の分母。review だけが計測対象なので self-review を混ぜない
n_gapfield_review = sum(1 for e in events
                        if isinstance(e["p"].get("measurement_gaps"), list)
                        and str(e["plugin"]).endswith(":review"))
# `late-publish` gap の分母。**self-review でしか立たない**（review は締めフローの人間待ちを
# 含むのが契約なので、publish が遅いこと自体は正常）。混ぜると #127 と同型に薄まる
n_gapfield_selfreview = sum(1 for e in events
                            if isinstance(e["p"].get("measurement_gaps"), list)
                            and str(e["plugin"]).endswith(":self-review"))

# 健全性表示の母集団は `measurement_gaps` を持つ回（= v2.62.0 以降）に絞る（issue #127）.
# フィールド不在は「そのサンプルは旧版で publish された」という identification であって
# 欠測ではない（orchestration-measurement.md `## 16`「フィールドの有無が版マーカー」）.
# 全サンプルを分母にすると版を重ねるほど記録率が構造的に下がって見える.
# フィールド自身の有無を分母にすると循環するので、後発フィールドを版プロキシに使う.
modern = [e for e in events if isinstance(e["p"].get("measurement_gaps"), list)]
n_modern = len(modern)
# **2 フィールドで欠測の現れ方が違う**（publish-review-event.sh）. 1 つの判定にまとめないこと:
#   duration_synthesis_min … 打点が無ければ -1 が入る → `measured()` の除外で検出できる
#   agents.explorer_waves  … 打点が無くても 0 が必ず入る → **存在判定では検出できない**.
#                            漏れは measurement_gaps の `explorer-wave` として現れる
# 後者を存在判定で数えると modern と恒真に一致し、打点漏れがあっても 100% しか表示しない.
modern_synthesis = len(measured(modern, "duration_synthesis_min"))
# explorer 未起動の回は「該当なし」なので分母から外す（欠測ではない）
modern_waves_scope = [e for e in modern
                      if (num((e["p"].get("agents") or {}).get("explorer")) or 0) >= 1]
modern_waves = sum(1 for e in modern_waves_scope
                   if "explorer-wave" not in (e["p"].get("measurement_gaps") or []))

# ---- 9. トークン消費（review のみ / GitHub issue #126） --------------------
# **窓が `since-t0` の回だけを集計する**。`session` はレビュー開始マーカーを撮れず
# セッション全体を集計した回で、レビュー外の作業が混ざるため体数との対応が読めない。
# 時間と混ぜて 1 つの結論を出さないこと（triage-guide.md `## 7`）— **体数が確実に効くのは
# こちら側**で、`duration_fleet_min` との相関（上の r）とは別物として読む。
# **分母は 3 段で出す**（`layer_stats` と同じ流儀 / issue #128 のセルフレビュー指摘）。
# 「まだサンプルが無い」と「絞った結果 0 件」を区別できないと、`t0` 打点が構造的に壊れて
# 全回 `window=session` になったとき「機能が新しい」と「計測が壊れている」を判別できない
tok_raw = [e for e in events if isinstance(e["p"].get("tokens"), dict)]
tok_rows, tok_dropped_window, tok_dropped_schema = [], 0, 0
for e in tok_raw:
    t = e["p"]["tokens"] or {}
    if schema_of(t, "schema") < 1:      # 今は恒真だが、次の版で無言の混入を防ぐ
        tok_dropped_schema += 1
    elif t.get("window") != "since-t0":
        tok_dropped_window += 1
    else:
        tok_rows.append(e)


def tok_vals(key):
    out = []
    for e in tok_rows:
        v = num((e["p"]["tokens"] or {}).get(key))
        if v is not None and v >= 0:
            out.append(v)
    return out


tok_main = tok_vals("main_output_k")
tok_sub = tok_vals("sub_output_k")
# 体数 vs sub.output。**トークンは体数に素直に効く**という主張の検算で、崩れたら
# 「体数を減らせばトークンが減る」という triage-guide `## 7` の前提を見直す信号になる
txs, tys = [], []
for e in tok_rows:
    ta, so = total_agents(e["p"]), num((e["p"]["tokens"] or {}).get("sub_output_k"))
    if ta is not None and so is not None and so >= 0:
        txs.append(ta)
        tys.append(so)
tok_r = pearson(txs, tys)

# **1 体あたりの cache_read**（GitHub issue #156）。体数キャップ（#96）は「広さ」を切ったが
# 1 体あたりの読む量には手が入っておらず、`pending-optimizations.md ## 計測の基準値` の
# 1 体平均 cache_read 5,039k と比べる先がここ。**effort × size_tier で層別する** — tier は
# 担当ファイル数を、effort は 1 体あたりの探索量を決めるので、混ぜた中央値は両方の交絡を負う。
# **除算は `sub_agents` が正のときだけ**（0 で割れば `ZeroDivisionError`、欠測なら
# `TypeError` で、その回だけ静かに落ちるのではなく集計全体が死ぬ）。
# **版マーカーで先に切る** — フィールドの在否で代用すると、将来 `sub_cache_read_k` の窓や
# 単位を変えて schema を上げたとき旧版が無言で同じ中央値に混ざる（冒頭の層別の原則）。
# 今は schema 2 とフィールド追加が同一版なので等価だが、等価なうちに揃えておく
TOK_CACHE_READ_MIN_SCHEMA = 2
per_agent_buckets = {}
per_agent_old_schema = per_agent_undividable = 0
for e in tok_rows:
    t = e["p"]["tokens"] or {}
    if schema_of(t, "schema") < TOK_CACHE_READ_MIN_SCHEMA:
        per_agent_old_schema += 1
        continue
    cr, na = num(t.get("sub_cache_read_k")), num(t.get("sub_agents"))
    if cr is None or cr < 0 or na is None or na <= 0:
        per_agent_undividable += 1
        continue
    key = with_gen(e["p"], "%s/%s" % (e["p"].get("effort", "?"), e["p"].get("size_tier", "?")))
    per_agent_buckets.setdefault(key, []).append(cr / na)

per_agent_rows = []
for key in sorted(per_agent_buckets, key=lambda k: -len(per_agent_buckets[k])):
    per_agent_rows.append((key, len(per_agent_buckets[key]),
                           median(per_agent_buckets[key])))

# ---- 9.5. 指摘の分類（何が捕まえるべきだったか / v2.68.0） ------------------
# **目的は指摘を減らすことではない**（300 行の diff で 0 件の方が疑わしい）。見るのは構成比で、
# `lint` が高い＝ linter を足す余地、`test` が高い＝回帰テストが足りない、というシグナル。
# 契約は orchestration-measurement.md `## 16` の `findings_class`
# 版マーカー（`>=` で前方互換にする / 冒頭の層別の原則）。**現時点では何も除外しない** —
# `schema_of` は欠落・0 を 1 に丸めるので `>= 1` は恒真。分類の定義を変えて 2 に上げたときに
# 初めて効くフック。**`dropped_schema: 0` を「層別が効いている」と読まないこと**
FC_MIN_SCHEMA = 1
fc_raw = [e for e in events if isinstance(e["p"].get("findings_class"), dict)]
fc_rows, fc_dropped_schema = [], 0
for e in fc_raw:
    if schema_of(e["p"]["findings_class"], "schema") < FC_MIN_SCHEMA:
        fc_dropped_schema += 1      # 分類の定義を変えたら旧サンプルを混ぜない
    else:
        fc_rows.append(e)
fc = {"lint": 0, "test": 0, "judgement": 0}
for e in fc_rows:
    d = e["p"]["findings_class"]
    for k in fc:
        fc[k] += num(d.get(k)) or 0
fc_total = sum(fc.values())


# ---- シグナル判定（ロールバック条件・再監視条件のトリガー） ----------------
# **すべて「サンプル数下限 × 比率」で判定する**。1 件でも点灯する条件を混ぜると
# シグナル欄が常時点灯し、「⚠️ が出たときだけ行動する」という契約が壊れる
newest_layer = max(verdict_layers) if verdict_layers else None
# 上流較正（`prompts/reviewer-common.md` の「降格される典型パターン」= v2.62.0）の効果は
# **対策後のサンプルでしか測れない**（orchestration-measurement.md `## 16` / triage-dynamic-gates.md
# `## 9`「この 52% を上流対策の効果測定に使わないこと」）。`calibration_schema` が未注入だった
# v2.64.x 以前のサンプルは全部 layer 1 に落ちるため、**対策前の累計値でシグナルが発火し続けて
# いた**（issue #131）。層 1 しか無いうちは黙る
CALIB_MIN = 2
VERDICT_MIN = 20     # 層内の verdict 件数の下限（これ未満では層の比率を解釈しない）
if newest_layer is not None:
    L = verdict_layers[newest_layer]
    ratio = pct(L["severity_inflated"], L["total"])
    if L["total"] >= VERDICT_MIN and ratio >= 45 and newest_layer >= CALIB_MIN:
        signals.append("severity_inflated が %.0f%%（calibration_schema=%s / %d verdict）。"
                       "上流較正（prompts/reviewer-common.md の降格典型）が効いていない疑い"
                       % (ratio, newest_layer, L["total"]))
    # 下の 2 つは `CALIB_MIN` で絞らない。**反証レイヤー自身の設定**（effort / バッチサイズ）の
    # 再監視条件であって上流較正の効果測定ではないので、較正版で層別する理由が無い
    if L["total"] >= VERDICT_MIN and pct(L["uncertain"], L["total"]) >= 15:
        signals.append("uncertain が %.0f%%。反証 effort を max に戻す条件"
                       "（triage-dynamic-gates.md `## 9`）に該当" % pct(L["uncertain"], L["total"]))
    if L["total"] >= VERDICT_MIN and pct(L["refuted"], L["total"]) >= 20:
        signals.append("refuted が %.0f%%。反証バッチサイズ 5 → 3 の再検討条件に該当"
                       % pct(L["refuted"], L["total"]))
# **層別なしの r では発火させない**（tier 交絡で常時点灯した / issue #151）
r_strong_tiers = [(t, n_t, rr) for t, n_t, rr in tier_r_judged if abs(rr) >= R_STRONG]
if r_strong_tiers:
    signals.append("体数と fleet 時間の相関が tier 内で高い（%s）。"
                   "「体数は壁時計のレバーではない」（triage-guide.md `## 7`）の再監視条件に該当"
                   % " / ".join("%s r=%.2f n=%d" % (t, rr, n_t)
                                for t, n_t, rr in r_strong_tiers))
if have_waves >= 10 and pct(split_waves, have_waves) >= 20:
    signals.append("explorer wave が 2 本以上に割れた回が %.0f%%（%d/%d）。一括発行の規約"
                   "（orchestration-guide.md `## 0`）が守られていない"
                   % (pct(split_waves, have_waves), split_waves, have_waves))
# **gap は種類ごとに評価する**（v2.66.0 / issue #133 のセルフレビュー指摘）。旧版は
# `max(gap_counts)` で最頻の 1 種だけを閾値にかけていたが、**分母が種類ごとに違う**（下記）ので
# 生カウントの大小で勝者を決めると母集団の違う指標を比べることになる。実害は 2 方向:
#   ① 分母の小さい種類（`tokens` / `late-publish`）が 1 件で 100% になり単発で点灯しうる
#   ② 逆に分母の大きい種類が件数で勝つと、100% の種類が一度も評価されない
# 種類ごとに (件数 / 自分の分母) で判定し、下限も自分の分母に掛ける。
GAP_MIN_N = 5        # その種類の分母がこれ未満なら判定しない（単発点灯の防止）
# wave 間ギャップの内訳から**打ち手を提示する**ための下限（GitHub issue #153）。
# 数値そのものは n=1 から出す（観測の可視化）が、`agent 支配 / idle 支配` の判定は
# ここを超えてから。#153 本文のサンプル下限（5 件）に合わせてある
WAVE_GAP_MIN_N = 5
GAP_RATIO = 20       # 欠測率がこれ以上で ⚠️


def gap_denom(g):
    """gap 種別ごとの母集団。**構造的に片方の skill でしか立たない種類がある**（#127 と同型）。"""
    if g == "tokens":                  # publish が `*:review` でのみ計測する
        return n_gapfield_review
    if g == "late-publish":            # publish が `*self-review` でのみ判定する
        return n_gapfield_selfreview
    return n_gapfield


def gap_hint(g):
    """**gap の種類で是正先が違う**（issue #128 のセルフレビュー指摘）。
    全部を「打点箇所の見直し」と言うと、payload の記述漏れに対して誤った是正先を指す。"""
    if g.startswith("payload:"):
        return "payload テンプレートの記述漏れ（両 SKILL の publish 節）を見直す"
    if g == "late-publish":
        return ("publish が t2 から 10 分以上遅れた回が常態化している（self-review Step 6.4）。"
                "`review-timing.sh publish-pending` のガード位置を見直す")
    if g == "tokens":
        return "transcript の引き当て（measure-tokens.sh のセッション選択・窓）を見直す"
    if g == "diff-digest":
        return "diff の突合キー算出（lib/review-paths.sh）を見直す"
    return "打点箇所の見直しが要る"


gap_hits = []
for g, cnt in gap_counts.items():
    d = gap_denom(g)
    if d >= GAP_MIN_N and pct(cnt, d) >= GAP_RATIO:
        gap_hits.append((pct(cnt, d), g, cnt, d))
# 欠測率の高い順。**上位 2 件まで**（全部並べるとシグナル欄が表になって「⚠️ が出たときだけ
# 行動する」契約の可読性が落ちる。残りは「計測の健全性」行の欠測内訳で見える）
for ratio_g, g, cnt, d in sorted(gap_hits, reverse=True)[:2]:
    signals.append("計測マーカー `%s` の欠測が %.0f%%（%d/%d）。%s"
                   % (g, ratio_g, cnt, d, gap_hint(g)))
# 指摘の分類（v2.68.0）。**機械で捕まる層を agent に探させている**割合が高いままなら、
# lint / テストを足す方が安い（CLAUDE.md「決定的 hook > LLM 判定」を自分の保守に適用する）
# **下限は「レビュー回数」と「指摘件数」の二重**。他のシグナル（skeptic の `fired >= 15` /
# 反証の `n >= 10` / meta の `n >= 8`）はすべて**回数**で切っており、件数だけで切ると
# **指摘の多いレビュー 1 回で点灯する**（同ブロック冒頭「1 件でも点灯する条件を混ぜない」に反する）。
FC_MIN_ROWS = 8      # レビュー回数の下限（既存シグナルの 8〜15 に揃える）
FC_MIN_N = 20        # 指摘件数の下限（これ未満では構成比を解釈しない）
# **しきい値は実測ベースラインの上に置く**。導入時の実測（v2.66.0 + v2.67.0 / 14 件）が
# lint 43% / test 43% なので、30% だと**定常状態で常時点灯**して「⚠️ が出たときだけ行動する」
# 契約を壊す。ベースラインを更新したらこの値も見直す（片方だけ動かさない）
FC_LINT_HOT = 55
FC_TEST_HOT = 55
if len(fc_rows) >= FC_MIN_ROWS and fc_total >= FC_MIN_N and pct(fc["lint"], fc_total) >= FC_LINT_HOT:
    signals.append("報告した指摘の %.0f%%（%d/%d 件 / %d 回）が **lint で捕まる層**。"
                   "静的検査（grep / AST / 構造走査）でルール化できないか検討する"
                   % (pct(fc["lint"], fc_total), fc["lint"], fc_total, len(fc_rows)))
if len(fc_rows) >= FC_MIN_ROWS and fc_total >= FC_MIN_N and pct(fc["test"], fc_total) >= FC_TEST_HOT:
    signals.append("報告した指摘の %.0f%%（%d/%d 件 / %d 回）が **回帰テストで捕まる層**。"
                   "同梱スクリプトのテストが足りていない"
                   % (pct(fc["test"], fc_total), fc["test"], fc_total, len(fc_rows)))
if skeptic["fired"] >= 15 and pct(skeptic["valuable"], skeptic["fired"]) < 25:
    signals.append("冷や読み skeptic の価値率が %.0f%%（fired %d 件 / attribution_schema>=2）。"
                   "high 起点への昇格を戻すロールバック条件"
                   "（triage-dynamic-gates.md `## 8.5`）に該当"
                   % (pct(skeptic["valuable"], skeptic["fired"]), skeptic["fired"]))
# 反証レイヤーのゲート幅（issue #129）。**「走らなかった」ではなく「対象が構造的に 0 件」**
# が常態化しているかを見る。既定 high のゲートは BLOCKER 60-94 / CRITICAL 80-94 だけなので、
# MAJOR しか出ないレビューが続くと層ごと不発になる（実測: `pre_adjust_counts` を持つ 6 件中
# 3 件が不発。いずれも BLOCKER + CRITICAL = 0 で MAJOR は 6〜8 件出ていた）
if adversarial["n"] >= 10:
    _dry = adversarial["skips"].get("no-eligible-findings", 0)
    if pct(_dry, adversarial["n"]) >= 50:
        signals.append("反証レイヤーがゲート該当 0 件で不発だった回が %.0f%%（%d/%d / "
                       "gate_schema>=2）。既定 high のゲート幅を再検討する条件"
                       "（triage-dynamic-gates.md `## 9`）に該当"
                       % (pct(_dry, adversarial["n"]), _dry, adversarial["n"]))
if meta["n"] >= 8 and meta["fired"] == 0:
    signals.append("meta-reviewer が起動対象 %d 件（gate_schema>=3・effort 帯内）で 1 度も"
                   "起動していない。起動ゲートの再検討が要る" % meta["n"])
elif meta["fired"] >= 10 and pct(meta["valuable"], meta["fired"]) < 20:
    signals.append("meta-reviewer の価値率が %.0f%%（fired %d 件 / gate_schema>=3）。"
                   "層を畳むロールバック条件（triage-dynamic-gates.md `## 8`）に該当"
                   % (pct(meta["valuable"], meta["fired"]), meta["fired"]))

# ---- 出力 -----------------------------------------------------------------
if as_json:
    print(json.dumps({
        "n": n_all, "n_recent_30d": len(recent), "by_plugin": by_plugin,
        # 母集団の再現性（どのログから何件採ったか / issue #160）
        "sources": source_rows(events), "sources_dropped_duplicates": dup_dropped,
        "sources_dropped_paths": dup_paths,
        "tiers": [{"key": k, "n": n, "fleet_median": f, "agents_median": a}
                  for k, n, f, a in tier_rows],
        # 層別なしは交絡を含む参考値（後方互換のため残す）。判定は by_tier 側で行う
        "agents_fleet_r": r, "agents_fleet_n": len(xs),
        "agents_fleet_by_tier": [{"tier": t, "n": n_t, "r": rr}
                                 for t, n_t, rr in tier_r_rows],
        "spans": {k: {"median": m, "n": c} for k, m, c in spans},
        "yields": yields, "verdict_layers": verdict_layers,
        "inflated_axes": inflated_axes, "demoted_types": demoted_types,
        "findings_class": {"n": len(fc_rows), "n_raw": len(fc_raw),
                           "dropped_schema": fc_dropped_schema, "total": fc_total, **fc},
        "recall_skeptic": skeptic, "meta_reviewer": meta,
        "adversarial_verify": adversarial,
        "round2_fired": round2_fired, "round2_scope": len(round2_scope),
        "tokens": {"n": len(tok_rows), "n_raw": len(tok_raw),
                   "dropped_window": tok_dropped_window,
                   "dropped_schema": tok_dropped_schema,
                   "main_output_k_median": median(tok_main),
                   "sub_output_k_median": median(tok_sub),
                   "agents_sub_output_r": tok_r, "agents_sub_output_n": len(txs)},
        "measurement": {"gaps": gap_counts, "n_with_gap_field": n_gapfield,
                        "have_synthesis": have_synthesis, "have_explorer_waves": have_waves,
                        "split_explorer_waves": split_waves,
                        # 健全性判定に使うのは下の modern 側。上の have_* は全サンプル母数の
                        # 生カウントで後方互換のため残す。**waves は分母が違う**
                        # （explorer 起動回のみ = modern_explorer_waves_scope）
                        "n_modern": n_modern, "modern_synthesis": modern_synthesis,
                        "modern_explorer_waves": modern_waves,
                        "modern_explorer_waves_scope": len(modern_waves_scope)},
        "signals": signals,
    }, ensure_ascii=False, indent=2))
    sys.exit(0)

print("## レビュー振り返り（review:completed n=%d）" % n_all)
print()
print(sources_line())
for row in source_rows(events):
    print("- `%s` … %d 件" % (row["path"], row["n"]))
print()
for label, value in report:
    print("- **%s**: %s" % (label, value))

print()
# **世代の内訳は常に出す**（#169）。層別しなかった回に「なぜ 1 本の中央値なのか」を
# 残さないと、次に世代が混ざったとき過去の数字をそのまま比較してしまう
print("**モデル世代**: %s → %s（#169）" % (
    " / ".join("`%s` %d 件" % (g, GEN_COUNTS[g]) for g in GEN_KINDS) or "サンプル無し",
    "2 種以上あるので下の層別キーに含めている" if GEN_SPLIT else "1 種のみなので層別しない"))
print()
print("**effort × size_tier**（fleet 中央値 / 体数中央値）")
print()
print("| effort/tier | n | fleet 中央値 | 体数中央値 |")
print("|---|---:|---:|---:|")
for key, n, f, a in tier_rows[:8]:
    print("| %s | %d | %s | %s |" % (key, n, "-" if f is None else "%g 分" % f,
                                     "-" if a is None else "%g" % a))
if tier_r_rows:
    print()
    print("**体数 vs fleet 時間の相関**（size_tier 内。tier が体数と fleet の両方を"
          "決めるため層別しない r は交絡する / issue #151）")
    print()
    print("| tier | n | r | 判定 |")
    print("|---|---:|---:|---|")
    for t, n_t, rr in tier_r_rows:
        if rr is None or n_t < R_MIN_N:
            verdict = "判定不能（n < %d）" % R_MIN_N
        elif abs(rr) < R_FLAT:
            verdict = "体数はレバーではない"
        elif abs(rr) < R_STRONG:
            verdict = "弱〜中（effort の交絡を疑う）"
        else:
            verdict = "⚠️ 高い"
        print("| %s | %d | %s | %s |" % (t, n_t, "-" if rr is None else "%.3f" % rr, verdict))
    print()
    if not tier_r_judged:
        print("どの tier も n < %d。**体数と壁時計の関係は判定しない**（標本不足）。" % R_MIN_N)
    elif all(abs(rr) < R_FLAT for _, _, rr in tier_r_judged):
        print("判定できる全 tier で |r| < %.1f。**体数は壁時計のレバーではない**"
              "（triage-guide.md `## 7`）— 時間が長いときの打ち手は synthesis / wave 側で"
              "切り分ける。" % R_FLAT)
    if r is not None:
        print("層別なしの r = %.3f（n=%d）は **tier 交絡を含むので発火条件には使わない**"
              "（参考値）。" % (r, len(xs)))

print()
print("**区間の中央値**: " + " / ".join(
    "%s %s（n=%d）" % (k, "-" if m is None else "%g 分" % m, c) for k, m, c in spans))

if yields:
    print()
    print("**pre_adjust → 報告の歩留まり**（版マーカー × 閾値で層別）")
    for key, y in sorted(yields.items()):
        print("- %s: n=%d / 検出 %d → 報告 %d（%.1f%%）"
              % (key, y["n"], y["pre"], y["post"], pct(y["post"], y["pre"])))

if splits:
    print()
    print("**検出 → 報告の内訳**（`below_threshold_counts` を持つ回のみ / #146）")
    for key, sp in sorted(splits.items()):
        written = sp["pre"] - sp["below"]
        dropped = written - sp["post"]
        print("- %s: n=%d / 本文を書いた %d（検出 %d − 件数のみ %d）→ 報告 %d"
              % (key, sp["n"], written, sp["pre"], sp["below"], sp["post"]))
        # **負を丸めない**（0 に丸めると「捨てていない」と読める）。手順 1 の後に走る層
        # （recall_skeptic / meta_reviewer の findings_added）が足すと負になりうる
        print("  - **本文を書いてから捨てた: %d 件（%.1f%%）**%s"
              % (dropped, pct(dropped, written),
                 "" if dropped >= 0 else
                 " — 負は手順 1 の後に走る層が足したぶん（recall_skeptic / meta_reviewer）"))
elif yields:
    print()
    print("**検出 → 報告の内訳**は `below_threshold_counts` を持つサンプル待ち（#146）"
          " — 上の歩留まりは「本文を書いてから捨てた」と「件数だけ返した」の合算で、"
          "この 2 つを分けないと閾値注入（#117）の効果は判定できない")

if verdict_layers:
    print()
    print("**反証 verdict 分布**（calibration_schema で層別 — 累計で読むと施策の効果が薄まる）")
    print()
    print("| calib | サンプル | verdict | confirmed | severity_inflated | refuted | uncertain | contested |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for layer in sorted(verdict_layers):
        L = verdict_layers[layer]
        print("| %s | %d | %d | %.0f%% | **%.0f%%** | %.0f%% | %.0f%% | %.0f%% |" % (
            layer, L["n"], L["total"],
            pct(L["confirmed"], L["total"]), pct(L["severity_inflated"], L["total"]),
            pct(L["refuted"], L["total"]), pct(L["uncertain"], L["total"]),
            pct(L["contested"], L["total"])))
    # 黙るだけだと「効果あり」と読まれうるので、**判定できない間はその旨を 1 行で言う**
    # （⚠️ 欄には出さない / issue #131）。**「層 1 のみ」だけを待ち扱いにしない** — 現行版 publish は
    # `calibration_schema: 2` を常に注入するので層 2 は 1 件目ですぐ現れる一方、シグナルは
    # `VERDICT_MIN` を要求する。層で切るだけだと**蓄積中（1〜19 verdict）が無言区間**になり、
    # まさに避けたかった誤読を作る
    if newest_layer is not None and newest_layer < CALIB_MIN:
        print()
        print("上流較正（v2.62.0）の効果判定は **`calibration_schema >= %d` のサンプル待ち**"
              "（現在は層 %s のみ = 対策前）。累計の severity_inflated 比率を効果測定に使わない"
              " — triage-dynamic-gates.md `## 9`" % (CALIB_MIN, newest_layer))
    elif newest_layer is not None and verdict_layers[newest_layer]["total"] < VERDICT_MIN:
        print()
        print("上流較正（v2.62.0）の効果判定は **層 %d を蓄積中**（%d/%d verdict）。"
              "この件数ではシグナルを出さない — triage-dynamic-gates.md `## 9`"
              % (newest_layer, verdict_layers[newest_layer]["total"], VERDICT_MIN))

for _title, _rows, _note in (
        ("反証 `severity_inflated` の型別内訳", inflated_axes, "下流（反証レイヤー）の降格"),
        ("上流降格（`## below-threshold` 跨ぎ）の型別内訳", demoted_types,
         "reviewer が自分で閾値を跨いで降格した分")):
    if not any(r["total"] for r in _rows.values()):
        continue
    print()
    print("**%s**（%s / **skill 別** — 非対称そのものが観測対象）" % (_title, _note))
    print()
    print("| skill | サンプル | 件数 | base 由来 | 読み違え | 影響過大 | カテゴリ違い | 型不明 |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for _plugin in sorted(_rows):
        _r = _rows[_plugin]
        if not _r["total"]:
            continue
        print("| %s | %d | %d | %.0f%% | %.0f%% | %.0f%% | %.0f%% | %.0f%% |"
              % (_plugin.split(":")[-1], _r["n"], _r["total"],
                 *[pct(_r[k], _r["total"]) for k in DEMOTE_TYPES]))

# **黙ると「型は取れている」と読まれる**（#131 と同じ型の誤読）。内訳が 1 件も無い間は、
# 反証 verdict が貯まっていること自体を根拠に待ち状態を 1 行出す
if verdict_layers and not any(r["total"] for r in inflated_axes.values()):
    print()
    print("**降格の型別内訳**は `inflated_axes` / `demoted_types` を持つサンプル待ち（#150）"
          " — 件数だけでは「型が的外れ」と「そもそも上流で直せない」を切り分けられない")

print()
print("**動的層の発火**（**層ごとに分母が違う** — 各層の版マーカーで濾し、設計上の非該当"
      "スキップを外した母集団。round2 は `agents.round2` を持つ回）: "
      "skeptic %d/%d（価値 %d） / meta %d/%d（価値 %d） / 反証 %d/%d（verdict 有 %d） / "
      "round2 %d/%d"
      % (skeptic["fired"], skeptic["n"], skeptic["valuable"],
         meta["fired"], meta["n"], meta["valuable"],
         adversarial["fired"], adversarial["n"], adversarial["valuable"],
         round2_fired, len(round2_scope)))
for name, st in (("skeptic", skeptic), ("meta", meta), ("反証", adversarial)):
    if st["dropped_schema"] or st["dropped_scope"] or st["dropped_unrecorded"]:
        print("  - %s 母集団: 全 %d 件 → 判定対象 %d 件（版マーカー %s>=%d で除外 %d / "
              "設計上非該当で除外 %d / 発火記録の欠落で除外 %d）"
              % (name, st["n_raw"], st["n"], st["schema_key"], st["min_schema"],
                 st["dropped_schema"], st["dropped_scope"], st["dropped_unrecorded"]))
    if st["skips"]:
        print("  - %s skip 理由: %s" % (name, " / ".join(
            "%s=%d" % kv for kv in sorted(st["skips"].items(), key=lambda kv: -kv[1]))))

print()
if fc_rows:
    print("**指摘の分類**（何が捕まえるべきだったか / n=%d 回・計 %d 件）: "
          "lint %.0f%%（%d） / test %.0f%%（%d） / judgement %.0f%%（%d）。"
          "**0 件を目標にしない — 見るのは構成比**（lint/test が高いほど機械化の余地）"
          % (len(fc_rows), fc_total,
             pct(fc["lint"], fc_total), fc["lint"],
             pct(fc["test"], fc_total), fc["test"],
             pct(fc["judgement"], fc_total), fc["judgement"]))
elif fc_raw:
    print("**指摘の分類**: 判定対象なし（`findings_class` を持つ %d 件はすべて版マーカーで除外）" % len(fc_raw))
else:
    print("**指摘の分類**: 判定対象なし（`findings_class` を持つサンプルが 0 件）")

# **発行パターン**（GitHub issue #142 / 判定単位の是正が #149）: 一括発行が守られた割合。
# **`dispatch.schema >= 2` だけを集計する** — schema 1 は起動時刻のフラットな時系列に 120 秒
# 閾値を当てており、**wave 間ギャップ（層をまたぐ正当な逐次実行）を違反として数えていた**。
# 混ぜると「守られた割合」が構造的に 0% に張り付く（実測: schema 1 の 4 件は全て serial）
disp_rows = [e for e in events if isinstance(e["p"].get("dispatch"), dict)]
v1_rows = [e for e in disp_rows if (e["p"]["dispatch"] or {}).get("schema") is None]
judged = [e["p"]["dispatch"] for e in disp_rows
          if (e["p"]["dispatch"] or {}).get("schema") is not None
          and (e["p"]["dispatch"] or {}).get("verdict") in ("batched", "serial", "layered")]
v1_tail = ("" if not v1_rows
           else " / 判定単位が誤っていた schema 1 を %d 件除外" % len(v1_rows))
print()
if not judged:
    print("**発行パターン**: 判定対象なし（`dispatch.schema >= 2` を持つサンプル %d 件%s）"
          % (len(disp_rows) - len(v1_rows), v1_tail))
else:
    n_b = sum(1 for d in judged if d["verdict"] == "batched")
    n_s = sum(1 for d in judged if d["verdict"] == "serial")
    # **1 wave あたりの体数**が効率の本体（wave 数は層の数なので減らせない）。
    # 守れているほど大きくなる
    per_wave = median([(d.get("agents") or 0) / (d.get("waves") or 1) for d in judged])
    tail = "" if per_wave is None else " / 1 wave あたり 中央値 %.1f 体" % per_wave
    print("**発行パターン**（一括発行 / n=%d%s）: **batched %d・layered %d・serial %d**%s"
          % (len(judged), v1_tail, n_b, len(judged) - n_b - n_s, n_s, tail))
    if n_s:
        print("  - **serial %d 件**（単独 wave が %d 連続以上）。同一フェーズを 1 メッセージで"
              "発行すれば fleet は**wave 内最長の 1 体**で決まる（orchestration-guide.md `## 0`）"
              % (n_s, min(d.get("max_solo_run") or 0 for d in judged
                          if d["verdict"] == "serial")))
    # **最大ギャップの内訳**（GitHub issue #153）。どちらが支配的かで打ち手が正反対
    # （agent 側なら wave を減らす / idle 側なら往復を減らす）。
    #
    # **比率は「回ごとの比の中央値」で採る**（総和プールではない）。プールド比 `sum(a)/sum(a+i)`
    # は巨大ギャップ 1 件に支配され、**同じ行に並ぶ中央値と逆の結論を出す**（実測:
    # (10,90)(11,89)(12,88)(13,87)(3000,200) で中央値は idle 支配なのにプールドは agent 85%）。
    # 印字した数値だけで再計算できることを不変条件にする。隣の `per_wave`（体数/wave）も
    # 回ごとの比の中央値を採っており、そちらに揃えた
    #
    # 除外は 2 種類あり、**理由を潰さない**: `-1` は欠測（終了時刻が引けなかった回）、
    # `(0, 0)` は `batched`（1 wave = ギャップ無し）で**目標状態そのもの**。どちらも
    # 「サンプルが無い」ではないので、else 側で件数を出し分ける（#131 と同じ誤読を作らない）
    gap_rows = [(num(d.get("inter_wave_agent_sec")), num(d.get("inter_wave_idle_sec")))
                for d in judged if schema_of(d, "schema") >= 3]
    gap_missing = sum(1 for a, i in gap_rows
                      if a is None or i is None or a < 0 or i < 0)
    gap_nogap = sum(1 for a, i in gap_rows
                    if a is not None and i is not None
                    and a >= 0 and i >= 0 and (a + i) == 0)
    gaps = [(a, i) for a, i in gap_rows if a is not None and i is not None
            and a >= 0 and i >= 0 and (a + i) > 0]
    if gaps:
        m_agent, m_idle = median([a for a, _ in gaps]), median([i for _, i in gaps])
        # 回ごとの比の中央値。`a + i > 0` は上のフィルタで保証済み
        share = median([a / (a + i) for a, i in gaps])
        line = ("  - **最大ギャップの内訳**（n=%d）: agent 実行 中央値 %.0f 秒 / "
                "オーケストレーター 中央値 %.0f 秒 / **agent 側 %.0f%%**（回ごとの比の中央値）"
                % (len(gaps), m_agent, m_idle, share * 100))
        # **打ち手の提示にはサンプル下限を掛ける**（このファイルの他の打ち手行と同じ流儀 —
        # `R_MIN_N` / `VERDICT_MIN` / `GAP_MIN_N` / skeptic `>= 15` / meta `>= 10`）。
        # #153 が Phase 2 を保留した理由（支配側が正反対の打ち手を指す）を、集計側から
        # 骨抜きにしないため。下限未満では数値だけ出して打ち手を出さない
        if len(gaps) < WAVE_GAP_MIN_N:
            line += "。**打ち手は出さない**（n < %d / issue #153）" % WAVE_GAP_MIN_N
        elif share >= 0.6:
            line += "。**agent 支配** → 打ち手は末尾 wave の去就（issue #153）"
        elif share <= 0.4:
            line += "。**idle 支配** → 打ち手は往復削減（#147 / issue #153）"
        else:
            line += "。**支配側なし**（40-60%%）— どちらの打ち手も当てない（issue #153）"
        print(line)
    else:
        print("  - **最大ギャップの内訳**: 実測 0 件（`dispatch.schema >= 3` が %d 件 / "
              "うち終了時刻の欠測 %d・`batched` でギャップ無し %d）。**「まだ載っていない」と"
              "「載ったが全件除外」を区別すること** — 前者は publisher、後者は transcript か "
              "wave 構成が原因（#153）"
              % (len(gap_rows), gap_missing, gap_nogap))

print()
if not tok_rows:
    print("**トークン**: 判定対象なし（`tokens` を持つサンプル %d 件 / うち "
          "`window=session` / `since-t0-late` で除外 %d 件。**v2.70.0 より前は review でしか"
          "載らなかった**ので、それ以前のサンプルには構造的に無い / GitHub issue #143）"
          % (len(tok_raw), tok_dropped_window))
else:
    line = ("**トークン**（t0 以降の窓 / n=%d/%d・`window=session` / `since-t0-late` で除外 %d）: "
            "main.output 中央値 %s / sub.output 中央値 %s"
            % (len(tok_rows), len(tok_raw), tok_dropped_window,
               "-" if median(tok_main) is None else "%g k" % median(tok_main),
               "-" if median(tok_sub) is None else "%g k" % median(tok_sub)))
    if tok_r is not None:
        line += " / 体数 vs sub.output r=%.2f（n=%d）" % (tok_r, len(txs))
    print(line + "。**壁時計の結論と混ぜない**（体数が効くのはこちら側 — triage-guide.md `## 7`）")
    print()
    if per_agent_rows:
        print("**1 体あたり cache_read**（effort × size_tier。基準値は 1 体 5,039k / "
              "`pending-optimizations.md ## 計測の基準値`。**体数キャップは広さを切っただけで"
              "ここには手が入っていない** / issue #156）")
        print()
        print("| effort/tier | n | 1 体あたり中央値 |")
        print("|---|---:|---:|")
        for key, n, m in per_agent_rows[:8]:
            print("| %s | %d | %s |" % (key, n, "-" if m is None else "%.0f k" % m))
    else:
        print("**1 体あたり cache_read**: 実測 0 件（`tokens.schema >= %d` 未満で除外 %d・"
              "`sub_agents` が 0 / 欠測で除算不可 %d）。**「まだ載っていない」と「載ったが"
              "除算できない」を区別すること** — 前者は publisher、後者は "
              "`measure-tokens.sh` の窓・引き当てが原因（issue #156）"
              % (TOK_CACHE_READ_MIN_SCHEMA, per_agent_old_schema, per_agent_undividable))

print()
if n_modern == 0:
    print("**計測の健全性**: 判定対象なし（`measurement_gaps` を持つ v2.62.0 以降の"
          "サンプルが 0 件。全 %d 件は旧版で publish されたもの）" % n_all)
else:
    waves_txt = ("explorer_waves %d/%d 件（explorer 起動回のみ）"
                 % (modern_waves, len(modern_waves_scope)) if modern_waves_scope
                 else "explorer_waves 該当なし（explorer 起動回 0）")
    print("**計測の健全性**（母集団 %d/%d 件 = v2.62.0 以降。フィールド不在は旧版の "
          "identification であって欠測ではない）: synthesis %d/%d 件 / %s"
          % (n_modern, n_all, modern_synthesis, n_modern, waves_txt)
          + ("" if not gap_counts else " / 欠測内訳 " + " ".join(
              "%s=%d" % kv for kv in sorted(gap_counts.items(), key=lambda kv: -kv[1]))))
    # **補完の待ち行を出し分ける**（issue #161）。「フィールドを持つ回が 0」（旧版のみ）と
    # 「持っているが 1 件も補完していない」（打点が守られた or 補完条件を満たさなかった）は
    # 別の状態で、潰すと「補完機構が入っているのに効いていない」を見逃す
    if n_derivedfield == 0:
        print("  - 打点補完: 判定対象なし（`derived_markers` フィールドが 1 件も無い"
              "＝すべて補完機構より前の版で publish された）")
    elif not derived_counts:
        print("  - 打点補完: %d 件中 0 件（打点が守られたか、補完条件を満たさなかった回のみ）"
              % n_derivedfield)
    else:
        print("  - 打点補完（agent の実測時刻で埋めた分 / `measurement_gaps` とは排他ではない）: "
              "%s" % " ".join("%s=%d" % kv
                              for kv in sorted(derived_counts.items(), key=lambda kv: -kv[1])))

if signals:
    print()
    print("**⚠️ シグナル**（ロールバック条件・再監視条件に該当）")
    for s in signals:
        print("- %s" % s)
PY
exit 0
