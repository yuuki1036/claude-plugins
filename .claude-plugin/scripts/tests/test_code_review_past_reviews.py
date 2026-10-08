#!/usr/bin/env python3
"""`fetch-past-reviews.sh` / `lib/past_reviews.py` の回帰テスト（GitHub issue #286）.

同じファイルを触った過去の merged PR のレビューコメントを集める。`gh` は PATH 先頭の stub に
差し替え、使い捨てリポジトリのコミットの件名で fixture を引く（SHA はテストごとに変わるため）。
**黙る条件を厚く見る**: 取得できない repo・コメント 0 件では、ファイルも作らずパスも出さない。
"""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from test_code_review_scripts import PLUGIN, ScriptTestBase

FETCH = PLUGIN / "scripts" / "fetch-past-reviews.sh"

GH_STUB = r'''#!/usr/bin/env python3
import json, os, subprocess, sys

args = sys.argv[1:]
fx = json.load(open(os.environ["GH_FIXTURES"]))
with open(os.environ["GH_LOG"], "a") as log:
    log.write(" ".join(args) + "\n")

if args[:2] == ["repo", "view"]:
    if not fx.get("repo"):
        sys.stderr.write("no git remotes found\n")
        sys.exit(1)
    print(fx["repo"])
    sys.exit(0)

if args[0] == "api":
    path = [a for a in args[1:] if not a.startswith("-")][0]
    parts = path.split("/")
    if parts[3] == "commits":
        subject = subprocess.run(["git", "log", "-1", "--format=%s", parts[4]],
                                 capture_output=True, text=True).stdout.strip()
        print(json.dumps(fx["pulls_by_subject"].get(subject, [])))
        sys.exit(0)
    if parts[3] == "pulls":
        pages = fx["comments"].get(parts[4])
        if pages is None:
            sys.stderr.write("HTTP 404\n")
            sys.exit(1)
        sys.stdout.write("".join(json.dumps(p) for p in pages))
        sys.exit(0)
sys.stderr.write("unexpected: %r\n" % args)
sys.exit(2)
'''


def comment(path: str, body: str, line: int = 10, user: str = "alice", reply_to: int | None = None) -> dict:
    return {"path": path, "body": body, "line": line, "user": {"login": user},
            "in_reply_to_id": reply_to}


