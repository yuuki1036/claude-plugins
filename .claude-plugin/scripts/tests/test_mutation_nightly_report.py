"""mutation-nightly-report.py — nightly の起票判定と本文（GitHub issue #288）.

予算や上限で打ち切った変異は、生存が無ければ success で終わって起票されず、翌晩の範囲からも外れて
検証されないまま消えていた。**黙る条件を厚く見る**: 起票しない回は stdout が空で本文も書かない。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / ".claude-plugin" / "scripts" / "mutation-nightly-report.py"

FULL = {"schema": 1, "generated": 16, "executed": 16, "killed": 16, "survived": 0, "invalid": 0,
        "timeout": 0, "unexecuted_max": 0, "unexecuted_budget": 0, "aborted": False}


class MutationNightlyReportTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        (self.d / "mutation.log").write_text("\n".join("line %d" % i for i in range(60)) + "\n",
                                             encoding="utf-8")

    def run_report(self, outcome: str, summary: dict | str | None) -> tuple[str, str | None]:
        """(stdout のタイトル, 本文 or None)."""
        s = self.d / "s.json"
        if isinstance(summary, dict):
            s.write_text(json.dumps(summary), encoding="utf-8")
        elif isinstance(summary, str):
            s.write_text(summary, encoding="utf-8")
        out = self.d / "body.md"
        res = subprocess.run(
            [sys.executable, str(SCRIPT), "--outcome", outcome, "--summary", str(s),
             "--log", str(self.d / "mutation.log"), "--base", "abc1234", "--head", "def5678",
             "--run-url", "https://example.invalid/run/1", "--out", str(out)],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout.strip(), (out.read_text(encoding="utf-8") if out.exists() else None)

    # --- 黙る ---
    def test_a_full_success_is_silent(self):
        title, body = self.run_report("success", FULL)
        self.assertEqual(title, "")
        self.assertIsNone(body)

    def test_zero_mutants_is_silent(self):
        title, body = self.run_report("success", dict(FULL, generated=0, executed=0, killed=0))
        self.assertEqual((title, body), ("", None))

    # --- 打ち切り（#288 の本題）---
    def test_a_budget_cut_on_success_is_reported(self):
        """10-03 の形: 36 個中 26 個で予算切れ・生存 0 ＝ success だが 10 個が検証されずに消える."""
        title, body = self.run_report("success", dict(FULL, generated=36, executed=26, killed=26,
                                                      unexecuted_budget=10))
        self.assertEqual(title, "[mutation-nightly] 検証しきれなかった変異がある")
        self.assertIn("生成 36 個のうち実行 26 個。**予算で未実行 10 / 上限で未実行 0**", body)
        self.assertIn("abc1234..def5678", body)
        self.assertNotIn("生存した変異がある", body)

    def test_a_single_unexecuted_mutant_is_enough(self):
        """境界: 1 個でも起票する（0 との比較を緩める変異を殺す）."""
        for key in ("unexecuted_budget", "unexecuted_max"):
            with self.subTest(key):
                title, _ = self.run_report("success", dict(FULL, **{key: 1}))
                self.assertEqual(title, "[mutation-nightly] 検証しきれなかった変異がある")

    def test_survivors_and_a_cut_share_one_body(self):
        """09-30 の形: 生存 3・予算で未実行 37・上限で未実行 8 → タイトルは生存、本文に両方."""
        title, body = self.run_report("failure", dict(FULL, generated=68, executed=23, survived=3,
                                                      killed=20, unexecuted_budget=37,
                                                      unexecuted_max=8))
        self.assertEqual(title, "[mutation-nightly] 生存した変異がある")
        self.assertIn("## 生存した変異がある", body)
        self.assertIn("**予算で未実行 37 / 上限で未実行 8**", body)

    # --- step の失敗（従来の起票）---
    def test_a_failure_without_a_summary_is_reported_as_before(self):
        """テストが最初から赤（exit 2）だと集計は書かれない。従来どおり生存の見出しで起票し、
        集計が無いことは騒がない（落ちた回は無くて当然）."""
        title, body = self.run_report("failure", None)
        self.assertEqual(title, "[mutation-nightly] 生存した変異がある")
        self.assertNotIn("集計を読めなかった", body)
        self.assertNotIn("検証しきれなかった", body)

    # --- 集計が読めない（判定できないことを黙らせない）---
    def test_success_without_a_summary_is_reported(self):
        title, body = self.run_report("success", None)
        self.assertEqual(title, "[mutation-nightly] 検証しきれなかった変異がある")
        self.assertIn("集計を読めなかった", body)

    def test_a_broken_summary_is_not_read_as_zero(self):
        for name, summary in (("not-json", "{"), ("not-object", "[]"),
                              ("string-count", json.dumps(dict(FULL, unexecuted_budget="3"))),
                              ("negative", json.dumps(dict(FULL, unexecuted_max=-1))),
                              ("bool", json.dumps(dict(FULL, unexecuted_budget=True)))):
            with self.subTest(name):
                title, body = self.run_report("success", summary)
                self.assertNotEqual(title, "", "壊れた集計を「未実行 0」と読んで黙っている")
                self.assertIn("集計を読めなかった", body)

    # --- 本文 ---
    def test_the_body_carries_the_log_tail(self):
        _, body = self.run_report("failure", None)
        self.assertIn("line 59", body)
        self.assertIn("line 20", body)
        self.assertNotIn("line 19\n", body, "ログの末尾 40 行より前まで貼っている")
        self.assertIn("https://example.invalid/run/1", body)

    def test_every_argument_is_required(self):
        """1 つでも欠けたら argparse で止める（`None` のまま進むと本文に `None` が入るか例外で死ぬ）."""
        args = {"--outcome": "success", "--summary": "s.json", "--log": "mutation.log",
                "--base": "a", "--head": "b", "--run-url": "u", "--out": "body.md"}
        for drop in args:
            with self.subTest(drop):
                argv = [x for k, v in args.items() if k != drop for x in (k, v)]
                res = subprocess.run([sys.executable, str(SCRIPT), *argv], cwd=self.d,
                                     capture_output=True, text=True, timeout=30)
                self.assertEqual(res.returncode, 2, res.stderr)
                self.assertIn(drop, res.stderr)

    def test_a_missing_log_is_named(self):
        (self.d / "mutation.log").unlink()
        _, body = self.run_report("failure", None)
        self.assertIn("(ログを取得できなかった)", body)


class WorkflowWiringTest(unittest.TestCase):
    """ワークフローが集計を書かせ、report が成功の回にも走ること（配線の確認）."""

    WF = REPO / ".github" / "workflows" / "mutation-nightly.yml"

    def test_the_test_step_writes_the_summary_the_report_reads(self):
        text = self.WF.read_text(encoding="utf-8")
        self.assertIn("--summary-json mutation-summary.json", text)
        self.assertIn("--summary mutation-summary.json", text)

    def test_the_report_step_is_not_limited_to_failures(self):
        """`if: failure()` のままだと打ち切った success の回で report が走らない."""
        text = self.WF.read_text(encoding="utf-8")
        report = text[text.index("- name: report"):]
        cond = next(l for l in report.splitlines() if l.strip().startswith("if:"))
        self.assertNotIn("failure()", cond)
        self.assertIn("!cancelled()", cond)
        self.assertIn("steps.mut.outcome", report)


if __name__ == "__main__":
    unittest.main()
