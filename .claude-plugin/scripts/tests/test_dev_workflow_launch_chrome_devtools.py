#!/usr/bin/env python3
"""dev-workflow の chrome-devtools MCP 起動ラッパ（launch-chrome-devtools.sh）の CLI 境界テスト.

ラッパの存在意義は「GUI app の痩せた PATH でも npx を引けること」なので、
**PATH を絞った状態**で mise 経路に落ちることを測る（環境の不在に頼らず stub を置く）:

- `--check` は npx を解決できたら 0 / できなければ 1。MCP は起動しない。
- PATH に npx が無く mise stub が `which npx` を返せば --check は 0。
- mise も npx も引けなければ --check は 1（silent に素通りさせない）。
- browser_connect=autoConnect で、旧版 npx stub を掴んだら autoConnect を付けず
  既定プロファイルに落とす（@latest がキャッシュ旧版に解決する事故の歯止め）。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LAUNCHER = REPO / "dev-workflow" / "scripts" / "launch-chrome-devtools.sh"


class LaunchWrapperTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self.bin = self.root / "bin"
        self.bin.mkdir()

    def _stub(self, name: str, body: str) -> None:
        p = self.bin / name
        p.write_text("#!/usr/bin/env bash\n" + textwrap.dedent(body))
        p.chmod(0o755)

    def _env(self, **extra: str) -> dict[str, str]:
        # bash / coreutils は引けないと困るので元 PATH の代表だけ足す。
        # npx は「置いていない」ので PATH から引けない状態を作る。
        env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.root),  # ~/.nvm ~/.volta ~/.local/bin を空にする
        }
        env.update(extra)
        return env

    def _run(self, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(LAUNCHER), *args],
            capture_output=True, text=True, env=env, timeout=30,
        )

    def test_check_succeeds_via_mise_when_npx_not_on_path(self) -> None:
        # npx は PATH に無いが mise which npx が在り処を返す
        fake_npx = self.bin / "real-npx"
        fake_npx.write_text("#!/usr/bin/env bash\n")
        fake_npx.chmod(0o755)
        self._stub("mise", f'[ "$1" = which ] && echo "{fake_npx}" && exit 0\nexit 1\n')
        res = self._run("--check", env=self._env())
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_check_fails_when_npx_unresolvable(self) -> None:
        # mise も無く npx も無い → --check は 1（素通りさせない）
        res = self._run("--check", env=self._env())
        self.assertEqual(res.returncode, 1)

    def test_default_connect_reaches_exec_without_crash(self) -> None:
        # 既定 browser_connect=default（EXTRA_ARGS 空）で exec に到達すること。
        # bash 3.2 + set -u では空配列の "${arr[@]}" が unbound で落ちるので、
        # exec が成功して npx stub の ARGS 行が stdout に出るまでを確認する（vacuous pass を防ぐ）。
        self._stub("npx", 'echo "ARGS: $*"\nexit 0\n')
        res = self._run(env=self._env(DEV_WORKFLOW_BROWSER_CONNECT=""))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("ARGS:", res.stdout)
        self.assertNotIn("unbound", res.stderr)

    def test_autoconnect_dropped_on_old_npx_version(self) -> None:
        # npx が chrome-devtools-mcp 1.2.0 を返す（autoConnect 非対応）。
        # launcher は --autoConnect を付けず、警告を stderr に出す。
        self._stub("npx", r'''
            for a in "$@"; do
              if [ "$a" = "--version" ]; then echo "1.2.0"; exit 0; fi
            done
            echo "ARGS: $*"
            exit 0
        ''')
        env = self._env(DEV_WORKFLOW_BROWSER_CONNECT="autoConnect")
        res = self._run(env=env)
        self.assertEqual(res.returncode, 0, res.stderr)  # exec 到達（crash しない）
        self.assertIn("ARGS:", res.stdout)               # exec 成功を確認（vacuous pass 防止）
        self.assertIn("autoConnect", res.stderr)         # 落とした旨の警告
        self.assertNotIn("--autoConnect", res.stdout)    # 実起動引数に付いていない

    def test_autoconnect_kept_on_new_npx_version(self) -> None:
        self._stub("npx", r'''
            for a in "$@"; do
              if [ "$a" = "--version" ]; then echo "1.7.0"; exit 0; fi
            done
            echo "ARGS: $*"
            exit 0
        ''')
        env = self._env(DEV_WORKFLOW_BROWSER_CONNECT="autoConnect")
        res = self._run(env=env)
        self.assertIn("--autoConnect", res.stdout)


if __name__ == "__main__":
    unittest.main()
