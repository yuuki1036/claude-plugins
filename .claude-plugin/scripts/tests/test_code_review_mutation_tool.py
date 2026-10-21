#!/usr/bin/env python3
"""変異テストの道具の検出（`detect-mutation-tool.sh`）と、この repo の宣言 `.claude/mutation-test.sh` の回帰テスト.

review-guide の読み合わせの締めの `変異テスト:` の行（GitHub issue #307）は、この検出の結果で
`提案する` / `道具なし` が決まる。誤って鳴ると、使っていない道具のコマンドを利用者に承認させることになるので、
**黙る条件を厚くする**（README に語があるだけ・下位のディレクトリの設定・PATH 上の実行ファイル・見出しに似た行）。
黙るテストには、同じ fixture に決め手を足すと鳴る側の対を置く（docs/testing-pitfalls.md ## 6）。

宣言のテストは本物の `.claude/mutation-test.sh` を使い捨てリポジトリへ複製し、`mutation-test.py` を
argv を書き出す stub に差し替えて回す（この repo のスイートに向けた本物の変異テストは作業ツリーを書き換えながら
10 分以上回るので、引数の受け渡しと終了コードの素通しは stub で見る）。
契約に書いた終了コードと集計の語が本物の出力と合っているかは、本物の `mutation-test.py` も複製し、変異 2 個・
テスト 2 件の小さな fixture に向けて回して見る（`RealToolContractTest`。変異体は複製先の fixture にだけ書かれる）。
PR モードで宣言に渡す `<ref>` の式は、format の文言から取り出して本物の git に当てる（`PrModeRefTest`）。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from test_code_review_scripts import PLUGIN, REPO, ScriptTestBase

DETECT = PLUGIN / "scripts" / "detect-mutation-tool.sh"
DECLARATION = REPO / ".claude" / "mutation-test.sh"
MUTATION_TOOL = REPO / ".claude-plugin" / "scripts" / "mutation-test.py"
FORMAT = PLUGIN / "references" / "review-guide-format.md"
README = PLUGIN / "README.md"

STRYKER_NAMES = [f"{base}.{ext}"
                 for base in ("stryker.conf", "stryker.config", ".stryker.conf", ".stryker.config")
                 for ext in ("json", "js", "mjs", "cjs")]


class DetectBase(ScriptTestBase):
    def detect(self, *args: str, cwd: Path | None = None, env: dict[str, str] | None = None
               ) -> tuple[int, list[str], str]:
        res = subprocess.run(["bash", str(DETECT), *args], cwd=str(cwd or self.root),
                             capture_output=True, text=True, env=env or self._env(), timeout=60)
        return res.returncode, res.stdout.splitlines(), res.stderr

    def put(self, rel: str, body: str = "") -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def declare(self, body: str = "#!/usr/bin/env bash\nexit 0\n") -> Path:
        return self.put(".claude/mutation-test.sh", body)

    def assertNone(self, lines: list[str]) -> None:
        self.assertEqual(lines, ["mutation_tool=none"])


class DetectMutationToolTest(DetectBase):
    def test_plain_repository_reports_none_only(self):
        rc, lines, _ = self.detect()
        self.assertEqual(rc, 0)
        self.assertNone(lines)
        self.declare()
        rc, lines, _ = self.detect()
        self.assertEqual(rc, 0)
        self.assertEqual(lines, ["mutation_tool=declared", "declared=.claude/mutation-test.sh"])

    def test_outside_git_reports_none(self):
        outside = self.root / "tmp" / "not-a-repo"
        outside.mkdir(parents=True)
        (outside / ".claude").mkdir()
        (outside / ".claude" / "mutation-test.sh").write_text("exit 0\n", encoding="utf-8")
        env = {**self._env(), "GIT_CEILING_DIRECTORIES": str(outside.parent)}
        rc, lines, _ = self.detect(cwd=outside, env=env)
        self.assertEqual(rc, 0)
        self.assertNone(lines)

    def test_arguments_are_rejected(self):
        self.declare()
        rc, lines, err = self.detect("--base")
        self.assertEqual(rc, 2)
        self.assertEqual(lines, [])
        self.assertIn("usage: detect-mutation-tool.sh", err)

    def test_declaration_wins_and_skips_inference(self):
        self.declare()
        self.put("stryker.config.json", "{}\n")
        self.put("pyproject.toml", "[tool.mutmut]\nsource_paths = ['src/']\n")
        self.put(".cargo/mutants.toml", "")
        rc, lines, _ = self.detect()
        self.assertEqual(rc, 0)
        self.assertEqual(lines[0], "mutation_tool=declared")
        self.assertFalse([l for l in lines if l.startswith("inferred=")], lines)

    def test_estimate_is_the_first_comment_line(self):
        self.declare("#!/usr/bin/env bash\n# 所要の目安:   約 3 分\n# 所要の目安: 約 9 分\nexit 0\n")
        _, lines, _ = self.detect()
        self.assertEqual(lines, ["mutation_tool=declared", "declared=.claude/mutation-test.sh",
                                 "estimate=約 3 分"])

    def test_estimate_without_space_after_colon(self):
        self.declare("# 所要の目安:約 3 分\n")
        _, lines, _ = self.detect()
        self.assertIn("estimate=約 3 分", lines)

    def test_estimate_needs_column_zero(self):
        body = '#!/usr/bin/env bash\n  # 所要の目安: 字下げ\necho "# 所要の目安: 本体"\n'
        self.declare(body)
        _, lines, _ = self.detect()
        self.assertFalse([l for l in lines if l.startswith("estimate=")], lines)
        self.declare(body + "# 所要の目安: 行頭\n")
        _, lines, _ = self.detect()
        self.assertIn("estimate=行頭", lines)

    def test_declaration_without_estimate_has_no_estimate_line(self):
        self.declare("#!/usr/bin/env bash\n# 所要の目安の根拠: 書いていない\nexit 0\n")
        _, lines, _ = self.detect()
        self.assertEqual(lines, ["mutation_tool=declared", "declared=.claude/mutation-test.sh"])

    def test_declaration_must_be_a_regular_file(self):
        (self.root / ".claude" / "mutation-test.sh").mkdir(parents=True)
        _, lines, _ = self.detect()
        self.assertNone(lines)
        (self.root / ".claude" / "mutation-test.sh").rmdir()
        self.declare()
        _, lines, _ = self.detect()
        self.assertEqual(lines[0], "mutation_tool=declared")

    def test_stryker_default_config_names(self):
        for name in STRYKER_NAMES:
            with self.subTest(name=name):
                path = self.put(name, "{}\n")
                try:
                    rc, lines, _ = self.detect()
                    self.assertEqual(rc, 0)
                    self.assertEqual(lines, ["mutation_tool=inferred", f"inferred=stryker\t{name}"])
                finally:
                    path.unlink()

    def test_first_stryker_config_name_is_the_evidence(self):
        """名前の並び（stryker.conf → stryker.config → .stryker.conf → .stryker.config、拡張子は json → js → mjs → cjs）の最初の 1 つ."""
        self.put(".stryker.config.json", "{}\n")
        self.put("stryker.config.json", "{}\n")
        self.put("stryker.conf.cjs", "")
        _, lines, _ = self.detect()
        self.assertEqual(lines, ["mutation_tool=inferred", "inferred=stryker\tstryker.conf.cjs"])

    def test_stryker_from_package_json_dependency(self):
        pkg = {"name": "a", "description": "mutation testing with stryker",
               "scripts": {"mutate": "stryker run"}, "devDependencies": {"jest": "^29"}}
        self.put("package.json", json.dumps(pkg, indent=2) + "\n")
        _, lines, _ = self.detect()
        self.assertNone(lines)
        pkg["devDependencies"]["@stryker-mutator/core"] = "^8"
        self.put("package.json", json.dumps(pkg, indent=2) + "\n")
        _, lines, _ = self.detect()
        self.assertEqual(lines, ["mutation_tool=inferred", "inferred=stryker\tpackage.json"])

    def test_stryker_is_listed_once(self):
        self.put("package.json", '{"devDependencies": {"@stryker-mutator/core": "^8"}}\n')
        self.put("stryker.config.mjs", "export default {};\n")
        _, lines, _ = self.detect()
        self.assertEqual(lines, ["mutation_tool=inferred", "inferred=stryker\tstryker.config.mjs"])

    def test_mutmut_sections(self):
        silent = {
            "pyproject.toml": "[tool.mutmutx]\nx = 1\n# [tool.mutmut]\n[tool.other]\nrunner = 'mutmut'\n",
            "setup.cfg": "[mutmutx]\n# [mutmut]\n[metadata]\nname = mutmut\n",
        }
        for name, body in silent.items():
            self.put(name, body)
        _, lines, _ = self.detect()
        self.assertNone(lines)
        self.put("setup.cfg", silent["setup.cfg"] + "[mutmut]\nsource_paths=src/\n")
        _, lines, _ = self.detect()
        self.assertEqual(lines, ["mutation_tool=inferred", "inferred=mutmut\tsetup.cfg"])
        self.put("pyproject.toml", silent["pyproject.toml"] + "[tool.mutmut]\nsource_paths = ['src/']\n")
        _, lines, _ = self.detect()
        self.assertEqual(lines, ["mutation_tool=inferred", "inferred=mutmut\tpyproject.toml"],
                         "mutmut は 1 行だけで、pyproject.toml を先に見る")

    def test_cargo_mutants_config_and_path_is_not_looked_at(self):
        """PATH に道具があっても設定が無ければ none（開発機に道具が無いことには頼らない / testing-pitfalls ## 1 ①）."""
        bin_dir = self.root / "tmp" / "bin"
        bin_dir.mkdir()
        for tool in ("cargo", "cargo-mutants", "mutmut", "stryker", "npx"):
            stub = bin_dir / tool
            stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            stub.chmod(0o755)
        env = self._env()
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        self.put("Cargo.toml", '[package]\nname = "a"\n')
        _, lines, _ = self.detect(env=env)
        self.assertNone(lines)
        self.put(".cargo/mutants.toml", "exclude_globs = []\n")
        _, lines, _ = self.detect(env=env)
        self.assertEqual(lines, ["mutation_tool=inferred", "inferred=cargo-mutants\t.cargo/mutants.toml"])

    def test_several_tools_are_all_listed_in_order(self):
        self.put(".cargo/mutants.toml", "")
        self.put("pyproject.toml", "[tool.mutmut]\n")
        self.put("stryker.conf.json", "{}\n")
        _, lines, _ = self.detect()
        self.assertEqual(lines, ["mutation_tool=inferred", "inferred=stryker\tstryker.conf.json",
                                 "inferred=mutmut\tpyproject.toml",
                                 "inferred=cargo-mutants\t.cargo/mutants.toml"])

    def test_runs_from_a_subdirectory(self):
        sub = self.root / "src" / "deep"
        sub.mkdir(parents=True)
        self.put("stryker.config.json", "{}\n")
        _, lines, _ = self.detect(cwd=sub)
        self.assertEqual(lines, ["mutation_tool=inferred", "inferred=stryker\tstryker.config.json"])
        self.declare()
        _, lines, _ = self.detect(cwd=sub)
        self.assertEqual(lines[0], "mutation_tool=declared")

    def test_configs_below_the_root_are_not_inferred(self):
        self.put("packages/a/stryker.config.json", "{}\n")
        self.put("packages/b/pyproject.toml", "[tool.mutmut]\n")
        self.put("packages/c/.cargo/mutants.toml", "")
        self.put("packages/d/.claude/mutation-test.sh", "exit 0\n")
        _, lines, _ = self.detect()
        self.assertNone(lines)
        self.put("stryker.config.json", "{}\n")
        _, lines, _ = self.detect()
        self.assertEqual(lines, ["mutation_tool=inferred", "inferred=stryker\tstryker.config.json"])

    def test_readme_mention_does_not_count(self):
        self.put("README.md", "We use Stryker (@stryker-mutator/core), mutmut ([tool.mutmut]) and "
                              "cargo-mutants (.cargo/mutants.toml).\n[mutmut]\n")
        _, lines, _ = self.detect()
        self.assertNone(lines)


