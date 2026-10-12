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

    def prior(self, cmd: str, stdin: str = "", session: str = "s1", cwd=None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(PRIOR), cmd], cwd=cwd or self.root, input=stdin, capture_output=True,
                              text=True, env=self._env(CLAUDE_CODE_SESSION_ID=session), timeout=60)

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

    def test_wrong_argument_counts_are_usage_errors(self):
        """呼び出し口（prior-fixes.sh）を通らない呼び方でも落ちずに usage を返す."""
        lib = PLUGIN / "scripts" / "lib" / "prior_fixes.py"
        for args in (["match", "p", "b"], ["clear", "p", "b"], ["record", "p", "b"], []):
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
