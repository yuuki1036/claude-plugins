"""reviewer の構成を決め（`plan`）、確定したテーブルを検算する（`check`）。GitHub issue #351。

**数値と順の正本は triage-guide.md**（`## 7` の effort 表・`## 6.2` の規模キャップ・`## 4` 末尾の
単独維持の順・`## 7` の単独維持の観点と設計バンドル）。ここにあるのはその複製で、
`test_code_review_reviewer_plan.py` が表を読んで突き合わせる（#295 の `PATTERN_MIN_FILES` と同じ扱い）。

なぜ script か: 構成を LLM が手順書を読んで数えると、上限の数え違い（high の 6 を 5 とした）と順の取り違え
（spec-compliance より security を先に取った）が起き、起動前の検算も同じ LLM が回すので止まらなかった。
観点の起動条件の判定（シグナルの閾値の読み）は LLM に残し、そこから先の数え上げをここで決める。

入口は `plan-reviewers.sh`（一時ファイルのパス・作業ツリー・ブランチを解決して渡す）。
終了コード: 0 = 正常 / 1 = check が規則違反を見つけた・plan を書けない / 2 = 引数・入力の誤り。
"""

import argparse
import json
from collections import Counter
import os
import re
import sys

sys.dont_write_bytecode = True    # mutation-ok: 配布物の `lib/` に `__pycache__` を作らせないだけで、判定にも出力にも効かない

# 上の行より後に import する（前に置くと、この import で `lib/__pycache__` が作られる）
import doc_locate  # noqa: E402

# triage-guide `## 3` の観点判定表のキー（18 観点）
FOCUS_KEYS = (
    "bug-detection", "claude-md-compliance", "error-handling", "comment-accuracy",
    "test-quality", "type-design", "security", "performance", "api-design",
    "dependency", "migration", "config", "cross-cutting", "layer-responsibility",
    "pattern-consistency", "spec-compliance", "ui-quality", "doc-substance",
)
MIN_GUARANTEE = ("bug-detection", "claude-md-compliance")
# `## 4` 末尾「単独維持の観点が上限に収まらないときの順」
SOLO_ORDER = ("bug-detection", "claude-md-compliance", "spec-compliance", "security",
              "layer-responsibility")
SOLO = frozenset(SOLO_ORDER)
# `## 7` の設計バンドル（low / medium のみ。layer-responsibility の単独維持を外す）
DESIGN_ORDER = ("layer-responsibility", "cross-cutting", "type-design", "pattern-consistency")
DESIGN = frozenset(DESIGN_ORDER)
DESIGN_EFFORTS = frozenset(("low", "medium"))
BUNDLE_MAX = 3
DESIGN_BUNDLE_MAX = 4
# 束ねる順（#351 で決めたもの。triage-guide に順の規定は無い）。隣どうしが同じ reviewer に入りやすい。
# 先頭 3 つと config・dependency の隣接は `## 7` の束ねの例に合わせた。あふれたときは後ろから落ちる
ADJACENCY = (
    "error-handling", "comment-accuracy", "type-design", "cross-cutting", "pattern-consistency",
    "test-quality", "performance", "api-design", "migration", "config", "dependency",
    "ui-quality", "doc-substance",
)

