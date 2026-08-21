#!/usr/bin/env python3
"""ポイズンした `GIT_DIR` の下でスイートを走らせても実リポジトリを触らない（issue #158）.

**なぜ要るか**: linked worktree の中で `git commit` すると、pre-commit が起動する本スイートは
`GIT_DIR=/path/to/repo/.git/worktrees/<name>`（**絶対パス**）を継承する。cwd を使い捨て
リポジトリにしても git は `GIT_DIR` を優先するので、テストの `git init` / `commit` が
**実リポジトリ**に当たる。実測（issue #158）では作業ブランチの ref がテスト由来の `init`
コミット列に乗っ取られ、`core.bare` が `true` に書き換わって `git status` すら通らなくなった。

**スクラブの仕組み自体は事故の前から在った**（`git_env.GIT_HOOK_ENV`）。壊れていたのは
**適用漏れ**（`_env()` にだけ入り `setUp` の `git init` に入っていない）なので、
「定義があること」を静的に見ても捕まらない。**実際に汚染環境で走らせて、外側のリポジトリが
1 バイトも動かないこと**を見る。CLAUDE.md「テストは『環境の不在』に頼らない」の系で、
ここは逆に**環境の存在を作って再現する**側。

**代表テストだけを走らせる**（全件だとスイートの実時間が倍になる）。選定基準は
「git を直接叩くファイルを 1 つずつ代表する」で、`test_every_git_touching_module_is_represented`
が機械的に強制する。スクリプト経由で間接的に git を叩くだけのテストは、その fixture
（`ScriptTestBase._env` / `HookTestCase.run_hook`）が代表側に含まれるので自動的に載る。
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from git_env import scrub

TESTS_DIR = Path(__file__).resolve().parent

#: git を直接叩くファイル → その経路を通す代表テスト
#: （`hook_harness` は基底なので、それを使うテストモジュール側で代表する）
REPRESENTATIVES = {
    "test_code_review_scripts.py":
        "test_code_review_scripts.BelowThresholdCountsValidationTest.test_bool_is_rejected",
    "test_bump_version.py":
        "test_bump_version.VnextResolutionTest.test_bare_placeholder_is_replaced",
    "test_pre_commit.py":
        "test_pre_commit.PreCommitTest.test_a_clean_change_passes",
    "test_auto_quality_check.py":
        "test_auto_quality_check.AutoQualityCheckTest.test_a_cached_detection_is_replayed_without_rerunning",
    "test_code_review_detection.py":
        "test_code_review_detection.CleanupRemovalTest.test_deletes_an_orphaned_agent_branch",
    "test_code_review_diff_scripts.py":
        "test_code_review_diff_scripts.DiffSliceListTest.test_lists_path_containing_space_from_real_git_output",
    "test_code_review_context.py":
        "test_code_review_context.MeasureTokensTest."
        "test_finds_the_transcript_of_the_main_repository_from_a_worktree",
    "hook_harness.py":
        "test_dev_workflow_hooks.OnCommitTest.test_publishes_commit_created",
}

#: 直接 git を叩くファイルの検出（この 2 ファイル自身は対象外）
GIT_CALL_RE = re.compile(r'subprocess\.run\(\s*\[\s*"git"')
EXEMPT = {"git_env.py", Path(__file__).name}


class VictimRepo:
    """「壊されてはいけない実リポジトリ」の役。linked worktree まで張って本番と同じ形にする."""

    def __init__(self, test: unittest.TestCase) -> None:
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "victim"
        self.root.mkdir()
        self.env = scrub()
        self._git("init", "-q", ".")
        self._git("config", "user.email", "victim@example.com")
        self._git("config", "user.name", "victim")
        (self.root / "keep.txt").write_text("original\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-qm", "victim baseline")
        self.worktree = self.root.parent / "wt"
        self._git("worktree", "add", "-q", "-b", "victim-work", str(self.worktree))
        # git が linked worktree の hook に渡すのと同じ**絶対パス**
        self.git_dir = self.root / ".git" / "worktrees" / self.worktree.name

    def _git(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=str(cwd or self.root), capture_output=True,
                              text=True, env=self.env, check=True)

    def poisoned_env(self, **extra: str) -> dict[str, str]:
        """worktree から commit したときに git が hook へ渡す環境（の危険な部分）を再現する."""
        env = scrub()
        env.update({
            "GIT_DIR": str(self.git_dir),
            "GIT_INDEX_FILE": str(self.git_dir / "index"),
            "GIT_PREFIX": "",
            "GIT_REFLOG_ACTION": "commit",
        })
        env.update(extra)
        return env

    def snapshot(self) -> dict[str, str]:
        """壊れ方（ref の乗っ取り / `core.bare` の反転 / 中身の書き換え）が見える最小の指紋."""
        return {
            "refs": self._git("show-ref").stdout,
            "config": self._git("config", "--local", "--list").stdout,
            "head": self._git("rev-parse", "HEAD").stdout,
            "worktree-head": self._git("rev-parse", "HEAD", cwd=self.worktree).stdout,
            "status": self._git("status", "--porcelain").stdout,
            "keep.txt": (self.root / "keep.txt").read_text(encoding="utf-8"),
        }


class GitEnvIsolationTest(unittest.TestCase):
    def test_the_poison_is_actually_dangerous(self):
        """**対照実験**: スクラブしなければ実リポジトリに当たる.

        これが無いと、`GIT_DIR` が伝わっていないだけの**空の緑**と区別がつかない
        （下の本体テストは「何も起きないこと」を見るので、無害な環境でも通ってしまう）。
        """
        victim = VictimRepo(self)
        before = victim.snapshot()
        sandbox = Path(tempfile.mkdtemp(dir=str(victim.root.parent)))
        (sandbox / "intruder.txt").write_text("x\n", encoding="utf-8")
        env = victim.poisoned_env()
        for args in (["add", "-A"], ["commit", "-qm", "intruder"]):
            subprocess.run(["git", *args], cwd=str(sandbox), capture_output=True, env=env)
        after = victim.snapshot()
        self.assertNotEqual(before["worktree-head"], after["worktree-head"],
                            "前提が崩れている: ポイズンした GIT_DIR が実リポジトリに届いていない")

    def test_the_suite_does_not_touch_the_outer_repository(self):
        victim = VictimRepo(self)
        before = victim.snapshot()
        res = subprocess.run(
            ["python3", "-m", "unittest", "-v", *sorted(REPRESENTATIVES.values())],
            cwd=str(TESTS_DIR), capture_output=True, text=True,
            env=victim.poisoned_env(PYTHONDONTWRITEBYTECODE="1"), timeout=600,
        )
        # **落ちたテストを「実リポジトリは無事だった」で素通りさせない**。setUp が
        # 例外で止まれば git を叩かずに終わるので、下の比較は自動的に通ってしまう
        self.assertEqual(res.returncode, 0,
                         "代表テストが汚染環境で落ちた:\n%s" % res.stderr[-4000:])
        self.assertEqual(before, victim.snapshot(),
                         "スイートが外側のリポジトリを書き換えた（issue #158 の再発）")

    def test_every_git_touching_module_is_represented(self):
        """git を直接叩くファイルが増えたら、汚染環境での代表テストも増やす."""
        touching = {p.name for p in sorted(TESTS_DIR.glob("*.py"))
                    if p.name not in EXEMPT and GIT_CALL_RE.search(p.read_text(encoding="utf-8"))}
        self.assertEqual(touching - set(REPRESENTATIVES), set(),
                         "git を直接叩くのに代表テストが無い（REPRESENTATIVES に足す）")
        self.assertEqual(set(REPRESENTATIVES) - touching, set(),
                         "git を叩かなくなったファイルが REPRESENTATIVES に残っている")


if __name__ == "__main__":
    unittest.main()
