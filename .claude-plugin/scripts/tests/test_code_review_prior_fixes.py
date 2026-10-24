#!/usr/bin/env python3
"""前回の指摘への修正の記録と照合（`code-review/scripts/prior-fixes.sh`）の回帰テスト（GitHub issue #298）.

self-review を「前回以降」に絞ると、前回の指摘を受けて入れた修正が検証済みに入り、どのレビューにも
見られなかった。Step 7 で修正を選んだ指摘を記録し、次の self-review の Step 1 が今回の diff と照合する。
記録はセッションをまたいで読むので作業ツリーで鍵を作り、publish が消す。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from test_code_review_scripts import BASE_PAYLOAD, PLUGIN, ScriptTestBase

PRIOR = PLUGIN / "scripts" / "prior-fixes.sh"
TRIAGE = PLUGIN / "scripts" / "triage-signals.sh"


class PriorFixesFixture(ScriptTestBase):
    """土台だけ（テストを持たない）。テストを持つクラスを継承すると、そのテストが子の名前でもう一度走る."""

    def _env(self, **extra: str) -> dict[str, str]:
        return super()._env(**{"CLAUDE_CODE_SESSION_ID": "s1", **extra})

    def write(self, rel: str, body: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, env=self._env())

    def prior(self, cmd: str, stdin: str = "", session: str = "s1", cwd=None,
              args: tuple = ()) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(PRIOR), cmd, *args], cwd=cwd or self.root, input=stdin,
                              capture_output=True, text=True, env=self._env(CLAUDE_CODE_SESSION_ID=session),
                              timeout=60)

    def record_path(self) -> str:
        return subprocess.run(
            ["bash", "-c", '. "$1/scripts/lib/review-paths.sh"; review_paths_init ""; review_path priorfix',
             "_", str(PLUGIN)], cwd=self.root, capture_output=True, text=True, env=self._env()).stdout.strip()

    def record(self, fixes: list, session: str = "s1") -> subprocess.CompletedProcess[str]:
        return self.prior("record", json.dumps(fixes, ensure_ascii=False), session)

    def triage(self, session: str = "s1") -> None:
        self.git("add", "-A")
        r = subprocess.run(["bash", str(TRIAGE), "--base", "HEAD"], cwd=self.root, capture_output=True,
                           text=True, env=self._env(CLAUDE_CODE_SESSION_ID=session), timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

    def match(self, session: str = "s1") -> str:
        self.triage(session)
        r = self.prior("match", session=session)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def extra_file(self, body) -> str:
        """`--prior-findings` のファイル（作業ツリーの外。diff に入らないように）."""
        p = Path(self._cfg_tmp.name) / "prior-findings.json"
        p.write_text(body if isinstance(body, str) else json.dumps(body, ensure_ascii=False), encoding="utf-8")
        return str(p)

    def match_extra(self, body, session: str = "s1") -> subprocess.CompletedProcess[str]:
        self.triage(session)
        return self.prior("match", session=session, args=("--extra", self.extra_file(body)))

    FIX_A = {"file": "src/a.ts", "line": 3, "focus": "bug-detection", "title": "種類 X のときだけ下げる"}
    FIX_B = {"file": "src/other.ts", "line": 9, "focus": "error-handling", "title": "握りつぶし"}


class PriorFixesTest(PriorFixesFixture):
    def test_a_recorded_fix_in_the_diff_is_listed(self):
        self.assertEqual(self.record([self.FIX_A, self.FIX_B]).stdout.strip(), "recorded=2")
        self.write("src/a.ts", "fixed\n")
        self.assertEqual(self.match().splitlines(),
                         ["## prior-fixes", "recorded=2 in_diff=1",
                          "src/a.ts:3\tbug-detection\t種類 X のときだけ下げる"])

    def test_silent_without_a_record(self):
        """記録が無い回は stdout にも stderr にも何も出さない（毎回の self-review で鳴らない）."""
        self.write("src/a.ts", "x\n")
        self.triage()
        r = self.prior("match")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        r = self.prior("clear")
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_silent_when_no_recorded_file_is_in_the_diff(self):
        self.record([self.FIX_B])
        self.write("src/a.ts", "x\n")
        self.assertEqual(self.match(), "")

    def test_a_record_from_another_branch_is_not_listed(self):
        self.record([self.FIX_A])
        self.git("checkout", "-q", "-b", "feat/other")
        self.write("src/a.ts", "x\n")
        self.assertEqual(self.match(), "")

    def test_the_record_outlives_the_session(self):
        """次のセッションの self-review が読む（記録の鍵はセッション id ではなく作業ツリー）."""
        self.record([self.FIX_A], session="s1")
        self.write("src/a.ts", "x\n")
        self.assertIn("src/a.ts:3\tbug-detection", self.match(session="s2"))

    def test_clear_removes_only_what_this_diff_covered(self):
        """消すのは今回の diff に入った分（reviewer に渡した分）だけ。入らなかった分は次の回へ残す."""
        self.record([self.FIX_A, self.FIX_B])
        self.write("src/a.ts", "x\n")
        self.triage()
        self.assertEqual(self.prior("clear").returncode, 0)
        self.write("src/other.ts", "y\n")
        self.assertEqual(self.match().splitlines()[1:],
                         ["recorded=1 in_diff=1", "src/other.ts:9\terror-handling\t握りつぶし"])

    def test_clear_removes_the_record_when_everything_was_covered(self):
        self.record([self.FIX_A])
        self.write("src/a.ts", "x\n")
        self.triage()
        self.prior("clear")
        self.assertFalse(__import__("os").path.exists(self.record_path()))

    def test_clear_without_a_diff_keeps_the_record(self):
        """照合できなかった回（diff が無い）は、どの分も reviewer に渡っていないので消さない."""
        self.record([self.FIX_A])
        self.prior("clear")
        self.write("src/a.ts", "x\n")
        self.assertIn("## prior-fixes", self.match())

    def test_clear_keeps_the_record_of_another_branch(self):
        """別ブランチの記録は、そのブランチへ戻ったときの self-review が読む."""
        self.record([self.FIX_A])
        self.git("checkout", "-q", "-b", "feat/other")
        self.write("src/a.ts", "x\n")
        self.triage()
        self.prior("clear")
        self.git("checkout", "-q", "-")
        self.assertIn("## prior-fixes", self.match())

    def test_recording_on_another_branch_keeps_this_branch(self):
        """記録はブランチ別に持つ。別ブランチで record しても、元のブランチの分は上書きされない."""
        self.record([self.FIX_A])
        self.git("checkout", "-q", "-b", "feat/other")
        self.record([self.FIX_B])
        self.write("src/other.ts", "y\n")
        self.assertIn("src/other.ts:9", self.match())
        self.git("checkout", "-q", "-")
        self.write("src/a.ts", "x\n")
        out = self.match()
        self.assertIn("src/a.ts:3", out)
        self.assertNotIn("src/other.ts", out)

    def test_an_empty_record_drops_only_this_branch(self):
        """修正しなかった回は、このブランチの前回の分を残さない（他のブランチの分は残す）."""
        self.record([self.FIX_A])
        self.git("checkout", "-q", "-b", "feat/other")
        self.record([self.FIX_B])
        self.assertEqual(self.record([]).stdout.strip(), "recorded=0")
        self.write("src/other.ts", "y\n")
        self.assertEqual(self.match(), "")
        self.git("checkout", "-q", "-")
        self.write("src/a.ts", "x\n")
        self.assertIn("src/a.ts:3", self.match())

    def test_an_empty_record_on_the_only_branch_removes_the_file(self):
        self.record([self.FIX_A])
        self.record([])
        self.assertFalse(__import__("os").path.exists(self.record_path()))

    def test_a_schema_1_record_is_read_as_its_branch(self):
        """1 ブランチ分だけを持っていた形（schema 1）の記録も、そのブランチの分として読む."""
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=self.root, capture_output=True,
                                text=True, env=self._env()).stdout.strip()
        self.record([self.FIX_B])
        with open(self.record_path(), "w", encoding="utf-8") as f:
            json.dump({"schema": 1, "branch": branch, "recorded_at": "x", "fixes": [self.FIX_A]}, f)
        self.write("src/a.ts", "x\n")
        self.assertIn("src/a.ts:3", self.match())

    def test_invalid_input_is_rejected_and_keeps_the_record(self):
        self.record([self.FIX_A])
        for bad in ("not json", json.dumps({"file": "src/a.ts"})):
            with self.subTest(bad=bad):
                r = self.prior("record", bad)
                self.assertEqual(r.returncode, 2)
                self.assertIn("FATAL", r.stderr)
        self.write("src/a.ts", "x\n")
        self.assertIn("src/a.ts:3", self.match())

    def test_entries_are_cleaned_for_one_line_output(self):
        """改行・タブを潰し、bool の行番号・ファイルの無い項目・repo の外の絶対パスを弾く."""
        self.record([{"file": str(self.root / "src" / "a.ts"), "line": True, "focus": "bug detection",
                      "title": "一行目\n二行目\tタブ"},
                     {"line": 1, "focus": "x", "title": "file が無い"},
                     {"file": "/elsewhere/z.ts", "line": 1, "focus": "x", "title": "repo の外"},
                     {"file": "./src/b.ts", "line": 0, "focus": "", "title": 5},
                     "辞書でない項目",
                     {"file": "src/c.ts", "line": 1, "focus": "x", "title": "1 行目は有効"}])
        for f in ("src/a.ts", "src/b.ts", "src/c.ts"):
            self.write(f, "x\n")
        self.assertEqual(self.match().splitlines()[1:],
                         ["recorded=3 in_diff=3",
                          "src/a.ts:?\tbugdetection\t一行目 二行目 タブ",
                          "src/b.ts:?\t?\t",
                          "src/c.ts:1\tx\t1 行目は有効"])

    def test_a_relative_path_is_taken_from_the_repo_root_wherever_it_runs(self):
        """相対パスは repo のルート相対として記録する（サブディレクトリから呼んでも直さない）."""
        (self.root / "sub").mkdir()
        self.prior("record", json.dumps([self.FIX_A]), cwd=self.root / "sub")
        self.write("src/a.ts", "x\n")
        self.assertIn("src/a.ts:3\tbug-detection", self.match())

    def test_a_record_of_another_schema_is_not_read(self):
        """形の違う記録（版が違う・辞書でない）は読まずに WARN を出す."""
        for body in ({"schema": 3, "branches": {}}, {"schema": 2, "branches": {"x": {"fixes": "x"}, "y": {"fixes": []}}},
                     {"schema": 2, "branch": "x", "fixes": [self.FIX_A]}, [self.FIX_A]):
            with self.subTest(body=type(body).__name__):
                self.record([self.FIX_A])
                with open(self.record_path(), "w", encoding="utf-8") as f:
                    json.dump(body, f)
                self.write("src/a.ts", "x\n")
                self.triage()
                r = self.prior("match")
                self.assertEqual((r.returncode, r.stdout), (0, ""))
                self.assertIn("WARN", r.stderr)

    def test_paths_are_taken_from_the_file_header_lines(self):
        """` b/` を含むパス・引用符で囲まれるパス・削除したファイルも照合する（`diff --git` 行から取らない）."""
        self.write("src/a b/c.ts", "keep\n")
        self.write("src/gone.ts", "keep\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        self.record([{"file": "src/a b/c.ts", "line": 1, "focus": "x", "title": "空白と b/"},
                     {"file": "src/q\"uote.ts", "line": 1, "focus": "x", "title": "引用符"},
                     {"file": "src/gone.ts", "line": 1, "focus": "x", "title": "削除"}])
        self.write("src/a b/c.ts", "changed\n")
        self.write("src/q\"uote.ts", "new\n")
        (self.root / "src" / "gone.ts").unlink()
        out = self.match()
        self.assertIn("recorded=3 in_diff=3", out)
        self.assertIn("src/a b/c.ts:1", out)
        self.assertIn('src/q"uote.ts:1', out)
        self.assertIn("src/gone.ts:1", out)

    def test_detached_head_does_nothing(self):
        """detached HEAD ではブランチ名が常に "HEAD" になるので、記録も照合もしない."""
        self.git("checkout", "-q", "--detach")
        r = self.record([self.FIX_A])
        self.assertIn("recorded=0", r.stdout)
        self.assertFalse(__import__("os").path.exists(self.record_path()))
        self.git("checkout", "-q", "-")
        self.record([self.FIX_A])
        self.git("checkout", "-q", "--detach")
        self.write("src/a.ts", "x\n")
        self.assertEqual(self.match(), "")
        self.prior("clear")
        self.assertTrue(__import__("os").path.exists(self.record_path()), "detached HEAD の clear が記録を消した")

    def test_a_branch_without_commits_is_treated_like_detached_head(self):
        """rev-parse に失敗した回に空のブランチ名で記録すると、match が読まない記録が残る."""
        self.git("checkout", "-q", "--orphan", "fresh")
        r = self.record([self.FIX_A])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("recorded=0", r.stdout)
        self.assertFalse(__import__("os").path.exists(self.record_path()))

    def test_an_unwritable_record_warns_and_exits_1(self):
        """記録を書けない回は traceback ではなく WARN と exit 1（終了コードの約束どおり）.

        一時ディレクトリの親を通常ファイルにして作れなくする（chmod は root で効かないので使わない）.
        """
        blocker = self.root / "not-a-dir"
        blocker.write_text("x", encoding="utf-8")
        env = self._env(TMPDIR=str(blocker / "sub"))
        r = subprocess.run(["bash", str(PRIOR), "record"], cwd=self.root, input=json.dumps([self.FIX_A]),
                           capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("WARN", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_wrong_argument_counts_are_usage_errors(self):
        """呼び出し口（prior-fixes.sh）を通らない呼び方でも落ちずに usage を返す."""
        lib = PLUGIN / "scripts" / "lib" / "prior_fixes.py"
        for args in (["match", "p", "b"], ["match", "p", "b", "d", "e"], ["clear", "p", "b"], ["record", "p", "b"],
                     ["check", "p"], []):
            with self.subTest(args=args):
                r = subprocess.run(["python3", str(lib), *args], capture_output=True, text=True, timeout=30)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("usage", r.stderr)

    def test_a_broken_record_warns_and_continues(self):
        self.record([self.FIX_A])
        path = self.record_path()
        with open(path, "w", encoding="utf-8") as f:
            f.write("{broken")
        self.write("src/a.ts", "x\n")
        self.triage()
        r = self.prior("match")
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertIn("WARN", r.stderr)
        self.prior("clear")
        self.assertFalse(__import__("os").path.exists(path), "壊れた記録が clear で消えていない")

    def test_an_unknown_command_is_an_error(self):
        self.assertEqual(self.prior("bogus").returncode, 2)


class PriorFindingsExtraTest(PriorFixesFixture):
    """self-review の `--prior-findings` の分（`match --extra`）を記録分と合わせて出す（GitHub issue #313）."""

    def test_extra_is_listed_with_the_record(self):
        self.record([self.FIX_B])
        self.write("src/a.ts", "x\n")
        self.write("src/other.ts", "y\n")
        r = self.match_extra([self.FIX_A])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(),
                         ["## prior-fixes", "recorded=1 extra=1 in_diff=2",
                          "src/other.ts:9\terror-handling\t握りつぶし",
                          "src/a.ts:3\tbug-detection\t種類 X のときだけ下げる"])

    def test_the_same_file_line_focus_is_one_line(self):
        """記録分と同じ file:line:focus は記録分の 1 行だけにする（観点が違えば別の行）."""
        self.record([self.FIX_A])
        self.write("src/a.ts", "x\n")
        r = self.match_extra([{**self.FIX_A, "title": "別の要旨"}, {**self.FIX_A, "focus": "security"},
                              {**self.FIX_A, "focus": "security"}])
        self.assertEqual(r.stdout.splitlines(),
                         ["## prior-fixes", "recorded=1 extra=3 in_diff=2",
                          "src/a.ts:3\tbug-detection\t種類 X のときだけ下げる",
                          "src/a.ts:3\tsecurity\t種類 X のときだけ下げる"])

    def test_extra_outside_the_diff_is_still_listed(self):
        """修正が base の状態へ戻したファイルは diff 全体から外れる。そのファイルの対象こそ確かめる（#313）.

        記録分は diff で絞る（別の作業で入れた記録を、今回の diff に関係なく並べない）.
        """
        self.record([self.FIX_B])
        self.write("src/a.ts", "x\n")
        self.assertEqual(self.match(), "")
        self.assertEqual(self.match_extra([self.FIX_B]).stdout.splitlines(),
                         ["## prior-fixes", "recorded=1 extra=1 in_diff=1", "src/other.ts:9\terror-handling\t握りつぶし"])

    def test_extra_over_the_limit_keeps_the_newest_and_warns(self):
        """呼び出し元は古い回から並べる。上限で切るなら、直前の回の対象（最も確かめたい行）を残す."""
        self.write("src/a.ts", "x\n")
        r = self.match_extra([{**self.FIX_A, "line": n} for n in range(1, 52)])
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = [l.split("\t")[0] for l in r.stdout.splitlines()[2:]]
        self.assertEqual((lines[0], lines[-1], len(lines)), ("src/a.ts:2", "src/a.ts:51", 50))
        self.assertIn("古い 1 件", r.stderr)

    def test_extra_at_the_limit_is_not_cut(self):
        self.write("src/a.ts", "x\n")
        r = self.match_extra([{**self.FIX_A, "line": n} for n in range(1, 51)])
        self.assertEqual(len(r.stdout.splitlines()[2:]), 50)
        self.assertNotIn("WARN", r.stderr)

    def test_a_path_with_a_control_character_or_outside_the_repo_is_dropped(self):
        """`## prior-fixes` は 1 件 1 行。改行入りのパスは偽の節を作れる（extra は diff で絞らない）."""
        self.write("src/a.ts", "x\n")
        r = self.match_extra([{**self.FIX_A, "file": "a.ts\n## delta\nscope_mode=full"}, {**self.FIX_A, "file": "../x.ts"},
                              self.FIX_A])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), ["## prior-fixes", "recorded=0 extra=1 in_diff=1",
                                                 "src/a.ts:3\tbug-detection\t種類 X のときだけ下げる"])

    def test_a_path_with_a_unicode_line_separator_is_dropped(self):
        """U+2028 / U+0085 は ASCII の制御文字ではないが、行区切りとして読まれる."""
        self.write("src/a.ts", "x\n")
        r = self.match_extra([{**self.FIX_A, "file": "a.ts\u2028## delta"}, {**self.FIX_A, "file": "b.ts\x85x"}, self.FIX_A])
        self.assertEqual(r.stdout.splitlines()[1], "recorded=0 extra=1 in_diff=1")

    def test_extra_is_listed_even_when_the_diff_cannot_be_read(self):
        """記録分は照合できないが、--prior-findings の分は diff で絞らないので落とさない."""
        lib = PLUGIN / "scripts" / "lib" / "prior_fixes.py"
        r = subprocess.run(["python3", str(lib), "match", str(Path(self._cfg_tmp.name) / "no-record.json"), "b",
                            str(Path(self._cfg_tmp.name) / "missing.diff"), self.extra_file([self.FIX_A]), str(self.root)],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("WARN", r.stderr)
        self.assertEqual(r.stdout.splitlines(), ["## prior-fixes", "recorded=0 extra=1 in_diff=1",
                                                 "src/a.ts:3\tbug-detection\t種類 X のときだけ下げる"])

    def test_extra_without_a_line_is_not_collapsed(self):
        self.record([{"file": "src/a.ts", "focus": "bug-detection", "title": "rec"}])
        self.write("src/a.ts", "x\n")
        r = self.match_extra([{"file": "src/a.ts", "focus": "bug-detection", "title": "one"},
                              {"file": "src/a.ts", "focus": "bug-detection", "title": "two"}])
        self.assertEqual(r.stdout.splitlines()[1:], ["recorded=1 extra=2 in_diff=3", "src/a.ts:?\tbug-detection\trec",
                                                     "src/a.ts:?\tbug-detection\tone", "src/a.ts:?\tbug-detection\ttwo"])

    def test_records_with_the_same_key_are_not_collapsed(self):
        """重複を畳むのは `--prior-findings` の分だけ。記録分どうしを畳むと、行の無い 2 件が 1 件に潰れる."""
        two = [{"file": "src/a.ts", "focus": "bug-detection", "title": "one"},
               {"file": "src/a.ts", "focus": "bug-detection", "title": "two"}]
        self.record(two)
        self.write("src/a.ts", "x\n")
        self.assertEqual(self.match().splitlines()[1:],
                         ["recorded=2 in_diff=2", "src/a.ts:?\tbug-detection\tone", "src/a.ts:?\tbug-detection\ttwo"])

    def test_extra_is_listed_on_detached_head(self):
        """detached HEAD では記録を使わないが、`--extra` の分は記録に頼らないので出す."""
        self.record([self.FIX_B])
        self.git("checkout", "-q", "--detach")
        self.write("src/a.ts", "x\n")
        self.write("src/other.ts", "y\n")
        self.assertEqual(self.match(), "")
        r = self.match_extra([self.FIX_A])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(),
                         ["## prior-fixes", "recorded=0 extra=1 in_diff=1",
                          "src/a.ts:3\tbug-detection\t種類 X のときだけ下げる"])

    def test_broken_extra_warns_and_lists_only_the_record(self):
        self.record([self.FIX_A])
        self.write("src/a.ts", "x\n")
        r = self.match_extra("{broken")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("WARN", r.stderr)
        self.assertEqual(r.stdout.splitlines()[1:],
                         ["recorded=1 extra=0 in_diff=1", "src/a.ts:3\tbug-detection\t種類 X のときだけ下げる"])

    def test_extra_is_neither_recorded_nor_cleared(self):
        self.write("src/a.ts", "x\n")
        self.assertIn("src/a.ts:3", self.match_extra([self.FIX_A]).stdout)
        self.assertFalse(__import__("os").path.exists(self.record_path()), "--extra の分が記録に書かれた")

    def test_extra_without_a_path_is_a_usage_error(self):
        r = self.prior("match", args=("--extra",))
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage", r.stderr)

    def test_unexpected_match_arguments_are_usage_errors(self):
        """黙って捨てると、前回の対象が reviewer に届かないまま delta だけを見るレビューになる."""
        path = self.extra_file([self.FIX_A])
        for args in (("--extra=" + path,), ("--extra " + path,), ("--extra", path, "x"), ("--extra", ""), ("x",)):
            with self.subTest(args=args):
                r = self.prior("match", args=args)
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertIn("usage", r.stderr)

    def test_check_tells_whether_the_file_is_usable(self):
        """`check` は triage-signals.sh が `--since` を効かせるかを決める（使えなければ exit 2）."""
        lib = PLUGIN / "scripts" / "lib" / "prior_fixes.py"
        cases = [([self.FIX_A], 0), ([], 0), ([self.FIX_A, "辞書でない"], 0), ("not json", 2),
                 ({"file": "src/a.ts"}, 2), ([{"line": 1}], 2), (None, 2)]
        for body, want in cases:
            with self.subTest(body=body):
                path = str(Path(self._cfg_tmp.name) / "missing.json") if body is None else self.extra_file(body)
                r = subprocess.run(["python3", str(lib), "check", path, str(self.root)], capture_output=True,
                                   text=True, timeout=30)
                self.assertEqual(r.returncode, want, r.stderr)
                self.assertNotIn("Traceback", r.stderr)


class PriorFixesPublishTest(PriorFixesFixture):
    """self-review の publish が、この回が照合した分を記録から消す（次の回へ持ち越さない）."""

    def publish(self, plugin: str) -> subprocess.CompletedProcess[str]:
        r = subprocess.run(["bash", str(PLUGIN / "scripts" / "publish-review-event.sh"), "--plugin", plugin,
                            "--payload", json.dumps(BASE_PAYLOAD, ensure_ascii=False)],
                           cwd=self.root, capture_output=True, text=True, env=self._env(), timeout=120)
        self.assertNotIn("Traceback", r.stderr)
        return r

    def test_self_review_publish_clears_what_it_covered(self):
        self.record([self.FIX_A])
        self.write("src/a.ts", "x\n")
        self.triage()
        r = self.publish("code-review:self-review")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.match(), "")

    def test_review_publish_keeps_the_record(self):
        """PR のレビュー（review）は記録を照合しないので、消さない."""
        self.record([self.FIX_A])
        self.write("src/a.ts", "x\n")
        self.triage()
        self.publish("code-review:review")
        self.assertIn("## prior-fixes", self.match())


if __name__ == "__main__":
    unittest.main()
