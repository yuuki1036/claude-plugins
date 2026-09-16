"""報告件数 4 フィールドの形の正規化（publish / retro が共有 / GitHub issue #238）。

契約はトップレベルのフラット 4 キー（`orchestration-measurement.md ## 16`）だが、LLM が
テンプレートを埋める形は回ごとにばらける。実データで観測した 3 形:

- `counts: {blocker, critical, major, minor}`（接尾辞なし・小文字）
- `counts: {BLOCKER, CRITICAL, MAJOR, MINOR}`（大文字）
- `report_counts: {blocker_count, …}`（gap 識別子 `report_counts.missing` の名前を構造化した形）

いずれも publish が「4 キー欠測」と判定し、その回は歩留まり・報告 0 件率・真の空振り・
`findings_class` 突合の**すべての分子**から外れていた（#215 は検知だけで防止になっていない）。

**`.misplaced`（#208）が「値は救わない」としたのと方向が逆になる**。あちらは親オブジェクトの
中に本来の位置があり、救うと埋める側が誤置に気づかず是正先（ネストを戻す）が読めなくなる。
こちらは 4 分子すべてが丸ごと失われるうえ、救った事実を別識別子（`payload:report_counts.nested`）
で残せば「フラット規約が破られた」は同じく観測できる。失うものと残せるものの釣り合いが違う。

**部分欠測は救わない**。トップレベルに 4 キーのうち 1 つでもあれば入れ子を見ない（そこは
`report_counts.missing` の側で、混ぜると「3 つ書いて 1 つ入れ子」のような形まで受理してしまう）。
入れ子側も 4 つ揃って非負整数のときだけ昇格する。
"""

from __future__ import annotations

SEVS = ("blocker", "critical", "major", "minor")
REPORT_KEYS = tuple(s + "_count" for s in SEVS)
#: 入れ子の親として受理するキー。先に見つかった方を使う
NESTED_PARENTS = ("report_counts", "counts")


def is_count(v) -> bool:
    """非負整数か（JSON の `true` は int の派生なので bool を先に弾く）。"""
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def lift_nested_report_counts(payload: dict) -> str | None:
    """入れ子の報告件数をトップレベルへ昇格する。昇格したら親キー名、しなければ None。

    親オブジェクトは残す（払い出した形の証拠。集計は昇格後のトップレベルだけを読む）。
    """
    if any(k in payload for k in REPORT_KEYS):
        return None
    for parent in NESTED_PARENTS:
        nested = payload.get(parent)
        if not isinstance(nested, dict):
            continue
        norm = {}
        for k, v in nested.items():
            if not isinstance(k, str):
                continue
            base = k.lower()
            if base.endswith("_count"):
                base = base[: -len("_count")]
            if base in SEVS:
                norm[base + "_count"] = v
        if all(is_count(norm.get(k)) for k in REPORT_KEYS):
            for k in REPORT_KEYS:
                payload[k] = norm[k]
            return parent
    return None
