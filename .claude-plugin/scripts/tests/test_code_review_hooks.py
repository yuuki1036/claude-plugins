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

    def _timing(self, *args: str, cwd: Path | None = None,
                sid: str | None = None) -> subprocess.CompletedProcess[str]:
        env = scrub(TMPDIR=self.tmpdir)
        # 実行中のセッションの id を継承させない（識別子になる / #247）
        env.pop("CLAUDE_CODE_SESSION_ID", None)
        if sid is not None:
            env["CLAUDE_CODE_SESSION_ID"] = sid
        return subprocess.run(
            ["bash", str(self.plugin_root / "scripts" / "review-timing.sh"), *args],
            cwd=str(cwd or self.repo), capture_output=True, text=True, env=env, timeout=30)

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

    # --- PreToolUse 経路（#232）: t2 後・publish 前に次のフェーズへ進むとその場で鳴る ---

    def _pre(self, tool: str, cwd: Path | None = None, session_id: str | None = None):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {}}
        if session_id is not None:
            payload["session_id"] = session_id
        return self.run_hook(payload, cwd=cwd or self.repo, env_extra={"TMPDIR": self.tmpdir})

    # --- セッション単位の識別子（#247）: cd 先が混ざっても 1 レビュー = 1 ファイル ---

    SID = "aaaaaaaa-1111-2222-3333-444444444444"

    def test_pre_tool_silent_after_a_split_run_was_published(self):
        """start / publish は main、t2 は worktree で打った回（09-18 の型）。publish 済みなら鳴らない.

        toplevel 由来の識別子では worktree 側に「t2 あり・pub なし」のファイルが残り、publish の
        8 分後に誤った nag が出ていた。hook は env ではなく stdin の `session_id` で同じ識別子を作る。
        """
        wt = self._repo.worktree("wt")
        self._timing("start", sid=self.SID)
        self._timing("mark", "t2", cwd=wt, sid=self.SID)
        self._timing("mark", "published", sid=self.SID)
        # **囮**: id 無し（toplevel 由来）の wt 側に「t2 あり・pub なし」を置く。hook が stdin の
        # id を拾えないとこちらを見て鳴るので、「黙る」が id を拾えた結果だと言える
        self._timing("start", cwd=wt)
        self._timing("mark", "t2", cwd=wt)
        res = self._pre("Edit", cwd=wt, session_id=self.SID)
        self.assertSilent(res, "publish 済みなのに鳴っている（id を拾えず toplevel 側を見た）")
        self.assertNotIn("Unexpected", res.stderr)

    def test_pre_tool_still_fires_for_this_session_across_worktrees(self):
        """識別子を変えても本来の脱落（t2 あり・pub なし）は cd 先からでも拾う."""
        wt = self._repo.worktree("wt")
        self._timing("start", sid=self.SID)
        self._timing("mark", "t2", sid=self.SID)
        self.assertTrue(self._pre("Edit", cwd=wt, session_id=self.SID).fired)

    def test_session_id_is_read_from_stdin_without_jq(self):
        """jq の無い環境でも stdin の `session_id` を拾う.

        **鳴る側で測る** — 拾えなかった回は cwd の toplevel 由来の識別子に落ちてファイルが
        見つからず黙るので、「黙る」を期待にすると拾えても拾えなくても緑になる。
        """
        wt = self._repo.worktree("wt")
        self._timing("start", sid=self.SID)
        self._timing("mark", "t2", sid=self.SID)
        path = self.path_with_only("cksum", "id", "mkdir", "chmod", "date", "awk")
        res = self.run_hook({"hook_event_name": "PreToolUse", "tool_name": "Edit",
                             "tool_input": {}, "session_id": self.SID},
                            cwd=wt, env_extra={"TMPDIR": self.tmpdir, "PATH": path})
        self.assertTrue(res.fired, "jq が無いと session_id を拾えていない")
        self.assertNotIn("Unexpected", res.stderr)

    def test_stop_is_silent_after_an_aborted_review_was_discarded(self):
        """中止した review（start の後に publish せず ExitWorktree）は discard で捨てれば鳴らない.

        識別子がセッション単位になったので、worktree を抜けた後の Stop からも中止した回の
        打点ファイルが見える。捨てないと中止したレビューを publish させる誘導になる。
        """
        wt = self._repo.worktree("wt")
        self._timing("start", "--pr", "5", cwd=wt, sid=self.SID)
        stop = {"hook_event_name": "Stop", "session_id": self.SID}
        self._timing("discard", "--pr", "5", cwd=wt, sid=self.SID)
        res = self.run_hook(stop, cwd=self.repo, env_extra={"TMPDIR": self.tmpdir})
        self.assertSilent(res, "捨てた打点ファイルで鳴っている")
        self.assertEqual(self._timing_files(), [])

    def test_the_stop_message_offers_discard_for_an_aborted_review(self):
        """鳴ったときの文言に「中止したなら publish せず捨てる」経路がある."""
        self._timing("start", "--pr", "5", sid=self.SID)
        res = self.run_hook({"hook_event_name": "Stop", "session_id": self.SID},
                            cwd=self.repo, env_extra={"TMPDIR": self.tmpdir})
        self.assertTrue(res.fired)
        self.assertIn("discard", res.context or "")

    def test_stop_only_looks_at_this_sessions_files(self):
        """並行セッションの打点ファイルで鳴らない（識別子がセッション単位になったので分けられる）."""
        self._timing("start", sid="bbbbbbbb-1111-2222-3333-444444444444")
        res = self.run_hook({"hook_event_name": "Stop", "session_id": self.SID},
                            cwd=self.repo, env_extra={"TMPDIR": self.tmpdir})
        self.assertSilent(res, "別セッションの打点ファイルで鳴っている")
        mine = self.run_hook({"hook_event_name": "Stop",
                              "session_id": "bbbbbbbb-1111-2222-3333-444444444444"},
                             cwd=self.repo, env_extra={"TMPDIR": self.tmpdir})
        self.assertTrue(mine.fired, "自分のセッションの打点ファイルを拾えていない")

    def test_pre_tool_fires_once_after_t2_without_publish(self):
        self._timing("start")
        self._timing("mark", "t2")
        res = self._pre("Skill")
        self.assertFired(res, "publish")
        self.assertIn("Skill", res.context or "")
        self.assertIn("定型", res.context or "")
        self.assertIn("PreToolUse", res.stdout)  # Stop として注入すると PreToolUse では捨てられる
        self.assertSilent(self._pre("Edit"), "同じ打点ファイルで 2 度鳴っている")
        # Stop とも nag を共有する（ターン終端で重ねて鳴らさない）
        self.assertSilent(self._stop(), "PreToolUse で鳴らした後に Stop でも鳴っている")

    def test_pre_tool_fires_for_each_phase_advancing_tool(self):
        for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Skill", "Agent", "Task"):
            with self.subTest(tool=tool):
                for f in self._timing_files():
                    f.unlink()
                self._timing("start")
                self._timing("mark", "t2")
                self.assertTrue(self._pre(tool).fired, tool)

    def test_pre_tool_silent_on_bash(self):
        # publish 自体が Bash なので、Bash で鳴らすと publish を止める誘導になる
        self._timing("start")
        self._timing("mark", "t2")
        self.assertSilent(self._pre("Bash"))
        self.assertNotIn("nag ", self._timing_files()[0].read_text())

    def test_pre_tool_silent_before_t2(self):
        # レポート前の Agent 起動（reviewer fan-out）では鳴らない
        self._timing("start")
        res = self._pre("Agent")
        self.assertSilent(res)
        self.assertNotIn("Unexpected", res.stderr)
        # 黙った回に nag を立てると、後の本当の脱落で鳴らなくなる
        self.assertNotIn("nag ", self._timing_files()[0].read_text())

    def test_pre_tool_silent_after_publish(self):
        # self-review Step 7 の comment-polish（Skill）は publish 後
        self._timing("start")
        self._timing("mark", "t2")
        self._timing("mark", "published")
        self.assertSilent(self._pre("Skill"))

    def test_pre_tool_silent_without_timing_file(self):
        res = self._pre("Edit")
        self.assertSilent(res)
        self.assertNotIn("Unexpected", res.stderr)

    def test_pre_tool_ignores_pr_scoped_review(self):
        # review は t2 と publish の間に締めフロー（writing-polish を Skill で呼ぶ）がある
        self._timing("start", "--pr", "42")
        self._timing("mark", "t2", "--pr", "42")
        self.assertSilent(self._pre("Skill"))


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
