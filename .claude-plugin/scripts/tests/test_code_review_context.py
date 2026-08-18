#!/usr/bin/env python3
"""`fetch-pr-context.sh` / `measure-tokens.sh` の回帰テスト（GitHub issue #138）.

- `fetch-pr-context.sh` … 取得失敗時に**空・古いコンテキストでレビューに倒れないか**。
  空ファイルは「読める」ため reviewer の「読めなかった場合」ガードをすり抜け、
  「過去指摘なし」と誤判定される。
- `measure-tokens.sh` … 計測値そのものの誤り。**窓（`--since`）と体数の意味が揃っているか**が
  実測で 1 度ずれている（`--since 2099-01-01` で `sub.n=0` なのに `sub_agents=8`）。

`gh` は PATH 先頭の stub に差し替える。**stub は本物の flag 体系に合わせる**
（`gh repo view` に `--repo` は無い、等）— ここを緩めると「stub でだけ通る」経路ができる。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
import os
import shutil
import subprocess
import time
import unittest
from pathlib import Path

from test_code_review_scripts import PLUGIN, ScriptTestBase

FETCH = PLUGIN / "scripts" / "fetch-pr-context.sh"
MEASURE = PLUGIN / "scripts" / "measure-tokens.sh"

# 本物の gh の flag 体系を模した stub。
#   - `gh pr view <N> [-R|--repo O/R] --json <fields>`   … --repo あり
#   - `gh repo view [<repository>] --json <fields> [--jq]`… **--repo は無い**（位置引数）
#   - `gh api <path> [--paginate]`
GH_STUB = r'''#!/usr/bin/env python3
import json, os, sys

args = sys.argv[1:]
fixtures = json.load(open(os.environ["GH_FIXTURES"]))


def die(msg, code=1):
    sys.stderr.write(msg + "\n")
    sys.exit(code)


def take_json_fields(rest):
    if "--json" not in rest:
        die("specify one or more comma-separated fields for --json")
    return rest[rest.index("--json") + 1].split(",")


if not args:
    die("usage: gh <command>", 2)

if args[0] == "pr" and args[1] == "view":
    rest = args[2:]
    pr = rest.pop(0) if rest and not rest[0].startswith("-") else None
    repo = None
    if "--repo" in rest:
        repo = rest[rest.index("--repo") + 1]
    elif "-R" in rest:
        repo = rest[rest.index("-R") + 1]
    if fixtures.get("pr_view_fails"):
        die("could not resolve to a PullRequest")
    if pr != str(fixtures["pr"]):
        die("no pull request found for %r" % pr)
    if fixtures.get("meta_invalid_json") and "body" in " ".join(rest):
        # gh は成功するが中身が JSON でない回（後段の jq が落ちる = 出力途中で失敗する）
        print("{not json")
        sys.exit(0)
    fields = take_json_fields(rest)
    out = {k: v for k, v in fixtures["pr_json"].items() if k in fields}
    for missing in set(fields) - set(out):
        out[missing] = None
    if repo:
        out["_repo"] = repo
    print(json.dumps(out))
elif args[0] == "repo" and args[1] == "view":
    rest = args[2:]
    # 本物の `gh repo view` は --repo を受け付けない（位置引数で渡す）
    for bad in ("--repo", "-R"):
        if bad in rest:
            die("unknown flag: %s" % bad, 1)
    take_json_fields(rest)
    print(fixtures["name_with_owner"])
elif args[0] == "api":
    if fixtures.get("api_fails"):
        die("HTTP 404")
    print(json.dumps(fixtures["line_comments"]))
else:
    die("unknown command: %s" % " ".join(args), 2)
'''

BASE_FIXTURES = {
    "pr": 42,
    "name_with_owner": "acme/widget",
    "pr_json": {
        "number": 42,
        "title": "認証フローの修正",
        "url": "https://github.com/acme/widget/pull/42",
        "author": {"login": "alice"},
        "state": "OPEN",
        "headRefName": "fix/auth",
        "baseRefName": "main",
        "body": "スコープ: ログインのみ",
        "comments": [],
        "reviews": [],
    },
    "line_comments": [],
}


class FetchPrContextTest(ScriptTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.bin = self.root / "tmp" / "bin"
        self.bin.mkdir(parents=True, exist_ok=True)
        stub = self.bin / "gh"
        stub.write_text(GH_STUB, encoding="utf-8")
        stub.chmod(0o755)
        self.fixtures_path = self.root / "tmp" / "fixtures.json"
        self.set_fixtures()

    def set_fixtures(self, **overrides) -> None:
        data = json.loads(json.dumps(BASE_FIXTURES))
        for key, value in overrides.items():
            if key in ("comments", "reviews", "body"):
                data["pr_json"][key] = value
            else:
                data[key] = value
        self.fixtures_path.write_text(json.dumps(data), encoding="utf-8")

    def isolated_bin(self, *names: str) -> Path:
        """指定した名前だけが引ける bin dir を作る（`bash` は常に入れる）.

        **`/usr/bin` や `/bin` を混ぜて「そこには無いはず」に頼ってはいけない。**
        Linux では `/bin` が `/usr/bin` の symlink で、CI には `gh` も `jq` も入っている
        （実測: この前提で書いた 2 件が ubuntu でだけ落ちた）。依存欠落の経路は
        **引けるものを列挙する**側で作る。
        """
        d = self.root / "tmp" / ("bin-" + "-".join(names or ("none",)))
        d.mkdir(parents=True, exist_ok=True)
        for name in ("bash", *names):
            real = shutil.which(name)
            self.assertIsNotNone(real, "%s が見つからない" % name)
            link = d / name
            if not link.exists():
                link.symlink_to(real)
        return d

    def env(self, with_gh: bool = True, with_jq: bool = True) -> dict[str, str]:
        """PATH を組み替える。**依存欠落の経路は PATH を絞って作る**."""
        env = self._env()
        env["GH_FIXTURES"] = str(self.fixtures_path)
        if not with_gh:
            env["PATH"] = str(self.isolated_bin())            # gh も jq も引けない
        elif not with_jq:
            gh_only = self.isolated_bin()                      # bash だけの dir に
            (gh_only / "gh").symlink_to(self.bin / "gh")       # gh stub を足す（jq は無い）
            env["PATH"] = str(gh_only)
        else:
            env["PATH"] = "%s:%s" % (self.bin, env["PATH"])
        return env

    def fetch(self, *args: str, env: dict[str, str] | None = None
              ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(FETCH), *args], cwd=self.root, capture_output=True,
                              text=True, env=env or self.env(), timeout=60)

    # ---- 引数と依存 --------------------------------------------------------
    def test_missing_pr_number_exits_1(self):
        res = self.fetch()
        self.assertEqual(res.returncode, 1)
        self.assertIn("Usage", res.stderr)

    def test_unknown_argument_exits_1(self):
        res = self.fetch("42", "--verbose")
        self.assertEqual(res.returncode, 1)
        self.assertIn("未知の引数", res.stderr)

    def test_repo_flag_without_value_exits_1(self):
        res = self.fetch("42", "--repo")
        self.assertEqual(res.returncode, 1)
        self.assertIn("リポジトリ名", res.stderr)

    def test_missing_gh_exits_1(self):
        res = self.fetch("42", env=self.env(with_gh=False))
        self.assertEqual(res.returncode, 1)
        self.assertIn("gh コマンドが見つかりません", res.stderr)

    def test_missing_jq_exits_1(self):
        res = self.fetch("42", env=self.env(with_jq=False))
        self.assertEqual(res.returncode, 1)
        self.assertIn("jq コマンドが見つかりません", res.stderr)

    # ---- 出力 --------------------------------------------------------------
    def test_renders_every_section(self):
        res = self.fetch("42")
        self.assertEqual(res.returncode, 0, res.stderr)
        for heading in ("## PR コンテキスト", "### PR 情報", "### PR 説明",
                        "### Issue コメント", "### レビューサマリ",
                        "### 行単位レビューコメント"):
            self.assertIn(heading, res.stdout)
        self.assertIn("- #42 認証フローの修正", res.stdout)
        self.assertIn("- 著者: @alice", res.stdout)
        self.assertIn("- Base → Head: main → fix/auth", res.stdout)
        # **本文が出ていること**（reviewer が読む「著者が明示したスコープ」）。
        # 「（空）」に化ける経路があるので、空判定の反対側も同時に固定する
        self.assertIn("スコープ: ログインのみ", res.stdout)
        self.assertNotIn("（空）", res.stdout)

    def test_empty_sections_are_explicit(self):
        """取得できたが空、を「（なし）」で明示する（項目の有無を reviewer が判別できる）."""
        res = self.fetch("42")
        self.assertEqual(res.stdout.count("（なし）"), 3)

    def test_empty_body_is_explicit(self):
        self.set_fixtures(body="")
        res = self.fetch("42")
        self.assertIn("（空）", res.stdout)

    def test_comments_and_reviews_are_flattened_to_one_line_each(self):
        self.set_fixtures(
            comments=[{"author": {"login": "bob"}, "createdAt": "2026-08-01T10:00:00Z",
                       "body": "1 行目\n2 行目"}],
            reviews=[{"author": {"login": "carol"}, "state": "CHANGES_REQUESTED",
                      "submittedAt": "2026-08-02T10:00:00Z", "body": "直して\nほしい"}])
        res = self.fetch("42")
        self.assertIn("- [@bob, 2026-08-01] 1 行目 2 行目", res.stdout)
        self.assertIn("- [@carol, CHANGES_REQUESTED, 2026-08-02] 直して ほしい", res.stdout)

    def test_line_comments_render_replies_indented(self):
        self.set_fixtures(line_comments=[
            {"id": 1, "user": {"login": "bob"}, "path": "src/a.ts", "line": 12,
             "created_at": "2026-08-01T10:00:00Z", "body": "ここ危ない"},
            {"id": 2, "user": {"login": "alice"}, "in_reply_to_id": 1,
             "created_at": "2026-08-01T11:00:00Z", "body": "直した"},
        ])
        res = self.fetch("42")
        self.assertIn("- [#1] [@bob, src/a.ts:12] ここ危ない", res.stdout)
        self.assertIn("  - 返信 [#1 への返信] [@alice] 直した", res.stdout)

    def test_unknown_author_falls_back_instead_of_printing_null(self):
        self.set_fixtures(comments=[{"author": None, "createdAt": "2026-08-01T10:00:00Z",
                                     "body": "退会済みの人"}])
        res = self.fetch("42")
        self.assertIn("@unknown", res.stdout)
        self.assertNotIn("@null", res.stdout)

    def test_repo_flag_targets_another_repository(self):
        """`--repo` 経路は `gh repo view` に渡せない（本物に `--repo` flag が無い）."""
        res = self.fetch("42", "--repo", "acme/widget")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("- #42", res.stdout)

    def test_fetch_failure_exits_nonzero_with_a_labelled_error(self):
        self.set_fixtures(pr_view_fails=True)
        res = self.fetch("42")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("ERROR", res.stderr)

    def test_line_comment_api_failure_exits_nonzero(self):
        self.set_fixtures(api_fails=True)
        res = self.fetch("42")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("行単位 review コメント", res.stderr)

    # ---- --save（成功時のみ確定する）---------------------------------------
    def saved_path(self) -> Path:
        res = self.fetch("42", "--save")
        self.assertEqual(res.returncode, 0, res.stderr)
        return Path(res.stdout.strip())

    def test_save_writes_the_file_and_prints_its_path(self):
        path = self.saved_path()
        self.assertTrue(path.is_file())
        self.assertIn("## PR コンテキスト", path.read_text(encoding="utf-8"))

    def test_save_accepts_the_flag_before_the_pr_number(self):
        res = self.fetch("--save", "42")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(Path(res.stdout.strip()).is_file())

    def test_save_leaves_no_file_when_the_fetch_fails(self):
        """空ファイルは「読める」ので reviewer のガードをすり抜ける."""
        self.set_fixtures(pr_view_fails=True)
        res = self.fetch("42", "--save")
        self.assertEqual(res.returncode, 1)
        self.assertIn("ERROR", res.stderr)
        candidates = list((self.root / "tmp").rglob("review-prctx-*"))
        self.assertEqual(candidates, [], "空ファイルも .tmp も残してはいけない")

    def test_save_removes_a_stale_context_when_the_fetch_fails(self):
        """**成功時のみ mv するガードは空ファイル対策であって stale 対策ではない.**

        前回の PR コンテキストが残ると、reviewer は「読めた」と判断して**古い過去指摘**で
        レビューする。縮退先は誤値ではなく欠測（triage-signals.sh の diff と同じ規約）。
        """
        path = self.saved_path()
        path.write_text("## PR コンテキスト\n（前回の実行結果）\n", encoding="utf-8")
        self.set_fixtures(pr_view_fails=True)
        res = self.fetch("42", "--save")
        self.assertEqual(res.returncode, 1)
        self.assertFalse(path.exists(), "古いコンテキストが残ると「読めた」に化ける")

    def test_save_leaves_no_file_when_the_run_fails_after_output_started(self):
        """**部分出力を「完全なコンテキスト」として確定させない.**

        gh は成功するが後段の jq が落ちる回では、tmp に見出しだけが書かれた状態で
        本体が非 0 終了する。空ファイル判定（`-s`）だけを見ていると**中身のある
        部分出力**が通ってしまうので、成否そのものを見る必要がある。
        """
        self.set_fixtures(meta_invalid_json=True)
        res = self.fetch("42", "--save")
        self.assertEqual(res.returncode, 1)
        self.assertIn("ERROR", res.stderr)
        self.assertEqual(list((self.root / "tmp").rglob("review-prctx-*")), [])

    def test_save_path_is_keyed_by_pr_number(self):
        first = self.saved_path()
        self.set_fixtures(pr=7, pr_json=dict(BASE_FIXTURES["pr_json"], number=7))
        res = self.fetch("7", "--save")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotEqual(first, Path(res.stdout.strip()))


class MeasureTokensTest(ScriptTestBase):
    """transcript から集計する。**偽の `$HOME` に合成 transcript を置く**."""

    def setUp(self) -> None:
        super().setUp()
        self.home = self.root / "home"
        (self.home / ".claude" / "projects").mkdir(parents=True)

    def slug(self, path: Path) -> str:
        return "".join(c if c.isalnum() else "-" for c in str(path))

    def project_dir(self, path: Path | None = None) -> Path:
        d = self.home / ".claude" / "projects" / self.slug(path or self.root)
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def usage_row(ts: str, out: int = 0, cw: int = 0, cr: int = 0, inp: int = 0) -> str:
        return json.dumps({"type": "assistant", "timestamp": ts,
                           "message": {"usage": {"output_tokens": out,
                                                 "cache_creation_input_tokens": cw,
                                                 "cache_read_input_tokens": cr,
                                                 "input_tokens": inp}}})

    def write_session(self, session_id: str, rows: list[str],
                      root: Path | None = None) -> Path:
        path = self.project_dir(root) / ("%s.jsonl" % session_id)
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        return path

    def write_subagent(self, session_id: str, name: str, rows: list[str],
                       root: Path | None = None) -> Path:
        d = self.project_dir(root) / session_id / "subagents"
        d.mkdir(parents=True, exist_ok=True)
        path = d / ("%s.jsonl" % name)
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        return path

    def env(self) -> dict[str, str]:
        return self._env(HOME=str(self.home))

    def measure(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(MEASURE), *args], cwd=str(cwd or self.root),
                              capture_output=True, text=True, env=self.env(), timeout=60)

    def as_json(self, *args: str, cwd: Path | None = None) -> dict:
        res = self.measure("--json", *args, cwd=cwd)
        self.assertEqual(res.returncode, 0, res.stderr)
        return json.loads(res.stdout)

    def intake_row(self, out: str, name: str) -> int:
        """取り込み内訳の表から `<name>` 行の chars を返す（行が無ければ fail）.

        表は `<名前24桁><件数6桁><chars12桁><占有>` の固定幅。名前の部分一致ではなく
        **行の左端が名前で始まること**を要求する（解説文中の同名語に当たらないため）。
        """
        for line in out.splitlines():
            if line.startswith(name) and "%" in line:
                digits = line[24:].replace(",", "").split()
                self.assertGreaterEqual(len(digits), 2, "表の形が変わった: %r" % line)
                return int(digits[1])
        self.fail("取り込み内訳に %r の行が無い:\n%s" % (name, out))

    # ---- 引数 --------------------------------------------------------------
    def test_unknown_argument_exits_2(self):
        res = self.measure("--nope")
        self.assertEqual(res.returncode, 2)
        self.assertIn("unknown arg", res.stderr)

    def test_flag_without_value_reports_the_error(self):
        """`$2` を素で読むと `set -u` の生エラーだけ出て診断が残らない."""
        for flag in ("--session", "--since"):
            with self.subTest(flag=flag):
                res = self.measure(flag)
                self.assertEqual(res.returncode, 2)
                self.assertIn("値が必要", res.stderr)
                self.assertNotIn("unbound variable", res.stderr)

    def test_missing_transcript_exits_1_and_lists_searched_dirs(self):
        # cwd に**最新の**無関係ファイルを置く。候補が空のときガードを外すと
        # `ls -t` が引数なしで cwd を列挙し、その先頭を transcript と誤認する
        decoy = self.root / "decoy.jsonl"
        decoy.write_text("{}\n", encoding="utf-8")
        os.utime(decoy, (time.time() + 60, time.time() + 60))
        res = self.measure()
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("transcript が見つからない", res.stderr)
        self.assertIn(self.slug(self.root), res.stderr)

    def test_explicitly_missing_session_exits_1(self):
        res = self.measure("--session", str(self.root / "nope.jsonl"))
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("transcript が見つからない", res.stderr)

    def test_list_without_any_session_exits_0(self):
        res = self.measure("--list")
        self.assertEqual(res.returncode, 0)
        self.assertIn("セッションが見つからない", res.stderr)

    def test_list_shows_the_candidates(self):
        self.write_session("s1", [self.usage_row("2026-08-17T10:00:00Z", out=1)])
        res = self.measure("--list")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("s1.jsonl", res.stdout)

    # ---- 集計 --------------------------------------------------------------
    def test_sums_main_usage(self):
        self.write_session("s1", [
            self.usage_row("2026-08-17T10:00:00Z", out=10, cw=100, cr=1000, inp=5),
            self.usage_row("2026-08-17T10:01:00Z", out=20, cw=200, cr=2000, inp=6),
        ])
        got = self.as_json()
        self.assertEqual(got["main"], {"n": 2, "output": 30, "cache_write": 300,
                                       "cache_read": 3000, "input": 11})
        self.assertEqual(got["sub"]["n"], 0)
        self.assertEqual(got["first_ts"], "2026-08-17T10:00:00Z")
        self.assertEqual(got["last_ts"], "2026-08-17T10:01:00Z")

    def test_rows_without_usage_are_ignored(self):
        self.write_session("s1", [
            json.dumps({"type": "user", "timestamp": "2026-08-17T10:00:00Z",
                        "message": {"content": "hi"}}),
            self.usage_row("2026-08-17T10:01:00Z", out=7),
        ])
        self.assertEqual(self.as_json()["main"]["n"], 1)

    def test_a_broken_line_does_not_abort_the_scan(self):
        self.write_session("s1", ["{not json", self.usage_row("2026-08-17T10:00:00Z", out=7)])
        self.assertEqual(self.as_json()["main"]["output"], 7)

    def test_subagent_transcripts_are_summed_separately(self):
        """`isSidechain` では分離できない（top-level は全行 false）ので所在で分ける."""
        self.write_session("s1", [self.usage_row("2026-08-17T10:00:00Z", out=10)])
        self.write_subagent("s1", "agent-1", [self.usage_row("2026-08-17T10:00:30Z", out=100)])
        self.write_subagent("s1", "agent-2", [self.usage_row("2026-08-17T10:00:40Z", out=200)])
        got = self.as_json()
        self.assertEqual(got["main"]["output"], 10)
        self.assertEqual(got["sub"]["output"], 300)
        self.assertEqual(got["sub_agents"], 2)
        self.assertEqual(got["sub_files"], 2)

    def test_since_filters_rows(self):
        self.write_session("s1", [
            self.usage_row("2026-08-17T09:00:00Z", out=10),
            self.usage_row("2026-08-17T11:00:00Z", out=20),
        ])
        got = self.as_json("--since", "2026-08-17T10:00:00Z")
        self.assertEqual(got["main"]["output"], 20)
        self.assertEqual(got["main"]["n"], 1)

    def test_sub_agents_counts_only_bodies_inside_the_window(self):
        """**窓と体数の意味を揃える**（`sub.n=0` なのに `sub_agents=8` を出さない）.

        `sub_files` は窓非適用の glob 総数なので、両者の差が「引き当て失敗」の検出になる。
        """
        self.write_session("s1", [self.usage_row("2026-08-17T11:00:00Z", out=1)])
        self.write_subagent("s1", "agent-old", [self.usage_row("2026-08-17T09:00:00Z", out=50)])
        self.write_subagent("s1", "agent-new", [self.usage_row("2026-08-17T11:00:30Z", out=60)])
        got = self.as_json("--since", "2026-08-17T10:00:00Z")
        self.assertEqual(got["sub"]["output"], 60)
        self.assertEqual(got["sub_agents"], 1, "窓内に usage を持つのは 1 体")
        self.assertEqual(got["sub_files"], 2, "glob した本数は窓非適用")

    def test_explicit_session_is_honored(self):
        """**明示指定を最新ファイルで上書きしない**こと.

        指定するのは**古い方**（新しい方を指定すると「上書きされても同じ結果」になり、
        上書きバグを検出できない）。
        """
        older = self.write_session("s1", [self.usage_row("2026-08-17T10:00:00Z", out=1)])
        newer = self.write_session("s2", [self.usage_row("2026-08-17T10:00:00Z", out=99)])
        os.utime(newer, (time.time() + 5, time.time() + 5))
        got = self.as_json("--session", str(older))
        self.assertEqual(got["session"], "s1.jsonl")
        self.assertEqual(got["main"]["output"], 1)

    def test_latest_session_is_picked_when_none_is_given(self):
        self.write_session("s1", [self.usage_row("2026-08-17T10:00:00Z", out=1)])
        newer = self.write_session("s2", [self.usage_row("2026-08-17T10:00:00Z", out=99)])
        os.utime(newer, (time.time() + 5, time.time() + 5))
        self.assertEqual(self.as_json()["session"], "s2.jsonl")

    def test_finds_the_transcript_of_the_main_repository_from_a_worktree(self):
        """review は Step 0 で EnterWorktree するので cwd 側の slug には無い（issue #112）."""
        wt = self.root / "wt"
        subprocess.run(["git", "worktree", "add", "-q", "--detach", str(wt)],
                       cwd=self.root, capture_output=True, env=self.env(), check=True)
        self.write_session("s1", [self.usage_row("2026-08-17T10:00:00Z", out=42)])
        got = self.as_json(cwd=wt)
        self.assertEqual(got["main"]["output"], 42)

    # ---- 表示モード --------------------------------------------------------
    def test_text_mode_warns_when_no_subagent_transcript_exists(self):
        """sub が常に 0 だと削減幅を過大評価する（黙って 0 を返さない）."""
        self.write_session("s1", [self.usage_row("2026-08-17T10:00:00Z", out=10)])
        res = self.measure()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("サブエージェントの transcript が見つからない", res.stdout)

    def test_text_mode_reports_the_subagent_count(self):
        self.write_session("s1", [self.usage_row("2026-08-17T10:00:00Z", out=10)])
        self.write_subagent("s1", "agent-1", [self.usage_row("2026-08-17T10:00:30Z", out=100)])
        res = self.measure()
        self.assertIn("サブエージェント: 1 体", res.stdout)
        self.assertNotIn("見つからない", res.stdout)

    def test_intake_breakdown_splits_tool_results_and_attachments(self):
        """cache_write 単独では分冊の効果を判定できない（GitHub issue #118）."""
        self.write_session("s1", [
            json.dumps({"type": "assistant", "timestamp": "2026-08-17T10:00:00Z",
                        "message": {"content": [{"type": "tool_use", "id": "tu1",
                                                 "name": "Agent"}]}}),
            json.dumps({"type": "user", "timestamp": "2026-08-17T10:00:10Z",
                        "message": {"content": [{"type": "tool_result", "tool_use_id": "tu1",
                                                 "content": "x" * 500}]}}),
            json.dumps({"type": "attachment", "timestamp": "2026-08-17T10:00:20Z",
                        "attachment": {"type": "hook", "stdout": "y" * 100}}),
            self.usage_row("2026-08-17T10:00:30Z", out=10),
        ])
        res = self.measure()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("main への取り込み内訳", res.stdout)
        # **表の行そのものを見る**。`assertIn("Agent", stdout)` は末尾の解説文
        # （「→ Agent 経由は…」）にも当たるので、ツール名が `?` に化けても通ってしまう
        self.assertEqual(self.intake_row(res.stdout, "Agent"), 500)
        self.assertEqual(self.intake_row(res.stdout, "attachment:hook"), 100)

    def test_attachment_without_a_known_body_field_is_not_counted_as_zero(self):
        # 非 ASCII を混ぜる（フォールバック側も `ensure_ascii=False` で数えないと
        # 日本語 1 文字が `\uXXXX` の 6 文字に膨らみ、比率が系統的に狂う）
        att = {"type": "mystery", "unexpected": "未知フィールド" * 4}
        self.write_session("s1", [
            json.dumps({"type": "attachment", "timestamp": "2026-08-17T10:00:00Z",
                        "attachment": att}),
            self.usage_row("2026-08-17T10:00:30Z", out=10),
        ])
        res = self.measure()
        # フォールバックは attachment 全体の JSON 長（**0 に潰さない**）。期待値はテスト側で
        # 独立に組む（スクリプトと同じ式を書き写すと、式ごと壊れても一致してしまう）
        expected = len(json.dumps(att, ensure_ascii=False, separators=(", ", ": ")))
        self.assertEqual(self.intake_row(res.stdout, "attachment:mystery"), expected)

    def test_known_field_attachments_do_not_fall_back_to_the_whole_json(self):
        """既知フィールドがあるときは**その長さ**（全体 JSON 長に化けない）."""
        self.write_session("s1", [
            json.dumps({"type": "attachment", "timestamp": "2026-08-17T10:00:00Z",
                        "attachment": {"type": "hook", "stdout": "y" * 40, "noise": "n" * 500}}),
            self.usage_row("2026-08-17T10:00:30Z", out=10),
        ])
        self.assertEqual(self.intake_row(self.measure().stdout, "attachment:hook"), 40)

    def test_non_ascii_bodies_are_counted_as_characters_not_escapes(self):
        """`ensure_ascii=True` だと日本語 1 文字が `\\uXXXX` の 6 文字に膨らむ.

        取り込み内訳は**経由別の比率**として読む指標なので、日本語の doc / agent 出力が
        系統的に過大計上されると比率そのものが壊れる。
        """
        body = ["日本語のテキスト"]          # 8 文字 → JSON 表現は `["日本語のテキスト"]` = 11 文字
        self.write_session("s1", [
            json.dumps({"type": "attachment", "timestamp": "2026-08-17T10:00:00Z",
                        "attachment": {"type": "ja", "addedLines": body}}),
            self.usage_row("2026-08-17T10:00:30Z", out=10),
        ])
        expected = len(json.dumps(body, ensure_ascii=False))
        self.assertEqual(self.intake_row(self.measure().stdout, "attachment:ja"), expected)

    def test_non_ascii_tool_results_are_counted_as_characters(self):
        text = "指摘は 3 件です" * 5
        self.write_session("s1", [
            json.dumps({"type": "assistant", "timestamp": "2026-08-17T10:00:00Z",
                        "message": {"content": [{"type": "tool_use", "id": "tu1",
                                                 "name": "Agent"}]}}),
            json.dumps({"type": "user", "timestamp": "2026-08-17T10:00:10Z",
                        "message": {"content": [{"type": "tool_result", "tool_use_id": "tu1",
                                                 "content": [{"type": "text", "text": text}]}]}}),
            self.usage_row("2026-08-17T10:00:30Z", out=10),
        ])
        expected = len(json.dumps([{"type": "text", "text": text}], ensure_ascii=False))
        self.assertEqual(self.intake_row(self.measure().stdout, "Agent"), expected)

    def test_tool_results_of_unknown_tool_use_are_labelled_unknown(self):
        """`--since` の境界で tool_use が窓外・tool_result が窓内になる回（欠測として出す）."""
        self.write_session("s1", [
            json.dumps({"type": "user", "timestamp": "2026-08-17T10:00:10Z",
                        "message": {"content": [{"type": "tool_result", "tool_use_id": "gone",
                                                 "content": "x" * 20}]}}),
            self.usage_row("2026-08-17T10:00:30Z", out=10),
        ])
        self.assertEqual(self.intake_row(self.measure().stdout, "?"), 20)


