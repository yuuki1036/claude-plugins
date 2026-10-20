#!/usr/bin/env python3
"""issue-workflow 同梱 `scripts/branch-setup.sh` の CLI 境界テスト（GitHub issue #280 / #305）.

start / issue-create がブランチを worktree に分けるときの決定的な部分を見る。
厚く見るのは「写してはいけないもの」の側（追跡済みの .env*・深すぎる階層・node_modules /
.claude 配下・既にあるファイル）と、「今いるブランチから切らない」こと — どちらも壊れても
worktree はできるので、出力を眺めただけでは気づけない。

existing（既存の作業の検知）で厚く見るのは、別の作業を Issue の作業と取り違えない側（似た ID・
main の session-context・ブランチを持つ worktree の session-context・.claude/ の未追跡・自分で写した
.env*）と、該当なしで found=0 だけを出す側。どれも壊れても候補が 1 件増えるだけで、出力を眺めても
気づけない。逆向きに、数えられなかった値（git の失敗）を 0 と書く側も作業なしに化けて気づけない。
黙る側のテストには、同じ入力で鳴る側の対を置く（docs/testing-pitfalls.md の 6）。

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
START = REPO / "issue-workflow" / "skills" / "start" / "SKILL.md"
EXISTING_DOC = REPO / "issue-workflow" / "skills" / "start" / "references" / "existing-work.md"
ENV = scrub()
#: existing が候補ごとに出すキー（この順で 1 件 9 行）
KEYS = ("worktree", "branch", "ahead", "dirty", "matched", "current", "prunable", "locked", "head")


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

    def commit(self, message: str, files: dict[str, str], cwd: Path | None = None) -> None:
        cwd = cwd or self.root
        for name, body in files.items():
            p = cwd / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
            git(cwd, "add", "--", name)
        git(cwd, "commit", "-qm", message)

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

    def existing(self, issue: str = "TEAM-1", cwd: Path | None = None) -> dict[str, list[str]]:
        res = run(cwd or self.root, "existing", issue)
        self.assertEqual(res.returncode, 0, res.stderr)
        return parse(res.stdout)

    def records(self, out: dict[str, list[str]]) -> list[dict[str, str]]:
        """同じキーの n 番目どうしを 1 件にまとめる（found と各キーの数が揃うことも見る）."""
        n = int(out["found"][0])
        self.assertEqual(set(out), ({"found", *KEYS} if n else {"found"}), out)
        for k in KEYS:
            self.assertEqual(len(out.get(k, [])), n, (k, out))
        return [{k: out[k][i] for k in KEYS} for i in range(n)]

    def add_worktree(self, *args: str) -> None:
        git(self.root, "worktree", "add", "-q", *args)

    def branch_with_commit(self, branch: str, cwd: Path | None = None) -> str:
        """<branch> を今の HEAD から切って 1 コミット積み、元のブランチへ戻る."""
        cwd = cwd or self.root
        back = git(cwd, "symbolic-ref", "--short", "HEAD")
        git(cwd, "checkout", "-qb", branch)
        self.commit(f"work on {branch}", {f"{branch.replace('/', '_')}.txt": branch}, cwd)
        sha = git(cwd, "rev-parse", "HEAD")
        git(cwd, "checkout", "-q", back)
        return sha

    def write_sc(self, root: Path, issue: str) -> None:
        """start の Phase CTX が書く形の session-context.md を置く."""
        p = root / ".claude" / "session-context.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"---\nshared_state_type: session\nissue_id: {issue}\n---\n")

    def vanished_worktree(self, branch: str = "feat/TEAM-1-x",
                          path: Path | None = None, *, locked: bool = False) -> Path:
        """<branch> の worktree を作ってディレクトリだけ消す（git に登録が残り、porcelain が prunable を付ける）.

        locked にすると porcelain は prunable を付けず、`git worktree prune` も登録を消さない。
        """
        path = path or self.root.parent / "sibling"
        self.add_worktree("-b", branch, str(path))
        if locked:
            git(self.root, "worktree", "lock", "--reason", "usb", str(path))
        shutil.rmtree(path)
        return path


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

    def test_branch_checked_out_at_another_path_is_reused(self):
        """Claude アプリの worktree や `../<name>` で checkout 済みなら、作らずにそこを返す（#305）."""
        self.commit("lock", {"package-lock.json": "{}"})
        self.write(".env.local", "SECRET=1")
        sibling = self.root.parent / "sibling"
        self.add_worktree("-b", "feat/TEAM-1-x", str(sibling))
        out = self.worktree()
        self.assertEqual(out["worktree"], [str(sibling)])
        self.assertEqual(out["created"], ["0"])
        self.assertEqual(out["base"], ["-"])
        self.assertEqual(out["excluded"], ["0"])
        # 既存のチェックアウトなので .env* を写さず、依存のインストールも出さない
        self.assertNotIn("env_copied", out)
        self.assertNotIn("install", out)
        self.assertFalse((sibling / ".env.local").exists())
        self.assertFalse((self.root / ".claude" / "worktrees" / "TEAM-1").exists())
        listed = git(self.root, "worktree", "list", "--porcelain").splitlines()
        self.assertEqual(sum(1 for line in listed if line.startswith("worktree ")), 2)
        self.assertNotIn(".claude/worktrees/", (self.root / ".git" / "info" / "exclude").read_text())

    def test_branch_checked_out_in_the_main_checkout_is_returned(self):
        """メインのチェックアウトが持っていても同じ。install= を出すと npm ci を打ち直させてしまう."""
        self.commit("lock", {"package-lock.json": "{}"})
        git(self.root, "checkout", "-qb", "feat/TEAM-1-x")
        out = self.worktree()
        self.assertEqual(out["worktree"], [str(self.root)])
        self.assertEqual(out["created"], ["0"])
        self.assertNotIn("install", out)
        self.assertNotIn("env_copied", out)
        self.assertFalse((self.root / ".claude" / "worktrees" / "TEAM-1").exists())

    def test_a_branch_sharing_the_prefix_is_not_taken_for_it(self):
        self.add_worktree("-b", "feat/TEAM-1-x-2", str(self.root.parent / "sibling"))
        git(self.root, "branch", "feat/TEAM-1-x")
        out = self.worktree()
        wt = self.root / ".claude" / "worktrees" / "TEAM-1"
        self.assertEqual(out["created"], ["1"])
        self.assertEqual(out["worktree"], [str(wt)])
        self.assertEqual(git(wt, "symbolic-ref", "--short", "HEAD"), "feat/TEAM-1-x")

    def assert_stopped_for_prune(self, res: subprocess.CompletedProcess, gone: Path) -> None:
        """登録だけが残った worktree の回は、何も書き換える前に prune を案内して止まる."""
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn(str(gone), res.stderr)
        self.assertIn("git worktree prune", res.stderr)
        self.assertNotIn("worktree=", res.stdout)
        self.assertNotIn(".claude/worktrees/", (self.root / ".git" / "info" / "exclude").read_text())
        self.assertFalse((self.root / ".claude" / "worktrees" / "TEAM-1").exists())

    def test_branch_held_by_a_vanished_worktree_stops_before_writing(self):
        """ディレクトリが消えた worktree のパスは返さない（移動が壊れる）。git worktree add も
        already used で落ちるので、info/exclude に書く前に prune を案内して止める."""
        sibling = self.vanished_worktree()
        res = run(self.root, "worktree", "feat/TEAM-1-x", "--name", "TEAM-1")
        self.assert_stopped_for_prune(res, sibling)
        # locked でないので unlock は案内しない。ブランチを持つ登録なのでコミットを残す git branch も案内しない
        self.assertNotIn("unlock", res.stderr)
        self.assertNotIn("git branch", res.stderr)
        # 鳴る側の対: prune すれば同じ呼び出しでそのブランチの worktree ができる
        git(self.root, "worktree", "prune")
        out = self.worktree()
        self.assertEqual((out["created"], out["base"]), (["1"], ["-"]))

    def test_vanished_worktree_at_the_path_stops_before_writing(self):
        """`.claude/worktrees/<name>` に登録だけが残っていると、別のブランチでも add は already registered で落ちる."""
        gone = self.vanished_worktree("feat/OTHER-1", self.root / ".claude" / "worktrees" / "TEAM-1")
        res = run(self.root, "worktree", "feat/TEAM-1-x", "--name", "TEAM-1")
        self.assert_stopped_for_prune(res, gone)
        self.assertNotIn("git branch", res.stderr)
        self.assertEqual(git(self.root, "branch", "--list", "feat/TEAM-1-x"), "")
        # 鳴る側の対: 登録の無い別の名前なら作れる
        self.assertEqual(self.worktree("feat/TEAM-1-x", "TEAM-1b")["created"], ["1"])

    def test_locked_vanished_worktree_points_to_unlock(self):
        """locked な登録は git worktree prune では消えない。prune だけを案内すると、打っても同じ所で止まり続ける."""
        sibling = self.vanished_worktree(locked=True)
        res = run(self.root, "worktree", "feat/TEAM-1-x", "--name", "TEAM-1")
        self.assert_stopped_for_prune(res, sibling)
        self.assertIn("git worktree unlock", res.stderr)
        git(self.root, "worktree", "prune")
        self.assert_stopped_for_prune(
            run(self.root, "worktree", "feat/TEAM-1-x", "--name", "TEAM-1"), sibling)
        # 鳴る側の対: unlock してから prune すれば作れる
        git(self.root, "worktree", "unlock", str(sibling))
        git(self.root, "worktree", "prune")
        self.assertEqual(self.worktree()["created"], ["1"])

    def test_vanished_detached_worktree_names_the_commit_to_keep(self):
        """detached HEAD のコミットは登録の HEAD からしか辿れないことがあり、prune で一緒に辿れなくなる."""
        wt = self.root / ".claude" / "worktrees" / "TEAM-1"
        self.add_worktree("--detach", str(wt))
        self.commit("w1", {"w1.txt": "1"}, wt)
        sha = git(wt, "rev-parse", "HEAD")
        shutil.rmtree(wt)
        res = run(self.root, "worktree", "feat/TEAM-1-x", "--name", "TEAM-1")
        self.assert_stopped_for_prune(res, wt)
        self.assertIn(f"git branch <名前> {sha}", res.stderr)

    def test_worktree_without_its_git_file_stops_before_writing(self):
        """ディレクトリが残っていても中の .git が消えれば、porcelain は prunable を付け、git は add を断る."""
        sibling = self.root.parent / "sibling"
        self.add_worktree("-b", "feat/TEAM-1-x", str(sibling))
        (sibling / ".git").unlink()
        self.assert_stopped_for_prune(
            run(self.root, "worktree", "feat/TEAM-1-x", "--name", "TEAM-1"), sibling)
        self.assertTrue(sibling.is_dir())
        rec = parse(run(self.root, "existing", "TEAM-1").stdout)
        self.assertEqual((rec["worktree"], rec["prunable"]), (["-"], [str(sibling)]))

    def test_path_with_another_branch_is_refused(self):
        """同じパスの worktree が別のブランチなら、頼まれたブランチの名前で created=0 を返さない（#305）."""
        self.write(".env.local", "SECRET=1")
        wt = self.root / ".claude" / "worktrees" / "TEAM-1"
        self.add_worktree("-b", "feat/OTHER-1", str(wt))
        res = run(self.root, "worktree", "feat/TEAM-1-x", "--name", "TEAM-1")
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("別のブランチ", res.stderr)
        self.assertNotIn("worktree=", res.stdout)
        self.assertEqual(git(self.root, "branch", "--list", "feat/TEAM-1-x"), "")
        self.assertFalse((wt / ".env.local").exists())
        # detached HEAD でも同じ
        git(wt, "checkout", "-q", "--detach")
        self.assertEqual(run(self.root, "worktree", "feat/TEAM-1-x", "--name", "TEAM-1").returncode, 1)
        # 鳴る側の対: そのパスの worktree が頼まれたブランチなら、作らずにそこを返す
        git(wt, "checkout", "-qb", "feat/TEAM-1-x")
        out = self.worktree()
        self.assertEqual((out["worktree"], out["created"]), ([str(wt)], ["0"]))

    def test_remote_only_branch_is_tracked_not_recut(self):
        """origin にだけあるブランチを既定ブランチから切り直すと、別のマシンで積んだコミットと分岐する."""
        git(self.root, "remote", "add", "origin", str(self.root.parent / "none.git"))
        sha = self.branch_with_commit("tmp")
        git(self.root, "update-ref", "refs/remotes/origin/feat/TEAM-1-x", sha)
        git(self.root, "branch", "-D", "tmp")
        out = self.worktree()
        wt = Path(out["worktree"][0])
        self.assertEqual(out["base"], ["origin/feat/TEAM-1-x"])
        self.assertEqual(out["created"], ["1"])
        self.assertEqual(git(wt, "rev-parse", "HEAD"), sha)
        self.assertEqual(git(wt, "rev-parse", "--abbrev-ref", "@{u}"), "origin/feat/TEAM-1-x")

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


