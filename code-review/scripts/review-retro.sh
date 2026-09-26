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
#   review-retro.sh --min-plugin-version <版>   # その版以上で publish された回だけ（#210）
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

SINCE=""; LAST=""; AS_JSON=0; EXPLICIT_LOGS=(); MIN_PV=""
while [ $# -gt 0 ]; do
  case "$1" in
    --since) [ $# -ge 2 ] || { echo "FATAL: --since に値が必要" >&2; exit 2; }; SINCE="$2"; shift 2 ;;
    --last)  [ $# -ge 2 ] || { echo "FATAL: --last に値が必要" >&2; exit 2; }; LAST="$2"; shift 2 ;;
    --json)  AS_JSON=1; shift ;;
    --min-plugin-version)
      [ $# -ge 2 ] || { echo "FATAL: --min-plugin-version に値が必要" >&2; exit 2; }
      # 数字とドットだけ（`v2.10.0` / `2.10.` / `latest` を黙って 0 に丸めると全件が残る）
      case "$2" in
        ''|.*|*.|*..*|*[!0-9.]*)
          echo "FATAL: --min-plugin-version は数字とドットの版で指定する（受領: '$2'）" >&2; exit 2 ;;
      esac
      MIN_PV="$2"; shift 2 ;;
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

# **集計が黙って死ぬのを防ぐ**（GitHub issue #211）。本体は 1 つの python ヒアドキュメントで、
# 未捕捉例外が出ても `set -uo pipefail` に `-e` が無く末尾が無条件 `exit 0` なので、
# **rc 0 のまま stdout が空**になり「⚠️ が出なかった」が「該当なし」と読まれていた。
# `exit 2` は既存の「python3 が無い」と同じ**実行できなかった＝判定不能**の意味。
# **`||` は heredoc と同じ物理行に置くこと** — 改行して `{ }` に展開すると、その中身が
# ヒアドキュメント本体として食われて構文エラーになる
retro_fatal() {
  echo "FATAL: 集計が異常終了した（stderr の traceback を参照。出力は途中まで出ていることがある）" >&2
  exit 2
}

REVIEW_SINCE="$SINCE" REVIEW_LAST="${LAST:-0}" REVIEW_JSON="$AS_JSON" \
  REVIEW_MIN_PLUGIN_VERSION="$MIN_PV" \
  REVIEW_LOGS_EXPLICIT="$([ ${#EXPLICIT_LOGS[@]} -gt 0 ] && echo 1 || echo 0)" \
  REVIEW_LIB_DIR="$HERE/lib" \
  REVIEW_RETRO_MACHINE_ID="$(hostname -s 2>/dev/null)" \
  REVIEW_RETRO_PLUGIN_JSON="$HERE/../.claude-plugin/plugin.json" \
  python3 - ${REVIEW_EVENT_LOGS[@]+"${REVIEW_EVENT_LOGS[@]}"} <<'PY' || retro_fatal
import json, os, sys
from datetime import datetime, timedelta, timezone

# 期待 wave 本数の式は `lib/wave_expect.py` が正本（publish / backfill / retro が共有）。
# **集計側は payload の `waves_expected` をそのまま使わず再計算する**（GitHub issue #200）
sys.dont_write_bytecode = True    # mutation-ok: 配布物の `lib/` に `__pycache__` を作らせないだけで、判定にも出力にも効かない
sys.path.insert(0, os.environ["REVIEW_LIB_DIR"])
from wave_expect import MAX_EXPECTED_WAVES, expected_waves
from report_counts import lift_nested_report_counts
from severity_threshold import lift_nested_threshold
from body_bound import body_bound

since_raw = os.environ.get("REVIEW_SINCE") or ""
last_n = int(os.environ.get("REVIEW_LAST") or 0)
as_json = os.environ.get("REVIEW_JSON") == "1"
#: `--logs` で明示指定されたか（0 なら今いるリポジトリ由来の自動探索 / GitHub issue #173）
logs_explicit = os.environ.get("REVIEW_LOGS_EXPLICIT") == "1"

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
#: 報告件数を入れ子から昇格して母集団へ戻した件数（#238）。publish 側で昇格済みの回は
#: トップレベルに 4 キーがあるので数えない — ここに乗るのは旧版で焼かれた行だけ
nested_recovered = 0
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
        # **publish が昇格を知らない版で焼かれた入れ子も読み側で回収する**（GitHub issue #238）。
        # gist は append-only の生イベント保管庫なので過去行は書き換えられない — 読む側で
        # 同じ正規化を掛ければ、既に載っている入れ子形が母集団へ戻る。dedup キーは正規化前の
        # payload で作ってある（上）ので、同じ生行は同じキーに畳まれる
        if lift_nested_report_counts(ev.get("payload") or {}) is not None:
            nested_recovered += 1
        # `severity_threshold` の入れ子も同じ（GitHub issue #252）。歩留まり・検出内訳の層別キーで、
        # 落ちた回は主層から `threshold=?` へ理由なしに外れていた。件数は窓で絞った後に数える
        threshold_lifted = lift_nested_threshold(ev.get("payload") or {}) is not None
        try:
            when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except ValueError:
            when = None
        events.append({"ts": ts, "when": when, "plugin": ev.get("plugin", "?"),
                       "p": ev.get("payload") or {}, "src": path,
                       "threshold_lifted": threshold_lifted})

events.sort(key=lambda e: e["ts"])

# ---- 旧版の transcript 取り違え疑い（GitHub issue #246） --------------------------
# `tokens.session_source` を持たない回は、publish が transcript を「候補 dir の最新 .jsonl」で
# 推定していた。並行セッションや publish 前の `cd` で**別セッションの tokens / models / dispatch を
# gap も立てずに**載せており（publish 元 transcript と照合できた 105 件中 3 件）、値はもっともらしい
# ので層別にそのまま入る。gist は append-only で過去行を直せないので、読み側で外す。
#   ① 同じ `tokens.session` で `since-t0` 系の窓（`first_ts` から publish まで）が重なる 2 回 →
#      推定で引いた側すべて。どちらが正しい側かは payload だけでは決まらない。id で引いた回は
#      相手としてだけ数える。`session` 窓は `first_ts` がセッションの先頭なので、同じセッションで
#      順に回した正常な 2 回でも重なる — 突合に入れない
#   ② explorer / reviewer / specialist / verify を 1 体以上起動したのに、`tokens.sub_agents` が 0
#      （`sub_agents` を持たない回は `models.sub_distinct` が空）
# 既存データ 115 件で ① 2 件・② 2 件を拾い、混入 3 件を全部含む（誤検出は ① の巻き添え 1 件だけ）。
# **窓の絞り込みより前に全件で判定する** — ① の相手が `--since` / 版の窓の外にあっても疑いは同じ
SUSPECT_LAUNCH_KEYS = ("explorer", "reviewer", "specialist", "verify")
#: 同じ transcript の計測から publish が導いた gap。外した値の上に立っているので一緒に外す
#: （残すと、外した `dispatch` から出た `agents-mismatch` が欠測内訳にだけ数えられる）
SUSPECT_DERIVED_GAPS = {"tokens", "tokens-sub", "models", "dispatch", "agents-mismatch",
                        "agents-abandoned", "agents-nested", "wave-split", "fleet-span-mismatch"}
#: 打点を transcript の時刻で補完した回（`derived_markers`）で、境界が補完値になりうる区間。
#: `duration_min`（t0 → t2）と closing（t2 → publish）は補完しない打点だけで決まる
SUSPECT_DERIVED_DURATIONS = ("duration_triage_min", "duration_explore_min",
                             "duration_fleet_min", "duration_synthesis_min")


def _utc(s):
    try:
        w = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return w if w.tzinfo else w.replace(tzinfo=timezone.utc)


