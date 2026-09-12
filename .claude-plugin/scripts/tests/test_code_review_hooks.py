#!/usr/bin/env python3
"""code-review の hook スクリプトを CLI 境界越しに叩く（`hook_harness.py`）.

`publish-guard.sh`（Stop）: `review-timing.sh start` の打点ファイルが「t0 あり・pub なし」の
ままターンが終わったら 1 回だけ鳴らす（GitHub issue #219）。**黙る条件を厚く**書く —
Stop は全ターンで走るので、暴発すると毎ターン additionalContext が注入される。
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from git_env import scrub
from hook_harness import HookTestCase, TempGitRepo


class PublishGuardTest(HookTestCase):
    PLUGIN = "code-review"
    SCRIPT = "hooks/scripts/publish-guard.sh"

    def setUp(self) -> None:
        # **TMPDIR を隔離する** — 打点ファイルは `$TMPDIR/claude-code-review-<uid>/` に置かれる
        # ので、隔離しないと開発機の実レビューの打点を読んで鳴る / 消す
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmpdir = self._tmp.name
        self._repo = TempGitRepo()
        self.repo = self._repo.__enter__()
        self.addCleanup(self._repo.__exit__, None, None, None)

    def _timing(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = scrub(TMPDIR=self.tmpdir)
        return subprocess.run(
            ["bash", str(self.plugin_root / "scripts" / "review-timing.sh"), *args],
            cwd=str(self.repo), capture_output=True, text=True, env=env, timeout=30)

    def _stop(self, raw: str | None = None):
        return self.run_hook({"hook_event_name": "Stop"} if raw is None else None,
                             cwd=self.repo, env_extra={"TMPDIR": self.tmpdir}, raw=raw)

    def _timing_files(self) -> list[Path]:
        root = Path(self.tmpdir) / ("claude-code-review-%d" % os.getuid())
        return sorted(root.glob("review-start-*")) if root.is_dir() else []

    def test_silent_when_no_review_was_started(self):
        res = self._stop()
        self.assertSilent(res)
        self.assertNotIn("Unexpected", res.stderr)

    def test_fires_once_when_start_has_no_publish(self):
        self.assertEqual(self._timing("start").returncode, 0)
        res = self._stop()
        self.assertTrue(res.fired, res)
        self.assertIn("publish", res.context or "")
        self.assertIn("WARN", res.stderr)
        # **2 回目は黙る**（`nag` 行で 1 回に抑える）
        again = self._stop()
        self.assertSilent(again, "同じ打点ファイルで 2 度鳴っている")
        files = self._timing_files()
        self.assertEqual(len(files), 1)
        self.assertIn("nag ", files[0].read_text())

    def test_silent_after_publish_was_marked(self):
        self._timing("start")
        self._timing("mark", "t2")
        self._timing("mark", "published")
        self.assertSilent(self._stop(), "pub があるのに鳴っている")

    def test_fires_even_if_t2_was_never_marked(self):
        """SKILL.md を読まずに走った回は `mark t2` も落ちる — `publish-pending`（t2 前提）では拾えない形."""
        self._timing("start")
        res = self._stop()
        self.assertTrue(res.fired, "t2 が無いと鳴らない（実測の落ち方を取りこぼす）")

    def test_a_pr_scoped_timing_file_is_also_covered(self):
        self._timing("start", "--pr", "42")
        res = self._stop()
        self.assertTrue(res.fired, res)
        self.assertIn("-pr42", res.context or "")

    def test_malformed_stdin_is_silent(self):
        self._timing("start")
        res = self._stop(raw="{not json")
        # stdin は消費するだけで判定に使わないので、壊れていても**打点の判定は変わらない**
        self.assertNotIn("Unexpected", res.stderr)

    def test_does_not_touch_the_timing_file_when_silent(self):
        self._timing("start")
        self._timing("mark", "t2")
        self._timing("mark", "published")
        before = self._timing_files()[0].read_text()
        self._stop()
        self.assertEqual(self._timing_files()[0].read_text(), before)


class ExternalIdReminderTest(HookTestCase):
    """external-id-reminder.sh（PreToolUse: git commit）.

    staged なコード内コメントに git 外 ID が残っていたら 1 回通知する。**黙る条件を厚く** —
    git commit 以外・検出 0 件・git 外では必ず黙る（PreToolUse の暴発は全 Bash 呼び出しに及ぶ）。
    """

    PLUGIN = "code-review"
    SCRIPT = "hooks/scripts/external-id-reminder.sh"

    def setUp(self) -> None:
        self._repo = TempGitRepo()
        self.repo = self._repo.__enter__()
        self.addCleanup(self._repo.__exit__, None, None, None)
        self._repo.commit("init")  # base を作る（staged diff が取れるように）

    def _stage(self, filename: str, body: str) -> None:
        (self.repo / filename).write_text(body)
        subprocess.run(["git", "add", filename], cwd=str(self.repo),
                       capture_output=True, env=scrub())

    def _commit_hook(self, command: str = "git commit -m x"):
        return self.run_hook(self.bash_payload(command), cwd=self.repo)

    def test_fires_on_staged_linear_id_in_comment(self):
        self._stage("f.ts", "// ABC-123 対応\nconst x = 1;\n")
        res = self._commit_hook()
        self.assertFired(res, "comment-polish")
        self.assertIn("1 件", res.context or "")

    def test_silent_when_no_external_id(self):
        self._stage("f.ts", "// 普通のコメント\nconst x = 1;\n")
        res = self._commit_hook()
        self.assertSilent(res)
        self.assertNotIn("Unexpected", res.stderr)

    def test_silent_when_id_in_code_not_comment(self):
        # コメントでないコード行の ID 様文字列は拾わない
        self._stage("f.ts", 'const u = "ABC-123";\n')
        res = self._commit_hook()
        self.assertSilent(res)

    def test_silent_on_non_commit_bash(self):
        self._stage("f.ts", "// ABC-123\n")
        res = self._commit_hook("git status")
        self.assertSilent(res)

    def test_silent_on_non_git_repo(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        res = self.run_hook(self.bash_payload("git commit -m x"), cwd=Path(tmp.name))
        self.assertSilent(res)

    def test_malformed_stdin_is_silent(self):
        res = self.run_hook(cwd=self.repo, raw="{not json")
        self.assertNotIn("Unexpected", res.stderr)


if __name__ == "__main__":
    unittest.main()
