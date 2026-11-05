#!/usr/bin/env python3
"""reviewer の構成の決定と起動前の検算（`code-review/scripts/plan-reviewers.sh` / `lib/reviewer_plan.py`）の回帰テスト（GitHub issue #351）.

self-review が triage-guide の構成の規則を LLM の数え上げで適用し、effort high の上限 6 を 5 と数え、
仕様ソースがあるのに spec-compliance より security を先に取った。起動前の検算も同じ LLM が回すので止まらなかった。
構成は script が決め、確定したテーブルは check が突き合わせる。

- 定数は triage-guide の表の複製なので、期待値は表を読んで作る（lib の値から作らない / testing-pitfalls）
- 割り当てと検算は純関数を直接呼ぶ。仕様ソースの検出と終了コードは CLI 越しに見る

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from test_code_review_scripts import PLUGIN, ScriptTestBase

sys.path.insert(0, str(PLUGIN / "scripts" / "lib"))

import reviewer_plan as rp  # noqa: E402

GUIDE = PLUGIN / "references" / "triage-guide.md"
PLAN = PLUGIN / "scripts" / "plan-reviewers.sh"
TRIAGE = PLUGIN / "scripts" / "triage-signals.sh"


def _guide_lines() -> list[str]:
    return GUIDE.read_text(encoding="utf-8").splitlines()


def _section(title: str) -> list[str]:
    lines = _guide_lines()
    start = lines.index(title)
    level = title.split(" ")[0]
    out = []
    for line in lines[start + 1:]:
        if line.startswith("#") and len(line.split(" ")[0]) <= len(level):
            break
        out.append(line)
    return out


def _keys_in_order(text: str) -> list[str]:
    """text に現れる観点キーを出現順に（長いキーを先に当てて部分一致を避ける）."""
    keys = sorted(rp.FOCUS_KEYS, key=len, reverse=True)
    pat = re.compile("|".join(re.escape(k) for k in keys))
    seen = []
    for m in pat.finditer(text):
        if m.group(0) not in seen:
            seen.append(m.group(0))
    return seen


class GuideTableTest(unittest.TestCase):
    """lib の定数は triage-guide の表の複製。表だけ直すと plan が古い値で構成し続ける."""

    def test_effort_caps_match_section_7_table(self):
        rows = {}
        for line in _section("## 7. 最小保証とフェーズ上限（effort 適応 / effort 側上限の正本。実効上限は `## 6.2` との min）"):
            cols = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cols) == 4 and cols[0] in ("explorer", "reviewer", "specialist"):
                rows[cols[0]] = [int(re.match(r"\d+", c).group(0)) for c in cols[1:]]
        self.assertEqual(set(rows), {"explorer", "reviewer", "specialist"})
        for role, (lowmed, high, xmax) in rows.items():
            caps = rp.EFFORT_CAP[role]
            self.assertEqual((caps["low"], caps["medium"], caps["high"], caps["xhigh"], caps["max"]),
                             (lowmed, lowmed, high, xmax, xmax), role)

    def test_size_caps_match_section_6_2_table(self):
        got = {}
        for line in _section("### 6.2 規模キャップ"):
            cols = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cols) == 5 and cols[0] in ("small", "medium", "large"):
                got[cols[0]] = [None if c == "キャップなし" else int(c) for c in cols[2:]]
        self.assertEqual(set(got), {"small", "medium", "large"})
        for tier, (explorer, reviewer, specialist) in got.items():
            self.assertEqual(rp.SIZE_CAP["explorer"][tier], explorer, tier)
            self.assertEqual(rp.SIZE_CAP["reviewer"][tier], reviewer, tier)
            self.assertEqual(rp.SIZE_CAP["specialist"][tier], specialist, tier)

    def test_solo_order_matches_section_4(self):
        line = next(l for l in _guide_lines() if l.startswith("- **単独維持の観点が上限に収まらないときの順**"))
        head = line.split("→ 残りは束ねる")[0]
        self.assertEqual(tuple(_keys_in_order(head)), rp.SOLO_ORDER)

    def test_solo_set_matches_section_7(self):
        line = next(l for l in _guide_lines() if "は束ねず単独を維持" in l)
        m = re.search(r"\*\*([^*]+) は束ねず単独を維持\*\*", line)
        self.assertIsNotNone(m, line)
        self.assertEqual(set(_keys_in_order(m.group(1))), set(rp.SOLO))
        self.assertIn("1 体あたり %d 観点まで" % rp.BUNDLE_MAX, line)

    def test_design_bundle_matches_section_7(self):
        line = next(l for l in _guide_lines() if l.lstrip().startswith("- **設計バンドル（low / medium のみ）**"))
        head = line.split("のうち起動条件")[0]
        self.assertEqual(set(_keys_in_order(head)), set(rp.DESIGN))
        self.assertIn("この束ねだけは %d 観点まで" % rp.DESIGN_BUNDLE_MAX, line)

    def test_focus_vocabulary_matches_section_3_table(self):
        keys = set()
        for line in _section("### reviewer の観点判定"):
            m = re.match(r"\| ([a-z][a-z-]+) \|", line)
            if m:
                keys.add(m.group(1))
        self.assertEqual(keys, set(rp.FOCUS_KEYS))
        # 束ねる順と単独維持で語彙を過不足なく覆う（どちらにも無い観点は割り当てられずに消える）
        self.assertEqual(sorted(rp.ADJACENCY + rp.SOLO_ORDER), sorted(rp.FOCUS_KEYS))


def plan(effort="high", tier="large", activated=(), spec=False, **kw):
    return rp.compute_plan(effort, tier, activated=list(activated),
                           spec_sources=[("issue-file", "/x")] if spec else [], **kw)


def rows(p):
    return [tuple(r["keys"]) for r in p["rows"]]


def dropped(p):
    return {d["key"]: d["reason"] for d in p["dropped"]}


def as_table(p):
    out = ["reviewer\t%s\t%s\t%s" % (r["id"], r["kind"], ",".join(r["keys"])) for r in p["rows"]]
    out += ["piggyback\t%s\t%s" % (x["id"], x["key"]) for x in p["piggyback"]]
    out += ["dropped\t%s\t%s" % (d["key"], d["reason"]) for d in p["dropped"]]
    return out


def check(p, lines):
    return [rule for rule, _ in rp.check_table(p, *rp.parse_table(lines))]


class ComputePlanTest(unittest.TestCase):
    def test_issue_351_high_large_with_spec_source_uses_six_and_keeps_spec(self):
        p = plan(activated=["security", "error-handling", "comment-accuracy", "test-quality"], spec=True)
        self.assertEqual(p["reviewer_cap"], 6)
        self.assertEqual(p["cap_source"], "effort")
        self.assertEqual(len(p["rows"]), 6)
        self.assertEqual(rows(p)[:4], [("bug-detection",), ("claude-md-compliance",),
                                       ("spec-compliance",), ("security",)])
        self.assertNotIn("size-cap", dropped(p).values())

    def test_no_spec_source_means_no_spec_row_and_adding_one_brings_it(self):
        without = plan(activated=["security"])
        self.assertNotIn(("spec-compliance",), rows(without))
        self.assertIn(("spec-compliance",), rows(plan(activated=["security"], spec=True)))

    def test_small_tier_takes_spec_before_security(self):
        for effort in rp.EFFORTS:
            p = plan(effort, "small", activated=["security"], spec=True)
            self.assertEqual(rows(p), [("bug-detection",), ("claude-md-compliance",), ("spec-compliance",)], effort)
            self.assertEqual(dropped(p), {"security": "size-cap"}, effort)
            self.assertEqual(p["cap_source"], "size")
        self.assertEqual(rows(plan("high", "small", activated=["security"]))[2], ("security",))

    def test_large_never_reports_size_cap(self):
        many = [k for k in rp.FOCUS_KEYS if k != "spec-compliance"]
        for effort in rp.EFFORTS:
            self.assertNotIn("size-cap", dropped(plan(effort, "large", activated=many, spec=True)).values())

    def test_unknown_tier_applies_no_size_cap(self):
        p = plan("high", "unknown", activated=["security", "error-handling"])
        self.assertIsNone(p["size_cap"])
        self.assertEqual(p["reviewer_cap"], 6)

    def test_design_bundle_only_on_low_and_medium(self):
        act = ["layer-responsibility", "cross-cutting", "type-design", "pattern-consistency"]
        for effort in ("low", "medium"):
            p = plan(effort, "large", activated=act)
            self.assertIn(("layer-responsibility", "cross-cutting", "type-design", "pattern-consistency"), rows(p))
            self.assertEqual([r["kind"] for r in p["rows"] if len(r["keys"]) == 4], ["design"])
        p = plan("high", "large", activated=act)
        self.assertIn(("layer-responsibility",), rows(p))
        self.assertTrue(all(len(r) == 1 or "layer-responsibility" not in r for r in rows(p)))

    def test_single_design_focus_on_medium_is_its_own_reviewer(self):
        self.assertIn(("cross-cutting",), rows(plan("medium", "large", activated=["cross-cutting"])))

    def test_bundle_absorbs_up_to_s_plus_remaining_times_three(self):
        # high・単独 4 観点（bug / claude / spec / security）: 4 + (6 - 4) × 3 = 10 観点まで
        rest = list(rp.ADJACENCY)
        p = plan(activated=["security"] + rest[:6], spec=True)
        self.assertEqual(dropped(p), {})
        p = plan(activated=["security"] + rest[:7], spec=True)
        self.assertEqual(list(dropped(p).values()), ["overflow"])
        # 単独 5 観点（layer-responsibility も起動）なら 5 + 1 × 3 = 8 観点まで
        p = plan(activated=["security", "layer-responsibility"] + rest[:3], spec=True)
        self.assertEqual(dropped(p), {})
        p = plan(activated=["security", "layer-responsibility"] + rest[:4], spec=True)
        self.assertEqual(list(dropped(p).values()), ["overflow"])

    def test_bundles_split_evenly_in_adjacency_order(self):
        p = plan(activated=["security"] + list(rp.ADJACENCY[:4]), spec=True)
        self.assertEqual(rows(p)[4:], [tuple(rp.ADJACENCY[:2]), tuple(rp.ADJACENCY[2:4])])

    def test_reason_splits_size_cap_from_effort_cap_and_overflow(self):
        # medium の帯（5）と low（4）: 4 体目までは effort 上限内なので、規模で落ちたものは無い
        p = plan("low", "medium", activated=["security", "layer-responsibility"] + list(rp.ADJACENCY), spec=True)
        reasons = dropped(p)
        self.assertNotIn("size-cap", reasons.values())
        self.assertIn("effort-cap", reasons.values())
        # high + medium の帯（5 < 6）: 規模キャップを外せば入る観点は size-cap
        p = plan("high", "medium", activated=["security", "layer-responsibility", "error-handling"], spec=True)
        self.assertEqual(dropped(p), {"error-handling": "size-cap"})

    def test_delta_prior_is_outside_size_cap_and_never_dropped(self):
        p = plan("high", "small", activated=["security"], spec=True, prior=["performance"], delta=True)
        self.assertIn(("performance",), rows(p))
        self.assertEqual(p["reviewer_cap"], 3)
        self.assertEqual(p["reviewer_cap_total"], 6)
        self.assertIn(("spec-compliance",), rows(p))
        # effort 上限を超える前回の対象は相乗りになる
        many = list(rp.ADJACENCY[:6])
        p = plan("low", "small", spec=True, prior=many, delta=True)
        self.assertEqual(len(p["rows"]), 4)
        self.assertEqual({x["key"] for x in p["piggyback"]}, set(many) - {k for r in rows(p) for k in r})
        self.assertFalse(set(many) & set(dropped(p)))

    def test_delta_solo_prior_gets_its_own_row_instead_of_piggyback(self):
        """単独維持の観点が前回の対象のとき、規模キャップで入らなくても effort 上限の内側なら専任にする（triage-guide `### 6.5`）."""
        p = plan("high", "small", spec=True, prior=["security"], delta=True)
        self.assertIn({"id": "R4", "kind": "prior", "keys": ["security"]}, p["rows"])
        self.assertEqual(p["piggyback"], [])
        # effort 上限も埋まっていれば相乗りになる
        p = plan("low", "small", spec=True, prior=["security"] + list(rp.ADJACENCY[:3]), delta=True)
        self.assertEqual(len(p["rows"]), 4)
        self.assertNotIn("security", dropped(p))
        # low・small で layer-responsibility が前回の対象なら、設計バンドルごと落とさず専任にする
        p = plan("low", "small", spec=True, activated=["cross-cutting"], prior=["layer-responsibility"], delta=True)
        self.assertIn(("layer-responsibility",), rows(p))
        # 4 体（最小保証 2・spec・前回の対象の専任）で low の effort 上限が埋まるので、規模ではなく effort で落ちる
        self.assertEqual(dropped(p), {"cross-cutting": "effort-cap"})

    def test_delta_solo_prior_does_not_use_size_cap_slots(self):
        """単独維持の前回の対象が規模キャップの枠を使うと、delta で立った観点が押し出される（### 6.5 の「キャップの外」）."""
        p = plan("high", "small", activated=["error-handling"], prior=["security"], delta=True)
        self.assertIn({"id": "R3", "kind": "prior", "keys": ["security"]}, p["rows"])
        self.assertIn(("error-handling",), rows(p))
        self.assertEqual(dropped(p), {})

    def test_delta_layer_prior_is_not_bundled_into_design(self):
        p = plan("medium", "medium", activated=["layer-responsibility", "cross-cutting", "type-design"],
                 prior=["layer-responsibility"], delta=True)
        self.assertIn({"id": "R3", "kind": "prior", "keys": ["layer-responsibility"]}, p["rows"])
        self.assertIn(("cross-cutting", "type-design"), rows(p))

    def test_spare_counts_only_rows_outside_prior(self):
        p = plan("high", "small", activated=["security", "error-handling"], prior=["performance"], delta=True)
        self.assertEqual(rp.render_plan(p).count("\nspare=0\n"), 1)

    def test_prior_on_full_scope_piggybacks_instead_of_dropping(self):
        p = plan("high", "small", activated=["security"], spec=True, prior=["security"])
        self.assertNotIn("security", dropped(p))
        self.assertEqual([x["key"] for x in p["piggyback"]], ["security"])

    def test_focus_scope_skips_size_cap_and_min_guarantee(self):
        p = plan("high", "small", focus=["security", "performance", "error-handling", "config"])
        self.assertIsNone(p["size_cap"])
        self.assertFalse(p["min_guarantee"])
        self.assertEqual(p["cap_source"], "scope")
        self.assertNotIn(("bug-detection",), rows(p))

    def test_exclude_scope_keeps_prior(self):
        p = plan("high", "large", activated=["security"], exclude=["security", "error-handling"], prior=["error-handling"])
        self.assertEqual(p["excluded"], ["security"])
        self.assertIn(("error-handling",), rows(p))

    def test_out_of_vocab_focus_is_reported_not_fatal(self):
        p = plan(focus=["security", "migration-safety", "md-polish"])
        self.assertEqual(p["out_of_vocab"], ["migration-safety"])

    def test_empty_effort_defaults_to_high(self):
        p = rp.compute_plan("", "large")
        self.assertEqual((p["effort"], p["effort_source"], p["reviewer_cap"]), ("high", "default", 6))


