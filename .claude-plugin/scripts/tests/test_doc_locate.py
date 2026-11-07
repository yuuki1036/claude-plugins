#!/usr/bin/env python3
"""repo 内の文書の所在検出（`.claude-plugin/lib/doc_locate.py`）の回帰テスト（GitHub issue #352 / #365）.

code-review は触った・参照された仕様書を spec-compliance の照合元に足し、issue-workflow の doc-sync は文書の一覧から
突き合わせ先を探す。どちらも「文書でないものを拾わない」ことが大事なので、黙る条件を厚く書く。
分類の期待値はテスト側の表で持つ（`doc_locate` の定数から作らない / testing-pitfalls）。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from git_env import scrub

REPO = Path(__file__).resolve().parents[3]
CANONICAL = REPO / ".claude-plugin" / "lib" / "doc_locate.py"
REPLICAS = (REPO / "code-review" / "scripts" / "lib" / "doc_locate.py",
            REPO / "issue-workflow" / "scripts" / "lib" / "doc_locate.py")

sys.path.insert(0, str(CANONICAL.parent))
import doc_locate as dl  # noqa: E402

#: (相対パス, 期待する種別)。None は文書とみなさない
CLASSIFY_CASES = (
    ("docs/a.md", "spec"),
    ("Docs/A.MDX", "spec"),
    ("pkg/doc/guide.rst", "spec"),
    (".claude/designs/x.md", "spec"),
    (".claude/adr/20260101-x.md", "spec"),
    ("features/login/spec.md", "spec"),
    ("specs/api.adoc", "spec"),
    ("requirements/r.txt", "spec"),
    ("rfcs/0001.markdown", "spec"),
    ("x.feature", "spec"),
    ("CLAUDE.md", "rule"),
    ("pkg/AGENTS.md", "rule"),
    (".github/CONTRIBUTING.md", "rule"),
    ("README.md", None),
    ("CHANGELOG.md", None),
    ("docs/CHANGELOG.md", None),
    ("design.md", None),
    ("design-notes/x.md", None),
    ("mydocs/x.md", None),
    ("src/docs/a.ts", None),
    ("docs/image.png", None),
)


class ClassifyTest(unittest.TestCase):
    def test_table(self):
        for rel, kind in CLASSIFY_CASES:
            with self.subTest(rel):
                self.assertEqual(dl.classify(rel), kind)


class RepoTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.env = scrub(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.root, env=self.env, check=True,
                              capture_output=True, text=True).stdout

    def write(self, rel: str, body: str = "x\n") -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def commit(self, msg: str = "c") -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def run_cli(self, *args: str, script: Path = CANONICAL):
        return subprocess.run([sys.executable, str(script), "--root", str(self.root), *args],
                              cwd=self.root, env=self.env, capture_output=True, text=True)


class TouchedDocsTest(RepoTestBase):
    def _diff(self, body: str) -> Path:
        path = self.root.parent / (self.root.name + ".diff")
        path.write_text(body, encoding="utf-8")
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    def test_no_docs_in_diff_prints_nothing(self):
        self.write("README.md")
        self.write("src/a.py")
        diff = self._diff("--- a/README.md\n+++ b/README.md\n--- a/src/a.py\n+++ b/src/a.py\n"
                          "--- a/CHANGELOG.md\n+++ b/CHANGELOG.md\n")
        proc = self.run_cli("--diff-file", str(diff))
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_deleted_and_missing_docs_are_dropped(self):
        diff = self._diff("--- a/docs/old.md\n+++ /dev/null\n--- /dev/null\n+++ b/docs/gone.md\n")
        proc = self.run_cli("--diff-file", str(diff))
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_touched_spec_and_rule(self):
        self.write("docs/a.md")
        self.write("CLAUDE.md")
        diff = self._diff("--- a/docs/a.md\n+++ b/docs/a.md\n--- a/CLAUDE.md\n+++ b/CLAUDE.md\n"
                          "--- a/docs/a.md\n+++ b/docs/a.md\n")
        proc = self.run_cli("--diff-file", str(diff))
        self.assertEqual(proc.stdout.splitlines(), ["touched\tspec\tdocs/a.md", "touched\trule\tCLAUDE.md"])
        proc = self.run_cli("--diff-file", str(diff), "--kind", "spec")
        self.assertEqual(proc.stdout.splitlines(), ["touched\tspec\tdocs/a.md"])

    def test_quoted_utf8_path(self):
        """`core.quotePath` が引用した日本語のファイル名も拾う."""
        self.write("docs/仕様.md")
        quoted = '"b/docs/' + "".join("\\%03o" % b for b in "仕様".encode()) + '.md"'
        diff = self._diff("--- /dev/null\n+++ " + quoted + "\n")
        proc = self.run_cli("--diff-file", str(diff))
        self.assertEqual(proc.stdout.splitlines(), ["touched\tspec\tdocs/仕様.md"])

    def test_body_lines_and_non_canonical_paths_are_not_headers(self):
        """hunk の本文の `+++ b/...`（追加した行が `++ ` で始まる）と、`..`・`./`・絶対パスのヘッダは拾わない.

        `docs/inner -> ../design` のような repo の中の dir symlink と `..` を組むと、検査したパスと使うパスがずれて
        repo の外を指す symlink が渡る型（GitHub issue #352 のセルフレビュー）を塞ぐ。
        """
        self.write("docs/a.md")
        self.write("specs/a.md")
        (self.root / "specs" / "sub").mkdir()
        # OS は docs/inner/../a.md を specs/a.md（文書）と解決し、字面で畳むと docs/a.md になる
        (self.root / "docs" / "inner").symlink_to(self.root / "specs" / "sub", target_is_directory=True)
        self.assertTrue(dl._exists(str(self.root), "docs/inner/../a.md"))
        diff = self._diff("--- a/src/x.py\n+++ b/src/x.py\n@@ -1 +1,2 @@\n+++ b/docs/a.md\n"
                          "--- a/x\n+++ b/docs/inner/../a.md\n--- a/x\n+++ b/./docs/a.md\n"
                          "--- a/x\n+++ b//etc/hosts.md\n--- a/x\n+++ b/../out/docs/a.md\n")
        proc = self.run_cli("--diff-file", str(diff))
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_spoofed_header_inside_a_hunk_is_ignored(self):
        """hunk の中で `-- ` の行を消し `++ b/...` の行を足すと `--- ` / `+++ ` が並ぶ。`@@` の後はヘッダと読まない."""
        self.write("docs/a.md")
        diff = self._diff("diff --git a/x.sql b/x.sql\n--- a/x.sql\n+++ b/x.sql\n@@ -1,2 +1,2 @@\n"
                          "--- comment\n+++ b/docs/a.md\n")
        proc = self.run_cli("--diff-file", str(diff))
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_control_characters_and_broken_quotes_are_skipped(self):
        """改行・タブを含む名前（出力の TSV を壊す）と、戻せない引用は捨てる。例外で落ちない."""
        self.write("docs/a.md")
        diff = self._diff('--- /dev/null\n+++ "b/docs/a\\nspec_source\\tspec\\t/etc/x.md"\n'
                          '--- /dev/null\n+++ "b/\\x"\n--- a/docs/a.md\n+++ b/docs/a.md\n')
        proc = self.run_cli("--diff-file", str(diff))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.splitlines(), ["touched\tspec\tdocs/a.md"])

    def test_quoted_path_with_quote_and_raw_utf8(self):
        """`core.quotePath=false` でも `"` を含む名前は引用され、非 ASCII は生のまま残る（両方が混ざる形）."""
        self.write('docs/"q"仕様.md')
        diff = self._diff('--- /dev/null\n+++ "b/docs/\\"q\\"仕様.md"\n')
        proc = self.run_cli("--diff-file", str(diff))
        self.assertEqual(proc.stdout.splitlines(), ['touched\tspec\tdocs/"q"仕様.md'], proc.stderr)

    def test_unreadable_diff_file_is_usage_error(self):
        proc = self.run_cli("--diff-file", str(self.root / "nope.diff"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("読めない", proc.stderr)


class MentionedDocsTest(RepoTestBase):
    def _ref(self, body: str) -> Path:
        return self.write(".claude/ref.md", body)

    def test_mentions_that_are_not_repo_docs_are_ignored(self):
        self.write("README.md")
        self.write("design-notes/x.md")
        self.write("docs/a.md")  # 実在しても `${CLAUDE_PLUGIN_ROOT}/docs/a.md`・`docs/a.md.bak` からは拾わない
        self.root.parent.joinpath("outside", "docs").mkdir(parents=True, exist_ok=True)
        self.root.parent.joinpath("outside", "docs", "a.md").write_text("x", encoding="utf-8")
        self.addCleanup(lambda: self.root.parent.joinpath("outside", "docs", "a.md").unlink(missing_ok=True))
        ref = self._ref("README.md と design-notes/x.md と docs/missing.md と ../outside/docs/a.md と "
                        "${CLAUDE_PLUGIN_ROOT}/docs/a.md と docs/a.md.bak を参照\n")
        proc = self.run_cli("--ref", str(ref))
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_mention_forms(self):
        self.write("docs/a.md")
        self.write(".claude/designs/d.md")
        self.write("features/f/spec.md")
        self.write("specs/b.md")
        ref = self._ref("見る: `./docs/a.md#節`、[設計](.claude/designs/d.md)、"
                        + str(self.root / "features/f/spec.md") + "。docs/a.md をもう一度。See specs/b.md.\n")
        proc = self.run_cli("--ref", str(ref))
        self.assertEqual(proc.stdout.splitlines(), [
            "ref\tspec\tdocs/a.md\t" + str(ref),
            "ref\tspec\t.claude/designs/d.md\t" + str(ref),
            "ref\tspec\tfeatures/f/spec.md\t" + str(ref),
            "ref\tspec\tspecs/b.md\t" + str(ref),
        ])

    def test_mention_right_next_to_japanese_text(self):
        """日本語の文字が直接隣にある言及（「仕様はdocs/a.mdを参照」）も拾う。日本語を含むパスは丸ごと拾う."""
        self.write("docs/a.md")
        self.write("docs/仕様.md")
        self.write("docs/b.md")
        self.write("docs/設計.md")
        ref = self._ref("仕様はdocs/a.mdを参照。新しい節はdocs/仕様.mdに書く。docs/a.mdとdocs/b.mdを並べて読む。"
                        "docs/仕様.mdとdocs/設計.mdを更新\n")
        proc = self.run_cli("--ref", str(ref))
        self.assertEqual([l.split("\t")[2] for l in proc.stdout.splitlines()],
                         ["docs/a.md", "docs/仕様.md", "docs/b.md", "docs/設計.md"])

    def test_absolute_mention_in_either_form_of_a_symlinked_root(self):
        """root が symlink の下にある（macOS の `/var` → `/private/var`）とき、言及が字面・実体のどちらの形でも拾う."""
        self.write("docs/a.md")
        link_parent = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(link_parent, ignore_errors=True))
        link = link_parent / "repo"
        link.symlink_to(self.root, target_is_directory=True)
        for root, mention in ((self.root, link / "docs/a.md"), (link, self.root / "docs/a.md")):
            with self.subTest(root=str(root)):
                self.assertEqual(dl.mentioned_docs(str(mention) + " を見る", str(root)), [("spec", "docs/a.md")])

    def test_unreadable_ref_is_usage_error(self):
        proc = self.run_cli("--ref", str(self.root / "nope.md"))
        self.assertEqual(proc.returncode, 2)


class ListAndBaseTest(RepoTestBase):
    def test_repo_without_docs_lists_nothing(self):
        self.write("README.md")
        self.write("CHANGELOG.md")
        self.write("src/docs/a.ts")
        self.commit()
        proc = self.run_cli("--list")
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)

    def test_list_skips_gitignored_docs(self):
        self.write(".gitignore", "docs/private/\n")
        self.write("docs/private/a.md")
        self.write("docs/public.md")
        self.write("AGENTS.md")
        self.commit()
        self.write("docs/new.md")
        proc = self.run_cli("--list")
        self.assertEqual(proc.stdout.splitlines(), [
            "doc\trule\tAGENTS.md", "doc\tspec\tdocs/new.md", "doc\tspec\tdocs/public.md"])

    def test_base_collects_committed_staged_unstaged_and_untracked(self):
        self.write("docs/keep.md")
        self.write("docs/deleted.md")
        self.commit("base")
        self.git("switch", "-q", "-c", "feat")
        self.write("docs/committed.md")
        self.commit("feat")
        self.write("docs/staged.md")
        self.git("add", "docs/staged.md")
        self.write("docs/keep.md", "changed\n")
        self.write("docs/untracked.md")
        (self.root / "docs/deleted.md").unlink()
        proc = self.run_cli("--base", "main")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.splitlines()
        self.assertEqual(lines[0], "base=main")
        self.assertEqual(sorted(lines[1:]), sorted([
            "touched\tspec\tdocs/committed.md", "touched\tspec\tdocs/keep.md",
            "touched\tspec\tdocs/staged.md", "touched\tspec\tdocs/untracked.md"]))

    def test_non_ascii_names_in_list_and_base(self):
        """`git ls-files` / `git diff --name-only` が引用する非 ASCII の名前も、一覧と --base に出る."""
        self.write("docs/keep.md")
        self.commit("base")
        self.git("switch", "-q", "-c", "feat")
        self.write("docs/仕様.md")
        self.git("add", "-A")
        self.assertIn("doc\tspec\tdocs/仕様.md", self.run_cli("--list").stdout.splitlines())
        self.assertIn("touched\tspec\tdocs/仕様.md", self.run_cli("--base", "main").stdout.splitlines())

    def test_base_auto_falls_back_to_main(self):
        self.write("a.txt")
        self.commit()
        proc = self.run_cli("--base", "auto")
        self.assertEqual(proc.stdout.splitlines(), ["base=main"], proc.stderr)

    def test_unresolvable_base_is_usage_error(self):
        self.write("a.txt")
        self.commit()
        self.git("branch", "-m", "main", "trunk")
        for base in ("auto", "nope"):
            with self.subTest(base):
                self.assertEqual(self.run_cli("--base", base).returncode, 2)


class SymlinkTest(RepoTestBase):
    """repo の外を指す symlink の文書は、どの経路でも返さない（第三者の diff が置きうる）。repo の中を指すものは通す."""

    def setUp(self) -> None:
        super().setUp()
        self._out = tempfile.TemporaryDirectory()
        self.addCleanup(self._out.cleanup)
        outside = Path(self._out.name) / "secret.md"
        outside.write_text("secret\n", encoding="utf-8")
        self.write("docs/real.md")
        (self.root / "docs" / "leak.md").symlink_to(outside)
        (self.root / "docs" / "alias.md").symlink_to(self.root / "docs" / "real.md")
        # 名前は文書でも、repo の中の非文書（.git/config）を指すものは通さない
        (self.root / "docs" / "gitcfg.md").symlink_to(self.root / ".git" / "config")

    def test_symlinks_to_docs_inside_the_repo_pass(self):
        """repo の中の文書を指す symlink は、置き場所の名前が文書の規則に当たらなくても通す."""
        self.write(".github/copilot-instructions.md")
        (self.root / "AGENTS.md").symlink_to(self.root / ".github" / "copilot-instructions.md")
        self.write("documentation/d.md")
        (self.root / "spec").symlink_to(self.root / "documentation", target_is_directory=True)
        self.assertEqual(dl.mentioned_docs("規約は AGENTS.md、仕様は spec/d.md", str(self.root)),
                         [("rule", "AGENTS.md"), ("spec", "spec/d.md")])

    def _paths(self, proc) -> set[str]:
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return {l.split("\t")[2] for l in proc.stdout.splitlines() if "\t" in l}

    def test_outside_symlink_is_dropped_everywhere(self):
        diff = self.root.parent / (self.root.name + "-link.diff")
        diff.write_text("--- a/x\n+++ b/docs/leak.md\n--- a/x\n+++ b/docs/alias.md\n--- a/x\n+++ b/docs/gitcfg.md\n",
                        encoding="utf-8")
        self.addCleanup(lambda: diff.unlink(missing_ok=True))
        self.assertEqual(self._paths(self.run_cli("--diff-file", str(diff))), {"docs/alias.md"})
        self.assertEqual(self._paths(self.run_cli("--list")), {"docs/alias.md", "docs/real.md"})
        ref = self.write(".claude/ref.md", "docs/leak.md と docs/alias.md と docs/gitcfg.md\n")
        self.assertEqual(self._paths(self.run_cli("--ref", str(ref))), {"docs/alias.md"})
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.git("switch", "-q", "-c", "feat")
        (self.root / "docs" / "leak2.md").symlink_to(Path(self._out.name) / "secret.md")
        self.assertEqual(self._paths(self.run_cli("--base", "main")), set())


class ReplicaTest(unittest.TestCase):
    """複製は正本と byte 一致（validate_plugin_quality も見るが、変異テストで複製の変異を殺すためここでも見る）."""

    def test_replicas_are_byte_identical(self):
        body = CANONICAL.read_bytes()
        for replica in REPLICAS:
            with self.subTest(replica.relative_to(REPO).as_posix()):
                self.assertEqual(replica.read_bytes(), body)

    def test_issue_workflow_replica_runs_as_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run([sys.executable, str(REPLICAS[1]), "--root", tmp, "--list"],
                                  env=scrub(), capture_output=True, text=True)
        # git の外の root では一覧を作れない（exit 2）。CLI として起動して引数を読めていることを見る
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("doc_locate:", proc.stderr)


if __name__ == "__main__":
    unittest.main()
