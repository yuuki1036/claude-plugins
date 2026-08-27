#!/usr/bin/env python3
"""`.githooks/pre-commit` の回帰テスト（GitHub issue #139 / #140）.

**機械層のゲート本体**（バージョンバンプ / CHANGELOG / SSoT / 品質 / 回帰テスト）で、
ここが素通りすると下流の検査がいくら正しくても commit は通る。壊れ方は静かで、
「ブロックされなかった＝問題が無かった」と区別がつかない。

**実物をそのまま実行する**: このスクリプトは相対パスしか見ないので、cwd を使い捨ての
リポジトリにすればそこを検査する（コピーも差し替え口も要らない）。検査本体は stub に
差し替え、**ゲートの判断**（何を止めるか / 何回走らせるか / 判定不能を通すか）だけを見る。
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from git_env import scrub

ROOT = Path(__file__).resolve().parents[3]
HOOK = ROOT / ".githooks" / "pre-commit"


class PreCommitTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self.scripts = self.root / ".claude-plugin" / "scripts"
        (self.scripts / "tests").mkdir(parents=True)
        self.git("init", "-q", ".")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.git("commit", "-q", "--allow-empty", "-m", "init")
        # 既定はすべて通る stub
        self.set_ssot(0)
        self.set_quality(0)
        self.set_tests(0)

    # ---- fixture ------------------------------------------------------------
    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=str(self.root), capture_output=True,
                              text=True, env=self.env(), check=True)

    def env(self) -> dict[str, str]:
        return scrub()   # git hook 由来の変数を落とす（正本と理由は `git_env`）

    def write(self, rel: str, body: str, mode: int = 0o644) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        path.chmod(mode)
        return path

    def set_ssot(self, code: int, message: str = "SSoT stub") -> None:
        self.write(".claude-plugin/scripts/validate-ssot.sh",
                   "#!/usr/bin/env bash\necho '%s'\nexit %d\n" % (message, code), 0o755)

    def set_quality(self, code: int) -> None:
        self.write(".claude-plugin/scripts/validate_plugin_quality.py",
                   "print('quality stub')\nimport sys; sys.exit(%d)\n" % code)

    def set_tests(self, code: int, message: str = "test stub") -> None:
        """回帰テストの stub。**呼ばれた回数を記録する**（二重実行の検出用）."""
        self.write(".claude-plugin/scripts/run-tests.py",
                   "import sys\n"
                   "open('run-tests.count', 'a').write('x')\n"
                   "print(%r)\n"
                   "sys.exit(%d)\n" % (message, code))

    @property
    def test_runs(self) -> int:
        path = self.root / "run-tests.count"
        return len(path.read_text()) if path.exists() else 0

    def stage(self, rel: str, body: str = "x\n") -> None:
        self.write(rel, body)
        self.git("add", rel)

    def stage_plugin_change(self, *, bump: bool = True, changelog: bool = True) -> None:
        self.write("demo/.claude-plugin/plugin.json", '{"name":"demo","version":"1.0.0"}')
        self.write("demo/CHANGELOG.md", "# Changelog\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "baseline")
        self.stage("demo/skills/s/SKILL.md", "変更\n")
        if bump:
            self.stage("demo/.claude-plugin/plugin.json", '{"name":"demo","version":"1.0.1"}')
        if changelog:
            self.stage("demo/CHANGELOG.md", "# Changelog\n\n## 1.0.1\n")

    def run_hook(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(HOOK)], cwd=str(self.root), capture_output=True,
                              text=True, env=self.env(), timeout=60)

    # ---- 通す側 -------------------------------------------------------------
    def test_nothing_staged_is_a_no_op(self):
        res = self.run_hook()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(self.test_runs, 0, "何も staged で無いなら検査も走らせない")

    def test_a_clean_change_passes(self):
        self.stage("docs/note.md")
        res = self.run_hook()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(self.test_runs, 1)

    def test_a_properly_bumped_plugin_change_passes(self):
        self.stage_plugin_change()
        res = self.run_hook()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    # ---- 止める側 -----------------------------------------------------------
    def test_missing_version_bump_blocks(self):
        self.stage_plugin_change(bump=False, changelog=False)
        res = self.run_hook()
        self.assertEqual(res.returncode, 1)
        self.assertIn("Version bump required", res.stdout)

    def test_missing_changelog_blocks(self):
        self.stage_plugin_change(changelog=False)
        res = self.run_hook()
        self.assertEqual(res.returncode, 1)
        self.assertIn("CHANGELOG.md update required", res.stdout)

    def test_a_running_mutation_test_blocks(self):
        """変異体がディスク上にある状態で staging すると変異が index に入る."""
        self.stage("docs/note.md")
        self.write(".mutation-test-journal.json", "{}")
        res = self.run_hook()
        self.assertEqual(res.returncode, 1)
        self.assertIn("変異テストが実行中", res.stdout)
        self.assertEqual(self.test_runs, 0, "以降の検査は走らせない")

    def test_ssot_violation_blocks(self):
        self.stage("docs/note.md")
        self.set_ssot(1, "marketplace がずれている")
        res = self.run_hook()
        self.assertEqual(res.returncode, 1)
        self.assertIn("plugin.json が SSoT", res.stdout)

    def test_an_undecidable_ssot_check_is_not_waved_through(self):
        """exit 2（jsonschema 不在等）を通すと、ローカル緑 / CI 赤が push まで見えない.

        **「違反が無い」と「検査できていない」を同じ扱いにしない**（issue #140）。
        """
        self.stage("docs/note.md")
        self.set_ssot(2, "jsonschema が無い")
        res = self.run_hook()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("判定不能", res.stdout)
        self.assertEqual(self.test_runs, 0, "前提が崩れている状態で先へ進まない")

    def test_quality_errors_block(self):
        self.stage("docs/note.md")
        self.set_quality(1)
        res = self.run_hook()
        self.assertEqual(res.returncode, 1)
        self.assertIn("validate_plugin_quality.py の errors", res.stdout)

    def test_failing_tests_block_and_are_shown(self):
        self.stage("docs/note.md")
        self.set_tests(1, "FAILED (failures=3)")
        res = self.run_hook()
        self.assertEqual(res.returncode, 1)
        self.assertIn("FAILED (failures=3)", res.stdout, "失敗内容を見せずに落とさない")

    def test_the_suite_is_not_run_twice_on_failure(self):
        """実測 92 秒のスイートを、落ちた回だけ 2 度払っていた（表示のための再実行）."""
        self.stage("docs/note.md")
        self.set_tests(1)
        self.run_hook()
        self.assertEqual(self.test_runs, 1)

    def test_a_leaked_process_warning_does_not_block(self):
        """残留プロセスの警告は「後始末の漏れ」で、commit は止めない（見せはする）."""
        self.stage("docs/note.md")
        self.set_tests(0, "[run-tests] テスト終了後に 2 個のプロセスが残っている: 1, 2")
        res = self.run_hook()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("[run-tests]", res.stdout)

    # ---- ゲート自体の欠落（GitHub issue #176）--------------------------------
    def test_a_missing_ssot_gate_blocks(self):
        """検査スクリプトの欠落は「違反なし」ではなく「検査していない」.

        以前は `[ -f ]` で存在しなければ黙って通していたため、**検査を消すだけで
        commit が素通り**した。同じリポジトリの他の検査（INDEX.md 欠落を error にする）と
        流儀を揃える。
        """
        self.stage("docs/note.md")
        (self.root / ".claude-plugin" / "scripts" / "validate-ssot.sh").unlink()
        res = self.run_hook()
        self.assertEqual(res.returncode, 1, "ゲートの欠落が素通りしている")
        self.assertIn("validate-ssot.sh", res.stdout)
        self.assertEqual(self.test_runs, 0, "前提が崩れている状態で先へ進まない")

    def test_a_missing_quality_gate_blocks(self):
        self.stage("docs/note.md")
        (self.root / ".claude-plugin" / "scripts" / "validate_plugin_quality.py").unlink()
        res = self.run_hook()
        self.assertEqual(res.returncode, 1, "ゲートの欠落が素通りしている")
        self.assertIn("validate_plugin_quality.py", res.stdout)

    def test_a_missing_tests_directory_blocks(self):
        self.stage("docs/note.md")
        (self.root / ".claude-plugin" / "scripts" / "run-tests.py").unlink()
        (self.root / ".claude-plugin" / "scripts" / "tests").rmdir()
        res = self.run_hook()
        self.assertEqual(res.returncode, 1, "テストディレクトリの欠落が素通りしている")
        self.assertIn("tests", res.stdout)

    def test_uncollected_tests_are_not_reported_as_a_failure(self):
        """exit 5（1 件も収集されなかった）は「失敗」ではなく「測れていない」と伝える."""
        self.stage("docs/note.md")
        self.set_tests(5, "Ran 0 tests")
        res = self.run_hook()
        self.assertEqual(res.returncode, 1, "収集ゼロを通している")
        self.assertIn("1 件も走っていません", res.stdout)


if __name__ == "__main__":
    unittest.main()
