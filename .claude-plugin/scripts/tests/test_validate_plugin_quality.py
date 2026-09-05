#!/usr/bin/env python3
"""validate_plugin_quality.py の決定的ロジックに対する回帰テスト.

**なぜこのファイルがあるか（v2.63.1 の失敗から）**

SSoT pin 機構は「消費サイトの pin」と「正本の実ハッシュ」を突合するが、
**pin の初期値も同じ `_slice_section` で生成する**。つまり切り出しが壊れていても
pin と検証が自己整合し、全 pin が `ok` に見える。実際 v2.63.1 の初稿では
`_slice_section` がフェンス付きコードブロックを認識せず、bash 片のコメント行
（`# ...`）を見出しと誤検出して節を途中で打ち切っていた
（`orchestration-measurement.md ## 16` は 156 行中 85 行しかハッシュされず、
両 SKILL の payload 契約の 46% が無保護だった）にもかかわらず、
実リポジトリに対する検証は 14 pin すべて pass していた。

したがってこのテストの要件は「実装を実装で確かめない」こと:
**期待値は `_slice_section` を呼ばずにテスト側で独立に構築する**
（`test_digest_matches_independently_computed_expectation` がその核）。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import hashlib
import json
import importlib.util
import sys
import tempfile
import textwrap
import os
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "validate_plugin_quality.py"
Q = '"' * 3   # fixture 内に docstring を書くための三重引用符（入れ子を避ける）


def _load_module():
    spec = importlib.util.spec_from_file_location("_vpq_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v = _load_module()


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    return path


class SliceSectionTest(unittest.TestCase):
    """節の切り出し（`_slice_section`）."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_fenced_bash_comment_is_not_a_heading(self):
        """フェンス内の `# ...` で節が打ち切られない（v2.63.1 の実バグの回帰テスト）."""
        doc = _write(
            self.root,
            "canon.md",
            """
            # Title

            ## 5. reviewer 起動

            前半の説明。

            ```bash
            # ローカルに同名ブランチが無い場合があるので origin 側を先に試す
            git show "origin/$BASE:$FILE"
            ```

            後半の説明（フェンスより後ろ）。

            ## 8. 次の節

            ここは含まれない。
            """,
        )
        section = v._slice_section(doc, "5")
        self.assertIn("前半の説明。", section)
        self.assertIn("後半の説明（フェンスより後ろ）。", section)
        self.assertNotIn("ここは含まれない。", section)

    def test_tilde_fence_is_also_tracked(self):
        doc = _write(
            self.root,
            "canon.md",
            """
            ## 1. 節

            ~~~sh
            # コメント
            ~~~

            末尾。

            ## 2. 次
            """,
        )
        self.assertIn("末尾。", v._slice_section(doc, "1"))

    def test_longer_fence_is_not_closed_by_shorter_one(self):
        """````  で開いたフェンスは ``` では閉じない（ネストしたコードブロックの表記）."""
        doc = _write(
            self.root,
            "canon.md",
            """
            ## 1. 節

            ````md
            ```bash
            # 内側のコメント
            ```
            ````

            末尾。

            ## 2. 次
            """,
        )
        section = v._slice_section(doc, "1")
        self.assertIn("末尾。", section)
        self.assertNotIn("## 2.", section)

    def test_anchor_requires_a_delimiter_after_it(self):
        """anchor `1` が `13.` に当たらない（前方一致の暴発防止）."""
        doc = _write(
            self.root,
            "canon.md",
            """
            ## 13. 先に出てくる節

            thirteen

            ## 1. 本命の節

            one
            """,
        )
        section = v._slice_section(doc, "1")
        self.assertIn("one", section)
        self.assertNotIn("thirteen", section)

    def test_sibling_subsection_is_not_included(self):
        """`#8` は同レベルの `## 8.5` を含まない（仕様。含めたいなら別 pin）."""
        doc = _write(
            self.root,
            "canon.md",
            """
            ## 8. 本体

            eight

            ## 8.5. 兄弟

            eight-and-a-half
            """,
        )
        self.assertNotIn("eight-and-a-half", v._slice_section(doc, "8"))
        self.assertIn("eight-and-a-half", v._slice_section(doc, "8.5"))

    def test_nested_deeper_heading_stays_inside(self):
        """より深いレベルの見出しは節の内側に留まる."""
        doc = _write(
            self.root,
            "canon.md",
            """
            ## 7. 本体

            seven

            ### 7.1 子

            child

            ## 8. 次
            """,
        )
        section = v._slice_section(doc, "7")
        self.assertIn("child", section)
        self.assertNotIn("## 8.", section)

    def test_anchor_does_not_stick_to_a_deeper_sibling(self):
        """`## 8.` が無い文書で anchor `8` が `## 8.5.` へ黙って吸着しない.

        吸着すると `#8` と `#8.5` が同一節をハッシュし, 打ち直しで「pin は ok なのに
        `## 8.` 本体は無保護」が恒久化する（v2.63.1 と同型の自己整合の盲点）.
        """
        doc = _write(
            self.root,
            "canon.md",
            """
            ## 2. two

            two

            ## 8.5. 兄弟だけがある

            eight-and-a-half
            """,
        )
        self.assertIsNone(v._slice_section(doc, "8"))
        self.assertIn("eight-and-a-half", v._slice_section(doc, "8.5"))

    def test_ambiguous_anchor_returns_none(self):
        """同一 anchor に一致する見出しが 2 件あれば, 先頭を黙って採らず None を返す."""
        doc = _write(
            self.root,
            "canon.md",
            """
            ## 3.5. 対象の節

            first

            ## 3.5. 同名の節

            second
            """,
        )
        self.assertIsNone(v._slice_section(doc, "3.5"))

    def test_anchor_none_returns_whole_file(self):
        doc = _write(self.root, "canon.md", "# A\n\nbody\n\n## B\n\nmore\n")
        section = v._slice_section(doc, None)
        self.assertIn("body", section)
        self.assertIn("more", section)

    def test_unknown_anchor_returns_none(self):
        doc = _write(self.root, "canon.md", "## 1. あ\n\nx\n")
        self.assertIsNone(v._slice_section(doc, "99"))


class NormalizeSectionTest(unittest.TestCase):
    def test_absorbs_trailing_whitespace_and_edge_blank_lines(self):
        self.assertEqual(
            v._normalize_section("\n\n  a  \nb\t\n\n\n"),
            v._normalize_section("  a\nb"),
        )

    def test_does_not_absorb_interior_blank_lines(self):
        self.assertNotEqual(v._normalize_section("a\n\nb"), v._normalize_section("a\nb"))


class PinRegexTest(unittest.TestCase):
    def test_parses_with_and_without_anchor(self):
        m = v.SSOT_PIN_RE.search("<!-- SSOT: a/b.md#3.5 @deadbeef -->")
        self.assertEqual((m.group("path"), m.group("anchor"), m.group("hash")), ("a/b.md", "3.5", "deadbeef"))
        m = v.SSOT_PIN_RE.search("<!-- SSOT: a/b.md @deadbeef -->")
        self.assertEqual((m.group("path"), m.group("anchor")), ("a/b.md", None))

    def test_does_not_match_documentation_placeholder(self):
        """doc が書式を説明する `@<hash8>` を pin として拾わない."""
        self.assertIsNone(v.SSOT_PIN_RE.search("`<!-- SSOT: <path>#<anchor> @<hash8> -->` を置く"))


