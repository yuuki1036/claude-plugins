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
# stale_skill.py が stderr へ出す行の頭（例外を握りつぶしたとき・stdin が JSON でないとき）
PY_ERROR = "[plugin-manager:stale-skill] "


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

    def python_stub_path(self) -> tuple[str, Path]:
        """呼ばれたら印のファイルを作るだけの python3 を先頭に置いた PATH.

        stub は path_with_only の dir（本物への symlink が並ぶ）に書かない。同名の symlink があると
        write_text がたどって本物の python3 を上書きする
        """
        stub_dir = tempfile.TemporaryDirectory()
        self.addCleanup(stub_dir.cleanup)
        marker = self.home / "python-called"
        stub = Path(stub_dir.name) / "python3"
        stub.write_text(f"#!/bin/bash\n: > '{marker}'\n")
        stub.chmod(0o755)
        return f"{stub_dir.name}:{self.path_with_only('find')}", marker

    def assertQuiet(self, res, msg=""):
        """黙ったうえで、ERR trap にも python の例外にも落ちていない.

        rc は正常系も trap も 0 なので stderr で見分ける。python の except は `[plugin-manager:stale-skill] `
        で始まる行を出す（bash の safe_hook_error は `[plugin-manager:stale-skill:<分類>]`。Unexpected だけは
        同じ頭の行も出すが、先の `Unexpected` の assert が捕まえる）。
        早期 return を外しても、後段で例外になって結局黙るので、stdout だけでは区別がつかない
        """
        self.assertSilent(res, msg)
        self.assertEqual(res.returncode, 0)
        self.assertNotIn("Unexpected", res.stderr)
        self.assertNotIn(PY_ERROR, res.stderr)

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
        """発言の本文の session_id の字面は、payload の JSON で `\\"` にエスケープされて候補にならない.

        候補が複数になる経路は test_nested_session_id_before_own_does_not_hide_notice が通す
        """
        self.stale_setup()
        res = self.prompt(text='{"session_id":"other"} \\"session_id\\":"other" を見て')
        self.assertIn("1.0.0 → 1.1.0", res.stdout)

    def test_nested_session_id_before_own_does_not_hide_notice(self):
        """payload の入れ子に session_id のキーが自分より先にあっても、出現をすべて候補にして通知する（GitHub issue #465）.

        "other" の状態ファイルは置かない。置くと、最初の 1 件だけを候補にする作りでも前段を通ってしまう
        """
        self.stale_setup()
        res = self.run_hook({"extra": {"session_id": "other"}, "session_id": SID,
                             "hook_event_name": "UserPromptSubmit", "prompt": "hi"},
                            env_extra=self.env(), args=("prompt",))
        self.assertIn("1.0.0 → 1.1.0", res.stdout)

    def test_nested_session_id_without_own_record_is_silent(self):
        """入れ子の session_id にだけ状態ファイルがあっても、自分の記録が無ければ黙る（python が payload の session_id で決める）."""
        self.stale_setup()
        moved = self.state_file("other")
        self.state_file().rename(moved)
        res = self.run_hook({"extra": {"session_id": "other"}, "session_id": "sess-2",
                             "hook_event_name": "UserPromptSubmit", "prompt": "hi"},
                            env_extra=self.env(), args=("prompt",))
        self.assertQuiet(res)

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

    def test_changelog_omits_older_heading_when_old_version_missing(self):
        old = self.version_dir("p", "1.0.0")
        self.version_dir("p", "1.3.0", changelog="## [1.3.0]\n## [1.2.0]\n## [0.9.0]\n## [0.8.0]\n")
        self.install({"p": "1.0.0"})
        self.read(old / "skills" / "s" / "SKILL.md")
        self.install({"p": "1.3.0"})
        out = self.prompt().stdout
        self.assertIn("## [1.2.0]", out)
        self.assertNotIn("## [0.9.0]", out)

    # backport（1.9.6）を時系列の位置に挟み、見出しが semver の降順に並ばない CHANGELOG（GitHub issue #464）
    BACKPORT_CHANGELOG = "## [2.1.0]\n## [1.9.6]\n## [2.0.1]\n## [2.0.0]\n"

    def backport_prompt(self, old_ver: str) -> str:
        old = self.version_dir("p", old_ver)
        self.version_dir("p", "2.1.0", changelog=self.BACKPORT_CHANGELOG)
        self.install({"p": old_ver})
        self.read(old / "skills" / "s" / "SKILL.md")
        self.install({"p": "2.1.0"})
        return self.prompt().stdout

    def test_changelog_reaches_new_heading_below_older_backport(self):
        """旧版より古い見出し（backport）の下にある、旧版より新しい見出しも拾う."""
        out = self.backport_prompt("2.0.0")
        self.assertIn("## [2.1.0]", out)
        self.assertIn("## [2.0.1]", out)
        self.assertNotIn("## [1.9.6]", out)
        self.assertNotIn("## [2.0.0]", out)

    def test_changelog_reaches_new_heading_below_old_version_heading(self):
        """読んだ旧版（backport）の見出しの下にある、旧版より新しい見出しも拾う."""
        out = self.backport_prompt("1.9.6")
        self.assertIn("## [2.1.0]", out)
        self.assertIn("## [2.0.1]", out)
        self.assertIn("## [2.0.0]", out)
        self.assertNotIn("## [1.9.6]", out)

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

    def test_record_keeps_unpaired_surrogate(self):
        """payload の `\\ud800` は json.loads で対のないサロゲートになる。保存して同じ文字列に読み戻せる（#455）."""
        skill = "s\ud800"
        path = f"{self.cache}/p/1.0.0/skills/{skill}/SKILL.md"
        payload = {"session_id": SID, "hook_event_name": "PostToolUse", "tool_name": "Read",
                   "tool_input": {"file_path": path}, "tool_response": "x"}
        res = self.run_hook(raw=json.dumps(payload), env_extra=self.env(), args=("record",))
        self.assertQuiet(res)
        st = json.loads(self.state_file().read_text(encoding="utf-8"))
        self.assertEqual(st["plugins"][f"p@{MP}"], {"version": "1.0.0", "skills": {skill: "1.0.0"}})

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

    # --- fork（GitHub issue #487） ---

    def transcript(self, *paths, extra_lines=()) -> Path:
        """親の会話で paths を Read した transcript（fork 先に写った形）."""
        tp = self.home / "fork.jsonl"
        lines = list(extra_lines)
        for p in paths:
            lines.append(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "読む"},
                {"type": "tool_use", "id": "t", "name": "Read", "input": {"file_path": str(p)}}]}}))
        tp.write_text("\n".join(lines) + "\n")
        return tp

    def fork_start(self, tp=None, sid="fork-1", source="fork"):
        payload = {"session_id": sid, "hook_event_name": "SessionStart", "source": source}
        if tp is not None:
            payload["transcript_path"] = str(tp)
        return self.run_hook(payload, env_extra=self.env(), args=("session-start",))

    def fork_prompt(self, tp, sid="fork-1"):
        return self.run_hook({"session_id": sid, "hook_event_name": "UserPromptSubmit", "prompt": "hi",
                              "transcript_path": str(tp)}, env_extra=self.env(), args=("prompt",))

    def fork_setup(self):
        old = self.version_dir("p", "1.0.0")
        self.version_dir("p", "1.1.0")
        self.install({"p": "1.1.0"})
        return old / "skills" / "s" / "SKILL.md"

    def test_fork_notifies_from_parent_transcript(self):
        """fork 先には状態ファイルが無い。transcript に写った親の Read の版で知らせる."""
        tp = self.transcript(self.fork_setup())
        out = self.fork_start(tp).stdout
        self.assertIn("p: 1.0.0 → 1.1.0", out)
        self.assertIn("p:s", out)
        self.assertNotIn("fork_pending", self.state_file("fork-1").read_text())

    def test_fork_waits_for_transcript(self):
        """SessionStart の時点で transcript が無ければ黙り、書かれた後の発言で知らせる."""
        old = self.fork_setup()
        tp = self.home / "fork.jsonl"
        self.assertQuiet(self.fork_start(tp))
        self.assertQuiet(self.fork_prompt(tp))
        self.transcript(old)
        self.assertIn("p: 1.0.0 → 1.1.0", self.fork_prompt(tp).stdout)
        self.assertQuiet(self.fork_prompt(tp))

    def test_fork_waits_without_transcript_path(self):
        old = self.fork_setup()
        self.assertQuiet(self.fork_start())
        self.assertIn("p: 1.0.0 → 1.1.0", self.fork_prompt(self.transcript(old)).stdout)

    def test_fork_last_read_wins(self):
        """親が旧版の後で新しい版を読み直していれば知らせない."""
        old = self.fork_setup()
        tp = self.transcript(old, self.cache / "p" / "1.1.0" / "skills" / "s" / "SKILL.md")
        self.assertQuiet(self.fork_start(tp))
        self.assertQuiet(self.fork_prompt(tp))

    def test_fork_own_read_beats_transcript(self):
        """fork した後に自分で新しい版を読んだ記録は、transcript の旧版より優先する."""
        old = self.fork_setup()
        tp = self.home / "fork.jsonl"
        self.assertQuiet(self.fork_start(tp))
        self.assertSilent(self.read(self.cache / "p" / "1.1.0" / "skills" / "s" / "SKILL.md", sid="fork-1"))
        self.transcript(old)
        self.assertQuiet(self.fork_prompt(tp))

    def test_fork_adopts_transcript_once(self):
        """取り込んだ後に transcript が旧版の Read に変わっても、もう一度は読まない."""
        new = self.fork_setup().parents[3] / "1.1.0" / "skills" / "s" / "SKILL.md"
        tp = self.transcript(new)
        self.assertQuiet(self.fork_start(tp))
        self.transcript(self.cache / "p" / "1.0.0" / "skills" / "s" / "SKILL.md")
        self.assertQuiet(self.fork_prompt(tp))

    def test_fork_ignores_lines_that_are_not_parent_reads(self):
        """Read 以外・assistant 以外・キャッシュ外・壊れた行は拾わず、例外にもしない."""
        old = self.fork_setup()
        tool_use = {"type": "tool_use", "id": "t", "name": "Read", "input": {"file_path": str(old)}}
        noise = [
            "{broken /plugins/cache/ \"tool_use\"",
            json.dumps(["/plugins/cache/", "tool_use"]),
            json.dumps({"type": "user", "message": {"content": [tool_use]}}),
            json.dumps({"type": "assistant", "message": "/plugins/cache/ tool_use"}),
            json.dumps({"type": "assistant", "message": {"content": "/plugins/cache/ \"tool_use\""}}),
            json.dumps({"type": "assistant", "message": {"content": [
                "/plugins/cache/", {"type": "tool_use", "name": "Skill", "input": {"skill": "p:s"},
                                    "note": "/plugins/cache/"},
                {"type": "tool_use", "name": "Edit", "input": {"file_path": str(old)}},
                {"type": "tool_use", "name": "Read", "input": {"file_path": "/tmp/plugins/cache/x"}},
                {"type": "tool_use", "name": "Read", "input": "/plugins/cache/mp/p/1.0.0/skills/s/SKILL.md"}]}}),
        ]
        tp = self.transcript(extra_lines=noise)
        self.assertQuiet(self.fork_start(tp))
        self.assertQuiet(self.fork_prompt(tp))
        self.assertFalse(self.state_file("fork-1").exists())

    def test_fork_without_parent_reads_removes_state(self):
        """記録の無い状態ファイルを残さない（前段はファイルの有無だけで python を起動する）."""
        self.fork_setup()
        tp = self.transcript(extra_lines=[json.dumps({"type": "user", "message": {"content": "hi"}})])
        self.assertQuiet(self.fork_start(tp))
        self.assertFalse(self.state_file("fork-1").exists())
        self.assertQuiet(self.fork_prompt(tp))

    def skill_line(self, path, meta=True) -> str:
        entry = {"type": "user", "message": {"role": "user", "content": [
            {"type": "text", "text": f"Base directory for this skill: {path}\n\n# 手順"}]}}
        if meta:
            entry["isMeta"] = True
        return json.dumps(entry)

    def test_fork_notifies_from_parent_skill_injection(self):
        """親が Skill tool で使った skill は、注入された行のパスの版で知らせる."""
        old = self.fork_setup()
        tp = self.transcript(extra_lines=[self.skill_line(old.parent)])
        out = self.fork_start(tp).stdout
        self.assertIn("p: 1.0.0 → 1.1.0", out)
        self.assertIn("p:s", out)

    def test_fork_ignores_quoted_skill_line(self):
        """利用者の発言に同じ字面が引用されていても（isMeta でない行）拾わない."""
        old = self.fork_setup()
        tp = self.transcript(extra_lines=[self.skill_line(old.parent, meta=False),
                                          json.dumps({"type": "user", "isMeta": True, "message": {"content": [
                                              {"type": "text", "text": f"前置き Base directory for this skill: {old.parent}"}]}})])
        self.assertQuiet(self.fork_start(tp))
        self.assertFalse(self.state_file("fork-1").exists())

    def test_fork_skill_after_fork_does_not_hide_parent_read(self):
        """fork の後の Skill の記録（呼んだ時点の installed の版）は、transcript の旧版の Read より優先しない."""
        old = self.version_dir("p", "1.0.0")
        (old / "references").mkdir()
        (old / "references" / "r.md").write_text("r")
        self.version_dir("p", "1.1.0")
        self.install({"p": "1.1.0"})
        tp = self.home / "fork.jsonl"
        self.assertQuiet(self.fork_start(tp))
        self.assertSilent(self.skill("p:s", sid="fork-1"))
        self.transcript(old / "references" / "r.md")
        self.assertIn("p: 1.0.0 → 1.1.0", self.fork_prompt(tp).stdout)

    def test_fork_read_after_skill_beats_transcript(self):
        """fork の後に Skill で呼んでから新しい版を Read し直したなら、transcript の旧版より Read を勝たせる."""
        old = self.fork_setup()
        tp = self.home / "fork.jsonl"
        self.assertQuiet(self.fork_start(tp))
        self.assertSilent(self.skill("p:s", sid="fork-1"))
        self.assertSilent(self.read(self.cache / "p" / "1.1.0" / "skills" / "s" / "SKILL.md", sid="fork-1"))
        self.transcript(old)
        self.assertQuiet(self.fork_prompt(tp))

    def test_fork_skill_after_fork_keeps_parent_skill_version(self):
        """fork の後の Skill の記録は、transcript にある同じ skill の旧版を上書きしない（skill を名指しで知らせる）."""
        old = self.version_dir("p", "1.0.0", skills=("s", "t"))
        self.version_dir("p", "1.1.0", skills=("s", "t"))
        self.install({"p": "1.1.0"})
        tp = self.home / "fork.jsonl"
        self.assertQuiet(self.fork_start(tp))
        self.assertSilent(self.skill("p:s", sid="fork-1"))
        self.transcript(extra_lines=[self.skill_line(old / "skills" / "s"), self.skill_line(old / "skills" / "t")])
        out = self.fork_prompt(tp).stdout
        self.assertIn("p:s →", out)
        self.assertIn("p:t →", out)

    def test_skill_outside_fork_has_no_fork_marks(self):
        """fork の取り込みを待っていないセッションの記録には、取り込み用の印を書かない."""
        self.version_dir("p", "1.0.0")
        self.install({"p": "1.0.0"})
        self.assertSilent(self.skill("p:s"))
        rec = json.loads(self.state_file().read_text())["plugins"][f"p@{MP}"]
        self.assertNotIn("version_from", rec)
        self.assertNotIn("skills_from_skill", rec)

    def test_fork_skill_line_with_spaces_in_path(self):
        """CLAUDE_CONFIG_DIR に空白があっても、行末の空白があっても、注入行のパスを取る."""
        self.fork_setup()
        spaced = f"/home/a b/.claude/plugins/cache/{MP}/p/1.0.0/skills/s"
        line = json.dumps({"type": "user", "isMeta": True, "message": {"content": [
            {"type": "text", "text": f"Base directory for this skill: {spaced}  \n\n# 手順"}]}})
        out = self.fork_start(self.transcript(extra_lines=[line])).stdout
        self.assertIn("p: 1.0.0 → 1.1.0", out)
        self.assertIn("p:s →", out)

    def test_fork_last_read_wins_even_if_older(self):
        """版の大小ではなく、最後に読んだ版で判定する（新版の後で旧版を読み直せば知らせる）."""
        old = self.fork_setup()
        tp = self.transcript(self.cache / "p" / "1.1.0" / "skills" / "s" / "SKILL.md", old)
        self.assertIn("p: 1.0.0 → 1.1.0", self.fork_start(tp).stdout)

    def test_non_fork_start_does_not_create_state(self):
        """startup の payload の入れ子に `"source": "fork"` があっても、状態ファイルを作らない."""
        tp = self.transcript(self.fork_setup())
        res = self.run_hook({"session_id": "fork-1", "hook_event_name": "SessionStart", "source": "startup",
                             "transcript_path": str(tp), "extra": {"source": "fork"}},
                            env_extra=self.env(), args=("session-start",))
        self.assertQuiet(res)
        self.assertFalse(self.state_file("fork-1").exists())
        self.assertQuiet(self.fork_start(tp, source="resume"))
        self.assertFalse(self.state_file("fork-1").exists())

    # --- 置き場所・前段 ---

    def test_config_dir_follows_claude_config_dir(self):
        """CLAUDE_CONFIG_DIR が HOME/.claude と違っても、bash の前段と同じ場所に記録する."""
        self.cfg = self.home / "cfg"
        self.cache = self.cfg / "plugins" / "cache" / MP
        self.stale_setup()
        self.assertTrue(self.state_file().exists())
        self.assertFalse((self.home / ".claude").exists())
        self.assertIn("p: 1.0.0 → 1.1.0", self.prompt().stdout)

    def test_prompt_does_not_start_python_without_own_state(self):
        """発言のたびに走るので、自分の状態ファイルが無ければ python を起動しない."""
        path, marker = self.python_stub_path()
        sessions = self.cfg / "plugin-manager" / "sessions"
        sessions.mkdir(parents=True)
        env = {**self.env(), "PATH": path}
        payload = {"session_id": SID, "hook_event_name": "UserPromptSubmit", "prompt": "hi"}
        self.assertQuiet(self.run_hook(payload, env_extra=env, args=("prompt",)))
        self.assertFalse(marker.exists())
        # stub が呼ばれれば印が残ることの確認（上の不在が stub の不発でないこと）
        (sessions / f"{SID}.json").write_text("{}")
        self.run_hook(payload, env_extra=env, args=("prompt",))
        self.assertTrue(marker.exists())

    def test_prompt_for_missing_own_state_touches_nothing(self):
        """payload の中の別の session_id で前段を通っても、自分の状態が無ければ何も作らない."""
        sessions = self.cfg / "plugin-manager" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "other.json").write_text("{}")
        # prompt の本文は JSON の中で引用符がエスケープされ前段の grep に掛からないので、入れ子の object に置く
        res = self.run_hook({"session_id": SID, "hook_event_name": "UserPromptSubmit", "prompt": "hi",
                             "x": {"session_id": "other"}}, env_extra=self.env(), args=("prompt",))
        self.assertQuiet(res)
        self.assertEqual(sorted(p.name for p in sessions.iterdir()), ["other.json"])

    def test_non_object_payload_is_ignored(self):
        """JSON として正しくても object でない stdin は捨てる（例外にしない）."""
        sessions = self.cfg / "plugin-manager" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / f"{SID}.json").write_text("{}")
        for mode, payload in (("prompt", [{"session_id": SID}]),
                              ("record", [{"session_id": SID, "tool_name": "Skill"}])):
            self.assertQuiet(self.run_hook(raw=json.dumps(payload), env_extra=self.env(), args=(mode,)), mode)

    # --- record の入力の形 ---

    def test_skill_with_non_object_tool_input_is_not_recorded(self):
        self.install({"p": "1.0.0"})
        res = self.run_hook({"session_id": SID, "tool_name": "Skill", "tool_input": "p:s"},
                            env_extra=self.env(), args=("record",))
        self.assertQuiet(res)
        self.assertFalse(self.state_file().exists())

    def test_read_with_non_string_file_path_is_not_recorded(self):
        res = self.run_hook({"session_id": SID, "tool_name": "Read", "tool_input": {"file_path": 1},
                             "tool_response": f"{self.cache}/p/1.0.0/skills/s/SKILL.md"},
                            env_extra=self.env(), args=("record",))
        self.assertQuiet(res)
        self.assertFalse(self.state_file().exists())

    # --- installed_plugins.json の形 ---

    def test_silent_when_any_installed_value_is_not_list(self):
        """list でない値が 1 つでもあれば形の違うファイルとして全体を読まない（version 1 との混在）."""
        self.stale_setup()
        path = self.cfg / "plugins" / "installed_plugins.json"
        data = json.loads(path.read_text())
        data["plugins"][f"q@{MP}"] = {}
        path.write_text(json.dumps(data))
        self.assertQuiet(self.prompt())

    def test_broken_installed_entry_is_skipped(self):
        """entry の list に object でないものが混ざっていても、残りの entry で知らせる."""
        self.stale_setup()
        self.install({"p": ["x", {"scope": "user", "installPath": str(self.cache / "p" / "1.1.0"),
                                  "version": "1.1.0"}]})
        res = self.prompt()
        self.assertIn("p: 1.0.0 → 1.1.0", res.stdout)
        self.assertNotIn(PY_ERROR, res.stderr)

    def test_user_scope_entry_is_preferred(self):
        """project scope の entry が先に並んでいても、user scope の版を新しい版とする."""
        self.stale_setup()
        self.version_dir("p", "1.2.0")
        self.install({"p": [
            {"scope": "project", "installPath": str(self.cache / "p" / "1.2.0"), "version": "1.2.0",
             "projectPath": "/x"},
            {"scope": "user", "installPath": str(self.cache / "p" / "1.1.0"), "version": "1.1.0"},
        ]})
        out = self.prompt().stdout
        self.assertIn("p: 1.0.0 → 1.1.0", out)
        self.assertNotIn("1.2.0", out)

    def test_silent_without_install_path(self):
        self.stale_setup()
        self.install({"p": [{"scope": "user", "version": "1.1.0"}]})
        self.assertQuiet(self.prompt())

    # --- 通知の判定 ---

    def test_empty_recorded_version_is_not_notified(self):
        self.version_dir("p", "1.1.0")
        self.install({"p": "1.1.0"})
        self.state_file().parent.mkdir(parents=True)
        self.state_file().write_text(json.dumps({"schema_version": 1, "session_id": SID,
                                                 "plugins": {f"p@{MP}": {"version": ""}}, "notified": {}}))
        self.assertQuiet(self.prompt())

    def test_changelog_with_non_semver_old_version(self):
        """旧版の片方が semver でなくても、通知と見出しを出す（古さの比較はしない）."""
        a = self.version_dir("p", "dev", skills=("a",))
        b = self.version_dir("p", "1.0.0", skills=("b",))
        self.version_dir("p", "1.1.0", skills=("a", "b"), changelog="## [1.1.0]\n## [1.0.0]\n")
        self.install({"p": "1.0.0"})
        self.read(a / "skills" / "a" / "SKILL.md")
        self.read(b / "skills" / "b" / "SKILL.md")
        self.install({"p": "1.1.0"})
        res = self.prompt()
        self.assertIn("p: 1.0.0, dev → 1.1.0", res.stdout)
        self.assertIn("## [1.1.0]", res.stdout)
        self.assertNotIn(PY_ERROR, res.stderr)

    def test_changelog_stops_at_non_semver_old_version_heading(self):
        """semver でない旧版でも、その見出しに着いたら止める（それより下は読んだ版に入っていた変更）."""
        old = self.version_dir("p", "dev")
        self.version_dir("p", "1.1.0", changelog="## [1.1.0]\n## [dev]\n## [0.9.0]\n")
        self.install({"p": "dev"})
        self.read(old / "skills" / "s" / "SKILL.md")
        self.install({"p": "1.1.0"})
        out = self.prompt().stdout
        self.assertIn("## [1.1.0]", out)
        self.assertNotIn("## [0.9.0]", out)

    def test_changelog_omits_heading_of_same_release_as_old_version(self):
        """build metadata だけ違う旧版（semver では同じ版）の見出しは、新しい変更として出さない."""
        old = self.version_dir("p", "1.0.0+b5")
        self.version_dir("p", "1.1.0", changelog="## [1.1.0]\n## [1.0.0]\n## [0.9.0]\n")
        self.install({"p": "1.0.0+b5"})
        self.read(old / "skills" / "s" / "SKILL.md")
        self.install({"p": "1.1.0"})
        out = self.prompt().stdout
        self.assertIn("## [1.1.0]", out)
        self.assertNotIn("## [1.0.0]", out)

    # --- 状態の保存 ---

    def test_prompt_without_change_does_not_rewrite_state(self):
        """知らせることも rearm も無い発言では状態ファイルを書き直さない（毎回の発言で走る）."""
        self.stale_setup()
        self.prompt()
        ino = self.state_file().stat().st_ino
        self.assertQuiet(self.prompt())
        self.assertEqual(self.state_file().stat().st_ino, ino)

    def test_compact_rearm_is_saved_without_installed_file(self):
        """installed_plugins.json が読めない回の compaction でも、通知済みを消したことは残す."""
        self.stale_setup()
        self.prompt()
        installed = self.cfg / "plugins" / "installed_plugins.json"
        saved = installed.read_text()
        installed.unlink()
        self.assertQuiet(self.compact())
        installed.write_text(saved)
        self.assertIn("1.0.0 → 1.1.0", self.prompt().stdout)

    def test_rearm_window_boundary_is_exclusive(self):
        """前回の rearm からちょうど REARM_WINDOW（120 秒）なら、まだ窓の中として通知済みを消さない."""
        self.stale_setup()
        self.prompt()
        base = json.loads(self.state_file().read_text())
        # python の now と同じ秒で走った回だけを判定に使う（秒をまたぐと差が 121 になる）
        for _ in range(5):
            t0 = int(time.time())
            self.state_file().write_text(json.dumps({**base, "rearm_at": t0 - 120}))
            res = self.compact()
            if int(time.time()) == t0:
                break
        else:
            self.skipTest("hook の実行が毎回秒をまたいだ")
        self.assertQuiet(res)


if __name__ == "__main__":
    unittest.main()
