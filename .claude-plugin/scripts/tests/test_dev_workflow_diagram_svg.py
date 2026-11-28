#!/usr/bin/env python3
"""dev-workflow の説明図の生成（diagram-svg.py）の CLI 境界テスト.

pr-creator Step 4.6 が PR に添付する図を、JSON の定義から SVG に組む（GitHub issue #349）。測るもの:

- 出力の契約: 定義の隣に .svg を書いて svg= を出す。壊れた定義は failed= を 1 行出し、他の定義の処理は続ける
  （exit 1）。型の違う値・UTF-8 でない定義・想定外の例外も failed= に落とす。幅が 1200 を超えた・線が箱を
  避けられない・ラベルや箱が重なった・範囲の枠に範囲外の箱が入った・複雑さの予算（箱 9・線 12・参加者 5・
  枠 1（分岐の無い枠だけなら 2）・alt の分岐 2・遷移は状態の 2 倍まで）を超えたときは warn= を足す。上限ちょうどでは黙る。
  flow / state は縦長・横長・線どうしの交差・線が枠の見出しの下を通るときも warn= を足す（#452）。
  sequence は title が無いときも warn= を足し、flow / state の legend_labels に reply / error を書くと failed=（#567）
- 太字で描く文字（2 行目のある参加者の 1 行目・区間の枠の札・範囲の枠の見出し・図の title）は、英字なら実測の
  太字の比で広げた幅に収まり、和文は太字でない幅のまま（#567）
- 手で描いたときに踏んだ 3 点（全角と曖昧幅の見出しが箱に収まる / 矢印の先が markerUnits="userSpaceOnUse" /
  ライフラインの見出しの箱が隣と重ならない）。1 点目はスクリプトの見積もりを使わず、1 文字 14px を下限に置く
- sequence: 呼び出しのラベルが両端のライフラインの間に収まる・複数行のラベルが矢印を隠さない・入れ子の枠が
  外の枠の内側に収まる
- state / flow: 往復の辺のラベルが向き（横・縦）に関わらず重ならない・自己ループのラベルが入ってくる辺の
  ラベルと重ならない・間の箱を横切る辺を曲げる・線の端が箱の境界に乗る・範囲の枠がメンバーだけを囲む
- flow の自動配置: groups の枠ごとに行（TB は列）の帯を取り、枠の外の箱は帯の行を避ける（#499）
- sequence の注記・区間の枠・エラーで戻る線・参加者の 2 行目（#533）: 注記は生存線の右で次の生存線に届かず、
  前後の呼び出しと縦に重ならない。区間の枠は札に名前、右に説明を括弧なしで出し、枠の予算に数えない。
  エラーで戻る線は赤の破線。2 行目は見出しの箱に収まる。新しいキーを使わない図は前の版と同じバイト列を出す（枠が次の生存線を越えていた図は列の間隔が広がる）
- 凡例: 使った status（箱・線・枠）だけを出し、legend_labels で文言を差し替えられる。sequence は枠で囲み、
  部品（参加者・注記）と呼び出し（線）を段に分ける
- --texts（#568）: .svg を書かずに、図に描く文字列を定義の中の場所つきで 1 件 1 行出す。期待する一覧はテストに
  手で書き、同じ定義で描いた SVG の <text> の中身と data-* の属性の値が、固定の語を除いて一覧の値と一致することも見る
- 境界ちょうどの点・矩形の判定（inside / overlap）、線分の接触と同じ直線上の 2 本（crosses）、折れ線が矩形を
  通るか（through）、縦長・横長の上限ちょうどは CLI から配置を作れないため、GeometryBoundaryTest だけ関数を直接
  読み込んで呼ぶ（上限ちょうどは定数を図の寸法に差し替えて測る）

描画は決定的なので、同じ定義の描画は 1 回だけ回して結果を使い回す（起動の回数を減らす）。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
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


def run(*specs: object, names: list[str] | None = None,
        flags: tuple[str, ...] = ()) -> tuple[int, list[str], str, Path]:
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
    proc = subprocess.run([sys.executable, str(SCRIPT), *flags, *args], capture_output=True, text=True, timeout=60)
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
# 出力の行を丸ごと比べるテストに使う。title の無い sequence は warn= が付く（#567）
SEQ_TITLED = {**SEQ, "title": "削除の流れ"}


class OutputContractTest(unittest.TestCase):
    def test_no_args_exits_2_with_usage(self):
        proc = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage", proc.stderr)

    def test_writes_svg_next_to_definition(self):
        rc, out, _, tmp = run(SEQ_TITLED)
        self.assertEqual(rc, 0)
        self.assertEqual(out, [f"svg={tmp / 'd0.svg'}"])
        self.assertTrue((tmp / "d0.svg").read_text(encoding="utf-8").startswith("<svg "))
        self.assertEqual(sorted(p.name for p in tmp.iterdir()), ["d0.json", "d0.svg"])

    def test_failures_are_reported_per_file_and_others_still_render(self):
        rc, out, _, tmp = run("{broken", SEQ_TITLED, None, SEQ_TITLED, names=["a.json", "b.json", "c.json", "d.txt"])
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
        rc, out, _, tmp = run(*[c for c, _ in cases], SEQ_TITLED)
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
            ({"type": "flow", "nodes": [{"id": "a", "pos": [1]}]}, "'a' の pos は [列, 行]"),
            ({"type": "flow", "nodes": [{"id": ""}]}, "nodes[0] に id が無い"),
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
            ({**SEQ, "steps": [{"note": "", "at": "ui"}]}, "note は空でない文字列"),
            ({**SEQ, "steps": [{"note": "x", "at": "z"}]}, "at 'z' が定義に無い"),
            ({**SEQ, "steps": [{"note": "x", "at": "ui", "label": "y"}]}, "知らないキー 'label'"),
            ({**SEQ, "steps": [{"frame": "opt", "label": "x", "cond": "y", "steps": [{"from": "ui", "to": "act"}]}]},
             "cond は section の枠だけに書ける"),
            ({**SEQ, "steps": [{"frame": "section", "steps": [{"from": "ui", "to": "act"}]}]}, "label は空でない文字列"),
            ({**SEQ, "steps": [{"frame": "section", "label": "1.\n受付", "steps": [{"from": "ui", "to": "act"}]}]},
             "label と cond は 1 行で書く"),
            ({**SEQ, "steps": [{"frame": "section", "label": "1", "cond": "a\nb", "steps": [{"from": "ui", "to": "act"}]}]},
             "label と cond は 1 行で書く"),
            ({**SEQ, "steps": [{"frame": "section", "label": "1", "branches": []}]}, "branches は alt の枠だけ"),
            ({**SEQ, "steps": [{"from": "ui", "to": "act", "error": 1}]}, "error は true / false"),
            ({**SEQ, "steps": [{"from": "ui", "to": "act", "error": True, "status": "added"}]},
             "error と status を一緒に書けない"),
            ({**SEQ, "participants": [{"id": "a", "sublabel": 1}]}, "participants[0] の sublabel は文字列で書く"),
            ({"type": "flow", "nodes": [{"id": "a", "sublabel": "x"}]}, "知らないキー 'sublabel'"),
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

    def test_exactly_1200_wide_does_not_warn(self):
        # 箱 1 つで幅がちょうど 1200 になる見出し（全角 63・英大文字 14・英小文字 12）
        root, out = render({"type": "flow", "nodes": [{"id": "a", "label": "あ" * 63 + "W" * 14 + "w" * 12}]})
        self.assertEqual(root.get("width"), "1200")
        # 高さ 84 の 1 行なので横長の warn は出る（LayoutShapeTest）。ここで見るのは幅の warn だけ
        self.assertFalse([w for w in out if "\t幅が " in w], out)

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

    def test_sections_and_notes_are_not_counted(self):
        def section(i: int) -> dict:
            return {"frame": "section", "label": f"{i}", "steps": [{"from": "p0", "to": "p1"}]}

        # 区間の枠は分岐を持たないので、分岐のある枠と並べても数えない。注記は呼び出しに数えない
        self.assert_budget(seq_of(2, 1, [section(1), section(2), section(3), frame("alt", 2)]), None)
        notes = [{"note": "n", "at": "p0"} for _ in range(3)]
        self.assert_budget(seq_of(5, 12, notes), None)
        self.assert_budget(seq_of(2, 1, [section(1), frame("alt", 2), frame("opt")]), "枠 2")


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

    def test_sequence_legend_splits_boxes_and_lines_into_framed_rows(self):
        root, _ = render(SEQ)
        rows = groups(root, "legend-row")
        self.assertEqual([r.get("data-row") for r in rows], ["boxes", "lines"])
        self.assertEqual([text_of(r.find(f"{NS}text")) for r in rows], ["部品", "呼び出し"])
        boxes, lines = (groups(r, "legend-item") for r in rows)
        self.assertEqual([i.get("data-status") for i in boxes], ["added", "changed", "existing"])
        # 呼び出しの段に changed は無い（SEQ で changed なのは参加者だけ）
        self.assertEqual([i.get("data-status") for i in lines], ["added", "existing", "reply"])
        self.assertEqual([text_of(i) for i in lines], ["この PR で足した", "既存", "返り値"])
        self.assertIsNotNone(boxes[0].find(f"{NS}rect"))
        self.assertIsNone(lines[0].find(f"{NS}rect"))
        self.assertEqual(lines[2].find(f"{NS}path").get("stroke-dasharray"), "6 4")
        frame = next(r for r in root.iter(f"{NS}rect") if r.get("class") == "legend-frame")
        fr = rect_of(frame)
        for item in boxes + lines:
            sample = item.find(f"{NS}rect") if item.find(f"{NS}rect") is not None else item.find(f"{NS}path")
            x = float(sample.get("x")) if sample.tag == f"{NS}rect" else path_points(sample.get("d"))[0][0]
            self.assertTrue(fr[0] < x < fr[2], (fr, x))
        lowest = max(path_points(p.get("d"))[-1][1] for p in root.iter(f"{NS}path") if p.get("class") == "lifeline")
        self.assertGreater(fr[1], lowest)

    def test_sequence_legend_shows_replies_as_dashed_samples_of_their_status(self):
        # 返り値の線は status の色の破線で描くので、凡例も同じ破線の見本にする。status を実線の見本として出すと
        # 図に無い線になり、返り値の見本を灰色に決め打ちすると返り値にしか使っていない色の説明が消える
        for reply_status, key, text in (("existing", "reply", "返り値"),
                                        ("added", "reply:added", "返り値（この PR で足した）"),
                                        ("changed", "reply:changed", "返り値（この PR で変えた）"),
                                        ("removed", "reply:removed", "返り値（この PR で消した）"),
                                        ("later", "reply:later", "返り値（後続の PR）")):
            with self.subTest(reply_status):
                root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}], "steps": [
                    {"from": "a", "to": "b"}, {"from": "b", "to": "a", "reply": True, "status": reply_status}]})
                lines = groups(groups(root, "legend-row")[1], "legend-item")
                self.assertEqual([i.get("data-status") for i in lines], ["existing", key])
                self.assertEqual(text_of(lines[1]), text)
                drawn = groups(root, "message")[1].find(f"{NS}path")
                sample = lines[1].find(f"{NS}path")
                self.assertEqual({k: sample.get(k) for k in ("stroke", "stroke-dasharray", "marker-end")},
                                 {k: drawn.get(k) for k in ("stroke", "stroke-dasharray", "marker-end")})

    def test_sequence_legend_without_boxes_other_than_existing_still_shows_reply(self):
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}],
                          "steps": [{"from": "a", "to": "b"}, {"from": "b", "to": "a", "reply": True}]})
        self.assertEqual([r.get("data-row") for r in groups(root, "legend-row")], ["boxes", "lines"])
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}],
                          "steps": [{"from": "a", "to": "b"}, {"note": "説明", "at": "a"}]})
        self.assertEqual(groups(root, "legend"), [])

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
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}],
                          "steps": [{"from": "b", "to": "a", "error": True}], "legend_labels": {"error": "例外"}})
        self.assertEqual(text_of(groups(root, "legend-item")[-1]), "例外")
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

    def test_bold_only_on_title_frame_kind_and_group_heading(self):
        root, _ = render({**SEQ, "title": "削除の流れ"})
        self.assertEqual(groups(root, "title")[0].find(f"{NS}text").get("font-weight"), "bold")
        tab = next(t for t in root.iter(f"{NS}text") if text_of(t) == "alt")
        self.assertEqual(tab.get("font-weight"), "bold")
        self.assertIsNone(node(root, "ui").find(f"{NS}text").get("font-weight"))
        label = next(t for t in root.iter(f"{NS}text") if text_of(t) == "deleteItem(id)")
        self.assertIsNone(label.get("font-weight"))
        root, _ = render({"type": "flow", "nodes": [{"id": "a"}], "groups": [{"label": "範囲", "nodes": ["a"]}]})
        heading = next(t for t in root.iter(f"{NS}text") if text_of(t) == "範囲")
        self.assertEqual(heading.get("font-weight"), "bold")

    def test_only_removed_lines_strike_their_labels(self):
        def deco(root, text):
            return next(t for t in root.iter(f"{NS}text") if text_of(t) == text).get("text-decoration")

        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}], "steps": [
            {"from": "a", "to": "b", "label": "消す", "status": "removed"}, {"from": "b", "to": "a", "label": "残す"},
            {"frame": "opt", "label": "条件", "steps": [{"from": "a", "to": "b", "label": "中"}]}]})
        self.assertEqual(deco(root, "消す"), "line-through")
        self.assertIsNone(deco(root, "残す"))
        self.assertIsNone(deco(root, "[条件]"))
        root, _ = render({"type": "flow", "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                          "edges": [{"from": "a", "to": "b", "label": "消す", "status": "removed"},
                                    {"from": "b", "to": "c", "label": "残す"}]})
        self.assertEqual(deco(root, "消す"), "line-through")
        self.assertIsNone(deco(root, "残す"))

    def test_upper_case_letters_are_estimated_wider_than_lower_case(self):
        root, _ = render({"type": "flow", "nodes": [{"id": "u", "label": "W" * 12}, {"id": "l", "label": "w" * 12}]})
        (u0, _, u1, _), (l0, _, l1, _) = rect_of(node(root, "u")), rect_of(node(root, "l"))
        self.assertGreater(u1 - u0, l1 - l0)

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

    def test_header_box_is_single(self):
        root, _ = render(SEQ)
        self.assertEqual(len(node(root, "ui").findall(f"{NS}rect")), 1)

    def test_frame_reaches_past_label_of_self_message(self):
        label = "自分を呼ぶ長いラベルの呼び出し"
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                          "steps": [{"frame": "opt", "steps": [{"from": "a", "to": "a", "label": label}]},
                                    {"from": "b", "to": "c"}]})
        self.assertGreater(rect_of(groups(root, "frame")[0])[2], label_bg(root, label)[2])

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


def note(root: ET.Element, nth: int = 0) -> ET.Element:
    return groups(root, "note")[nth]


def arrow_ys(root: ET.Element) -> list[float]:
    return [path_points(m.find(f"{NS}path").get("d"))[0][1] for m in groups(root, "message")]


# 前の版（#533 より前）が出したバイト列の sha256。新しいキーを使わない図の描画が変わらないことを押さえる。
# 凡例の無い sequence と、凡例が前の形のままの flow / state を選んだ（sequence の凡例は #533 で形が変わる）。
# sequence の 2 つは #567 で打ち直した。太字の見積もりで alt / opt / loop の札が広がり、変わったのは札の幅と、
# その右の条件の位置だけ（前後の SVG を比べて確かめた）
UNCHANGED = {
    "0b2d7c6abdaa4dfe95ac40b9b3ac48c2a4806a41aae2a84d58661f789580416e": {**SEQ, "legend": False, "title": "削除の流れ"},
    "8bacff933e419e7a12f136c80f2ee46a3ec7b1666769cfafd810fdc525bc7a45": {
        "type": "sequence", "participants": [{"id": "a", "label": "画面"}, {"id": "b", "label": "API"}],
        "steps": [{"from": "a", "to": "b", "label": "取得"}, {"frame": "opt", "label": "キャッシュが無い", "steps": [
            {"from": "b", "to": "b", "label": "組み立てる"},
            {"frame": "loop", "label": "各行", "steps": [{"from": "b", "to": "a", "label": "行\n2 行目"}]}]}]},
    "76d4b28dd2d32e3e6b602c84fa768d87b07b6c406315a2c69eaab145da698af4": {
        "type": "flow", "nodes": [{"id": "a", "status": "removed"}, {"id": "b"}],
        "edges": [{"from": "a", "to": "b", "status": "added", "label": "呼ぶ"}],
        "groups": [{"nodes": ["b"], "status": "later", "label": "範囲"}]},
    "1ce0e8d56750a86517326251a109a5f68b08f549d474c0a1dab518e547a85f44": {
        "type": "state", "initial": "a", "states": [{"id": "a"}, {"id": "b", "status": "changed", "final": True}],
        "transitions": [{"from": "a", "to": "b", "label": "閉じる"}, {"from": "b", "to": "b", "label": "再送"}]},
}


class SequenceAnnotationTest(unittest.TestCase):
    """注記・区間の枠・エラーで戻る線・参加者の 2 行目（#533）."""

    def test_definitions_without_new_keys_render_the_same_bytes_as_before(self):
        specs = list(UNCHANGED.values())
        rc, out, _, tmp = run(*specs)
        self.assertEqual(rc, 0, out)
        for i, expected in enumerate(UNCHANGED):
            with self.subTest(type=specs[i]["type"]):
                self.assertEqual(hashlib.sha256((tmp / f"d{i}.svg").read_bytes()).hexdigest(), expected)

    def test_note_sits_right_of_its_lifeline_without_reaching_the_next(self):
        text = "権限を確かめてから\nユースケースへ渡す"
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                          "steps": [{"from": "a", "to": "b"}, {"note": text, "at": "b"}, {"from": "b", "to": "c"}]})
        n = note(root)
        self.assertEqual(n.get("data-at"), "b")
        x0, _, x1, _ = rect_of(n)
        self.assertGreater(x0, center(root, "b")[0])
        self.assertLess(x1, center(root, "c")[0])
        # 全角 9 文字の行が収まる（1 文字 13px を下限に置く）
        self.assertGreaterEqual(x1 - x0, 9 * 13)
        self.assertEqual(text_of(n), text)

    def test_note_is_drawn_between_the_calls_around_it(self):
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}], "steps": [
            {"from": "a", "to": "b", "label": "前"}, {"note": "1 行目\n2 行目\n3 行目", "at": "a"},
            {"from": "b", "to": "a", "label": "後"}]})
        _, y0, _, y1 = rect_of(note(root))
        before, after = arrow_ys(root)
        self.assertGreater(y0, before)
        self.assertLess(y1, label_bg(root, "後")[1])
        self.assertLess(y1, after)

    def test_note_on_last_lifeline_stays_on_canvas(self):
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}],
                          "steps": [{"from": "a", "to": "b"}, {"note": "最後の参加者に付けた長い注記", "at": "b"}]})
        tx, _ = translate(root)
        self.assertLessEqual(rect_of(note(root))[2] + tx, float(root.get("width")))

    def test_frame_with_a_note_stops_before_the_next_lifeline(self):
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}, {"id": "c"}], "steps": [
            {"frame": "opt", "label": "c", "steps": [{"from": "a", "to": "b"},
                                                     {"note": "b の位置に置いた長い注記", "at": "b"}]},
            {"from": "b", "to": "c"}]})
        fr, nr = rect_of(groups(root, "frame")[0]), rect_of(note(root))
        lifelines = [p for p in root.iter(f"{NS}path") if p.get("class") == "lifeline"]
        life_c = path_points(lifelines[2].get("d"))[0][0]
        self.assertLess(nr[2], fr[2])
        self.assertLess(fr[2], life_c)

    def test_nested_frames_with_a_note_stop_before_the_next_lifeline(self):
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}, {"id": "c"}], "steps": [
            {"frame": "section", "label": "1. 受け付け", "steps": [
                {"frame": "opt", "label": "c", "steps": [{"from": "a", "to": "b"},
                                                         {"note": "b の位置に置いた長い注記", "at": "b"}]}]},
            {"from": "b", "to": "c"}]})
        lifelines = [p for p in root.iter(f"{NS}path") if p.get("class") == "lifeline"]
        life_c = path_points(lifelines[2].get("d"))[0][0]
        for frame in groups(root, "frame"):
            self.assertLess(rect_of(frame)[2], life_c, frame.get("data-kind"))

    def test_frames_widened_by_self_calls_or_long_text_stop_before_the_next_lifeline(self):
        cases = {
            "入れ子の自己呼び出し": [{"frame": "section", "label": "1. 受け付け", "steps": [
                {"frame": "opt", "label": "c", "steps": [
                    {"from": "a", "to": "b"}, {"from": "b", "to": "b", "label": "自分を呼ぶ長いラベルの処理"}]}]}],
            "長い cond": [{"frame": "section", "label": "1. 受け付け",
                           "cond": "利用者が送った申請を受け取り内容を確かめる", "steps": [{"from": "a", "to": "b"}]}],
            "長い label": [{"frame": "opt", "label": "利用者が送った申請を受け取ったときだけ",
                            "steps": [{"from": "a", "to": "b"}]}],
        }
        for name, steps in cases.items():
            with self.subTest(name):
                root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                                  "steps": steps + [{"from": "b", "to": "c"}]})
                lifelines = [p for p in root.iter(f"{NS}path") if p.get("class") == "lifeline"]
                life_c = path_points(lifelines[2].get("d"))[0][0]
                for frame in groups(root, "frame"):
                    self.assertLess(rect_of(frame)[2], life_c, frame.get("data-kind"))

    def test_frames_widening_two_columns_stop_before_the_next_lifelines(self):
        # 2 列を順に広げる回。広げた直後の丸めで同じ列を 2 度越えたと読むと、最後の列を広げた後に測り直さずに抜けていた
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}, {"id": "c"}], "steps": [
            {"frame": "opt", "label": "あ申WixiWx1申W申申ix1iabxababmabm申i申", "steps": [{"from": "b", "to": "b"}]},
            {"frame": "opt", "label": "x申abxab1mmmmiああmi", "steps": [{"from": "a", "to": "a"}]},
            {"from": "b", "to": "c"}]})
        lifelines = [path_points(p.get("d"))[0][0] for p in root.iter(f"{NS}path") if p.get("class") == "lifeline"]
        frames = groups(root, "frame")
        self.assertLess(rect_of(frames[0])[2], lifelines[2])
        self.assertLess(rect_of(frames[1])[2], lifelines[1])

    def test_widening_for_frames_leaves_exactly_the_margin(self):
        # 越えた枠ごとに足し合わせると、入れ子の外側の枠と次の生存線の間が必要以上に空く
        cases = {
            "入れ子": [{"frame": "section", "label": "1", "steps": [
                {"frame": "opt", "label": "利用者が送った申請を受け取ったときだけ", "steps": [{"from": "a", "to": "b"}]}]}],
            "続けて 2 つ": [
                {"frame": "opt", "label": "利用者が送った申請を受け取ったときだけ", "steps": [{"from": "a", "to": "b"}]},
                {"frame": "loop", "label": "申請に添付されたファイルの数だけ繰り返す", "steps": [{"from": "a", "to": "b"}]}],
        }
        for name, steps in cases.items():
            with self.subTest(name):
                root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                                  "steps": steps + [{"from": "b", "to": "c"}]})
                lifelines = [p for p in root.iter(f"{NS}path") if p.get("class") == "lifeline"]
                life_c = path_points(lifelines[2].get("d"))[0][0]
                right = max(rect_of(f)[2] for f in groups(root, "frame"))
                self.assertAlmostEqual(life_c - right, 4, delta=0.2)

    def test_frame_encloses_its_note(self):
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}], "steps": [
            {"frame": "opt", "label": "c", "steps": [{"from": "a", "to": "b"}, {"note": "枠の中の長い注記", "at": "b"}]}]})
        fr, nr = rect_of(groups(root, "frame")[0]), rect_of(note(root))
        self.assertTrue(fr[0] < nr[0] and nr[2] < fr[2] and fr[1] < nr[1] and nr[3] < fr[3], (fr, nr))

    def test_note_takes_status_colors_and_strikes_when_removed(self):
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}], "steps": [
            {"from": "a", "to": "b"}, {"note": "足した", "at": "a", "status": "added"},
            {"note": "消した", "at": "a", "status": "removed"}]})
        added, removed = note(root, 0), note(root, 1)
        self.assertEqual(added.find(f"{NS}rect").get("stroke"), "#1e8e3e")
        self.assertIsNone(added.find(f"{NS}text").get("text-decoration"))
        self.assertEqual(removed.find(f"{NS}text").get("text-decoration"), "line-through")

    def test_section_shows_its_label_on_the_tab_and_cond_without_brackets(self):
        cond = "画面から呼ぶときだけ通る"
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}], "steps": [
            {"frame": "section", "label": "1. 受け付け", "cond": cond, "steps": [{"from": "a", "to": "b"}]}]})
        frame = groups(root, "frame")[0]
        self.assertEqual(frame.get("data-kind"), "section")
        self.assertEqual(frame.get("data-label"), "1. 受け付け")
        texts = [text_of(t) for t in root.iter(f"{NS}text")]
        self.assertIn("1. 受け付け", texts)
        self.assertNotIn("section", texts)
        self.assertNotIn(f"[{cond}]", texts)
        bg = label_bg(root, cond)
        tab = next(p for p in root.iter(f"{NS}path") if p.get("class") == "frame-tab")
        self.assertGreater(bg[0], max(x for x, _ in path_points(tab.get("d"))))
        self.assertLessEqual(bg[2], rect_of(frame)[2])

    def test_error_return_is_a_red_dashed_line(self):
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}], "steps": [
            {"from": "a", "to": "b"}, {"from": "b", "to": "a", "label": "NotFound", "error": True}]})
        call, err = groups(root, "message")
        self.assertIsNone(call.get("data-error"))
        self.assertEqual(err.get("data-error"), "true")
        path = err.find(f"{NS}path")
        self.assertEqual(path.get("stroke"), "#d93025")
        self.assertEqual(path.get("stroke-dasharray"), "3 3")
        self.assertEqual(path.get("marker-end"), "url(#arrow-removed)")
        # 消した呼び出しと違い、ラベルに取り消し線を引かない
        label = next(t for t in root.iter(f"{NS}text") if text_of(t) == "NotFound")
        self.assertIsNone(label.get("text-decoration"))
        lines = groups(groups(root, "legend-row")[1], "legend-item")
        self.assertEqual([i.get("data-status") for i in lines], ["existing", "error"])
        self.assertEqual(text_of(lines[1]), "エラーで戻る")
        # 凡例の見本は図の中のエラーの線と同じ描き方
        sample = lines[1].find(f"{NS}path")
        self.assertEqual({k: sample.get(k) for k in ("stroke", "stroke-dasharray", "marker-end")},
                         {k: path.get(k) for k in ("stroke", "stroke-dasharray", "marker-end")})

    def test_error_return_differs_from_a_removed_reply(self):
        root, _ = render({"type": "sequence", "participants": [{"id": "a"}, {"id": "b"}], "steps": [
            {"from": "a", "to": "b"}, {"from": "b", "to": "a", "reply": True, "status": "removed"},
            {"from": "b", "to": "a", "error": True}]})
        removed_reply, err = (m.find(f"{NS}path") for m in groups(root, "message")[1:])
        self.assertEqual(removed_reply.get("stroke"), err.get("stroke"))
        self.assertNotEqual(removed_reply.get("stroke-dasharray"), err.get("stroke-dasharray"))

    def test_sublabel_is_a_smaller_grey_second_line_inside_the_header(self):
        root, _ = render({"type": "sequence", "participants": [
            {"id": "a", "label": "一覧画面", "sublabel": "app/items/page.tsx"}, {"id": "b", "label": "API"},
            {"id": "c", "label": "消す", "sublabel": "旧実装", "status": "removed"}],
            "steps": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}]})
        head = node(root, "a")
        x0, y0, x1, y1 = rect_of(head)
        name, sub = head.findall(f"{NS}text")
        self.assertEqual((text_of(name), text_of(sub)), ("一覧画面", "app/items/page.tsx"))
        # 2 行目があるときは 1 行目（役割）を太字にし、2 行目は太字にしない
        self.assertEqual((name.get("font-weight"), sub.get("font-weight")), ("bold", None))
        self.assertEqual(sub.get("font-size"), "12")
        self.assertEqual(sub.get("fill"), "#5f6368")
        sub_y, name_y = (float(t.find(f"{NS}tspan").get("y")) for t in (sub, name))
        self.assertTrue(y0 < name_y < sub_y < y1)
        self.assertGreaterEqual(x1 - x0, len("app/items/page.tsx") * 12 * 0.62)
        # 見出しの高さは揃い、2 行目の無い参加者は 1 行のまま
        self.assertEqual(rect_of(node(root, "b"))[3] - rect_of(node(root, "b"))[1], y1 - y0)
        self.assertEqual(len(node(root, "b").findall(f"{NS}text")), 1)
        self.assertEqual([t.get("text-decoration") for t in node(root, "c").findall(f"{NS}text")],
                         ["line-through", "line-through"])


