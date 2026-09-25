"""`severity_threshold` の形の正規化（publish / retro が共有 / GitHub issue #252）。

契約はトップレベルの 1 キー（`orchestration-measurement.md ## 16`。v2.58.0〜必須）で、retro の
歩留まり・検出 → 報告の内訳の層別キーになる。LLM がテンプレートを埋めるときに直前の
`below_threshold_counts` / `pre_adjust_counts` の中へ 1 段深く書く回があり（版付き 47 件中 5 件。
値はすべて `MAJOR`）、その回は理由なしに主層から `threshold=?` 層へ落ちていた。

**救う理由は報告件数の入れ子（`lib/report_counts.py`）と同じ**。層別キーが 1 つ落ちるだけで
その回が主層から丸ごと外れ、救った事実は別識別子（`payload:severity_threshold.nested`）で残せる。

**推測はしない**。語彙外の値と、2 つの親で食い違う値は昇格しない（どれが実効値か決められない）。
"""

from __future__ import annotations

THRESHOLDS = ("BLOCKER", "CRITICAL", "MAJOR", "MINOR")
#: 入れ子の親として見るキー。実データの 5 件中 4 件が前者
NESTED_PARENTS = ("below_threshold_counts", "pre_adjust_counts")


def lift_nested_threshold(payload: dict) -> str | None:
    """入れ子の `severity_threshold` をトップレベルへ昇格する。昇格したら親キー名、しなければ None。

    トップレベルに値があれば（語彙外でも）触らない — 語彙の検証は呼び出し側の責務。
    親オブジェクトの中の値は残す（払い出した形の証拠）。
    """
    if payload.get("severity_threshold") is not None:
        return None
    found = []
    for parent in NESTED_PARENTS:
        nested = payload.get(parent)
        if isinstance(nested, dict) and nested.get("severity_threshold") is not None:
            found.append((parent, nested["severity_threshold"]))
    # 語彙外の値を先に捨ててから食い違いを見ると、`MAJOR` と `minor` のような組が 1 値に見えて
    # 昇格してしまう（実効値が MINOR だった可能性を消す）。書かれた値はすべて突合に入れる
    if (not found or any(value not in THRESHOLDS for _, value in found)
            or len({value for _, value in found}) != 1):
        return None
    payload["severity_threshold"] = found[0][1]
    return found[0][0]
