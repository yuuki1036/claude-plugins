#!/usr/bin/env python3
"""`run-oracles.sh` の回帰テスト（GitHub issue #137 / ADR-20260817170000）.

機械層を agent の手前に置く経路。**壊れ方が「静かに緑」になってはいけない**のがこの
スクリプトの要求仕様の中心なので、タイムアウト・実行不能・宣言なしを**それぞれ別の
status として区別できること**を測る（すべて `green` に倒れると reviewer は「機械層は
何も検出しなかった」と読む）。
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from test_code_review_scripts import PLUGIN, ScriptTestBase

ORACLES = PLUGIN / "scripts" / "run-oracles.sh"


class RunOraclesTest(ScriptTestBase):
    def declare(self, body: str) -> Path:
        d = self.root / ".claude"
        d.mkdir(exist_ok=True)
        path = d / "review-oracles.sh"
        path.write_text(body, encoding="utf-8")
        return path

    def run_oracles(self, *args: str, cwd: Path | None = None
                    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(ORACLES), *args], cwd=str(cwd or self.root),
                              capture_output=True, text=True, env=self._env(), timeout=120)

    def fields(self, out: str) -> dict[str, str]:
        got = {}
        for line in out.splitlines():
            if "=" in line and not line.startswith(" "):
                k, _, v = line.partition("=")
                if k in ("status", "exit_code", "elapsed_sec", "log"):
                    got[k] = v
        return got

    # ---- 宣言が無い / 引数 ---------------------------------------------------
    def test_no_declaration_is_a_silent_no_op(self):
        res = self.run_oracles()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout, "", "宣言が無いプロジェクトでは何も報告しない")

    def test_outside_a_git_repository_is_a_silent_no_op(self):
        outside = self.root / "tmp" / "not-a-repo"
        outside.mkdir(parents=True)
        env = {**self._env(), "GIT_CEILING_DIRECTORIES": str(outside.parent)}
        res = subprocess.run(["bash", str(ORACLES)], cwd=str(outside), capture_output=True,
                             text=True, env=env, timeout=60)
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout, "")

    def test_unknown_argument_exits_2(self):
        res = self.run_oracles("--force")
        self.assertEqual(res.returncode, 2)
        self.assertIn("usage", res.stderr)

    def test_flag_without_value_exits_2(self):
        for flag in ("--timeout", "--max-lines"):
            with self.subTest(flag=flag):
                res = self.run_oracles(flag)
                self.assertEqual(res.returncode, 2)
                self.assertIn("値が必要", res.stderr)

    def test_non_numeric_flag_exits_2(self):
        res = self.run_oracles("--timeout", "abc")
        self.assertEqual(res.returncode, 2)
        self.assertIn("数値のみ", res.stderr)

    # ---- status の区別 ------------------------------------------------------
    def test_green_when_the_oracle_succeeds(self):
        self.declare("#!/usr/bin/env bash\necho 'すべて通過'\n")
        res = self.run_oracles()
        self.assertEqual(res.returncode, 0, res.stderr)
        got = self.fields(res.stdout)
        self.assertEqual(got["status"], "green")
        self.assertEqual(got["exit_code"], "0")
        self.assertIn("## machine-layer", res.stdout)
        self.assertIn("すべて通過", res.stdout)

    def test_log_path_comes_from_the_shared_path_helper(self):
        """**パス導出は `lib/review-paths.sh` が正本**（式をここに複製しない）.

        `review_path` に種別が無いと rc=2 + stderr の FATAL になり、フォールバックの
        `$TMPDIR/review-oracles-$$.log` へ静かに逃げる。逃げると呼び出し間でパスが変わり、
        「配る前に消す」規約も効かない（実測でこの経路に落ちていた）。
        """
        self.declare("#!/usr/bin/env bash\necho x\n")
        res = self.run_oracles()
        self.assertNotIn("FATAL", res.stderr)
        log = Path(self.fields(res.stdout)["log"])
        self.assertIn("claude-code-review-", str(log.parent), "専用 tmproot の下に置く")
        self.assertRegex(log.name, r"^review-oracles-\d+\.log$")
        # 同一 worktree なら**呼び出しをまたいで同じパス**（PR 番号なしの self-review 経路）
        again = Path(self.fields(self.run_oracles().stdout)["log"])
        self.assertEqual(log, again)

    def test_red_when_the_oracle_reports_findings(self):
        self.declare("#!/usr/bin/env bash\necho 'ERROR: 3 件'\nexit 1\n")
        got = self.fields(self.run_oracles().stdout)
        self.assertEqual(got["status"], "red")
        self.assertEqual(got["exit_code"], "1")

    def test_error_is_distinguished_from_red_when_a_tool_is_missing(self):
        """**「検出した」と「動かなかった」を混ぜない.**

        オラクル script の最後のコマンドが見つからないと 127 で終わる。これを red に
        まとめると、機械層が動いていないのに「指摘があった」と読める。
        """
        self.declare("#!/usr/bin/env bash\nno_such_command_xyz\n")
        got = self.fields(self.run_oracles().stdout)
        self.assertEqual(got["status"], "error")
        self.assertEqual(got["exit_code"], "127")

    def test_timeout_is_reported_and_the_child_is_killed(self):
        """タイムアウトを green に倒さない。かつ**孫プロセスを走らせ続けない**."""
        canary = self.root / "tmp" / "after-sleep"
        self.declare("#!/usr/bin/env bash\nsleep 30\ntouch '%s'\n" % canary)
        res = self.run_oracles("--timeout", "1")
        self.assertEqual(res.returncode, 0, res.stderr)
        got = self.fields(res.stdout)
        self.assertEqual(got["status"], "timeout")
        self.assertEqual(got["exit_code"], "-1")
        self.assertLess(int(got["elapsed_sec"]), 25, "待ち切らずに打ち切ること")
        self.assertFalse(canary.exists(), "子プロセスが生き残って続きを実行した")

    def test_elapsed_seconds_is_reported(self):
        self.declare("#!/usr/bin/env bash\nexit 0\n")
        self.assertIn("elapsed_sec", self.fields(self.run_oracles().stdout))

    # ---- 出力の扱い --------------------------------------------------------
    def test_output_is_capped_and_the_omission_is_reported(self):
        """digest はオーケストレーターのコンテキストに載るので上限を切る（黙って捨てない）."""
        self.declare("#!/usr/bin/env bash\nseq 1 100\n")
        res = self.run_oracles("--max-lines", "10")
        body = [l for l in res.stdout.splitlines() if l.isdigit()]
        self.assertEqual(len(body), 10)
        self.assertIn("... (+90 行省略", res.stdout)

    def test_output_exactly_at_the_cap_reports_no_omission(self):
        """境界を両側から測る（`-ge` に取り違えると「+0 行省略」を出す）."""
        self.declare("#!/usr/bin/env bash\nseq 1 10\n")
        res = self.run_oracles("--max-lines", "10")
        self.assertEqual(len([l for l in res.stdout.splitlines() if l.isdigit()]), 10)
        self.assertNotIn("行省略", res.stdout)

    def test_full_output_is_kept_in_the_log(self):
        self.declare("#!/usr/bin/env bash\nseq 1 100\n")
        res = self.run_oracles("--max-lines", "5")
        log = Path(self.fields(res.stdout)["log"])
        self.assertTrue(log.is_file())
        self.assertEqual(len(log.read_text(encoding="utf-8").splitlines()), 100)

    def test_stderr_of_the_oracle_is_captured_too(self):
        self.declare("#!/usr/bin/env bash\necho 'WARN: 怪しい' >&2\nexit 1\n")
        res = self.run_oracles()
        self.assertIn("WARN: 怪しい", res.stdout, "stderr も digest に載せる（見落とす）")

    def test_a_previous_log_does_not_leak_into_the_next_run(self):
        self.declare("#!/usr/bin/env bash\necho '1 回目'\n")
        log = Path(self.fields(self.run_oracles().stdout)["log"])
        self.declare("#!/usr/bin/env bash\necho '2 回目'\n")
        res = self.run_oracles()
        self.assertIn("2 回目", res.stdout)
        self.assertNotIn("1 回目", res.stdout)
        self.assertNotIn("1 回目", log.read_text(encoding="utf-8"))

    def test_partial_output_survives_a_timeout(self):
        self.declare("#!/usr/bin/env bash\necho '途中まで'\nsleep 30\n")
        res = self.run_oracles("--timeout", "1")
        self.assertIn("途中まで", res.stdout, "打ち切っても得られた分は渡す")

    # ---- 起動 dir ----------------------------------------------------------
    def test_the_oracle_runs_at_the_repository_root(self):
        """self-review の cwd はセッション起動 dir のまま（サブディレクトリでも動く）."""
        sub = self.root / "deep" / "nested"
        sub.mkdir(parents=True)
        self.declare("#!/usr/bin/env bash\npwd\n")
        res = self.run_oracles(cwd=sub)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn(str(self.root), res.stdout)
        self.assertNotIn(str(sub), res.stdout)


if __name__ == "__main__":
    unittest.main()
