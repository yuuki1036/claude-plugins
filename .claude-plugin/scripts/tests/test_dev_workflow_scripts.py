#!/usr/bin/env python3
"""dev-workflow の worktree-gc スクリプト（scan.sh / reap.sh）の CLI 境界テスト.

worktree-gc は **worktree を消し DB を drop する不可逆操作**なので、
「消さない / 拒否する」条件を肯定側より厚く書く:

- `scan.sh` … 副作用なしの列挙。primary / self / dirty を **keep** に倒すことと、
  ブランチ名（PR 作者が制御する外部入力）が**シェルで再評価されない**ことを測る。
- `reap.sh` … stdin の承認済み行だけを消す。`verdict != reap` の行を渡したら
  **全体を exit 2 で拒否**すること、scan 後に消えた path を SKIP することを測る。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from git_env import scrub

REPO = Path(__file__).resolve().parents[3]
PLUGIN = REPO / "dev-workflow"
SCAN = PLUGIN / "scripts" / "worktree-gc" / "scan.sh"
REAP = PLUGIN / "scripts" / "worktree-gc" / "reap.sh"


class GcTestBase(unittest.TestCase):
    """一時 git repo に本物の worktree を張る（`git worktree list` の出力を模造しない）."""

    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        (self.root / "tmp").mkdir()
        env = self._env()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True, env=env)
        for key, value in (("user.email", "t@example.com"), ("user.name", "t")):
            subprocess.run(["git", "config", key, value], cwd=self.root, check=True, env=env)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"],
                       cwd=self.root, check=True, env=env)

    def _env(self, **extra: str) -> dict[str, str]:
        env = scrub(TMPDIR=str(self.root / "tmp"), CLAUDE_PLUGIN_ROOT=str(PLUGIN))
        env.pop("LC_ALL", None)
        env["LC_CTYPE"] = "C.UTF-8"
        env.update(extra)
        return env

    def git(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=str(cwd or self.root),
                              capture_output=True, text=True, env=self._env())

    def add_worktree(self, rel: str, branch: str | None = None) -> Path:
        path = self.root / rel
        args = ["worktree", "add", "-q"]
        if branch:
            args += ["-b", branch]
        res = self.git(*args, str(path))
        self.assertEqual(res.returncode, 0, res.stderr)
        return path

    def scan(self, *args: str, cwd: Path | None = None) -> list[dict]:
        res = subprocess.run(["bash", str(SCAN), *args], cwd=str(cwd or self.root),
                             capture_output=True, text=True, env=self._env(), timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        rows = []
        for line in res.stdout.splitlines():
            if line.strip():
                rows.append(json.loads(line))  # 各行が valid JSON でなければここで落ちる
        return rows

    def reap(self, stdin: str, *args: str, cwd: Path | None = None
             ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(REAP), *args], cwd=str(cwd or self.root),
                              input=stdin, capture_output=True, text=True,
                              env=self._env(), timeout=60)

    def row_for(self, rows: list[dict], path: Path) -> dict:
        for r in rows:
            if r["path"] == str(path):
                return r
        self.fail(f"{path} が scan 出力に無い")


class ScanKeepTest(GcTestBase):
    """**消してはいけないものを keep に倒す**（誤 reap の blast radius が最大）."""

    def test_primary_worktree_is_kept(self):
        """メインの作業ツリーは primary-worktree として keep."""
        rows = self.scan(cwd=self.root)
        primary = self.row_for(rows, self.root)
        self.assertEqual(primary["verdict"], "keep")
        self.assertTrue(primary["primary"])
        self.assertIn("primary-worktree", primary["reasons"])

    def test_self_worktree_is_kept(self):
        """scan を起動した cwd を含む worktree は self として keep."""
        wt = self.add_worktree("wt-self", branch="feat-self")
        rows = self.scan(cwd=wt)
        row = self.row_for(rows, wt)
        self.assertEqual(row["verdict"], "keep")
        self.assertIn("self", row["reasons"])

    def test_dirty_worktree_is_kept(self):
        """未コミット変更のある worktree は keep（--no-lsof で live 要因を排して dirty を単離）."""
        wt = self.add_worktree("wt-dirty", branch="feat-dirty")
        (wt / "scratch.txt").write_text("uncommitted\n")
        rows = self.scan("--no-lsof", cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["verdict"], "keep")
        self.assertIn("dirty", row["reasons"])

    def test_no_pr_unmerged_branch_is_kept(self):
        """PR も無く origin/main も無い（merged 判定不能）なら保守的に keep."""
        wt = self.add_worktree("wt-plain", branch="feat-plain")
        rows = self.scan("--no-lsof", cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["verdict"], "keep")
        self.assertIn("no-pr-not-merged", row["reasons"])


class ScanReapTest(GcTestBase):
    """reap に落ちる条件（prunable）と JSON 妥当性・シェル注入耐性."""

    def test_prunable_is_reaped(self):
        """dir を消した残骸は prunable として reap（prune で回収する対象）."""
        import shutil

        wt = self.add_worktree("wt-gone", branch="feat-gone")
        shutil.rmtree(wt)  # dir だけ消す（git worktree list には prunable として残る）
        rows = self.scan("--no-lsof", cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["verdict"], "reap")
        self.assertEqual(row["kind"], "prunable")

    def test_every_line_is_valid_json(self):
        """全行が valid JSON（self.scan が json.loads で落ちなければ OK）."""
        self.add_worktree("wt-a", branch="feat-a")
        self.add_worktree("wt-b", branch="feat-b")
        rows = self.scan("--no-lsof", cwd=self.root)
        self.assertGreaterEqual(len(rows), 3)  # primary + 2

    def test_branch_name_is_never_evaluated_by_the_shell(self):
        """ブランチ名に埋め込んだコマンドが実行されない（外部入力のシェル再評価防止）.

        `feat/$(pwn)` は git check-ref-format を通る有効な ref 名。評価されたら PATH 上の
        `pwn` が走るので canary の有無で測れる（detect-dev-worktree.sh と同じ脅威モデル）。
        """
        canary = self.root / "tmp" / "pwned"
        bin_dir = self.root / "tmp" / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        pwn = bin_dir / "pwn"
        pwn.write_text("#!/bin/sh\ntouch '%s'\n" % canary, encoding="utf-8")
        pwn.chmod(0o755)
        env = self._env()
        env["PATH"] = "%s:%s" % (bin_dir, env["PATH"])

        wt = self.root / "wt-inj"
        res = self.git("worktree", "add", "-q", "-b", "feat/$(pwn)", str(wt))
        self.assertEqual(res.returncode, 0, res.stderr)
        run = subprocess.run(["bash", str(SCAN), "--no-lsof"], cwd=str(self.root),
                             capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse(canary.exists(), "ブランチ名がシェルで評価された（注入経路がある）")
        # クラッシュせず全行 valid JSON であること
        for line in run.stdout.splitlines():
            if line.strip():
                json.loads(line)


class ReapContractTest(GcTestBase):
    """**入力契約 = 消さない側**（承認フローの迂回・stale な承認を弾く）."""

    def test_rejects_keep_verdict_rows(self):
        """verdict=keep の行が 1 行でも混じれば全体を exit 2 で拒否."""
        row = json.dumps({"path": str(self.root), "kind": "other",
                          "nested_parent": None, "db_guess": [], "verdict": "keep"})
        res = self.reap(row + "\n", "--dry-run")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("FATAL", res.stderr)

    def test_rejects_when_a_non_json_line_is_mixed_in(self):
        """非 JSON 行が 1 行でも混じれば全体を exit 2 で拒否（fail-closed).

        `jq -e 'select(.verdict!="reap")'` 型のガードは非 JSON 混入で exit 5 を返し
        「非 reap 無し(4)」と区別できず素通りした（fail-open）。ノイズ 1 行で keep 保護が
        全面無効化されるので、reap 行 + ゴミ行の混在を必ず拒否する。
        """
        good = json.dumps({"path": str(self.root), "kind": "other",
                          "nested_parent": None, "db_guess": [], "verdict": "reap"})
        res = self.reap(good + "\nNOT_JSON_NOISE\n", "--dry-run")
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("FATAL", res.stderr)

    def test_empty_stdin_is_noop(self):
        """空 stdin は exit 0 で「対象なし」."""
        res = self.reap("", "--dry-run")
        self.assertEqual(res.returncode, 0)

    def test_malicious_db_name_is_not_dropped(self):
        """SQL identifier として不正な db_guess は自動 drop せず手動案内に落とす（注入防止).

        db_name は env 由来の外部入力。`foo'; DROP ...` のような値を psql SQL に内挿しない。
        """
        wt = self.add_worktree("wt-db", branch="feat-db")
        row = json.dumps({"path": str(wt), "kind": "dev", "nested_parent": None,
                         "db_guess": ["foo'; SELECT 1--"], "verdict": "reap"})
        res = self.reap(row + "\n", "--dry-run")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("識別子として不正", res.stderr)

    def test_skips_row_whose_path_no_longer_exists(self):
        """scan 後に消えた path（worktree list に無い）は SKIP して消さない."""
        row = json.dumps({"path": str(self.root / "gone"), "kind": "other",
                          "nested_parent": None, "db_guess": [], "verdict": "reap"})
        res = self.reap(row + "\n", "--dry-run")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("SKIP", res.stderr)


class ReapRemovalTest(GcTestBase):
    """実際に消す側（dry-run で内容確認・nested→親の順序）."""

    def _reap_row(self, path: Path, kind: str = "other", nested_parent=None) -> str:
        return json.dumps({"path": str(path), "kind": kind,
                          "nested_parent": nested_parent, "db_guess": [], "verdict": "reap"})

    def test_dry_run_lists_reap_target_without_removing(self):
        """dry-run は would remove を出すが実際には消さない."""
        wt = self.add_worktree("wt-reap", branch="feat-reap")
        res = self.reap(self._reap_row(wt) + "\n", "--dry-run")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("would remove", res.stdout)
        self.assertTrue(wt.is_dir(), "dry-run なのに消えた")

    def test_actually_removes_a_clean_reap_target(self):
        """clean な reap 対象は実際に git worktree remove される."""
        wt = self.add_worktree("wt-del", branch="feat-del")
        res = self.reap(self._reap_row(wt) + "\n")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse(wt.is_dir(), "reap されなかった")

    def test_nested_agent_removed_before_parent(self):
        """nested（agent）を親（review）より先に処理する（出力順で確認）."""
        parent = self.add_worktree(".claude/worktrees/review-1", branch="review-1")
        agent = self.add_worktree(".claude/worktrees/review-1/agent-a", branch="agent-a")
        stdin = (self._reap_row(parent, kind="review") + "\n"
                 + self._reap_row(agent, kind="agent", nested_parent=str(parent)) + "\n")
        res = self.reap(stdin, "--dry-run")
        self.assertEqual(res.returncode, 0, res.stderr)
        # parent path は agent path の prefix なので単純な str.index は衝突する。
        # 「would remove」行の順序で判定する（親 review の行は agent-a を含まない）
        lines = [l for l in res.stdout.splitlines() if "would remove" in l]
        agent_line = next(i for i, l in enumerate(lines) if "agent-a" in l)
        parent_line = next(i for i, l in enumerate(lines)
                           if "review-1" in l and "agent-a" not in l)
        self.assertLess(agent_line, parent_line,
                        "nested agent が親 review より後に処理されている")


if __name__ == "__main__":
    unittest.main()