# `## 7` の effort 側上限
EFFORT_CAP = {
    "reviewer": {"low": 4, "medium": 4, "high": 6, "xhigh": 10, "max": 10},
    "explorer": {"low": 2, "medium": 2, "high": 4, "xhigh": 6, "max": 6},
    "specialist": {"low": 3, "medium": 3, "high": 3, "xhigh": 6, "max": 6},
}
# `## 6.2` の規模キャップ（None = キャップなし）
SIZE_CAP = {
    "reviewer": {"small": 3, "medium": 5, "large": None},
    "explorer": {"small": 0, "medium": 2, "large": None},
    "specialist": {"small": 1, "medium": 2, "large": None},
}
EFFORTS = tuple(EFFORT_CAP["reviewer"])
SIZE_TIERS = ("small", "medium", "large", "unknown")
REDUNDANT_EFFORTS = frozenset(("xhigh", "max"))
SPEC_SOURCE_LABELS = ("pr-issue", "knowledge")
# plan が diff と参照から見つける repo の仕様書（GitHub issue #352）。`--spec-source` では渡せない
# （SPEC_SOURCE_LABELS に入れない）: touched = diff が触った、ref = session-context・Issue ファイル・PR 本文が言及した
SPEC_DOC_LABELS = ("repo-spec-touched", "repo-spec-ref")
PR_BODY_HEADING = "### PR 説明"
# fetch-pr-context.sh が PR 本文の次に出す見出し。PR 本文の中の `### ` 見出しでは打ち切らない
PR_BODY_END_HEADING = "### Issue コメント"
# focus に来ても観点ではないので無視する値（self-review SKILL.md の `--focus` の注入と同じ扱い）
NON_FOCUS = frozenset(("md-polish", "design-review"))
ISSUE_ID_RE = re.compile(r"[A-Z]+-[0-9]+")

# check の規則名 → 直し方（NG 行の 4 列目に添える）
RULE_HINT = {
    "over-cap": "plan の reviewer 行の数に収める",
    "min-guarantee": "bug-detection と claude-md-compliance を単独の行で起動する",
    "spec-missing": "仕様ソースがあるので spec-compliance を単独の行で起動する",
    "solo-bundled": "単独維持の観点を束ねから外して単独の行にする",
    "over-bundled": "1 体に束ねる観点を減らす",
    "redundant-not-allowed": "冗長ペアは xhigh / max だけ。同じ観点の行を 1 つにする",
    "unknown-focus": "観点のキーを triage-guide `## 3` の語彙に直す",
    "not-in-plan": "8a で足す観点は plan の --activated に足して plan を引き直す",
    "unaccounted": "plan の reviewer / piggyback の観点を行に戻す",
    "wrong-reason": "dropped の理由を plan の値に揃える",
    "dropped-revived": "plan が落とした観点を起こすなら、plan を引き直す（上限に空きが無いので落ちている）",
    "bad-prior": "prior の行は plan の前回の対象だけを 1 観点ずつ単独で置く",
    "bad-piggyback": "相乗りは plan の piggyback 行だけにする",
    "not-plan-row": "reviewer の行は plan の行と同じ観点の組にする（束ね直さない。冗長ペアは xhigh / max で plan の行を重ねるだけ）",
}


class UsageError(Exception):
    pass


def _csv(value):
    return [v.strip() for v in value.split(",") if v.strip()]


def _ordered(keys):
    """SOLO_ORDER → ADJACENCY の順に並べる（どちらにも無いキーは末尾に入力順で）。"""
    rank = {k: i for i, k in enumerate(SOLO_ORDER + ADJACENCY)}
    seen = []
    for k in keys:
        if k not in seen:
            seen.append(k)
    return sorted(seen, key=lambda k: rank.get(k, len(rank)))


def _split_even(keys, slots):
    """keys を slots 個の連続した塊に均等に割る（大きい塊が先）。"""
    q, r = divmod(len(keys), slots)
    chunks, i = [], 0
    for n in range(slots):
        size = q + (1 if n < r else 0)
        if size:
            chunks.append(keys[i:i + size])
        i += size
    return chunks


