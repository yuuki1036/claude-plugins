#!/usr/bin/env python3
"""issue-workflow の hook スクリプトの回帰テスト.

対象 6 本のうち、**自己判定で黙るか**と**閾値の境界**が仕様の中心にあるものを厚く見る。
特に `check-scope-size.sh` は「上限ちょうどでは鳴らない / 1 超えたら鳴る」が仕様なので、
境界を両側から測る（`<=` を `<` にする類の変異はここでしか死なない）。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


def design_issue_file(root: Path, *, slug: str = "demo", name: str = "ISS-2.md",
                      scope: str = "small", tasks: int = 0, backend: str = "indie",
                      issue_id: str = "ISS-2") -> Path:
    """issue-design の 9 セクションテンプレ形式（チェックリストは `## 完了条件`）.

    テンプレ系統が 2 つあり、`## 進捗` だけを数えると**この形式の Issue で
    スコープ警告が無言で無効化**される（GitHub issue #179）。
    """
    p = root / ".claude" / backend / slug / "issues" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    checks = "\n".join("- [ ] todo" for _ in range(tasks))
    p.write_text(
        f"---\nid: {issue_id}\nscope_size: {scope}\n---\n\n"
        "## Why\n\n背景\n\n"
        f"## 完了条件\n\n{checks}\n\n"
        "## スコープ外\n\n- [ ] これは別節なので数えない\n"
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

    # --- テンプレ系統が 2 つある（GitHub issue #179）---
    def test_the_nine_section_template_is_counted(self):
        """`## 完了条件` のチェックリストも数える.

        `## 進捗` だけを見ていたため、`/issue-design` でリライトした Issue では
        COUNT=0 になり**警告が無言で無効化**されていた（issue-create/SKILL.md は
        「スコープサイズは全 type で必須」と宣言していた）。
        """
        with TempGitRepo() as root:
            f = design_issue_file(root, scope="small", tasks=4)   # 上限 3 を超過
            self.assertFired(self.run_hook(self.edit_payload(f)), "scope-size")

    def test_the_nine_section_template_respects_the_limit(self):
        """上限内なら鳴らない（新しい節を数え始めて誤爆させない）."""
        with TempGitRepo() as root:
            f = design_issue_file(root, scope="small", tasks=3)
            self.assertSilent(self.run_hook(self.edit_payload(f)))

    def test_sections_are_not_summed_when_both_exist(self):
        """両方の節があるとき足し合わせない（移行途中のファイルを誤って警告しない）."""
        with TempGitRepo() as root:
            f = issue_file(root, scope="small", tasks=3)
            f.write_text(f.read_text() + "\n## 完了条件\n\n- [ ] a\n- [ ] b\n")
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

    def test_events_never_land_in_the_ambient_project_dir(self):
        """publish 先は**テストが見るディレクトリ**（環境変数の継承で外へ出さない / #139 の実測）."""
        with TempGitRepo() as root:
            f = issue_file(root, scope="small", tasks=1)
            f.write_text(f.read_text().replace("scope_size: small",
                                               "scope_size: small\nstatus: completed"))
            decoy = root / "decoy"
            decoy.mkdir()
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(decoy)}):
                self.run_hook(self._payload(f), cwd=root)
            self.assertEqual([e["event"] for e in self._events(root)], ["issue:completed"])
            self.assertFalse((decoy / ".claude" / "events.jsonl").exists(),
                             "環境変数が指す先へ publish している")

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

    def test_a_payload_without_file_path_reaches_the_guard(self):
        """キー欠損で ERR trap に落ちない（GitHub issue #179）.

        `|| true` が無いと grep の exit 1 が safe-hook の ERR trap を踏み、**自己判定
        ガードが永久に unreachable** になる。正常系が silent exit 0 なので rc だけでは
        「ガードで黙った」と「途中で死んだ」を区別できない — stderr で見分ける。
        """
        with TempGitRepo() as root:
            res = self.run_hook({"tool_name": "Edit", "tool_input": {}}, cwd=root)
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("Unexpected", res.stderr, "ERR trap で落ちている")
            self.assertIn("not an issue file", res.stderr, "自己判定ガードに到達していない")