class RepoDeclarationTest(DetectBase):
    """この repo の宣言は mutation-test.py を `--strict --related-first` で呼び、引数と終了コードを素通しする."""

    STUB = (
        "import json, os, sys\n"
        "out = os.environ['STUB_OUT']\n"
        "with open(out, 'w', encoding='utf-8') as f:\n"
        "    json.dump({'argv': sys.argv[1:], 'cwd': os.getcwd()}, f)\n"
        "sys.exit(int(os.environ.get('STUB_RC', '0')))\n"
    )

    def setUp(self) -> None:
        super().setUp()
        dest = self.root / ".claude" / "mutation-test.sh"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DECLARATION, dest)
        self.put(".claude-plugin/scripts/mutation-test.py", self.STUB)
        self.out = self.root / "tmp" / "stub.json"

    def run_declaration(self, *args: str, cwd: Path | None = None, rc: int = 0
                        ) -> tuple[subprocess.CompletedProcess[str], dict]:
        env = self._env(STUB_OUT=str(self.out), STUB_RC=str(rc))
        res = subprocess.run(["bash", ".claude/mutation-test.sh" if cwd is None
                              else str(self.root / ".claude" / "mutation-test.sh"), *args],
                             cwd=str(cwd or self.root), capture_output=True, text=True, env=env, timeout=60)
        self.assertTrue(self.out.is_file(), f"stub に届いていない: {res.stderr}")
        return res, json.loads(self.out.read_text(encoding="utf-8"))

    def test_forwards_base_and_keeps_strict(self):
        _, got = self.run_declaration("--base", "abc123")
        argv = got["argv"]
        self.assertIn("--strict", argv, "生存しても exit 1 にならない（契約の 1 が崩れる）")
        self.assertIn("--related-first", argv)
        i = argv.index("--base")
        self.assertEqual(argv[i + 1], "abc123")

    def test_exit_code_passes_through(self):
        for rc in (0, 1, 2):
            with self.subTest(rc=rc):
                res, _ = self.run_declaration("--base", "HEAD", rc=rc)
                self.assertEqual(res.returncode, rc)

    def test_works_from_a_subdirectory(self):
        sub = self.root / "a" / "b"
        sub.mkdir(parents=True)
        res, got = self.run_declaration("--base", "HEAD", cwd=sub)
        self.assertEqual(res.returncode, 0)
        self.assertEqual(got["argv"][-2:], ["--base", "HEAD"])

    def test_estimate_is_declared(self):
        _, lines, _ = self.detect()
        self.assertEqual(lines[:2], ["mutation_tool=declared", "declared=.claude/mutation-test.sh"])
        estimate = [l for l in lines if l.startswith("estimate=")]
        self.assertEqual(len(estimate), 1, lines)
        self.assertTrue(estimate[0].removeprefix("estimate=").strip(), "所要の目安が空")


