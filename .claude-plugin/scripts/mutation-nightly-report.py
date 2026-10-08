#!/usr/bin/env python3
"""mutation-nightly の起票判定と本文の組み立て（GitHub issue #288）.

nightly の変異テストは、生存があれば `--strict` で落ちて起票される。ところが**予算や上限で打ち切った
変異は、生存が無ければ success で終わり起票されない**。打ち切った分は翌晩の範囲（この晩の head より後の変更行）
からも外れるので、検証されないまま消える。実測で 10-03 は 36 個中 10 個、09-28 は 36 個中 13 個が
この形で消えていた（どちらも success）。

判定と本文をワークフローの YAML に書くとテストできないので、ここに寄せる。

  mutation-nightly-report.py --outcome <success|failure|...> --summary s.json --log mutation.log \\
      --base <sha> --head <sha> --run-url <url> --out body.md

起票が要る回は issue のタイトルを stdout に 1 行で出し、本文を `--out` に書く。要らない回は何も出さない。
起票が要るのは次のどれか:
  - 変異テストの step が success でない（生存・中断・テストが最初から赤）
  - 未実行（予算・上限）がある。ただし持ち越しの状態（`--state`、mutation-nightly-state.py advance の出力）
    がある晩は、未実行は翌晩に持ち越されるので起票しない。持ち越しが `STALE_DAYS` 日以上解消していない
    （1 晩の処理量が流入に追いついていない）ときだけ起票する
  - 持ち越しの状態を失った（`--state-lost`。持ち越していた未実行の変異が回らなくなる）
集計（`--summary`）が無い・読めない回は、step が success でも起票する（判定できないことを黙らせない）。
mutation-test.py は exit 0 で終わる回に必ず集計を書くので、success で集計が無いのは配線の故障。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

PREFIX = "[mutation-nightly]"
TITLE_SURVIVED = PREFIX + " 生存した変異がある"
TITLE_UNEXECUTED = PREFIX + " 検証しきれなかった変異がある"
TITLE_NOT_RUN = PREFIX + " 変異テストを回せなかった"
TITLE_STATE = PREFIX + " 持ち越しの状態を読めなかった"
LOG_TAIL = 40
#: 持ち越しがこの日数以上解消していなければ起票する（毎晩の打ち切りは持ち越しで回収されるので起票しない）
STALE_DAYS = 7


def load_summary(path: str) -> dict | None:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def unexecuted(summary: dict) -> tuple[int, int]:
    """(予算で未実行, 上限で未実行)。値が数でなければ 0 に丸めず ValueError（壊れた集計を「0」と読まない）."""
    vals = []
    for k in ("unexecuted_budget", "unexecuted_max"):
        v = summary.get(k, 0)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise ValueError(k)
        vals.append(v)
    return vals[0], vals[1]


def log_tail(path: str) -> str:
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "(ログを取得できなかった)"
    return "\n".join(lines[-LOG_TAIL:])


def stale_days(state: dict | None, now: dt.datetime) -> int | None:
    """持ち越しが解消していない日数。持ち越しが無い・読めなければ None."""
    if not isinstance(state, dict) or not isinstance(state.get("remaining"), int) or state["remaining"] < 1:
        return None
    try:
        since = dt.datetime.fromisoformat(str(state.get("since")).replace("Z", "+00:00"))
    except ValueError:
        return None
    if since.tzinfo is None:
        since = since.replace(tzinfo=dt.timezone.utc)
    return (now - since).days


def build(outcome: str, summary: dict | None, log: str, base: str, head: str,
          run_url: str, state: dict | None = None, state_lost: bool = False, state_held: bool = False,
          now: dt.datetime | None = None) -> tuple[str, str] | None:
    """(タイトル, 本文) を返す。起票が要らなければ None."""
    failed = outcome != "success"
    broken = summary is None
    budget = limit = 0
    if not broken:
        try:
            budget, limit = unexecuted(summary)
        except ValueError:
            broken = True
    survived = summary.get("survived") if isinstance(summary, dict) else None
    has_survivors = isinstance(survived, int) and not isinstance(survived, bool) and survived > 0
    days = stale_days(state, now or dt.datetime.now(dt.timezone.utc))
    # **持ち越しがある晩の打ち切りは起票しない**（翌晩に回る。毎晩起票すると騒音になる）。持ち越しが
    # 解消しないまま日数が経ったときだけ起票する
    carried = isinstance(state, dict)
    stale = carried and days is not None and days >= STALE_DAYS
    lost_cut = budget + limit > 0 and not carried
    if not failed and not broken and not stale and not lost_cut and not state_lost:
        return None

    out = []
    if failed and has_survivors:
        out += ["## 生存した変異がある（nightly / `--base %s`）" % base, "",
                "**生存 = そのコードを壊してもテストが落ちない**＝その挙動を検証していない。",
                "直し方は 2 つだけ: ①生存した変異を殺すテストを足す",
                "②等価変異なら**理由つきで** `# mutation-ok: <理由>` を同じ行に置く。", ""]
    elif failed:
        # 変異前のテストが赤い（集計を書かずに exit 2）・中断など。生存の見出しで出すと実態と食い違う
        out += ["## 変異テストを回せなかった（nightly / `--base %s`）" % base, "",
                "変異前のテストが赤い・中断したなど、生存 0 のまま step が落ちた。ログの末尾で原因を見る。",
                "持ち越しの状態は前の晩のまま残るので、範囲は直った後の晩に回る。", ""]
    if stale:
        out += ["## 持ち越しが %d 日以上解消していない（nightly / `--base %s`）" % (days, base), "",
                "起点 `%s` から残り %d 個の変異が回っていない（%s から）。1 晩に回せる数が新しく入る変更行の"
                "変異に追いついていないか、変異前のテストが赤い晩が続いている。予算を延ばす・1 変異のコストを"
                "下げる・赤いテストを直す（#288）。"
                % (str(state.get("base", "?"))[:12], state["remaining"], state.get("since")), ""]
    elif lost_cut:
        g = summary.get("generated")
        e = summary.get("executed")
        out += ["## 検証しきれなかった変異がある（nightly / `--base %s`）" % base, "",
                "生成 %s 個のうち実行 %s 個。**予算で未実行 %d / 上限で未実行 %d**。"
                % (g if g is not None else "?", e if e is not None else "?", budget, limit),
                "持ち越しの状態が無い晩なので、未実行の変異が翌晩以降に回る保証は無い。"
                "範囲を指定して回し直すときは、ワークフローの手動起動で `base` に下の起点を入れる"
                "（同じ予算で回すと同じ所で打ち切られるので、`--max` と予算に収まるように範囲を割る）。", ""]
    if state_lost and state_held:
        out += ["## 持ち越しの状態を読めなかった（nightly / `--base %s`）" % base, "",
                "前の晩までの状態（artifact `mutation-state`）を読めなかった（API の失敗など）。前の状態は"
                "上書きしていないので、読めるようになった晩にそこから再開する。今晩の範囲は代わりの起点で回した。"
                "続くならログの resolve-base の warning で原因を見る。", ""]
    elif state_lost:
        out += ["## 持ち越しの状態を失った（nightly / `--base %s`）" % base, "",
                "前の晩までの状態（artifact `mutation-state`）が壊れている・期限切れ・起点が HEAD の祖先でない。"
                "持ち越していた未実行の変異は回らない。ログの resolve-base の warning で原因を見る。", ""]
    # step が落ちた回は集計が無くて当然（テストが最初から赤なら書く前に exit 2）なので、success の回だけ
    if broken and not failed:
        out += ["## 変異テストの集計を読めなかった（nightly / `--base %s`）" % base, "",
                "`--summary-json` の出力が無いか壊れている。未実行の有無を判定できないので起票した。", ""]
    out += ["- run: %s" % run_url, "- 対象: %s..%s" % (base, head), "", "```", log, "```"]
    if failed:
        title = TITLE_SURVIVED if has_survivors else TITLE_NOT_RUN
    elif stale or lost_cut or broken:
        title = TITLE_UNEXECUTED
    else:
        title = TITLE_STATE
    return title, "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--outcome", required=True, help="変異テストの step の outcome（steps.<id>.outcome）")
    ap.add_argument("--summary", required=True, help="mutation-test.py --summary-json の出力")
    ap.add_argument("--log", required=True, help="mutation-test.py の出力ログ（末尾を本文に貼る）")
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--run-url", required=True)
    ap.add_argument("--out", required=True, help="本文を書くパス（起票が要らない回は書かない）")
    ap.add_argument("--state", default=None,
                    help="持ち越しの状態（mutation-nightly-state.py advance の出力）。読めなければ持ち越し無しと扱う")
    ap.add_argument("--state-lost", action="store_true", help="前の晩までの状態を読めなかった")
    ap.add_argument("--state-held", action="store_true",
                    help="読めなかった状態を上書きせずに残した（翌晩に再開する）")
    args = ap.parse_args(argv)
    got = build(args.outcome, load_summary(args.summary), log_tail(args.log), args.base, args.head,
                args.run_url, state=load_summary(args.state) if args.state else None,
                state_lost=args.state_lost, state_held=args.state_held)
    if got is None:
        return 0
    title, body = got
    Path(args.out).write_text(body, encoding="utf-8")
    print(title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
