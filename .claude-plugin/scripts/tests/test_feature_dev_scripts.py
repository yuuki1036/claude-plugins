#!/usr/bin/env python3
"""feature-dev 同梱スクリプトの CLI 境界テスト（`scripts/plugin-enabled.sh`）.

有効判定を誤ると、無効化したプラグインの skill を呼びに行く（有効と誤認）か、project だけで
有効化したプラグインを使わない（取りこぼし）。以前の判定は `$HOME/.claude/settings.json` に
キーがあるかだけを見ていて、両方を起こしていた。**0 に倒すべき条件を厚く**書く。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from git_env import scrub

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "feature-dev" / "scripts" / "plugin-enabled.sh"


class PluginEnabledTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / "home"
        self.proj = self.root / "proj"
        (self.home / ".claude").mkdir(parents=True)
        (self.proj / ".claude").mkdir(parents=True)

    def settings(self, where: str, plugins: dict[str, bool], *, compact: bool = False) -> None:
        base = self.home if where == "user" else self.proj
        name = "settings.local.json" if where == "local" else "settings.json"
        body = {"enabledPlugins": {f"{k}@mkt": v for k, v in plugins.items()}}
        text = json.dumps(body, separators=(",", ":")) if compact else json.dumps(body, indent=2)
        (base / ".claude" / name).write_text(text)

    def run_script(self, *args: str, project_env: bool = True,
                   cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        # 環境は組み立てて渡す（実機の HOME / CLAUDE_PROJECT_DIR を継承すると本物の settings を読む）
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home)}
        if project_env:
            env["CLAUDE_PROJECT_DIR"] = str(self.proj)
        return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True,
                              env=env, cwd=str(cwd or self.root))

    def assertState(self, plugin: str, expected: str, **kw) -> None:
        res = self.run_script(plugin, **kw)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), expected, res.stderr)

    # --- 1 に倒すもの ---
    def test_enabled_in_user_settings(self):
        self.settings("user", {"bdd-spec": True})
        self.assertState("bdd-spec", "1")

    def test_enabled_only_in_project_settings(self):
        """project だけで有効化したものを取りこぼさない（旧判定の取りこぼし）."""
        self.settings("project", {"bdd-spec": True})
        self.assertState("bdd-spec", "1")

    def test_local_true_overrides_user_false(self):
        self.settings("user", {"bdd-spec": False})
        self.settings("local", {"bdd-spec": True})
        self.assertState("bdd-spec", "1")

    def test_compact_json_is_read(self):
        self.settings("user", {"bdd-spec": True}, compact=True)
        self.assertState("bdd-spec", "1")

    def test_project_dir_falls_back_to_cwd(self):
        """CLAUDE_PROJECT_DIR が無い（Bash ツールの既定）ときは cwd の .claude を読む."""
        self.settings("project", {"design-doc": True})
        self.assertState("design-doc", "1", project_env=False, cwd=self.proj)

    # --- 0 に倒すもの ---
    def test_no_settings_at_all(self):
        self.assertState("bdd-spec", "0")

    def test_disabled_but_installed_is_not_enabled(self):
        """`false` で無効化したプラグインを有効と誤認しない（旧判定の誤認 / spec-advisor #74 と同型）."""
        self.settings("user", {"bdd-spec": False})
        self.assertState("bdd-spec", "0")

    def test_project_false_overrides_user_true(self):
        self.settings("user", {"code-review": True})
        self.settings("project", {"code-review": False})
        self.assertState("code-review", "0")

    def test_local_false_overrides_project_true(self):
        self.settings("project", {"code-review": True})
        self.settings("local", {"code-review": False})
        self.assertState("code-review", "0")

    def test_other_plugin_with_a_shared_suffix_does_not_count(self):
        """`bdd-spec` が有効でも `spec` は有効にならない（名前の前方を `"` で固定している）."""
        self.settings("user", {"bdd-spec": True})
        self.assertState("spec", "0")

    def test_other_plugin_with_a_shared_prefix_does_not_count(self):
        self.settings("user", {"bdd-spec-extra": True})
        self.assertState("bdd-spec", "0")

    def test_missing_argument_prints_zero_and_succeeds(self):
        res = self.run_script()
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "0")
        self.assertIn("usage", res.stderr)


