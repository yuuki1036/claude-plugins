#!/usr/bin/env python3
"""残りの hook スクリプト（1 プラグイン 1〜2 本）と `check-deps.sh` の共通契約テスト.

`check-deps.sh` は 6 プラグインにほぼ同型で存在する。個別に書くと同じテストを 6 回
書くことになるので、**契約（全部が満たすべき性質）をパラメタライズして 1 回だけ**書く:

- stdin を消費する（消費しないと hook がハングする — リポジトリ最大の Gotcha）
- 依存が揃っていれば無音（毎セッション鳴る hook は「⚠️ が出たら行動」の契約を壊す）
- 依存不足でも exit 2 でブロックしない（起動を止めない）

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path

from hook_harness import HookTestCase, ROOT, TempGitRepo

CHECK_DEPS = sorted(
    p for p in ROOT.glob("*/hooks/scripts/check-deps.sh") if p.is_file()
)


class CheckDepsContractTest(unittest.TestCase):
    """全 `check-deps.sh` が共通で満たすべき性質."""

    def _run(self, script: Path, *, path_env: str | None = None, timeout: int = 20):
        env = dict(os.environ)
        env["CLAUDE_PLUGIN_ROOT"] = str(script.parents[2])
        if path_env is not None:
            env["PATH"] = path_env
        # bash は絶対パスで叩く（PATH を潰すテストがあるため）
        return subprocess.run(["/bin/bash", str(script)],
                              input='{"hook_event_name":"SessionStart"}',
                              capture_output=True, text=True, cwd=str(ROOT), env=env,
                              timeout=timeout)

    def test_at_least_one_exists(self):
        """走査が空振りしていたら、この契約テスト自体が無意味になる."""
        self.assertGreaterEqual(len(CHECK_DEPS), 4, "check-deps.sh が見つからない")

    def test_consumes_stdin_and_terminates(self):
        """**stdin を消費しないと hook はハングする**（リポジトリ最大の Gotcha）."""
        for script in CHECK_DEPS:
            with self.subTest(script=script.parents[2].name):
                # timeout に達したら TimeoutExpired が上がる = ハング検出
                self._run(script, timeout=15)

    def test_never_blocks(self):
        for script in CHECK_DEPS:
            with self.subTest(script=script.parents[2].name):
                self.assertNotEqual(self._run(script).returncode, 2)

    def test_silent_when_dependencies_present(self):
        """依存が揃っている環境（このリポジトリ）では何も出さない."""
        for script in CHECK_DEPS:
            with self.subTest(script=script.parents[2].name):
                out = self._run(script).stdout.strip()
                if out:
                    # 出るのは「本当に依存が無い」場合だけ。何が足りないか明示されていること
                    self.assertIn("依存チェック", out)

    def test_reports_missing_dependency_without_blocking(self):
        """依存 CLI が見つからない環境でも、ブロックせず理由を述べる.

        PATH を `/bin` だけにすると gh / jq / npm 等が解決できなくなる（bash 自体は残る）。
        """
        for script in CHECK_DEPS:
            with self.subTest(script=script.parents[2].name):
                res = self._run(script, path_env="/bin")
                self.assertNotEqual(res.returncode, 2, res.stderr)
                if res.stdout.strip():
                    self.assertIn("依存チェック", res.stdout)


class InjectAdvisorRuleTest(HookTestCase):
    """dormant ゲート: 提案先が 1 つも**有効**でなければ何も注入しない."""

    PLUGIN = "spec-advisor"
    SCRIPT = "hooks/scripts/inject-advisor-rule.sh"

    def _run(self, root: Path, settings: dict | None, *, local: bool = False):
        if settings is not None:
            d = root / ".claude"; d.mkdir(exist_ok=True)
            name = "settings.local.json" if local else "settings.json"
            (d / name).write_text(json.dumps(settings))
        return self.run_hook({"hook_event_name": "SessionStart"}, cwd=root,
                             env_extra={"CLAUDE_PROJECT_DIR": str(root), "HOME": str(root)})

    def test_injects_when_a_planning_plugin_is_enabled(self):
        with TempGitRepo() as root:
            res = self._run(root, {"enabledPlugins": {"design-doc@mp": True}})
            self.assertIn("spec ルーティング", res.stdout)

    def test_project_local_settings_are_honoured(self):
        """project-scoped 有効化を取りこぼさない（#74 と同根の罠）."""
        with TempGitRepo() as root:
            res = self._run(root, {"enabledPlugins": {"adr-keeper@mp": True}}, local=True)
            self.assertIn("spec ルーティング", res.stdout)

    def test_disabled_plugin_does_not_count(self):
        """`": false"` はキー文字列が残る。**存在ではなく値を見る**のが仕様."""
        with TempGitRepo() as root:
            self.assertSilent(self._run(root, {"enabledPlugins": {"design-doc@mp": False}}))

    def test_silent_without_any_planning_plugin(self):
        with TempGitRepo() as root:
            self.assertSilent(self._run(root, {"enabledPlugins": {"unrelated@mp": True}}))

    def test_silent_without_settings(self):
        with TempGitRepo() as root:
            self.assertSilent(self._run(root, None))

    def test_never_blocks(self):
        with TempGitRepo() as root:
            self.assertNotEqual(self._run(root, None).returncode, 2)


