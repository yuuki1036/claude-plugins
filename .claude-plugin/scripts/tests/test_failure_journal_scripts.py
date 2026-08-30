#!/usr/bin/env python3
"""`failure-journal` 同梱スクリプトの回帰テスト（CLI 境界越しの subprocess テスト）.

**なぜあるか**（GitHub issue #193）: retro の閾値判定が「還流済みの発生」を除外しない
ため、対策を打った後も 30 日窓を抜けるまで同じ tag が鳴り続け、次の retro が同じ手を
再提案していた。除外を入れると今度は**黙って分子を減らす**危険が出る（「収まった」と
誤読される）ので、分母・除外件数の併記まで含めて契約として固定する。

壊れ方が「閾値の境界が 1 つずれる」「還流日ちょうどの発生が落ちる」なので、
**出力を見ても異常に見えない**。境界は必ずテスト側で独立に組んだ期待値と突き合わせる。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
AGGREGATE = ROOT / "failure-journal" / "scripts" / "retro-aggregate.sh"
# PATH を絞るテストのために解決しておく（絞ってから探すと bash 自身が引けない）
BASH = shutil.which("bash") or "/bin/bash"

NOW = "2026-08-30T12:00:00Z"
# NOW から 30 日窓の境界（テスト側で独立に算出した値。スクリプトの計算とは別経路）
WINDOW_SINCE = "2026-07-31T12:00:00Z"


def occ(ts: str, tag: str) -> str:
    return json.dumps({"timestamp": ts, "tag": tag, "phenomenon": "x", "context": {}},
                      ensure_ascii=False)


def rem(ts: str, tag: str, target: str = "convention", ref: str = "abc1234") -> str:
    return json.dumps({"timestamp": ts, "tag": tag, "target": target, "ref": ref},
                      ensure_ascii=False)


class AggregateTestCase(unittest.TestCase):
    """`retro-aggregate.sh` の集計契約."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def run_agg(self, journal: list[str] | None = None, remediations: list[str] | None = None,
                *, args: list[str] | None = None, now: str | None = NOW,
                env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        cmd = ["bash", str(AGGREGATE)]
        if journal is not None:
            p = self.dir / "journal.jsonl"
            p.write_text("".join(line + "\n" for line in journal), encoding="utf-8")
            cmd += ["--journal", str(p)]
        if remediations is not None:
            p = self.dir / "remediations.jsonl"
            p.write_text("".join(line + "\n" for line in remediations), encoding="utf-8")
            cmd += ["--remediations", str(p)]
        if now is not None:
            cmd += ["--now", now]
        cmd += args or []
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)

    def tags(self, proc: subprocess.CompletedProcess[str]) -> dict[str, dict]:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return {t["tag"]: t for t in json.loads(proc.stdout)["tags"]}


class WindowTest(AggregateTestCase):
    """窓の境界（還流記録が無いときの後方互換）."""

    def test_window_boundary_is_inclusive(self):
        """窓境界ちょうどの発生は**窓内**に数える（`>=` の境界）."""
        t = self.tags(self.run_agg([occ(WINDOW_SINCE, "alpha")], []))
        self.assertEqual(t["alpha"]["count_window"], 1)

    def test_occurrence_before_window_is_excluded(self):
        t = self.tags(self.run_agg([occ("2026-07-31T11:59:59Z", "alpha"),
                                    occ("2026-08-01T00:00:00Z", "alpha")], []))
        self.assertEqual(t["alpha"]["count_window"], 1)
        self.assertEqual(t["alpha"]["count_all_time"], 2)

    def test_days_option_moves_the_window(self):
        t = self.tags(self.run_agg([occ("2026-08-20T00:00:00Z", "alpha")], [],
                                   args=["--days", "5"]))
        self.assertEqual(t["alpha"]["count_window"], 0)
        self.assertEqual(t["alpha"]["count_all_time"], 1)

    def test_window_since_is_reported(self):
        """分母の境界を出力に載せる（読む側が窓を再現できないと件数を検算できない）."""
        proc = self.run_agg([occ("2026-08-20T00:00:00Z", "alpha")], [])
        self.assertEqual(json.loads(proc.stdout)["window"]["since"], WINDOW_SINCE)


class ThresholdTest(AggregateTestCase):
    """閾値の境界."""

    def test_exactly_at_threshold_is_over(self):
        """3 件ちょうどで閾値超え（`>=` を `>` にすると落ちる）."""
        t = self.tags(self.run_agg(
            [occ(f"2026-08-2{i}T00:00:00Z", "alpha") for i in (1, 2, 3)], []))
        self.assertEqual(t["alpha"]["count_effective"], 3)
        self.assertTrue(t["alpha"]["over_threshold"])

    def test_one_below_threshold_is_not_over(self):
        t = self.tags(self.run_agg(
            [occ(f"2026-08-2{i}T00:00:00Z", "alpha") for i in (1, 2)], []))
        self.assertFalse(t["alpha"]["over_threshold"])

    def test_threshold_option(self):
        t = self.tags(self.run_agg(
            [occ(f"2026-08-2{i}T00:00:00Z", "alpha") for i in (1, 2)], [],
            args=["--threshold", "2"]))
        self.assertTrue(t["alpha"]["over_threshold"])


