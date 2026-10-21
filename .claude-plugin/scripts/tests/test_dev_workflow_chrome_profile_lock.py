#!/usr/bin/env python3
"""dev-workflow の `chrome-profile-lock.sh`（ui-verify の既存ブラウザの検知と停止）の CLI テスト.

**何を守るか**: ui-verify はこの出力で「既存のブラウザを止める確認を出すか」を決め、利用者が
「止めて続行」を選んだときだけ stop を呼ぶ（GitHub issue #306）。**誤って止める側**
（別プロファイル・pid の再利用・このセッション自身のブラウザ・判定できないセッション）を厚く書く。
stop は確認の後に lock を確かめ直すので、表示した holder と止める相手がずれないことも見る。

実プロセスを使う（ps の出力を模造しない）: 偽のブラウザは `--user-data-dir=<dir>` を引数に持って
sleep する python、偽の MCP は chrome-devtools-mcp の起動形（node が process.title を書き換えた形 /
build/ を指す node の形 / `npm exec chrome-devtools-mcp@…`）を真似た bash。SingletonLock は Chrome と
同じ `<hostname>-<pid>` を指す symlink。

**`CLAUDE_PID` を継承させない**: 実行中の Claude Code セッションの pid が入っていると、テストの
プロセスがその子孫なので self / other の判定が開発機と CI で割れる。ケースごとに明示する。
**orphan を期待するケース（と MCP の祖先が無い self）は holder を再親付けしたプロセスにする**（`orphan_browser()` /
`chain(..., detach=True)`）: テストの
直接の子にすると、祖先の walk がテストランナーの祖先（シェル・claude・端末）まで届き、そのどれかの
コマンド行に MCP の印があると other に化ける（実測）。
起動したプロセスはすべて回収する（run-tests.py の残留検出に掛からないように）。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "dev-workflow" / "scripts" / "chrome-profile-lock.sh"

SLEEP = "import time; time.sleep(120)"
# SIGTERM を無視する holder。handler を入れる前に SIGTERM が届くと素直に死ぬので、入れてから
# 環境変数 READY のファイルを作る（stdout は再親付けの経路で /dev/null に向く）
IGNORE_TERM = ("import os, signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
               "open(os.environ['READY'], 'w').close(); time.sleep(120)")
# 偽の MCP の本体: 子に偽のブラウザを起こして pid を出し、stdin が閉じるまで builtin の read で待つ
# （sleep を子に持たせると、MCP を殺したあとに孤児が残る）
MCP_BODY = '"$1" -c "$2" "--user-data-dir=$3" </dev/null >/dev/null 2>&1 & echo $!; read -r _'
MCP_BUILD_PATH = "/opt/x/node_modules/chrome-devtools-mcp/build/src/index.js"
# 祖先の層を任意の名前で重ねる: LAYERS（| 区切り）の先頭の名前を argv[0] にして次の層を起こし、尽きたら
# 偽のブラウザを起こす。各層は「自分の pid と子の pid」を PIDS に追記し、子が終わるまで wait する。
# 名前は環境変数で渡す（引数にすると外側の層のコマンド行に内側の名前が出て、is_mcp の照合に混ざる）
LAYER_SH = r'''
py="$1"; code="$2"; dir="$3"
if [ -z "${LAYERS:-}" ]; then
  "$py" -c "$code" "--user-data-dir=$dir" </dev/null >/dev/null 2>&1 &
else
  name="${LAYERS%%|*}"
  case "$LAYERS" in *"|"*) rest="${LAYERS#*|}" ;; *) rest="" ;; esac
  ( export LAYERS="$rest"; exec -a "$name" bash "$0" "$py" "$code" "$dir" ) </dev/null >/dev/null 2>&1 &
fi
echo "$$ $!" >> "$PIDS"
wait
'''
NPM_EXEC = "npm exec chrome-devtools-mcp@latest"


def alive(pid: int) -> bool:
    """スクリプトとは独立に生存を見る（zombie は終わった扱い）."""
    out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True,
                         text=True).stdout.strip()
    return bool(out) and not out.startswith("Z")


def parse(stdout: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in stdout.splitlines() if "=" in line)


class ProfileLockBase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.dir = self.tmp / "profile"
        self.dir.mkdir()
        self.host = os.uname().nodename

    # --- プロセス ---
    def spawn(self, argv: list[str], **kw) -> subprocess.Popen:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, **kw)
        self.addCleanup(self._reap_child, proc)
        return proc

    def _reap_child(self, proc: subprocess.Popen) -> None:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)
        proc.stdin.close()
        proc.stdout.close()

    def kill_pid(self, pid: int) -> None:
        """子ではないプロセス（孫・孤児）の回収. wait できないので消えるまで待つ."""
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        deadline = time.time() + 10
        while alive(pid) and time.time() < deadline:
            time.sleep(0.05)

    def browser(self, profile: Path | str | None = None, code: str = SLEEP) -> subprocess.Popen:
        """このテストの直接の子としての偽ブラウザ（祖先に MCP はいない）."""
        return self.spawn([sys.executable, "-c", code, f"--user-data-dir={profile or self.dir}"])

    def unrelated_pid(self) -> int:
        """生きているが holder の祖先ではないプロセス（別セッションの claude の役）."""
        return self.spawn([sys.executable, "-c", SLEEP]).pid

    def mcp_browser(self, form: str = "build") -> tuple[int, int]:
        """偽の MCP の子として偽のブラウザを起こし、(mcp_pid, browser_pid) を返す."""
        if form == "title":
            # exec -a で argv[0] を書き換える = node の process.title と同じく ps の先頭語が MCP 名になる
            argv = ["bash", "-c", 'exec -a chrome-devtools-mcp bash -c "$0" mcp "$@"',
                    MCP_BODY, sys.executable, SLEEP, str(self.dir)]
        else:
            argv = ["bash", "-c", MCP_BODY, MCP_BUILD_PATH, sys.executable, SLEEP, str(self.dir)]
        mcp = self.spawn(argv)
        pid = int(mcp.stdout.readline().strip())
        self.addCleanup(self.kill_pid, pid)      # LIFO: MCP より先に回収される
        return mcp.pid, pid

    def chain(self, names: tuple[str, ...] = (), *, detach: bool = False,
              code: str = SLEEP) -> tuple[list[int], int]:
        """names の名前の層（外側から順）の下に偽のブラウザを起こし、(層の pid, ブラウザの pid) を返す.

        detach=True は最も外側（名前を持たない起動役）を再親付けする: 祖先の walk はそこで pid 1 に当たり、
        テストランナーの祖先に届かない.
        """
        self._chains = getattr(self, "_chains", 0) + 1
        layer_sh = self.tmp / "layer.sh"
        if not layer_sh.exists():
            layer_sh.write_text(LAYER_SH)
        pids = self.tmp / f"pids-{self._chains}"
        ready = self.tmp / f"ready-{self._chains}"
        env = {**os.environ, "LAYERS": "|".join(names), "PIDS": str(pids), "READY": str(ready)}
        argv = ["bash", str(layer_sh), sys.executable, code, str(self.dir)]
        if detach:
            subprocess.run(["bash", "-c", '"$@" </dev/null >/dev/null 2>&1 &', "detach", *argv],
                           env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10, check=True)
        else:
            self.spawn(argv, env=env)
        deadline = time.time() + 10
        while time.time() < deadline:
            lines = pids.read_text().splitlines() if pids.exists() else []
            if len(lines) == len(names) + 1:
                break
            time.sleep(0.02)
        else:
            self.fail(f"層が揃わない: {lines}")
        child_of = dict(tuple(map(int, line.split())) for line in lines)
        (top,) = set(child_of) - set(child_of.values())
        if detach:
            self.addCleanup(self.kill_pid, top)
        seq: list[int] = []
        while top in child_of:
            top = child_of[top]
            seq.append(top)
        for pid in seq:                          # LIFO: ブラウザ → 内側の層 → 外側の層の順に回収される
            self.addCleanup(self.kill_pid, pid)
        if code == IGNORE_TERM:
            deadline = time.time() + 10
            while not ready.exists():
                self.assertLess(time.time(), deadline, "holder が SIGTERM の handler を入れない")
                time.sleep(0.02)
        return seq[:-1], seq[-1]

    def orphan_browser(self, code: str = SLEEP) -> int:
        """起動役が終わって再親付けされた偽ブラウザ（MCP の終了後に残ったブラウザの役）."""
        return self.chain(detach=True, code=code)[1]

    def dead_pid(self) -> int:
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        return proc.pid

    # --- lock とスクリプト ---
    def lock(self, pid: int | None = None, target: str | None = None) -> None:
        (self.dir / "SingletonLock").symlink_to(target or f"{self.host}-{pid}")

    def run_script(self, *args: str, claude_pid: int | str | None = None,
                   env_extra: dict[str, str] | None = None,
                   cwd: Path | None = None,
                   script: Path | None = None) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
        env = {k: v for k, v in os.environ.items()
               if k not in ("CLAUDE_PID", "DEV_WORKFLOW_BROWSER_CONNECT", "BASH_ENV")}
        env.update(HOME=str(self.home), CHROME_PROFILE_LOCK_WAIT="1")
        if claude_pid is not None:
            env["CLAUDE_PID"] = str(claude_pid)
        env.update(env_extra or {})
        proc = subprocess.run(["bash", str(script or SCRIPT), *args], capture_output=True, text=True,
                              env=env, cwd=str(cwd or self.tmp), timeout=60)
        return proc, parse(proc.stdout)

    def status(self, **kw) -> dict[str, str]:
        proc, out = self.run_script("status", "--dir", str(self.dir), **kw)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return out

    def stop(self, pid: int | str, **kw) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
        # --pid を最後に置く（引数の値の有無の判定を --pid の側でも通す）
        return self.run_script("stop", "--dir", str(self.dir), "--pid", str(pid), **kw)

    def assertNoHolder(self, out: dict[str, str]) -> None:
        for key in ("HOLDER_PID", "HOLDER_STARTED", "HOLDER_MCP_PID", "HOLDER_MCP_STARTED",
                    "HOLDER_SESSION"):
            self.assertEqual(out[key], "", key)


class LockStateTest(ProfileLockBase):
    def test_no_lock_is_none(self):
        out = self.status()
        self.assertEqual(out["LOCK"], "none")
        self.assertEqual(out["REASON"], "")
        self.assertEqual(out["PROFILE_DIR"], str(self.dir))
        self.assertEqual(out["DIR_SOURCE"], "arg")
        self.assertNoHolder(out)

    def test_dead_pid_is_stale_and_a_live_holder_is_held(self):
        """lock の存在だけで「掴まれている」としない（Chrome が落ちると lock は残る）."""
        self.lock(self.dead_pid())
        out = self.status()
        self.assertEqual(out["LOCK"], "stale")
        self.assertNoHolder(out)
        (self.dir / "SingletonLock").unlink()
        holder = self.browser()
        self.lock(holder.pid)
        out = self.status()
        self.assertEqual(out["LOCK"], "held")
        self.assertEqual(out["HOLDER_PID"], str(holder.pid))
        self.assertNotEqual(out["HOLDER_STARTED"], "")

    def test_live_pid_without_profile_arg_is_stale(self):
        """pid が再利用されて、別のプロセスが同じ pid を持っている."""
        self.lock(self.unrelated_pid())
        out = self.status()
        self.assertEqual(out["LOCK"], "stale")
        self.assertNoHolder(out)

    def test_profile_dir_prefix_is_not_a_match(self):
        """<dir>-beta も <dir>/sub も別プロファイル（末尾 / の形を受けても、その下までは広げない）."""
        for profile in (f"{self.dir}-beta", f"{self.dir}/sub"):
            with self.subTest(profile=profile):
                holder = self.browser(profile=profile)
                self.lock(holder.pid)
                self.assertEqual(self.status()["LOCK"], "stale")
                (self.dir / "SingletonLock").unlink()

    def test_other_host_is_foreign_host(self):
        holder = self.browser()
        self.lock(target=f"another-host.local-{holder.pid}")
        out = self.status()
        self.assertEqual(out["LOCK"], "foreign-host")
        self.assertNoHolder(out)

    def test_unparseable_lock_is_unknown(self):
        for target in ("garbage", f"{self.host}-abc", "-123"):
            with self.subTest(target=target):
                self.lock(target=target)
                out = self.status()
                self.assertEqual(out["LOCK"], "unknown")
                self.assertIn("<host>-<pid>", out["REASON"])
                self.assertNoHolder(out)
                (self.dir / "SingletonLock").unlink()

    def test_regular_file_lock_is_unknown(self):
        (self.dir / "SingletonLock").write_text("x")
        out = self.status()
        self.assertEqual(out["LOCK"], "unknown")
        self.assertIn("symlink", out["REASON"])

    def test_extra_slash_on_the_dir_side_is_dropped(self):
        """--dir の側にだけ余分な / があっても held を取り逃さない（PROFILE_DIR は / を落として出す）."""
        holder = self.browser()
        self.lock(holder.pid)
        proc, out = self.run_script("status", "--dir", f"{self.dir}/")
        self.assertEqual(out["PROFILE_DIR"], str(self.dir))
        self.assertEqual(out["LOCK"], "held")

    def test_trailing_slash_on_the_process_side_is_matched(self):
        """絶対パスの userDataDir は puppeteer が無加工で Chrome に渡すので、設定値の末尾の / は
        コマンド行にも残る（chrome-devtools-mcp 1.11.0 の実物で確認）. dir の側の / の有無によらず held."""
        holder = self.browser(profile=f"{self.dir}/")
        self.lock(holder.pid)
        for dir_arg in (str(self.dir), f"{self.dir}/"):
            with self.subTest(dir_arg=dir_arg):
                _, out = self.run_script("status", "--dir", dir_arg)
                self.assertEqual(out["LOCK"], "held")
        _, out = self.run_script(
            "status", env_extra={"DEV_WORKFLOW_BROWSER_CONNECT": f"userDataDir={self.dir}/"})
        self.assertEqual((out["DIR_SOURCE"], out["LOCK"]), ("userDataDir", "held"))

    def test_relative_or_tilde_dir_is_unknown(self):
        """相対の userDataDir は MCP の cwd を起点に絶対化されて Chrome に渡る（`~` は展開されない）.

        MCP の cwd はここから分からないので、照合せずに unknown と理由を出す（掴まれているのに stale と
        書かない）。ここでは cwd 直下の profile を相対で指し、実物と同じく絶対パスで起動した holder を置く.
        """
        holder = self.browser()
        self.lock(holder.pid)
        for value in ("profile", "./profile", "profile/", "~/profile"):
            with self.subTest(value=value):
                _, out = self.run_script(
                    "status", env_extra={"DEV_WORKFLOW_BROWSER_CONNECT": f"userDataDir={value}"})
                self.assertEqual(out["LOCK"], "unknown")
                self.assertIn("絶対パス", out["REASON"])
                self.assertNoHolder(out)
                _, out = self.run_script("status", "--dir", value)   # エラー文は設定値のまま出る
                self.assertEqual(out["LOCK"], "unknown")
                proc, out = self.run_script("stop", "--dir", value, "--pid", str(holder.pid),
                                            claude_pid=self.unrelated_pid())
                self.assertEqual((proc.returncode, out["REFUSED"]), (3, "not-held"))
        self.assertTrue(alive(holder.pid))

    def test_missing_lib_exits_2_only_when_the_dir_is_resolved(self):
        """--dir を省いた回だけ lib/browser-connect.sh を読む. 読めない配布では既定の dir に黙って倒さない."""
        bare = self.tmp / "bare"
        bare.mkdir()
        shutil.copy(SCRIPT, bare / SCRIPT.name)
        proc, out = self.run_script("status", script=bare / SCRIPT.name)
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("lib", proc.stderr)
        self.assertNotIn("LOCK", out)
        proc, out = self.run_script("status", "--dir", str(self.dir), script=bare / SCRIPT.name)
        self.assertEqual((proc.returncode, out["LOCK"]), (0, "none"), proc.stderr)


class ProfileDirSourceTest(ProfileLockBase):
    """--dir を省いたときは、起動ラッパと同じ順（env → .claude/dev-workflow.json）で読めた接続方式の dir を見る
    （違う dir を見ると、使わないプロファイルの停止を聞く）。Bash tool からの呼び出しには env が無く、
    userConfig だけの設定は見えない（ADR-20261020221214 の決定 2）."""

    def config(self, value: str) -> Path:
        cwd = self.tmp / "project"
        (cwd / ".claude").mkdir(parents=True)
        (cwd / ".claude" / "dev-workflow.json").write_text(json.dumps({"browser_connect": value}))
        return cwd

    def require_jq(self) -> None:
        if shutil.which("jq") is None:
            self.skipTest("jq が無い（.claude/dev-workflow.json を読む経路の前提）")

    def test_default_dir_is_under_home(self):
        proc, out = self.run_script("status")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(out["PROFILE_DIR"],
                         str(self.home / ".cache" / "chrome-devtools-mcp" / "chrome-profile"))
        self.assertEqual(out["DIR_SOURCE"], "default")
        self.assertEqual(out["LOCK"], "none")

    def test_user_data_dir_from_env_is_followed(self):
        holder = self.browser()
        self.lock(holder.pid)
        _, out = self.run_script("status",
                                 env_extra={"DEV_WORKFLOW_BROWSER_CONNECT": f"userDataDir={self.dir}"})
        self.assertEqual(out["DIR_SOURCE"], "userDataDir")
        self.assertEqual(out["PROFILE_DIR"], str(self.dir))
        self.assertEqual(out["LOCK"], "held")

    def test_empty_user_data_dir_is_default(self):
        """`userDataDir=`（path が空）は既定の dir. 起動ラッパも空の --userDataDir を渡さない
        （解釈は lib/browser-connect.sh を共有。test_dev_workflow_launch_chrome_devtools.py が対）."""
        _, out = self.run_script("status", env_extra={"DEV_WORKFLOW_BROWSER_CONNECT": "userDataDir="})
        self.assertEqual(out["DIR_SOURCE"], "default")
        self.assertEqual(out["PROFILE_DIR"],
                         str(self.home / ".cache" / "chrome-devtools-mcp" / "chrome-profile"))

    def test_auto_connect_from_config_checks_no_profile(self):
        """autoConnect は実 Chrome につなぐだけで、既定のプロファイルを起動しない."""
        self.require_jq()
        default = self.home / ".cache" / "chrome-devtools-mcp" / "chrome-profile"
        default.mkdir(parents=True)
        holder = self.browser(profile=default)
        (default / "SingletonLock").symlink_to(f"{self.host}-{holder.pid}")
        _, out = self.run_script("status", cwd=self.config("autoConnect"))
        self.assertEqual(out["DIR_SOURCE"], "autoConnect")
        self.assertEqual(out["PROFILE_DIR"], "")
        self.assertEqual(out["LOCK"], "none")
        _, out = self.run_script("status")      # 設定が無ければ同じ holder を held と見る（対照）
        self.assertEqual(out["LOCK"], "held")

    def test_env_wins_over_config(self):
        self.require_jq()
        _, out = self.run_script(
            "status", cwd=self.config("autoConnect"),
            env_extra={"DEV_WORKFLOW_BROWSER_CONNECT": f"userDataDir={self.dir}"})
        self.assertEqual(out["DIR_SOURCE"], "userDataDir")
        self.assertEqual(out["PROFILE_DIR"], str(self.dir))

    def test_unexpanded_user_config_literal_is_ignored(self):
        self.require_jq()
        _, out = self.run_script(
            "status", cwd=self.config(f"userDataDir={self.dir}"),
            env_extra={"DEV_WORKFLOW_BROWSER_CONNECT": "${user_config.browser_connect}"})
        self.assertEqual(out["DIR_SOURCE"], "userDataDir")
        self.assertEqual(out["PROFILE_DIR"], str(self.dir))


class HolderSessionTest(ProfileLockBase):
    def test_held_reports_holder_and_mcp(self):
        mcp, holder = self.mcp_browser("build")
        self.lock(holder)
        out = self.status(claude_pid=self.unrelated_pid())
        self.assertEqual(out["LOCK"], "held")
        self.assertEqual(out["HOLDER_PID"], str(holder))
        self.assertEqual(out["HOLDER_MCP_PID"], str(mcp))
        self.assertNotEqual(out["HOLDER_STARTED"], "")
        self.assertNotEqual(out["HOLDER_MCP_STARTED"], "")

    def test_mcp_title_form_is_recognised(self):
        mcp, holder = self.mcp_browser("title")
        self.lock(holder)
        out = self.status(claude_pid=self.unrelated_pid())
        self.assertEqual(out["HOLDER_MCP_PID"], str(mcp))
        self.assertEqual(out["HOLDER_SESSION"], "other")

    def test_session_self_when_claude_pid_is_an_ancestor(self):
        _, holder = self.mcp_browser()
        self.lock(holder)
        self.assertEqual(self.status(claude_pid=os.getpid())["HOLDER_SESSION"], "self")

    def test_session_self_without_mcp_ancestor(self):
        """CLAUDE_PID が祖先にいれば、MCP の祖先が無くても self（orphan と書かない）. judge_session は self を
        orphan より先に見る（逆にすると、このセッションが MCP を通さずに起動したブラウザに停止の確認が出る）.

        claude の役の層の下に置いて再親付けする: テストの直接の子にすると祖先の walk がテストランナーの祖先に
        届き、そこに MCP の印がある機では順を入れ替えても self のまま緑になる. CLAUDE_PID が無関係なら orphan（対照）.
        """
        (claude,), holder = self.chain(("claude",), detach=True)
        self.lock(holder)
        out = self.status(claude_pid=claude)
        self.assertEqual((out["HOLDER_SESSION"], out["HOLDER_MCP_PID"]), ("self", ""))
        self.assertEqual(self.status(claude_pid=self.unrelated_pid())["HOLDER_SESSION"], "orphan")

    def test_session_other_when_claude_pid_is_unrelated(self):
        _, holder = self.mcp_browser()
        self.lock(holder)
        self.assertEqual(self.status(claude_pid=self.unrelated_pid())["HOLDER_SESSION"], "other")

    def test_session_unknown_without_a_valid_claude_pid(self):
        """CLAUDE_PID が使えないと self と other を見分けられない（other と書かない）."""
        _, holder = self.mcp_browser()
        self.lock(holder)
        for claude_pid in (None, "", "abc", self.dead_pid()):
            with self.subTest(claude_pid=claude_pid):
                self.assertEqual(self.status(claude_pid=claude_pid)["HOLDER_SESSION"], "unknown")

    def test_claude_pid_1_is_not_self(self):
        """pid 1 は全プロセスの祖先なので、このセッションの印にならない."""
        _, holder = self.mcp_browser()
        self.lock(holder)
        for claude_pid in (1, 0):
            with self.subTest(claude_pid=claude_pid):
                self.assertEqual(self.status(claude_pid=claude_pid)["HOLDER_SESSION"], "unknown")

    def test_orphan_without_mcp_ancestor(self):
        self.lock(self.orphan_browser())
        out = self.status(claude_pid=self.unrelated_pid())
        self.assertEqual(out["LOCK"], "held")
        self.assertEqual(out["HOLDER_SESSION"], "orphan")
        self.assertEqual(out["HOLDER_MCP_PID"], "")
        self.assertEqual(out["HOLDER_MCP_STARTED"], "")

    def test_parent_that_is_not_mcp_is_not_taken_as_mcp(self):
        """直近の親が MCP でなければ、祖先をたどっても MCP の印が無い限り orphan."""
        _, holder = self.chain(("node",), detach=True)
        self.lock(holder)
        out = self.status(claude_pid=self.unrelated_pid())
        self.assertEqual(out["HOLDER_SESSION"], "orphan")
        self.assertEqual(out["HOLDER_MCP_PID"], "")

    def test_npm_exec_form_is_recognised(self):
        """`npm exec chrome-devtools-mcp@…`（実物の起動ラッパの親）の形を、子が MCP に見えなくても拾う."""
        (npm, _node), holder = self.chain((NPM_EXEC, "node"), detach=True)
        self.lock(holder)
        out = self.status(claude_pid=self.unrelated_pid())
        self.assertEqual(out["HOLDER_MCP_PID"], str(npm))
        self.assertEqual(out["HOLDER_SESSION"], "other")

    def test_title_with_a_path_is_recognised(self):
        """先頭語がパスつきでも、basename が chrome-devtools-mcp なら MCP."""
        (mcp,), holder = self.chain(("/usr/local/lib/node_modules/.bin/chrome-devtools-mcp",),
                                    detach=True)
        self.lock(holder)
        out = self.status(claude_pid=self.unrelated_pid())
        self.assertEqual(out["HOLDER_MCP_PID"], str(mcp))
        self.assertEqual(out["HOLDER_SESSION"], "other")

    def test_nearest_mcp_is_reported(self):
        """実物の連鎖（title 形 → `npm exec …@latest` → claude）では、ブラウザに最も近い MCP を出す."""
        (_npm, mcp), holder = self.chain((NPM_EXEC, "chrome-devtools-mcp"), detach=True)
        self.lock(holder)
        out = self.status(claude_pid=self.unrelated_pid())
        self.assertEqual(out["HOLDER_MCP_PID"], str(mcp))


class StopTest(ProfileLockBase):
    def test_stop_refuses_pid_mismatch(self):
        holder = self.browser()
        self.lock(holder.pid)
        proc, out = self.stop(self.unrelated_pid(), claude_pid=self.unrelated_pid())
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertEqual(out["REFUSED"], "pid-mismatch")
        self.assertEqual(out["STOPPED"], "no")
        self.assertTrue(alive(holder.pid))

    def test_stop_refuses_self(self):
        _, holder = self.mcp_browser()
        self.lock(holder)
        proc, out = self.stop(holder, claude_pid=os.getpid())
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertEqual(out["REFUSED"], "self")
        self.assertEqual(out["STOPPED"], "no")
        self.assertTrue(alive(holder))

    def test_stop_refuses_self_without_mcp_ancestor(self):
        """MCP の祖先が無くても、CLAUDE_PID が祖先にいる holder は止めない（orphan として止める側に倒さない）."""
        (claude,), holder = self.chain(("claude",), detach=True)
        self.lock(holder)
        proc, out = self.stop(holder, claude_pid=claude)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertEqual((out["REFUSED"], out["STOPPED"]), ("self", "no"))
        self.assertTrue(alive(holder))

    def test_stop_refuses_unknown_session(self):
        _, holder = self.mcp_browser()
        self.lock(holder)
        proc, out = self.stop(holder)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertEqual(out["REFUSED"], "session-unknown")
        self.assertTrue(alive(holder))

    def test_stop_refuses_when_not_held(self):
        proc, out = self.stop(self.unrelated_pid())
        self.assertEqual((proc.returncode, out["LOCK"], out["REFUSED"]), (3, "none", "not-held"))
        dead = self.dead_pid()
        self.lock(dead)
        proc, out = self.stop(dead)
        self.assertEqual((proc.returncode, out["LOCK"], out["REFUSED"]), (3, "stale", "not-held"))
        (self.dir / "SingletonLock").unlink()
        holder = self.browser()
        self.lock(target=f"another-host.local-{holder.pid}")
        proc, out = self.stop(holder.pid, claude_pid=self.unrelated_pid())
        self.assertEqual((proc.returncode, out["REFUSED"]), (3, "not-held"))
        self.assertTrue(alive(holder.pid))

    def test_stop_requires_numeric_pid(self):
        holder = self.browser()
        self.lock(holder.pid)
        for args in (("stop", "--dir", str(self.dir)), ("stop", "--dir", str(self.dir), "--pid", "abc"),
                     ("stop", "--dir", str(self.dir), "--pid")):
            with self.subTest(args=args):
                proc, out = self.run_script(*args, claude_pid=self.unrelated_pid())
                self.assertEqual(proc.returncode, 2, proc.stdout)
                self.assertNotIn("STOPPED", out)
        self.assertTrue(alive(holder.pid))

    def test_unknown_subcommand_and_argument_exit_2(self):
        for args in ((), ("kill",), ("status", "--force"), ("status", "--dir")):
            with self.subTest(args=args):
                proc, out = self.run_script(*args)
                self.assertEqual(proc.returncode, 2, proc.stdout)
                self.assertNotIn("LOCK", out)

    def test_stop_terminates_holder_of_other_session(self):
        mcp, holder = self.mcp_browser()
        self.lock(holder)
        proc, out = self.stop(holder, claude_pid=self.unrelated_pid())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(out["STOPPED"], "yes")
        self.assertNotIn("REFUSED", out)
        self.assertFalse(alive(holder))
        self.assertTrue(alive(mcp), "MCP 本体には触れない")

    def test_stop_terminates_an_orphan(self):
        holder = self.orphan_browser()
        self.lock(holder)
        proc, out = self.stop(holder)
        self.assertEqual((proc.returncode, out["STOPPED"]), (0, "yes"), proc.stderr)
        self.assertFalse(alive(holder))

    def test_stop_does_not_touch_other_processes_with_the_same_profile(self):
        """lock の holder 以外（renderer の役）には送らない."""
        holder = self.orphan_browser()
        renderer = self.browser()
        self.lock(holder)
        proc, out = self.stop(holder)
        self.assertEqual((proc.returncode, out["STOPPED"]), (0, "yes"), proc.stderr)
        self.assertFalse(alive(holder))
        self.assertTrue(alive(renderer.pid))

    def test_stop_reports_not_stopped_when_sigterm_is_ignored(self):
        """SIGKILL に格上げしない（プロファイルの書き出しと lock の解放を飛ばす）."""
        holder = self.orphan_browser(code=IGNORE_TERM)
        self.lock(holder)
        proc, out = self.stop(holder)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(out["STOPPED"], "no")
        self.assertNotIn("REFUSED", out)
        self.assertTrue(alive(holder))

    def bash_env(self, body: str) -> dict[str, str]:
        """スクリプトの bash に先に読ませる定義（builtin の kill を関数で差し替える）."""
        path = self.tmp / "bash_env.sh"
        path.write_text(body)
        return {"BASH_ENV": str(path)}

    def test_stop_refuses_without_waiting_when_sigterm_cannot_be_sent(self):
        """送れない（EPERM など）のに待ち切って「SIGTERM で終わらない」と同じ exit 1 にしない."""
        holder = self.orphan_browser()
        self.lock(holder)
        proc, out = self.stop(holder, env_extra={**self.bash_env("kill() { return 1; }\n"),
                                                 "CHROME_PROFILE_LOCK_WAIT": "30"})
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertEqual((out["REFUSED"], out["STOPPED"]), ("signal-failed", "no"))
        self.assertTrue(alive(holder))

    def test_stop_succeeds_when_the_target_is_gone_before_the_signal(self):
        """送れなかった理由が「既に終わっていた」（ESRCH）なら止まったとして扱う."""
        holder = self.orphan_browser()
        self.lock(holder)
        gone = ('kill() { command kill -KILL "$2" 2>/dev/null\n'
                '  while ps -o stat= -p "$2" 2>/dev/null | grep -qv "^Z"; do sleep 0.05; done\n'
                '  return 1; }\n')
        proc, out = self.stop(holder, env_extra=self.bash_env(gone))
        self.assertEqual((proc.returncode, out["STOPPED"]), (0, "yes"), proc.stderr)
        self.assertNotIn("REFUSED", out)
        self.assertFalse(alive(holder))


if __name__ == "__main__":
    unittest.main()
