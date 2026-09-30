#!/usr/bin/env python3
"""issue-workflow 同梱 `scripts/business-days.py` の CLI 境界テスト（GitHub issue #255）.

祝日の期待値は内閣府の公表データ（syukujitsu.csv）の 2020〜2027 年の日付をそのまま写したもので、
スクリプトの規則とは独立に作ってある。規則で期待値を作ると、規則の誤りがそのまま通る。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "issue-workflow" / "scripts" / "business-days.py"

# 内閣府「国民の祝日」CSV の 2020〜2027 年（振替休日・国民の休日を含む）
CAO_HOLIDAYS = """
2020/1/1 2020/1/13 2020/2/11 2020/2/23 2020/2/24 2020/3/20 2020/4/29 2020/5/3 2020/5/4 2020/5/5
2020/5/6 2020/7/23 2020/7/24 2020/8/10 2020/9/21 2020/9/22 2020/11/3 2020/11/23
2021/1/1 2021/1/11 2021/2/11 2021/2/23 2021/3/20 2021/4/29 2021/5/3 2021/5/4 2021/5/5 2021/7/22
2021/7/23 2021/8/8 2021/8/9 2021/9/20 2021/9/23 2021/11/3 2021/11/23
2022/1/1 2022/1/10 2022/2/11 2022/2/23 2022/3/21 2022/4/29 2022/5/3 2022/5/4 2022/5/5 2022/7/18
2022/8/11 2022/9/19 2022/9/23 2022/10/10 2022/11/3 2022/11/23
2023/1/1 2023/1/2 2023/1/9 2023/2/11 2023/2/23 2023/3/21 2023/4/29 2023/5/3 2023/5/4 2023/5/5
2023/7/17 2023/8/11 2023/9/18 2023/9/23 2023/10/9 2023/11/3 2023/11/23
2024/1/1 2024/1/8 2024/2/11 2024/2/12 2024/2/23 2024/3/20 2024/4/29 2024/5/3 2024/5/4 2024/5/5
2024/5/6 2024/7/15 2024/8/11 2024/8/12 2024/9/16 2024/9/22 2024/9/23 2024/10/14 2024/11/3
2024/11/4 2024/11/23
2025/1/1 2025/1/13 2025/2/11 2025/2/23 2025/2/24 2025/3/20 2025/4/29 2025/5/3 2025/5/4 2025/5/5
2025/5/6 2025/7/21 2025/8/11 2025/9/15 2025/9/23 2025/10/13 2025/11/3 2025/11/23 2025/11/24
2026/1/1 2026/1/12 2026/2/11 2026/2/23 2026/3/20 2026/4/29 2026/5/3 2026/5/4 2026/5/5 2026/5/6
2026/7/20 2026/8/11 2026/9/21 2026/9/22 2026/9/23 2026/10/12 2026/11/3 2026/11/23
2027/1/1 2027/1/11 2027/2/11 2027/2/23 2027/3/21 2027/3/22 2027/4/29 2027/5/3 2027/5/4 2027/5/5
2027/7/19 2027/8/11 2027/9/20 2027/9/23 2027/10/11 2027/11/3 2027/11/23
"""


def _iso(cao: str) -> str:
    y, m, d = cao.split("/")
    return f"{y}-{int(m):02d}-{int(d):02d}"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=30)


class HolidaysTest(unittest.TestCase):
    def test_matches_cabinet_office_2020_to_2027(self):
        res = run("holidays", "2020-01-01", "2027-12-31")
        self.assertEqual(res.returncode, 0, res.stderr)
        got = [line.split("\t")[0] for line in res.stdout.splitlines()]
        self.assertEqual(got, [_iso(d) for d in CAO_HOLIDAYS.split()])

    def test_names_substitute_and_citizens_holiday(self):
        out = run("holidays", "2026-05-01", "2026-09-30").stdout
        self.assertIn("2026-05-06\t水\t休日（振替休日）", out)
        self.assertIn("2026-09-22\t火\t休日（国民の休日）", out)


class CountTest(unittest.TestCase):
    def count(self, *args: str) -> str:
        res = run("count", *args)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout.strip()

    def test_both_ends_are_included_by_default(self):
        # 2026-09-28（月）〜10-02（金）は祝日なし
        self.assertEqual(self.count("2026-09-28", "2026-10-02"), "5")

    def test_exclude_flags(self):
        self.assertEqual(self.count("2026-09-28", "2026-10-02", "--exclude-start"), "4")
        self.assertEqual(self.count("2026-09-28", "2026-10-02", "--exclude-end"), "4")
        self.assertEqual(
            self.count("2026-09-28", "2026-10-02", "--exclude-start", "--exclude-end"), "3")

    def test_single_day(self):
        self.assertEqual(self.count("2026-09-30", "2026-09-30"), "1")
        self.assertEqual(self.count("2026-09-30", "2026-09-30", "--exclude-end"), "0")

    def test_citizens_holiday_is_not_a_business_day(self):
        # シルバーウィーク: 9/21 敬老の日・9/22 国民の休日・9/23 秋分の日
        self.assertEqual(self.count("2026-09-21", "2026-09-25"), "2")

    def test_weekend_is_not_a_business_day(self):
        self.assertEqual(self.count("2026-10-03", "2026-10-04"), "0")


class AddTest(unittest.TestCase):
    def add(self, start: str, n: str) -> str:
        res = run("add", start, n)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout.strip()

    def test_skips_weekend_and_holidays(self):
        # 9/18（金）の 1 営業日後は、土日と 9/21〜23 を飛ばして 9/24
        self.assertEqual(self.add("2026-09-18", "1"), "2026-09-24")

    def test_start_is_not_counted(self):
        self.assertEqual(self.add("2026-09-28", "1"), "2026-09-29")

    def test_negative(self):
        self.assertEqual(self.add("2026-09-24", "-1"), "2026-09-18")

    def test_zero_snaps_to_next_business_day(self):
        self.assertEqual(self.add("2026-10-03", "0"), "2026-10-05")
        self.assertEqual(self.add("2026-09-30", "0"), "2026-09-30")


class WeeksTest(unittest.TestCase):
    def test_holiday_week_is_short(self):
        res = run("weeks", "2026-09-14", "2026-10-04")
        self.assertEqual(res.returncode, 0, res.stderr)
        rows = [line.split("\t") for line in res.stdout.splitlines()]
        self.assertEqual([(r[0], r[1]) for r in rows],
                         [("2026-09-14", "5"), ("2026-09-21", "2"), ("2026-09-28", "5")])
        self.assertIn("2026-09-22 休日（国民の休日）", rows[1][2])
        self.assertEqual(rows[0][2], "")

    def test_partial_weeks_count_only_the_range(self):
        # 範囲の外にある同じ週の日は数えない
        rows = [l.split("\t") for l in run("weeks", "2026-09-30", "2026-10-06").stdout.splitlines()]
        self.assertEqual([(r[0], r[1]) for r in rows], [("2026-09-28", "3"), ("2026-10-05", "2")])


class InputContractTest(unittest.TestCase):
    """推測で数えずに止まること（exit 2・stdout は空）."""

    def assertRefused(self, *args: str) -> None:
        res = run(*args)
        self.assertEqual(res.returncode, 2, res.stdout)
        self.assertEqual(res.stdout, "")

    def test_out_of_supported_range(self):
        self.assertRefused("count", "2019-12-31", "2020-01-02")
        self.assertRefused("holidays", "2099-12-01", "2100-01-01")

    def test_add_walking_out_of_range(self):
        self.assertRefused("add", "2099-12-31", "5")

    def test_bad_date(self):
        self.assertRefused("count", "2026/09/28", "2026-10-02")
        self.assertRefused("count", "2026-02-30", "2026-03-02")

    def test_reversed_range(self):
        self.assertRefused("count", "2026-10-02", "2026-09-28")

    def test_today_is_accepted(self):
        self.assertEqual(run("add", "today", "0").returncode, 0)


if __name__ == "__main__":
    unittest.main()