def _assign(cands, prior, effort, main_cap, total_cap, delta):
    """候補を reviewer の行に割り当てる。戻り値は (rows, piggyback, dropped_keys)。

    rows は [kind, [keys]]。main_cap は前回の対象の専任以外が使える体数、total_cap は全体の体数。
    前回の対象（prior）は落とさない — 枠が無ければ既存の行に相乗りさせる（prior-fixes-guide の 1 節）。
    """
    rows, piggyback, dropped = [], [], []
    main_used = 0
    design_effort = effort in DESIGN_EFFORTS
    # delta の回は前回の対象を規模キャップの外の専任にする（相乗りや束ねにすると、修正の確認が他の観点の片手間に
    # なる / triage-guide `### 6.5`）。単独維持の観点は単独維持の順の位置で、それ以外は単独維持の後に取る
    held = [k for k in prior if delta and k not in SOLO]

    def room():
        return main_used < main_cap and len(rows) < total_cap

    def take(kind, keys):
        nonlocal main_used
        rows.append([kind, list(keys)])
        if kind != "prior":
            main_used += 1

    def take_prior(k):
        # effort 上限を超える分は落ちる側に入れ、末尾で相乗りに移す
        if len(rows) < total_cap:
            take("prior", [k])
        else:
            dropped.append(k)

    pool = [k for k in _ordered(cands) if k not in held]
    for k in SOLO_ORDER:
        if k in pool and delta and k in prior:
            take_prior(k)
            if k != "layer-responsibility" or not design_effort:
                continue
        if k == "layer-responsibility" and design_effort:
            design = [d for d in DESIGN_ORDER if d in pool and not (delta and d in prior)]
            if design:
                if room():
                    take("design", design[:DESIGN_BUNDLE_MAX])
                    dropped.extend(design[DESIGN_BUNDLE_MAX:])
                else:
                    dropped.extend(design)
            continue
        if k in pool:
            if room():
                take("solo", [k])
            else:
                dropped.append(k)
    taken = {k for _, keys in rows for k in keys} | set(dropped)
    rest = [k for k in pool if k not in taken and k not in SOLO
            and not (design_effort and k in DESIGN)]

    for k in held:
        if len(rows) < total_cap:
            take("prior", [k])
        else:
            piggyback.append(k)

    slots = min(main_cap - main_used, total_cap - len(rows))
    if rest:
        if slots <= 0:
            dropped.extend(rest)
        elif len(rest) <= slots:
            for k in rest:
                take("solo", [k])
        else:
            fit = rest[:BUNDLE_MAX * slots]
            for chunk in _split_even(fit, slots):
                take("bundle" if len(chunk) > 1 else "solo", chunk)
            dropped.extend(rest[len(fit):])

    # 通常の回の前回の対象は、落ちる側に入っても相乗りで残す
    for k in [d for d in dropped if d in prior]:
        dropped.remove(k)
        piggyback.append(k)
    return rows, piggyback, dropped


def _piggyback_target(rows, key):
    """相乗り先の行番号（0 始まり）。束ねの順で一番近いキーを持つ行、無ければ先頭の行。"""
    if key in ADJACENCY:
        best, dist = None, None
        for i, (_, keys) in enumerate(rows):
            for k in keys:
                if k in ADJACENCY:
                    d = abs(ADJACENCY.index(k) - ADJACENCY.index(key))
                    if dist is None or d < dist:
                        best, dist = i, d
        if best is not None:
            return best
    return 0


