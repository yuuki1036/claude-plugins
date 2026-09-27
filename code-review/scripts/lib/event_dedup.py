"""複数ログを合算するときの `review:completed` の重複除去（retro が使う）。

**キーは `(ts, plugin)`**。計測ストア（private リポジトリ review-metrics の `bin/sanitize.py`）が
マシン間の合算に使う union キーと同じにする。以前は `ts` + `plugin` + payload 全体をキーにしていたので、
ストアのサニタイズ済みの行（`pr` と `base` を落とし、`machine_id` を label にし、語彙外の文字列を
`other` に置き換えた行）とローカルの生の `events.jsonl` を合算すると、同じイベントが別物として 2 回数えられた
（実測: 生の gist なら n=282 の組み合わせが、サニタイズ済みのストアでは n=335。53 件が二重）。

同じ `(ts, plugin)` の行が 2 本来たときの扱い:

1. payload が同一 → 重複（従来どおり）
2. 片方がもう片方のサニタイズ済みの形 → 重複。**生の側（情報が多い側）を採る**。`other` に置き換わった
   値を集計の層に入れないため。「サニタイズ済みの形」とは、トップレベルの `machine_id` を除いて、
   キーがすべて相手にもあり、値が一致するか、文字列が `other` に置き換わっているか、有限でない数が
   null になっているもの（相手にだけあるキーは、落とされたキーとして許す）。`missing_coverage[]` は
   `:` 区切りの語ごとに `other` へ置き換わる（`reviewer:<未知の語>` → `reviewer:other`）ので、文字列は
   区切りの数が同じで語ごとに一致か `other` のものも含める。互いにそう言える
   （`machine_id` だけが違う）ときは下の 3 と同じ規則で片方を採る
3. どちらでもない（中身が食い違う）→ **片方だけを数え、件数を報告する**（呼び出し側が WARN と母集団行に出す）。
   採るのは計測ストアの union と同じ規則で、正規形の JSON が長い方、同じ長さなら辞書順で後ろの方。
   引数の順に依存させない（`--logs` の並びで集計が変わらない）

`ts` が空・文字列でない行は時刻でイベントを識別できないので、従来どおり payload 全体をキーに含める
（時刻の壊れた別々のイベントを 1 件に畳まない）。
"""

from __future__ import annotations

import json
import math

#: サニタイザが語彙外の文字列を置き換える値（review-metrics の `bin/sanitize.py` と同じ）
SANITIZED = "other"
#: サニタイザが別の値に付け替えるトップレベルのキー（生の hostname → label）。突合では見ない
REWRITTEN_TOP_KEYS = frozenset({"machine_id"})


def canonical(value) -> str:
    """比較と採否の規則に使う正規形（キー整列・ASCII・区切りの空白なし）."""
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def covers(rich, poor, top: bool = True) -> bool:
    """`poor` が `rich` をサニタイズした形として説明できるか."""
    if isinstance(poor, dict):
        if not isinstance(rich, dict):
            return False
        for key, value in poor.items():
            if top and key in REWRITTEN_TOP_KEYS:
                continue
            if key not in rich or not covers(rich[key], value, top=False):
                return False
        return True
    if isinstance(poor, list):
        return (isinstance(rich, list) and len(rich) == len(poor)
                and all(covers(r, p, top=False) for r, p in zip(rich, poor)))
    if isinstance(poor, str):
        if not isinstance(rich, str):
            return False
        if poor == rich or poor == SANITIZED:
            return True
        # `:` 区切りの一部だけ置き換わった形（`missing_coverage[]`）
        segs_poor, segs_rich = poor.split(":"), rich.split(":")
        return (len(segs_poor) == len(segs_rich) > 1
                and all(p == r or p == SANITIZED for p, r in zip(segs_poor, segs_rich)))
    if poor is None:
        return rich is None or (isinstance(rich, float) and not math.isfinite(rich))
    # bool と数値。`True == 1` を一致にしない
    return type(rich) is type(poor) and rich == poor


class EventDeduper:
    """`add` でログの行を順に入れ、`events` で採った行を最初に現れた順に返す."""

    def __init__(self) -> None:
        #: キー -> [ev, src, 正規形の payload]
        self._kept: dict[tuple, list] = {}
        #: 捨てた行の数（重複と食い違いの両方。行数 = 採った数 + dropped）
        self.dropped = 0
        #: 食い違いで捨てた行（ts, plugin, 採った src, 捨てた src）
        self.conflicts: list[tuple] = []

    @staticmethod
    def key(ev: dict, payload_canon: str) -> tuple:
        ts = ev.get("ts")
        if isinstance(ts, str) and ts:
            return (ts, ev.get("plugin"))
        return ("", ev.get("plugin"), payload_canon)

    def add(self, ev: dict, src: str) -> None:
        payload = ev.get("payload")
        canon = canonical(payload)
        key = self.key(ev, canon)
        cur = self._kept.get(key)
        if cur is None:
            self._kept[key] = [ev, src, canon]
            return
        self.dropped += 1
        if canon == cur[2]:
            return
        old_payload = cur[0].get("payload")
        new_covers, old_covers = covers(payload, old_payload), covers(old_payload, payload)
        if new_covers != old_covers:
            # 片方がもう片方のサニタイズ済みの形。生の側を採る
            take_new = new_covers
        else:
            # 互いに説明できる（`machine_id` だけが違う）か、食い違う。どちらも引数の順に依存させない
            take_new = (len(canon), canon) > (len(cur[2]), cur[2])
            if not new_covers:
                kept_src, lost_src = (src, cur[1]) if take_new else (cur[1], src)
                self.conflicts.append((ev.get("ts"), ev.get("plugin"), kept_src, lost_src))
        if take_new:
            # 位置（最初に現れた順）は保ったまま中身だけ差し替える
            self._kept[key] = [ev, src, canon]

    def events(self):
        """採った (ev, src) を最初に現れた順に返す."""
        return [(ev, src) for ev, src, _ in self._kept.values()]