class RemediationTest(AggregateTestCase):
    """還流済みの発生の除外（本 issue の主眼）."""

    def test_no_remediation_file_keeps_previous_behaviour(self):
        """還流記録が無い環境では分子＝分母（後方互換）."""
        proc = self.run_agg([occ(f"2026-08-2{i}T00:00:00Z", "alpha") for i in (1, 2, 3)],
                            remediations=None)
        t = self.tags(proc)
        self.assertEqual(t["alpha"]["count_effective"], t["alpha"]["count_window"])
        self.assertEqual(t["alpha"]["excluded_by_remediation"], 0)
        self.assertTrue(t["alpha"]["over_threshold"])

    def test_occurrences_before_remediation_leave_the_numerator(self):
        """#193 の実例: 窓内 3 件がすべて還流日より前なら閾値を鳴らさない."""
        t = self.tags(self.run_agg(
            [occ("2026-08-20T00:00:00Z", "alpha"),
             occ("2026-08-25T00:00:00Z", "alpha"),
             occ("2026-08-27T00:00:00Z", "alpha")],
            [rem("2026-08-28T00:00:00Z", "alpha")]))
        self.assertEqual(t["alpha"]["count_window"], 3)
        self.assertEqual(t["alpha"]["count_effective"], 0)
        self.assertEqual(t["alpha"]["excluded_by_remediation"], 3)
        self.assertFalse(t["alpha"]["over_threshold"])

    def test_denominator_and_exclusion_are_always_reported(self):
        """**黙って分子を減らさない**。分母と除外件数が消えたら誤読が形を変えて残る."""
        t = self.tags(self.run_agg(
            [occ("2026-08-20T00:00:00Z", "alpha")],
            [rem("2026-08-28T00:00:00Z", "alpha")]))["alpha"]
        self.assertEqual(t["count_window"] - t["count_effective"], t["excluded_by_remediation"])
        self.assertEqual(t["effective_since"], "2026-08-28T00:00:00Z")
        self.assertEqual(t["window_since"], WINDOW_SINCE)

    def test_occurrence_at_remediation_timestamp_counts(self):
        """還流日**ちょうど**の発生は分子に残す（`>=` の境界。落とすと再発を見逃す）."""
        t = self.tags(self.run_agg(
            [occ("2026-08-28T00:00:00Z", "alpha")],
            [rem("2026-08-28T00:00:00Z", "alpha")]))
        self.assertEqual(t["alpha"]["count_effective"], 1)
        self.assertEqual(t["alpha"]["excluded_by_remediation"], 0)

    def test_occurrence_after_remediation_still_fires(self):
        t = self.tags(self.run_agg(
            [occ("2026-08-20T00:00:00Z", "alpha")]
            + [occ(f"2026-08-2{i}T00:00:00Z", "alpha") for i in (8, 9)]
            + [occ("2026-08-30T00:00:00Z", "alpha")],
            [rem("2026-08-27T00:00:00Z", "alpha")]))
        self.assertEqual(t["alpha"]["count_window"], 4)
        self.assertEqual(t["alpha"]["count_effective"], 3)
        self.assertTrue(t["alpha"]["over_threshold"])
        self.assertFalse(t["alpha"]["quiet_since_remediation"])

    def test_remediation_older_than_window_does_not_shrink_the_window(self):
        """窓より古い還流は有効境界を動かさない（窓境界の方が遅い）."""
        t = self.tags(self.run_agg(
            [occ(f"2026-08-2{i}T00:00:00Z", "alpha") for i in (1, 2, 3)],
            [rem("2026-06-01T00:00:00Z", "alpha")]))["alpha"]
        self.assertEqual(t["effective_since"], WINDOW_SINCE)
        self.assertEqual(t["excluded_by_remediation"], 0)
        self.assertTrue(t["over_threshold"])

    def test_latest_remediation_wins_and_all_are_listed(self):
        t = self.tags(self.run_agg(
            [occ("2026-08-26T00:00:00Z", "alpha")],
            [rem("2026-08-28T00:00:00Z", "alpha", "hook", "df00462"),
             rem("2026-08-10T00:00:00Z", "alpha", "convention", "ac8214d")]))["alpha"]
        self.assertEqual(t["last_remediated_at"], "2026-08-28T00:00:00Z")
        self.assertEqual(t["effective_since"], "2026-08-28T00:00:00Z")
        self.assertEqual([r["ref"] for r in t["remediations"]], ["ac8214d", "df00462"])
        self.assertEqual([r["target"] for r in t["remediations"]], ["convention", "hook"])

    def test_remediation_only_tag_is_listed_as_quiet(self):
        """還流後 1 件も出ていない tag も行として出す（**シグナルはここにしか現れない**）."""
        t = self.tags(self.run_agg([occ("2026-08-20T00:00:00Z", "beta")],
                                   [rem("2026-08-10T00:00:00Z", "alpha")]))
        self.assertIn("alpha", t)
        self.assertEqual(t["alpha"]["count_window"], 0)
        self.assertTrue(t["alpha"]["quiet_since_remediation"])
        self.assertEqual(t["alpha"]["days_since_remediation"], 20)

    def test_quiet_requires_a_remediation(self):
        """還流していない tag は、発生が 0 件でも「還流後 0 件」ではない."""
        t = self.tags(self.run_agg([occ("2026-01-01T00:00:00Z", "alpha")], []))["alpha"]
        self.assertEqual(t["count_effective"], 0)
        self.assertIsNone(t["last_remediated_at"])
        self.assertFalse(t["quiet_since_remediation"])
        self.assertIsNone(t["days_since_remediation"])

    def test_remediation_of_another_tag_does_not_leak(self):
        t = self.tags(self.run_agg(
            [occ(f"2026-08-2{i}T00:00:00Z", "alpha") for i in (1, 2, 3)],
            [rem("2026-08-28T00:00:00Z", "beta")]))
        self.assertTrue(t["alpha"]["over_threshold"])
        self.assertEqual(t["alpha"]["excluded_by_remediation"], 0)