class RealToolContractTest(DetectBase):
    """契約の終了コードと、それを見分ける手がかりの出どころを、本物の宣言と mutation-test.py で確かめる.

    上の RepoDeclarationTest は stub なので、契約に書いた集計の語（「上限で未実行 N」など）が本物の出力に
    あるかは見ていない。宣言は `--max` を渡さず既定の 25 個が上限になるので、それを超える変更では
    「殺した 25 / 生存 0 / 上限で未実行 N」が exit 0 で返る。ここでは `--max 1` で同じ形を作る.
    """

    LIB_BASE = "def f(x):\n    return x\n\n\ndef g(x):\n    return x\n"
    # 2・6 行目が変更行。変異は各行 1 個（== と != の反転）
    LIB = "def f(x):\n    return x == 1\n\n\ndef g(x):\n    return x != 2\n"

    @staticmethod
    def suite(check_g: bool = True, edit_when_f_mutated: bool = False) -> str:
        g = ("        self.assertTrue(lib.g(3))\n        self.assertFalse(lib.g(2))\n" if check_g
             else "        self.assertIsInstance(lib.g(3), bool)\n")
        # 変異した f を見たら lib.py に書き足す。mutation-test.py には実行中の外部編集に見え、書き戻さずに中断する
        edit = ("        if not lib.f(1):\n"
                "            p = Path(lib.__file__)\n"
                "            p.write_text(p.read_text(encoding='utf-8') + '# edited\\n', encoding='utf-8')\n"
                if edit_when_f_mutated else "")
        return ("import sys\nimport unittest\nfrom pathlib import Path\n\n"
                "sys.path.insert(0, str(Path(__file__).resolve().parents[3]))\n"
                "import lib  # noqa: E402\n\n\n"
                "class T(unittest.TestCase):\n"
                "    def test_f(self):\n" + edit +
                "        self.assertTrue(lib.f(1))\n        self.assertFalse(lib.f(2))\n\n"
                "    def test_g(self):\n" + g)

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=str(self.root), capture_output=True, text=True,
                              env=self._env(), check=True)

    def setUp(self) -> None:
        super().setUp()
        for src, rel in ((DECLARATION, ".claude/mutation-test.sh"),
                         (MUTATION_TOOL, ".claude-plugin/scripts/mutation-test.py")):
            dest = self.root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        self.put("lib.py", self.LIB_BASE)
        self.put("README.md", "a\n")
        self.put(".claude-plugin/scripts/tests/test_lib.py", self.suite())
        self.git("add", ".claude", ".claude-plugin", "lib.py", "README.md")
        self.git("commit", "-qm", "base")
        # **宣言は toplevel の mutation-test.py を回す**。外側のリポジトリに解決されると、本物の変異が
        # 実際の作業ツリーに当たる。回す前に使い捨て側に解決されることを確かめる
        top = Path(self.git("rev-parse", "--show-toplevel").stdout.strip()).resolve()
        self.assertEqual(top, self.root)

    def run_real(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", ".claude/mutation-test.sh", "--base", "HEAD", *args],
                              cwd=str(self.root), capture_output=True, text=True, env=self._env(),
                              timeout=300)

    def summary(self, res: subprocess.CompletedProcess[str]) -> str:
        line = next((l for l in res.stdout.splitlines() if l.startswith("殺した ")), None)
        self.assertIsNotNone(line, f"集計の行が無い:\n{res.stdout}\n{res.stderr}")
        return line

    def test_cap_leaves_unexecuted_mutants_but_exits_zero(self):
        self.put("lib.py", self.LIB)
        res = self.run_real("--max", "1")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        line = self.summary(res)
        self.assertIn("生存 0", line)
        self.assertIn("上限で未実行 1", line, "契約が見分ける手がかりにした語が集計に無い")
        res = self.run_real()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        line = self.summary(res)
        self.assertIn("殺した 2 / 生存 0", line)
        self.assertNotIn("上限で未実行", line, "上限に当たらない回にも出ている（一部未実行と区別できない）")

    def test_survivor_exits_one_and_is_listed_on_stdout(self):
        self.put("lib.py", self.LIB)
        self.put(".claude-plugin/scripts/tests/test_lib.py", self.suite(check_g=False))
        res = self.run_real()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("生存 1", self.summary(res))
        self.assertIn("生存した変異", res.stdout)
        self.assertIn("lib.py:6", res.stdout.split("生存した変異", 1)[1], "生存した変異の file:line が stdout に無い")
        self.assertNotIn("FATAL", res.stderr, "生存だけの回に中断の FATAL が出ている（途中で止まった回と区別できない）")

    def test_abort_exits_one_and_is_told_on_stderr(self):
        """途中で止まった回は、stdout の集計だけを見ると生存 0 に見える。exit 1 と stderr の FATAL で見分ける."""
        self.put("lib.py", self.LIB)
        self.put(".claude-plugin/scripts/tests/test_lib.py", self.suite(edit_when_f_mutated=True))
        res = self.run_real()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("生存 0", self.summary(res))
        for clue in ("FATAL", "実行済み", "変異が当たったまま"):
            with self.subTest(clue=clue):
                self.assertIn(clue, res.stderr, "途中で止まった手がかりが stderr に無い")
        self.assertNotIn("FATAL", res.stdout)

    def test_no_target_lines_is_unmeasured_and_exits_zero(self):
        self.put("README.md", "b\n")
        res = self.run_real()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("変異対象の変更行が無い", res.stdout)
        self.assertNotIn("殺した", res.stdout, "未計測の回に集計を出している（生存 0 に見える）")

    def test_no_mutant_is_unmeasured_and_exits_zero(self):
        """変更行はあるが、どの変異規則にも当たらない回。契約が未計測の手がかりに挙げた「変異 0 個」の行が出る."""
        self.put("lib.py", self.LIB_BASE.replace("    return x\n", "    return (x)\n", 1))
        res = self.run_real()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("変異 0 個", res.stdout)
        self.assertNotIn("殺した", res.stdout, "未計測の回に集計を出している（生存 0 に見える）")


