#!/usr/bin/env python3
"""dev-workflow の hook スクリプトの回帰テスト.

**通す条件より、黙る条件を厚く**書く。hook の失敗様式は「鳴らない」より
「鳴りすぎる」方が高コストで（全ツール呼び出しに影響する）、実際に踏んだのもそちら。

- `push-reminder.sh` — 暴発の当事者（`if: "Bash(git push *)"` が評価されず全 Bash 呼び出しに注入した）
- `on-commit.sh` — Event Bus の `commit:created` publisher。誤発火すると subscriber が空振りする
- `detect-web-project.sh` — フラグの**立て方だけでなく消し方**（Web でなくなった時）
- `ui-verify-gate.sh` / `ui-change-reminder.sh` — 3 値フラグ（unverified / verified-local / verified-snap）
- `tdd-phase-gate.sh` — opt-in なので**既定で絶対に鳴らない**ことが第一の仕様

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest import mock

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

    def test_events_never_land_in_the_ambient_project_dir(self):
        """**環境の `CLAUDE_PROJECT_DIR` を継承しない**（この変数は書き込み先を決める）.

        継承すると publish は `${CLAUDE_PROJECT_DIR}/.claude/events.jsonl` へ飛ぶ。
        本スイートは Stop hook / self-review 前段からも走る＝**その環境ではこの変数が入る**ので、
        publish を見るテストは落ち、黙る側のテストは**緑のまま**実リポジトリの計測データを汚す
        （実測: 偽イベント 20 件が `.claude/events.jsonl` に混入していた）。
        """
        with TempGitRepo() as repo_path:
            repo = TempGitRepo.__new__(TempGitRepo); repo.path = repo_path
            repo.commit("feat(x): 追加")
            decoy = repo_path / "decoy"
            decoy.mkdir()
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(decoy)}):
                self.run_hook(self.bash_payload('git commit -m "feat(x): 追加"'), cwd=repo_path)
            self.assertEqual([e["event"] for e in self._events(repo_path)], ["commit:created"])
            self.assertFalse((decoy / ".claude" / "events.jsonl").exists(),
                             "環境変数が指す先へ publish している")

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


class DetectWebProjectTest(HookTestCase):
    """SessionStart: package.json の依存で ui-verify 連携フラグを管理する（無音）."""

    PLUGIN = "dev-workflow"
    SCRIPT = "hooks/scripts/detect-web-project.sh"

    def _run_in(self, root: Path, package: dict | None):
        if package is not None:
            (root / "package.json").write_text(json.dumps(package))
        return self.run_hook({"hook_event_name": "SessionStart"}, cwd=root)

    def test_enables_for_web_framework(self):
        for dep in ("next", "react", "vue", "svelte", "@angular/core", "astro"):
            with self.subTest(dep=dep), TempGitRepo() as root:
                self._run_in(root, {"dependencies": {dep: "^1.0.0"}})
                self.assertTrue((root / ".claude" / ".ui-verify-enabled").is_file(), dep)

    def test_enables_from_dev_dependencies(self):
        with TempGitRepo() as root:
            self._run_in(root, {"devDependencies": {"vue": "^3"}})
            self.assertTrue((root / ".claude" / ".ui-verify-enabled").is_file())

    def test_does_not_enable_for_non_web(self):
        with TempGitRepo() as root:
            self._run_in(root, {"dependencies": {"express": "^4", "lodash": "^4"}})
            self.assertFalse((root / ".claude" / ".ui-verify-enabled").exists())

    def test_partial_name_does_not_match(self):
        """`react-native-cli` のような部分一致で有効化しない（完全一致が仕様）."""
        with TempGitRepo() as root:
            self._run_in(root, {"dependencies": {"preact-compat-shim": "^1"}})
            self.assertFalse((root / ".claude" / ".ui-verify-enabled").exists())

    def test_removes_flag_when_package_json_disappears(self):
        """**有効化だけでなく無効化も**する（Web でなくなったのに残ると誤って gate が働く）."""
        with TempGitRepo() as root:
            flag = root / ".claude" / ".ui-verify-enabled"
            flag.parent.mkdir(exist_ok=True); flag.touch()
            self._run_in(root, None)
            self.assertFalse(flag.exists())

    def test_removes_flag_when_web_dep_removed(self):
        with TempGitRepo() as root:
            flag = root / ".claude" / ".ui-verify-enabled"
            flag.parent.mkdir(exist_ok=True); flag.touch()
            self._run_in(root, {"dependencies": {"express": "^4"}})
            self.assertFalse(flag.exists())

    def test_is_silent(self):
        with TempGitRepo() as root:
            self.assertSilent(self._run_in(root, {"dependencies": {"next": "^14"}}))


class UiVerifyGateTest(HookTestCase):
    """PreToolUse(commit): 未確認の UI 変更があれば促す（ブロックはしない）."""

    PLUGIN = "dev-workflow"
    SCRIPT = "hooks/scripts/ui-verify-gate.sh"

    def _setup(self, root: Path, *, enabled: bool, pending: str | None):
        d = root / ".claude"; d.mkdir(exist_ok=True)
        if enabled:
            (d / ".ui-verify-enabled").touch()
        if pending is not None:
            (d / ".ui-verify-pending").write_text(f"{pending}\n2026-08-17T00:00:00Z\n")

    def test_fires_when_unverified(self):
        with TempGitRepo() as root:
            self._setup(root, enabled=True, pending="unverified")
            self.assertFired(self.run_hook(self.bash_payload("git commit -m x"), cwd=root),
                             "ui-verify")

    def test_silent_when_already_verified(self):
        for status in ("verified-local", "verified-snap"):
            with self.subTest(status=status), TempGitRepo() as root:
                self._setup(root, enabled=True, pending=status)
                self.assertSilent(self.run_hook(self.bash_payload("git commit -m x"), cwd=root))

    def test_silent_when_not_enabled(self):
        with TempGitRepo() as root:
            self._setup(root, enabled=False, pending="unverified")
            self.assertSilent(self.run_hook(self.bash_payload("git commit -m x"), cwd=root))

    def test_silent_without_pending(self):
        with TempGitRepo() as root:
            self._setup(root, enabled=True, pending=None)
            self.assertSilent(self.run_hook(self.bash_payload("git commit -m x"), cwd=root))

    def test_silent_for_non_commit_command(self):
        with TempGitRepo() as root:
            self._setup(root, enabled=True, pending="unverified")
            for cmd in ("git push", "ls", 'echo "git commit"'):
                with self.subTest(cmd=cmd):
                    self.assertSilent(self.run_hook(self.bash_payload(cmd), cwd=root))

    def test_never_blocks(self):
        with TempGitRepo() as root:
            self._setup(root, enabled=True, pending="unverified")
            self.assertNotEqual(
                self.run_hook(self.bash_payload("git commit -m x"), cwd=root).returncode, 2)


class UiChangeReminderTest(HookTestCase):
    PLUGIN = "dev-workflow"
    SCRIPT = "hooks/scripts/ui-change-reminder.sh"

    def _enable(self, root: Path):
        d = root / ".claude"; d.mkdir(exist_ok=True); (d / ".ui-verify-enabled").touch()

    def payload(self, path: str, tool: str = "Edit") -> dict:
        return {"tool_name": tool, "tool_input": {"file_path": path}}

    def test_fires_for_ui_extensions(self):
        for name in ("a.tsx", "b.vue", "c.svelte", "d.css", "e.scss", "f.astro", "g.mdx"):
            with self.subTest(name=name), TempGitRepo() as root:
                self._enable(root)
                res = self.run_hook(self.payload(str(root / name)), cwd=root)
                self.assertIn("[ui-verify]", res.stdout, name)

    def test_creates_pending_flag_as_unverified(self):
        with TempGitRepo() as root:
            self._enable(root)
            self.run_hook(self.payload(str(root / "a.tsx")), cwd=root)
            self.assertEqual((root / ".claude" / ".ui-verify-pending")
                             .read_text().splitlines()[0], "unverified")

    def test_does_not_reset_existing_verified_flag(self):
        """1 セッション中の小修正で verified を毎回消さない（意図的な仕様）."""
        with TempGitRepo() as root:
            self._enable(root)
            pending = root / ".claude" / ".ui-verify-pending"
            pending.write_text("verified-snap\n2026-08-17T00:00:00Z\n")
            self.run_hook(self.payload(str(root / "a.tsx")), cwd=root)
            self.assertEqual(pending.read_text().splitlines()[0], "verified-snap")

    def test_silent_for_non_ui_file(self):
        with TempGitRepo() as root:
            self._enable(root)
            for name in ("a.ts", "b.py", "README.md", "c.json"):
                with self.subTest(name=name):
                    self.assertSilent(self.run_hook(self.payload(str(root / name)), cwd=root))

    def test_silent_when_not_enabled(self):
        with TempGitRepo() as root:
            self.assertSilent(self.run_hook(self.payload(str(root / "a.tsx")), cwd=root))

    def test_silent_for_non_edit_tool(self):
        with TempGitRepo() as root:
            self._enable(root)
            self.assertSilent(self.run_hook(self.payload(str(root / "a.tsx"), tool="Bash"), cwd=root))


class TddPhaseGateTest(HookTestCase):
    """opt-in なので**既定では絶対に鳴らない**ことが第一の仕様."""

    PLUGIN = "dev-workflow"
    SCRIPT = "hooks/scripts/tdd-phase-gate.sh"

    def _enable(self, root: Path):
        d = root / ".claude"; d.mkdir(exist_ok=True); (d / ".tdd-phase-gate-enabled").touch()

    def payload(self, path: Path, tool: str = "Edit") -> dict:
        return {"tool_name": tool, "tool_input": {"file_path": str(path)}}

    def test_silent_when_not_enabled(self):
        with TempGitRepo() as root:
            src = root / "a.ts"; src.write_text("export const a = 1\n")
            self.assertSilent(self.run_hook(self.payload(src), cwd=root))

    def test_fires_for_source_without_test(self):
        with TempGitRepo() as root:
            self._enable(root)
            src = root / "a.ts"; src.write_text("export const a = 1\n")
            self.assertFired(self.run_hook(self.payload(src), cwd=root), "tdd-phase-gate")

    def test_silent_when_sibling_test_exists(self):
        for test_name in ("a.test.ts", "a.spec.ts"):
            with self.subTest(test_name=test_name), TempGitRepo() as root:
                self._enable(root)
                src = root / "a.ts"; src.write_text("x\n")
                (root / test_name).write_text("test\n")
                self.assertSilent(self.run_hook(self.payload(src), cwd=root))

    def test_silent_when_test_in_tests_dir(self):
        with TempGitRepo() as root:
            self._enable(root)
            src = root / "a.ts"; src.write_text("x\n")
            (root / "__tests__").mkdir()
            (root / "__tests__" / "a.test.ts").write_text("t\n")
            self.assertSilent(self.run_hook(self.payload(src), cwd=root))

    def test_silent_for_test_and_config_files(self):
        with TempGitRepo() as root:
            self._enable(root)
            for name in ("a.test.ts", "a.spec.ts", "test_a.py", "vite.config.ts",
                         "next.config.js", "a.d.ts", "a.stories.tsx"):
                with self.subTest(name=name):
                    f = root / name; f.write_text("x\n")
                    self.assertSilent(self.run_hook(self.payload(f), cwd=root))

    def test_silent_inside_test_directories(self):
        with TempGitRepo() as root:
            self._enable(root)
            for d in ("__tests__", "tests", "test", "__mocks__"):
                with self.subTest(dir=d):
                    (root / d).mkdir(exist_ok=True)
                    f = root / d / "a.ts"; f.write_text("x\n")
                    self.assertSilent(self.run_hook(self.payload(f), cwd=root))

    def test_silent_for_non_source_extension(self):
        with TempGitRepo() as root:
            self._enable(root)
            for name in ("README.md", "a.json", "a.css", "a.yaml"):
                with self.subTest(name=name):
                    f = root / name; f.write_text("x\n")
                    self.assertSilent(self.run_hook(self.payload(f), cwd=root))

    def test_new_file_write_is_allowed(self):
        """テストより先に空の実装ファイルを作るのは Red phase の正常フロー."""
        with TempGitRepo() as root:
            self._enable(root)
            self.assertSilent(self.run_hook(self.payload(root / "new.ts", tool="Write"), cwd=root))

    def test_never_blocks(self):
        with TempGitRepo() as root:
            self._enable(root)
            src = root / "a.ts"; src.write_text("x\n")
            self.assertNotEqual(self.run_hook(self.payload(src), cwd=root).returncode, 2)

    # --- 場所 × 命名の直積（GitHub issue #180）---
    def test_every_documented_layout_silences_the_gate(self):
        """README が宣言する「場所 × 命名」の全組み合わせで黙ること.

        以前は手書きの 9 通りで直積になっておらず、`tests/` 配下は `.test.` と `test_`
        しか探していなかった。**`tests/foo.spec.ts` 構成はテストが実在しても常に警告**
        が出る状態で、恒常的な誤警告は「⚠️ が出たときだけ行動する」契約を壊す。
        """
        layouts = [(d, n) for d in ("", "__tests__", "tests")
                   for n in ("a.test.ts", "a.spec.ts", "test_a.ts", "a_test.ts")]
        layouts += [("__tests__", "a.ts"), ("tests", "a.ts")]   # ミラー配置
        for subdir, test_name in layouts:
            with self.subTest(layout=f"{subdir or '.'}/{test_name}"), TempGitRepo() as root:
                self._enable(root)
                src = root / "a.ts"; src.write_text("x\n")
                target = root / subdir if subdir else root
                target.mkdir(exist_ok=True)
                (target / test_name).write_text("t\n")
                self.assertSilent(self.run_hook(self.payload(src), cwd=root))


class JqAbsentFallbackTest(HookTestCase):
    """`jq` を引けない環境での自己判定（GitHub issue #180）.

    jq 分岐は `|| true` 済みだったが、grep fallback 側に無かった。対象キーを欠く
    payload（**まさに自己判定が受け持つべきケース**）で grep の exit 1 が safe-hook の
    ERR trap を踏み、自己判定ごと死んでいた。`rc` は同じ 0 なので stderr で見分ける。
    """

    PLUGIN = "dev-workflow"

    SCRIPTS = {
        "hooks/scripts/on-commit.sh": {"tool_input": {}},
        "hooks/scripts/push-reminder.sh": {"tool_input": {}},
        "hooks/scripts/ui-verify-gate.sh": {"tool_input": {}},
        "hooks/scripts/tdd-phase-gate.sh": {"tool_input": {}},
        "hooks/scripts/ui-change-reminder.sh": {"tool_input": {}},
    }

    def test_a_missing_key_does_not_trip_the_err_trap(self):
        path = self.path_with_only()          # jq を含めない
        for script, payload in self.SCRIPTS.items():
            with self.subTest(script=script), TempGitRepo() as root:
                # tdd-phase-gate / ui-verify-gate は opt-in なので有効化して経路に入れる
                d = root / ".claude"; d.mkdir(exist_ok=True)
                (d / ".tdd-phase-gate-enabled").touch()
                (d / ".ui-verify-enabled").touch()
                self.SCRIPT = script
                res = self.run_hook(payload, cwd=root, env_extra={"PATH": path})
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertNotIn("Unexpected", res.stderr,
                                 f"{script}: ERR trap で落ちている（自己判定に到達しない）")


class PostFormatLintTest(HookTestCase):
    """opt-in の 3 段チェーン（fmt → lint → check）。**check だけが block を出す**."""

    PLUGIN = "dev-workflow"
    SCRIPT = "hooks/scripts/post-format-lint.sh"

    def _config(self, root: Path, cfg: dict):
        d = root / ".claude"; d.mkdir(exist_ok=True)
        (d / "dev-workflow.json").write_text(json.dumps(cfg))

    def payload(self, path: Path, tool: str = "Edit") -> dict:
        return {"tool_name": tool, "tool_input": {"file_path": str(path)}}

    def _lang(self, *, fmt="", lint="", check="", enabled=None) -> dict:
        lang: dict = {"extensions": ["ts"]}
        if fmt:
            lang["fmt"] = fmt
        if lint:
            lang["lint"] = lint
        if check:
            lang["check"] = check
        if enabled is not None:
            lang["enabled"] = enabled
        return {"lint": {"enabled": True, "languages": {"typescript": lang}}}

    def test_dormant_without_config(self):
        """**設定が無ければ完全 dormant**（opt-in の第一要件）."""
        with TempGitRepo() as root:
            src = root / "a.ts"; src.write_text("x\n")
            self.assertSilent(self.run_hook(self.payload(src), cwd=root))

    def test_dormant_when_disabled(self):
        with TempGitRepo() as root:
            self._config(root, {"lint": {"enabled": False,
                                         "languages": {"typescript": {"extensions": ["ts"],
                                                                      "check": "false"}}}})
            src = root / "a.ts"; src.write_text("x\n")
            self.assertSilent(self.run_hook(self.payload(src), cwd=root))

    def test_language_can_be_disabled_individually(self):
        """`enabled: false` の言語だけ止まる（jq の `//` 罠を踏んでいないこと）."""
        with TempGitRepo() as root:
            self._config(root, self._lang(check="false", enabled=False))
            src = root / "a.ts"; src.write_text("x\n")
            self.assertSilent(self.run_hook(self.payload(src), cwd=root))

    def test_blocks_when_check_fails(self):
        with TempGitRepo() as root:
            self._config(root, self._lang(check="sh -c 'echo 違反あり >&2; exit 1' --"))
            src = root / "a.ts"; src.write_text("x\n")
            out = self.run_hook(self.payload(src), cwd=root).stdout
            self.assertIn("block", out)
            self.assertIn("post-format-lint", out)

    def test_silent_when_check_passes(self):
        with TempGitRepo() as root:
            self._config(root, self._lang(check="true"))
            src = root / "a.ts"; src.write_text("x\n")
            self.assertSilent(self.run_hook(self.payload(src), cwd=root))

    def test_fmt_and_lint_failures_do_not_block(self):
        """fmt / lint 段は黙って直す係。**失敗しても block しない**."""
        with TempGitRepo() as root:
            self._config(root, self._lang(fmt="false", lint="false", check="true"))
            src = root / "a.ts"; src.write_text("x\n")
            self.assertSilent(self.run_hook(self.payload(src), cwd=root))

    def test_unknown_extension_is_silent(self):
        with TempGitRepo() as root:
            self._config(root, self._lang(check="false"))
            src = root / "a.py"; src.write_text("x\n")
            self.assertSilent(self.run_hook(self.payload(src), cwd=root))

    def test_non_edit_tool_is_silent(self):
        with TempGitRepo() as root:
            self._config(root, self._lang(check="false"))
            src = root / "a.ts"; src.write_text("x\n")
            self.assertSilent(self.run_hook(self.payload(src, tool="Bash"), cwd=root))

    def test_missing_file_is_silent(self):
        with TempGitRepo() as root:
            self._config(root, self._lang(check="false"))
            self.assertSilent(self.run_hook(self.payload(root / "none.ts"), cwd=root))

    def test_never_exits_two(self):
        """block は JSON で表現する。exit 2 は使わない."""
        with TempGitRepo() as root:
            self._config(root, self._lang(check="false"))
            src = root / "a.ts"; src.write_text("x\n")
            self.assertNotEqual(self.run_hook(self.payload(src), cwd=root).returncode, 2)


class UploadScreenshotsTest(unittest.TestCase):
    """引数バリデーションのみ（本体は gh 経由の network I/O なので対象外）.

    `hooks/scripts/` に置かれているが hooks.json から呼ばれる hook ではなく CLI。
    それでも「引数無しで走ると何をするか」は決まっているべきなので、そこだけ固定する。
    """

    SCRIPT = Path(__file__).resolve().parents[3] / "dev-workflow/hooks/scripts/upload-screenshots.sh"

    def _run(self, *args):
        import subprocess
        return subprocess.run(["bash", str(self.SCRIPT), *args],
                              capture_output=True, text=True, timeout=30)

    def test_usage_without_arguments(self):
        res = self._run()
        self.assertEqual(res.returncode, 1)
        self.assertIn("Usage:", res.stderr)

    def test_usage_for_missing_directory(self):
        res = self._run("/nonexistent/dir")
        self.assertEqual(res.returncode, 1)
        self.assertIn("Usage:", res.stderr)


if __name__ == "__main__":
    unittest.main()
