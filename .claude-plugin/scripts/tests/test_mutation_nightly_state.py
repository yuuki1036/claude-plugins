"""mutation-nightly-state.py — nightly の比較起点と持ち越しの状態（GitHub issue #288）.

24h 窓の起点は、前の晩の head と 24h の境界の間に落ちたコミットを取りこぼす（10-07 は PR #281 の
マージ分 35 ファイル）。予算で打ち切った変異は、起点を進めると二度と回らない。そこで「全件を回し切った
最後の head」と「実行済みの変異のキー」を状態として artifact で持ち越す。
gh は stub（fixture の JSON を返し、呼ばれた引数を記録する。`--json` は要求されたフィールドだけ返す
ので、フィールド名の綴りを誤ると候補が消えて落ちる）、git は使い捨てリポジトリで本物を使う。
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from git_env import scrub
from hook_harness import TempGitRepo

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / ".claude-plugin" / "scripts" / "mutation-nightly-state.py"
WORKFLOW_YML = REPO / ".github" / "workflows" / "mutation-nightly.yml"
OLD = "2020-01-01T00:00:00"
ART = ["mutation-summary"]

GH_STUB = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["GH_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps(args) + "\\n")
fx = json.load(open(os.environ["GH_FIXTURE"], encoding="utf-8"))
if fx.get("fail"):
    sys.stderr.write("HTTP 403: Resource not accessible by integration\\n")
    sys.exit(1)
if fx.get("garbage"):
    print("<html>")
    sys.exit(0)
if args[:2] == ["run", "list"]:
    fields = args[args.index("--json") + 1].split(",")
    print(json.dumps([{k: r[k] for k in fields if k in r} for r in fx["runs"]]))
elif args[:2] == ["run", "download"]:
    if fx.get("fail_download"):
        sys.stderr.write("HTTP 502: Bad Gateway\\n")
        sys.exit(1)
    run_id = args[2]
    state = fx.get("states", {}).get(run_id)
    if state is None:
        sys.stderr.write("no artifact matches any of the names\\n")
        sys.exit(1)
    d = args[args.index("-D") + 1]
    with open(os.path.join(d, "mutation-state.json"), "w", encoding="utf-8") as f:
        f.write(state if isinstance(state, str) else json.dumps(state))
elif args[0] == "api":
    run_id = args[1].split("/runs/")[1].split("/")[0]
    names = fx.get("artifacts", {}).get(run_id, [])
    old = fx.get("expired", {}).get(run_id, [])
    arts = [{"name": n, "expired": False} for n in names] + [{"name": n, "expired": True} for n in old]
    print(json.dumps({"total_count": len(arts), "artifacts": arts}))
else:
    sys.exit(2)
"""


def run_entry(run_id: int, head: str, created: str, status: str = "completed",
              conclusion: str = "success") -> dict:
    return {"databaseId": run_id, "headSha": head, "status": status, "conclusion": conclusion,
            "createdAt": created}


