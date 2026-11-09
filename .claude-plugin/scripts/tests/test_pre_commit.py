#!/usr/bin/env python3
"""`.githooks/pre-commit` の回帰テスト（GitHub issue #139 / #140）.

**機械層のゲート本体**（バージョンバンプ / CHANGELOG / plugin eval の鮮度 / SSoT / 品質）で、
ここが素通りすると下流の検査がいくら正しくても commit は通る。壊れ方は静かで、
「ブロックされなかった＝問題が無かった」と区別がつかない。

**実物をそのまま実行する**: このスクリプトは相対パスしか見ないので、cwd を使い捨ての
リポジトリにすればそこを検査する（コピーも差し替え口も要らない）。検査本体は stub に
差し替え、**ゲートの判断**（何を止めるか / 何を走らせないか / 判定不能を通すか）だけを見る。

**回帰テストは pre-commit から外した**（2026-11-08 決定 / GitHub issue #436。CI が ubuntu と macOS で
回す）。`run-tests.py` の stub は呼ばれた回数を数えるために置き、**呼ばれないこと**を確かめる。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from git_env import scrub

ROOT = Path(__file__).resolve().parents[3]
HOOK = ROOT / ".githooks" / "pre-commit"
PLUGIN_EVAL = ROOT / ".claude-plugin" / "scripts" / "plugin-eval.sh"


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
        # plugin eval の鮮度ゲートは指紋の算法を plugin-eval.sh から借りる。stub にすると
        # 「指紋が一致するか」の判断そのものが消えるので**実物**を置く（eval 自体は
        # pre-commit から呼ばれないので claude CLI は要らない）
        shutil.copy(PLUGIN_EVAL, self.scripts / "plugin-eval.sh")
        (self.scripts / "plugin-eval.sh").chmod(0o755)

    # ---- fixture ------------------------------------------------------------
    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=str(self.root), capture_output=True,
                              text=True, env=self.env(), check=True)

    def env(self) -> dict[str, str]:
        env = scrub()   # git hook 由来の変数を落とす（正本と理由は `git_env`）
        # 迂回の変数も継承しない。この変数が入った環境からこのスイートが走ると、ゲートが止めることを
        # 見るテストまで迂回されて落ちる（2026-10-08 の実測。当時は `PLUGIN_EVAL_SKIP=1 git commit` の
        # pre-commit からスイートを回していた）。
        # 迂回を試すテストは `run_hook(PLUGIN_EVAL_SKIP="1")` で明示する
        env.pop("PLUGIN_EVAL_SKIP", None)
        return env

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
        """回帰テストの stub。**呼ばれた回数を記録する**（pre-commit が呼ばないことの確認用）."""
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

    def run_hook(self, **extra_env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(HOOK)], cwd=str(self.root), capture_output=True,
                              text=True, env=self.env() | extra_env, timeout=60)

    # ---- plugin eval ゲートの fixture ----------------------------------------
    def stage_eval_plugin_change(self, rel: str = "demo/skills/s/SKILL.md") -> None:
        """eval ケースを持つプラグインの、eval 入力に当たるファイルを bump 込みで stage する."""
        self.write("demo/evals/c/prompt.md", "do it\n")
        self.write("demo/evals/c/graders/g.md", "good\n")
        self.stage_plugin_change()
        if rel != "demo/skills/s/SKILL.md":
            self.stage(rel, "変更\n")

    def fingerprint(self, plugin: str = "demo") -> str:
        res = subprocess.run(["bash", str(self.scripts / "plugin-eval.sh"), "--fingerprint", plugin],
                             cwd=str(self.root), capture_output=True, text=True, check=True)
        return res.stdout.strip()

    def record_eval(self, fingerprint: str, code: int = 0) -> None:
        self.write("demo/evals/results/.last-eval",
                   "fingerprint=%s\nexit=%d\nat=2026-01-01T00:00:00Z\n" % (fingerprint, code))

    # ---- 通す側 -------------------------------------------------------------
    def test_nothing_staged_is_a_no_op(self):
        res = self.run_hook()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(self.test_runs, 0, "何も staged で無いなら検査も走らせない")

    def test_a_clean_change_passes(self):
        self.stage("src/note.txt")
        res = self.run_hook()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_the_regression_suite_is_left_to_ci(self):
        """コミットのたびにフルスイートを回さない（並列の作業で待ち・時間切れが出ていた / #436）.

        プラグイン配下・CLAUDE.md のようなテストが読む側の変更でも回さない。テストが落ちる
        状態で通るのは、回帰テストの stub を落ちる側にしても通ることで確かめる。
        """
        self.set_tests(1, "FAILED (failures=3)")
        self.stage_plugin_change()
        self.stage("CLAUDE.md")
        res = self.run_hook()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(self.test_runs, 0, "pre-commit が回帰テストを起動している")
        self.assertNotIn("FAILED", res.stdout)

    def test_a_docs_only_change_still_runs_the_other_gates(self):
        self.stage("docs/a.md")
        self.set_quality(1)
        res = self.run_hook()
        self.assertEqual(res.returncode, 1, "docs だけの変更でも品質の検査は省かない")
        self.assertIn("validate_plugin_quality.py の errors", res.stdout)

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
        self.stage("src/note.txt")
        self.write(".mutation-test-journal.json", "{}")
        res = self.run_hook()
        self.assertEqual(res.returncode, 1)
        self.assertIn("変異テストが実行中", res.stdout)

    def test_ssot_violation_blocks(self):
        self.stage("src/note.txt")
        self.set_ssot(1, "marketplace がずれている")
        res = self.run_hook()
        self.assertEqual(res.returncode, 1)
        self.assertIn("plugin.json が SSoT", res.stdout)

    def test_an_undecidable_ssot_check_is_not_waved_through(self):
        """exit 2（jsonschema 不在等）を通すと、ローカル緑 / CI 赤が push まで見えない.

        **「違反が無い」と「検査できていない」を同じ扱いにしない**（issue #140）。
        """
        self.stage("src/note.txt")
        self.set_ssot(2, "jsonschema が無い")
        res = self.run_hook()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("判定不能", res.stdout)

    def test_quality_errors_block(self):
        self.stage("src/note.txt")
        self.set_quality(1)
        res = self.run_hook()
        self.assertEqual(res.returncode, 1)
        self.assertIn("validate_plugin_quality.py の errors", res.stdout)

    # ---- plugin eval の鮮度 ---------------------------------------------------
    def test_an_eval_input_change_without_a_matching_eval_blocks(self):
        """スキル本文を変えたのに、その内容で `claude plugin eval` を回していない."""
        self.stage_eval_plugin_change()
        res = self.run_hook()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("plugin eval required", res.stdout)
        self.assertIn("plugin-eval.sh demo", res.stdout, "回すコマンドを示す")

    def test_a_stale_eval_record_blocks(self):
        """一度回した後に SKILL.md を直した — 記録の指紋は古い内容のもの."""
        self.stage_eval_plugin_change()
        self.record_eval("0000000000")
        res = self.run_hook()
        self.assertEqual(res.returncode, 1)
        self.assertIn("回していない", res.stdout)

    def test_a_matching_passing_eval_passes(self):
        self.stage_eval_plugin_change()
        self.record_eval(self.fingerprint())
        res = self.run_hook()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_a_matching_but_failing_eval_blocks(self):
        """回してはいるが閾値未満（exit 1）のまま — 「回した」だけでは通さない."""
        self.stage_eval_plugin_change()
        self.record_eval(self.fingerprint(), code=1)
        res = self.run_hook()
        self.assertEqual(res.returncode, 1)
        self.assertIn("閾値未満", res.stdout)

    def test_the_eval_gate_can_be_bypassed_explicitly(self):
        self.stage_eval_plugin_change()
        res = self.run_hook(PLUGIN_EVAL_SKIP="1")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_a_plugin_without_eval_cases_is_not_gated(self):
        """evals/ を持たないプラグイン（大半）は従来どおり. results/ だけの evals/ も同じ."""
        self.stage_plugin_change()
        self.write("demo/evals/results/old/report.html", "<html>")
        res = self.run_hook()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_a_non_input_change_is_not_gated(self):
        """hooks / CHANGELOG / README の変更は eval の結果に効かないので要求しない."""
        self.write("demo/evals/c/prompt.md", "do it\n")
        self.write("demo/.claude-plugin/plugin.json", '{"name":"demo","version":"1.0.0"}')
        self.write("demo/CHANGELOG.md", "# Changelog\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "baseline")
        self.stage("demo/hooks/scripts/h.sh", "echo\n")
        self.stage("demo/.claude-plugin/plugin.json", '{"name":"demo","version":"1.0.1"}')
        self.stage("demo/CHANGELOG.md", "# Changelog\n\n## 1.0.1\n")
        res = self.run_hook()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_an_eval_case_change_is_gated_too(self):
        """grader を変えたら判定基準が変わっているので、同じく回し直す."""
        self.write("demo/evals/c/prompt.md", "do it\n")
        self.stage_eval_plugin_change(rel="demo/evals/c/graders/g.md")
        res = self.run_hook()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("plugin eval required", res.stdout)

    # ---- ゲート自体の欠落（GitHub issue #176）--------------------------------
    def test_a_missing_ssot_gate_blocks(self):
        """検査スクリプトの欠落は「違反なし」ではなく「検査していない」.

        以前は `[ -f ]` で存在しなければ黙って通していたため、**検査を消すだけで
        commit が素通り**した。同じリポジトリの他の検査（INDEX.md 欠落を error にする）と
        流儀を揃える。
        """
        self.stage("src/note.txt")
        (self.root / ".claude-plugin" / "scripts" / "validate-ssot.sh").unlink()
        res = self.run_hook()
        self.assertEqual(res.returncode, 1, "ゲートの欠落が素通りしている")
        self.assertIn("validate-ssot.sh", res.stdout)

    def test_a_missing_quality_gate_blocks(self):
        self.stage("src/note.txt")
        (self.root / ".claude-plugin" / "scripts" / "validate_plugin_quality.py").unlink()
        res = self.run_hook()
        self.assertEqual(res.returncode, 1, "ゲートの欠落が素通りしている")
        self.assertIn("validate_plugin_quality.py", res.stdout)



if __name__ == "__main__":
    unittest.main()
