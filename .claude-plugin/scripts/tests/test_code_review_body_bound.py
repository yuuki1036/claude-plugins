#!/usr/bin/env python3
"""付録と報告件数の上限（`code-review/scripts/lib/body_bound.py`）の単体テスト.

publish / retro の 2 経路が共有する判定なので純関数として見る（GitHub issue #248）。CLI 側の
統合は `test_code_review_scripts.py` の `BodyBoundPublishTest` / `BodyBoundRetroTest` が持つ。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "code-review" / "scripts" / "lib"))

from body_bound import body_bound  # noqa: E402

#: pre 6（MAJOR 1 + MINOR 5）/ below 5 → 本文を書いたのは 1 件。報告 0 なので付録の上限は 1
BASE = {"pre_adjust_counts": {"blocker": 0, "critical": 0, "major": 1, "minor": 5, "schema": 2},
        "below_threshold_counts": {"blocker": 0, "critical": 0, "major": 0, "minor": 5},
        "blocker_count": 0, "critical_count": 0, "major_count": 0, "minor_count": 0,
        "appendix": {"listed": 1, "recommended": 0}}


def payload(**changes) -> dict:
    p = copy.deepcopy(BASE)
    for key, value in changes.items():
        p[key] = value
    return p


class BodyBoundTest(unittest.TestCase):
    def test_the_bound_is_written_minus_reported(self):
        b = body_bound(payload())
        self.assertEqual((b["written"], b["reported"], b["appendix_cap"]), (1, 0, 1))
        self.assertFalse(b["appendix_over"])
        self.assertTrue(body_bound(payload(appendix={"listed": 2, "recommended": 0}))["appendix_over"])

    def test_the_appendix_bound_does_not_go_negative(self):
        """報告が本文を書いた数を超えた回の付録の上限は 0（負の上限で行数と比べない）."""
        b = body_bound(payload(major_count=3, appendix={"listed": 0, "recommended": 0}))
        self.assertEqual(b["appendix_cap"], 0)
        self.assertFalse(b["appendix_over"])
        self.assertTrue(b["report_over"])

    def test_reported_exactly_at_the_bound_is_not_over(self):
        self.assertFalse(body_bound(payload(major_count=1))["report_over"])
        self.assertTrue(body_bound(payload(major_count=2))["report_over"])

    def test_findings_added_are_not_added_again(self):
        """skeptic / meta の指摘は手順 1 より前に統合され pre に入っている（二重計上しない）."""
        b = body_bound(payload(recall_skeptic={"fired": True, "findings_added": 1},
                               meta_reviewer={"fired": True, "findings_added": 2},
                               appendix={"listed": 2, "recommended": 0}))
        self.assertEqual(b["appendix_cap"], 1)
        self.assertTrue(b["appendix_over"])

    def test_each_missing_input_alone_stops_the_judgement(self):
        """入力が 1 つ欠けるだけで判定しない（0 を埋めると上限が下がって違反を作る）."""
        cases = {
            "pre key": ("pre_adjust_counts", "minor"),
            "below key": ("below_threshold_counts", "minor"),
            "report count": (None, "minor_count"),
            "appendix listed": ("appendix", "listed"),
        }
        for name, (parent, key) in cases.items():
            with self.subTest(name):
                p = payload()
                del (p[parent] if parent else p)[key]
                self.assertIsNone(body_bound(p))

    def test_a_schema_that_is_not_an_integer_is_not_judged(self):
        """旧データの schema が文字列・bool でも落ちずに判定しない（`"2" < 2` は TypeError）."""
        for schema in ("2", True, None, 1):
            with self.subTest(schema=schema):
                pre = dict(BASE["pre_adjust_counts"], schema=schema)
                self.assertIsNone(body_bound(payload(pre_adjust_counts=pre)))

    def test_non_count_values_are_not_counts(self):
        for bad in (-1, True, "1", 1.0):
            with self.subTest(bad=bad):
                self.assertIsNone(body_bound(payload(major_count=bad)))


if __name__ == "__main__":
    unittest.main()
