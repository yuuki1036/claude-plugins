#!/usr/bin/env python3
"""複数ログの重複除去（`code-review/scripts/lib/event_dedup.py`）の単体テスト.

retro の CLI 側の統合は `test_code_review_scripts.py` の `RetroExplicitLogsTest` が持つ。ここでは
「サニタイズ済みの形か」の判定（`covers`）と採否の規則を純関数として見る。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "code-review" / "scripts" / "lib"))

from event_dedup import EventDeduper, covers  # noqa: E402

TS, PLUGIN = "2026-08-01T00:00:00Z", "code-review:self-review"


def ev(payload, ts=TS, plugin=PLUGIN) -> dict:
    e = {"event": "review:completed", "plugin": plugin, "payload": payload}
    if ts is not None:
        e["ts"] = ts
    return e


class CoversTest(unittest.TestCase):
    """`covers(rich, poor)`: poor が rich のサニタイズ済みの形として説明できるか."""

    def test_dropped_keys_are_allowed_only_on_the_poor_side(self):
        self.assertTrue(covers({"pr": "12", "effort": "high"}, {"effort": "high"}))
        self.assertFalse(covers({"effort": "high"}, {"pr": "12", "effort": "high"}),
                         "サニタイズで増えるキーは無い")

    def test_nested_dropped_keys_are_allowed(self):
        self.assertTrue(covers({"a": {"base": "x", "n": 1}}, {"a": {"n": 1}}))
        self.assertFalse(covers({"a": {"n": 1}}, {"a": {"n": 2}}))

    def test_a_string_replaced_by_other(self):
        self.assertTrue(covers({"s": "free text"}, {"s": "other"}))
        self.assertTrue(covers({"s": "other"}, {"s": "other"}))
        self.assertFalse(covers({"s": "other"}, {"s": "free text"}), "other から元の値は戻らない")
        self.assertFalse(covers({"s": "a"}, {"s": "b"}))
        self.assertFalse(covers({"s": 1}, {"s": "other"}), "文字列でない値は other にならない")

    def test_missing_coverage_words_are_replaced_one_by_one(self):
        """`missing_coverage[]` はサニタイザが `:` 区切りの語ごとに `other` へ置き換える."""
        rich = {"missing_coverage": ["reviewer:acme-doc", "explorer"]}
        self.assertTrue(covers(rich, {"missing_coverage": ["reviewer:other", "explorer"]}))
        self.assertTrue(covers(rich, {"missing_coverage": ["other:acme-doc", "explorer"]}))
        self.assertFalse(covers(rich, {"missing_coverage": ["meta:other", "explorer"]}), "残った語が違う")
        self.assertFalse(covers({"s": "a:b"}, {"s": "other:b:c"}), "区切りの数が違う")
        self.assertFalse(covers({"s": "ab"}, {"s": "a:other"}))

    def test_lists_are_compared_element_wise(self):
        self.assertTrue(covers({"l": ["a", "b"]}, {"l": ["other", "b"]}))
        self.assertFalse(covers({"l": ["a", "b"]}, {"l": ["a"]}), "要素の数は変わらない")
        self.assertFalse(covers({"l": "a"}, {"l": ["a"]}))

    def test_non_finite_numbers_become_null(self):
        self.assertTrue(covers({"x": float("nan")}, {"x": None}))
        self.assertTrue(covers({"x": float("inf")}, {"x": None}))
        self.assertTrue(covers({"x": None}, {"x": None}))
        self.assertFalse(covers({"x": 1.5}, {"x": None}))
        self.assertFalse(covers({"x": 0}, {"x": None}))

    def test_bool_is_not_a_number(self):
        self.assertTrue(covers({"x": True}, {"x": True}))
        self.assertFalse(covers({"x": 1}, {"x": True}))
        self.assertFalse(covers({"x": True}, {"x": 1}))
        self.assertFalse(covers({"x": 1}, {"x": 2}))

    def test_machine_id_is_ignored_only_at_the_top(self):
        """サニタイザが label に付け替えるのはトップレベルの `machine_id` だけ."""
        self.assertTrue(covers({"machine_id": "AcmeCorp-host"}, {"machine_id": "m1"}))
        self.assertTrue(covers({}, {"machine_id": "m1"}))
        self.assertFalse(covers({"a": {"machine_id": "x"}}, {"a": {"machine_id": "m1"}}))

    def test_a_dict_is_not_covered_by_a_non_dict(self):
        self.assertFalse(covers(["a"], {"a": 1}))
        self.assertTrue(covers({"a": 1}, {}))


class EventDeduperTest(unittest.TestCase):
    def run_all(self, *rows):
        d = EventDeduper()
        for e, src in rows:
            d.add(e, src)
        return d

    def test_identical_lines_are_one_event(self):
        d = self.run_all((ev({"a": 1}), "x"), (ev({"a": 1}), "y"))
        self.assertEqual(d.events(), [(ev({"a": 1}), "x")])
        self.assertEqual((d.dropped, d.conflicts), (1, []))

    def test_the_key_is_ts_and_plugin(self):
        d = self.run_all((ev({"a": 1}), "x"), (ev({"a": 1}, ts="2026-08-02T00:00:00Z"), "x"),
                         (ev({"a": 1}, plugin="code-review:review"), "x"))
        self.assertEqual(len(d.events()), 3)
        self.assertEqual(d.dropped, 0)

    def test_the_raw_line_wins_over_its_sanitized_copy_in_either_order(self):
        raw, san = ev({"pr": "12", "s": "free text"}), ev({"s": "other"})
        for rows in (((raw, "raw"), (san, "store")), ((san, "store"), (raw, "raw"))):
            with self.subTest(first=rows[0][1]):
                d = self.run_all(*rows)
                self.assertEqual(d.events(), [(raw, "raw")])
                self.assertEqual((d.dropped, d.conflicts), (1, []))

    def test_disagreeing_lines_keep_the_longer_one_in_either_order(self):
        short, longer = ev({"e": "high"}), ev({"e": "low", "n": 1})
        for rows in (((short, "s"), (longer, "l")), ((longer, "l"), (short, "s"))):
            with self.subTest(first=rows[0][1]):
                d = self.run_all(*rows)
                self.assertEqual(d.events(), [(longer, "l")])
                self.assertEqual(d.dropped, 1)
                self.assertEqual(d.conflicts, [(TS, PLUGIN, "l", "s")])

    def test_same_length_disagreement_keeps_the_later_one_in_dictionary_order(self):
        a, b = ev({"e": "aaa"}), ev({"e": "bbb"})
        for rows in (((a, "a"), (b, "b")), ((b, "b"), (a, "a"))):
            with self.subTest(first=rows[0][1]):
                d = self.run_all(*rows)
                self.assertEqual(d.events(), [(b, "b")])
                self.assertEqual(d.conflicts, [(TS, PLUGIN, "b", "a")])

    def test_only_the_machine_id_differs_is_not_a_conflict(self):
        """互いに説明できる（`machine_id` だけが違う）ときは食い違いに数えず、長い方を採る."""
        label, raw = ev({"machine_id": "m1", "e": 1}), ev({"machine_id": "AcmeCorp-host", "e": 1})
        for rows in (((label, "l"), (raw, "r")), ((raw, "r"), (label, "l"))):
            with self.subTest(first=rows[0][1]):
                d = self.run_all(*rows)
                self.assertEqual(d.events(), [(raw, "r")])
                self.assertEqual((d.dropped, d.conflicts), (1, []))

    def test_the_first_position_is_kept_when_the_content_is_replaced(self):
        """差し替えても並び（最初に現れた順）は変えない（同じ ts の行の並びを引数の順に依存させない）."""
        other = ev({"a": 1}, ts="2026-08-02T00:00:00Z")
        san, raw = ev({"s": "other"}), ev({"s": "free text"})
        d = self.run_all((san, "store"), (other, "store"), (raw, "raw"))
        self.assertEqual(d.events(), [(raw, "raw"), (other, "store")])

    def test_lines_without_a_timestamp_are_keyed_by_payload(self):
        d = self.run_all((ev({"e": "high"}, ts=None), "x"), (ev({"e": "low"}, ts=None), "x"),
                         (ev({"e": "high"}, ts=None), "y"), (ev({"e": "high"}, ts=""), "y"))
        self.assertEqual([e["payload"] for e, _ in d.events()], [{"e": "high"}, {"e": "low"}])
        self.assertEqual((d.dropped, d.conflicts), (2, []))


if __name__ == "__main__":
    unittest.main()