CHAIN = {"type": "state", "initial": "a",
         "states": [{"id": "a", "label": "閉じている"}, {"id": "b", "label": "確認中"}, {"id": "c", "label": "送信中"}],
         "transitions": [{"from": "a", "to": "b", "label": "削除を押す"}, {"from": "b", "to": "a", "label": "キャンセル"},
                         {"from": "b", "to": "c", "label": "削除する"}, {"from": "c", "to": "a", "label": "閉じる"}]}


# 太字の幅の下限に使う。Hiragino Sans を Chrome で測った、太字と細字の幅の比の最大（英字。#567）
BOLD_MEASURED = 1.136


def tab_width(root: ET.Element, nth: int = 0) -> float:
    tabs = [p for p in root.iter(f"{NS}path") if p.get("class") == "frame-tab"]
    (x0, _), (x1, _) = path_points(tabs[nth].get("d"))[:2]
    return x1 - x0


class TitleAndLegendKeyTest(unittest.TestCase):
    """sequence の title の warn= と、型ごとに許す legend_labels のキー（#567）."""

    TITLE_WARN = "sequence に title が無い（何の流れかを title に書く）"

    def test_sequence_without_title_warns(self):
        for spec in (SEQ, {**SEQ, "title": ""}, {**SEQ, "title": " \u3000"}):
            with self.subTest(title=spec.get("title")):
                _, out = render(spec)
                self.assertEqual([w.split("\t", 1)[1] for w in out[1:] if "title" in w], [self.TITLE_WARN])

    def test_blank_title_is_not_drawn(self):
        root, _ = render({**SEQ, "title": " "})
        self.assertEqual(groups(root, "title"), [])

    def test_titled_sequence_and_untitled_flow_state_stay_quiet(self):
        for spec in (SEQ_TITLED,
                     {"type": "flow", "nodes": [{"id": "a"}, {"id": "b"}], "edges": [{"from": "a", "to": "b"}]},
                     {"type": "state", "states": [{"id": "a"}, {"id": "b"}],
                      "transitions": [{"from": "a", "to": "b"}]}):
            with self.subTest(type=spec["type"]):
                _, out = render(spec)
                self.assertEqual(out[1:], [])

    def test_reply_and_error_labels_fail_on_flow_and_state(self):
        flow = {"type": "flow", "nodes": [{"id": "a"}]}
        state = {"type": "state", "states": [{"id": "a"}]}
        statuses = "added / changed / removed / existing / later"
        cases = [({**flow, "legend_labels": {"reply": "返す"}}, f"flow の legend_labels のキーは {statuses}"),
                 ({**state, "legend_labels": {"error": "例外"}}, f"state の legend_labels のキーは {statuses}")]
        rc, out, _, tmp = run(*[c for c, _ in cases])
        self.assertEqual(rc, 1)
        for i, (_, message) in enumerate(cases):
            self.assertEqual(out[i], f"failed={tmp / f'd{i}.json'}\t{message}")
            self.assertFalse((tmp / f"d{i}.svg").exists())

    def test_sequence_keeps_reply_and_error_and_flow_keeps_statuses(self):
        rc, out, _, _ = run({**SEQ_TITLED, "legend_labels": {"reply": "返す", "error": "例外", "added": "足す"}},
                            {"type": "flow", "nodes": [{"id": "a", "status": "added"}],
                             "legend_labels": {"added": "足す"}})
        self.assertEqual(rc, 0, out)
        self.assertEqual([o.split("=", 1)[0] for o in out], ["svg", "svg"])