def compute_plan(effort, size_tier, activated=(), prior=(), delta=False, focus=(), exclude=(),
                 spec_sources=(), spec_missing=()):
    """構成を決める（純関数）。引数の語彙の検査は呼び出し側（`parse_plan_args`）が済ませている前提。"""
    effort_source = "given"
    if not effort:
        effort, effort_source = "high", "default"
    focus = [k for k in focus if k not in NON_FOCUS]
    exclude = [k for k in exclude if k not in NON_FOCUS]
    out_of_vocab = [k for k in focus + exclude if k not in FOCUS_KEYS]
    focus = [k for k in focus if k in FOCUS_KEYS]
    exclude = [k for k in exclude if k in FOCUS_KEYS]
    prior = _ordered(prior)
    scope = "focus" if focus else ("exclude" if exclude else "full")

    if scope == "focus":
        cands = set(focus) | set(prior)
        excluded = []
        min_guarantee = all(k in focus for k in MIN_GUARANTEE)
    else:
        cands = set(activated) | set(MIN_GUARANTEE) | set(prior)
        if spec_sources:
            cands.add("spec-compliance")
        excluded = [k for k in _ordered(exclude) if k in cands and k not in prior]
        cands -= set(excluded)
        min_guarantee = not any(k in excluded for k in MIN_GUARANTEE)

    effort_cap = EFFORT_CAP["reviewer"][effort]
    # `--focus` / `--exclude` の回は規模キャップを掛けない（triage-guide `## 4` 末尾の plan の節）。
    # unknown の帯もキャップなし — small に倒すと大きな diff が最小構成で黙って処理される
    size_cap = SIZE_CAP["reviewer"].get(size_tier) if scope == "full" else None
    reviewer_cap = effort_cap if size_cap is None else min(effort_cap, size_cap)
    # 前回の対象の専任は規模キャップの外・effort 上限の内（triage-guide `### 6.5`）
    total_cap = effort_cap if delta else reviewer_cap

    rows, piggyback, dropped = _assign(cands, prior, effort, reviewer_cap, total_cap, delta)

    # 理由: 規模キャップを外して割り当て直すと入るなら size-cap。入らないなら、単独維持（low / medium では
    # 設計バンドルも）は effort-cap、束ねであふれたものは overflow
    reasons = {}
    if dropped:
        _, _, uncapped = _assign(cands, prior, effort, effort_cap, effort_cap, delta)
        for k in dropped:
            if k not in uncapped:
                reasons[k] = "size-cap"
            elif k in SOLO or (effort in DESIGN_EFFORTS and k in DESIGN):
                reasons[k] = "effort-cap"
            else:
                reasons[k] = "overflow"

    cap_source = "scope" if scope != "full" else (
        "size" if size_cap is not None and size_cap < effort_cap else "effort")
    explorer_size = SIZE_CAP["explorer"].get(size_tier)
    specialist_size = SIZE_CAP["specialist"].get(size_tier)

    def _min(a, b):
        return a if b is None else min(a, b)

    return {
        "effort": effort,
        "effort_source": effort_source,
        "size_tier": size_tier,
        "scope": scope,
        "delta": bool(delta),
        "effort_cap": effort_cap,
        "size_cap": size_cap,
        "reviewer_cap": reviewer_cap,
        "reviewer_cap_total": total_cap,
        "cap_source": cap_source,
        "explorer_cap": _min(EFFORT_CAP["explorer"][effort], explorer_size),
        "specialist_cap": _min(EFFORT_CAP["specialist"][effort], specialist_size),
        "redundant_pairs": "allowed" if effort in REDUNDANT_EFFORTS else "none",
        "min_guarantee": bool(min_guarantee),
        "candidates": _ordered(cands),
        "prior": prior,
        "rows": [{"id": "R%d" % (i + 1), "kind": kind, "keys": keys}
                 for i, (kind, keys) in enumerate(rows)],
        "piggyback": [{"id": "R%d" % (_piggyback_target(rows, k) + 1), "key": k} for k in piggyback],
        "dropped": [{"key": k, "reason": reasons[k]} for k in dropped],
        "excluded": excluded,
        "out_of_vocab": out_of_vocab,
        "spec_sources": [list(s) for s in spec_sources],
        "spec_missing": list(spec_missing),
    }


def render_plan(plan, plan_file=""):
    def v(x):
        if x is None:
            return "none"
        if isinstance(x, bool):
            return "1" if x else "0"
        return str(x)

    lines = ["## reviewer-plan"]
    for key in ("effort", "effort_source", "size_tier", "scope", "delta", "effort_cap", "size_cap",
                "reviewer_cap", "reviewer_cap_total", "cap_source", "explorer_cap",
                "specialist_cap", "redundant_pairs", "min_guarantee"):
        lines.append("%s=%s" % (key, v(plan[key])))
    # 前回の対象の専任でない行を足せる枠（delta の回は reviewer_cap_total の残りより小さいことがある）
    main_rows = sum(1 for r in plan["rows"] if r["kind"] != "prior")
    lines.append("spare=%d" % min(plan["reviewer_cap"] - main_rows,
                                  plan["reviewer_cap_total"] - len(plan["rows"])))
    if plan_file:
        lines.append("plan_file=%s" % plan_file)
    for label, detail in plan["spec_sources"]:
        lines.append("spec_source\t%s\t%s" % (label, detail))
    if not plan["spec_sources"]:
        lines.append("spec_source\tnone\t-")
    for path in plan["spec_missing"]:
        lines.append("spec_missing\t%s" % path)
    for row in plan["rows"]:
        lines.append("reviewer\t%s\t%s\t%s" % (row["id"], row["kind"], ",".join(row["keys"])))
    for p in plan["piggyback"]:
        lines.append("piggyback\t%s\t%s" % (p["id"], p["key"]))
    for d in plan["dropped"]:
        lines.append("dropped\t%s\t%s" % (d["key"], d["reason"]))
    for k in plan["excluded"]:
        lines.append("excluded\t%s" % k)
    for k in plan["out_of_vocab"]:
        lines.append("out_of_vocab\t%s" % k)
    return "\n".join(lines) + "\n"