class PastReviewsTest(ScriptTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.bin = self.root / "tmp" / "bin"
        self.bin.mkdir(parents=True, exist_ok=True)
        stub = self.bin / "gh"
        stub.write_text(GH_STUB, encoding="utf-8")
        stub.chmod(0o755)
        self.fixtures_path = self.root / "tmp" / "fixtures.json"
        self.log = self.root / "tmp" / "gh.log"
        (self.root / "src").mkdir()
        # a.py を触ったコミットが 2 つ（それぞれ PR #11・#12 で merge）、b.py を触ったコミットが 1 つ（#13）
        self.commit("src/a.py", "x = 1\n", "feat: a を足す")
        self.commit("src/a.py", "x = 2\n", "fix: a を直す")
        self.commit("src/b.py", "y = 1\n", "feat: b を足す")
        self.fixtures(
            pulls_by_subject={
                "feat: a を足す": [{"number": 11, "merged_at": "2026-09-01T00:00:00Z"}],
                "fix: a を直す": [{"number": 12, "merged_at": "2026-09-02T00:00:00Z"},
                                 {"number": 99, "merged_at": None}],
                "feat: b を足す": [{"number": 13, "merged_at": "2026-09-03T00:00:00Z"}],
            },
            comments={
                "11": [[comment("src/a.py", "None のときに落ちる。先に弾くこと")]],
                "12": [[comment("src/a.py", "境界の\n= を落とさない", line=3),
                        comment("src/a.py", "了解", reply_to=1),
                        comment("src/other.py", "別ファイルの指摘")]],
                "13": [[comment("src/b.py", "ページ 1")], [comment("src/b.py", "ページ 2", user="bob")]],
            })
        self.core_list(["src/a.py", "src/b.py"])

    def commit(self, rel: str, body: str, msg: str) -> None:
        (self.root / rel).write_text(body, encoding="utf-8")
        env = self._env()
        subprocess.run(["git", "add", rel], cwd=self.root, check=True, env=env)
        subprocess.run(["git", "commit", "-q", "-m", msg], cwd=self.root, check=True, env=env)

    def fixtures(self, repo: str | None = "o/r", **data) -> None:
        self.fixtures_path.write_text(json.dumps({"repo": repo, **data}), encoding="utf-8")

    def review_path(self, kind: str, pr: str = "") -> Path:
        proc = subprocess.run(
            ["bash", "-c", '. "$1/scripts/lib/review-paths.sh"; review_paths_init "$3"; review_path "$2"',
             "_", str(PLUGIN), kind, pr],
            cwd=self.root, capture_output=True, text=True, env=self._env(), check=True)
        return Path(proc.stdout.strip())

    def core_list(self, files: list[str], pr: str = "") -> None:
        self.review_path("corelist", pr).write_text("".join(f + "\n" for f in files), encoding="utf-8")

    def env(self) -> dict[str, str]:
        env = self._env(GH_FIXTURES=str(self.fixtures_path), GH_LOG=str(self.log))
        env["PATH"] = "%s:%s" % (self.bin, env["PATH"])
        return env

    def fetch(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(FETCH), "--base", "HEAD", *args], cwd=self.root,
                              capture_output=True, text=True, env=self.env(), timeout=60)

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    # ---- 集める --------------------------------------------------------------
    def test_comments_on_the_same_file_from_merged_prs_are_collected(self):
        res = self.fetch()
        self.assertEqual(res.returncode, 0, res.stderr)
        out = res.stdout
        self.assertIn("### `src/a.py`（PR #12, PR #11）", out)
        self.assertIn("[PR #11 @alice L10] None のときに落ちる。先に弾くこと", out)
        self.assertIn("[PR #12 @alice L3] 境界の = を落とさない", out, "改行を 1 行に畳んでいない")
        self.assertNotIn("了解", out, "返信を拾っている")
        self.assertNotIn("別ファイルの指摘", out, "別ファイルのコメントを拾っている")
        self.assertNotIn("PR #99", out, "merge されていない PR を拾っている")

    def test_every_page_is_read(self):
        out = self.fetch().stdout
        self.assertIn("[PR #13 @alice L10] ページ 1", out)
        self.assertIn("[PR #13 @bob L10] ページ 2", out)

    def test_the_pr_under_review_is_excluded(self):
        self.core_list(["src/a.py", "src/b.py"], pr="12")   # triage-signals --pr 12 が書く置き場所
        out = self.fetch("--pr", "12").stdout
        self.assertNotIn("PR #12", out)
        self.assertIn("PR #11", out)

    def test_the_same_pr_is_fetched_once(self):
        self.core_list(["src/a.py", "src/a.py"])
        self.fetch()
        self.assertEqual(sum("pulls/11/comments" in c for c in self.calls()), 1)

    def test_prs_per_file_is_capped(self):
        res = subprocess.run(
            ["python3", str(PLUGIN / "scripts" / "lib" / "past_reviews.py"), "--core-list",
             str(self.review_path("corelist")), "--base", "HEAD", "--prs-per-file", "1"],
            cwd=self.root, capture_output=True, text=True, env=self.env(), timeout=60)
        self.assertIn("### `src/a.py`（PR #12）", res.stdout)
        self.assertNotIn("PR #11", res.stdout)

    def test_comments_are_capped_with_the_rest_counted(self):
        res = subprocess.run(
            ["python3", str(PLUGIN / "scripts" / "lib" / "past_reviews.py"), "--core-list",
             str(self.review_path("corelist")), "--base", "HEAD", "--max-comments", "2",
             "--body-chars", "4"],
            cwd=self.root, capture_output=True, text=True, env=self.env(), timeout=60)
        out = res.stdout
        self.assertEqual(sum(1 for ln in out.splitlines() if ln.startswith("- [PR #")), 2)
        self.assertIn("（ほか 2 件は上限で省いた）", out)
        self.assertIn("] 境界の…", out, "本文を指定字数で切っていない（末尾の空白も落とす）")
        self.assertNotIn("### `src/b.py`", out, "上限に達した後のファイルを出している")

    def test_max_files_limits_the_files_read(self):
        res = subprocess.run(
            ["python3", str(PLUGIN / "scripts" / "lib" / "past_reviews.py"), "--core-list",
             str(self.review_path("corelist")), "--base", "HEAD", "--max-files", "1"],
            cwd=self.root, capture_output=True, text=True, env=self.env(), timeout=60)
        self.assertNotIn("src/b.py", res.stdout)
        self.assertFalse(any("pulls/13" in c for c in self.calls()), "上限外のファイルの PR を引いている")

    def lib(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(PLUGIN / "scripts" / "lib" / "past_reviews.py"), "--core-list",
             str(self.review_path("corelist")), *args],
            cwd=self.root, capture_output=True, text=True, env=self.env(), timeout=60)

    def test_reaching_the_pr_cap_stops_reading_older_commits(self):
        """PR の上限に達したら古いコミットの PR を引かない（API 呼び出しの数を頭打ちにする）."""
        self.lib("--base", "HEAD", "--prs-per-file", "1")
        commit_calls = [c for c in self.calls() if "/commits/" in c]
        self.assertEqual(len(commit_calls), 2, "a.py は直近 1 コミット・b.py は 1 コミットだけ引くはず: %r"
                         % commit_calls)

    def test_a_file_without_comments_gets_no_heading(self):
        self.fixtures(pulls_by_subject={"feat: b を足す": [{"number": 13, "merged_at": "x"}],
                                        "feat: a を足す": [{"number": 11, "merged_at": "x"}]},
                      comments={"11": [[comment("src/a.py", "a の指摘")]],
                                "13": [[comment("src/other.py", "別ファイル")]]})
        out = self.fetch().stdout
        self.assertIn("### `src/a.py`", out)
        self.assertNotIn("### `src/b.py`", out)

    def test_a_cap_exactly_met_counts_nothing_left(self):
        """総数が上限ちょうど（4 件）なら「ほか 0 件」を出さない."""
        out = self.lib("--base", "HEAD", "--max-comments", "4").stdout
        self.assertEqual(sum(1 for ln in out.splitlines() if ln.startswith("- [PR #")), 4)
        self.assertNotIn("上限で省いた", out)

    def test_a_body_of_exactly_the_limit_is_not_marked_as_cut(self):
        out = self.lib("--base", "HEAD", "--body-chars", "5").stdout
        self.assertIn("] ページ 1\n", out, "字数ちょうどの本文に … を付けている")

    def test_origin_is_preferred_over_a_stale_local_base(self):
        """review は base のブランチ名を渡す。ローカルの base が古いと、その後に merge された PR を見落とす."""
        env = self._env()
        subprocess.run(["git", "branch", "stale-base", "HEAD~2"], cwd=self.root, check=True, env=env)
        subprocess.run(["git", "update-ref", "refs/remotes/origin/stale-base", "HEAD"], cwd=self.root,
                       check=True, env=env)
        out = self.lib("--base", "stale-base").stdout
        self.assertIn("PR #12", out, "ローカルの古い base で履歴を引いている")

    def test_the_lib_requires_its_inputs(self):
        for args in (["--base", "HEAD"], []):
            with self.subTest(args):
                res = subprocess.run(["python3", str(PLUGIN / "scripts" / "lib" / "past_reviews.py"), *args]
                                     + ([] if args else ["--core-list", "x"]),
                                     cwd=self.root, capture_output=True, text=True, env=self.env(), timeout=60)
                self.assertEqual(res.returncode, 2, res.stderr)

    # ---- --save --------------------------------------------------------------
    def test_save_writes_the_file_and_prints_its_path(self):
        res = self.fetch("--save")
        self.assertEqual(res.returncode, 0, res.stderr)
        path = Path(res.stdout.strip())
        self.assertEqual(path, self.review_path("pastrev"))
        self.assertIn("PR #11", path.read_text(encoding="utf-8"))

    def test_save_with_no_comments_leaves_no_file_and_no_path(self):
        """0 件のファイルを agent に読ませない。前回の残骸も消す（古い過去指摘でレビューしない）."""
        self.assertTrue(Path(self.fetch("--save").stdout.strip()).exists(), "前提: 1 回目は書く")
        self.fixtures(pulls_by_subject={}, comments={})
        res = self.fetch("--save")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout, "")
        self.assertFalse(self.review_path("pastrev").exists(), "前回のファイルが残っている")

    # ---- 黙って飛ばす ----------------------------------------------------------
    def test_a_repo_without_github_is_skipped(self):
        self.fixtures(repo=None, pulls_by_subject={}, comments={})
        res = self.fetch("--save")
        self.assertEqual(res.returncode, 3)
        self.assertIn("skip:", res.stderr)
        self.assertEqual(res.stdout, "")
        self.assertFalse(self.review_path("pastrev").exists())

    def test_a_missing_core_list_is_skipped(self):
        self.review_path("corelist").unlink()
        res = self.fetch()
        self.assertEqual(res.returncode, 3)
        self.assertIn("core の変更ファイルの一覧", res.stderr)

    def test_an_empty_core_list_makes_no_api_call(self):
        self.core_list([])
        res = self.fetch()
        self.assertEqual((res.returncode, res.stdout), (0, ""))
        self.assertEqual(self.calls(), [])

    def test_a_failing_api_is_read_as_no_prs(self):
        """コミットに紐づく PR を引けない（GitHub に無いコミット等）回は落ちずに 0 件にする."""
        self.fixtures(pulls_by_subject={"feat: a を足す": [{"number": 11, "merged_at": "x"}]},
                      comments={})
        res = self.fetch()
        self.assertEqual((res.returncode, res.stdout), (0, ""))

    def test_missing_base_is_an_argument_error(self):
        res = subprocess.run(["bash", str(FETCH)], cwd=self.root, capture_output=True, text=True,
                             env=self.env(), timeout=60)
        self.assertEqual(res.returncode, 2)


