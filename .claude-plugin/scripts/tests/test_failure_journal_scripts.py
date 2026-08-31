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
LOOKUP = ROOT / "failure-journal" / "scripts" / "tag-split-lookup.sh"
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


def spl(declared_at: str, umbrella: str, subs: list[str] | None = None,
        redirects: list[str] | None = None) -> str:
    row: dict = {"declared_at": declared_at, "umbrella": umbrella,
                 "sub_tags": [{"tag": t, "mechanism": f"{t} の機構"} for t in (subs or ["sub-a"])]}
    if redirects is not None:
        row["redirects"] = [{"when": "他者の出力を検算せず採用", "tag": t} for t in redirects]
    return json.dumps(row, ensure_ascii=False)


class AggregateTestCase(unittest.TestCase):
    """`retro-aggregate.sh` の集計契約."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def run_agg(self, journal: list[str] | None = None, remediations: list[str] | None = None,
                *, splits: list[str] | None = None, args: list[str] | None = None,
                now: str | None = NOW,
                env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        cmd = ["bash", str(AGGREGATE)]
        if splits is not None:
            p = self.dir / "splits.jsonl"
            p.write_text("".join(line + "\n" for line in splits), encoding="utf-8")
            cmd += ["--splits", str(p)]
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


class SplitLookupTest(unittest.TestCase):
    """`tag-split-lookup.sh` の照会契約（GitHub issue #195）.

    **壊れ方が「分割されていない」に化ける**のがこのスクリプトの怖いところで、
    起票側は黙って umbrella へ寄せる。落ちたことが分かる形（exit 2）を契約として固定する。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def run_lookup(self, lines: list[str] | None = None, *, raw: str | None = None,
                   args: list[str] | None = None,
                   env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        cmd = [BASH, str(LOOKUP)]
        if lines is not None or raw is not None:
            p = self.dir / "splits.jsonl"
            p.write_text(raw if raw is not None else "".join(l + "\n" for l in lines),
                         encoding="utf-8")
            cmd += ["--splits", str(p)]
        cmd += args or []
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)

    def splits(self, proc: subprocess.CompletedProcess[str]) -> list[dict]:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)["splits"]

    def test_missing_file_answers_empty(self):
        """新規プロジェクトでは宣言が無い。**毎回 Phase 2 を止めない**."""
        proc = self.run_lookup(args=["--splits", str(self.dir / "nope.jsonl")])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), {"splits": []})

    def test_declaration_is_returned_with_mechanism(self):
        """`mechanism` は起票側が読む唯一の行。projection で落とさない."""
        got = self.splits(self.run_lookup([spl("2026-08-20T00:00:00Z", "umb", ["sub-a"])]))
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["umbrella"], "umb")
        self.assertEqual(got[0]["declared_at"], "2026-08-20T00:00:00Z")
        self.assertEqual([t["tag"] for t in got[0]["sub_tags"]], ["sub-a"])
        self.assertEqual(got[0]["sub_tags"][0]["mechanism"], "sub-a の機構")

    def test_latest_row_wins_but_the_oldest_date_is_the_origin(self):
        """**2 つの畳み込みを 1 つのテストで固定する**（min と last の取り違え）.

        内容は最新行（サブ tag を後から足せる）、`declared_at` は最古
        （足すたびに採用計測の起点が動くと、非追随の観測が毎回リセットされる）。
        """
        got = self.splits(self.run_lookup([
            spl("2026-08-20T00:00:00Z", "umb", ["sub-a"]),
            spl("2026-08-25T00:00:00Z", "umb", ["sub-a", "sub-b"]),
        ]))
        self.assertEqual(got[0]["declared_at"], "2026-08-20T00:00:00Z")
        self.assertEqual([t["tag"] for t in got[0]["sub_tags"]], ["sub-a", "sub-b"])

    def test_same_timestamp_resolves_to_the_last_line(self):
        """同時刻の 2 行は**ファイル末尾**が勝つ（append-only の「最後に書いた方」）."""
        got = self.splits(self.run_lookup([
            spl("2026-08-20T00:00:00Z", "umb", ["old"]),
            spl("2026-08-20T00:00:00Z", "umb", ["new"]),
        ]))
        self.assertEqual([t["tag"] for t in got[0]["sub_tags"]], ["new"])

    def test_broken_line_is_undecidable_not_empty(self):
        """**捨てると「分割なし」に化ける**。行番号つきで止める（fail-loud）."""
        proc = self.run_lookup(raw=spl("2026-08-20T00:00:00Z", "umb") + "\nこわれた行\n")
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("2 行目", proc.stderr)

    def test_row_missing_required_fields_is_undecidable(self):
        proc = self.run_lookup(raw='{"declared_at":"2026-08-20T00:00:00Z"}\n')
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("1 行目", proc.stderr)

    def test_row_with_non_string_fields_is_undecidable(self):
        """型が違う行も「読めない」に含める（数値の日時は比較で静かに化ける）."""
        for raw in ('{"umbrella":"umb","declared_at":20260820}\n',
                    '{"umbrella":123,"declared_at":"2026-08-20T00:00:00Z"}\n'):
            with self.subTest(raw=raw):
                proc = self.run_lookup(raw=raw)
                self.assertEqual(proc.returncode, 2, proc.stdout)
                self.assertIn("1 行目", proc.stderr)

    def test_blank_lines_are_skipped(self):
        got = self.splits(self.run_lookup(raw="\n" + spl("2026-08-20T00:00:00Z", "umb") + "\n\n"))
        self.assertEqual(len(got), 1)

    def test_missing_redirects_is_an_empty_array(self):
        """キー欠落で落ちない（`redirects` は任意）."""
        got = self.splits(self.run_lookup([spl("2026-08-20T00:00:00Z", "umb")]))
        self.assertEqual(got[0]["redirects"], [])
        got = self.splits(self.run_lookup([
            spl("2026-08-20T00:00:00Z", "umb", redirects=["misread-or-trusted-bad-output"])]))
        self.assertEqual([r["tag"] for r in got[0]["redirects"]], ["misread-or-trusted-bad-output"])

    def test_umbrellas_are_sorted(self):
        got = self.splits(self.run_lookup([
            spl("2026-08-20T00:00:00Z", "zulu"),
            spl("2026-08-21T00:00:00Z", "alpha"),
        ]))
        self.assertEqual([g["umbrella"] for g in got], ["alpha", "zulu"])

    def test_the_journal_next_door_is_not_read(self):
        """**起票側の Read 制約と衝突しない根拠**: 件数を 1 つも出力しない.

        journal を読む実装に退行したら、この tag 名か件数が出力に現れて落ちる。
        """
        (self.dir / "journal.jsonl").write_text(
            "".join(occ("2026-08-2%dT00:00:00Z" % (i % 10), "leaked-tag") + "\n"
                    for i in range(50)), encoding="utf-8")
        proc = self.run_lookup([spl("2026-08-20T00:00:00Z", "umb")])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("leaked-tag", proc.stdout)
        self.assertEqual(len(self.splits(proc)), 1)

    def test_unknown_flag_is_undecidable(self):
        proc = self.run_lookup(args=["--nope"])
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("不明な引数", proc.stderr)

    def test_flag_without_value_is_undecidable(self):
        proc = self.run_lookup(args=["--splits"])
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("値がありません", proc.stderr)

    def test_help_is_not_an_error(self):
        proc = self.run_lookup(args=["--help"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--splits", proc.stdout)

    def test_missing_jq_is_undecidable_not_empty(self):
        """jq が引けないときに `{\"splits\":[]}` を返すと「分割なし」に化ける.

        **bash は絶対パスで起動する**（PATH を空にしてから探すと bash 自身が引けない）。
        """
        empty_bin = self.dir / "empty-bin"
        empty_bin.mkdir()
        p = self.dir / "splits.jsonl"
        p.write_text(spl("2026-08-20T00:00:00Z", "umb") + "\n", encoding="utf-8")
        proc = subprocess.run([BASH, str(LOOKUP), "--splits", str(p)],
                              capture_output=True, text=True, timeout=60,
                              env={"PATH": str(empty_bin)})
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("jq", proc.stderr)


class SplitFieldTest(AggregateTestCase):
    """集計側の分割フィールド（GitHub issue #195）.

    **分割は語彙の宣言であって還流ではない。** 分子を動かしたら、対策を打っていない
    tag のアラームが消えて「還流後に再発なし」として報告される（#193 が避けた失敗）。
    """

    DECL = "2026-08-20T00:00:00Z"

    def test_without_splits_the_fields_are_null_and_false(self):
        t = self.tags(self.run_agg([occ("2026-08-25T00:00:00Z", "umb")], []))["umb"]
        self.assertIsNone(t["split_declared_at"])
        self.assertIsNone(t["sub_tags"])
        self.assertIsNone(t["count_after_split"])
        self.assertFalse(t["split_not_adopted"])

    def test_splits_do_not_move_the_numerator(self):
        """**本設計の要**: remediations 相乗りへの退行を止める.

        分割宣言があってもなくても、閾値判定に効くフィールドは 1 つも変わらない。
        """
        journal = [occ("2026-08-05T00:00:00Z", "umb"), occ("2026-08-25T00:00:00Z", "umb")]
        keys = ("count_window", "count_effective", "excluded_by_remediation",
                "effective_since", "over_threshold", "quiet_since_remediation",
                "last_remediated_at")
        without = self.tags(self.run_agg(journal, []))["umb"]
        with_splits = self.tags(self.run_agg(journal, [], splits=[spl(self.DECL, "umb")]))["umb"]
        self.assertEqual({k: without[k] for k in keys}, {k: with_splits[k] for k in keys})

    def test_occurrence_at_the_declaration_timestamp_counts(self):
        """宣言と同時刻の起票は「宣言後」に数える（境界を 1 つ狭める変異を殺す）."""
        t = self.tags(self.run_agg([occ(self.DECL, "umb")], [],
                                   splits=[spl(self.DECL, "umb")]))["umb"]
        self.assertEqual(t["count_after_split"], 1)
        self.assertTrue(t["split_not_adopted"])

    def test_occurrence_one_second_before_the_declaration_does_not_count(self):
        t = self.tags(self.run_agg([occ("2026-08-19T23:59:59Z", "umb")], [],
                                   splits=[spl(self.DECL, "umb")]))["umb"]
        self.assertEqual(t["count_after_split"], 0)
        self.assertFalse(t["split_not_adopted"], "宣言前の umbrella 起票は append-only どおり正しい")

    def test_declared_but_not_used_is_flagged(self):
        t = self.tags(self.run_agg([occ("2026-08-25T00:00:00Z", "umb")], [],
                                   splits=[spl(self.DECL, "umb", ["sub-a", "sub-b"])]))["umb"]
        self.assertEqual(t["split_declared_at"], self.DECL)
        self.assertEqual(t["sub_tags"], ["sub-a", "sub-b"])
        self.assertTrue(t["split_not_adopted"])

    def test_occurrence_after_the_declaration_but_outside_the_window_is_not_counted(self):
        """窓スコープで判定する。全期間にすると一度鳴った tag が永久に鳴る."""
        t = self.tags(self.run_agg([occ("2026-07-01T00:00:00Z", "umb")], [],
                                   splits=[spl("2026-06-01T00:00:00Z", "umb")]))["umb"]
        self.assertEqual(t["count_window"], 0)
        self.assertEqual(t["count_after_split"], 0)
        self.assertFalse(t["split_not_adopted"])

    def test_declaration_origin_is_the_oldest_row(self):
        """サブ tag を後から足しても採用計測の起点は動かない."""
        t = self.tags(self.run_agg([occ("2026-08-22T00:00:00Z", "umb")], [], splits=[
            spl(self.DECL, "umb", ["sub-a"]),
            spl("2026-08-24T00:00:00Z", "umb", ["sub-a", "sub-b"]),
        ]))["umb"]
        self.assertEqual(t["split_declared_at"], self.DECL)
        self.assertEqual(t["sub_tags"], ["sub-a", "sub-b"])
        self.assertEqual(t["count_after_split"], 1, "起点が最新行だと 0 になる")

    def test_the_sub_tag_row_is_not_marked_as_declared(self):
        t = self.tags(self.run_agg([occ("2026-08-25T00:00:00Z", "sub-a")], [],
                                   splits=[spl(self.DECL, "umb", ["sub-a"])]))["sub-a"]
        self.assertIsNone(t["split_declared_at"])
        self.assertFalse(t["split_not_adopted"])

    def test_broken_split_line_does_not_break_the_aggregation(self):
        """集計は fail-soft（照会側の fail-loud と非対称。理由は doc に明記）."""
        proc = self.run_agg([occ("2026-08-25T00:00:00Z", "umb")], [],
                            splits=["こわれた行", spl(self.DECL, "umb")])
        t = self.tags(proc)["umb"]
        self.assertTrue(t["split_not_adopted"])

    def test_a_row_with_a_non_string_declared_at_is_ignored(self):
        """**JSON としては読めるがスキーマが壊れている行**を弾く.

        読めない行は `_stream` の手前で落ちるので、スキーマ判定（`ok_split`）まで届く
        のはこの形だけ。受理すると `declared_at` が数値のまま比較に入り、jq は数値を
        文字列より小さく扱うので**窓内の全件が「宣言後」に化ける**。
        """
        broken = json.dumps({"umbrella": "umb", "declared_at": 20260820}, ensure_ascii=False)
        t = self.tags(self.run_agg([occ("2026-08-25T00:00:00Z", "umb")], [],
                                   splits=[broken]))["umb"]
        self.assertIsNone(t["split_declared_at"])
        self.assertIsNone(t["count_after_split"])
        self.assertFalse(t["split_not_adopted"])

    def test_an_umbrella_with_no_occurrences_is_not_synthesised(self):
        """splits にしか出てこない tag の行を作らない（発生も還流も無い行が並ぶ）."""
        t = self.tags(self.run_agg([occ("2026-08-25T00:00:00Z", "other")], [],
                                   splits=[spl(self.DECL, "umb")]))
        self.assertNotIn("umb", t)


if __name__ == "__main__":
    unittest.main()
