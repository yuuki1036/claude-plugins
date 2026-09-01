#!/usr/bin/env python3
"""期待 wave 本数の式（`code-review/scripts/lib/wave_expect.py`）の単体テスト.

**なぜ subprocess ではないのか**: 同ファイルの他のテストは bash の CLI 境界越しに叩くが、
ここは**純関数のモジュール**（`evals/runner.py` の判定部と同じ扱い）。式の分岐は
publish / backfill / retro の 3 経路が共有する 1 箇所に寄っており（GitHub issue #200）、
CLI 越しだと 1 分岐を確かめるのに transcript と時刻の fixture が要る。

CLI 側の統合は `test_code_review_scripts.py` の `WaveSplitDetectionTest` /
`ReviewBackfillTest.test_waves_expected_agrees_with_publish` が持つ。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "code-review" / "scripts" / "lib"))

from wave_expect import expected_waves, meta_added_findings, skeptic_tail_solo  # noqa: E402


def _sk(fired: bool = True) -> dict:
    return {"recall_skeptic": {"fired": fired, "skip_reason": None if fired else "no-surface"}}


class LayerTermsTest(unittest.TestCase):
    """`agents` の層が期待本数に効く形（reviewer は常に 1 本）."""

    def test_reviewer_alone_expects_one_wave(self):
        self.assertEqual(expected_waves({"agents": {"reviewer": 3}}, [3]), 1)

    def test_a_missing_agents_field_still_expects_the_reviewer_wave(self):
        """`agents` が無い / 壊れた回でも reviewer 層の 1 本は見込む（review は必ず走る）."""
        self.assertEqual(expected_waves({}, [3]), 1)
        self.assertEqual(expected_waves({"agents": ["not", "a", "dict"]}, [3]), 1)

    def test_explorer_adds_one(self):
        self.assertEqual(expected_waves({"agents": {"explorer": 1, "reviewer": 3}}, [1, 3]), 2)

    def test_verify_adds_one(self):
        self.assertEqual(
            expected_waves({"agents": {"explorer": 1, "reviewer": 3, "verify": 1}}, [1, 3, 1]), 3)

    def test_round_two_adds_two(self):
        """Round 2 は再起動なので 2 本（`triage-dynamic-gates.md ## 8`）."""
        self.assertEqual(expected_waves({"agents": {"reviewer": 3, "round2": 2}}, [3, 2, 1]), 3)

    def test_a_zero_layer_does_not_add_a_wave(self):
        """**0 体の層は 1 本増やさない**（`> 0` を `>= 0` に緩めると見込み過多で検出漏れ）."""
        self.assertEqual(
            expected_waves({"agents": {"explorer": 0, "reviewer": 3, "verify": 0}}, [3]), 1)

    def test_a_boolean_layer_count_is_not_a_count(self):
        """`True` は `int` の部分型なので、素で読むと 1 体として数えてしまう."""
        self.assertEqual(expected_waves({"agents": {"explorer": True, "reviewer": 3}}, [3]), 1)


class MetaTermTest(unittest.TestCase):
    """meta が足した指摘の反証バッチ（GitHub issue #166）."""

    def test_added_findings_expect_one_more_wave(self):
        p = {"meta_reviewer": {"fired": True, "findings_added": 2}}
        self.assertTrue(meta_added_findings(p))

    def test_zero_added_findings_does_not(self):
        """**見込み過多は検出漏れになる**（追加バッチは指摘があるときだけ起動する）."""
        self.assertFalse(meta_added_findings({"meta_reviewer": {"fired": True,
                                                                "findings_added": 0}}))

    def test_an_unfired_meta_does_not(self):
        """`findings_added` が残っていても発火が優先."""
        self.assertFalse(meta_added_findings({"meta_reviewer": {"fired": False,
                                                                "findings_added": 3}}))

    def test_a_truthy_non_boolean_fired_is_not_a_firing(self):
        """`fired` は `True` そのものを要求する（`"yes"` のような自由文を通さない）."""
        self.assertFalse(meta_added_findings({"meta_reviewer": {"fired": "yes",
                                                                "findings_added": 3}}))

    def test_a_non_integer_added_count_does_not(self):
        self.assertFalse(meta_added_findings({"meta_reviewer": {"fired": True,
                                                                "findings_added": "2"}}))
        self.assertFalse(meta_added_findings({"meta_reviewer": {"fired": True,
                                                                "findings_added": True}}))

    def test_a_missing_meta_object_does_not(self):
        self.assertFalse(meta_added_findings({}))


