"""計測の更新（`/code-review:metrics-update`）の決定的な部分。GitHub issue #480。

なぜ script か: 計測ストアを集計して関連 issue に返す作業を手で 6 回回したところ、集計を毎回その場で
python で書き直し、フィルタ（世代・再レビューの除外・transcript の取り違えが直った版）が揃わず、
前回どこまで見たかも残らなかった。比較表・前回からの差分・`## 15` の更新条件・語彙落ちの特定は
件数と比率で決まるので、ここに閉じる。どの issue にコメントするか・起票するか・ベースラインを
書き換えるかは SKILL.md の手順に残す。

入口は `metrics-update.sh`（手元のログを `review_event_logs` で解決して渡す）。`review-retro.sh` は変えない
（publish 直後に毎回出す 40 行・⚠️ のときだけ行動する、の出力契約を崩さない）。

判定は retro と揃える: 世代（`gen_of`）・再レビュー（`is_rereview`）・delta（`scope_mode_of`）の正本は
`review-retro.sh` のヒアドキュメントの中にあって import できないので、同じ式をここに書く。
`test_code_review_metrics_update.py` が retro の本文から関数を切り出して突き合わせる。

出力にマシンの生の名前とリポジトリのパスを出さない（retro と同じく `lib/machine_label.py` で伏せる）。
語彙落ちの差分（生の値を含みうる）は手元表示用で、公開先に貼らない。

終了コード: 0 = 正常（0 件・ストアが無いときも `--json` は必ず JSON を返す）/
2 = 判定不能（引数の誤り・明示したパスが読めない・状態ファイルが壊れている・書き込みの失敗・未捕捉の例外）。
"""

import argparse
import ast
import copy
from collections import Counter
import json
import os
import re
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime, timezone

sys.dont_write_bytecode = True    # mutation-ok: 配布物の `lib/` に `__pycache__` を作らせないだけで、判定にも出力にも効かない

# 上の行より後に import する（前に置くと、この import で `lib/__pycache__` が作られる）
from event_dedup import EventDeduper, SANITIZED, REWRITTEN_TOP_KEYS  # noqa: E402
from machine_label import STORE_DIR, Aliaser, hmac8, tilde  # noqa: E402
from report_counts import REPORT_KEYS, lift_nested_report_counts  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(os.path.dirname(HERE))
DEFAULT_BASELINE_DOC = os.path.join(PLUGIN_ROOT, "references", "orchestration-measurement.md")
DEFAULT_PLUGIN_JSON = os.path.join(PLUGIN_ROOT, ".claude-plugin", "plugin.json")
DEFAULT_STATE = os.path.join(os.path.expanduser("~"), ".claude", "code-review", "metrics-update-state.json")

STATE_SCHEMA = 1
#: dispatch と tokens を読んでよい最小の版。transcript の取り違え（#246）が直った版（`## 15` の注記）
RELIABLE_SINCE = "2.130.6"
#: tokens.schema 3 で usage の算法が変わり、スケールがおよそ半分になった（retro の `TOK_SCALE_MIN_SCHEMA`）
TOK_SCALE_MIN_SCHEMA = 3
#: `## 15` の更新条件の既定（xhigh 以上の review の件数）
DEFAULT_XHIGH_NEED = 5
BASELINE_SECTION = "## 15."
BASELINE_RE = re.compile(r"<!--\s*METRICS-BASELINE:(.*?)-->", re.S)
VERSION_RE = re.compile(r"[0-9]+(?:\.[0-9]+)*")
#: 世代の分かる直近のこの回数に印の世代が 1 回も無ければ「世代が変わった」とする
ABSENT_WINDOW = 4
#: 差分に出す commit の上限（超えた分は件数だけ出す）
LOG_LIMIT = 30
#: 語彙落ちの回を列挙する上限
DROPS_LIMIT = 20


# ---- retro と同じ判定（正本は review-retro.sh。parity テストで縛る） ------------------

def gen_of(p):
    m = p.get("models")
    if not isinstance(m, dict):
        return "unrecorded"
    v = m.get("main")
    if not isinstance(v, str) or not v:
        return "mixed"
    return v[len("claude-"):] if v.startswith("claude-") else v


