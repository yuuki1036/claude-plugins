"""🔁 付録と報告件数の上限（publish / retro が共有 / GitHub issue #248）。

契約 (a)（#248 で決定）: reviewer は実効閾値未満と判定した指摘に**本文を書かず件数だけ返す**
（`## below-threshold`）。🔁 付録に載せるのは閾値以上で列挙されたのに報告マトリクスを通らなかった
指摘だけ。したがって本文を持つ指摘の数は `pre_adjust − below_threshold` で、1 回ごとに

    報告件数 ≤ pre − below
    付録の行数 ≤ max((pre − below) − 報告件数, 0)

が成り立つ。

**skeptic / meta の `findings_added` は足さない**。両 SKILL は skeptic（review 5.8 / self-review 4.8）と
meta（5.6 / 4.6）を Step 6 の手順 1 より前に統合し、`pre_adjust_counts` はその統合の後に控える
（transcript でも skeptic 単独の指摘が pre に入っていた）。足すと二重計上で上限が緩み、既存データで
4 回の違反を見逃す。`## 16` の旧説明「手順 1 の後に走る層が足すので本文を書いてから捨てたが負になる」は
この順序と合わない — 負になる回は報告件数が上限を超えた回（`report_over`）として扱う。

実測（2 マシン合算 n=89）では付録が上限を超える回が 43 回あり（opus-4-8 は 54 回中 37 回）、
reviewer が `## below-threshold` の件数行の後や独自の節に本文を書き、オーケストレーターが
below に数えたうえで付録にも載せていた。
"""

from __future__ import annotations

SEVS = ("blocker", "critical", "major", "minor")
REPORT_KEYS = tuple(s + "_count" for s in SEVS)


def _count(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def body_bound(payload: dict) -> dict | None:
    """判定に要る値が揃っていれば上限と実数を、揃わなければ None を返す.

    **揃わない回は判定しない**（推測で 0 を埋めると上限が下がり、違反を作る）:
    `pre_adjust_counts`（schema 2 以上・4 キー）/ `below_threshold_counts`（4 キー）/ 報告件数 4 つ /
    `appendix.listed` のどれかが欠けた回。
    """
    pre = payload.get("pre_adjust_counts")
    below = payload.get("below_threshold_counts")
    appendix = payload.get("appendix")
    if not isinstance(pre, dict) or not isinstance(below, dict) or not isinstance(appendix, dict):
        return None
    schema = pre.get("schema")
    if not isinstance(schema, int) or isinstance(schema, bool) or schema < 2:
        return None
    pre_n = [_count(pre.get(s)) for s in SEVS]
    below_n = [_count(below.get(s)) for s in SEVS]
    reported_n = [_count(payload.get(k)) for k in REPORT_KEYS]
    listed = _count(appendix.get("listed"))
    if None in pre_n or None in below_n or None in reported_n or listed is None:
        return None
    written = sum(pre_n) - sum(below_n)
    reported = sum(reported_n)
    appendix_cap = max(written - reported, 0)
    return {"written": written, "reported": reported, "listed": listed,
            "appendix_cap": appendix_cap,
            "appendix_over": listed > appendix_cap,
            "report_over": reported > written}
