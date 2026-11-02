#!/usr/bin/env python3
"""dev-workflow の説明図の生成（diagram-svg.py）の CLI 境界テスト.

pr-creator Step 4.6 が PR に添付する図を、JSON の定義から SVG に組む（GitHub issue #349）。測るもの:

- 出力の契約: 定義の隣に .svg を書いて svg= を出す。壊れた定義は failed= を 1 行出し、他の定義の処理は続ける
  （exit 1）。型の違う値・UTF-8 でない定義・想定外の例外も failed= に落とす。幅が 1200 を超えた・線が箱を
  避けられない・ラベルや箱が重なった・範囲の枠に範囲外の箱が入った・複雑さの予算（箱 9・線 12・参加者 5・
  枠 1（分岐の無い枠だけなら 2）・alt の分岐 2・遷移は状態の 2 倍まで）を超えたときは warn= を足す。上限ちょうどでは黙る
- 手で描いたときに踏んだ 3 点（全角と曖昧幅の見出しが箱に収まる / 矢印の先が markerUnits="userSpaceOnUse" /
  ライフラインの見出しの箱が隣と重ならない）。1 点目はスクリプトの見積もりを使わず、1 文字 14px を下限に置く
- sequence: 呼び出しのラベルが両端のライフラインの間に収まる・複数行のラベルが矢印を隠さない・入れ子の枠が
  外の枠の内側に収まる
- state / flow: 往復の辺のラベルが向き（横・縦）に関わらず重ならない・自己ループのラベルが入ってくる辺の
  ラベルと重ならない・間の箱を横切る辺を曲げる・線の端が箱の境界に乗る・範囲の枠がメンバーだけを囲む
- 凡例: 使った status（箱・線・枠）だけを出し、legend_labels で文言を差し替えられる

描画は決定的なので、同じ定義の描画は 1 回だけ回して結果を使い回す（起動の回数を減らす）。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "dev-workflow" / "scripts" / "diagram-svg.py"
NS = "{http://www.w3.org/2000/svg}"
DIRECTORY = object()  # run() に渡すと、その名前でディレクトリを作る

_ROOT: Path | None = None
_CACHE: dict[str, tuple[ET.Element, list[str]]] = {}


def setUpModule() -> None:
    global _ROOT
    _ROOT = Path(tempfile.mkdtemp(prefix="diagram-svg-test."))


def tearDownModule() -> None:
    shutil.rmtree(_ROOT, ignore_errors=True)


def run(*specs: object, names: list[str] | None = None) -> tuple[int, list[str], str, Path]:
    tmp = Path(tempfile.mkdtemp(dir=_ROOT))
    args = []
    for i, spec in enumerate(specs):
        p = tmp / (names[i] if names else f"d{i}.json")
        if spec is DIRECTORY:
            p.mkdir()
        elif isinstance(spec, bytes):
            p.write_bytes(spec)
        elif spec is not None:
            p.write_text(spec if isinstance(spec, str) else json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        args.append(str(p))
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=60)
    return proc.returncode, proc.stdout.splitlines(), proc.stderr, tmp


def render(spec: dict) -> tuple[ET.Element, list[str]]:
    key = json.dumps(spec, sort_keys=True, ensure_ascii=False)
    if key not in _CACHE:
        rc, out, err, tmp = run(spec)
        if rc != 0:
            raise AssertionError(f"rc={rc} out={out} err={err}")
        _CACHE[key] = (ET.parse(tmp / "d0.svg").getroot(), out)
    return _CACHE[key]


def groups(root: ET.Element, cls: str) -> list[ET.Element]:
    return [g for g in root.iter(f"{NS}g") if g.get("class") == cls]


def rect_of(el: ET.Element) -> tuple[float, float, float, float]:
    r = el if el.tag == f"{NS}rect" else el.find(f"{NS}rect")
    x, y, w, h = (float(r.get(k)) for k in ("x", "y", "width", "height"))
    return x, y, x + w, y + h


def text_of(el: ET.Element) -> str:
    return "\n".join(t.text or "" for t in el.iter(f"{NS}tspan"))


def bg_before(root: ET.Element, text: str, cls: str = "label-bg") -> tuple[float, float, float, float]:
    """文字の直前に置いた白地の矩形（ラベルなら label-bg、範囲の枠の見出しなら group-heading）."""
    for parent in root.iter():
        kids = list(parent)
        for i, k in enumerate(kids):
            if k.tag == f"{NS}text" and text_of(k) == text and i > 0 and kids[i - 1].get("class") == cls:
                return rect_of(kids[i - 1])
    raise AssertionError(f"{text!r} の白地が無い")


def label_bg(root: ET.Element, text: str) -> tuple[float, float, float, float]:
    return bg_before(root, text)


def path_points(d: str) -> list[tuple[float, float]]:
    nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", d)]
    return list(zip(nums[0::2], nums[1::2]))


def overlap(r, s) -> bool:
    return r[0] < s[2] and s[0] < r[2] and r[1] < s[3] and s[1] < r[3]


def on_border(p, r, tol: float = 0.6) -> bool:
    inside_grown = r[0] - tol <= p[0] <= r[2] + tol and r[1] - tol <= p[1] <= r[3] + tol
    inside_shrunk = r[0] + tol < p[0] < r[2] - tol and r[1] + tol < p[1] < r[3] - tol
    return inside_grown and not inside_shrunk


def translate(root: ET.Element) -> tuple[float, float]:
    g = next(g for g in root if g.get("transform"))
    x, y = re.match(r"translate\(([-\d.]+) ([-\d.]+)\)", g.get("transform")).groups()
    return float(x), float(y)


def node(root: ET.Element, ident: str) -> ET.Element:
    return next(g for g in root.iter(f"{NS}g") if g.get("class") in ("node", "participant") and g.get("data-id") == ident)


def edge(root: ET.Element, a: str, b: str, nth: int = 0) -> ET.Element:
    return [g for g in groups(root, "edge") if g.get("data-from") == a and g.get("data-to") == b][nth]


def center(root: ET.Element, ident: str) -> tuple[float, float]:
    r = rect_of(node(root, ident))
    return (r[0] + r[2]) / 2, (r[1] + r[3]) / 2


SEQ = {
    "type": "sequence",
    "participants": [
        {"id": "ui", "label": "一覧画面"},
        {"id": "act", "label": "Server Action", "status": "added"},
        {"id": "uc", "label": "DeleteItemUseCase", "status": "added"},
        {"id": "repo", "label": "ItemRepository", "status": "changed"},
    ],
    "steps": [
        {"from": "ui", "to": "act", "label": "deleteItem(id)", "status": "added"},
        {"from": "act", "to": "uc", "label": "execute(id)", "status": "added"},
        {"from": "uc", "to": "repo", "label": "findById(id)"},
        {"frame": "alt", "branches": [
            {"label": "見つからない", "steps": [{"from": "repo", "to": "uc", "label": "null", "reply": True}]},
            {"label": "見つかった", "steps": [{"from": "uc", "to": "repo", "label": "softDelete(id)"}]},
        ]},
    ],
}


class OutputContractTest(unittest.TestCase):
    def test_no_args_exits_2_with_usage(self):
        proc = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage", proc.stderr)

    def test_writes_svg_next_to_definition(self):
        rc, out, _, tmp = run(SEQ)
        self.assertEqual(rc, 0)
        self.assertEqual(out, [f"svg={tmp / 'd0.svg'}"])
        self.assertTrue((tmp / "d0.svg").read_text(encoding="utf-8").startswith("<svg "))
        self.assertEqual(sorted(p.name for p in tmp.iterdir()), ["d0.json", "d0.svg"])

    def test_failures_are_reported_per_file_and_others_still_render(self):
        rc, out, _, tmp = run("{broken", SEQ, None, SEQ, names=["a.json", "b.json", "c.json", "d.txt"])
        self.assertEqual(rc, 1)
        self.assertTrue(out[0].startswith(f"failed={tmp / 'a.json'}\tJSON として読めない（1 行"))
        self.assertEqual(out[1], f"svg={tmp / 'b.svg'}")
        self.assertEqual(out[2], f"failed={tmp / 'c.json'}\tファイルが無い")
        self.assertEqual(out[3], f"failed={tmp / 'd.txt'}\t拡張子が .json でない")
        self.assertFalse((tmp / "d.svg").exists())

    def test_wrong_types_and_unreadable_files_fail_per_file_and_later_specs_still_render(self):
        cases = [
            ({"type": "flow", "nodes": [{"id": "a", "status": ["added"]}]}, "status ['added'] は使えない"),
            ({"type": "flow", "nodes": [{"id": "a"}], "edges": [{"from": ["a"], "to": "a"}]},
             "from ['a'] が定義に無い"),
            ({"type": "state", "states": [{"id": "a"}], "initial": ["a"]}, "initial ['a'] が states に無い"),
            ({"type": "flow", "nodes": [{"id": "a"}], "groups": [{"nodes": [{"id": "a"}]}]},
             "nodes {'id': 'a'} が定義に無い"),
            ('{"type": "flow", "nodes": [{"id": "a", "pos": [Infinity, 0]}]}', "0 以上の有限の数"),
            ('{"type": "flow", "nodes": [{"id": "a", "label": "\\u000bx"}]}', "SVG に書けない文字 '\\x0b'"),
            ("{\"type\": \"flow\", \"nodes\": [{\"id\": \"注文\"}]}".encode("shift_jis"), "UTF-8 として読めない"),
            (DIRECTORY, "想定外のエラー（IsADirectoryError"),
        ]
        rc, out, _, tmp = run(*[c for c, _ in cases], SEQ)
        self.assertEqual(rc, 1)
        self.assertEqual(len(out), len(cases) + 1, out)
        for i, (_, fragment) in enumerate(cases):
            self.assertTrue(out[i].startswith(f"failed={tmp / f'd{i}.json'}\t"), out[i])
            self.assertIn(fragment, out[i])
            self.assertFalse((tmp / f"d{i}.svg").exists())
        self.assertEqual(out[-1], f"svg={tmp / f'd{len(cases)}.svg'}")

    def test_rejects_invalid_definitions(self):
        flow = {"type": "flow", "nodes": [{"id": "a"}]}
        cases = [
            ([], "定義はオブジェクトで書く"),
            ({"type": "pie"}, "type 'pie'"),
            ({**SEQ, "lable": "x"}, "知らないキー 'lable'"),
            ({**SEQ, "participants": []}, "participants を 1 つ以上"),
            ({**SEQ, "participants": ["a"]}, "participants[0] はオブジェクトで書く"),
            ({**SEQ, "participants": [{"label": "x"}]}, "participants[0] に id が無い"),
            ({**SEQ, "participants": [{"id": "a", "label": ""}]}, "label は空でない文字列"),
            ({**SEQ, "steps": [{"from": "ui", "to": "nowhere"}]}, "to 'nowhere' が定義に無い"),
            ({**SEQ, "steps": [{"from": "ui", "to": "act", "label": 1}]}, "label は文字列で書く"),
            ({**SEQ, "participants": [{"id": "a"}, {"id": "a"}]}, "id 'a' が重複"),
            ({**SEQ, "participants": [{"id": "a", "status": "new"}]}, "status 'new'"),
            ({**SEQ, "steps": [{"frame": "if", "steps": []}]}, "frame 'if'"),
            ({**SEQ, "steps": [{"frame": "par", "steps": [{"from": "ui", "to": "act"}]}]}, "frame 'par'"),
            ({**SEQ, "steps": [{"frame": "opt", "branches": [{"label": "x", "steps": [{"from": "ui", "to": "act"}]}]}]},
             "branches は alt の枠だけに書ける"),
            ({**SEQ, "steps": [{"frame": "loop", "steps": []}]}, "呼び出しを 1 つ以上"),
            ({**SEQ, "steps": [{"frame": "alt", "steps": [], "branches": []}]}, "steps と branches のどちらか"),
            ({**SEQ, "steps": [{"frame": "alt", "branches": []}]}, "branches を 1 つ以上"),
            ({**SEQ, "steps": [{"frame": "alt", "label": "x", "branches": [
                {"label": "y", "steps": [{"from": "ui", "to": "act"}]}]}]}, "条件を branches[].label に書く"),
            ({**SEQ, "steps": [{"from": "ui", "to": "act", "reply": "yes"}]}, "reply は true / false"),
            ({"type": "flow", "nodes": [{"id": "a", "pos": [0, 0]}, {"id": "b"}]}, "pos は全部に付けるか"),
            ({"type": "flow", "nodes": [{"id": "a", "pos": [0, 0]}, {"id": "b", "pos": [0, 0]}]},
             "'b' の pos [0, 0] が他と重なっている"),
            ({"type": "flow", "nodes": [{"id": "a", "pos": [-1, 0]}]}, "0 以上の有限の数"),
            ({**flow, "edges": {}}, "edges は配列で書く"),
            ({**flow, "edges": [{"from": "a", "to": "a", "label": 1}]}, "edges[0] の label は文字列で書く"),
            ({"type": "state", "states": [{"id": "a", "final": "yes"}]}, "'a' の final は true / false"),
            ({"type": "state", "states": [{"id": "a"}], "initial": "z"}, "initial 'z'"),
            ({**flow, "groups": {}}, "groups は配列で書く"),
            ({**flow, "groups": [{"nodes": []}]}, "groups[0] の nodes を 1 つ以上"),
            ({**flow, "groups": [{"nodes": ["z"]}]}, "nodes 'z'"),
            ({**flow, "direction": "RL"}, "LR か TB"),
            ({**flow, "title": 1}, "title は文字列で書く"),
            ({**SEQ, "legend_labels": {"new": "x"}}, "legend_labels のキー"),
            ({**SEQ, "legend_labels": {"added": ""}}, "legend_labels の値は空でない文字列"),
            ({**SEQ, "legend": "no"}, "legend は true / false"),
        ]
        rc, out, _, tmp = run(*[c for c, _ in cases])
        self.assertEqual(rc, 1)
        self.assertEqual(len(out), len(cases), out)
        for i, (spec, fragment) in enumerate(cases):
            with self.subTest(fragment=fragment):
                self.assertTrue(out[i].startswith(f"failed={tmp / f'd{i}.json'}\t"), out[i])
                self.assertIn(fragment, out[i])
                self.assertFalse((tmp / f"d{i}.svg").exists())

    def test_failed_line_stays_one_line_when_id_has_newline(self):
        rc, out, _, _ = run({"type": "flow", "nodes": [{"id": "注文\nテーブル", "pos": [-1, 0]}]})
        self.assertEqual(rc, 1)
        self.assertEqual(len(out), 1, out)
        self.assertIn("'注文\\nテーブル' の pos", out[0])

    def test_warns_when_wider_than_1200_but_still_writes(self):
        parts = [{"id": f"p{i}", "label": f"とても長い参加者の名前その{i}"} for i in range(8)]
        steps = [{"from": "p0", "to": "p7", "label": "x"}]
        rc, out, _, tmp = run({"type": "sequence", "participants": parts, "steps": steps})
        self.assertEqual(rc, 0)
        self.assertEqual(out[0], f"svg={tmp / 'd0.svg'}")
        self.assertRegex(out[1], rf"^warn={re.escape(str(tmp / 'd0.svg'))}\t幅が \d+px で 1200 を超えた")
        width = int(ET.parse(tmp / "d0.svg").getroot().get("width"))
        self.assertGreater(width, 1200)

    def test_output_is_deterministic(self):
        _, _, _, a = run(SEQ)
        _, _, _, b = run(SEQ)
        self.assertEqual((a / "d0.svg").read_bytes(), (b / "d0.svg").read_bytes())


def budget_warns(out: list[str]) -> list[str]:
    return [w.split("\t", 1)[1] for w in out if w.startswith("warn=") and "\t複雑さの予算を超えた" in w]


def flow_of(n_nodes: int, n_edges: int) -> dict:
    ids = [f"n{i}" for i in range(n_nodes)]
    return {"type": "flow", "nodes": [{"id": i} for i in ids],
            "edges": [{"from": ids[k % n_nodes], "to": ids[(k + 1) % n_nodes]} for k in range(n_edges)]}


def seq_of(n_parts: int, n_msgs: int, frames: list | None = None) -> dict:
    ids = [f"p{i}" for i in range(n_parts)]
    steps = [{"from": ids[k % n_parts], "to": ids[(k + 1) % n_parts]} for k in range(n_msgs)]
    return {"type": "sequence", "participants": [{"id": i} for i in ids], "steps": steps + (frames or [])}


def frame(kind: str, branches: int = 1) -> dict:
    call = {"from": "p0", "to": "p1"}
    if branches == 1:
        return {"frame": kind, "label": "c", "steps": [call]}
    return {"frame": kind, "branches": [{"label": f"b{i}", "steps": [call]} for i in range(branches)]}


class ComplexityBudgetTest(unittest.TestCase):
    """上限ちょうどは黙り、1 つ超えたら warn= を 1 行出す（cathrynlavery/diagram-design の complexity budget）."""

    def assert_budget(self, spec: dict, fragment: str | None) -> None:
        warns = budget_warns(render(spec)[1])
        if fragment is None:
            self.assertEqual(warns, [])
        else:
            self.assertEqual(len(warns), 1, warns)
            self.assertIn(fragment, warns[0])
            self.assertTrue(warns[0].endswith("。概要と詳細の 2 枚に分ける"), warns[0])

    def test_boxes_and_lines(self):
        self.assert_budget(flow_of(9, 12), None)
        self.assert_budget(flow_of(10, 9), "箱 10 > 9")
        self.assert_budget(flow_of(9, 13), "線 13 > 12")

    def test_states_and_transitions(self):
        states = [{"id": "a"}, {"id": "b"}]
        within = [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}, {"from": "a", "to": "a"}, {"from": "b", "to": "b"}]
        self.assert_budget({"type": "state", "states": states, "transitions": within}, None)
        self.assert_budget({"type": "state", "states": states, "transitions": [*within, {"from": "a", "to": "b"}]},
                           "遷移 5 が状態の 2 倍 4 を超えた（2 つの状態機械に分ける）")
        many = [{"id": f"s{i}"} for i in range(10)]
        self.assert_budget({"type": "state", "states": many}, "状態 10 > 9")
        nine = [{"id": f"s{i}"} for i in range(9)]
        ring = [{"from": f"s{k % 9}", "to": f"s{(k + 1) % 9}"} for k in range(13)]
        self.assert_budget({"type": "state", "states": nine, "transitions": ring}, "遷移 13 > 12")
        # 両方を超えたら「状態の 2 倍」だけを出す
        six = {"type": "state", "states": [{"id": f"s{i}"} for i in range(6)],
               "transitions": [{"from": f"s{k % 6}", "to": f"s{(k + 1) % 6}"} for k in range(13)]}
        self.assert_budget(six, "遷移 13 が状態の 2 倍 12 を超えた")
        self.assertNotIn("遷移 13 > 12", budget_warns(render(six)[1])[0])

    def test_participants_and_calls(self):
        self.assert_budget(seq_of(5, 12), None)
        self.assert_budget(seq_of(6, 2), "参加者 6 > 5")
        self.assert_budget(seq_of(2, 13), "呼び出し 13 > 12")

    def test_frames(self):
        self.assert_budget(seq_of(2, 1, [frame("alt", 2)]), None)
        self.assert_budget(seq_of(2, 1, [frame("opt"), frame("loop")]), None)
        self.assert_budget(seq_of(2, 1, [frame("alt", 2), frame("opt")]), "枠 2")
        self.assert_budget(seq_of(2, 1, [frame("opt"), frame("loop"), frame("opt")]), "枠 3")
        self.assert_budget(seq_of(2, 1, [frame("alt", 3)]), "alt の分岐 3 > 2")
        # 入れ子の枠も数える（alt の分岐の中の opt で 2 つ）
        nested = {"frame": "alt", "branches": [{"label": "b0", "steps": [frame("opt")]},
                                               {"label": "b1", "steps": [{"from": "p0", "to": "p1"}]}]}
        self.assert_budget(seq_of(2, 1, [nested]), "枠 2")


class CommonRenderingTest(unittest.TestCase):
    def test_root_has_pixel_size_and_white_background(self):
        root, _ = render(SEQ)
        w, h = root.get("width"), root.get("height")
        self.assertRegex(w, r"^\d+$")
        self.assertRegex(h, r"^\d+$")
        self.assertEqual(root.get("viewBox"), f"0 0 {w} {h}")
        bg = list(root)[0]
        self.assertEqual((bg.tag, bg.get("fill"), bg.get("width"), bg.get("height")), (f"{NS}rect", "#ffffff", w, h))

    def test_arrow_heads_do_not_scale_with_stroke(self):
        root, _ = render(SEQ)
        markers = list(root.iter(f"{NS}marker"))
        self.assertEqual(sorted(m.get("id") for m in markers), ["arrow-added", "arrow-existing"])
        for m in markers:
            self.assertEqual(m.get("markerUnits"), "userSpaceOnUse")

    def test_legend_lists_only_used_statuses_in_fixed_order(self):
        root, _ = render(SEQ)
        items = groups(root, "legend-item")
        self.assertEqual([i.get("data-status") for i in items], ["added", "changed", "existing", "reply"])
        self.assertEqual([text_of(i) for i in items], ["この PR で足した", "この PR で変えた", "既存", "返り値"])

    def test_legend_of_graphs_includes_box_line_and_group_statuses(self):
        root, _ = render({"type": "flow", "nodes": [{"id": "a", "status": "removed"}, {"id": "b"}],
                          "edges": [{"from": "a", "to": "b", "status": "added"}],
                          "groups": [{"nodes": ["b"], "status": "later"}]})
        self.assertEqual([i.get("data-status") for i in groups(root, "legend-item")],
                         ["added", "removed", "existing", "later"])
        root, _ = render({"type": "state", "states": [{"id": "a"}, {"id": "b", "status": "changed"}],
                          "transitions": [{"from": "a", "to": "b"}]})
        self.assertEqual([i.get("data-status") for i in groups(root, "legend-item")], ["changed", "existing"])

    def test_legend_labels_override_and_legend_can_be_turned_off(self):
        root, _ = render({**SEQ, "legend_labels": {"added": "PR-1 で足す"}})
        self.assertEqual(text_of(groups(root, "legend-item")[0]), "PR-1 で足す")
        root, _ = render({**SEQ, "legend": False})
        self.assertEqual(groups(root, "legend"), [])

    def test_no_legend_when_everything_is_existing(self):
        root, _ = render({"type": "flow", "nodes": [{"id": "a"}, {"id": "b"}], "edges": [{"from": "a", "to": "b"}]})
        self.assertEqual(groups(root, "legend"), [])

    def test_status_styles(self):
        root, _ = render({"type": "flow",
                          "nodes": [{"id": "a", "status": "removed"}, {"id": "b", "status": "later"}],
                          "edges": [{"from": "a", "to": "b", "status": "later"}]})
        self.assertEqual(node(root, "a").find(f"{NS}text").get("text-decoration"), "line-through")
        self.assertIsNone(node(root, "b").find(f"{NS}text").get("text-decoration"))
        self.assertEqual(node(root, "b").find(f"{NS}rect").get("stroke-dasharray"), "6 4")
        self.assertIsNone(node(root, "a").find(f"{NS}rect").get("stroke-dasharray"))
        self.assertEqual(edge(root, "a", "b").find(f"{NS}path").get("stroke-dasharray"), "2 4")

    def test_reply_and_later_lines_are_told_apart(self):
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}], "steps": [
            {"from": "a", "to": "b"}, {"from": "b", "to": "a", "reply": True},
            {"from": "a", "to": "b", "status": "later"}, {"from": "b", "to": "a", "reply": True, "status": "later"}]})
        dashes = [m.find(f"{NS}path").get("stroke-dasharray") for m in groups(root, "message")]
        self.assertEqual(dashes, [None, "6 4", "2 4", "8 3 2 3"])

    def test_title_is_drawn_above_content(self):
        root, _ = render({**SEQ, "title": "削除の流れ"})
        title = groups(root, "title")[0]
        self.assertEqual(text_of(title), "削除の流れ")
        top_of_header = min(rect_of(p)[1] for p in groups(root, "participant"))
        self.assertLess(float(title.find(f"{NS}text/{NS}tspan").get("y")), top_of_header)


class SequenceTest(unittest.TestCase):
    def test_full_width_and_ambiguous_width_headers_fit_their_boxes(self):
        # 全角も曖昧幅（→ ① ×）も 1 文字 = 1em（14px）を下限に置く。英字の幅で見積もると、この下限を割る
        for label in ("監査ログを書き込む処理", "→①×→①×→①×"):
            with self.subTest(label=label):
                root, _ = render({"type": "sequence", "participants": [{"id": "a", "label": label}, {"id": "b"}],
                                  "steps": [{"from": "a", "to": "b"}]})
                x0, _, x1, _ = rect_of(node(root, "a"))
                self.assertGreaterEqual(x1 - x0, len(label) * 14)

    def test_headers_never_overlap(self):
        parts = [{"id": f"p{i}", "label": "長い見出しの参加者" * (i % 2 + 1)} for i in range(4)]
        root, _ = render({"type": "sequence", "participants": parts, "steps": [{"from": "p0", "to": "p1"}]})
        rects = [rect_of(node(root, f"p{i}")) for i in range(4)]
        for left, right in zip(rects, rects[1:]):
            self.assertLess(left[2], right[0])

    def test_message_label_fits_between_its_lifelines(self):
        label = "とても長い呼び出しの説明を書いたラベル"
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                          "steps": [{"from": "a", "to": "b", "label": label}, {"from": "b", "to": "c"}]})
        bg = label_bg(root, label)
        self.assertGreater(bg[0], center(root, "a")[0])
        self.assertLess(bg[2], center(root, "b")[0])
        self.assertGreaterEqual(bg[2] - bg[0], len(label) * 13)

    def test_label_of_call_skipping_a_lifeline_fits_between_its_ends(self):
        label = "途中の層を飛ばして呼ぶとても長いラベルの呼び出し"
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                          "steps": [{"from": "a", "to": "c", "label": label}]})
        bg = label_bg(root, label)
        self.assertGreater(bg[0], center(root, "a")[0])
        self.assertLess(bg[2], center(root, "c")[0])

    def test_multi_line_message_label_sits_above_its_arrow(self):
        label = "deleteItem(id)\n確認後に呼ぶ"
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}],
                          "steps": [{"from": "a", "to": "b", "label": label}, {"from": "b", "to": "a", "label": "x"}]})
        arrows = [path_points(m.find(f"{NS}path").get("d"))[0][1] for m in groups(root, "message")]
        bg = label_bg(root, label)
        self.assertLess(bg[3], arrows[0])
        self.assertGreater(label_bg(root, "x")[1], arrows[0])

    def test_frame_is_wide_enough_for_its_guard(self):
        guard = "見つからなかったときの処理"
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}],
                          "steps": [{"frame": "opt", "label": guard, "steps": [{"from": "a", "to": "a"}]}]})
        frame = groups(root, "frame")[0]
        self.assertEqual(frame.get("data-kind"), "opt")
        fx0, _, fx1, _ = rect_of(frame)
        bg = label_bg(root, f"[{guard}]")
        self.assertGreater(bg[0], fx0)
        self.assertLessEqual(bg[2], fx1)

    def test_multi_line_guard_stays_below_its_divider(self):
        guard = "在庫が無い\nまたは\n非会員"
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}], "steps": [
            {"frame": "alt", "branches": [
                {"label": "ある", "steps": [{"from": "a", "to": "b"}, {"from": "b", "to": "a", "reply": True}]},
                {"label": guard, "steps": [{"from": "b", "to": "a", "label": "ng"}]}]}]})
        frame = groups(root, "frame")[0]
        divider = next(p for p in frame.iter(f"{NS}path") if p.get("stroke-dasharray") == "6 4")
        dy = path_points(divider.get("d"))[0][1]
        arrows = [path_points(m.find(f"{NS}path").get("d"))[0][1] for m in groups(root, "message")]
        bg = label_bg(root, f"[{guard}]")
        self.assertLess(arrows[1], dy)
        self.assertGreater(bg[1], dy)
        self.assertLess(bg[3], label_bg(root, "ng")[1])

    def test_nested_frame_stays_inside_outer_frame(self):
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                          "steps": [{"frame": "loop", "label": "各行", "steps": [
                              {"from": "a", "to": "b"},
                              {"frame": "alt", "label": "とても長い条件の説明をここに書いておく", "steps": [
                                  {"from": "b", "to": "c"}]}]}]})
        frames = {f.get("data-kind"): rect_of(f) for f in groups(root, "frame")}
        outer, inner = frames["loop"], frames["alt"]
        self.assertLess(outer[0], inner[0])
        self.assertGreater(outer[2], inner[2])
        self.assertLess(outer[1], inner[1])
        self.assertGreater(outer[3], inner[3])

    def test_frame_encloses_its_messages_vertically(self):
        root, _ = render(SEQ)
        _, fy0, _, fy1 = rect_of(groups(root, "frame")[0])
        ys = [path_points(m.find(f"{NS}path").get("d"))[0][1] for m in groups(root, "message")]
        self.assertEqual(len(ys), 5)
        self.assertTrue(all(fy0 < y < fy1 for y in ys[3:]), (fy0, fy1, ys))
        self.assertTrue(all(y < fy0 for y in ys[:3]))

    def test_else_divider_sits_between_branches(self):
        root, _ = render(SEQ)
        frame = groups(root, "frame")[0]
        dividers = [p for p in frame.iter(f"{NS}path") if p.get("stroke-dasharray") == "6 4"]
        self.assertEqual(len(dividers), 1)
        dy = path_points(dividers[0].get("d"))[0][1]
        ys = [path_points(m.find(f"{NS}path").get("d"))[0][1] for m in groups(root, "message")]
        self.assertLess(ys[3], dy)
        self.assertGreater(ys[4], dy)

    def test_self_message_on_last_lifeline_stays_on_canvas(self):
        label = "自分を呼ぶ長いラベルの呼び出し"
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}],
                          "steps": [{"from": "b", "to": "b", "label": label}]})
        tx, _ = translate(root)
        bg = label_bg(root, label)
        self.assertLessEqual(bg[2] + tx, float(root.get("width")))
        self.assertGreaterEqual(bg[2] - bg[0], len(label) * 13)

    def test_self_message_label_does_not_reach_next_lifeline(self):
        label = "自分を呼ぶ長いラベルの呼び出し"
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}],
                          "steps": [{"from": "a", "to": "a", "label": label}]})
        self.assertLess(label_bg(root, label)[2], center(root, "b")[0])

    def test_lifelines_run_from_header_to_below_last_message(self):
        root, _ = render(SEQ)
        last_y = max(path_points(m.find(f"{NS}path").get("d"))[0][1] for m in groups(root, "message"))
        lifelines = [p for p in root.iter(f"{NS}path") if p.get("class") == "lifeline"]
        self.assertEqual(len(lifelines), 4)
        head_bottom = rect_of(node(root, "ui"))[3]
        for p in lifelines:
            d = p.get("d")
            y0 = float(re.match(r"M [-\d.]+ ([-\d.]+)", d).group(1))
            y1 = float(re.search(r"V ([-\d.]+)", d).group(1))
            self.assertEqual(y0, head_bottom)
            self.assertGreater(y1, last_y)


CHAIN = {"type": "state", "initial": "a",
         "states": [{"id": "a", "label": "閉じている"}, {"id": "b", "label": "確認中"}, {"id": "c", "label": "送信中"}],
         "transitions": [{"from": "a", "to": "b", "label": "削除を押す"}, {"from": "b", "to": "a", "label": "キャンセル"},
                         {"from": "b", "to": "c", "label": "削除する"}, {"from": "c", "to": "a", "label": "閉じる"}]}


class GraphLayoutTest(unittest.TestCase):
    def test_auto_layout_follows_direction(self):
        spec = {"type": "flow", "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}]}
        c = {i: center(render(spec)[0], i) for i in "abc"}
        self.assertTrue(c["a"][0] < c["b"][0] < c["c"][0])
        self.assertTrue(c["a"][1] == c["b"][1] == c["c"][1])
        root = render({**spec, "direction": "TB"})[0]
        c = {i: center(root, i) for i in "abc"}
        self.assertTrue(c["a"][1] < c["b"][1] < c["c"][1])
        self.assertTrue(c["a"][0] == c["b"][0] == c["c"][0])

    def test_back_edge_does_not_change_layers(self):
        root, _ = render(CHAIN)
        c = {i: center(root, i) for i in "abc"}
        self.assertTrue(c["a"][0] < c["b"][0] < c["c"][0])

    def test_pos_places_nodes_on_grid_and_overrides_direction(self):
        spec = {"type": "flow", "nodes": [{"id": "a", "pos": [1, 0]}, {"id": "b", "pos": [0, 1]}]}
        lr = {i: center(render(spec)[0], i) for i in "ab"}
        self.assertGreater(lr["a"][0], lr["b"][0])
        self.assertLess(lr["a"][1], lr["b"][1])
        tb = {i: center(render({**spec, "direction": "TB"})[0], i) for i in "ab"}
        self.assertEqual(lr, tb)

    def test_warns_when_boxes_overlap(self):
        _, out = render({"type": "flow", "nodes": [{"id": "a", "pos": [0, 0]}, {"id": "b", "pos": [0.5, 0]}]})
        self.assertIn("\t箱 'a' と 'b' が重なる（pos の間隔を 1 以上空ける）", out[1])

    def test_group_encloses_only_its_members(self):
        spec = {"type": "flow",
                "nodes": [{"id": "src"}, {"id": "old", "status": "removed"}, {"id": "new", "status": "added"},
                          {"id": "agg", "status": "changed"}],
                "edges": [{"from": "src", "to": "old"}, {"from": "src", "to": "new"},
                          {"from": "old", "to": "agg"}, {"from": "new", "to": "agg"}],
                "groups": [{"label": "レビューで見てほしい範囲", "nodes": ["new", "agg"], "status": "added"}]}
        root, out = render(spec)
        self.assertEqual(len(out), 1, out)
        g = rect_of(groups(root, "group")[0])
        for m in ("new", "agg"):
            r = rect_of(node(root, m))
            self.assertTrue(g[0] < r[0] and r[2] < g[2] and g[1] < r[1] and r[3] < g[3])
        for m in ("src", "old"):
            self.assertFalse(overlap(rect_of(node(root, m)), g), m)

    def test_group_frame_is_wide_enough_for_its_heading(self):
        root, _ = render({"type": "flow", "nodes": [{"id": "a"}],
                          "groups": [{"label": "とても長い範囲の見出しをここに書いておく", "nodes": ["a"]}]})
        self.assertGreaterEqual(rect_of(groups(root, "group")[0])[2],
                                bg_before(root, "とても長い範囲の見出しをここに書いておく", "group-heading")[2])

    def test_group_warns_when_pos_puts_an_outsider_inside(self):
        spec = {"type": "flow", "nodes": [{"id": "a", "pos": [0, 0]}, {"id": "b", "pos": [1, 0]},
                                          {"id": "c", "pos": [2, 0]}],
                "groups": [{"nodes": ["a", "c"]}]}
        _, out = render(spec)
        self.assertEqual(len(out), 2)
        self.assertTrue(out[1].endswith("\tgroups[0] の枠に、メンバーでない 'b' が入った（pos で並べ直す）"), out)


class GraphEdgeTest(unittest.TestCase):
    def test_round_trip_edges_are_drawn_apart(self):
        root, _ = render(CHAIN)
        (ab0, ab1), (ba0, ba1) = (path_points(edge(root, *p).find(f"{NS}path").get("d")) for p in ("ab", "ba"))
        self.assertNotEqual(ab0[1], ba0[1])
        self.assertLess(ab0[0], ab1[0])
        self.assertGreater(ba0[0], ba1[0])

    def test_edge_ends_sit_on_box_borders(self):
        root, _ = render(CHAIN)
        for a, b in (("a", "b"), ("b", "c")):
            (sx, sy), (ex, ey) = path_points(edge(root, a, b).find(f"{NS}path").get("d"))
            ra, rb = rect_of(node(root, a)), rect_of(node(root, b))
            self.assertAlmostEqual(sx, ra[2], delta=0.6)
            self.assertAlmostEqual(ex, rb[0], delta=0.6)
            self.assertTrue(ra[1] < sy < ra[3])

    def test_edge_that_would_cross_a_box_is_curved_around_it(self):
        root, out = render(CHAIN)
        g = edge(root, "c", "a")
        self.assertEqual(g.get("data-route"), "curve")
        pts = path_points(g.find(f"{NS}path").get("d"))
        middle = rect_of(node(root, "b"))
        for p in pts:
            self.assertFalse(middle[0] < p[0] < middle[2] and middle[1] < p[1] < middle[3], p)
        self.assertTrue(on_border(pts[0], rect_of(node(root, "c"))), pts[0])
        self.assertTrue(on_border(pts[-1], rect_of(node(root, "a"))), pts[-1])
        self.assertEqual(len(out), 1)
        self.assertEqual(edge(root, "a", "b").get("data-route"), "straight")

    def test_warns_when_no_route_avoids_boxes(self):
        # 間の列を箱で埋め、まっすぐも上下どちらへ曲げても箱に当たる形にする
        wall = [{"id": f"w{i}", "pos": [1, i * 0.4]} for i in range(9)]
        nodes = [{"id": "a", "pos": [0, 1.6]}, {"id": "b", "pos": [2, 1.6]}, *wall]
        root, out = render({"type": "flow", "nodes": nodes, "edges": [{"from": "a", "to": "b"}]})
        warns = [w.split("\t", 1)[1] for w in out[1:]]
        self.assertEqual(warns, ["複雑さの予算を超えた（箱 11 > 9）。概要と詳細の 2 枚に分ける",
                                 "edges の 'a' → 'b' が他の箱を横切る（pos で並べ直す）"], out)
        self.assertEqual(edge(root, "a", "b").get("data-route"), "straight")

    def test_parallel_edges_start_inside_tall_boxes(self):
        # 縦に並んだ背の高い箱の間の辺 8 本。ずらし幅を箱の高さで決めると、始点が箱の幅の外に出る
        tall = "一\n二\n三\n四\n五"
        spec = {"type": "flow", "direction": "TB", "nodes": [{"id": "a", "label": tall}, {"id": "b", "label": tall}],
                "edges": [{"from": "a", "to": "b"}] * 8}
        root, _ = render(spec)
        ra = rect_of(node(root, "a"))
        for k in range(8):
            start = path_points(edge(root, "a", "b", k).find(f"{NS}path").get("d"))[0]
            self.assertTrue(ra[0] - 0.6 <= start[0] <= ra[2] + 0.6, (k, start, ra))
            self.assertTrue(on_border(start, ra), (k, start))


class GraphLabelTest(unittest.TestCase):
    def assert_apart(self, root, texts):
        bgs = [label_bg(root, s) for s in texts]
        for i, r in enumerate(bgs):
            for s in bgs[i + 1:]:
                self.assertFalse(overlap(r, s), (r, s))

    def test_labels_do_not_overlap_each_other(self):
        root, out = render(CHAIN)
        self.assert_apart(root, ("削除を押す", "キャンセル", "削除する", "閉じる"))
        self.assertEqual(len(out), 1, out)

    def test_vertical_round_trip_labels_sit_beside_their_lines(self):
        root, out = render({"type": "flow", "direction": "TB", "nodes": [{"id": "a"}, {"id": "b"}],
                            "edges": [{"from": "a", "to": "b", "label": "リクエストを送る"},
                                      {"from": "b", "to": "a", "label": "レスポンスを返す"}]})
        self.assertEqual(len(out), 1, out)
        self.assert_apart(root, ("リクエストを送る", "レスポンスを返す"))
        xs = [path_points(edge(root, *p).find(f"{NS}path").get("d"))[0][0] for p in ("ab", "ba")]
        for text in ("リクエストを送る", "レスポンスを返す"):
            bg = label_bg(root, text)
            for x in xs:
                self.assertFalse(bg[0] < x < bg[2], (text, bg, x))

    def test_labels_of_parallel_vertical_edges_do_not_collide(self):
        root, out = render({"type": "flow", "direction": "TB",
                            "nodes": [{"id": "r"}, {"id": "a"}, {"id": "b"}, {"id": "a2"}, {"id": "b2"}],
                            "edges": [{"from": "r", "to": "a"}, {"from": "r", "to": "b"},
                                      {"from": "a", "to": "a2", "label": "とても長いラベルの一本目の辺"},
                                      {"from": "b", "to": "b2", "label": "とても長いラベルの二本目の辺"}]})
        self.assertEqual(len(out), 1, out)
        self.assert_apart(root, ("とても長いラベルの一本目の辺", "とても長いラベルの二本目の辺"))

    def test_multi_line_label_of_vertical_edge_fits_between_boxes(self):
        label = "一行目\n二行目\n三行目"
        root, _ = render({"type": "flow", "direction": "TB", "nodes": [{"id": "a"}, {"id": "b"}],
                          "edges": [{"from": "a", "to": "b", "label": label}]})
        bg = label_bg(root, label)
        for n in "ab":
            self.assertFalse(overlap(bg, rect_of(node(root, n))), n)

    def test_self_loop_label_stays_clear_of_incoming_vertical_edge_label(self):
        root, out = render({"type": "state", "states": [{"id": "s", "pos": [0, 0]}, {"id": "e", "pos": [0, 1]}],
                            "transitions": [{"from": "s", "to": "e", "label": "失敗する"},
                                            {"from": "e", "to": "e", "label": "閉じる"},
                                            {"from": "e", "to": "e", "label": "下書き保存"}]})
        self.assertEqual(len(out), 1, out)
        self.assert_apart(root, ("失敗する", "閉じる", "下書き保存"))
        loops = [path_points(edge(root, "e", "e", k).find(f"{NS}path").get("d")) for k in range(2)]
        self.assertNotEqual(loops[0][1], loops[1][1])
        top = rect_of(node(root, "e"))[1]
        self.assertLess(label_bg(root, "閉じる")[3], top)

    def test_group_heading_is_masked_and_avoided_by_incoming_edge_label(self):
        root, out = render({"type": "flow", "direction": "TB",
                            "nodes": [{"id": "src"}, {"id": "f", "status": "added"}],
                            "edges": [{"from": "src", "to": "f", "label": "createdAt"}],
                            "groups": [{"label": "レビューで見てほしい範囲", "nodes": ["f"], "status": "added"}]})
        self.assertEqual(len(out), 1, out)
        heading = bg_before(root, "レビューで見てほしい範囲", "group-heading")
        self.assertFalse(overlap(label_bg(root, "createdAt"), heading))

    def test_warns_when_a_label_has_nowhere_to_go(self):
        edges = [{"from": "a", "to": "b", "label": f"長めのラベルその{i}"} for i in range(4)]
        _, out = render({"type": "flow", "nodes": [{"id": "a"}, {"id": "b"}], "edges": edges})
        warns = [w for w in out[1:] if "のラベルが他のラベルか箱と重なる" in w]
        self.assertTrue(warns, out)
        self.assertIn("\tedges の 'a' → 'b' のラベルが", warns[0])

    def test_self_loop_initial_marker_and_final_state(self):
        root, _ = render({"type": "state", "initial": "a",
                          "states": [{"id": "a"}, {"id": "b", "final": True}],
                          "transitions": [{"from": "a", "to": "a", "label": "再読み込み"}, {"from": "a", "to": "b"}]})
        self.assertEqual(edge(root, "a", "a").get("data-route"), "self")
        circle = groups(root, "initial")[0].find(f"{NS}circle")
        self.assertLess(float(circle.get("cx")), rect_of(node(root, "a"))[0])
        self.assertEqual(len(node(root, "b").findall(f"{NS}rect")), 2)
        self.assertEqual(len(node(root, "a").findall(f"{NS}rect")), 1)
        self.assertLess(label_bg(root, "再読み込み")[3], rect_of(node(root, "a"))[1])

    def test_initial_marker_moves_off_an_incoming_edge(self):
        # 左から initial へ入る辺があると、左に置いた黒丸はその線に乗る。上へ逃がす
        root, out = render({"type": "state", "initial": "a",
                            "states": [{"id": "x", "pos": [0, 0]}, {"id": "a", "pos": [1, 0]}],
                            "transitions": [{"from": "x", "to": "a"}]})
        self.assertEqual(len(out), 1, out)
        circle = groups(root, "initial")[0].find(f"{NS}circle")
        ra = rect_of(node(root, "a"))
        self.assertLess(float(circle.get("cy")), ra[1])
        self.assertTrue(ra[0] < float(circle.get("cx")) < ra[2])


if __name__ == "__main__":
    unittest.main()
