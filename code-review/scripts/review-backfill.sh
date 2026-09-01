#!/usr/bin/env bash
# publish 済みの `review:completed` に、**生き残っている agent transcript から**
# `dispatch` / `tokens` を後付けする（GitHub issue #153 / #156）。
#
# **なぜ要るのか**: 計測フィールドは追加された版以降の回にしか載らないので、判断に
# 必要なサンプルが貯まるまで待つしかなかった。しかし transcript は残っているので、
# **窓を復元できる回に限り**事後に同じ値を算出できる（実測: #153 は n=1 から n=6 に
# なり Phase 2 の判定下限を満たした / #156 は n=2 から n=7）。
#
# **これは推定ではない。** 使うのは `measure-tokens.sh` が読む agent transcript の
# 実測時刻で、#142 が `dispatch` で確立した経路と同じ。窓（`[t0, t2]`）だけが
# payload の `duration_*` からの逆算で、**分オーダーの誤差が乗る**。
#
# **後付け値を publish しない / `review-retro.sh` に混ぜない。** retro は publish 時点の
# 計測を集計する道具で、そこへ精度の違う値を混ぜると層別が読めなくなる。本スクリプトは
# 「判断のためにサンプルを増やしたいとき」に**手で**回す。
#
# 使い方:
#   review-backfill.sh                    # 既定のイベントログを後付けして表で出す
#   review-backfill.sh --logs A B         # ログを明示（review-retro.sh と同じ流儀）
#   review-backfill.sh --projects ~/.claude/projects/*   # transcript の探索先を明示
#   review-backfill.sh --json             # 機械可読
#
# **`--projects` は明示指定のみ**（既定は今いるリポジトリ由来の 2 候補）。`--logs` で
# 他リポジトリのイベントを混ぜると transcript は別 slug にあるため既定では解決できないが、
# **暗黙に全 slug へ広げない** — 同時刻に別リポジトリでレビューが走っていると、窓が重なった
# 別セッションを掴みうる（誤値より欠測に倒す本スクリプトの方針）。広げるのは利用者の明示操作。
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=lib/review-paths.sh
. "$HERE/lib/review-paths.sh"

