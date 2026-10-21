#!/usr/bin/env python3
"""dev-workflow の `pick-screenshot-dir.sh`（pr-creator Step 4.5 が添付する撮影の選び方）の CLI テスト.

**何を守るか**: `.claude/screenshots/` はチェックアウトに 1 つでブランチを切り替えても残るので、最新の
撮影をそのまま添付すると、前に別のブランチで撮った画面が PR に載る（public repo なら誰でも見られる）。
**外す側**（切り替え前の撮影・切り替えと同じ秒・HEAD の reflog が無い回）を厚く書き、通す側
（切り替えた後の撮影・同じブランチへの checkout し直し・worktree の作成後）と対にする。

reflog の時刻は GIT_COMMITTER_DATE で、ディレクトリの mtime は os.utime で決める（実時間に頼らない）。
pr-creator / ui-verify / ADR の文言がこの判定を指していることも見る（最新をそのまま使う旧い書き方に戻さない）。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from git_env import scrub

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "dev-workflow" / "scripts" / "pick-screenshot-dir.sh"
PR_CREATOR = REPO / "dev-workflow" / "skills" / "pr-creator" / "SKILL.md"
UI_VERIFY = REPO / "dev-workflow" / "skills" / "ui-verify" / "SKILL.md"
ADR = REPO / ".claude" / "adr" / "20261020221214-ui-verify-browser-by-screenshot-need.md"

T0 = 1_000_000_000
KEYS = {"SCREENSHOT_DIR", "SINCE", "SINCE_SOURCE", "SKIPPED", "REASON"}


def parse(stdout: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in stdout.splitlines() if "=" in line)


def section(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]


class PickBase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        # 利用者の global 設定で reflog が切られていても、このリポジトリでは書く
        self.git("config", "core.logAllRefUpdates", "true")
        self.git("commit", "-q", "--allow-empty", "-m", "init", at=T0)

    def git(self, *args: str, at: int | None = None, cwd: Path | None = None) -> None:
        env = scrub()
        if at is not None:
            env.update(GIT_COMMITTER_DATE=f"@{at} +0000", GIT_AUTHOR_DATE=f"@{at} +0000")
        r = subprocess.run(["git", *args], cwd=str(cwd or self.repo), capture_output=True,
                           text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)

    def shot(self, name: str, mtime: int, top: Path | None = None) -> Path:
        d = (top or self.repo) / ".claude" / "screenshots" / name
        d.mkdir(parents=True)
        (d / "desktop.png").write_bytes(b"png")
        os.utime(d, (mtime, mtime))            # 中身を書いた後に揃える（書くと dir の mtime が動く）
        return d

    def pick(self, cwd: Path | None = None, *args: str) -> dict[str, str]:
        r = subprocess.run(["bash", str(SCRIPT), *args], cwd=str(cwd or self.repo),
                           capture_output=True, text=True, env=scrub())
        self.assertEqual(r.returncode, 0, r.stderr)
        out = parse(r.stdout)
        self.assertEqual(set(out), KEYS)
        return out


class SinceTest(PickBase):
    def test_shots_from_the_previous_branch_are_skipped(self):
        """A で撮ったものを、後で切り替えた B の PR に添付しない（最新がそれしか無くても）."""
        self.git("checkout", "-q", "-b", "A", at=T0 + 100)
        self.shot("snap-a", T0 + 200)
        self.git("checkout", "-q", "-b", "B", at=T0 + 300)
        out = self.pick()
        self.assertEqual((out["SCREENSHOT_DIR"], out["SINCE"], out["SINCE_SOURCE"], out["SKIPPED"]),
                         ("none", str(T0 + 300), "checkout", "1"))
        self.assertIn("1 件はそれより前", out["REASON"])
        self.shot("snap-b", T0 + 400)
        out = self.pick()
        self.assertEqual((out["SCREENSHOT_DIR"], out["SKIPPED"], out["REASON"]),
                         (".claude/screenshots/snap-b", "1", ""))

    def test_shot_in_the_same_second_as_the_checkout_is_skipped(self):
        """切り替えと同じ秒の撮影は、どちらのブランチのものか決められないので外す."""
        self.git("checkout", "-q", "-b", "B", at=T0 + 300)
        self.shot("snap-same", T0 + 300)
        self.assertEqual(self.pick()["SCREENSHOT_DIR"], "none")
        self.shot("snap-after", T0 + 301)
        self.assertEqual(self.pick()["SCREENSHOT_DIR"], ".claude/screenshots/snap-after")

    def test_checkout_of_the_current_branch_and_rename_keep_since(self):
        """今のブランチへの checkout し直しと rename は切り替えではない（その前の撮影を外さない）."""
        self.git("checkout", "-q", "-b", "B", at=T0 + 100)
        self.shot("snap-b", T0 + 200)
        self.git("checkout", "-q", "B", at=T0 + 300)
        self.git("branch", "-m", "B", "B2", at=T0 + 400)
        out = self.pick()
        self.assertEqual((out["SCREENSHOT_DIR"], out["SINCE"], out["SINCE_SOURCE"]),
                         (".claude/screenshots/snap-b", str(T0 + 100), "checkout"))

    def test_newest_eligible_dir_wins_across_kinds(self):
        """snap / verify / tune のうち最も新しいもの. 別の名前のディレクトリと、同じ名前のファイルは見ない.

        3 種それぞれが最も新しい回を見る（tune だけの回が黙って撮り直しに変わらない。pr-creator は tune の
        before / after を対で出す）."""
        self.git("checkout", "-q", "-b", "B", at=T0 + 100)
        dirs = {"snap-x": self.shot("snap-x", T0 + 200), "verify-y": self.shot("verify-y", T0 + 400),
                "tune-z": self.shot("tune-z", T0 + 300)}
        self.shot("manual-w", T0 + 900)
        stray = self.repo / ".claude" / "screenshots" / "snap-stray.png"
        stray.write_bytes(b"png")
        os.utime(stray, (T0 + 800, T0 + 800))
        out = self.pick()
        self.assertEqual((out["SCREENSHOT_DIR"], out["SKIPPED"]), (".claude/screenshots/verify-y", "0"))
        for name, t in (("tune-z", T0 + 950), ("snap-x", T0 + 990)):
            with self.subTest(newest=name):
                os.utime(dirs[name], (t, t))
                self.assertEqual(self.pick()["SCREENSHOT_DIR"], f".claude/screenshots/{name}")

    def test_fresh_worktree_falls_back_to_its_creation(self):
        """checkout の記録が無い worktree は、作った時刻より後の撮影を通す（前のものは外す）.

        撮った後に commit しても起点は作成の時刻のまま（reflog の最も古い記録。最も新しい記録を使うと、
        worktree を作る → 撮る → commit する → PR を作る、の流れで撮り直しになる）."""
        wt = self.root / "wt"
        self.git("worktree", "add", "-q", "-b", "W", str(wt), at=T0 + 500)
        self.shot("snap-before", T0 + 400, top=wt)
        out = self.pick(wt)
        self.assertEqual((out["SCREENSHOT_DIR"], out["SINCE"], out["SINCE_SOURCE"]),
                         ("none", str(T0 + 500), "reflog-start"))
        self.shot("snap-after", T0 + 600, top=wt)
        self.assertEqual(self.pick(wt)["SCREENSHOT_DIR"], ".claude/screenshots/snap-after")
        self.git("commit", "-q", "--allow-empty", "-m", "w", at=T0 + 700, cwd=wt)
        out = self.pick(wt)
        self.assertEqual((out["SCREENSHOT_DIR"], out["SINCE"], out["SINCE_SOURCE"]),
                         (".claude/screenshots/snap-after", str(T0 + 500), "reflog-start"))

    def test_missing_head_reflog_selects_nothing(self):
        """HEAD の reflog が無ければ選ばない. git はブランチの reflog（作成時刻）を代わりに出すが、それを使うと
        作成から今の checkout までに別のブランチで撮ったものを通す."""
        self.git("checkout", "-q", "-b", "B", at=T0 + 100)
        self.shot("snap-b", T0 + 200)
        (self.repo / ".git" / "logs" / "HEAD").unlink()
        self.assertTrue((self.repo / ".git" / "logs" / "refs" / "heads" / "B").exists())
        out = self.pick()
        self.assertEqual((out["SCREENSHOT_DIR"], out["SINCE"], out["SINCE_SOURCE"], out["SKIPPED"]),
                         ("none", "", "none", "1"))
        self.assertIn("reflog", out["REASON"])

    def test_no_screenshot_dir_is_reported_as_such(self):
        out = self.pick()
        self.assertEqual((out["SCREENSHOT_DIR"], out["SKIPPED"]), ("none", "0"))
        self.assertIn("撮影ディレクトリ", out["REASON"])
        self.assertNotIn("それより前", out["REASON"])

    def test_looks_at_the_cwd_not_the_top(self):
        """ui-verify は cwd の `.claude/screenshots/` に撮り、pr-creator は返したパスを cwd から `--attach` に
        渡す. cwd がサブディレクトリなら、トップの撮影は見ず（cwd から引けない）、cwd の撮影を cwd からの
        相対パスで返す."""
        self.git("checkout", "-q", "-b", "B", at=T0 + 100)
        self.shot("snap-top", T0 + 300)
        sub = self.repo / "pkg" / "web"
        sub.mkdir(parents=True)
        out = self.pick(sub)
        self.assertEqual((out["SCREENSHOT_DIR"], out["SKIPPED"]), ("none", "0"))
        self.assertIn("撮影ディレクトリ", out["REASON"])
        self.shot("snap-sub", T0 + 200, top=sub)
        out = self.pick(sub)
        self.assertEqual(out["SCREENSHOT_DIR"], ".claude/screenshots/snap-sub")
        self.assertTrue((sub / out["SCREENSHOT_DIR"]).is_dir())
        self.assertEqual(self.pick()["SCREENSHOT_DIR"], ".claude/screenshots/snap-top")

    def test_outside_git_and_unknown_argument_exit_2(self):
        outside = self.root / "outside"
        outside.mkdir()
        for cwd, args in ((outside, ()), (self.repo, ("--all",))):
            with self.subTest(cwd=cwd.name, args=args):
                r = subprocess.run(["bash", str(SCRIPT), *args], cwd=str(cwd), capture_output=True,
                                   text=True, env=scrub(GIT_CEILING_DIRECTORIES=str(self.root)))
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertNotIn("SCREENSHOT_DIR", r.stdout)


class CallerContractTest(unittest.TestCase):
    """撮影の選び方を書く 3 か所が、最新をそのまま使う形に戻らない."""

    def test_pr_creator_picks_through_the_script(self):
        text = PR_CREATOR.read_text(encoding="utf-8")
        flow = section(text, "#### 撮影フローと PR body 添付", "#### 機密 UI チェックリスト")
        self.assertIn('scripts/pick-screenshot-dir.sh"', flow)
        self.assertNotIn("ls -1dt", text)
        for key in sorted(KEYS):
            with self.subTest(key=key):
                self.assertIn(f"`{key}=", flow)
        none = flow[flow.index("`SCREENSHOT_DIR=none`"):]
        self.assertIn("`snap` モード", none.split("\n\n")[0])

    def test_ui_verify_and_adr_describe_the_condition(self):
        for path in (UI_VERIFY, ADR):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("従来どおり pr-creator の Step 4.5 が snap で撮る", text)
                self.assertNotIn("snap 経路に寄る", text)
                lines = [l for l in text.splitlines() if "PR に添付するスクショ" in l]
                self.assertTrue(lines, "PR に添付するスクショの行が消えた")
                for line in lines:
                    self.assertIn("今のブランチ", line)
                    self.assertIn("pick-screenshot-dir.sh", line)


if __name__ == "__main__":
    unittest.main()
