#!/usr/bin/env python3
"""issue-workflow 同梱 `scripts/sync-claude-to-main.py` の CLI 境界テスト.

issue-maintain が完了 Issue の worktree から .claude/ の未追跡ファイルをメインへ写す口。
厚く見るのは「メインを壊さない」側（メインの方が新しいファイル・追記型の .jsonl・チェックアウトごとの
状態・メインで追跡しているパス・--dry-run・メインのチェックアウトで呼んだ回）。どれも壊れても
コピー自体は成功して見えるので、出力を眺めても気づけない。黙る側には同じ入力で動く側の対を置く。

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
SCRIPT = REPO / "issue-workflow" / "scripts" / "sync-claude-to-main.py"
ENV = scrub()


def git(cwd: Path, *args: str) -> str:
    res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=ENV)
    if res.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {res.stderr}")
    return res.stdout.strip()


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["python3", str(SCRIPT), *args], cwd=cwd, capture_output=True,
                          text=True, env=ENV, timeout=60)


def lines(stdout: str, key: str) -> list[str]:
    return [ln.split("=", 1)[1] for ln in stdout.splitlines() if ln.startswith(key + "=")]


class SyncTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.main = self.tmp / "repo"
        self.main.mkdir()
        git(self.main, "init", "-q", "-b", "main")
        git(self.main, "config", "user.email", "t@example.com")
        git(self.main, "config", "user.name", "t")
        (self.main / ".gitignore").write_text(".claude/indie/\n.claude/worktrees/\n")
        (self.main / ".claude").mkdir()
        (self.main / ".claude" / "tracked.md").write_text("v1\n")
        git(self.main, "add", "-A")
        git(self.main, "commit", "-q", "-m", "init")
        self.wt = self.main / ".claude" / "worktrees" / "X-1"
        git(self.main, "worktree", "add", "-q", "-b", "feat/X-1", str(self.wt))

    def write(self, root: Path, rel: str, text: str, mtime: float | None = None) -> Path:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        if mtime is not None:
            os.utime(p, (mtime, mtime))
        return p


class TestOutsideWorktree(SyncTestCase):
    def test_main_checkout_does_nothing(self):
        self.write(self.main, ".claude/indie/a/issues/X-2.md", "main only\n")
        res = run(self.main)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "in_worktree=0")

    def test_outside_git_exits_2(self):
        res = run(self.tmp)
        self.assertEqual(res.returncode, 2)


class TestCopy(SyncTestCase):
    def test_copies_ignored_file_missing_in_main(self):
        self.write(self.wt, ".claude/indie/a/knowledge/k.md", "new\n")
        res = run(self.wt)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("in_worktree=1", res.stdout)
        self.assertEqual(lines(res.stdout, "main_root"), [str(self.main.resolve())])
        self.assertEqual(lines(res.stdout, "copied"), [".claude/indie/a/knowledge/k.md"])
        self.assertEqual((self.main / ".claude/indie/a/knowledge/k.md").read_text(), "new\n")

    def test_copies_untracked_not_ignored_file(self):
        self.write(self.wt, ".claude/adr/new.md", "adr\n")
        res = run(self.wt)
        self.assertEqual(lines(res.stdout, "copied"), [".claude/adr/new.md"])
        self.assertTrue((self.main / ".claude/adr/new.md").exists())

    def test_dry_run_writes_nothing(self):
        self.write(self.wt, ".claude/indie/a/knowledge/k.md", "new\n")
        res = run(self.wt, "--dry-run")
        self.assertEqual(lines(res.stdout, "copied"), [".claude/indie/a/knowledge/k.md"])
        self.assertFalse((self.main / ".claude/indie/a/knowledge/k.md").exists())

    def test_identical_counts_unchanged(self):
        self.write(self.wt, ".claude/indie/a/x.md", "same\n")
        self.write(self.main, ".claude/indie/a/x.md", "same\n")
        res = run(self.wt)
        self.assertEqual(lines(res.stdout, "copied"), [])
        self.assertEqual(lines(res.stdout, "unchanged"), ["1"])


class TestConflict(SyncTestCase):
    def test_worktree_newer_overwrites_and_backs_up(self):
        self.write(self.main, ".claude/indie/a/issues/X-1.md", "old\n", mtime=1_000_000)
        self.write(self.wt, ".claude/indie/a/issues/X-1.md", "done\n", mtime=2_000_000)
        res = run(self.wt)
        self.assertEqual(lines(res.stdout, "overwritten"), [".claude/indie/a/issues/X-1.md"])
        self.assertEqual((self.main / ".claude/indie/a/issues/X-1.md").read_text(), "done\n")
        backup = lines(res.stdout, "backup")
        self.assertEqual(len(backup), 1)
        self.assertEqual((Path(backup[0]) / ".claude/indie/a/issues/X-1.md").read_text(), "old\n")
        self.assertFalse(Path(backup[0]).is_relative_to(self.main.resolve() / ".claude"))

    def test_main_newer_is_kept(self):
        self.write(self.main, ".claude/indie/a/issues/X-1.md", "main\n", mtime=2_000_000)
        self.write(self.wt, ".claude/indie/a/issues/X-1.md", "wt\n", mtime=1_000_000)
        res = run(self.wt)
        self.assertEqual(lines(res.stdout, "kept_main"), [".claude/indie/a/issues/X-1.md"])
        self.assertEqual(lines(res.stdout, "backup"), [])
        self.assertEqual((self.main / ".claude/indie/a/issues/X-1.md").read_text(), "main\n")

    def test_jsonl_appends_only_missing_lines(self):
        self.write(self.main, ".claude/indie/events.jsonl", '{"a":1}\n{"b":2}', mtime=2_000_000)
        self.write(self.wt, ".claude/indie/events.jsonl", '{"a":1}\n{"c":3}\n', mtime=1_000_000)
        res = run(self.wt)
        self.assertEqual(lines(res.stdout, "appended"), [".claude/indie/events.jsonl 1"])
        self.assertEqual((self.main / ".claude/indie/events.jsonl").read_text(),
                         '{"a":1}\n{"b":2}\n{"c":3}\n')

    def test_jsonl_with_no_new_lines_is_unchanged(self):
        self.write(self.main, ".claude/indie/events.jsonl", '{"a":1}\n{"b":2}\n')
        self.write(self.wt, ".claude/indie/events.jsonl", '{"a":1}\n')
        res = run(self.wt)
        self.assertEqual(lines(res.stdout, "appended"), [])
        self.assertEqual(lines(res.stdout, "unchanged"), ["1"])
        self.assertEqual((self.main / ".claude/indie/events.jsonl").read_text(), '{"a":1}\n{"b":2}\n')


class TestSkip(SyncTestCase):
    def test_checkout_local_state_is_skipped(self):
        self.write(self.wt, ".claude/session-context.md", "wt ctx\n")
        self.write(self.wt, ".claude/settings.local.json", "{}\n")
        res = run(self.wt)
        self.assertEqual(sorted(lines(res.stdout, "skipped")),
                         [".claude/session-context.md", ".claude/settings.local.json"])
        self.assertFalse((self.main / ".claude/session-context.md").exists())
        self.assertFalse((self.main / ".claude/settings.local.json").exists())

    def test_symlink_is_skipped(self):
        (self.wt / ".claude").mkdir(exist_ok=True)
        os.symlink("/etc/hosts", self.wt / ".claude/link.md")
        res = run(self.wt)
        self.assertEqual(lines(res.stdout, "skipped"), [".claude/link.md"])
        self.assertFalse((self.main / ".claude/link.md").exists())

    def test_path_tracked_in_main_is_not_touched(self):
        # worktree のブランチで消したファイルを未追跡で置き直した回。メインの追跡済みの版を残す
        git(self.wt, "rm", "-q", ".claude/tracked.md")
        git(self.wt, "commit", "-q", "-m", "rm")
        self.write(self.wt, ".claude/tracked.md", "wt\n", mtime=4_000_000_000)
        res = run(self.wt)
        self.assertEqual(lines(res.stdout, "tracked_in_main"), [".claude/tracked.md"])
        self.assertEqual((self.main / ".claude/tracked.md").read_text(), "v1\n")

    def test_tracked_uncommitted_change_is_reported_not_copied(self):
        self.write(self.wt, ".claude/tracked.md", "v2\n")
        res = run(self.wt)
        self.assertEqual(lines(res.stdout, "uncommitted"), [".claude/tracked.md"])
        self.assertEqual(lines(res.stdout, "copied"), [])
        self.assertEqual((self.main / ".claude/tracked.md").read_text(), "v1\n")

    def test_clean_tracked_file_is_not_reported(self):
        res = run(self.wt)
        self.assertEqual(lines(res.stdout, "uncommitted"), [])

    def test_renamed_tracked_file_reports_new_path_only(self):
        git(self.wt, "mv", ".claude/tracked.md", ".claude/moved.md")
        res = run(self.wt)
        self.assertEqual(lines(res.stdout, "uncommitted"), [".claude/moved.md"])


if __name__ == "__main__":
    unittest.main()