class FailureJournalInitTest(HookTestCase):
    PLUGIN = "failure-journal"
    SCRIPT = "hooks/scripts/session-start-init.sh"

    def _run(self, root: Path):
        return self.run_hook({"hook_event_name": "SessionStart"}, cwd=root,
                             env_extra={"CLAUDE_PROJECT_DIR": str(root)})

    def test_creates_journal_files(self):
        with TempGitRepo() as root:
            self._run(root)
            d = root / ".claude" / "failure-journal"
            self.assertTrue((d / "journal.jsonl").is_file())
            self.assertTrue((d / "candidates.jsonl").is_file())

    def test_injects_self_report_rule(self):
        with TempGitRepo() as root:
            self.assertIn("candidates.jsonl", self._run(root).stdout)

    def test_does_not_truncate_existing_journal(self):
        """**既存の記録を消さない**（消すと失敗履歴が毎セッション消える）."""
        with TempGitRepo() as root:
            d = root / ".claude" / "failure-journal"
            d.mkdir(parents=True)
            (d / "journal.jsonl").write_text('{"ts":"x","summary":"既存"}\n')
            (d / "candidates.jsonl").write_text('{"ts":"y"}\n')
            self._run(root)
            self.assertIn("既存", (d / "journal.jsonl").read_text())
            self.assertIn('"y"', (d / "candidates.jsonl").read_text())

    def test_is_idempotent(self):
        with TempGitRepo() as root:
            self._run(root); self._run(root)
            self.assertEqual(
                (root / ".claude" / "failure-journal" / "journal.jsonl").read_text(), "")

    def test_never_blocks(self):
        with TempGitRepo() as root:
            self.assertNotEqual(self._run(root).returncode, 2)