def _count(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


_by_session = {}
for _e in events:
    _t = _e["p"].get("tokens")
    if not isinstance(_t, dict):
        continue
    _estimated = _t.get("session_source") is None
    _s, _first = _t.get("session"), _utc(_t.get("first_ts"))
    if (isinstance(_s, str) and _s and _first is not None and _e["when"] is not None
            and _t.get("window") in ("since-t0", "since-t0-late")):
        _by_session.setdefault(_s, []).append((_first, _e, _estimated))
    if not _estimated:
        continue
    _a = _e["p"].get("agents")
    _launched = sum(_count(_a.get(k)) or 0 for k in SUSPECT_LAUNCH_KEYS) if isinstance(_a, dict) else 0
    _m = _e["p"].get("models")
    # `sub_distinct` は `sub_agents` を持たない回の代わりにだけ使う。sub が走った回
    # （`sub_agents` が 1 以上）で世代だけ空なのは model 名を引けなかっただけで、取り違えの証拠ではない
    _sub_n = _count(_t.get("sub_agents"))
    if _launched >= 1 and (_sub_n == 0 if _sub_n is not None
                           else isinstance(_m, dict) and not _m.get("sub_distinct")):
        _e["session_suspect"] = "sub-blank"
for _rows in _by_session.values():
    for _i, (_f1, _e1, _est1) in enumerate(_rows):
        for _f2, _e2, _est2 in _rows[_i + 1:]:
            if _f1 <= _e2["when"] and _f2 <= _e1["when"]:  # mutation-ok: 左辺の等号が効くのは `_f1` と 2 回の publish 時刻がすべて一致するときだけ（`_e2` は時刻順で `_e1` 以降、`_f1` は `_e1` の publish 以前）
                for _e, _est in ((_e1, _est1), (_e2, _est2)):
                    if _est:
                        _e.setdefault("session_suspect", "overlap")
for _e in events:
    if not _e.get("session_suspect"):
        continue
    _p = {k: v for k, v in _e["p"].items() if k not in ("tokens", "models", "dispatch")}
    if isinstance(_p.get("measurement_gaps"), list):
        _p["measurement_gaps"] = [g for g in _p["measurement_gaps"]
                                  if g not in SUSPECT_DERIVED_GAPS]
    if _p.get("derived_markers"):
        for _k in SUSPECT_DERIVED_DURATIONS:
            if _k in _p:
                _p[_k] = -1
    _e["p"] = _p

if since:
    events = [e for e in events if e["when"] and e["when"] >= since]
# `--last` は版の絞り込み（下の「版で絞る」）の後で掛ける。先に掛けると「直近 N 件のうち
# 版を満たすもの」になり、指定した N 件に満たない

def source_rows(rows):
    """**集計に実際に入った件数**をログごとに返す（0 件のログも母集団の一部として残す）."""
    counted = {path: 0 for path in source_paths}
    for e in rows:
        counted[e["src"]] = counted.get(e["src"], 0) + 1
    return [{"path": path, "n": counted[path]} for path in source_paths]


def sources_line():
    extra = "（同一ファイルの重複指定 %d 本を除外）" % dup_paths if dup_paths else ""
    return ("**母集団**: ログ %d 本%s / 重複イベント除外 %d 件%s"
            % (len(source_paths), extra, dup_dropped,
               "" if logs_explicit else "（**このリポジトリのログのみ**）"))


# **読んだものだけを書くと「これが全部」と読まれる**（GitHub issue #173）。自動探索は
# 今いるリポジトリ由来の 2 候補しか見ないので、他リポジトリのレビューは**構造的に母集団へ
# 入らない**。実測ではプラグインを開発しているリポジトリが最も母数を持たず、素の実行が
# n=2 になって出力が「サンプル待ち」で埋まり、**判定可能なデータがあるのに 2 セッション
# 判断が先送りされた**（`--logs` で合算すると n=99 だった）。
#
# **探索は既定にしない**（#160 で「探索範囲が暗黙になる」として `--all-repos` を見送った
# 判断を維持）。消すのは誤読だけなので、**事実を 1 行足す**。
#
# 閾値は置かない — 「n が小さいときだけ」にすると閾値の下で黙る区間ができ、そこが
# まさに誤読の起きる帯になる。自動探索なら常に出す（`--logs` 指定時は利用者が範囲を
# 決めているので出さない）。
def scope_note():
    if logs_explicit:
        return None
    return ("> **母集団はこのリポジトリのログに限られている。** 他リポジトリのレビューは"
            "含まれていない（`.claude/events.jsonl` はリポジトリごとに分かれる）。"
            "**「サンプル待ち」と出ていても、他リポジトリを合算すれば判定できることがある** — "
            "`review-retro.sh --logs <path>...` で明示合算する。\n"
            ">\n"
            "> 合算するログの一覧を作る:\n"
            "> ```bash\n"
            "> find ~ -maxdepth 6 -name events.jsonl -path '*/.claude/*' -not -path '*/node_modules/*' 2>/dev/null\n"
            "> ```")


# ---- 計測の出所（v2.120.0）----------------------------------------------------
# **引用された数字の食い違いを出所で切り分けるため**、集計した retro の版・マシンと、母集団の
# マシン × plugin 版の内訳を必ず出す。実測で同じ issue への再集計が判定成立 51 件 / 42 件に
# 割れ、どのマシン・どの版で測ったかをコメントから復元できなかった（#220）。
# 古いイベントは `machine_id` / `plugin_version` を持たないので `None`（未記録）に置く —
# ログのファイル名や日付から推測して埋めない
def _read_version(path):
    try:
        with open(path, encoding="utf-8") as f:
            v = json.load(f).get("version")
    except (OSError, ValueError, AttributeError):
        return None
    return v if isinstance(v, str) and v else None


retro_version = _read_version(os.environ.get("REVIEW_RETRO_PLUGIN_JSON") or "")
retro_machine = (os.environ.get("REVIEW_RETRO_MACHINE_ID") or "").strip() or None


def _str_or_none(v):
    return v if isinstance(v, str) and v else None


def _version_tuple(v):
    """版を数値の組にする（文字列比較だと 2.9.0 が 2.10.0 より上に来る）。3 桁に揃える."""
    t = tuple(int(x) if x.isdigit() else 0 for x in v.split("."))
    return t + (0,) * (3 - len(t))


def _version_key(v):
    """新しい版を先に並べる（未記録は末尾）."""
    if v is None:
        return (1, ())
    return (0, tuple(-x for x in _version_tuple(v)))


def machine_rows(rows):
    """母集団をマシン × plugin 版で数える（未記録のマシンは末尾）."""
    by = {}
    for e in rows:
        vers = by.setdefault(_str_or_none(e["p"].get("machine_id")), {})
        ver = _str_or_none(e["p"].get("plugin_version"))
        vers[ver] = vers.get(ver, 0) + 1
    out = [{"machine_id": mid, "n": sum(vers.values()),
            "plugin_versions": [{"version": v, "n": vers[v]}
                                for v in sorted(vers, key=_version_key)]}
           for mid, vers in by.items()]
    out.sort(key=lambda r: (r["machine_id"] is None, -r["n"], r["machine_id"] or ""))
    return out


def filters_of():
    """母集団の絞り込み条件（引用した数字の範囲を後から言えるように出所と一緒に出す）."""
    return {"since": since_raw if since else None, "last": last_n or None,
            "min_plugin_version": min_pv_raw or None,
            "dropped_unversioned": dropped_unversioned, "dropped_older": dropped_older}


def provenance_of(rows):
    return {"retro_version": retro_version, "retro_machine_id": retro_machine,
            "machines": machine_rows(rows), "filters": filters_of()}


def provenance_lines(rows):
    head = ("**集計**: review-retro %s @ %s"
            % ("v" + retro_version if retro_version else "版不明",
               "`%s`" % retro_machine if retro_machine else "マシン不明"))
    parts = []
    for r in machine_rows(rows):
        vers = " / ".join("%s %d" % ("v" + x["version"] if x["version"] else "版未記録", x["n"])
                          for x in r["plugin_versions"])
        parts.append("`%s` %d 件（%s）" % (r["machine_id"] or "未記録", r["n"], vers))
    narrowed = []
    if since:
        narrowed.append("--since %s" % since_raw)
    if min_pv_raw:
        narrowed.append("plugin_version %s 以上（版なし %d 件・それより古い %d 件を除外）"
                        % (min_pv_raw, dropped_unversioned, dropped_older))
    if last_n:
        narrowed.append("--last %d" % last_n)
    if narrowed:
        head += " / 絞り込み: " + " / ".join(narrowed)
    return [head,"**マシン / 版**: %s" % (" / ".join(parts) if parts else "なし（0 件）")]


# ---- 版で絞る（v2.121.0 / GitHub issue #210）----------------------------------
# **日付や直近 N 件ではなく版で切る**（冒頭「層別の原則」— 配布ラグで未更新マシンが旧仕様の
# まま publish し続けるので、日付で切ると旧版の回が混ざる）。打ち手を入れた版以降だけで
# 回復を読むための窓で、累計には打ち手より前の回が残り続ける。版を持たない回は推測で入れない
min_pv_raw = os.environ.get("REVIEW_MIN_PLUGIN_VERSION") or ""
dropped_unversioned = dropped_older = 0
if min_pv_raw:
    _min_pv = _version_tuple(min_pv_raw)
    _kept = []
    for e in events:
        _v = _str_or_none(e["p"].get("plugin_version"))
        if _v is None:
            dropped_unversioned += 1
        elif _version_tuple(_v) < _min_pv:
            dropped_older += 1
        else:
            _kept.append(e)
    events = _kept
if last_n:
    events = events[-last_n:]


if not events:
    if as_json:
        print(json.dumps({"n": 0, "reason": "no-samples-in-range", "signals": [],
                          "provenance": provenance_of(events),
                          "sources": source_rows(events),
                          "sources_dropped_duplicates": dup_dropped,
                          "sources_dropped_paths": dup_paths,
                          "sources_scope": "explicit" if logs_explicit else "this-repo"},
                         ensure_ascii=False))
    else:
        print("## レビュー振り返り")
        print("対象サンプルが 0 件。")
        print()
        for _line in provenance_lines(events):
            print("- " + _line)
        print()
        print(sources_line())
        for row in source_rows(events):
            print("- `%s` … %d 件" % (row["path"], row["n"]))
        note = scope_note()
        if note:
            print()
            print(note)
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


REPORT_KEYS = ("blocker_count", "critical_count", "major_count", "minor_count")


def reported_missing(p):
    """報告件数を**1 つも申告していない回**か（GitHub issue #212）。

    欠測を 0 として足すと「検出したのに 1 件も報告しなかった」に化ける。#203 が
    `pre_adjust_counts` の語彙違反について同じ理由で母集団から外したのと同型で、
    そちらのコメントが失敗の形をそのまま書いている（実数が 0 として分子に入り
    歩留まりを下振れさせる）。**縮退先は欠測であって誤値ではない**（`## 13.1`）。
    """
    return all(p.get(k) is None for k in REPORT_KEYS)


def _fleet_span_judgeable(p):
    """fleet 区間と agent 起動スパンの突合ができる回か（GitHub issue #207）.

    **publish が欠測に倒した回も分母に残す** — 倒した回を外すと分子だけが消えて
    欠測率が恒久的にゼロになる（判定した結果が分母から抜ける自己参照）。
    """
    tok, disp = p.get("tokens"), p.get("dispatch")
    if not isinstance(tok, dict) or not isinstance(disp, dict):
        return False
    # 窓が `since-t0` の回だけ。`session` は起点に下限が無く、`since-t0-late` は
    # 締めのあとに起動した agent が窓へ入るので、スパンが区間を超えるのが正常
    if tok.get("window") != "since-t0":
        return False
    span = disp.get("span_sec")
    if not isinstance(span, int) or isinstance(span, bool) or span <= 0:
        return False
    f = p.get("duration_fleet_min")
    if isinstance(f, int) and not isinstance(f, bool) and f >= 0:
        return True
    g = p.get("measurement_gaps")
    return isinstance(g, list) and "fleet-span-mismatch" in g


def _fleet_span_conflict(p):
    """**既に publish 済みの回にも効かせる**（#199 と同じ理由）.

    publish 側のガードはこれから publish する回にしか掛からないが、汚染された値は
    もう集計に入っている。倒し済みの回は `measured` が外すのでここでは扱わない。
    """
    if not _fleet_span_judgeable(p):
        return False
    f = p.get("duration_fleet_min")
    if not (isinstance(f, int) and not isinstance(f, bool) and f >= 0):
        return False
    return p["dispatch"]["span_sec"] >= (f + 1) * 60


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


def agents_dict(p):
    """`payload.agents` を dict として読む（非 dict・欠測は空 dict / GitHub issue #200）.

    retro は `--logs` で他マシン・他リポジトリ由来の異形ログも読むので、`agents` が dict
    である保証は無い。欠測だけを空 dict に倒す書き方（フォールバック演算子で `{}` を挟む形）
    では、`agents` が truthy な非 dict（list / 非空文字列 / 正の int）のとき `.get()` が
    AttributeError になり、**retro が出力 0 行・終了コード 0 で沈黙死する**
    （末尾の無条件 `exit 0` が例外を握る）。**型で判定すること。**

    **この docstring に演算子や真偽リテラルを地の文で書かないこと**（CLAUDE.md Gotchas）。
    `.sh` 内の python ヒアドキュメントは `#` で始まらないので変異ツールの除外に掛からず、
    説明文中の字面がそのまま書き換えられて**必ず生存し CI（`--strict`）を落とす**。
    行内コードに入れても効かない — 除外はコメント判定であって markdown 記法の解釈ではない。
    """
    a = p.get("agents")
    return a if isinstance(a, dict) else {}


def total_agents(p):
    """fleet の実体数。`agents` に数えない層（meta / skeptic / Markdown 推敲）も起動していれば足す。"""
    a = p.get("agents")
    if not isinstance(a, dict):
        return None
    vals = [num(a.get(k)) for k in ("explorer", "reviewer", "specialist", "round2", "verify")]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    extra = 0
    for field in ("meta_reviewer", "recall_skeptic", "md_polish"):
        d = p.get(field)
        if isinstance(d, dict) and d.get("fired") is True:
            extra += 1
    return sum(vals) + extra


#: 一括発行違反の型ラベル（**推定** / GitHub issue #200 の内訳）。是正先が型で違う。
WAVE_SPLIT_KINDS = {
    "explorer": "explorer を 1 体ずつ発行",
    "layer": "同一層の wave 分割",
    "unknown": "型不明（`wave_sizes` が無い）",
    # 申告が壊れているので型は推定しない（#220）
    "over-max": "`agents-mismatch` の回で全層起動の上限を超過",
}


def wave_split_kind(p, sizes):
    """違反 1 件の型を**推定**する（GitHub issue #200）.

    検知は #172 / #192 で整ったが、**違反を減らす打ち手**は型ごとに違う（explorer を
    1 体ずつ出したのか、同一層の wave が割れたのか）。層の割り当ては payload に無いので
    （publish は「層の同定はしない」を維持している）、`wave_sizes` の形と申告体数からの
    **推定**にとどめ、出力でもそう名乗る。
    """
    if not isinstance(sizes, list) or len(sizes) == 0:
        return "unknown"
    # **`agents` を dict と決めつけない**（`agents_dict` で正規化 / GitHub issue #200）
    if sizes[0] == 1 and (num(agents_dict(p).get("explorer")) or 0) >= 2:
        return "explorer"
    return "layer"


#: `pre_adjust_counts` の契約語彙（`orchestration-measurement.md ## 16` の payload テンプレート）
PRE_SEVS = ("blocker", "critical", "major", "minor")


def pre_vocab_ok(pre):
    """`pre_adjust_counts` が契約どおりの語彙か（GitHub issue #203）.

    契約外のキー（実データに `{threshold, pre_major, pre_minor}` の例がある）で来た回は、
    `pre.get("major")` が `None` になるので**実数が 0 として計上される**。`schema` は publish が
    無条件に注入するため、下流からは「旧版で publish された回」と区別が付かない。
    **0 件と語彙違反を潰さないよう、集計の母集団から外して件数を出す。**

    publish は v2.104.0 以降 `payload:pre_adjust_counts.vocab` を立てるが、それ以前に焼かれた
    回にも効かせるため**構造で判定する**（`tokens-sub` と同じ流儀）。
    """
    return isinstance(pre, dict) and all(num(pre.get(k)) is not None for k in PRE_SEVS)


def wave_split_kinds_txt():
    """違反の型ごとの件数を並べる（多い順）。0 件なら「該当なし」."""
    if not wave_split_kinds:
        return "該当なし"
    return " / ".join("%s %d 件" % (WAVE_SPLIT_KINDS.get(k, k), v)
                      for k, v in sorted(wave_split_kinds.items(), key=lambda kv: -kv[1]))


def pct(part, whole):
    return (100.0 * part / whole) if whole else 0.0


# 「設計上そもそも起動しない」スキップ理由。**価値率とゲート判定の分母から外す**。
# これを分母に入れると、既定 effort で回しただけのサンプルが「起動していない」として
# 積み上がり、ゲートの実装バグと運用上の非該当を区別できなくなる
# `no-md-prose` / `embed` / `not-installed` は Markdown 推敲（`md_polish`）だけの値（#243）。
# md の変更がある回にだけ意味を持つ層なので、対象が無い回も分母に入れない
OUT_OF_SCOPE_SKIPS = {"effort", "config", "emergency", "scope",
                      "no-md-prose", "embed", "not-installed"}

report, signals = [], []

# ---- 1. サンプル数 ---------------------------------------------------------
by_plugin = {}
for e in events:
    by_plugin[e["plugin"]] = by_plugin.get(e["plugin"], 0) + 1
report.append(("サンプル", "全 %d 件（直近 30 日 %d 件） / %s"
               % (len(events), len(recent),
                  " ".join("%s=%d" % kv for kv in sorted(by_plugin.items())))))

# ---- モデル世代の層別キー（GitHub issue #169） ------------------------------
# `effort` / `size_tier` の層別は、Opus 5 と 4.8 が混ざった
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
# **`unrecorded` / `mixed` も分割の根拠に数える**（セルフレビューで一度外して差し戻した / v2.88.2）。
# 外すと「世代不明の回」と「既知世代の回」が同じバケツに入り、**#169 が防ごうとした当の
# プーリング**が起きる（`test_unrecorded_generation_is_not_folded_into_a_known_one` ほか 2 件が
# 表明している不変条件）。**既知の副作用**: `unrecorded` は retro が全履歴を読む限り消えないので、
# `models` 付きの 1 件目が publish された時点で既存バケツが `/unrecorded` 側に分かれ、
# 新しい観測は当面 n=1 で溜まる。これは可読性の劣化であって誤りではない — 世代不明の
# 母数を既知世代の中央値に混ぜないことの対価として受け入れる


#: 層別キー → その層の世代（`GEN_SPLIT` のときだけ埋まる）。表示上限で世代を丸ごと
#: 落とさないための逆引き（GitHub issue #198）。**キーを `/` で割り戻して世代を取らない** —
#: `effort` / `size_tier` は payload 由来の自由文で `/` を含みうる
LAYER_GEN = {}

#: 層別表の表示上限（可読性のための上限で、母集団の定義ではない）。**超えたら省略行を出す**
#: — 「どのログから何件採ったか」を必ず出す本スクリプトの流儀（冒頭）に、この 2 表だけが
#: 従っていなかった（#198）。裸で切ると落ちるのは必ず n の小さい層 ＝ 新しい世代になる
LAYER_ROWS_MAX = 8


def with_gen(p, key):
    """世代が 2 種以上ある母集団でだけ層別キーへ世代を足す。"""
    if not GEN_SPLIT:
        return key
    full = key + "/" + gen_of(p)
    LAYER_GEN[full] = gen_of(p)
    return full


def cap_layer_rows(rows):
    """層別表を上限で切る。**世代ごとに最低 1 行は残す**（GitHub issue #198）。

    `rows` は `(key, n, ...)` の n 降順。返り値は `(表示する行, 省略した層数, 省略した件数)`。

    世代キーを層別に足すと層数がほぼ倍になり（#191）、裸の上限では**新しい世代が丸ごと
    表から消える**（実測: n=108 で opus-5 が 2 表とも 0 行）。世代比較のための層別が世代の
    観測を消しては本末転倒なので、上限を超えても各世代の最大の層 1 つは救う。
    """
    shown = list(rows[:LAYER_ROWS_MAX])
    if GEN_SPLIT:
        seen = {LAYER_GEN.get(r[0]) for r in shown}
        for r in rows[LAYER_ROWS_MAX:]:
            g = LAYER_GEN.get(r[0])
            if g not in seen:
                seen.add(g)
                shown.append(r)
    keys = {r[0] for r in shown}
    dropped = [r for r in rows if r[0] not in keys]
    shown.sort(key=lambda r: -r[1])
    return shown, len(dropped), sum(r[1] for r in dropped)


def layer_omission_note(dropped_layers, dropped_n):
    """省略行。**0 件のときは何も出さない**（常時出ると読み飛ばされる）。"""
    if not dropped_layers:
        return None
    return ("_他 %d 層（計 %d 件）を省略（表示は n の多い順 上限 %d 層%s）_"
            % (dropped_layers, dropped_n, LAYER_ROWS_MAX,
               " + 世代ごとの最低 1 行" if GEN_SPLIT else ""))


# ---- 2. effort × size_tier 別の fleet 時間・体数 ---------------------------
buckets = {}
for e in events:
    p = e["p"]
    fleet = num(p.get("duration_fleet_min"))
    if fleet is None or fleet < 0 or _fleet_span_conflict(p):
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
    if fleet is not None and fleet >= 0 and ta is not None and not _fleet_span_conflict(p):
        xs.append(ta)
        ys.append(fleet)
        # **層別キーを tier 中央値表と揃える**（GitHub issue #217）。相関だけ `size_tier`
        # 単独で、上の表は `with_gen` という食い違いがあり、同じ ⚠️ の中で粒度が混ざっていた。
        # 世代を足しても small/opus-4-8 は 0.687 のままで交絡ではない（#217 で確認済み）が、
        # **どの層で見ているかは読み手に見えていなければならない**
        tx, ty = tier_xy.setdefault(with_gen(p, str(p.get("size_tier", "?"))), ([], []))
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

# ---- 4b. synthesis の支配率（GitHub issue #218） ------------------------------
# `## 14` は `duration_synthesis_min` の用途を**打ち手の切り分け**として書いている（支配的なら
# メイン側 / そうでなければ wave 側）のに、retro は区間の中央値 1 行しか出していなかった。
# 中央値 5% の分布で 43% の回（PR #469 / fleet 92 分中 40 分）が起きても、目に入るのは
# fleet と体数だけで、triage-guide `## 7` が禁じる「時間が長いから体数を減らす」に誘導される。
# 判断基準が doc にあって機械層に無い形は #209 / #214 と同型。
#
# 閾値は**実データから決めた**（CLAUDE.md「水準を先に測ってから入れる」/ gist + ローカル合算
# n=71・2026-09-06）: 中央値 5% / 75% 点 15% / 90% 点 35% / 最大 59%。`SYN_DOMINANT_PCT` 30 は
# 90% 点付近で、超えたのは 9 件（13%）。⚠️ の水準 `SYN_RATE_HOT` 10 は初回から鳴るが、
# これは #218 が「外れ値の領域」と呼んだ回そのものなので偽陽性ではない
SYN_DOMINANT_PCT = 30   # 1 回の syn ÷ fleet がこれ以上なら「支配的」
SYN_RATE_HOT = 10       # 支配的な回の割合がこれ以上で ⚠️
SYN_MIN_N = 10          # 層 / 累計の分母の下限（他のシグナルの 8〜15 に揃える）
SYN_TOP = 5             # 本文に列挙する支配的な回の上限
syn_stats = {"n": 0, "dominant": 0, "by_gen": {}}
syn_ratios = []                 # (支配率 %, ts, plugin, tier, 世代, syn, fleet)
syn_inconsistent = 0            # syn が fleet を超えた回（打点の矛盾。内数の契約に反する）
for e in events:
    p = e["p"]
    syn, fleet = num(p.get("duration_synthesis_min")), num(p.get("duration_fleet_min"))
    # **両区間を実測で持つ回だけ**（-1 は欠測 / fleet 0 は割れない / `fleet-span-mismatch` の
    # 回は publish が fleet を -1 に倒しているのでここで落ちる）
    if syn is None or fleet is None or syn < 0 or fleet <= 0:
        continue
    if syn > fleet:
        syn_inconsistent += 1
        continue
    ratio = pct(syn, fleet)
    syn_ratios.append((ratio, e["ts"], e["plugin"], p.get("size_tier") or "?", gen_of(p), syn, fleet))
    _g = syn_stats["by_gen"].setdefault(gen_of(p), {"n": 0, "dominant": 0})
    _g["n"] += 1
    syn_stats["n"] += 1
    if ratio >= SYN_DOMINANT_PCT:
        _g["dominant"] += 1
        syn_stats["dominant"] += 1


def quantile(xs, q):
    """最近傍順位法の分位点（n が小さいので補間しない）。"""
    if not xs:
        return None
    s = sorted(xs)
    return s[int(round(q * (len(s) - 1)))]


syn_pcts = [r[0] for r in syn_ratios]

# ---- 5. pre_adjust → 報告の歩留まり（版マーカー × 閾値 × 世代で層別）--------
# `>= 2` にするのは前方互換のため（`== 2` だと schema 3 でセクションが無音で消える）
#
# **世代キーを入れる**（GitHub issue #191）。#169 は世代を**コスト側だけ**に入れたため、
# 検出・報告側は世代をまたいで累計されていた。実測では踏み下げの前後で `pre_adjust` の
# MAJOR 中央値が 7 → 0・報告 0 件率が 42% → 91% に動いており、累計するとこれが平均に
# 埋もれる。**「安くなった」だけが見えて「効かなくなった」が見えない**非対称になる
yields = {}
yields_bad_vocab = 0
yields_missing_post = 0   # 報告件数を 1 つも申告していない回（#212）    # 語彙違反で外した回（#203）
#: 歩留まりの母集団のうち、入れ子から回収した回と、回収しても無く `threshold=?` 層に入った回（#252）。
#: **同じ母集団で数える**（回収の方だけ全件で数えると、どの表にも入らない回まで「回収」に数え、
#: 表の動きと件数が合わない）。検出内訳は歩留まりの部分集合（`below_threshold_counts` を持つ回）
threshold_missing = 0
threshold_recovered = 0
for e in events:
    p = e["p"]
    pre = p.get("pre_adjust_counts")
    if not isinstance(pre, dict) or schema_of(pre, "schema") < 2:
        continue
    # **語彙違反は母集団から外す**（#203）。混ぜると実数が 0 として分子に入り、歩留まりを
    # 下振れさせる（実測: `pre_major: 11` の回が `検出 0 → 報告 0` として計上されていた）
    if not pre_vocab_ok(pre):
        yields_bad_vocab += 1
        continue
    # **報告側の欠測も同じ理由で外す**（#212）。`if v:` は `None` を飛ばすので、
    # 4 つとも欠測の回は `post` に 0 を足しつつ `pre` は加算され、**検出したのに
    # 全部捨てた回**として歩留まりを押し下げる（実測 3/43 件。うち 1 件は
    # critical 2 / major 13 を検出していた）
    if reported_missing(p):
        yields_missing_post += 1
        continue
    if not p.get("severity_threshold"):
        threshold_missing += 1
    elif e["threshold_lifted"]:
        threshold_recovered += 1
    key = with_gen(p, "schema>=%d/threshold=%s" % (
        schema_of(pre, "schema"), p.get("severity_threshold") or "?"))
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
splits_bad_vocab = 0    # 語彙違反で外した回（#203）
splits_missing_post = 0  # 報告件数を 1 つも申告していない回（#213 / #212 と同型の 3 箇所目）
for e in events:
    p = e["p"]
    pre = p.get("pre_adjust_counts")
    bt = p.get("below_threshold_counts")
    if not isinstance(pre, dict) or schema_of(pre, "schema") < 2 or not isinstance(bt, dict):
        continue
    # 語彙違反は歩留まりと同じく外す（#203）。ここは `pre − below` を引くので、混ぜると
    # **`本文を書いた` が負に振れる**（実測 -10）。負値は「手順 1 の後に走る層が足したぶん」
    # という別経路の指標なので、語彙違反を混ぜるとその読みごと壊れる
    if not pre_vocab_ok(pre):
        splits_bad_vocab += 1
        continue
    # **報告側の欠測も外す**（#213）。`or 0` で `post` が 0 に化けると `written − post` が
    # 全部 `dropped` に計上され、「申告していない」回が「本文を書いてから捨てた 100%」に
    # なる（実測: mixed 世代の 1 行がこのアーティファクトだけで構成されていた）。
    # 歩留まりが #212 で同じ回を外しているので、**隣り合う 2 表の同一層の n もここで揃う**
    if reported_missing(p):
        splits_missing_post += 1
        continue
    # **歩留まり（yields）と同じ粒度にする**。片方だけ割ると、隣り合う 2 表のどの行を
    # 分解した数字なのかが対応付かない（#191 のセルフレビュー指摘）
    key = with_gen(p, "schema>=%d/threshold=%s" % (
        schema_of(pre, "schema"), p.get("severity_threshold") or "?"))
    sp = splits.setdefault(key, {"n": 0, "pre": 0, "below": 0, "post": 0, "judged": 0,
                                 "over": 0, "over_appendix": 0, "over_report": 0, "lower": 0})
    sp["n"] += 1
    _written = 0
    for sev in ("blocker", "critical", "major", "minor"):
        sp["pre"] += num(pre.get(sev)) or 0
        sp["below"] += num(bt.get(sev)) or 0
        _written += (num(pre.get(sev)) or 0) - (num(bt.get(sev)) or 0)
    for sev in ("blocker_count", "critical_count", "major_count", "minor_count"):
        sp["post"] += num(p.get(sev)) or 0
    # **`本文を書いた` は下限でしかない**（GitHub issue #248）。付録と報告件数が `pre − below` を
    # 超えた回は、閾値未満に数えた指摘にも本文が書かれていた（契約 (a) の違反）。値は変えずに、
    # 付録と報告から見た下限 Σmax(pre − below, 付録 + 報告) を並べる。違反した回を
    # 母集団から外すと opus-4-8 では大半が消えるので外さない。式の根拠は `lib/body_bound.py`
    _b = body_bound(p)
    if _b is None:
        sp["lower"] += _written
    else:
        sp["judged"] += 1
        sp["over"] += 1 if (_b["appendix_over"] or _b["report_over"]) else 0
        sp["over_appendix"] += 1 if _b["appendix_over"] else 0
        sp["over_report"] += 1 if _b["report_over"] else 0
        sp["lower"] += max(_b["written"], _b["listed"] + _b["reported"])


# ---- 5.15 報告 0 件率（世代別 / GitHub issue #191）-------------------------
# **recall の最も粗い代理指標**。踏み下げの前後で 42% → 91% に動いた実測があり、
# 累計では見えない。
#
# **母数は「報告件数フィールドを実際に持つ回」に限る。** `pre_adjust_counts` の版マーカー
# だけで濾すと、`*_count` を 1 つも持たない旧版の回が `sum(... or 0)` で 0 と評価され、
# **欠測が「報告 0 件」に化ける**。このリポジトリの実データではそれで陽性セルの
# 3/3 が偽陽性になっていた（0 件率が構造的に上振れし、しかも古い版ほど欠測が多いので
# 「新しい世代ほど recall が落ちた」を機構が自分で作り出す）。
# **除外件数は表に出す** — 黙って落とすと「該当が無かった」と読まれる
zero_rows = {}
zero_missing = 0        # 報告件数フィールドを 1 つも持たず母数から外した回
zero_missing_current = 0  # うち現行版の埋め落とし（publish が gap を立てた回 / #215）
for e in events:
    p = e["p"]
    pre = p.get("pre_adjust_counts")
    if not isinstance(pre, dict) or schema_of(pre, "schema") < 2:
        continue
    counts = [num(p.get(k)) for k in
              ("blocker_count", "critical_count", "major_count", "minor_count")]
    # **`setdefault` より前に弾く**。後ろに置くと除外された回でも空バケツができ、
    # n=0 の行が表に並ぶ（比率は 0/0）
    if all(v is None for v in counts):
        zero_missing += 1
        # **旧版と現行版の埋め落としを分ける**（#215）。publish が gap を立てるようになった
        # 版以降の回は「テンプレートを埋め落とした」＝ サンプルの損失で、増えるなら
        # SKILL 側を直す根拠になる。旧版（gap を持たない）は identification であって損失ではない
        if "payload:report_counts.missing" in (p.get("measurement_gaps") or []):
            zero_missing_current += 1
        continue
    g = gen_of(p)
    z = zero_rows.setdefault(g, {"n": 0, "zero": 0, "pre_major": []})
    z["n"] += 1
    if sum(v or 0 for v in counts) == 0:
        z["zero"] += 1
    pm = num(pre.get("major"))
    if pm is not None:
        z["pre_major"].append(pm)

# ---- 5.2 「報告 0 件」と「価値 0」の分離（GitHub issue #168） ---------------
# 報告 0 件の回は**空振りとは限らない**。閾値の外に落ちた指摘を付録で人間に推している回が
# あり、集計側がそれを 0 と読むと**費用対効果の分子が構造的に欠ける**（実測: severity 4 バケツ
# すべて 0 なのに付録 18 件・うち 4 件を人間に推していた回。1 件はテストの穴が実証済み）。
#
# **`appendix` を持つ回だけを母数にする**（旧版を混ぜると「推奨なし」が水増しされる）。
# 版マーカーで切る流儀は `## 9` の cache_read と同じ。
APPENDIX_MIN_SCHEMA = 1
apx_rows, apx_silent, apx_rescued, apx_missing = [], 0, 0, 0
# **真の空振りを「検出 0」と「検出はあったが全部閾値未満」に割る**（GitHub issue #210）。
# 打ち手が違う: 前者は recall（reviewer が何も見つけていない）、後者は閾値・付録の方針
# （見つけているが `## below-threshold` に件数だけ返るので、報告にも付録にも出ない —
# 付録の対象は「reviewer が列挙した指摘」だけという契約 / scoring-guide）。
# 実測（opus-4-8 / n=21）では真の空振り 9 件のうち**検出 0 は 2 件だけ**で、残り 7 件は
# MINOR を 2〜6 件見つけていた。混ぜたままだと #210 の回復サイン「20% 未満」が
# **どちらの改善を求めているのか決まらない**
apx_stats = {"n": 0, "true_silent": 0, "true_silent_empty": 0, "true_silent_below": 0,
             "true_silent_below_listed": 0, "true_silent_below_over": 0,
             "true_silent_unknown": 0,
             "rescued_judged": 0, "rescued_uncontracted": 0,
             "by_gen": {}}   # 世代別の真の空振り（#214 / #210）
for e in events:
    p = e["p"]
    a = p.get("appendix")
    if not isinstance(a, dict) or schema_of(a, "schema") < APPENDIX_MIN_SCHEMA:
        continue
    listed, rec = num(a.get("listed")), num(a.get("recommended"))
    if listed is None or listed < 0 or rec is None or rec < 0:
        continue
    # **報告件数の欠測を「報告 0」と読まない**（#212）。`or 0` で化けた回が
    # `apx_silent`（＝真の空振りの分子）に入る。#210 はこの数字の上に打ち手を求めている
    if reported_missing(p):
        apx_missing += 1
        continue
    reported = sum(num(p.get(k)) or 0 for k in REPORT_KEYS)
    apx_rows.append((listed, rec, reported))
    # **世代で層別する**（GitHub issue #214）。#210 の判定基準「真の空振り率 20% 未満」の
    # 片方だけが機械化されていなかった。`報告 0 件率（世代別）` と同じ母数の扱い
    # （欠測は上で外し、`appendix` を持つ回だけ）。**真の空振り = 報告 0 かつ推奨 0**（#168）
    _g = apx_stats["by_gen"].setdefault(gen_of(p), {"n": 0, "silent": 0, "rescued": 0,
                                                    "rescued_judged": 0,
                                                    "rescued_uncontracted": 0,
                                                    "true_silent": 0, "true_silent_empty": 0,
                                                    "true_silent_below": 0,
                                                    "true_silent_below_listed": 0,
                                                    "true_silent_below_over": 0,
                                                    "true_silent_unknown": 0})
    _g["n"] += 1
    apx_stats["n"] += 1
    if reported == 0:
        apx_silent += 1
        _g["silent"] += 1
        if rec > 0:
            apx_rescued += 1
            _g["rescued"] += 1
            # **契約外の行に救われた回を分ける**（GitHub issue #248）。上限が 0 の回は、契約 (a)
            # どおりなら付録に 1 行も載らない ＝ 推奨は閾値未満に数えた指摘の本文から来ている。
            # 真の空振り率はこの混入が増えるか減るかだけでも動く（opus-4-8 で 33% から最大 60%）
            _b = body_bound(p)
            if _b is not None:
                for _d in (_g, apx_stats):
                    _d["rescued_judged"] += 1
                    _d["rescued_uncontracted"] += 1 if _b["appendix_cap"] == 0 else 0
        else:
            _g["true_silent"] += 1
            apx_stats["true_silent"] += 1
            # **検出の有無で割る**（#210）。`pre_adjust_counts` を持たない回・語彙違反の回は
            # どちらとも言えないので `unknown` に置く（0 に丸めると「検出が無かった」に化ける）
            _pre = p.get("pre_adjust_counts")
            if (isinstance(_pre, dict) and schema_of(_pre, "schema") >= 2
                    and pre_vocab_ok(_pre)):
                _kind = ("true_silent_below"
                         if sum(num(_pre.get(_k)) or 0 for _k in PRE_SEVS) > 0
                         else "true_silent_empty")
            else:
                _kind = "true_silent_unknown"
            _g[_kind] += 1
            apx_stats[_kind] += 1
            # 「閾値未満のみ」のうち付録には出た回（推奨なし / #248）。処方文の「報告にも付録にも
            # 出ていない」はこちらには当たらない。**契約外と言えるのは上限を超えた回だけ** —
            # 上限内の付録行は閾値以上で書かれて報告マトリクスで落ちた指摘で、契約 (a) どおり
            if _kind == "true_silent_below" and listed > 0:
                _b = body_bound(p)
                for _d in (_g, apx_stats):
                    _d["true_silent_below_listed"] += 1
                    _d["true_silent_below_over"] += 1 if (_b and _b["appendix_over"]) else 0

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
    # **世代キーを足す**（#191）。`calibration_schema` × 世代が完全交絡している回が
    # あり（calib=3 が片方の世代に偏る）、層別しないと打ち手の効果と世代の副作用を
    # 分離できない
    calib = schema_of(av, "calibration_schema")
    layer = with_gen(e["p"], str(calib))
    # **`calib` を層に持たせる**。キーが `"3/opus-5"` のような複合文字列になったので、
    # 下流の閾値比較（`>= CALIB_MIN`）を文字列で行うと Python 3 では TypeError になる。
    # キーから数値を切り出し直す実装は `with_gen` の書式に依存するので持たない
    L = verdict_layers.setdefault(layer, {"n": 0, "total": 0, "confirmed": 0, "refuted": 0,
                                          "uncertain": 0, "severity_inflated": 0,
                                          "contested": 0, "calib": calib})
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
    """`{rowkey: {n, total, <type>...}}`。内訳を持たない回は分母にも入れない。
    **`calibration_schema` で層別する**（#150 / v2.90.0）— `miscategorized` の判別条件は版で
    変わる（挙動ゼロの MAJOR に発現経路の立証責任を課したのが層 3）ので、層を跨いで合算すると
    **同じキーの意味の違う値**が混ざり、CHANGELOG が指定する効果測定（`miscategorized` の推移）が
    読めなくなる。`with_gen` と同じく**2 層以上あるときだけ**キーへ足す（1 層しか無い間は
    キーを砕かない）。層マーカーは `adversarial_verify.calibration_schema` で、これは
    「上流較正ガードの版」なので下流（`inflated_axes`）・上流（`demoted_types`）の両テーブルに効く。"""
    contrib = []
    for e in events:
        parent = e["p"].get(field)
        d = parent.get(key) if isinstance(parent, dict) else None
        if isinstance(d, dict):
            # **層のオブジェクトは丸ごと落ちうる** — publish は欠落を `payload:<field>` の
            # gap にして**通す**設計なので、`below_threshold_counts` はあるが
            # `adversarial_verify` が無い payload が正規に作られる。ガード無しで渡すと
            # `None.get` の `AttributeError` が `schema_of` の except（`TypeError` /
            # `ValueError`）をすり抜け、**retro が rc 0 のまま出力ごと消える**（issue #211）。
            # `verdict_layers` 側は同じ値を isinstance で濾しており、ここだけが非対称だった。
            # 空 dict に倒して**層 1（最古の版）として残す** — 行ごと落とすと
            # `demoted_types` の分母が黙って減る
            _av = e["p"].get("adversarial_verify")
            contrib.append((e, d, schema_of(_av if isinstance(_av, dict) else {},
                                            "calibration_schema")))
    calib_split = len({layer for _, _, layer in contrib}) > 1
    rows = {}
    for e, d, layer in contrib:
        rk = with_gen(e["p"], e["plugin"])
        if calib_split:
            rk += "/calib" + str(layer)
        row = rows.setdefault(rk,
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
VERDICT_KEYS = ("confirmed", "refuted", "uncertain", "severity_inflated", "contested")


def verdict_total(d):
    """反証レイヤーの「価値」は verdict が返った件数（findings_added を持たない層）。"""
    return sum(num(d.get(k)) or 0 for k in VERDICT_KEYS)


def major_only_verdicts(p, d):
    """反証の verdict がすべて MAJOR についてのものと言える回なら、その内訳を返す（GitHub issue #249）。

    payload の verdict は severity 別に分かれていない。上流（`pre_adjust_counts`。skeptic / meta の
    指摘も統合済み）に BLOCKER / CRITICAL が 0 件で閾値が MAJOR なら、反証にかかったのは MAJOR だけ
    （MINOR は閾値未満でゲートの外）なので、この回の verdict を MAJOR の verdict として読める。
    上流の件数か閾値が欠けた回は None（MAJOR 以外が混ざっていないと言えない）。
    """
    pre = p.get("pre_adjust_counts")
    if not isinstance(pre, dict) or not pre_vocab_ok(pre) or p.get("severity_threshold") != "MAJOR":
        return None
    if num(pre.get("blocker")) != 0 or num(pre.get("critical")) != 0:
        return None
    return {k: num(d.get(k)) or 0 for k in VERDICT_KEYS}


#: effort 帯の並び（表示順）。`other` は low / medium / 未記録（反証は low / medium を
#: `effort` の設計上非該当で外すので、ここに残るのは主に未記録の回）
EFFORT_BANDS = ("high", "xhigh+", "other")


def effort_band(p):
    e = p.get("effort")
    if e == "high":
        return "high"
    if e in ("xhigh", "max"):
        return "xhigh+"
    return "other"


def layer_stats(field, schema_key, min_schema, value_of=None, major_only_of=None):
    """版マーカーで濾し、設計上非該当のスキップを分母から外して集計する。

    `n_raw` は全サンプル、`n` は判定に使える母集団（層別後 × スコープ内）。
    両方返すのは「まだサンプルが貯まっていない」と「絞った結果 0 件」を区別するため。

    `value_of` は「その回に価値が出たか」を測る関数（既定は `findings_added`）。
    **層ごとに価値の定義が違う**ので固定しない — 反証は指摘を足す層ではないため
    `findings_added` を持たず、既定のままだと価値率が恒常 0% に潰れる。

    `major_only_of` は発火した回の verdict を MAJOR のものとして取り出す関数（反証だけが渡す）。
    返した内訳を effort 帯ごとに `major_only` へ合算する。
    """
    if value_of is None:
        value_of = lambda d: num(d.get("findings_added")) or 0  # noqa: E731
    # **`by_gen` は世代別の内訳**（GitHub issue #191 期待動作 1 の 3 項目目）。
    # コスト側（fleet / 体数 / cache_read）と検出側（歩留まり / 報告 0 件率）は世代で
    # 層別済みだが、**動的層の発火率と skip 理由だけが全世代の累計**のまま残っていた。
    # 踏み下げの崩壊はここに最も鋭く出る — 上流の MAJOR がほぼゼロになると反証は
    # `no-eligible-findings` で不発になり（#191 の実測: calib=3 の 7 件中 6 件）、
    # 累計すると「ゲート幅が広すぎる」という**別の是正先**に見える
    # **`by_effort` は effort 帯別の内訳**（GitHub issue #249）。反証のゲートは effort で定義が
    # 違う（high は BLOCKER 60-94 / CRITICAL 80-94 だけ、xhigh 以上は報告見込みの全 severity）ので、
    # 不発率を 1 つの分母に混ぜると世代差に見えるものが effort の構成差になる
    st = {"n_raw": 0, "n": 0, "fired": 0, "valuable": 0, "by_gen": {}, "by_effort": {},
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
        # 分母は `n` と同じ（スコープ外スキップは上で除外済み）。集計と内訳で母集団を
        # ずらすと、世代別の合計が本体と合わずに読み手が原因を探すことになる
        g = st["by_gen"].setdefault(gen_of(e["p"]),
                                    {"n": 0, "fired": 0, "valuable": 0, "skips": {}})
        g["n"] += 1
        eb = st["by_effort"].setdefault(effort_band(e["p"]), {"n": 0, "fired": 0, "by_gen": {}})
        ebg = eb["by_gen"].setdefault(gen_of(e["p"]), {"n": 0, "fired": 0, "skips": {}})
        eb["n"] += 1
        ebg["n"] += 1
        if d.get("fired") is True:
            st["fired"] += 1
            g["fired"] += 1
            eb["fired"] += 1
            ebg["fired"] += 1
            mo = major_only_of(e["p"], d) if major_only_of else None
            if mo is not None:
                acc = eb.setdefault("major_only", dict.fromkeys(("n",) + VERDICT_KEYS, 0))
                acc["n"] += 1
                for k, v in mo.items():
                    acc[k] += v
            if value_of(d) > 0:
                st["valuable"] += 1
                # **価値率も層別で判定する**（GitHub issue #209）。累計だけだと世代の
                # 違う母集団を平均することになり、崩れている層が薄まって鳴らない
                g["valuable"] += 1
        else:
            key = reason or "unknown"
            st["skips"][key] = st["skips"].get(key, 0) + 1
            g["skips"][key] = g["skips"].get(key, 0) + 1
            ebg["skips"][key] = ebg["skips"].get(key, 0) + 1
    return st


# 保留として出すときの分母の下限。**単発点灯の防止**（`GAP_MIN_N` と同じ流儀 / #209）。
# これが無いと n=1 の層が毎回「閾値を超えている」として並び、「⚠️ が出たときだけ行動する」
# 契約の可読性が落ちる（実測: 既定母集団で n=1 の層が 3 本並んだ）
LAYER_PENDING_MIN_N = 5


def layered_signal(st, numer_of, denom_of, min_n, is_hot, render, pending=None):
    """**世代層ごとに閾値を評価し、超えた層だけを鳴らす**（GitHub issue #209）。

    表は既に世代別に出ているのに判定だけ累計のままだと、母集団の違う層を平均する
    ことになり、崩れている層が薄まって鳴らない（実測: 反証レイヤーの不発が opus-4-8 で
    78% あったのに、累計 43% では閾値の 50 に届かなかった）。

    **閾値を超えた層が 1 つも無ければ累計で評価する。** 分岐を「判定できた層の有無」で
    切ってはならない — 判定できた層が健全なだけのとき、下限に届かない層が崩れていても
    行が 1 本も出なくなる。このリポジトリでは実際に到達する経路で、`unrecorded` 層は
    現行版が必ず世代を記録するため増えず、伸びるのは最新世代だけだから、最新世代が
    下限に達した瞬間に**いま鳴っている行が消えて代わりに何も出ない**。#209 が直そうと
    した「表には出ているが鳴らない」を裏返しで再生産する。

    累計で鳴らすときは**なぜ層別で判定していないか**を必ず添える（黙ると層別が効いて
    いると読まれる）。**分母はシグナルごとに違う**ので注記も同じ関数から取り直す
    （skeptic の分母は起動回数であって母集団ではない）。
    """
    by_gen = st.get("by_gen") or {}
    hot = []
    judged = []
    for key in sorted(by_gen):
        g = by_gen[key]
        d = denom_of(g)
        if d < min_n:
            continue
        judged.append(key)
        if is_hot(numer_of(g), d):
            hot.append(render("`%s` 層" % key, numer_of(g), d, ""))
    if hot:
        return hot
    total = denom_of(st)
    if total < min_n or not is_hot(numer_of(st), total):
        # **どこも鳴らなかったときだけ、下限未満で閾値を超えている層を控える**（#209）。
        # 累計は層を平均するので、判定できる層が健全だと**崩れている少数層が希釈されて
        # 消える**（実測の形: 健全な層 n=10 と崩れた層 n=8 で累計 28% ＝ 閾値 50 に届かない）。
        # ⚠️ には出さない — 下限未満は「行動する根拠がまだ無い」という判断そのもの。
        # 代わりに「計測の健全性」へ保留として出し、**黙って落ちる状態を作らない**
        if pending is not None:
            for key in sorted(by_gen):
                g = by_gen[key]
                d = denom_of(g)
                if LAYER_PENDING_MIN_N <= d < min_n and is_hot(numer_of(g), d):
                    pending.append((key, numer_of(g), d, min_n))
        return []
    if judged:
        note = ("。**累計で判定**（層別では %s が下限に達したが閾値に届かない）"
                % " / ".join("`%s`" % k for k in judged))
    else:
        top = max(((denom_of(g), k) for k, g in by_gen.items()), default=(0, "-"))
        note = ("。**累計で判定**（層別では判定不能 — 最大層 `%s` の分母 %d・下限 %d）"
                % (top[1], top[0], min_n))
    return [render("累計", numer_of(st), total, note)]


# ロールバック条件の層別要件の正本: triage-dynamic-gates.md `## 8`（meta） / `## 8.5`（skeptic）
# / `## 9`（反証）
skeptic = layer_stats("recall_skeptic", "attribution_schema", 2)
meta = layer_stats("meta_reviewer", "gate_schema", 3)
# Markdown 推敲（self-review のみ / #243）。価値は「提案が 1 件以上あった」（`suggested` の -1 は
# 測定不能なので価値に数えない）
md_polish = layer_stats("md_polish", "gate_schema", 1,
                        value_of=lambda d: num(d.get("suggested")) or 0)
# 反証も他 2 層と同じ流儀で絞る（issue #129）。**旧版は `fired` を持たない**ので
# `gate_schema >= 2` で落ちる — 「起動しなかった」ではなく「発火を記録していない版」
adversarial = layer_stats("adversarial_verify", "gate_schema", 2, value_of=verdict_total,
                          major_only_of=major_only_verdicts)
# round2 は専用オブジェクトを持たないので `agents.round2` の**キー存在**を版プロキシにする
# （`agents` を持たない旧サンプルを分母に入れると発火率が構造的に薄まる。#127 と同型）
round2_scope = [e for e in events
                if num(agents_dict(e["p"]).get("round2")) is not None]
round2_fired = sum(1 for e in round2_scope
                   if (num(agents_dict(e["p"]).get("round2")) or 0) > 0)

# ---- 8. 計測の欠測率 -------------------------------------------------------
n_all = len(events)
gap_counts = {}
for e in events:
    gaps = e["p"].get("measurement_gaps")
    if isinstance(gaps, list):
        for g in gaps:
            gap_counts[str(g)] = gap_counts.get(str(g), 0) + 1
# **`wave-split` は「欠測」ではなく行動の逸脱**（#192）なので、欠測内訳の表から外す。
# しかも payload のマーカーは**publish 時点の式**で立っており、集計は現行式で再計算した
# `n_wave_split` を使う（#200）ので、同じ表に並べると 2 つの数が食い違って見える。
# **黙って捨てない** — 生のマーカー件数は `--json` の `wave_split.marker` に残す
n_wave_split_marker = gap_counts.pop("wave-split", 0)
# **`agents-abandoned` / `agents-nested` も「欠測」ではない**（GitHub issue #211 / #154）。
# publish は `agents` の分解で説明が付いた分を別識別子で載せているだけで、打点漏れでも
# 申告の誤りでもない（捨てられた試行と孫 agent。孫はオーケストレーターが申告しようがない）。
# 外す理由は `wave-split` と同じ 2 つ:
#   ① シグナルの文言が「計測マーカー `%s` の**欠測**が」で固定なので呼称が誤りになる
#   ② 判定に載せると上位 2 件枠（下の `[:2]`）を両方占有し、**本物の欠測を締め出す**
#      （実測: 両識別子が 100% で並び、`payload:pre_adjust_counts.vocab` の 30% が消える）
# **黙って捨てない** — 生のマーカー件数は `--json` の `agents_decomposition` に残し、
# 立った回があれば「計測の健全性」に 1 行出す
n_agents_abandoned_marker = gap_counts.pop("agents-abandoned", 0)
n_agents_nested_marker = gap_counts.pop("agents-nested", 0)
# **付録・報告件数の上限超え（#248）も欠測ではなく契約 (a) の違反**なので、同じ理由で外す
# （「欠測が N%」という呼称が誤りになり、既存データの約半数で上位 2 件枠を占有する）。
# 上限超えは「検出 → 報告の内訳」が payload から再計算して層ごとに出す（旧版の回にも効く）。
# 生のマーカー件数は `--json` の `body_bound_marker` に残す
n_exceeds_marker = {"appendix": gap_counts.pop("payload:appendix.exceeds-body", 0),
                    "report": gap_counts.pop("payload:report_counts.exceeds-body", 0)}
# **定型レポートの判定**（#250）。gap は定型なしの回にしか立たないので、率は payload の
# `report_template`（present / absent。判定できなかった回は null）を分母にして skill 別に数える
report_template_rates = {}
for e in events:
    _rt = e["p"].get("report_template")
    if _rt in ("present", "absent"):
        _s = str(e["plugin"]).split(":")[-1]
        _d = report_template_rates.setdefault(_s, {"judged": 0, "absent": 0})
        _d["judged"] += 1
        _d["absent"] += 1 if _rt == "absent" else 0
# 取り違え疑いで外した回（#246）。publish の gap ではなく読み側の判定なので欠測内訳には混ぜない
session_suspects = {}
for e in events:
    if e.get("session_suspect"):
        session_suspects[e["session_suspect"]] = session_suspects.get(e["session_suspect"], 0) + 1
have_synthesis = len(measured(events, "duration_synthesis_min"))
have_waves = sum(1 for e in events
                 if num(agents_dict(e["p"]).get("explorer_waves")) is not None)
split_waves = sum(1 for e in events
                  if (num(agents_dict(e["p"]).get("explorer_waves")) or 0) >= 2)
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
# **`wave-split` の分母は他の gap と意味が違う**（GitHub issue #192）。他は「フィールドが
# 載っていたか」なので `n_gapfield` でよいが、`wave-split` は**wave 判定が成立した回**が
# 母集団になる。判定は `dispatch.waves` と `waves_expected` が揃い、かつ
# `agents-mismatch` で抑止されていない回でだけ行われる（publish-review-event.sh）。
# 全 gap 保持者を分母にすると比率が薄まり、実測 50% が 18% に見えて閾値を下回っていた
#
# **判定は payload の `waves_expected` ではなく現行式で再計算する**（GitHub issue #200）。
# `waves_expected` は publish 時点の式で焼き付くが**式の版マーカーが無い**ので、式を直しても
# 過去のイベントは旧値のまま数え続けられ、**一度出た偽陽性が固定化する**（実測: `[6,10,4,1]`
# の回が #166 で解決済みの偽陽性なのに違反として残っていた）。再計算に必要な入力はすべて
# payload にある。payload の値は消さない — 食い違った件数を `stale` として出す。
n_wave_judged = 0
n_wave_suppressed = 0     # `agents-mismatch` で判定が抑止された回（分母にも分子にも入らない）
n_wave_split = 0          # 現行式で再計算した違反
n_wave_split_stale = 0    # payload の `waves_expected` と判定が食い違った回
wave_split_kinds = {}     # 違反の型ごとの件数（**推定** / 是正先の出し分け）
for _e in events:
    _p = _e["p"]
    _d = _p.get("dispatch")
    if not isinstance(_d, dict):
        continue
    if not isinstance(_d.get("waves"), int) or not isinstance(_d.get("waves_expected"), int):
        continue
    _sizes = _d.get("wave_sizes")
    # **判定は `waves_effective`（捨てられた試行・孫を除いた本数）**。無ければ `waves` に
    # 落とす。publish 側と同じ順序にすること（違うと再計算が別の量になる）
    _w = _d.get("waves_effective")
    if not isinstance(_w, int) or isinstance(_w, bool):
        _w = _d["waves"]
    if "agents-mismatch" in (_p.get("measurement_gaps") or []):
        # 申告が壊れた回は期待本数を作れないので抑止する。**ただし全層が起動した場合の上限すら
        # 超えた回は、申告に依らず違反と確定できる**（v2.120.1 / GitHub issue #220。実測で
        # `[1×14]` と `[1,1,1,1,6,6,1,6]` という最悪の逐次発行が抑止の側に隠れていた）。
        # 確定できた回だけを判定成立に入れる — 上限以下の回は守られたとも破られたとも言えない。
        # `verdict: serial` で数えないのは、単独 wave の連続だけで決まり期待本数を見ないため
        if _w > MAX_EXPECTED_WAVES:
            n_wave_judged += 1
            n_wave_split += 1
            wave_split_kinds["over-max"] = wave_split_kinds.get("over-max", 0) + 1
        else:
            n_wave_suppressed += 1
        continue
    n_wave_judged += 1
    _hit = _w > expected_waves(_p, _sizes)
    if _hit != (_w > _d["waves_expected"]):
        n_wave_split_stale += 1
    if _hit:
        n_wave_split += 1
        _kind = wave_split_kind(_p, _sizes)
        wave_split_kinds[_kind] = wave_split_kinds.get(_kind, 0) + 1
# `tokens` gap の分母。review だけが計測対象なので self-review を混ぜない
n_gapfield_review = sum(1 for e in events
                        if isinstance(e["p"].get("measurement_gaps"), list)
                        and str(e["plugin"]).endswith(":review"))
# `late-publish` gap の分母。**self-review でしか立たない**（review は締めフローの人間待ちを
# 含むのが契約なので、publish が遅いこと自体は正常）。混ぜると #127 と同型に薄まる
n_gapfield_selfreview = sum(1 for e in events
                            if isinstance(e["p"].get("measurement_gaps"), list)
                            and str(e["plugin"]).endswith(":self-review"))
# `fleet-span-mismatch` gap の分母（#207）。**判定できた回だけ**を数える — 突合には
# `dispatch.span_sec` と `since-t0` 窓が要り、揃う回は実測でごく一部（ローカル 15 件中 2 件）。
# `n_gapfield` に載せると #127 と同型に薄まって、比率が構造的に閾値へ届かなくなる
n_fleet_span_judged = sum(1 for e in events if _fleet_span_judgeable(e["p"]))
n_fleet_span_conflict = sum(1 for e in events if _fleet_span_conflict(e["p"]))

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
                      if (num(agents_dict(e["p"]).get("explorer")) or 0) >= 1]
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
# **tokens.schema 3 で usage の算法が変わり、スケールがおよそ半分になった**（transcript の行ごと
# → message.id 単位の重複排除）。schema 2 以下は行数ぶん膨らんだ値で、倍率も世代で違うので、
# 中央値・体数相関・1 体あたり cache_read のどれにも混ぜない（下限を上げる＝冒頭の層別の原則の
# 想定どおりの使い方）
TOK_SCALE_MIN_SCHEMA = 3
for e in tok_raw:
    t = e["p"]["tokens"] or {}
    if schema_of(t, "schema") < TOK_SCALE_MIN_SCHEMA:
        tok_dropped_schema += 1
    elif t.get("window") != "since-t0":
        tok_dropped_window += 1
    else:
        tok_rows.append(e)


#: `sub_*` 系のキー（sub 側の集計が空振りした回は分母から外す / GitHub issue #199）
_SUB_KEYS = ("sub_output_k", "sub_cache_write_k", "sub_cache_read_k")


def _sub_is_blank(t):
    """sub 側の計測が空振りした回か（GitHub issue #199）.

    sub の体数が 0 なのは「窓が sub の transcript を覆っていない」を意味する（申告体数が
    1 以上ある前提。レビューは必ず sub agent を起動する）。**publish は v2.101.0 以降 sub_* を
    None に倒して `tokens-sub` を立てる**が、それ以前に焼かれた回は `sub_output_k: 0.0` が
    残っているので、集計側でも `sub_agents` を見て弾く（旧データにも効かせる）。
    """
    n = num(t.get("sub_agents"))
    return n is not None and n == 0


def tok_vals(key):
    out = []
    for e in tok_rows:
        t = e["p"]["tokens"] or {}
        if key in _SUB_KEYS and _sub_is_blank(t):
            continue
        v = num(t.get(key))
        if v is not None and v >= 0:
            out.append(v)
    return out


tok_main = tok_vals("main_output_k")
tok_sub = tok_vals("sub_output_k")
# 体数 vs sub.output。**トークンは体数に素直に効く**という主張の検算で、崩れたら
# 「体数を減らせばトークンが減る」という triage-guide `## 7` の前提を見直す信号になる
txs, tys = [], []
for e in tok_rows:
    t = e["p"]["tokens"] or {}
    if _sub_is_blank(t):                 # sub 空振りの回は相関の分母に入れない（#199）
        continue
    ta, so = total_agents(e["p"]), num(t.get("sub_output_k"))
    if ta is not None and so is not None and so >= 0:
        txs.append(ta)
        tys.append(so)
tok_r = pearson(txs, tys)

# **1 体あたりの cache_read**（GitHub issue #156）。体数キャップ（#96）は「広さ」を切ったが
# 1 体あたりの読む量には手が入っておらず、`pending-optimizations.md ## 計測の基準値` の
# 1 体平均 cache_read 5,039k と比べる先がここ（ただし 5,039k は旧算法＝重複計上込みの値で、
# schema 3 の中央値とは直接比べられない）。**effort × size_tier で層別する** — tier は
# 担当ファイル数を、effort は 1 体あたりの探索量を決めるので、混ぜた中央値は両方の交絡を負う。
# **除算は `sub_agents` が正のときだけ**（0 で割れば `ZeroDivisionError`、欠測なら
# `TypeError` で、その回だけ静かに落ちるのではなく集計全体が死ぬ）。
# **版マーカーは `tok_rows` の時点で切ってある**（`TOK_SCALE_MIN_SCHEMA`）。`sub_cache_read_k` の
# 追加は schema 2 で、下限の 3 はそれより上なのでここで別の門は要らない。フィールドの在否で
# 代用すると、窓や単位を変えて schema を上げたとき旧版が無言で同じ中央値に混ざる（冒頭の層別の原則）
per_agent_buckets = {}
per_agent_undividable = 0
for e in tok_rows:
    t = e["p"]["tokens"] or {}
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
# **calib が最大の層**を代表に取り、同じ calib が世代で割れているときは verdict の
# 多い方を選ぶ（#191 で層キーに世代が入ったため、単純な `max()` では辞書順で
# `unrecorded` が勝ってしまう）
#
# **代表と「他世代」の数え上げから `unrecorded` / `mixed` を外す**（GitHub issue #251）。表の行は
# 残す（既知世代と同じバケツに入れない v2.88.2 の判断は変えない）が、世代が分からない層を
# 1 世代として扱うと、版窓では欠測した 1 回が代表になり「達成不能」の誤った ⚠️ を出していた
# （実測: 7 窓中 6 窓で代表が unrecorded。唯一の標本は transcript で見ると opus-5-5 だった）。
# **最新の calib は verdict の有無ではなく走行から取る** — verdict 0 件の世代も「走った」ことは
# payload に残っている（`adversarial_verify.fired` / `skip_reason`）。同点は層キーで決定的に割る
UNKNOWN_GENS = ("unrecorded", "mixed")
#: calib → 世代 → {runs, fired, verdicts, skips}（verdict 0 件の世代を黙らせないために使う / #251）。
#: **世代は `gen_of` で直接引く** — 層キーの世代（`LAYER_GEN`）は `GEN_SPLIT` のときしか埋まらず、
#: 単一世代の母集団で「verdict 0 件の世代」が数えられなくなる
calib_runs = {}
for _e in events:
    _av = _e["p"].get("adversarial_verify")
    if not isinstance(_av, dict):
        continue
    _r = calib_runs.setdefault(schema_of(_av, "calibration_schema"), {}).setdefault(
        gen_of(_e["p"]), {"runs": 0, "fired": 0, "verdicts": 0, "skips": {}})
    _r["runs"] += 1
    _r["verdicts"] += sum(num(_av.get(k)) or 0 for k in
                          ("confirmed", "refuted", "uncertain", "severity_inflated", "contested"))
    if _av.get("fired") is True:
        _r["fired"] += 1
    elif isinstance(_av.get("skip_reason"), str) and _av["skip_reason"]:
        _r["skips"][_av["skip_reason"]] = _r["skips"].get(_av["skip_reason"], 0) + 1
latest_calib = max(calib_runs) if calib_runs else None
_latest_known = [k for k, v in verdict_layers.items()
                 if v["calib"] == latest_calib and LAYER_GEN.get(k) not in UNKNOWN_GENS]
newest_layer = (max(_latest_known, key=lambda k: (verdict_layers[k]["total"], k))
                if _latest_known else None)
# 上流較正（`prompts/reviewer-common.md` の「降格される典型パターン」= v2.62.0）の効果は
# **対策後のサンプルでしか測れない**（orchestration-measurement.md `## 16` / triage-dynamic-gates.md
# `## 9`「この 52% を上流対策の効果測定に使わないこと」）。`calibration_schema` が未注入だった
# v2.64.x 以前のサンプルは全部 layer 1 に落ちるため、**対策前の累計値でシグナルが発火し続けて
# いた**（issue #131）。層 1 しか無いうちは黙る
CALIB_MIN = 2
VERDICT_MIN = 20     # 層内の verdict 件数の下限（これ未満では層の比率を解釈しない）
# **該当する層をすべて出す**。層キーに世代が入って同じ calib に複数層が並ぶように
# なったので、代表 1 層だけを見ると**条件を満たした別世代が黙って落ちる**
# （「⚠️ が出たときだけ行動する」契約では「該当なし」と読まれる）
for _lk in sorted(verdict_layers):
    L = verdict_layers[_lk]
    ratio = pct(L["severity_inflated"], L["total"])
    # **最新より古い calib の層では鳴らさない**（GitHub issue #251 提案 3）。publish は現行の
    # `calibration_schema` を固定で注入するので、古い層はもう増えず、鳴っても行動の先が無い
    # （#221 で「鳴っていること自体は新しい情報ではない」と確認済み）。古さは母集団の最新と
    # 比べる — 最新が古い calib しか無い母集団では従来どおり鳴る。表の行と注記は残す
    # **世代が分からない層でも鳴らさない**（#251）。節が「世代が分からないので効果判定に使わない」と
    # 言う層で「効いていない疑い」を出すと、同じ出力の中で表示が食い違う
    if (L["total"] >= VERDICT_MIN and ratio >= 45 and L["calib"] >= CALIB_MIN
            and L["calib"] == latest_calib and LAYER_GEN.get(_lk) not in UNKNOWN_GENS):
        # ラベルは**その層のキー**を出す（`newest_layer` を出すと別層の名前が付く）。
        # キーには世代が入っているので `層=` と呼ぶ
        signals.append("severity_inflated が %.0f%%（層=%s / %d verdict）。"
                       "上流較正（prompts/reviewer-common.md の降格典型）が効いていない疑い"
                       % (ratio, _lk, L["total"]))
    # 下の 2 つは `CALIB_MIN` で絞らない。**反証レイヤー自身の設定**（effort / バッチサイズ）の
    # 再監視条件であって上流較正の効果測定ではないので、較正版で層別する理由が無い
    if L["total"] >= VERDICT_MIN and pct(L["uncertain"], L["total"]) >= 15:
        signals.append("uncertain が %.0f%%。反証 effort を max に戻す条件"
                       "（triage-dynamic-gates.md `## 9`）に該当" % pct(L["uncertain"], L["total"]))
    if L["total"] >= VERDICT_MIN and pct(L["refuted"], L["total"]) >= 20:
        signals.append("refuted が %.0f%%。反証バッチサイズ 5 → 3 の再検討条件に該当"
                       % pct(L["refuted"], L["total"]))
# **相関は ⚠️ に出さない**（GitHub issue #217 で再監視を終了した）。この行はもともと
# 「`## 7` の『体数と fleet は無相関』を再監視せよ」というトリガーで、実際に 3 回鳴って
# 3 回とも調べ切った: tier 交絡（#151）/ 世代・effort・wave 数の統制（#217）/ synthesis の
# 混入（#217）。**どれでも消えない＝もう調べる先が無い**ので、鳴らし続けると「⚠️ が出た
# ときだけ行動する」契約の方が壊れる。規範自体は残るが根拠が変わった（無相関だから、では
# なく**相関は因果ではなく体数削減は recall を削るから** / `## 7`）。
#
# **再開の条件は指標ではなく実験**: #190 の A/B が「体数削減で fleet が縮み、かつ MAJOR が
# 減らない」を示したときに `## 7` ごと見直す。閾値を層ごとに動かして黙らせる案（#217 候補①）は
# 採らない — データに合わせて水準を動かすのは検出力を捨てるのと同じ。
r_strong_tiers = [(t, n_t, rr) for t, n_t, rr in tier_r_judged if abs(rr) >= R_STRONG]
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
    if g == "fleet-span-mismatch":     # 突合の材料が揃った回でのみ判定できる（#207）
        return n_fleet_span_judged
    if g.startswith("payload:md_polish"):  # self-review だけのフィールド（#243）
        return n_gapfield_selfreview
    # **`agents-abandoned` / `agents-nested` / `wave-split` はここに来ない** — 欠測ではないので `gap_counts` から外してあり
    # （#192）、分母 `n_wave_judged` と分子は専用の判定ブロックが持つ（#200）
    return n_gapfield


def gap_hint(g):
    """**gap の種類で是正先が違う**（issue #128 のセルフレビュー指摘）。
    全部を「打点箇所の見直し」と言うと、payload の記述漏れに対して誤った是正先を指す。"""
    # **`startswith("payload:")` より前に置く**（後ろだと到達しない）。記述漏れではなく
    # 語彙違反なので是正先が違う — キーを足すのではなく契約どおりの名前に直す（#203）
    if g == "payload:pre_adjust_counts.vocab":
        return ("`pre_adjust_counts` のキーが契約外。**記述漏れではなく語彙違反**なので"
                "キーを足すのではなく名前を直す — 正しくは `blocker` / `critical` / `major` / "
                "`minor` の 4 つ（正本の payload テンプレート: orchestration-measurement.md "
                "`## 16`。**SKILL 本文にはキー名が書かれていない**ので、埋める側はここを引く）")
    # **記述漏れではなく置き場所の誤り**（#208）。テンプレートを見てネストを 1 段外へ
    # 書いた回で、値は誤った場所にあるので集計されない。是正先はキーを足すことではない
    if g.endswith(".misplaced"):
        return ("`%s` が payload のトップレベルにある。**記述漏れではなくネストの誤り**で、"
                "値は集計されない — 親オブジェクトの中へ 1 段戻す（正本の payload "
                "テンプレート: orchestration-measurement.md `## 16`）"
                % g[len("payload:"):-len(".misplaced")])
    if g == "payload:agents.vocab":
        return ("`agents` のキーが契約外。**記述漏れではなく語彙違反**なので名前を直す — "
                "契約は `explorer` / `reviewer` / `specialist` / `round2` / `verify` / "
                "`verify_findings` / `explorer_waves` の 7 つで、動的層は専用フィールドの "
                "`fired` から数える（orchestration-measurement.md `## 16`）")
    # **欠測ではなく形の違反**（#238）。値は昇格して集計に載っているので、是正先は
    # キーを足すことではなくフラットに書くこと
    if g == "payload:report_counts.nested":
        return ("報告件数が `report_counts` / `counts` の入れ子で渡された。publish がトップレベルへ"
                "昇格したので**集計には載っている**が、契約はフラットな `blocker_count` / "
                "`critical_count` / `major_count` / `minor_count`（正本の payload テンプレート: "
                "orchestration-measurement.md `## 16`）")
    if g == "payload:severity_threshold.nested":
        return ("`severity_threshold` が `below_threshold_counts` / `pre_adjust_counts` の中に書かれた。"
                "publish がトップレベルへ昇格したので**層別には使われている**が、契約はトップレベルの "
                "1 キー（正本の payload テンプレート: orchestration-measurement.md `## 16` / #252）")
    if g == "payload:report_counts.missing":
        return ("報告件数（`blocker_count` / `critical_count` / `major_count` / `minor_count`）が"
                "揃っていない。**4 つとも必須で 0 件でも省かない** — 埋め落とした回は歩留まり・"
                "報告 0 件率・真の空振りの母集団から外れる（サンプルの損失 / #215）。"
                "正本の payload テンプレート: orchestration-measurement.md `## 16`")
    if g == "payload:agents.empty":
        return ("`agents` に体数のキーが 1 つも無い。集計側はこの回を体数中央値・fleet 相関・"
                "1 体あたり cache_read の母集団から外す — 起動した体数は失われる")
    if g == "payload:recall_skeptic.launch":
        return ("skeptic が起動したのに起動経路（`launch`: `rider` = 相乗り / `fallback` = 単独）の"
                "自己申告が無い。集計は位置ヒューリスティックに落ちる — 同じ層構成でも反証 wave の"
                "体数で wave-split の判定が反転する（#216）。値は両 SKILL の skeptic 相乗り / "
                "fallback 段落が決めている（orchestration-measurement.md `## 16`）")
    if g.startswith("payload:md_polish"):
        # `.skip_reason` は判定材料（`## md-polish`）が出なかった回にも立つ（guide 1 節）。
        # そちらは `missing_coverage` に `md-polish` が並ぶので是正先を併記する
        return ("self-review の publish 節（Step 6.4）の `md_polish` の記述漏れ。**起動しなかった回も** "
                "`fired: false` と `skip_reason` で入れる（md-polish-guide.md の 5 節 / #243）。"
                "`missing_coverage` に `md-polish` がある回は記述漏れではなく `md-prose-lines.sh` の失敗")
    if g.startswith("payload:"):
        return "payload テンプレートの記述漏れ（両 SKILL の publish 節）を見直す"
    if g == "late-publish":
        return ("publish が t2 から 10 分以上遅れた回が常態化している（self-review Step 6.4）。"
                "`review-timing.sh publish-pending` のガード位置を見直す")
    if g == "tokens":
        # transcript を引けなかった回は v2.130.6 から `session-unresolved` に分かれた（#246）
        return ("transcript は引けたが main のメッセージを数えられなかった（窓の空振り・"
                "measure-tokens.sh の失敗）。窓の起点（t0 の打点）を見直す")
    if g == "tokens-sub":
        # **打点ではなく窓の被覆**（#199）。sub agent の transcript が窓の外にある
        return ("sub 側の計測が空振りした（`sub_agents == 0`。セッション再開・窓の開始遅れで "
                "sub agent の transcript が `since-t0` の窓の外にある）。measure-tokens.sh の "
                "窓の起点（t0 の打点・セッション選択）を見直す")
    if g == "diff-digest":
        return "diff の突合キー算出（lib/review-paths.sh）を見直す"
    # 新識別子を足したら**ここにも分岐を足す**（v2.88.2 / #167・#169）。既定に落とすと
    # 「打点箇所の見直し」＝**確実に誤った是正先**を提示する（`models` は打点と無関係で、
    # `axis-unknown` / `demoted-unknown` は語彙の寄せ漏れ）。識別子を分けた目的が
    # シグナル欄で消えるので、分けた側と読む側は同時に直す
    if g == "models":
        return ("transcript の窓内に実モデル名が無かった（窓の空振り・プレースホルダのみ）。"
                "窓の起点（t0 の打点）を見直す")
    if g == "report-template":
        # 打点でも payload でもなく、レポートの出し方（#250）
        return ("レポート出力の定型（self-review Step 6 / review Step 7。`**指摘件数**: BLOCKER …` の行）を"
                "publish の前に出していない。SKILL.md を Bash の cat / sed で読んで切り詰められていないか"
                "（Read の offset でテンプレートまで読む）、他 skill から回したときに進捗報告で置き換えて"
                "いないかを見る。skill 別の率は「計測の健全性」の定型レポートの行")
    if g == "session-unresolved":
        # **窓でも打点でもなく id の解決**（#246）。推定には倒していないので値は欠測で、誤値は無い
        return ("publish 時に `CLAUDE_CODE_SESSION_ID` から transcript を引けなかった（env が無い / "
                "id が英数字・`_`・`-` 以外を含む / `~/.claude/projects/*/<id>.jsonl` が無い）。"
                "`tokens` / `models` / `dispatch` は"
                "欠測にしてある — Claude Code が env を渡しているか、transcript の置き場所が"
                "変わっていないかを見る（lib/review-paths.sh の `review_session_transcript`）")
    if g == "axis-unknown":
        return "反証 agent の axis 語彙（prompts/adversarial-verify.md）と両 SKILL Step 6 の対応表を見直す"
    if g == "demoted-unknown":
        return "reviewer の降格型名（prompts/reviewer-common.md の 4 型）と両 SKILL Step 6 の対応表を見直す"
    if g == "fleet-span-mismatch":
        # **打点の話だが区間が特定できる**ので、既定より具体的に言える（#207）
        return ("fleet 区間が agent の起動スパンを覆えていない。t1 を一括発行の直前に、"
                "t2 を全 agent の回収後に打てているか見直す（orchestration-measurement.md "
                "`## 14`）。**該当回の `duration_fleet_min` は欠測に倒してある**")
    if g == "machine-id":
        return ("publish 時に `hostname -s` が値を返さなかった。どのマシンの回か payload から"
                "言えず、マシン間の読み違いを切り分けられない（publish-review-event.sh の出所注入）")
    if g == "plugin-version":
        return ("publish スクリプト自身の `plugin.json` を読めなかった（プラグインの配置が壊れている"
                "疑い）。その回がどの版の規約で走ったかが分からず、配布ラグの交絡を外せない")
    if g == "wave-split":
        # **打点とは無関係**。既定に落ちると確実に誤った是正先を指す（#192）
        return ("同一フェーズの agent を 1 メッセージで一括発行する"
                "（orchestration-guide.md `## 0`）。打点の問題ではない")
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
# **一括発行の規約違反は欠測と別枠で出す**（#192）。`measurement_gaps` に積まれるだけで
# 計測は取れており、「計測が取れなかった」と「規約が守られなかった」では読む人の次の一手が
# 違う。**上の上位 2 件枠とも競合させない** — 枠から溢れると是正先ごと消える。
# 分子は現行式での再計算（#200）で、payload の `waves_expected` は使わない
if n_wave_judged >= GAP_MIN_N and pct(n_wave_split, n_wave_judged) >= GAP_RATIO:
    signals.append("一括発行の規約違反が %.0f%%（%d/%d・wave 判定が成立した回のみ）。%s"
                   "。内訳（**推定** / 型で是正先が違う）: %s"
                   % (pct(n_wave_split, n_wave_judged), n_wave_split, n_wave_judged,
                      gap_hint("wave-split"), wave_split_kinds_txt()))
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
# 下限未満で閾値を超えた層の控え（#209）。⚠️ が 1 本も出なかったシグナルだけ後で出す
layer_pending = {}
# 保留行の「累計では」は、母集団を絞った実行では誤読になる（絞った後の全体であって累計ではない）
pending_filtered = bool(since or last_n or min_pv_raw)
signals.extend(layered_signal(
    skeptic, lambda d: d.get("valuable", 0), lambda d: d.get("fired", 0), 15,
    lambda v, f: pct(v, f) < 25,
    lambda label, v, f, note:
        "冷や読み skeptic の価値率が %.0f%%（%s / fired %d 件 / attribution_schema>=2）。"
        "high 起点への昇格を戻すロールバック条件"
        "（triage-dynamic-gates.md `## 8.5`）に該当%s" % (pct(v, f), label, f, note),
    pending=layer_pending.setdefault("skeptic 価値率", [])))
# 反証レイヤーの不発（`no-eligible-findings`）は **⚠️ にしない**（GitHub issue #249）。以前は世代別に
# 50% 以上で鳴らしていたが、分母に effort の違う回が混ざっていた:
#   - high 帯は世代が分かる 31 回中 30 回が不発で、opus-4-8 / opus-5 / opus-5-5 のどれも 9 割超。
#     ただし率は「上流に MAJOR も無かった」（30 回中 17 回）と「MAJOR はあったが帯の外」（12 回）の
#     和で、率からはどちらかを読めない。行動（ゲート幅の再検討）は率ではなく
#     `design-notes/scoring-rationale.md` の再検討条件で決める
#   - xhigh 以上の不発は「報告見込みの指摘が 0 件」とほぼ同じ現象（実測: 報告件数が取れる 17 件は
#     全件 BLOCKER + CRITICAL + MAJOR = 0）で、報告 0 件率の表が既に測っている
# 数字は「動的層の発火」の effort 帯別の行に残す（黙らせない）
# **起動ゼロと価値率は排他のまま**（1 度も起動していない層に価値率を出しても意味が無い）
_meta_dead = layered_signal(
    meta, lambda d: d.get("fired", 0), lambda d: d.get("n", 0), 8,
    lambda fired, n: fired == 0,
    lambda label, fired, n, note:
        "meta-reviewer が起動対象 %d 件（%s / gate_schema>=3・effort 帯内）で 1 度も"
        "起動していない。起動ゲートの再検討が要る%s" % (n, label, note),
    pending=layer_pending.setdefault("meta の起動ゼロ", []))
if _meta_dead:
    signals.extend(_meta_dead)
else:
    signals.extend(layered_signal(
        meta, lambda d: d.get("valuable", 0), lambda d: d.get("fired", 0), 10,
        lambda v, f: pct(v, f) < 20,
        lambda label, v, f, note:
            "meta-reviewer の価値率が %.0f%%（%s / fired %d 件 / gate_schema>=3）。"
            "層を畳むロールバック条件（triage-dynamic-gates.md `## 8`）に該当%s"
            % (pct(v, f), label, f, note),
        pending=layer_pending.setdefault("meta 価値率", [])))

# **真の空振り率**（GitHub issue #214）。#210 の判定基準の片方で、表に出ていても鳴らなければ
# 行動につながらない（#209）。閾値 20 は #210 本文が「回復のサイン」として先に固定した値で、
# 下限 10（#249 で外した反証の不発シグナルと同じ値だった）。
# 実測（gist 集約 n=183）: opus-4-8 で 43%（9/21）が閾値超え、
# 他の層は下限未満 ＝ 新しい ⚠️ として鳴るのは 1 層だけで、初回から鳴りっぱなしにはならない
# **⚠️ にも内訳を載せる**（GitHub issue #210）。行動する人が見るのはこの 1 行なので、
# 表にだけ内訳があっても「どちらを直すのか」が伝わらない。`layered_signal` は層の dict を
# render へ渡さないので、label から引ける対応表を先に作る（label の書式は同関数の正本）
_ts_split = {"`%s` 層" % _k: (_v.get("true_silent_empty", 0), _v.get("true_silent_below", 0),
                              _v.get("true_silent_below_listed", 0),
                              _v.get("true_silent_below_over", 0))
             for _k, _v in apx_stats["by_gen"].items()}
_ts_split["累計"] = (apx_stats["true_silent_empty"], apx_stats["true_silent_below"],
                   apx_stats["true_silent_below_listed"], apx_stats["true_silent_below_over"])


def _ts_breakdown(label):
    """⚠️ に付ける内訳と**処方**（GitHub issue #210）。

    **率そのものは絞らない**（報告 0 かつ推奨 0 = 利用者から見た「何も返ってこなかった」割合で、
    これが体感そのもの）。分母を「検出 0」だけに絞れば基準を満たすが、それは #217 で却下したのと
    同じ形 — データに合わせて定義を動かして基準を通すことになる。**動かすのは処方の側**:

    - 検出 0 が主 … reviewer が何も見つけていない ＝ recall の問題。世代を見直す
    - 閾値未満のみが主 … 見つけたものに出口が無い ＝ 閾値と付録の方針の問題。
      **世代を上げても同じ結果になりうる**ので、世代だけを指すのは誤った是正先
    - 同数・判定不能 … 絞らずに両方を出す（推測で片方に倒さない）

    対応表に無い label では黙る（数字を捏造しない）。
    """
    if label not in _ts_split:
        return ""
    empty, below, below_listed, below_over = _ts_split[label]
    if empty > below:
        why = ("**検出 0 が主**なので打ち手は recall 側 — 実行世代を見直す"
               "（triage-guide.md `### 5.2`）")
    elif below > empty:
        # 付録に出た回には「付録にも出ていない」と言い切らない（#248）
        where = ("報告にも付録にも出ていない" if not below_listed else
                 "報告には出ていない（付録にも出ていないのは %d 件。残る %d 件は付録に出たが推奨なし"
                 "%s / #248）"
                 % (below - below_listed, below_listed,
                    "" if not below_over else
                    "。うち %d 件は付録が上限を超えた ＝ 閾値未満の本文が混ざった回（契約外）" % below_over))
        why = ("**閾値未満のみが主**なので打ち手は閾値と付録の方針 — reviewer は見つけており、"
               "`## below-threshold` に件数だけ返って%s。"
               "**世代を上げても同じ結果になりうる**（triage-guide.md `### 5.2` / scoring-guide.md）"
               % where)
    elif empty or below:  # mutation-ok: ここに来る時点で empty == below なので or と and は同値
        why = ("検出 0 と閾値未満のみが同数なので**打ち手を 1 つに絞れない** — "
               "実行世代と、閾値・付録の方針の両方を見る（triage-guide.md `### 5.2`）")
    else:
        why = ("内訳が判定不能（`pre_adjust_counts` の不在・語彙違反）なので**打ち手を絞れない** — "
               "まず payload の欠測を潰す（orchestration-measurement.md `## 16`）")
    return "（検出 0 が %d 件 / 検出はあったが全部閾値未満が %d 件）。%s" % (empty, below, why)


def _recovery_window_hint():
    """回復の読み方を添える（#210）。累計には打ち手より前の回が残り続け、率が構造的に下がりにくい."""
    if min_pv_raw:
        return "（plugin_version %s 以上に絞った集計）" % min_pv_raw
    return ("。**回復は打ち手を入れた版以降に絞って読む** — 累計には打ち手より前の回が残り続ける"
            "（`--min-plugin-version <版>`）")


signals.extend(layered_signal(
    apx_stats, lambda d: d.get("true_silent", 0), lambda d: d.get("n", 0), 10,
    lambda ts, n: pct(ts, n) >= 20,
    lambda label, ts, n, note:
        "真の空振り率（報告 0 件かつ付録推奨 0）が %.0f%%（%s / %d/%d）%s。#210 の回復サイン"
        "（20%% 未満）を満たしていない%s%s"
        % (pct(ts, n), label, ts, n, _ts_breakdown(label), note, _recovery_window_hint()),
    pending=layer_pending.setdefault("真の空振り率", [])))

# **synthesis の支配率**（GitHub issue #218）。閾値の根拠は上の 4b。層別は他と同じ流儀
signals.extend(layered_signal(
    syn_stats, lambda d: d.get("dominant", 0), lambda d: d.get("n", 0), SYN_MIN_N,
    lambda dom, n: pct(dom, n) >= SYN_RATE_HOT,
    lambda label, dom, n, note:
        "synthesis が fleet の %d%% 以上を占めた回が %.0f%%（%s / %d/%d）。打ち手はメイン側"
        "（分冊の遅延読み込み・可変部の圧縮・scoring の機械化 / orchestration-measurement.md "
        "`## 14`）— 体数削減では縮まない（triage-guide.md `## 7`）%s"
        % (SYN_DOMINANT_PCT, pct(dom, n), label, dom, n, note),
    pending=layer_pending.setdefault("synthesis の支配率", [])))

# ---- 出力 -----------------------------------------------------------------
if as_json:
    print(json.dumps({
        "n": n_all, "n_recent_30d": len(recent), "by_plugin": by_plugin,
        # 母集団の再現性（どのログから何件採ったか / issue #160）
        "sources": source_rows(events), "sources_dropped_duplicates": dup_dropped,
        "sources_dropped_paths": dup_paths,
        # 母集団の**範囲**（#173）。`this-repo` は自動探索 = 他リポジトリを含まない
        "sources_scope": "explicit" if logs_explicit else "this-repo",
        # 計測の出所（集計した retro の版・マシン / 母集団のマシン × plugin 版）
        "provenance": provenance_of(events),
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
        "md_polish": md_polish,
        "round2_fired": round2_fired, "round2_scope": len(round2_scope),
        "tokens": {"n": len(tok_rows), "n_raw": len(tok_raw),
                   "dropped_window": tok_dropped_window,
                   "dropped_schema": tok_dropped_schema,
                   "main_output_k_median": median(tok_main),
                   "sub_output_k_median": median(tok_sub),
                   "agents_sub_output_r": tok_r, "agents_sub_output_n": len(txs)},
        # **一括発行は欠測と別枠**（#192 / #200）。`marker` は payload に焼かれた
        # publish 時点の判定の生カウントで、`n` は現行式での再計算。食い違いは `stale`
        "wave_split": {"n": n_wave_split, "judged": n_wave_judged,
                       "suppressed": n_wave_suppressed, "stale": n_wave_split_stale,
                       "marker": n_wave_split_marker, "kinds": wave_split_kinds},
        # **`agents` の分解は欠測ではない**ので下の `measurement.gaps` から外してある
        # （#211）。**黙って捨てない** — 生のマーカー件数をここに残す
        "agents_decomposition": {"abandoned_marker": n_agents_abandoned_marker,
                                 "nested_marker": n_agents_nested_marker},
        # **判定できた回の数を出す**（#207）。分母が小さいうちは ⚠️ が出ないので、
        # 出ないことを「該当なし」と読ませないために母数そのものを見せる
        "fleet_span": {"judged": n_fleet_span_judged, "conflict": n_fleet_span_conflict},
        # 世代別の真の空振り（#214）。`報告 0 件率（世代別）` と同じ母数の扱い
        "appendix_by_gen": apx_stats["by_gen"],
        # 真の空振りの内訳（#210）。`empty` = 検出 0 / `below` = 検出はあったが全部閾値未満
        "true_silent_split": {"empty": apx_stats["true_silent_empty"],
                              "below": apx_stats["true_silent_below"],
                              # #248。`below` のうち付録には出た回（推奨なし）
                              "below_listed": apx_stats["true_silent_below_listed"],
                              "below_over": apx_stats["true_silent_below_over"],
                              "unknown": apx_stats["true_silent_unknown"]},
        # 推奨で救われた回のうち、付録の上限が 0 だった回（契約外の行に救われた / #248）
        "appendix_bound": {"rescued_judged": apx_stats["rescued_judged"],
                           "rescued_uncontracted": apx_stats["rescued_uncontracted"]},
        "body_bound_marker": n_exceeds_marker,
        "splits_bound": {k: {"judged": v["judged"], "over": v["over"],
                             "over_appendix": v["over_appendix"], "over_report": v["over_report"],
                             "lower": v["lower"], "written": v["pre"] - v["below"],
                             "post": v["post"]}
                         for k, v in splits.items()},
        # synthesis の支配率（#218）。比率は % の整数ではなく実数（丸めは表示側）
        "synthesis_dominance": {
            "n": syn_stats["n"], "dominant": syn_stats["dominant"],
            "inconsistent": syn_inconsistent, "threshold_pct": SYN_DOMINANT_PCT,
            "median_pct": median(syn_pcts), "p75_pct": quantile(syn_pcts, 0.75),
            "max_pct": max(syn_pcts) if syn_pcts else None, "by_gen": syn_stats["by_gen"]},
        "measurement": {"gaps": gap_counts, "n_with_gap_field": n_gapfield,
                        "nested_report_counts_recovered": nested_recovered,  # #238（読み側の回収）
                        # #252。どちらも歩留まりの母集団で数える（`missing` は `threshold=?` に入った回）
                        "severity_threshold": {"nested_recovered": threshold_recovered,
                                               "missing": threshold_missing},
                        # #250。skill → {judged, absent}（判定できた回だけを分母にする）
                        "report_template": report_template_rates,
                        # #246（読み側で外した回。キーは規則 `overlap` / `sub-blank`）
                        "session_suspect": session_suspects,
                        "have_synthesis": have_synthesis, "have_explorer_waves": have_waves,
                        "split_explorer_waves": split_waves,
                        # 健全性判定に使うのは下の modern 側。上の have_* は全サンプル母数の
                        # 生カウントで後方互換のため残す。**waves は分母が違う**
                        # （explorer 起動回のみ = modern_explorer_waves_scope）
                        "n_modern": n_modern, "modern_synthesis": modern_synthesis,
                        "modern_explorer_waves": modern_waves,
                        "modern_explorer_waves_scope": len(modern_waves_scope)},
        "signals": signals,
        # 下限未満で閾値を超えた層（#209）と、判定可能になるまでの件数（#230）。
        # テキスト出力はシグナルごとに 2 層で切るが、こちらは全層を出す
        "pending": [{"signal": sig, "layer": k, "numer": num, "denom": den,
                     "min_n": mn, "remaining": mn - den}
                    for sig in sorted(layer_pending)
                    for k, num, den, mn in layer_pending[sig]],
    }, ensure_ascii=False, indent=2))
    sys.exit(0)

print("## レビュー振り返り（review:completed n=%d）" % n_all)
print()
for _line in provenance_lines(events):
    print("- " + _line)
print()
print(sources_line())
for row in source_rows(events):
    print("- `%s` … %d 件" % (row["path"], row["n"]))
_note = scope_note()
if _note:
    print()
    print(_note)
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
_tier_shown, _tier_dropped, _tier_dropped_n = cap_layer_rows(tier_rows)
for key, n, f, a in _tier_shown:
    print("| %s | %d | %s | %s |" % (key, n, "-" if f is None else "%g 分" % f,
                                     "-" if a is None else "%g" % a))
_note = layer_omission_note(_tier_dropped, _tier_dropped_n)
if _note:
    print()
    print(_note)
if tier_r_rows:
    print()
    print("**体数 vs fleet 時間の相関**（size_tier × 世代。tier が体数と fleet の両方を"
          "決めるため層別しない r は交絡する / issue #151・#217）")
    print()
    print("| 層 | n | r | 判定 |")
    print("|---|---:|---:|---|")
    for t, n_t, rr in tier_r_rows:
        if rr is None or n_t < R_MIN_N:
            verdict = "判定不能（n < %d）" % R_MIN_N
        elif abs(rr) < R_FLAT:
            verdict = "体数はレバーではない"
        elif abs(rr) < R_STRONG:
            verdict = "弱〜中（effort の交絡を疑う）"
        else:
            verdict = "高い（既知 / #217）"
        print("| %s | %d | %s | %s |" % (t, n_t, "-" if rr is None else "%.3f" % rr, verdict))
    print()
    if not tier_r_judged:
        print("どの tier も n < %d。**体数と壁時計の関係は判定しない**（標本不足）。" % R_MIN_N)
    elif all(abs(rr) < R_FLAT for _, _, rr in tier_r_judged):
        print("判定できる全 tier で |r| < %.1f。**体数は壁時計のレバーではない**"
              "（triage-guide.md `## 7`）— 時間が長いときの打ち手は synthesis / wave 側で"
              "切り分ける。" % R_FLAT)
    if r_strong_tiers:
        # **鳴らさないが黙りもしない**（#217）。この行を消すと「測っていない」と読まれる
        print("|r| が %.1f 以上の層がある（%s）が、**⚠️ には出さない** — tier / 世代 / effort / "
              "wave 数の統制 / synthesis の減算のどれでも消えないことまで確認済みで、"
              "**再監視は終了している**（GitHub issue #217）。相関は因果ではなく、体数と一緒に"
              "動く未観測の変数（diff の難しさ・1 体あたりの探索量）が両方を押していると読む。"
              "規範「体数を壁時計のレバーとして扱わない」は残るが、根拠は無相関ではなく"
              "**体数削減が recall を削ること**（triage-guide.md `## 7`）。次の判断材料は"
              "#190 の A/B。"
              % (R_STRONG, " / ".join("%s r=%.2f n=%d" % (t, rr, n_t)
                                      for t, n_t, rr in r_strong_tiers)))
    if r is not None:
        print("層別なしの r = %.3f（n=%d）は **tier 交絡を含むので発火条件には使わない**"
              "（参考値）。" % (r, len(xs)))

print()
print("**区間の中央値**: " + " / ".join(
    "%s %s（n=%d）" % (k, "-" if m is None else "%g 分" % m, c) for k, m, c in spans))

# **synthesis の支配率**（#218）。中央値だけでは「支配的だった回」が見えない — 打ち手の
# 切り分け（`## 14`）は回ごとの比率で決まるので、分布と上位の回を出す
if syn_pcts:
    print()
    print("**synthesis の支配率**（syn ÷ fleet / 両区間を実測で持つ回 n=%d）: 中央値 %.0f%% / "
          "75%% 点 %.0f%% / 最大 %.0f%% / %d%% 以上 **%d 件（%.0f%%）**"
          % (syn_stats["n"], median(syn_pcts), quantile(syn_pcts, 0.75), max(syn_pcts),
             SYN_DOMINANT_PCT, syn_stats["dominant"], pct(syn_stats["dominant"], syn_stats["n"])))
    if len(syn_stats["by_gen"]) > 1:
        print()
        print("| 世代 | n | %d%% 以上 |" % SYN_DOMINANT_PCT)
        print("|---|---:|---:|")
        for _gk in sorted(syn_stats["by_gen"]):
            _gv = syn_stats["by_gen"][_gk]
            print("| %s | %d | %d（%.0f%%） |" % (_gk, _gv["n"], _gv["dominant"],
                                                 pct(_gv["dominant"], _gv["n"])))
        print()
    _top = [r for r in sorted(syn_ratios, reverse=True) if r[0] >= SYN_DOMINANT_PCT][:SYN_TOP]
    if _top:
        print("- 支配的だった回（上位 %d）: " % len(_top) + " / ".join(
            "%.0f%% %s %s/%s/%s（syn %g / fleet %g 分）"
            % (r[0], r[1][5:16], r[2].split(":")[-1], r[3], r[4], r[5], r[6]) for r in _top))
    print("- 読み方: 支配的なら打ち手は**メイン側**（分冊の遅延読み込み・可変部の圧縮・scoring の"
          "機械化）で、**体数削減では縮まない**。そうでなければ wave 側（直列 wave 数・1 体あたりの"
          "探索量）を見る（orchestration-measurement.md `## 14` / triage-guide.md `## 7`）")
    if syn_inconsistent:
        print("- **%d 件は synthesis が fleet を超えており母数から外した**（内数の契約に反する = "
              "打点の矛盾。`fleet-span-mismatch` と同じ扱い）" % syn_inconsistent)

# **全件除外でも通知は出す**（#212）。ガードの内側に置くと、除外した結果 0 行になった
# ときに通知ごと消えて「該当なし」と読まれる — 直そうとしている誤読の同型
if not yields and yields_missing_post:
    print()
    print("**pre_adjust → 報告の歩留まり**: 判定対象なし（**%d 件は報告件数を 1 つも"
          "申告しておらず母集団から外した** / #212）" % yields_missing_post)
if yields:
    print()
    print("**pre_adjust → 報告の歩留まり**（%sで層別 / #191）"
          % ("版マーカー × 閾値 × 世代" if GEN_SPLIT else "版マーカー × 閾値"))
    for key, y in sorted(yields.items()):
        print("- %s: n=%d / 検出 %d → 報告 %d（%.1f%%）"
              % (key, y["n"], y["pre"], y["post"], pct(y["post"], y["pre"])))
    if yields_bad_vocab:
        print("  - **%d 件は `pre_adjust_counts` の語彙が契約外で母集団から外した**"
              "（`%s` の 4 つが揃っていない回。混ぜると実数が 0 として分子に入る / #203）"
              % (yields_bad_vocab, "` / `".join(PRE_SEVS)))
    # **除外した事実を残す**（`zero_missing` と同じ流儀）。黙って外すと母数が減った
    # 理由が読めなくなり、今度は「レビュー回数が減った」と誤読される
    if yields_missing_post:
        print("  - **%d 件は報告件数を 1 つも申告しておらず母集団から外した**"
              "（欠測を 0 と足すと**検出したのに全部捨てた回**に化ける / #212）"
              % yields_missing_post)

# **報告 0 件率（世代別）** — recall の最も粗い代理指標（GitHub issue #191）。
# コスト側だけ世代で層別して報告側を累計すると、「安くなった」だけが見えて
# 「効かなくなった」が見えない非対称になる
# **世代が 1 種でも出す。** この表は世代**間**の比較だけでなく「今どれだけ空振りして
# いるか」自体が指標なので、1 行でも意味がある（世代が 1 種のリポジトリは平常状態で、
# そこで指標が消えると recall の劣化を見る手段が無くなる）。`with_gen` の
# 「2 種以上のときだけ足す」規則は**追加キーが既存バケツを砕く**のを避けるためのもので、
# ここは世代が行そのものなので当てはまらない
# **全件除外でも注記は出す**（#212 / #213 と同じ穴の 4 箇所目 / #215）。ガードの内側に
# 置くと、除外した結果 0 行になった回は注記ごと消えて「該当なし」と読まれる
if not zero_rows and zero_missing:
    print()
    print("**報告 0 件率**: 判定対象なし（報告件数フィールドを 1 つも持たない **%d 件は母数から"
          "外した**%s）" % (zero_missing,
                             "" if not zero_missing_current else
                             "。うち %d 件は現行版の埋め落とし ＝ サンプルの損失 / #215"
                             % zero_missing_current))
if zero_rows:
    print()
    print("**報告 0 件率**（世代別 / 報告件数フィールドを持つ回。**recall の粗い代理**"
          " — 付録に救われた回は 0 件でも空振りとは限らない / #168・#191）")
    print()
    print("| 世代 | n | 報告 0 件 | pre_adjust MAJOR 中央値（n） |")
    print("|---|---:|---:|---:|")
    for g in sorted(zero_rows):
        z = zero_rows[g]
        pm = median(z["pre_major"])
        # **中央値の分母は行の n と違う**（`pre_adjust_counts.major` が欠測の回がある）。
        # 併記しないと同じ母数の統計だと読まれる
        pm_s = ("%g（n=%d）" % (pm, len(z["pre_major"]))) if pm is not None else "-"
        print("| %s | %d | %d（%.0f%%） | %s |"
              % (g, z["n"], z["zero"], pct(z["zero"], z["n"]), pm_s))
    if zero_missing:
        print()
        print("> 報告件数フィールドを 1 つも持たない **%d 件は母数から外した**"
              "（**0 件と欠測を潰さない** — 混ぜると 0 件率が構造的に上振れし、欠測の多い"
              "古い版ほど「recall が落ちた」に見える）%s"
              % (zero_missing,
                 "" if not zero_missing_current else
                 "。**うち %d 件は現行版の埋め落とし**（publish が `payload:report_counts.missing` "
                 "を立てた回 ＝ サンプルの損失。旧版の identification ではない / #215）"
                 % zero_missing_current))
    print()
    print("> `unrecorded` は**世代が記録されていない回**であって「古い世代」ではない。"
          "既知の世代と同じバケツに入れない（#169）")
    if len(zero_rows) > 1:
        print()
        print("**世代間で差が出ていたら、コスト側の層別（fleet / 体数 / cache_read）だけでは"
              "見えない。** 踏み下げは制御点だが recall 側の代償があり、"
              "その量はここでしか観測できない（#170・#191）")
    print()

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
        # **負に百分率を出さない**（#203）。`pct(-10, -10)` は 100.0% を返すが、負の分母に
        # 対する百分率は意味を持たない。負値そのものは残す（0 に丸めると「捨てていない」と
        # 読める）。**語彙違反は上で母集団から外してあるので、ここに残る負値は正当な経路**
        # （手順 1 の後に走る層が足したぶん）だけになる
        print("  - **本文を書いてから捨てた: %d 件（%s）**%s"
              % (dropped, "-" if written <= 0 else "%.1f%%" % pct(dropped, written),
                 "" if dropped >= 0 else
                 " — 負は報告件数が本文を書いた数を超えた回のぶん（閾値未満に数えた指摘にも本文が"
                 "書かれていた / #248）"))
        if sp["over"]:
            # 下限が 0 以下になるのは below が pre を超えた旧データだけ。分母が無いので率は出さない
            _rate = ("" if sp["lower"] <= 0 else "で、書いた後の破棄率は **%.1f%% 以上**"
                     % pct(sp["lower"] - sp["post"], sp["lower"]))
            print("  - **上限超え %d/%d 回**（付録 %d 回 / 報告件数 %d 回。本文を書いた数を超えた回 ＝ "
                  "閾値未満に数えた指摘にも本文が書かれていた / #248）。付録と報告から見ると本文を"
                  "書いたのは **%d 件以上**%s。上の `本文を書いた` は下限として読む"
                  % (sp["over"], sp["judged"], sp["over_appendix"], sp["over_report"],
                     sp["lower"], _rate))
    if splits_bad_vocab:
        print("  - **%d 件は `pre_adjust_counts` の語彙が契約外で母集団から外した**"
              "（#203。混ぜると `本文を書いた` が負に振れる）" % splits_bad_vocab)
    if splits_missing_post:
        print("  - **%d 件は報告件数を 1 つも申告しておらず母集団から外した**"
              "（欠測を 0 と足すと「本文を書いてから捨てた 100%%」に化ける / #213）"
              % splits_missing_post)
elif splits_missing_post:
    # **全件除外でも通知は出す**（#212 のコメントが踏んだ「ガードの内側に置くと通知ごと
    # 消える」を繰り返さない）
    print()
    print("**検出 → 報告の内訳**: 判定対象なし（**%d 件は報告件数を 1 つも申告しておらず"
          "母集団から外した** / #213）" % splits_missing_post)
elif yields:
    print()
    print("**検出 → 報告の内訳**は `below_threshold_counts` を持つサンプル待ち（#146）"
          " — 上の歩留まりは「本文を書いてから捨てた」と「件数だけ返した」の合算で、"
          "この 2 つを分けないと閾値注入（#117）の効果は判定できない")

if verdict_layers:
    print()
    print("**反証 verdict 分布**（%sで層別 — 累計で読むと施策の効果が薄まる / #191）"
          % ("calibration_schema × 世代" if GEN_SPLIT else "calibration_schema"))
    print()
    print("| %s | サンプル | verdict | confirmed | severity_inflated | refuted | uncertain | contested |"
          % ("calib/世代" if GEN_SPLIT else "calib"))
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
    _older = sorted({v["calib"] for v in verdict_layers.values() if v["calib"] < latest_calib})
    if _older and latest_calib >= CALIB_MIN:
        print()
        print("層 %s は旧較正（この母集団の最新は層 %d。publish は現行の calib を注入するので"
              "旧較正の層はもう増えない）。**severity_inflated の ⚠️ は層 %d だけで判定する**（#251）"
              % (" / ".join(str(c) for c in _older), latest_calib, latest_calib))

    def _runs_txt(r):
        return "%d 回（反証発火 %d 回%s）" % (
            r["runs"], r["fired"], "" if not r["skips"] else ": " + " / ".join(
                "%s %d" % kv for kv in sorted(r["skips"].items(), key=lambda kv: (-kv[1], kv[0]))))

    # 同じ最新層を走ったが verdict 0 件の既知世代と、世代が分からない回（#251）。**黙らせない** —
    # 待ちを止めているのが「他世代のサンプル」ではなく「現行世代で反証が発火していないこと」
    # だと、この行が無いと読めない（#131 の無言区間）
    _runs_latest = calib_runs.get(latest_calib, {})
    _zero_gens = sorted(g for g, r in _runs_latest.items()
                        if g not in UNKNOWN_GENS and r["verdicts"] == 0)
    _unknown_runs = sum(_runs_latest[g]["runs"] for g in UNKNOWN_GENS if g in _runs_latest)
    _unknown_verdicts = sum(_runs_latest[g]["verdicts"] for g in UNKNOWN_GENS if g in _runs_latest)

    def _print_runs_lines():
        if _zero_gens:
            print("  - 層 %d を走ったが verdict 0 件の世代: %s"
                  % (latest_calib, " / ".join("%s %s" % (g, _runs_txt(_runs_latest[g]))
                                              for g in _zero_gens)))
        if _unknown_runs:
            print("  - 世代を記録できなかった回（unrecorded / mixed）: %d 回・%d verdict — "
                  "世代が分からないので効果判定に使わない（#246 の transcript 取り違えでも生じる）"
                  % (_unknown_runs, _unknown_verdicts))

    if latest_calib is not None and latest_calib < CALIB_MIN:
        print()
        print("上流較正（v2.62.0）の効果判定は **`calibration_schema >= %d` のサンプル待ち**"
              "（現在は層 %s のみ = 対策前）。累計の severity_inflated 比率を効果測定に使わない"
              " — triage-dynamic-gates.md `## 9`" % (CALIB_MIN, newest_layer or latest_calib))
    elif newest_layer is None and latest_calib is not None:
        # **原因は言い切らない**（#251 のセルフレビュー）。世代不明の回が発火して verdict を出して
        # いることも、既知世代が 1 回も走っていないこともある。事実（走行・発火・verdict）は下の行に出す
        print()
        print("上流較正（v2.62.0）の効果判定は **層 %d で世代を記録できた verdict が 0 件**"
              "（効果判定には世代の分かる verdict が要る）— triage-dynamic-gates.md `## 9`"
              % latest_calib)
        if not _zero_gens:
            print("  - 層 %d を走った回のうち世代を記録できたものは 0 件" % latest_calib)
        _print_runs_lines()
    elif newest_layer is not None and verdict_layers[newest_layer]["total"] < VERDICT_MIN:
        print()
        print("上流較正（v2.62.0）の効果判定は **層 %s を蓄積中**（%d/%d verdict）。"
              "この件数ではシグナルを出さない — triage-dynamic-gates.md `## 9`"
              % (newest_layer, verdict_layers[newest_layer]["total"], VERDICT_MIN))
        # **「待てば貯まる」とは限らない**（GitHub issue #191）。対策後の層が特定の世代に
        # 偏っていると、比率が下がっても打ち手の効果か世代の副作用かを分離できない。
        # さらに上流の MAJOR がほぼゼロだと反証対象が無く、分子も分母も増えない。
        # **その状態を「蓄積中」と出すと、達成不能な条件を待ち続けることになる**
        if GEN_SPLIT:
            # **世代が分からない層は他世代に数えない**（#251）。中身は同じ世代でありうるので、
            # 数えると「分離できない」のに「分離できる」と読まれて警告が黙る
            if len(_latest_known) == 1:
                # 「層が 1 世代にしか存在しない」とは言わない — verdict 0 件で走った世代は
                # 下の行に出る（#251 で「opus-5-5 で 14 回走っているのに存在しないと出た」）
                print("  - ⚠️ **層 %d の verdict は世代 %s にしか無い**。比率が動いても"
                      "打ち手の効果と世代の副作用を分離できない。**この待ち行は"
                      "他世代の verdict が出るまで達成不能**（#191）"
                      % (latest_calib, LAYER_GEN.get(newest_layer)))
        _print_runs_lines()

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
if md_polish["n_raw"]:   # review だけの母集団では出さない（self-review のみの層）
    print("  - Markdown 推敲（self-review のみ / #243）: 起動 %d 回（提案あり %d 回）"
          % (md_polish["fired"], md_polish["valuable"]))
for name, st in (("skeptic", skeptic), ("meta", meta), ("反証", adversarial),
                 ("md 推敲", md_polish)):
    if st["dropped_schema"] or st["dropped_scope"] or st["dropped_unrecorded"]:
        print("  - %s 母集団: 全 %d 件 → 判定対象 %d 件（版マーカー %s>=%d で除外 %d / "
              "設計上非該当で除外 %d / 発火記録の欠落で除外 %d）"
              % (name, st["n_raw"], st["n"], st["schema_key"], st["min_schema"],
                 st["dropped_schema"], st["dropped_scope"], st["dropped_unrecorded"]))
    if st["skips"]:
        print("  - %s skip 理由: %s" % (name, " / ".join(
            "%s=%d" % kv for kv in sorted(st["skips"].items(), key=lambda kv: -kv[1]))))
    # **世代別の内訳**（GitHub issue #191 期待動作 1）。世代が 1 種の母集団では本体の
    # 1 行と同じ内容になるので出さない（no-op の行を足さない）
    if GEN_SPLIT and len(st["by_gen"]) > 1:
        for _g in sorted(st["by_gen"]):
            _b = st["by_gen"][_g]
            _sk = (" / skip: " + " ".join(
                "%s=%d" % kv for kv in sorted(_b["skips"].items(), key=lambda kv: -kv[1]))
                if _b["skips"] else "")
            print("    - %s / %s: 発火 %d/%d（%.0f%%）%s"
                  % (name, _g, _b["fired"], _b["n"], pct(_b["fired"], _b["n"]), _sk))

# **反証の不発を effort 帯で割って出す**（GitHub issue #249）。⚠️ にはしない（上のシグナル判定の
# 注記）。帯ごとに意味が違うので、帯の後に読み方を 1 句添える
_adv_bands = adversarial["by_effort"]
if _adv_bands:   # 判定対象の回が 1 件でもあれば帯の内訳も埋まる（`layer_stats`）
    _band_note = {"high": "ゲートが BLOCKER 60-94 / CRITICAL 80-94 だけなので、MAJOR しか出ない回は"
                          "構造的に不発（high-risk surface の MAJOR 85-94 / CRITICAL 70-79 を除く）",
                  "xhigh+": "ゲートは報告見込みの全 severity。不発は報告見込みの指摘 0 件に近く、"
                            "報告 0 件率の表で見る",
                  "other": "effort 未記録など"}
    print("  - 反証の不発（`no-eligible-findings`）を effort 帯別に（⚠️ にしない / #249）:")
    for _band in EFFORT_BANDS:
        _eb = _adv_bands.get(_band)
        if not _eb:
            continue
        _dry = sum(g["skips"].get("no-eligible-findings", 0) for g in _eb["by_gen"].values())
        # 世代が 1 つしか無い帯は、帯の行と同じ数字を繰り返すだけになる
        _gens = (" — " + " / ".join(
            "%s %d/%d" % (_g, _v["skips"].get("no-eligible-findings", 0), _v["n"])
            for _g, _v in sorted(_eb["by_gen"].items()))) if GEN_SPLIT and len(_eb["by_gen"]) > 1 else ""
        print("    - %s: 不発 %d/%d（%.0f%%）。%s%s"
              % (_band, _dry, _eb["n"], pct(_dry, _eb["n"]), _band_note[_band], _gens))
        # **報告見込みの MAJOR の verdict**（`scoring-rationale.md` の再検討条件の後半の代理）。
        # high はこの帯（confidence 95 以上の MAJOR）を反証にかけないので、xhigh 以上でしか見えない。
        # high の発火回にも MAJOR だけの回はあるが、それは high-risk surface の 85-94 帯で対象が違う
        _mo = _eb.get("major_only")
        if _band == "xhigh+" and _mo:
            _mv = sum(_mo[k] for k in VERDICT_KEYS)
            print("      - 報告見込みの MAJOR への verdict（上流の BLOCKER + CRITICAL が 0 件・閾値 MAJOR の"
                  "発火回。high はこの帯を反証にかけない）: %d 回・%d 件のうち refuted %d（%.0f%%）/ "
                  "severity_inflated %d（%.0f%%）/ confirmed %d（%.0f%%）"
                  % (_mo["n"], _mv, _mo["refuted"], pct(_mo["refuted"], _mv),
                     _mo["severity_inflated"], pct(_mo["severity_inflated"], _mv),
                     _mo["confirmed"], pct(_mo["confirmed"], _mv)))

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
          "`window=session` / `since-t0-late` で除外 %d 件・`tokens.schema` %d 未満"
          "（行ごとの重複計上込みの旧算法）で除外 %d 件。**v2.70.0 より前は review でしか"
          "載らなかった**ので、それ以前のサンプルには構造的に無い / GitHub issue #143）"
          % (len(tok_raw), tok_dropped_window, TOK_SCALE_MIN_SCHEMA, tok_dropped_schema))
else:
    line = ("**トークン**（t0 以降の窓 / n=%d/%d・`window=session` / `since-t0-late` で除外 %d・"
            "旧算法の `tokens.schema` で除外 %d）: "
            "main.output 中央値 %s / sub.output 中央値 %s"
            % (len(tok_rows), len(tok_raw), tok_dropped_window, tok_dropped_schema,
               "-" if median(tok_main) is None else "%g k" % median(tok_main),
               "-" if median(tok_sub) is None else "%g k" % median(tok_sub)))
    if tok_r is not None:
        line += " / 体数 vs sub.output r=%.2f（n=%d）" % (tok_r, len(txs))
    print(line + "。**壁時計の結論と混ぜない**（体数が効くのはこちら側 — triage-guide.md `## 7`）")
    print()
    if per_agent_rows:
        print("**1 体あたり cache_read**（effort × size_tier。旧基準値の 1 体 5,039k は"
              "行ごとの重複計上込みで**この表と直接比べられない**。比べるなら同じ世代の"
              "新算法の値（`pending-optimizations.md ## 計測の基準値`）。**体数キャップは広さを切っただけで"
              "ここには手が入っていない** / issue #156）")
        print()
        print("| effort/tier | n | 1 体あたり中央値 |")
        print("|---|---:|---:|")
        _pa_shown, _pa_dropped, _pa_dropped_n = cap_layer_rows(per_agent_rows)
        for key, n, m in _pa_shown:
            print("| %s | %d | %s |" % (key, n, "-" if m is None else "%.0f k" % m))
        _pa_note = layer_omission_note(_pa_dropped, _pa_dropped_n)
        if _pa_note:
            print()
            print(_pa_note)
    else:
        print("**1 体あたり cache_read**: 実測 0 件（`sub_cache_read_k` または `sub_agents` が"
              "欠測・0 で除算不可 %d）。旧算法の schema で落とした回はここではなくトークン行の"
              "除外件数に出る。除算不可が続くなら `measure-tokens.sh` の窓・引き当てが原因"
              "（issue #156）" % per_agent_undividable)

print()
# ---- 🔁 付録（「報告 0 件」と「価値 0」の分離 / GitHub issue #168） ----------
if not apx_rows and apx_missing:
    print("**🔁 付録**: 判定対象なし（**%d 件は報告件数を 1 つも申告しておらず母集団から"
          "外した** — 欠測を「報告 0」と読むと真の空振りの分子が膨らむ / #212）"
          % apx_missing)
if apx_rows:
    tot_listed = sum(r[0] for r in apx_rows)
    tot_rec = sum(r[1] for r in apx_rows)
    print("**🔁 付録**（n=%d / `appendix.schema` を持つ回だけ）: 列挙 %d 件 / うち人間に推した %d 件"
          % (len(apx_rows), tot_listed, tot_rec))
    # **世代別の真の空振り**（#214）。#210 の判定基準「20% 未満」を人が引き算せずに読める形。
    # 世代が 1 種しか無い母集団では表を割らない（`with_gen` と同じ方針）
    if len(apx_stats["by_gen"]) > 1:
        print()
        print("| 世代 | n | 報告 0 件 | うち推奨あり | 真の空振り | うち検出 0 | うち閾値未満のみ |")
        print("|---|---:|---:|---:|---:|---:|---:|")
        for _gk in sorted(apx_stats["by_gen"]):
            _gv = apx_stats["by_gen"][_gk]
            _unk = _gv.get("true_silent_unknown", 0)
            _unc = _gv.get("rescued_uncontracted", 0)
            _bl = _gv.get("true_silent_below_listed", 0)
            print("| %s | %d | %d | %d%s | %d（%.0f%%） | %d | %d%s%s |"
                  % (_gk, _gv["n"], _gv["silent"], _gv["rescued"],
                     "" if not _unc else "（上限 0 が %d）" % _unc,
                     _gv["true_silent"], pct(_gv["true_silent"], _gv["n"]),
                     _gv.get("true_silent_empty", 0), _gv.get("true_silent_below", 0),
                     "" if not _bl else "（付録あり %d）" % _bl,
                     "" if not _unk else "（判定不能 %d）" % _unk))
        print()
    # **内訳を読ませる**（#210）。混ぜたままだと回復サインがどちらの改善を求めているのか
    # 決まらない。**検出 0 = recall の問題 / 閾値未満のみ = 閾値・付録の方針の問題**
    if apx_stats["true_silent"]:
        print("- **真の空振りの内訳**: 検出 0 が %d 件 / 検出はあったが全部閾値未満が %d 件"
              "%s%s。**打ち手が違う** — 前者は reviewer が何も見つけていない（recall）、"
              "後者は見つけたものが `## below-threshold` に件数だけ返り、報告に出ない"
              "（閾値と付録の方針。契約 (a) では付録にも出ない — 付録の対象は「reviewer が列挙した"
              "指摘」だけ / scoring-guide.md）。**#210 の回復サインはこの内訳を見てから読む**"
              % (apx_stats["true_silent_empty"], apx_stats["true_silent_below"],
                 "" if not apx_stats["true_silent_below_listed"]
                 else "（うち %d 件は付録には出た — 推奨なし。付録が上限を超えた ＝ 閾値未満の本文が"
                      "混ざった回は %d 件 / #248）"
                      % (apx_stats["true_silent_below_listed"], apx_stats["true_silent_below_over"]),
                 "" if not apx_stats["true_silent_unknown"]
                 else " / 判定不能が %d 件（`pre_adjust_counts` 不在・語彙違反）"
                      % apx_stats["true_silent_unknown"]))
        print()
    # **契約外の行に救われた回**（#248）。真の空振り率の分母側（救われた回）がこの混入に支えられて
    # いると、混入が増えるか減るかだけで #210 の回復サインが動く
    if apx_stats["rescued_uncontracted"]:
        print("- **推奨で救われた回のうち、上限を判定できた %d 件中 %d 件は付録の上限が 0**（契約上は"
              "付録に 1 行も載らない回 ＝ 閾値未満に数えた指摘の本文に救われた / #248）。"
              "真の空振り率はこの混入が増えるか減るかだけでも動く"
              % (apx_stats["rescued_judged"], apx_stats["rescued_uncontracted"]))
        print()
    if apx_missing:
        print("- **%d 件は報告件数を 1 つも申告しておらず母集団から外した**"
              "（欠測を「報告 0」と読むと真の空振りの分子が膨らむ / #212）" % apx_missing)
    if apx_silent:
        print("- **報告 0 件の回 %d 件のうち %d 件は推奨あり**（＝空振りではない）。"
              "**この %d 件を「価値 0」として費用対効果の分子から落とさない** — "
              "体数キャップ・effort profile・閾値の判断が過小評価に倒れる（issue #168）"
              % (apx_silent, apx_rescued, apx_rescued))
    if tot_listed:
        # **推奨率そのものを見る**。全件が推奨に膨らむ失敗モードは、上限を置く代わりに
        # ここで観測して実測で判断する（`scoring-guide.md` の「推奨マーカー」）
        print("- 推奨率 %.0f%%（%d/%d）。**高止まりするなら定義が緩んでいる**"
              "（推奨は「修正コストが小さい」項目に限る規約 / issue #168）"
              % (tot_rec / tot_listed * 100, tot_rec, tot_listed))
    print()
else:
    print("**🔁 付録**: 実測 0 件（`appendix` を持つ回がまだ無い / issue #168）。"
          "**「推した指摘が無かった」ではなく「フィールドが載っていない」**")
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
    # **読み側で回収した入れ子を黙って母集団へ混ぜない**（#238）。publish が昇格を知らない
    # 版で焼かれた行で、gap を持たないので欠測内訳には出ない。0 件なら出さない（⚠️ 契約）
    if nested_recovered:
        print("  - 報告件数: %d 件は入れ子（`report_counts` / `counts`）からトップレベルへ"
              "昇格して母集団に戻した（旧版の publish が弾いていた回 / #238）" % nested_recovered)
    # **層別キーの回収と欠落も黙らない**（#252）。欠落した回は歩留まりの表に理由の無い
    # `threshold=?` 行として出るので、その内訳をここで言う。0 件なら出さない（⚠️ 契約）
    if threshold_recovered or threshold_missing:
        print("  - severity_threshold（歩留まりの母集団 / #252）: %d 件は入れ子からトップレベルへ回収 / "
              "%d 件は欠落で `threshold=?` に置いた"
              % (threshold_recovered, threshold_missing))
    # **定型レポートの率**（#250）。判定できた回が 1 件も無ければ出さない（⚠️ 契約）
    if report_template_rates:
        print("  - 定型レポート（publish の前に出したか / #250）: %s"
              % " / ".join("%s 判定 %d 件中 %d 件で定型なし" % (k, v["judged"], v["absent"])
                           for k, v in sorted(report_template_rates.items())))
    # **外した回を黙って消さない**（#246）。0 件なら出さない（⚠️ 契約）
    if session_suspects:
        print("  - transcript の取り違え疑い: %d 件（同じ transcript で窓が重なる %d 件 / "
              "agent を起動したのに sub が空 %d 件）。旧版の publish が「候補 dir の最新 .jsonl」で"
              "推定した回で、**`tokens` / `models` / `dispatch` を集計から外した**（世代は "
              "unrecorded に入る / #246）"
              % (sum(session_suspects.values()), session_suspects.get("overlap", 0),
                 session_suspects.get("sub-blank", 0)))
    # **`wave-split` の分母を明示する**（#192）。他の gap と母集団の意味が違ううえ、
    # `agents-mismatch` で判定を抑止された回は分母にも分子にも入らない。黙って落とすと
    # 「一括発行は守られている」と読まれる。**件数は現行式での再計算**（#200）
    if n_wave_judged or n_wave_suppressed:
        print("  - 一括発行: 判定できた %d 件中 %d 件が規約違反（**現行式で再計算**）"
              % (n_wave_judged, n_wave_split)
              + ("" if not n_wave_split else "。内訳（**推定**）: %s" % wave_split_kinds_txt())
              + ("" if not n_wave_suppressed else
                 "。**別に %d 件は `agents-mismatch` で判定を抑止**（分母にも分子にも"
                 "入らない — 守られたのではなく**測れていない**）" % n_wave_suppressed)
              + ("" if not n_wave_split_stale else
                 "。**%d 件は payload の `waves_expected` と判定が食い違う**"
                 "（publish 時点の式で焼かれた値。再計算した側が現行の判定 / #200）"
                 % n_wave_split_stale))
    # **下限未満で閾値を超えた層を保留として出す**（#209）。⚠️ が 1 本も出なかった
    # シグナルに限る — 鳴っているなら行動の根拠は既にあり、重ねると枠を食う。
    # **⚠️ には出さない**（下限未満は「まだ行動しない」という判断そのもの）が、
    # 黙ると「該当なし」と読まれるので、判定の保留として残す。
    # **あと何件で判定できるかを添える**（#230）。版で絞った窓では保留が主要な出力になり、
    # 件数が無いと「いつ読み直せばよいか」が決まらない。N は層の分母が下限に届くまでの件数で、
    # 届いた時点で閾値を超えているとは限らない（判定が「できる」であって「鳴る」ではない）
    _scope_txt = "絞り込んだ集計全体でも" if pending_filtered else "累計では"
    for _sig in sorted(layer_pending):
        for _k, _num, _den, _min in layer_pending[_sig][:2]:
            print("  - %s: `%s` 層が閾値を超えている（%d/%d）が、下限 %d に届かないので"
                  "**判定を保留**（**あと %d 件で判定可能** / %s閾値に届かず ⚠️ も出ていない）"
                  % (_sig, _k, _num, _den, _min, _min - _den, _scope_txt))
    # **分母を明示する**（#207 / `wave-split` と同じ流儀）。判定できた回が少ないうちは
    # 比率が閾値に届かず ⚠️ が出ないので、黙ると「fleet の打点は守られている」と読まれる
    if n_fleet_span_judged:
        print("  - fleet 区間: 判定できた %d 件中 %d 件が agent の起動スパンと矛盾"
              "（矛盾した回の `duration_fleet_min` は中央値・相関の分母から外す）"
              % (n_fleet_span_judged, n_fleet_span_conflict))
    # **欠測内訳から外した分を黙って消さない**（#211 / #192 と同じ流儀）。立った回が
    # 無ければ 1 行も出さない（「⚠️ が出たときだけ行動する」契約の可読性を守る）
    if n_agents_abandoned_marker or n_agents_nested_marker:
        print("  - `agents` の分解: 捨てられた試行がある回 %d 件 / 孫 agent がある回 %d 件"
              "（**欠測ではない** — コスト集計は総数、突合は `agents_completed` を見る）"
              % (n_agents_abandoned_marker, n_agents_nested_marker))
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
