#!/usr/bin/env python3
"""issue-workflow 同梱 `scripts/issue-files.py` の CLI 境界テスト（GitHub issue #422）.

maintain 系が完了 Issue を消す前に通す口。厚く見るのは「戻せないファイルを消さない」側
（gitignore・.git/info/exclude で外した DATA_DIR / git 管理外の dir / 未コミットの変更がある追跡下のファイル /
退避先の同名ファイル / glob 文字を含むファイル名）。
どれも壊れても削除自体は成功して見えるので、出力を眺めても気づけない。

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
SCRIPT = REPO / "issue-workflow" / "scripts" / "issue-files.py"
ENV = scrub()


def git(cwd: Path, *args: str) -> str:
    res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=ENV)
    if res.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {res.stderr}")
    return res.stdout.strip()


def run(cwd: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["python3", str(SCRIPT), *args], cwd=cwd, capture_output=True,
                          text=True, env=env or ENV, timeout=60)


def lines(stdout: str, key: str) -> list[str]:
    return [ln.split("=", 1)[1] for ln in stdout.splitlines() if ln.startswith(key + "=")]


class IssueFilesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "t")
        self.issues = self.repo / ".claude" / "indie" / "cp" / "issues"
        self.issues.mkdir(parents=True)
        self.archive = self.repo / ".claude" / "indie" / "cp" / "archive"

    def write(self, name: str, body: str = "---\nstatus: completed\n---\n") -> Path:
        p = self.issues / name
        p.write_text(body)
        return p

    def commit_all(self) -> None:
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")

    def exclude_data_dir(self) -> None:
        (self.repo / ".git" / "info").mkdir(exist_ok=True)
        with open(self.repo / ".git" / "info" / "exclude", "a") as f:
            f.write(".claude/indie/\n")


class CheckTest(IssueFilesTestCase):
    def test_tracked_file(self):
        p = self.write("CP-1.md")
        self.commit_all()
        res = run(self.repo, "check", str(p))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(lines(res.stdout, "tracked"), [str(p)])
        self.assertEqual(lines(res.stdout, "untracked"), [])

    def test_modified_tracked_file_is_dirty(self):
        # 削除すると git から戻るのは最後にコミットした版だけなので、tracked と分ける
        p = self.write("CP-1.md")
        self.commit_all()
        p.write_text("圧縮した後\n")
        res = run(self.repo, "check", str(p))
        self.assertEqual(lines(res.stdout, "dirty"), [str(p)])
        self.assertEqual(lines(res.stdout, "tracked"), [])

    def test_added_but_never_committed_is_dirty(self):
        (self.repo / "README.md").write_text("x\n")
        self.commit_all()
        p = self.write("CP-2.md")
        git(self.repo, "add", str(p.relative_to(self.repo)))
        res = run(self.repo, "check", str(p))
        self.assertEqual(lines(res.stdout, "dirty"), [str(p)])

    def test_glob_chars_in_name_do_not_match_other_tracked_file(self):
        self.write("x1.md")
        self.commit_all()
        p = self.write("x[1].md")
        res = run(self.repo, "check", str(p))
        self.assertEqual(lines(res.stdout, "untracked"), [str(p)])

    def test_excluded_data_dir_is_untracked(self):
        self.exclude_data_dir()
        (self.repo / "README.md").write_text("x\n")
        self.commit_all()
        p = self.write("CP-1.md")
        res = run(self.repo, "check", str(p))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(lines(res.stdout, "untracked"), [str(p)])
        self.assertEqual(lines(res.stdout, "tracked"), [])

    def test_new_file_not_yet_added_is_untracked(self):
        (self.repo / "README.md").write_text("x\n")
        self.commit_all()
        p = self.write("CP-2.md")
        res = run(self.repo, "check", str(p))
        self.assertEqual(lines(res.stdout, "untracked"), [str(p)])

    def test_outside_git_is_untracked(self):
        d = self.tmp / "nogit"
        d.mkdir()
        p = d / "CP-1.md"
        p.write_text("x\n")
        # 一時 dir の祖先に repo があっても拾わないよう、探索を tmp で止める
        env = scrub(GIT_CEILING_DIRECTORIES=str(self.tmp))
        res = run(self.tmp, "check", str(p), env=env)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(lines(res.stdout, "untracked"), [str(p)])

    def test_judged_by_file_dir_not_cwd(self):
        # cwd が別の repo（worktree のセッション）でも、ファイル側の repo の index で決める
        p = self.write("CP-1.md")
        self.commit_all()
        other = self.tmp / "other"
        other.mkdir()
        git(other, "init", "-q", "-b", "main")
        res = run(other, "check", str(p))
        self.assertEqual(lines(res.stdout, "tracked"), [str(p)])

    def test_failed_status_is_dirty(self):
        # status が失敗したら一致を確かめられないので、戻せる側（tracked）に倒さない。
        # $1 は issue-files.py が先頭に付ける --literal-pathspecs
        p = self.write("CP-1.md")
        self.commit_all()
        stub = self.tmp / "bin"
        stub.mkdir()
        (stub / "git").write_text(
            f'#!/bin/sh\n[ "$2" = status ] && exit 128\nexec "{shutil.which("git")}" "$@"\n')
        (stub / "git").chmod(0o755)
        env = scrub(PATH=f"{stub}{os.pathsep}{os.environ['PATH']}")
        res = run(self.repo, "check", str(p), env=env)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(lines(res.stdout, "dirty"), [str(p)])

    def test_missing_path_exit_2_and_others_still_reported(self):
        p = self.write("CP-1.md")
        self.commit_all()
        res = run(self.repo, "check", str(self.issues / "CP-9.md"), str(p))
        self.assertEqual(res.returncode, 2)
        self.assertEqual(lines(res.stdout, "missing"), [str(self.issues / "CP-9.md")])
        self.assertEqual(lines(res.stdout, "tracked"), [str(p)])


class RetireTest(IssueFilesTestCase):
    def test_untracked_is_archived_not_deleted(self):
        self.exclude_data_dir()
        (self.repo / "README.md").write_text("x\n")
        self.commit_all()
        p = self.write("CP-1.md", "本文\n")
        res = run(self.repo, "retire", "--archive-dir", str(self.archive), str(p))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse(p.exists())
        dest = self.archive / "CP-1.md"
        self.assertEqual(dest.read_text(), "本文\n")
        self.assertEqual(lines(res.stdout, "archived"), [str(p)])
        self.assertEqual(lines(res.stdout, "archived_to"), [str(dest)])
        self.assertEqual(lines(res.stdout, "deleted"), [])

    def test_tracked_is_deleted_and_restorable_from_git(self):
        p = self.write("CP-1.md", "本文\n")
        self.commit_all()
        res = run(self.repo, "retire", "--archive-dir", str(self.archive), str(p))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse(p.exists())
        self.assertFalse(self.archive.exists())
        self.assertEqual(lines(res.stdout, "deleted"), [str(p)])
        git(self.repo, "checkout", "--", str(p.relative_to(self.repo)))
        self.assertEqual(p.read_text(), "本文\n")

    def test_dirty_in_head_is_deleted(self):
        # 2026-11-08 決定: HEAD に版があれば、この実行で書き換えた dirty も削除する（前の内容は HEAD か backup の控えに残る）
        p = self.write("CP-1.md", "コミットした版\n")
        self.commit_all()
        p.write_text("圧縮した後\n")
        res = run(self.repo, "retire", "--archive-dir", str(self.archive), str(p))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(lines(res.stdout, "deleted"), [str(p)])
        self.assertFalse(p.exists())
        self.assertFalse(self.archive.exists())
        git(self.repo, "checkout", "--", str(p.relative_to(self.repo)))
        self.assertEqual(p.read_text(), "コミットした版\n")

    def test_added_but_not_in_head_is_archived(self):
        (self.repo / "README.md").write_text("x\n")
        self.commit_all()
        p = self.write("CP-2.md", "add しただけ\n")
        git(self.repo, "add", str(p.relative_to(self.repo)))
        res = run(self.repo, "retire", "--archive-dir", str(self.archive), str(p))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(lines(res.stdout, "deleted"), [])
        self.assertEqual((self.archive / "CP-2.md").read_text(), "add しただけ\n")

    def test_glob_chars_in_name_are_not_deleted_via_other_file(self):
        # HEAD の判定も literal に読む（x[1].md が x1.md の版で HEAD にあると判定されない）
        self.write("x1.md")
        self.commit_all()
        p = self.write("x[1].md", "追跡外\n")
        git(self.repo, "add", str(p.relative_to(self.repo)))
        res = run(self.repo, "retire", "--archive-dir", str(self.archive), str(p))
        self.assertEqual(lines(res.stdout, "deleted"), [])
        self.assertTrue((self.archive / "x[1].md").exists())

    def test_archive_dir_defaults_to_slug_archive(self):
        self.exclude_data_dir()
        (self.repo / "README.md").write_text("x\n")
        self.commit_all()
        p = self.write("CP-1.md")
        res = run(self.repo, "retire", str(p))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(lines(res.stdout, "archived_to"), [str((self.archive / "CP-1.md").resolve())])

    def test_archive_dir_with_missing_parents_is_created(self):
        p = self.write("CP-1.md")
        dest_dir = self.tmp / "a" / "b" / "archive"
        res = run(self.repo, "retire", "--archive-dir", str(dest_dir), str(p))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue((dest_dir / "CP-1.md").exists())

    def test_existing_archive_entry_is_not_overwritten(self):
        self.exclude_data_dir()
        (self.repo / "README.md").write_text("x\n")
        self.commit_all()
        self.archive.mkdir(parents=True)
        (self.archive / "CP-1.md").write_text("先の退避\n")
        p = self.write("CP-1.md", "後の退避\n")
        res = run(self.repo, "retire", "--archive-dir", str(self.archive), str(p))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual((self.archive / "CP-1.md").read_text(), "先の退避\n")
        dest = Path(lines(res.stdout, "archived_to")[0])
        self.assertNotEqual(dest, self.archive / "CP-1.md")
        self.assertEqual(dest.parent, self.archive)
        self.assertEqual(dest.read_text(), "後の退避\n")

    def test_mixed_and_missing(self):
        tracked = self.write("CP-1.md")
        self.commit_all()
        untracked = self.write("CP-2.md")
        res = run(self.repo, "retire", "--archive-dir", str(self.archive),
                  str(tracked), str(self.issues / "CP-9.md"), str(untracked))
        self.assertEqual(res.returncode, 2)
        self.assertEqual(lines(res.stdout, "deleted"), [str(tracked)])
        self.assertEqual(lines(res.stdout, "archived"), [str(untracked)])
        self.assertTrue((self.archive / "CP-2.md").exists())

    def test_unknown_subcommand_exit_2(self):
        p = self.write("CP-1.md")
        res = run(self.repo, "remove", str(p))
        self.assertEqual(res.returncode, 2)
        self.assertTrue(p.exists())

    def test_no_subcommand_is_usage_error(self):
        res = run(self.repo)
        self.assertEqual(res.returncode, 2, res)
        self.assertIn("usage", res.stderr)
        self.assertEqual(res.stdout, "")


class BackupTest(IssueFilesTestCase):
    def test_untracked_is_copied_and_left_in_place(self):
        self.exclude_data_dir()
        (self.repo / "README.md").write_text("x\n")
        self.commit_all()
        p = self.write("CP-1.md", "書き換え前\n")
        res = run(self.repo, "backup", "--archive-dir", str(self.archive), str(p))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(p.read_text(), "書き換え前\n")
        dest = self.archive / "CP-1.md"
        self.assertEqual(dest.read_text(), "書き換え前\n")
        self.assertEqual(lines(res.stdout, "backed_up"), [str(p)])
        self.assertEqual(lines(res.stdout, "backed_up_to"), [str(dest)])

    def test_dirty_tracked_is_copied(self):
        p = self.write("CP-1.md", "コミットした版\n")
        self.commit_all()
        p.write_text("未コミットの追記\n")
        res = run(self.repo, "backup", "--archive-dir", str(self.archive), str(p))
        self.assertEqual(lines(res.stdout, "backed_up"), [str(p)])
        self.assertEqual((self.archive / "CP-1.md").read_text(), "未コミットの追記\n")

    def test_clean_tracked_is_not_copied(self):
        p = self.write("CP-1.md")
        self.commit_all()
        res = run(self.repo, "backup", "--archive-dir", str(self.archive), str(p))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(lines(res.stdout, "tracked"), [str(p)])
        self.assertFalse(self.archive.exists())

    def test_backup_then_retire_keeps_both(self):
        self.exclude_data_dir()
        (self.repo / "README.md").write_text("x\n")
        self.commit_all()
        p = self.write("CP-1.md", "書き換え前\n")
        run(self.repo, "backup", "--archive-dir", str(self.archive), str(p))
        p.write_text("書き換え後\n")
        res = run(self.repo, "retire", "--archive-dir", str(self.archive), str(p))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual((self.archive / "CP-1.md").read_text(), "書き換え前\n")
        moved = Path(lines(res.stdout, "archived_to")[0])
        self.assertEqual(moved.read_text(), "書き換え後\n")


if __name__ == "__main__":
    unittest.main()