class BoldWidthTest(unittest.TestCase):
    """太字で描く文字の幅を、太字の見積もりで取る（#567）. 下限は細字の字幅 0.62em に実測の太字の比を掛けて組み、スクリプトの係数 BOLD_HALF は使わない."""

    LATIN = "abcdefghijklmn"  # 英小文字 14 字

    def test_participant_with_sublabel_widens_for_latin_bold(self):
        root, _ = render({"type": "sequence", "title": "t", "participants": [
            {"id": "a", "label": self.LATIN, "sublabel": "x"}, {"id": "b"}],
            "steps": [{"from": "a", "to": "b"}]})
        x0, _, x1, _ = rect_of(node(root, "a"))
        self.assertGreaterEqual(x1 - x0, len(self.LATIN) * 0.62 * 14 * BOLD_MEASURED + 2 * 12)

    def test_japanese_bold_keeps_its_width(self):
        # 和文は太字でも幅が変わらない。全角 9 字 × 14px と左右の余白 12px ちょうど
        root, _ = render({"type": "sequence", "title": "t", "participants": [
            {"id": "a", "label": "削除の受け付けの係", "sublabel": "x"}, {"id": "b"}],
            "steps": [{"from": "a", "to": "b"}]})
        x0, _, x1, _ = rect_of(node(root, "a"))
        self.assertAlmostEqual(x1 - x0, 9 * 14 + 2 * 12, delta=0.1)

    def test_frame_tab_widens_for_latin_and_not_for_japanese(self):
        root, _ = render({"type": "sequence", "title": "t", "participants": [{"id": "a"}, {"id": "b"}], "steps": [
            {"frame": "section", "label": self.LATIN, "steps": [{"from": "a", "to": "b"}]},
            {"frame": "section", "label": "入力の確認", "steps": [{"from": "b", "to": "a"}]}]})
        # 札は文字の左右に 8px ずつ
        self.assertGreaterEqual(tab_width(root, 0), len(self.LATIN) * 0.62 * 12 * BOLD_MEASURED + 16)
        self.assertAlmostEqual(tab_width(root, 1), 5 * 12 + 16, delta=0.1)

    def test_group_heading_widens_for_latin_bold(self):
        root, _ = render({"type": "flow", "nodes": [{"id": "a"}], "groups": [{"label": self.LATIN, "nodes": ["a"]}]})
        x0, _, x1, _ = rect_of(next(r for r in root.iter(f"{NS}rect") if r.get("class") == "group-heading"))
        # 白地は文字の左 4px から右 4px まで
        self.assertGreaterEqual(x1 - x0, len(self.LATIN) * 0.62 * 12 * BOLD_MEASURED + 8)

    def test_title_widens_the_canvas_for_latin_bold(self):
        title = "abcdefghij" * 6
        root, _ = render({"type": "flow", "title": title, "nodes": [{"id": "a"}]})
        self.assertGreaterEqual(int(root.get("width")), len(title) * 0.62 * 16 * BOLD_MEASURED + 2 * 24)


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

    def test_layers_start_from_nodes_without_incoming_edges(self):
        # 入る辺の無い r から辿る。定義の先頭の y から辿ると、y → x を前向きの辺に取って y が r と同じ層に来る
        root, _ = render({"type": "flow", "nodes": [{"id": "y"}, {"id": "x"}, {"id": "r"}],
                          "edges": [{"from": "r", "to": "x"}, {"from": "x", "to": "y"}, {"from": "y", "to": "x"}]})
        c = {i: center(root, i) for i in "rxy"}
        self.assertTrue(c["r"][0] < c["x"][0] < c["y"][0], c)

    def test_layer_is_ordered_by_position_of_predecessors(self):
        # 定義順（c1, c2）ではなく、前の層の親の並び（r1, r2）に合わせて c2 を上に置く（線が交差しない）
        root, _ = render({"type": "flow", "nodes": [{"id": "r1"}, {"id": "r2"}, {"id": "c1"}, {"id": "c2"}],
                          "edges": [{"from": "r1", "to": "c2"}, {"from": "r2", "to": "c1"}]})
        self.assertLess(center(root, "c2")[1], center(root, "c1")[1])

    def test_gaps_between_boxes(self):
        # 線のラベルが無ければ縦の間隔は 56
        root, _ = render({"type": "flow", "direction": "TB", "nodes": [{"id": "a"}, {"id": "b"}],
                          "edges": [{"from": "a", "to": "b"}]})
        self.assertAlmostEqual(rect_of(node(root, "b"))[1] - rect_of(node(root, "a"))[3], 56, delta=0.15)
        # 横の辺のラベルは、ラベルの白地の幅 + 24 の横の間隔を取る
        label = "とても長いラベル"
        root, _ = render({"type": "flow", "nodes": [{"id": "a"}, {"id": "b"}],
                          "edges": [{"from": "a", "to": "b", "label": label}]})
        bg = label_bg(root, label)
        self.assertAlmostEqual(rect_of(node(root, "b"))[0] - rect_of(node(root, "a"))[2], bg[2] - bg[0] + 24,
                               delta=0.15)
        # 横の辺の複数行のラベルは、縦の間隔を広げない
        root, _ = render({"type": "flow", "nodes": [{"id": "a", "pos": [0, 0]}, {"id": "b", "pos": [1, 0]},
                                                    {"id": "c", "pos": [0, 1]}],
                          "edges": [{"from": "a", "to": "b", "label": "一\n二\n三"}]})
        self.assertAlmostEqual(rect_of(node(root, "c"))[1] - rect_of(node(root, "a"))[3], 56, delta=0.15)

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
        # 範囲の枠を持つ図は層の中央寄せをしない（1 つだけの層も先頭の行に置く）
        self.assertEqual({center(root, m)[1] for m in ("src", "new", "agg")}, {center(root, "new")[1]})

    def test_group_frame_top_leaves_room_only_for_a_heading(self):
        for label, room in (("", 16), ("範囲", 40)):
            with self.subTest(label=label):
                root, _ = render({"type": "flow", "nodes": [{"id": "a"}], "groups": [{"label": label, "nodes": ["a"]}]})
                self.assertAlmostEqual(rect_of(node(root, "a"))[1] - rect_of(groups(root, "group")[0])[1], room,
                                       delta=0.15)

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


