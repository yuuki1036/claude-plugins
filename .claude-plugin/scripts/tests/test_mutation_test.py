#!/usr/bin/env python3
"""`mutation-test.py` 自身の回帰テスト.

**このツールは「検証コードの検証が無い」問題への対応なのに、自分自身が無検証だった**
（セルフレビューの MAJOR 指摘）。指標を計算するツールが静かに壊れると、
`changed_lines` が空を返すだけで「変異対象の変更行が無い」＝生存 0%＝満点に見え、
exit 0 で通る。

**特に `apply_and_test` の復元経路は、失敗するとユーザーの未コミット変更が消える**。
docstring 自身が「実測で事故った」と書いている箇所なので、ここを厚く見る。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
import textwrap
import time
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
        # 同じ規則が出ても同一リストになり、境界の反転を検知できない（実測でここを踏んだ）。
        # 1 行目の条件式には条件式の規則も当たるので `>=` の規則に絞る
        got = [(m.lineno, m.rule) for m in mt.build_mutants({p: {1, 2, 3}})
               if m.rule.startswith(">=")]
        self.assertEqual(got, [(1, ">= を > に（境界を 1 つ狭める）")])

    def test_fstring_content_is_not_mutated(self):
        """**f-string の中身も伏せる**（3.12 以降は STRING ではなく FSTRING_* で出る / 3.14 で実測）.

        入れ子の f-string の後ろにも外側の散文が続く形にして、内側の終了で範囲を閉じないことも見る。
        """
        p = self._file("i.py", '''
            x = f"{a} {f'{b}'} does not exist, a >= b"
            y = rf"(?:<[^<>]*>)"
            z = not w
            ''')
        got = [(m.lineno, m.rule) for m in mt.build_mutants({p: {1, 2, 3}})]
        self.assertEqual(got, [(3, "not を外す（条件を反転）")])

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


class SpreadTest(unittest.TestCase):
    """`--max` で切るときにファイルが偏らないこと（push 側の CI は浅く回すため）."""

    @staticmethod
    def _m(name: str, lineno: int):
        return mt.Mutant(path=Path(name), lineno=lineno, original="x", mutated="y", rule="r")

    def test_files_are_interleaved(self):
        mutants = [self._m("a.sh", i) for i in range(1, 4)]
        mutants += [self._m("b.sh", i) for i in range(1, 4)]
        got = [m.path.name for m in mt.spread(mutants)]
        self.assertEqual(got, ["a.sh", "b.sh", "a.sh", "b.sh", "a.sh", "b.sh"])

    def test_the_first_n_cover_every_file(self):
        """**先頭 N 件で全ファイルに触れる**のが目的（偏ると片方が無検証のまま緑になる）."""
        mutants = [self._m("%d.sh" % f, i) for f in range(4) for i in range(1, 6)]
        head = mt.spread(mutants)[:4]
        self.assertEqual(sorted(m.path.name for m in head),
                         ["0.sh", "1.sh", "2.sh", "3.sh"])

    def test_uneven_counts_do_not_drop_mutants(self):
        mutants = [self._m("a.sh", i) for i in range(1, 5)] + [self._m("b.sh", 1)]
        self.assertEqual(len(mt.spread(mutants)), 5, "並べ替えで落ちている")


class ShellRedirectTest(unittest.TestCase):
    """シェルの `>` はリダイレクトであって比較ではない.

    `2>/dev/null` を `2>=/dev/null` にしても**テストが落ちない**ので生存扱いになるが、
    これは「検証していない挙動」ではなく偽の生存。生存リストは行動を促す信号なので、
    ここにノイズが混ざると一覧そのものが読まれなくなる（実測で 2/10 が偽の生存だった）。
    """

    def _rules(self, path: Path):
        return [m.rule for m in mt.build_mutants(
            {path: set(range(1, len(path.read_text().splitlines()) + 1))})]

    def test_redirects_are_not_mutated(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.sh"
            p.write_text("jq -r .a f 2>/dev/null || true\necho hi > out.log\ncat <in.txt\n")
            self.assertEqual([r for r in self._rules(p) if ">" in r or "<" in r], [])

    def test_command_flags_are_not_mutated_as_comparisons(self):
        """`ls -lt` の `-lt` は**フラグ**。変異させると `ls -le` という有効な別コマンドになり、
        テストは落ちないので偽の生存が並ぶ（実測: `measure-tokens.sh` の `ls -lt`）。
        """
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.sh"
            p.write_text('ls -lt "${FILES[@]}" | head -20\nsort -n out.txt\n')
            self.assertEqual([r for r in self._rules(p) if "-lt" in r or "-le" in r], [])

    def test_numeric_comparison_in_a_test_expression_is_mutated(self):
        """`[ ... ]` / `test ...` の中の `-lt` は比較なので変異させる（両側から測る）."""
        for src in ('if [ "$n" -lt 3 ]; then echo x; fi\n',
                    'if [[ "$n" -lt 3 ]]; then echo x; fi\n',
                    'if test "$n" -lt 3; then echo x; fi\n'):
            with self.subTest(src=src.strip()):
                with tempfile.TemporaryDirectory() as d:
                    p = Path(d) / "x.sh"
                    p.write_text(src)
                    self.assertTrue(any("-lt を -le に" in r for r in self._rules(p)))

    def test_numeric_comparison_in_python_is_unaffected_by_the_shell_guard(self):
        """`.py` の `==` は素通し（この抑制は `-lt` 系の綴りにだけ効く）."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.py"
            p.write_text('flag = "-lt"\nif n == 1:\n    pass\n')
            rules = self._rules(p)
            self.assertTrue(any("== を != に" in r for r in rules))
            # `.py` の文字列に入っている `-lt` も test 式の外なので変異させない
            self.assertFalse(any("-lt を -le に" in r for r in rules))

    def test_comparison_inside_double_brackets_is_mutated(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.sh"
            p.write_text('if [[ "$a" > "$b" ]]; then echo x; fi\n')
            self.assertTrue(any("> を >= に" in r for r in self._rules(p)))

    def test_arithmetic_comparison_is_mutated(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.sh"
            p.write_text("if (( count > limit )); then echo x; fi\n")
            self.assertTrue(any("> を >= に" in r for r in self._rules(p)))

    def test_python_comparison_is_unaffected(self):
        """この抑制は .sh 限定（.py の `>` は比較）."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.py"
            p.write_text("if count > limit:\n    pass\n")
            self.assertTrue(any("> を >= に" in r for r in self._rules(p)))

    def test_shell_numeric_test_operators_still_mutate(self):
        """`-gt` 等は文脈に関係なく比較."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.sh"
            p.write_text('[ "$n" -gt 3 ] && echo big\n')
            self.assertTrue(any("-gt" in r for r in self._rules(p)))


class PythonBranchRulesTest(unittest.TestCase):
    """Python の分岐の形（`not` / 条件式 / `any`・`all` / `continue` / 早期 return）.

    RULES が比較演算子と and/or だけだった頃、Python の分岐 55 行に「変異 0 個」を返し、
    生存 0 が検証済みに見えた（実測 2026-10-07）。**変異が出ること**と、**同じ綴りの別物
    （`not in` / `is not` / 行頭の if 文 / 複数行の return）に当たらないこと**の両側を見る。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _mutants(self, name: str, body: str):
        p = self.root / name
        p.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
        n = len(p.read_text().splitlines())
        return [(m.lineno, m.rule, m.mutated.strip()) for m in mt.build_mutants({p: set(range(1, n + 1))})]

    def _of(self, mutants, rule_prefix: str):
        return [(ln, mutated) for ln, rule, mutated in mutants if rule.startswith(rule_prefix)]

    def test_not_is_removed(self):
        got = self._mutants("a.py", """
            if not x:
                pass
            y = not(z)
            """)
        self.assertEqual(self._of(got, "not を外す"), [(1, "if x:"), (3, "y = (z)")])

    def test_not_in_and_is_not_are_left_to_their_own_rules(self):
        """`not in` / `is not` から `not` だけを外すと既存の規則と重複する（別物にもなる）."""
        got = self._mutants("a.py", """
            if a not in b:
                pass
            if a is not b:
                pass
            """)
        self.assertEqual(self._of(got, "not を外す"), [])
        self.assertEqual(len(self._of(got, "not in を in に")), 1)
        self.assertEqual(len(self._of(got, "is not を is に")), 1)

    def test_any_and_all_are_swapped(self):
        got = self._mutants("a.py", """
            ok = any(x for x in xs)
            ng = all(x for x in xs)
            ar = arr.any()
            """)
        self.assertEqual(self._of(got, "any を all に"), [(1, "ok = all(x for x in xs)")])
        self.assertEqual(self._of(got, "all を any に"), [(2, "ng = any(x for x in xs)")])

    def test_conditional_expression_is_inverted_but_if_statement_is_not(self):
        got = self._mutants("a.py", """
            if c:
                y = a if c else b
            z = a if not c else b
            """)
        self.assertEqual(self._of(got, "条件式の条件を反転"), [(2, "y = a if not c else b")],
                         "行頭の if 文と、既に not の付いた条件式には当てない")

    def test_continue_becomes_pass_in_python(self):
        got = self._mutants("a.py", """
            for x in xs:
                if x:
                    continue
                if y: continue
            """)
        self.assertEqual(self._of(got, "continue を pass に"), [(3, "pass"), (4, "if y: pass")])

    def test_early_return_directly_under_if_becomes_pass(self):
        got = self._mutants("a.py", """
            def f(x):
                if x:
                    # コメントを挟んでも if 直下とみなす
                    return ")"
                elif x is None: return 2
                return 3
            """)
        self.assertEqual(self._of(got, "if 直下の return"),
                         [(4, "pass"), (5, "elif x is None: pass")])

    def test_return_not_directly_under_if_is_left_alone(self):
        """if 直下でない return と、行で閉じない return は外さない（後者は構文エラーの変異になる）."""
        got = self._mutants("a.py", """
            def f(x):
                if x:
                    y = 1
                    return y
                else:
                    return 0
            def g(x):
                if x:
                    return (1,
                            2)
                if x: return \\
                    3
            """)
        self.assertEqual(self._of(got, "if 直下の return"), [])

    def test_return_on_the_first_line_has_no_header(self):
        self.assertEqual(self._of(self._mutants("a.py", "return 1\n"), "if 直下の return"), [])

    def test_untokenizable_python_still_gets_early_return(self):
        """tokenize できない（閉じていない三重引用符がある）ファイルでも近似で当てる."""
        got = self._mutants("a.py", """
            if x:
                return 1
            s = '''
            """)
        self.assertEqual(self._of(got, "if 直下の return"), [(2, "pass")])

    def test_python_rules_do_not_touch_bash(self):
        """`find -not` / jq の `if ... else` / bash の英文は python の構文ではない."""
        got = self._mutants("a.sh", """
            find . -not -path '*/x/*'
            jq '.a' f | if [ -n "$x" ]; then echo a; else echo b; fi
            echo "does not exist" >&2
            [ -f "$f" ] || continue
            """)
        rules = {rule for _, rule, _ in got}
        for prefix in ("not を外す", "条件式", "any を", "all を", "continue を pass", "if 直下"):
            self.assertFalse(any(r.startswith(prefix) for r in rules), prefix)
        self.assertEqual(self._of(got, "continue を : に"), [(4, '[ -f "$f" ] || :')])


class ShellEmbeddedPythonTest(unittest.TestCase):
    """`.sh` に埋め込まれた python（ヒアドキュメント / `python3 -c '...'`）.

    **docstring の散文を変異させない**（CLAUDE.md Gotchas「散文に `>=` / `<=` を書かない」の
    原因: 行内の近似は複数行文字列を追えず、散文の比較演算子が定義上 100% 生存する）ことと、
    **python の行には python の規則を当てる**ことを見る。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _mutants(self, body: str):
        p = self.root / "x.sh"
        p.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
        n = len(p.read_text().splitlines())
        return [(m.lineno, m.rule) for m in mt.build_mutants({p: set(range(1, n + 1))})]

    def test_heredoc_docstring_prose_is_not_mutated(self):
        got = self._mutants('''
            X="$1" python3 - "$2" <<'PY'
            """説明.

            a >= b のとき not で反転する（散文）。
            """
            if not x and a > b:
                pass
            PY
            [ -f "$f" ] || continue
            ''')
        self.assertEqual([ln for ln, _ in got if ln in (2, 3, 4, 5)], [], "docstring を変異させている")
        line6 = {rule for ln, rule in got if ln == 6}
        self.assertIn("not を外す（条件を反転）", line6)
        # bash のリダイレクト扱いにしない（python の `>` は比較）
        self.assertIn("> を >= に（境界を 1 つ広げる）", line6)
        self.assertIn((9, "continue を : に（読み飛ばしを外す）"), got, "終端の後は bash に戻る")

    def test_dash_c_body_is_python_but_its_boundary_lines_are_not(self):
        """`python3 -c '` の開始行・終了行は bash と同居するので python の行に数えない."""
        lines = textwrap.dedent('''
            V=$(printf x | python3 -c 'import sys
            if not sys.argv:
                pass
            print(1 if x else 2)') || V=""
            ''').lstrip("\n").splitlines()
        self.assertEqual(sorted(mt._sh_python_lines(lines)), [2, 3])

    def test_untokenizable_body_is_still_python(self):
        """tokenize できない塊（`$x` を展開する unquoted のヒアドキュメント等）も python の規則で見る."""
        lines = ["python3 <<PY", "x = '''", "if not y: pass", "PY"]
        spans = mt._sh_python_lines(lines)
        self.assertEqual(spans, {2: None, 3: None})

    def test_unclosed_dash_c_is_not_a_region(self):
        """閉じる `'` がどこにも無ければ領域にしない（その先の走査も止めない）."""
        lines = ["python3 -c 'import sys", "print(1)", "python3 <<PY", "x = 1", "PY"]
        self.assertEqual(mt._sh_python_lines(lines), {4: []})

    def test_here_string_is_not_a_region(self):
        self.assertEqual(mt._sh_python_lines(['python3 -c "$p" <<< "$x"', "if not y; then :; fi"]), {})


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

    def test_timeout_kills_the_whole_process_tree(self):
        """**孫プロセスを置き去りにしない.**

        `subprocess.run(timeout=...)` は直接の子だけを殺す。テストランナーが起動した
        被験スクリプトが変異で無限ループ化していると、そちらは生き残って回り続ける
        （実測: `triage-signals.sh` が **12 本・4 時間**、各 14% CPU で残っていた）。
        timeout は想定内の結果なので、後始末まで含めて想定内にする。

        ここでは「子が孫を産んでから自分は待つだけ」という構造を作り、timeout 後に
        **孫が生きていないこと**を pid で直接確かめる（`kill -0` 相当）。
        """
        marker = self.root / "grandchild.pid"
        script = self.root / "spawn.sh"
        script.write_text(
            "#!/usr/bin/env bash\n"
            # 孫: 自分の pid を書いてから延々と回る（無限ループ化した被験スクリプトの代役）
            "bash -c 'echo $$ > \"%s\"; while :; do sleep 0.2; done' &\n"
            "wait\n" % marker, encoding="utf-8")
        verdict = mt.apply_and_test(self._mutant(), ["bash", str(script)], 2)
        self.assertEqual(verdict, "timeout")
        self.assertTrue(marker.is_file(), "前提: 孫が起動して pid を書く")
        pid = int(marker.read_text().strip())
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except (ProcessLookupError, PermissionError):
                break                      # 回収済み
            time.sleep(0.1)
        else:
            os.kill(pid, 9)                # テストが CPU を焼き続けないよう始末する
            self.fail("孫プロセス %d が timeout 後も生きている" % pid)

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
        target = self.root / "t.py"
        target.write_text("if a >= b:\n    pass\n", encoding="utf-8")
        before = target.read_bytes()
        # 一時ファイルの位置を、存在しない dir を指す symlink で塞ぐ。dir を書込不可にする手は
        # root（クラウドのコンテナ）では権限を素通りして書けてしまうので使わない
        (self.root / "t.py.mutant.tmp").symlink_to(self.root / "missing" / "x")
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



class AtomicWriteTest(unittest.TestCase):
    def test_preserves_file_mode(self):
        """実行ビットを落とさない（落とすと `.sh` のガードが無言で外れる）.

        `write_bytes` は新しい inode を umask 既定で作り `os.replace` がメタデータごと
        差し替える。**バイト列は原本に戻るがモードは戻らない**ので、変異テストを
        1 回回すだけで `.githooks/` 配下の実行ビットが 755 → 644 に落ちていた。"""
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "hook.sh"
            f.write_text("echo ok\n")
            os.chmod(f, 0o755)
            mt._atomic_write(f, b"echo mutated\n")
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o755)
            mt._atomic_write(f, b"echo ok\n")
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o755)

    def test_keeps_non_executable_as_is(self):
        """644 のファイルを勝手に 755 にしない（逆方向の取り違えを防ぐ）."""
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "mod.py"
            f.write_text("x = 1\n")
            os.chmod(f, 0o644)
            mt._atomic_write(f, b"x = 2\n")
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o644)

    def test_no_tmp_file_left_behind(self):
        """一時ファイルを残さない（次回の走査対象に混ざる）."""
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "a.py"
            f.write_text("x = 1\n")
            mt._atomic_write(f, b"x = 2\n")
            self.assertEqual([p.name for p in Path(d).iterdir()], ["a.py"])