class DispatchPatternTest(MeasureTokensTest):
    """agent の**起動間隔**から一括発行が守られたかを判定する（GitHub issue #142）.

    `duration_fleet_min` は「9 体を逐次で回した 89 分」と「1 体が 89 分かかった」を
    区別できない。実測ではこの区別が最大の改善余地だった（16 回中 13 回が逐次発行で、
    累計 431 分＝7.2 時間を失っていた）。**規約はあるのに守られない**ので、
    守られたかどうかを事後に観測できるようにする。
    """

    def with_agents(self, offsets_sec: list[int], session: str = "s1") -> dict:
        """`offsets_sec` の秒数だけずらして agent を起動した transcript を作る."""
        base = datetime(2026, 8, 18, 1, 0, 0)
        self.write_session(session, [self.usage_row(base.isoformat() + "Z", out=10)])
        for i, off in enumerate(offsets_sec):
            ts = (base + timedelta(seconds=off)).isoformat() + "Z"
            self.write_subagent(session, "agent-%d" % i, [self.usage_row(ts, out=5)])
        return self.as_json()["dispatch"]

    def test_same_message_dispatch_is_batched(self):
        d = self.with_agents([1, 3, 8])
        self.assertEqual(d["verdict"], "batched", d)
        self.assertEqual(d["agents"], 3)

    def test_one_by_one_dispatch_is_serial(self):
        """1 体ずつ別メッセージで発行した回（実測の 13/16 がこれ）."""
        d = self.with_agents([0, 400, 900])
        self.assertEqual(d["verdict"], "serial", d)
        self.assertEqual(d["max_gap_sec"], 500)
        self.assertEqual(d["span_sec"], 900)

    def test_split_dispatch_is_mixed(self):
        """間隔は詰まっているが総幅が広い＝何回かに分けて発行している."""
        d = self.with_agents([0, 60, 119, 175])
        self.assertEqual(d["verdict"], "mixed", d)

    def test_exactly_two_agents_are_judged(self):
        """**2 体ちょうど**が判定の下限（`>= 2`）。ここを外すと最小の fleet が判定不能に落ちる."""
        self.assertEqual(self.with_agents([0, 4])["verdict"], "batched")
        self.setUp()
        d = self.with_agents([0, 600])
        self.assertEqual(d["verdict"], "serial", d)
        self.assertEqual(d["agents"], 2)

    def test_text_mode_prints_the_pattern_and_hints_only_when_broken(self):
        """人間向け出力: 破られた回だけ是正先を出す（守れた回は行だけで黙る）."""
        self.with_agents([0, 600])
        broken = self.measure().stdout
        self.assertIn("逐次発行", broken)
        self.assertIn("最長 1 体ぶん", broken, "是正先を出していない")
        self.setUp()
        self.with_agents([0, 4])
        ok = self.measure().stdout
        self.assertIn("一括発行", ok)
        self.assertNotIn("最長 1 体ぶん", ok, "守れた回にまで是正を出している")

    def test_a_single_agent_cannot_be_judged(self):
        """1 体では wave の概念が立たない。**batched に倒さない**."""
        self.assertEqual(self.with_agents([0])["verdict"], "single")

    def test_no_agent_is_unknown_not_batched(self):
        base = datetime(2026, 8, 18, 1, 0, 0).isoformat() + "Z"
        self.write_session("s1", [self.usage_row(base, out=10)])
        d = self.as_json()["dispatch"]
        self.assertEqual(d["verdict"], "unknown", d)
        self.assertEqual(d["agents"], 0)

    def test_agents_outside_the_window_are_not_counted(self):
        """窓（`--since`）と体数の意味を揃える（既存の `sub_agents` と同じ契約）."""
        base = datetime(2026, 8, 18, 1, 0, 0)
        self.write_session("s1", [self.usage_row(base.isoformat() + "Z", out=10)])
        self.write_subagent("s1", "agent-old",
                            [self.usage_row((base - timedelta(hours=2)).isoformat() + "Z", out=5)])
        self.write_subagent("s1", "agent-new",
                            [self.usage_row(base.isoformat() + "Z", out=5)])
        d = json.loads(self.measure("--json", "--since",
                                    base.isoformat()).stdout)["dispatch"]
        self.assertEqual(d["agents"], 1, "窓の外で起動した agent を数えている")


if __name__ == "__main__":
    unittest.main()