def load_script():
    spec = importlib.util.spec_from_file_location("mutation_nightly_state", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ResolveBaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self._repo = TempGitRepo()
        self.repo = self._repo.__enter__()
        self.addCleanup(self._repo.__exit__, None, None, None)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        (self.d / "bin").mkdir()
        stub = self.d / "bin" / "gh"
        stub.write_text(GH_STUB, encoding="utf-8")
        stub.chmod(0o755)

    def history(self) -> dict[str, str]:
        """10-07 の形: prev（前の晩の head）の後に、24h より古い committer date の gap が入っている."""
        return {"c1": self._repo.commit("c1", body="1", committed_at=OLD),
                "prev": self._repo.commit("prev", body="2", committed_at=OLD),
                "gap": self._repo.commit("gap", body="3", committed_at=OLD),
                "head": self._repo.commit("head", body="4")}

    def env(self) -> dict[str, str]:
        return scrub(PATH=str(self.d / "bin") + os.pathsep + os.environ["PATH"],
                     GH_FIXTURE=str(self.d / "fx.json"), GH_LOG=str(self.d / "gh.log"))

    def resolve(self, fixture: dict, *extra: str) -> tuple[subprocess.CompletedProcess[str], str]:
        (self.d / "fx.json").write_text(json.dumps(fixture), encoding="utf-8")
        env_file = self.d / "github_env"
        env_file.write_text("", encoding="utf-8")
        res = subprocess.run(
            [sys.executable, str(SCRIPT), "resolve-base", "--run-id", "999", "--repo", "o/r",
             "--state-dir", str(self.d / "tmp" / "state"), "--env-file", str(env_file), *extra],
            cwd=self.repo, capture_output=True, text=True, timeout=60, env=self.env())
        return res, env_file.read_text(encoding="utf-8")

    def gh_calls(self) -> list[list[str]]:
        log = self.d / "gh.log"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

    def assert_base(self, env: str, short: str) -> None:
        bases = [l for l in env.splitlines() if l.startswith(("MUT_BASE=", "SKIP="))]
        self.assertEqual(len(bases), 1, env)
        self.assertTrue(bases[0].startswith("MUT_BASE=" + short), env)

    @staticmethod
    def env_map(env: str) -> dict[str, str]:
        return dict(l.split("=", 1) for l in env.splitlines())

    # --- 集計を残した直近の nightly の head を起点にする（#288 の本題）---
    def test_the_previous_runs_head_closes_the_window_gap(self):
        """24h 窓なら起点は gap（gap の変更が範囲から落ちる）。前回の head なら gap が範囲に入る."""
        h = self.history()
        res, env = self.resolve({"runs": [run_entry(41, h["prev"], "2026-10-06T22:17:33Z")],
                                 "artifacts": {"41": ART}})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assert_base(env, h["prev"])
        self.assertNotIn("STATE_LOST", env, "状態がまだ無いだけ（入れた最初の晩）")
        # 同じリポジトリで 24h 窓に落ちた場合の起点は gap（対の鳴る側: 起点が違うことを確かめる）
        res2, env2 = self.resolve({"runs": []})
        self.assert_base(env2, h["gap"])

    def test_the_workflow_passes_an_empty_input_base_on_schedule(self):
        """schedule では `inputs.base` が空文字で渡る（ワークフローの書き方そのまま）."""
        h = self.history()
        res, env = self.resolve({"runs": [run_entry(41, h["prev"], "2026-10-06T22:17:33Z")],
                                 "artifacts": {"41": ART}}, "--input-base", "")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assert_base(env, h["prev"])

    def test_the_lookup_asks_for_this_repos_completed_schedule_runs(self):
        h = self.history()
        self.resolve({"runs": [run_entry(41, h["prev"], "2026-10-06T22:17:33Z")], "artifacts": {"41": ART}})
        calls = self.gh_calls()
        self.assertEqual(calls[0][:2], ["run", "list"])
        for flag, value in (("--repo", "o/r"), ("--workflow", "mutation-nightly.yml"),
                            ("--event", "schedule"), ("--status", "completed"), ("--limit", "30")):
            self.assertEqual(calls[0][calls[0].index(flag) + 1], value, flag)
        self.assertEqual(calls[1], ["api", "repos/o/r/actions/runs/41/artifacts?per_page=100"])

    def test_a_run_without_the_summary_is_carried_over(self):
        """変異前のテストが赤い晩（集計なし）の head は起点にしない — その範囲は翌晩に持ち越す."""
        h = self.history()
        res, env = self.resolve({"runs": [run_entry(42, h["gap"], "2026-10-07T22:39:25Z", conclusion="failure"),
                                          run_entry(41, h["prev"], "2026-10-06T22:17:33Z")],
                                 "artifacts": {"41": ART, "42": ["other-artifact"]}})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assert_base(env, h["prev"])
        self.assertNotIn("最新の run", res.stdout, "集計なしの run へ退避している")

    def test_the_newest_run_wins_regardless_of_the_listing_order(self):
        h = self.history()
        res, env = self.resolve({"runs": [run_entry(41, h["c1"], "2026-10-05T22:00:00Z"),
                                          run_entry(42, h["prev"], "2026-10-06T22:00:00Z")],
                                 "artifacts": {"41": ART, "42": ART}})
        self.assert_base(env, h["prev"])

    def test_this_run_and_unfinished_runs_are_not_candidates(self):
        """自分（実行中）を拾うと起点が HEAD になって毎晩 SKIP する."""
        h = self.history()
        res, env = self.resolve({"runs": [run_entry(999, h["head"], "2026-10-08T22:00:00Z"),
                                          run_entry(43, h["head"], "2026-10-08T21:00:00Z", "in_progress"),
                                          run_entry(41, h["prev"], "2026-10-06T22:17:33Z")],
                                 "artifacts": {"999": ART, "43": ART, "41": ART}})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assert_base(env, h["prev"])

    def test_no_change_since_the_previous_run_skips(self):
        h = self.history()
        res, env = self.resolve({"runs": [run_entry(41, h["head"], "2026-10-07T22:00:00Z")],
                                 "artifacts": {"41": ART}})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.env_map(env).get("SKIP"), "1")

    # --- HEAD の祖先でない head は飛ばして古い方へさかのぼる ---
    def test_a_head_that_is_not_an_ancestor_is_skipped_for_an_older_one(self):
        """古い run の re-run（新しい晩の head を持つ）や force push 前の head は起点にしない."""
        self._repo.commit("c1", body="1", committed_at=OLD)
        self._repo.branch("trunk")
        self._repo.branch("side")
        side = self._repo.commit("side", body="s", committed_at=OLD)
        self._repo.checkout("trunk")
        old = self._repo.commit("old", body="2", committed_at=OLD)
        self._repo.commit("head", body="3")
        res, env = self.resolve({"runs": [run_entry(42, side, "2026-10-07T22:00:00Z"),
                                          run_entry(41, old, "2026-10-06T22:00:00Z")],
                                 "artifacts": {"41": ART, "42": ART}})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assert_base(env, old)
        self.assertIn("祖先でないので飛ばす", res.stdout)

    def test_an_unknown_head_alone_falls_back_to_the_window(self):
        h = self.history()
        res, env = self.resolve({"runs": [run_entry(41, "f" * 40, "2026-10-06T22:00:00Z")],
                                 "artifacts": {"41": ART}})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assert_base(env, h["gap"])
        self.assertIn("::warning::", res.stdout)

    # --- 集計の artifact が無い（導入した最初の晩）---
    def test_without_any_summary_the_newest_run_that_ran_is_used_with_a_warning(self):
        """artifact を上げ始める前の晩でも、24h 窓に戻らずに前の晩の head を起点にする."""
        h = self.history()
        res, env = self.resolve({"runs": [run_entry(42, h["gap"], "2026-10-07T22:39:25Z", conclusion="cancelled"),
                                          run_entry(41, h["prev"], "2026-10-06T22:17:33Z", conclusion="failure")],
                                 "artifacts": {}})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assert_base(env, h["prev"])
        self.assertIn("::warning::", res.stdout)
        self.assertIn("run 41", res.stdout)

    def test_only_cancelled_runs_fall_back_to_the_window_with_a_warning(self):
        h = self.history()
        res, env = self.resolve({"runs": [run_entry(41, h["prev"], "2026-10-06T22:17:33Z", conclusion="cancelled")],
                                 "artifacts": {}})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assert_base(env, h["gap"])
        self.assertIn("::warning::", res.stdout)

    # --- API が使えない（24h 窓へ戻り、黙らずに warning）---
    def test_a_failing_gh_falls_back_to_the_window_with_a_warning(self):
        h = self.history()
        res, env = self.resolve({"fail": True})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assert_base(env, h["gap"])
        self.assertIn("::warning::", res.stdout)
        self.assertIn("403", res.stdout)

    def test_unparsable_gh_output_falls_back_to_the_window_with_a_warning(self):
        h = self.history()
        res, env = self.resolve({"garbage": True})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assert_base(env, h["gap"])
        self.assertIn("::warning::", res.stdout)

    def test_the_window_without_an_older_commit_skips(self):
        """24h 窓に戻った晩で、24h より古いコミットが無ければ比べる相手が無い."""
        self._repo.commit("only", body="1")
        res, env = self.resolve({"runs": []})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(env, "SKIP=1\n")

    # --- 手動起動の起点 ---
    def test_an_explicit_base_wins_without_asking_gh(self):
        h = self.history()
        res, env = self.resolve({"runs": []}, "--input-base", h["c1"])
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assert_base(env, h["c1"])
        self.assertEqual(self.gh_calls(), [])

    def test_an_unresolvable_explicit_base_fails_without_writing(self):
        self.history()
        res, env = self.resolve({"runs": []}, "--input-base", "no-such-ref")
        self.assertEqual(res.returncode, 1)
        self.assertIn("no-such-ref", res.stderr)
        self.assertEqual(env, "")

    # --- 持ち越しの状態（D）---
    def test_a_carried_state_wins_with_its_done_keys(self):
        """状態があれば、その base（全件を回し切った最後の head）から回し、済みの変異を飛ばす."""
        h = self.history()
        res, env = self.resolve({"runs": [run_entry(42, h["gap"], "2026-10-07T22:00:00Z"),
                                          run_entry(41, h["prev"], "2026-10-06T22:00:00Z")],
                                 "artifacts": {"42": ART + ["mutation-state"]},
                                 "states": {"42": {"schema": 1, "base": h["c1"], "done": ["aaaa", "bbbb"],
                                                   "since": "2026-10-05T00:00:00Z", "remaining": 3}}})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assert_base(env, h["c1"])
        e = self.env_map(env)
        self.assertEqual(Path(e["MUT_SKIP_KEYS"]).read_text(encoding="utf-8").split(), ["aaaa", "bbbb"])
        self.assertEqual(json.loads(Path(e["STATE_PREV"]).read_text(encoding="utf-8"))["base"][:7], h["c1"][:7])
        self.assertNotIn("STATE_LOST", e)
        self.assertNotIn("::warning::", res.stdout)
        dl = [c for c in self.gh_calls() if c[:2] == ["run", "download"]][0]
        self.assertEqual(dl[2:], ["42", "--repo", "o/r", "-n", "mutation-state", "-D", dl[-1]])

    def test_an_older_state_is_used_when_the_newest_run_has_none(self):
        """状態を上げられなかった晩（cancelled 等）の後は、その前の状態から再開する（安全側）."""
        h = self.history()
        res, env = self.resolve({"runs": [run_entry(42, h["gap"], "2026-10-07T22:00:00Z"),
                                          run_entry(41, h["prev"], "2026-10-06T22:00:00Z")],
                                 "artifacts": {"42": ART, "41": ART + ["mutation-state"]},
                                 "states": {"41": {"base": h["c1"], "done": []}}})
        self.assert_base(env, h["c1"])

    def test_a_broken_state_is_reported_as_lost(self):
        """壊れた状態から done を読むと未検証の変異を済み扱いにする。使わずに起票させる."""
        h = self.history()
        for broken in ("{", json.dumps({"base": h["c1"], "done": [1, 2]}), json.dumps({"done": []})):
            with self.subTest(broken=broken):
                res, env = self.resolve({"runs": [run_entry(41, h["prev"], "2026-10-06T22:00:00Z")],
                                         "artifacts": {"41": ART + ["mutation-state"]},
                                         "states": {"41": broken}})
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assert_base(env, h["prev"])
                e = self.env_map(env)
                self.assertEqual(e.get("STATE_LOST"), "1")
                self.assertNotIn("MUT_SKIP_KEYS", e)
                self.assertNotIn("STATE_HOLD", e, "壊れた状態は上書きしてよい（翌晩に読んでも同じく壊れている）")

    def test_a_state_whose_base_is_not_an_ancestor_is_reported_as_lost(self):
        """解決できるが HEAD の祖先でない base（force push の前の履歴）も、解決できない base も使わない."""
        self._repo.commit("c1", body="1", committed_at=OLD)
        self._repo.branch("trunk")
        self._repo.branch("side")
        side = self._repo.commit("side", body="s", committed_at=OLD)
        self._repo.checkout("trunk")
        prev = self._repo.commit("prev", body="2", committed_at=OLD)
        self._repo.commit("head", body="3")
        for base in (side, "f" * 40):
            with self.subTest(base=base):
                res, env = self.resolve({"runs": [run_entry(41, prev, "2026-10-06T22:00:00Z")],
                                         "artifacts": {"41": ART + ["mutation-state"]},
                                         "states": {"41": {"base": base, "done": []}}})
                self.assert_base(env, prev)
                self.assertEqual(self.env_map(env).get("STATE_LOST"), "1")

    def test_an_expired_state_is_lost_without_holding(self):
        """期限切れの状態を取りに行くと download が失敗し、API の失敗として毎晩 hold し続ける."""
        h = self.history()
        res, env = self.resolve({"runs": [run_entry(41, h["prev"], "2026-10-06T22:00:00Z")],
                                 "artifacts": {"41": ART}, "expired": {"41": ["mutation-state"]}})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assert_base(env, h["prev"])
        e = self.env_map(env)
        self.assertEqual(e.get("STATE_LOST"), "1")
        self.assertNotIn("STATE_HOLD", e)
        self.assertEqual([c for c in self.gh_calls() if c[:2] == ["run", "download"]], [])

    def test_an_expired_summary_still_marks_the_range_as_run(self):
        h = self.history()
        res, env = self.resolve({"runs": [run_entry(41, h["prev"], "2026-10-06T22:00:00Z")],
                                 "artifacts": {}, "expired": {"41": ART}})
        self.assert_base(env, h["prev"])
        self.assertNotIn("最新の run", res.stdout)

    def test_a_failed_download_holds_the_previous_state(self):
        """一覧は取れたが download だけ失敗した晩も、前の状態を上書きしない."""
        h = self.history()
        res, env = self.resolve({"runs": [run_entry(41, h["prev"], "2026-10-06T22:00:00Z")],
                                 "artifacts": {"41": ["mutation-state"]}, "fail_download": True,
                                 "states": {"41": {"base": h["c1"], "done": []}}})
        e = self.env_map(env)
        self.assertEqual((e.get("STATE_HOLD"), e.get("STATE_LOST")), ("1", "1"))
        self.assertIn("502", res.stdout)

    def test_a_lost_state_without_any_base_is_held_too(self):
        """代わりの起点も見つからない（集計なし・24h より古いコミットなし）skip の晩も、前の状態を残す."""
        self._repo.commit("only", body="1")
        head = self._repo.commit("head", body="2")
        res, env = self.resolve({"runs": [run_entry(41, head, "2026-10-06T22:00:00Z", conclusion="cancelled")],
                                 "artifacts": {"41": ["mutation-state"]}, "states": {"41": "{"}})
        e = self.env_map(env)
        self.assertEqual((e.get("SKIP"), e.get("STATE_LOST"), e.get("STATE_HOLD")), ("1", "1", "1"))

    def test_a_lost_state_on_a_skip_night_is_held_until_report_can_run(self):
        """skip の晩は report が走らない。新しい状態で上書きすると、失ったことを誰も知らないまま消える."""
        h = self.history()
        res, env = self.resolve({"runs": [run_entry(41, h["head"], "2026-10-06T22:00:00Z")],
                                 "artifacts": {"41": ART + ["mutation-state"]},
                                 "states": {"41": "{"}})
        e = self.env_map(env)
        self.assertEqual((e.get("SKIP"), e.get("STATE_LOST"), e.get("STATE_HOLD")), ("1", "1", "1"))

    def test_no_state_yet_is_not_reported_as_lost(self):
        """入れた最初の晩は状態が無くて当然（warning だけ）."""
        h = self.history()
        res, env = self.resolve({"runs": [run_entry(41, h["prev"], "2026-10-06T22:00:00Z")],
                                 "artifacts": {"41": ART}})
        self.assert_base(env, h["prev"])
        self.assertNotIn("STATE_LOST", self.env_map(env))
        self.assertIn("::warning::", res.stdout)

    def test_an_api_failure_keeps_the_previous_state_for_the_next_night(self):
        """状態を読めなかった晩に新しい状態を上げると、持ち越していた範囲を上書きして失う."""
        h = self.history()
        res, env = self.resolve({"fail": True})
        e = self.env_map(env)
        self.assertEqual((e.get("STATE_HOLD"), e.get("STATE_LOST")), ("1", "1"))
        self.assert_base(env, h["gap"])

    def test_a_carried_state_at_head_skips(self):
        h = self.history()
        res, env = self.resolve({"runs": [run_entry(41, h["head"], "2026-10-06T22:00:00Z")],
                                 "artifacts": {"41": ["mutation-state"]},
                                 "states": {"41": {"base": h["head"], "done": []}}})
        e = self.env_map(env)
        self.assertEqual(e.get("SKIP"), "1")
        self.assertIn("STATE_PREV", e, "skip の晩も前の状態を引き継がせる")

    # --- 引数 ---
    def test_each_required_argument_is_enforced(self):
        """欠けたまま走ると、自分を候補から外せない・別のリポジトリを引く・起点をどこにも書かない."""
        self.history()
        (self.d / "fx.json").write_text(json.dumps({"runs": []}), encoding="utf-8")
        full = ["--run-id", "999", "--repo", "o/r", "--state-dir", str(self.d / "st"), "--env-file", str(self.d / "e")]
        for flag in ("--run-id", "--repo", "--state-dir", "--env-file"):
            i = full.index(flag)
            args = full[:i] + full[i + 2:]
            res = subprocess.run([sys.executable, str(SCRIPT), "resolve-base", *args], cwd=self.repo,
                                 capture_output=True, text=True, timeout=60, env=self.env())
            self.assertEqual(res.returncode, 2, flag)
            self.assertIn(flag, res.stderr)
        res = subprocess.run([sys.executable, str(SCRIPT)], cwd=self.repo, capture_output=True, text=True,
                             timeout=60, env=self.env())
        self.assertEqual(res.returncode, 2, "サブコマンドが無い")