def parse_table(lines):
    """check に流す確定テーブルを読む。reviewer の行が 1 つも無ければ UsageError。"""
    rows, piggyback, dropped = [], [], {}
    for raw in lines:
        cols = raw.rstrip("\r\n").split("\t")
        if cols[0] == "reviewer":
            if len(cols) != 4:
                raise UsageError("reviewer の行は reviewer<TAB>id<TAB>kind<TAB>keys の 4 列: %r" % raw)
            rows.append({"id": cols[1], "kind": cols[2], "keys": _csv(cols[3])})
        elif cols[0] == "piggyback":
            if len(cols) != 3:
                raise UsageError("piggyback の行は piggyback<TAB>id<TAB>key の 3 列: %r" % raw)
            piggyback.append({"id": cols[1], "key": cols[2]})
        elif cols[0] == "dropped":
            if len(cols) != 3:
                raise UsageError("dropped の行は dropped<TAB>key<TAB>reason の 3 列: %r" % raw)
            dropped[cols[1]] = cols[2]
    if not rows:
        raise UsageError("reviewer の行が無い（plan の出力を土台にした確定テーブルを stdin で渡す）")
    return rows, piggyback, dropped


def check_table(plan, rows, piggyback, dropped):
    """確定テーブルを plan と突き合わせる。戻り値は [(rule, detail)]（空なら ok）。"""
    ng = []
    effort = plan["effort"]
    design_effort = effort in DESIGN_EFFORTS
    row_keys = [k for r in rows for k in r["keys"]]
    present = set(row_keys) | {p["key"] for p in piggyback}

    for k in sorted(present | set(dropped)):
        if k not in FOCUS_KEYS:
            ng.append(("unknown-focus", k))
    allowed = set(plan["candidates"])
    for k in sorted(present - allowed):
        if k in FOCUS_KEYS:
            ng.append(("not-in-plan", k))

    prior_rows = [r for r in rows if r["kind"] == "prior"]
    if len(rows) > plan["reviewer_cap_total"]:
        ng.append(("over-cap", "reviewer %d 体 > 上限 %d（%s）" % (
            len(rows), plan["reviewer_cap_total"], plan["cap_source"])))
    elif len(rows) - len(prior_rows) > plan["reviewer_cap"]:
        ng.append(("over-cap", "前回の対象の専任を除いて %d 体 > 上限 %d（%s）" % (
            len(rows) - len(prior_rows), plan["reviewer_cap"], plan["cap_source"])))

    solo_rows = {r["keys"][0] for r in rows if len(set(r["keys"])) == 1}
    if plan["min_guarantee"]:
        for k in MIN_GUARANTEE:
            if k not in solo_rows:
                ng.append(("min-guarantee", k))
    if plan["spec_sources"] and "spec-compliance" in allowed and "spec-compliance" not in solo_rows:
        ng.append(("spec-missing", ",".join(l for l, _ in plan["spec_sources"])))

    for r in rows:
        keys = set(r["keys"])
        is_design = design_effort and len(keys) > 1 and keys <= DESIGN
        if len(keys) > 1 and keys & SOLO and not is_design:
            ng.append(("solo-bundled", "%s: %s" % (r["id"], ",".join(r["keys"]))))
        limit = DESIGN_BUNDLE_MAX if is_design else BUNDLE_MAX
        if len(keys) > limit:
            ng.append(("over-bundled", "%s: %d 観点 > %d" % (r["id"], len(keys), limit)))

    if effort not in REDUNDANT_EFFORTS:
        for k in sorted({k for k in row_keys if row_keys.count(k) > 1}):
            ng.append(("redundant-not-allowed", k))

    # kind 列と piggyback 行は LLM が書くので、plan と同じものだけを認める。認めないと、落とした観点を
    # prior の行や相乗りで書き足して規模キャップと単独維持を越えられる（#351 が止めたい書き換えそのもの）
    plan_prior = set(plan["prior"])
    for r in prior_rows:
        if len(set(r["keys"])) != 1 or r["keys"][0] not in plan_prior:
            ng.append(("bad-prior", "%s: %s" % (r["id"], ",".join(r["keys"]))))
    for r in plan["rows"]:
        if r["kind"] == "prior" and r["keys"][0] not in solo_rows:
            ng.append(("bad-prior", "%s: 単独の行が無い" % r["keys"][0]))
    # 観点の有無だけを見ると、束ね直して体数を減らした構成（plan の 6 体を 5 体に）が通る。前回の対象の専任を除く
    # 行は、観点の組が plan の行と 1 対 1 で一致することを求める（xhigh / max は plan の行を重ねる冗長ペアだけ許す）
    plan_sets = Counter(frozenset(r["keys"]) for r in plan["rows"] if r["kind"] != "prior")
    table_sets = Counter(frozenset(r["keys"]) for r in rows if r["kind"] != "prior")
    for keyset, n in sorted(table_sets.items(), key=lambda kv: sorted(kv[0])):
        extra = n - plan_sets.get(keyset, 0)
        if keyset not in plan_sets or (extra > 0 and effort not in REDUNDANT_EFFORTS):
            ng.append(("not-plan-row", ",".join(sorted(keyset))))
    for keyset in sorted(set(plan_sets) - set(table_sets), key=sorted):
        ng.append(("not-plan-row", "plan の行が無い: " + ",".join(sorted(keyset))))
    plan_piggyback = {p["key"] for p in plan["piggyback"]}
    for p in piggyback:
        if p["key"] not in plan_piggyback:
            ng.append(("bad-piggyback", p["key"]))

    planned = {k for r in plan["rows"] for k in r["keys"]} | plan_piggyback
    for k in sorted(planned - present):
        ng.append(("unaccounted", k))
    plan_dropped = {d["key"]: d["reason"] for d in plan["dropped"]}
    for k, reason in sorted(plan_dropped.items()):
        if k in present:
            ng.append(("dropped-revived", k))
        elif k not in dropped:
            ng.append(("unaccounted", k))
        elif dropped[k] != reason:
            ng.append(("wrong-reason", "%s: %s（plan は %s）" % (k, dropped[k], reason)))
    return ng


