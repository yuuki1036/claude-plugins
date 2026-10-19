#!/usr/bin/env python3
"""コミットへ進む導線が `dev-workflow:git-commit-helper` を通る、という文言契約のテスト.

self-review の「このまま」・review-guide の `次の一手: コミットへ`・軽量フローの Step 5・feature-dev の Phase 7・
worktree-teardown の未コミット変更の選択肢に従って進むと、`git commit` を直接打って git-commit-helper の手順
（分割判定・protected branch の確認・メッセージの規約）を飛ばす回があった。どの導線も skill を名前で呼ぶ。

command の `dev-workflow:commit` は skill と名前が違うので、呼ぶと command 本文が返る（#219 と同じ型）。
command 本文には SKILL.md への Read 誘導を置き、呼び出し側は skill を直接呼ぶ。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DW = REPO / "dev-workflow"
HELPER = "`dev-workflow:git-commit-helper`"

CONSUMERS = {
    "self-review": REPO / "code-review" / "skills" / "self-review" / "SKILL.md",
    "review-guide-format": REPO / "code-review" / "references" / "review-guide-format.md",
    "lightweight-flow": REPO / "issue-workflow" / "skills" / "start" / "references" / "lightweight-flow.md",
    "feature-dev": REPO / "feature-dev" / "skills" / "feature-dev" / "SKILL.md",
    "teardown-checklist": DW / "skills" / "worktree-teardown" / "references" / "cleanup-checklist.md",
}


def between(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i:text.index(end, i)]


class SkillExistsTest(unittest.TestCase):
    def test_called_skills_exist(self):
        for name in ("git-commit-helper", "pr-creator"):
            self.assertTrue((DW / "skills" / name / "SKILL.md").is_file(), f"dev-workflow に {name} が無い")


class ConsumersCallTheSkillTest(unittest.TestCase):
    def test_every_commit_route_names_the_skill(self):
        for label, path in CONSUMERS.items():
            self.assertIn(HELPER, path.read_text(encoding="utf-8"), f"{label} のコミット導線が git-commit-helper を呼ばない")

    def test_no_route_invokes_the_commit_command(self):
        """`Skill` で command の `dev-workflow:commit` を起動させない（command 本文が返り、SKILL.md を経由しない）."""
        for label, path in CONSUMERS.items():
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("`dev-workflow:commit` を起動", text, f"{label} が command を起動している")

    def test_lightweight_flow_step5_calls_the_skill(self):
        flow = CONSUMERS["lightweight-flow"].read_text(encoding="utf-8")
        step5 = between(flow, "### Step 5:", "### Step 6:")
        dw1 = next(l for l in step5.splitlines() if l.startswith("- `DW=1`"))
        self.assertIn(f"`Skill` tool で {HELPER} を起動", dw1)

    def test_feature_dev_phase7_routes_commit_and_pr_to_skills(self):
        text = CONSUMERS["feature-dev"].read_text(encoding="utf-8")
        p7 = between(text, "## Phase 7: Summary", "**Event Bus publish")
        self.assertIn(HELPER, p7)
        self.assertIn("`dev-workflow:pr-creator`", p7)
        self.assertIn("plugin-enabled.sh\" dev-workflow", p7, "dev-workflow の有効判定をせずに呼んでいる")

    def test_self_review_keep_as_is_does_not_commit_by_itself(self):
        """「このまま」の説明が「このままコミットする」だと、選んだ直後に `git commit` を打つ回がある."""
        text = CONSUMERS["self-review"].read_text(encoding="utf-8")
        option = next(l for l in text.splitlines() if 'label: "このまま"' in l)
        self.assertNotIn("このままコミットする", option)
        self.assertIn("git-commit-helper", option)
        self.assertIn("**コミットはこの skill でしない**", text)


class AliasCommandReadsSkillTest(unittest.TestCase):
    """`/commit` / `/pr` は名前の違う skill のラッパ。本文で SKILL.md を Read させる（#219）."""

    def test_alias_commands_hop_to_skill(self):
        for cmd, skill in (("commit", "git-commit-helper"), ("pr", "pr-creator")):
            text = (DW / "commands" / f"{cmd}.md").read_text(encoding="utf-8")
            body = text.split("\n---\n", 1)[1]
            self.assertIn(f"${{CLAUDE_PLUGIN_ROOT}}/skills/{skill}/SKILL.md", body, f"/{cmd} が SKILL.md を読ませない")


if __name__ == "__main__":
    unittest.main()