class AdvanceTest(unittest.TestCase):
    """advance — この晩の集計で状態を進める（純関数 + CLI）."""

    NOW = "2026-10-09T00:00:00Z"

    def setUp(self) -> None:
        self.mod = load_script()

    def state(self, base="B", done=(), since="2026-10-01T00:00:00Z", remaining=1) -> dict:
        return {"schema": 1, "base": base, "done": list(done), "since": since, "remaining": remaining}

    @staticmethod
    def summary(keys_all, executed, aborted=False) -> dict:
        return {"schema": 2, "keys_all": list(keys_all), "keys_executed": list(executed), "aborted": aborted}

    def test_a_fully_run_range_moves_the_base_to_head(self):
        st = self.mod.advance(self.state(done=["a"]), self.summary(["a", "b"], ["b"]), "B", "H", self.NOW)
        self.assertEqual(st, {"schema": 1, "base": "H", "done": [], "since": self.NOW, "remaining": 0})

    def test_a_cut_range_keeps_the_base_and_carries_the_done_keys(self):
        st = self.mod.advance(self.state(done=["a"]), self.summary(["a", "b", "c"], ["b"]), "B", "H", self.NOW)
        self.assertEqual((st["base"], st["done"], st["remaining"], st["since"]),
                         ("B", ["a", "b"], 1, "2026-10-01T00:00:00Z"))

    def test_done_keys_outside_the_range_are_dropped(self):
        """行が書き換わって範囲から消えた変異は済み集合から刈る（状態が際限なく太らない）."""
        st = self.mod.advance(self.state(done=["gone", "a"]), self.summary(["a", "b", "c"], ["b"]),
                              "B", "H", self.NOW)
        self.assertEqual(st["done"], ["a", "b"])

    def test_a_new_carry_over_starts_its_own_clock(self):
        """回し切った後の状態（skip の晩に上げ直したもの）の since を引き継ぐと、持ち越しが始まった最初の晩に
        「何日も解消しない」と起票する."""
        done_state = self.state(done=[], since="2026-09-01T00:00:00Z", remaining=0)
        st = self.mod.advance(done_state, self.summary(["a", "b"], ["a"]), "B", "H", self.NOW)
        self.assertEqual(st["since"], self.NOW)
        unknown = self.state(done=[], since="2026-09-01T00:00:00Z", remaining=None)
        self.assertEqual(self.mod.advance(unknown, self.summary(["a", "b"], ["a"]), "B", "H", self.NOW)["since"],
                         self.NOW)

    def test_an_aborted_night_does_not_move_the_base(self):
        st = self.mod.advance(self.state(), self.summary(["a"], ["a"], aborted=True), "B", "H", self.NOW)
        self.assertEqual((st["base"], st["done"]), ("B", ["a"]))

    def test_a_night_without_a_summary_keeps_the_state(self):
        """変異前のテストが赤い晩・skip の晩は何も回していない（範囲は翌晩に繰り越す）."""
        prev = self.state(done=["a"], remaining=7)   # 進めた結果（remaining 1）と区別できる値
        for summary in (None, {"schema": 1, "generated": 3}, self.summary(["a"], ["a"]) | {"keys_all": "x"},
                        self.summary(["a", 1], ["a"]), self.summary(["a"], [1])):
            with self.subTest(summary=summary):
                self.assertEqual(self.mod.advance(prev, summary, "B", "H", self.NOW), prev)

    def test_a_state_for_another_base_is_not_carried(self):
        """起点が状態の base と違う晩（状態を使えなかった晩）は、その done を持ち込まない."""
        st = self.mod.advance(self.state(base="OLD", done=["a"]), self.summary(["a", "b"], ["b"]),
                              "B", "H", self.NOW)
        self.assertEqual((st["base"], st["done"], st["since"]), ("B", ["b"], self.NOW))
        st = self.mod.advance(self.state(base="OLD"), None, "B", "H", self.NOW)
        self.assertEqual((st["base"], st["done"], st["remaining"]), ("B", [], None))

    def test_the_first_night_starts_a_state(self):
        st = self.mod.advance(None, self.summary(["a", "b"], ["a"]), "B", "H", self.NOW)
        self.assertEqual((st["base"], st["done"], st["remaining"], st["since"]), ("B", ["a"], 1, self.NOW))

    def run_cli(self, d: Path, prev: str, *extra: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        res = subprocess.run([sys.executable, str(SCRIPT), "advance", "--prev", prev, "--summary",
                              str(d / "s.json"), "--base", "B", "--head", "H", "--out", str(d / "out.json"),
                              *extra], capture_output=True, text=True, timeout=30)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res, json.loads((d / "out.json").read_text(encoding="utf-8"))

    def test_the_cli_reports_whether_the_range_was_finished(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "prev.json").write_text(json.dumps(self.state(base="B", done=["b"])), encoding="utf-8")
            (d / "s.json").write_text(json.dumps(self.summary(["a", "b"], ["a"])), encoding="utf-8")
            res, st = self.run_cli(d, str(d / "prev.json"), "--now", self.NOW)
            self.assertIn("範囲を回し切った。起点を H に進める", res.stdout)
            res, st = self.run_cli(d, "", "--now", self.NOW)
            self.assertIn("持ち越し: 残り 1 個・済み 1 個（起点 B・%s から）" % self.NOW, res.stdout)
            (d / "s.json").write_text("{", encoding="utf-8")
            res, st = self.run_cli(d, "", "--now", self.NOW)
            self.assertIn("持ち越し: 残り ? 個・済み 0 個", res.stdout)
            # 全部回したが中断した晩: 残り 0 でも起点は進めない（「回し切った」と言わない）
            (d / "s.json").write_text(json.dumps(self.summary(["a"], ["a"], aborted=True)), encoding="utf-8")
            res, st = self.run_cli(d, "", "--now", self.NOW)
            self.assertEqual((st["base"], st["remaining"]), ("B", 0))
            self.assertNotIn("回し切った", res.stdout)

    def test_the_cli_stamps_the_current_time_without_now(self):
        import datetime as dt
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "s.json").write_text(json.dumps(self.summary(["a"], [])), encoding="utf-8")
            _, st = self.run_cli(d, "")
            since = dt.datetime.fromisoformat(st["since"].replace("Z", "+00:00"))
            self.assertLess(abs((dt.datetime.now(dt.timezone.utc) - since).total_seconds()), 120)

    def test_each_required_advance_argument_is_enforced(self):
        full = {"--prev": "", "--summary": "s", "--base": "B", "--head": "H", "--out": "o"}
        with tempfile.TemporaryDirectory() as d:     # 必須を外した変異体が --out をカレントに書く
            for drop in full:
                argv = [x for k, v in full.items() if k != drop for x in (k, v)]
                res = subprocess.run([sys.executable, str(SCRIPT), "advance", *argv], capture_output=True,
                                     text=True, timeout=30, cwd=d)
                self.assertEqual(res.returncode, 2, drop)
                self.assertIn(drop, res.stderr)

    def test_the_cli_writes_the_state_and_reads_an_empty_prev(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "s.json").write_text(json.dumps(self.summary(["a", "b"], ["a"])), encoding="utf-8")
            (d / "prev.json").write_text(json.dumps(self.state(base="B", done=["b"])), encoding="utf-8")
            for prev, want_base in (("", "B"), (str(d / "prev.json"), "H")):
                res = subprocess.run([sys.executable, str(SCRIPT), "advance", "--prev", prev, "--summary",
                                      str(d / "s.json"), "--base", "B", "--head", "H", "--out",
                                      str(d / "out.json"), "--now", self.NOW],
                                     capture_output=True, text=True, timeout=30)
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertEqual(json.loads((d / "out.json").read_text(encoding="utf-8"))["base"], want_base)