# ---- 入出力（仕様ソースの検出・plan ファイル） ---------------------------------

def _frontmatter(path):
    """先頭 40 行の frontmatter から branch と issue_id を読む（無ければ空の dict）。"""
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    if not lines or lines[0].strip() != "---":
        return out
    for line in lines[1:40]:
        if line.strip() == "---":
            break
        m = re.match(r"^(branch|issue_id):\s*['\"]?([^'\"#]+?)['\"]?\s*$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def _pr_body(path):
    """fetch-pr-context.sh の保存先から PR 本文の節（`### PR 説明` から `### Issue コメント` の手前まで）を返す。

    コメント・レビューの節は読まない（参照を拾うのは著者が書いた本文だけ）。ファイルが無ければ空。
    """
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return ""
    out, inside = [], False
    for line in lines:
        if line.startswith(PR_BODY_HEADING):
            inside = True
            continue
        if inside and line.startswith(PR_BODY_END_HEADING):
            break
        if inside:
            out.append(line)
    return "\n".join(out)


def _read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def detect_spec_sources(roots, branch, issue_ids, specs, diff_text="", pr_body=""):
    """仕様ソースを探す。戻り値は (sources, missing)。sources は [(label, detail)]。

    roots は作業ツリーとメインのチェックアウト（Issue ファイルを gitignore した repo では worktree に無い）。
    repo の仕様書は作業ツリー（roots[0]）で探す: diff が触ったもの（repo-spec-touched）と、session-context・
    Issue ファイル・PR 本文が言及したもの（repo-spec-ref）。規約（CLAUDE.md 等）は claude-md-compliance の
    担当なので足さない。
    """
    sources, missing, seen = [], [], set()
    ids = list(issue_ids)

    def add(label, detail):
        # plan は TSV で出すので、改行・タブを含むパス（第三者の diff が置いた名前）は行を壊す。仕様ソースにしない
        if any(c in detail for c in "\t\n\r"):
            return
        if (label, detail) not in seen:
            seen.add((label, detail))
            sources.append((label, detail))

    # detached HEAD（"HEAD"）では branch の一致が無関係な作業と重なるので session-context を見ない
    if branch and branch != "HEAD":
        for root in roots:
            path = os.path.join(root, ".claude", "session-context.md")
            meta = _frontmatter(path)
            if meta.get("branch") == branch:
                add("session-context", os.path.abspath(path))
                # ブランチ名に Issue ID が無い回（GitHub の番号で切ったブランチ）も、session-context の issue_id で Issue ファイルを探す
                if meta.get("issue_id"):
                    ids.append(meta["issue_id"])
    ids = list(dict.fromkeys(ids + ISSUE_ID_RE.findall(branch or "")))
    for root in roots:
        for backend in ("indie", "linear"):
            base = os.path.join(root, ".claude", backend)
            try:
                slugs = sorted(os.listdir(base))
            except OSError:
                continue
            for slug in slugs:
                for issue_id in ids:
                    path = os.path.join(base, slug, "issues", issue_id + ".md")
                    if os.path.isfile(path):
                        add("issue-file", os.path.abspath(path))
    for spec in specs:
        if os.path.isfile(spec):
            add("spec", os.path.abspath(spec))
        else:
            missing.append(spec)
    if roots:
        root = roots[0]
        known = {os.path.realpath(d) for label, d in sources if label == "spec"}
        for kind, rel in doc_locate.touched_docs(diff_text, root):
            path = os.path.join(root, rel)
            if kind == "spec" and os.path.realpath(path) not in known:
                known.add(os.path.realpath(path))
                add("repo-spec-touched", path)
        refs = [_read_text(d) for label, d in list(sources) if label in ("session-context", "issue-file")]
        for kind, rel in doc_locate.mentioned_docs("\n".join(refs + [pr_body]), root):
            path = os.path.join(root, rel)
            if kind == "spec" and os.path.realpath(path) not in known:
                known.add(os.path.realpath(path))
                add("repo-spec-ref", path)
    return sources, missing


def _keys_arg(value, name, allow_spec=True):
    keys = _csv(value)
    bad = [k for k in keys if k not in FOCUS_KEYS]
    if bad:
        raise UsageError("%s に語彙外の観点: %s（語彙: %s）" % (name, ",".join(bad), ",".join(FOCUS_KEYS)))
    if not allow_spec and "spec-compliance" in keys:
        raise UsageError("spec-compliance は %s に入れない。仕様ソースから決める"
                         "（PR の紐づき Issue・knowledge は --spec-source pr-issue:#N / knowledge:<path>）" % name)
    return keys


def _plan_main(ns):
    effort = ns.effort or ""
    if effort and effort not in EFFORTS:
        raise UsageError("--effort は %s のどれか（空なら high）。受領: %r" % ("|".join(EFFORTS), effort))
    if ns.size_tier not in SIZE_TIERS:
        raise UsageError("--size-tier は %s のどれか。受領: %r" % ("|".join(SIZE_TIERS), ns.size_tier))
    if ns.focus and ns.exclude:
        raise UsageError("--focus と --exclude は同時に渡さない")
    activated = _keys_arg(ns.activated, "--activated", allow_spec=False)
    prior_raw = _csv(ns.prior)
    # 前回の対象のうち reviewer の観点でないもの: specialist は plan の範囲外、recall-skeptic / meta /
    # 語彙外は bug-detection の担当に読み替える（prior-fixes-guide の 1 節）
    prior, prior_specialist = [], []
    for k in prior_raw:
        if k.startswith("specialist-"):
            prior_specialist.append(k)
        elif k in FOCUS_KEYS:
            prior.append(k)
        else:
            prior.append("bug-detection")
    extra = []
    for s in ns.spec_source or []:
        label, _, detail = s.partition(":")
        if label not in SPEC_SOURCE_LABELS:
            raise UsageError("--spec-source のラベルは %s。受領: %r" % ("|".join(SPEC_SOURCE_LABELS), s))
        extra.append((label, detail or "-"))
    roots = [r for r in (ns.wt, ns.main_root) if r]
    roots = list(dict.fromkeys(os.path.abspath(r) for r in roots))
    diff_text = _read_text(ns.diff_file) if ns.diff_file else ""
    found, missing = detect_spec_sources(roots, ns.branch, ns.issue_id or [], ns.spec or [],
                                         diff_text=diff_text, pr_body=_pr_body(ns.pr_context))
    if ns.size_tier == "unknown":
        print("WARN: size_tier=unknown のため規模キャップを掛けずに effort 上限だけで構成した", file=sys.stderr)
    plan = compute_plan(effort, ns.size_tier, activated=activated, prior=prior, delta=ns.delta,
                        focus=_csv(ns.focus), exclude=_csv(ns.exclude),
                        spec_sources=found + extra, spec_missing=missing)
    plan["prior_specialist"] = prior_specialist
    text = render_plan(plan, ns.plan_file)
    text += "".join("prior_specialist\t%s\n" % k for k in prior_specialist)
    rc = 0
    try:
        with open(ns.plan_file, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False)
    except OSError as e:
        print("WARN: plan を書けない（check が使えない）: %s" % e, file=sys.stderr)
        rc = 1
    sys.stdout.write(text)
    return rc


def _check_main(ns):
    try:
        with open(ns.plan_file, encoding="utf-8") as f:
            plan = json.load(f)
    except (OSError, ValueError):
        raise UsageError("plan が無い（先に plan-reviewers.sh plan を呼ぶ）: %s" % ns.plan_file)
    lines = sys.stdin.read().splitlines()
    if not plan["rows"] and not any(l.startswith("reviewer\t") for l in lines):
        # 候補がすべて外れた回（--exclude で最小保証まで外した等）。起動する reviewer が無いのが plan どおり
        print("ok")
        return 0
    rows, piggyback, dropped = parse_table(lines)
    ng = check_table(plan, rows, piggyback, dropped)
    if not ng:
        print("ok")
        return 0
    for rule, detail in ng:
        print("NG\t%s\t%s\t%s" % (rule, detail, RULE_HINT[rule]))
    return 1


def main(argv=None):
    # 省略形（--plan-f など）を受けると、plan-reviewers.sh の内部引数のガードをすり抜けて保存先が差し替わる
    ap = argparse.ArgumentParser(prog="reviewer_plan.py", allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", allow_abbrev=False)
    p.add_argument("--plan-file", required=True)
    p.add_argument("--wt", default="")
    p.add_argument("--main-root", default="")
    p.add_argument("--branch", default="")
    p.add_argument("--effort", default="")
    p.add_argument("--size-tier", required=True)
    p.add_argument("--activated", default="")
    p.add_argument("--prior", default="")
    p.add_argument("--delta", action="store_true")
    p.add_argument("--focus", default="")
    p.add_argument("--exclude", default="")
    p.add_argument("--spec", action="append")
    p.add_argument("--spec-source", action="append")
    p.add_argument("--issue-id", action="append")
    p.add_argument("--diff-file", default="")
    p.add_argument("--pr-context", default="")
    c = sub.add_parser("check", allow_abbrev=False)
    c.add_argument("--plan-file", required=True)
    try:
        ns = ap.parse_args(argv)
    except SystemExit as e:
        if e.code:
            # argparse は usage と理由を出し終えている。呼び出し側が引数の誤りと分かる行を揃える
            print("FATAL: 引数の誤り（上の usage を見る）", file=sys.stderr)
            return 2
        return 0
    try:
        return _plan_main(ns) if ns.cmd == "plan" else _check_main(ns)
    except UsageError as e:
        print("FATAL: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
