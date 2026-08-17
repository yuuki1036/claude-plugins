#!/usr/bin/env python3
"""worktree の掃除・検出系 3 本の回帰テスト（GitHub issue #138）.

- `cleanup-agent-worktrees.sh` … **worktree を消す = 不可逆**。誤爆すると作業中の
  worktree が消えるので、「**消さない**条件」を肯定側より厚く書く。
- `detect-dev-worktree.sh` … 判定を誤ると teardown 案内が別 worktree を指す。
  ブランチ名は PR 作者が完全に制御する外部入力なので**シェルで再評価されない**ことも測る。
- `detect-recent-review.sh` … 判定を誤ると二重レビュー（費用）か未検出（重複）。
  **書き手（`publish-review-event.sh`）と読み手が同じキーを見ているか**は 2 本を通さないと
  分からないので、実際に publish した event を読ませる。
"""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from test_code_review_scripts import BASE_PAYLOAD, PLUGIN, ScriptTestBase

CLEANUP = PLUGIN / "scripts" / "cleanup-agent-worktrees.sh"
DETECT_DEV = PLUGIN / "scripts" / "detect-dev-worktree.sh"
DETECT_RECENT = PLUGIN / "scripts" / "detect-recent-review.sh"
TRIAGE = PLUGIN / "scripts" / "triage-signals.sh"


class WorktreeTestBase(ScriptTestBase):
    """本物の worktree を張る（`git worktree list --porcelain` の出力を模造しない）."""

    def git(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=str(cwd or self.root), capture_output=True,
                              text=True, env=self._env())

    def run_in(self, script: Path, *args: str, cwd: Path | None = None,
               env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(script), *args], cwd=str(cwd or self.root),
                              capture_output=True, text=True, env=env or self._env(), timeout=60)

    def add_worktree(self, rel: str, branch: str | None = None, detach: bool = False) -> Path:
        path = self.root / rel
        args = ["worktree", "add", "-q"]
        if branch:
            args += ["-b", branch]
        if detach:
            args += ["--detach"]
        res = self.git(*args, str(path))
        self.assertEqual(res.returncode, 0, res.stderr)
        return path

    def worktrees(self) -> list[str]:
        out = self.git("worktree", "list", "--porcelain").stdout
        return [l[len("worktree "):] for l in out.splitlines() if l.startswith("worktree ")]

    def branches(self) -> list[str]:
        return self.git("branch", "--format=%(refname:short)").stdout.split()


class CleanupSafetyTest(WorktreeTestBase):
    """**消してはいけないもの**（誤爆の blast radius が最大なので肯定側より先に置く）."""

    def test_refuses_to_run_on_the_main_repository(self):
        """メインリポジトリ上で走らせると、レビュー用 worktree と開発用 worktree を巻き込む."""
        review = self.add_worktree("review-wt", branch="agent-review")
        agent = self.add_worktree("review-wt/agents/a1", branch="agent-a1")
        res = self.run_in(CLEANUP)
        self.assertEqual(res.returncode, 0)
        self.assertIn("skip", res.stderr)
        self.assertTrue(review.is_dir())
        self.assertTrue(agent.is_dir())

    def test_keeps_a_sibling_worktree_that_is_not_underneath(self):
        """並行する別レビュー / 開発用 worktree（配下でないもの）には触れない."""
        review = self.add_worktree("review-wt", branch="agent-review")
        sibling = self.add_worktree("other-wt", branch="agent-other")
        res = self.run_in(CLEANUP, cwd=review)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(sibling.is_dir(), "配下でない worktree を消してはいけない")
        self.assertIn(str(sibling), self.worktrees())

    def test_never_removes_itself(self):
        review = self.add_worktree("review-wt", branch="agent-review")
        res = self.run_in(CLEANUP, cwd=review)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(review.is_dir())

    def test_keeps_an_agent_worktree_with_uncommitted_changes(self):
        """agent が何か書いていたら残す（消すと成果物が消える）."""
        review = self.add_worktree("review-wt", branch="agent-review")
        agent = self.add_worktree("review-wt/agents/a1", branch="agent-a1")
        (agent / "notes.md").write_text("agent の作業結果\n", encoding="utf-8")
        res = self.run_in(CLEANUP, cwd=review)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(agent.is_dir())
        self.assertIn("keep", res.stdout)
        self.assertIn("保持 1 件", res.stdout)

    def test_keeps_an_agent_branch_checked_out_by_a_live_worktree(self):
        """並行レビューの生きた worktree が使っているブランチは削除しない."""
        review = self.add_worktree("review-wt", branch="agent-review")
        self.add_worktree("other-wt", branch="agent-live")
        res = self.run_in(CLEANUP, cwd=review)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("agent-live", self.branches())

    def test_never_deletes_a_non_agent_branch(self):
        review = self.add_worktree("review-wt", branch="agent-review")
        self.git("branch", "feature/keep-me")
        res = self.run_in(CLEANUP, cwd=review)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("feature/keep-me", self.branches())

    def test_dry_run_removes_nothing(self):
        review = self.add_worktree("review-wt", branch="agent-review")
        agent = self.add_worktree("review-wt/agents/a1", branch="agent-a1")
        res = self.run_in(CLEANUP, "--dry-run", cwd=review)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(agent.is_dir(), "--dry-run で消してはいけない")
        self.assertIn("agent-a1", self.branches())
        self.assertIn("would remove", res.stdout)
        self.assertIn("(dry-run)", res.stdout)
        # **dry-run では「消す予定の worktree が使っているブランチ」も報告する**。
        # 実削除時は INUSE を削除後に数えるので自然に落ちるが、dry-run では残るため
        # 別集合（FREED）で拾わないと「消せるブランチ」が 0 件に見える
        self.assertIn("would delete branch  agent-a1", res.stdout)
        self.assertIn("agent-* ブランチ: 1 件 (dry-run)", res.stdout)

    def test_unknown_argument_exits_2(self):
        res = self.run_in(CLEANUP, "--force")
        self.assertEqual(res.returncode, 2)
        self.assertIn("usage", res.stderr)

    def test_outside_a_git_repository_exits_2(self):
        outside = self.root / "tmp" / "not-a-repo"
        outside.mkdir(parents=True)
        env = {**self._env(), "GIT_CEILING_DIRECTORIES": str(outside.parent)}
        res = self.run_in(CLEANUP, cwd=outside, env=env)
        self.assertEqual(res.returncode, 2)
        self.assertIn("FATAL", res.stderr)


