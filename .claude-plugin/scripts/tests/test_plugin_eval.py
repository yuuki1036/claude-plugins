#!/usr/bin/env python3
"""`plugin-eval.sh`（`claude plugin eval` の起動口 + 入力指紋の記録）の回帰テスト.

pre-commit の「スキル本文を変えたのに eval を回していない」ゲートは、このスクリプトが
残す `.last-eval` の指紋にだけ依存する。**指紋が入力の変化に追随しない**と、eval を
一度回した後は何を変えても pre-commit が通る（静かに緑）。逆に results/ や無関係な
ファイルで指紋が動くと、回した直後に止まる。両方向を見る。

`claude` は PATH 先頭の stub に差し替える（引数を記録し、指定の exit code を返す）。
PATH は絞らず**前置**する — 引ける側を列挙する規約（`docs/testing-pitfalls.md`）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude-plugin" / "scripts" / "plugin-eval.sh"


class PluginEvalTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        # スクリプトは自分の位置から REPO_ROOT を導くので、同じ相対位置にコピーする
        scripts = self.root / ".claude-plugin" / "scripts"
        scripts.mkdir(parents=True)
        self.script = scripts / "plugin-eval.sh"
        shutil.copy(SCRIPT, self.script)
        self.script.chmod(0o755)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.set_claude(0)
        self.write("demo/.claude-plugin/plugin.json", '{"name":"demo","version":"1.0.0"}')
        self.write("demo/skills/s/SKILL.md", "# s\n")
        self.write("demo/evals/c/prompt.md", "do it\n")
        self.write("demo/evals/c/graders/g.md", "good\n")

    def write(self, rel: str, body: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def set_claude(self, code: int) -> None:
        """`claude` の stub。呼ばれた cwd と引数を記録し、`code` で終わる."""
        stub = self.bin / "claude"
        stub.write_text("#!/usr/bin/env bash\n"
                        "printf '%%s\\n' \"$PWD\" \"$@\" > \"$CLAUDE_STUB_LOG\"\n"
                        "exit %d\n" % code)
        stub.chmod(0o755)

    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "")
        env["CLAUDE_STUB_LOG"] = str(self.root / "claude.log")
        return subprocess.run(["bash", str(self.script), *args], cwd=str(self.root),
                              capture_output=True, text=True, env=env, timeout=60)

    def fingerprint(self, plugin: str = "demo") -> str:
        res = self.run_script("--fingerprint", plugin)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout.strip()

    @property
    def marker(self) -> dict[str, str]:
        text = (self.root / "demo/evals/results/.last-eval").read_text()
        return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)

    # ---- 指紋 -----------------------------------------------------------------
    def test_fingerprint_is_stable_for_the_same_tree(self):
        self.assertEqual(self.fingerprint(), self.fingerprint())

    def test_fingerprint_follows_every_eval_input(self):
        """skills / commands / agents / references / evals のどれを変えても指紋が動く."""
        before = self.fingerprint()
        for rel in ("demo/skills/s/SKILL.md", "demo/commands/c.md", "demo/agents/a.md",
                    "demo/references/r.md", "demo/evals/c/graders/g.md"):
            self.write(rel, "changed %s\n" % rel)
            after = self.fingerprint()
            self.assertNotEqual(before, after, "%s の変更が指紋に出ていない" % rel)
            before = after

    def test_fingerprint_ignores_results_and_non_inputs(self):
        """results/ と、eval の結果に効かないファイルでは指紋が動かない.

        動くと「回した直後に pre-commit が止まる」— results/ は eval 自身が書くので
        特に危ない。
        """
        before = self.fingerprint()
        self.write("demo/evals/results/2026/aggregate-result.json", "{}")
        self.write("demo/evals/results/.last-eval", "fingerprint=x\n")
        self.write("demo/hooks/scripts/h.sh", "echo\n")
        self.write("demo/CHANGELOG.md", "# c\n")
        self.write("demo/README.md", "# r\n")
        self.assertEqual(before, self.fingerprint())

    def test_fingerprint_is_none_for_a_plugin_without_inputs(self):
        self.write("bare/.claude-plugin/plugin.json", "{}")
        self.assertEqual(self.fingerprint("bare"), "none")

    # ---- 実行と記録 -----------------------------------------------------------
    def test_a_run_records_the_fingerprint_and_exit_code(self):
        expected = self.fingerprint()
        res = self.run_script("demo")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.marker["fingerprint"], expected)
        self.assertEqual(self.marker["exit"], "0")
        self.assertIn("at", self.marker)

    def test_eval_runs_in_the_plugin_dir_with_the_default_flags(self):
        self.run_script("demo", "--runs", "1")
        cwd, *args = (self.root / "claude.log").read_text().splitlines()
        self.assertEqual(Path(cwd).resolve(), (self.root / "demo").resolve())
        self.assertEqual(args[:3], ["plugin", "eval", "."])
        self.assertIn("--no-publish", args)
        self.assertIn("--trust-plugin", args)
        self.assertEqual(args[-2:], ["--runs", "1"], "追加引数がそのまま渡っていない")

    def test_the_default_threshold_tolerates_judge_flake(self):
        """tool 既定の 1.0 だと LLM judge の票割れ 1 回で pre-commit が止まる."""
        self.run_script("demo")
        args = (self.root / "claude.log").read_text().splitlines()[1:]
        self.assertEqual(args[args.index("--threshold") + 1], "0.8")

    def test_an_explicit_threshold_replaces_the_default(self):
        """両方渡すと後勝ちかどうかが CLI 実装依存になるので、既定の方を引っ込める."""
        for extra in (["--threshold", "1.0"], ["--threshold=1.0"]):
            self.run_script("demo", *extra)
            args = (self.root / "claude.log").read_text().splitlines()[1:]
            self.assertEqual(sum(a.startswith("--threshold") for a in args), 1, args)
            self.assertNotIn("0.8", args)

    def test_the_cost_estimate_is_shown_before_the_run(self):
        """paid な実行を黙って始めない. 既定は 1 ケース × 2 アーム × 3 runs = 6 run."""
        res = self.run_script("demo")
        self.assertIn("1 ケース × 2 アーム × 3 runs = 6 run", res.stderr)
        self.assertIn("1.5〜3.0 USD", res.stderr)

    def test_the_cost_estimate_follows_runs_and_ablation(self):
        for extra in (["--runs", "1", "--ablation", "none"], ["--runs=1", "--ablation=none"]):
            res = self.run_script("demo", *extra)
            self.assertIn("1 ケース × 1 アーム × 1 runs = 1 run", res.stderr, extra)

    def test_the_cost_estimate_counts_each_case_once(self):
        """prompt.md と case.yaml を両方持つケースを 2 と数えない. results/ 配下も数えない."""
        self.write("demo/evals/c/case.yaml", "schema_version: '1.1'\n")
        self.write("demo/evals/d/prompt.md", "another\n")
        self.write("demo/evals/results/old/prompt.md", "stale\n")
        res = self.run_script("demo")
        self.assertIn("2 ケース × 2 アーム × 3 runs = 12 run", res.stderr)

    def test_a_failing_eval_is_recorded_and_propagated(self):
        """閾値未満（exit 1）を握り潰すと pre-commit が「回して通った」と読む."""
        self.set_claude(1)
        res = self.run_script("demo")
        self.assertEqual(res.returncode, 1)
        self.assertEqual(self.marker["exit"], "1")

    def test_the_fingerprint_is_taken_before_the_run(self):
        """eval 実行後の内容ではなく、eval が読んだ内容の指紋を残す.

        stub の claude が SKILL.md を書き換える（＝実行中の編集を模す）。記録される指紋は
        書き換え前のものでなければ、その後の pre-commit が「測った」と誤認する。
        """
        before = self.fingerprint()
        stub = self.bin / "claude"
        stub.write_text("#!/usr/bin/env bash\n"
                        "echo edited > \"%s\"\nexit 0\n" % (self.root / "demo/skills/s/SKILL.md"))
        stub.chmod(0o755)
        self.run_script("demo")
        self.assertEqual(self.marker["fingerprint"], before)
        self.assertNotEqual(self.fingerprint(), before)

    # ---- 入口の検査 -----------------------------------------------------------
    def test_a_non_plugin_target_is_refused(self):
        res = self.run_script("nope")
        self.assertEqual(res.returncode, 2)
        self.assertIn("プラグインではありません", res.stderr)

    def test_a_plugin_without_evals_is_refused_with_the_init_hint(self):
        self.write("noeval/.claude-plugin/plugin.json", "{}")
        res = self.run_script("noeval")
        self.assertEqual(res.returncode, 2)
        self.assertIn("claude plugin eval init", res.stderr)

    def test_no_arguments_prints_usage(self):
        res = self.run_script()
        self.assertEqual(res.returncode, 2)
        self.assertIn("usage", res.stderr)


if __name__ == "__main__":
    unittest.main()
