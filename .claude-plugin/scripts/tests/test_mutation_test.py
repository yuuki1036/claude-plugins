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

if __name__ == "__main__":
    unittest.main()
