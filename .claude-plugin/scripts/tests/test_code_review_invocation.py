#!/usr/bin/env python3
"""呼び出し経路の判定（`code-review/scripts/lib/invocation.py`）の単体テスト.

publish が payload の `invocation` に載せる判定を純関数として見る（GitHub issue #265）。publish 経由の
統合は `test_code_review_scripts.py` の `InvocationPublishTest` が持つ。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LIB = REPO / "code-review" / "scripts" / "lib"
sys.path.insert(0, str(LIB))

from invocation import judge_entries  # noqa: E402

START = 'bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" start'


def assistant(*blocks: dict) -> dict:
    return {"type": "assistant", "message": {"content": list(blocks)}}


def start() -> dict:
    return assistant({"type": "tool_use", "name": "Bash", "input": {"command": START}})


def skill(name: str) -> dict:
    return assistant({"type": "tool_use", "name": "Skill", "input": {"skill": name}})


def prompt(body: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": body}}


def slash(name: str) -> dict:
    """実 transcript の形: command 起動の行と、isMeta の本文展開の行の 2 行."""
    return prompt("<command-message>%s</command-message>\n<command-name>/%s</command-name>"
                  % (name, name))


def expanded(body: str = "self-review スキルを使用して…") -> dict:
    return {"type": "user", "isMeta": True,
            "message": {"role": "user", "content": [{"type": "text", "text": body}]}}


def tool_result() -> dict:
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t", "content": "Launching skill: x"}]}}


def via(entries: list) -> str:
    return judge_entries(entries)["via"]


def parent(entries: list):
    return judge_entries(entries)["parent"]


class ViaTest(unittest.TestCase):
    def test_four_routes(self):
        self.assertEqual(via([slash("code-review:self-review"), expanded(), start()]), "slash")
        self.assertEqual(via([prompt("y"), skill("code-review:self-review"), tool_result(), start()]),
                         "skill-tool")
        self.assertEqual(via([prompt("self-review 要る？ → y"), start()]), "inline")
        self.assertEqual(via([prompt("y"), skill("code-review:self-review")]), "unknown",
                         "start が無い")

    def test_slash_wins_over_the_skill_call_it_triggers(self):
        """slash の本文が「スキルを使って」と言うので、直後に同じ skill を Skill で呼び直す（実測）."""
        self.assertEqual(via([slash("code-review:self-review"), expanded(),
                              skill("code-review:self-review"), tool_result(), start()]), "slash")

    def test_a_human_prompt_bounds_the_search(self):
        self.assertEqual(via([slash("code-review:self-review"), expanded(), start(),
                              prompt("もう一度"), start()]), "inline")
        self.assertEqual(via([slash("code-review:self-review"), prompt("続けて"),
                              skill("code-review:self-review"), start()]), "skill-tool")

    def test_another_slash_bounds_the_search(self):
        self.assertEqual(via([slash("code-review:self-review"), slash("issue-workflow:start"),
                              skill("code-review:self-review"), start()]), "skill-tool")
        self.assertEqual(via([slash("code-review:self-review"), slash("issue-workflow:start"),
                              start()]), "inline")

    def test_notifications_are_not_human_prompts(self):
        note = prompt("<task-notification>\n<status>completed</status>\n</task-notification>")
        self.assertEqual(via([slash("code-review:self-review"), expanded(), note, start()]), "slash")

    def test_the_previous_review_bounds_the_search(self):
        """同じターンで start を 2 回呼んだら、2 回目は前の start より後だけを見る."""
        self.assertEqual(via([slash("code-review:self-review"), expanded(), start(), start()]),
                         "inline")
        self.assertEqual(via([slash("code-review:self-review"), start(),
                              skill("code-review:review"), start()]), "skill-tool")

    def test_a_non_code_review_skill_is_not_the_route(self):
        self.assertEqual(via([prompt("y"), skill("feature-dev:feature-dev"), start()]), "inline")
        self.assertEqual(via([slash("design-doc:design-review"), start()]), "inline")

    def test_a_start_inside_a_heredoc_is_not_a_start(self):
        heredoc = assistant({"type": "tool_use", "name": "Bash", "input": {
            "command": "cat > x.py <<'PY'\n" + START + "\nPY"}})
        self.assertEqual(via([prompt("y"), skill("code-review:self-review"), heredoc]), "unknown")


class ParentTest(unittest.TestCase):
    def test_the_last_non_code_review_skill_before_start(self):
        self.assertEqual(parent([slash("issue-workflow:start"), skill("feature-dev:feature-dev"),
                                 skill("code-review:self-review"), start()]),
                         "feature-dev:feature-dev")
        self.assertEqual(parent([slash("issue-workflow:start"), expanded(),
                                 skill("code-review:self-review"), start()]),
                         "issue-workflow:start")

    def test_none_when_only_code_review_was_invoked(self):
        self.assertIsNone(parent([slash("code-review:self-review"), expanded(),
                                  skill("code-review:self-review"), start()]))
        self.assertIsNone(parent([prompt("y"), start()]))

    def test_names_outside_the_marketplace_become_other(self):
        self.assertEqual(parent([skill("my-private:secret-flow"), start()]), "other")
        self.assertEqual(parent([skill("simplify"), start()]), "other")
        self.assertEqual(parent([skill("feature-dev:Feature Dev"), start()]), "other")
        self.assertEqual(parent([slash("acme-internal:deploy"), start()]), "other")

    def test_builtin_slash_commands_are_not_skills(self):
        self.assertEqual(parent([skill("feature-dev:feature-dev"), prompt(
            "<command-name>/clear</command-name>"), start()]), "feature-dev:feature-dev")

    def test_skills_after_the_start_are_ignored(self):
        self.assertIsNone(parent([prompt("y"), start(), skill("failure-journal:retro")]))


class MarketplaceListTest(unittest.TestCase):
    def test_the_allowlist_matches_the_plugins_in_this_repo(self):
        """プラグインを足したら `MARKETPLACE_PLUGINS` と計測ストアの語彙も足す（足さないと parent が other に落ちる）."""
        from invocation import MARKETPLACE_PLUGINS
        plugins = {p.parent.parent.name for p in REPO.glob("*/.claude-plugin/plugin.json")}
        self.assertEqual(set(MARKETPLACE_PLUGINS), plugins)


class CliTest(unittest.TestCase):
    def run_cli(self, path: str) -> dict:
        out = subprocess.run([sys.executable, str(LIB / "invocation.py"), path],
                             capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    def test_reads_a_transcript_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.jsonl"
            lines = [slash("code-review:self-review"), expanded(), {"type": "attachment"},
                     skill("code-review:self-review"), start()]
            p.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in lines)
                         + "\nnot json\n", encoding="utf-8")
            self.assertEqual(self.run_cli(str(p)), {"via": "slash", "parent": None})

    def test_an_unreadable_transcript_is_unknown(self):
        self.assertEqual(self.run_cli("/nonexistent/s.jsonl"), {"via": "unknown", "parent": None})


if __name__ == "__main__":
    unittest.main()
