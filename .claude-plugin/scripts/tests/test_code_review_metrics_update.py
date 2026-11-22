#!/usr/bin/env python3
"""計測の更新（`code-review/scripts/metrics-update.sh` / `lib/metrics_update.py`）のテスト. GitHub issue #480.

使い捨てのストア・手元のログ・状態ファイル・git リポジトリを立て、CLI 境界越しに叩く。判定の小関数は
純関数として見る。世代・再レビュー・delta の判定は `review-retro.sh` の本文から関数を切り出して突き合わせる
（retro のヒアドキュメントの中にあって import できないので、metrics_update.py は同じ式を複製している）。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import git_env  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "code-review" / "scripts"
WRAPPER = SCRIPTS / "metrics-update.sh"
RETRO = SCRIPTS / "review-retro.sh"
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


def retro_function(name: str) -> str:
    """`review-retro.sh` の本文から top-level の関数 1 つを切り出す（見つからなければ fail）."""
    text = RETRO.read_text(encoding="utf-8")
    m = re.search(r"^def %s\(.*?(?=^\S)" % re.escape(name), text, re.S | re.M)
    if not m:
        raise AssertionError("review-retro.sh に def %s が見つからない" % name)
    return m.group(0)


class RetroParityTest(unittest.TestCase):
    """世代・再レビュー・delta の判定が retro と一致する（metrics_update.py は同じ式を複製している）."""

    CASES = [
        {}, {"models": None}, {"models": {"main": ""}}, {"models": {"main": "claude-opus-5-5"}},
        {"models": {"main": "sonnet-5-5"}}, {"models": {"main": 3}},
        {"invocation": {"rereview": True}}, {"invocation": {"rereview": "true"}}, {"invocation": []},
        {"review_scope": {"mode": "delta"}}, {"review_scope": {"mode": "x"}}, {"review_scope": "delta"},
    ]

    def test_parity(self):
        ns: dict = {}
        for name in ("gen_of", "is_rereview", "scope_mode_of"):
            exec(retro_function(name), ns)
        for p in self.CASES:
            with self.subTest(p=p):
                self.assertEqual(ns["gen_of"](p), mu.gen_of(p))
                self.assertEqual(ns["is_rereview"](p), mu.is_rereview(p))
                self.assertEqual(ns["scope_mode_of"](p), mu.scope_mode_of(p))


if __name__ == "__main__":
    unittest.main()
