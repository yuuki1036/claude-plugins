#!/usr/bin/env python3
"""計測の更新（`code-review/scripts/metrics-update.sh` / `lib/metrics_update.py`）のテスト. GitHub issue #480.

使い捨てのストア・手元のログ・状態ファイル・git リポジトリを立て、CLI 境界越しに叩く。判定の小関数は
純関数として見る。世代・再レビュー・delta の判定は retro と共有の `lib/payload_judge.py` にあり、
`test_code_review_payload_judge.py` が見る。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import git_env  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "code-review" / "scripts"
WRAPPER = SCRIPTS / "metrics-update.sh"
DOC = REPO / "code-review" / "references" / "orchestration-measurement.md"
sys.path.insert(0, str(SCRIPTS / "lib"))

import metrics_update as mu  # noqa: E402

SELF, REVIEW = "code-review:self-review", "code-review:review"


def payload(**kw) -> dict:
    p = {
        "machine_id": "m1", "plugin_version": "2.168.0", "effort": "medium", "size_tier": "small",
        "models": {"main": "claude-opus-5-5"}, "duration_fleet_min": 4, "duration_min": 5,
        "blocker_count": 0, "critical_count": 0, "major_count": 1, "minor_count": 2,
        "tokens": {"schema": 3, "window": "since-t0", "main_output_k": 10, "sub_output_k": 20,
                   "sub_cache_read_k": 300},
        "dispatch": {"max_inter_wave_sec": 60},
    }
    p.update(kw)
    return p


def ev(ts, p, plugin=SELF) -> dict:
    return {"event": "review:completed", "ts": ts, "plugin": plugin, "payload": p}


def write_jsonl(path: Path, events) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return path


class Env(unittest.TestCase):
    """HOME・設定 dir・git リポジトリを使い捨てにする（実機のストアと状態ファイルに当てない）."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.env = git_env.scrub(HOME=str(self.home), CLAUDE_REVIEW_CONFIG_DIR=str(self.tmp / "cfg"))
        for k in ("REVIEW_METRICS_DIR", "CLAUDE_PROJECT_DIR"):
            self.env.pop(k, None)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.commit("init", "README.md")
        self.state = self.tmp / "state.json"

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], env=self.env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, msg, rel):
        f = self.repo / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(msg + "\n", encoding="utf-8")
        self.git("add", rel)
        self.git("commit", "-q", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def run_cli(self, *args, mode=None):
        cmd = ["bash", str(WRAPPER)] + ([mode] if mode else []) + list(args)
        if mode != "retro":
            cmd += ["--state", str(self.state)]
        return subprocess.run(cmd, cwd=self.repo, env=self.env, capture_output=True, text=True)

    def run_json(self, *args):
        r = self.run_cli(*args, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def store(self, events_by_label):
        d = self.tmp / "review-metrics"
        for label, events in events_by_label.items():
            write_jsonl(d / "events" / ("%s.jsonl" % label), events)
        return d


class NoDataTest(Env):
    def test_no_store_no_logs_returns_json_with_zero(self):
        out = self.run_json()
        self.assertEqual(out["scope"]["n"], 0)
        self.assertIsNone(out["scope"]["store"])
        self.assertTrue(out["since_previous"]["first_run"])
        self.assertFalse(self.state.exists(), "既定の実行は状態ファイルを作らない")

    def test_default_store_location_is_used_when_present(self):
        d = self.home / ".claude" / "review-metrics"
        write_jsonl(d / "events" / "m1.jsonl", [ev("2026-11-01T00:00:00Z", payload())])
        out = self.run_json()
        self.assertEqual(out["scope"]["n"], 1)
        self.assertEqual(out["scope"]["store"], "~/.claude/review-metrics")

    def test_no_store_flag_skips_the_default_store(self):
        d = self.home / ".claude" / "review-metrics"
        write_jsonl(d / "events" / "m1.jsonl", [ev("2026-11-01T00:00:00Z", payload())])
        self.assertEqual(self.run_json("--no-store")["scope"]["n"], 0)

    def test_explicit_missing_paths_are_fatal(self):
        r = self.run_cli("--store", str(self.tmp / "nope"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("--store", r.stderr)
        r = self.run_cli("--logs", str(self.tmp / "nope.jsonl"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("--logs", r.stderr)

    def test_bad_split_version_is_fatal(self):
        self.assertEqual(self.run_cli("--split-version", "v2.1").returncode, 2)


class PopulationTest(Env):
    def test_sanitized_and_raw_rows_count_once_and_raw_wins(self):
        raw = payload(machine_id="host-a", pr="12", effort="medium")
        san = payload(machine_id="m1", effort="medium")
        store = self.store({"m1": [ev("2026-11-01T00:00:00Z", san)]})
        log = write_jsonl(self.repo / ".claude" / "events.jsonl", [ev("2026-11-01T00:00:00Z", raw)])
        out = self.run_json("--store", str(store), "--logs", str(log))
        self.assertEqual(out["scope"]["n"], 1)
        self.assertEqual(out["scope"]["dedup_dropped"], 1)
        self.assertEqual(out["scope"]["dedup_conflicts"], 0, "サニタイズ済みの形として説明できる")
        r = out["since_previous"]
        self.assertEqual(r["n"], 1)

    def test_malformed_rows_do_not_stop_the_whole_run(self):
        bad_plugin = ev("2026-11-03T00:00:00Z", payload())
        bad_plugin["plugin"] = ["x"]
        store = self.store({"m1": [ev(123, payload()), ev(["2026"], payload(machine_id="m2")),
                                   ev({"a": 1}, payload(machine_id="m3")),
                                   ev("2026-11-01T00:00:00Z", payload(effort=["x"], size_tier={"a": 1})),
                                   ev("2026-11-02T00:00:00Z", payload()), bad_plugin]})
        out = self.run_json("--store", str(store))
        self.assertEqual(out["scope"]["n"], 6)
        self.assertIn("?", {r["effort"] for r in out["comparison"]["rows"]})

    def test_store_outside_home_or_with_another_name_is_hashed(self):
        named = self.store({"m1": [ev("2026-11-01T00:00:00Z", payload())]})
        self.assertTrue(self.run_json("--store", str(named))["scope"]["store"].startswith("<store sha="))
        other = self.home / "acme-secret-metrics"
        write_jsonl(other / "events" / "m1.jsonl", [ev("2026-11-01T00:00:00Z", payload())])
        r = self.run_cli("--store", str(other), "--json")
        self.assertNotIn("acme-secret", r.stdout)
        bad = self.tmp / "acme-secret-missing"
        r = self.run_cli("--store", str(bad), mode="retro")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("acme-secret", r.stderr)

    def test_local_logs_default_to_this_repo(self):
        write_jsonl(self.repo / ".claude" / "events.jsonl", [ev("2026-11-01T00:00:00Z", payload())])
        out = self.run_json("--no-store")
        self.assertEqual(out["scope"]["n"], 1)
        self.assertEqual(len(out["scope"]["local_logs"]), 1)

    def test_output_hides_raw_machine_names_and_paths(self):
        store = self.store({"m1": [ev("2026-11-01T00:00:00Z", payload(machine_id="secret-host"))]})
        r = self.run_cli("--store", str(store), "--json")
        self.assertNotIn("secret-host", r.stdout)
        self.assertNotIn(str(self.tmp), r.stdout)
        r = self.run_cli("--store", str(store))
        self.assertNotIn("secret-host", r.stdout)
        self.assertNotIn(str(self.tmp), r.stdout)


class StateTest(Env):
    def test_record_writes_state_and_next_run_shows_only_new_rows_per_machine(self):
        store = self.store({
            "m1": [ev("2026-11-01T00:00:00Z", payload(machine_id="m1"))],
            "m2": [ev("2026-11-03T00:00:00Z", payload(machine_id="m2"))],
        })
        r = self.run_cli("--store", str(store), "--record")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(st["n"], 2)
        self.assertEqual(st["last_ts_by_machine"], {"m1": "2026-11-01T00:00:00Z", "m2": "2026-11-03T00:00:00Z"})
        if os.name == "posix":
            self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)
        # m1 の回は m2 の最新より前の時刻だが、m1 としては新しいので数える（後から同期された回）
        self.store({
            "m1": [ev("2026-11-01T00:00:00Z", payload(machine_id="m1")),
                   ev("2026-11-02T00:00:00Z", payload(machine_id="m1"))],
            "m2": [ev("2026-11-03T00:00:00Z", payload(machine_id="m2"))],
        })
        out = self.run_json("--store", str(store))
        sp = out["since_previous"]
        self.assertFalse(sp["first_run"])
        self.assertEqual(sp["n"], 1)
        self.assertEqual(sp["by_machine"], {"m1": 1})
        self.assertEqual(out["scope"]["previous"]["n"], 2)

    def test_corrupt_state_is_fatal_and_left_untouched(self):
        self.state.write_text("{broken", encoding="utf-8")
        r = self.run_cli("--record")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.state.read_text(encoding="utf-8"), "{broken")

    def test_state_with_broken_machine_map_is_fatal(self):
        self.state.write_text(json.dumps({"schema_version": 1, "last_ts_by_machine": []}), encoding="utf-8")
        r = self.run_cli()
        self.assertEqual(r.returncode, 2)
        self.assertIn("last_ts_by_machine", r.stderr)

    def test_state_with_wrong_value_types_is_fatal(self):
        for st in ({"schema_version": 1, "last_ts_by_machine": {"m1": 5}},
                   {"schema_version": 1, "last_ts_by_machine": {}, "main_commit": 12345678}):
            with self.subTest(st=st):
                self.state.write_text(json.dumps(st), encoding="utf-8")
                r = self.run_cli()
                self.assertEqual(r.returncode, 2)
                self.assertIn("状態ファイルの", r.stderr)
                self.assertNotIn(str(self.tmp), r.stderr, "--state のパスは出さない")

    def test_wrong_schema_state_is_fatal(self):
        self.state.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
        self.assertEqual(self.run_cli().returncode, 2)

    def test_commits_since_previous_main_touching_code_review_only(self):
        self.run_cli("--record")
        self.commit("feat: code-review change", "code-review/a.txt")
        self.commit("feat: other plugin", "other/b.txt")
        out = self.run_json()
        cm = out["commits"]
        self.assertIsNone(cm["reason"])
        self.assertEqual(cm["total"], 1)
        self.assertIn("code-review change", cm["commits"][0])

    def test_first_run_has_no_commit_diff(self):
        self.assertEqual(self.run_json()["commits"]["reason"], "no-previous")


class ComparisonTest(unittest.TestCase):
    @staticmethod
    def rows(*ps):
        return [{"ts": "2026-11-0%dT00:00:00Z" % (i + 1), "plugin": SELF, "p": p, "src": "x"}
                for i, p in enumerate(ps)]

    def test_rereview_is_excluded_and_counted(self):
        cp = mu.comparison(self.rows(payload(), payload(invocation={"rereview": True})))
        self.assertEqual(cp["rereview_excluded"], 1)
        self.assertEqual(sum(r["n"] for r in cp["rows"]), 1)

    def test_delta_full_and_generation_are_separate_rows(self):
        cp = mu.comparison(self.rows(payload(), payload(review_scope={"mode": "delta"}),
                                     payload(models={"main": "claude-opus-4-8"})))
        keys = {(r["generation"], r["scope"]) for r in cp["rows"]}
        self.assertEqual(keys, {("opus-5-5", "full"), ("opus-5-5", "delta"), ("opus-4-8", "full")})

    def test_generation_filter(self):
        cp = mu.comparison(self.rows(payload(), payload(models={"main": "claude-opus-4-8"})),
                           generation="opus-4-8")
        self.assertEqual([r["generation"] for r in cp["rows"]], ["opus-4-8"])

    def test_dispatch_and_tokens_only_from_reliable_versions(self):
        cp = mu.comparison(self.rows(payload(plugin_version="2.130.5"),
                                     payload(plugin_version="2.130.6", dispatch=None)))
        r = cp["rows"][0]
        self.assertEqual(r["n"], 2)
        self.assertEqual(r["dispatch_n"], 1, "2.130.6 より前の回は dispatch の母数に入れない")
        self.assertEqual(r["dispatch_missing"], 1)
        self.assertEqual(r["tokens_n"], 1)

    def test_tokens_schema_and_window_filter(self):
        t2 = {"schema": 2, "window": "since-t0", "main_output_k": 99}
        tw = {"schema": 3, "window": "session", "main_output_k": 99}
        cp = mu.comparison(self.rows(payload(tokens=t2), payload(tokens=tw), payload()))
        r = cp["rows"][0]
        self.assertEqual(r["tokens_n"], 1)
        self.assertEqual(r["main_output_k"], 10)

    def test_measurement_gap_counts_as_dispatch_missing(self):
        cp = mu.comparison(self.rows(payload(measurement_gaps=["dispatch"])))
        self.assertEqual(cp["rows"][0]["dispatch_missing"], 1)

    def test_split_version_groups(self):
        cp = mu.comparison(self.rows(payload(plugin_version="2.150.0"), payload(plugin_version="2.160.0"),
                                     payload(plugin_version=None)), split="2.158.0")
        groups = sorted(r["version_group"] for r in cp["rows"])
        self.assertEqual(groups, ["2.158.0 より前", "2.158.0 以上", "版未記録"])

    def test_reported_median_skips_runs_without_counts(self):
        p = payload()
        for k in ("blocker_count", "critical_count", "major_count", "minor_count"):
            p.pop(k)
        cp = mu.comparison(self.rows(p, payload(major_count=3)))
        r = cp["rows"][0]
        self.assertEqual(r["reported_n"], 1)
        self.assertEqual(r["reported"], 5)


class ComparisonCliTest(Env):
    def test_split_and_generation_flags(self):
        store = self.store({"m1": [ev("2026-11-01T00:00:00Z", payload(plugin_version="2.150.0")),
                                   ev("2026-11-02T00:00:00Z", payload(models={"main": "claude-opus-4-8"}))]})
        out = self.run_json("--store", str(store), "--split-version", "2.158.0", "--generation", "claude-opus-5-5")
        cp = out["comparison"]
        self.assertEqual(cp["generation"], "opus-5-5")
        self.assertEqual([r["version_group"] for r in cp["rows"]], ["2.158.0 より前"])


class BaselineTest(unittest.TestCase):
    DOC = "intro\n## 15. ベースライン\n\n<!-- METRICS-BASELINE: generation=claude-opus-5-5 taken=2026-10-25 review_xhigh_need=%s -->\n\n## 16. 次\n"

    @staticmethod
    def rows(*specs):
        return [{"ts": ts, "plugin": plugin, "p": p, "src": "x"} for ts, plugin, p in specs]

    def test_marker_states(self):
        self.assertEqual(mu.parse_baseline_marker("## 14. x\n")["status"], "no-section")
        self.assertEqual(mu.parse_baseline_marker("x\n## 15. a\nbody\n## 16. b\n")["status"], "no-marker")
        self.assertEqual(mu.parse_baseline_marker("x\n## 15. a\n<!-- METRICS-BASELINE: generation -->\n")["status"],
                         "malformed")
        self.assertEqual(mu.parse_baseline_marker(self.DOC % "x")["status"], "malformed")
        m = mu.parse_baseline_marker(self.DOC % "5")
        self.assertEqual((m["status"], m["generation"], m["taken"], m["review_xhigh_need"]),
                         ("ok", "opus-5-5", "2026-10-25", 5))

    def test_marker_outside_section_15_is_ignored(self):
        text = "x\n## 15. a\nbody\n## 16. b\n<!-- METRICS-BASELINE: generation=g taken=2026-01-01 -->\n"
        self.assertEqual(mu.parse_baseline_marker(text)["status"], "no-marker")

    def test_xhigh_reviews_after_taken_make_it_due(self):
        m = mu.parse_baseline_marker(self.DOC % "2")
        xr = payload(effort="xhigh")
        rows = self.rows(("2026-10-20T00:00:00Z", REVIEW, xr), ("2026-10-26T00:00:00Z", REVIEW, xr))
        self.assertFalse(mu.baseline_due(rows, m)["due"], "取り直しより前の回は数えない")
        rows += self.rows(("2026-10-27T00:00:00Z", REVIEW, xr),
                          ("2026-10-28T00:00:00Z", SELF, xr),
                          ("2026-10-29T00:00:00Z", REVIEW, payload(effort="xhigh", invocation={"rereview": True})))
        d = mu.baseline_due(rows, m)
        self.assertEqual(d["xhigh_review_n"], 2, "self-review と再レビューは数えない")
        self.assertTrue(d["due"])

    def test_need_zero_disables_the_xhigh_condition(self):
        m = mu.parse_baseline_marker(self.DOC % "0")
        xr = payload(effort="max")
        rows = self.rows(*[("2026-10-%dT00:00:00Z" % d, REVIEW, xr) for d in range(26, 31)])
        d = mu.baseline_due(rows, m)
        self.assertEqual(d["xhigh_review_n"], 5)
        self.assertFalse(d["due"])

    @staticmethod
    def gen(model):
        return payload(models={"main": model})

    def seq(self, *models, day="2026-10-26"):
        return self.rows(*[("%sT00:%02d:00Z" % (day, i), SELF, self.gen(mdl)) for i, mdl in enumerate(models)])

    def test_generation_change_makes_it_due(self):
        m = mu.parse_baseline_marker(self.DOC % "0")
        d = mu.baseline_due(self.seq("claude-opus-6", "", "claude-opus-6", "claude-opus-6", "", "claude-opus-6"), m)
        self.assertEqual(d["window_generations"], ["opus-6"] * 4, "mixed は世代に数えない")
        self.assertTrue(d["generation_changed"])
        self.assertTrue(d["due"])

    def test_switch_is_noticed_even_after_many_old_generation_runs(self):
        m = mu.parse_baseline_marker(self.DOC % "0")
        old = [("2026-10-26T%02d:%02d:00Z" % (i // 60, i % 60), SELF, payload()) for i in range(300)]
        new = [("2026-11-01T00:00:0%dZ" % i, SELF, self.gen("claude-opus-6")) for i in range(4)]
        self.assertTrue(mu.baseline_due(self.rows(*(old + new)), m)["due"],
                        "旧世代の累計に関わらず、全マシンが移ってから 4 回で気づく")
        self.assertFalse(mu.baseline_due(self.rows(*(old + new[:3])), m)["due"])

    def test_one_run_on_another_model_does_not_flip_the_generation(self):
        m = mu.parse_baseline_marker(self.DOC % "0")
        o, s5 = "claude-opus-5-5", "claude-sonnet-5-5"
        self.assertFalse(mu.baseline_due(self.seq(o, o, o, s5), m)["due"])
        self.assertFalse(mu.baseline_due(self.seq(s5, o), m)["due"], "窓が埋まるまでは判定しない")
        lone = mu.baseline_due(self.rows(("2026-10-25T01:00:00Z", SELF, self.gen(s5))), m)
        self.assertFalse(lone["due"], "印の世代が 0 件でも、別の世代 1 回では変えない")

    def test_machines_on_different_generations_do_not_flap(self):
        m = mu.parse_baseline_marker(self.DOC % "0")
        o, n = "claude-opus-5-5", "claude-opus-6"
        # 1 台だけ移った時期: 新しい世代が続いても、旧世代のマシンの回が窓に残る間は変わらない
        for models in ((o, n, n), (o, n, n, o), (o, n, n, n), (n, o, n, n)):
            with self.subTest(models=models):
                self.assertFalse(mu.baseline_due(self.seq(*models), m)["due"])

    def test_two_new_generations_alternating_still_make_it_due(self):
        m = mu.parse_baseline_marker(self.DOC % "0")
        d = mu.baseline_due(self.seq("claude-sonnet-6", "claude-opus-6", "claude-sonnet-6", "claude-opus-6"), m)
        self.assertTrue(d["due"], "直近 4 回に印の世代が 1 回も無い")

    def test_order_of_rows_does_not_matter(self):
        m = mu.parse_baseline_marker(self.DOC % "0")
        new = [("2026-11-01T00:00:0%dZ" % i, SELF, self.gen("claude-opus-6")) for i in range(4)]
        old = [("2026-10-26T00:00:0%dZ" % i, SELF, payload()) for i in range(3)]
        self.assertTrue(mu.baseline_due(self.rows(*(new + old)), m)["due"],
                        "ファイルの順（マシンごと）と時刻の順が逆でも、時刻で直近を決める")
        self.assertFalse(mu.baseline_due(self.rows(*(old[:1] + new[:3] + old[1:])), m)["due"])

    def test_runs_on_the_taken_day_count(self):
        m = mu.parse_baseline_marker(self.DOC % "1")
        rows = self.rows(("2026-10-24T23:59:59Z", REVIEW, payload(effort="xhigh")),
                         ("2026-10-25T00:00:00Z", REVIEW, payload(effort="xhigh")))
        d = mu.baseline_due(rows, m)
        self.assertEqual(d["xhigh_review_n"], 1)
        self.assertTrue(d["due"])

    def test_real_doc_has_a_readable_marker(self):
        m = mu.parse_baseline_marker(DOC.read_text(encoding="utf-8"))
        self.assertEqual(m["status"], "ok", "orchestration-measurement.md `## 15` の METRICS-BASELINE の印")


class VocabDropsTest(Env):
    def test_raw_diff_lists_dropped_keys_values_and_coverage(self):
        raw = payload(machine_id="host-a", pr="12", new_key=1, invocation={"parent": "acme:skill"},
                      missing_coverage=["reviewer:acme-doc"])
        san = payload(machine_id="m1", invocation={"parent": "other"},
                      missing_coverage=["reviewer:other"], sanitize_drops={"keys": 1, "values": 1, "coverage": 1})
        store = self.store({"m1": [ev("2026-11-01T00:00:00Z", san),
                                   ev("2026-11-02T00:00:00Z", payload(sanitize_drops={"keys": 1}))]})
        (store / "bin").mkdir()
        (store / "bin" / "sanitize.py").write_text('DENY_KEYS = frozenset({"pr", "base"})\n', encoding="utf-8")
        log = write_jsonl(self.repo / ".claude" / "events.jsonl", [ev("2026-11-01T00:00:00Z", raw)])
        out = self.run_json("--store", str(store), "--logs", str(log))
        vd = out["vocab_drops"]
        self.assertTrue(vd["local_only"])
        runs = vd["runs"]
        self.assertEqual([r["raw_found"] for r in runs], [True, False])
        d = runs[0]["diff"]
        self.assertEqual(d["keys"], ["new_key"])
        self.assertEqual(d["denied_keys"], ["pr"])
        self.assertEqual(d["values"], [{"path": "invocation.parent", "value": "acme:skill"}])
        self.assertEqual(d["coverage"], [{"path": "missing_coverage[0]", "value": "reviewer:acme-doc"}])

    def test_runs_without_drops_are_not_listed(self):
        store = self.store({"m1": [ev("2026-11-01T00:00:00Z", payload(sanitize_drops={"keys": 0}))]})
        self.assertEqual(self.run_json("--store", str(store))["vocab_drops"]["runs"], [])

    def test_text_output_warns_not_to_paste(self):
        store = self.store({"m1": [ev("2026-11-01T00:00:00Z", payload(sanitize_drops={"keys": 1}))]})
        r = self.run_cli("--store", str(store))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("公開先に貼らない", r.stdout)


class WorkdirTest(Env):
    def test_workdir_is_new_private_dir_each_time(self):
        self.env["TMPDIR"] = str(self.tmp)
        dirs = []
        for _ in range(2):
            r = subprocess.run(["bash", str(WRAPPER), "workdir"], cwd=self.repo, env=self.env,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            d = Path(r.stdout.strip().split("=", 1)[1])
            self.assertTrue(d.is_dir() and not d.is_symlink())
            if os.name == "posix":
                self.assertEqual(d.stat().st_mode & 0o777, 0o700)
            dirs.append(d)
        self.assertNotEqual(dirs[0], dirs[1], "固定の名前にしない（先に置かれた symlink を踏まない）")


class RetroModeTest(Env):
    def test_retro_reads_the_same_population(self):
        store = self.store({"m1": [ev("2026-11-01T00:00:00Z", payload())],
                            "m2": [ev("2026-11-02T00:00:00Z", payload(machine_id="m2"))]})
        log = write_jsonl(self.repo / ".claude" / "events.jsonl", [ev("2026-11-03T00:00:00Z", payload())])
        r = self.run_cli("--store", str(store), "--logs", str(log), "--json", mode="retro")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["n"], 3)
        self.assertEqual(out.get("sources_scope"), "explicit")

    def test_retro_with_bad_store_is_fatal(self):
        r = self.run_cli("--store", str(self.tmp / "nope"), mode="retro")
        self.assertEqual(r.returncode, 2)


class WrapperArgsTest(Env):
    """metrics-update.sh の引数の境界（GitHub issue #522）。`--state` を後ろに足さずに叩く（末尾の引数を見るため）."""

    def run_raw(self, *args):
        return subprocess.run(["bash", str(WRAPPER), *args], cwd=self.repo, env=self.env,
                              capture_output=True, text=True)

    def test_logs_without_paths_is_fatal(self):
        for args in (("--logs",), ("--logs", "--no-store")):
            with self.subTest(args=args):
                r = self.run_raw(*args)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("--logs にパスが必要", r.stderr)

    def test_store_as_the_last_pair_is_accepted(self):
        store = self.store({"m1": [ev("2026-11-01T00:00:00Z", payload())]})
        r = self.run_raw("--json", "--store", str(store))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["scope"]["n"], 1)

    def test_store_without_value_is_fatal(self):
        r = self.run_raw("--store")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--store に値が必要", r.stderr)

    def test_retro_without_any_source_does_not_pass_an_empty_logs(self):
        r = self.run_raw("retro", "--no-store")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("--logs にパスが必要", r.stderr)


class SmallFunctionsTest(unittest.TestCase):
    def test_median_of_odd_and_even_lengths(self):
        self.assertEqual(mu.median([3, 1, 2]), 2)
        self.assertEqual(mu.median([4, 1, 3, 2]), 2.5)
        self.assertIsNone(mu.median([]))

    def test_state_display_shows_only_the_default_path(self):
        self.assertEqual(mu.state_display(mu.DEFAULT_STATE), "~/.claude/code-review/metrics-update-state.json")
        self.assertEqual(mu.state_display("/elsewhere/state.json"), "--state のファイル")

    def test_store_files_without_events_dir_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(mu.store_files(d), [])


class ReadEventsTest(unittest.TestCase):
    def test_only_review_completed_dicts_with_dict_payload_are_read(self):
        lines = [
            '{"event": "review:completed", "ts": ',                          # 壊れた JSON（先頭）
            json.dumps(ev("2026-11-01T00:00:00Z", payload())),
            '{"event": "review:completed", "payload": ',                     # 壊れた JSON（有効な行の後）
            json.dumps(["review:completed"]),                                # dict でない
            json.dumps({"event": "x", "note": "review:completed", "payload": {}}),  # 別の event
            json.dumps({"event": "review:completed", "payload": "x"}),     # payload が dict でない
        ]
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "e.jsonl"
            f.write_text("\n".join(lines) + "\n", encoding="utf-8")
            evs = mu.read_events(str(f))
        self.assertEqual([e["ts"] for e in evs], ["2026-11-01T00:00:00Z"])


class GitTest(Env):
    def call(self, fn, *args):
        env = dict(self.env, GIT_CEILING_DIRECTORIES=str(self.tmp))
        with unittest.mock.patch.dict(os.environ, env, clear=True):
            return fn(*args)

    def test_git_info(self):
        sha = self.git("rev-parse", "HEAD")
        self.assertEqual(self.call(mu.git_info, str(self.repo)),
                         {"present": True, "main_commit": sha, "ref": "main"})
        plain = self.tmp / "plain"
        plain.mkdir()
        self.assertEqual(self.call(mu.git_info, str(plain)), {"present": False, "main_commit": None, "ref": None})
        self.git("branch", "-m", "main", "other")
        self.assertEqual(self.call(mu.git_info, str(self.repo)), {"present": True, "main_commit": None, "ref": None})

    def test_git_log_since_failure_reasons(self):
        sha = self.git("rev-parse", "HEAD")
        self.assertEqual(self.call(mu.git_log_since, str(self.repo), "1" * 40, sha)["reason"], "prev-unreachable")
        self.assertEqual(self.call(mu.git_log_since, str(self.repo), sha, "0" * 40)["reason"], "log-failed")


class StateMoreTest(Env):
    def test_wrong_shape_state_names_the_shape(self):
        for st in ([1], {"schema_version": 99}):
            with self.subTest(st=st):
                self.state.write_text(json.dumps(st), encoding="utf-8")
                r = self.run_cli()
                self.assertEqual(r.returncode, 2)
                self.assertIn("状態ファイルの形が違う", r.stderr)

    def test_rows_without_ts_are_not_recorded_as_the_machine_latest(self):
        store = self.store({"m1": [ev("", payload())]})
        r = self.run_cli("--store", str(store), "--record")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(self.state.read_text(encoding="utf-8"))["last_ts_by_machine"], {})

    def test_new_rows_are_counted_by_version(self):
        store = self.store({"m1": [ev("2026-11-01T00:00:00Z", payload())]})
        self.assertEqual(self.run_cli("--store", str(store), "--record").returncode, 0)
        self.store({"m1": [ev("2026-11-01T00:00:00Z", payload()),
                           ev("2026-11-02T00:00:00Z", payload()),
                           ev("2026-11-03T00:00:00Z", payload(plugin_version=None))]})
        sp = self.run_json("--store", str(store))["since_previous"]
        self.assertEqual(sp["by_version"], {"2.168.0": 1, "未記録": 1})

    def test_same_log_given_twice_is_read_once(self):
        log = write_jsonl(self.tmp / "e.jsonl", [ev("2026-11-01T00:00:00Z", payload())])
        sc = self.run_json("--no-store", "--logs", str(log), str(log))["scope"]
        self.assertEqual((sc["n"], sc["dedup_dropped"]), (1, 0))


class ComparisonMoreTest(unittest.TestCase):
    rows = staticmethod(ComparisonTest.rows)

    def test_split_version_boundary_is_inclusive(self):
        cp = mu.comparison(self.rows(payload(plugin_version="2.158.0")), split="2.158.0")
        self.assertEqual(cp["rows"][0]["version_group"], "2.158.0 以上")

    def test_rows_are_sorted_by_key(self):
        cp = mu.comparison(self.rows(payload(), payload(models={"main": "claude-opus-4-8"})))
        self.assertEqual([r["generation"] for r in cp["rows"]], ["opus-4-8", "opus-5-5"])

    def test_medians_keep_zero_and_drop_negative(self):
        for vals, want in (((0, 4, 5), 4), ((-1, 4, 5), 4.5)):
            with self.subTest(vals=vals):
                r = mu.comparison(self.rows(*[payload(duration_fleet_min=v) for v in vals]))["rows"][0]
                self.assertEqual(r["fleet_min"], want)
                r = mu.comparison(self.rows(*[payload(dispatch={"max_inter_wave_sec": v * 30})
                                              for v in vals]))["rows"][0]
                self.assertEqual(r["max_inter_wave_sec"], want * 30)

    def test_reported_skips_a_run_missing_one_count(self):
        p = payload()
        p.pop("major_count")
        r = mu.comparison(self.rows(p, payload()))["rows"][0]
        self.assertEqual((r["reported_n"], r["reported"]), (1, 3))


class BaselineMoreTest(unittest.TestCase):
    def test_section_at_the_very_start_is_found(self):
        m = mu.parse_baseline_marker("\n## 15. a\n<!-- METRICS-BASELINE: generation=g taken=2026-01-01 -->\n")
        self.assertEqual(m["status"], "ok")

    def test_malformed_tokens(self):
        for body in ("generation=g taken=2026-01-01 extra=", "generation=g taken=2026-01-01 junk",
                     "taken=2026-01-01"):
            with self.subTest(body=body):
                m = mu.parse_baseline_marker("x\n## 15. a\n<!-- METRICS-BASELINE: %s -->\n" % body)
                self.assertEqual(m["status"], "malformed")

    def test_due_is_none_without_a_marker(self):
        marker = {"status": "no-marker"}
        self.assertEqual(mu.baseline_due([], marker), {"marker": marker, "due": None})


class DenyKeysAndDiffTest(unittest.TestCase):
    def deny(self, src):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "bin").mkdir()
            (Path(d) / "bin" / "sanitize.py").write_text(src, encoding="utf-8")
            return mu.deny_keys(d)

    def test_deny_keys_reads_only_the_deny_keys_assignment(self):
        self.assertEqual(self.deny("import os\nALLOW = {'pr'}\nDENY_KEYS = {'base'}\n"), frozenset({"base"}))
        self.assertEqual(self.deny("DENY_KEYS = frozenset({'pr'})\n"), frozenset({"pr"}))

    def test_deny_keys_rejects_non_string_collections(self):
        for src in ("DENY_KEYS = 'pr'\n", "DENY_KEYS = frozenset({'pr', 1})\n"):
            with self.subTest(src=src):
                self.assertEqual(self.deny(src), frozenset())

    def test_sanitize_diff_skips_rewritten_keys_only_at_top(self):
        d = mu.sanitize_diff({"machine_id": "h", "x": {"machine_id": "h"}}, {"x": {}}, frozenset())
        self.assertEqual(d["keys"], ["x.machine_id"])

    def test_sanitize_diff_does_not_descend_into_mismatched_types(self):
        d = mu.sanitize_diff({"a": {"b": 1}}, {"a": "other"}, frozenset())
        self.assertEqual(d["keys"], [])
        d = mu.sanitize_diff({"a": ["x"]}, {"a": None}, frozenset())
        self.assertEqual(d, {"keys": [], "denied_keys": [], "values": [], "coverage": []})

    def test_sanitize_diff_inside_a_list_is_not_top(self):
        d = mu.sanitize_diff({"a": [{"machine_id": "h"}]}, {"a": [{}]}, frozenset())
        self.assertEqual(d["keys"], ["a[0].machine_id"])

    def test_sanitize_diff_lists_only_values_replaced_by_the_sanitizer(self):
        s = mu.SANITIZED
        d = mu.sanitize_diff({"same": s, "changed": "a"}, {"same": s, "changed": "b"}, frozenset())
        self.assertEqual(d["values"], [], "同じ値・置き換えでない違いは数えない")


class PluginVersionTest(unittest.TestCase):
    def test_only_string_versions_are_returned(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "plugin.json"
            for doc, want in (({"version": "1.2.3"}, "1.2.3"), ({"version": 1}, None), ({}, None)):
                with self.subTest(doc=doc):
                    f.write_text(json.dumps(doc), encoding="utf-8")
                    self.assertEqual(mu.plugin_version(str(f)), want)


class FormatTest(unittest.TestCase):
    def test_fmt(self):
        self.assertEqual([mu.fmt(None), mu.fmt(2.0), mu.fmt(2.5), mu.fmt(3)], ["-", "2", "2.5", "3"])

    def test_short(self):
        self.assertEqual((mu.short("0123456789abcdef"), mu.short(None)), ("0123456", "未取得"))


def base_res(scope=None, commits=None, comparison=None, baseline=None, runs=None) -> dict:
    """render_text に渡す最小の結果（既定はどの値も「無い」側）."""
    sc = {"store": None, "store_files": [], "local_logs": [], "n": 0, "dedup_dropped": 0, "dedup_conflicts": 0,
          "main_commit": None, "main_ref": None, "plugin_version": None, "previous": None}
    sc.update(scope or {})
    cm = {"reason": None, "commits": [], "total": 0}
    cm.update(commits or {})
    cp = {"generation": None, "rereview_excluded": 0, "split_version": None, "rows": []}
    cp.update(comparison or {})
    return {"scope": sc, "since_previous": {"first_run": True, "n": 0}, "commits": cm, "comparison": cp,
            "baseline": baseline or {"marker": {"status": "no-marker"}, "due": None},
            "vocab_drops": {"local_only": True, "runs": runs or []}}


def drop_run(i=0, version="2.0.0", raw_found=True) -> dict:
    return {"ts": "2026-11-%02dT00:00:00Z" % (i % 28 + 1), "plugin": SELF, "version": version,
            "counts": {"keys": 1, "coverage": 0, "values": 0}, "raw_found": raw_found, "diff": None}


class RenderTextTest(unittest.TestCase):
    def lines(self, **kw):
        return mu.render_text(base_res(**kw)).split("\n")

    def line(self, prefix, **kw):
        found = [l for l in self.lines(**kw) if l.startswith(prefix)]
        self.assertEqual(len(found), 1, (prefix, found))
        return found[0]

    def test_scope_defaults(self):
        self.assertEqual(self.line("- ストア:"), "- ストア: なし（手元のログだけで集計）")
        self.assertEqual(self.line("- ストア:", scope={"store": "~/s"}), "- ストア: ~/s（events なし）")
        self.assertEqual(self.line("- ストア:", scope={"store": "~/s", "store_files": [{"path": "p", "rows": 3}]}),
                         "- ストア: ~/s（p 3 行）")
        self.assertEqual(self.line("- 手元のログ:"), "- 手元のログ: なし")
        self.assertEqual(self.line("- 手元のログ:", scope={"local_logs": [{"path": "l", "rows": 2}]}),
                         "- 手元のログ: l 2 行")
        self.assertEqual(self.line("- main:"), "- main: 未取得（-）/ code-review 未取得")
        self.assertEqual(self.line("- main:", scope={"main_commit": "0123456789", "main_ref": "main",
                                                     "plugin_version": "2.1.0"}),
                         "- main: 0123456（main）/ code-review 2.1.0")

    def test_more_commits_line_only_when_some_are_hidden(self):
        lines = self.lines(commits={"total": 1, "commits": ["abc x"]})
        self.assertFalse([l for l in lines if "ほか" in l])
        self.assertIn("  - ほか 1 件", self.lines(commits={"total": 2, "commits": ["abc x"]}))

    def test_comparison_heading_and_version_column(self):
        self.assertEqual(self.line("### 比較表"), "### 比較表（再レビューを除く。除いた回 0 件）")
        self.assertEqual(self.line("### 比較表", comparison={"generation": "opus-5-5"}),
                         "### 比較表（世代 opus-5-5・再レビューを除く。除いた回 0 件）")
        self.assertNotIn("| 版 |", self.line("| 世代"))
        self.assertIn("| 範囲 | 版 | n |", self.line("| 世代", comparison={"split_version": "2.1.0"}))

    def test_baseline_lines(self):
        self.assertTrue(self.line("- 判定できない").startswith("- 判定できない（印: no-marker）"))
        bl = {"marker": {"status": "ok", "generation": "opus-5-5", "taken": "2026-10-25"}, "due": False,
              "xhigh_review_n": 0, "xhigh_need": 0, "window_generations": [], "generation_changed": False}
        self.assertEqual(self.line("- 印:", baseline=bl), "- 印: 世代 opus-5-5・取り直し 2026-10-25")
        self.assertEqual(self.line("- 判定:", baseline=bl),
                         "- 判定: まだ（直近 4 回の世代 -・xhigh の条件は消化済み（取り直し以降の xhigh 以上の review 0 件））")
        bl.update(due=True, xhigh_review_n=1, xhigh_need=2, window_generations=["a", "b"], generation_changed=True)
        self.assertEqual(self.line("- 判定:", baseline=bl),
                         "- 判定: 更新の時期（直近 4 回の世代 a → b（変わった）・取り直し以降の xhigh 以上の review 1/2 件）")

    def test_vocab_drop_lines(self):
        lines = self.lines(runs=[drop_run(0, version=None, raw_found=False), drop_run(1)])
        drops = [l for l in lines if l.startswith("- 2026-11-")]
        self.assertEqual(drops, [
            "- 2026-11-01T00:00:00Z %s（版 未記録）キー 1・観点 0・値 0 — 手元に生の行なし（publish したマシンで回す）" % SELF,
            "- 2026-11-02T00:00:00Z %s（版 2.0.0）キー 1・観点 0・値 0" % SELF,
        ])

    def test_more_drops_line_only_past_the_limit(self):
        n = mu.DROPS_LIMIT
        self.assertFalse([l for l in self.lines(runs=[drop_run(i) for i in range(n)]) if "ほか" in l])
        self.assertIn("- ほか 1 件（古い順に省略）", self.lines(runs=[drop_run(i) for i in range(n + 1)]))


class MainOutputTest(Env):
    def test_json_output_keeps_non_ascii(self):
        store = self.store({"m1": [ev("2026-11-01T00:00:00Z", payload(plugin_version="2.150.0"))]})
        r = self.run_cli("--store", str(store), "--split-version", "2.158.0", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("2.158.0 より前", r.stdout)

    def test_record_line_without_plugin_version(self):
        pj = self.tmp / "plugin.json"
        pj.write_text("{}", encoding="utf-8")
        r = self.run_cli("--no-store", "--plugin-json", str(pj), "--record")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("版 未取得", r.stderr)

    def test_unexpected_error_names_the_file_and_line(self):
        # side_effect に例外を渡すと mock.py の中で投げられる。ここで投げて、最後のフレーム（tb[-1]）を出すことまで見る
        def boom(*_args, **_kwargs):
            raise RuntimeError("boom")

        err = io.StringIO()
        with unittest.mock.patch.dict(os.environ, self.env, clear=True), \
                unittest.mock.patch.object(mu, "build", boom), \
                contextlib.redirect_stderr(err):
            rc = mu.main(["--no-store", "--state", str(self.state)])
        self.assertEqual(rc, 2)
        self.assertRegex(err.getvalue(), r"RuntimeError at %s:\d+）" % re.escape(Path(__file__).name))


if __name__ == "__main__":
    unittest.main()