class InitialSelfReviewScopeTest(unittest.TestCase):
    """Phase 6 の初回 self-review に `--focus` を渡さない（GitHub issue #283）.

    `--focus` を付けると self-review は反証レイヤーと skeptic を `scope` でスキップし、triage が出す観点
    （`layer-responsibility` など）も起動しない。初回は観点選定を code-review の triage に任せ、
    `--focus` は G-V ループの再レビュー（既検証の観点の見直し）だけで使う。
    """

    SKILL = REPO / "feature-dev" / "skills" / "feature-dev" / "SKILL.md"
    REVIEW_LOOP = REPO / "feature-dev" / "references" / "review-loop.md"

    @staticmethod
    def section(text: str, start: str, end: str) -> str:
        i = text.index(start)
        return text[i:text.index(end, i)]

    def test_initial_call_does_not_pass_focus(self):
        step2 = self.section(self.SKILL.read_text(), "### Step 2: Invoke code-review:self-review",
                             "self-review 内部の動き")
        args = [l for l in step2.splitlines() if l.startswith("- ")]
        self.assertTrue(args, "Step 2 の引数の箇条書きを拾えていない")
        self.assertFalse([l for l in args if l.startswith("- `--focus")], "初回の self-review に --focus を渡している")
        self.assertTrue([l for l in args if "`--embed`" in l])

    def test_re_review_keeps_focus(self):
        """再レビューは既検証の観点の見直しなので `--focus` を使う（初回の禁止を広げすぎない）."""
        loop = self.section(self.REVIEW_LOOP.read_text(), "7. **Re-review**", "8. **Update loop state**")
        self.assertIn("`--focus <persisting issue の focus 集合>`", loop)


class SummaryReadingGuideTest(unittest.TestCase):
    """Phase 7 は独自サマリの代わりに code-review:review-guide を案内する（GitHub issue #290）.

    PR がまだ無い段階なので base モード（`--base`）で呼ぶ。PR モードは PR に push 済みのコミットしか
    見ないので、feature-dev が作った未コミットの変更が読み順から落ちる。`--base` は review-guide 側の
    引数なので、向こうで名前が変わったらここで気づけるよう、review-guide の引数の宣言と突き合わせる。
    """

    SKILL = REPO / "feature-dev" / "skills" / "feature-dev" / "SKILL.md"
    GUIDE = REPO / "code-review" / "skills" / "review-guide" / "SKILL.md"

    def phase7(self) -> str:
        text = self.SKILL.read_text()
        i = text.index("## Phase 7: Summary")
        return text[i:text.index("**Event Bus publish", i)]

    def test_invokes_review_guide_in_base_mode(self):
        self.assertIn("`code-review:review-guide` を `--base <BASE>` 付きで呼ぶ", self.phase7())

    def test_review_guide_still_accepts_base(self):
        guide = self.GUIDE.read_text()
        front = guide[:guide.index("\n---", 4)]
        self.assertIn("--base <ref>", front, "review-guide の引数から --base が消えた")

    def test_falls_back_to_plain_summary(self):
        """code-review が無効・「出さない」・呼び出しの失敗のときは従来のサマリを出す."""
        p7 = self.phase7()
        fallback = p7[p7.index("**従来のサマリ**"):]
        for cond in ("code-review が無効", "「出さない」", "呼び出しが失敗"):
            self.assertIn(cond, fallback)
        self.assertIn("Files modified", fallback)


SNAPSHOT = REPO / "feature-dev" / "scripts" / "review-snapshot.sh"


