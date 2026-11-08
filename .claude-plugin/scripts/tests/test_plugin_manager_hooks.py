#!/usr/bin/env python3
"""plugin-manager の stale-skill hook（GitHub issue #416）.

読んだ skill の版を記録し、新しい版が入ったら読み直すよう知らせる。UserPromptSubmit で毎回走り、
PostToolUse(Read) はプラグインのファイルを読むたびに走るので、**黙る条件**を厚く見る。
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from hook_harness import HookTestCase

MP = "mp"
SID = "sess-1"


class StaleSkillTest(HookTestCase):
    PLUGIN = "plugin-manager"
    SCRIPT = "hooks/scripts/stale-skill.sh"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        # CLAUDE_CONFIG_DIR は harness が継承を消さないので、必ず明示する（開発機の実 dir に書かない）
        self.cfg = self.home / ".claude"
        self.cache = self.cfg / "plugins" / "cache" / MP

    # --- fixture ---

    def env(self) -> dict:
        return {"HOME": str(self.home), "CLAUDE_CONFIG_DIR": str(self.cfg)}

    def version_dir(self, plugin: str, ver: str, skills=("s",), changelog=None) -> Path:
        d = self.cache / plugin / ver
        for s in skills:
            (d / "skills" / s).mkdir(parents=True, exist_ok=True)
            (d / "skills" / s / "SKILL.md").write_text(f"# {s} {ver}\n")
        d.mkdir(parents=True, exist_ok=True)
        if changelog is not None:
            (d / "CHANGELOG.md").write_text(changelog)
        return d

    def install(self, plugins: dict):
        """plugins: {"<p>": "<ver>" | [entry, ...]}."""
        out = {}
        for p, v in plugins.items():
            if isinstance(v, list):
                out[f"{p}@{MP}"] = v
            else:
                out[f"{p}@{MP}"] = [{"scope": "user", "installPath": str(self.cache / p / v), "version": v}]
        path = self.cfg / "plugins" / "installed_plugins.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 2, "plugins": out}))

    def state_file(self, sid: str = SID) -> Path:
        return self.cfg / "plugin-manager" / "sessions" / f"{sid}.json"

    def read(self, path, sid=SID, response="x"):
        return self.run_hook({"session_id": sid, "hook_event_name": "PostToolUse", "tool_name": "Read",
                              "tool_input": {"file_path": str(path)}, "tool_response": response},
                             env_extra=self.env(), args=("record",))

    def skill(self, name, sid=SID):
        return self.run_hook({"session_id": sid, "hook_event_name": "PostToolUse", "tool_name": "Skill",
                              "tool_input": {"skill": name}, "tool_response": "ok"},
                             env_extra=self.env(), args=("record",))

    def prompt(self, sid=SID, text="hi"):
        return self.run_hook({"session_id": sid, "hook_event_name": "UserPromptSubmit", "prompt": text},
                             env_extra=self.env(), args=("prompt",))

    def compact(self, sid=SID):
        return self.run_hook({"session_id": sid, "hook_event_name": "PostCompact"},
                             env_extra=self.env(), args=("compact",))

    def session_start(self, source, sid=SID):
        return self.run_hook({"session_id": sid, "hook_event_name": "SessionStart", "source": source},
                             env_extra=self.env(), args=("session-start",))

    def stale_setup(self, changelog=None):
        """旧版 1.0.0 の SKILL.md を読んだあと、1.1.0 に更新された状態."""
        old = self.version_dir("p", "1.0.0")
        self.version_dir("p", "1.1.0", changelog=changelog)
        self.install({"p": "1.0.0"})
        self.assertSilent(self.read(old / "skills" / "s" / "SKILL.md"))
        self.install({"p": "1.1.0"})

    def assertQuiet(self, res, msg=""):
        """黙ったうえで、ERR trap にも落ちていない（rc は正常系も trap も 0 なので stderr で見分ける）."""
        self.assertSilent(res, msg)
        self.assertEqual(res.returncode, 0)
        self.assertNotIn("Unexpected", res.stderr)

    # --- 発火する ---

    def test_notifies_after_update(self):
        self.stale_setup(changelog="# Changelog\n\n## [1.1.0] - 2026-11-08\n\n## [1.0.0] - 2026-11-01\n")
        out = self.prompt().stdout
        self.assertIn("p: 1.0.0 → 1.1.0", out)
        self.assertIn(str(self.cache / "p" / "1.1.0" / "skills" / "s" / "SKILL.md"), out)
        self.assertIn("p:s", out)
        self.assertIn("## [1.1.0] - 2026-11-08", out)
        self.assertNotIn("## [1.0.0]", out)
        # 常設のセッションが自分で追従するための案内
        self.assertIn("利用者に確かめずに先に済ませて", out)

    def test_skill_tool_records_installed_version(self):
        self.version_dir("p", "1.0.0")
        self.version_dir("p", "1.1.0")
        self.install({"p": "1.0.0"})
        self.assertSilent(self.skill("p:s"))
        self.install({"p": "1.1.0"})
        self.assertIn("p: 1.0.0 → 1.1.0", self.prompt().stdout)

    def test_skill_does_not_overwrite_read_record(self):
        """Skill の時点の installed は新版でも、Read で記録した旧版を残す（通知漏れを防ぐ）."""
        self.stale_setup()
        self.assertSilent(self.skill("p:s"))
        self.assertIn("p: 1.0.0 → 1.1.0", self.prompt().stdout)

    def test_notifies_only_once_per_version(self):
        self.stale_setup()
        self.assertTrue(self.prompt().stdout.strip())
        self.assertQuiet(self.prompt())

    def test_notifies_again_for_next_version(self):
        self.stale_setup()
        self.prompt()
        self.version_dir("p", "1.2.0")
        self.install({"p": "1.2.0"})
        self.assertIn("1.0.0 → 1.2.0", self.prompt().stdout)

    def test_compact_rearms_once(self):
        """compaction の後はもう一度出す。続けて来る SessionStart(compact) では重ねない."""
        self.stale_setup()
        self.prompt()
        self.assertIn("1.0.0 → 1.1.0", self.compact().stdout)
        self.assertQuiet(self.session_start("compact"))
        self.assertQuiet(self.prompt())

    def test_session_start_compact_rearms(self):
        self.stale_setup()
        self.prompt()
        self.assertIn("1.0.0 → 1.1.0", self.session_start("compact").stdout)

    def test_session_start_resume_notifies_pending(self):
        self.stale_setup()
        self.assertIn("1.0.0 → 1.1.0", self.session_start("resume").stdout)

    def test_session_start_resume_does_not_rearm(self):
        self.stale_setup()
        self.prompt()
        self.assertQuiet(self.session_start("resume"))

    def test_reading_new_version_stops_notice(self):
        self.stale_setup()
        self.read(self.cache / "p" / "1.1.0" / "skills" / "s" / "SKILL.md")
        self.assertQuiet(self.prompt())
        self.assertQuiet(self.compact())

    def test_changelog_limited_to_five(self):
        heads = "".join(f"## [1.{i}.0]\n" for i in range(9, 0, -1)) + "## [Unreleased]\n## [1.0.0]\n"
        old = self.version_dir("p", "1.0.0")
        self.version_dir("p", "1.9.0", changelog="## [Unreleased]\n" + heads)
        self.install({"p": "1.0.0"})
        self.read(old / "skills" / "s" / "SKILL.md")
        self.install({"p": "1.9.0"})
        out = self.prompt().stdout
        self.assertIn("## [1.9.0]", out)
        self.assertIn("## [1.5.0]", out)
        self.assertNotIn("## [1.4.0]", out)
        self.assertNotIn("Unreleased", out)

    def test_record_writes_state_shape(self):
        old = self.version_dir("p", "1.0.0")
        self.install({"p": "1.0.0"})
        res = self.read(old / "skills" / "s" / "SKILL.md")
        self.assertQuiet(res)
        st = json.loads(self.state_file().read_text())
        self.assertEqual(st["schema_version"], 1)
        self.assertEqual(st["session_id"], SID)
        self.assertEqual(st["plugins"][f"p@{MP}"], {"version": "1.0.0", "skills": {"s": "1.0.0"}})

    def test_large_read_response_is_recorded(self):
        """tool_response が大きくても前段で取りこぼさない（pipefail × SIGPIPE の回帰）."""
        old = self.version_dir("p", "1.0.0")
        self.install({"p": "1.0.0"})
        self.read(old / "skills" / "s" / "SKILL.md", response="y" * 1_000_000)
        self.assertTrue(self.state_file().exists())

    def test_session_id_in_prompt_text_does_not_hide_notice(self):
        self.stale_setup()
        res = self.prompt(text='{"session_id":"other"} を見て')
        self.assertIn("1.0.0 → 1.1.0", res.stdout)

    def test_multiple_skills_listed(self):
        old = self.version_dir("p", "1.0.0", skills=("a", "b"))
        self.version_dir("p", "1.1.0", skills=("a", "b"))
        self.install({"p": "1.0.0"})
        self.read(old / "skills" / "a" / "SKILL.md")
        self.read(old / "skills" / "b" / "SKILL.md")
        self.install({"p": "1.1.0"})
        out = self.prompt().stdout
        self.assertIn("p:a", out)
        self.assertIn("p:b", out)

    def test_non_skill_file_read_compares_plugin_version(self):
        old = self.version_dir("p", "1.0.0")
        (old / "references").mkdir()
        (old / "references" / "x.md").write_text("x")
        self.version_dir("p", "1.1.0")
        self.install({"p": "1.0.0"})
        self.read(old / "references" / "x.md")
        self.install({"p": "1.1.0"})
        self.assertIn("p: 1.0.0 → 1.1.0", self.prompt().stdout)

    def test_resume_after_two_weeks_keeps_own_record(self):
        """14 日ぶりの resume でも、掃除より先に自分の記録を外して通知する."""
        self.stale_setup()
        past = time.time() - 20 * 86400
        os.utime(self.state_file(), (past, past))
        self.assertIn("1.0.0 → 1.1.0", self.session_start("resume").stdout)
        self.assertTrue(self.state_file().exists())

    def test_changelog_reaches_oldest_of_several_old_versions(self):
        """skill ごとに読んだ版が違うときは、一番古い旧版からの見出しを出す."""
        a = self.version_dir("p", "1.0.0", skills=("a",))
        b = self.version_dir("p", "1.1.0", skills=("b",))
        self.version_dir("p", "1.2.0", skills=("a", "b"),
                         changelog="## [1.2.0]\n## [1.1.0]\n## [1.0.0]\n## [0.9.0]\n")
        self.install({"p": "1.0.0"})
        self.read(a / "skills" / "a" / "SKILL.md")
        self.install({"p": "1.1.0"})
        self.read(b / "skills" / "b" / "SKILL.md")
        self.install({"p": "1.2.0"})
        out = self.prompt().stdout
        self.assertIn("1.0.0, 1.1.0 → 1.2.0", out)
        self.assertIn("## [1.2.0]", out)
        self.assertIn("## [1.1.0]", out)
        self.assertNotIn("## [1.0.0]", out)
        self.assertNotIn("## [0.9.0]", out)

    def test_broken_plugin_record_is_rebuilt(self):
        """記録の値の型が崩れていても、捨てて記録し直す（以後ずっと止まらない）."""
        old = self.version_dir("p", "1.0.0")
        self.version_dir("p", "1.1.0")
        self.install({"p": "1.0.0"})
        self.state_file().parent.mkdir(parents=True)
        self.state_file().write_text(json.dumps({"schema_version": 1, "session_id": SID,
                                                 "plugins": {f"p@{MP}": "x", f"q@{MP}": {"skills": []}},
                                                 "notified": {}}))
        res = self.read(old / "skills" / "s" / "SKILL.md")
        self.assertQuiet(res)
        self.assertEqual(res.stderr.strip(), "")
        self.install({"p": "1.1.0"})
        self.assertIn("p: 1.0.0 → 1.1.0", self.prompt().stdout)

    def test_broken_skill_values_do_not_stop_notices(self):
        """skills の値の型が崩れた記録は捨て、他のプラグインの通知は止めない."""
        self.stale_setup()
        st = json.loads(self.state_file().read_text())
        st["plugins"][f"p@{MP}"]["skills"].update({"a": ["x"], "b": 1})
        self.state_file().write_text(json.dumps(st))
        res = self.prompt()
        self.assertIn("p: 1.0.0 → 1.1.0", res.stdout)
        self.assertEqual(res.stderr.strip(), "")

    def test_other_schema_version_is_not_read(self):
        self.stale_setup()
        st = json.loads(self.state_file().read_text())
        st["schema_version"] = 2
        self.state_file().write_text(json.dumps(st))
        self.assertQuiet(self.prompt())

    def test_parallel_reads_are_all_recorded(self):
        """同じターンの並列の Read で、状態ファイルの更新が片方消えない."""
        from concurrent.futures import ThreadPoolExecutor
        names = [f"p{i}" for i in range(8)]
        paths = [self.version_dir(n, "1.0.0") / "skills" / "s" / "SKILL.md" for n in names]
        self.install({n: "1.0.0" for n in names})
        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(self.read, paths))
        st = json.loads(self.state_file().read_text())
        self.assertEqual(sorted(st["plugins"]), sorted(f"{n}@{MP}" for n in names))

    def test_command_only_skill_does_not_block_plugin_notice(self):
        """SKILL.md の無い名前（command だけ）を Skill で呼んでも、Read した旧版の通知は止めない."""
        old = self.version_dir("p", "1.0.0")
        (old / "references").mkdir()
        (old / "references" / "x.md").write_text("x")
        self.version_dir("p", "1.1.0")
        self.install({"p": "1.0.0"})
        self.read(old / "references" / "x.md")
        self.skill("p:cmd-only")
        st = json.loads(self.state_file().read_text())
        self.assertNotIn("skills", st["plugins"][f"p@{MP}"])
        self.install({"p": "1.1.0"})
        self.assertIn("p: 1.0.0 → 1.1.0", self.prompt().stdout)

    def test_read_version_survives_later_skill_record(self):
        """旧版の references を Read した後、更新後に Skill を呼んでも、旧版の記録で知らせる."""
        old = self.version_dir("p", "1.0.0")
        (old / "references").mkdir()
        (old / "references" / "x.md").write_text("x")
        self.version_dir("p", "1.1.0")
        self.install({"p": "1.0.0"})
        self.read(old / "references" / "x.md")
        self.install({"p": "1.1.0"})
        self.skill("p:s")
        self.assertIn("p: 1.0.0 → 1.1.0", self.prompt().stdout)

    def test_changelog_stops_at_older_heading_when_old_version_missing(self):
        old = self.version_dir("p", "1.0.0")
        self.version_dir("p", "1.3.0", changelog="## [1.3.0]\n## [1.2.0]\n## [0.9.0]\n## [0.8.0]\n")
        self.install({"p": "1.0.0"})
        self.read(old / "skills" / "s" / "SKILL.md")
        self.install({"p": "1.3.0"})
        out = self.prompt().stdout
        self.assertIn("## [1.2.0]", out)
        self.assertNotIn("## [0.9.0]", out)

    # --- 黙る ---

    def test_silent_without_session_id(self):
        old = self.version_dir("p", "1.0.0")
        self.install({"p": "1.0.0"})
        res = self.run_hook({"tool_name": "Read", "tool_input": {"file_path": str(old / "skills/s/SKILL.md")}},
                            env_extra=self.env(), args=("record",))
        self.assertQuiet(res)
        self.assertFalse((self.cfg / "plugin-manager" / "sessions").exists())
        self.assertQuiet(self.run_hook({"prompt": "hi"}, env_extra=self.env(), args=("prompt",)))

    def test_traversal_session_id_writes_nothing(self):
        old = self.version_dir("p", "1.0.0")
        self.install({"p": "1.0.0"})
        self.assertQuiet(self.read(old / "skills" / "s" / "SKILL.md", sid="../x"))
        self.assertFalse((self.cfg / "plugin-manager").exists())

    def test_silent_without_installed_file(self):
        self.stale_setup()
        (self.cfg / "plugins" / "installed_plugins.json").unlink()
        self.assertQuiet(self.prompt())

    def test_silent_with_broken_installed_file(self):
        self.stale_setup()
        (self.cfg / "plugins" / "installed_plugins.json").write_text("{broken")
        self.assertQuiet(self.prompt())

    def test_silent_with_old_installed_format(self):
        """plugins の値が dict の形（version 1）は読まない."""
        self.stale_setup()
        (self.cfg / "plugins" / "installed_plugins.json").write_text(json.dumps({"plugins": {f"p@{MP}": {}}}))
        self.assertQuiet(self.prompt())

    def test_silent_without_state_file(self):
        self.version_dir("p", "1.1.0")
        self.install({"p": "1.1.0"})
        (self.cfg / "plugin-manager" / "sessions").mkdir(parents=True)
        self.assertQuiet(self.prompt())
        self.assertQuiet(self.compact())
        self.assertQuiet(self.session_start("resume"))

    def test_silent_without_sessions_dir(self):
        self.assertQuiet(self.prompt())

    def test_silent_for_other_session(self):
        self.stale_setup()
        self.assertQuiet(self.prompt(sid="sess-2"))

    def test_silent_when_version_unchanged(self):
        old = self.version_dir("p", "1.0.0")
        self.install({"p": "1.0.0"})
        self.read(old / "skills" / "s" / "SKILL.md")
        self.assertQuiet(self.prompt())
        self.assertQuiet(self.compact())

    def test_silent_after_uninstall(self):
        self.stale_setup()
        self.install({})
        self.assertQuiet(self.prompt())

    def test_silent_when_any_scope_matches(self):
        """複数 scope の entry のどれかが読んだ版なら、更新とみなさない."""
        old = self.version_dir("p", "1.0.0")
        self.version_dir("p", "1.1.0")
        self.install({"p": "1.0.0"})
        self.read(old / "skills" / "s" / "SKILL.md")
        self.install({"p": [
            {"scope": "user", "installPath": str(self.cache / "p" / "1.1.0"), "version": "1.1.0"},
            {"scope": "project", "installPath": str(old), "version": "1.0.0", "projectPath": "/x"},
        ]})
        self.assertQuiet(self.prompt())

    def test_read_outside_cache_is_not_recorded(self):
        self.install({})
        self.assertQuiet(self.read(self.home / "repo" / "p" / "skills" / "s" / "SKILL.md"))
        self.assertFalse(self.state_file().exists())

    def test_read_shallow_cache_path_is_not_recorded(self):
        self.assertQuiet(self.read(self.cfg / "plugins" / "cache" / MP / "x.json"))
        self.assertFalse(self.state_file().exists())

    def test_cache_path_only_in_response_is_not_recorded(self):
        res = self.read(self.home / "notes.md", response=f"see {self.cache}/p/1.0.0/skills/s/SKILL.md")
        self.assertQuiet(res)
        self.assertFalse(self.state_file().exists())

    def test_bash_with_cache_path_is_not_recorded(self):
        res = self.run_hook(self.bash_payload(f"cat {self.cache}/p/1.0.0/skills/s/SKILL.md", session_id=SID),
                            env_extra=self.env(), args=("record",))
        self.assertQuiet(res)
        self.assertFalse(self.state_file().exists())

    def test_skill_without_plugin_prefix_is_not_recorded(self):
        self.install({"p": "1.0.0"})
        self.assertQuiet(self.skill("simplify"))
        self.assertFalse(self.state_file().exists())

    def test_skill_of_unknown_plugin_is_not_recorded(self):
        self.install({"p": "1.0.0"})
        self.assertQuiet(self.skill("q:s"))
        self.assertFalse(self.state_file().exists())

    def test_skill_in_two_marketplaces_is_not_recorded(self):
        self.install({"p": "1.0.0"})
        path = self.cfg / "plugins" / "installed_plugins.json"
        data = json.loads(path.read_text())
        data["plugins"]["p@other"] = [{"scope": "user", "installPath": "/x", "version": "2.0.0"}]
        path.write_text(json.dumps(data))
        self.assertQuiet(self.skill("p:s"))
        self.assertFalse(self.state_file().exists())

    def test_silent_without_python3(self):
        old = self.version_dir("p", "1.0.0")
        res = self.run_hook({"session_id": SID, "tool_name": "Read",
                             "tool_input": {"file_path": str(old / "skills/s/SKILL.md")}},
                            env_extra={**self.env(), "PATH": self.path_with_only()}, args=("record",))
        self.assertQuiet(res)
        self.assertFalse(self.state_file().exists())

    def test_session_start_startup_and_clear_are_silent(self):
        self.stale_setup()
        self.assertQuiet(self.session_start("startup"))
        self.assertQuiet(self.session_start("clear"))
        # 黙った回は通知済みにしない（次の発言で出る）
        self.assertIn("1.0.0 → 1.1.0", self.prompt().stdout)

    def test_broken_stdin(self):
        for mode in ("record", "prompt", "compact", "session-start"):
            res = self.run_hook(raw="{not json", env_extra=self.env(), args=(mode,))
            self.assertQuiet(res, mode)

    def test_broken_state_file(self):
        self.stale_setup()
        self.state_file().write_text("{broken")
        self.assertQuiet(self.prompt())

    def test_skill_removed_in_new_version(self):
        """新しい版で消えた skill の読み直し先は出さず、プラグイン単位で更新を知らせる."""
        old = self.version_dir("p", "1.0.0")
        self.version_dir("p", "1.1.0", skills=("other",))
        self.install({"p": "1.0.0"})
        self.read(old / "skills" / "s" / "SKILL.md")
        self.install({"p": "1.1.0"})
        out = self.prompt().stdout
        self.assertIn("p: 1.0.0 → 1.1.0", out)
        self.assertNotIn("skills/s/SKILL.md", out)

    def test_unknown_mode(self):
        self.assertQuiet(self.run_hook({"session_id": SID}, env_extra=self.env(), args=("bogus",)))
        self.assertQuiet(self.run_hook({"session_id": SID}, env_extra=self.env()))

    def test_prune_old_state_files_on_session_start(self):
        sessions = self.cfg / "plugin-manager" / "sessions"
        sessions.mkdir(parents=True)
        old, new = sessions / "old.json", sessions / "new.json"
        tmp = sessions / ".old.json.123.tmp"
        for f in (old, new, tmp):
            f.write_text("{}")
        past = time.time() - 20 * 86400
        os.utime(old, (past, past))
        os.utime(tmp, (past, past))
        self.prompt(sid="other")
        self.assertTrue(old.exists(), "prompt では消さない")
        self.session_start("startup", sid="other")
        self.assertFalse(old.exists())
        self.assertFalse(tmp.exists(), "書きかけの tmp も消す")
        self.assertTrue(new.exists())

    def test_prompt_refreshes_state_mtime(self):
        """Read の無い日が続く常設のセッションの記録を掃除で消さない."""
        self.stale_setup()
        past = time.time() - 20 * 86400
        os.utime(self.state_file(), (past, past))
        self.prompt()
        self.assertGreater(self.state_file().stat().st_mtime, past + 86400)


if __name__ == "__main__":
    unittest.main()