AS_JSON=0; EXPLICIT_LOGS=(); EXPLICIT_PROJS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --json) AS_JSON=1; shift ;;
    --logs)
      shift
      while [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; do EXPLICIT_LOGS+=("$1"); shift; done
      [ ${#EXPLICIT_LOGS[@]} -gt 0 ] || { echo "FATAL: --logs にパスが必要" >&2; exit 2; }
      ;;
    --projects)
      shift
      while [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; do EXPLICIT_PROJS+=("$1"); shift; done
      [ ${#EXPLICIT_PROJS[@]} -gt 0 ] || { echo "FATAL: --projects にパスが必要" >&2; exit 2; }
      ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 が必要" >&2; exit 2; }

LOGS=()
if [ ${#EXPLICIT_LOGS[@]} -gt 0 ]; then
  # **明示指定は実在を要求する**（review-retro.sh と同じ）。タイプミスを
  # 「サンプルが少ない」に化けさせない
  for _l in "${EXPLICIT_LOGS[@]}"; do
    [ -f "$_l" ] || { echo "FATAL: ログが読めない: ${_l}" >&2; exit 2; }
    LOGS+=("$_l")
  done
else
  review_event_logs && LOGS=(${REVIEW_EVENT_LOGS[@]+"${REVIEW_EVENT_LOGS[@]}"})
fi
[ ${#LOGS[@]} -gt 0 ] || { echo "イベントログが無い（.claude/events.jsonl）" >&2; exit 0; }

if [ ${#EXPLICIT_PROJS[@]} -gt 0 ]; then
  # **実在を要求する**（`--logs` と同じ。タイプミスを「サンプルが少ない」に化けさせない）
  for _d in "${EXPLICIT_PROJS[@]}"; do
    [ -d "$_d" ] || { echo "FATAL: project ディレクトリが読めない: ${_d}" >&2; exit 2; }
  done
  PROJ_DIRS=("${EXPLICIT_PROJS[@]}")
else
  review_project_dirs
  PROJ_DIRS=(${REVIEW_PROJECT_DIRS[@]+"${REVIEW_PROJECT_DIRS[@]}"})
fi

REVIEW_LOGS=$(printf '%s\n' "${LOGS[@]}") \
REVIEW_PROJS=$(printf '%s\n' "${PROJ_DIRS[@]}") \
REVIEW_MEASURE="$HERE/measure-tokens.sh" \
REVIEW_LIB_DIR="$HERE/lib" \
REVIEW_JSON="$AS_JSON" \
python3 <<'PY'
import glob, json, os, subprocess, sys

# 期待 wave 本数の式は `lib/wave_expect.py` が正本（publish / backfill / retro が共有）
sys.dont_write_bytecode = True    # mutation-ok: 配布物の `lib/` に `__pycache__` を作らせないだけで、判定にも出力にも効かない
sys.path.insert(0, os.environ["REVIEW_LIB_DIR"])
from wave_expect import expected_waves
from datetime import datetime, timezone

MEASURE = os.environ["REVIEW_MEASURE"]
AS_JSON = os.environ.get("REVIEW_JSON") == "1"
LOGS = [x for x in os.environ.get("REVIEW_LOGS", "").split("\n") if x]
PROJS = [x for x in os.environ.get("REVIEW_PROJS", "").split("\n") if x]

# 窓の外にどれだけ離れた agent までを「別レビューの疑い」と見るか。
# 6 時間は「同じセッションで前後に別のレビューを回した」を拾い、
# 「何日も前の別作業」を拾わない幅（実測でこの帯に混入が集中した）
NEAR_SEC = 6 * 3600
# wave 間ギャップの上限。これを超える回は窓が別レビューを丸ごと飲み込んでいる
# （実測: 27 時間。レビュー中の wave 間隔ではありえない）
MAX_GAP_SEC = 2 * 3600


def ep(s):
    return int(datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
               .replace(tzinfo=timezone.utc).timestamp())


def iso(e):
    return datetime.fromtimestamp(e, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- このリポジトリの session-id を集める -----------------------------------
# **slug をまたいで session-id で引き当てる**（`measure-tokens.sh` と同じ理由 —
# EnterWorktree でサブエージェントが別 slug に落ちる）。ただし「このリポジトリの
# セッション」に絞るため、**トップレベルの .jsonl が候補 dir にある sid だけ**採る
own, session_path = set(), {}
for d in PROJS:
    for f in glob.glob(os.path.join(d, "*.jsonl")):
        sid = os.path.basename(f)[:-len(".jsonl")]
        own.add(sid)
        session_path[sid] = f

starts = {}
for d in glob.glob(os.path.join(os.path.expanduser("~/.claude/projects"), "*", "*", "subagents")):
    sid = os.path.basename(os.path.dirname(d))
    if sid not in own:
        continue
    for f in glob.glob(os.path.join(d, "agent-*.jsonl")):
        try:
            fh = open(f, errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    ts = json.loads(line).get("timestamp")
                except ValueError:
                    continue
                if ts:
                    starts.setdefault(sid, []).append(ep(ts))
                    break
for sid in starts:
    starts[sid].sort()

# --- イベントを読む（複数ログは dedup） -------------------------------------
seen, events = set(), []
for p in LOGS:
    try:
        fh = open(p, errors="replace")
    except OSError:
        continue
    with fh:
        for line in fh:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("event") != "review:completed":
                continue
            key = (e.get("ts"), e.get("plugin"), json.dumps(e.get("payload"), sort_keys=True))
            if key in seen:
                continue
            seen.add(key)
            events.append(e)
events.sort(key=lambda e: e.get("ts") or "")

rows, skipped = [], {}


def skip(reason):
    skipped[reason] = skipped.get(reason, 0) + 1


def num(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and v > -1 else None


for e in events:
    p = e.get("payload") or {}
    total, tri, fleet = (num(p.get(k)) for k in
                         ("duration_min", "duration_triage_min", "duration_fleet_min"))
    if total is None or tri is None or fleet is None:
        skip("区間欠測で窓を作れない")
        continue
    t3 = ep(e["ts"])
    t0 = t3 - total * 60
    t2 = t0 + (tri + fleet) * 60

    best, hits = None, 0
    for sid, st in starts.items():
        n = sum(1 for x in st if t0 <= x <= t2)
        if n > hits:
            best, hits = sid, n
    if not best:
        skip("transcript が残っていない")
        continue
    if any(t0 - NEAR_SEC <= x <= t2 + NEAR_SEC for x in starts[best] if not (t0 <= x <= t2)):
        skip("窓の外にも同セッションの agent がある（別レビュー混入）")
        continue

    out = subprocess.run(["bash", MEASURE, "--session", session_path[best],
                          "--since", iso(t0), "--json"],
                         capture_output=True, text=True)
    try:
        tok = json.loads(out.stdout)
    except ValueError:
        skip("measure-tokens が値を返さなかった")
        continue
    d = tok.get("dispatch") or {}
    if (d.get("max_inter_wave_sec") or 0) > MAX_GAP_SEC:
        skip("窓が別レビューを内包している")
        continue

    # 突合式は `publish-review-event.sh` の `declared` と同一にすること。
    # **`adversarial_verify` は足さない** — `verify` として既に `agents` に入っている
    # （`orchestration-measurement.md ## 16`）。ここを踏み外すと #154 が検知したい
    # 信号と同じ形のノイズが出る
    a = p.get("agents") if isinstance(p.get("agents"), dict) else {}
    declared = sum(v for k, v in a.items()
                   if k in ("explorer", "reviewer", "specialist", "round2", "verify")
                   and isinstance(v, int) and not isinstance(v, bool))
    declared += sum(1 for f in ("recall_skeptic", "meta_reviewer")
                    if isinstance(p.get(f), dict) and p[f].get("fired") is True)

    # 期待 wave 本数。**式の正本は `lib/wave_expect.py`**（publish / retro と共有する）。
    # 以前はここに publish の式の複製を置き、一致を回帰テストで縛っていた（`declared` を
    # 意味から再構成して偽の食い違いを出した実例がある）。#200 で正本へ寄せた。
    expected = expected_waves(p, d.get("wave_sizes"))
    # **判定は `waves_effective`（捨てられた試行・孫を除いた本数）**。無ければ `waves`
    # にフォールバックする（旧 schema / 分解が成立しなかった回）。式は上の
    # `expected_waves`（`lib/wave_expect.py`）と共有するので、この行の順序を publish と揃える。
    waves = d.get("waves_effective")
    if not isinstance(waves, int) or isinstance(waves, bool):
        waves = d.get("waves")
    # publish 側と同じく **`agents` の申告が壊れている回では判定しない**
    # 突合の相手も publish に揃える（`agents_completed` → 無ければ `agents`）
    _measured = d.get("agents_completed")
    if not isinstance(_measured, int) or isinstance(_measured, bool):
        _measured = d.get("agents") or 0
    split = (declared == _measured and isinstance(waves, int)
             and not isinstance(waves, bool) and waves > expected)

    sub, n_ag = tok.get("sub") or {}, tok.get("sub_agents") or 0
    clock = tok.get("wave_clock") or []
    tail_share = tail_n = None
    # **`end` は欠測しうる**（wave 内に終了時刻を取れない体が 1 体でもいれば
    # `measure-tokens.sh` が `None` を入れる / #153 の縮退方向）。素で引き算すると
    # `TypeError` で**行の途中まで出力して落ちる** — 実データが全部埋まっていたので
    # 表に出ていなかった経路（回帰テストで検出）
    if len(clock) > 1:
        last_end, first_start = clock[-1].get("end"), clock[0].get("start")
        last_start = clock[-1].get("start")
        if None not in (last_end, first_start, last_start):
            span = last_end - first_start
            if span > 0:
                tail_n = clock[-1]["n"]
                tail_share = (last_end - last_start) / span
    rows.append({
        "ts": e["ts"], "plugin": e.get("plugin"), "session": best,
        "effort": p.get("effort"), "size_tier": p.get("size_tier"),
        "dispatch": d, "declared": declared,
        "agents_diff": (d.get("agents") or 0) - declared,
        "cache_read_k_per_agent": round(sub.get("cache_read", 0) / n_ag / 1000, 1) if n_ag else None,
        "sub_agents": n_ag,
        "tail_wave_n": tail_n,
        "tail_wave_share": round(tail_share, 3) if tail_share is not None else None,
        "waves_expected": expected,
        "wave_split": split,
        # **モデル世代**（#169）。`cache_read_k_per_agent` は tier と世代が交絡するので、
        # 層別キー無しに中央値を出すと「深さのコストが下がった」と「世代が違うから軽い」を
        # 分離できない。`main` が `None` の回（実行中に切り替えた / 引けなかった）は
        # `mixed` として別バケツに落とす — **単一世代の分布に混ぜない**
        "model_main": (tok.get("models") or {}).get("main"),
    })

if AS_JSON:
    print(json.dumps({"backfilled": rows, "candidates": len(events),
                      "skipped": skipped}, ensure_ascii=False, indent=2))  # mutation-ok: ensure_ascii は日本語の除外理由を生で出すためで、JSON としては等価（テストは json.loads を通すので殺せないし殺す意味もない）
    raise SystemExit(0)


def med(vals):
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    h = len(v) // 2
    return v[h] if len(v) % 2 else (v[h - 1] + v[h]) / 2


print("## 後付け計測（publish 済み payload には無い値 / retro には出ない）\n")
print("母集団: review:completed %d 件 → 後付け成立 %d 件" % (len(events), len(rows)))
for k in sorted(skipped, key=lambda x: -skipped[x]):
    print("  除外 %3d 件: %s" % (skipped[k], k))
if not rows:
    print("\n窓を復元できる回が無い。**これは「計測が壊れている」ではない** — "
          "打点が落ちた回と transcript が消えた回は原理的に後付けできない")
    raise SystemExit(0)

def gen_label(v):
    """モデル世代の表示ラベル。`None` は混在か引き当て失敗で、どちらも層別に使えない"""
    if not v:
        return "mixed"
    return v[len("claude-"):] if v.startswith("claude-") else v


print("\n%-22s %-12s %-10s %-16s %6s %6s %8s %9s" %
      ("ts", "effort/tier", "世代", "wave_sizes", "体数", "申告差", "cr/体(k)", "末尾wave"))
for r in rows:
    d = r["dispatch"]
    tail = "-" if r["tail_wave_share"] is None else "%d体 %.0f%%" % (r["tail_wave_n"], r["tail_wave_share"] * 100)
    print("%-22s %-12s %-10s %-16s %6s %+6d %8s %9s" % (
        r["ts"], "%s/%s" % (r["effort"], r["size_tier"]), gen_label(r["model_main"]),
        json.dumps(d.get("wave_sizes")), d.get("agents"), r["agents_diff"],
        r["cache_read_k_per_agent"] if r["cache_read_k_per_agent"] is not None else "-", tail))

split = [r for r in rows if r["wave_split"]]
judged = [r for r in rows if r["agents_diff"] == 0]
print("\n- **一括発行違反（wave 本数が期待超え）**: %d / %d 件"
      "（`agents` の申告が壊れた回 %d 件は判定対象外）"
      % (len(split), len(judged), len(rows) - len(judged)))
for r in split:
    print("    %s  wave %s（期待 %s） %s" % (r["ts"], r["dispatch"].get("waves"),
                                            r["waves_expected"], json.dumps(r["dispatch"].get("wave_sizes"))))
mismatch = [r for r in rows if r["agents_diff"] != 0]
print("\n- **`agents` の申告と機械計測の差**: 一致 %d / 不一致 %d（#154）"
      % (len(rows) - len(mismatch), len(mismatch)))
m = med([r["cache_read_k_per_agent"] for r in rows])
if m is not None:
    print("- **1 体あたり cache_read の中央値**: %.1fk（#156 の基準値は 5,039k）" % m)
# **世代で層別する**（#169）。tier と世代が交絡した状態で 1 本の中央値を出すと、
# 「深さのコストが下がった」と「世代が違うから軽い」を分離できない。
# **単一世代の回だけを比較に使う** — mixed は件数だけ出して分布には混ぜない
by_gen = {}
for r in rows:
    by_gen.setdefault(gen_label(r["model_main"]), []).append(r["cache_read_k_per_agent"])
# **全行が mixed の回でも内訳を出す**。1 種だからと「層別不要」で畳むと、
# **上の中央値が丸ごと比較に使えない行から出来ている**ことが表に出ない
UNUSABLE_GEN = "mixed"
if len(by_gen) > 1 or UNUSABLE_GEN in by_gen:
    print("  世代別（交絡を切るための層別 / #169）:")
    for g in sorted(by_gen):
        gm = med(by_gen[g])
        note = "  ← 混在・引き当て失敗。単一世代の比較には使わない" if g == "mixed" else ""
        print("    %-10s n=%-3d 中央値 %s%s"
              % (g, len(by_gen[g]), "%.1fk" % gm if gm is not None else "-", note))
elif rows:
    print("  （世代は %s の 1 種のみ。層別不要 / #169）" % next(iter(by_gen)))
gaps = [(d["inter_wave_agent_sec"], d["inter_wave_idle_sec"])
        for d in (r["dispatch"] for r in rows)
        # mutation-ok: 2 つのフィールドは `measure-tokens.sh` が必ず同時に入れる（`schema` 3）ので、片方だけ在る dispatch は生成経路が無い
        if d.get("inter_wave_agent_sec", -1) > -1 and d.get("inter_wave_idle_sec", -1) > -1
        # mutation-ok: 同上（上の行で両方の存在が確定してから足している）
        and (d["inter_wave_agent_sec"] + d["inter_wave_idle_sec"]) > 0]
if gaps:
    ar = med([g[0] / (g[0] + g[1]) for g in gaps])
    print("- **最大 wave 間ギャップに占める agent 実行の中央値**: %.1f%%（n=%d / #153）"
          % (ar * 100, len(gaps)))
ts = med([r["tail_wave_share"] for r in rows if r["tail_wave_n"] == 1])
if ts is not None:
    print("- **末尾 1 体 wave が fleet span に占める割合の中央値**: %.1f%%"
          "（`max_inter_wave_sec` と混同しないこと / `orchestration-measurement.md ## 15`）" % (ts * 100))
print("\n**窓は payload の `duration_*` からの逆算なので分オーダーの誤差が乗る。** "
      "境界に近い判定（打点補完の可否など）には使えない")
PY
