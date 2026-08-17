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

    def write_stub(self, name: str, body: str) -> Path:
        p = self.scripts / name
        p.write_text(body, encoding="utf-8")
        p.chmod(0o755)
        return p

    def with_tests_dir(self, passing: bool = True) -> None:
        """`unittest discover` の対象を置く（`python3 -m unittest` を実際に走らせる）."""
        d = self.scripts / "tests"
        d.mkdir(exist_ok=True)
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
        stub = self.bin / "claude"
        args = " ".join("'%s'" % f.replace("'", "'\\''") for f in findings) or "''"
        stub.write_text("#!/usr/bin/env bash\nprintf '%%s\\n' %s\nexit 0\n" % args,
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
