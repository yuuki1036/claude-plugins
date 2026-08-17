#!/usr/bin/env python3
"""doc-freshness の hook スクリプトの回帰テスト.

この 2 本は**毎セッション / 毎編集で鳴りうる**ので、誤発火のコストが特に高い
（「⚠️ が出たときだけ行動する」契約が壊れると、既存の全警告の信頼度が落ちる）。

- `frontmatter-guard.sh` — 対象 prefix 配下の .md だけを見る。プラグイン内部 doc は
  CLAUDE.md 規約で frontmatter 対象外なので、**そこで鳴らないこと**が仕様
- `stale-check.sh` — opt-in。config が無ければ**何もしない**。閾値は phase 別で、
  境界（ちょうど閾値なら鳴らない / 1 日超えたら鳴る）を両側から測る

実行: python3 -m unittest discover -s .claude-plugin/scripts/tests
"""

from __future__ import annotations

import datetime
import json
import unittest
from pathlib import Path

from hook_harness import HookTestCase, TempGitRepo


def days_ago(n: int) -> str:
    return (datetime.date.today() - datetime.timedelta(days=n)).isoformat()


class FrontmatterGuardTest(HookTestCase):
    PLUGIN = "doc-freshness"
    SCRIPT = "hooks/scripts/frontmatter-guard.sh"

    def payload(self, path: Path, tool: str = "Edit") -> dict:
        return {"tool_name": tool, "tool_input": {"file_path": str(path)}}

    def _doc(self, root: Path, rel: str, body: str) -> Path:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
        return p

    def _run(self, root: Path, p: Path, tool: str = "Edit"):
        return self.run_hook(self.payload(p, tool), cwd=root,
                             env_extra={"CLAUDE_PROJECT_DIR": str(root)})

    def test_fires_when_frontmatter_missing(self):
        with TempGitRepo() as root:
            p = self._doc(root, ".claude/designs/x.md", "# 設計\n\n本文\n")
            self.assertFired(self._run(root, p), "frontmatter")

    def test_fires_when_only_one_key_missing(self):
        with TempGitRepo() as root:
            p = self._doc(root, ".claude/adr/y.md", "---\nphase: current\n---\n\n本文\n")
            res = self._run(root, p)
            self.assertFired(res, "last-validated")
            self.assertNotIn("phase", res.context.split("不足しています:")[1].split("。")[0])

    def test_silent_when_both_keys_present(self):
        with TempGitRepo() as root:
            p = self._doc(root, ".claude/designs/z.md",
                          f"---\nlast-validated: {days_ago(0)}\nphase: current\n---\n\n本文\n")
            self.assertSilent(self._run(root, p))

    def test_silent_outside_target_prefixes(self):
        """**プラグイン内部 doc で鳴らない**（CLAUDE.md 規約で frontmatter 対象外）."""
        for rel in ("code-review/skills/review/SKILL.md", "README.md",
                    "docs/pipeline-design.md", ".claude/notes/memo.md"):
            with self.subTest(rel=rel), TempGitRepo() as root:
                p = self._doc(root, rel, "# 見出し\n")
                self.assertSilent(self._run(root, p), rel)

    def test_silent_for_non_markdown(self):
        with TempGitRepo() as root:
            p = self._doc(root, ".claude/designs/x.json", "{}")
            self.assertSilent(self._run(root, p))

    def test_silent_for_non_edit_tool(self):
        with TempGitRepo() as root:
            p = self._doc(root, ".claude/designs/x.md", "# 見出し\n")
            for tool in ("Bash", "Read", "Glob"):
                with self.subTest(tool=tool):
                    self.assertSilent(self._run(root, p, tool=tool))

    def test_config_can_disable(self):
        with TempGitRepo() as root:
            (root / ".claude").mkdir(exist_ok=True)
            (root / ".claude" / "doc-freshness.json").write_text(
                json.dumps({"postToolUseCheck": False}))
            p = self._doc(root, ".claude/designs/x.md", "# 見出し\n")
            self.assertSilent(self._run(root, p))

    def test_config_can_override_targets(self):
        with TempGitRepo() as root:
            (root / ".claude").mkdir(exist_ok=True)
            (root / ".claude" / "doc-freshness.json").write_text(
                json.dumps({"hookTargets": ["docs/"]}))
            self.assertFired(self._run(root, self._doc(root, "docs/a.md", "# a\n")))
            self.assertSilent(self._run(root, self._doc(root, ".claude/designs/b.md", "# b\n")))

    def test_missing_file_is_silent(self):
        with TempGitRepo() as root:
            self.assertSilent(self._run(root, root / ".claude/designs/none.md"))

    def test_malformed_input_is_silent(self):
        self.assertSilent(self.run_hook({}))

    def test_never_blocks(self):
        with TempGitRepo() as root:
            p = self._doc(root, ".claude/designs/x.md", "# 見出し\n")
            self.assertNotEqual(self._run(root, p).returncode, 2)


