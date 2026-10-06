#!/usr/bin/env python3
"""issue-workflow 同梱 `scripts/branch-setup.sh` の CLI 境界テスト（GitHub issue #280）.

start / issue-create がブランチを worktree に分けるときの決定的な部分を見る。
厚く見るのは「写してはいけないもの」の側（追跡済みの .env*・深すぎる階層・node_modules /
.claude 配下・既にあるファイル）と、「今いるブランチから切らない」こと — どちらも壊れても
worktree はできるので、出力を眺めただけでは気づけない。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from git_env import scrub

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "issue-workflow" / "scripts" / "branch-setup.sh"
ENV = scrub()


def git(cwd: Path, *args: str) -> str:
    res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=ENV)
    if res.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {res.stderr}")
    return res.stdout.strip()


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(SCRIPT), *args], cwd=cwd, capture_output=True,
                          text=True, env=ENV, timeout=60)


def parse(stdout: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in stdout.splitlines():
        k, _, v = line.partition("=")
        out.setdefault(k, []).append(v)
    return out


class RepoTestCase(unittest.TestCase):
    """main に 1 コミットある使い捨てリポジトリ（author と署名はリポジトリ側で固定する）."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        for k, v in (("user.email", "t@example.com"), ("user.name", "t"),
                     ("commit.gpgsign", "false")):
            git(self.root, "config", k, v)
        self.commit("init", {"a.txt": "a"})
        self.main_sha = git(self.root, "rev-parse", "HEAD")

    def commit(self, message: str, files: dict[str, str]) -> None:
        for name, body in files.items():
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
            git(self.root, "add", "--", name)
        git(self.root, "commit", "-qm", message)

    def write(self, name: str, body: str = "x") -> Path:
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
        return p

    def worktree(self, branch: str = "feat/TEAM-1-x", name: str = "TEAM-1",
                 *extra: str) -> dict[str, list[str]]:
        res = run(self.root, "worktree", branch, "--name", name, *extra)
        self.assertEqual(res.returncode, 0, res.stderr)
        return parse(res.stdout)