class ReviewSnapshotTest(unittest.TestCase):
    """`review-snapshot.sh save|check` — レビュー後に入った変更を出す（GitHub issue #276）.

    **ref も index も動かさない**こと、未追跡の新規ファイルを数えること、.gitignore を数えないことを見る。
    """

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.env = scrub()
        for args in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"]):
            self.git(*args)
        (self.root / ".gitignore").write_text("build/\n", encoding="utf-8")
        (self.root / "spec.md").write_text("rule 1\nrule 2\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")

    def git(self, *args: str) -> str:
        res = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout

    def run_snap(self, mode: str, cwd: Path | None = None) -> dict:
        res = subprocess.run(["bash", str(SNAPSHOT), mode], cwd=cwd or self.root, capture_output=True,
                             text=True, env=self.env, timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        out = {"rows": []}
        for line in res.stdout.splitlines():
            if "\t" in line:
                out["rows"].append(line.split("\t"))
            else:
                k, _, v = line.partition("=")
                out[k] = v
        return out

    def test_unchanged_after_save(self):
        (self.root / "spec.md").write_text("rule 1\nrule 2 edited\n", encoding="utf-8")  # レビュー前の未コミット変更
        self.run_snap("save")
        got = self.run_snap("check")
        self.assertEqual((got["changed_files"], got["changed_lines"]), ("0", "0"))

    def test_edits_and_new_files_after_save_are_reported(self):
        self.run_snap("save")
        (self.root / "spec.md").write_text("rule 1\nrule 2 changed\nrule 3\n", encoding="utf-8")
        (self.root / "new.md").write_text("added\n", encoding="utf-8")
        got = self.run_snap("check")
        self.assertEqual(got["changed_files"], "2")
        self.assertEqual(got["changed_lines"], "4")  # spec.md +2 -1 / new.md +1
        self.assertEqual(sorted(r[2] for r in got["rows"]), ["new.md", "spec.md"])

    def test_deleted_file_is_reported(self):
        self.run_snap("save")
        (self.root / "spec.md").unlink()
        self.assertEqual(self.run_snap("check")["changed_files"], "1")

    def test_ignored_files_are_not_counted(self):
        self.run_snap("save")
        (self.root / "build").mkdir()
        (self.root / "build" / "out.txt").write_text("x\n", encoding="utf-8")
        self.assertEqual(self.run_snap("check")["changed_files"], "0")

    def test_refs_and_index_are_untouched(self):
        (self.root / "spec.md").write_text("unstaged\n", encoding="utf-8")
        (self.root / "untracked.md").write_text("u\n", encoding="utf-8")
        before = (self.git("rev-parse", "HEAD"), self.git("status", "--porcelain"), self.git("stash", "list"))
        self.run_snap("save")
        self.run_snap("check")
        self.assertEqual((self.git("rev-parse", "HEAD"), self.git("status", "--porcelain"),
                          self.git("stash", "list")), before)

    def test_commit_after_save_without_content_change_is_not_a_change(self):
        """レビュー後にコミットしただけなら中身は変わっていない（tree で比べる）."""
        (self.root / "spec.md").write_text("reviewed\n", encoding="utf-8")
        self.run_snap("save")
        self.git("commit", "-qam", "commit reviewed state")
        self.assertEqual(self.run_snap("check")["changed_files"], "0")

    def test_check_from_a_subdirectory_sees_the_whole_tree(self):
        (self.root / "docs").mkdir()
        self.run_snap("save", cwd=self.root / "docs")
        (self.root / "spec.md").write_text("changed\n", encoding="utf-8")
        self.assertEqual(self.run_snap("check", cwd=self.root / "docs")["changed_files"], "1")

    def test_missing_snapshot(self):
        self.assertEqual(self.run_snap("check")["snapshot"], "missing")

    def test_not_a_git_repo(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.run_snap("check", cwd=Path(d))["snapshot"], "unavailable")

    def test_snapshots_are_per_worktree(self):
        wt = self.root.parent / (self.root.name + "-wt")
        self.git("worktree", "add", "-q", "-b", "other", str(wt))
        self.addCleanup(lambda: subprocess.run(["git", "worktree", "remove", "--force", str(wt)],
                                               cwd=self.root, capture_output=True, env=self.env))
        self.run_snap("save")
        self.assertEqual(self.run_snap("check", cwd=wt)["snapshot"], "missing")


if __name__ == "__main__":
    unittest.main()
