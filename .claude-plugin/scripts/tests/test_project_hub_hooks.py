#!/usr/bin/env python3
"""project-hub の hook スクリプトの回帰テスト.

- `inject-state.sh`（SessionStart / PostCompact）— stdin の session_id が hub.json と一致した
  セッションにだけ state.md を注入する。**すべてのセッションの開始で走る**ので、黙る条件
  （hub でないセッション・root も hub.json も無い・壊れた入力・closed の PJ・python3 が無い）を厚く書く。
  hub でないセッションには、cwd の repo が未登録の PJ に入っているときだけ紐付けの案内を出す
- `notify-pending.sh`（UserPromptSubmit）— hub のセッションに、未取り込みの report があるときだけ
  取り込むよう促す。**すべての発言で走る**ので、python を起動する前の絞り込みも見る
- `check-deps.sh` — python3 が無いときだけ知らせる。任意の gh が無くても黙る

root は必ず `PROJECT_HUB_DIR` で使い捨ての dir に向ける（`hook_harness` は HOME を隔離しない）。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from hook_harness import HookTestCase, TempGitRepo

SID_HUB = "11111111-1111-4111-8111-111111111111"
SID_OTHER = "22222222-2222-4222-8222-222222222222"


class InjectStateTest(HookTestCase):
    PLUGIN = "project-hub"
    SCRIPT = "hooks/scripts/inject-state.sh"

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / "hub-root"

    def make_project(self, name: str = "pj", session_id: str = SID_HUB, status: str = "active",
                     state: str | None = None, journal: list[dict] | None = None,
                     inbox: int = 0) -> Path:
        pdir = self.root / name
        (pdir / "inbox" / "done").mkdir(parents=True)
        (pdir / "config.json").write_text(json.dumps({"project": name, "status": status}),
                                          encoding="utf-8")
        (pdir / "hub.json").write_text(json.dumps({"session_id": session_id, "name": "hub"}),
                                       encoding="utf-8")
        (pdir / "journal.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in journal or []), encoding="utf-8")
        if state is not None:
            (pdir / "state.md").write_text(state, encoding="utf-8")
        for i in range(inbox):
            (pdir / "inbox" / f"2026102{i}T000000000000Z-x.json").write_text("{}", encoding="utf-8")
        return pdir

    def fire(self, session_id: str | None = SID_HUB, event: str = "SessionStart", raw: str | None = None,
             env_extra: dict | None = None):
        payload = {"hook_event_name": event, "source": "startup"}
        if session_id is not None:
            payload["session_id"] = session_id
        env = {"PROJECT_HUB_DIR": str(self.root), "HOME": str(self.tmp / "home")}
        env.update(env_extra or {})
        return self.run_hook(payload, raw=raw, env_extra=env)

    def assertQuiet(self, res):
        self.assertSilent(res)
        self.assertNotIn("Unexpected", res.stderr)

    STATE = ("<!-- project-hub-state generated_at=2026-10-21T00:00:00Z journal_lines=2 -->\n"
             "# project-hub: pj\n\n- 表の本文\n")
    JOURNAL = [{"kind": "fact"}, {"kind": "fact"}, {"kind": "report"}, {"kind": "relay"},
               {"kind": "report"}]

    def test_the_hub_session_gets_the_state_and_what_came_after(self):
        self.make_project(state=self.STATE, journal=self.JOURNAL, inbox=2)
        res = self.fire()
        self.assertEqual(res.returncode, 0, res)
        out = res.stdout
        self.assertIn("このセッションは PJ「pj」の hub", out)
        self.assertIn("- 表の本文", out)
        self.assertNotIn("<!-- project-hub-state", out, "機械用の見出しは注入しない")
        # state.md が 2 行目まで反映済みなので、残りの 3 行を kind 別に数える
        self.assertIn("増えた journal（kind 別）: relay 1・report 2", out)
        self.assertIn("未取り込みの report: 2 件", out)
        self.assertNotIn("Unexpected", res.stderr)

    def test_post_compact_injects_the_same(self):
        self.make_project(state=self.STATE)
        res = self.fire(event="PostCompact")
        self.assertIn("- 表の本文", res.stdout)
        self.assertIn("増えた journal（kind 別）: なし", res.stdout)

    def test_a_hub_without_state_md_is_told_to_run_status(self):
        self.make_project(journal=self.JOURNAL)
        res = self.fire()
        self.assertIn("state.md がまだ無い", res.stdout)
        self.assertIn("fact 2・relay 1・report 2", res.stdout)

    def test_only_the_projects_this_session_is_the_hub_of(self):
        # 飛ばされる側を並びの先頭に置く（飛ばした後で走査を打ち切る退行を捕まえる）
        self.make_project("aaa-theirs", session_id=SID_OTHER, state="# theirs\n")
        self.make_project("mine", state=self.STATE)
        self.make_project("mine2", state=self.STATE.replace("表の本文", "二つ目の表"))
        res = self.fire()
        self.assertIn("PJ「mine」", res.stdout)
        self.assertIn("二つ目の表", res.stdout, "hub を務める PJ が複数あれば全部出す")
        self.assertNotIn("theirs", res.stdout)

    def test_a_broken_project_does_not_stop_the_others(self):
        broken = self.make_project("aaa-broken", state=self.STATE)
        (broken / "state.md").write_bytes(b"\xff\xfe broken")
        self.make_project("mine", state=self.STATE)
        res = self.fire()
        self.assertIn("PJ「mine」", res.stdout)
        self.assertNotIn("Unexpected", res.stderr)
        self.assertIn("aaa-broken", res.stderr)

    def test_a_broken_config_of_a_project_this_session_is_not_the_hub_of_is_not_read(self):
        other = self.make_project("aaa-theirs", session_id=SID_OTHER)
        (other / "config.json").write_bytes(b"\xff broken")
        self.make_project("mine", state=self.STATE)
        res = self.fire()
        self.assertIn("PJ「mine」", res.stdout)
        self.assertNotIn("aaa-theirs", res.stderr, "hub でない PJ の壊れた config で騒がない")

    # --- 黙る条件（同じ root で鳴る側は上のテスト） ---

    def test_another_session_is_silent(self):
        self.make_project(state=self.STATE)
        self.assertQuiet(self.fire(session_id=SID_OTHER))
        self.assertIn("表の本文", self.fire().stdout, "対照: hub のセッションでは鳴る")

    def test_no_root_is_silent(self):
        self.assertQuiet(self.fire())

    def test_a_root_without_any_hub_is_silent(self):
        (self.root / "pj").mkdir(parents=True)
        self.assertQuiet(self.fire())

    def test_a_project_that_is_not_active_is_silent(self):
        for status in ("closed", "Active"):
            with self.subTest(status=status):
                self.root = self.tmp / status
                self.make_project(status=status, state=self.STATE)
                self.assertQuiet(self.fire())

    def test_broken_files_are_silent(self):
        pdir = self.make_project(state=self.STATE)
        (pdir / "hub.json").write_text("{broken", encoding="utf-8")
        self.assertQuiet(self.fire())
        (pdir / "hub.json").write_text(json.dumps({"session_id": SID_HUB}), encoding="utf-8")
        (pdir / "config.json").write_text("[]", encoding="utf-8")
        self.assertQuiet(self.fire())

    def test_broken_or_incomplete_stdin_is_silent(self):
        self.make_project(state=self.STATE)
        self.assertQuiet(self.fire(raw="{not json"))
        self.assertQuiet(self.fire(session_id=None))
        self.assertQuiet(self.fire(raw="[]"))
        self.assertQuiet(self.fire(session_id=""))

    def test_a_missing_session_id_never_matches_a_hub_json_without_one(self):
        # 壊れた hub.json の「無い」「空」と、stdin の「無い」「空」を一致とみなさない
        pdir = self.make_project(state=self.STATE)
        for hub, session_id in (({"name": "hub"}, None), ({"session_id": "", "name": "hub"}, "")):
            with self.subTest(hub=hub):
                (pdir / "hub.json").write_text(json.dumps(hub), encoding="utf-8")
                self.assertQuiet(self.fire(session_id=session_id))

    def test_python_is_not_launched_on_a_machine_without_a_hub(self):
        # 大半のセッションは hub を持たない。そこで python を起動しないことを stub で見る
        bin_dir = Path(self.path_with_only())
        stub = bin_dir / "python3"
        stub.write_text("#!/bin/bash\necho LAUNCHED\n", encoding="utf-8")
        os.chmod(stub, 0o755)
        (self.root / "pj").mkdir(parents=True)
        self.assertQuiet(self.fire(env_extra={"PATH": str(bin_dir)}))
        self.make_project("pj2", state=self.STATE)
        res = self.fire(env_extra={"PATH": str(bin_dir)})
        self.assertIn("LAUNCHED", res.stdout, "対照: hub.json があれば python を起動する")

    def test_without_python3_it_is_silent(self):
        self.make_project(state=self.STATE)
        res = self.fire(env_extra={"PATH": self.path_with_only()})
        self.assertQuiet(res)
        res = self.fire(env_extra={"PATH": self.path_with_only("python3")})
        self.assertIn("表の本文", res.stdout, "対照: python3 を引ければ鳴る")

    def test_the_root_follows_claude_config_dir(self):
        self.root = self.tmp / "cfg" / "project-hub"
        self.make_project(state=self.STATE)
        res = self.fire(env_extra={"PROJECT_HUB_DIR": "", "CLAUDE_CONFIG_DIR": str(self.tmp / "cfg")})
        self.assertIn("表の本文", res.stdout)

    def test_an_unregistered_session_in_a_project_repo_gets_the_hello_hint(self):
        # 作業側（issue-workflow の start などで始めた）への紐付けの案内（GitHub issue #315）。
        # 判定の境界は test_project_hub_scripts の WorkerHintTest
        git_repo = TempGitRepo()
        repo = git_repo.__enter__()
        self.addCleanup(git_repo.__exit__, None, None, None)
        git_repo.commit("init")
        pdir = self.make_project(session_id=SID_HUB)
        config = json.loads((pdir / "config.json").read_text(encoding="utf-8"))
        config["repos"] = [{"path": str(repo), "base": "main"}]
        (pdir / "config.json").write_text(json.dumps(config), encoding="utf-8")
        env = {"PROJECT_HUB_DIR": str(self.root), "HOME": str(self.tmp / "home")}
        payload = {"hook_event_name": "SessionStart", "source": "startup",
                   "session_id": SID_OTHER, "cwd": str(repo)}
        res = self.run_hook(payload, env_extra=env)
        self.assertIn("state=hello", res.stdout)
        self.assertNotIn("Unexpected", res.stderr)
        payload["cwd"] = str(self.tmp)
        self.assertQuiet(self.run_hook(payload, env_extra=env))


class NotifyPendingTest(HookTestCase):
    """`notify-pending.sh`（UserPromptSubmit）。**すべての発言で走る**ので黙る条件を厚く書く（GitHub issue #314）."""

    PLUGIN = "project-hub"
    SCRIPT = "hooks/scripts/notify-pending.sh"

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / "hub-root"

    def make_project(self, name: str = "pj", session_id: str = SID_HUB, status: str = "active",
                     inbox: int = 1) -> Path:
        pdir = self.root / name
        (pdir / "inbox" / "done").mkdir(parents=True)
        (pdir / "config.json").write_text(json.dumps({"project": name, "status": status}), encoding="utf-8")
        (pdir / "hub.json").write_text(json.dumps({"session_id": session_id, "name": "hub"}), encoding="utf-8")
        for i in range(inbox):
            (pdir / "inbox" / f"2026102{i}T000000000000Z-x.json").write_text("{}", encoding="utf-8")
        return pdir

    def fire(self, session_id: str | None = SID_HUB, raw: str | None = None, env_extra: dict | None = None):
        payload = {"hook_event_name": "UserPromptSubmit",
                   "prompt": '<cross-session-message from-name="w">report を置いた</cross-session-message>'}
        if session_id is not None:
            payload["session_id"] = session_id
        env = {"PROJECT_HUB_DIR": str(self.root), "HOME": str(self.tmp / "home")}
        env.update(env_extra or {})
        return self.run_hook(payload, raw=raw, env_extra=env)

    def assertQuiet(self, res):
        self.assertSilent(res)
        self.assertNotIn("Unexpected", res.stderr)

    def test_the_hub_with_pending_reports_is_told_to_ingest(self):
        self.make_project(inbox=2)
        res = self.fire()
        self.assertEqual(res.returncode, 0, res)
        self.assertIn("未取り込みの report がある", res.stdout)
        self.assertIn("PJ「pj」: 2 件", res.stdout)
        self.assertIn("ingest --project 'pj'", res.stdout)
        self.assertNotIn("Unexpected", res.stderr)

    def test_a_pretty_printed_stdin_still_finds_the_session(self):
        self.make_project()
        raw = json.dumps({"session_id": SID_HUB, "prompt": "x"}, indent=2)
        self.assertIn("PJ「pj」", self.fire(raw=raw).stdout)

    # --- 黙る条件 ---

    def test_another_session_is_silent(self):
        self.make_project()
        self.assertQuiet(self.fire(session_id=SID_OTHER))
        self.assertIn("PJ「pj」", self.fire().stdout, "対照: hub のセッションでは鳴る")

    def test_nothing_pending_or_a_closed_project_is_silent(self):
        self.make_project(inbox=0)
        self.assertQuiet(self.fire())
        self.root = self.tmp / "closed"
        self.make_project(status="closed")
        self.assertQuiet(self.fire())

    def test_no_root_or_no_hub_is_silent(self):
        self.assertQuiet(self.fire())
        (self.root / "pj").mkdir(parents=True)
        self.assertQuiet(self.fire())

    def test_broken_or_incomplete_stdin_is_silent(self):
        self.make_project()
        for raw in ("{not json", "[]", json.dumps({"session_id": ""}), json.dumps({"prompt": "x"})):
            with self.subTest(raw=raw):
                self.assertQuiet(self.fire(raw=raw))

    def test_a_session_id_only_inside_the_prompt_does_not_count(self):
        # stdin の文面に hub の id を書いても、session_id の欄でなければ hub とみなさない
        self.make_project()
        raw = json.dumps({"session_id": SID_OTHER, "prompt": f'"session_id": "{SID_HUB}"'})
        self.assertQuiet(self.fire(raw=raw))

    def test_python_is_not_launched_unless_a_hub_json_names_this_session(self):
        bin_dir = Path(self.path_with_only())
        stub = bin_dir / "python3"
        stub.write_text("#!/bin/bash\necho LAUNCHED\n", encoding="utf-8")
        os.chmod(stub, 0o755)
        self.make_project(session_id=SID_OTHER)
        self.assertQuiet(self.fire(env_extra={"PATH": str(bin_dir)}))
        self.make_project("pj2")
        res = self.fire(env_extra={"PATH": str(bin_dir)})
        self.assertIn("LAUNCHED", res.stdout, "対照: この session_id を含む hub.json があれば python を起動する")

    def test_without_python3_it_is_silent(self):
        self.make_project()
        self.assertQuiet(self.fire(env_extra={"PATH": self.path_with_only()}))
        res = self.fire(env_extra={"PATH": self.path_with_only("python3")})
        self.assertIn("PJ「pj」", res.stdout, "対照: python3 を引ければ鳴る")


class CheckDepsTest(HookTestCase):
    PLUGIN = "project-hub"
    SCRIPT = "hooks/scripts/check-deps.sh"

    def test_missing_python3_is_reported(self):
        res = self.run_hook({}, env_extra={"PATH": self.path_with_only()})
        self.assertIn("python3", res.stdout)
        self.assertIn("[ERROR]", res.stdout)

    def test_optional_gh_missing_is_silent(self):
        res = self.run_hook({}, env_extra={"PATH": self.path_with_only("python3")})
        self.assertSilent(res)
        self.assertNotIn("Unexpected", res.stderr)


if __name__ == "__main__":
    unittest.main()
