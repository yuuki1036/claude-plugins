#!/usr/bin/env python3
"""定型レポートの判定（`code-review/scripts/lib/report_template.py`）の単体テスト.

publish が呼ぶ判定を純関数として見る（GitHub issue #250）。publish 経由の統合は
`test_code_review_scripts.py` の `ReportTemplatePublishTest` が持つ。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "code-review" / "scripts" / "lib"))

from report_template import RECENT_SEC, judge, judge_lines  # noqa: E402

START = 'bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" start --pr 12'
PUBLISH = 'bash "${CLAUDE_PLUGIN_ROOT}/scripts/publish-review-event.sh" --plugin code-review:review'
TEMPLATE = "**指摘件数**: BLOCKER 0 件 / CRITICAL 0 件 / MAJOR 0 件 / MINOR 0 件"


def assistant(block: dict) -> str:
    return json.dumps({"type": "assistant", "message": {"content": [block]}}, ensure_ascii=False)


def bash(command: str) -> str:
    return assistant({"type": "tool_use", "name": "Bash", "input": {"command": command}})


def text(body: str) -> str:
    return assistant({"type": "text", "text": body})


def verdict(lines, now=None):
    return judge_lines(lines, now)[0]


class JudgeLinesTest(unittest.TestCase):
    def test_present_absent_and_unknown(self):
        self.assertTrue(verdict([bash(START), text(TEMPLATE), bash(PUBLISH)]))
        self.assertFalse(verdict([bash(START), text("済"), bash(PUBLISH)]))
        self.assertIsNone(verdict([bash(START), text(TEMPLATE)]), "publish がまだ無い")
        self.assertIsNone(verdict([text(TEMPLATE), bash(PUBLISH)]), "起点が無い")

    def test_it_says_when_waiting_can_help(self):
        """待つ価値があるのは start があって publish がまだ無いときだけ."""
        self.assertEqual(judge_lines([text(TEMPLATE), bash(PUBLISH)]), (None, False))
        self.assertEqual(judge_lines([bash(START), text(TEMPLATE)]), (None, True))
        self.assertEqual(judge_lines([bash(START), text(TEMPLATE), bash(PUBLISH)]), (True, False))

    def test_a_command_that_only_mentions_the_scripts_is_not_a_call(self):
        """grep 等の引数に名前が出るだけでは起点にも publish にもならない."""
        grep_start = "grep -n 'bash \"x/review-timing.sh\" start' code-review/SKILL.md"
        sed_pub = "sed -n '1,60p' code-review/scripts/publish-review-event.sh"
        self.assertTrue(verdict([bash(START), text(TEMPLATE), bash(grep_start), bash(PUBLISH)]),
                        "grep を起点にしている")
        self.assertTrue(verdict([bash(START), bash(sed_pub), text(TEMPLATE), bash(PUBLISH)]),
                        "sed で開いただけを publish にしている")

    def test_heredoc_bodies_are_not_calls(self):
        """テストや SKILL を直す heredoc の本文に呼び出しの字面があっても数えない."""
        heredoc = ("python3 - <<'PY'\n"
                   "START = 'x'\n"
                   "bash \"${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh\" start\n"
                   "bash \"${CLAUDE_PLUGIN_ROOT}/scripts/publish-review-event.sh\" --plugin x\n"
                   "PY")
        self.assertTrue(verdict([bash(START), text(TEMPLATE), bash(heredoc), bash(PUBLISH)]))
        self.assertTrue(verdict([bash(START), bash(heredoc), text(TEMPLATE), bash(PUBLISH)]))

    def test_calls_after_an_operator_or_on_a_later_line_count(self):
        """SKILL の Step 1 はコメント行の後に start を書く。mark t2 と publish は && で連結されうる."""
        multi = "# 開始マーカー\n" + START
        chained = "bash x/review-timing.sh mark t2 && " + PUBLISH
        self.assertTrue(verdict([bash(multi), text(TEMPLATE), bash(chained)]))
        self.assertFalse(verdict([bash(multi), text("済"), bash(chained)]))

    def test_the_last_publish_after_the_start_is_judged(self):
        """fail-fast で落ちた publish を直して再実行した回は、通した publish の前に定型があればよい."""
        self.assertTrue(verdict([bash(START), text("済"), bash(PUBLISH), text(TEMPLATE),
                                 bash(PUBLISH)]))
        self.assertFalse(verdict([bash(START), text(TEMPLATE), bash(PUBLISH), bash(START),
                                  text("済"), bash(PUBLISH)]), "前のレビューの定型を数えている")

    def test_near_templates_do_not_count(self):
        """定型に近いが指摘件数の行が無い形（issue の 09-17T01:44 / 09-24T01:31 の型）."""
        for body in ("### BLOCKER\n- なし\n### MAJOR\n- x", "## セルフレビュー結果\n| 指摘件数 | 2 |",
                     "指摘件数: BLOCKER 0 件"):
            with self.subTest(body=body[:20]):
                self.assertFalse(verdict([bash(START), text(body), bash(PUBLISH)]))

    def test_an_old_publish_is_not_the_current_one(self):
        """`now` から 5 分以上前の publish の呼び出しは今回のものと見なさない（subagent が親の組を引く型）."""
        now = time.time()
        old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - RECENT_SEC - 5))
        fresh = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - RECENT_SEC + 30))
        pub_old = json.loads(bash(PUBLISH)); pub_old["timestamp"] = old
        pub_new = json.loads(bash(PUBLISH)); pub_new["timestamp"] = fresh
        self.assertEqual(judge_lines([bash(START), text("済"), json.dumps(pub_old)], now), (None, True))
        self.assertFalse(verdict([bash(START), text("済"), json.dumps(pub_new)], now))
        self.assertFalse(verdict([bash(START), text("済"), json.dumps(pub_old)]), "now 無しでは見ない")

    def test_exactly_the_limit_is_already_old(self):
        """境界: ちょうど `RECENT_SEC` 前の呼び出しは今回のものと見なさない."""
        pub = json.loads(bash(PUBLISH))
        pub["timestamp"] = "2026-09-26T00:00:00Z"
        base = time.mktime(time.strptime("2026-09-26T00:00:00", "%Y-%m-%dT%H:%M:%S")) - time.timezone
        lines = [bash(START), text("済"), json.dumps(pub)]
        self.assertIsNone(verdict(lines, base + RECENT_SEC))
        self.assertFalse(verdict(lines, base + RECENT_SEC - 1))

    def test_the_template_must_come_from_assistant_text(self):
        user = json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "content": TEMPLATE}]}}, ensure_ascii=False)
        self.assertFalse(verdict([bash(START), user, bash(PUBLISH)]))
        self.assertFalse(verdict([bash(START), bash("echo '%s'" % TEMPLATE), bash(PUBLISH)]),
                         "コマンドの中の文字列は出力ではない")

    def test_broken_and_foreign_lines_are_skipped(self):
        lines = ["{not json", json.dumps({"type": "assistant", "message": {"content": "str"}}),
                 json.dumps({"type": "assistant", "message": None}),
                 bash(START), text(TEMPLATE), bash(PUBLISH)]
        self.assertTrue(verdict(lines))

    def test_non_assistant_entries_do_not_count(self):
        """ユーザーの発言（本文に assistant の語を含む）に貼られたテンプレートは、出したことにならない."""
        user = json.dumps({"type": "user", "message": {"content": [
            {"type": "text", "text": "assistant の出力を見て: " + TEMPLATE}]}}, ensure_ascii=False)
        self.assertFalse(verdict([bash(START), user, bash(PUBLISH)]))


class CliTest(unittest.TestCase):
    """publish は標準出力の 1 語で受け取る。**落ちても publish 側では「gap なし」に見える**ので CLI で測る."""

    SCRIPT = REPO / "code-review" / "scripts" / "lib" / "report_template.py"

    def run_cli(self, lines: list[str], *wait: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            r = subprocess.run([sys.executable, str(self.SCRIPT), str(path), *wait],
                               capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_each_verdict_has_its_word(self):
        self.assertEqual(self.run_cli([bash(START), text(TEMPLATE), bash(PUBLISH)], "0.1"), "present")
        self.assertEqual(self.run_cli([bash(START), text("済"), bash(PUBLISH)], "0.1"), "absent")
        self.assertEqual(self.run_cli([bash(START)], "0.1"), "unknown")

    def test_the_wait_argument_is_optional(self):
        self.assertEqual(self.run_cli([bash(START), text(TEMPLATE), bash(PUBLISH)]), "present")


class JudgeWaitTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "t.jsonl"

    def test_an_unreadable_transcript_is_unknown(self):
        self.assertIsNone(judge(str(self.path), 0.1))

    def test_waiting_ends_at_the_deadline(self):
        self.path.write_text(bash(START) + "\n" + text("済") + "\n", encoding="utf-8")
        t0 = time.monotonic()
        self.assertIsNone(judge(str(self.path), 0.3))
        self.assertLess(time.monotonic() - t0, 2.0)

    def test_it_rereads_until_the_publish_is_written(self):
        """publish の呼び出しは tool の開始から少し遅れて書き出される。待って読み直す."""
        self.path.write_text(bash(START) + "\n" + text(TEMPLATE) + "\n", encoding="utf-8")

        def append_later():
            time.sleep(0.3)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(bash(PUBLISH) + "\n")
        t = threading.Thread(target=append_later)
        t.start()
        try:
            self.assertTrue(judge(str(self.path), 3.0))
        finally:
            t.join()

    def test_a_transcript_without_a_start_returns_without_waiting(self):
        self.path.write_text(text(TEMPLATE) + "\n" + bash(PUBLISH) + "\n", encoding="utf-8")
        t0 = time.monotonic()
        self.assertIsNone(judge(str(self.path), 5.0))
        self.assertLess(time.monotonic() - t0, 1.0)

    def test_a_decided_transcript_returns_without_waiting(self):
        self.path.write_text("\n".join([bash(START), text(TEMPLATE), bash(PUBLISH)]) + "\n",
                             encoding="utf-8")
        t0 = time.monotonic()
        self.assertTrue(judge(str(self.path), 5.0))
        self.assertLess(time.monotonic() - t0, 1.0)


if __name__ == "__main__":
    unittest.main()
