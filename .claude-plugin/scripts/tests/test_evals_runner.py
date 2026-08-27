#!/usr/bin/env python3
"""`evals/runner.py` の判定ロジックの回帰テスト（GitHub issue #187）.

**なぜあるか**: 620 行あって repo 内で最大の無テスト領域だった。`claude` CLI を叩く部分は
テストできないが、**判定（grader）とケース選別（タグ）は純粋関数**なので切り離して測れる。
ここが壊れると eval の緑／赤が意味を失い、しかも「スキル選択の回帰を見ている」つもりの
まま気づけない（eval 自体が測定器なので、測定器の故障は測定結果からは見えない）。

evals がローカル実行のみ（CI で回さない）という決定とは独立に、**判定ロジックは
本スイートで守る**。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "evals" / "runner.py"


def _load():
    """`runner.py` を単体で読み込む.

    **`sys.modules` へ先に登録してから exec する**: `@dataclass` はフィールドの型解決で
    `sys.modules[cls.__module__]` を引くので、登録前に実行すると
    `AttributeError: 'NoneType' object has no attribute '__dict__'` で落ちる。
    """
    spec = importlib.util.spec_from_file_location("_evals_runner_under_test", RUNNER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


r = _load()


def _obs(skill=None, stdout="", latency_ms=0, error=None):
    return r.AttemptObservation(skill=skill, stdout=stdout, latency_ms=latency_ms, error=error)


class SkillInvocationGraderTest(unittest.TestCase):
    """期待スキルの一致判定。**tail 一致を許すのがこの grader の肝**（別名ペア対応）."""

    def test_an_exact_match_passes(self):
        g = r.SkillInvocationGrader(["dev-workflow:pr-creator"])
        self.assertTrue(g.grade(_obs(skill="dev-workflow:pr-creator")).passed)

    def test_a_tail_match_passes(self):
        """`plugin:skill` の plugin 部が違っても skill 名が一致すれば通す."""
        g = r.SkillInvocationGrader(["dev-workflow:pr-creator"])
        self.assertTrue(g.grade(_obs(skill="other:pr-creator")).passed)

    def test_a_different_skill_fails(self):
        g = r.SkillInvocationGrader(["dev-workflow:pr-creator"])
        res = g.grade(_obs(skill="dev-workflow:commit"))
        self.assertFalse(res.passed)
        self.assertIn("commit", res.detail)

    def test_any_of_several_expectations_passes(self):
        """エイリアスを列挙したケース（コマンド名 / スキル名の非対称）."""
        g = r.SkillInvocationGrader(["claude-meta:cc-catch-up", "claude-meta:catch-up"])
        self.assertTrue(g.grade(_obs(skill="claude-meta:catch-up")).passed)

    def test_no_skill_detected_fails(self):
        self.assertFalse(r.SkillInvocationGrader(["a:b"]).grade(_obs(skill=None)).passed)

    def test_a_runtime_error_fails_even_with_a_matching_skill(self):
        """**エラーを緑に倒さない**（落ちた実行を「期待どおり」と数えない）."""
        g = r.SkillInvocationGrader(["a:b"])
        self.assertFalse(g.grade(_obs(skill="a:b", error="timeout")).passed)


class TextGraderTest(unittest.TestCase):
    def test_must_match_passes_when_present(self):
        g = r.TextGrader("marker", r'"skill"\s*:')
        self.assertTrue(g.grade(_obs(stdout='{"skill": "x"}')).passed)

    def test_must_match_fails_when_absent(self):
        g = r.TextGrader("marker", r'"skill"\s*:')
        self.assertFalse(g.grade(_obs(stdout="なにもない")).passed)

    def test_must_not_match_inverts_the_verdict(self):
        g = r.TextGrader("forbidden", r"secret", mode="must_not_match")
        self.assertTrue(g.grade(_obs(stdout="clean")).passed)
        self.assertFalse(g.grade(_obs(stdout="a secret leaked")).passed)

    def test_an_unknown_mode_is_rejected_at_construction(self):
        """黙って must_match に倒すと、typo したケースが**常に緑**になる."""
        with self.assertRaises(ValueError):
            r.TextGrader("x", "y", mode="must_matchh")

    def test_a_runtime_error_fails(self):
        self.assertFalse(r.TextGrader("m", "x").grade(_obs(stdout="x", error="boom")).passed)


class BehaviorGraderTest(unittest.TestCase):
    def test_latency_within_budget_passes(self):
        self.assertTrue(r.BehaviorGrader("l", max_latency_ms=100).grade(_obs(latency_ms=100)).passed)

    def test_latency_over_budget_fails(self):
        """境界の両側を測る（`>` と `>=` の取り違えが素通りしないように）."""
        self.assertFalse(r.BehaviorGrader("l", max_latency_ms=100).grade(_obs(latency_ms=101)).passed)

    def test_stdout_size_budget(self):
        g = r.BehaviorGrader("s", max_stdout_chars=5)
        self.assertTrue(g.grade(_obs(stdout="12345")).passed)
        self.assertFalse(g.grade(_obs(stdout="123456")).passed)

    def test_without_budgets_it_always_passes(self):
        self.assertTrue(r.BehaviorGrader("noop").grade(_obs(latency_ms=10**6)).passed)


class TagFilterTest(unittest.TestCase):
    """`holdout` の既定除外。**除外が効かないと holdout ケースが結果に混ざる**."""

    def _cases(self):
        return [
            r.Case(plugin="demo", id="a", prompt="p", expected_skill=None, tags=[]),
            r.Case(plugin="demo", id="b", prompt="p", expected_skill=None, tags=["holdout"]),
            r.Case(plugin="demo", id="c", prompt="p", expected_skill=None, tags=["slow", "holdout"]),
            r.Case(plugin="demo", id="d", prompt="p", expected_skill=None, tags=["slow"]),
        ]

    def _ids(self, cases):
        return [c.id for c in cases]

    def test_exclude_drops_matching_cases(self):
        out = r.filter_by_tags(self._cases(), [], ["holdout"])
        self.assertEqual(self._ids(out), ["a", "d"])

    def test_only_keeps_matching_cases(self):
        out = r.filter_by_tags(self._cases(), ["slow"], [])
        self.assertEqual(self._ids(out), ["c", "d"])

    def test_exclude_wins_over_only(self):
        out = r.filter_by_tags(self._cases(), ["slow"], ["holdout"])
        self.assertEqual(self._ids(out), ["d"])

    def test_no_filters_keeps_everything(self):
        self.assertEqual(len(r.filter_by_tags(self._cases(), [], [])), 4)

    def test_holdout_is_the_default_exclusion(self):
        self.assertIn("holdout", r.DEFAULT_EXCLUDE_TAGS)


class PassCriterionTest(unittest.TestCase):
    """pass^k の判定: **k 回すべて通ってはじめて pass**（k=1 の結果で判断しない規約の実体）."""

    def _result(self, verdicts: list[bool], k: int = 3):
        case = r.Case(plugin="demo", id="x", prompt="p", expected_skill="a:b", k=k)
        res = r.CaseResult(case=case, model="m")
        for v in verdicts:
            res.attempts.append(_obs(skill="a:b"))
            res.grader_results.append([r.GraderResult("g", v)])
        return res

    def test_all_attempts_passing_is_a_pass(self):
        self.assertTrue(self._result([True, True, True]).passed)

    def test_one_failure_fails_the_case(self):
        self.assertFalse(self._result([True, False, True]).passed)

    def test_fewer_attempts_than_k_is_not_a_pass(self):
        """**試行が足りない回を緑にしない**（途中で落ちた実行を成功と数えない）."""
        self.assertFalse(self._result([True, True], k=3).passed)


if __name__ == "__main__":
    unittest.main()
