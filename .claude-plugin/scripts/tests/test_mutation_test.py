#!/usr/bin/env python3
"""`mutation-test.py` 自身の回帰テスト.

**このツールは「検証コードの検証が無い」問題への対応なのに、自分自身が無検証だった**
（セルフレビューの MAJOR 指摘）。指標を計算するツールが静かに壊れると、
`changed_lines` が空を返すだけで「変異対象の変更行が無い」＝生存 0%＝満点に見え、
exit 0 で通る。

**特に `apply_and_test` の復元経路は、失敗するとユーザーの未コミット変更が消える**。
docstring 自身が「実測で事故った」と書いている箇所なので、ここを厚く見る。

実行: python3 -m unittest discover -s .claude-plugin/scripts/tests
"""

from __future__ import annotations

import importlib.util
import os
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "mutation-test.py"


def _load():
    # ハイフン付きファイル名なので importlib 経由。**`sys.modules` へ先に登録する** —
    # 登録前に exec すると Python 3.14 で `@dataclass` が AttributeError で落ちる
    spec = importlib.util.spec_from_file_location("_mutation_test_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mt = _load()


class CodeEndTest(unittest.TestCase):
    """行末コメントの判定（`#` の扱い）."""

    def test_trailing_comment_is_excluded(self):
        line = "FC_MIN = 1    # `>=` で前方互換にする"
        self.assertEqual(mt._code_end(line), line.index("#"))

    def test_bash_positional_count_is_not_a_comment(self):
        """`$#` はコメントではない（実測でここが `-gt` を丸ごと未計測にしていた）."""
        line = "while [ $# -gt 0 ]; do"
        self.assertEqual(mt._code_end(line), len(line))

    def test_anchor_in_a_path_is_not_a_comment(self):
        line = 'echo "see doc.md#anchor"'
        self.assertEqual(mt._code_end(line), len(line))

    def test_hash_inside_a_string_is_not_a_comment(self):
        line = 'x = "a >= b # not a comment"'
        self.assertEqual(mt._code_end(line), len(line))


class BuildMutantsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _file(self, name: str, body: str) -> Path:
        p = self.root / name
        p.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
        return p

    def _rules(self, path: Path) -> list[str]:
        n = len(path.read_text().splitlines())
        return [m.rule for m in mt.build_mutants({path: set(range(1, n + 1))})]

    def test_docstring_prose_is_not_mutated(self):
        """**複数行文字列の散文は変異させない**（書き換えても落ちない＝ 100% 生存の偽陽性）."""
        p = self._file("a.py", '''
            def f(a):
                """説明.

                a >= 1 のとき True を返す（散文）。
                """
                return a >= 1
            ''')
        # 実コード行の 1 個だけ（docstring 内の `>=` と `True` は出ない）
        self.assertEqual(self._rules(p), [">= を > に（境界を 1 つ狭める）"])

    def test_multiline_string_start_column_is_respected(self):
        """**複数行文字列の開始行は「開始桁より前」を守る**（変異ランで生き残った境界）.

        `lo = scol if ln == srow else 0` を反転すると、開始行の桁が 0 になって
        **文字列より前にあるコードまで除外される**。ここに実コードを置いて固定する。
        """
        p = self._file("g.py", '\n            x = 1 if a >= b else """\n            散文の中の c >= d\n            """\n            ')
        # **行番号まで固定する**: 規則名だけ見ると、1 行目が除外されて 2 行目の散文から
        # 同じ規則が出ても同一リストになり、境界の反転を検知できない（実測でここを踏んだ）
        got = [(m.lineno, m.rule) for m in mt.build_mutants({p: {1, 2, 3}})]
        self.assertEqual(got, [(1, ">= を > に（境界を 1 つ狭める）")])

    def test_sh_falls_back_to_the_approximation(self):
        """`.sh` は tokenize が使えないので近似（`_code_end`）に落ちること.

        `masked is not None` を反転すると .sh が「tokenize 済み」扱いになり、
        行末コメント内まで変異対象になる。
        """
        p = self._file("h.sh", 'x=1   # a >= b はコメント\n[ "$n" -ge 2 ] || exit 2\n')
        rules = self._rules(p)
        self.assertNotIn(">= を > に（境界を 1 つ狭める）", rules, "コメント内を変異させている")
        self.assertIn("-ge を -gt に（bash の境界を 1 つ狭める）", rules)

    def test_comment_only_line_is_skipped(self):
        p = self._file("b.py", "# a >= 1 のとき\nx = 1\n")
        self.assertEqual(self._rules(p), [])

    def test_mutation_ok_marker_skips_the_line(self):
        p = self._file("c.py", "x = 1 if y >= 2 else 0  # mutation-ok: 等価変異\n")
        self.assertEqual(self._rules(p), [])

    def test_bash_argument_guard_is_covered(self):
        """`while [ $# -gt 0 ]` は bash の fail-open ゲートの最頻形（実測で 0 個だった）."""
        p = self._file("d.sh", "while [ $# -gt 0 ]; do\n  shift\ndone\n")
        self.assertIn("-gt を -ge に（bash の境界を 1 つ広げる）", self._rules(p))

    def test_one_mutant_per_rule_not_per_line(self):
        """**1 行から規則数ぶんの変異が出る**（コメントが「1 行 1 規則」と誤記していた）."""
        p = self._file("e.py", "if a >= b and c == d:\n    pass\n")
        rules = self._rules(p)
        self.assertEqual(len(rules), 3, rules)      # >= / == / and

    def test_same_rule_twice_on_a_line_yields_one(self):
        """同一規則の 2 個目は変異されない（既知の制約。仕様として固定する）."""
        p = self._file("f.py", "if a >= b and c >= d:\n    pass\n")
        self.assertEqual(sum(1 for r in self._rules(p) if r.startswith(">=")), 1)

    def test_test_files_are_excluded(self):
        """テストは判定者であって被験者ではない."""
        self.assertTrue(mt.is_test_file(Path("x/tests/test_a.py")))
        self.assertTrue(mt.is_test_file(Path("x/a_test.py")))
        self.assertFalse(mt.is_test_file(Path("x/scripts/mutation-test.py")))


class ApplyAndTestTest(unittest.TestCase):
    """**復元経路**（失敗するとユーザーの未コミット変更が消える）."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self._orig_root = mt.ROOT
        mt.ROOT = self.root
        self.addCleanup(lambda: setattr(mt, "ROOT", self._orig_root))
        self.target = self.root / "target.py"
        self.target.write_text("x = 1\nif a >= b:\n    pass\n", encoding="utf-8")
        self.original = self.target.read_bytes()

    def _mutant(self) -> mt.Mutant:
        return mt.Mutant(self.target, 2, "if a >= b:", "if a > b:", "テスト用")

    def test_restores_the_original_bytes(self):
        v = mt.apply_and_test(self._mutant(), ["true"], 30)
        self.assertEqual(v, "survived")
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_failing_tests_are_killed_and_restored(self):
        v = mt.apply_and_test(self._mutant(), ["false"], 30)
        self.assertEqual(v, "killed")
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_timeout_is_its_own_verdict(self):
        """**hang は想定内**（`break` → `continue` の変異は無限ループを作りうる）.

        1 個の hang で run 全体を落とすと残りが未実行のままサマリも出ない。
        """
        v = mt.apply_and_test(self._mutant(), ["sleep", "5"], 1)
        self.assertEqual(v, "timeout")
        self.assertEqual(self.target.read_bytes(), self.original, "タイムアウトでも復元される")

    def test_external_edit_is_not_overwritten(self):
        """**外部が編集していたら書き戻さない**（黙って作業を消さない）."""
        script = self.root / "edit.sh"
        script.write_text('printf "\\n# 外部からの追記\\n" >> "%s"\n' % self.target, encoding="utf-8")
        with self.assertRaises(mt.ExternalEditError):
            mt.apply_and_test(self._mutant(), ["bash", str(script)], 30)
        body = self.target.read_text(encoding="utf-8")
        self.assertIn("外部からの追記", body, "外部の編集が消えている")

    def test_external_edit_message_carries_recovery_info(self):
        """**復旧に必要な情報を全部出す**（行番号 + 元テキスト）.

        「`git diff` で確認」だけだと実際に見落とし、変異が残ったまま次の run の
        baseline を壊した（実測）。
        """
        script = self.root / "edit2.sh"
        script.write_text('printf "\n# 追記\n" >> "%s"\n' % self.target, encoding="utf-8")
        with self.assertRaises(mt.ExternalEditError) as cm:
            mt.apply_and_test(self._mutant(), ["bash", str(script)], 30)
        msg = str(cm.exception)
        self.assertIn("target.py:2", msg)
        self.assertIn("if a >= b:", msg)      # 元のテキスト
        self.assertIn("if a > b:", msg)       # 変異後のテキスト

    def test_readonly_file_no_longer_blocks_the_write(self):
        """**アトミック書き込みにしたので読み取り専用ファイルでも変異できる**.

        旧実装（`write_text`）はここで `PermissionError` を出し、`finally` が
        「外部から変更された」と**誤診断**していた。`os.replace` は対象ファイルの権限では
        なくディレクトリの権限で決まるので、この失敗経路自体が消えた。
        """
        os.chmod(self.target, stat.S_IRUSR)
        self.addCleanup(lambda: os.chmod(self.target, stat.S_IRUSR | stat.S_IWUSR))
        self.assertEqual(mt.apply_and_test(self._mutant(), ["true"], 30), "survived")
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_write_failure_propagates_the_real_exception(self):
        """**書けなかった回に「外部から変更された」と誤診断しない**.

        誤診断は原因の調査先を誤らせるうえ、`SystemExit` は CPython が特別扱いするので
        真の例外が表示されずに消える。書けていないなら整合ガードを通さず素通しする。
        """
        sub = self.root / "ro"
        sub.mkdir()
        target = sub / "t.py"
        target.write_text("if a >= b:\n    pass\n", encoding="utf-8")
        before = target.read_bytes()
        os.chmod(sub, stat.S_IRUSR | stat.S_IXUSR)          # ディレクトリを書込不可に
        self.addCleanup(lambda: os.chmod(sub, stat.S_IRWXU))
        m = mt.Mutant(target, 1, "if a >= b:", "if a > b:", "テスト用")
        with self.assertRaises(OSError) as cm:
            mt.apply_and_test(m, ["true"], 30)
        self.assertNotIsInstance(cm.exception, mt.ExternalEditError)
        self.assertEqual(target.read_bytes(), before, "書けていないのに原本が変わった")

    def test_partial_write_cannot_truncate_the_original(self):
        """**アトミック書き込み**（`write_text` は先に truncate するので途中失敗で原本が壊れる）."""
        mt._atomic_write(self.target, b"new content")
        self.assertEqual(self.target.read_bytes(), b"new content")
        self.assertFalse(list(self.root.glob("*.mutant.tmp")), "一時ファイルが残っている")


class ChangedLinesTest(unittest.TestCase):
    """diff の追加行の拾い方（ここが静かに壊れると「対象なし」＝満点に見える）."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self._orig_root, self._orig_run = mt.ROOT, mt.run
        mt.ROOT = self.root
        self.addCleanup(lambda: (setattr(mt, "ROOT", self._orig_root),
                                 setattr(mt, "run", self._orig_run)))

    def _diff(self, text: str) -> dict:
        class _P:
            stdout = textwrap.dedent(text).lstrip()
        mt.run = lambda *a, **k: _P()
        return {p.name: sorted(v) for p, v in mt.changed_lines("HEAD").items()}

    def test_multiple_hunks_keep_their_own_line_numbers(self):
        got = self._diff("""
            +++ b/pkg/a.py
            @@ -2,0 +3 @@
            +x = 1
            @@ -20,0 +22,2 @@
            +y = 2
            +z = 3
            """)
        self.assertEqual(got, {"a.py": [3, 22, 23]})

    def test_test_files_are_not_targeted(self):
        got = self._diff("""
            +++ b/pkg/tests/test_a.py
            @@ -1,0 +2 @@
            +x = 1
            """)
        self.assertEqual(got, {})

    def test_non_target_suffix_is_ignored(self):
        got = self._diff("""
            +++ b/README.md
            @@ -1,0 +2 @@
            +文章
            """)
        self.assertEqual(got, {})


if __name__ == "__main__":
    unittest.main()
