#!/usr/bin/env python3
"""PR の説明図を JSON の定義から SVG に組む（pr-creator Step 4.6 / GitHub issue #349）.

型は 3 つ。どれを選ぶかと定義の書き方は skills/pr-creator/references/diagram-guide.md:
  flow      箱と矢印（流れ・範囲）。groups で「この PR のレビュー範囲」などを枠で囲む
  sequence  ライフラインと alt / opt / loop / par / break / critical の枠（層をまたぐ呼び出しの順と分岐）
  state     状態を節・操作を辺にした状態遷移図

使い方:
  diagram-svg.py <定義.json>...
各定義の隣に拡張子を .svg に替えたファイルを書き、1 ファイルにつき 1 行（警告があればその後に続けて）出す:
  svg=<svg のパス>                 書けた
  warn=<svg のパス>\t<理由>         書けたが直したほうがよい（幅が 1200 を超えた・線が箱を横切る・
                                   ラベルや箱が重なるなど）
  failed=<定義のパス>\t<理由>       書けなかった（JSON が壊れている・id の参照先が無い・値の型が違う・
                                   想定外のエラーなど）。前回書いた .svg はそのまま残る
exit 0 = 全件書けた / 1 = 1 件以上失敗 / 2 = 引数なし
1 件が失敗しても残りの定義は処理する。

手で座標を組んだときに踏んだ点（#349）をここで固定している:
- 文字の幅は全角と曖昧幅を 1 文字 = 1em で見積もる（英字の幅で見積もると日本語が枠からはみ出す）
- 矢印の先は markerUnits="userSpaceOnUse" で大きさを固定する（既定の strokeWidth だと線の太さに比例して膨らむ）
- ライフラインの見出しの箱は、見出しの幅から列の間隔を決めて隣と重ならないように並べる
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import unicodedata
from pathlib import Path

FONT = "Hiragino Sans, Noto Sans CJK JP, Yu Gothic, sans-serif"
FS = 14  # 箱・見出し
FS_LABEL = 13  # 線のラベル・枠の条件
FS_SMALL = 12  # 凡例・枠の種類・範囲の枠の見出し
LINE_H = 1.4
MAX_WIDTH = 1200
MARGIN = 24
PAD_X = 12
PAD_Y = 8
BOX_MIN_W = 96
TEXT = "#202124"

STATUSES = {
    "added": {"fill": "#e6f4ea", "stroke": "#1e8e3e", "label": "この PR で足した"},
    "changed": {"fill": "#fef7e0", "stroke": "#e37400", "label": "この PR で変えた"},
    "removed": {"fill": "#fce8e6", "stroke": "#d93025", "label": "この PR で消した"},
    "existing": {"fill": "#ffffff", "stroke": "#5f6368", "label": "既存"},
    "later": {"fill": "#ffffff", "stroke": "#9aa0a6", "label": "後続の PR"},
}
BOX_DASH = {"later": "6 4"}
# 返り値の破線（6 4）と見分けるため、後続の PR の線は点線、後続の PR の返り値は一点鎖線にする
REPLY_DASH = "6 4"
LATER_DASH = "2 4"
LATER_REPLY_DASH = "8 3 2 3"

FRAME_KINDS = ("alt", "opt", "loop", "par", "break", "critical")
COMMON_KEYS = {"type", "title", "legend", "legend_labels"}
# XML 1.0 に書けない文字（タブ・改行・復帰以外の制御文字、サロゲート、U+FFFE / U+FFFF）。
# 通すと svg= を出したのに読めない SVG ができ、Chrome で PNG にするとパースエラーの画面が写る
XML_INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")


class SpecError(Exception):
    pass


def fmt(v: float) -> str:
    r = round(v, 1)
    return str(int(r)) if r == int(r) else str(r)


def escape(s: str) -> str:
    # xml.sax.saxutils.escape は import が起動時間の約 4 割を占める（urllib まで読む）ので同じ置換を手で書く
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def attr(s: str) -> str:
    return escape(s).replace('"', "&quot;")


def char_em(ch: str) -> float:
    # 曖昧幅（A）も 1em に数える。日本語のフォントでは「→」「①」「×」が全角で描かれる
    if unicodedata.east_asian_width(ch) in ("W", "F", "A"):
        return 1.0
    return 0.72 if ch.isupper() else 0.62


def text_w(s: str, fs: float) -> float:
    return max(sum(char_em(c) for c in row) for row in s.split("\n")) * fs


def text_h(s: str, fs: float) -> float:
    return len(s.split("\n")) * fs * LINE_H


class Canvas:
    """描いた要素を層ごとに持ち、全体の外接矩形を測る（render が余白を付けて原点へ寄せるのに使う）."""

    def __init__(self) -> None:
        self.layers: dict[str, list[str]] = {k: [] for k in ("under", "lines", "boxes", "over")}
        self.x0 = self.y0 = math.inf
        self.x1 = self.y1 = -math.inf
        self.markers: set[str] = set()
        self.warnings: list[str] = []

    def add(self, layer: str, svg: str, bbox: tuple[float, float, float, float] | None = None) -> None:
        self.layers[layer].append(svg)
        if bbox is not None:
            self.x0 = min(self.x0, bbox[0])
            self.y0 = min(self.y0, bbox[1])
            self.x1 = max(self.x1, bbox[2])
            self.y1 = max(self.y1, bbox[3])


def text_svg(x: float, cy: float, s: str, fs: float, anchor: str = "middle",
             bold: bool = False, strike: bool = False) -> str:
    rows = s.split("\n")
    lh = fs * LINE_H
    # dominant-baseline は rsvg-convert が解釈しないことがあるので、中心から基線を計算する
    first = cy - lh * (len(rows) - 1) / 2 + fs * 0.35
    extra = (' font-weight="bold"' if bold else "") + (' text-decoration="line-through"' if strike else "")
    spans = "".join(f'<tspan x="{fmt(x)}" y="{fmt(first + i * lh)}">{escape(r)}</tspan>'
                    for i, r in enumerate(rows))
    return f'<text font-size="{fs}" text-anchor="{anchor}" fill="{TEXT}"{extra}>{spans}</text>'


def label_svg(c: Canvas, x: float, cy: float, s: str, anchor: str = "middle", strike: bool = False) -> None:
    """線の上に白地のラベルを置く（下を通る線・ライフラインで文字が読めなくならないように）."""
    w = text_w(s, FS_LABEL) + 8
    h = text_h(s, FS_LABEL) + 2
    left = x - w / 2 if anchor == "middle" else x - 4
    c.add("over", f'<rect class="label-bg" x="{fmt(left)}" y="{fmt(cy - h / 2)}" width="{fmt(w)}" '
                  f'height="{fmt(h)}" fill="#ffffff"/>' + text_svg(x, cy, s, FS_LABEL, anchor, strike=strike),
          (left, cy - h / 2, left + w, cy + h / 2))


def box_size(label: str) -> tuple[float, float]:
    return max(text_w(label, FS) + 2 * PAD_X, BOX_MIN_W), text_h(label, FS) + 2 * PAD_Y


def box_svg(c: Canvas, cls: str, ident: str, x: float, y: float, w: float, h: float,
            status: str, label: str, rx: float, double: bool = False) -> None:
    st = STATUSES[status]
    dash = f' stroke-dasharray="{BOX_DASH[status]}"' if status in BOX_DASH else ""
    parts = [f'<g class="{cls}" data-id="{attr(ident)}" data-status="{status}">',
             f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" rx="{fmt(rx)}" '
             f'fill="{st["fill"]}" stroke="{st["stroke"]}" stroke-width="1.5"{dash}/>']
    if double:
        parts.append(f'<rect x="{fmt(x + 4)}" y="{fmt(y + 4)}" width="{fmt(w - 8)}" height="{fmt(h - 8)}" '
                     f'rx="{fmt(max(rx - 4, 0))}" fill="none" stroke="{st["stroke"]}" stroke-width="1"/>')
    parts.append(text_svg(x + w / 2, y + h / 2, label, FS, strike=status == "removed"))
    parts.append("</g>")
    c.add("boxes", "".join(parts), (x, y, x + w, y + h))


def line_attrs(c: Canvas, status: str, dashed: bool = False) -> str:
    c.markers.add(status)
    if status == "later":
        dash = LATER_REPLY_DASH if dashed else LATER_DASH
    else:
        dash = REPLY_DASH if dashed else ""
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'fill="none" stroke="{STATUSES[status]["stroke"]}" stroke-width="1.5"{dash_attr} '
            f'marker-end="url(#arrow-{status})"')


# ---------------------------------------------------------------- 定義の検査


def check_keys(obj: object, allowed: set[str], where: str) -> dict:
    if not isinstance(obj, dict):
        raise SpecError(f"{where} はオブジェクトで書く")
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise SpecError(f"{where} に知らないキー {', '.join(map(repr, unknown))}"
                        f"（使えるのは {', '.join(sorted(allowed))}）")
    return obj


def check_chars(v: object, where: str) -> None:
    """定義の中の文字列（キーも値も）に、SVG に書けない文字が無いかを確かめる."""
    if isinstance(v, str):
        m = XML_INVALID.search(v)
        if m:
            raise SpecError(f"{where} に SVG に書けない文字 {m.group()!r} がある")
    elif isinstance(v, dict):
        for k, x in v.items():
            check_chars(k, where)
            check_chars(x, f"{where}.{k}")
    elif isinstance(v, list):
        for i, x in enumerate(v):
            check_chars(x, f"{where}[{i}]")


def get_status(obj: dict, where: str) -> str:
    status = obj.get("status", "existing")
    # 文字列かを先に見る。list / dict のまま dict に `in` すると TypeError で落ちる
    if not isinstance(status, str) or status not in STATUSES:
        raise SpecError(f"{where} の status {status!r} は使えない（{' / '.join(STATUSES)}）")
    return status


def get_label(obj: dict, key: str, default: str, where: str) -> str:
    v = obj.get(key, default)
    if not isinstance(v, str) or not v:
        raise SpecError(f"{where} の {key} は空でない文字列で書く")
    return v


def opt_str(obj: dict, key: str, where: str) -> str:
    v = obj.get(key, "")
    if not isinstance(v, str):
        raise SpecError(f"{where} の {key} は文字列で書く")
    return v


def parse_items(items: object, key: str, where: str, allowed: set[str]) -> list[dict]:
    if not isinstance(items, list) or not items:
        raise SpecError(f"{key} を 1 つ以上書く")
    out: list[dict] = []
    seen: set[str] = set()
    for i, raw in enumerate(items):
        obj = check_keys(raw, allowed, f"{key}[{i}]")
        ident = obj.get("id")
        if not isinstance(ident, str) or not ident:
            raise SpecError(f"{key}[{i}] に id が無い")
        if ident in seen:
            raise SpecError(f"{where} の id {ident!r} が重複している")
        seen.add(ident)
        item = {"id": ident, "label": get_label(obj, "label", ident, f"{key}[{i}]"),
                "status": get_status(obj, f"{key}[{i}]")}
        for extra in ("pos", "final"):
            if extra in obj:
                item[extra] = obj[extra]
        out.append(item)
    return out


def ref(obj: dict, key: str, ids: dict, where: str) -> str:
    v = obj.get(key)
    if not isinstance(v, str) or v not in ids:
        raise SpecError(f"{where} の {key} {v!r} が定義に無い（id の文字列で書く）")
    return v


# ---------------------------------------------------------------- sequence

SEQ_HEAD_GAP = 24
SEQ_ROW = 40
SELF_W = 36
SELF_H = 22
FRAME_BASE = 20
FRAME_INSET = 10
FRAME_HEAD = 24


def parse_steps(steps: object, pids: dict, where: str) -> list[dict]:
    if not isinstance(steps, list) or not steps:
        raise SpecError(f"{where} に呼び出しを 1 つ以上書く")
    out: list[dict] = []
    for i, raw in enumerate(steps):
        w = f"{where}[{i}]"
        if isinstance(raw, dict) and "frame" in raw:
            obj = check_keys(raw, {"frame", "label", "steps", "branches"}, w)
            kind = obj["frame"]
            if kind not in FRAME_KINDS:
                raise SpecError(f"{w} の frame {kind!r} は使えない（{' / '.join(FRAME_KINDS)}）")
            if "branches" in obj:
                if "steps" in obj:
                    raise SpecError(f"{w} は steps と branches のどちらかで書く")
                if "label" in obj:
                    raise SpecError(f"{w} は branches を使うとき、条件を branches[].label に書く")
                if not isinstance(obj["branches"], list) or not obj["branches"]:
                    raise SpecError(f"{w} の branches を 1 つ以上書く")
                branches = []
                for j, b in enumerate(obj["branches"]):
                    bobj = check_keys(b, {"label", "steps"}, f"{w}.branches[{j}]")
                    branches.append((opt_str(bobj, "label", f"{w}.branches[{j}]"),
                                     parse_steps(bobj.get("steps"), pids, f"{w}.branches[{j}].steps")))
            else:
                branches = [(opt_str(obj, "label", w), parse_steps(obj.get("steps"), pids, f"{w}.steps"))]
            out.append({"kind": "frame", "op": kind, "branches": branches})
        else:
            obj = check_keys(raw, {"from", "to", "label", "status", "reply"}, w)
            if "reply" in obj and not isinstance(obj["reply"], bool):
                raise SpecError(f"{w} の reply は true / false で書く")
            out.append({"kind": "msg", "from": ref(obj, "from", pids, w), "to": ref(obj, "to", pids, w),
                        "label": opt_str(obj, "label", w), "status": get_status(obj, w),
                        "reply": obj.get("reply") is True})
    return out


def walk_msgs(nodes: list[dict]):
    for n in nodes:
        if n["kind"] == "msg":
            yield n
        else:
            for _, sub in n["branches"]:
                yield from walk_msgs(sub)


def self_need(label: str) -> float:
    return SELF_W + 8 + text_w(label, FS_LABEL) + 8


def extra_rows(label: str) -> float:
    """2 行目以降のラベルの高さ。行の送りに足して、白地が矢印や前の分岐に掛からないようにする."""
    return text_h(label, FS_LABEL) - FS_LABEL * LINE_H if label else 0.0


def render_sequence(spec: dict, c: Canvas) -> list[tuple[str, str]]:
    check_keys(spec, COMMON_KEYS | {"participants", "steps"}, "定義")
    parts = parse_items(spec.get("participants"), "participants", "participants", {"id", "label", "status"})
    col = {p["id"]: i for i, p in enumerate(parts)}
    steps = parse_steps(spec.get("steps"), col, "steps")
    n = len(parts)

    hw = [box_size(p["label"])[0] for p in parts]
    head_h = max(box_size(p["label"])[1] for p in parts)
    gaps = [(hw[i] + hw[i + 1]) / 2 + SEQ_HEAD_GAP for i in range(n - 1)]
    right_extra = 0.0
    msgs = list(walk_msgs(steps))
    for m in sorted(msgs, key=lambda m: abs(col[m["from"]] - col[m["to"]])):
        a, b = col[m["from"]], col[m["to"]]
        if a == b:
            if a < n - 1:
                gaps[a] = max(gaps[a], self_need(m["label"]) + 8)
            else:
                right_extra = max(right_extra, self_need(m["label"]))
            continue
        lo, hi = min(a, b), max(a, b)
        short = text_w(m["label"], FS_LABEL) + 32 - sum(gaps[lo:hi])
        if short > 0:
            for i in range(lo, hi):
                gaps[i] += short / (hi - lo)
    cx = [hw[0] / 2]
    for g in gaps:
        cx.append(cx[-1] + g)

    def extent(frame: dict) -> tuple[float, float]:
        inner = [n2 for _, sub in frame["branches"] for n2 in sub if n2["kind"] == "frame"]
        cols = [col[e] for m in walk_msgs([frame]) for e in (m["from"], m["to"])]
        x0, x1 = cx[min(cols)] - FRAME_BASE, cx[max(cols)] + FRAME_BASE
        for m in walk_msgs([frame]):
            if m["from"] == m["to"]:
                x1 = max(x1, cx[col[m["from"]]] + self_need(m["label"]) + 4)
        for f in inner:
            ix0, ix1 = extent(f)
            x0, x1 = min(x0, ix0 - FRAME_INSET), max(x1, ix1 + FRAME_INSET)
        tab_w = text_w(frame["op"], FS_SMALL) + 16
        first = frame["branches"][0][0]
        need = tab_w + (8 + text_w(f"[{first}]", FS_LABEL) + 12 if first else 0)
        for blabel, _ in frame["branches"][1:]:
            if blabel:
                need = max(need, text_w(f"[{blabel}]", FS_LABEL) + 20)
        x1 = max(x1, x0 + need)
        frame["x0"], frame["x1"], frame["tab_w"] = x0, x1, tab_w
        return x0, x1

    for top in steps:
        if top["kind"] == "frame":
            extent(top)

    y = head_h + 20

    def emit(nodes: list[dict]) -> None:
        nonlocal y
        for node in nodes:
            if node["kind"] == "msg":
                a, b = col[node["from"]], col[node["to"]]
                strike = node["status"] == "removed"
                group = f'<g class="message" data-from="{attr(node["from"])}" data-to="{attr(node["to"])}">'
                extra = extra_rows(node["label"])
                if a == b:
                    y += SEQ_ROW - 8 + extra / 2
                    x = cx[a]
                    c.add("lines", f'{group}<path d="M {fmt(x)} {fmt(y)} H {fmt(x + SELF_W)} V {fmt(y + SELF_H)} '
                                   f'H {fmt(x)}" {line_attrs(c, node["status"], node["reply"])}/></g>',
                          (x, y, x + SELF_W, y + SELF_H))
                    if node["label"]:
                        label_svg(c, x + SELF_W + 8, y + SELF_H / 2, node["label"], "start", strike)
                    y += SELF_H + extra / 2
                else:
                    y += SEQ_ROW + extra
                    c.add("lines", f'{group}<path d="M {fmt(cx[a])} {fmt(y)} H {fmt(cx[b])}" '
                                   f'{line_attrs(c, node["status"], node["reply"])}/></g>',
                          (min(cx[a], cx[b]), y, max(cx[a], cx[b]), y))
                    if node["label"]:
                        # 白地の下端を矢印の 3px 上に揃える（行数に依らず矢印を隠さない）
                        h = text_h(node["label"], FS_LABEL) + 2
                        label_svg(c, (cx[a] + cx[b]) / 2, y - 3 - h / 2, node["label"], strike=strike)
                continue
            y += 12
            top = y
            y += FRAME_HEAD + extra_rows(node["branches"][0][0])
            dividers = []
            for bi, (blabel, sub) in enumerate(node["branches"]):
                if bi > 0:
                    y += 12
                    dividers.append((y, blabel))
                    y += 18 + extra_rows(blabel)
                emit(sub)
            y += 14
            x0, x1, tab_w = node["x0"], node["x1"], node["tab_w"]
            svg = [f'<g class="frame" data-kind="{node["op"]}">',
                   f'<rect x="{fmt(x0)}" y="{fmt(top)}" width="{fmt(x1 - x0)}" height="{fmt(y - top)}" '
                   f'fill="none" stroke="#5f6368" stroke-width="1"/>']
            for dy, _ in dividers:
                svg.append(f'<path d="M {fmt(x0)} {fmt(dy)} H {fmt(x1)}" stroke="#5f6368" stroke-width="1" '
                           f'stroke-dasharray="6 4"/>')
            svg.append("</g>")
            c.add("under", "".join(svg), (x0, top, x1, y))
            # 種類の札と条件の文字は、上を通るライフラインに消されないよう前面に置く
            c.add("over", f'<path class="frame-tab" d="M {fmt(x0)} {fmt(top)} H {fmt(x0 + tab_w)} V {fmt(top + 14)} '
                          f'L {fmt(x0 + tab_w - 8)} {fmt(top + 20)} H {fmt(x0)} Z" fill="#f1f3f4" stroke="#5f6368" '
                          f'stroke-width="1"/>' + text_svg(x0 + 8, top + 10, node["op"], FS_SMALL, "start", bold=True))
            # 条件の白地は上端を枠の上辺・区切り線の 1px 下に揃え、行が増えたら下へ伸ばす（上へ伸ばすと前の分岐の矢印を隠す）
            first = node["branches"][0][0]
            if first:
                label_svg(c, x0 + tab_w + 8, top + (text_h(first, FS_LABEL) + 2) / 2 + 1, f"[{first}]", "start")
            for dy, blabel in dividers:
                if blabel:
                    label_svg(c, x0 + 8, dy + (text_h(blabel, FS_LABEL) + 2) / 2 + 1, f"[{blabel}]", "start")

    emit(steps)
    y += 24
    for i, p in enumerate(parts):
        st = STATUSES[p["status"]]
        c.add("under", f'<path class="lifeline" d="M {fmt(cx[i])} {fmt(head_h)} V {fmt(y)}" '
                       f'stroke="{st["stroke"]}" stroke-width="1" stroke-dasharray="4 4"/>', (cx[i], 0, cx[i], y))
        box_svg(c, "participant", p["id"], cx[i] - hw[i] / 2, 0, hw[i], head_h, p["status"], p["label"], 4)
    if right_extra:
        c.add("under", "", (cx[-1], 0, cx[-1] + right_extra, 0))
    used = [p["status"] for p in parts] + [m["status"] for m in msgs]
    extra = [("reply", "返り値")] if any(m["reply"] for m in msgs) else []
    return [(s, "") for s in used] + extra


# ---------------------------------------------------------------- flow / state


def assign_grid(nodes: list[dict], edges: list[tuple[str, str]], roots: list[str],
                clusters: dict[str, int]) -> dict[str, tuple[float, float]]:
    """(層, 層の中の順番) を返す. 閉路は戻る辺を外して層を決め、層の中は前の層の位置の平均で並べる.

    clusters（groups の番号）を持つ箱は各層の先頭に寄せ、層の中央寄せもしない。寄せないと、範囲の枠が
    別の行に並んだ範囲外の箱まで囲ってしまう.
    """
    ids = [nd["id"] for nd in nodes]
    if all("pos" in nd for nd in nodes):
        grid = {}
        for nd in nodes:
            p = nd["pos"]
            if (not isinstance(p, list) or len(p) != 2
                    or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                               and math.isfinite(v) and v >= 0 for v in p)):
                raise SpecError(f"{nd['id']!r} の pos は [列, 行]（0 以上の有限の数）で書く")
            if tuple(p) in grid.values():
                raise SpecError(f"{nd['id']!r} の pos {p} が他と重なっている")
            grid[nd["id"]] = (float(p[0]), float(p[1]))
        return grid
    if any("pos" in nd for nd in nodes):
        raise SpecError("pos は全部に付けるか、どれにも付けない")
    succ: dict[str, list[str]] = {i: [] for i in ids}
    for a, b in edges:
        if a != b:
            succ[a].append(b)
    state: dict[str, int] = {}
    forward: list[tuple[str, str]] = []

    def dfs(u: str) -> None:
        state[u] = 1
        for v in succ[u]:
            if state.get(v) == 1:
                continue
            forward.append((u, v))
            if v not in state:
                dfs(v)
        state[u] = 2

    for r in roots + ids:
        if r not in state:
            dfs(r)
    layer = {i: 0 for i in ids}
    for _ in ids:
        for a, b in forward:
            layer[b] = max(layer[b], layer[a] + 1)
    order = {i: k for k, i in enumerate(ids)}
    row: dict[str, float] = {}
    for lv in range(max(layer.values()) + 1):
        members = [i for i in ids if layer[i] == lv]

        def bary(i: str) -> float:
            prev = [row[a] for a, b in forward if b == i and a in row]
            return sum(prev) / len(prev) if prev else math.inf

        members.sort(key=lambda i: (clusters.get(i, math.inf), bary(i), order[i]))
        for k, i in enumerate(members):
            row[i] = k
    if clusters:
        return {i: (layer[i], row[i]) for i in ids}
    tallest = max(sum(1 for i in ids if layer[i] == lv) for lv in set(layer.values()))
    for lv in set(layer.values()):
        members = [i for i in ids if layer[i] == lv]
        for i in members:
            row[i] += (tallest - len(members)) / 2
    return {i: (layer[i], row[i]) for i in ids}


def quad(p0, c1, p1, t):
    return ((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c1[0] + t * t * p1[0],
            (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c1[1] + t * t * p1[1])


def inside(p, r, grow: float = 0.0) -> bool:
    return r[0] - grow < p[0] < r[2] + grow and r[1] - grow < p[1] < r[3] + grow


def overlap(r, s) -> bool:
    return r[0] < s[2] and s[0] < r[2] and r[1] < s[3] and s[1] < r[3]


def loop_size(i: int) -> float:
    """同じ箱の i 本目（0 始まり）の自己ループの張り出し。外側のループほど大きくして重ならないようにする."""
    return 40 + 20 * i


def border_t(p0, c1, p1, r, t_in: float, t_out: float) -> float:
    for _ in range(24):
        mid = (t_in + t_out) / 2
        if inside(quad(p0, c1, p1, mid), r):
            t_in = mid
        else:
            t_out = mid
    return t_out


def render_graph(spec: dict, c: Canvas, kind: str) -> list[tuple[str, str]]:
    if kind == "state":
        check_keys(spec, COMMON_KEYS | {"states", "transitions", "initial"}, "定義")
        nodes = parse_items(spec.get("states"), "states", "states", {"id", "label", "status", "pos", "final"})
        raw_edges, ekey, rx = spec.get("transitions", []), "transitions", 14.0
    else:
        check_keys(spec, COMMON_KEYS | {"nodes", "edges", "groups", "direction"}, "定義")
        nodes = parse_items(spec.get("nodes"), "nodes", "nodes", {"id", "label", "status", "pos"})
        raw_edges, ekey, rx = spec.get("edges", []), "edges", 4.0
    by_id = {nd["id"]: nd for nd in nodes}
    if not isinstance(raw_edges, list):
        raise SpecError(f"{ekey} は配列で書く")
    edges = []
    for i, raw in enumerate(raw_edges):
        obj = check_keys(raw, {"from", "to", "label", "status"}, f"{ekey}[{i}]")
        label = obj.get("label", "")
        if not isinstance(label, str):
            raise SpecError(f"{ekey}[{i}] の label は文字列で書く")
        edges.append({"from": ref(obj, "from", by_id, f"{ekey}[{i}]"), "to": ref(obj, "to", by_id, f"{ekey}[{i}]"),
                      "label": label, "status": get_status(obj, f"{ekey}[{i}]")})
    initial = spec.get("initial")
    if initial is not None and (not isinstance(initial, str) or initial not in by_id):
        raise SpecError(f"initial {initial!r} が states に無い（id の文字列で書く）")
    direction = spec.get("direction", "LR")
    if direction not in ("LR", "TB"):
        raise SpecError("direction は LR か TB")
    for nd in nodes:
        if "final" in nd and not isinstance(nd["final"], bool):
            raise SpecError(f"{nd['id']!r} の final は true / false で書く")

    groups = []
    raw_groups = spec.get("groups", [])
    if not isinstance(raw_groups, list):
        raise SpecError("groups は配列で書く")
    for gi, raw in enumerate(raw_groups):
        g = check_keys(raw, {"label", "nodes", "status"}, f"groups[{gi}]")
        members = g.get("nodes")
        if not isinstance(members, list) or not members:
            raise SpecError(f"groups[{gi}] の nodes を 1 つ以上書く")
        for m in members:
            if not isinstance(m, str) or m not in by_id:
                raise SpecError(f"groups[{gi}] の nodes {m!r} が定義に無い（id の文字列で書く）")
        groups.append({"label": opt_str(g, "label", f"groups[{gi}]"), "nodes": members,
                       "status": get_status(g, f"groups[{gi}]")})
    clusters: dict[str, int] = {}
    for gi, g in enumerate(groups):
        for m in g["nodes"]:
            clusters.setdefault(m, gi)

    pairs = [(e["from"], e["to"]) for e in edges]
    has_in = {b for a, b in pairs if a != b}
    roots = ([initial] if initial else []) + [nd["id"] for nd in nodes if nd["id"] not in has_in]
    grid = assign_grid(nodes, pairs, roots, clusters)
    if direction == "TB" and not all("pos" in nd for nd in nodes):
        grid = {i: (r, lv) for i, (lv, r) in grid.items()}
    size = {nd["id"]: box_size(nd["label"]) for nd in nodes}
    maxw = max(w for w, _ in size.values())
    maxh = max(h for _, h in size.values())
    loop_count: dict[str, int] = {}
    for e in edges:
        if e["from"] == e["to"]:
            loop_count[e["from"]] = loop_count.get(e["from"], 0) + 1
    gap_x, gap_y = 72.0, 56.0
    for e in edges:
        (ca, ra), (cb, rb) = grid[e["from"]], grid[e["to"]]
        lw = text_w(e["label"], FS_LABEL) + 8
        if e["from"] == e["to"]:
            gap_y = max(gap_y, 72)
            if e["label"]:
                # 自己ループのラベルは箱の右上に出るので、右隣の箱との間にラベルが入る幅を取る
                gap_x = max(gap_x, loop_size(loop_count[e["from"]] - 1) * 0.45 + 6 + lw + 12)
            continue
        if e["label"]:
            # 縦の辺のラベルは線の上か横に出るので、隣の列の辺のラベルと重ならない幅を取る
            gap_x = max(gap_x, lw + (24 if ca != cb else 32))
        if e["label"] and ra != rb:
            gap_y = max(gap_y, text_h(e["label"], FS_LABEL) + 28)
    if any(g["label"] for g in groups):
        # 範囲の枠の見出し（箱の上 40px）の上に、上の行から入る辺のラベルが入る高さを残す
        gap_y = max(gap_y, 96)
    center = {i: (cc * (maxw + gap_x), rr * (maxh + gap_y)) for i, (cc, rr) in grid.items()}
    rect = {i: (center[i][0] - size[i][0] / 2, center[i][1] - size[i][1] / 2,
                center[i][0] + size[i][0] / 2, center[i][1] + size[i][1] / 2) for i in by_id}
    ids = [nd["id"] for nd in nodes]
    for k, a in enumerate(ids):
        for b in ids[k + 1:]:
            if overlap(rect[a], rect[b]):
                c.warnings.append(f"箱 {a!r} と {b!r} が重なる（pos の間隔を 1 以上空ける）")

    # 箱・範囲の枠の見出し・置いたラベルの矩形。ラベルと始まりの黒丸はこれを避けて置く
    placed: list[tuple[float, float, float, float]] = list(rect.values())
    for gi, g in enumerate(groups):
        members, label, status = g["nodes"], g["label"], g["status"]
        x0 = min(rect[m][0] for m in members) - 16
        x1 = max(rect[m][2] for m in members) + 16
        y0 = min(rect[m][1] for m in members) - 16 - (24 if label else 0)
        y1 = max(rect[m][3] for m in members) + 16
        x1 = max(x1, x0 + text_w(label, FS_SMALL) + 20)
        st = STATUSES[status]
        svg = (f'<g class="group" data-status="{status}"><rect x="{fmt(x0)}" y="{fmt(y0)}" width="{fmt(x1 - x0)}" '
               f'height="{fmt(y1 - y0)}" rx="8" fill="none" stroke="{st["stroke"]}" stroke-width="1.5" '
               f'stroke-dasharray="8 4"/>')
        c.add("under", svg + "</g>", (x0, y0, x1, y1))
        if label:
            # 見出しは白地を付けて前面に置く（枠に入ってくる辺の線が見出しの文字を貫かないように）
            hx1 = x0 + 14 + text_w(label, FS_SMALL)
            c.add("over", f'<rect class="group-heading" x="{fmt(x0 + 6)}" y="{fmt(y0 + 4)}" '
                          f'width="{fmt(hx1 - x0 - 6)}" height="20" fill="#ffffff"/>'
                          + text_svg(x0 + 10, y0 + 14, label, FS_SMALL, "start", bold=True))
            placed.append((x0 + 6, y0 + 4, hx1, y0 + 24))
        outsiders = [i for i in by_id if i not in members and overlap(rect[i], (x0, y0, x1, y1))]
        if outsiders:
            c.warnings.append(f"groups[{gi}] の枠に、メンバーでない {', '.join(map(repr, outsiders))} が入った"
                              f"（pos で並べ直す）")

    for nd in nodes:
        r = rect[nd["id"]]
        box_svg(c, "node", nd["id"], r[0], r[1], r[2] - r[0], r[3] - r[1], nd["status"], nd["label"], rx,
                double=nd.get("final") is True)

    order = {nd["id"]: k for k, nd in enumerate(nodes)}
    bundles: dict[tuple[str, str], list[int]] = {}
    loops: dict[str, int] = {}
    # 描いた線の上の点。始まりの黒丸を線に乗せないために使う
    line_pts: list[tuple[float, float]] = []

    def put_label(s: str, at, strike: bool, what: str, anchor: str = "middle") -> None:
        """候補の位置のうち、箱・枠の見出し・先に置いたラベルに重ならない最初の位置に置く.

        全部重なれば最初の候補に置いて warn= を出す（画像を見ない呼び出し側には、これが重なりを知る唯一の合図）.
        """
        w, h = text_w(s, FS_LABEL) + 8, text_h(s, FS_LABEL) + 2

        def box(p):
            left = p[0] - w / 2 if anchor == "middle" else p[0] - 4
            return (left, p[1] - h / 2, left + w, p[1] + h / 2)

        spots = [at(f) for f in (0.5, 0.4, 0.6, 0.3, 0.7)]
        free = next((p for p in spots if not any(overlap(box(p), r) for r in placed)), None)
        if free is None:
            c.warnings.append(f"{what} のラベルが他のラベルか箱と重なる（pos で間隔を空けるか、ラベルを短くする）")
            free = spots[0]
        placed.append(box(free))
        label_svg(c, free[0], free[1], s, anchor, strike)

    for k, e in enumerate(edges):
        if e["from"] != e["to"]:
            bundles.setdefault(tuple(sorted((e["from"], e["to"]), key=order.get)), []).append(k)
    for k, e in enumerate(edges):
        a, b = e["from"], e["to"]
        strike = e["status"] == "removed"
        what = f"{ekey} の {a!r} → {b!r}"
        head = f'<g class="edge" data-from="{attr(a)}" data-to="{attr(b)}"'
        if a == b:
            # 自己ループは箱の右上の角に掛ける。上辺の中央に掛けると、上の箱から縦に入る辺とラベルが重なる
            i = loops.get(a, 0)
            loops[a] = i + 1
            size_l = loop_size(i)
            right, top = rect[a][2], rect[a][1]
            sx, ey = right - 18, top + 16
            c.add("lines", f'{head} data-route="self"><path d="M {fmt(sx)} {fmt(top)} C {fmt(sx)} '
                           f'{fmt(top - size_l)} {fmt(right + size_l)} {fmt(ey)} {fmt(right)} {fmt(ey)}" '
                           f'{line_attrs(c, e["status"])}/></g>',
                  (sx, top - size_l * 0.45, right + size_l * 0.45, ey))
            if e["label"]:
                lh = text_h(e["label"], FS_LABEL) + 4

                def at_loop(f, x=right + size_l * 0.45 + 6, y=top - lh / 2, lh=lh):
                    # 候補は縦に積む（f = 0.5 が基準。同じ箱の 2 本目以降は上下にずれる）
                    return x, y + round((f - 0.5) * 10) * lh

                put_label(e["label"], at_loop, strike, what, "start")
            continue
        canon = tuple(sorted((a, b), key=order.get))
        siblings = bundles[canon]
        (ax, ay), (bx, by) = center[canon[0]], center[canon[1]]
        dist = math.hypot(bx - ax, by - ay)
        nx, ny = -(by - ay) / dist, (bx - ax) / dist
        # ずらす向きは辺の法線なので、箱の中に残る幅も法線方向の半幅で測る（縦の辺は箱の幅、横の辺は高さ）。
        # 箱の外から始めると境界の二分探索が成り立たない
        room = min(size[i][0] / 2 * abs(nx) + size[i][1] / 2 * abs(ny) for i in (a, b)) - 4
        step = min(16.0, 2 * room / (len(siblings) - 1)) if len(siblings) > 1 else 0.0
        off = (siblings.index(k) - (len(siblings) - 1) / 2) * step
        p0 = (center[a][0] + nx * off, center[a][1] + ny * off)
        p1 = (center[b][0] + nx * off, center[b][1] + ny * off)
        mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
        others = [rect[i] for i in by_id if i not in (a, b)]
        route, ctrl = "straight", mid
        for bow in (0.0, 0.35, -0.35, 0.7, -0.7):
            cand = (mid[0] + nx * bow * dist, mid[1] + ny * bow * dist)
            pts = [quad(p0, cand, p1, s / 48) for s in range(49)]
            if not any(inside(p, r, 4) for p in pts for r in others):
                route, ctrl = ("straight" if bow == 0 else "curve"), cand
                break
        else:
            c.warnings.append(f"{what} が他の箱を横切る（pos で並べ直す）")
        t0 = border_t(p0, ctrl, p1, rect[a], 0.0, 0.5)
        t1 = border_t(p0, ctrl, p1, rect[b], 1.0, 0.5)
        pts = [quad(p0, ctrl, p1, t0 + (t1 - t0) * s / 24) for s in range(25)]
        line_pts.extend(pts)
        if route == "straight":
            d = f"M {fmt(pts[0][0])} {fmt(pts[0][1])} L {fmt(pts[-1][0])} {fmt(pts[-1][1])}"
        else:
            d = "M " + " L ".join(f"{fmt(px)} {fmt(py)}" for px, py in pts)
        c.add("lines", f'{head} data-route="{route}"><path d="{d}" {line_attrs(c, e["status"])}/></g>',
              (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)))
        if e["label"]:
            # 同じ 2 つの箱をつなぐ辺が複数あるときは、ずらした側の外へラベルを出す（線の上に置くと隣の線のラベルと
            # 重なる）。出す量は法線方向のラベルの半幅で、縦の辺なら幅の半分、横の辺なら高さの半分になる
            w, h = text_w(e["label"], FS_LABEL) + 8, text_h(e["label"], FS_LABEL) + 2
            push = math.copysign(w / 2 * abs(nx) + h / 2 * abs(ny) + 2, off) if off else 0.0

            def at(f, p0=p0, ctrl=ctrl, p1=p1, t0=t0, t1=t1, push=push, nx=nx, ny=ny):
                px, py = quad(p0, ctrl, p1, t0 + (t1 - t0) * f)
                return px + nx * push, py + ny * push

            put_label(e["label"], at, strike, what)

    if initial:
        r = rect[initial]
        cx0, cy0 = center[initial]
        # 左・上・下の順に試し、他の箱・ラベル・線に掛からない最初の位置に置く
        spots = [((r[0] - 44, cy0), (r[0], cy0), (7, 0)),
                 ((cx0, r[1] - 44), (cx0, r[1]), (0, 7)),
                 ((cx0, r[3] + 44), (cx0, r[3]), (0, -7))]

        def clear(dot, end) -> bool:
            mid = ((dot[0] + end[0]) / 2, (dot[1] + end[1]) / 2)
            if any(inside(p, q, 10) for p in (dot, mid) for q in placed if q is not rect[initial]):
                return False
            return not any(math.hypot(p[0] - q[0], p[1] - q[1]) < 10 for p in (dot, mid) for q in line_pts)

        pick = next((s for s in spots if clear(s[0], s[1])), None)
        if pick is None:
            c.warnings.append(f"initial {initial!r} の始まりの黒丸が他の箱か線と重なる（pos で並べ直す）")
            pick = spots[0]
        dot, end, (ox, oy) = pick
        c.add("lines", f'<g class="initial"><circle cx="{fmt(dot[0])}" cy="{fmt(dot[1])}" r="7" fill="{TEXT}"/>'
                       f'<path d="M {fmt(dot[0] + ox)} {fmt(dot[1] + oy)} L {fmt(end[0])} {fmt(end[1])}" '
                       f'{line_attrs(c, "existing")}/></g>',
              (min(dot[0] - 7, end[0]), min(dot[1] - 7, end[1]), max(dot[0] + 7, end[0]), max(dot[1] + 7, end[1])))
    return ([(nd["status"], "") for nd in nodes] + [(e["status"], "") for e in edges]
            + [(g["status"], "") for g in groups])


# ---------------------------------------------------------------- 組み立て


def legend(c: Canvas, used: list[tuple[str, str]], labels: dict) -> None:
    seen: list[str] = []
    for s, _ in used:
        if s not in seen:
            seen.append(s)
    items = [s for s in STATUSES if s in seen] + [s for s in seen if s not in STATUSES]
    if items == ["existing"]:
        return
    x, y = c.x0, c.y1 + 28
    svg = ['<g class="legend">']
    for s in items:
        text = labels.get(s) or STATUSES.get(s, {}).get("label") or "返り値"
        svg.append(f'<g class="legend-item" data-status="{s}">')
        if s == "reply":
            svg.append(f'<path d="M {fmt(x)} {fmt(y)} H {fmt(x + 22)}" stroke="#5f6368" stroke-width="1.5" '
                       f'stroke-dasharray="6 4"/>')
        else:
            st = STATUSES[s]
            dash = f' stroke-dasharray="{BOX_DASH[s]}"' if s in BOX_DASH else ""
            svg.append(f'<rect x="{fmt(x)}" y="{fmt(y - 6)}" width="22" height="12" rx="2" fill="{st["fill"]}" '
                       f'stroke="{st["stroke"]}" stroke-width="1.5"{dash}/>')
        svg.append(text_svg(x + 28, y, text, FS_SMALL, "start") + "</g>")
        x += 28 + text_w(text, FS_SMALL) + 20
    svg.append("</g>")
    c.add("over", "".join(svg), (c.x0, y - 8, x - 20, y + 8))


def render(spec: object) -> tuple[str, int, list[str]]:
    if not isinstance(spec, dict):
        raise SpecError("定義はオブジェクトで書く")
    check_chars(spec, "定義")
    kind = spec.get("type")
    if kind not in ("flow", "sequence", "state"):
        raise SpecError(f"type {kind!r} は使えない（flow / sequence / state）")
    title = spec.get("title", "")
    if not isinstance(title, str):
        raise SpecError("title は文字列で書く")
    labels = spec.get("legend_labels", {})
    if not isinstance(labels, dict) or not all(k in STATUSES or k == "reply" for k in labels):
        raise SpecError(f"legend_labels のキーは {' / '.join(STATUSES)} / reply")
    if not all(isinstance(v, str) and v for v in labels.values()):
        raise SpecError("legend_labels の値は空でない文字列で書く（凡例を消すなら legend: false）")
    show_legend = spec.get("legend", True)
    if not isinstance(show_legend, bool):
        raise SpecError("legend は true / false で書く")

    c = Canvas()
    used = render_sequence(spec, c) if kind == "sequence" else render_graph(spec, c, kind)
    if show_legend:
        legend(c, used, labels)
    if title:
        c.add("over", f'<g class="title">{text_svg(c.x0, c.y0 - 22, title, 16, "start", bold=True)}</g>',
              (c.x0, c.y0 - 22 - 12, c.x0 + text_w(title, 16), c.y0))

    width = math.ceil(c.x1 - c.x0 + 2 * MARGIN)
    height = math.ceil(c.y1 - c.y0 + 2 * MARGIN)
    markers = "".join(
        f'<marker id="arrow-{s}" markerWidth="10" markerHeight="10" refX="10" refY="5" orient="auto" '
        f'markerUnits="userSpaceOnUse"><path d="M 0 0 L 10 5 L 0 10 Z" fill="{STATUSES[s]["stroke"]}"/></marker>'
        for s in STATUSES if s in c.markers)
    body = "".join(svg for layer in c.layers.values() for svg in layer)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" font-family="{FONT}">'
           f'<rect class="background" width="{width}" height="{height}" fill="#ffffff"/>'
           f'<defs>{markers}</defs>'
           f'<g transform="translate({fmt(MARGIN - c.x0)} {fmt(MARGIN - c.y0)})">{body}</g></svg>\n')
    warnings = list(c.warnings)
    if width > MAX_WIDTH:
        warnings.insert(0, f"幅が {width}px で {MAX_WIDTH} を超えた（主題を分けるか、ラベルを短くする）")
    return svg, width, warnings


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: diagram-svg.py <定義.json>...", file=sys.stderr)
        return 2
    rc = 0
    for arg in argv:
        path = Path(arg)
        if path.suffix != ".json":
            print(f"failed={arg}\t拡張子が .json でない")
            rc = 1
            continue
        out = path.with_suffix(".svg")
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
            svg, _, warnings = render(spec)
            # 一時ファイルに書いてから差し替える（書き込みの途中で落ちても、空や書きかけの .svg を残さない）
            tmp = out.with_name(f".{out.name}.tmp")
            tmp.write_text(svg, encoding="utf-8")
            os.replace(tmp, out)
        except FileNotFoundError:
            reason = "ファイルが無い"
        except json.JSONDecodeError as e:
            reason = f"JSON として読めない（{e.lineno} 行 {e.colno} 列: {e.msg}）"
        except SpecError as e:
            reason = str(e)
        except UnicodeDecodeError:
            reason = "UTF-8 として読めない"
        except RecursionError:
            reason = "入れ子や辺の連なりが深すぎる（図を分ける）"
        except Exception as e:  # noqa: BLE001 — 1 件の想定外で後ろの定義まで止めない（1 定義 1 行の契約）
            reason = f"想定外のエラー（{type(e).__name__}: {e}）"
        else:
            print(f"svg={out}")
            for w in warnings:
                print(f"warn={out}\t{w}")
            continue
        # 理由に id などの改行・タブが混ざっても 1 定義 1 行を保つ
        print(f"failed={arg}\t" + reason.replace("\n", "\\n").replace("\t", "\\t"))
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