class PrModeRefTest(ScriptTestBase):
    """PR モードの `<ref>`（format の「道具」の節）を、手元が PR head でない 2 つの形で本物の git に当てる.

    宣言の対象は `git diff <ref>` なので、PR head を checkout した後のその diff が PR の変更（lib.py）だけかで見る。
    式は format の文言から取り出す（手元の `HEAD` 起点に戻すとここが落ちる）。同じ fixture で `HEAD` 起点の式も回し、
    base のコミット（other.py）が混ざること、つまり fixture が両者を見分けられることを対で確かめる.
    """

    LOCAL_HEAD = "git merge-base origin/<baseRefName> HEAD"

    def git(self, *args: str, cwd: Path | None = None) -> str:
        return subprocess.run(["git", *args], cwd=str(cwd or self.root), capture_output=True, text=True,
                              env=self._env(), check=True).stdout.strip()

    def commit(self, rel: str, line: str, msg: str) -> None:
        with (self.root / rel).open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        self.git("add", rel)
        self.git("commit", "-qm", msg)

    def setUp(self) -> None:
        super().setUp()
        # self.root を origin にし、commit はすべてここで作る（clone 側には author を設定しない）
        self.git("checkout", "-q", "-B", "main")
        self.commit("lib.py", "a", "A")
        self.commit("other.py", "o", "A2")
        self.git("checkout", "-q", "-b", "feature")
        self.commit("lib.py", "pr", "F1")
        self.git("checkout", "-q", "main")
        self.commit("other.py", "base-later", "B")
        self.local = self.root / "tmp" / "local"
        self.git("clone", "-q", str(self.root), str(self.local))
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD", cwd=self.local), "main")

    def doc_command(self) -> str:
        text = FORMAT.read_text(encoding="utf-8")
        bullet = next((l for l in text.splitlines() if l.startswith("- `<ref>` は")), None)
        self.assertIsNotNone(bullet, "format に `<ref>` の決め方の行が無い")
        m = re.search(r"PR モードなら `(git merge-base [^`]+)`", bullet)
        self.assertIsNotNone(m, f"PR モードの式が読めない: {bullet}")
        return m.group(1)

    def argv(self, command: str, head_oid: str) -> list[str]:
        argv = command.replace("<baseRefName>", "main").replace("<headRefOid>", head_oid).split()
        self.assertEqual(argv[:2], ["git", "merge-base"], argv)
        return argv[1:]

    def target(self, ref: str, head_oid: str) -> list[str]:
        self.git("checkout", "-q", head_oid, cwd=self.local)
        return self.git("diff", "--name-only", ref, cwd=self.local).splitlines()

    def check(self, head_oid: str) -> None:
        # どちらの起点も、手元が PR head でない今の状態で求める（checkout を促すのは起点を決めた後）
        doc_ref = self.git(*self.argv(self.doc_command(), head_oid), cwd=self.local)
        head_ref = self.git(*self.argv(self.LOCAL_HEAD, head_oid), cwd=self.local)
        self.assertEqual(self.target(doc_ref, head_oid), ["lib.py"], "format の式で base のコミットが混ざった")
        self.assertEqual(self.target(head_ref, head_oid), ["lib.py", "other.py"],
                         "fixture が手元の HEAD 起点との違いを作れていない")

    def test_local_head_is_on_base_that_moved_after_the_pr_forked(self):
        """手元が main: HEAD 起点だと、PR の分岐後に base へ入ったコミット（B）が逆向きに混ざる."""
        self.check(self.git("rev-parse", "origin/feature", cwd=self.local))

    def test_local_head_is_an_old_pr_head(self):
        """手元が古い PR head で、PR が後から base を取り込んだ: HEAD 起点だと、取り込んだ B が混ざる."""
        old = self.git("rev-parse", "origin/feature", cwd=self.local)
        self.git("checkout", "-q", "feature")
        self.git("merge", "-q", "--no-edit", "main")
        self.commit("lib.py", "pr2", "F2")
        self.git("checkout", "-q", "main")
        self.git("checkout", "-q", old, cwd=self.local)
        self.git("fetch", "-q", "origin", cwd=self.local)
        head = self.git("rev-parse", "origin/feature", cwd=self.local)
        self.assertNotEqual(head, old)
        self.check(head)

    def test_missing_pr_head_commit_fails_without_a_value(self):
        """手元に headRefOid のコミットが無いと式は失敗し、値を返さない（format はその回を HEAD で代えず、
        `<ref>` を埋める回し方では `道具なし` にする）."""
        res = subprocess.run(["git", *self.argv(self.doc_command(), "0" * 40)], cwd=str(self.local),
                             capture_output=True, text=True, env=self._env())
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "")
        present = self.git("rev-parse", "origin/feature", cwd=self.local)
        self.assertTrue(self.git(*self.argv(self.doc_command(), present), cwd=self.local),
                        "コミットがある回にも値が出ない（失敗の対が成り立たない）")


