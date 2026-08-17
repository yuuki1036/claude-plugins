#!/usr/bin/env python3
"""dev-workflow の hook スクリプトの回帰テスト.

対象は「自己判定で黙るか」が仕様の中心にある 2 本:

- `push-reminder.sh` — 実際に暴発した当事者（`if: "Bash(git push *)"` が評価されず
  全 Bash 呼び出しに注入した）。**通す条件より、黙る条件の方が重要**
- `on-commit.sh` — Event Bus の `commit:created` publisher。誤発火すると
  subscriber（issue-maintain）が存在しないコミットに反応する

実行: python3 -m unittest discover -s .claude-plugin/scripts/tests
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from hook_harness import HookTestCase, TempGitRepo


class PushReminderTest(HookTestCase):
    PLUGIN = "dev-workflow"
    SCRIPT = "hooks/scripts/push-reminder.sh"

    # --- 通すべきもの ---
    def test_plain_push(self):
        self.assertFired(self.run_hook(self.bash_payload("git push")), "self-review")

    def test_push_with_remote_and_branch(self):
        self.assertFired(self.run_hook(self.bash_payload("git push origin main")))

    def test_push_with_flags(self):
        self.assertFired(self.run_hook(self.bash_payload("git push --force-with-lease origin main")))

    def test_push_via_global_option(self):
        """`git -C <dir> push` / `git -c k=v push` も push."""
        self.assertFired(self.run_hook(self.bash_payload("git -C /tmp/x push")))
        self.assertFired(self.run_hook(self.bash_payload("git -c core.pager=cat push")))

    def test_push_in_compound_command(self):
        self.assertFired(self.run_hook(self.bash_payload("git add -A && git push")))

    # --- 黙るべきもの（暴発の反対側） ---
    def test_unrelated_command_is_silent(self):
        for cmd in ("ls -la", "npm test", "git status", "git log -5", "cat README.md"):
            with self.subTest(cmd=cmd):
                self.assertSilent(self.run_hook(self.bash_payload(cmd)), cmd)

    def test_push_inside_quotes_is_silent(self):
        """コミットメッセージ中の "git push" で発火しない（実際に踏んだ形）."""
        for cmd in ('git commit -m "git push の説明"',
                    "git commit -m 'git push を追加'",
                    'echo "git push"'):
            with self.subTest(cmd=cmd):
                self.assertSilent(self.run_hook(self.bash_payload(cmd)), cmd)

    def test_word_boundary(self):
        """`push` を部分文字列に含むだけのコマンドで発火しない."""
        for cmd in ("npm run pushall", "git pushx", "./pusher.sh", "git push-all-the-things"):
            with self.subTest(cmd=cmd):
                self.assertSilent(self.run_hook(self.bash_payload(cmd)), cmd)

    def test_empty_command_is_silent(self):
        self.assertSilent(self.run_hook({"tool_name": "Bash", "tool_input": {}}))

    def test_malformed_input_is_silent(self):
        """壊れた入力でも黙って終わる（hook が例外で騒がない）."""
        self.assertSilent(self.run_hook({}))

    def test_never_blocks(self):
        """PreToolUse でも**ブロックしない**（exit 2 を返さない）."""
        for cmd in ("git push", "ls"):
            with self.subTest(cmd=cmd):
                self.assertNotEqual(self.run_hook(self.bash_payload(cmd)).returncode, 2)


class OnCommitTest(HookTestCase):
    PLUGIN = "dev-workflow"
    SCRIPT = "hooks/scripts/on-commit.sh"

    def _events(self, repo: Path) -> list[dict]:
        log = repo / ".claude" / "events.jsonl"
        if not log.is_file():
            return []
        return [json.loads(l) for l in log.read_text().splitlines() if l.strip()]

    def test_publishes_commit_created(self):
        with TempGitRepo() as repo_path:
            repo = TempGitRepo.__new__(TempGitRepo)
            repo.path = repo_path
            repo.commit("feat(x): 追加")
            self.run_hook(self.bash_payload('git commit -m "feat(x): 追加"'), cwd=repo_path)
            events = self._events(repo_path)
            self.assertEqual([e["event"] for e in events], ["commit:created"])
            self.assertEqual(events[0]["payload"]["type"], "feat")
            self.assertEqual(events[0]["payload"]["files"], 1)

    def test_type_falls_back_to_other(self):
        with TempGitRepo() as repo_path:
            repo = TempGitRepo.__new__(TempGitRepo); repo.path = repo_path
            repo.commit("メッセージだけ")
            self.run_hook(self.bash_payload("git commit -m x"), cwd=repo_path)
            self.assertEqual(self._events(repo_path)[0]["payload"]["type"], "other")

    def test_amend_and_dry_run_are_skipped(self):
        """--amend / --dry-run は新規 commit ではない（dedup の責務がここにある）."""
        with TempGitRepo() as repo_path:
            repo = TempGitRepo.__new__(TempGitRepo); repo.path = repo_path
            repo.commit("feat: x")
            for cmd in ("git commit --amend --no-edit", "git commit --dry-run", "git commit --help"):
                with self.subTest(cmd=cmd):
                    self.run_hook(self.bash_payload(cmd), cwd=repo_path)
            self.assertEqual(self._events(repo_path), [])

    def test_non_bash_tool_is_ignored(self):
        with TempGitRepo() as repo_path:
            repo = TempGitRepo.__new__(TempGitRepo); repo.path = repo_path
            repo.commit("feat: x")
            self.run_hook({"tool_name": "Edit", "tool_input": {"command": "git commit -m x"}},
                          cwd=repo_path)
            self.assertEqual(self._events(repo_path), [])

    def test_commit_word_inside_quotes_is_ignored(self):
        with TempGitRepo() as repo_path:
            repo = TempGitRepo.__new__(TempGitRepo); repo.path = repo_path
            repo.commit("feat: x")
            self.run_hook(self.bash_payload('echo "git commit を実行する"'), cwd=repo_path)
            self.assertEqual(self._events(repo_path), [])

    def test_unrelated_commands_are_ignored(self):
        with TempGitRepo() as repo_path:
            repo = TempGitRepo.__new__(TempGitRepo); repo.path = repo_path
            repo.commit("feat: x")
            for cmd in ("git status", "ls", "git rebase -i HEAD~2", "npm run commit-lint"):
                with self.subTest(cmd=cmd):
                    self.run_hook(self.bash_payload(cmd), cwd=repo_path)
            self.assertEqual(self._events(repo_path), [])

    def test_outside_git_repo_is_silent(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            res = self.run_hook(self.bash_payload("git commit -m x"), cwd=Path(d))
            self.assertSilent(res)
            self.assertNotEqual(res.returncode, 2)

    def test_post_tool_use_emits_nothing_to_context(self):
        """PostToolUse なので stdout 注入しない（無音が仕様）."""
        with TempGitRepo() as repo_path:
            repo = TempGitRepo.__new__(TempGitRepo); repo.path = repo_path
            repo.commit("feat: x")
            self.assertSilent(self.run_hook(self.bash_payload("git commit -m x"), cwd=repo_path))


if __name__ == "__main__":
    unittest.main()