def is_rereview(p):
    inv = p.get("invocation")
    return isinstance(inv, dict) and inv.get("rereview") is True


def scope_mode_of(p):
    sc = p.get("review_scope")
    mode = sc.get("mode") if isinstance(sc, dict) else None
    return mode if mode in ("delta", "full") else "full"


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def schema_of(d, key):
    try:
        return int(d.get(key) or 1)
    except (TypeError, ValueError):
        return 1


def median(xs):
    if not xs:
        return None
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def version_tuple(v):
    t = tuple(int(x) for x in v.split("."))
    return t + (0,) * (3 - len(t))


def version_of(p):
    """payload の `plugin_version`。数字とドットの形でなければ None（推測で層に入れない）."""
    v = p.get("plugin_version")
    return v if isinstance(v, str) and VERSION_RE.fullmatch(v) else None


def reliable(p):
    v = version_of(p)
    return v is not None and version_tuple(v) >= version_tuple(RELIABLE_SINCE)


# ---- 入力 -------------------------------------------------------------------

def read_events(path):
    """1 ファイルの `review:completed` 行を返す。JSON として読めない行と payload が dict でない行は飛ばし、
    文字列でない `ts` / `plugin` はここで空と None に倒す（dict のキーに使うので、配列のままだと集計全体が落ちる。
    `ts` が空の行は dedup が payload 全体をキーにする）。`effort` / `size_tier` は `comparison` が `?` に倒す."""
    out = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            # JSON を読む前に行を減らす近道（空行もここで落ちる）
            if '"review:completed"' not in line:
                continue  # mutation-ok: 読み進めても、空行は json.loads が、他の event は下の判定が落とす（違うのは event 名を \u でエスケープした行だけ）
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if isinstance(ev, dict) and ev.get("event") == "review:completed" \
                    and isinstance(ev.get("payload"), dict):
                ev["ts"] = text_of(ev.get("ts"), "")
                ev["plugin"] = text_of(ev.get("plugin"), None)
                out.append(ev)
    return out


def store_files(store):
    d = os.path.join(store, "events")
    if not os.path.isdir(d):
        return []
    return sorted(os.path.join(d, n) for n in os.listdir(d) if n.endswith(".jsonl"))