class CheckSsotPinsTest(unittest.TestCase):
    """pin 突合の end-to-end（`ROOT` を一時ディレクトリへ差し替える）."""

    CANON = """
        # 正本

        ## 3.5. 対象の節

        本文の前半。

        ```bash
        # フェンス内のコメント
        echo hi
        ```

        本文の後半。

        ## 4. 別の節

        無関係。
        """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self._orig_root = v.ROOT
        v.ROOT = self.root
        self.addCleanup(lambda: setattr(v, "ROOT", self._orig_root))
        self.canon = _write(self.root, "canon.md", self.CANON)

    def _consumer(self, pin_hash: str, anchor: str = "#3.5", canon: str = "canon.md") -> Path:
        return _write(self.root, "consumer.md", f"# 消費サイト\n\n<!-- SSOT: {canon}{anchor} @{pin_hash} -->\n")

    def test_digest_matches_independently_computed_expectation(self):
        """期待ハッシュを `_slice_section` を使わずに構築する.

        生成と検証が同じ関数を共有する自己整合の盲点（v2.63.1）を塞ぐ要のテスト。
        ここだけは実装の出力を期待値にしないこと。
        """
        expected_section = "\n".join(
            [
                "## 3.5. 対象の節",
                "",
                "本文の前半。",
                "",
                "```bash",
                "# フェンス内のコメント",
                "echo hi",
                "```",
                "",
                "本文の後半。",
            ]
        )
        expected = hashlib.sha256(expected_section.encode("utf-8")).hexdigest()[: v.SSOT_PIN_LEN]
        self.assertEqual(v._canonical_digest(self.canon, "3.5"), expected)

    def test_matching_pin_produces_no_error(self):
        self._consumer(v._canonical_digest(self.canon, "3.5"))
        errors: list[str] = []
        v.check_ssot_pins(errors)
        self.assertEqual(errors, [])

    def test_stale_pin_is_reported(self):
        self._consumer("00000000")
        errors: list[str] = []
        v.check_ssot_pins(errors)
        self.assertEqual(len(errors), 1)
        self.assertIn("[ssot-pin]", errors[0])

    def test_edit_after_fenced_block_is_detected(self):
        """フェンスより後ろの編集が pin を発火させる（無保護区間を作らない）."""
        self._consumer(v._canonical_digest(self.canon, "3.5"))
        self.canon.write_text(self.canon.read_text().replace("本文の後半。", "本文の後半（改）。"), encoding="utf-8")
        errors: list[str] = []
        v.check_ssot_pins(errors)
        self.assertEqual(len(errors), 1)

    def test_edit_in_unrelated_section_is_not_detected(self):
        """節単位のスコープ: 無関係な節の編集では発火しない."""
        self._consumer(v._canonical_digest(self.canon, "3.5"))
        self.canon.write_text(self.canon.read_text().replace("無関係。", "無関係（改）。"), encoding="utf-8")
        errors: list[str] = []
        v.check_ssot_pins(errors)
        self.assertEqual(errors, [])

    def test_missing_canonical_is_reported(self):
        self._consumer("00000000", canon="nope.md")
        errors: list[str] = []
        v.check_ssot_pins(errors)
        self.assertIn("canonical missing", errors[0])

    def test_non_md_canonical_is_reported(self):
        _write(self.root, "lib.sh", "echo hi\n")
        self._consumer("00000000", anchor="", canon="lib.sh")
        errors: list[str] = []
        v.check_ssot_pins(errors)
        self.assertIn("md のみ対応", errors[0])

    def test_self_reference_is_reported(self):
        _write(self.root, "consumer.md", "# c\n\n<!-- SSOT: consumer.md#1 @00000000 -->\n")
        errors: list[str] = []
        v.check_ssot_pins(errors)
        self.assertIn("自己参照", errors[0])

    def test_unknown_anchor_is_reported(self):
        self._consumer("00000000", anchor="#99")
        errors: list[str] = []
        v.check_ssot_pins(errors)
        self.assertIn("見つからない", errors[0])

    def test_whole_file_pin_of_a_pinning_canonical_is_reported(self):
        """全ファイル pin の正本が自身も pin を持つと打ち直しが収束しないので error."""
        _write(self.root, "a.md", "# a\n\n<!-- SSOT: b.md#1 @00000000 -->\n")
        _write(self.root, "b.md", "# b\n\n<!-- SSOT: a.md @00000000 -->\n\n## 1. x\n\ny\n")
        errors: list[str] = []
        v.check_ssot_pins(errors)
        self.assertTrue(any("収束しない" in e for e in errors), errors)

    def test_pin_in_a_fenced_block_is_not_collected(self):
        """解説のコードブロックに書いた記法例は「生きた pin」にならない.

        収集がフェンスを見ないと, 具体的なハッシュ入りの例を doc に 1 つ書いた瞬間に
        repo 全体が 3 経路で落ち, `--update-ssot-pins` が解説文のハッシュを書き換える.
        """
        _write(
            self.root,
            "consumer.md",
            """
            # 消費サイト

            ```md
            <!-- SSOT: canon.md#3.5 @00000000 -->
            ```
            """,
        )
        errors: list[str] = []
        v.check_ssot_pins(errors)
        self.assertEqual(errors, [])

    def test_pin_in_inline_code_is_not_collected(self):
        """行内コード片の記法説明（CLAUDE.md / ADR の書式例）も収集しない."""
        _write(self.root, "consumer.md", "# c\n\n`<!-- SSOT: canon.md#3.5 @00000000 -->` を置く\n")
        errors: list[str] = []
        v.check_ssot_pins(errors)
        self.assertEqual(errors, [])

    def test_pin_outside_fence_is_still_collected(self):
        """フェンス除外が「全部拾わない」に倒れていないことの対（negative の相方）."""
        self._consumer("00000000")
        errors: list[str] = []
        v.check_ssot_pins(errors)
        self.assertEqual(len(errors), 1)

    def test_malformed_pin_is_reported(self):
        """記法を外した pin を「pin ではない」と黙って捨てない（無警告の無効化を作らない）."""
        for bad in ("DEADBEEF", "TBD", "<hash8>"):
            with self.subTest(hash=bad):
                self._consumer(bad)
                errors: list[str] = []
                v.check_ssot_pins(errors)
                self.assertEqual(len(errors), 1, errors)
                self.assertIn("記法が不正", errors[0])

    def test_pin_inside_the_pinned_section_is_reported(self):
        """anchor 付きでも, pin した節が pin を含めば収束しないので error.

        「pin はそれが効く節の直上に置く」という自然な整理で踏む（旧ガードは
        anchor 省略時にしか掛かっておらず, 現行 pin が無事なのは配置の慣習のおかげだった）.
        """
        _write(self.root, "a.md", "# a\n\n## 1. 節\n\n<!-- SSOT: b.md#1 @00000000 -->\n\nx\n")
        _write(self.root, "b.md", "# b\n\n## 1. 節\n\n<!-- SSOT: a.md#1 @00000000 -->\n\ny\n")
        errors: list[str] = []
        v.check_ssot_pins(errors)
        self.assertTrue(all("収束しない" in e for e in errors), errors)
        self.assertEqual(len(errors), 2, errors)

    def test_pin_in_a_nested_directory_is_collected(self):
        """走査はサブディレクトリまで再帰する（実 pin は全件サブディレクトリにある）.

        `rglob` → `glob` の 1 文字改変で pin 機構が 3 経路とも沈黙するが,
        消費サイトを ROOT 直下にしか置かない fixture ではこの改変が素通りする.
        """
        _write(self.root, "nested/deep/consumer.md", "# c\n\n<!-- SSOT: canon.md#3.5 @00000000 -->\n")
        errors: list[str] = []
        v.check_ssot_pins(errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("nested/deep/consumer.md", errors[0])

    def test_update_rewrites_every_pin_in_a_file(self):
        """1 ファイルに複数 pin がある実形状（実 repo は最大 5 pin/ファイル）を打ち直す."""
        consumer = _write(
            self.root,
            "consumer.md",
            """
            # 消費サイト

            <!-- SSOT: canon.md#3.5 @00000000 -->
            <!-- SSOT: canon.md#4 @00000000 -->
            """,
        )
        updated = v.check_ssot_pins([], update=True)
        self.assertEqual(updated, 2)
        body = consumer.read_text()
        self.assertIn(v._canonical_digest(self.canon, "3.5"), body)
        self.assertIn(v._canonical_digest(self.canon, "4"), body)
        errors: list[str] = []
        v.check_ssot_pins(errors)
        self.assertEqual(errors, [])

    def test_update_rewrites_pin_and_converges(self):
        consumer = self._consumer("00000000")
        updated = v.check_ssot_pins([], update=True)
        self.assertEqual(updated, 1)
        self.assertIn(v._canonical_digest(self.canon, "3.5"), consumer.read_text())
        errors: list[str] = []
        v.check_ssot_pins(errors)
        self.assertEqual(errors, [])

    def test_update_still_reports_broken_pins(self):
        """打ち直し経路でも壊れた pin を握り潰さない（v2.63.1 の初稿は捨てていた）."""
        self._consumer("00000000", anchor="#99")
        errors: list[str] = []
        v.check_ssot_pins(errors, update=True)
        self.assertEqual(len(errors), 1)




class CheckSchemaMarkersSyncTest(unittest.TestCase):
    """版マーカー定数の script <-> doc 突合（GitHub issue #134）.

    **期待値をテスト側で独立に構築する**（CLAUDE.md「検証機構の期待値をその機構自身で
    生成すると、壊れていても全件 pass する」）。fixture の script / doc はどちらも
    下の `MARKERS` リテラルから組み立て、実装のパーサは一切通さない。
    """

    # 唯一の真値。script fixture も doc fixture もここから機械的に生成する
    MARKERS = {
        ("pre_adjust_counts", "schema"): 2,
        ("adversarial_verify", "calibration_schema"): 2,
        ("adversarial_verify", "gate_schema"): 3,
        ("meta_reviewer", "gate_schema"): 3,
    }

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self._orig = (v.ROOT, v.SCHEMA_MARKERS_SCRIPT, v.SCHEMA_MARKERS_DOC, v.SCHEMA_MARKERS_PLUGIN)
        v.ROOT = self.root
        v.SCHEMA_MARKERS_SCRIPT = self.root / "publish.sh"
        v.SCHEMA_MARKERS_DOC = self.root / "doc.md"
        v.SCHEMA_MARKERS_PLUGIN = self.root / "plugin.json"
        # skip の判定は「プラグインが在るか」なので, 既定では在る状態にしておく
        v.SCHEMA_MARKERS_PLUGIN.write_text("{}", encoding="utf-8")

        def _restore() -> None:
            (v.ROOT, v.SCHEMA_MARKERS_SCRIPT, v.SCHEMA_MARKERS_DOC,
             v.SCHEMA_MARKERS_PLUGIN) = self._orig

        self.addCleanup(_restore)

    def _write_script(self, markers: dict[tuple[str, str], int]) -> None:
        """実スクリプトと同じ形（heredoc python ブロック内の dict）で書き出す."""
        by_field: dict[str, dict[str, int]] = {}
        for (field, key), value in markers.items():
            by_field.setdefault(field, {})[key] = value
        body = "\n".join(
            '    "%s": {%s},' % (f, ", ".join('"%s": %d' % kv for kv in m.items()))
            for f, m in by_field.items()
        )
        v.SCHEMA_MARKERS_SCRIPT.write_text(
            "#!/usr/bin/env bash\n"
            "python3 - <<'PY'\n"
            "# 版マーカー（定数）の注入\n"
            "SCHEMA_MARKERS = {\n" + body + "\n}\n"
            "PY\n",
            encoding="utf-8",
        )

    # 実データ相当のノイズ. **対象節の「中」に置く** — 実ファイルの anchor 節は次の
    # 同レベル以上の見出しまで（実測 193 行）に及び, `## 16` は payload 契約の本体なので
    # 非対象テーブルが同一節内に実在する. 節の「外」に置く fixture では,
    # 実際に効いている防御（テーブルブロック限定 + 行書式の厳格さ）を一度も通らない.
    IN_SECTION_NOISE = (
        "\n"
        "| フィールド | 内容 |\n|---|---|\n"
        "| `diff_digest` | diff 全文の cksum |\n"
        "\n"
        "| `schema` | 算出方法 | 粒度 |\n|---|---|---|\n"
        "| `1`（v2.44.0〜） | reviewer が列挙した指摘のみ | 統合・dedup 後 |\n"
    )

    # **対象テーブルの中**に置く非マーカー行（バッククォート無し × 3 列目が数値）。
    # テーブルブロック限定は「ブロックの外」を守るだけなので, **行書式の厳格さ**を試すには
    # ブロックの中にノイズが要る。これが無いとバッククォート要求を外す変異を検知できない
    IN_TABLE_NOISE = "\n| 備考 | 旧ゲート | 2 |"

    def _write_doc(
        self,
        markers: dict[tuple[str, str], int],
        anchor: str = "版マーカーの現行値",
        trailing_rows: str = "",
        noise: bool = True,
    ) -> None:
        rows = "\n".join("| `%s` | `%s` | %d |" % (f, k, val) for (f, k), val in markers.items())
        v.SCHEMA_MARKERS_DOC.write_text(
            "# 計測\n\n"
            "## 16. payload 契約\n\n"
            "本文。\n\n"
            f"### {anchor}\n\n"
            "| payload フィールド | 版マーカー | 現行値 |\n|---|---|---|\n"
            + rows + (self.IN_TABLE_NOISE if noise else "") + trailing_rows + "\n\n"
            "- 注記。\n"
            + (self.IN_SECTION_NOISE if noise else "") +
            "\n### 別の節\n\n"
            "| payload フィールド | 版マーカー | 現行値 |\n|---|---|---|\n"
            "| `無関係` | `dummy` | 99 |\n",
            encoding="utf-8",
        )

    def test_matching_values_produce_no_error(self):
        """ノイズ無しの最小 doc での baseline（ノイズ耐性は別テストが見る）."""
        self._write_script(self.MARKERS)
        self._write_doc(self.MARKERS, noise=False)
        errors: list[str] = []
        v.check_schema_markers_sync(errors)
        self.assertEqual(errors, [])

    def test_value_drift_is_reported(self):
        drifted = dict(self.MARKERS)
        drifted[("meta_reviewer", "gate_schema")] = 4     # doc だけ据え置き
        self._write_script(drifted)
        self._write_doc(self.MARKERS)
        errors: list[str] = []
        v.check_schema_markers_sync(errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("meta_reviewer.gate_schema", errors[0])
        self.assertIn("script=4", errors[0])
        self.assertIn("doc=3", errors[0])

    def test_marker_missing_from_doc_is_reported(self):
        partial = {k: val for k, val in self.MARKERS.items() if k != ("adversarial_verify", "gate_schema")}
        self._write_script(self.MARKERS)
        self._write_doc(partial)
        errors: list[str] = []
        v.check_schema_markers_sync(errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("adversarial_verify.gate_schema", errors[0])
        self.assertIn("doc の表に無い", errors[0])

    def test_marker_only_in_doc_is_reported(self):
        partial = {k: val for k, val in self.MARKERS.items() if k != ("pre_adjust_counts", "schema")}
        self._write_script(partial)
        self._write_doc(self.MARKERS)
        errors: list[str] = []
        v.check_schema_markers_sync(errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("pre_adjust_counts.schema", errors[0])
        self.assertIn("SCHEMA_MARKERS に無い", errors[0])

    def test_noise_tables_in_the_same_section_are_not_read(self):
        """**同一節内の非対象テーブルを拾わないこと**（実データのレイアウト）.

        `_write_doc` は対象表の後ろに 2 列表と「3 列目が非数値」の表を置く.
        テーブルブロック限定 + 行書式の厳格さのどちらかを緩めるとここが落ちる.
        """
        self._write_script(self.MARKERS)
        self._write_doc(self.MARKERS)          # 既定でノイズ入り
        errors: list[str] = []
        v.check_schema_markers_sync(errors)
        self.assertEqual(errors, [])

    def test_a_later_row_in_the_section_does_not_override(self):
        """**節の後方に同型行を足しても正本を上書きしないこと**.

        節全体に findall を掛けていた版は dict の後勝ちで `3` が `2` に化けた（実測）.
        対象表の外に置いた行は「拾わない」のが正しい挙動なので errors は空.
        """
        self._write_script(self.MARKERS)
        self._write_doc(self.MARKERS)
        doc = v.SCHEMA_MARKERS_DOC.read_text(encoding="utf-8")
        # **対象節の中・最初のテーブルブロックの外**に置く（節末尾に足すのと同じ位置）。
        # ファイル末尾に足すと「別の節」に入ってしまい, 節境界だけを見るテストに退化する
        assert "\n### 別の節" in doc
        doc = doc.replace("\n### 別の節", "\n| `meta_reviewer` | `gate_schema` | 2 |\n\n### 別の節", 1)
        v.SCHEMA_MARKERS_DOC.write_text(doc, encoding="utf-8")
        errors: list[str] = []
        v.check_schema_markers_sync(errors)
        self.assertEqual(errors, [])

    def test_duplicate_row_in_the_table_is_reported(self):
        """**対象表の中の重複は後勝ちで黙らせない**（どちらが正本か決められない）."""
        self._write_script(self.MARKERS)
        self._write_doc(self.MARKERS, trailing_rows="\n| `meta_reviewer` | `gate_schema` | 2 |")
        errors: list[str] = []
        v.check_schema_markers_sync(errors)
        self.assertTrue(any("重複" in e and "meta_reviewer.gate_schema" in e for e in errors), errors)

    def test_one_sided_missing_file_is_reported(self):
        """**片方だけ欠けているのは error**（リネームで保護が無言で外れるのを防ぐ）."""
        self._write_script(self.MARKERS)
        self._write_doc(self.MARKERS)
        v.SCHEMA_MARKERS_SCRIPT.unlink()
        errors: list[str] = []
        v.check_schema_markers_sync(errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("突合対象が見つからない", errors[0])

    def test_bool_value_is_rejected(self):
        """`isinstance(True, int)` は真なので, bool を通すと `True == 1` で一致扱いになる."""
        self._write_doc(self.MARKERS)
        v.SCHEMA_MARKERS_SCRIPT.write_text(
            "python3 - <<'PY'\nSCHEMA_MARKERS = {\n    \"pre_adjust_counts\": {\"schema\": True},\n}\nPY\n",
            encoding="utf-8",
        )
        errors: list[str] = []
        v.check_schema_markers_sync(errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("整数ではない", errors[0])

    def test_unreadable_dict_is_reported(self):
        v.SCHEMA_MARKERS_SCRIPT.write_text("#!/usr/bin/env bash\necho no markers here\n", encoding="utf-8")
        self._write_doc(self.MARKERS)
        errors: list[str] = []
        v.check_schema_markers_sync(errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("SCHEMA_MARKERS を読めない", errors[0])

    def test_missing_doc_section_is_reported(self):
        self._write_script(self.MARKERS)
        self._write_doc(self.MARKERS, anchor="別名の節")
        errors: list[str] = []
        v.check_schema_markers_sync(errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("節が無い", errors[0])

    def test_missing_plugin_is_skipped(self):
        """**黙るのはプラグインごと無いときだけ**（code-review を消した repo で誤爆させない）."""
        v.SCHEMA_MARKERS_PLUGIN.unlink()
        errors: list[str] = []
        v.check_schema_markers_sync(errors)
        self.assertEqual(errors, [])


class TestDiscoveryTest(unittest.TestCase):
    """**このファイルのテストが全部収集されているか**を自分で確かめる.

    `if __name__ == "__main__": unittest.main()` より後ろにクラスを足すと,
    `unittest.main()` が `sys.exit()` するため後続のクラス定義自体が評価されず,
    **直接実行だけ静かに件数が減る**（実測: discover 41 件 / 直接実行 33 件で
    どちらも `OK`）. 強制経路（pre-commit / CI / Stop hook）は 3 本とも discover なので
    実害は出ないが, 「OK が出るのに走っていない」はこのファイルが存在する理由そのもの.
    """

    def test_every_testcase_in_this_module_is_collected(self):
        import __main__  # noqa: F401  （直接実行時のモジュール差異を吸収する意図はない）

        module = sys.modules[__name__]
        defined = {
            name
            for name, obj in vars(module).items()
            if isinstance(obj, type) and issubclass(obj, unittest.TestCase)
        }
        collected = {
            type(t).__name__
            for t in unittest.defaultTestLoader.loadTestsFromModule(module)._tests
            for t in getattr(t, "_tests", [t])
        }
        self.assertEqual(defined - collected, set(), "収集されていない TestCase がある")


class DocStructureTest(unittest.TestCase):
    """番号見出しの重複と blockquote 分断（doc lint）.

    どちらも**実際にセルフレビューをすり抜けた / agent 8 体を要した**型なので,
    「lint が見つけるべきものを agent に探させない」の実装として入れた.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self._orig = v.ROOT
        v.ROOT = self.root
        self.addCleanup(lambda: setattr(v, "ROOT", self._orig))
        self.plugin = self.root / "demo"
        (self.plugin / "references").mkdir(parents=True)

    def _doc(self, body: str) -> None:
        _write(self.plugin / "references", "guide.md", body)

    def test_clean_doc_produces_no_error(self):
        self._doc("""
            # ガイド

            ## 1. 最初

            > 引用の 1 段落目。
            >
            > 2 段落目。

            ## 2. 次
            """)
        errors: list[str] = []
        v.check_doc_structure(self.plugin, errors)
        self.assertEqual(errors, [])

    def test_duplicate_numbered_heading_is_reported(self):
        self._doc("""
            # ガイド

            ## 5. これ

            ## 4. あれ

            ## 5. 重複
            """)
        errors: list[str] = []
        v.check_doc_structure(self.plugin, errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("番号見出し `5` が重複", errors[0])

    def test_orphan_blockquote_line_is_reported(self):
        self._doc("""
            # ガイド

            ## 1. これ

            > 引用。
            >

            通常の段落。
            """)
        errors: list[str] = []
        v.check_doc_structure(self.plugin, errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("孤立した `>` 行", errors[0])

    def test_skill_md_is_also_scanned(self):
        """**`*/skills/*/SKILL.md` 経路**（glob からこちらを落としても気づけない状態にしない）."""
        (self.plugin / "skills" / "demo").mkdir(parents=True)
        _write(self.plugin / "skills" / "demo", "SKILL.md", """
            # スキル

            ## 3. これ

            ## 3. 重複
            """)
        errors: list[str] = []
        v.check_doc_structure(self.plugin, errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("SKILL.md", errors[0])

    def test_orphan_is_found_even_when_the_section_ends_with_a_quote(self):
        """探索は**最初の非空行で打ち切る**（打ち切りを外すと節末尾の引用に吸われて見逃す）."""
        self._doc("""
            # ガイド

            ## 1. これ

            > 引用の途中。
            >

            通常の段落（ここで分断されている）。

            > 別の引用が節末尾にある。
            """)
        errors: list[str] = []
        v.check_doc_structure(self.plugin, errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("孤立した `>` 行", errors[0])

    def test_quote_ending_before_a_heading_is_not_reported(self):
        """**節末尾で引用が終わるのは正常**（探索が節境界を越えると誤検知になる）."""
        self._doc("""
            # ガイド

            ## 1. これ

            > 引用。
            >

            ## 2. 次の節
            """)
        errors: list[str] = []
        v.check_doc_structure(self.plugin, errors)
        self.assertEqual(errors, [])

    def test_fenced_block_is_not_scanned(self):
        """**フェンス内の `##` と `>` は見出しでも引用でもない**（誤検知の主因）."""
        self._doc("""
            # ガイド

            ## 1. これ

            ```markdown
            ## 1. フェンス内の同番号
            > 引用の例
            >
            ```

            本文。
            """)
        errors: list[str] = []
        v.check_doc_structure(self.plugin, errors)
        self.assertEqual(errors, [])


class TestFileLintTest(unittest.TestCase):
    """テストファイル自身の lint（収集漏れ / 本体重複）."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self._orig = v.ROOT
        v.ROOT = self.root
        self.addCleanup(lambda: setattr(v, "ROOT", self._orig))
        (self.root / "tests").mkdir()

    def _test_file(self, body: str) -> None:
        _write(self.root / "tests", "test_demo.py", body)

    def test_class_before_main_is_fine(self):
        self._test_file("""
            import unittest


            class A(unittest.TestCase):
                def test_x(self):
                    self.assertTrue(True)


            if __name__ == "__main__":
                unittest.main()
            """)
        errors: list[str] = []
        v.check_test_collection(errors)
        self.assertEqual(errors, [])

    def test_class_after_main_is_reported(self):
        self._test_file("""
            import unittest


            if __name__ == "__main__":
                unittest.main()


            class Late(unittest.TestCase):
                def test_x(self):
                    self.assertTrue(True)
            """)
        errors: list[str] = []
        v.check_test_collection(errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("`if __name__` より後ろ", errors[0])

    def test_class_with_docstring_and_attributes_is_handled(self):
        """**クラス本体に関数以外がある**実データ形（docstring / 属性）で壊れないこと.

        `isinstance(n, ast.FunctionDef) and n.name.startswith("test")` の `and` を緩めると
        属性ノードで `.name` を触って落ちる。fixture が関数だけだとこの変異が生き残る。
        """
        self._test_file("""
            import unittest


            class A(unittest.TestCase):
                MARKER = {"a": 1}

                def test_one(self):
                    self.assertEqual(1, 1)

                def helper(self):
                    return 2
            """)
        errors: list[str] = []
        v.check_duplicate_test_bodies(errors)
        self.assertEqual(errors, [])

    def test_identical_test_bodies_are_reported(self):
        self._test_file("""
            import unittest


            class A(unittest.TestCase):
                def test_one(self):
                    self.assertEqual(1, 1)

                def test_two(self):
                    # 名前は別のことを主張しているが中身は同じ
                    self.assertEqual(1, 1)
            """)
        errors: list[str] = []
        v.check_duplicate_test_bodies(errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("`A.test_two` の本体が `test_one` と同一", errors[0])

    def test_decorator_difference_is_not_a_duplicate(self):
        """`@patch` 違いは**本体が同じでも独立に失敗しうる**正当なテスト."""
        self._test_file("""
            import unittest
            from unittest.mock import patch


            class A(unittest.TestCase):
                @patch("mod.a")
                def test_one(self, m):
                    self.assertEqual(1, 1)

                @patch("mod.b")
                def test_two(self, m):
                    self.assertEqual(1, 1)
            """)
        errors: list[str] = []
        v.check_duplicate_test_bodies(errors)
        self.assertEqual(errors, [])

    def test_placeholder_pass_bodies_are_not_duplicates(self):
        """`pass` のみのプレースホルダは対象外（3 つあると 2 件目以降が全部誤検知になる）."""
        self._test_file("""
            import unittest


            class A(unittest.TestCase):
                def test_one(self):
                    pass

                def test_two(self):
                    pass

                def test_three(self):
                    pass
            """)
        errors: list[str] = []
        v.check_duplicate_test_bodies(errors)
        self.assertEqual(errors, [])

    def test_docstring_only_difference_is_still_a_duplicate(self):
        """説明だけ違うのは同一とみなす（docstring 剥がしが効いていること）."""
        body = "\n".join([
            "",
            "            import unittest",
            "",
            "",
            "            class A(unittest.TestCase):",
            "                def test_one(self):",
            "                    " + Q + "ある観点。" + Q,
            "                    self.assertEqual(1, 1)",
            "",
            "                def test_two(self):",
            "                    " + Q + "別の観点のつもり。" + Q,
            "                    self.assertEqual(1, 1)",
            "            ",
        ])
        self._test_file(body)
        errors: list[str] = []
        v.check_duplicate_test_bodies(errors)
        self.assertEqual(len(errors), 1, errors)

    def test_different_bodies_are_fine(self):
        self._test_file("""
            import unittest


            class A(unittest.TestCase):
                def test_one(self):
                    self.assertEqual(1, 1)

                def test_two(self):
                    self.assertEqual(2, 2)
            """)
        errors: list[str] = []
        v.check_duplicate_test_bodies(errors)
        self.assertEqual(errors, [])


class VersionPlaceholderTest(unittest.TestCase):
    """`vNEXT` の残存検査.

    **開発中の残存は正常**（bump 前）なので、bump が起きた作業ツリーでだけ鳴ること —
    ここを間違えると毎ターン鳴る warning になり、このリポジトリが繰り返し避けてきた
    「⚠️ が出たときだけ行動する」契約の破壊になる。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self._orig = v.ROOT
        v.ROOT = self.root
        self.addCleanup(lambda: setattr(v, "ROOT", self._orig))
        self.plugin = self.root / "demo"
        (self.plugin / ".claude-plugin").mkdir(parents=True)
        (self.plugin / "references").mkdir()
        self._head_version = "1.0.0"
        self._orig_head = v._version_at_head
        v._version_at_head = lambda _p: self._head_version
        self.addCleanup(lambda: setattr(v, "_version_at_head", self._orig_head))

    def _plugin_json(self, version: str) -> None:
        (self.plugin / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "demo", "version": version}), encoding="utf-8")

    def _doc(self, body: str) -> None:
        (self.plugin / "references" / "note.md").write_text(body, encoding="utf-8")

    def test_placeholder_before_bump_is_allowed(self):
        """**bump 前の `vNEXT` は正常**（開発中に毎回鳴らさない）."""
        self._plugin_json("1.0.0")           # HEAD と同じ = 未 bump
        self._doc("この挙動は vNEXT で入った。")
        errors: list[str] = []
        v.check_pending_version_placeholder(self.plugin, errors)
        self.assertEqual(errors, [])

    def test_placeholder_after_bump_is_reported(self):
        self._plugin_json("1.1.0")           # HEAD と違う = bump 済み
        self._doc("この挙動は vNEXT で入った。")
        errors: list[str] = []
        v.check_pending_version_placeholder(self.plugin, errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("vNEXT", errors[0])
        self.assertIn("note.md", errors[0])

    def test_resolved_placeholder_after_bump_is_clean(self):
        self._plugin_json("1.1.0")
        self._doc("この挙動は v1.1.0 で入った。")
        errors: list[str] = []
        v.check_pending_version_placeholder(self.plugin, errors)
        self.assertEqual(errors, [])

    def test_unknown_head_version_is_skipped(self):
        """HEAD に無い（新規プラグイン）回は判定しない."""
        v._version_at_head = lambda _p: None
        self._plugin_json("0.1.0")
        self._doc("vNEXT")
        errors: list[str] = []
        v.check_pending_version_placeholder(self.plugin, errors)
        self.assertEqual(errors, [])

    def test_placeholder_in_inline_code_is_not_reported(self):
        """**規約そのものを説明する文章は対象外**（`vNEXT` を行内コードで書いた場合）.

        SSoT pin と同じ扱い。これを入れないと「置換も検出も、規約の説明文を壊す」
        （実測: bump が説明文の 7 箇所を実版に書き換えた）。
        """
        self._plugin_json("1.1.0")
        self._doc("\n".join([
            "版ラベルは `vNEXT` と書く（行内コード）。",
            "",
            "```markdown",
            "この挙動は vNEXT で入った   <- フェンス内の記法例",
            "```",
            "",
        ]))
        errors: list[str] = []
        v.check_pending_version_placeholder(self.plugin, errors)
        self.assertEqual(errors, [])

    def test_only_md_sh_py_are_scanned(self):
        """走査対象は md / sh / py（JSON の中の文字列などは見ない）."""
        self._plugin_json("1.1.0")
        (self.plugin / "data.json").write_text('{"note": "vNEXT"}', encoding="utf-8")
        errors: list[str] = []
        v.check_pending_version_placeholder(self.plugin, errors)
        self.assertEqual(errors, [])

class TextAtBaseTest(unittest.TestCase):
    """比較基準時点のファイル内容の取得.

    **`git show` の失敗を空文字として返すと、差分検査が「基準では空だった」と読んで
    全ファイルを『新規追加』扱いする**（鳴りっぱなしか、逆に沈黙しっぱなしになる）。
    不在と取得失敗は None で表現する契約をここで固定する。
    """

    def test_a_tracked_file_comes_back(self):
        self.assertIn("claude-plugins", v.text_at_base(v.ROOT / "CLAUDE.md") or "")

    def test_a_path_absent_from_the_base_is_none(self):
        """空文字ではなく None（`git show` の非ゼロ終了を値として通さない）."""
        self.assertIsNone(v.text_at_base(v.ROOT / "no-such-file-for-tests.md"))


class VersionBaseTest(unittest.TestCase):
    """比較基準の解決（`QUALITY_VERSION_BASE`）.

    **既定が壊れると検査が構造的に no-op になる**（`git show None:...` が必ず失敗し、
    version が読めない → 早期 return → 何も鳴らない）。しかも「エラーが出ない」ので
    壊れていることに気づけない — CI で一度も発火しなかった原因と同じ形。
    """

    SCRIPT = Path(__file__).resolve().parents[1] / "validate_plugin_quality.py"

    def _base_with_env(self, value):
        env = dict(os.environ)
        env.pop("QUALITY_VERSION_BASE", None)
        if value is not None:
            env["QUALITY_VERSION_BASE"] = value
        code = (
            "import importlib.util,sys;"
            f"spec=importlib.util.spec_from_file_location('vq', r'{self.SCRIPT}');"
            "m=importlib.util.module_from_spec(spec);sys.modules['vq']=m;"
            "spec.loader.exec_module(m);print(m.VERSION_BASE)"
        )
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_defaults_to_head(self):
        self.assertEqual(self._base_with_env(None), "HEAD")

    def test_empty_env_falls_back_to_head(self):
        """CI が空文字を渡しうる（初回コミットで base が決まらない場合）."""
        self.assertEqual(self._base_with_env(""), "HEAD")

    def test_env_overrides(self):
        self.assertEqual(self._base_with_env("origin/main"), "origin/main")


class HookScriptRefsTest(unittest.TestCase):
    """hooks.json が参照する `.sh` の実在検査（GitHub issue #176）.

    実在しない参照は解決側が黙って落とすので、パスのタイポやスクリプト移動で
    hooks 安全性 / hook 自己判定の検査が**無言で対象ゼロ**になる（hook は配布された
    ままで検査だけ消える）。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self._orig = v.ROOT
        v.ROOT = self.root
        self.addCleanup(lambda: setattr(v, "ROOT", self._orig))
        self.plugin = self.root / "demo"
        (self.plugin / "hooks" / "scripts").mkdir(parents=True)

    def _hooks_json(self, script_ref: str) -> None:
        _write(self.plugin, "hooks/hooks.json", json.dumps({
            "hooks": {"SessionStart": [{"hooks": [
                {"type": "command", "command": "bash", "args": [script_ref]}]}]}}))

    def _script(self, rel: str) -> None:
        _write(self.plugin, rel, "#!/usr/bin/env bash\nsource lib/safe-hook.sh\n")

    def test_an_existing_reference_is_accepted(self):
        self._hooks_json("${CLAUDE_PLUGIN_ROOT}/hooks/scripts/ok.sh")
        self._script("hooks/scripts/ok.sh")
        errors: list[str] = []
        v.check_hook_script_refs(self.plugin, errors)
        self.assertEqual(errors, [])

    def test_a_missing_reference_is_an_error(self):
        self._hooks_json("${CLAUDE_PLUGIN_ROOT}/hooks/scripts/gone.sh")
        errors: list[str] = []
        v.check_hook_script_refs(self.plugin, errors)
        self.assertEqual(len(errors), 1, "実在しない参照を黙って落としている")
        self.assertIn("gone.sh", errors[0])

    def test_a_renamed_script_is_caught(self):
        """スクリプトを改名すると宣言だけが残る（この型が検査を無言で消す）."""
        self._hooks_json("${CLAUDE_PLUGIN_ROOT}/hooks/scripts/old-name.sh")
        self._script("hooks/scripts/new-name.sh")
        errors: list[str] = []
        v.check_hook_script_refs(self.plugin, errors)
        self.assertEqual(len(errors), 1)
        self.assertIn("old-name.sh", errors[0])

    def test_the_legacy_command_form_is_also_checked(self):
        """`command: "bash <path>"` の旧記法も対象（新旧が混在している）."""
        _write(self.plugin, "hooks/hooks.json", json.dumps({
            "hooks": {"SessionStart": [{"hooks": [
                {"type": "command",
                 "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/gone.sh"}]}]}}))
        errors: list[str] = []
        v.check_hook_script_refs(self.plugin, errors)
        self.assertEqual(len(errors), 1)

    def test_a_plugin_without_hooks_is_silent(self):
        errors: list[str] = []
        v.check_hook_script_refs(self.root / "no-hooks", errors)
        self.assertEqual(errors, [])

    # ---- 解決側（`_hook_script_paths`）---------------------------------------
    def test_resolution_returns_the_existing_scripts(self):
        """**空のリストを返していないこと**を直接見る.

        ここが空になると `check_hooks_safety` と `check_hook_self_judgement` が
        無言で対象ゼロになる — 検査は緑のまま hook だけが無検証で配布される。
        """
        _write(self.plugin, "hooks/hooks.json", json.dumps({"hooks": {"SessionStart": [
            {"hooks": [{"type": "command", "command": "bash",
                        "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/scripts/a.sh"]},
                       {"type": "command", "command": "bash",
                        "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/scripts/b.sh"]}]}]}}))
        self._script("hooks/scripts/a.sh")
        self._script("hooks/scripts/b.sh")
        found = v._hook_script_paths(self.plugin, None)
        self.assertEqual([p.name for p in found], ["a.sh", "b.sh"])

    def test_resolution_dedups_repeated_references(self):
        """同じスクリプトを 2 イベントから参照しても 1 回だけ返す."""
        entry = {"hooks": [{"type": "command", "command": "bash",
                            "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/scripts/a.sh"]}]}
        _write(self.plugin, "hooks/hooks.json", json.dumps({
            "hooks": {"SessionStart": [entry], "PostCompact": [entry]}}))
        self._script("hooks/scripts/a.sh")
        found = v._hook_script_paths(self.plugin, None)
        self.assertEqual([p.name for p in found], ["a.sh"])


class CheckScopeTest(unittest.TestCase):
    """検査の走査範囲が正本の宣言どおりか（GitHub issue #177）.

    範囲の穴は「検出ゼロ」と見分けがつかない — 対象に入っていないファイルは
    何を書いても緑になる。**範囲そのものを表明する**テストで塞ぐ。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self._orig = v.ROOT
        v.ROOT = self.root
        self.addCleanup(lambda: setattr(v, "ROOT", self._orig))
        self.plugin = self.root / "demo"

    def test_skill_bundled_scripts_are_syntax_checked(self):
        """`skills/*/scripts/` は配布物なのに `scripts/**` にも `hooks/**` にも掛からない."""
        _write(self.plugin, "skills/s/scripts/broken.sh", "#!/usr/bin/env bash\nif [ 1 ; then\n")
        errors: list[str] = []
        v.check_shell_syntax(self.plugin, errors)
        self.assertEqual(len(errors), 1, "skill 同梱スクリプトが構文検査の外にある")
        self.assertIn("broken.sh", errors[0])

    def test_skill_bundled_scripts_are_multibyte_checked(self):
        _write(self.plugin, "skills/s/scripts/x.sh", '#!/usr/bin/env bash\necho "$VAR（説明）"\n')
        errors: list[str] = []
        v.check_shell_multibyte_expansion(self.plugin, errors)
        self.assertEqual(len(errors), 1, "skill 同梱スクリプトが多バイト検査の外にある")

    def test_skill_bundled_references_are_doc_linted(self):
        """`skills/*/references/` は実測 76 ファイルが doc lint の外にあった."""
        _write(self.plugin, "skills/s/references/note.md", """
            ## 1. あ

            ## 1. い
            """)
        errors: list[str] = []
        v.check_doc_structure(self.plugin, errors)
        self.assertTrue(errors, "skill 配下 references が doc lint の外にある")

    def test_repo_local_scripts_are_checked(self):
        """repo 直下の共通スクリプトはプラグイン版に属さないが、壊れるとゲートが死ぬ."""
        _write(self.root, ".claude-plugin/scripts/gate.sh", "#!/usr/bin/env bash\nif [ 1 ; then\n")
        errors: list[str] = []
        v.check_shell_repo_local(errors)
        self.assertTrue(any("gate.sh" in e for e in errors),
                        "repo 直下スクリプトが構文検査の外にある")

    def test_repo_local_scripts_are_multibyte_checked(self):
        _write(self.root, ".claude/oracles.sh", '#!/usr/bin/env bash\necho "$OUT（結果）"\n')
        errors: list[str] = []
        v.check_shell_repo_local(errors)
        self.assertTrue(any("shell-multibyte" in e for e in errors),
                        "repo 直下スクリプトが多バイト検査の外にある")


class DocAnchorFormsTest(unittest.TestCase):
    """節参照の書き方ごとの拾い漏れ（GitHub issue #177）."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self._orig = v.ROOT
        v.ROOT = self.root
        self.addCleanup(lambda: setattr(v, "ROOT", self._orig))
        self.plugin = self.root / "demo"
        _write(self.plugin, "references/target.md", "## 8.5 実在する節\n\n本文\n")

    def _refs(self, body: str) -> list[str]:
        _write(self.plugin, "references/src.md", body)
        errors: list[str] = []
        v.check_doc_anchors(self.plugin, errors)
        return errors

    def test_a_section_title_after_the_number_is_still_checked(self):
        """`foo.md \\`## 9 反証レイヤー\\`` 形式（実測 14 箇所が無検証だった）."""
        self.assertTrue(self._refs("詳細は `target.md `## 9 反証レイヤー`` を読む\n"),
                        "節番号の後ろに節タイトルが続く形を拾えていない")

    def test_a_bare_reference_is_checked(self):
        self.assertTrue(self._refs("詳細は target.md ## 9 を読む\n"),
                        "裸形式を拾えていない")

    def test_an_existing_section_is_accepted(self):
        self.assertEqual(self._refs("詳細は `target.md `## 8.5 実在する節`` を読む\n"), [])

    def test_a_reference_does_not_span_a_newline(self):
        """ファイル名で終わる行の次に来る**自ファイルの見出し**を参照と誤認しない."""
        self.assertEqual(
            self._refs("→ 根拠: `target.md`\n\n## 9. この見出しは src.md 自身のもの\n"), [],
            "改行をまたいで見出しを参照と誤認している")


class PluginDescriptionSizeTest(unittest.TestCase):
    """`plugin.json` の description 上限（設計 20260610-plugin-description-diet の Phase 3）.

    規約に「短く書け」と書いても再発したので機械強制に昇格させた検査
    （実測: code-review が 915 → 2177 字までリリースノート化した）。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self._orig = v.ROOT
        v.ROOT = self.root
        self.addCleanup(lambda: setattr(v, "ROOT", self._orig))
        self.plugin = self.root / "demo"
        (self.plugin / ".claude-plugin").mkdir(parents=True)

    def _desc(self, n: int) -> list[str]:
        (self.plugin / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "demo", "description": "あ" * n}), encoding="utf-8")
        warnings: list[str] = []
        v.check_plugin_description_size(self.plugin, warnings)
        return warnings

    def test_over_the_limit_warns(self):
        self.assertEqual(len(self._desc(v.PLUGIN_DESC_CHAR_LIMIT + 1)), 1)

    def test_exactly_at_the_limit_is_accepted(self):
        """境界の片側だけ測ると `>` と `>=` の取り違えが素通りする."""
        self.assertEqual(self._desc(v.PLUGIN_DESC_CHAR_LIMIT), [])

    def test_a_short_description_is_silent(self):
        self.assertEqual(self._desc(50), [])

    def test_a_missing_description_is_silent(self):
        (self.plugin / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "demo"}), encoding="utf-8")
        warnings: list[str] = []
        v.check_plugin_description_size(self.plugin, warnings)
        self.assertEqual(warnings, [])

    def test_a_broken_plugin_json_is_left_to_the_ssot_check(self):
        (self.plugin / ".claude-plugin" / "plugin.json").write_text("{ not json",
                                                                   encoding="utf-8")
        warnings: list[str] = []
        v.check_plugin_description_size(self.plugin, warnings)
        self.assertEqual(warnings, [])

    def test_the_repository_itself_is_within_the_limit(self):
        """**この検査を入れた時点で全プラグインが上限内**であること.

        既存 corpus で鳴り続ける warning は「⚠️ が出たときだけ行動する」契約を壊す
        （`docs/rule-placement.md`）。閾値を下げるなら先にリライトする。
        """
        v.ROOT = self._orig
        offenders = []
        for pj in sorted(self._orig.glob("*/.claude-plugin/plugin.json")):
            warnings: list[str] = []
            v.check_plugin_description_size(pj.parent.parent, warnings)
            offenders += warnings
        self.assertEqual(offenders, [], "上限を超えるプラグインが残っている")


class WarningChannelTest(unittest.TestCase):
    """warning の出し分け（GitHub issue #182）.

    人手確認の助言は 2026-06-01 の導入以来 42〜73 件が毎回そのまま出続け、
    **行動につながる警告を埋めていた**（実測: skill-size 2 件が 8 日間・毎日リリースの
    中で放置）。既定では件数だけにして S/N を戻す。
    """

    ADVISORY = "[minimality:demo] 要確認 'Read'（本文に直接言及なし）: demo/skills/s/SKILL.md"
    ACTIONABLE = "[skill-size] SKILL.md 本文 505 行（references へ）: demo/skills/s/SKILL.md"

    def _render(self, warnings: list[str], *, verbose: bool) -> str:
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            v._print_warnings(warnings, verbose=verbose)
        return buf.getvalue()

    def test_advisories_are_summarised_by_default(self):
        out = self._render([self.ADVISORY] * 42, verbose=False)
        self.assertIn("42 件", out)
        self.assertNotIn("要確認 'Read'", out, "既定で全件出している")

    def test_actionable_warnings_are_always_listed(self):
        out = self._render([self.ADVISORY] * 42 + [self.ACTIONABLE], verbose=False)
        self.assertIn("SKILL.md 本文 505 行", out, "行動できる警告が助言に埋もれている")

    def test_verbose_lists_every_advisory(self):
        out = self._render([self.ADVISORY] * 3, verbose=True)
        self.assertEqual(out.count("要確認 'Read'"), 3)

    def test_only_advisory_tags_are_summarised(self):
        """助言として畳むのは既知のタグだけ（新しい検査を黙って隠さない）."""
        out = self._render(["[agent-sync:demo] 要確認: run_in_background 未言及"], verbose=False)
        self.assertIn("run_in_background", out)

    def test_the_verbose_flag_is_not_mistaken_for_a_plugin_name(self):
        """`--verbose` を付けても全プラグインを検査する（CLI 境界越しに見る）.

        フラグを引数リストから落とし損ねると、`--verbose` がプラグイン名として
        解決されて「指定されたプラグインが無い」で落ちる。
        """
        r = subprocess.run([sys.executable, str(SCRIPT), "--verbose"],
                           capture_output=True, text=True, cwd=str(v.ROOT))
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertNotIn("[args]", r.stderr, "フラグをプラグイン名として解決している")


class ResolvePluginsTest(unittest.TestCase):
    """引数のプラグイン解決（GitHub issue #176）.

    CWD 相対で解くと、リポジトリ外から起動したときに存在しないパスへ解決され、
    **プラグイン別検査を 1 つも走らせずに passed** になる。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self._orig = v.ROOT
        v.ROOT = self.root
        self.addCleanup(lambda: setattr(v, "ROOT", self._orig))
        self._cwd = os.getcwd()
        self.addCleanup(lambda: os.chdir(self._cwd))

    def test_a_relative_name_resolves_against_the_repo_not_the_cwd(self):
        (self.root / "demo" / ".claude-plugin").mkdir(parents=True)
        other = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: other.rmdir())
        os.chdir(other)
        self.assertEqual(v.resolve_plugins(["demo"]), [self.root / "demo"])

    def test_an_absolute_path_is_kept(self):
        (self.root / "demo" / ".claude-plugin").mkdir(parents=True)
        target = self.root / "demo"
        self.assertEqual(v.resolve_plugins([str(target)]), [target])

    def test_no_arguments_lists_every_plugin(self):
        for name in ("alpha", "beta"):
            d = self.root / name / ".claude-plugin"
            d.mkdir(parents=True)
            (d / "plugin.json").write_text("{}", encoding="utf-8")
        self.assertEqual(v.resolve_plugins([]),
                         [self.root / "alpha", self.root / "beta"])


class CommentRuleSyncTest(unittest.TestCase):
    """コードコメント規約の区間同期（`ROOT` と定数を一時ディレクトリへ差し替える）.

    **消したら黙って通る**のがこの手の検査の壊れ方なので、マーカー欠落・重複・逆順を
    個別に固定する。区間がフェンスの中にあっても拾うことも固定する — 消費サイトの片方
    （reviewer プロンプト）は本文がフェンス内にあり、将来 `_iter_unfenced_lines` を
    挟むと**検査対象が静かにゼロになる**。
    """

    REGION = "軸は 2 つだけ。\n\n観点 1 — 必要な情報のみか\n観点 2 — 冗長表現の排除"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        for name in ("ROOT", "CANONICAL_COMMENT_RULE", "COMMENT_RULE_CONSUMERS"):
            self.addCleanup(lambda n=name, o=getattr(v, name): setattr(v, n, o))
        v.ROOT = self.root
        v.CANONICAL_COMMENT_RULE = self.root / "lib" / "comment-rule.md"
        v.COMMENT_RULE_CONSUMERS = [self.root / "CLAUDE.md", self.root / "prompt.md"]

    def _block(self, region: str | None = None, indent: str = "") -> str:
        body = self.REGION if region is None else region
        lines = [v.COMMENT_RULE_START, *body.split("\n"), v.COMMENT_RULE_END]
        return "\n".join(indent + l if l else l for l in lines)

    def _setup(self, *, canonical: str | None = None, claude: str | None = None,
               prompt: str | None = None) -> list[str]:
        _write(self.root, "lib/comment-rule.md", "# 正本\n\n" + (canonical or self._block()) + "\n")
        _write(self.root, "CLAUDE.md", "# 規約\n\n" + (claude or self._block()) + "\n")
        _write(self.root, "prompt.md", "### B 系統\n\n```\n" + (prompt or self._block()) + "\n```\n")
        errors: list[str] = []
        v.check_comment_rule_sync(errors)
        return errors

    def test_identical_regions_pass(self):
        self.assertEqual(self._setup(), [])

    def test_region_inside_a_fence_is_still_compared(self):
        """フェンス内でも拾う（拾わなくなると prompt.md 側の検査が黙って消える）."""
        errors = self._setup(prompt=self._block("軸は 2 つだけ。\n\n観点 1 — 別物\n観点 2 — 別物"))
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("prompt.md", errors[0])

    def test_one_character_difference_in_claude_md_is_caught(self):
        errors = self._setup(claude=self._block(self.REGION.replace("2 つ", "3 つ")))
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("CLAUDE.md", errors[0])

    def test_uniform_indent_is_allowed(self):
        """消費サイトはリスト内などで一様なインデントを付けてよい（dedent の契約）."""
        self.assertEqual(self._setup(claude=self._block(indent="   ")), [])

    def test_non_uniform_indent_is_a_divergence(self):
        body = "\n".join(("  " + l if i == 0 else l) for i, l in enumerate(self.REGION.split("\n")))
        errors = self._setup(claude=self._block(body))
        self.assertEqual(len(errors), 1, errors)

    def test_missing_markers_are_an_error(self):
        errors = self._setup(claude="規約は無い")
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("marker count invalid", errors[0])

    def test_duplicated_start_marker_is_an_error(self):
        errors = self._setup(claude=v.COMMENT_RULE_START + "\n" + self._block())
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("marker count invalid", errors[0])

    def test_reversed_markers_are_an_error(self):
        errors = self._setup(claude=v.COMMENT_RULE_END + "\n本文\n" + v.COMMENT_RULE_START)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("precedes", errors[0])

    def test_missing_consumer_file_is_an_error(self):
        self._setup()
        (self.root / "CLAUDE.md").unlink()
        errors: list[str] = []
        v.check_comment_rule_sync(errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("consumer missing", errors[0])

    def test_missing_canonical_is_an_error(self):
        errors: list[str] = []
        v.check_comment_rule_sync(errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("canonical missing", errors[0])

    def test_extracted_region_matches_an_independently_built_expectation(self):
        """期待値を `_extract_marked_region` で作らない.

        検証機構の期待値をその機構自身で生成すると、壊れていても全件 pass する（v2.63.1）。
        """
        self._setup()
        got = v._extract_marked_region(self.root / "CLAUDE.md", v.COMMENT_RULE_START,
                                       v.COMMENT_RULE_END, "t", [])
        self.assertEqual(got, self.REGION)


class CommentPolishWiringTest(unittest.TestCase):
    """B 系統の連結宣言（消失 = silent な不発 / 混入 = 他人の PR への越権）."""

    ATTACH = "- <!-- COMMENT-POLISH: attach --> reviewer に prompts/focus/comment-polish.md を渡す\n"
    DETACH = "- <!-- COMMENT-POLISH: detach --> prompts/focus/comment-polish.md は渡さない\n"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        for name in ("ROOT", "COMMENT_POLISH_WIRING"):
            self.addCleanup(lambda n=name, o=getattr(v, name): setattr(v, n, o))
        v.ROOT = self.root
        self.self_review = self.root / "self.md"
        self.review = self.root / "review.md"
        v.COMMENT_POLISH_WIRING = {self.self_review: "attach", self.review: "detach"}

    def _run(self, attach: str | None = None, detach: str | None = None) -> list[str]:
        _write(self.root, "self.md", "# self-review\n\n" + (self.ATTACH if attach is None else attach))
        _write(self.root, "review.md", "# review\n\n" + (self.DETACH if detach is None else detach))
        errors: list[str] = []
        v.check_comment_polish_wiring(errors)
        return errors

    def test_correct_wiring_passes(self):
        self.assertEqual(self._run(), [])

    def test_spacing_variants_are_accepted(self):
        self.assertEqual(
            self._run(attach="<!--COMMENT-POLISH:attach--> prompts/focus/comment-polish.md\n"), [])

    def test_missing_declaration_is_an_error(self):
        errors = self._run(attach="- reviewer に prompts/focus/comment-polish.md を渡す\n")
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("ちょうど 1 個", errors[0])

    def test_attach_without_the_prompt_path_is_an_error(self):
        """**silent 不発の本体**: 宣言はあるが実際には渡していない."""
        errors = self._run(attach="- <!-- COMMENT-POLISH: attach --> 連結する\n")
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("silent", errors[0])

    def test_review_declaring_attach_is_an_error(self):
        errors = self._run(detach=self.ATTACH)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("期待 detach", errors[0])

    def test_duplicated_marker_is_an_error(self):
        errors = self._run(attach=self.ATTACH + self.ATTACH)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("ちょうど 1 個", errors[0])

    def test_missing_skill_file_is_an_error(self):
        self._run()
        self.self_review.unlink()
        errors: list[str] = []
        v.check_comment_polish_wiring(errors)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("SKILL.md missing", errors[0])


class RouterVisibleDescriptionsTest(unittest.TestCase):
    """スキル選択の一覧に実際に載る description の集合（GitHub issue #206）.

    **期待値は実装を呼ばずにテスト側で組み立てる**（このファイル冒頭の要件）。
    同名判定を実装から借りると「同名なら commands 側」という当の契約が
    自己整合して素通りする。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self._orig = v.ROOT
        v.ROOT = self.root
        self.addCleanup(lambda: setattr(v, "ROOT", self._orig))

    def _plugin(self, name: str) -> Path:
        d = self.root / name
        (d / ".claude-plugin").mkdir(parents=True, exist_ok=True)
        (d / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": name, "version": "1.0.0"}), encoding="utf-8")
        return d

    def _command(self, plugin: Path, stem: str, desc: str) -> None:
        _write(plugin, f"commands/{stem}.md", f"---\ndescription: {desc}\n---\n\nbody\n")

    def _skill(self, plugin: Path, name: str, desc: str) -> None:
        _write(plugin, f"skills/{name}/SKILL.md",
               f"---\nname: {name}\ndescription: {desc}\n---\n\nbody\n")

    def _visible(self) -> dict[str, str]:
        return {label: text for label, _path, text in v.router_visible_descriptions()}

    def test_same_name_hides_the_skill_description(self):
        """同名ペアで載るのは commands 側だけ（#205 の 6/6 恒常 fail の原因）."""
        plug = self._plugin("demo")
        self._command(plug, "thing", "COMMAND SIDE")
        self._skill(plug, "thing", "SKILL SIDE")
        self.assertEqual(self._visible(), {"demo:thing": "COMMAND SIDE"})

    def test_differently_named_pairs_expose_both(self):
        """名前が衝突しなければ両方載る（同名時の非対称の裏取りになっている観測）."""
        plug = self._plugin("demo")
        self._command(plug, "do-thing", "COMMAND SIDE")
        self._skill(plug, "thing-doer", "SKILL SIDE")
        self.assertEqual(self._visible(),
                         {"demo:do-thing": "COMMAND SIDE", "demo:thing-doer": "SKILL SIDE"})

    def test_a_command_without_a_skill_is_counted(self):
        """command 単独のプラグイン（feature-dev / plugin-manager）も常駐する."""
        plug = self._plugin("demo")
        self._command(plug, "solo", "COMMAND SIDE")
        self.assertEqual(self._visible(), {"demo:solo": "COMMAND SIDE"})

    def test_a_directory_without_a_manifest_is_skipped(self):
        """docs/ や evals/ をプラグインとして数えない."""
        (self.root / "docs" / "commands").mkdir(parents=True)
        _write(self.root / "docs", "commands/x.md", "---\ndescription: NOT A PLUGIN\n---\n")
        self.assertEqual(self._visible(), {})

    def test_a_block_scalar_description_drops_the_indicator(self):
        """`description: >` の `>` は値ではないので字数に数えない."""
        plug = self._plugin("demo")
        _write(plug, "skills/folded/SKILL.md",
               "---\nname: folded\ndescription: >\n  first line\n  second line\n---\n\nbody\n")
        self.assertEqual(self._visible(), {"demo:folded": "first line second line"})


class ContextBudgetTest(unittest.TestCase):
    """常駐 description の予算（GitHub issue #206 で分母を実態に合わせた）.

    旧実装は `SKILL.md` だけを数えていたので、**同名 26 スキルぶんを過大計上する一方
    commands 側には上限が一つも掛かっていなかった**。そのずれは実際に空振りを生んで
    いる（`6138179` は削減 1,564 chars の 88%、`fa16377` は 722 chars の 80% が
    そもそも常駐しないテキストだった）。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self._orig = v.ROOT
        v.ROOT = self.root
        self.addCleanup(lambda: setattr(v, "ROOT", self._orig))
        self.plugin = self.root / "demo"
        (self.plugin / ".claude-plugin").mkdir(parents=True)
        (self.plugin / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "demo", "version": "1.0.0"}), encoding="utf-8")

    def _run(self) -> list[str]:
        warnings: list[str] = []
        v.check_context_budget(warnings)
        return warnings

    def _pair(self, name: str, cmd_len: int, skill_len: int) -> None:
        _write(self.plugin, f"commands/{name}.md",
               "---\ndescription: " + "c" * cmd_len + "\n---\n\nbody\n")
        _write(self.plugin, f"skills/{name}/SKILL.md",
               f"---\nname: {name}\ndescription: " + "s" * skill_len + "\n---\n\nbody\n")

    def test_a_shadowed_skill_description_is_not_measured(self):
        """同名 skill の description は常駐しないので上限を超えても鳴らない."""
        self._pair("thing", cmd_len=10, skill_len=v.SKILL_DESC_CHAR_LIMIT + 1)
        self.assertEqual(self._run(), [])

    def test_a_command_description_is_measured(self):
        """commands 側にも単体上限が掛かる（旧実装はここを一切見ていなかった）."""
        self._pair("thing", cmd_len=v.SKILL_DESC_CHAR_LIMIT + 1, skill_len=10)
        warnings = self._run()
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn("commands/thing.md", warnings[0])

    def test_exactly_at_the_limit_is_accepted(self):
        """境界の片側だけ測ると `>` と `>=` の取り違えが素通りする."""
        self._pair("thing", cmd_len=v.SKILL_DESC_CHAR_LIMIT, skill_len=10)
        self.assertEqual(self._run(), [])

    def test_an_unshadowed_skill_description_is_measured(self):
        _write(self.plugin, "skills/solo/SKILL.md",
               "---\nname: solo\ndescription: " + "s" * (v.SKILL_DESC_CHAR_LIMIT + 1)
               + "\n---\n\nbody\n")
        warnings = self._run()
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn("skills/solo/SKILL.md", warnings[0])

    def test_the_total_counts_only_what_resides(self):
        """合計は「commands 全部 + 非同名 skill」。同名 skill は分母に入れない."""
        self._pair("thing", cmd_len=100, skill_len=v.SKILL_DESC_TOTAL_LIMIT)
        self.assertEqual([w for w in self._run() if "合計" in w], [])

    def test_the_total_exactly_at_the_limit_is_accepted(self):
        """合計側も境界の片側だけ測ると `>` と `>=` の取り違えが素通りする."""
        half = v.SKILL_DESC_TOTAL_LIMIT // 2
        _write(self.plugin, "commands/a.md", "---\ndescription: " + "c" * half + "\n---\n")
        _write(self.plugin, "commands/b.md",
               "---\ndescription: " + "c" * (v.SKILL_DESC_TOTAL_LIMIT - half) + "\n---\n")
        self.assertEqual([w for w in self._run() if "合計" in w], [])

    def test_the_total_over_the_limit_warns(self):
        for i in range(3):
            _write(self.plugin, f"commands/c{i}.md",
                   "---\ndescription: " + "c" * (v.SKILL_DESC_TOTAL_LIMIT // 2) + "\n---\n")
        self.assertEqual(len([w for w in self._run() if "合計" in w]), 1)

    def test_the_repository_itself_is_within_the_budget(self):
        """**この分母に切り替えた時点で** repo 全体が予算内であること."""
        v.ROOT = self._orig
        self.assertEqual(self._run(), [])


class SameNameCommandTriggerTest(unittest.TestCase):
    """同名 command の description にも `トリガー:` を必須にする（GitHub issue #206）.

    同名ペアでは router に載るのは `commands/*.md` 側だけ（`router_visible_descriptions`）。
    SKILL.md にだけ `トリガー:` があっても選択挙動は変わらない。**SKILL 側の必須は残す** —
    `check_router_trigger_drift` が SKILL.md の `トリガー:` を入力にしており、移動すると
    その機械ガードが沈黙する（複製であって移動ではない）。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.plugin = Path(self._tmp.name) / "demo"
        _write(self.plugin, ".claude-plugin/plugin.json", '{"name": "demo", "version": "0.0.1"}')
        # エラー文は `relative_to(ROOT)` で相対化するので、一時ディレクトリを ROOT に向ける
        self._orig_root = v.ROOT
        v.ROOT = Path(self._tmp.name)
        self.addCleanup(lambda: setattr(v, "ROOT", self._orig_root))

    def _md(self, desc: str) -> str:
        return f"---\ndescription: {desc}\n---\n\nbody\n"

    def _run(self) -> list[str]:
        errors: list[str] = []
        v.check_trigger_phrases(self.plugin, errors)
        return errors

    def test_a_same_name_command_without_a_trigger_is_an_error(self):
        _write(self.plugin, "skills/thing/SKILL.md", self._md("説明 トリガー: 「A」"))
        _write(self.plugin, "commands/thing.md", self._md("説明だけ"))
        errors = self._run()
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("trigger-cmd:demo", errors[0])
        self.assertIn("commands/thing.md", errors[0])

    def test_a_same_name_command_with_a_trigger_is_clean(self):
        _write(self.plugin, "skills/thing/SKILL.md", self._md("説明 トリガー: 「A」"))
        _write(self.plugin, "commands/thing.md", self._md("説明 トリガー: 「A」"))
        self.assertEqual(self._run(), [])

    def test_a_command_without_a_same_name_skill_is_not_checked(self):
        """非同名の command は SKILL.md が router に見えるので対象外（欠陥が無い）."""
        _write(self.plugin, "skills/thing/SKILL.md", self._md("説明 トリガー: 「A」"))
        _write(self.plugin, "commands/other.md", self._md("説明だけ"))
        self.assertEqual(self._run(), [])

    def test_the_skill_side_requirement_is_kept(self):
        """複製であって移動ではない — SKILL 側の必須は残る（drift 検査の入力を消さない）."""
        _write(self.plugin, "skills/thing/SKILL.md", self._md("説明だけ"))
        _write(self.plugin, "commands/thing.md", self._md("説明 トリガー: 「A」"))
        errors = self._run()
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("[trigger:demo]", errors[0])


class RouterTriggerDriftTest(unittest.TestCase):
    """同名ペアで `SKILL.md` のトリガーフレーズだけを直した変更の検出（issue #206 案 B）.

    水準は履歴で測って決めた: 素朴な案（トリガー代表語が command description にあるか）は
    同名 26 件中 12 件で鳴る一方、実害の無い対照群でも 10 件中 6 件で鳴って判別して
    いなかった。本検査は 498 コミット中 9 コミット・15 ペアで鳴り、**うち 1 件が
    #205 の混入コミット `a3c6ad3` そのもの**。

    比較基準の取得（`text_at_base`）は差し替える。ここで確かめたいのは git の引き方では
    なく「何に鳴って何に黙るか」の判断。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self._orig = v.ROOT
        v.ROOT = self.root
        self.addCleanup(lambda: setattr(v, "ROOT", self._orig))
        self.plugin = self.root / "demo"
        (self.plugin / ".claude-plugin").mkdir(parents=True)
        (self.plugin / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "demo", "version": "1.0.0"}), encoding="utf-8")
        self.base: dict[str, str] = {}
        self._orig_base = v.text_at_base
        v.text_at_base = lambda path: self.base.get(path.relative_to(v.ROOT).as_posix())
        self.addCleanup(lambda: setattr(v, "text_at_base", self._orig_base))

    def _md(self, desc: str) -> str:
        return f"---\ndescription: {desc}\n---\n\nbody\n"

    def _setup(self, *, cmd_now, cmd_base, skill_now, skill_base, name="thing",
               skill_dir=None) -> None:
        skill_dir = skill_dir or name
        _write(self.plugin, f"commands/{name}.md", self._md(cmd_now))
        _write(self.plugin, f"skills/{skill_dir}/SKILL.md", self._md(skill_now))
        if cmd_base is not None:
            self.base[f"demo/commands/{name}.md"] = self._md(cmd_base)
        if skill_base is not None:
            self.base[f"demo/skills/{skill_dir}/SKILL.md"] = self._md(skill_base)

    def _run(self) -> list[str]:
        warnings: list[str] = []
        v.check_router_trigger_drift(warnings)
        return warnings

    def test_a_trigger_added_only_to_the_skill_warns(self):
        """#205 の型: 逐語トリガーを SKILL.md にだけ足した変更."""
        self._setup(cmd_now="取り込む", cmd_base="取り込む",
                    skill_now="説明 トリガー: 「A」「B」", skill_base="説明 トリガー: 「A」")
        warnings = self._run()
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn("router-drift", warnings[0])
        self.assertIn("'B'", warnings[0])
        self.assertIn("commands/thing.md", warnings[0])

    def test_a_trigger_removed_only_from_the_skill_warns(self):
        self._setup(cmd_now="取り込む", cmd_base="取り込む",
                    skill_now="説明 トリガー: 「A」", skill_base="説明 トリガー: 「A」「B」")
        self.assertEqual(len(self._run()), 1)

    def test_editing_both_sides_is_silent(self):
        """対で直したなら黙る（案 A で決めた規約を満たしている）."""
        self._setup(cmd_now="取り込む NEW", cmd_base="取り込む",
                    skill_now="説明 トリガー: 「A」「B」", skill_base="説明 トリガー: 「A」")
        self.assertEqual(self._run(), [])

    def test_an_unchanged_trigger_set_is_silent(self):
        """散文だけ直したのは対象外（鳴らすと 44 件に膨らんで判別が落ちる）."""
        self._setup(cmd_now="取り込む", cmd_base="取り込む",
                    skill_now="説明を書き直した トリガー: 「A」", skill_base="説明 トリガー: 「A」")
        self.assertEqual(self._run(), [])

    def test_reordering_the_same_triggers_is_silent(self):
        """集合で比べる（並べ替えは選択挙動を変えない）."""
        self._setup(cmd_now="取り込む", cmd_base="取り込む",
                    skill_now="説明 トリガー: 「B」「A」", skill_base="説明 トリガー: 「A」「B」")
        self.assertEqual(self._run(), [])

    def test_a_differently_named_pair_is_silent(self):
        """非同名なら SKILL.md の description も router に載るので実害が無い."""
        self._setup(cmd_now="c", cmd_base="c",
                    skill_now="説明 トリガー: 「A」「B」", skill_base="説明 トリガー: 「A」",
                    name="do-thing", skill_dir="thing-doer")
        self.assertEqual(self._run(), [])

    def test_a_new_skill_is_silent(self):
        """基準に無い新規 skill は「直した」ではないので黙る."""
        self._setup(cmd_now="c", cmd_base="c",
                    skill_now="説明 トリガー: 「A」", skill_base=None)
        self.assertEqual(self._run(), [])

    def test_a_skill_without_a_trigger_section_is_silent(self):
        """`トリガー:` を持たない側は比較できない（不在は error 側の担当）."""
        self._setup(cmd_now="c", cmd_base="c",
                    skill_now="説明だけ", skill_base="説明 トリガー: 「A」")
        self.assertEqual(self._run(), [])

    def test_the_repository_is_clean_against_head(self):
        """作業ツリーと HEAD が同じなら鳴らない（毎ターン鳴る warning にしない）."""
        v.ROOT = self._orig
        v.text_at_base = self._orig_base
        self.assertEqual(self._run(), [])


class TriggerPhrasesTest(unittest.TestCase):
    """`トリガー:` 節の逐語フレーズ抽出."""

    def test_missing_section_is_none(self):
        self.assertIsNone(v.trigger_phrases("説明だけ"))

    def test_none_input_is_none(self):
        self.assertIsNone(v.trigger_phrases(None))

    def test_phrases_before_the_section_are_ignored(self):
        """`トリガー:` より前の鉤括弧はトリガーではない."""
        self.assertEqual(v.trigger_phrases("「用語」の説明 トリガー: 「A」"), frozenset({"A"}))

    def test_double_angle_brackets_are_collected(self):
        self.assertEqual(v.trigger_phrases("x トリガー: 『A』「B」"), frozenset({"A", "B"}))

    def test_a_section_without_phrases_is_an_empty_set(self):
        """空集合と None を潰さない（前者は「宣言はあるが空」）."""
        self.assertEqual(v.trigger_phrases("x トリガー: なし"), frozenset())

if __name__ == "__main__":
    unittest.main()