class PreConfigGuardTest(HookTestCase):
    """lint / hook 設定ファイルの骨抜き編集をブロックする（opt-in）."""

    PLUGIN = "guardrail-protect"
    SCRIPT = "hooks/scripts/pre-config-guard.sh"

    def _run(self, root: Path, path: str, *, protected: list[str] | None = None,
             tool: str = "Edit"):
        if protected is not None:
            d = root / ".claude"; d.mkdir(exist_ok=True)
            (d / "guardrail-protect.json").write_text(
                json.dumps({"protected_basenames": protected}))
        return self.run_hook({"tool_name": tool, "tool_input": {"file_path": path}},
                             cwd=root, env_extra={"CLAUDE_PROJECT_DIR": str(root)})

    def test_blocks_protected_basename(self):
        with TempGitRepo() as root:
            res = self._run(root, str(root / "sub" / ".golangci.yml"), protected=[".golangci.yml"])
            self.assertEqual(res.returncode, 2)
            self.assertIn("Refusing to edit guardrail config file", res.stderr)

    def test_matches_by_basename_not_path(self):
        """どこに置かれていても basename で保護する."""
        with TempGitRepo() as root:
            for p in ("a/lefthook.yml", "b/c/lefthook.yml", "lefthook.yml"):
                with self.subTest(path=p):
                    self.assertEqual(self._run(root, str(root / p),
                                               protected=["lefthook.yml"]).returncode, 2)

    def test_partial_basename_does_not_match(self):
        """`grep -Fxq` の完全一致（`lefthook.yml.bak` は別物）."""
        with TempGitRepo() as root:
            self.assertEqual(self._run(root, str(root / "lefthook.yml.bak"),
                                       protected=["lefthook.yml"]).returncode, 0)

    def test_always_protects_its_own_config(self):
        """**自己保護**: basename を外す 2 段階バイパスを塞ぐ（設定が無くても効く）."""
        with TempGitRepo() as root:
            res = self._run(root, str(root / ".claude" / "guardrail-protect.json"))
            self.assertEqual(res.returncode, 2)
            self.assertIn("guardrail config itself", res.stderr)

    def test_self_protection_works_without_config_file(self):
        with TempGitRepo() as root:
            self.assertEqual(self._run(root, "/tmp/guardrail-protect.json").returncode, 2)

    def test_no_op_without_config(self):
        """既定では保護対象ゼロ＝誤爆なし（プロジェクト側が opt-in で宣言する）."""
        with TempGitRepo() as root:
            self.assertEqual(self._run(root, str(root / ".golangci.yml")).returncode, 0)

    def test_no_op_with_empty_protected_list(self):
        with TempGitRepo() as root:
            self.assertEqual(self._run(root, str(root / ".golangci.yml"),
                                       protected=[]).returncode, 0)

    def test_unprotected_file_passes(self):
        with TempGitRepo() as root:
            self.assertEqual(self._run(root, str(root / "src" / "main.go"),
                                       protected=[".golangci.yml"]).returncode, 0)

    def test_malformed_input_does_not_block(self):
        with TempGitRepo() as root:
            self.assertEqual(self.run_hook({}, cwd=root).returncode, 0)