class SkepticTailSoloTest(unittest.TestCase):
    """skeptic fallback の控除（GitHub issue #172 / #200）.

    末尾に固まった単独 wave は**入力が揃うまで発行できない層**（skeptic fallback / 反証 /
    meta 反証）が並ぶ場所。それ以外の位置の単独 wave は層の分割を意味する。
    """

    def test_the_tail_solo_wave_is_deducted(self):
        """実測 08-24T05:40 の `[2,5,1]` 型（初版から効いていた形）."""
        self.assertTrue(skeptic_tail_solo(_sk(), [2, 5, 1]))

    def test_a_trailing_run_of_solo_waves_is_deducted(self):
        """**実測 08-28T00:28 の `[2,5,1,1]`**（#200 の偽陽性 2 件目）.

        skeptic wave の後ろに反証 wave が 1 本付いた形。初版の
        `sizes[-1] == 1 and 1 not in sizes[:-1]` は**後ろに 1 本付いた瞬間に効かなくなり**、
        #172 が「既知の残存限界②」として予告していた偽陽性をそのまま出していた。
        """
        self.assertTrue(skeptic_tail_solo(_sk(), [2, 5, 1, 1]))

    def test_a_leading_solo_wave_blocks_the_deduction(self):
        """**実測 08-25T08:32 の `[1,1,6,1]` は本物の違反**（explorer の先頭分割）.

        控除は総本数を 1 増やすだけなので、超過 1 の回はそれで消える。末尾より前に単独
        wave が残っている回で控除すると、**この違反が丸ごと見えなくなる**。
        """
        self.assertFalse(skeptic_tail_solo(_sk(), [1, 1, 6, 1]))

    def test_a_solo_wave_in_the_middle_blocks_the_deduction(self):
        self.assertFalse(skeptic_tail_solo(_sk(), [2, 1, 5, 1]))

    def test_the_scan_stops_at_the_first_non_solo_wave(self):
        """末尾の**連続**だけを数える（飛び越えて数えると先頭の分割を消す）.

        `[1,6,1]` は末尾の連なりが 1 本で、その手前に単独 wave が残る形。走査が
        非単独 wave で止まらないと連なりが 3 本と数えられ、手前が空になって控除が効く。
        """
        self.assertFalse(skeptic_tail_solo(_sk(), [1, 6, 1]))

    def test_a_non_solo_tail_is_not_deducted(self):
        """fallback は単独 1 体なので、末尾が 2 体以上ならその形では説明できない."""
        self.assertFalse(skeptic_tail_solo(_sk(), [2, 2, 4]))

    def test_an_all_solo_run_is_deducted_only_once(self):
        """全部が単独 wave の回。控除は**常に 1 本だけ**（末尾の連なりの本数ではない）.

        `[1,1]` は reviewer 1 体 + skeptic 1 体の正当な形なので違反にならないが、
        `[1,1,1]` は 1 本ぶんしか説明が付かないので違反として残る。
        """
        p = dict(_sk(), agents={"reviewer": 1})
        self.assertEqual(expected_waves(p, [1, 1]), 2)
        self.assertEqual(expected_waves(p, [1, 1, 1]), 2)

    def test_an_unfired_skeptic_is_not_deducted(self):
        """形だけで引くと本物を取り逃す."""
        self.assertFalse(skeptic_tail_solo(_sk(fired=False), [2, 5, 1]))

    def test_a_missing_skeptic_object_is_not_deducted(self):
        self.assertFalse(skeptic_tail_solo({}, [2, 5, 1]))

    def test_missing_wave_sizes_is_not_deducted(self):
        """`wave_sizes` を引けない回（`measure-tokens.sh` が `unresolved` に倒した回）."""
        self.assertFalse(skeptic_tail_solo(_sk(), None))
        self.assertFalse(skeptic_tail_solo(_sk(), []))

    def test_a_non_list_wave_sizes_is_rejected_before_the_scan(self):
        """**型で先に落とす**（走査に落ちると `TypeError` で publish が丸ごと死ぬ）.

        `wave_sizes` は JSON 由来なので、リスト以外が来ないことを式は保証できない。
        """
        self.assertFalse(skeptic_tail_solo(_sk(), 3))
        self.assertFalse(skeptic_tail_solo(_sk(), "31"))


class RealShapesTest(unittest.TestCase):
    """#200 に関わる実測 7 件の形を式に通す（判定の変化を表明する）.

    層構成は `wave_sizes` と申告体数の突合による**推定**（issue の補足のとおり）。
    ここで縛りたいのは「この形をこう判定する」という式の側の表明。
    """

    #: (ラベル, wave_sizes, agents, skeptic 発火, meta が指摘を足したか, 違反として残るか)
    SHAPES = [
        # ---- 偽陽性（式が正しく効けば違反にならない形）----
        # #166 の meta 項が入る前に publish された回。payload には期待 3 が焼かれているが、
        # 現行式では 4 で違反にならない。**再計算しないとこれが違反として残り続ける**
        ("[6,10,4,1] meta 反証つき", [6, 10, 4, 1],
         {"explorer": 6, "reviewer": 10, "verify": 4}, False, True, False),
        # skeptic fallback が末尾の単独 wave になった形（#172 の控除が効く）
        ("[2,5,1] skeptic 末尾", [2, 5, 1], {"explorer": 2, "reviewer": 5}, True, False, False),
        # **#200 の偽陽性 2 件目**: skeptic の後ろに反証 wave が付き、初版の控除が効かなかった
        ("[2,5,1,1] skeptic + 反証", [2, 5, 1, 1],
         {"explorer": 2, "reviewer": 5, "verify": 1}, True, False, False),
        # ---- 本物（#200 が内訳を割った 2 型）----
        # 型①: explorer を 1 体ずつ発行（先頭が単独 wave）
        ("[1,1,6,1] explorer 分割", [1, 1, 6, 1],
         {"explorer": 2, "reviewer": 5, "verify": 1}, True, False, True),
        ("[1,2,1,2,1] explorer 分割", [1, 2, 1, 2, 1],
         {"explorer": 2, "reviewer": 5}, True, False, True),
        # 型②: 同一層の wave 分割
        ("[2,2,4] 層の分割", [2, 2, 4], {"explorer": 2, "reviewer": 5}, True, False, True),
        ("[2,3] 層の分割", [2, 3], {"reviewer": 5}, False, False, True),
    ]

    def test_the_named_shapes_keep_their_verdict(self):
        for label, sizes, agents, fired, meta, violates in self.SHAPES:
            with self.subTest(shape=label):
                p = dict(_sk(fired), agents=agents,
                         meta_reviewer={"fired": meta, "findings_added": 2 if meta else 0})
                self.assertEqual(len(sizes) > expected_waves(p, sizes), violates,
                                 "期待本数 %d / 実 %d" % (expected_waves(p, sizes), len(sizes)))


if __name__ == "__main__":
    unittest.main()