class WorkflowWiringTest(unittest.TestCase):
    """スクリプトの定数とワークフローの配線が食い違うと、毎晩黙って 24h 窓へ戻る."""

    def setUp(self) -> None:
        self.mod = load_script()
        self.yml = WORKFLOW_YML.read_text(encoding="utf-8")

    def test_the_workflow_file_is_the_one_the_script_lists(self):
        self.assertEqual(WORKFLOW_YML.name, self.mod.WORKFLOW)

    def test_the_uploaded_artifact_is_the_one_the_script_looks_for(self):
        step = self.yml.split("- name: upload-summary", 1)[1].split("- name:", 1)[0]
        self.assertIn("uses: actions/upload-artifact@", step)
        self.assertIn("name: %s\n" % self.mod.ARTIFACT, step)
        self.assertIn("path: mutation-summary.json\n", step)
        self.assertIn("--summary-json mutation-summary.json", self.yml)

    def test_the_token_can_read_runs_and_artifacts(self):
        perms = self.yml.split("\npermissions:\n", 1)[1].split("\n\n", 1)[0]
        self.assertRegex(perms, r"(?m)^  actions: read\b")

    def test_the_budget_ends_before_the_job_timeout(self):
        """予算が job の timeout に食い込むと cancelled になり、結果もログも report も残らない.

        余裕（600 秒）は準備（checkout・依存・起点の解決）と、予算で切った後の後始末・artifact・起票の分.
        """
        minutes = int(re.search(r"(?m)^    timeout-minutes: (\d+)$", self.yml).group(1))
        # **step の中から読む**（直前のコメントにも `--budget-sec 19000` と書いてあり、yml 全体の最初の一致は
        # コメントの数字になる。引数だけ変えてコメントを直し忘れても通ってしまう）
        step = self.yml.split("- name: mutation-test", 1)[1].split("- name:", 1)[0]
        budget = float(re.search(r"--budget-sec (\d+)", step).group(1))
        self.assertLessEqual(budget, minutes * 60 - 600)

    def step(self, name: str) -> str:
        return self.yml.split("- name: %s\n" % name, 1)[1].split("- name:", 1)[0]

    def test_the_state_is_carried_through_every_step(self):
        """状態の受け渡し（取得 → 済みを飛ばす → 進める → 上げる → 起票の判定）が 1 か所でも切れると、
        打ち切った変異が黙って消える #288 の元の形に戻る."""
        self.assertIn("id: base", self.step("resolve-base"))
        self.assertIn('--state-dir "$RUNNER_TEMP/mutation-state"', self.step("resolve-base"))
        self.assertIn('${MUT_SKIP_KEYS:+--skip-keys "$MUT_SKIP_KEYS"}', self.step("mutation-test"))
        adv = self.step("advance-state")
        for needle in ("id: state", "steps.base.outcome == 'success'", "env.STATE_HOLD != '1'",
                       "github.event_name == 'schedule'",
                       "mutation-nightly-state.py advance", '--prev "${STATE_PREV:-}"',
                       "--summary mutation-summary.json", "--out %s" % self.mod.STATE_FILE):
            self.assertIn(needle, adv)
        up = self.step("upload-state")
        for needle in ("steps.state.outcome == 'success'", "name: %s\n" % self.mod.STATE_ARTIFACT,
                       "path: %s\n" % self.mod.STATE_FILE, "if-no-files-found: error"):
            self.assertIn(needle, up)
        rep = self.step("report")
        self.assertIn("id: upstate", up)
        self.assertIn("STATE_UP: ${{ steps.upstate.outcome }}", rep)
        self.assertIn('if [ "$STATE_UP" = success ]; then state_args=(--state %s); fi' % self.mod.STATE_FILE, rep)
        self.assertIn('"${state_args[@]}"', rep)
        self.assertIn("${STATE_LOST:+--state-lost}", rep)
        self.assertIn("${STATE_HOLD:+--state-held}", rep)

    def test_no_env_sentinel_is_compared_with_zero(self):
        """`if:` は型が違えば数値に寄せ、未設定の env（null）は 0 になる。`env.X != '0'` は未設定の晩に偽で、
        step が毎晩飛ぶ（実例: advance-state が一度も走らない配線をレビューで見つけた）."""
        self.assertNotRegex(self.yml, r"env\.\w+\s*[!=]=\s*'0'")
        self.assertNotRegex(self.yml, r"env\.\w+\s*[!=]=\s*0\b")

    def test_resolve_base_is_wired_with_this_runs_id_and_repo(self):
        step = self.yml.split("- name: resolve-base", 1)[1].split("- name:", 1)[0]
        for needle in ("mutation-nightly-state.py resolve-base", '--run-id "$GITHUB_RUN_ID"',
                       '--repo "$GITHUB_REPOSITORY"', '--env-file "$GITHUB_ENV"',
                       "GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}"):
            self.assertIn(needle, step)


if __name__ == "__main__":
    unittest.main()