class JournalRecoveryTest(unittest.TestCase):
    """中断で残った変異をディスク経由で戻せること.

    復元は `try/finally` に閉じているので Python 例外は全部通るが、**SIGTERM / SIGHUP は
    `finally` を走らせない**。原本がプロセスメモリにしか無いと、その瞬間に
    「fail-open 方向へ書き換わった未コミットのファイル」が作業ツリーに残る。
    しかも変異は survived 型＝**テストが定義上検知しない**ので、緑のまま commit される。"""

    def setUp(self):
        self._orig_root = mt.ROOT
        # **周囲の env に依存させない**。このテスト群は変異 run の子プロセスとしても走るので,
        # 所有者マーカーが立ったまま復旧を期待すると baseline が赤くなる
        self._orig_owner = os.environ.get(mt.OWNER_ENV)
        os.environ[mt.OWNER_ENV] = str(os.getpid())
        self._tmp = tempfile.TemporaryDirectory()
        mt.ROOT = Path(self._tmp.name)
        self.target = mt.ROOT / "guard.sh"
        self.original = b"[ $# -gt 2 ] || exit 2\n"
        self.target.write_bytes(self.original)
        os.chmod(self.target, 0o755)

    def tearDown(self):
        mt.ROOT = self._orig_root
        os.environ.pop(mt.OWNER_ENV, None)
        if self._orig_owner is not None:
            os.environ[mt.OWNER_ENV] = self._orig_owner
        self._tmp.cleanup()

    def _leave_mutation(self):
        """「変異を書いた直後に殺された」状態を作る."""
        mt._journal_write(self.target, self.original)
        mt._atomic_write(self.target, b"[ $# -ge 2 ] || exit 2\n")

    def test_recovers_content_and_mode(self):
        self._leave_mutation()
        self.assertTrue(mt.recover_from_journal())
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o755)
        self.assertFalse(mt._journal_path().exists())

    def test_no_journal_is_a_noop(self):
        self.assertFalse(mt.recover_from_journal())

    def test_already_restored_only_clears_journal(self):
        """正常終了直後にジャーナルだけ残った場合は書き戻さない."""
        mt._journal_write(self.target, self.original)
        self.assertFalse(mt.recover_from_journal())
        self.assertFalse(mt._journal_path().exists())
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_live_owner_journal_is_left_alone(self):
        """実行中の run のジャーナルは触らない（自己干渉の回帰テスト）.

        テストコマンドがこのツール自身のテストを含むと, 子プロセスの起動時復旧が
        **親が当てている最中の変異を戻す**。親からは外部編集に見えて計測が止まる
        （実測: 9 変異中 0 件で中断した）。
        """
        self._leave_mutation()
        mutated = self.target.read_bytes()
        raw = json.loads(mt._journal_path().read_text())
        raw["pid"] = os.getpid() + 0          # 生存中の別 pid として自分自身を書く
        mt._journal_path().write_text(json.dumps(raw), encoding="utf-8")
        # 自分自身の pid は「自分が所有者」なので復旧してよい
        self.assertTrue(mt.recover_from_journal())

        self._leave_mutation()
        raw = json.loads(mt._journal_path().read_text())
        raw["pid"] = os.getppid()             # 親プロセス = 生存している別 pid
        mt._journal_path().write_text(json.dumps(raw), encoding="utf-8")
        self.assertFalse(mt.recover_from_journal(), "生存所有者のジャーナルは戻さない")
        self.assertEqual(self.target.read_bytes(), mutated, "他 run の変異を横取りしない")
        self.assertTrue(mt._journal_path().exists(), "他 run のジャーナルを消さない")

    def test_pid_alive_predicate(self):
        """生存判定そのものを直接測る（変異が harness 経由でしか効かないため）."""
        self.assertTrue(mt._pid_alive(os.getpid()))
        self.assertTrue(mt._pid_alive(os.getppid()))
        self.assertFalse(mt._pid_alive(2 ** 22))

    def test_owner_env_blocks_recovery(self):
        """親 run の実行中は子プロセスが復旧しない（env 経路）."""
        self._leave_mutation()
        mutated = self.target.read_bytes()
        old = os.environ.get(mt.OWNER_ENV)
        os.environ[mt.OWNER_ENV] = str(os.getpid() + 1)
        try:
            self.assertFalse(mt.recover_from_journal())
            self.assertEqual(self.target.read_bytes(), mutated)
        finally:
            os.environ.pop(mt.OWNER_ENV, None)
            if old is not None:
                os.environ[mt.OWNER_ENV] = old

    def test_owner_env_matching_self_allows_recovery(self):
        """自分が所有者なら復旧してよい（env が付いていても止めない）."""
        self._leave_mutation()
        old = os.environ.get(mt.OWNER_ENV)
        os.environ[mt.OWNER_ENV] = str(os.getpid())
        try:
            self.assertTrue(mt.recover_from_journal())
            self.assertEqual(self.target.read_bytes(), self.original)
        finally:
            os.environ.pop(mt.OWNER_ENV, None)
            if old is not None:
                os.environ[mt.OWNER_ENV] = old

    def test_dead_owner_journal_is_recovered(self):
        """所有者が死んでいれば戻す（SIGKILL / クラッシュ経路）."""
        self._leave_mutation()
        raw = json.loads(mt._journal_path().read_text())
        raw["pid"] = 2 ** 22                  # 存在しない pid
        mt._journal_path().write_text(json.dumps(raw), encoding="utf-8")
        self.assertTrue(mt.recover_from_journal())
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_journal_clear_is_idempotent(self):
        """ジャーナルが無くても落ちない（正常終了経路で二重に呼ばれる）."""
        mt._journal_clear()
        mt._journal_clear()
        self.assertFalse(mt._journal_path().exists())

    def test_missing_target_reports_and_does_not_claim_recovery(self):
        """対象が消えていたら「復旧した」と言わない（呼び出し側の判断が変わる）."""
        self._leave_mutation()
        self.target.unlink()
        self.assertFalse(mt.recover_from_journal())
        self.assertFalse(mt._journal_path().exists())

    def test_broken_journal_is_not_swallowed(self):
        """壊れたジャーナルは黙って消さない（消すと復旧手段が無くなる）."""
        self._leave_mutation()
        mt._journal_path().write_text("{ 壊れている", encoding="utf-8")
        self.assertFalse(mt.recover_from_journal())
        self.assertTrue(mt._journal_path().exists())

    def test_apply_and_test_clears_journal_on_success(self):
        """復元できた回はジャーナルを残さない（残ると次回に誤検出する）."""
        mutant = mt.Mutant(path=self.target, lineno=1, rule="test",
                           original="[ $# -gt 2 ] || exit 2",
                           mutated="[ $# -ge 2 ] || exit 2")
        mt.apply_and_test(mutant, ["true"], timeout=30)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertFalse(mt._journal_path().exists())