class TriageCoreListTest(ScriptTestBase):
    """triage-signals.sh が core の変更ファイルを変更行の多い順に書き出す（fetch-past-reviews の入力）."""

    def test_core_files_are_listed_by_changed_lines(self):
        env = self._env()
        (self.root / "src").mkdir()
        (self.root / "docs").mkdir()
        subprocess.run(["git", "checkout", "-q", "-b", "feat"], cwd=self.root, check=True, env=env)
        (self.root / "src" / "small.py").write_text("a = 1\n", encoding="utf-8")
        (self.root / "src" / "big.py").write_text("".join("b%d = %d\n" % (i, i) for i in range(5)),
                                                  encoding="utf-8")
        (self.root / "docs" / "x.md").write_text("doc\n" * 9, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True, env=env)
        subprocess.run(["git", "commit", "-q", "-m", "work"], cwd=self.root, check=True, env=env)
        res = subprocess.run(["bash", str(PLUGIN / "scripts" / "triage-signals.sh"), "--base", "main"],
                             cwd=self.root, capture_output=True, text=True, env=env, timeout=60)
        if res.returncode != 0 and "base ref" in res.stderr:
            res = subprocess.run(["bash", str(PLUGIN / "scripts" / "triage-signals.sh"), "--base", "master"],
                                 cwd=self.root, capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        proc = subprocess.run(
            ["bash", "-c", '. "$1/scripts/lib/review-paths.sh"; review_paths_init ""; review_path corelist',
             "_", str(PLUGIN)], cwd=self.root, capture_output=True, text=True, env=env, check=True)
        listed = Path(proc.stdout.strip()).read_text(encoding="utf-8").splitlines()
        self.assertEqual(listed, ["src/big.py", "src/small.py"], "doc を含めたか、変更行の順でない")


if __name__ == "__main__":
    unittest.main()