def lane(root: ET.Element, ident: str, direction: str) -> float:
    """層の中の位置（LR は箱の中心の y、TB は x）. 同じ行（TB は列）の箱は同じ値になる."""
    x, y = center(root, ident)
    return y if direction == "LR" else x


def banded(nodes: list[str], edges: list[tuple[str, str]], members: list[list[str]], direction: str = "LR") -> dict:
    return {"type": "flow", "direction": direction, "nodes": [{"id": i} for i in nodes],
            "edges": [{"from": a, "to": b} for a, b in edges],
            "groups": [{"nodes": m} for m in members]}


class GroupBandLayoutTest(unittest.TestCase):
    """自動配置で groups の枠ごとに行（TB は列）の帯を取る（#499）. 期待する行の関係は図ごとに手で決めた."""

    def assert_frames_hold_only_members(self, root: ET.Element, out: list[str], spec: dict) -> None:
        for gi, g in enumerate(spec["groups"]):
            frame_rect = rect_of(groups(root, "group")[gi])
            for nd in spec["nodes"]:
                if nd["id"] not in g["nodes"]:
                    self.assertFalse(overlap(rect_of(node(root, nd["id"])), frame_rect), (gi, nd["id"]))
        self.assertFalse([w for w in out if "メンバーでない" in w or "\t箱 " in w], out)

    def test_two_groups_sharing_a_layer_get_their_own_rows(self):
        nodes, edges = ["a0", "a1", "b1", "b2"], [("a0", "a1"), ("a0", "b1"), ("b1", "b2")]
        for direction in ("LR", "TB"):
            for first, second in ((["a0", "a1"], ["b1", "b2"]), (["b1", "b2"], ["a0", "a1"])):
                with self.subTest(direction=direction, first=first):
                    spec = banded(nodes, edges, [first, second], direction)
                    root, out = render(spec)
                    at = {i: lane(root, i, direction) for i in nodes}
                    self.assertAlmostEqual(at[first[0]], at[first[1]], delta=0.15)
                    self.assertAlmostEqual(at[second[0]], at[second[1]], delta=0.15)
                    # 先に書いた枠が上（TB は左）
                    self.assertLess(at[first[0]], at[second[0]])
                    self.assert_frames_hold_only_members(root, out, spec)

    def test_outsiders_keep_out_of_the_band_across_its_layers(self):
        # a0（層 0）と a2（層 2）の枠。w は層 0、x は層 1、z は層 2 にいる枠の外の箱
        nodes = ["a0", "w", "x", "a2", "z"]
        edges = [("a0", "x"), ("w", "x"), ("x", "a2"), ("x", "z")]
        for direction in ("LR", "TB"):
            with self.subTest(direction=direction):
                spec = banded(nodes, edges, [["a0", "a2"]], direction)
                root, out = render(spec)
                at = {i: lane(root, i, direction) for i in nodes}
                self.assertAlmostEqual(at["a0"], at["a2"], delta=0.15)
                for i in ("w", "x", "z"):
                    self.assertGreater(at[i], at["a0"], i)
                self.assert_frames_hold_only_members(root, out, spec)

    def test_later_group_moves_back_up_where_the_rows_are_free(self):
        # A は層 0、B は層 0〜1 で A の下。C は層 1 だけなので、A と同じ行に戻れる
        spec = banded(["a", "b0", "b1", "c"], [("a", "c"), ("b0", "b1")], [["a"], ["b0", "b1"], ["c"]])
        root, out = render(spec)
        at = {i: lane(root, i, "LR") for i in ("a", "b0", "b1", "c")}
        self.assertAlmostEqual(at["c"], at["a"], delta=0.15)
        self.assertAlmostEqual(at["b1"], at["b0"], delta=0.15)
        self.assertGreater(at["b0"], at["a"])
        self.assert_frames_hold_only_members(root, out, spec)

    def test_bands_leave_no_empty_row_between_them(self):
        spec = banded(["a0", "a1", "b"], [], [["a0", "a1"], ["b"]])
        root, out = render(spec)
        at = {i: lane(root, i, "LR") for i in ("a0", "a1", "b")}
        self.assertGreater(at["a1"], at["a0"])
        self.assertAlmostEqual(at["b"] - at["a1"], at["a1"] - at["a0"], delta=0.15)
        self.assert_frames_hold_only_members(root, out, spec)

    def test_groups_on_separate_layers_share_a_row(self):
        spec = banded(["a", "x", "b"], [("a", "x"), ("x", "b")], [["a"], ["b"]])
        root, out = render(spec)
        self.assertAlmostEqual(lane(root, "a", "LR"), lane(root, "b", "LR"), delta=0.15)
        self.assert_frames_hold_only_members(root, out, spec)

    def test_third_group_goes_below_both_bands(self):
        spec = banded(["a", "b", "c"], [], [["a"], ["b"], ["c"]])
        root, out = render(spec)
        at = [lane(root, i, "LR") for i in ("a", "b", "c")]
        self.assertLess(at[0], at[1])
        self.assertLess(at[1], at[2])
        self.assert_frames_hold_only_members(root, out, spec)


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
        # 縦の線は見出しの下を通る（LayoutShapeTest が warn を見る）。ここで見るのはラベルが見出しを避けることだけ
        self.assertEqual([w.split("\t", 1)[1] for w in out[1:]],
                         ["edges の 'src' → 'f' が groups[0] の見出しの下を通る（pos で並べ直すか、見出しを短くする）"])
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

    def test_initial_marker_moves_off_a_neighbouring_box(self):
        # 左隣の箱 x が近く、左に置いた黒丸が x に乗る。上へ逃がす（離れた z は、黒丸を全部の箱と比べる変異 any → all を落とすために置く）
        root, out = render({"type": "state", "initial": "a",
                            "states": [{"id": "x", "pos": [0, 0]}, {"id": "a", "pos": [0.6, 0]},
                                       {"id": "z", "pos": [3, 0]}]})
        self.assertEqual(len(out), 1, out)
        circle = groups(root, "initial")[0].find(f"{NS}circle")
        ra = rect_of(node(root, "a"))
        self.assertLess(float(circle.get("cy")), ra[1])
        self.assertTrue(ra[0] < float(circle.get("cx")) < ra[2])


