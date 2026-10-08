"""mutation-nightly-state.py resolve-base — nightly の比較起点（GitHub issue #288）.

24h 窓の起点は、前の晩の head と 24h の境界の間に落ちたコミットを取りこぼす（10-07 は PR #281 の
マージ分 35 ファイル）。起点は「集計を残した最新の schedule run の headSha」にする。
gh は stub（fixture の JSON を返し、呼ばれた引数を記録する。`--json` は要求されたフィールドだけ返す
ので、フィールド名の綴りを誤ると候補が消えて落ちる）、git は使い捨てリポジトリで本物を使う。
"""

from __future__ import annotations

import importlib.util
import json
import os
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
elif args[0] == "api":
    run_id = args[1].split("/runs/")[1].split("/")[0]
    names = fx.get("artifacts", {}).get(run_id, [])
    print(json.dumps({"total_count": len(names), "artifacts": [{"name": n} for n in names]}))
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
             "--env-file", str(env_file), *extra],
            cwd=self.repo, capture_output=True, text=True, timeout=60, env=self.env())
        return res, env_file.read_text(encoding="utf-8")

    def gh_calls(self) -> list[list[str]]:
        log = self.d / "gh.log"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

    def assert_base(self, env: str, short: str) -> None:
        lines = env.splitlines()
        self.assertEqual(len(lines), 1, env)
        self.assertTrue(lines[0].startswith("MUT_BASE=" + short), env)

    # --- 集計を残した直近の nightly の head を起点にする（#288 の本題）---
    def test_the_previous_runs_head_closes_the_window_gap(self):
        """24h 窓なら起点は gap（gap の変更が範囲から落ちる）。前回の head なら gap が範囲に入る."""
        h = self.history()
        res, env = self.resolve({"runs": [run_entry(41, h["prev"], "2026-10-06T22:17:33Z")],
                                 "artifacts": {"41": ART}})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assert_base(env, h["prev"])
        self.assertNotIn("::warning::", res.stdout)
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
        self.assertNotIn("::warning::", res.stdout)

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
        self.assertEqual(env, "SKIP=1\n")

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

    # --- 引数 ---
    def test_each_required_argument_is_enforced(self):
        """欠けたまま走ると、自分を候補から外せない・別のリポジトリを引く・起点をどこにも書かない."""
        self.history()
        (self.d / "fx.json").write_text(json.dumps({"runs": []}), encoding="utf-8")
        full = ["--run-id", "999", "--repo", "o/r", "--env-file", str(self.d / "e")]
        for flag in ("--run-id", "--repo", "--env-file"):
            i = full.index(flag)
            args = full[:i] + full[i + 2:]
            res = subprocess.run([sys.executable, str(SCRIPT), "resolve-base", *args], cwd=self.repo,
                                 capture_output=True, text=True, timeout=60, env=self.env())
            self.assertEqual(res.returncode, 2, flag)
            self.assertIn(flag, res.stderr)
        res = subprocess.run([sys.executable, str(SCRIPT)], cwd=self.repo, capture_output=True, text=True,
                             timeout=60, env=self.env())
        self.assertEqual(res.returncode, 2, "サブコマンドが無い")


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

    def test_resolve_base_is_wired_with_this_runs_id_and_repo(self):
        step = self.yml.split("- name: resolve-base", 1)[1].split("- name:", 1)[0]
        for needle in ("mutation-nightly-state.py resolve-base", '--run-id "$GITHUB_RUN_ID"',
                       '--repo "$GITHUB_REPOSITORY"', '--env-file "$GITHUB_ENV"',
                       "GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}"):
            self.assertIn(needle, step)


if __name__ == "__main__":
    unittest.main()
