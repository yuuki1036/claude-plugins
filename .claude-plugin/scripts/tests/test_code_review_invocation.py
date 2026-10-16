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


def skill(name: str, args: str | None = None) -> dict:
    inp = {"skill": name}
    if args is not None:
        inp["args"] = args
    return assistant({"type": "tool_use", "name": "Skill", "input": inp})


def prompt(body: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": body}}


def slash(name: str, args: str | None = None) -> dict:
    """実 transcript の形: command 起動の行と、isMeta の本文展開の行の 2 行."""
    tail = "" if args is None else "\n<command-args>%s</command-args>" % args
    return prompt("<command-message>%s</command-message>\n<command-name>/%s</command-name>%s"
                  % (name, name, tail))


def expanded(body: str = "self-review スキルを使用して…") -> dict:
    return {"type": "user", "isMeta": True,
            "message": {"role": "user", "content": [{"type": "text", "text": body}]}}


def tool_result() -> dict:
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t", "content": "Launching skill: x"}]}}


def uid(entry: dict, value: str) -> dict:
    return dict(entry, uuid=value)


def via(entries: list) -> str:
    return judge_entries(entries)["via"]


def parent(entries: list):
    return judge_entries(entries)["parent"]


def rereview(entries: list):
    return judge_entries(entries)["rereview"]


class ViaTest(unittest.TestCase):
    def test_four_routes(self):
        self.assertEqual(via([slash("code-review:self-review"), expanded(), start()]), "slash")
        self.assertEqual(via([prompt("y"), skill("code-review:self-review"), tool_result(), start()]),
                         "skill-tool")
        self.assertEqual(via([prompt("self-review 要る？ → y"), start()]), "inline")
        self.assertEqual(via([prompt("y"), skill("code-review:self-review")]), "unknown",
                         "start が無い")

    def test_slash_in_list_content(self):
        """発話の content が text ブロックの配列でも slash と読む（#267: `== "text"` の反転が生きていた）."""
        body = slash("code-review:self-review")["message"]["content"]
        listed = {"type": "user", "message": {"role": "user",
                                              "content": [{"type": "text", "text": body}]}}
        self.assertEqual(via([listed, expanded(), start()]), "slash")

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


class ParentBoundaryTest(unittest.TestCase):
    """遡りをレビューを頼む人間の発話で止める（GitHub issue #301）.

    境界が無かった頃は、利用者の「self-review 回して」を数時間前の feature-dev / writing-polish の
    配下に数えていた。止めるのはレビューを頼む発話だけで、phase 境界の「OK」は越える。
    """

    def test_a_prompt_asking_for_a_review_stops_the_search(self):
        for body in ("self-review 回して", "一応セルフレビューして", "Review please", "/review の結果を見せて"):
            with self.subTest(body=body):
                self.assertIsNone(parent([skill("writing-polish:writing-polish"), prompt(body),
                                          skill("code-review:self-review"), start()]))

    def test_a_code_review_slash_stops_the_search(self):
        """slash で頼んだ回（実測: 前日の feature-dev に当たっていた）."""
        self.assertIsNone(parent([skill("feature-dev:feature-dev"), slash("code-review:self-review"),
                                  expanded(), skill("code-review:self-review"), start()]))

    def test_phase_boundary_prompts_are_crossed(self):
        """どの発話でも止めると、feature-dev の Phase 6 の初回 self-review が parent を失う."""
        self.assertEqual(parent([slash("feature-dev:feature-dev"), expanded(), prompt("OK"),
                                 prompt("進めて"), skill("code-review:self-review", "--embed"), start()]),
                         "feature-dev:feature-dev")

    def test_words_that_only_contain_review_do_not_stop(self):
        self.assertEqual(parent([skill("feature-dev:feature-dev"), prompt("preview を確認した。進めて"),
                                 skill("code-review:self-review"), start()]),
                         "feature-dev:feature-dev")

    def test_notifications_do_not_stop(self):
        note = prompt("<task-notification>\n<summary>review finished</summary>\n</task-notification>")
        self.assertEqual(parent([skill("feature-dev:feature-dev"), note,
                                 skill("code-review:self-review"), start()]),
                         "feature-dev:feature-dev")

    def test_another_plugins_slash_named_review_is_a_parent(self):
        """`design-review` は skill の起動で、code-review を頼む発話ではない."""
        self.assertEqual(parent([slash("design-doc:design-review"), expanded(),
                                 skill("code-review:self-review"), start()]),
                         "design-doc:design-review")


class ReplayedLinesTest(unittest.TestCase):
    """同じ `uuid` の行は最初の 1 行だけを読む（GitHub issue #301）.

    transcript には、セッションの先頭からの行が同じ `uuid` のまま後ろへ書き足されることがある。
    """

    def test_a_replayed_skill_is_not_the_parent(self):
        """実測の形: 境界が無いだけなら writing-polish になる回が、再生された前日の feature-dev に当たった."""
        fd = uid(skill("feature-dev:feature-dev"), "u1")
        entries = [fd, uid(prompt("PR 本文を直して"), "u2"), uid(skill("writing-polish:writing-polish"), "u3"),
                   fd, uid(skill("code-review:self-review"), "u4"), uid(start(), "u5")]
        self.assertEqual(parent(entries), "writing-polish:writing-polish")

    def test_a_replayed_prompt_does_not_bound_a_skill_procedure(self):
        """G-V ループの途中に再生された発話を、利用者が挟んだ発話と読まない."""
        head = uid(prompt("機能を作って"), "u1")
        entries = [head, uid(skill("feature-dev:feature-dev"), "u2"), uid(start(), "u3"), head,
                   uid(skill("code-review:self-review", "--embed --rereview"), "u4"), uid(start(), "u5")]
        self.assertIs(rereview(entries), True)

    def test_a_replayed_start_is_not_the_previous_review(self):
        first = uid(start(), "u2")
        entries = [uid(prompt("y"), "u1"), first, uid(slash("code-review:self-review"), "u3"),
                   uid(expanded(), "u4"), first, uid(start(), "u5")]
        self.assertEqual(via(entries), "slash", "再生された start を前のレビューにして slash を見落とした")

    def test_lines_without_a_uuid_are_all_kept(self):
        self.assertEqual(via([slash("code-review:self-review"), expanded(), expanded(), start()]), "slash")
        self.assertEqual(parent([skill("feature-dev:feature-dev"), skill("feature-dev:feature-dev"),
                                 start()]), "feature-dev:feature-dev")


class MarketplaceListTest(unittest.TestCase):
    def test_the_allowlist_matches_the_plugins_in_this_repo(self):
        """プラグインを足したら `MARKETPLACE_PLUGINS` と計測ストアの語彙も足す（足さないと parent が other に落ちる）."""
        from invocation import CURRENT_PLUGINS
        plugins = {p.parent.parent.name for p in REPO.glob("*/.claude-plugin/plugin.json")}
        self.assertEqual(set(CURRENT_PLUGINS), plugins)

    def test_a_former_name_is_still_a_parent(self):
        """改名前の transcript の呼び出し元を other に落とさない（claude-meta → harness-keeper）."""
        from invocation import CURRENT_PLUGINS, FORMER_PLUGINS
        self.assertFalse(FORMER_PLUGINS & CURRENT_PLUGINS, "旧名がいまの名前と重なっている")
        self.assertEqual(parent([prompt("x"), skill("claude-meta:eval-runner"), start()]),
                         "claude-meta:eval-runner")
        self.assertEqual(parent([prompt("x"), skill("harness-keeper:eval-runner"), start()]),
                         "harness-keeper:eval-runner")


class RereviewTest(unittest.TestCase):
    """修正を確かめる再レビューの申告（`--rereview`）を読む（GitHub issue #296）."""

    def test_the_flag_in_the_skill_args(self):
        self.assertIs(rereview([skill("feature-dev:feature-dev"),
                                skill("code-review:self-review", "--focus x --embed --rereview"),
                                tool_result(), start()]), True)

    def test_the_flag_in_the_slash_args(self):
        self.assertIs(rereview([slash("code-review:self-review", "--rereview"), expanded(), start()]), True)

    def test_the_slash_args_count_even_if_the_skill_call_drops_them(self):
        """slash の本文に従って Skill を呼び直すとき、引数が落ちることがある（slash 側の申告を読む）."""
        self.assertIs(rereview([slash("code-review:self-review", "--embed --rereview"), expanded(),
                                skill("code-review:self-review", "--embed"), tool_result(), start()]), True)

    def test_no_flag_is_false(self):
        self.assertIs(rereview([skill("code-review:self-review", "--focus x --embed"), start()]), False)
        self.assertIs(rereview([skill("code-review:self-review"), start()]), False)
        self.assertIs(rereview([slash("code-review:self-review", "--embed"), expanded(), start()]), False)
        self.assertIs(rereview([prompt("y"), start()]), False, "inline は引数を持たない")

    def test_a_flag_must_be_a_whole_token(self):
        self.assertIs(rereview([skill("code-review:self-review", "--rereviewed --no-rereview"), start()]),
                      False)

    def test_a_flag_on_another_skill_is_not_a_declaration(self):
        self.assertIs(rereview([skill("feature-dev:feature-dev", "--rereview"),
                                skill("code-review:self-review"), start()]), False)

    def test_the_previous_review_bounds_the_search(self):
        """同じターンの前の start より前の申告は、次のレビューに持ち越さない."""
        self.assertIs(rereview([skill("code-review:self-review", "--rereview"), start(),
                                skill("code-review:self-review", "--embed"), start()]), False)

    def test_a_human_prompt_bounds_the_search(self):
        self.assertIs(rereview([skill("code-review:self-review", "--rereview"), prompt("続けて"),
                                start()]), False)

    def test_undecidable_without_a_start(self):
        self.assertIsNone(rereview([skill("code-review:self-review", "--rereview")]))


class RereviewSourceTest(unittest.TestCase):
    """申告として読むのは利用者か呼び出し元 skill の手順が付けたものだけ（GitHub issue #300）.

    利用者が「self-review 回して」としか言っていないのに、モデルが前回の構成から推して `--rereview` を
    足した回があった（3 回中 2 回は修正確認ではなかった）。
    """

    def test_a_flag_the_model_added_after_a_prompt_is_not_a_declaration(self):
        for body in ("self-review 回して", "回して", "self-review もう一度回して"):
            with self.subTest(body=body):
                self.assertIs(rereview([skill("code-review:self-review"), start(), prompt(body),
                                        skill("code-review:self-review", "--rereview --focus x"),
                                        start()]), False)

    def test_the_first_review_of_a_session_needs_a_declaration_too(self):
        self.assertIs(rereview([prompt("self-review 回して"), skill("code-review:self-review", "--rereview"),
                                start()]), False)

    def test_a_prompt_that_asks_for_a_rereview_is_a_declaration(self):
        for body in ("直したので再レビューして", "--rereview で回して", "ReReview で"):
            with self.subTest(body=body):
                self.assertIs(rereview([skill("code-review:self-review"), start(), prompt(body),
                                        skill("code-review:self-review", "--rereview"), start()]), True)

    def test_a_flag_inside_a_skill_procedure_is_a_declaration(self):
        """G-V ループ: 前のレビューから人間の発話を挟まずに呼び直す。通知は発話ではない."""
        note = prompt("<task-notification>\n<status>completed</status>\n</task-notification>")
        self.assertIs(rereview([slash("feature-dev:feature-dev"), expanded(),
                                skill("code-review:self-review", "--embed"), start(), note,
                                skill("code-review:self-review", "--embed --rereview"), start()]), True)

    def test_a_flag_the_model_added_after_a_slash_is_not_a_declaration(self):
        """slash の後に Skill で呼び直すときの args は、利用者が打った引数ではない."""
        self.assertIs(rereview([slash("code-review:self-review"), expanded(),
                                skill("code-review:self-review", "--rereview"), tool_result(), start()]),
                      False)

    def test_a_prompt_without_a_flag_still_needs_one(self):
        """発話が再レビューを頼んでも、`--rereview` の付いた起動が無ければ申告ではない."""
        self.assertIs(rereview([skill("code-review:self-review"), start(), prompt("再レビューして"),
                                skill("code-review:self-review"), start()]), False)


class SchemaTest(unittest.TestCase):
    def test_every_judgement_carries_the_rule_version(self):
        """retro は鍵の無い回を境界の無い規則（1）として層別する（#300 / #301）."""
        from invocation import SCHEMA
        self.assertEqual(SCHEMA, 2)
        self.assertEqual(judge_entries([prompt("y"), start()])["schema"], 2)
        self.assertEqual(judge_entries([prompt("y")])["schema"], 2, "start が無い回も判定器の版は付ける")


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
            self.assertEqual(self.run_cli(str(p)),
                             {"via": "slash", "parent": None, "rereview": False, "schema": 2})

    def test_an_unreadable_transcript_is_unknown(self):
        self.assertEqual(self.run_cli("/nonexistent/s.jsonl"),
                         {"via": "unknown", "parent": None, "rereview": None, "schema": 2})


if __name__ == "__main__":
    unittest.main()