class CleanupRemovalTest(WorktreeTestBase):
    """**消すべきもの**（片付かないと worktree とブランチが恒久的に残る）."""

    def setUp(self) -> None:
        super().setUp()
        self.review = self.add_worktree("review-wt", branch="agent-review")

    def test_removes_a_clean_agent_worktree_underneath(self):
        agent = self.add_worktree("review-wt/agents/a1", branch="agent-a1")
        res = self.run_in(CLEANUP, cwd=self.review)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse(agent.is_dir())
        self.assertNotIn(str(agent), self.worktrees())

    def test_removes_a_detached_agent_worktree(self):
        """agent は detach で作業する（issue #98 のブランチ誤読対策）."""
        agent = self.add_worktree("review-wt/agents/a1", detach=True)
        res = self.run_in(CLEANUP, cwd=self.review)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse(agent.is_dir())

    def test_deletes_the_branch_freed_by_the_removed_worktree(self):
        """自分が今 free にしたブランチは削除する（`INUSE` の一覧は削除前の状態）."""
        self.add_worktree("review-wt/agents/a1", branch="agent-a1")
        res = self.run_in(CLEANUP, cwd=self.review)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("agent-a1", self.branches())

    def test_deletes_an_orphaned_agent_branch(self):
        """どの worktree にも checkout されていない `agent-*` は残骸."""
        self.git("branch", "agent-orphan")
        res = self.run_in(CLEANUP, cwd=self.review)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("agent-orphan", self.branches())

    def test_reports_counts_even_when_there_is_nothing_to_do(self):
        """silent skip で「片付いたつもり」を作らない（必ず件数を報告する）."""
        res = self.run_in(CLEANUP, cwd=self.review)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("agent worktree: 0 件", res.stdout)
        self.assertIn("保持 0 件", res.stdout)
        self.assertIn("失敗 0 件", res.stdout)

    def test_counts_multiple_removals(self):
        self.add_worktree("review-wt/agents/a1", branch="agent-a1")
        self.add_worktree("review-wt/agents/a2", branch="agent-a2")
        res = self.run_in(CLEANUP, cwd=self.review)
        self.assertIn("agent worktree: 2 件 削除", res.stdout)
        self.assertIn("agent-* ブランチ: 2 件 削除", res.stdout)

    def test_reports_a_failed_branch_deletion(self):
        """**削除できなかったブランチを黙って件数から落とさない.**

        報告が「0 件 削除」だけだと、残骸が積もっても誰も気づかない
        （worktree 側は `失敗 N 件` を報告しているので非対称だった）。
        ref 置き場を書込不可にして `git branch -D` を実際に失敗させる。
        """
        self.git("branch", "agent-orphan")
        heads = self.root / ".git" / "refs" / "heads"
        self.assertTrue((heads / "agent-orphan").is_file(), "前提: loose ref として存在する")
        heads.chmod(0o500)
        self.addCleanup(heads.chmod, 0o700)
        res = self.run_in(CLEANUP, cwd=self.review)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("agent-orphan", self.branches(), "前提: 削除が失敗している")
        self.assertIn("agent-* ブランチ: 0 件 削除 / 失敗 1 件", res.stdout)
        self.assertIn("FAILED branch agent-orphan", res.stderr)


