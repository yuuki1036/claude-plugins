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
import re
import shutil
import subprocess
import tempfile
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


class CheckDepsPluginEnabledTest(unittest.TestCase):
    """`check_plugin` が同梱の plugin-enabled.sh で判定すること（GitHub issue #423）.

    以前はキーの有無だけを user の settings で見ており、`false` で無効化したものを黙って通し、
    project / local だけで有効化したものを未導入と鳴らしていた。依存 1 つごとに
    「（<dep>）が未導入か無効」の行の有無で見る（gh 等の他の検査の出力が混ざるので、全体の無音では見ない）。
    """

    MARKETPLACE = "yuuki1036-claude-plugins"

    # 他プラグインを判定する check-deps.sh（project-hub / adr-keeper の check_plugin は何もしない）.
    # 中身で選ぶと、旧実装へ戻ったスクリプトが対象から外れて回帰を見逃す
    PLUGINS = ("code-review", "dev-workflow", "feature-dev", "issue-workflow")

    @classmethod
    def setUpClass(cls):
        cls.scripts = [ROOT / p / "hooks" / "scripts" / "check-deps.sh" for p in cls.PLUGINS]

    def _deps(self, script: Path) -> list[str]:
        return re.findall(r'^check_plugin "([a-z-]+)"', script.read_text(encoding="utf-8"), re.M)

    def _run(self, script: Path, settings: dict[str, dict[str, bool]]):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            proj = Path(tmp) / "proj"
            for base in (home / ".claude", proj / ".claude"):
                base.mkdir(parents=True)
            files = {"user": home / ".claude" / "settings.json",
                     "project": proj / ".claude" / "settings.json",
                     "local": proj / ".claude" / "settings.local.json"}
            for layer, enabled in settings.items():
                plugins = {f"{k}@{self.MARKETPLACE}": val for k, val in enabled.items()}
                files[layer].write_text(json.dumps({"enabledPlugins": plugins}, indent=2), encoding="utf-8")
            # 実 HOME と CLAUDE_PROJECT_DIR を継承させない（testing-pitfalls）
            env = {"PATH": os.environ["PATH"], "HOME": str(home),
                   "CLAUDE_PROJECT_DIR": str(proj), "CLAUDE_PLUGIN_ROOT": str(script.parents[2])}
            res = subprocess.run(["/bin/bash", str(script)], input='{"hook_event_name":"SessionStart"}',
                                 capture_output=True, text=True, cwd=str(proj), env=env, timeout=20)
        self.assertNotEqual(res.returncode, 2, res.stderr)
        self.assertNotIn("Unexpected", res.stderr)
        return res.stdout

    def _flagged(self, out: str, dep: str) -> bool:
        return f"（{dep}）が未導入か無効" in out

    def test_targets_are_found(self):
        for script in self.scripts:
            self.assertTrue(self._deps(script), script)
        # 他プラグインを実際に判定する check-deps.sh が対象に入っていなければ足し忘れ.
        # 本体が `return 0` だけの no-op（_requirements との対応のためだけに呼ぶもの）は除く
        noop = re.compile(r'check_plugin\(\) \{\n(?:\s*#[^\n]*\n)?\s*local [^\n]*\n\s*return 0\n\}')
        others = [p.parents[2].name for p in CHECK_DEPS
                  if self._deps(p) and p.parents[2].name not in self.PLUGINS
                  and not noop.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(others, [])

    def test_silent_when_enabled_in_user_settings(self):
        for script in self.scripts:
            deps = self._deps(script)
            with self.subTest(script=script.parents[2].name):
                out = self._run(script, {"user": {d: True for d in deps}})
                self.assertEqual([d for d in deps if self._flagged(out, d)], [], out)

    def test_silent_when_enabled_only_in_project_settings(self):
        """旧実装は user の settings しか見ず、ここで鳴っていた."""
        for script in self.scripts:
            deps = self._deps(script)
            with self.subTest(script=script.parents[2].name):
                out = self._run(script, {"project": {d: True for d in deps}})
                self.assertEqual([d for d in deps if self._flagged(out, d)], [], out)

    def test_reports_every_dependency_without_settings(self):
        for script in self.scripts:
            deps = self._deps(script)
            with self.subTest(script=script.parents[2].name):
                out = self._run(script, {})
                self.assertEqual([d for d in deps if not self._flagged(out, d)], [], out)

    def test_reports_only_the_dependency_disabled_with_false(self):
        """旧実装はキーがあれば `false` でも黙っていた."""
        for script in self.scripts:
            deps = self._deps(script)
            with self.subTest(script=script.parents[2].name):
                enabled = {d: True for d in deps}
                enabled[deps[0]] = False
                out = self._run(script, {"user": enabled})
                self.assertEqual([d for d in deps if self._flagged(out, d)], [deps[0]], out)

    def test_local_false_overrides_user_true(self):
        for script in self.scripts:
            deps = self._deps(script)
            with self.subTest(script=script.parents[2].name):
                out = self._run(script, {"user": {d: True for d in deps}, "local": {deps[-1]: False}})
                self.assertEqual([d for d in deps if self._flagged(out, d)], [deps[-1]], out)


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
            self.assertTrue((d / "remediations.jsonl").is_file())
            self.assertTrue((d / "splits.jsonl").is_file())

    def test_injects_self_report_rule(self):
        with TempGitRepo() as root:
            self.assertIn("candidates.jsonl", self._run(root).stdout)

    CONCRETE_VALUE = "永続成果物に書く具体値"

    def test_injects_concrete_value_rule_after_nudge(self):
        """還流規約は催促の行より後に出る（催促は自己申告ルールの末尾に付く行）."""
        with TempGitRepo() as root:
            self._candidates(root, 15, 0)
            out = self._run(root).stdout
            self.assertIn(self.CONCRETE_VALUE, out)
            self.assertLess(out.index(self.NUDGE), out.index(self.CONCRETE_VALUE))

    def test_injects_behavior_assertion_rule(self):
        """挙動・因果の断定の規約も同じファイルから注入される（GitHub issue #266）."""
        with TempGitRepo() as root:
            self.assertIn("挙動・因果・深刻度の断定", self._run(root).stdout)

    def test_injects_location_assertion_rule(self):
        """所在・構造の断定の規約も同じファイルから注入される（GitHub issue #368）."""
        with TempGitRepo() as root:
            self.assertIn("コードの所在・構造の断定", self._run(root).stdout)

    def test_concrete_value_rule_is_reinjected_on_post_compact(self):
        with TempGitRepo() as root:
            res = self.run_hook({"hook_event_name": "PostCompact"}, cwd=root,
                                env_extra={"CLAUDE_PROJECT_DIR": str(root)})
            self.assertIn(self.CONCRETE_VALUE, res.stdout)

    def test_does_not_truncate_existing_journal(self):
        """**既存の記録を消さない**（消すと失敗履歴が毎セッション消える）."""
        with TempGitRepo() as root:
            d = root / ".claude" / "failure-journal"
            d.mkdir(parents=True)
            (d / "journal.jsonl").write_text('{"ts":"x","summary":"既存"}\n')
            (d / "candidates.jsonl").write_text('{"ts":"y"}\n')
            (d / "remediations.jsonl").write_text('{"tag":"z"}\n')
            (d / "splits.jsonl").write_text('{"umbrella":"w"}\n')
            self._run(root)
            self.assertIn("既存", (d / "journal.jsonl").read_text())
            self.assertIn('"y"', (d / "candidates.jsonl").read_text())
            self.assertIn('"z"', (d / "remediations.jsonl").read_text())
            self.assertIn('"w"', (d / "splits.jsonl").read_text())

    def test_is_idempotent(self):
        with TempGitRepo() as root:
            self._run(root); self._run(root)
            self.assertEqual(
                (root / ".claude" / "failure-journal" / "journal.jsonl").read_text(), "")

    # --- 未レビュー候補の /retro 催促 ---
    NUDGE = "未レビューの候補が"

    def _candidates(self, root: Path, pending: int, age_days: int, reviewed: int = 0):
        import datetime
        d = root / ".claude" / "failure-journal"
        d.mkdir(parents=True, exist_ok=True)
        now = datetime.datetime.now(datetime.timezone.utc)
        rows = []
        for i in range(pending):
            ts = now - datetime.timedelta(days=age_days if i == 0 else 0, hours=1)
            rows.append({"ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "summary": "x", "verdict": None})
        for _ in range(reviewed):
            rows.append({"ts": "2020-01-01T00:00:00Z", "summary": "x", "verdict": "accepted"})
        (d / "candidates.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    def test_nudges_when_many_pending(self):
        """件数の境界: 15 件で促す・14 件（どれも新しい）では黙る."""
        for n, fires in ((15, True), (14, False)):
            with self.subTest(n=n), TempGitRepo() as root:
                self._candidates(root, n, 0)
                out = self._run(root).stdout
                (self.assertIn if fires else self.assertNotIn)(self.NUDGE, out)

    def test_nudges_when_oldest_pending_is_old(self):
        """最古の未レビュー候補の境界: 14 日で促す・13 日では黙る（件数は少なくても）."""
        for days, fires in ((14, True), (13, False)):
            with self.subTest(days=days), TempGitRepo() as root:
                self._candidates(root, 1, days)
                out = self._run(root).stdout
                (self.assertIn if fires else self.assertNotIn)(self.NUDGE, out)

    def test_reviewed_candidates_do_not_count(self):
        """verdict の付いた（レビュー済みの）候補は、古くても数えない."""
        with TempGitRepo() as root:
            self._candidates(root, 0, 0, reviewed=40)
            self.assertNotIn(self.NUDGE, self._run(root).stdout)

    def test_no_nudge_on_post_compact(self):
        """PostCompact のたびに繰り返さない."""
        with TempGitRepo() as root:
            self._candidates(root, 30, 30)
            res = self.run_hook({"hook_event_name": "PostCompact"}, cwd=root,
                                env_extra={"CLAUDE_PROJECT_DIR": str(root)})
            self.assertIn("candidates.jsonl", res.stdout)
            self.assertNotIn(self.NUDGE, res.stdout)

    def test_unparseable_ts_is_not_treated_as_old(self):
        """読めない ts を「大昔」と数えない（件数が少なければ黙る）."""
        with TempGitRepo() as root:
            d = root / ".claude" / "failure-journal"
            d.mkdir(parents=True)
            (d / "candidates.jsonl").write_text('{"ts":"y","verdict":null}\n')
            self.assertNotIn(self.NUDGE, self._run(root).stdout)

    def test_nudge_tolerates_malformed_rows(self):
        """壊れた ts が混ざっても落ちない（ERR trap に落ちて規則の注入ごと消えない）."""
        with TempGitRepo() as root:
            d = root / ".claude" / "failure-journal"
            d.mkdir(parents=True)
            (d / "candidates.jsonl").write_text('{"ts":"y","verdict":null}\n' * 20)
            res = self._run(root)
            self.assertIn("candidates.jsonl", res.stdout)
            self.assertIn(self.NUDGE, res.stdout)
            self.assertNotIn("Unexpected", res.stderr)

    def test_never_blocks(self):
        with TempGitRepo() as root:
            self.assertNotEqual(self._run(root).returncode, 2)


class FailureJournalSubagentRuleTest(HookTestCase):
    """SubagentStart で concrete-value-rule.md を subagent に注入する（GitHub issue #428）."""

    PLUGIN = "failure-journal"
    SCRIPT = "hooks/scripts/subagent-start-rule.sh"
    RULE = ROOT / PLUGIN / "rules" / "concrete-value-rule.md"

    def _payload(self, **extra) -> dict:
        return {"hook_event_name": "SubagentStart", "agent_id": "a1",
                "agent_type": "Explore", **extra}

    # --- 発火する ---
    def test_injects_rule_as_subagent_start_context(self):
        res = self.run_hook(self._payload())
        self.assertEqual(res.returncode, 0)
        out = json.loads(res.stdout)
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SubagentStart")
        # 規約の全文がそのまま届く（要約・切り詰めをしない）
        self.assertEqual(out["hookSpecificOutput"]["additionalContext"].strip(),
                         self.RULE.read_text(encoding="utf-8").strip())
        self.assertNotIn("Unexpected", res.stderr)

    def test_rule_fits_additional_context_limit(self):
        # 注入は 10,000 字以下に収める（GitHub #428 の「期待する動作」が置いた上限）
        self.assertLess(len(self.RULE.read_text(encoding="utf-8")), 10000)

    def test_does_not_create_journal_dir(self):
        # cwd と CLAUDE_PROJECT_DIR を同じ使い捨て dir に揃え、$PWD 側に作る退行も拾う
        proj = self.isolated_project_dir()
        res = self.run_hook(self._payload(), cwd=proj)
        self.assertFired(res)
        self.assertFalse((proj / ".claude" / "failure-journal").exists())

    def test_injects_via_python3_without_jq(self):
        # jq が無い環境では python3 でイベント名を読む
        res = self.run_hook(self._payload(),
                            env_extra={"PATH": self.path_with_only("python3")})
        self.assertFired(res)
        self.assertEqual(json.loads(res.stdout)["hookSpecificOutput"]["hookEventName"],
                         "SubagentStart")
        self.assertNotIn("Unexpected", res.stderr)

    def test_python3_fallback_silent_on_other_events(self):
        for payload in ({"hook_event_name": "SessionStart"}, {"agent_type": "Explore"}):
            with self.subTest(payload=payload):
                res = self.run_hook(payload,
                                    env_extra={"PATH": self.path_with_only("python3")})
                self.assertSilent(res)
                self.assertNotIn("Unexpected", res.stderr)

    def test_silent_without_jq_and_python3(self):
        # イベント名を読めない環境では自己判定できないので注入しない
        res = self.run_hook(self._payload(), env_extra={"PATH": self.path_with_only()})
        self.assertSilent(res)
        self.assertEqual(res.returncode, 0)
        self.assertNotIn("Unexpected", res.stderr)

    # --- 黙る ---
    def test_silent_on_other_events(self):
        for event in ("SessionStart", "PostCompact", "SubagentStop", "PreToolUse", ""):
            with self.subTest(event=event):
                res = self.run_hook({"hook_event_name": event})
                self.assertSilent(res, event)
                self.assertEqual(res.returncode, 0)
                self.assertNotIn("Unexpected", res.stderr)

    def test_silent_without_event_name(self):
        res = self.run_hook({"agent_type": "Explore"})
        self.assertSilent(res)
        self.assertNotIn("Unexpected", res.stderr)

    def test_silent_on_invalid_json(self):
        for raw in ("{not json", "", "[]", '"SubagentStart"'):
            with self.subTest(raw=raw):
                res = self.run_hook(raw=raw)
                self.assertSilent(res, raw)
                self.assertEqual(res.returncode, 0)
                self.assertNotIn("Unexpected", res.stderr)

    def test_silent_when_rule_missing(self):
        # プラグインの複製から規約ファイルだけ外す
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        copy = Path(tmp.name) / self.PLUGIN
        shutil.copytree(ROOT / self.PLUGIN, copy)
        (copy / "rules" / "concrete-value-rule.md").unlink()
        res = self.run_hook(self._payload(),
                            env_extra={"CLAUDE_PLUGIN_ROOT": str(copy)})
        self.assertSilent(res)
        self.assertEqual(res.returncode, 0)
        self.assertNotIn("Unexpected", res.stderr)
        # ガードで先に止まる（cat まで進んで失敗し、空の注入で黙るのとは区別する）
        self.assertNotIn("No such file", res.stderr)

    def test_never_blocks(self):
        self.assertNotEqual(self.run_hook(self._payload()).returncode, 2)


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


class DevWorkflowGhVersionTest(unittest.TestCase):
    """dev-workflow check-deps.sh の gh 版下限チェック（2.99.0 境界）.

    gh < 2.99.0 は `gh pr create --attach` 非対応で pr-creator の Screenshots 添付が
    手動になるため WARN を出す。バージョン比較 `!= "2.99.0"` が `==` に倒れると
    判定が反転して「古い gh で無警告 / 新しい gh で誤警告」になる（mutation-nightly #229）。
    """

    SCRIPT = ROOT / "dev-workflow" / "hooks" / "scripts" / "check-deps.sh"

    def _run_with_gh(self, version: str) -> str:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            gh = bin_dir / "gh"
            # `gh --version` は version を返す。その他のサブコマンド（pr list 等）は空で成功。
            gh.write_text("#!/bin/sh\n"
                          'case "$1" in --version) echo "gh version %s (2024-01-01)";;'
                          " *) exit 0;; esac\n" % version)
            gh.chmod(0o755)
            env = dict(os.environ)
            env["CLAUDE_PLUGIN_ROOT"] = str(self.SCRIPT.parents[2])
            env["PATH"] = "%s:%s" % (bin_dir, env.get("PATH", ""))
            res = subprocess.run(["/bin/bash", str(self.SCRIPT)],
                                 input='{"hook_event_name":"SessionStart"}',
                                 capture_output=True, text=True, cwd=str(ROOT),
                                 env=env, timeout=20)
            self.assertNotEqual(res.returncode, 2, res.stderr)
            return res.stdout

    def test_old_gh_version_warns_about_attach(self):
        out = self._run_with_gh("2.40.0")
        self.assertIn("--attach", out)
        self.assertIn("2.40.0", out)

    def test_new_gh_version_does_not_warn(self):
        out = self._run_with_gh("2.99.0")
        self.assertNotIn("--attach", out)


class WritingPolishCheckDepsTest(HookTestCase):
    """textlint の**ルール解決**まで見る check-deps（本体の有無だけでは足りない）.

    textlint v15 は config のルールが 1 つでも解決できないと全ルールを drop して
    `== No rules found ==` を **exit 0** で返す。本物の textlint を欠落状態に持ち込むのは
    環境依存なので、stub の textlint を PATH 先頭に置いて出力の形だけを再現する。
    """

    PLUGIN = "writing-polish"
    SCRIPT = "hooks/scripts/check-deps.sh"

    def _stub_textlint(self, missing_rule: str | None) -> str:
        """`--config` では全 drop、`--rule <key>` では missing_rule だけ usage を返す stub."""
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        if missing_rule is None:
            body = 'echo \'[{"messages":[],"filePath":"probe.md"}]\'\n'
        else:
            body = (
                'case "$*" in\n'
                f'  *"--rule {missing_rule} "*|*"--rule {missing_rule}") echo "textlint [options] file.md"; exit 0;;\n'
                '  *--config*) echo "== No rules found, textlint hasn\'t done anything =="; exit 0;;\n'
                '  *) echo \'[{"messages":[],"filePath":"probe.md"}]\';;\n'
                'esac\n'
            )
        (d / "textlint").write_text("#!/bin/bash\n" + body)
        (d / "textlint").chmod(0o755)
        return str(d)

    def _run(self, stub_dir: str):
        return self.run_hook({"hook_event_name": "SessionStart"},
                             env_extra={"PATH": stub_dir + os.pathsep + os.environ["PATH"]})

    def test_names_missing_package_and_install_command(self):
        res = self._run(self._stub_textlint("preset-ai-words-ja"))
        self.assertIn("依存チェック", res.stdout)
        self.assertIn("textlint-rule-preset-ai-words-ja", res.stdout)
        self.assertIn("npm i -g", res.stdout)
        self.assertNotIn("Unexpected", res.stderr)

    def test_scoped_rule_maps_to_scoped_package(self):
        """`@textlint-ja/preset-ai-writing` → `@textlint-ja/textlint-rule-preset-ai-writing`."""
        res = self._run(self._stub_textlint("@textlint-ja/preset-ai-writing"))
        self.assertIn("@textlint-ja/textlint-rule-preset-ai-writing", res.stdout)

    def test_silent_when_config_resolves(self):
        self.assertSilent(self._run(self._stub_textlint(None)))

    def test_warns_without_blocking_when_textlint_absent(self):
        res = self.run_hook({"hook_event_name": "SessionStart"},
                            env_extra={"PATH": self.path_with_only("python3")})
        self.assertNotEqual(res.returncode, 2)
        self.assertIn("textlint", res.stdout)


if __name__ == "__main__":
    unittest.main()
