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

    def set_origin_main(self) -> None:
        """`refs/remotes/origin/main` を現 HEAD に張る（merged / ahead 判定の基準）.

        scan.sh は `origin/main` が無いと merged 判定を保守側（keep）に倒すため、
        reap に落ちる verdict 境界を測るにはこの ref が要る。
        """
        res = self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.assertEqual(res.returncode, 0, res.stderr)

    def stub_bin(self, name: str, script: str) -> dict[str, str]:
        """PATH 先頭に差し込む実行可能スタブを作り、それを積んだ env を返す.

        gh / lsof / psql の presence 分岐を決定的に測る（CI ランナーの実インストール有無に
        依存させない）。`script` は `#!/bin/sh` 本体。
        """
        bin_dir = self.root / "tmp" / "stubbin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        f = bin_dir / name
        f.write_text("#!/bin/sh\n" + script, encoding="utf-8")
        f.chmod(0o755)
        env = self._env()
        env["PATH"] = "%s:%s" % (bin_dir, env["PATH"])
        return env

    def scan_env(self, env: dict[str, str], *args: str,
                 cwd: Path | None = None) -> list[dict]:
        """env を明示指定して scan を走らせる（stub PATH を渡すため）."""
        res = subprocess.run(["bash", str(SCAN), *args], cwd=str(cwd or self.root),
                             capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        return [json.loads(l) for l in res.stdout.splitlines() if l.strip()]


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


class ScanVerdictBoundaryTest(GcTestBase):
    """verdict が keep/reap に切り替わる境界（origin/main 基準の merged / ahead / dirty）.

    `origin/main` を張った状態でしか通らない分岐（no-pr-ahead / reapable / merged 判定）を
    測る。既存の ScanKeepTest は origin/main 無し（保守 keep）しか見ておらず、
    分類ロジックの `!=` / `-gt` / reasons 件数の境界が素通りしていた（mutation-nightly #229）。
    """

    def _lsof_empty_env(self) -> dict[str, str]:
        """lsof を「生存プロセス無し」で固定するスタブ env.

        `--no-lsof` は live_unknown=true→live-or-unknown で必ず keep に倒れるため、reap 側の
        境界は測れない。lsof を空出力に固定すると USE_LSOF=1 のまま live が空になり、
        lsof の実インストール有無に依存せず reap 経路を決定的に踏める。
        """
        return self.stub_bin("lsof", "exit 0\n")

    def test_merged_clean_branch_is_reaped(self):
        """origin/main に merged 済み・clean・PR 無しの worktree は reap（reasons=reapable）.

        reasons が 1 件も立たない → verdict=reap の経路。self/primary/dirty/merged/ahead の
        どれか 1 つでも誤って真に倒れると keep になるので、reap 側の最小ケースで境界を締める。
        """
        self.set_origin_main()
        wt = self.add_worktree("wt-merged", branch="feat-merged")  # HEAD=origin/main に作る→merged
        rows = self.scan_env(self._lsof_empty_env(), cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["verdict"], "reap", row)
        self.assertEqual(row["reasons"], ["reapable"])
        self.assertFalse(row["primary"])
        self.assertFalse(row["dirty"])
        self.assertTrue(row["merged_into_main"])
        self.assertEqual(row["ahead_of_main"], 0)

    def test_merged_but_dirty_branch_is_kept(self):
        """merged でも未コミット変更があれば keep（dirty ゲートが merged より優先）.

        merged+clean なら reap になるケースを dirty にすると keep へ倒れることを測る
        （dirty 判定ガード `[ prunable != 1 ] && [ -d path ]` の `!=` が死ぬと dirty を
        取りこぼして reap してしまう）。
        """
        self.set_origin_main()
        wt = self.add_worktree("wt-merged-dirty", branch="feat-merged-dirty")
        (wt / "scratch.txt").write_text("uncommitted\n")
        rows = self.scan_env(self._lsof_empty_env(), cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["verdict"], "keep", row)
        self.assertTrue(row["dirty"])
        self.assertIn("dirty", row["reasons"])

    def test_ahead_unmerged_branch_without_pr_is_kept(self):
        """origin/main より ahead で PR 無しの worktree は no-pr-ahead で keep.

        `[ -z pr_state ] && [ ahead -gt 0 ]` の `-gt`（ahead==0 との境界）と `&&` が死ぬと、
        ahead の有無に関わらず reason が付いたり消えたりする。ahead=1 を立てて keep を測る。
        """
        self.set_origin_main()
        wt = self.add_worktree("wt-ahead", branch="feat-ahead")
        (wt / "f.txt").write_text("x\n")
        self.git("add", "f.txt", cwd=wt)
        self.git("commit", "-q", "-m", "ahead", cwd=wt)
        rows = self.scan_env(self._lsof_empty_env(), cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["verdict"], "keep", row)
        self.assertEqual(row["ahead_of_main"], 1)
        self.assertFalse(row["merged_into_main"])
        self.assertIn("no-pr-ahead", row["reasons"])

    def test_linked_worktree_is_not_primary(self):
        """linked worktree は primary=false（primary 判定 `[ -n gd ] && [ gd = gcd ]`）.

        この `&&` が `||` に倒れると linked worktree も primary=true になり、
        本来 reap できる worktree が primary-worktree で keep され続ける。
        """
        self.set_origin_main()
        wt = self.add_worktree("wt-linked", branch="feat-linked")
        rows = self.scan_env(self._lsof_empty_env(), cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertFalse(row["primary"], row)
        self.assertNotIn("primary-worktree", row["reasons"])

    def test_no_lsof_sets_live_unknown_and_keeps(self):
        """`--no-lsof` は live_unknown=true にして live-or-unknown で keep に倒す.

        live ブロックのガード `[ USE_LSOF=1 ] && [ prunable!=1 ] && [ -d path ]` の `&&` や、
        live-or-unknown reason の `[ prunable != 1 ]` の `!=` が死ぬと、--no-lsof でも
        live_unknown を立て損ねて「生存不明なのに reap」へ倒れる。merged+clean（本来 reap）を
        --no-lsof で keep できることで両方を締める。
        """
        self.set_origin_main()
        wt = self.add_worktree("wt-unknown", branch="feat-unknown")  # merged(HEAD)+clean
        rows = self.scan("--no-lsof", cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertTrue(row["live_unknown"], row)
        self.assertEqual(row["verdict"], "keep", row)
        self.assertIn("live-or-unknown-process", row["reasons"])

    def test_live_pids_populated_when_lsof_reports_a_pid(self):
        """lsof が pid を返すと live_pids に載り live-or-unknown で keep.

        live_pids の jq `if $live == "" then [] else (split...)` の `==` が反転すると、
        pid があるのに空配列になる（生存プロセスを取りこぼして reap する）。
        """
        self.set_origin_main()
        wt = self.add_worktree("wt-live", branch="feat-live")
        env = self.stub_bin("lsof", 'echo 99999\n')  # cwd が path 配下の pid を 1 つ返す体
        rows = self.scan_env(env, cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["live_pids"], [99999], row)
        self.assertFalse(row["live_unknown"])
        self.assertEqual(row["verdict"], "keep")
        self.assertIn("live-or-unknown-process", row["reasons"])


class ScanJsonFieldsTest(GcTestBase):
    """JSON フィールドの値（branch / nested_parent / marker / db_guess）の契約."""

    def test_branch_field_carries_the_branch_name(self):
        """branch フィールドは実ブランチ名（jq `if $branch == "" then null` の反転検出）."""
        wt = self.add_worktree("wt-b", branch="feat-branchname")
        row = self.row_for(self.scan("--no-lsof", cwd=self.root), wt)
        self.assertEqual(row["branch"], "feat-branchname", row)

    def test_nested_parent_null_for_plain_and_set_for_agent(self):
        """nested_parent は通常 null・agent worktree では親 review パス（jq の反転検出）."""
        plain = self.add_worktree("wt-plain2", branch="feat-plain2")
        parent = self.add_worktree(".claude/worktrees/review-x", branch="review-x")
        agent = self.add_worktree(".claude/worktrees/review-x/agent-q", branch="agent-q")
        rows = self.scan("--no-lsof", cwd=self.root)
        self.assertIsNone(self.row_for(rows, plain)["nested_parent"])
        self.assertEqual(self.row_for(rows, agent)["nested_parent"], str(parent))

    def test_marker_and_db_guess_populated_for_dev_worktree(self):
        """DB_NAME marker を持つ dev worktree は marker / db_guess に載る（jq 反転検出）.

        `if $db_name == "" then null/[]` の `==` が反転すると、marker 有りの行が
        null/[] になり DB drop 候補の取りこぼし（F1 の逆）になる。
        """
        wt = self.add_worktree("wt-dev", branch="feat-dev2")
        (wt / "envs").mkdir()
        (wt / "envs" / ".backend.env.worktree").write_text('DB_NAME="appdb_wtdev"\n')
        row = self.row_for(self.scan("--no-lsof", cwd=self.root), wt)
        self.assertEqual(row["db_guess"], ["appdb_wtdev"], row)
        self.assertEqual(row["marker"], {"db_name": "appdb_wtdev"})

    def test_non_marker_worktree_has_no_db_guess(self):
        """marker の無い worktree は db_guess 空・marker null（DB に触れない / F1）."""
        wt = self.add_worktree("wt-nomarker", branch="feat-nomarker")
        row = self.row_for(self.scan("--no-lsof", cwd=self.root), wt)
        self.assertEqual(row["db_guess"], [])
        self.assertIsNone(row["marker"])


class ScanPrStateTest(GcTestBase):
    """gh presence 分岐（PR 状態の取り込み）を gh スタブで決定的に測る."""

    def _gh_stub_env(self, pr_json: str) -> dict[str, str]:
        # scan.sh は `gh pr list --head <branch> --json number,state` を叩く。
        # サブコマンドに関わらず固定 JSON を返すスタブで pr_state を注入する。
        self.stub_bin("lsof", "exit 0\n")  # 同じ stubbin に積む（live を空に固定）
        return self.stub_bin("gh", "printf '%s' '" + pr_json + "'\n")

    def test_open_pr_branch_is_kept(self):
        """PR が OPEN の worktree は pr-open で keep（merged 済みでも PR 優先で残す）."""
        self.set_origin_main()
        wt = self.add_worktree("wt-pr-open", branch="feat-pr-open")  # merged(HEAD) だが PR OPEN
        env = self._gh_stub_env('[{"number":7,"state":"OPEN"}]')
        rows = self.scan_env(env, cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["verdict"], "keep", row)
        self.assertIn("pr-open", row["reasons"])
        self.assertEqual(row["pr"], {"number": 7, "state": "OPEN"})

    def test_merged_pr_closed_branch_is_reaped(self):
        """PR が MERGED で branch も merged 済みなら reap（pr_state 非 OPEN は keep 要因にしない）."""
        self.set_origin_main()
        wt = self.add_worktree("wt-pr-merged", branch="feat-pr-merged")
        env = self._gh_stub_env('[{"number":8,"state":"MERGED"}]')
        rows = self.scan_env(env, cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["verdict"], "reap", row)
        self.assertNotIn("pr-open", row["reasons"])


class ScanPrDictTest(GcTestBase):
    """PR 辞書（リポごとに 1 回の `gh pr list`）が効いていること（`--head` を worktree ごとに叩かない）."""

    def test_branch_found_in_dict_skips_per_branch_call(self):
        self.set_origin_main()
        wt = self.add_worktree("wt-dict", branch="feat-dict")
        log = self.root / "tmp" / "gh.log"
        self.stub_bin("lsof", "exit 0\n")
        env = self.stub_bin("gh", 'echo "$@" >> "%s"\n'
                            'printf \'%%s\' \'[{"number":9,"state":"MERGED","headRefName":"feat-dict"}]\'\n' % log)
        rows = self.scan_env(env, cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["pr"], {"number": 9, "state": "MERGED"})
        calls = log.read_text().splitlines()
        self.assertTrue(any("--limit 200" in c for c in calls), calls)
        # primary の `main` は辞書に無いので --head が走る。辞書にある feat-dict だけを見る
        self.assertFalse(any("--head feat-dict" in c for c in calls),
                         "辞書にあるのに --head を叩いた: %s" % calls)


class ReapDirtyForceTest(GcTestBase):
    """reap の dirty 再確認（clean は WARN を出さない / dirty は --force で消す）."""

    def _reap_row(self, path: Path) -> str:
        return json.dumps({"path": str(path), "kind": "other",
                          "nested_parent": None, "db_guess": [], "verdict": "reap"}) + "\n"

    def test_clean_reap_target_is_removed_without_force_warning(self):
        """clean な reap 対象に dirty WARN を出さない（`[ -d path ] && [ -n status ]` の境界）.

        この `&&` が死ぬと clean でも force WARN が出る（= dirty 判定が常時真）。
        WARN が stderr に出ないことと、--force 無しで remove されることを測る。
        """
        wt = self.add_worktree("wt-clean", branch="feat-clean")
        res = self.reap(self._reap_row(wt))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse(wt.is_dir(), "reap されなかった")
        self.assertNotIn("未コミット変更", res.stderr)

    def test_dirty_reap_target_is_force_removed_with_warning(self):
        """dirty な reap 対象は WARN を出して --force で remove する."""
        wt = self.add_worktree("wt-dirty-reap", branch="feat-dirty-reap")
        (wt / "scratch.txt").write_text("uncommitted\n")
        res = self.reap(self._reap_row(wt))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("未コミット変更", res.stderr)
        self.assertFalse(wt.is_dir(), "dirty な reap 対象が --force で消えていない")

    def test_became_live_target_is_skipped(self):
        """削除直前に lsof が生存 pid を返したら SKIP して消さない（became-live race）.

        `command -v lsof && have_lsof=1` の `&&` が死ぬと lsof があっても have_lsof=0 に
        なり再確認が走らず、使い始めた worktree を消す。lsof スタブで pid を返させて
        SKIP に落ちることと、worktree が残ることを測る。
        """
        wt = self.add_worktree("wt-became-live", branch="feat-became-live")
        bin_dir = self.root / "tmp" / "stubbin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        (bin_dir / "lsof").write_text("#!/bin/sh\necho 99999\n")
        (bin_dir / "lsof").chmod(0o755)
        env = self._env()
        env["PATH"] = "%s:%s" % (bin_dir, env["PATH"])
        res = subprocess.run(["bash", str(REAP)], cwd=str(self.root),
                             input=self._reap_row(wt), capture_output=True, text=True,
                             env=env, timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("SKIP", res.stderr)
        self.assertTrue(wt.is_dir(), "became-live なのに消えた")


class ScanDetachedReviewTest(GcTestBase):
    """detached な review worktree（branch=null）の PR 解決（GitHub issue #224）.

    review worktree は `git checkout --detach FETCH_HEAD` で作られブランチを持たない。
    旧版はゲート 6（pr null かつ未マージ）で必ず keep に落ち、#223 の主目的（review 残骸の掃除）が
    回らなかった。HEAD sha → PR（commits/<sha>/pulls）で状態を引き、閉じていれば reap する。
    **gh が無い / PR が引けない detached は従来どおり keep**（消さない側を厚く）。
    """

    def _detached_review(self, name: str = "review-x") -> Path:
        path = self.root / ".claude" / "worktrees" / name
        res = self.git("worktree", "add", "-q", "--detach", str(path))
        self.assertEqual(res.returncode, 0, res.stderr)
        return path

    def _gh_env(self, api_json: str) -> dict[str, str]:
        """`gh api` には api_json を、`gh pr list` には空配列を返すスタブ."""
        self.stub_bin("lsof", "exit 0\n")
        return self.stub_bin(
            "gh",
            'case "$1" in api) printf \'%s\' \'' + api_json + '\' ;; *) printf "[]" ;; esac\n')

    def test_detached_without_gh_is_kept(self):
        """gh 不在なら detached は PR 不明 → no-pr-not-merged で keep（origin/main より先の HEAD）."""
        self.set_origin_main()
        wt = self._detached_review()
        (wt / "f.txt").write_text("x\n")
        self.git("add", "f.txt", cwd=wt)
        self.git("commit", "-q", "-m", "ahead", cwd=wt)
        self.stub_bin("lsof", "exit 0\n")
        env = self.stub_bin("gh", "exit 1\n")  # gh が使えない（未認証等）を PATH を絞らず stub で再現
        rows = self.scan_env(env, cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertIsNone(row["branch"])
        self.assertEqual(row["kind"], "review")
        self.assertEqual(row["verdict"], "keep", row)
        self.assertIn("no-pr-not-merged", row["reasons"])
        # detached の ahead は HEAD sha で測る（branch が無いと 0 に潰れる経路を塞ぐ）
        self.assertEqual(row["ahead_of_main"], 1, row)
        self.assertIn("no-pr-ahead", row["reasons"])

    def test_detached_with_merged_pr_is_reaped(self):
        """HEAD sha に紐づく PR が merged なら detached review worktree は reap."""
        self.set_origin_main()
        wt = self._detached_review()
        (wt / "f.txt").write_text("x\n")
        self.git("add", "f.txt", cwd=wt)
        self.git("commit", "-q", "-m", "pr head", cwd=wt)  # origin/main に無い = 未マージ扱い
        env = self._gh_env('[{"number":42,"state":"closed","merged_at":"2026-09-01T00:00:00Z"}]')
        rows = self.scan_env(env, cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["pr"], {"number": 42, "state": "MERGED"})
        self.assertEqual(row["verdict"], "reap", row)
        self.assertIsNotNone(row["head"])

    def test_detached_with_open_pr_is_kept(self):
        """PR が open なら pr-open で keep（merged_at 無し・state open）."""
        self.set_origin_main()
        wt = self._detached_review()
        env = self._gh_env('[{"number":43,"state":"open","merged_at":null}]')
        rows = self.scan_env(env, cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["pr"], {"number": 43, "state": "OPEN"})
        self.assertEqual(row["verdict"], "keep", row)
        self.assertIn("pr-open", row["reasons"])

    def test_detached_with_closed_unmerged_pr_is_reaped(self):
        """PR が closed（未マージ）でも review 残骸は reap（PR 側に履歴が残る）."""
        self.set_origin_main()
        wt = self._detached_review()
        env = self._gh_env('[{"number":44,"state":"closed","merged_at":null}]')
        rows = self.scan_env(env, cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["pr"]["state"], "CLOSED")
        self.assertEqual(row["verdict"], "reap", row)

    def test_parent_review_is_not_dirty_because_of_nested_agent_dirs(self):
        """親 review worktree はネスト agent dir（.claude/worktrees/）を untracked に数えない."""
        self.set_origin_main()
        parent = self._detached_review("review-p")
        agent = parent / ".claude" / "worktrees" / "agent-a"
        res = self.git("worktree", "add", "-q", "--detach", str(agent))
        self.assertEqual(res.returncode, 0, res.stderr)
        env = self._gh_env('[{"number":45,"state":"closed","merged_at":"2026-09-01T00:00:00Z"}]')
        rows = self.scan_env(env, cwd=self.root)
        prow = self.row_for(rows, parent)
        self.assertFalse(prow["dirty"], prow)
        self.assertFalse(prow["untracked"], prow)
        self.assertEqual(prow["verdict"], "reap", prow)
        arow = self.row_for(rows, agent)
        self.assertEqual(arow["kind"], "agent")
        self.assertEqual(arow["nested_parent"], str(parent))

    def test_parent_review_with_real_untracked_file_is_still_dirty(self):
        """ネスト dir 以外の untracked（本物の作業）は従来どおり dirty keep."""
        self.set_origin_main()
        parent = self._detached_review("review-d")
        (parent / ".claude" / "worktrees").mkdir(parents=True)
        (parent / "scratch.txt").write_text("work\n")
        env = self._gh_env('[{"number":46,"state":"closed","merged_at":"2026-09-01T00:00:00Z"}]')
        rows = self.scan_env(env, cwd=self.root)
        prow = self.row_for(rows, parent)
        self.assertTrue(prow["dirty"], prow)
        self.assertEqual(prow["verdict"], "keep", prow)


class ScanIssueStatusTest(GcTestBase):
    """`--issue-status` による Issue 状態の取り込み（GitHub issue #240）.

    調査だけで完結し PR を作らない Issue の worktree は「PR 無し・未マージ」で keep に
    落ち続ける。ブランチ名の Issue ID に閉じた状態（Done / Canceled）が付いていれば
    ゲート 6 / 7 を外す。**状態が open / 不明なら従来どおり keep**。
    """

    def _lsof_empty_env(self) -> dict[str, str]:
        return self.stub_bin("lsof", "exit 0\n")

    def _ahead_worktree(self, rel: str, branch: str) -> Path:
        wt = self.add_worktree(rel, branch=branch)
        (wt / "f.txt").write_text("x\n")
        self.git("add", "f.txt", cwd=wt)
        self.git("commit", "-q", "-m", "research", cwd=wt)
        return wt

    def _status_file(self, mapping: dict) -> Path:
        f = self.root / "tmp" / "issues.json"
        f.write_text(json.dumps(mapping), encoding="utf-8")
        return f

    def test_issue_id_is_extracted_from_branch(self):
        """ブランチ名の `PRE-1` を issue.id に載せる（状態ファイル無しなら state null）."""
        self.set_origin_main()
        wt = self._ahead_worktree("wt-pre1", "feat/PRE-1-research")
        rows = self.scan_env(self._lsof_empty_env(), cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["issue"], {"id": "PRE-1", "state": None, "closed": False})
        self.assertEqual(row["verdict"], "keep", row)
        self.assertIn("no-pr-ahead", row["reasons"])
        # 状態が無いのに `issue-open:PRE-1:` のような空注記を付けない
        self.assertFalse([r for r in row["reasons"] if r.startswith("issue-")], row["reasons"])

    def test_closed_issue_lifts_no_pr_gates(self):
        """Issue が completed なら no-pr-* を外して reap（reasons に issue-closed を添える）."""
        self.set_origin_main()
        wt = self._ahead_worktree("wt-pre2", "feat/PRE-2-research")
        f = self._status_file({"PRE-2": {"state": "Done", "type": "completed"}})
        rows = self.scan_env(self._lsof_empty_env(), "--issue-status", str(f), cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["verdict"], "reap", row)
        self.assertIn("issue-closed:PRE-2:Done", row["reasons"])
        self.assertNotIn("no-pr-ahead", row["reasons"])
        self.assertTrue(row["issue"]["closed"])
        self.assertTrue(wt.is_dir())  # scan は副作用なし

    def test_open_issue_keeps_and_annotates(self):
        """Issue が started なら keep のまま、reasons に issue-open を添える."""
        self.set_origin_main()
        wt = self._ahead_worktree("wt-pre3", "feat/PRE-3-research")
        f = self._status_file({"PRE-3": {"state": "In Progress", "type": "started"}})
        rows = self.scan_env(self._lsof_empty_env(), "--issue-status", str(f), cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["verdict"], "keep", row)
        self.assertIn("no-pr-ahead", row["reasons"])
        self.assertIn("issue-open:PRE-3:In Progress", row["reasons"])

    def test_type_wins_over_state_name(self):
        """type があれば名前より優先（名前が Done でも type が started なら open 扱い）."""
        self.set_origin_main()
        wt = self._ahead_worktree("wt-pre4", "feat/PRE-4")
        f = self._status_file({"PRE-4": {"state": "Done", "type": "started"}})
        rows = self.scan_env(self._lsof_empty_env(), "--issue-status", str(f), cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["verdict"], "keep", row)

    def test_string_value_is_matched_by_name(self):
        """値が文字列なら名前で判定（"Canceled" は閉じている）."""
        self.set_origin_main()
        wt = self._ahead_worktree("wt-pre5", "feat/PRE-5")
        f = self._status_file({"PRE-5": "Canceled"})
        rows = self.scan_env(self._lsof_empty_env(), "--issue-status", str(f), cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["verdict"], "reap", row)

    def test_closed_issue_does_not_override_other_gates(self):
        """Issue が閉じていても dirty なら keep（外すのはゲート 6 / 7 だけ）."""
        self.set_origin_main()
        wt = self._ahead_worktree("wt-pre6", "feat/PRE-6")
        (wt / "scratch.txt").write_text("uncommitted\n")
        f = self._status_file({"PRE-6": {"state": "Done", "type": "completed"}})
        rows = self.scan_env(self._lsof_empty_env(), "--issue-status", str(f), cwd=self.root)
        row = self.row_for(rows, wt)
        self.assertEqual(row["verdict"], "keep", row)
        self.assertIn("dirty", row["reasons"])

    def test_unreadable_status_file_is_fatal(self):
        """状態ファイルが読めない / オブジェクトでないなら exit 2（黙って無視しない）."""
        f = self._status_file({})
        f.write_text("[1,2]", encoding="utf-8")
        res = subprocess.run(["bash", str(SCAN), "--no-lsof", "--issue-status", str(f)],
                             cwd=str(self.root), capture_output=True, text=True,
                             env=self._env(), timeout=60)
        self.assertEqual(res.returncode, 2, res.stderr)
        res = subprocess.run(["bash", str(SCAN), "--no-lsof", "--issue-status",
                              str(self.root / "tmp" / "missing.json")],
                             cwd=str(self.root), capture_output=True, text=True,
                             env=self._env(), timeout=60)
        self.assertEqual(res.returncode, 2, res.stderr)


class ScanAllTest(GcTestBase):
    """`--all [root]` の横断走査（GitHub issue #224）.

    find は main repo の発見にだけ使い、worktree の列挙は各 repo の git に委ねる
    （design doc open 5）。submodule の gitlink は common-dir が `.git/modules/<name>` なので
    main repo として採用されない。
    """

    def _init_repo(self, rel: str) -> Path:
        path = self.root / rel
        path.mkdir(parents=True)
        env = self._env()
        subprocess.run(["git", "init", "-q"], cwd=path, check=True, env=env)
        for key, value in (("user.email", "t@example.com"), ("user.name", "t")):
            subprocess.run(["git", "config", key, value], cwd=path, check=True, env=env)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"],
                       cwd=path, check=True, env=env)
        return path

    def test_all_scans_every_repo_under_root(self):
        """root 配下の 2 リポの worktree が両方出て、各行の repo が自分のリポを指す."""
        a = self._init_repo("proj/a")
        b = self._init_repo("proj/b")
        wa = a / "wt-a"
        wb = b.parent / "b-wt"
        self.assertEqual(self.git("worktree", "add", "-q", "-b", "fa", str(wa), cwd=a).returncode, 0)
        self.assertEqual(self.git("worktree", "add", "-q", "-b", "fb", str(wb), cwd=b).returncode, 0)
        rows = self.scan("--no-lsof", "--all", str(self.root / "proj"), cwd=self.root)
        paths = {r["path"] for r in rows}
        self.assertIn(str(wa), paths)
        self.assertIn(str(wb), paths)
        self.assertEqual(self.row_for(rows, wa)["repo"], str(a))
        self.assertEqual(self.row_for(rows, wb)["repo"], str(b))
        # 自分のリポ（self.root）は proj 配下ではないので出ない
        self.assertNotIn(str(self.root), paths)

    def test_all_does_not_treat_submodule_gitlink_as_repo(self):
        """submodule の `.git` ファイルは main repo に採用しない（他人のリポを候補に混ぜない）."""
        sup = self._init_repo("proj/super")
        sub = self._init_repo("proj/sublib")
        env = self._env()
        env["GIT_ALLOW_PROTOCOL"] = "file"
        res = subprocess.run(["git", "-c", "protocol.file.allow=always", "submodule", "add", "-q",
                              str(sub), "vendor/sublib"], cwd=sup, capture_output=True,
                             text=True, env=env)
        self.assertEqual(res.returncode, 0, res.stderr)
        rows = self.scan("--no-lsof", "--all", str(self.root / "proj"), cwd=self.root)
        repos = {r["repo"] for r in rows}
        # `.git/modules/<name>` の親（`<super>/.git/modules`）を repo に採用しないこと
        self.assertEqual(repos, {str(sup), str(sub)}, repos)
        self.assertNotIn(str(sup / "vendor" / "sublib"), repos)
        self.assertNotIn(str(sup / "vendor" / "sublib"), {r["path"] for r in rows})

    def test_all_explicit_root_wins_over_config_file(self):
        """root を引数で渡したら `.claude/dev-workflow.json` の値では上書きしない."""
        a = self._init_repo("projA/a")
        self._init_repo("projB/b")
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "dev-workflow.json").write_text(
            json.dumps({"worktree_gc_root": str(self.root / "projB")}), encoding="utf-8")
        rows = self.scan("--no-lsof", "--all", str(self.root / "projA"), cwd=self.root)
        self.assertEqual({r["repo"] for r in rows}, {str(a)})

    def test_all_root_falls_back_to_config_file(self):
        """root 省略・環境変数なしなら `.claude/dev-workflow.json` の worktree_gc_root を使う."""
        b = self._init_repo("projB/b")
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "dev-workflow.json").write_text(
            json.dumps({"worktree_gc_root": str(self.root / "projB")}), encoding="utf-8")
        env = self._env()
        env.pop("DEV_WORKFLOW_WORKTREE_GC_ROOT", None)
        rows = self.scan_env(env, "--no-lsof", "--all", cwd=self.root)
        self.assertEqual({r["repo"] for r in rows}, {str(b)})

    def test_all_root_defaults_to_env(self):
        """root 省略時は DEV_WORKFLOW_WORKTREE_GC_ROOT を使う."""
        a = self._init_repo("proj2/a")
        env = self._env(DEV_WORKFLOW_WORKTREE_GC_ROOT=str(self.root / "proj2"))
        rows = self.scan_env(env, "--no-lsof", "--all", cwd=self.root)
        self.assertEqual({r["repo"] for r in rows}, {str(a)})

    def test_depth_limits_the_search(self):
        """`--depth N` は find の深さ。浅すぎると見つからず、足りれば見つかる（値の受け取りも測る）."""
        deep = self._init_repo("proj3/x/y/z/deep")
        rows = self.scan("--no-lsof", "--all", str(self.root / "proj3"), "--depth", "2", cwd=self.root)
        self.assertNotIn(str(deep), {r["repo"] for r in rows})
        rows = self.scan("--no-lsof", "--all", str(self.root / "proj3"), "--depth", "5", cwd=self.root)
        self.assertIn(str(deep), {r["repo"] for r in rows})

    def test_depth_without_value_is_usage_error(self):
        res = subprocess.run(["bash", str(SCAN), "--no-lsof", "--all", str(self.root), "--depth"],
                             cwd=str(self.root), capture_output=True, text=True,
                             env=self._env(), timeout=60)
        self.assertEqual(res.returncode, 2, res.stderr)

    def test_all_with_bad_root_is_fatal(self):
        res = subprocess.run(["bash", str(SCAN), "--no-lsof", "--all", str(self.root / "nope")],
                             cwd=str(self.root), capture_output=True, text=True,
                             env=self._env(), timeout=60)
        self.assertEqual(res.returncode, 2, res.stderr)


class ReapCrossRepoTest(GcTestBase):
    """reap が行の `repo` を見て他リポの worktree を扱う（--all の出力を受ける）."""

    def _init_repo(self, rel: str) -> Path:
        path = self.root / rel
        path.mkdir(parents=True)
        env = self._env()
        subprocess.run(["git", "init", "-q"], cwd=path, check=True, env=env)
        for key, value in (("user.email", "t@example.com"), ("user.name", "t")):
            subprocess.run(["git", "config", key, value], cwd=path, check=True, env=env)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"],
                       cwd=path, check=True, env=env)
        return path

    def test_removes_worktree_of_another_repo(self):
        """cwd と別リポの行でも repo を見て実在確認・remove できる."""
        other = self._init_repo("other")
        wt = other.parent / "other-wt"
        self.assertEqual(self.git("worktree", "add", "-q", "-b", "fo", str(wt), cwd=other).returncode, 0)
        row = json.dumps({"repo": str(other), "path": str(wt), "kind": "other",
                          "nested_parent": None, "db_guess": [], "verdict": "reap"})
        res = self.reap(row + "\n", cwd=self.root)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("SKIP", res.stderr)
        self.assertFalse(wt.is_dir(), "他リポの worktree が reap されなかった")
        listed = self.git("worktree", "list", "--porcelain", cwd=other).stdout
        self.assertNotIn(str(wt), listed, "prune が other リポで走っていない")

    def test_prunable_row_is_pruned_only_on_real_run(self):
        """prunable 行は実行時だけ prune され、dry-run では worktree list に残る."""
        import shutil

        wt = self.add_worktree("wt-prune", branch="feat-prune")
        shutil.rmtree(wt)
        row = json.dumps({"repo": str(self.root), "path": str(wt), "kind": "prunable",
                          "nested_parent": None, "db_guess": [], "verdict": "reap"})
        res = self.reap(row + "\n", "--dry-run")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn(str(wt), self.git("worktree", "list", "--porcelain").stdout,
                      "dry-run なのに prune された")
        res = self.reap(row + "\n")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn(str(wt), self.git("worktree", "list", "--porcelain").stdout,
                         "prune が走っていない")

    def test_row_without_repo_uses_cwd_repo(self):
        """repo の無い行（旧版 scan）は cwd のリポで見る（後方互換）."""
        wt = self.add_worktree("wt-legacy", branch="feat-legacy")
        row = json.dumps({"path": str(wt), "kind": "other",
                          "nested_parent": None, "db_guess": [], "verdict": "reap"})
        res = self.reap(row + "\n")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse(wt.is_dir())


if __name__ == "__main__":
    unittest.main()
