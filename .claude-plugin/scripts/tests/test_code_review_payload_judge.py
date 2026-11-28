#!/usr/bin/env python3
"""payload の層の判定（`code-review/scripts/lib/payload_judge.py`）の単体テスト. GitHub issue #536.

`review-retro.sh` と `metrics_update.py` が共有する純関数なので、期待値をここで直接書いて見る（実装を
通して期待値を作らない）。retro 側の層の分け方は `test_code_review_scripts.py`、metrics-update 側の比較表は
`test_code_review_metrics_update.py` が CLI 越しに見る。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "code-review" / "scripts" / "lib"))

from payload_judge import (  # noqa: E402
    TOK_SCALE_MIN_SCHEMA, gen_of, is_rereview, num, schema_of, scope_mode_of,
)


class GenOfTest(unittest.TestCase):
    def test_without_models_is_unrecorded(self):
        for p in ({}, {"models": None}, {"models": []}, {"models": "opus-5-5"}):
            with self.subTest(p=p):
                self.assertEqual(gen_of(p), "unrecorded")

    def test_models_without_a_usable_main_is_mixed(self):
        for p in ({"models": {}}, {"models": {"main": ""}}, {"models": {"main": None}},
                  {"models": {"main": 3}}):
            with self.subTest(p=p):
                self.assertEqual(gen_of(p), "mixed")

    def test_claude_prefix_is_stripped(self):
        self.assertEqual(gen_of({"models": {"main": "claude-opus-5-5"}}), "opus-5-5")

    def test_main_without_prefix_is_kept_as_is(self):
        self.assertEqual(gen_of({"models": {"main": "sonnet-5-5"}}), "sonnet-5-5")

    def test_prefix_only_in_the_middle_is_not_stripped(self):
        self.assertEqual(gen_of({"models": {"main": "x-claude-opus"}}), "x-claude-opus")


class IsRereviewTest(unittest.TestCase):
    def test_only_true_counts(self):
        self.assertIs(is_rereview({"invocation": {"rereview": True}}), True)

    def test_truthy_non_bool_and_missing_are_first_reviews(self):
        for p in ({}, {"invocation": None}, {"invocation": []}, {"invocation": {}},
                  {"invocation": {"rereview": "true"}}, {"invocation": {"rereview": 1}},
                  {"invocation": {"rereview": False}}):
            with self.subTest(p=p):
                self.assertIs(is_rereview(p), False)


class ScopeModeOfTest(unittest.TestCase):
    def test_known_modes_are_kept(self):
        self.assertEqual(scope_mode_of({"review_scope": {"mode": "delta"}}), "delta")
        self.assertEqual(scope_mode_of({"review_scope": {"mode": "full"}}), "full")

    def test_missing_or_unknown_is_full(self):
        for p in ({}, {"review_scope": None}, {"review_scope": "delta"}, {"review_scope": {}},
                  {"review_scope": {"mode": "x"}}, {"review_scope": {"mode": "DELTA"}}):
            with self.subTest(p=p):
                self.assertEqual(scope_mode_of(p), "full")


class NumTest(unittest.TestCase):
    def test_numbers_pass_through(self):
        for v in (0, 3, -1, 2.5):
            with self.subTest(v=v):
                self.assertEqual(num(v), v)

    def test_bool_and_non_numbers_are_none(self):
        for v in (True, False, None, "3", [1], {}):
            with self.subTest(v=v):
                self.assertIsNone(num(v))


class SchemaOfTest(unittest.TestCase):
    def test_int_and_numeric_string_are_read(self):
        self.assertEqual(schema_of({"schema": 3}, "schema"), 3)
        self.assertEqual(schema_of({"schema": "2"}, "schema"), 2)

    def test_missing_empty_and_unparsable_are_oldest(self):
        for d in ({}, {"schema": None}, {"schema": 0}, {"schema": ""}, {"schema": "x"},
                  {"schema": [2]}):
            with self.subTest(d=d):
                self.assertEqual(schema_of(d, "schema"), 1)

    def test_reads_the_named_key(self):
        self.assertEqual(schema_of({"schema": 5, "calibration_schema": 2}, "calibration_schema"), 2)


class TokScaleTest(unittest.TestCase):
    def test_threshold_is_schema_3(self):
        self.assertEqual(TOK_SCALE_MIN_SCHEMA, 3)


if __name__ == "__main__":
    unittest.main()
