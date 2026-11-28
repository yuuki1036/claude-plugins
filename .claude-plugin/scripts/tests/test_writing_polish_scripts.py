"""writing-polish/scripts/textlint-unresolved.sh の CLI テスト.

本物の textlint をルール欠落の状態に持ち込むのは環境依存なので、stub の textlint を
PATH 先頭に置いて出力の形（JSON か / v15 の `== No rules found ==` か）だけを再現する。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "writing-polish" / "scripts" / "textlint-unresolved.sh"
CONFIG = REPO / "writing-polish" / "skills" / "writing-polish" / "references" / "textlintrc.json"

OK_JSON = 'echo \'[{"messages":[],"filePath":"probe.md"}]\''
NO_RULES = "echo \"== No rules found, textlint hasn't done anything ==\""


class TextlintUnresolvedTest(unittest.TestCase):
    def _tmpdir(self) -> Path:
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def _stub(self, body: str) -> Path:
        d = self._tmpdir()
        (d / "textlint").write_text("#!/bin/bash\n" + body + "\n")
        (d / "textlint").chmod(0o755)
        return d

    def _stub_missing(self, *missing: str) -> Path:
        """`--config` では全 drop、`--rule <key>` では missing のキーだけ非 JSON を返す stub."""
        cases = "".join(
            f'  *"--rule {k} "*) {NO_RULES}; exit 0;;\n' for k in missing
        )
        return self._stub(
            'case "$*" in\n'
            + cases
            + f"  *--config*) {NO_RULES}; exit 0;;\n"
            + f"  *) {OK_JSON};;\n"
            + "esac"
        )

    def _only(self, *names: str) -> Path:
        """指定したコマンドだけを引ける bin dir（引ける側を列挙する）."""
        d = self._tmpdir()
        for name in names:
            real = shutil.which(name)
            self.assertIsNotNone(real, f"{name} が見つからない（テストの前提）")
            (d / name).symlink_to(real)
        return d

    def _run(self, path: str, *args: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"}
        env["PATH"] = path
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            capture_output=True, text=True, env=env, timeout=60,
        )

    def _with_stub(self, stub: Path, *args: str) -> subprocess.CompletedProcess:
        return self._run(str(stub) + os.pathsep + os.environ["PATH"], *args)

    @staticmethod
    def _kv(stdout: str) -> dict[str, str]:
        return dict(line.split("=", 1) for line in stdout.splitlines() if "=" in line)

    def test_ok_when_config_returns_json(self):
        res = self._with_stub(self._stub(OK_JSON))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self._kv(res.stdout), {"status": "ok"})

    def test_names_missing_packages_in_config_order(self):
        """非 JSON のルールだけを、config の並びで空白区切りに出す（scoped は scoped のパッケージ名）."""
        rules = list(json.loads(CONFIG.read_text())["rules"].keys())
        scoped = next(k for k in rules if k.startswith("@"))
        plain = next(k for k in rules if not k.startswith("@"))
        res = self._with_stub(self._stub_missing(scoped, plain))
        self.assertEqual(res.returncode, 1, res.stderr)
        kv = self._kv(res.stdout)
        self.assertEqual(kv["status"], "unresolved")
        scope, name = scoped.split("/", 1)
        expected = {scoped: f"{scope}/textlint-rule-{name}", plain: f"textlint-rule-{plain}"}
        ordered = [expected[k] for k in rules if k in expected]
        self.assertEqual(kv["missing"], " ".join(ordered))

    def test_config_error_when_every_rule_resolves_alone(self):
        stub = self._stub(
            'case "$*" in\n'
            f"  *--config*) {NO_RULES}; exit 0;;\n"
            f"  *) {OK_JSON};;\n"
            "esac"
        )
        res = self._with_stub(stub)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertEqual(self._kv(res.stdout), {"status": "config-error"})

    def test_lint_findings_exit_code_does_not_count_as_failure(self):
        """指摘ありの textlint は exit 1 で JSON を返す。exit code ではなく stdout の形で見る."""
        res = self._with_stub(self._stub(OK_JSON + "; exit 1"))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self._kv(res.stdout)["status"], "ok")

    def test_explicit_config_path_is_used(self):
        cfg = self._tmpdir() / "rc.json"
        cfg.write_text(json.dumps({"rules": {"only-rule": True}}))
        res = self._with_stub(self._stub_missing("only-rule"), str(cfg))
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertEqual(self._kv(res.stdout)["missing"], "textlint-rule-only-rule")

    def test_not_runnable_textlint_is_not_reported_as_missing_rules(self):
        """本体が起動しない（stdout 空・exit 非 0）と、全ルールを未解決と誤って出さない."""
        stub = self._stub('echo "mise ERROR No version is set for shim: textlint" >&2; exit 1')
        res = self._with_stub(stub)
        self.assertEqual(res.returncode, 2, res.stderr)
        kv = self._kv(res.stdout)
        self.assertEqual(kv["status"], "unavailable")
        self.assertEqual(kv["reason"], "textlint-not-runnable")
        self.assertEqual(kv["detail"], "mise ERROR No version is set for shim: textlint")
        self.assertNotIn("missing", kv)

    def test_not_runnable_python3_is_not_reported_as_config_error(self):
        """python3 の shim が版を決められないと、JSON の判定が全部偽になり config-error に化ける."""
        d = self._tmpdir()
        (d / "python3").write_text('#!/bin/bash\necho "mise ERROR No version is set for shim: python3" >&2\nexit 1\n')
        (d / "python3").chmod(0o755)
        res = self._run(str(d) + os.pathsep + str(self._stub(OK_JSON)) + os.pathsep + os.environ["PATH"])
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertEqual(self._kv(res.stdout), {"status": "unavailable", "reason": "python3-not-runnable"})

    def test_not_runnable_detail_falls_back_to_stdout(self):
        """エラーを stdout にだけ出して落ちる textlint でも、理由を空にしない."""
        res = self._with_stub(self._stub('echo "Error: boom"; exit 1'))
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertEqual(self._kv(res.stdout)["detail"], "Error: boom")

    def test_unavailable_without_python3(self):
        res = self._run(str(self._only("bash", "dirname")) + os.pathsep + str(self._stub(OK_JSON)))
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertEqual(self._kv(res.stdout)["reason"], "python3-not-found")

    def test_unavailable_without_textlint(self):
        res = self._run(str(self._only("bash", "python3", "dirname")))
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertEqual(self._kv(res.stdout), {"status": "unavailable", "reason": "textlint-not-found"})

    def test_unavailable_without_config(self):
        res = self._with_stub(self._stub(OK_JSON), str(self._tmpdir() / "absent.json"))
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertEqual(self._kv(res.stdout)["reason"], "config-not-found")


if __name__ == "__main__":
    unittest.main()