class StaleCheckTest(HookTestCase):
    PLUGIN = "doc-freshness"
    SCRIPT = "hooks/scripts/stale-check.sh"

    def _setup(self, root: Path, config: dict | None):
        (root / ".claude").mkdir(exist_ok=True)
        if config is not None:
            (root / ".claude" / "doc-freshness.json").write_text(json.dumps(config))

    def _doc(self, root: Path, rel: str, *, validated: str | None, phase: str = "current",
             append_only: bool = False) -> Path:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        fm = ["---"]
        if validated:
            fm.append(f"last-validated: {validated}")
        fm.append(f"phase: {phase}")
        if append_only:
            fm.append("append_only: true")
        fm += ["---", "", "本文", ""]
        p.write_text("\n".join(fm))
        return p

    def _run(self, root: Path):
        return self.run_hook({"hook_event_name": "SessionStart"}, cwd=root,
                             env_extra={"CLAUDE_PROJECT_DIR": str(root)})

    # --- opt-in（既定で鳴らないことが第一の仕様） ---
    def test_silent_without_config(self):
        with TempGitRepo() as root:
            self._doc(root, ".claude/designs/old.md", validated=days_ago(999))
            self.assertSilent(self._run(root))

    def test_silent_when_not_opted_in(self):
        with TempGitRepo() as root:
            self._setup(root, {"sessionStartCheck": False})
            self._doc(root, ".claude/designs/old.md", validated=days_ago(999))
            self.assertSilent(self._run(root))

    # --- 閾値の境界 ---
    def test_current_threshold_boundary(self):
        with TempGitRepo() as root:
            self._setup(root, {"sessionStartCheck": True, "thresholds": {"current": 60}})
            self._doc(root, ".claude/designs/a.md", validated=days_ago(60))
            self.assertSilent(self._run(root), "60 日ちょうどは stale でない")
            self._doc(root, ".claude/designs/a.md", validated=days_ago(61))
            self.assertFired(self._run(root), "stale")

    def test_target_phase_uses_its_own_threshold(self):
        with TempGitRepo() as root:
            self._setup(root, {"sessionStartCheck": True,
                               "thresholds": {"current": 60, "target": 15}})
            self._doc(root, ".claude/designs/t.md", validated=days_ago(20), phase="target")
            self.assertFired(self._run(root), "20日 > 15日")

    def test_phase_missing_is_treated_as_current(self):
        with TempGitRepo() as root:
            self._setup(root, {"sessionStartCheck": True, "thresholds": {"current": 10}})
            p = root / ".claude/designs/n.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"---\nlast-validated: {days_ago(30)}\n---\n\n本文\n")
            self.assertFired(self._run(root))

    # --- 免除 ---
    def test_append_only_is_exempt(self):
        with TempGitRepo() as root:
            self._setup(root, {"sessionStartCheck": True, "thresholds": {"current": 1}})
            self._doc(root, ".claude/adr/a.md", validated=days_ago(999), append_only=True)
            self.assertSilent(self._run(root))

    def test_superseded_phase_is_exempt(self):
        with TempGitRepo() as root:
            self._setup(root, {"sessionStartCheck": True, "thresholds": {"current": 1}})
            self._doc(root, ".claude/designs/s.md", validated=days_ago(999), phase="superseded")
            self.assertSilent(self._run(root))

    def test_missing_last_validated_is_left_to_frontmatter_guard(self):
        with TempGitRepo() as root:
            self._setup(root, {"sessionStartCheck": True, "thresholds": {"current": 1}})
            self._doc(root, ".claude/designs/m.md", validated=None)
            self.assertSilent(self._run(root))

    def test_no_frontmatter_is_left_to_frontmatter_guard(self):
        with TempGitRepo() as root:
            self._setup(root, {"sessionStartCheck": True, "thresholds": {"current": 1}})
            p = root / ".claude/designs/x.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("# 見出しだけ\n")
            self.assertSilent(self._run(root))

    def test_counts_multiple_stale_docs(self):
        with TempGitRepo() as root:
            self._setup(root, {"sessionStartCheck": True, "thresholds": {"current": 1}})
            for i in range(3):
                self._doc(root, f".claude/designs/d{i}.md", validated=days_ago(99))
            self.assertFired(self._run(root), "3 件")

    def test_broken_config_falls_back_to_defaults(self):
        """config が壊れていても走査が止まらない（既定閾値に倒す）."""
        with TempGitRepo() as root:
            (root / ".claude").mkdir(exist_ok=True)
            (root / ".claude" / "doc-freshness.json").write_text("{ 壊れている")
            self._doc(root, ".claude/designs/a.md", validated=days_ago(999))
            res = self._run(root)
            self.assertNotEqual(res.returncode, 2)

    def test_missing_target_dirs_do_not_crash(self):
        with TempGitRepo() as root:
            self._setup(root, {"sessionStartCheck": True})
            self.assertSilent(self._run(root))


if __name__ == "__main__":
    unittest.main()
