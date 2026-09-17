#!/usr/bin/env python3
"""dev-workflow の `detect-checkout.sh`（ui-verify Step 0）の CLI 境界テスト.

**何を守るか**: worktree で ui-verify を起動したとき、main の clone が立てた dev server を
「起動中 → そのまま使う」と誤認して**別のコードに pass を書く**事故を止める。
port の占有だけでは区別できないので、LISTEN している process の cwd と checkout の
toplevel を突き合わせた `SERVER_MATCH` が判定の要。**`foreign` を `ours` に倒さない**側を厚く書く。

server は本物の socket を bind して立てる（lsof の出力を模造しない）。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from git_env import scrub

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "dev-workflow" / "scripts" / "detect-checkout.sh"

LISTENER = textwrap.dedent("""\
    import socket, sys, time
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", int(sys.argv[1]))); s.listen(1)
    print("ready", flush=True)
    time.sleep(120)
    """)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class DetectCheckoutBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.main = self.root / "main"
        self.main.mkdir()
        self._git("init", "-q")
        self._git("config", "user.email", "t@example.com")
        self._git("config", "user.name", "t")
        self._git("commit", "-q", "--allow-empty", "-m", "init")
        self._servers: list[subprocess.Popen] = []
        self.addCleanup(self._stop_servers)

    def _env(self) -> dict[str, str]:
        return scrub()

    def _git(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=str(cwd or self.main), capture_output=True,
                              text=True, env=self._env())

    def add_worktree(self, name: str = "wt") -> Path:
        path = self.root / name
        r = self._git("worktree", "add", "-q", str(path), "-b", name)
        self.assertEqual(r.returncode, 0, r.stderr)
        return path

    def listen(self, cwd: Path, port: int) -> None:
        """cwd を指定して本物の LISTEN socket を立てる（dev server の代役）."""
        p = subprocess.Popen([sys.executable, "-c", LISTENER, str(port)], cwd=str(cwd),
                             stdout=subprocess.PIPE, text=True)
        self._servers.append(p)
        self.assertEqual(p.stdout.readline().strip(), "ready")
        # lsof が拾えるまで僅かな遅延があることがある
        for _ in range(20):
            if subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                              capture_output=True, text=True).stdout.strip():
                return
            time.sleep(0.1)
        self.fail("LISTEN socket が lsof に見えない")

    def _stop_servers(self) -> None:
        for p in self._servers:
            p.kill()
            p.wait()
            p.stdout.close()

    def run_script(self, cwd: Path, *args: str, expect_ok: bool = True) -> dict[str, str]:
        r = subprocess.run(["bash", str(SCRIPT), *args], cwd=str(cwd), capture_output=True,
                           text=True, env=self._env())
        if expect_ok:
            self.assertEqual(r.returncode, 0, r.stderr)
        self.last = r
        return dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)


class CheckoutKindTest(DetectCheckoutBase):
    def test_main_clone_is_main(self):
        out = self.run_script(self.main)
        self.assertEqual(out["CHECKOUT"], "main")
        self.assertEqual(out["WORKTREE_STATE"], "main")
        self.assertEqual(Path(out["TOPLEVEL"]).resolve(), self.main)

    def test_worktree_without_marker_is_unconfigured(self):
        wt = self.add_worktree()
        out = self.run_script(wt)
        self.assertEqual(out["CHECKOUT"], "worktree")
        self.assertEqual(out["WORKTREE_STATE"], "worktree-unconfigured")
        self.assertEqual(out["BRANCH"], "wt")

    def test_worktree_with_marker_is_ready(self):
        wt = self.add_worktree()
        (wt / "envs").mkdir()
        (wt / "envs" / ".frontend.env.worktree").write_text("FRONTEND_PORT=3010\n")
        out = self.run_script(wt)
        self.assertEqual(out["WORKTREE_STATE"], "worktree-ready")

    def test_subdirectory_of_worktree_is_still_that_worktree(self):
        wt = self.add_worktree()
        sub = wt / "apps" / "web"
        sub.mkdir(parents=True)
        out = self.run_script(sub)
        self.assertEqual(out["CHECKOUT"], "worktree")
        self.assertEqual(Path(out["TOPLEVEL"]).resolve(), wt.resolve())

    def test_outside_git_is_exit_2(self):
        outside = self.root / "nogit"
        outside.mkdir()
        self.run_script(outside, expect_ok=False)
        self.assertEqual(self.last.returncode, 2)
        self.assertIn("FATAL", self.last.stderr)


class PortResolutionTest(DetectCheckoutBase):
    def test_arg_wins(self):
        (self.main / "package.json").write_text('{"scripts":{"dev":"next dev -p 4000"}}')
        out = self.run_script(self.main, "--port", "5555")
        self.assertEqual((out["DEV_PORT"], out["PORT_SOURCE"]), ("5555", "arg"))

    def test_worktree_env_beats_package_json(self):
        """worktree-setup が割り当てた port を main 共有の package.json より優先する."""
        wt = self.add_worktree()
        (wt / "package.json").write_text('{"scripts":{"dev":"next dev -p 4000"}}')
        (wt / "envs").mkdir()
        (wt / "envs" / ".frontend.env.worktree").write_text("WORKTREE_NAME=wt\nFRONTEND_PORT=4010\n")
        out = self.run_script(wt)
        self.assertEqual((out["DEV_PORT"], out["PORT_SOURCE"]), ("4010", "worktree-env"))

    def test_marker_in_main_is_ignored(self):
        """main では envs/ のマーカーを見ない（main は worktree-setup の対象外）."""
        (self.main / "envs").mkdir()
        (self.main / "envs" / ".frontend.env.worktree").write_text("FRONTEND_PORT=4010\n")
        out = self.run_script(self.main)
        self.assertEqual(out["WORKTREE_STATE"], "main")
        self.assertEqual(out["PORT_SOURCE"], "default")

    def test_package_json_port_forms(self):
        for script, port in (("next dev -p 4000", "4000"), ("vite --port 5173", "5173"),
                             ("vite --port=5174", "5174"), ("PORT=8081 node server.js", "8081")):
            with self.subTest(script=script):
                (self.main / "package.json").write_text('{"scripts":{"dev":"%s"}}' % script)
                out = self.run_script(self.main)
                self.assertEqual((out["DEV_PORT"], out["PORT_SOURCE"]), (port, "package.json"))

    def test_default_is_3000(self):
        out = self.run_script(self.main)
        self.assertEqual((out["DEV_PORT"], out["PORT_SOURCE"]), ("3000", "default"))

    def test_non_numeric_port_is_exit_2(self):
        self.run_script(self.main, "--port", "abc", expect_ok=False)
        self.assertEqual(self.last.returncode, 2)


class ServerMatchTest(DetectCheckoutBase):
    def test_no_listener_is_none(self):
        out = self.run_script(self.main, "--port", str(free_port()))
        self.assertEqual(out["SERVER_MATCH"], "none")
        self.assertEqual(out["SERVER_PID"], "")

    def test_listener_in_this_checkout_is_ours(self):
        port = free_port()
        self.listen(self.main, port)
        out = self.run_script(self.main, "--port", str(port))
        self.assertEqual(out["SERVER_MATCH"], "ours")
        self.assertEqual(out["SERVER_PID"], str(self._servers[0].pid))

    def test_listener_in_subdirectory_is_ours(self):
        """monorepo で apps/web から起動した server も自分のもの."""
        sub = self.main / "apps" / "web"
        sub.mkdir(parents=True)
        port = free_port()
        self.listen(sub, port)
        out = self.run_script(self.main, "--port", str(port))
        self.assertEqual(out["SERVER_MATCH"], "ours")

    def test_main_server_seen_from_worktree_is_foreign(self):
        """核心: main が立てた server を worktree から流用しない."""
        wt = self.add_worktree()
        port = free_port()
        self.listen(self.main, port)
        out = self.run_script(wt, "--port", str(port))
        self.assertEqual(out["CHECKOUT"], "worktree")
        self.assertEqual(out["SERVER_MATCH"], "foreign")
        self.assertEqual(Path(out["SERVER_CWD"]).resolve(), self.main)

    def test_worktree_server_seen_from_main_is_foreign(self):
        wt = self.add_worktree()
        port = free_port()
        self.listen(wt, port)
        out = self.run_script(self.main, "--port", str(port))
        self.assertEqual(out["SERVER_MATCH"], "foreign")

    def test_sibling_prefix_is_not_ours(self):
        """`main` と `main-2` のように前方一致するだけの別ディレクトリを ours にしない."""
        sibling = self.root / "main-2"
        sibling.mkdir()
        port = free_port()
        self.listen(sibling, port)
        out = self.run_script(self.main, "--port", str(port))
        self.assertEqual(out["SERVER_MATCH"], "foreign")

    def test_script_never_kills_the_foreign_server(self):
        wt = self.add_worktree()
        port = free_port()
        self.listen(self.main, port)
        self.run_script(wt, "--port", str(port))
        self.assertIsNone(self._servers[0].poll(), "判定スクリプトが他 checkout の server を殺した")


if __name__ == "__main__":
    unittest.main()