class DetectDevWorktreeTest(WorktreeTestBase):
    """開発用 worktree の検出（レビュー用の一時 worktree と混同しないこと）."""

    def marker(self, wt: Path, which: str = "backend") -> None:
        (wt / "envs").mkdir(parents=True, exist_ok=True)
        (wt / "envs" / (".%s.env.worktree" % which)).write_text("PORT=1\n", encoding="utf-8")

    def gh_stub(self, branch: str = "", rc: int = 0) -> dict[str, str]:
        bin_dir = self.root / "tmp" / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        stub = bin_dir / "gh"
        stub.write_text("#!/bin/sh\ncat <<'EOF'\n{branch}\nEOF\nexit {rc}\n".format(
            branch=branch, rc=rc), encoding="utf-8")
        stub.chmod(0o755)
        env = self._env()
        env["PATH"] = "%s:%s" % (bin_dir, env["PATH"])
        return env

    def test_reports_a_worktree_with_the_worktree_setup_marker(self):
        wt = self.add_worktree("dev-wt", branch="feat/x")
        self.marker(wt)
        res = self.run_in(DETECT_DEV, "--branch", "feat/x")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), str(wt))

    def test_accepts_the_frontend_marker_too(self):
        wt = self.add_worktree("dev-wt", branch="feat/x")
        self.marker(wt, "frontend")
        res = self.run_in(DETECT_DEV, "--branch", "feat/x")
        self.assertEqual(res.stdout.strip(), str(wt))

    def test_ignores_a_worktree_without_the_marker(self):
        self.add_worktree("dev-wt", branch="feat/x")
        res = self.run_in(DETECT_DEV, "--branch", "feat/x")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "")

    def test_ignores_the_review_temporary_worktree(self):
        """`.claude/worktrees/` 配下は EnterWorktree の一時 worktree（teardown 案内の対象外）."""
        wt = self.add_worktree(".claude/worktrees/review-1", branch="feat/x")
        self.marker(wt)
        res = self.run_in(DETECT_DEV, "--branch", "feat/x")
        self.assertEqual(res.stdout.strip(), "")

    def test_unknown_branch_prints_nothing(self):
        res = self.run_in(DETECT_DEV, "--branch", "feat/absent")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "")

    def test_branch_name_is_never_evaluated_by_the_shell(self):
        """**ブランチ名は PR 作者が制御する外部入力**（`$(...)` は有効な ref 名）.

        `feat/$(pwn)` は `git check-ref-format` を通る。評価されたら PATH 上の `pwn` が
        走るので、canary の有無で「評価されたか」を直接測れる。
        """
        canary = self.root / "tmp" / "pwned"
        bin_dir = self.root / "tmp" / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        pwn = bin_dir / "pwn"
        pwn.write_text("#!/bin/sh\ntouch '%s'\n" % canary, encoding="utf-8")
        pwn.chmod(0o755)
        env = self._env()
        env["PATH"] = "%s:%s" % (bin_dir, env["PATH"])

        name = "feat/$(pwn)"
        wt = self.add_worktree("dev-wt", branch=name)
        self.marker(wt)
        res = self.run_in(DETECT_DEV, "--branch", name, env=env)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse(canary.exists(), "ブランチ名がシェルで評価された")
        self.assertEqual(res.stdout.strip(), str(wt), "評価せずに一致させられること")

    def test_no_argument_exits_2(self):
        res = self.run_in(DETECT_DEV)
        self.assertEqual(res.returncode, 2)
        self.assertIn("usage", res.stderr)

    def test_flag_without_value_exits_2(self):
        for flag in ("--pr", "--branch"):
            with self.subTest(flag=flag):
                res = self.run_in(DETECT_DEV, flag)
                self.assertEqual(res.returncode, 2)
                self.assertIn("値が必要", res.stderr)

    def test_non_numeric_pr_exits_2(self):
        res = self.run_in(DETECT_DEV, "--pr", "12; rm -rf /")
        self.assertEqual(res.returncode, 2)
        self.assertIn("数値のみ", res.stderr)

    def test_pr_resolves_the_branch_through_gh(self):
        wt = self.add_worktree("dev-wt", branch="feat/from-pr")
        self.marker(wt)
        res = self.run_in(DETECT_DEV, "--pr", "42", env=self.gh_stub("feat/from-pr"))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), str(wt))

    def test_pr_without_a_resolvable_head_ref_exits_1(self):
        """取得失敗を「該当なし」に潰さない（無いことの証明にならない）."""
        res = self.run_in(DETECT_DEV, "--pr", "42", env=self.gh_stub("", rc=1))
        self.assertEqual(res.returncode, 1)
        self.assertIn("head ref を取得できない", res.stderr)


