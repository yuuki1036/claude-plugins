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
  python3 -m unittest discover -s .claude-plugin/scripts/tests
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "validate_plugin_quality.py"


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


if __name__ == "__main__":
    unittest.main()