class RootContainmentTest(unittest.TestCase):
    """`--file` が repo 外を受け付けないこと.

    テストコマンドは repo 固定なので repo 外を変異させても全部 survived になり、
    「生存率 100%」という無意味な数字が出る。加えて表示・復旧経路が ROOT 相対前提で、
    `relative_to` が **メッセージを組み立てる前に** 例外を投げると
    「どのファイルの何行目が原本だったか」という復旧情報ごと消える。"""

    def test_rejects_path_outside_root(self):
        with tempfile.TemporaryDirectory() as d:
            outside = Path(d) / "x.py"
            outside.write_text("x = 1 > 2\n")
            rc = mt.main(["--file", str(outside)])
            self.assertEqual(rc, 2)

    def test_rel_does_not_raise_outside_root(self):
        """表示用パスは repo 外でも落ちない（復旧情報を守る最後の砦）."""
        self.assertEqual(mt._rel(Path("/nowhere/x.py")), "/nowhere/x.py")
        self.assertEqual(mt._rel(mt.ROOT / "a/b.py"), "a/b.py")

class ShellCmdGuardTest(unittest.TestCase):
    """`--test-cmd` の shell 構文を弾く（実測 2026-09-11）.

    `cd x && ...` は先頭の `cd` が exit 0 で終わるので、split して直接 spawn すると
    baseline が 0.0s で緑・全変異 SURVIVED という嘘の結果になる。**黙って緑にする経路**
    なので、baseline チェックの前に落とす。
    """

    def test_a_plain_unittest_command_is_accepted(self):
        for cmd in (mt.DEFAULT_TEST_CMD,
                    "python3 -m unittest discover -s x -p test_y.py -k SomeTest"):
            with self.subTest(cmd=cmd):
                self.assertIsNone(mt.shell_cmd_reason(cmd.split()))

    def test_leading_cd_is_rejected(self):
        """`cd x && ...` / `cd x; ...` の両方を先頭 cd で捕まえる（演算子の綴りに依らない）."""
        self.assertIsNotNone(mt.shell_cmd_reason("cd x && python3 -m unittest".split()))
        self.assertIsNotNone(mt.shell_cmd_reason("cd x; python3 -m unittest".split()))

    def test_shell_operators_are_rejected(self):
        for cmd in ("pytest | tee log", "a && b", "a || b", "run > out.txt"):
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(mt.shell_cmd_reason(cmd.split()))

    def test_empty_command_is_rejected(self):
        self.assertIsNotNone(mt.shell_cmd_reason([]))

    def test_main_rejects_shell_cmd_before_touching_files(self):
        """main() が shell 構文を **file 処理より前に** FATAL で落とす（順序の回帰）.

        repo 外のパスを渡すので、ガードを素通りした場合は「リポジトリ外」で落ちる。
        **stderr で判定する** — どちらの経路も exit 2 なので rc だけでは分岐の反転
        （`is not None` → `is None`）を殺せない。ガード非通過側も baseline を走らせない
        （SCRIPT 自身を --file にすると変異機構が再帰起動して結果が不安定になる）。
        """
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as d:
            outside = Path(d) / "x.py"
            outside.write_text("x = 1 > 2\n")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = mt.main(["--file", str(outside),
                              "--test-cmd", "cd foo && python3 -m unittest"])
            self.assertEqual(rc, 2)
            # shell ガードが先に鳴る（file 処理の「リポジトリ外」ではない）
            self.assertIn("shell 演算子", err.getvalue())
            self.assertNotIn("リポジトリ外", err.getvalue())


