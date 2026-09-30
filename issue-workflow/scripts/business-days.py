#!/usr/bin/env python3
"""日本の祝日込みで営業日を数える（GitHub issue #255）。

日程・ペースを暗算すると、暦日で割る・連休の週を通常週として扱う・国民の休日を営業日に数える、
といった誤りを繰り返した（30 日で 4 件）。決定的に数える口をここに置く。

祝日は祝日法の規則で計算する（CSV を同梱すると年 1 回の更新が要り、収録範囲外が判定不能になる）。
対応は 2020〜2099 年。下限は現行の祝日の並び（天皇誕生日 2/23・スポーツの日）が揃った年、
上限は春分・秋分の近似式の適用範囲の端。範囲外は推測せず exit 2 で止める。
公表値との一致を確かめたのは 2020〜2027 年（テスト）。春分・秋分は前年 2 月の官報で確定するので、
それより先の年は近似式による推定値。
臨時の祝日（五輪による移動など）は OVERRIDES に年ごとに足す。将来の臨時祝日は法律が
できるまで分からないので、そのときに足す。

  business-days.py count FROM TO [--exclude-start] [--exclude-end]
      FROM〜TO の営業日数（既定は両端を含む）
  business-days.py add FROM N
      FROM から N 営業日後の日付（FROM 自身は数えない。N が負なら前、0 なら FROM 以降で最初の営業日）
  business-days.py holidays FROM TO
      範囲内の休日（祝日・振替休日・国民の休日）を「日付<TAB>曜日<TAB>名前」で列挙
  business-days.py weeks FROM TO
      月曜始まりの週ごとに「週の月曜<TAB>営業日数<TAB>その週の休日」を列挙

日付は YYYY-MM-DD か today。exit 0 成功 / 2 入力不正・対応範囲外。
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

MIN_YEAR, MAX_YEAR = 2020, 2099
WEEKDAYS = "月火水木金土日"

FIXED = {
    (1, 1): "元日",
    (2, 11): "建国記念の日",
    (2, 23): "天皇誕生日",
    (4, 29): "昭和の日",
    (5, 3): "憲法記念日",
    (5, 4): "みどりの日",
    (5, 5): "こどもの日",
    (8, 11): "山の日",
    (11, 3): "文化の日",
    (11, 23): "勤労感謝の日",
}
# (月, 第 n 月曜)
HAPPY_MONDAY = {
    (1, 2): "成人の日",
    (7, 3): "海の日",
    (9, 3): "敬老の日",
    (10, 2): "スポーツの日",
}
# 東京五輪による移動（五輪特措法）。その年の規則上の日付を置き換える
OVERRIDES = {
    2020: {"海の日": (7, 23), "スポーツの日": (7, 24), "山の日": (8, 10)},
    2021: {"海の日": (7, 22), "スポーツの日": (7, 23), "山の日": (8, 8)},
}


class InputError(Exception):
    pass


def _nth_monday(year: int, month: int, n: int) -> dt.date:
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(7 - first.weekday()) % 7 + 7 * (n - 1))


def _equinox_day(year: int, base: float) -> int:
    # 1980〜2099 年で使われる近似式。base は春分 20.8431 / 秋分 23.2488
    y = year - 1980
    return int(base + 0.242194 * y - y // 4)


def _national_holidays(year: int) -> dict[dt.date, str]:
    """国民の祝日（振替休日・国民の休日を含まない）."""
    days: dict[dt.date, str] = {}
    override = OVERRIDES.get(year, {})
    for (m, d), name in FIXED.items():
        m, d = override.get(name, (m, d))
        days[dt.date(year, m, d)] = name
    for (m, n), name in HAPPY_MONDAY.items():
        if name in override:
            days[dt.date(year, *override[name])] = name
        else:
            days[_nth_monday(year, m, n)] = name
    days[dt.date(year, 3, _equinox_day(year, 20.8431))] = "春分の日"
    days[dt.date(year, 9, _equinox_day(year, 23.2488))] = "秋分の日"
    return days


_CACHE: dict[int, dict[dt.date, str]] = {}


def holidays_of(year: int) -> dict[dt.date, str]:
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise InputError(f"対応範囲は {MIN_YEAR}〜{MAX_YEAR} 年: {year}")
    if year in _CACHE:
        return _CACHE[year]
    national = _national_holidays(year)
    days = dict(national)
    # 振替休日: 日曜の祝日の後で、最も近い祝日でない日
    for day in sorted(national):
        if day.weekday() == 6:
            sub = day + dt.timedelta(days=1)
            while sub in national:
                sub += dt.timedelta(days=1)
            days[sub] = "休日（振替休日）"
    # 国民の休日: 前日と翌日がともに国民の祝日で、自身は祝日でない日
    for day in sorted(national):
        mid = day + dt.timedelta(days=1)
        if mid + dt.timedelta(days=1) in national and mid not in days:
            days[mid] = "休日（国民の休日）"
    _CACHE[year] = days
    return days


def holiday_name(day: dt.date) -> str | None:
    return holidays_of(day.year).get(day)


def is_business_day(day: dt.date) -> bool:
    return day.weekday() < 5 and holiday_name(day) is None


def parse_date(text: str) -> dt.date:
    if text == "today":
        day = dt.date.today()
    else:
        try:
            day = dt.date.fromisoformat(text)
        except ValueError:
            raise InputError(f"日付は YYYY-MM-DD か today: {text}") from None
    holidays_of(day.year)  # 範囲外をここで止める
    return day


def _days(start: dt.date, end: dt.date):
    day = start
    while day <= end:
        yield day
        day += dt.timedelta(days=1)


def _ordered(start: dt.date, end: dt.date) -> None:
    if start > end:
        raise InputError(f"FROM が TO より後: {start} > {end}")


def cmd_count(args) -> None:
    start, end = parse_date(args.start), parse_date(args.end)
    _ordered(start, end)
    one = dt.timedelta(days=1)
    first = start + one if args.exclude_start else start
    last = end - one if args.exclude_end else end
    print(sum(1 for d in _days(first, last) if is_business_day(d)))


def cmd_add(args) -> None:
    day = parse_date(args.start)
    n = args.n
    if n == 0:
        while not is_business_day(day):
            day += dt.timedelta(days=1)
    step = dt.timedelta(days=1 if n > 0 else -1)
    for _ in range(abs(n)):
        day += step
        while not is_business_day(day):
            day += step
    holidays_of(day.year)
    print(day.isoformat())


def cmd_holidays(args) -> None:
    start, end = parse_date(args.start), parse_date(args.end)
    _ordered(start, end)
    for day in _days(start, end):
        name = holiday_name(day)
        if name:
            print(f"{day.isoformat()}\t{WEEKDAYS[day.weekday()]}\t{name}")


def cmd_weeks(args) -> None:
    start, end = parse_date(args.start), parse_date(args.end)
    _ordered(start, end)
    monday = start - dt.timedelta(days=start.weekday())
    while monday <= end:
        week = [d for d in _days(max(monday, start), min(monday + dt.timedelta(days=6), end))]
        n = sum(1 for d in week if is_business_day(d))
        off = ",".join(f"{d.isoformat()} {holiday_name(d)}" for d in week
                       if d.weekday() < 5 and holiday_name(d))
        print(f"{monday.isoformat()}\t{n}\t{off}")
        monday += dt.timedelta(days=7)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="business-days.py",
                                     description="日本の祝日込みで営業日を数える")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("count")
    p.add_argument("start"); p.add_argument("end")
    p.add_argument("--exclude-start", action="store_true")
    p.add_argument("--exclude-end", action="store_true")
    p.set_defaults(func=cmd_count)
    p = sub.add_parser("add")
    p.add_argument("start"); p.add_argument("n", type=int)
    p.set_defaults(func=cmd_add)
    for name, func in (("holidays", cmd_holidays), ("weeks", cmd_weeks)):
        p = sub.add_parser(name)
        p.add_argument("start"); p.add_argument("end")
        p.set_defaults(func=func)
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except InputError as e:
        print(f"business-days: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