class ContractWordingTest(unittest.TestCase):
    """宣言の契約の文言は、正本（format）・この repo の宣言・README の例で揃える（#307 の確定事項 1）.

    mutation-test.py は対象行が無いときも、変異が 0 個のときも、上限・タイムアウトで未実行が残っても
    生存が無ければ exit 0 を返すので、0 を「生存 0」と読ませない。途中で止まった回の FATAL は stderr に出る.
    見分ける手がかりを出すのは宣言の側で、語は宣言が決める（mutation-test.py の語は例）。
    文言が本物の出力と合っているかは RealToolContractTest で見る.
    """

    EXIT_ZERO = ("実行した変異に生存なし（上限・タイムアウトで未実行が残った回を含む",
                 "または未計測（対象行・変異が 0 個）",
                 "どれかは stdout で見分ける")
    EXIT_ONE = ("途中で止まった（stderr に中断の FATAL と実行済みの件数）",
                "stdout と stderr の両方で見分ける")
    # 宣言が出す義務と、その例（mutation-test.py の語）
    CLUES = ("見分ける手がかりは宣言が出す",
             "未計測の回は集計の代わり",
             "「上限で未実行 N」「タイムアウト N」",
             "「変異対象の変更行が無い」「変異 0 個」")

    def test_exit_zero_includes_partial_runs_and_unmeasured(self):
        for path in (FORMAT, DECLARATION, README):
            text = path.read_text(encoding="utf-8")
            for phrase in self.EXIT_ZERO:
                with self.subTest(path=path.name, phrase=phrase):
                    self.assertIn(phrase, text)

    def test_clues_are_the_declarations_duty(self):
        """未計測の回は集計の行を出さないので、「stdout の集計で見分ける」とは書かない."""
        for path in (FORMAT, DECLARATION, README):
            text = path.read_text(encoding="utf-8")
            for phrase in self.CLUES:
                with self.subTest(path=path.name, phrase=phrase):
                    self.assertIn(phrase, text)
            with self.subTest(path=path.name):
                self.assertNotIn("stdout の集計で見分ける", text)

    def test_aborted_runs_are_told_apart_on_stderr(self):
        for path in (FORMAT, DECLARATION, README):
            text = path.read_text(encoding="utf-8")
            for phrase in self.EXIT_ONE:
                with self.subTest(path=path.name, phrase=phrase):
                    self.assertIn(phrase, text)
            for line in text.splitlines():
                if "途中で止まった" in line:
                    with self.subTest(path=path.name, line=line):
                        self.assertIn("stderr", line, "途中で止まった回を stdout だけで見分けさせている")

    def test_untracked_files_are_out_of_scope(self):
        for path in (FORMAT, DECLARATION, README):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("`git diff <ref>` に出る変更", text)
                self.assertIn("未追跡のファイルは対象外", text)

    def test_declaration_is_invoked_with_base(self):
        for path in (FORMAT, DECLARATION, README):
            with self.subTest(path=path.name):
                self.assertIn("bash .claude/mutation-test.sh --base <ref>", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
