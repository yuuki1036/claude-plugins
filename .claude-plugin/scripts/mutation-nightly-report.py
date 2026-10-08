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
起票が要るのは次のどちらか:
  - 変異テストの step が success でない（生存・中断・テストが最初から赤）
  - 未実行（予算・上限）が 1 個以上ある
集計（`--summary`）が無い・読めない回は、step が success でも起票する（判定できないことを黙らせない）。
mutation-test.py は exit 0 で終わる回に必ず集計を書くので、success で集計が無いのは配線の故障。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PREFIX = "[mutation-nightly]"
TITLE_SURVIVED = PREFIX + " 生存した変異がある"
TITLE_UNEXECUTED = PREFIX + " 検証しきれなかった変異がある"
LOG_TAIL = 40


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


def build(outcome: str, summary: dict | None, log: str, base: str, head: str,
          run_url: str) -> tuple[str, str] | None:
    """(タイトル, 本文) を返す。起票が要らなければ None."""
    failed = outcome != "success"
    broken = summary is None
    budget = limit = 0
    if not broken:
        try:
            budget, limit = unexecuted(summary)
        except ValueError:
            broken = True
    if not failed and not broken and budget + limit == 0:
        return None

    out = []
    if failed:
        out += ["## 生存した変異がある（nightly / `--base %s`）" % base, "",
                "**生存 = そのコードを壊してもテストが落ちない**＝その挙動を検証していない。",
                "直し方は 2 つだけ: ①生存した変異を殺すテストを足す",
                "②等価変異なら**理由つきで** `# mutation-ok: <理由>` を同じ行に置く。", ""]
    if budget + limit:
        g = summary.get("generated")
        e = summary.get("executed")
        out += ["## 検証しきれなかった変異がある（nightly / `--base %s`）" % base, "",
                "生成 %s 個のうち実行 %s 個。**予算で未実行 %d / 上限で未実行 %d**。"
                % (g if g is not None else "?", e if e is not None else "?", budget, limit),
                "schedule の晩なら、未実行の変異は翌晩の範囲（この晩の head より後の変更行）から外れるので、このままでは**二度と回らない**。"
                "範囲を指定して回し直すときは、ワークフローの手動起動で `base` に下の起点を入れる"
                "（同じ予算で回すと同じ所で打ち切られるので、`--max` と予算に収まるように範囲を割る）。", ""]
    # step が落ちた回は集計が無くて当然（テストが最初から赤なら書く前に exit 2）なので、success の回だけ
    if broken and not failed:
        out += ["## 変異テストの集計を読めなかった（nightly / `--base %s`）" % base, "",
                "`--summary-json` の出力が無いか壊れている。未実行の有無を判定できないので起票した。", ""]
    out += ["- run: %s" % run_url, "- 対象: %s..%s" % (base, head), "", "```", log, "```"]
    return (TITLE_SURVIVED if failed else TITLE_UNEXECUTED), "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--outcome", required=True, help="変異テストの step の outcome（steps.<id>.outcome）")
    ap.add_argument("--summary", required=True, help="mutation-test.py --summary-json の出力")
    ap.add_argument("--log", required=True, help="mutation-test.py の出力ログ（末尾を本文に貼る）")
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--run-url", required=True)
    ap.add_argument("--out", required=True, help="本文を書くパス（起票が要らない回は書かない）")
    args = ap.parse_args(argv)
    got = build(args.outcome, load_summary(args.summary), log_tail(args.log), args.base, args.head,
                args.run_url)
    if got is None:
        return 0
    title, body = got
    Path(args.out).write_text(body, encoding="utf-8")
    print(title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