class BudgetTest(unittest.TestCase):
    """`--budget-sec`（実測: nightly が job timeout 180 分で cancelled になり、結果もログも残らなかった）."""

    def test_zero_budget_is_unlimited(self):
        self.assertFalse(mt.over_budget(10_000.0, [100.0], 100.0, 0))

    def test_estimate_before_any_mutant_is_the_baseline(self):
        self.assertTrue(mt.over_budget(5.0, [], 6.0, 10.0))
        self.assertFalse(mt.over_budget(5.0, [], 4.0, 10.0))

    def test_estimate_is_the_mean_of_executed_mutants(self):
        """baseline ではなく実行済みの平均で見積もる（baseline 1 秒でも 1 変異 6 秒なら止まる）."""
        self.assertTrue(mt.over_budget(5.0, [4.0, 8.0], 1.0, 10.0))
        self.assertFalse(mt.over_budget(5.0, [2.0, 4.0], 100.0, 10.0))

    def test_landing_exactly_on_the_budget_still_runs(self):
        self.assertFalse(mt.over_budget(8.0, [2.0], 2.0, 10.0))


class BudgetMainTest(unittest.TestCase):
    """main() が予算で打ち切った分を「予算で未実行」として数える（配線の確認）."""

    def setUp(self) -> None:
        import signal
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self._orig_root = mt.ROOT
        mt.ROOT = self.root
        self.addCleanup(lambda: setattr(mt, "ROOT", self._orig_root))
        # main() は変異を書く区間の前に SIGTERM / SIGHUP の handler を差し替える
        for sig in (signal.SIGTERM, signal.SIGHUP):
            self.addCleanup(signal.signal, sig, signal.getsignal(sig))
        (self.root / "t.py").write_text("x = 1 > 2\ny = 3 < 4\n", encoding="utf-8")

    def _main(self, *extra: str) -> tuple[int, str]:
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = mt.main(["--file", "t.py", "--test-cmd", "true", *extra])
        return rc, out.getvalue()

    def test_exhausted_budget_counts_the_rest_as_unexecuted(self):
        rc, out = self._main("--budget-sec", "0.000001")
        self.assertEqual(rc, 0)
        self.assertIn("殺した 0 / 生存 0", out)
        self.assertIn("予算で未実行 2", out)
        self.assertNotIn("SURVIVED", out, "打ち切ったのに変異を当てている")

    def test_without_budget_every_mutant_runs(self):
        rc, out = self._main()
        self.assertEqual(rc, 0)
        self.assertIn("生存 2", out)
        self.assertNotIn("予算", out)