def chain(n: int, direction: str = "LR") -> dict:
    return {"type": "flow", "direction": direction, "nodes": [{"id": f"n{i}"} for i in range(n)],
            "edges": [{"from": f"n{i}", "to": f"n{i + 1}"} for i in range(n - 1)]}


def shape_warns(out: list[str], fragment: str) -> list[str]:
    return [w.split("\t", 1)[1] for w in out if w.startswith("warn=") and fragment in w]


X_NODES = [{"id": "a", "pos": [0, 0]}, {"id": "d", "pos": [1, 0]}, {"id": "c", "pos": [0, 1]}, {"id": "b", "pos": [1, 1]}]


class LayoutShapeTest(unittest.TestCase):
    """縦横比・線どうしの交差・線と枠の見出しの重なり（GitHub issue #452）."""

    def test_tall_graph_warns_only_past_400px(self):
        # 縦 4 段は高さ 359 で下限 400 に届かない。5 段で 450 を超え、幅 144 より高い
        root, out = render(chain(5, "TB"))
        self.assertGreater(int(root.get("height")), 400)
        self.assertEqual(shape_warns(out, "縦長"),
                         [f"高さ {root.get('height')}px が幅 144px を超えた縦長の図（direction を LR にするか、"
                          "pos で横に並べる）"])
        root, out = render(chain(4, "TB"))
        self.assertGreater(int(root.get("height")), int(root.get("width")))
        self.assertEqual(shape_warns(out, "縦長"), [])

    def test_wide_graph_warns_only_past_880px(self):
        # 横 5 個は幅 816 で、比率が 9 を超えても本文の幅 880 に収まるので縮まない。6 個で 984 になる
        root, out = render(chain(6))
        self.assertEqual(shape_warns(out, "横長"),
                         [f"幅 {root.get('width')}px が高さ 84px の 3.5 倍を超えた横長の図（PR の本文の幅 880 に"
                          "縮むと文字が小さくなる。direction を TB にするか、pos で 2 段に折り返す）"])
        root, out = render(chain(5))
        self.assertLess(int(root.get("width")), 880)
        self.assertEqual(shape_warns(out, "横長"), [])

    def test_wide_graph_within_ratio_does_not_warn(self):
        # 幅 880 超でも高さが幅の 1/3.5 以上あれば出さない（横 6 個の 3 行下にもう 1 個）
        nodes = [{"id": f"n{i}", "pos": [i % 6, 0 if i < 6 else 3]} for i in range(7)]
        root, out = render({"type": "flow", "nodes": nodes, "edges": []})
        width, height = int(root.get("width")), int(root.get("height"))
        self.assertGreater(width, 880)
        self.assertLessEqual(width, 3.5 * height)
        self.assertEqual(shape_warns(out, "横長"), [])

    def test_suggested_direction_is_the_opposite_and_dropped_with_pos(self):
        # LR のまま 1 つの層に 6 個並ぶと縦長になる。勧めるのは今の LR ではなく TB
        fan = {"type": "flow", "nodes": [{"id": "a"}] + [{"id": f"c{i}"} for i in range(6)],
               "edges": [{"from": "a", "to": f"c{i}"} for i in range(6)]}
        _, out = render(fan)
        self.assertEqual(len(shape_warns(out, "縦長")), 1, out)
        self.assertIn("（direction を TB にするか、pos で横に並べる）", shape_warns(out, "縦長")[0])
        # pos を全部に付けると direction は効かないので、pos だけを挙げる
        _, out = render({"type": "flow", "direction": "LR", "nodes": [{"id": f"n{i}", "pos": [0, i]} for i in range(5)],
                         "edges": []})
        self.assertEqual(len(shape_warns(out, "縦長")), 1, out)
        self.assertIn("（pos で横に並べる）", shape_warns(out, "縦長")[0])

    def test_state_is_checked_but_sequence_is_not(self):
        root, out = render({"type": "state", "states": [{"id": f"s{i}", "pos": [0, i]} for i in range(5)],
                            "transitions": [{"from": f"s{i}", "to": f"s{i + 1}"} for i in range(4)]})
        # state は direction を持たない（書くと failed=）ので、直し方に pos だけを挙げる
        self.assertEqual(shape_warns(out, "縦長"),
                         [f"高さ {root.get('height')}px が幅 {root.get('width')}px を超えた縦長の図（pos で横に並べる）"])
        root, out = render({"type": "sequence", "title": "縦に長い流れ", "participants": [{"id": "a"}, {"id": "b"}],
                            "steps": [{"from": "a", "to": "b", "label": "x"}] * 12})
        self.assertGreater(int(root.get("height")), max(int(root.get("width")), 400))
        self.assertEqual(out[1:], [])

    def test_crossing_edges_warn(self):
        _, out = render({"type": "flow", "nodes": X_NODES,
                         "edges": [{"from": "a", "to": "b"}, {"from": "c", "to": "d"}]})
        self.assertEqual(shape_warns(out, "交差"),
                         ["edges の 'a' → 'b' と edges の 'c' → 'd' が交差する（pos で並べ直す）"])

    def test_same_crossing_is_reported_once(self):
        # a → b が 2 本あっても、c → d との交差の理由は同じ文言なので 1 行にまとめる
        _, out = render({"type": "flow", "nodes": X_NODES,
                         "edges": [{"from": "a", "to": "b"}, {"from": "a", "to": "b"}, {"from": "c", "to": "d"}]})
        self.assertEqual(len(shape_warns(out, "交差")), 1, out)

    def test_crossing_off_the_sample_points_also_warns(self):
        # 上の X 字は 2 本が中央の標本点で交わる。こちらは標本点の間で交わる
        nodes = [{"id": "a", "pos": [0, 0]}, {"id": "d", "pos": [2, 0]}, {"id": "c", "pos": [0, 2]},
                 {"id": "b", "pos": [3, 1]}]
        _, out = render({"type": "flow", "nodes": nodes, "edges": [{"from": "a", "to": "b"}, {"from": "c", "to": "d"}]})
        self.assertEqual(len(shape_warns(out, "交差")), 1, out)

    def test_parallel_edges_and_edges_sharing_a_box_do_not_warn(self):
        _, out = render({"type": "flow", "nodes": X_NODES,
                         "edges": [{"from": "a", "to": "d"}, {"from": "c", "to": "b"}, {"from": "a", "to": "b"},
                                   {"from": "b", "to": "a"}]})
        self.assertEqual(shape_warns(out, "交差"), [])

    def test_curved_edge_meeting_another_edge_at_their_shared_box_does_not_warn(self):
        # a → c は間の b を避けて d の側へ曲がり、c の手前で d → c と交わる。どちらも c に入る線なので数えない
        nodes = [{"id": "a", "pos": [0, 0]}, {"id": "b", "pos": [1, 0]}, {"id": "c", "pos": [2, 0]},
                 {"id": "d", "pos": [1, 1]}]
        root, out = render({"type": "flow", "nodes": nodes,
                            "edges": [{"from": "a", "to": "c"}, {"from": "d", "to": "c"}]})
        self.assertNotEqual(edge(root, "a", "c").get("data-route"), "straight")
        self.assertEqual(shape_warns(out, "交差"), [])

    def test_edge_under_group_heading_warns_and_short_heading_does_not(self):
        def spec(label):
            return {"type": "flow", "direction": "TB", "nodes": [{"id": "src"}, {"id": "f"}],
                    "edges": [{"from": "src", "to": "f"}], "groups": [{"label": label, "nodes": ["f"]}]}

        _, out = render(spec("レビューで見てほしい範囲"))
        self.assertEqual(shape_warns(out, "見出し"),
                         ["edges の 'src' → 'f' が groups[0] の見出しの下を通る（pos で並べ直すか、見出しを短くする）"])
        _, out = render(spec("範囲"))
        self.assertEqual(out[1:], [])

    def test_self_loop_under_group_heading_warns(self):
        # 2 本目の輪は 60px 張り出し、長い見出しの白地に届く
        _, out = render({"type": "flow", "nodes": [{"id": "x"}],
                         "edges": [{"from": "x", "to": "x"}, {"from": "x", "to": "x"}],
                         "groups": [{"label": "レビューで見てほしい範囲とその周辺", "nodes": ["x"]}]})
        self.assertEqual(shape_warns(out, "見出し"),
                         ["edges の 'x' → 'x' が groups[0] の見出しの下を通る（pos で並べ直すか、見出しを短くする）"])


