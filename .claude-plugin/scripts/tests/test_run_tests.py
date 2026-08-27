#!/usr/bin/env python3
"""`run-tests.py`（回帰テストの起動口 + 残留プロセスの回収）のテスト（GitHub issue #140）.

**測るのは「テストが緑でも外に副作用が残る」型を検出できるか**。実測の事故は
テスト全件 green のまま 12 本のプロセスが 4 時間回り続けたもので、**テストの成否では
検出できない**（発覚はユーザーの体感だった）。ここでは意図的に孫を置き去りにする
偽テストを走らせ、①検出して報告するか ②回収するか ③**緑判定を変えないか**を見る。

対象は実物をコピーしたもの（`ROOT` はスクリプト自身の位置から決まる）。
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude-plugin" / "scripts" / "run-tests.py"

PASSING = """import unittest


class T(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(True)
"""

FAILING = """import unittest


class T(unittest.TestCase):
    def test_ng(self):
        self.fail('わざと失敗')
"""

#: 孫を置き去りにする偽テスト（無限ループ化した被験スクリプトの代役）。
#: **待たずに終わる**ので、テスト自体は緑のまま孫だけが残る
LEAKING = """import os
import subprocess
import time
import unittest

MARKER = os.path.join(os.path.dirname(__file__), "leaked.pid")


class T(unittest.TestCase):
    def test_spawns_and_walks_away(self):
        # **stdout/stderr は切っておく**: 孫がパイプを掴んだままだと、回収されない回に
        # 呼び出し側の capture が EOF 待ちで止まり、「検出できなかった」ではなく
        # 「ハングした」になって観測できない（変異テストが 4 件 TIMEOUT で表れた）
        subprocess.Popen(["bash", "-c",
                          'echo $$ > "%s"; while :; do sleep 1; done' % MARKER],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if os.path.exists(MARKER):
                break
            time.sleep(0.05)
        self.assertTrue(os.path.exists(MARKER), "前提: 孫が起動して pid を書く")
"""


#: **SIGTERM を無視する**孫（回収に SIGKILL が要る回。実運用の残留はこちら側が普通で、
#: bash の `while :; do sleep N; done` も前景の sleep が終わるまで TERM を保留する）
LEAKING_STUBBORN = LEAKING.replace('echo $$ > "%s";', 'trap "" TERM; echo $$ > "%s";')

#: 孫を残したまま**長く走り続ける**偽テスト（上位層から殺される回の再現用）
LEAKING_SLOW = LEAKING.replace(
    '        self.assertTrue(os.path.exists(MARKER), "前提: 孫が起動して pid を書く")',
    '        self.assertTrue(os.path.exists(MARKER), "前提: 孫が起動して pid を書く")\n'
    '        time.sleep(60)   # ここで上位層に殺される')

#: 孫が**親の stdout/stderr をそのまま継承する**偽テスト（現実の残留はこちら）
LEAKING_INHERIT = LEAKING.replace(
    """,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)""", ")")


class RunTestsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self.scripts = self.root / ".claude-plugin" / "scripts"
        self.tests = self.scripts / "tests"
        self.tests.mkdir(parents=True)
        shutil.copy2(SCRIPT, self.scripts / "run-tests.py")
        # `run-tests.py` は起動口で git hook 由来の env を落とすのに `git_env` を読む
        shutil.copy2(SCRIPT.parent / "tests" / "git_env.py", self.tests / "git_env.py")
        self.marker = self.tests / "leaked.pid"
        self.addCleanup(self.kill_leftovers)

    def kill_leftovers(self) -> None:
        """**テストが失敗した回でも孫を残さない**（このテスト自身が事故の再現なので）."""
        if not self.marker.exists():
            return
        try:
            pid = int(self.marker.read_text().strip())
        except (ValueError, OSError):
            return
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    def write_test(self, body: str) -> None:
        (self.tests / "test_stub.py").write_text(body, encoding="utf-8")

    def run_wrapper(self, env: dict[str, str] | None = None
                    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(self.scripts / "run-tests.py")],
                              capture_output=True, text=True, timeout=120,
                              cwd=str(self.root), env=env or dict(os.environ))

    def alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    def running_test_pids(self) -> list[int]:
        """使い捨てリポジトリの tests/ を走らせている unittest プロセスの pid."""
        out = subprocess.run(["pgrep", "-f", str(self.tests)], capture_output=True, text=True)
        return [int(x) for x in out.stdout.split() if x.isdigit()]

    def leaked_pid_is_alive(self) -> bool:
        pid = int(self.marker.read_text().strip())
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    # ---- 終了コードは素通し（緑判定を変えない） -----------------------------
    def test_passing_tests_exit_0(self):
        self.write_test(PASSING)
        res = self.run_wrapper()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_collecting_nothing_never_looks_green(self):
        """1 件も収集されなかったら 5（測れていない）を返す（GitHub issue #176）.

        machine-layer は 5 を「判定不能」として扱う契約。**この終了コードは Python の版に
        依存してはいけない** — unittest 自身が no-tests で 5 を返すのは 3.12 以降で、
        それ以前は 0 なので、版差に任せると古い開発機だけ収集ゼロが緑に見える。
        """
        res = self.run_wrapper()          # tests/ に test_*.py を 1 つも置かない
        self.assertEqual(res.returncode, 5, res.stdout + res.stderr)
        self.assertIn("1 件も収集されなかった", res.stderr,
                      "「測れていない」を黙って返している（通知が出る条件が死んでいる）")

    def test_failing_tests_keep_their_exit_code(self):
        self.write_test(FAILING)
        res = self.run_wrapper()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("わざと失敗", res.stderr)

    def test_a_clean_run_says_nothing_about_processes(self):
        self.write_test(PASSING)
        res = self.run_wrapper()
        self.assertNotIn("残っている", res.stderr, "残留が無い回は黙る")
        self.assertNotIn("skip", res.stderr)

    # ---- 残留の検出と回収 ---------------------------------------------------
    def test_a_leaked_grandchild_is_reported_and_reaped(self):
        self.write_test(LEAKING)
        res = self.run_wrapper()
        self.assertTrue(self.marker.exists(), "前提: 孫が起動している")
        self.assertIn("残っている", res.stderr, "テストは緑なので、ここでしか気づけない")
        self.assertNotIn("回収できなかった", res.stderr, "回収できたのに誤報している")
        self.assertFalse(self.leaked_pid_is_alive(), "残留プロセスを回収していない")

    def test_a_grandchild_that_needs_sigkill_is_not_reported_as_unreapable(self):
        """**SIGKILL で落とせたものを「回収できなかった」と言わない**（GitHub issue #140 / M1）.

        送出の成否と生死は別物。再確認せずに「手動で kill しろ」と出すと、
        本当に落とせなかった回（権限不足・D state）と区別できず、
        唯一のエスカレーション経路がノイズになる。
        """
        self.write_test(LEAKING_STUBBORN)
        res = self.run_wrapper()
        self.assertIn("残っている", res.stderr, "前提: 残留として検出できている")
        self.assertNotIn("回収できなかった", res.stderr,
                         "SIGKILL で落とせたものを誤報している")
        self.assertFalse(self.leaked_pid_is_alive(), "SIGKILL まで上げても残っている")

    def test_a_leak_does_not_turn_a_green_run_red(self):
        """残留は「テストの失敗」ではなく後始末の漏れ（ここで赤にすると commit が止まる）."""
        self.write_test(LEAKING)
        res = self.run_wrapper()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_being_killed_from_above_still_reaps_the_test_group(self):
        """**自分が上位層に殺される回**でも、テスト木を残さない（GitHub issue #140 / C1）.

        `mutation-test.py` は timeout でプロセスグループごと回収する。テストを別**セッション**に
        置くとその killpg が届かず、こちらが即死してテスト木が孤児になる
        （実測: 孫 3 本が ppid=1 で 2 時間残っていた）。グループだけ分けて同一セッションに
        留まり、シグナルを受けたら**自分のグループを回収してから死ぬ**ことを固定する。
        """
        self.write_test(LEAKING_SLOW)
        with subprocess.Popen([sys.executable, str(self.scripts / "run-tests.py")],
                              cwd=str(self.root), stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL) as proc:
            self.addCleanup(proc.kill)
            for _ in range(200):
                if self.marker.exists():
                    break
                time.sleep(0.05)
            self.assertTrue(self.marker.exists(), "前提: 孫が起動している")
            child = self.running_test_pids()
            self.assertTrue(child, "前提: テスト本体が走っている")
            os.kill(proc.pid, signal.SIGTERM)
            proc.wait(timeout=30)
        time.sleep(1)
        self.assertFalse(self.leaked_pid_is_alive(), "孫を置き去りにしている")
        for pid in child:
            self.assertFalse(self.alive(pid), "テスト本体 %d が走り続けている" % pid)

    def test_a_leak_holding_the_output_pipe_does_not_hang_the_caller(self):
        """呼び出し側は `OUT="$(run-tests.py 2>&1)"` で使う（#140 / C2）.

        子の stdio をそのまま継承させると、残留した孫がパイプの write 端を握り続け、
        こちらが終了してもコマンド置換が EOF を待って**無言でハングする**（＝`git commit`
        が固まる）。回収できない状況（`pgrep` 不在）でも返ることを固定する。
        """
        bash = shutil.which("bash")
        self.assertIsNotNone(bash)
        no_pgrep = self.root / "no-pgrep"
        no_pgrep.mkdir()
        (no_pgrep / "bash").symlink_to(bash)
        self.write_test(LEAKING_INHERIT)
        res = self.run_wrapper(env={**os.environ, "PATH": str(no_pgrep)})   # timeout=120
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("skip", res.stderr, "前提: 回収できない状況を作れている")
        self.assertTrue(self.marker.exists(), "前提: 孫が残っている")
        self.assertTrue(self.leaked_pid_is_alive(), "前提: 回収されずに生きている")

    def test_a_process_we_may_not_kill_is_reported_not_crashed(self):
        """権限が無い相手は **traceback ではなく「回収できなかった」**として報告する（M2）.

        `os.kill` の `PermissionError` を捕まえないと `main` を貫通し、**緑のテストが
        traceback + exit 1** に化ける（「終了コードはテストのものをそのまま返す」契約違反）。
        pid 1 を返す `pgrep` の stub で、その経路だけを再現する。
        """
        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        stub = fake_bin / "pgrep"
        stub.write_text("#!/usr/bin/env bash\nprintf '1\\n'\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
        self.write_test(PASSING)
        res = self.run_wrapper(env={**os.environ, "PATH": "%s:%s" % (fake_bin, os.environ["PATH"])})
        self.assertEqual(res.returncode, 0, "後始末の失敗をテストの結果に載せている")
        self.assertNotIn("Traceback", res.stderr)
        self.assertIn("回収できなかった", res.stderr, "落とせなかったものは人に渡す")

    def test_without_pgrep_detection_is_skipped_not_silently_passed(self):
        """`pgrep` が引けない環境では**判定を skip したと言う**（黙って緑にしない）."""
        empty_bin = self.root / "empty-bin"
        empty_bin.mkdir()
        self.write_test(PASSING)
        res = self.run_wrapper(env={**os.environ, "PATH": str(empty_bin)})
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("skip", res.stderr)


class RanCountTest(unittest.TestCase):
    """集計行から件数を読む処理（GitHub issue #176）.

    E2E では新しい Python が自前で 5 を返すため**この判定を一度も通らない**ので、
    版差を吸収する当の処理はここで直接表明する（期待値はテスト側で独立に組む）。
    """

    @staticmethod
    def _module():
        spec = importlib.util.spec_from_file_location("_run_tests_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_reads_the_summary_line(self):
        self.assertEqual(self._module()._ran_count(b"Ran 12 tests in 1.2s\n\nOK\n"), 12)

    def test_a_single_test_uses_the_singular_form(self):
        self.assertEqual(self._module()._ran_count(b"Ran 1 test in 0.1s\n\nOK\n"), 1)

    def test_zero_is_zero(self):
        self.assertEqual(
            self._module()._ran_count(b"Ran 0 tests in 0.000s\n\nNO TESTS RAN\n"), 0)

    def test_a_missing_summary_counts_as_zero(self):
        """集計行が無い（収集前にクラッシュした等）＝走ったと見なさない."""
        self.assertEqual(
            self._module()._ran_count(b"Traceback (most recent call last):\n"), 0)

    # ---- 終了コードの決定（rc と件数の組み合わせ）--------------------------
    def test_green_with_no_tests_becomes_unmeasured(self):
        self.assertEqual(self._module()._exit_code(0, b"Ran 0 tests in 0.0s\n"), 5)

    def test_green_with_tests_stays_green(self):
        self.assertEqual(self._module()._exit_code(0, b"Ran 7 tests in 0.1s\n"), 0)

    def test_a_failure_keeps_its_own_code_even_with_no_tests(self):
        """失敗の rc を 5 に塗り潰さない（直しどころが分からなくなる）."""
        self.assertEqual(self._module()._exit_code(1, b"Ran 0 tests in 0.0s\n"), 1)

    def test_a_failure_with_tests_keeps_its_code(self):
        self.assertEqual(self._module()._exit_code(1, b"Ran 7 tests in 0.1s\n"), 1)


if __name__ == "__main__":
    unittest.main()
