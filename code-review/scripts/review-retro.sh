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
#
# **層別の原則**: 版マーカー（`pre_adjust_counts.schema` / `*.gate_schema` /
# `attribution_schema` / `calibration_schema`）で切り、日付では切らない。マーケットプレイス
# 配布のため未更新マシンが旧仕様で publish し続けるため。**累計で読むと施策の効果が薄まる**
# ので、版マーカーを持つ指標は必ず層別してから判定する（比較演算子は `>=` で前方互換にする。
# `== N` にすると次の版 bump でセクションが無音で消える）。
set -uo pipefail

SINCE=""; LAST=""; AS_JSON=0
while [ $# -gt 0 ]; do
  case "$1" in
    --since) [ $# -ge 2 ] || { echo "FATAL: --since に値が必要" >&2; exit 2; }; SINCE="$2"; shift 2 ;;
    --last)  [ $# -ge 2 ] || { echo "FATAL: --last に値が必要" >&2; exit 2; }; LAST="$2"; shift 2 ;;
    --json)  AS_JSON=1; shift ;;
    *) echo "FATAL: 未知の引数: $1" >&2; exit 2 ;;
  esac
done
case "${LAST:-0}" in ''|*[!0-9]*) echo "FATAL: --last は数値のみ（受領: '$LAST'）" >&2; exit 2 ;; esac

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/review-paths.sh
# 読み取り専用なので `review_paths_init`（一時 dir の作成）は呼ばない。使うのは
# `review_event_logs` / `review_main_root` だけで、どちらも init に依存しない
. "$HERE/lib/review-paths.sh"

if ! review_event_logs; then
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
for path in sys.argv[1:]:
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
        if key in seen:           # 候補パスが同一ファイルを指す場合の重複除去
            continue
        seen.add(key)
        try:
            when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except ValueError:
            when = None
        events.append({"ts": ts, "when": when, "plugin": ev.get("plugin", "?"),
                       "p": ev.get("payload") or {}})

events.sort(key=lambda e: e["ts"])
if since:
    events = [e for e in events if e["when"] and e["when"] >= since]
if last_n:
    events = events[-last_n:]

if not events:
    if as_json:
        print(json.dumps({"n": 0, "reason": "no-samples-in-range", "signals": []},
                         ensure_ascii=False))
    else:
        print("## レビュー振り返り")
        print("対象サンプルが 0 件。")
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

# ---- 2. effort × size_tier 別の fleet 時間・体数 ---------------------------
buckets = {}
for e in events:
    p = e["p"]
    fleet = num(p.get("duration_fleet_min"))
    if fleet is None or fleet < 0:
        continue
    key = "%s/%s" % (p.get("effort", "?"), p.get("size_tier", "?"))
    buckets.setdefault(key, {"fleet": [], "agents": []})
    buckets[key]["fleet"].append(fleet)
    ta = total_agents(p)
    if ta is not None:
        buckets[key]["agents"].append(ta)

tier_rows = []
for key in sorted(buckets, key=lambda k: -len(buckets[k]["fleet"])):
    b = buckets[key]
    tier_rows.append((key, len(b["fleet"]), median(b["fleet"]), median(b["agents"])))

# ---- 3. 体数 vs 壁時計の相関 ----------------------------------------------
xs, ys = [], []
for e in events:
    p = e["p"]
    fleet, ta = num(p.get("duration_fleet_min")), total_agents(p)
    if fleet is not None and fleet >= 0 and ta is not None:
        xs.append(ta)
        ys.append(fleet)
r = pearson(xs, ys)
R_MIN_N = 10          # これ未満では結論を書かない（標本が小さすぎる）
R_FLAT = 0.3          # |r| < これ なら「レバーではない」を支持
R_STRONG = 0.6        # |r| >= これ なら再監視条件に該当

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
if r is not None and len(xs) >= R_MIN_N and abs(r) >= R_STRONG:
    signals.append("体数と fleet 時間の相関が r=%.2f（n=%d）と高い。"
                   "「体数は壁時計のレバーではない」（triage-guide.md `## 7`）の再監視条件に該当"
                   % (r, len(xs)))
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
        "tiers": [{"key": k, "n": n, "fleet_median": f, "agents_median": a}
                  for k, n, f, a in tier_rows],
        "agents_fleet_r": r, "agents_fleet_n": len(xs),
        "spans": {k: {"median": m, "n": c} for k, m, c in spans},
        "yields": yields, "verdict_layers": verdict_layers,
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
for label, value in report:
    print("- **%s**: %s" % (label, value))

print()
print("**effort × size_tier**（fleet 中央値 / 体数中央値）")
print()
print("| effort/tier | n | fleet 中央値 | 体数中央値 |")
print("|---|---:|---:|---:|")
for key, n, f, a in tier_rows[:8]:
    print("| %s | %d | %s | %s |" % (key, n, "-" if f is None else "%g 分" % f,
                                     "-" if a is None else "%g" % a))
if r is not None:
    print()
    line = "体数 vs fleet 時間の相関 **r = %.3f**（n=%d）。" % (r, len(xs))
    if len(xs) < R_MIN_N:
        line += "**n < %d なので解釈しない**（標本不足）。" % R_MIN_N
    elif abs(r) < R_FLAT:
        line += ("**体数は壁時計のレバーではない**（triage-guide.md `## 7`）— "
                 "時間が長いときの打ち手は synthesis / wave 側で切り分ける。")
    elif abs(r) < R_STRONG:
        line += ("弱〜中程度の相関。**effort が交絡している可能性**があるので、"
                 "上の effort × tier 表で帯別に見てから判断する。")
    else:
        line += "**⚠️ 相関が高い**（下のシグナル欄を参照）。"
    print(line)

print()
print("**区間の中央値**: " + " / ".join(
    "%s %s（n=%d）" % (k, "-" if m is None else "%g 分" % m, c) for k, m, c in spans))

if yields:
    print()
    print("**pre_adjust → 報告の歩留まり**（版マーカー × 閾値で層別）")
    for key, y in sorted(yields.items()):
        print("- %s: n=%d / 検出 %d → 報告 %d（%.1f%%）"
              % (key, y["n"], y["pre"], y["post"], pct(y["post"], y["pre"])))

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
if not tok_rows:
    print("**トークン**: 判定対象なし（`tokens` を持つ review のサンプル %d 件 / うち "
          "`window=session` で除外 %d 件。self-review は構造的に載らない）"
          % (len(tok_raw), tok_dropped_window))
else:
    line = ("**トークン**（review のみ / t0 以降の窓 / n=%d/%d・`window=session` で除外 %d）: "
            "main.output 中央値 %s / sub.output 中央値 %s"
            % (len(tok_rows), len(tok_raw), tok_dropped_window,
               "-" if median(tok_main) is None else "%g k" % median(tok_main),
               "-" if median(tok_sub) is None else "%g k" % median(tok_sub)))
    if tok_r is not None:
        line += " / 体数 vs sub.output r=%.2f（n=%d）" % (tok_r, len(txs))
    print(line + "。**壁時計の結論と混ぜない**（体数が効くのはこちら側 — triage-guide.md `## 7`）")

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

if signals:
    print()
    print("**⚠️ シグナル**（ロールバック条件・再監視条件に該当）")
    for s in signals:
        print("- %s" % s)
PY
exit 0