class GeometryBoundaryTest(unittest.TestCase):
    """点・矩形の判定は境界ちょうどを含めない（辺上の点は内側でない・辺が接するだけの箱は重ならない）.
    線分は端が相手の線に乗っても交わるとし、同じ直線の上に並ぶ 2 本は交わらないとする.

    境界ちょうどの配置は定義（CLI）から作れないので、このクラスだけ関数を直接読み込んで呼ぶ.
    """

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("_diagram_svg_under_test", SCRIPT)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def test_point_on_border_is_not_inside(self):
        self.assertFalse(self.mod.inside((0, 5), (0, 0, 10, 10)))
        self.assertFalse(self.mod.inside((-4, 5), (0, 0, 10, 10), 4))
        self.assertTrue(self.mod.inside((0.1, 5), (0, 0, 10, 10)))

    def test_touching_rects_do_not_overlap(self):
        self.assertFalse(self.mod.overlap((10, 0, 20, 10), (0, 0, 10, 10)))
        self.assertFalse(self.mod.overlap((0, 0, 10, 10), (10, 0, 20, 10)))
        self.assertTrue(self.mod.overlap((9.9, 0, 20, 10), (0, 0, 10, 10)))

    def test_segment_ending_on_another_line_crosses_it_from_either_side(self):
        # T 字の接触: 縦の線の端が横の線の上に乗る。残りの端が横の線の上側・下側のどちらでも交わる
        self.assertTrue(self.mod.crosses((0, 0), (10, 0), (5, 0), (5, 5)))
        self.assertTrue(self.mod.crosses((0, 0), (10, 0), (5, 0), (5, -5)))
        self.assertTrue(self.mod.crosses((0, 0), (10, 0), (5, 5), (5, 0)))
        self.assertFalse(self.mod.crosses((0, 0), (10, 0), (5, 1), (5, 5)))

    def test_segments_on_the_same_line_do_not_cross(self):
        self.assertFalse(self.mod.crosses((0, 0), (10, 0), (5, 0), (15, 0)))
        self.assertFalse(self.mod.crosses((0, 0), (1, 0), (5, 0), (6, 0)))

    def test_polyline_through_rect_by_vertex_or_by_crossing(self):
        r = (0, 0, 10, 10)
        # 頂点がすべて内側で、辺は横切らない
        self.assertTrue(self.mod.through([(2, 2), (8, 8)], r))
        # 両端は外で、途中で矩形を突き抜ける
        self.assertTrue(self.mod.through([(-5, 5), (15, 5)], r))
        self.assertFalse(self.mod.through([(-5, -5), (15, -5)], r))

    def test_shape_warns_only_past_the_limit(self):
        # 上限を図の寸法ちょうどに置くと黙り、1 つ下げると出す
        svg, width, _ = self.mod.render(chain(5, "TB"))
        height = int(re.search(r'height="(\d+)"', svg).group(1))
        self.assertGreater(height, width)
        with mock.patch.object(self.mod, "TALL_MIN", height):
            self.assertEqual([w for w in self.mod.render(chain(5, "TB"))[2] if "縦長" in w], [])
        with mock.patch.object(self.mod, "TALL_MIN", height - 1):
            self.assertEqual(len([w for w in self.mod.render(chain(5, "TB"))[2] if "縦長" in w]), 1)
        _, width, _ = self.mod.render(chain(6))
        with mock.patch.object(self.mod, "GITHUB_WIDTH", width):
            self.assertEqual([w for w in self.mod.render(chain(6))[2] if "横長" in w], [])
        with mock.patch.object(self.mod, "GITHUB_WIDTH", width - 1):
            self.assertEqual(len([w for w in self.mod.render(chain(6))[2] if "横長" in w]), 1)