class MalformedInputTest(AggregateTestCase):
    """壊れた入力で集計を落とさない・混ぜない."""

    def test_broken_lines_are_skipped(self):
        t = self.tags(self.run_agg(
            ["これは JSON ではない", occ("2026-08-20T00:00:00Z", "alpha"), "{"], []))
        self.assertEqual(t["alpha"]["count_window"], 1)
        self.assertEqual(list(t), ["alpha"])

    def test_records_without_timestamp_are_dropped(self):
        """tag だけの行を通すと、集計に幽霊 tag が生える."""
        t = self.tags(self.run_agg(
            ['{"tag":"ghost"}', occ("2026-08-20T00:00:00Z", "alpha")], []))
        self.assertNotIn("ghost", t)

    def test_records_without_tag_are_dropped(self):
        t = self.tags(self.run_agg(
            ['{"timestamp":"2026-08-20T00:00:00Z"}', occ("2026-08-20T00:00:00Z", "alpha")], []))
        self.assertEqual(list(t), ["alpha"])

    def test_missing_journal_is_not_an_error(self):
        """初回実行（journal 未作成）は「失敗 0 件」であって判定不能ではない."""
        proc = subprocess.run(
            ["bash", str(AGGREGATE), "--journal", str(self.dir / "nope.jsonl"),
             "--remediations", str(self.dir / "nope2.jsonl"), "--now", NOW],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["tags"], [])

    def test_single_option_pair_is_accepted(self):
        """フラグ + 値がちょうど 1 組でも値なしと誤判定しない."""
        proc = subprocess.run(
            ["bash", str(AGGREGATE), "--journal", str(self.dir / "nope.jsonl")],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)


class ArgumentContractTest(AggregateTestCase):
    """exit code の契約: 0 集計成功 / 2 判定不能."""

    def _expect_rc2(self, args: list[str], needle: str) -> None:
        proc = subprocess.run(["bash", str(AGGREGATE), *args],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn(needle, proc.stderr)

    def test_non_numeric_days(self):
        self._expect_rc2(["--days", "thirty", "--now", NOW], "days")

    def test_non_numeric_threshold(self):
        self._expect_rc2(["--threshold", "-1", "--now", NOW], "threshold")

    def test_bad_now_format(self):
        self._expect_rc2(["--now", "2026-08-30"], "now")

    def test_unknown_flag(self):
        self._expect_rc2(["--nope"], "不明な引数")

    def test_flag_without_value(self):
        self._expect_rc2(["--days"], "値がありません")

    def test_missing_jq_is_undecidable_not_empty(self):
        """jq が引けないときに空の集計を返すと「失敗 0 件」に化ける.

        **bash は絶対パスで起動する**。PATH を空にしてから探すと bash 自身が引けず、
        「jq が無いから落ちた」ではない理由で落ちる（stderr の突合で見分けている）。
        """
        empty_bin = self.dir / "empty-bin"
        empty_bin.mkdir()
        journal = self.dir / "journal.jsonl"
        journal.write_text(occ("2026-08-20T00:00:00Z", "alpha") + "\n", encoding="utf-8")
        proc = subprocess.run(
            [BASH, str(AGGREGATE), "--journal", str(journal), "--now", NOW],
            capture_output=True, text=True, timeout=60, env={"PATH": str(empty_bin)})
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("jq", proc.stderr)


if __name__ == "__main__":
    unittest.main()