class RunReportTest(unittest.TestCase):
    """実行の冒頭に出す対象モード・変更行の内訳・走ったテストの件数（GitHub issue #256）.

    どれも読み違えを結果の数字だけで気づけなかった実例への対策。main() を本物の git リポジトリで
    回して出力を見る（git は hook 由来の変数を落とした env で叩く / `git_env`）。
    """

    def setUp(self) -> None:
        import signal
        import subprocess
        from unittest import mock
        from git_env import scrub
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self._orig_root = mt.ROOT
        mt.ROOT = self.root
        self.addCleanup(lambda: setattr(mt, "ROOT", self._orig_root))
        for sig in (signal.SIGTERM, signal.SIGHUP):
            self.addCleanup(signal.signal, sig, signal.getsignal(sig))
        patcher = mock.patch.dict(os.environ, scrub(), clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.git = lambda *a: subprocess.run(["git", *a], cwd=self.root, check=True,
                                             capture_output=True)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        (self.root / "t.py").write_text("a = 1 > 2\nb = 3 < 4\nc = 5 > 6\n", encoding="utf-8")
        self.git("add", "t.py")
        self.git("commit", "-qm", "init")
        # unittest の出力を真似る小さなテストコマンド（件数と rc を env で決める）
        (self.root / "fake_tests.py").write_text(
            "import os, sys\n"
            "n = int(os.environ.get('FAKE_RAN', '3'))\n"
            "sys.stderr.write('-' * 70 + '\\nRan %d test%s in 0.001s\\n' % (n, '' if n == 1 else 's'))\n"
            "sys.exit(5 if n == 0 else 0)\n", encoding="utf-8")

    def _main(self, *args: str, ran: int = 3) -> tuple[int, str, str]:
        import contextlib
        import io
        os.environ["FAKE_RAN"] = str(ran)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = mt.main(list(args))
        return rc, out.getvalue(), err.getvalue()

    CMD = ("--test-cmd", "python3 fake_tests.py")

    def test_file_mode_says_it_is_not_a_diff_and_counts_changed_lines(self):
        (self.root / "t.py").write_text("a = 1 > 2\nb = 3 <= 4\nc = 5 > 6\n", encoding="utf-8")
        rc, out, _ = self._main("--file", "t.py", *self.CMD)
        self.assertEqual(rc, 0)
        self.assertIn("対象: ファイル全体（--file。差分ではない）", out)
        # 2 行目（変更行）の <= に当たる変異が 1 個、1・3 行目の > が 2 個
        self.assertIn("未追跡ファイル）1 個 / 既存行 2 個", out)
        self.assertNotIn("変更行に当たる変異が 0 個", out)

    def test_file_mode_warns_when_no_mutant_hits_a_changed_line(self):
        rc, out, _ = self._main("--file", "t.py", *self.CMD)
        self.assertIn("未追跡ファイル）0 個 / 既存行 3 個", out)
        self.assertIn("変更行に当たる変異が 0 個", out)

    def test_an_untracked_file_counts_every_line_as_changed(self):
        (self.root / "new.py").write_text("x = 1 > 2\n", encoding="utf-8")
        rc, out, _ = self._main("--file", "new.py", *self.CMD)
        self.assertIn("未追跡ファイル）1 個 / 既存行 0 個", out)

    def test_diff_mode_names_its_base_and_size(self):
        (self.root / "t.py").write_text("a = 1 > 2\nb = 3 <= 4\nc = 5 >= 6\n", encoding="utf-8")
        rc, out, _ = self._main(*self.CMD)
        self.assertEqual(rc, 0)
        self.assertIn("対象: 差分（--base HEAD）の追加行 — 1 ファイル・2 行のうち変異規則に当たった行 2", out)
        self.assertNotIn("既存行", out, "差分モードに --file の内訳を出している")

    def test_zero_mutants_says_unmeasured_and_skips_the_baseline(self):
        """**変異 0 個を「殺した 0 / 生存 0」と出さない**（検証済みに見える / 実測 2026-10-07）.

        テストコマンドを `false` にしておく — baseline を回していれば「失敗している」で exit 2 になる。
        """
        (self.root / "t.py").write_text("a = 1 > 2\nb = 3\nc = 5 > 6\n", encoding="utf-8")
        rc, out, err = self._main("--test-cmd", "false", "--strict")
        self.assertEqual(rc, 0, err)
        self.assertIn("1 行のうち変異規則に当たった行 0", out)
        self.assertIn("変異 0 個", out)
        self.assertIn("未計測", out)
        self.assertNotIn("殺した", out)
        self.assertNotIn("失敗している", err, "変異が無いのに baseline を回している")

    def test_the_number_of_tests_ran_is_shown_with_the_k_filter(self):
        rc, out, _ = self._main("--file", "t.py", "--max", "1", "--test-cmd",
                                "python3 fake_tests.py -k Foo", ran=1)
        self.assertEqual(rc, 0)
        self.assertIn("・1 件 / timeout", out)
        self.assertIn("-k Foo（部分一致）で 1 件", out)

    def test_zero_tests_ran_is_fatal_and_names_the_k_filter(self):
        rc, out, err = self._main("--file", "t.py", "--test-cmd", "python3 fake_tests.py -k Foo", ran=0)
        self.assertEqual(rc, 2)
        self.assertIn("1 件も走っていない", err)
        self.assertIn("-k Foo", err)
        self.assertNotIn("失敗している", err, "0 件を「テストが失敗」と誤って伝えている")
        self.assertNotRegex(out, r"変異 \d+ 個を実行する", "0 件のまま変異を当てている")
        self.assertNotIn("殺した", out, "0 件のまま変異を当てている")

    def test_zero_tests_without_k_is_still_fatal(self):
        rc, _, err = self._main("--file", "t.py", *self.CMD, ran=0)
        self.assertEqual(rc, 2)
        self.assertIn("1 件も走っていない", err)
        self.assertNotIn("-k", err)

    def test_every_option_has_help(self):
        """`--help` にオプション名しか出ないと、実行時に意味が見えない（#256 の 3 件）."""
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            mt.main(["--help"])
        for opt, words in (("--file", "差分ではなくファイル全体"), ("--test-cmd", "shell を通さず"),
                           ("--base", "差分の起点"), ("--max", "上限"), ("--strict", "exit 1")):
            with self.subTest(opt=opt):
                self.assertIn(words, out.getvalue())


class ReportHelperTest(unittest.TestCase):
    def test_tests_ran_reads_unittest_output(self):
        self.assertEqual(mt.tests_ran("...\nRan 12 tests in 0.5s\n\nOK\n"), 12)
        self.assertEqual(mt.tests_ran("Ran 1 test in 0.1s\n"), 1)
        self.assertEqual(mt.tests_ran("Ran 0 tests in 0.000s\n\nNO TESTS RAN\n"), 0)
        self.assertIsNone(mt.tests_ran("5 passed in 0.12s"), "unittest 以外は判定しない")
        self.assertIsNone(mt.tests_ran("log: Ran 3 tests in x"), "行頭でない Ran は拾わない")

    def test_k_patterns(self):
        self.assertEqual(mt.k_patterns("python3 -m unittest -k A -k B".split()), ["A", "B"])
        self.assertEqual(mt.k_patterns("python3 -m unittest -k".split()), [])
        self.assertEqual(mt.k_patterns("python3 -m unittest".split()), [])


if __name__ == "__main__":
    unittest.main()