# スクリプトが定義に依らず描く語（既定の凡例名・凡例の段見出し・枠の種類の札）。スクリプトの定数を読まずに書く
FIXED_TEXTS = {"この PR で足した", "この PR で変えた", "この PR で消した", "既存", "後続の PR", "返り値", "エラーで戻る",
               "部品", "呼び出し", "alt", "opt", "loop"}
# 値が定義から来ない data-* の属性（status・枠の種類・凡例の段・エラーの印・線の引き方）
ENUM_ATTRS = {"data-status", "data-kind", "data-row", "data-error", "data-route"}

TEXTS_FLOW = {
    "type": "flow", "title": "注文の集計",
    "legend_labels": {"added": "足した処理", "removed": "使わない凡例"},
    "nodes": [{"id": "src", "label": "注文テーブル"}, {"id": "agg", "label": "今月に絞る\n集計", "status": "added"},
              {"id": "out"}],
    "edges": [{"from": "src", "to": "agg", "label": "読む"}, {"from": "agg", "to": "out"}],
    "groups": [{"label": "レビュー範囲", "nodes": ["agg"], "status": "added"}, {"nodes": ["out"]}],
}
TEXTS_FLOW_EXPECTED = [
    ("groups[0].label", "レビュー範囲"),
    ("nodes[0].id", "src"), ("nodes[0].label", "注文テーブル"),
    ("nodes[1].id", "agg"), ("nodes[1].label", "今月に絞る\\n集計"),
    ("nodes[2].id", "out"),
    ("edges[0].label", "読む"),
    ("legend_labels.added", "足した処理"),
    ("title", "注文の集計"),
]
TEXTS_STATE = {
    "type": "state", "initial": "closed",
    "states": [{"id": "closed", "label": "閉じている"}, {"id": "open", "label": "確認中", "status": "changed"},
               {"id": "done", "label": "完了", "final": True}],
    "transitions": [{"from": "closed", "to": "open", "label": "開く"}, {"from": "open", "to": "open", "label": "待つ"},
                    {"from": "open", "to": "done", "label": "送る", "status": "added"}],
}
TEXTS_STATE_EXPECTED = [
    ("states[0].id", "closed"), ("states[0].label", "閉じている"),
    ("states[1].id", "open"), ("states[1].label", "確認中"),
    ("states[2].id", "done"), ("states[2].label", "完了"),
    ("transitions[1].label", "待つ"),
    ("transitions[0].label", "開く"), ("transitions[2].label", "送る"),
]
TEXTS_SEQ = {
    "type": "sequence", "title": "削除の流れ",
    "legend_labels": {"reply": "戻り", "changed": "直した", "error": "失敗で戻る"},
    "participants": [{"id": "ui", "label": "画面", "sublabel": "ItemPage"}, {"id": "api", "status": "changed"},
                     {"id": "db", "label": "保存先", "sublabel": ""}],
    "steps": [
        {"from": "ui", "to": "api", "label": "del(id)"},
        {"note": "権限を\n確かめる", "at": "api"},
        {"frame": "alt", "branches": [
            {"label": "ある", "steps": [{"from": "api", "to": "db", "label": "softDelete"},
                                       {"from": "api", "to": "ui", "label": "ok", "reply": True, "status": "changed"}]},
            {"label": "ない", "steps": [{"from": "api", "to": "ui", "error": True}]}]},
        {"frame": "opt", "label": "一覧を開いている", "steps": [{"from": "ui", "to": "ui", "label": "再読込"}]},
        {"frame": "section", "label": "後片付け", "cond": "毎回", "steps": [{"from": "api", "to": "db", "label": ""}]},
    ],
}
TEXTS_SEQ_EXPECTED = [
    ("steps[0].label", "del(id)"),
    ("steps[1].note", "権限を\\n確かめる"),
    ("steps[2].branches[0].steps[0].label", "softDelete"),
    ("steps[2].branches[0].steps[1].label", "ok"),
    ("steps[2].branches[0].label", "ある"), ("steps[2].branches[1].label", "ない"),
    ("steps[3].steps[0].label", "再読込"),
    ("steps[3].label", "一覧を開いている"),
    ("steps[4].label", "後片付け"), ("steps[4].cond", "毎回"),
    ("participants[0].id", "ui"), ("participants[0].label", "画面"), ("participants[0].sublabel", "ItemPage"),
    ("participants[1].id", "api"),
    ("participants[2].id", "db"), ("participants[2].label", "保存先"),
    ("legend_labels.changed", "直した"), ("legend_labels.reply", "戻り"), ("legend_labels.error", "失敗で戻る"),
    ("title", "削除の流れ"),
]