def resolve_store(arg, no_store):
    """(ストアの dir か None, 明示されたか)。既定の場所に無ければ飛ばし、明示して無ければ呼び出し側が止める."""
    if no_store:
        return None, False
    if arg:
        return arg, True
    d = os.environ.get("REVIEW_METRICS_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "review-metrics")
    return (d if os.path.isdir(os.path.join(d, "events")) else None), False


def text_of(v, default):
    """文字列の値だけを採る。型の崩れた行（`ts` が数値・`effort` が配列など）1 行で集計全体を止めない."""
    return v if isinstance(v, str) and v else default


def load_population(store_paths, local_paths):
    """ストア → 手元の順に dedup する。語彙落ちの照合用に、昇格前の payload の索引も返す."""
    dedup = EventDeduper()
    store_index, local_index, rows_by_src = {}, {}, {}
    seen_real = set()
    for kind, paths in (("store", store_paths), ("local", local_paths)):
        for path in paths:
            real = os.path.realpath(path)
            if real in seen_real:
                continue
            seen_real.add(real)
            evs = read_events(path)
            rows_by_src[path] = (kind, len(evs))
            for ev in evs:
                key = (ev.get("ts"), ev.get("plugin"))
                (store_index if kind == "store" else local_index)[key] = copy.deepcopy(ev["payload"])
                dedup.add(ev, path)
    rows = []
    for ev, src in dedup.events():
        p = ev["payload"]
        lift_nested_report_counts(p)
        rows.append({"ts": text_of(ev.get("ts"), ""), "plugin": text_of(ev.get("plugin"), ""), "p": p, "src": src})
    return rows, dedup, store_index, local_index, rows_by_src


# ---- 状態（前回の実行時点） --------------------------------------------------------

class StateError(Exception):
    pass


def load_state(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError) as exc:
        raise StateError("状態ファイルを読めない: %s（%s）" % (state_display(path), exc.__class__.__name__))
    if not isinstance(st, dict) or st.get("schema_version") != STATE_SCHEMA:
        raise StateError("状態ファイルの形が違う（schema_version %d を期待）: %s" % (STATE_SCHEMA, state_display(path)))
    seen = st.get("last_ts_by_machine")
    if not (isinstance(seen, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in seen.items())):
        raise StateError("状態ファイルの last_ts_by_machine が「マシン → ts の文字列」の辞書でない: %s" % state_display(path))
    if not (st.get("main_commit") is None or isinstance(st.get("main_commit"), str)):
        raise StateError("状態ファイルの main_commit が文字列でない: %s" % state_display(path))
    return st


def state_display(path):
    """状態ファイルの表示名。既定の場所だけ `~` 始まりで出し、`--state` で渡した場所はパスを出さない."""
    if os.path.abspath(path) == os.path.abspath(DEFAULT_STATE):
        return tilde(os.path.abspath(path))
    return "--state のファイル"


def save_state(path, st):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".metrics-update-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2, sort_keys=True)  # mutation-ok: 書式だけの違いで、load_state が読み戻す値は同じ
            f.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ---- git -----------------------------------------------------------------------

def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def git_info(repo):
    """main の commit。origin/main を先に見る（手元の main は取り込みを忘れると古い）."""
    if not repo or git(repo, "rev-parse", "--git-dir") is None:
        return {"present": False, "main_commit": None, "ref": None}
    for ref in ("refs/remotes/origin/main", "refs/heads/main"):
        sha = git(repo, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
        if sha:
            return {"present": True, "main_commit": sha, "ref": ref.split("/", 2)[2]}
    return {"present": True, "main_commit": None, "ref": None}


def git_log_since(repo, prev, cur):
    """前回の main から今の main までに `code-review/` を触った commit."""
    if not (prev and cur):
        return {"reason": "no-previous" if not prev else "no-main", "commits": [], "total": 0}
    if prev == cur:
        return {"reason": None, "commits": [], "total": 0}  # mutation-ok: 外しても下の git log の範囲 prev..prev が空で、同じ値を返す
    if git(repo, "cat-file", "-e", prev + "^{commit}") is None:
        return {"reason": "prev-unreachable", "commits": [], "total": 0}
    out = git(repo, "log", "--format=%h %cs %s", "%s..%s" % (prev, cur), "--", "code-review/")
    if out is None:
        return {"reason": "log-failed", "commits": [], "total": 0}
    lines = [ln for ln in out.splitlines() if ln]
    return {"reason": None, "commits": lines[:LOG_LIMIT], "total": len(lines)}


# ---- 前回からの差分 ---------------------------------------------------------------

def machine_of(row, aliaser):
    return aliaser.machine(row["p"].get("machine_id")) or "未記録"


def last_ts_by_machine(rows, aliaser):
    out = {}
    for r in rows:
        m = machine_of(r, aliaser)
        if r["ts"] > out.get(m, ""):
            out[m] = r["ts"]
    return out


def diff_since(rows, state, aliaser):
    """前回の記録より後の回。マシンごとの最新の ts で切る — 別のマシンの回は後から同期されるので、
    全体の最新の ts で切ると、前回より前の時刻で publish されて後から届いた回を落とす."""
    if state is None:
        return {"first_run": True, "n": len(rows), "by_machine": {}, "by_plugin": {}, "by_version": {}}
    seen = state["last_ts_by_machine"]
    new = [r for r in rows if r["ts"] > seen.get(machine_of(r, aliaser), "")]
    return {
        "first_run": False,
        "n": len(new),
        "by_machine": dict(sorted(Counter(machine_of(r, aliaser) for r in new).items())),
        "by_plugin": dict(sorted(Counter(r["plugin"] for r in new).items())),
        "by_version": dict(sorted(Counter(version_of(r["p"]) or "未記録" for r in new).items())),
    }


# ---- 比較表 ----------------------------------------------------------------------

def version_group(p, split):
    if split is None:
        return None
    v = version_of(p)
    if v is None:
        return "版未記録"
    return ("%s 以上" if version_tuple(v) >= version_tuple(split) else "%s より前") % split


def tokens_ok(p):
    t = p.get("tokens")
    return (isinstance(t, dict) and schema_of(t, "schema") >= TOK_SCALE_MIN_SCHEMA
            and t.get("window") == "since-t0" and reliable(p))


def dispatch_missing(p):
    gaps = p.get("measurement_gaps")
    return not isinstance(p.get("dispatch"), dict) or (isinstance(gaps, list) and "dispatch" in gaps)


def comparison(rows, split=None, generation=None):
    """世代 × effort × size_tier × delta/full（× 版の前後）で割った中央値の表。`generation` で 1 世代に絞る."""
    groups = {}
    rereview = 0
    for r in rows:
        p = r["p"]
        if generation is not None and gen_of(p) != generation:
            continue
        if is_rereview(p):
            rereview += 1
            continue
        key = (gen_of(p), text_of(p.get("effort"), "?"), text_of(p.get("size_tier"), "?"), scope_mode_of(p),
               version_group(p, split))
        groups.setdefault(key, []).append(p)
    table = []
    for key in sorted(groups, key=lambda k: tuple("" if x is None else str(x) for x in k)):
        ps = groups[key]

        def med(field, src=ps):
            return median([v for v in (num(q.get(field)) for q in src) if v is not None and v >= 0])

        reported = [sum(q[k] for k in REPORT_KEYS) for q in ps
                    if all(num(q.get(k)) is not None for k in REPORT_KEYS)]
        tok = [q["tokens"] for q in ps if tokens_ok(q)]
        rel = [q for q in ps if reliable(q)]
        miss = [q for q in rel if dispatch_missing(q)]
        inter = [num(q["dispatch"].get("max_inter_wave_sec")) for q in rel if not dispatch_missing(q)]

        def tmed(field):
            return median([v for v in (num(t.get(field)) for t in tok) if v is not None])

        table.append({
            "generation": key[0], "effort": key[1], "size_tier": key[2], "scope": key[3],
            "version_group": key[4], "n": len(ps),
            "fleet_min": med("duration_fleet_min"), "duration_min": med("duration_min"),
            "reported": median(reported), "reported_n": len(reported),
            "main_output_k": tmed("main_output_k"), "sub_output_k": tmed("sub_output_k"),
            "sub_cache_read_k": tmed("sub_cache_read_k"), "tokens_n": len(tok),
            "dispatch_missing": len(miss), "dispatch_n": len(rel),
            "max_inter_wave_sec": median([v for v in inter if v is not None and v >= 0]),
        })
    return {"rereview_excluded": rereview, "split_version": split, "generation": generation, "rows": table}


# ---- `## 15` の更新条件 -----------------------------------------------------------

def parse_baseline_marker(text):
    """`## 15.` の節にある `<!-- METRICS-BASELINE: k=v ... -->`。無い・壊れているときは status で返す."""
    start = text.find("\n" + BASELINE_SECTION)
    if start < 0:
        return {"status": "no-section"}
    end = text.find("\n## ", start + 1)
    if end == -1:
        end = len(text)
    m = BASELINE_RE.search(text[start:end])
    if not m:
        return {"status": "no-marker"}
    kv = {}
    for tok in m.group(1).split():
        k, sep, v = tok.partition("=")
        if not sep or not v:
            return {"status": "malformed"}
        kv[k] = v
    gen, taken = kv.get("generation"), kv.get("taken")
    try:
        datetime.strptime(taken or "", "%Y-%m-%d")
        need = int(kv.get("review_xhigh_need", DEFAULT_XHIGH_NEED))
    except ValueError:
        return {"status": "malformed"}
    if not gen:
        return {"status": "malformed"}
    if gen.startswith("claude-"):
        gen = gen[len("claude-"):]
    return {"status": "ok", "generation": gen, "taken": taken, "review_xhigh_need": need}


def baseline_due(rows, marker):
    if marker.get("status") != "ok":
        return {"marker": marker, "due": None}
    taken = marker["taken"]
    # `taken` は表に入れた最後の回の翌日なので、その日の回から数える。ts は UTC の日付で比べる
    after = [r for r in rows if r["ts"][:10] >= taken]
    counter = Counter(gen_of(r["p"]) for r in after)
    gen_counts = dict(sorted(counter.items()))
    # 印の世代が直近 ABSENT_WINDOW 回から消えたら「変わった」とする（マシンをまたいで時刻順）。最新の 1 回で決めると
    # 比べるために別のモデルで 1 回回しただけで変わり、件数の多さで決めると旧世代の累計を新しい世代が上回るまで
    # （実測で数百件）変わらない。「新しい世代が 2 回続いた」で決めると、マシンごとに世代が違う時期に
    # 旧世代のマシンが 1 回回るたびに判定が戻る
    known = sorted((r for r in after if gen_of(r["p"]) not in ("unrecorded", "mixed")), key=lambda r: r["ts"])
    window = [gen_of(r["p"]) for r in known[-ABSENT_WINDOW:]]
    changed = len(window) == ABSENT_WINDOW and marker["generation"] not in window
    xhigh = sum(1 for r in after
                if r["plugin"] == "code-review:review" and r["p"].get("effort") in ("xhigh", "max")
                and not is_rereview(r["p"]) and gen_of(r["p"]) == marker["generation"])
    need = marker["review_xhigh_need"]
    # need が 0 の印は「xhigh の条件は消化済みで、次は世代が変わったとき」（`## 15` の更新の条件の文面）
    return {"marker": marker, "window_generations": window, "generation_changed": changed,
            "gen_counts_since_taken": gen_counts, "xhigh_review_n": xhigh, "xhigh_need": need,
            "due": changed or (need > 0 and xhigh >= need)}


# ---- 語彙落ち ---------------------------------------------------------------------

def deny_keys(store):
    """計測ストアの `bin/sanitize.py` の `DENY_KEYS`（意図して落とすキー）。読めなければ空."""
    if not store:
        return frozenset()
    try:
        with open(os.path.join(store, "bin", "sanitize.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError, ValueError):
        return frozenset()
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "DENY_KEYS"):
            value = node.value
            if isinstance(value, ast.Call) and len(value.args) == 1:
                value = value.args[0]
            try:
                keys = ast.literal_eval(value)
            except (ValueError, TypeError):
                return frozenset()
            if isinstance(keys, (set, frozenset, list, tuple)) and all(isinstance(k, str) for k in keys):
                return frozenset(keys)
    return frozenset()


def sanitize_diff(rich, poor, deny, path="", top=True, out=None):
    """生の payload（rich）とストアの payload（poor）の差。`event_dedup.covers` と同じ規則の裏返し."""
    if out is None:
        out = {"keys": [], "denied_keys": [], "values": [], "coverage": []}
    if isinstance(rich, dict) and isinstance(poor, dict):
        for k, v in rich.items():
            if top and k in REWRITTEN_TOP_KEYS:
                continue
            sub = "%s.%s" % (path, k) if path else k
            if k not in poor:
                out["denied_keys" if k in deny else "keys"].append(sub)
            else:
                sanitize_diff(v, poor[k], deny, sub, False, out)
    elif isinstance(rich, list) and isinstance(poor, list):
        for i, (r, q) in enumerate(zip(rich, poor)):
            sanitize_diff(r, q, deny, "%s[%d]" % (path, i), False, out)
    elif isinstance(rich, str) and isinstance(poor, str) and rich != poor:
        replaced = poor == SANITIZED or SANITIZED in poor.split(":")
        if replaced:
            bucket = "coverage" if path.startswith("missing_coverage[") else "values"
            out[bucket].append({"path": path, "value": rich})
    return out


def vocab_drops(store_index, local_index, deny):
    runs = []
    for (ts, plugin), p in sorted(store_index.items(), key=lambda kv: str(kv[0][0])):
        d = p.get("sanitize_drops")
        counts = {k: num(d.get(k)) or 0 for k in ("keys", "coverage", "values")} if isinstance(d, dict) else {}
        if not any(counts.values()):
            continue
        raw = local_index.get((ts, plugin))
        runs.append({"ts": ts, "plugin": plugin, "counts": counts, "version": version_of(p),
                     "raw_found": raw is not None,
                     "diff": sanitize_diff(raw, p, deny) if raw is not None else None})
    return runs


# ---- 組み立てと出力 ------------------------------------------------------------------

def plugin_version(path):
    try:
        with open(path, encoding="utf-8") as f:
            v = json.load(f).get("version")
        return v if isinstance(v, str) else None
    except (OSError, ValueError, AttributeError):
        return None


def store_display(store, aliaser):
    """ストアの表示名。`$HOME` 配下の `review-metrics` だけ `~` 始まりで出し、それ以外は HMAC にする
    （dir の名前に何が入っているか分からない。`Aliaser.path` がストアを名前で判定するのと同じ方針）."""
    shown = tilde(os.path.abspath(store), aliaser.home)
    if shown.startswith("~") and os.path.basename(os.path.normpath(store)) == STORE_DIR:
        return shown
    return "<store sha=%s>" % hmac8(aliaser.salt, os.path.realpath(store))


def store_file_display(path, store_shown, aliaser):
    stem = os.path.splitext(os.path.basename(path))[0]
    return "%s/events/%s.jsonl" % (store_shown, aliaser.machine(stem))


def build(args, aliaser):
    store, store_explicit = resolve_store(args.store, args.no_store)
    if store_explicit and not os.path.isdir(os.path.join(store, "events")):
        raise StateError("--store に events/ が無い: %s" % store_display(store, aliaser))
    for path in args.logs:
        if not os.path.isfile(path):
            raise StateError("--logs のパスが読めない: %s" % aliaser.path(path))
    store_paths = store_files(store) if store else []
    rows, dedup, store_index, local_index, rows_by_src = load_population(store_paths, args.logs)
    state = load_state(args.state)
    gi = git_info(args.repo)
    try:
        with open(args.baseline_doc, encoding="utf-8") as f:
            marker = parse_baseline_marker(f.read())
    except OSError:
        marker = {"status": "no-doc"}
    drops = vocab_drops(store_index, local_index, deny_keys(store))
    store_shown = store_display(store, aliaser) if store else None
    return {
        "scope": {
            "store": store_shown,
            "store_files": [{"path": store_file_display(p, store_shown, aliaser), "rows": rows_by_src[p][1]}
                            for p in store_paths if p in rows_by_src],
            "local_logs": [{"path": aliaser.path(p), "rows": rows_by_src[p][1]}
                           for p in args.logs if p in rows_by_src],
            "n": len(rows), "dedup_dropped": dedup.dropped, "dedup_conflicts": len(dedup.conflicts),
            "main_commit": gi["main_commit"], "main_ref": gi["ref"],
            "plugin_version": plugin_version(args.plugin_json),
            "previous": ({k: state.get(k) for k in ("recorded_at", "main_commit", "n", "plugin_version")}
                         if state else None),
        },
        "since_previous": diff_since(rows, state, aliaser),
        "commits": git_log_since(args.repo, state.get("main_commit") if state else None, gi["main_commit"]),
        "comparison": comparison(rows, args.split_version, args.generation),
        "baseline": baseline_due(rows, marker),
        "vocab_drops": {"local_only": True, "runs": drops},
        "_state": {
            "schema_version": STATE_SCHEMA,
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "main_commit": gi["main_commit"], "n": len(rows),
            "store_rows": sum(rows_by_src[p][1] for p in store_paths if p in rows_by_src),
            "plugin_version": plugin_version(args.plugin_json),
            "last_ts_by_machine": last_ts_by_machine(rows, aliaser),
        },
    }


def fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return ("%.1f" % v).rstrip("0").rstrip(".")
    return str(v)


def short(sha):
    return sha[:7] if sha else "未取得"


def render_text(res):
    sc, out = res["scope"], []
    out.append("## 計測の更新（metrics-update）")
    files = ", ".join("%s %d 行" % (f["path"], f["rows"]) for f in sc["store_files"])
    out.append("- ストア: %s" % ("%s（%s）" % (sc["store"], files or "events なし") if sc["store"] else "なし（手元のログだけで集計）"))
    logs = ", ".join("%s %d 行" % (f["path"], f["rows"]) for f in sc["local_logs"])
    out.append("- 手元のログ: %s" % (logs or "なし"))
    out.append("- 合算: n=%d（重複で除いた行 %d・食い違い %d）" % (sc["n"], sc["dedup_dropped"], sc["dedup_conflicts"]))
    out.append("- main: %s（%s）/ code-review %s" % (short(sc["main_commit"]), sc["main_ref"] or "-",
                                                    sc["plugin_version"] or "未取得"))
    pv = sc["previous"]
    out.append("- 前回の記録: %s" % ("%s（main %s・n=%s・版 %s）" % (pv["recorded_at"], short(pv["main_commit"]), pv["n"],
                                                                pv["plugin_version"]) if pv else "なし（初回）"))
    out.append("")
    out.append("### 前回からの差分")
    sp = res["since_previous"]
    if sp["first_run"]:
        out.append("- 前回の記録が無いので差分は出さない（全 %d 件を見た）。`--record` で今回を記録する" % sp["n"])
    else:
        out.append("- 新しい回: %d 件" % sp["n"])
        for label, key in (("マシン", "by_machine"), ("plugin", "by_plugin"), ("版", "by_version")):
            if sp[key]:
                out.append("  - %s: %s" % (label, " / ".join("%s %d" % kv for kv in sp[key].items())))
    cm = res["commits"]
    if cm["reason"]:
        out.append("- code-review/ の commit: 出せない（%s）" % cm["reason"])
    else:
        out.append("- code-review/ を触った commit: %d 件" % cm["total"])
        out.extend("  - %s" % c for c in cm["commits"])
        if cm["total"] > len(cm["commits"]):
            out.append("  - ほか %d 件" % (cm["total"] - len(cm["commits"])))
    out.append("")
    cp = res["comparison"]
    out.append("### 比較表（%s再レビューを除く。除いた回 %d 件）"
               % ("世代 %s・" % cp["generation"] if cp["generation"] else "", cp["rereview_excluded"]))
    out.append("> 中央値。トークンと dispatch は %s 以上・tokens.schema %d 以上の回だけ（括弧内は母数）"
               % (RELIABLE_SINCE, TOK_SCALE_MIN_SCHEMA))
    head = ["世代", "effort", "size", "範囲"] + (["版"] if cp["split_version"] else []) + \
        ["n", "fleet 分", "全体 分", "報告件数", "main out k", "sub out k", "sub cache_read k",
         "dispatch 欠測", "最大 wave 間隔 秒"]
    out.append("| " + " | ".join(head) + " |")
    out.append("|" + "---|" * len(head))
    for r in cp["rows"]:
        cells = [r["generation"], r["effort"], r["size_tier"], r["scope"]] + \
            ([r["version_group"]] if cp["split_version"] else []) + \
            [fmt(r["n"]), fmt(r["fleet_min"]), fmt(r["duration_min"]),
             "%s（%d）" % (fmt(r["reported"]), r["reported_n"]),
             "%s（%d）" % (fmt(r["main_output_k"]), r["tokens_n"]), fmt(r["sub_output_k"]),
             fmt(r["sub_cache_read_k"]), "%d/%d" % (r["dispatch_missing"], r["dispatch_n"]),
             fmt(r["max_inter_wave_sec"])]
        out.append("| " + " | ".join(cells) + " |")
    out.append("")
    bl = res["baseline"]
    out.append("### `## 15` の更新条件")
    mk = bl["marker"]
    if mk.get("status") != "ok":
        out.append("- 判定できない（印: %s）。orchestration-measurement.md `## 15` の METRICS-BASELINE の印を確かめる"
                   % mk.get("status"))
    else:
        out.append("- 印: 世代 %s・取り直し %s" % (mk["generation"], mk["taken"]))
        xh = ("取り直し以降の xhigh 以上の review %d/%d 件" % (bl["xhigh_review_n"], bl["xhigh_need"])
              if bl["xhigh_need"] > 0 else "xhigh の条件は消化済み（取り直し以降の xhigh 以上の review %d 件）"
              % bl["xhigh_review_n"])
        out.append("- 判定: %s（直近 4 回の世代 %s%s・%s）"
                   % ("更新の時期" if bl["due"] else "まだ", " → ".join(bl["window_generations"]) or "-",
                      "（変わった）" if bl["generation_changed"] else "", xh))
    out.append("")
    runs = res["vocab_drops"]["runs"]
    out.append("### 語彙落ち（計測ストアの同期で落とした回）: %d 件" % len(runs))
    if runs:
        out.append("> 下の値は手元表示のみ。公開先に貼らない（業務の語を含みうる）")
    for r in runs[-DROPS_LIMIT:]:
        line = "- %s %s（版 %s）キー %d・観点 %d・値 %d" % (r["ts"], r["plugin"], r["version"] or "未記録",
                                                    r["counts"]["keys"], r["counts"]["coverage"], r["counts"]["values"])
        if not r["raw_found"]:
            line += " — 手元に生の行なし（publish したマシンで回す）"
        out.append(line)
        if r["diff"]:
            d = r["diff"]
            for k in d["keys"]:
                out.append("  - 落ちたキー: %s" % k)
            for v in d["values"] + d["coverage"]:
                out.append("  - other になった値: %s = %s" % (v["path"], v["value"]))
            if d["denied_keys"]:
                out.append("  - 意図して落とすキー（DENY_KEYS）: %s" % ", ".join(d["denied_keys"]))
    if len(runs) > DROPS_LIMIT:
        out.append("- ほか %d 件（古い順に省略）" % (len(runs) - DROPS_LIMIT))
    return "\n".join(out)


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="metrics-update.sh")
    ap.add_argument("--logs", nargs="*", default=[])
    ap.add_argument("--store")
    ap.add_argument("--no-store", action="store_true")
    ap.add_argument("--state", default=DEFAULT_STATE)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--split-version")
    ap.add_argument("--generation", help="比較表を 1 世代に絞る（`opus-5-5` の形。`claude-` は付けても外す）")
    ap.add_argument("--repo", default=os.getcwd())
    ap.add_argument("--baseline-doc", default=DEFAULT_BASELINE_DOC)
    ap.add_argument("--plugin-json", default=DEFAULT_PLUGIN_JSON)
    ap.add_argument("--list-sources", action="store_true",
                    help="retro に渡すログ（ストアの events と手元のログ）を 1 行ずつ出して終える")
    args = ap.parse_args(argv)
    if args.split_version is not None and not VERSION_RE.fullmatch(args.split_version):
        ap.error("--split-version は数字とドットの版で指定する（受領: %r）" % args.split_version)
    if args.generation and args.generation.startswith("claude-"):
        args.generation = args.generation[len("claude-"):]
    if args.store and args.no_store:
        ap.error("--store と --no-store は同時に指定しない")
    return args


def main(argv):
    try:
        args = parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    try:
        if args.list_sources:
            store, explicit = resolve_store(args.store, args.no_store)
            if explicit and not os.path.isdir(os.path.join(store, "events")):
                raise StateError("--store に events/ が無い: %s" % store_display(store, Aliaser()))
            for p in (store_files(store) if store else []) + args.logs:
                print(p)
            return 0
        aliaser = Aliaser()
        res = build(args, aliaser)
        state = res.pop("_state")
        print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else render_text(res))
        if args.record:
            save_state(args.state, state)
            sys.stderr.write("記録した: %s（main %s・n=%d・版 %s）\n"
                             % (state_display(args.state), short(state["main_commit"]), state["n"],
                                state["plugin_version"] or "未取得"))
        return 0
    except StateError as exc:
        sys.stderr.write("FATAL: %s\n" % exc)
        return 2
    except Exception as exc:
        # traceback 全体は出さない（例外のメッセージと引数に生のパスが入る）。型と発生した行だけを出す
        tb = traceback.extract_tb(exc.__traceback__)
        where = "%s:%d" % (os.path.basename(tb[-1].filename), tb[-1].lineno) if tb else "?"
        sys.stderr.write("FATAL: 集計が異常終了した（%s at %s）\n" % (exc.__class__.__name__, where))
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
