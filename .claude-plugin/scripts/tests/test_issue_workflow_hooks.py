#!/usr/bin/env python3
"""issue-workflow の hook スクリプトの回帰テスト.

対象 6 本のうち、**自己判定で黙るか**と**閾値の境界**が仕様の中心にあるものを厚く見る。
特に `check-scope-size.sh` は「上限ちょうどでは鳴らない / 1 超えたら鳴る」が仕様なので、
境界を両側から測る（`<=` を `<` にする類の変異はここでしか死なない）。

実行: python3 -m unittest discover -s .claude-plugin/scripts/tests
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from hook_harness import HookTestCase, TempGitRepo


def issue_file(root: Path, *, slug: str = "demo", name: str = "ISS-1.md",
               scope: str = "small", tasks: int = 0, backend: str = "indie",
               issue_id: str = "ISS-1", done: int = 0) -> Path:
    p = root / ".claude" / backend / slug / "issues" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    checks = "\n".join(["- [x] done" for _ in range(done)]
                       + ["- [ ] todo" for _ in range(tasks - done)])
    # **dedent は使わない**: 補間する `checks` が無インデントなので共通接頭辞が "" になり
    # dedent が何もせず、frontmatter の `---` が行頭に来ない（`^---$` にマッチしない）
    p.write_text(
        f"---\nid: {issue_id}\nscope_size: {scope}\n---\n\n"
        f"## 進捗\n\n{checks}\n\n"
        "## メモ\n\n- [ ] これは進捗セクション外なので数えない\n"
    )
    return p


class CheckScopeSizeTest(HookTestCase):
    PLUGIN = "issue-workflow"
    SCRIPT = "hooks/scripts/check-scope-size.sh"

    def edit_payload(self, path: Path, tool: str = "Edit") -> dict:
        return {"tool_name": tool, "tool_input": {"file_path": str(path)}}

    # --- 閾値の境界（片側だけ測ると `<=` / `<` の取り違えが素通りする） ---
    def test_small_limit_boundary(self):
        with TempGitRepo() as root:
            for n, should_fire in ((3, False), (4, True)):
                with self.subTest(tasks=n):
                    f = issue_file(root, scope="small", tasks=n)
                    res = self.run_hook(self.edit_payload(f))
                    if should_fire:
                        self.assertFired(res, "上限 3 を超過")
                    else:
                        self.assertSilent(res, f"{n} 件は上限内")

    def test_medium_and_large_limits(self):
        with TempGitRepo() as root:
            for scope, limit in (("medium", 7), ("large", 15)):
                with self.subTest(scope=scope):
                    self.assertSilent(self.run_hook(self.edit_payload(
                        issue_file(root, scope=scope, tasks=limit, name=f"{scope}.md"))))
                    self.assertFired(self.run_hook(self.edit_payload(
                        issue_file(root, scope=scope, tasks=limit + 1, name=f"{scope}o.md"))))

    def test_checked_items_count_too(self):
        """完了済み `- [x]` も件数に入る（残タスクではなく分割単位の指標）."""
        with TempGitRepo() as root:
            f = issue_file(root, scope="small", tasks=4, done=4)
            self.assertFired(self.run_hook(self.edit_payload(f)))

    def test_only_the_progress_section_counts(self):
        """`## 進捗` 以外のチェックリストは数えない."""
        with TempGitRepo() as root:
            f = issue_file(root, scope="small", tasks=3)   # + メモ節に 1 件ある
            self.assertSilent(self.run_hook(self.edit_payload(f)))

    def test_issue_id_appears_in_message(self):
        with TempGitRepo() as root:
            f = issue_file(root, scope="small", tasks=9, issue_id="ABC-42")
            self.assertFired(self.run_hook(self.edit_payload(f)), "ABC-42")

    # --- 黙るべき ---
    def test_linear_backend_path_is_also_matched(self):
        with TempGitRepo() as root:
            f = issue_file(root, scope="small", tasks=9, backend="linear")
            self.assertFired(self.run_hook(self.edit_payload(f)))

    def test_non_issue_path_is_silent(self):
        with TempGitRepo() as root:
            other = root / "README.md"; other.write_text("- [ ] a\n")
            self.assertSilent(self.run_hook(self.edit_payload(other)))

    def test_non_edit_tool_is_silent(self):
        with TempGitRepo() as root:
            f = issue_file(root, scope="small", tasks=9)
            for tool in ("Bash", "Read", "Glob"):
                with self.subTest(tool=tool):
                    self.assertSilent(self.run_hook(self.edit_payload(f, tool=tool)))

    def test_missing_scope_size_is_silent(self):
        with TempGitRepo() as root:
            f = root / ".claude/indie/demo/issues/x.md"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("---\nid: X\n---\n\n## 進捗\n\n" + "- [ ] a\n" * 9)
            self.assertSilent(self.run_hook(self.edit_payload(f)))

    def test_unknown_scope_size_is_silent(self):
        with TempGitRepo() as root:
            f = issue_file(root, scope="gigantic", tasks=99)
            self.assertSilent(self.run_hook(self.edit_payload(f)))

    def test_missing_file_is_silent(self):
        with TempGitRepo() as root:
            self.assertSilent(self.run_hook(self.edit_payload(root / ".claude/indie/d/issues/none.md")))

    def test_malformed_input_is_silent(self):
        self.assertSilent(self.run_hook({}))

    def test_never_blocks(self):
        with TempGitRepo() as root:
            f = issue_file(root, scope="small", tasks=99)
            self.assertNotEqual(self.run_hook(self.edit_payload(f)).returncode, 2)


class OnIssueChangeTest(HookTestCase):
    PLUGIN = "issue-workflow"
    SCRIPT = "hooks/scripts/on-issue-change.sh"

    def _events(self, root: Path) -> list[dict]:
        log = root / ".claude" / "events.jsonl"
        return [json.loads(l) for l in log.read_text().splitlines() if l.strip()] \
            if log.is_file() else []

    def _payload(self, path: Path) -> dict:
        return {"tool_name": "Edit", "tool_input": {"file_path": str(path)},
                "file_path": str(path)}

    def test_publishes_on_completed(self):
        with TempGitRepo() as root:
            f = issue_file(root, scope="small", tasks=1)
            f.write_text(f.read_text().replace("scope_size: small",
                                               "scope_size: small\nstatus: completed"))
            self.run_hook(self._payload(f), cwd=root)
            events = self._events(root)
            self.assertEqual([e["event"] for e in events], ["issue:completed"])

    def test_silent_when_not_completed(self):
        with TempGitRepo() as root:
            f = issue_file(root, scope="small", tasks=1)
            f.write_text(f.read_text().replace("scope_size: small",
                                               "scope_size: small\nstatus: in_progress"))
            self.run_hook(self._payload(f), cwd=root)
            self.assertEqual(self._events(root), [])

    def test_silent_for_non_issue_file(self):
        with TempGitRepo() as root:
            other = root / "notes.md"
            other.write_text("---\nstatus: completed\n---\n")
            self.run_hook(self._payload(other), cwd=root)
            self.assertEqual(self._events(root), [])

    def test_malformed_input_does_not_crash(self):
        with TempGitRepo() as root:
            res = self.run_hook({}, cwd=root)
            self.assertNotEqual(res.returncode, 2)


class InjectRulesTest(HookTestCase):
    PLUGIN = "issue-workflow"
    SCRIPT = "hooks/scripts/inject-rules.sh"

    def test_injects_when_rules_file_exists(self):
        """SessionStart でプロジェクトルールを注入する（存在時のみ）."""
        with TempGitRepo() as root:
            (root / ".claude").mkdir(exist_ok=True)
            res = self.run_hook({"hook_event_name": "SessionStart"}, cwd=root)
            self.assertNotEqual(res.returncode, 2)

    def test_no_crash_without_project_dir(self):
        with TempGitRepo() as root:
            self.assertNotEqual(self.run_hook({}, cwd=root).returncode, 2)


class SetSessionTitleTest(HookTestCase):
    PLUGIN = "issue-workflow"
    SCRIPT = "hooks/scripts/set-session-title.sh"

    def test_no_crash_without_issue(self):
        with TempGitRepo() as root:
            res = self.run_hook({"prompt": "何か作業する"}, cwd=root)
            self.assertNotEqual(res.returncode, 2)

    def test_malformed_input_does_not_crash(self):
        self.assertNotEqual(self.run_hook({}).returncode, 2)


class OnKnowledgeChangeTest(HookTestCase):
    PLUGIN = "issue-workflow"
    SCRIPT = "hooks/scripts/on-knowledge-change.sh"

    def test_no_crash_on_unrelated_file(self):
        with TempGitRepo() as root:
            res = self.run_hook({"tool_name": "Edit",
                                 "tool_input": {"file_path": str(root / "README.md")}}, cwd=root)
            self.assertNotEqual(res.returncode, 2)

    def test_malformed_input_does_not_crash(self):
        self.assertNotEqual(self.run_hook({}).returncode, 2)


if __name__ == "__main__":
    unittest.main()