def svg_strings(root: ET.Element) -> set[str]:
    """描いた SVG に出る、定義から来うる文字（枠の条件の [ ] と、凡例の「返り値（status）」は分けて数える）."""
    found: set[str] = set()
    legend_texts = {id(t) for g in groups(root, "legend-item") for t in g.iter(f"{NS}text")}
    for t in root.iter(f"{NS}text"):
        s = text_of(t)
        m = re.fullmatch(r"\[(.*)\]", s, re.S)
        if m:
            found.add(m.group(1))
            continue
        m = re.fullmatch(r"(.+)（(.+)）", s, re.S)
        if m and id(t) in legend_texts:
            found.update(m.groups())
            continue
        found.add(s)
    for el in root.iter():
        for k, v in el.attrib.items():
            if k.startswith("data-") and k not in ENUM_ATTRS:
                found.add(v)
    return found - FIXED_TEXTS


class TextsListTest(unittest.TestCase):
    def texts(self, spec: dict) -> list[tuple[str, str]]:
        rc, out, err, tmp = run(spec, flags=("--texts",))
        self.assertEqual(rc, 0, f"out={out} err={err}")
        self.assertEqual(sorted(p.name for p in tmp.iterdir()), ["d0.json"])  # .svg を書かない
        rows = []
        for line in out:
            head, where, s = line.split("\t")
            self.assertEqual(head, f"text={tmp / 'd0.json'}")
            rows.append((where, s))
        return rows

    def assert_matches_svg(self, spec: dict, expected: list[tuple[str, str]]) -> None:
        # 並びは描いた順で、定義の順とは限らない（state の自己ループのラベルは他の線より先に描く）
        self.assertCountEqual(self.texts(spec), expected)
        root, _ = render(spec)
        self.assertEqual(svg_strings(root), {s.replace("\\n", "\n") for _, s in expected})

    def test_flow_lists_labels_ids_group_heading_used_legend_label_and_title(self):
        # 使わない status の legend_labels（removed）・ラベルの無い線・見出しの無い枠は描かないので出さない
        self.assert_matches_svg(TEXTS_FLOW, TEXTS_FLOW_EXPECTED)

    def test_state_lists_states_and_transition_labels(self):
        self.assert_matches_svg(TEXTS_STATE, TEXTS_STATE_EXPECTED)

    def test_sequence_lists_notes_sublabels_frame_conditions_and_legend_labels(self):
        # 空の sublabel と空の label は描かないので出さない。枠の種類（alt / opt）は定義の値ではないので出さない
        self.assert_matches_svg(TEXTS_SEQ, TEXTS_SEQ_EXPECTED)

    def test_legend_off_drops_legend_labels(self):
        spec = {**TEXTS_FLOW, "legend": False}
        self.assert_matches_svg(spec, [r for r in TEXTS_FLOW_EXPECTED if not r[0].startswith("legend_labels.")])

    def test_tab_and_carriage_return_in_value_stay_on_one_line(self):
        rows = self.texts({"type": "flow", "nodes": [{"id": "a", "label": "x\ty"}, {"id": "b", "label": "p\rq"}]})
        self.assertEqual(rows, [("nodes[0].id", "a"), ("nodes[0].label", "x\\ty"),
                                ("nodes[1].id", "b"), ("nodes[1].label", "p\\rq")])

    def test_failures_and_usage_follow_the_normal_contract(self):
        rc, out, _, tmp = run("{broken", TEXTS_STATE, flags=("--texts",))
        self.assertEqual(rc, 1)
        self.assertTrue(out[0].startswith(f"failed={tmp / 'd0.json'}\tJSON として読めない"))
        self.assertTrue(all(line.startswith(f"text={tmp / 'd1.json'}\t") for line in out[1:]))
        self.assertFalse(list(tmp.glob("*.svg")))
        proc = subprocess.run([sys.executable, str(SCRIPT), "--texts"], capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage", proc.stderr)


if __name__ == "__main__":
    unittest.main()
