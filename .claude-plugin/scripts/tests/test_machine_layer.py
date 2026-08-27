#!/usr/bin/env python3
"""`machine-layer.sh` の回帰テスト（GitHub issue #137）.

**exit code が契約**（0 = 緑 / 1 = 検出 / 2 = 判定不能）で、呼び出し側はこれで分岐する:

- Stop hook（`auto-quality-check.sh`）… 1 は問題として通知、2 は「判定不能」として通知
- self-review 前段（`run-oracles.sh` ← `.claude/review-oracles.sh`）… 2 を green に倒さない

**2 を 0 と混ぜると「機械層が死んでいる」と「通っている」が区別できない**ので、
そこを中心に固定する。検査本体は実行に数分かかるため、`MACHINE_LAYER_ROOT` で
stub を置いた使い捨てリポジトリに向けて契約だけを見る。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude-plugin" / "scripts" / "machine-layer.sh"

STUB_OK = "#!/usr/bin/env bash\nexit 0\n"


class MachineLayerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self.scripts = self.root / ".claude-plugin" / "scripts"
        self.scripts.mkdir(parents=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        # 既定はすべて通る stub（テストごとに必要なものだけ差し替える）
        self.write_stub("validate-ssot.sh", STUB_OK)
        self.write_stub("validate_plugin_quality.py", "import sys\nsys.exit(0)\n")
        # 回帰テストの起動口は本物を使う（stub にすると「テストを実際に走らせて
        # 失敗を拾う」という検査 3（回帰テスト）の要件そのものが検証されなくなる）
        shutil.copy2(ROOT / ".claude-plugin" / "scripts" / "run-tests.py",
                     self.scripts / "run-tests.py")

    def write_stub(self, name: str, body: str) -> Path:
        p = self.scripts / name
        p.write_text(body, encoding="utf-8")
        p.chmod(0o755)
        return p

    def with_tests_dir(self, passing: bool = True) -> None:
        """`unittest discover` の対象を置く（`python3 -m unittest` を実際に走らせる）."""
        d = self.scripts / "tests"
        d.mkdir(exist_ok=True)
        # 本物の `run-tests.py` は起動口で git hook 由来の env を落とすのに `git_env` を読む
        shutil.copy2(Path(__file__).resolve().parent / "git_env.py", d / "git_env.py")
        body = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n"
        body += "        self.assertTrue(True)\n" if passing else "        self.fail('わざと失敗')\n"
        (d / "test_stub.py").write_text(body, encoding="utf-8")

    def env(self, with_python: bool = True, with_claude: bool = False) -> dict[str, str]:
        """PATH を絞った環境を作る（本物の `claude` を引くと実リポジトリの検査が走る）.

        **「このディレクトリには無いはず」に頼らない。** Linux では `/bin` が `/usr/bin` の
        symlink なので、`/bin` を混ぜると python3 が引けてしまう（実測: `with_python=False`
        の 2 件が ubuntu でだけ落ちた）。**引けるものを列挙する**側で作る。
        """
        env = dict(os.environ)
        env["MACHINE_LAYER_ROOT"] = str(self.root)
        link = self.bin / "python3"
        if with_python:
            if not link.exists():
                link.symlink_to(sys.executable)
        else:
            link.unlink(missing_ok=True)
        # bash は常に要る。section 4（CLI スキーマ検査）は find / xargs / grep / sort /
        # basename を使うので、python3 がある構成だけそれらを足す
        needed = ["bash"]
        if with_python:
            needed += ["find", "xargs", "grep", "sort", "basename", "tail", "dirname"]
        for name in needed:
            real = shutil.which(name)
            self.assertIsNotNone(real, "%s が見つからない" % name)
            dest = self.bin / name
            if not dest.exists():
                dest.symlink_to(real)
        env["PATH"] = str(self.bin)
        if with_claude:
            self.write_claude_stub()
        return env

    def write_claude_stub(self, *findings: str) -> None:
        """`claude` の stub。**bash builtin だけで書く**（PATH を絞るので `cat` は引けない）.

        実測: `cat <<EOF` の stub が `cat: command not found` で落ち、出力が空になったため
        「指摘なし」と区別できなかった。stub が壊れていても**テストは緑に見える**型なので、
        `test_..._reported_per_plugin` の assert が唯一の防壁になる。
        """
        self.write_claude_stub_rc(0, *findings)

    def write_claude_stub_rc(self, code: int, *findings: str) -> None:
        """終了コードも指定できる `claude` stub（rc を捨てていないかの検証用）."""
        stub = self.bin / "claude"
        args = " ".join("'%s'" % f.replace("'", "'\\''") for f in findings) or "''"
        stub.write_text("#!/usr/bin/env bash\nprintf '%%s\\n' %s\nexit %d\n" % (args, code),
                        encoding="utf-8")
        stub.chmod(0o755)

    def run_layer(self, env: dict[str, str] | None = None
                  ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(SCRIPT)], cwd=str(self.root), capture_output=True,
                              text=True, env=env or self.env(), timeout=120)

    # ---- exit code の契約 --------------------------------------------------
    def test_all_green_exits_0_with_no_output(self):
        self.with_tests_dir(passing=True)
        res = self.run_layer()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(res.stdout, "", "緑のときは何も出さない（no-op を報告しない）")

    def test_ssot_failure_exits_1_and_reports(self):
        self.write_stub("validate-ssot.sh",
                        "#!/usr/bin/env bash\necho 'marketplace が同期していない'\nexit 1\n")
        self.with_tests_dir(passing=True)
        res = self.run_layer()
        self.assertEqual(res.returncode, 1)
        self.assertIn("marketplace が同期していない", res.stdout)

    def test_quality_failure_exits_1_and_reports(self):
        self.write_stub("validate_plugin_quality.py",
                      "print('allowed-tools が一致しない')\nimport sys; sys.exit(1)\n")
        self.with_tests_dir(passing=True)
        res = self.run_layer()
        self.assertEqual(res.returncode, 1)
        self.assertIn("allowed-tools が一致しない", res.stdout)

    def test_failing_tests_exit_1_and_are_labelled(self):
        self.with_tests_dir(passing=False)
        res = self.run_layer()
        self.assertEqual(res.returncode, 1)
        self.assertIn("[unit-tests]", res.stdout)

    def test_ssot_unknown_verdict_is_not_reported_as_a_detection(self):
        """子の exit 2 を 1 に混ぜない（「直せるもの」と「判定できなかった」は別物）.

        `validate-ssot.sh` は jsonschema が無いと 2 を返す。ここで 1 に倒すと
        「品質問題あり」として通知され、直せない指摘が指摘欄に出る。
        """
        self.write_stub("validate-ssot.sh",
                        "#!/usr/bin/env bash\necho 'jsonschema が無い' >&2\nexit 2\n")
        self.with_tests_dir(passing=True)
        res = self.run_layer()
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("判定不能", res.stdout)
        self.assertIn("jsonschema が無い", res.stdout)

    def test_unknown_verdict_wins_over_detections(self):
        """判定不能と検出が同居したら 2（機械層を信用してよいかが呼び出し側の関心）."""
        self.write_stub("validate-ssot.sh", "#!/usr/bin/env bash\nexit 2\n")
        self.write_stub("validate_plugin_quality.py",
                        "print('allowed-tools が一致しない')\nimport sys; sys.exit(1)\n")
        self.with_tests_dir(passing=True)
        res = self.run_layer()
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("判定不能", res.stdout)
        self.assertIn("allowed-tools が一致しない", res.stdout, "検出内容も捨てない")

    def test_a_check_that_could_not_run_is_unknown_not_a_detection(self):
        """検査 2 / 3 の「実行できなかった」も 1 に畳まない（GitHub issue #140 / M5）.

        スクリプト不在（python の exit 2 / 127）を「品質問題あり」として通知すると、
        直せないものが指摘欄に出る。検査 1 だけに入れていた区別を全検査へ揃える。
        """
        cases = (("validate_plugin_quality.py", "品質検査が判定不能"),
                 ("run-tests.py", "回帰テストが判定不能"))
        for name, fragment in cases:
            with self.subTest(script=name):
                self.setUp()
                self.with_tests_dir(passing=True)
                (self.scripts / name).unlink()   # 実行できない状態にする
                res = self.run_layer()
                self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
                self.assertIn(fragment, res.stdout)

    def test_a_leaked_process_warning_is_not_swallowed(self):
        """`run-tests.py` の残留警告は **rc=0 でも捨てない**（#140 / M4）.

        残留は exit code に載らない契約なので、rc だけ見ていると Stop hook と
        self-review 前段の 2 経路で #140 の検出が丸ごと消える。
        """
        self.with_tests_dir(passing=True)
        self.write_stub("run-tests.py",
                        "import sys\n"
                        "print('[run-tests:leak] テスト終了後に 2 個のプロセスが残っている: 1, 2',"
                        " file=sys.stderr)\n"
                        "sys.exit(0)\n")
        res = self.run_layer()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("残っている", res.stdout)

    def test_missing_python_exits_2_not_0(self):
        """**「判定不能」を「通過」に倒さない.**

        python3 が無いと品質検査と回帰テストが走らないので、0 を返すと
        「機械層が通った」と読まれる（緑と欠測の区別が消える）。
        """
        res = self.run_layer(env=self.env(with_python=False))
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("python3", res.stderr)

    def test_missing_python_still_reports_what_it_managed_to_find(self):
        """判定不能でも、そこまでに検出したものは捨てない."""
        self.write_stub("validate-ssot.sh", "#!/usr/bin/env bash\necho 'SSoT NG'\nexit 1\n")
        res = self.run_layer(env=self.env(with_python=False))
        self.assertEqual(res.returncode, 2)
        self.assertIn("SSoT NG", res.stdout)

    def test_unreachable_root_exits_2(self):
        env = dict(os.environ, MACHINE_LAYER_ROOT=str(self.root / "no-such-dir"))
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 2)
        self.assertIn("FATAL", res.stderr)

    # ---- CLI スキーマ検査（`claude` があるときだけ） ------------------------
    def test_schema_findings_are_reported_per_plugin(self):
        (self.root / "demo" / ".claude-plugin").mkdir(parents=True)
        (self.root / "demo" / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
        self.with_tests_dir(passing=True)
        env = self.env(with_claude=True)
        self.write_claude_stub("  ❯ name: 必須フィールドが無い")
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("[schema:demo]", res.stdout)

    def test_ssot_only_warnings_are_filtered_out(self):
        """`_requirements` / `_superseded_by` は独自フィールドなので警告から除外する."""
        (self.root / "demo" / ".claude-plugin").mkdir(parents=True)
        (self.root / "demo" / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
        self.with_tests_dir(passing=True)
        env = self.env(with_claude=True)
        self.write_claude_stub("  ❯ _requirements: Unknown field", "  ❯ _superseded_by: Unknown")
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertEqual(res.stdout, "")

    def test_missing_claude_cli_does_not_make_the_whole_run_unknown(self):
        """`claude` が無い環境ではこの検査だけ skip（1〜3 は判定済みなので 0 でよい）."""
        self.with_tests_dir(passing=True)
        res = self.run_layer(env=self.env(with_claude=False))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_a_failing_cli_that_reports_nothing_is_unknown_not_green(self):
        """rc を捨てない（GitHub issue #176）.

        指摘の抽出は出力の `❯` 行に依存しているので、CLI が出力形式を変えた版では
        **1 行も拾えず無言で常時緑**になる。rc が非ゼロなのに抽出が空なら
        「違反なし」ではなく「読めなかった」（exit 2）に倒す。
        """
        (self.root / "demo" / ".claude-plugin").mkdir(parents=True)
        (self.root / "demo" / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
        self.with_tests_dir(passing=True)
        env = self.env(with_claude=True)
        self.write_claude_stub_rc(1, "PLUGIN ERROR: name is required")  # `❯` を含まない書式
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 2, "rc を捨てて緑に倒している: " + res.stdout)
        self.assertIn("指摘行を抽出できなかった", res.stdout)

    def test_a_successful_cli_with_no_findings_stays_green(self):
        """rc=0 で指摘も無ければ従来どおり緑（判定不能に倒しすぎない）."""
        (self.root / "demo" / ".claude-plugin").mkdir(parents=True)
        (self.root / "demo" / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
        self.with_tests_dir(passing=True)
        env = self.env(with_claude=True)
        self.write_claude_stub_rc(0)
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_every_plugin_is_validated_not_just_the_first(self):
        """空行スキップを「非空スキップ」に取り違えると**全件が黙って飛ぶ**."""
        for name in ("alpha", "beta"):
            (self.root / name / ".claude-plugin").mkdir(parents=True)
            (self.root / name / ".claude-plugin" / "plugin.json").write_text(
                "{}", encoding="utf-8")
        self.with_tests_dir(passing=True)
        env = self.env(with_claude=True)
        self.write_claude_stub("  ❯ name: 必須フィールドが無い")
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("[schema:alpha]", res.stdout)
        self.assertIn("[schema:beta]", res.stdout)


if __name__ == "__main__":
    unittest.main()