class CheckTableTest(unittest.TestCase):
    CASES = [
        ("high", "large", dict(activated=["security", "error-handling", "comment-accuracy"], spec=True)),
        ("low", "small", dict(activated=["security", "cross-cutting", "type-design"], spec=True)),
        ("medium", "large", dict(activated=["layer-responsibility", "cross-cutting"] + list(rp.ADJACENCY))),
        ("xhigh", "medium", dict(activated=list(rp.ADJACENCY), spec=True)),
        ("high", "small", dict(activated=["security"], spec=True, prior=["performance"], delta=True)),
        ("high", "small", dict(focus=["security", "performance"])),
    ]

    def test_plan_output_always_passes(self):
        for effort, tier, kw in self.CASES:
            p = plan(effort, tier, **kw)
            self.assertEqual(check(p, as_table(p)), [], (effort, tier, kw))

    def test_plan_output_passes_across_the_grid(self):
        """新しい check の規則が plan 自身の出力を NG にしないこと。effort × 帯 × delta × 範囲 × 前回の対象を総当たりする."""
        act = ["security", "layer-responsibility", "cross-cutting", "error-handling", "config", "ui-quality"]
        priors = ([], ["security"], ["layer-responsibility"], ["cross-cutting", "performance"], ["bug-detection"])
        scopes = ({}, {"focus": ["security", "type-design"]}, {"exclude": ["error-handling"]})
        for effort in rp.EFFORTS:
            for tier in rp.SIZE_TIERS:
                for delta in (False, True):
                    for prior in priors:
                        for scope in scopes:
                            for spec in (False, True):
                                p = plan(effort, tier, activated=act, spec=spec, prior=prior, delta=delta, **scope)
                                if not p["rows"]:
                                    continue
                                key = (effort, tier, delta, prior, scope, spec)
                                self.assertEqual(check(p, as_table(p)), [], key)

    def test_issue_351_table_is_stopped(self):
        p = plan(activated=["security", "error-handling", "comment-accuracy"], spec=True)
        table = ["reviewer\tR1\tsolo\tbug-detection", "reviewer\tR2\tsolo\tclaude-md-compliance",
                 "reviewer\tR3\tsolo\tsecurity", "reviewer\tR4\tbundle\terror-handling,comment-accuracy",
                 "dropped\tspec-compliance\tsize-cap"]
        got = check(p, table)
        self.assertIn("spec-missing", got)
        self.assertIn("unaccounted", got)

    def test_over_cap(self):
        p = plan("high", "small", activated=["security"])
        extra = as_table(p) + ["reviewer\tR4\tsolo\tsecurity"]
        self.assertIn("over-cap", check(p, [l for l in extra if not l.startswith("dropped")]))

    def test_min_guarantee(self):
        p = plan(activated=["security"])
        table = [l for l in as_table(p) if not l.endswith("\tbug-detection")]
        self.assertIn("min-guarantee", check(p, table))

    def test_solo_bundled_and_design_exception(self):
        p = plan(activated=["security", "error-handling"])
        table = ["reviewer\tR1\tsolo\tbug-detection", "reviewer\tR2\tsolo\tclaude-md-compliance",
                 "reviewer\tR3\tbundle\tsecurity,error-handling"]
        self.assertIn("solo-bundled", check(p, table))
        act = ["layer-responsibility", "cross-cutting"]
        low = plan("low", "large", activated=act)
        self.assertEqual(check(low, as_table(low)), [])
        high = plan("high", "large", activated=act)
        bundled = ["reviewer\tR1\tsolo\tbug-detection", "reviewer\tR2\tsolo\tclaude-md-compliance",
                   "reviewer\tR3\tdesign\tlayer-responsibility,cross-cutting"]
        self.assertIn("solo-bundled", check(high, bundled))

    def test_over_bundled(self):
        p = plan(activated=list(rp.ADJACENCY[:4]))
        table = ["reviewer\tR1\tsolo\tbug-detection", "reviewer\tR2\tsolo\tclaude-md-compliance",
                 "reviewer\tR3\tbundle\t" + ",".join(rp.ADJACENCY[:4])]
        self.assertIn("over-bundled", check(p, table))

    def test_redundant_pair_only_on_xhigh_and_max(self):
        for effort, ok in (("high", False), ("xhigh", True), ("max", True)):
            p = plan(effort, "large", activated=["security"])
            table = as_table(p) + ["reviewer\tR9\tsolo\tbug-detection"]
            self.assertEqual("redundant-not-allowed" in check(p, table), not ok, effort)

    def test_not_in_plan_and_unknown_focus(self):
        p = plan(activated=["security"])
        self.assertIn("not-in-plan", check(p, as_table(p) + ["reviewer\tR9\tsolo\tperformance"]))
        self.assertIn("unknown-focus", check(p, as_table(p) + ["reviewer\tR9\tsolo\tperf"]))

    def test_wrong_reason(self):
        p = plan("high", "small", activated=["security"], spec=True)
        table = [l.replace("size-cap", "effort-cap") for l in as_table(p)]
        self.assertIn("wrong-reason", check(p, table))

    def test_rebundled_table_with_fewer_rows_is_stopped(self):
        """#351 の「上限 6 を 5 と数えた」形: 単独維持は落とさず、束ね直して体数を減らした構成."""
        p = plan(activated=["security", "error-handling", "test-quality"], spec=True)
        self.assertEqual(len(p["rows"]), 6)
        table = [l for l in as_table(p) if not l.endswith("\terror-handling") and not l.endswith("\ttest-quality")]
        table.append("reviewer\tR5\tbundle\terror-handling,test-quality")
        self.assertIn("not-plan-row", check(p, table))
        table[-1] = "reviewer\tR5\tsolo\terror-handling,test-quality"
        self.assertIn("not-plan-row", check(p, table))

    def test_dropped_focus_cannot_be_revived_as_prior_or_piggyback(self):
        """落とした観点を prior の行や相乗りで書き足すと規模キャップと単独維持を越えられる（#351 の書き換え）."""
        p = plan("high", "small", activated=["security", "error-handling"], spec=True, prior=["performance"], delta=True)
        self.assertEqual(dropped(p), {"security": "size-cap", "error-handling": "size-cap"})
        fake_prior = [l for l in as_table(p) if not l.startswith("dropped\terror")] + ["reviewer\tR9\tprior\terror-handling"]
        got = check(p, fake_prior)
        self.assertIn("bad-prior", got)
        self.assertIn("dropped-revived", got)
        fake_pig = [l for l in as_table(p) if not l.startswith("dropped\tsecurity")] + ["piggyback\tR1\tsecurity"]
        got = check(p, fake_pig)
        self.assertIn("bad-piggyback", got)
        self.assertIn("dropped-revived", got)

    def test_prior_row_must_stay_solo(self):
        p = plan("high", "large", activated=["security"], prior=["performance", "config"], delta=True)
        table = [l for l in as_table(p) if "\tprior\t" not in l] + ["reviewer\tR9\tbundle\tperformance,config"]
        self.assertIn("bad-prior", check(p, table))

    def test_table_without_reviewer_rows_is_a_usage_error(self):
        with self.assertRaises(rp.UsageError):
            rp.parse_table(["dropped\tsecurity\tsize-cap"])