class ExistingTest(RepoTestCase):
    """`existing <ISSUE-ID>`（start の Phase F2.5 が新規か続きかを決める材料）."""

    def one(self, out: dict[str, list[str]]) -> dict[str, str]:
        recs = self.records(out)
        self.assertEqual(len(recs), 1, out)
        return recs[0]

    # --- 黙る側（別の作業を Issue の作業と取り違えない）---

    def test_nothing_found_in_a_fresh_repo(self):
        self.assertEqual(self.existing(), {"found": ["0"]})

    def test_lookalike_and_unrelated_branches_are_not_matched(self):
        for b in ("feat/TEAM-12-x", "feat/XTEAM-1", "user/team-1-title", "feat/OTHER-1"):
            self.branch_with_commit(b)
        git(self.root, "update-ref", "refs/remotes/origin/feat/TEAM-10-y", self.main_sha)
        sibling = self.root.parent / "sibling"
        self.add_worktree("-b", "feat/OTHER-2", str(sibling))
        (sibling / "wip.txt").write_text("wip")
        self.assertEqual(self.existing(), {"found": ["0"]})
        # 鳴る側の対: 同じ repo に ID を含むブランチを 1 本足すと、それだけが出る
        git(self.root, "branch", "feat/TEAM-1-x")
        self.assertEqual(self.records(self.existing()), [{
            "worktree": "-", "branch": "feat/TEAM-1-x", "ahead": "0", "dirty": "-",
            "matched": "branch", "current": "0", "prunable": "-", "locked": "0",
            "head": self.main_sha}])

    def test_main_checkout_session_context_and_dirty_changes_are_not_work(self):
        """main で `/start {ID}` を呼ぶと Phase CTX がメイン側に issue_id を書く。main の変更は続きではない."""
        self.write_sc(self.root, "TEAM-1")
        (self.root / "a.txt").write_text("changed")
        self.write("new.txt")
        self.assertEqual(self.existing(), {"found": ["0"]})
        # 鳴る側の対: 同じ session-context を detached HEAD の worktree に置くと結び付く
        wt = self.root / ".claude" / "worktrees" / "happy-x"
        self.add_worktree("--detach", str(wt))
        self.write_sc(wt, "TEAM-1")
        self.assertEqual(self.one(self.existing()), {
            "worktree": str(wt), "branch": "detached", "ahead": "0", "dirty": "0",
            "matched": "session-context", "current": "0", "prunable": "-", "locked": "0",
            "head": self.main_sha})

    def test_session_context_on_a_branch_worktree_is_ignored(self):
        wt = self.root.parent / "sibling"
        self.add_worktree("-b", "feat/OTHER-1", str(wt))
        self.write_sc(wt, "TEAM-1")
        self.assertEqual(self.existing(), {"found": ["0"]})
        # 鳴る側の対: 同じ worktree を detached HEAD にすると session-context で結び付く
        git(wt, "checkout", "-q", "--detach")
        rec = self.one(self.existing())
        self.assertEqual((rec["matched"], rec["branch"]), ("session-context", "detached"))

    def test_session_context_of_another_issue_is_ignored(self):
        wt = self.root / ".claude" / "worktrees" / "happy-x"
        self.add_worktree("--detach", str(wt))
        (wt / ".claude").mkdir()
        (wt / ".claude" / "session-context.md").write_text('---\nissue_id: "TEAM-12"\n---\n')
        self.assertEqual(self.existing("TEAM-1"), {"found": ["0"]})
        self.assertEqual(self.one(self.existing("TEAM-12"))["matched"], "session-context")

    def test_untracked_files_under_dot_claude_are_not_counted_as_dirty(self):
        """start と hook が書くファイルを gitignore していない repo で、/start しただけの worktree を作業ありにしない."""
        self.commit("settings", {".claude/settings.json": "{}"})
        wt = self.root.parent / "sibling"
        self.add_worktree("-b", "feat/TEAM-1-x", str(wt))
        self.write_sc(wt, "TEAM-1")
        (wt / ".claude" / "events.jsonl").write_text("{}\n")
        self.assertEqual(self.one(self.existing())["dirty"], "0")
        # 鳴る側の対: .claude/ の下でも追跡済みのファイルの変更は数える（除くのは未追跡だけ）
        (wt / ".claude" / "settings.json").write_text('{"changed": 1}')
        self.assertEqual(self.one(self.existing())["dirty"], "1")
        # .claude/ の外の未追跡と追跡済みの変更も数える
        (wt / "x.txt").write_text("x")
        (wt / "a.txt").write_text("changed")
        self.assertEqual(self.one(self.existing())["dirty"], "3")

    def test_env_files_copied_by_worktree_are_not_counted_as_dirty(self):
        """worktree サブコマンドが写した .env* で、作った直後の worktree を作業ありにしない（新規の選択が出なくなる）."""
        self.commit("web", {"apps/web/index.js": ""})
        self.write(".env.local", "SECRET=1")
        self.write("apps/web/.env", "W=1")
        out = self.worktree()
        self.assertEqual(sorted(out["env_copied"]), [".env.local", "apps/web/.env"])
        wt = Path(out["worktree"][0])
        self.assertEqual(self.one(self.existing())["dirty"], "0")
        # 鳴る側の対: 写した後に中身が変われば数える（worktree 側でもメイン側でも）
        (wt / ".env.local").write_text("SECRET=2")
        self.assertEqual(self.one(self.existing())["dirty"], "1")
        self.write("apps/web/.env", "W=2")
        self.assertEqual(self.one(self.existing())["dirty"], "2")
        # .env* でない未追跡は、メイン側に同じ中身があっても数える
        self.write("notes.txt", "n")
        (wt / "notes.txt").write_text("n")
        self.assertEqual(self.one(self.existing())["dirty"], "3")
        # 通常のファイルでない .env*（壊れたリンク）は写したものではないので数える
        os.symlink("missing", wt / ".env.broken")
        self.assertEqual(self.one(self.existing())["dirty"], "4")

    def test_untracked_env_in_the_main_checkout_still_counts(self):
        """メインのチェックアウト自身は比べる相手が自分なので、未追跡の .env* も数える."""
        git(self.root, "checkout", "-qb", "feat/TEAM-1-x")
        self.assertEqual(self.one(self.existing())["dirty"], "0")
        self.write(".env.local", "SECRET=1")
        self.assertEqual(self.one(self.existing())["dirty"], "1")

    def test_failed_counts_are_reported_as_unknown_not_zero(self):
        """数えられなかった値を 0 と書くと作業なしに化ける。- は start が作業ありに倒す."""
        # まだコミットの無い HEAD（orphan のブランチ）は rev-list が 0000… を読めない
        wt = self.root.parent / "orphan"
        self.add_worktree("--detach", str(wt))
        git(wt, "checkout", "-q", "--orphan", "feat/TEAM-1-x")
        rec = self.one(self.existing())
        # porcelain の HEAD は 0000… — それを head= に出すと git branch <名前> 0000… を案内してしまう
        self.assertEqual((rec["ahead"], rec["head"], rec["worktree"]), ("-", "-", str(wt)))
        # 鳴る側の対: 1 つでもコミットがあれば数える
        self.commit("first", {"o.txt": "o"}, wt)
        rec = self.one(self.existing())
        self.assertEqual((rec["ahead"], rec["head"]), ("1", git(wt, "rev-parse", "HEAD")))
        # index が壊れた worktree は git status が失敗する
        self.assertEqual(self.one(self.existing())["dirty"], "0")
        (Path(git(wt, "rev-parse", "--absolute-git-dir")) / "index").write_text("garbage")
        self.assertEqual(self.one(self.existing())["dirty"], "-")

    def test_a_vanished_worktree_is_reported_as_prunable(self):
        """ディレクトリが消えた worktree のパスを worktree= に出さない（そこへ移ると壊れる）。ブランチだけの
        候補に見せると、start は git switch / worktree の作成に進んでどちらも already used で落ちる."""
        sibling = self.vanished_worktree()
        self.assertEqual(self.records(self.existing()), [{
            "worktree": "-", "branch": "feat/TEAM-1-x", "ahead": "0", "dirty": "-",
            "matched": "branch", "current": "0", "prunable": str(sibling), "locked": "0",
            "head": self.main_sha}])
        # 鳴る側の対: prune した後はブランチだけの候補になる
        git(self.root, "worktree", "prune")
        self.assertEqual(self.one(self.existing())["prunable"], "-")

    def test_a_vanished_locked_worktree_is_marked_locked(self):
        """locked な登録は prune で消えない。start が prune だけを案内しないよう locked=1 で知らせる."""
        sibling = self.vanished_worktree(locked=True)
        rec = self.one(self.existing())
        self.assertEqual((rec["worktree"], rec["prunable"], rec["locked"]), ("-", str(sibling), "1"))
        git(self.root, "worktree", "prune")
        self.assertEqual(self.one(self.existing())["prunable"], str(sibling))
        # 鳴る側の対: unlock してから prune すればブランチだけの候補になる
        git(self.root, "worktree", "unlock", str(sibling))
        git(self.root, "worktree", "prune")
        rec = self.one(self.existing())
        self.assertEqual((rec["prunable"], rec["locked"]), ("-", "0"))

    def test_locked_is_not_carried_over_to_the_next_worktree(self):
        """porcelain は worktree ごとに locked の行を持つ。前の worktree の値を次へ持ち越さない."""
        # git worktree list はパスの順に並べる（実測 git 2.50）ので、locked の方を先に置く
        self.vanished_worktree("feat/TEAM-1-a", self.root.parent / "a-locked", locked=True)
        self.vanished_worktree("feat/TEAM-1-b", self.root.parent / "b-open")
        self.assertEqual({r["branch"]: r["locked"] for r in self.records(self.existing())},
                         {"feat/TEAM-1-a": "1", "feat/TEAM-1-b": "0"})

    def test_a_locked_worktree_that_is_still_there_is_not_prunable(self):
        """locked は prune を止めるだけで、ディレクトリがあればそこへ移れる."""
        sibling = self.root.parent / "sibling"
        self.add_worktree("-b", "feat/TEAM-1-x", str(sibling))
        git(self.root, "worktree", "lock", str(sibling))
        rec = self.one(self.existing())
        self.assertEqual((rec["worktree"], rec["prunable"], rec["locked"]), (str(sibling), "-", "1"))

    def test_a_vanished_detached_worktree_reports_its_head(self):
        """prune の前に git branch で残すコミットを start が案内できるよう、head= に HEAD を出す."""
        wt = self.root / ".claude" / "worktrees" / "TEAM-1"
        self.add_worktree("--detach", str(wt))
        self.commit("w1", {"w1.txt": "1"}, wt)
        sha = git(wt, "rev-parse", "HEAD")
        shutil.rmtree(wt)
        rec = self.one(self.existing())
        self.assertEqual(
            {k: rec[k] for k in ("branch", "ahead", "matched", "prunable", "head")},
            {"branch": "detached", "ahead": "1", "matched": "path", "prunable": str(wt), "head": sha})
        # prune すると候補ごと消え（次の /start は新規になる）、そのコミットはどの ref からも辿れない
        git(self.root, "worktree", "prune")
        self.assertEqual(self.existing(), {"found": ["0"]})
        self.assertEqual(git(self.root, "for-each-ref", "--contains", sha), "")

    def test_a_vanished_worktree_is_found_without_the_prunable_note(self):
        """porcelain の `prunable` は git 2.31 から。無い git でもディレクトリの有無で見分ける."""
        real_git = shutil.which("git", path=ENV.get("PATH"))
        self.assertIsNotNone(real_git)
        bindir = self.root.parent / "bin"
        bindir.mkdir()
        stub = bindir / "git"
        stub.write_text('#!/bin/sh\ncase " $* " in *" worktree list "*)\n'
                        f'  "{real_git}" "$@" | grep -v "^prunable"; exit 0 ;;\nesac\n'
                        f'exec "{real_git}" "$@"\n')
        stub.chmod(0o755)
        sibling = self.root.parent / "sibling"
        self.add_worktree("-b", "feat/TEAM-1-x", str(sibling))
        shutil.rmtree(sibling)
        env = {**ENV, "PATH": f"{bindir}{os.pathsep}{ENV.get('PATH', '')}"}
        listed = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=self.root,
                                capture_output=True, text=True, env=env).stdout
        self.assertIn(f"worktree {sibling}", listed)
        self.assertNotIn("prunable", listed)
        res = subprocess.run(["bash", str(SCRIPT), "existing", "TEAM-1"], cwd=self.root,
                             capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        rec = self.one(parse(res.stdout))
        self.assertEqual((rec["worktree"], rec["prunable"]), ("-", str(sibling)))
        # worktree サブコマンドも同じ見分け方で、git に落とされる前に止まる
        res = subprocess.run(["bash", str(SCRIPT), "worktree", "feat/TEAM-1-x", "--name", "TEAM-1"],
                             cwd=self.root, capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("git worktree prune", res.stderr)

    def test_unknown_default_branch_reports_ahead_as_dash(self):
        """既定ブランチが分からない回に 0 と書くと「作業なし」と取り違える."""
        git(self.root, "branch", "-m", "main", "trunk")
        self.branch_with_commit("feat/TEAM-1-x")
        self.assertEqual(self.one(self.existing())["ahead"], "-")

    def test_bad_issue_ids_are_argument_errors(self):
        """正規表現に埋め込む前に弾く."""
        for args in ((), ("team-1",), ("TEAM-",), ("TEAM-1.*",), ("-1",), ("TEAM-1", "x")):
            with self.subTest(args=args):
                res = run(self.root, "existing", *args)
                self.assertEqual(res.returncode, 2, res.stderr)
                self.assertNotIn("found=", res.stdout)

    # --- 鳴る側 ---

    def test_branch_checked_out_in_another_worktree_is_reported(self):
        elsewhere = self.root.parent / "elsewhere"
        self.add_worktree("-b", "feat/TEAM-1-x", str(elsewhere))
        self.commit("w1", {"w1.txt": "1"}, elsewhere)
        self.commit("w2", {"w2.txt": "2"}, elsewhere)
        (elsewhere / "wip.txt").write_text("wip")
        # ブランチだけの候補と二重に出さない
        self.assertEqual(self.records(self.existing()), [{
            "worktree": str(elsewhere), "branch": "feat/TEAM-1-x", "ahead": "2", "dirty": "1",
            "matched": "branch", "current": "0", "prunable": "-", "locked": "0",
            "head": git(elsewhere, "rev-parse", "HEAD")}])
        self.assertEqual(self.one(self.existing(cwd=elsewhere))["current"], "1")

    def test_issue_named_worktree_is_matched_even_when_detached(self):
        wt = self.root / ".claude" / "worktrees" / "TEAM-1"
        self.add_worktree("--detach", str(wt))
        self.commit("w1", {"w1.txt": "1"}, wt)
        rec = self.one(self.existing())
        self.assertEqual((rec["matched"], rec["branch"], rec["ahead"]), ("path", "detached", "1"))

    def test_id_at_either_end_of_the_name_is_matched(self):
        """`feat/TEAM-1`（F1 の例の形）と `TEAM-1-x`。境界の `$` と `^` はどちらも引用符の中で変異ツールが触らない."""
        git(self.root, "branch", "feat/TEAM-12")
        self.assertEqual(self.existing(), {"found": ["0"]})
        # 鳴る側の対: 末尾が ID の名前と、先頭が ID の名前
        git(self.root, "branch", "feat/TEAM-1")
        git(self.root, "branch", "TEAM-1-x")
        recs = self.records(self.existing())
        self.assertEqual(sorted(r["branch"] for r in recs), ["TEAM-1-x", "feat/TEAM-1"])
        self.assertEqual({r["matched"] for r in recs}, {"branch"})

    def test_worktree_made_by_branch_setup_matches_by_branch_and_path(self):
        self.worktree()
        self.assertEqual(self.one(self.existing())["matched"], "branch,path")

    def test_commits_already_on_origin_default_are_not_counted(self):
        """worktree は origin/<既定> から切るので、ローカルの main が遅れていても作業のコミットだけを数える."""
        self.commit("c2", {"c2.txt": "2"})
        git(self.root, "update-ref", "refs/remotes/origin/main", "HEAD")
        self.branch_with_commit("feat/TEAM-1-x")
        git(self.root, "reset", "-q", "--hard", self.main_sha)
        self.assertEqual(self.one(self.existing())["ahead"], "1")

    def test_remote_only_branch_is_reported_and_local_wins(self):
        sha = self.branch_with_commit("tmp")
        git(self.root, "update-ref", "refs/remotes/origin/feat/TEAM-1-r", sha)
        git(self.root, "branch", "-D", "tmp")
        self.assertEqual(self.records(self.existing()), [{
            "worktree": "-", "branch": "origin/feat/TEAM-1-r", "ahead": "1", "dirty": "-",
            "matched": "branch", "current": "0", "prunable": "-", "locked": "0", "head": sha}])
        # 同名のローカルができたら origin 側は重ねて出さない
        git(self.root, "branch", "feat/TEAM-1-r", "origin/feat/TEAM-1-r")
        self.assertEqual(self.one(self.existing())["branch"], "feat/TEAM-1-r")

    def test_main_checkout_on_the_issue_branch_is_current(self):
        git(self.root, "checkout", "-qb", "feat/TEAM-1-x")
        rec = self.one(self.existing())
        self.assertEqual((rec["worktree"], rec["current"]), (str(self.root), "1"))

    def test_candidates_are_ordered_worktree_then_local_then_remote(self):
        """辞書順と逆に名前を付け、並びが出力の規約から来ていることを見る."""
        self.add_worktree("-b", "feat/TEAM-1-c", str(self.root.parent / "sibling"))
        git(self.root, "branch", "feat/TEAM-1-b")
        git(self.root, "update-ref", "refs/remotes/origin/feat/TEAM-1-a", self.main_sha)
        # worktree が持つブランチと同名の origin のブランチは重ねて出さない
        git(self.root, "update-ref", "refs/remotes/origin/feat/TEAM-1-c", self.main_sha)
        self.assertEqual([r["branch"] for r in self.records(self.existing())],
                         ["feat/TEAM-1-c", "feat/TEAM-1-b", "origin/feat/TEAM-1-a"])

    def test_vanished_worktree_is_listed_with_the_worktrees_not_with_the_branches(self):
        """登録だけが残った worktree のブランチは worktree の並びに 1 回だけ出す（ブランチだけの候補と重ねない）.

        ブランチだけの並びは refname の辞書順なので、辞書順と逆に名前を付けて、どちらの並びから出たかを見る。
        """
        self.vanished_worktree("feat/TEAM-1-c")
        git(self.root, "branch", "feat/TEAM-1-b")
        recs = self.records(self.existing())
        self.assertEqual([(r["branch"], r["prunable"] != "-") for r in recs],
                         [("feat/TEAM-1-c", True), ("feat/TEAM-1-b", False)])


class WorktreesListTest(RepoTestCase):
    """`worktrees`（start の Phase D2 が「worktree で作業中」に出す一覧）."""

    def listed(self) -> list[tuple[str, str, str]]:
        res = run(self.root, "worktrees")
        self.assertEqual(res.returncode, 0, res.stderr)
        out = parse(res.stdout)
        self.assertLessEqual(set(out), {"id", "branch", "worktree"}, out)
        ids, branches, paths = (out.get(k, []) for k in ("id", "branch", "worktree"))
        self.assertEqual(len(ids), len(branches))
        self.assertEqual(len(ids), len(paths))
        return list(zip(ids, branches, paths))

    def test_lists_linked_worktrees_whose_branch_has_an_issue_id(self):
        team = self.root.parent / "team"
        self.add_worktree("-b", "feat/TEAM-12-x", str(team))
        self.add_worktree("-b", "TEAM-3", str(self.root.parent / "bare-id"))
        # worktree どうしの並びは git worktree list の順（作った順とは限らない）なので並べ替えて比べる
        self.assertEqual(sorted(self.listed()), [
            ("TEAM-12", "feat/TEAM-12-x", str(team)),
            ("TEAM-3", "TEAM-3", str(self.root.parent / "bare-id"))])

    def test_skips_main_detached_vanished_and_branches_without_an_id(self):
        git(self.root, "checkout", "-qb", "feat/MAIN-1-x")
        self.add_worktree("--detach", str(self.root.parent / "detached"))
        self.vanished_worktree("feat/GONE-1-x")
        for name, branch in (("lower", "user/team-1-title"), ("glued", "fix/abcTEAM-1"),
                             ("plain", "chore/cleanup")):
            self.add_worktree("-b", branch, str(self.root.parent / name))
        self.assertEqual(self.listed(), [])
        # 鳴る側の対: 同じ repo に ID を含むブランチの worktree を 1 つ足すと、それだけが出る
        self.add_worktree("-b", "feat/TEAM-1-x", str(self.root.parent / "team"))
        self.assertEqual([i for i, _, _ in self.listed()], ["TEAM-1"])

    def test_arguments_are_refused(self):
        self.assertEqual(run(self.root, "worktrees", "TEAM-1").returncode, 2)


def section(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i:text.index(end, i)]


class StartSkillContractTest(RepoTestCase):
    """start が読むキーと WORK_STATE が、スクリプトの出力・判定の正本とずれない."""

    STATES = ("none", "fresh", "here", "moved", "branch", "detached", "closed", "prunable")

    def test_dashboard_lists_worktrees_through_the_script(self):
        """D2 は porcelain を散文で読み分けず、スクリプトの出力を表示するだけにする（除外条件と ID の当て方がずれる）."""
        self.add_worktree("-b", "feat/TEAM-1-x", str(self.root.parent / "team"))
        res = run(self.root, "worktrees")
        self.assertEqual(res.returncode, 0, res.stderr)
        keys = set(parse(res.stdout))
        self.assertEqual(keys, {"id", "branch", "worktree"})
        d2 = section(START.read_text(encoding="utf-8"), "### Phase D2:", "### Phase D2.5")
        self.assertIn('branch-setup.sh" worktrees', d2)
        self.assertNotIn("git worktree list", d2)
        for k in sorted(keys):
            with self.subTest(key=k):
                self.assertIn(f"`{k}=`", d2)

    def test_start_skill_names_every_key_the_script_prints(self):
        git(self.root, "branch", "feat/TEAM-1-x")
        keys = set(self.existing())
        self.assertEqual(keys, {"found", *KEYS})
        f25 = section(START.read_text(encoding="utf-8"), "### Phase F2.5", "### Phase F3:")
        doc = EXISTING_DOC.read_text(encoding="utf-8")
        self.assertIn('branch-setup.sh" existing', f25)
        self.assertIn("skills/start/references/existing-work.md", f25)
        for k in sorted(keys):
            with self.subTest(key=k):
                self.assertIn(f"`{k}=`", f25)
                self.assertIn(f"`{k}=`", doc)

    def test_every_work_state_is_defined_and_handled_by_f7(self):
        skill = START.read_text(encoding="utf-8")
        f7 = section(skill, "### Phase F7", "\n---\n")
        table = section(EXISTING_DOC.read_text(encoding="utf-8"), "## 2.", "## 3.")
        for st in self.STATES:
            with self.subTest(state=st):
                self.assertIn(f"`{st}`", table)
                # F7 は単独の `here` と、分岐の見出しの `WORK_STATE = branch` の両方で書く
                self.assertRegex(f7, rf"`(WORK_STATE = )?{st}`")
                # F2.5 の要点の一覧にも並べる（F7 と表にだけ足して F2.5 から漏れた値を拾う）
                self.assertIn(f"`{st}`", section(skill, "### Phase F2.5", "### Phase F3:"))


if __name__ == "__main__":
    unittest.main()