# knowledge を出さない回の案内。期待値はテスト側で独立に持つ（実装の定数を import すると、
# 両方を同じに変えたときに検知できない）。見出しは共通で、理由は経路ごとに違う
# 字数を数えられない回（bash の emit_without_budget）
UNCOUNTED_NOTE = ("\n---\n## Knowledge\n\nknowledge の index は注入していない（字数を数えられず、"
                  "注入の上限に収められない）。`/knowledge` で一覧を見る。\n")
# index を読めなかった回（inject-budget.py の例外の経路）
UNREAD_NOTE = ("\n---\n## Knowledge\n\nknowledge の index は注入していない（index の読み込みか"
               "注入の処理に失敗した）。`/knowledge` で一覧を見る。\n")


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

    def test_plugin_root_placeholder_becomes_a_runnable_path(self):
        """営業日スクリプトの `{PLUGIN_ROOT}` は実在するパスに置き換わる（GitHub issue #255）."""
        with TempGitRepo() as root:
            (root / ".claude" / "indie" / "demo").mkdir(parents=True)
            res = self.run_hook({"hook_event_name": "SessionStart"}, cwd=root)
            self.assertNotIn("{PLUGIN_ROOT}", res.stdout)
            script = self.plugin_root / "scripts" / "business-days.py"
            self.assertIn(f"python3 {script} count", res.stdout)
            self.assertTrue(script.is_file())

    def test_worktree_without_a_data_dir_reads_the_main_checkout(self):
        """gitignore された Issue データは worktree に無いので、メインのチェックアウトを見る（GitHub issue #280）."""
        repo = TempGitRepo()
        with repo as root:
            wt = repo.worktree("feat/TEAM-9-x")
            index = root / ".claude" / "linear" / "team" / "knowledge" / "index.md"
            index.parent.mkdir(parents=True)
            index.write_text("| topic | tags |\n")
            res = self.run_hook({"hook_event_name": "SessionStart"}, cwd=wt)
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("Unexpected", res.stderr)
            data_dir = root.resolve() / ".claude" / "linear"
            self.assertIn(f"backend: linear（DATA_DIR={data_dir}）", res.stdout)
            self.assertIn("## Knowledge（team）", res.stdout)

    def test_worktree_with_its_own_data_dir_ignores_the_main_checkout(self):
        """worktree に追跡済みのデータ dir があればそれを使い、メイン側とは衝突させない."""
        repo = TempGitRepo()
        with repo as root:
            (root / ".claude" / "indie" / "demo").mkdir(parents=True)
            repo.commit("init", filename=".claude/indie/demo/project.md")
            wt = repo.worktree("feat/DEMO-1-x")
            (root / ".claude" / "linear" / "team").mkdir(parents=True)
            res = self.run_hook({"hook_event_name": "SessionStart"}, cwd=wt)
            self.assertIn("backend: local（DATA_DIR=.claude/indie）", res.stdout)
            self.assertNotIn("backend 衝突", res.stdout)

    def test_fallback_is_only_for_linked_worktrees(self):
        """メインのチェックアウトの中では従来どおり cwd 基準で、サブディレクトリからルートを探さない."""
        with TempGitRepo() as root:
            (root / ".claude" / "linear" / "team").mkdir(parents=True)
            sub = root / "sub"
            sub.mkdir()
            res = self.run_hook({"hook_event_name": "SessionStart"}, cwd=sub)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout, "")

    def test_main_checkout_does_not_look_into_worktrees(self):
        """メインのチェックアウトにデータ dir が無ければ、worktree 側にあっても黙る."""
        repo = TempGitRepo()
        with repo as root:
            wt = repo.worktree("feat/TEAM-9-x")
            (wt / ".claude" / "linear" / "team").mkdir(parents=True)
            res = self.run_hook({"hook_event_name": "SessionStart"}, cwd=root)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout, "")
            self.assertNotIn("Unexpected", res.stderr)

    # --- 注入の上限（GitHub issue #424） ---
    # Claude Code は hook の stdout を 10,000 字で打ち切り、先頭 2,000 字のプレビューしか渡さない

    CC_LIMIT = 10_000

    def rules_tail(self) -> str:
        lines = (self.plugin_root / "rules" / "project-rules.md").read_text(encoding="utf-8").splitlines()
        return [line for line in lines if line.strip()][-1]

    def write_index(self, root: Path, rows: int, slug: str = "demo") -> Path:
        index = root / ".claude" / "indie" / slug / "knowledge" / "index.md"
        index.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(f"| concepts/{slug}-{i:03d}.md | 認証, セッション | - | 外部の認証を既存のセッションに束ねる知見 {i} |\n"
                       for i in range(rows))
        index.write_text("# Knowledge Index\n\n| ファイル | tags | status | 概要 |\n|---|---|---|---|\n" + body,
                         encoding="utf-8")
        return index

    def write_stale_issue(self, root: Path) -> None:
        p = root / ".claude" / "indie" / "demo" / "issues" / "DEMO-7.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("---\nid: DEMO-7\nstatus: in-progress\nlast_active: 2020-01-01\n---\n", encoding="utf-8")

    def test_a_large_index_is_cut_to_fit_and_the_rules_reach_their_end(self):
        """大きな index でも全体が上限に収まり、規約は末尾まで入り、省いた件数が出る."""
        with TempGitRepo() as root:
            self.write_index(root, rows=300)
            self.write_stale_issue(root)
            res = self.run_hook({"hook_event_name": "SessionStart"}, cwd=root)
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("Unexpected", res.stderr)
            self.assertLessEqual(len(res.stdout), self.CC_LIMIT)
            self.assertIn(self.rules_tail(), res.stdout)
            # 放置 Issue は knowledge より先に予算を取る
            self.assertIn("- **DEMO-7**:", res.stdout)
            shown = res.stdout.count("| concepts/demo-")
            self.assertGreater(shown, 0)
            self.assertIn(f"（index の残り {300 - shown} 件は注入の上限で省いた。`/knowledge` で一覧を見る）",
                          res.stdout)
            # 字数で数えている（バイト数で数えると日本語の index は半分も入らない）
            self.assertGreater(len(res.stdout), 9000)

    def test_a_small_index_is_injected_whole_without_a_note(self):
        """上限に収まる index は一字も省かず、案内も出さない（黙る側）."""
        with TempGitRepo() as root:
            index = self.write_index(root, rows=5)
            res = self.run_hook({"hook_event_name": "SessionStart"}, cwd=root)
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("Unexpected", res.stderr)
            self.assertIn("## Knowledge（demo）", res.stdout)
            self.assertIn(index.read_text(encoding="utf-8"), res.stdout)
            self.assertNotIn("注入の上限", res.stdout)

    def test_no_index_means_no_knowledge_section(self):
        with TempGitRepo() as root:
            (root / ".claude" / "indie" / "demo").mkdir(parents=True)
            res = self.run_hook({"hook_event_name": "SessionStart"}, cwd=root)
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("Unexpected", res.stderr)
            self.assertIn(self.rules_tail(), res.stdout)
            # 規約の本文にも「## Knowledge の活用」があるので、注入の見出しの形で見る
            self.assertNotIn("## Knowledge（", res.stdout)
            self.assertNotIn("注入の上限", res.stdout)

    def test_slugs_that_do_not_fit_are_listed_by_name(self):
        """先の slug で予算を使い切ったら、後の slug は名前と `/knowledge` の案内だけを出す."""
        with TempGitRepo() as root:
            self.write_index(root, rows=300, slug="aaa")
            self.write_index(root, rows=3, slug="bbb")
            res = self.run_hook({"hook_event_name": "SessionStart"}, cwd=root)
            self.assertLessEqual(len(res.stdout), self.CC_LIMIT)
            self.assertIn("## Knowledge（省略）\n\nbbb（3 件）の index は注入の上限で省いた。", res.stdout)
            self.assertNotIn("| concepts/bbb-", res.stdout)

    def test_without_python3_the_rules_still_arrive_and_the_index_is_skipped(self):
        """字数を数えられない環境では index を出さず、規約と放置 Issue は出す."""
        with TempGitRepo() as root:
            self.write_index(root, rows=300)
            self.write_stale_issue(root)
            path = self.path_with_only("date", "find")
            res = self.run_hook({"hook_event_name": "SessionStart"}, cwd=root, env_extra={"PATH": path})
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("Unexpected", res.stderr)
            self.assertIn(self.rules_tail(), res.stdout)
            self.assertIn(UNCOUNTED_NOTE, res.stdout)
            self.assertNotIn("| concepts/demo-", res.stdout)
            self.assertIn("- **DEMO-7**:", res.stdout)

    def test_a_python3_that_fails_to_start_still_lets_the_rules_through(self):
        """PATH の python3 が起動に失敗しても（CLT の無い macOS のスタブ等）、規約と放置 Issue は出す.

        パイプの失敗が pipefail で ERR trap に落ちると、規約ごと 0 バイトになる（self-review で実測）。
        """
        with TempGitRepo() as root:
            self.write_index(root, rows=300)
            self.write_stale_issue(root)
            # スタブは path_with_only の dir（本物への symlink が並ぶ）に書かない。同名の symlink が
            # あると write_text がたどって本物の python3 を上書きする（レビュー中に一度起きた）
            stub_dir = tempfile.TemporaryDirectory()
            self.addCleanup(stub_dir.cleanup)
            stub = Path(stub_dir.name) / "python3"
            stub.write_text("#!/bin/sh\nexit 1\n")
            stub.chmod(0o755)
            path = f"{stub_dir.name}:{self.path_with_only('date', 'find')}"
            res = self.run_hook({"hook_event_name": "SessionStart"}, cwd=root,
                                env_extra={"PATH": path})
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("Unexpected", res.stderr, "ERR trap で落ちている")
            self.assertIn(self.rules_tail(), res.stdout)
            self.assertIn(UNCOUNTED_NOTE, res.stdout)
            self.assertIn("- **DEMO-7**:", res.stdout)
            self.assertNotIn("| concepts/demo-", res.stdout)


    def test_rules_that_fail_to_read_are_not_emitted_twice(self):
        """規約を出す側だけが失敗しても、縮退の経路で規約（と backend の行）を二重に出さない."""
        with TempGitRepo() as root:
            self.write_index(root, rows=3)
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            plugin = Path(tmp.name) / "issue-workflow"
            shutil.copytree(self.plugin_root, plugin, ignore=shutil.ignore_patterns("evals"))
            rules = plugin / "rules" / "project-rules.md"
            rules.chmod(0)
            self.addCleanup(rules.chmod, 0o644)
            if os.access(rules, os.R_OK):  # root は mode 0 でも読めるので、読めない状態を再現できない
                self.skipTest("規約を読めない状態を作れない（root で走っている）")
            res = self.run_hook({"hook_event_name": "SessionStart"}, cwd=root,
                                env_extra={"CLAUDE_PLUGIN_ROOT": str(plugin)})
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("Unexpected", res.stderr)
            self.assertEqual(res.stdout.count("issue-workflow backend:"), 1)
            self.assertIn("## Knowledge（demo）", res.stdout)