class PlanCliTest(ScriptTestBase):
    def _env(self, **extra: str) -> dict[str, str]:
        return super()._env(**{"CLAUDE_CODE_SESSION_ID": "s1", **extra})

    def git(self, *args: str, cwd=None) -> None:
        subprocess.run(["git", *args], cwd=cwd or self.root, check=True, capture_output=True, env=self._env())

    def write(self, rel: str, body: str, root=None) -> None:
        p = (root or self.root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def cli(self, *args: str, stdin: str = "", cwd=None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(PLAN), *args], cwd=cwd or self.root, input=stdin,
                              capture_output=True, text=True, env=self._env(), timeout=60)

    def sources(self, out: str) -> list[str]:
        return [l.split("\t")[1] for l in out.splitlines() if l.startswith("spec_source\t")]

    def test_session_context_counts_only_when_branch_matches(self):
        self.git("checkout", "-q", "-b", "feat/x")
        self.write(".claude/session-context.md", "---\nbranch: feat/x\nissue_id: CP-1\n---\n")
        r = self.cli("plan", "--effort", "high", "--size-tier", "large")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.sources(r.stdout), ["session-context"])
        self.assertIn("reviewer\tR3\tsolo\tspec-compliance", r.stdout)
        self.write(".claude/session-context.md", "---\nbranch: feat/other\n---\n")
        r = self.cli("plan", "--effort", "high", "--size-tier", "large")
        self.assertEqual(self.sources(r.stdout), ["none"])
        self.assertNotIn("spec-compliance", r.stdout)

    def test_issue_file_found_from_session_context_issue_id(self):
        """ブランチ名に Issue ID が無くても（GitHub の番号で切ったブランチ）、一致した session-context の issue_id で探す."""
        self.git("checkout", "-q", "-b", "fix/351-x")
        self.write(".claude/session-context.md", "---\nbranch: fix/351-x\nissue_id: CP-9\n---\n")
        self.write(".claude/indie/cp/issues/CP-9.md", "# CP-9\n")
        r = self.cli("plan", "--effort", "high", "--size-tier", "large")
        self.assertEqual(self.sources(r.stdout), ["session-context", "issue-file"])

    def test_issue_file_found_from_worktree_in_main_checkout(self):
        self.write(".gitignore", ".claude/\nwt/\n")
        self.git("add", ".gitignore")
        self.git("commit", "-q", "-m", "ignore")
        self.write(".claude/indie/cp/issues/CP-1.md", "# CP-1\n")
        self.write(".claude/indie/cp/issues/CP-2.md", "# CP-2\n")
        self.git("worktree", "add", "-q", "-b", "feat/CP-1-x", str(self.root / "wt"))
        r = self.cli("plan", "--effort", "high", "--size-tier", "large", cwd=self.root / "wt")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = [l for l in r.stdout.splitlines() if l.startswith("spec_source\t")]
        self.assertEqual(len(lines), 1, r.stdout)
        self.assertTrue(lines[0].endswith("/.claude/indie/cp/issues/CP-1.md"), lines)

    def test_missing_spec_path_is_reported(self):
        r = self.cli("plan", "--effort", "high", "--size-tier", "large", "--spec", "nope/spec.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("spec_missing\tnope/spec.md", r.stdout)
        self.assertNotIn("spec-compliance", r.stdout)
        self.write("features/a/spec.md", "Feature: a\n")
        r = self.cli("plan", "--effort", "high", "--size-tier", "large", "--spec", "features/a/spec.md")
        self.assertEqual(self.sources(r.stdout), ["spec"])

    def test_spec_source_argument(self):
        r = self.cli("plan", "--effort", "high", "--size-tier", "large", "--spec-source", "pr-issue:#12")
        self.assertIn("spec_source\tpr-issue\t#12", r.stdout)
        self.assertEqual(self.cli("plan", "--effort", "high", "--size-tier", "large",
                                  "--spec-source", "wiki:x").returncode, 2)

    def test_usage_errors_exit_2(self):
        for args in (["--effort", "${CLAUDE_EFFORT}", "--size-tier", "large"],
                     ["--effort", "high", "--size-tier", "huge"],
                     ["--effort", "high", "--size-tier", "large", "--activated", "perf"],
                     ["--effort", "high", "--size-tier", "large", "--activated", "spec-compliance"],
                     ["--effort", "high", "--size-tier", "large", "--focus", "security", "--exclude", "config"],
                     ["--effort", "high", "--size-tier", "large", "--plan-file", "/tmp/x.json"],
                     ["--effort", "high", "--size-tier", "large", "--branch=feat/CP-1"],
                     ["--effort", "high", "--size-tier", "large", "--plan-f", "/tmp/x.json"]):
            r = self.cli("plan", *args)
            self.assertEqual(r.returncode, 2, (args, r.stdout))
            self.assertIn("FATAL", r.stderr)

    def test_check_passes_when_plan_has_no_reviewer(self):
        r = self.cli("plan", "--effort", "high", "--size-tier", "large", "--exclude", "bug-detection,claude-md-compliance")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("reviewer\t", r.stdout)
        ok = self.cli("check", stdin="")
        self.assertEqual((ok.returncode, ok.stdout.strip()), (0, "ok"), ok.stderr)

    def test_pr_selects_its_own_plan_file(self):
        """--pr が引数の末尾にあっても値を受け取り、PR ごとの保存先に書く。値が無ければ exit 2."""
        r = self.cli("plan", "--effort", "high", "--size-tier", "large", "--pr", "7")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("-pr7.json", r.stdout)
        self.assertEqual(self.cli("check", "--pr", "7", stdin=r.stdout).returncode, 0)
        self.assertEqual(self.cli("check", stdin=r.stdout).returncode, 2)
        bad = self.cli("plan", "--effort", "high", "--size-tier", "large", "--pr")
        self.assertEqual(bad.returncode, 2)
        self.assertIn("FATAL", bad.stderr)

    def test_check_round_trip_and_exit_codes(self):
        self.assertEqual(self.cli("check", stdin="reviewer\tR1\tsolo\tbug-detection\n").returncode, 2)
        r = self.cli("plan", "--effort", "high", "--size-tier", "small", "--activated", "security")
        self.assertEqual(r.returncode, 0, r.stderr)
        ok = self.cli("check", stdin=r.stdout)
        self.assertEqual((ok.returncode, ok.stdout.strip()), (0, "ok"), ok.stderr)
        bad = "\n".join(l for l in r.stdout.splitlines() if "claude-md-compliance" not in l)
        ng = self.cli("check", stdin=bad)
        self.assertEqual(ng.returncode, 1)
        self.assertTrue(ng.stdout.startswith("NG\tmin-guarantee\t"), ng.stdout)
        self.assertEqual(self.cli("check", stdin="effort=high\n").returncode, 2)
        self.assertEqual(self.cli("check", "--effort", "high", stdin=r.stdout).returncode, 2)

    def test_plan_file_is_json_and_triage_signals_removes_it(self):
        r = self.cli("plan", "--effort", "high", "--size-tier", "large")
        path = Path(next(l.split("=", 1)[1] for l in r.stdout.splitlines() if l.startswith("plan_file=")))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["reviewer_cap"], 6)
        self.write("a.txt", "x\n")
        self.git("add", "a.txt")
        t = subprocess.run(["bash", str(TRIAGE), "--base", "HEAD"], cwd=self.root, capture_output=True,
                           text=True, env=self._env(), timeout=60)
        self.assertEqual(t.returncode, 0, t.stderr)
        self.assertFalse(path.exists())
        self.assertEqual(self.cli("check", stdin=r.stdout).returncode, 2)


if __name__ == "__main__":
    unittest.main()