class CheckMissingPluginsTest(HookTestCase):
    """後発追加の通知。**閾値・cooldown・ignore・deprecated 除外**が全部「黙る理由」."""

    PLUGIN = "plugin-manager"
    SCRIPT = "hooks/scripts/check-missing-plugins.sh"

    def _home(self, root: Path, *, market: list[dict], installed: list[str],
              config: dict | None = None, state: dict | None = None) -> Path:
        home = root / "home"
        mp = home / ".claude" / "plugins" / "marketplaces" / "mp" / ".claude-plugin"
        mp.mkdir(parents=True, exist_ok=True)
        (mp / "marketplace.json").write_text(json.dumps({"name": "mp", "plugins": market}))
        (home / ".claude" / "plugins" / "installed_plugins.json").write_text(
            json.dumps({"plugins": {k: {} for k in installed}}))
        cfg_dir = home / ".claude" / "plugin-manager"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        if config is not None:
            (cfg_dir / "config.json").write_text(json.dumps(config))
        if state is not None:
            (cfg_dir / "state.json").write_text(json.dumps(state))
        return home

    def _plugins(self, n: int, *, superseded: dict | None = None) -> list[dict]:
        out = []
        for i in range(n):
            e = {"name": f"p{i}", "source": f"./p{i}", "version": "1.0.0",
                 "description": "d", "author": {"name": "a"}}
            if superseded and f"p{i}" in superseded:
                e["_superseded_by"] = superseded[f"p{i}"]
            out.append(e)
        return out

    def _run(self, root: Path, home: Path):
        return self.run_hook({"hook_event_name": "SessionStart"}, cwd=root,
                             env_extra={"HOME": str(home)})

    def test_notifies_for_newly_added_plugin(self):
        with TempGitRepo() as root:
            home = self._home(root, market=self._plugins(5),
                              installed=[f"p{i}@mp" for i in range(4)])
            self.assertIn("p4@mp", self._run(root, home).stdout)

    def test_silent_when_everything_installed(self):
        with TempGitRepo() as root:
            home = self._home(root, market=self._plugins(5),
                              installed=[f"p{i}@mp" for i in range(5)])
            self.assertSilent(self._run(root, home))

    def test_silent_below_install_ratio_threshold(self):
        """一部しか入れていない巨大 marketplace で通知爆発させない."""
        with TempGitRepo() as root:
            home = self._home(root, market=self._plugins(10), installed=["p0@mp"])
            self.assertSilent(self._run(root, home))

    def test_silent_when_nothing_installed_from_marketplace(self):
        with TempGitRepo() as root:
            home = self._home(root, market=self._plugins(5), installed=["other@x"])
            self.assertSilent(self._run(root, home))

    def test_ignore_plugins_is_honoured(self):
        with TempGitRepo() as root:
            home = self._home(root, market=self._plugins(5),
                              installed=[f"p{i}@mp" for i in range(4)],
                              config={"ignore_plugins": ["p4@mp"]})
            self.assertSilent(self._run(root, home))

    def test_ignore_marketplaces_is_honoured(self):
        with TempGitRepo() as root:
            home = self._home(root, market=self._plugins(5),
                              installed=[f"p{i}@mp" for i in range(4)],
                              config={"ignore_marketplaces": ["mp"]})
            self.assertSilent(self._run(root, home))

    def test_cooldown_suppresses_repeat_notification(self):
        with TempGitRepo() as root:
            home = self._home(root, market=self._plugins(5),
                              installed=[f"p{i}@mp" for i in range(4)],
                              state={"last_notified": {"p4@mp": "2999-01-01T00:00:00Z"}})
            self.assertSilent(self._run(root, home))

    def test_records_state_after_notifying(self):
        """通知したら state に記録する（記録しないと cooldown が効かない）."""
        with TempGitRepo() as root:
            home = self._home(root, market=self._plugins(5),
                              installed=[f"p{i}@mp" for i in range(4)])
            self._run(root, home)
            state = json.loads((home / ".claude" / "plugin-manager" / "state.json").read_text())
            self.assertIn("p4@mp", state["last_notified"])

    def test_deprecated_plugin_is_not_suggested(self):
        """deprecated の**新規 install を勧めない**."""
        with TempGitRepo() as root:
            home = self._home(root, market=self._plugins(5, superseded={"p4": "p0"}),
                              installed=[f"p{i}@mp" for i in range(4)])
            self.assertSilent(self._run(root, home))

    def test_successor_of_installed_deprecated_routes_to_update_all(self):
        """後継の直接 install は併存を招くので /update-all に誘導する."""
        # 監視対象になるには install ratio >= 0.8 が要る。deprecated は分母から外れるので、
        # 非 deprecated 5 件中 4 件インストール済み（= 0.8）になるよう組む
        with TempGitRepo() as root:
            market = self._plugins(6, superseded={"p1": "p5"})
            home = self._home(root, market=market,
                              installed=[f"p{i}@mp" for i in range(5)])
            out = self._run(root, home).stdout
            self.assertIn("/update-all", out)
            self.assertIn("p5@mp", out)

    def test_silent_without_marketplaces_dir(self):
        with TempGitRepo() as root:
            home = root / "empty-home"; home.mkdir()
            self.assertSilent(self._run(root, home))

    def test_never_blocks(self):
        with TempGitRepo() as root:
            home = self._home(root, market=self._plugins(5),
                              installed=[f"p{i}@mp" for i in range(4)])
            self.assertNotEqual(self._run(root, home).returncode, 2)


if __name__ == "__main__":
    unittest.main()