class DetectRecentReviewTest(ScriptTestBase):
    """直近レビューの検出。**publish 側と読み側のキー一致**を 2 本通しで測る."""

    def setUp(self) -> None:
        super().setUp()
        (self.root / "src").mkdir(exist_ok=True)
        (self.root / "src" / "a.ts").write_text("const x = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, capture_output=True, env=self._env())

    def save_diff(self) -> Path:
        """`triage-signals.sh` に実際の diff を保存させる（パス導出も本物を通す）."""
        res = self.run_script(TRIAGE, "--base", "HEAD")
        self.assertEqual(res.returncode, 0, res.stderr)
        for line in res.stdout.splitlines():
            if line.startswith("diff_file="):
                return Path(line.split("=", 1)[1])
        self.fail("diff_file が出力されていない")

    def detect(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self.run_script(DETECT_RECENT, *args)

    def previous_review(self, payload: dict | None = None,
                        plugin: str = "code-review:self-review") -> Path:
        """「直前のレビューが終わっている」状態を作る.

        **publish は成功時に diff / prctx / agentctx を掃除する**ので、検出側が読む diff は
        「次のレビューが保存したもの」になる。この順序（保存 → publish → 保存）が実フロー。
        """
        self.save_diff()
        pub = self.publish(payload, plugin)
        self.assertEqual(pub.returncode, 0, pub.stderr)
        return self.save_diff()

    def log(self) -> Path:
        path = self.root / ".claude" / "events.jsonl"
        self.assertTrue(path.is_file(), "publish が events.jsonl を書いていない")
        return path

    def test_silent_without_any_event_log(self):
        self.save_diff()
        res = self.detect()
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "", "no-op を報告させない")

    def test_silent_without_a_saved_diff(self):
        """自力導出が空なのは「まだ diff を保存していない」だけ（silent）."""
        res = self.detect()
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "")
        self.assertEqual(res.stderr.strip(), "")

    def test_explicit_missing_diff_warns(self):
        """明示指定の不在は caller のバグなので黙らない.

        **UTF-8 ロケールでのみ再現する経路**だった: `$DIFF（` は `（` の先頭バイトまで
        変数名に取り込まれ、`set -u` で WARN を出さず exit 1 していた。
        """
        res = self.detect("--diff", str(self.root / "absent.diff"))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("WARN", res.stderr)
        self.assertIn("absent.diff", res.stderr)
        self.assertNotIn("unbound variable", res.stderr)

    def test_flag_without_value_exits_2(self):
        for flag in ("--diff", "--window-hours", "--pr"):
            with self.subTest(flag=flag):
                res = self.detect(flag)
                self.assertEqual(res.returncode, 2)
                self.assertIn("値が必要", res.stderr)

    def test_flag_with_a_value_as_the_last_argument_is_accepted(self):
        """**境界を両側から測る**: 値が最後の引数でも「値が必要」にしない.

        `[ $# -ge 2 ]` を `-gt 2` と取り違えると、`--pr 123` のように**値を渡しているのに**
        FATAL になる（引数を 1 つも足さずに呼ぶのが通常経路なので気づきにくい）。
        """
        for args in (("--pr", "123"), ("--window-hours", "48")):
            with self.subTest(args=args):
                res = self.detect(*args)
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertNotIn("値が必要", res.stderr)

    def test_non_numeric_window_exits_2(self):
        res = self.detect("--window-hours", "abc")
        self.assertEqual(res.returncode, 2)
        self.assertIn("数値のみ", res.stderr)

    def test_unknown_argument_exits_2(self):
        res = self.detect("--nope")
        self.assertEqual(res.returncode, 2)

    def test_detects_the_event_written_by_publish(self):
        """**書き手と読み手が同じ digest を見ているか**（片方だけの単体テストでは分からない）."""
        self.previous_review()
        res = self.detect()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("## recent-review", res.stdout)
        self.assertIn("完全一致 1 件", res.stdout)
        self.assertIn("code-review:self-review", res.stdout)
        # 明細の強弱ラベル（件数行とは別経路。取り違えると弱いキーの警告文と矛盾する）
        self.assertIn("[完全一致]", res.stdout)
        self.assertNotIn("[ファイル集合のみ]", res.stdout)

    def test_files_only_match_is_labelled_as_the_weak_key(self):
        """skill を跨ぐと diff のバイト列が変わる（`gh pr diff` vs 3 本連結）."""
        diff = self.previous_review()
        # 同じファイル集合・別バイト列（review 側の diff の作り方を模す）
        body = diff.read_text(encoding="utf-8")
        diff.write_text(body.replace("index ", "index~"), encoding="utf-8")
        res = self.detect()
        self.assertIn("## recent-review", res.stdout)
        self.assertIn("ファイル集合のみ一致 1 件", res.stdout)
        self.assertIn("[ファイル集合のみ]", res.stdout)
        self.assertNotIn("[完全一致]", res.stdout)
        self.assertIn("重複の証明ではない", res.stdout)

    def test_a_different_file_set_is_not_reported(self):
        self.previous_review()
        (self.root / "src" / "other.ts").write_text("const y = 2\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, capture_output=True, env=self._env())
        self.save_diff()
        res = self.detect()
        self.assertEqual(res.stdout.strip(), "")

    def test_events_outside_the_window_are_ignored(self):
        self.previous_review()
        log = self.log()
        rows = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
        old = (datetime.now(timezone.utc) - timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows[-1]["ts"] = old
        log.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                       encoding="utf-8")
        self.assertEqual(self.detect().stdout.strip(), "", "24h の既定窓の外")
        self.assertIn("## recent-review", self.detect("--window-hours", "48").stdout)

    def test_a_broken_line_does_not_hide_the_rest(self):
        self.previous_review()
        log = self.log()
        good = log.read_text(encoding="utf-8")
        log.write_text('{"ts":"broken\n' + good, encoding="utf-8")
        self.assertIn("## recent-review", self.detect().stdout)

    def test_a_non_utf8_byte_does_not_crash_the_scan(self):
        """events.jsonl は全プラグイン共有の追記ログ。1 バイトで恒久クラッシュさせない."""
        self.previous_review()
        log = self.log()
        with open(log, "rb") as fh:
            good = fh.read()
        with open(log, "wb") as fh:
            fh.write(b'{"ts":"\xff\xfe"}\n' + good)
        res = self.detect()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("## recent-review", res.stdout)

    def test_reviews_from_two_plugins_are_both_reported(self):
        """self-review 直後に review を回す経路（`--focus` / `--exclude` では防げない重複）."""
        self.previous_review()
        log = self.log()
        rows = log.read_text(encoding="utf-8").splitlines()
        ev = json.loads(rows[-1])
        ev["plugin"] = "code-review:review"
        log.write_text("\n".join(rows + [json.dumps(ev, ensure_ascii=False)]) + "\n",
                       encoding="utf-8")
        out = self.detect().stdout
        self.assertIn("2 件", out)
        self.assertIn("code-review:review", out)

    def test_payload_counts_are_surfaced(self):
        # 明細に出るのは severity 別の `*_count`（`pre_adjust_counts` は調整前の値で別物）
        payload = dict(BASE_PAYLOAD, blocker_count=1, critical_count=2, major_count=3,
                       minor_count=4)
        payload["findings_class"] = {"lint": 0, "test": 0, "judgement": 10}
        self.previous_review(payload)
        out = self.detect().stdout
        self.assertIn("B1/C2/M3/m4", out)
        self.assertIn("effort=high", out)

    def test_at_most_five_hits_are_listed(self):
        """出力は 5 件まで（件数は全件、明細は打ち切り）."""
        self.previous_review()
        log = self.log()
        base = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
        rows = []
        for i in range(7):
            ev = dict(base)
            ev["ts"] = (datetime.now(timezone.utc) - timedelta(minutes=i + 1)
                        ).strftime("%Y-%m-%dT%H:%M:%SZ")
            rows.append(json.dumps(ev, ensure_ascii=False))
        log.write_text("\n".join(rows) + "\n", encoding="utf-8")
        out = self.detect().stdout
        self.assertIn("7 件", out)
        rows = [l for l in out.splitlines() if l.startswith("- 20")]
        self.assertEqual(len(rows), 5)
        # **新しい順**（直近を先に見せる。打ち切りが「古い 5 件」になると意味が反転する）
        stamps = [l.split()[1] for l in rows]
        self.assertEqual(stamps, sorted(stamps, reverse=True))


if __name__ == "__main__":
    unittest.main()
