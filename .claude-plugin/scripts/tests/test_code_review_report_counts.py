#!/usr/bin/env python3
"""報告件数の入れ子正規化（`code-review/scripts/lib/report_counts.py`）の単体テスト.

`test_code_review_wave_expect.py` と同じ理由で純関数として見る（publish / retro の 2 経路が
共有する 1 箇所 / GitHub issue #238）。CLI 側の統合は `test_code_review_scripts.py` の
`ReportCountNestedTest` / `RetroNestedRecoveryTest` が持つ。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "code-review" / "scripts" / "lib"))

from report_counts import REPORT_KEYS, lift_nested_report_counts  # noqa: E402

FLAT = {"blocker_count": 0, "critical_count": 0, "major_count": 1, "minor_count": 0}


class LiftNestedReportCountsTest(unittest.TestCase):
    def test_counts_lowercase_without_suffix_is_lifted(self):
        p = {"counts": {"blocker": 0, "critical": 0, "major": 1, "minor": 0}}
        self.assertEqual(lift_nested_report_counts(p), "counts")
        self.assertEqual({k: p[k] for k in REPORT_KEYS}, FLAT)

    def test_counts_uppercase_is_lifted(self):
        """実データの形（2026-09-12 / `pre_adjust_counts` も大文字で語彙違反だった回）."""
        p = {"counts": {"BLOCKER": 0, "CRITICAL": 0, "MAJOR": 1, "MINOR": 0}}
        self.assertEqual(lift_nested_report_counts(p), "counts")
        self.assertEqual({k: p[k] for k in REPORT_KEYS}, FLAT)

    def test_report_counts_with_suffix_is_lifted(self):
        """gap 識別子 `report_counts.missing` の名前を構造化した形（2026-09-16T07:19）."""
        p = {"report_counts": dict(FLAT)}
        self.assertEqual(lift_nested_report_counts(p), "report_counts")
        self.assertEqual({k: p[k] for k in REPORT_KEYS}, FLAT)

    def test_the_nested_parent_is_kept_as_evidence(self):
        p = {"counts": {"blocker": 0, "critical": 0, "major": 1, "minor": 0}}
        lift_nested_report_counts(p)
        self.assertIn("counts", p, "払い出した形の証拠を消している")

    def test_a_partial_nest_is_not_lifted(self):
        """3 つしか無い入れ子は救わない（`missing` の側に残す）."""
        p = {"counts": {"blocker": 0, "critical": 0, "major": 1}}
        self.assertIsNone(lift_nested_report_counts(p))
        self.assertFalse(any(k in p for k in REPORT_KEYS))

    def test_a_non_count_value_in_the_nest_is_not_lifted(self):
        for bad in (True, -1, "1", None):
            with self.subTest(bad=bad):
                p = {"counts": {"blocker": 0, "critical": 0, "major": bad, "minor": 0}}
                self.assertIsNone(lift_nested_report_counts(p))
                self.assertFalse(any(k in p for k in REPORT_KEYS))

    def test_any_top_level_key_disables_lifting(self):
        """トップレベルに 1 つでもあれば入れ子を見ない（部分欠測と入れ子を混ぜない）."""
        p = {"major_count": 1, "counts": {"blocker": 0, "critical": 0, "major": 1, "minor": 0}}
        self.assertIsNone(lift_nested_report_counts(p))
        self.assertNotIn("blocker_count", p)

    def test_a_flat_payload_is_untouched(self):
        p = dict(FLAT)
        self.assertIsNone(lift_nested_report_counts(p))
        self.assertEqual(p, FLAT)

    def test_report_counts_wins_over_counts_when_both_present(self):
        p = {"report_counts": dict(FLAT),
             "counts": {"blocker": 9, "critical": 9, "major": 9, "minor": 9}}
        self.assertEqual(lift_nested_report_counts(p), "report_counts")
        self.assertEqual(p["major_count"], 1)

    def test_a_non_dict_parent_is_skipped(self):
        p = {"report_counts": [0, 0, 1, 0], "counts": {"blocker": 0, "critical": 0,
                                                       "major": 1, "minor": 0}}
        self.assertEqual(lift_nested_report_counts(p), "counts")

    def test_unrelated_keys_in_the_nest_are_ignored(self):
        p = {"counts": {"blocker": 0, "critical": 0, "major": 1, "minor": 0,
                        "schema": 1, "total": 1}}
        self.assertEqual(lift_nested_report_counts(p), "counts")
        self.assertNotIn("total_count", p)


if __name__ == "__main__":
    unittest.main()