class StatusTest(RepoTestCase):
    def test_clean_main_checkout(self):
        res = run(self.root, "status")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(parse(res.stdout), {
            "in_worktree": ["0"], "dirty": ["0"], "branch": ["main"],
            "main_root": [str(self.root)], "default_branch": ["main"],
        })

    def test_dirty_counts_modified_and_untracked(self):
        (self.root / "a.txt").write_text("changed")
        self.write("new.txt")
        self.assertEqual(parse(run(self.root, "status").stdout)["dirty"], ["2"])

    def test_inside_a_worktree_points_at_the_main_checkout(self):
        wt = Path(self.worktree()["worktree"][0])
        st = parse(run(wt, "status").stdout)
        self.assertEqual(st["in_worktree"], ["1"])
        self.assertEqual(st["main_root"], [str(self.root)])
        self.assertEqual(st["branch"], ["feat/TEAM-1-x"])

    def test_default_branch_follows_origin_head(self):
        git(self.root, "update-ref", "refs/remotes/origin/trunk", "HEAD")
        git(self.root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        self.assertEqual(parse(run(self.root, "status").stdout)["default_branch"], ["trunk"])

    def test_outside_git_is_an_argument_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(run(Path(d), "status").returncode, 2)

    def test_git_without_path_format_still_resolves_the_main_checkout(self):
        """`--path-format` は git 2.31 から。無い git では相対の common dir を cwd 基準で解決する."""
        real_git = shutil.which("git", path=ENV.get("PATH"))
        self.assertIsNotNone(real_git)
        bindir = self.root.parent / "bin"
        bindir.mkdir()
        stub = bindir / "git"
        stub.write_text('#!/bin/sh\ncase " $* " in *" --path-format="*) exit 129 ;; esac\n'
                        f'exec "{real_git}" "$@"\n')
        stub.chmod(0o755)
        wt = Path(self.worktree()["worktree"][0])
        env = {**ENV, "PATH": f"{bindir}{os.pathsep}{ENV.get('PATH', '')}"}
        for cwd in (self.root / "sub", wt):
            cwd.mkdir(exist_ok=True)
            with self.subTest(cwd=cwd):
                res = subprocess.run(["bash", str(SCRIPT), "status"], cwd=cwd, capture_output=True,
                                     text=True, env=env, timeout=60)
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertEqual(parse(res.stdout)["main_root"], [str(self.root)])


class WorktreeCreateTest(RepoTestCase):
    def test_branches_from_the_default_branch_not_from_the_current_one(self):
        git(self.root, "checkout", "-qb", "feat/OTHER-1")
        self.commit("other work", {"b.txt": "b"})
        out = self.worktree()
        wt = Path(out["worktree"][0])
        self.assertEqual(wt, self.root / ".claude" / "worktrees" / "TEAM-1")
        self.assertEqual(out["created"], ["1"])
        self.assertEqual(out["base"], ["main"])
        self.assertEqual(git(wt, "rev-parse", "HEAD"), self.main_sha)
        self.assertEqual(git(wt, "symbolic-ref", "--short", "HEAD"), "feat/TEAM-1-x")

    def test_prefers_origin_default_and_does_not_track_it(self):
        self.commit("local only", {"b.txt": "b"})
        git(self.root, "update-ref", "refs/remotes/origin/main", self.main_sha)
        out = self.worktree()
        wt = Path(out["worktree"][0])
        self.assertEqual(out["base"], ["origin/main"])
        self.assertEqual(git(wt, "rev-parse", "HEAD"), self.main_sha)
        upstream = subprocess.run(["git", "rev-parse", "--abbrev-ref", "@{u}"], cwd=wt,
                                  capture_output=True, text=True, env=ENV)
        self.assertNotEqual(upstream.returncode, 0, "新しいブランチが origin/main を追跡している")

    def test_explicit_base(self):
        git(self.root, "checkout", "-qb", "feat/OTHER-1")
        self.commit("other work", {"b.txt": "b"})
        other = git(self.root, "rev-parse", "HEAD")
        out = self.worktree("feat/TEAM-1-x", "TEAM-1", "--base", "feat/OTHER-1")
        self.assertEqual(out["base"], ["feat/OTHER-1"])
        self.assertEqual(git(Path(out["worktree"][0]), "rev-parse", "HEAD"), other)

    def test_existing_branch_is_checked_out_as_is(self):
        git(self.root, "branch", "feat/TEAM-1-x")
        out = self.worktree()
        self.assertEqual(out["base"], ["-"])
        self.assertEqual(git(Path(out["worktree"][0]), "symbolic-ref", "--short", "HEAD"),
                         "feat/TEAM-1-x")

    def test_rerun_reuses_the_worktree(self):
        first = self.worktree()
        second = self.worktree()
        self.assertEqual(second["worktree"], first["worktree"])
        self.assertEqual(second["created"], ["0"])

    def test_path_that_is_not_a_worktree_is_refused(self):
        self.write(".claude/worktrees/TEAM-1/keep.txt")
        res = run(self.root, "worktree", "feat/TEAM-1-x", "--name", "TEAM-1")
        self.assertEqual(res.returncode, 1)
        self.assertIn("worktree ではない", res.stderr)
        self.assertEqual(git(self.root, "branch", "--list", "feat/TEAM-1-x"), "")

    def test_branch_checked_out_elsewhere_is_a_failure(self):
        git(self.root, "checkout", "-qb", "feat/TEAM-1-x")
        res = run(self.root, "worktree", "feat/TEAM-1-x", "--name", "TEAM-1")
        self.assertEqual(res.returncode, 1)
        self.assertIn("git worktree add", res.stderr)

    def test_bad_names_are_argument_errors(self):
        for name in ("", ".", "..", "../x", "a/b", "a b"):
            with self.subTest(name=name):
                res = run(self.root, "worktree", "feat/TEAM-1-x", "--name", name)
                self.assertEqual(res.returncode, 2, res.stderr)
        self.assertFalse((self.root / ".claude").exists())

    def test_bad_branch_and_missing_args_are_argument_errors(self):
        for args in (("worktree", "bad..branch", "--name", "T"), ("worktree", "--name", "T"),
                     ("worktree", "b", "--name"), ("worktree", "a", "b", "--name", "T"), ()):
            with self.subTest(args=args):
                self.assertEqual(run(self.root, *args).returncode, 2)


class IgnoreTest(RepoTestCase):
    def test_worktrees_dir_is_excluded_locally_once(self):
        self.assertEqual(self.worktree()["excluded"], ["1"])
        self.assertEqual(git(self.root, "status", "--porcelain"), "")
        self.assertEqual(self.worktree("feat/TEAM-2-x", "TEAM-2")["excluded"], ["0"])
        exclude = (self.root / ".git" / "info" / "exclude").read_text()
        self.assertEqual(exclude.count(".claude/worktrees/"), 1)
        self.assertFalse((self.root / ".gitignore").exists(), ".gitignore を書き換えた")

    def test_already_ignored_by_gitignore_is_left_alone(self):
        self.commit("ignore", {".gitignore": ".claude/\n"})
        before = (self.root / ".git" / "info" / "exclude").read_text()
        self.assertEqual(self.worktree()["excluded"], ["0"])
        self.assertEqual((self.root / ".git" / "info" / "exclude").read_text(), before)


class EnvCopyTest(RepoTestCase):
    def test_copies_untracked_env_files_up_to_depth_three(self):
        self.write(".env.local", "SECRET=1")
        self.write("apps/web/.env", "W=1")
        self.write("a/b/c/.env", "deep")
        out = self.worktree()
        wt = Path(out["worktree"][0])
        self.assertEqual(sorted(out.get("env_copied", [])), [".env.local", "apps/web/.env"])
        self.assertEqual((wt / ".env.local").read_text(), "SECRET=1")
        self.assertFalse((wt / "a/b/c/.env").exists())

    def test_skips_tracked_files_even_when_missing_from_the_worktree(self):
        git(self.root, "checkout", "-qb", "feat/OTHER-1")
        self.commit("other env", {".env.shared": "OTHER"})
        out = self.worktree()
        self.assertNotIn(".env.shared", out.get("env_copied", []))
        self.assertFalse((Path(out["worktree"][0]) / ".env.shared").exists())

    def test_skips_node_modules_and_dot_claude(self):
        self.write("node_modules/pkg/.env")
        self.write(".claude/.env")
        self.assertEqual(self.worktree().get("env_copied", []), [])

    def test_does_not_overwrite_an_existing_file(self):
        self.write(".env.local", "v1")
        wt = Path(self.worktree()["worktree"][0])
        self.write(".env.local", "v2")
        self.assertEqual(self.worktree().get("env_copied", []), [])
        self.assertEqual((wt / ".env.local").read_text(), "v1")


class InstallDetectTest(RepoTestCase):
    def install(self, files: dict[str, str]) -> list[str]:
        self.commit("lock", files)
        return self.worktree().get("install", [])

    def test_no_lockfile_no_command(self):
        self.assertEqual(self.worktree().get("install", []), [])

    def test_pnpm(self):
        self.assertEqual(self.install({"pnpm-lock.yaml": ""}), ["pnpm install --frozen-lockfile"])

    def test_npm(self):
        self.assertEqual(self.install({"package-lock.json": "{}"}), ["npm ci"])

    def test_pnpm_wins_over_npm_and_other_ecosystems_are_added(self):
        self.assertEqual(
            self.install({"pnpm-lock.yaml": "", "package-lock.json": "{}", "uv.lock": ""}),
            ["pnpm install --frozen-lockfile", "uv sync --frozen"])

    def test_lockfile_only_on_the_current_branch_is_not_used(self):
        git(self.root, "checkout", "-qb", "feat/OTHER-1")
        self.commit("lock", {"package-lock.json": "{}"})
        self.assertEqual(self.worktree().get("install", []), [])


if __name__ == "__main__":
    unittest.main()