class InjectBudgetTest(unittest.TestCase):
    """inject-budget.py の境界を直接見る（hook 越しでは規約の字数に左右されて境界を測れない）."""

    SCRIPT = Path(__file__).resolve().parents[3] / "issue-workflow" / "hooks" / "scripts" / "inject-budget.py"
    HEAD = "\n---\n## Knowledge（demo）\n\n以下の知見が蓄積されている。実装時に関連する knowledge があれば Read して活用すること。\n\n"

    def run_budget(self, prefix: str, limit: int, *pairs: str, stale: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(["python3", str(self.SCRIPT), str(limit), *pairs], input=prefix,
                      capture_output=True, text=True, encoding="utf-8",
                      env={**os.environ, "IW_STALE": stale}, timeout=30)

    def index(self, body: str) -> str:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / "index.md"
        p.write_text(body, encoding="utf-8")
        return str(p)

    def test_exactly_at_the_limit_is_kept_whole(self):
        body = "| a | b |\n|---|---|\n| 知見 | x |\n"
        prefix = "規約" * 10
        limit = len(prefix) + len(self.HEAD) + len(body)
        res = self.run_budget(prefix, limit, "demo", self.index(body))
        self.assertEqual(res.stdout, prefix + self.HEAD + body)

    def test_one_over_the_limit_is_cut(self):
        body = "| a | b |\n|---|---|\n" + "".join(f"| 知見 {i} | x |\n" for i in range(20))
        prefix = "規約" * 10
        limit = len(prefix) + len(self.HEAD) + len(body) - 1
        res = self.run_budget(prefix, limit, "demo", self.index(body))
        self.assertLessEqual(len(res.stdout), limit)
        self.assertTrue(res.stdout.startswith(prefix))
        self.assertIn("注入の上限で省いた", res.stdout)

    def test_the_header_row_and_separator_are_not_counted_as_entries(self):
        """省いた件数は表の行だけを数える。見出し行・区切り行・表の外の行は数えない."""
        rows = 30
        body = "# Knowledge Index\n\n| a | b |\n|---|---|\n" + "".join(f"| 知見 {i} | x |\n" for i in range(rows))
        res = self.run_budget("", len(self.HEAD) + len(body) // 2, "demo", self.index(body))
        shown = res.stdout.count("| 知見 ")
        self.assertGreater(shown, 0)
        self.assertIn(f"（index の残り {rows - shown} 件は注入の上限で省いた。", res.stdout)

    def test_a_budget_smaller_than_the_reserve_still_says_knowledge_was_omitted(self):
        """省略の案内すら入らない予算でも、案内 1 行は上限を超えて出す（knowledge を黙って消さない）."""
        res = self.run_budget("規約", 3, "demo", self.index("| a |\n|---|\n| x |\n"))
        self.assertEqual(res.stdout, "規約\n---\n## Knowledge（省略）\n\ndemo（1 件）の index は注入の上限で省いた。"
                                     "`/knowledge` で一覧を見る。\n")

    def test_a_prefix_over_the_limit_is_never_cut(self):
        """規約は上限を超えても削らない（knowledge は案内 1 行だけにし、放置 Issue は落とす）."""
        prefix = "規約の本文" * 100
        res = self.run_budget(prefix, 10, "demo", self.index("| a |\n|---|\n| x |\n"), stale="- **X-1**: 9日間未更新")
        self.assertEqual(res.stdout, prefix + "\n---\n## Knowledge（省略）\n\ndemo（1 件）の index は注入の上限で省いた。"
                                              "`/knowledge` で一覧を見る。\n")

    def test_an_unreadable_index_falls_back_to_the_rules_and_stale_issues(self):
        res = self.run_budget("規約", 9500, "demo", "/nonexistent/index.md", stale="- **X-1**: 9日間未更新")
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout, "規約" + UNREAD_NOTE + "\n---\n## 放置 Issue 検知\n\n- **X-1**: 9日間未更新\n")
        self.assertIn("inject-budget failed", res.stderr)

    def test_the_fallback_after_an_error_still_keeps_the_limit(self):
        """例外の経路でも放置 Issue は案内の残りに収める（予算を無制限にしない）."""
        stale = "\n".join(f"- **X-{i}**: 9日間未更新" for i in range(50))
        res = self.run_budget("規約", 150, "demo", "/nonexistent/index.md", stale=stale)
        self.assertLessEqual(len(res.stdout), 150)
        self.assertTrue(res.stdout.startswith("規約" + UNREAD_NOTE))
        self.assertIn("ほか", res.stdout)

    def test_the_fallback_after_an_error_says_knowledge_was_omitted_even_over_the_limit(self):
        """例外の経路でも、案内すら入らない予算なら上限を超えて案内だけは出す（通常の経路と揃える）."""
        res = self.run_budget("規約", 3, "demo", "/nonexistent/index.md", stale="- **X-1**: 9日間未更新")
        self.assertEqual(res.stdout, "規約" + UNREAD_NOTE)

    STALE_HEAD = "\n---\n## 放置 Issue 検知\n\n"

    def test_stale_issues_exactly_at_the_limit_are_kept_whole(self):
        lines = [f"- **X-{i}**: 9日間未更新" for i in range(5)]
        full = self.STALE_HEAD + "".join(f"{line}\n" for line in lines)
        res = self.run_budget("", len(full), stale="\n".join(lines))
        self.assertEqual(res.stdout, full)

    def test_stale_issues_one_over_the_limit_are_summarized(self):
        lines = [f"- **X-{i}**: 9日間未更新" for i in range(5)]
        full = self.STALE_HEAD + "".join(f"{line}\n" for line in lines)
        res = self.run_budget("", len(full) - 1, stale="\n".join(lines))
        self.assertLessEqual(len(res.stdout), len(full) - 1)
        self.assertRegex(res.stdout, r"- ほか \d+ 件（`/maintain` で確かめる）\n$")

    def test_a_partial_index_line_that_fits_exactly_is_kept(self):
        """行ごとの切り詰めで、案内まで含めてちょうど収まる行は残し、1 字足りなければ落とす."""
        rows = [f"| 知見 {i} | x |\n" for i in range(30)]
        body = "| a | b |\n|---|---|\n" + "".join(rows)
        reserve = len("\n---\n## Knowledge（省略）\n\ndemo（30 件）の index は注入の上限で省いた。"
                      "`/knowledge` で一覧を見る。\n")
        kept = "| a | b |\n|---|---|\n" + "".join(rows[:4])
        note = "\n（index の残り 26 件は注入の上限で省いた。`/knowledge` で一覧を見る）\n"
        limit = reserve + len(self.HEAD) + len(kept) + len(note)
        res = self.run_budget("", limit, "demo", self.index(body))
        self.assertEqual(res.stdout, self.HEAD + kept + note)
        res = self.run_budget("", limit - 1, "demo", self.index(body))
        self.assertEqual(res.stdout.count("| 知見 "), 3)

    def test_stale_issues_that_do_not_fit_are_summarized(self):
        stale = "\n".join(f"- **X-{i}**: 9日間未更新" for i in range(50))
        res = self.run_budget("", 120, stale=stale)
        self.assertLessEqual(len(res.stdout), 120)
        self.assertRegex(res.stdout, r"- ほか \d+ 件（`/maintain` で確かめる）\n$")


class SetSessionTitleTest(HookTestCase):
    PLUGIN = "issue-workflow"
    SCRIPT = "hooks/scripts/set-session-title.sh"

    def test_no_crash_without_issue(self):
        with TempGitRepo() as root:
            res = self.run_hook({"prompt": "何か作業する"}, cwd=root)
            self.assertNotEqual(res.returncode, 2)

    def test_malformed_input_does_not_crash(self):
        self.assertNotEqual(self.run_hook({}).returncode, 2)

    def test_an_issue_without_a_title_reaches_the_guard(self):
        """`title:` を欠く issue ファイルで ERR trap に落ちない（GitHub issue #179）."""
        repo = TempGitRepo()
        with repo as root:
            repo.branch("ISS-1-work")
            p = root / ".claude" / "indie" / "demo" / "issues" / "ISS-1.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("---\nid: ISS-1\n---\n\n本文だけで title 行が無い\n")
            res = self.run_hook({"prompt": "作業する"}, cwd=root)
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("Unexpected", res.stderr, "ERR trap で落ちている")
            self.assertIn("title empty", res.stderr, "Validation ガードに到達していない")

    def test_reads_the_issue_from_the_main_checkout_inside_a_worktree(self):
        """worktree に Issue ファイルが無くても、メインのチェックアウトのものでタイトルを付ける（GitHub issue #280）."""
        repo = TempGitRepo()
        with repo as root:
            wt = repo.worktree("feat/TEAM-9-x")
            p = root / ".claude" / "linear" / "team" / "issues" / "TEAM-9.md"
            p.parent.mkdir(parents=True)
            p.write_text("---\nlinear: TEAM-9\ntitle: 帯を出す\n---\n")
            res = self.run_hook({"prompt": "作業する"}, cwd=wt)
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("Unexpected", res.stderr)
            self.assertEqual(json.loads(res.stdout)["hookSpecificOutput"]["sessionTitle"],
                             "TEAM-9: 帯を出す")

    def test_ignores_the_copy_in_archive(self):
        """maintain 系が archive/ に置いた同じ名前の控えを掴まない（GitHub issue #422）."""
        repo = TempGitRepo()
        with repo as root:
            repo.branch("ISS-2-work")
            base = root / ".claude" / "indie" / "demo"
            for sub, title in (("archive", "古い控え"), ("issues", "今の題")):
                p = base / sub / "ISS-2.md"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(f"---\nid: ISS-2\ntitle: {title}\n---\n")
            res = self.run_hook({"prompt": "作業する"}, cwd=root)
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("Unexpected", res.stderr)
            self.assertEqual(json.loads(res.stdout)["hookSpecificOutput"]["sessionTitle"],
                             "ISS-2: 今の題")


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

    def test_a_payload_without_file_path_reaches_the_guard(self):
        """キー欠損で ERR trap に落ちない（GitHub issue #179。on-issue-change と同型）."""
        with TempGitRepo() as root:
            res = self.run_hook({"tool_name": "Edit", "tool_input": {}}, cwd=root)
            self.assertEqual(res.returncode, 0)
            self.assertNotIn("Unexpected", res.stderr, "ERR trap で落ちている")
            self.assertIn("not a knowledge file", res.stderr, "自己判定ガードに到達していない")


if __name__ == "__main__":
    unittest.main()
