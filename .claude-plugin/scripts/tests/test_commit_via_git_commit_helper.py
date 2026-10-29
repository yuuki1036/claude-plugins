#!/usr/bin/env python3
"""コミットへ進む導線が `dev-workflow:git-commit-helper` を通る、という文言契約のテスト.

self-review の「このまま」・review-guide の `次の一手: コミットへ`・軽量フローのコミットの Step・feature-dev の Phase 7・
worktree-teardown の未コミット変更の選択肢に従って進むと、`git commit` を直接打って git-commit-helper の手順
（分割判定・protected branch の確認・メッセージの規約）を飛ばす回があった。どの導線も skill を名前で呼ぶ。

command の `dev-workflow:commit` は skill と名前が違うので、呼ぶと command 本文が返る（#219 と同じ型）。
command 本文には SKILL.md への Read 誘導を置き、呼び出し側は skill を直接呼ぶ。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import re
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

    def test_lightweight_flow_commit_step_calls_the_skill(self):
        """節は見出しの名前で探す（Step の挿入で番号が動く。#306 で動作確認が入り 5 → 6 になった）."""
        flow = CONSUMERS["lightweight-flow"].read_text(encoding="utf-8")
        m = re.search(r"(?m)^### Step \d+: コミット$", flow)
        self.assertIsNotNone(m, "軽量フローにコミットの Step が無い")
        nxt = re.compile(r"(?m)^### Step \d+:").search(flow, m.end())
        commit_step = flow[m.start():nxt.start() if nxt else len(flow)]
        dw1 = next(l for l in commit_step.splitlines() if l.startswith("- `DW=1`"))
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


class ReviewOfferBeforeCommitTest(unittest.TestCase):
    """呼び出し元のフローを持たないコミットでも、self-review と読み合わせを提案する.

    提案は軽量フローと feature-dev にしか無く、start を通さないセッション・hub から起動した sub・GitHub の
    Issue の作業では、self-review も review-guide も提案されないままコミットまで進んだ
    """

    def step(self) -> str:
        return between((DW / "skills" / "git-commit-helper" / "SKILL.md").read_text(encoding="utf-8"),
                       "### 1.5 コミット前のレビュー提案", "### 2. コミット分割判定")

    def test_offers_both_reviews_and_skipping(self):
        s = self.step()
        self.assertIn("`AskUserQuestion` で 1 問だけ聞く", s)
        for option in ('"self-review → 読み合わせ (Recommended)"', '"self-review だけ"', '"このままコミット"'):
            self.assertIn(option, s, f"選択肢に {option} が無い")
        self.assertIn("`--base <控えた base_branch> --walkthrough`", s, "読み合わせを self-review と同じ base で回さない")

    def test_does_not_ask_again_after_a_flow_already_reviewed(self):
        s = self.step()
        self.assertIn("今回コミットする変更に self-review か読み合わせ（review-guide の締め）を回した", s,
                      "self-review・読み合わせの後に聞き直す")
        self.assertIn("呼び出し元のフロー（issue-workflow の軽量フロー・feature-dev）から起動された", s,
                      "フローが回さないと決めた回にも聞き直す")
        self.assertIn("使える skill に `code-review:self-review` が無い", s, "code-review が無いのに提案する")
        self.assertIn("機械的な更新だけ", s, "版の bump だけのコミットにも聞く")
        self.assertIn("「レビューは要らない」", s, "利用者が断ったのに聞く")
        self.assertIn("取り直してから 2. へ戻り、この skill の手順でコミットする", s)

    def test_reviews_return_here_instead_of_committing_by_themselves(self):
        """起動した self-review / review-guide が git-commit-helper を起動し直すと、読み合わせの前にコミットが入る."""
        s = self.step()
        self.assertIn("git-commit-helper を起動し直さずにこの 1.5 の続きへ戻る", s)
        self.assertIn("2. へ進まずに終える", s, "コミットを断った回にもコミットへ進む")

    def test_heavy_branches_stop_before_committing(self):
        """検証が赤のまま・変異テストを回しながらコミットへ進まない（変異体は作業ツリーへ直接書かれる）."""
        s = self.step()
        self.assertIn("赤なら 2. へ進まずに結果を示し", s)
        self.assertIn("`次の一手:` が `self-review をもう一度` → self-review を `<控えた base_branch>` だけを引数にもう一度回す", s,
                      "2 回目の self-review を求められてもそのままコミットへ進む")
        self.assertIn("両方に当たる回は `次の一手:` を済ませてから `変異テスト:` を見る", s)
        self.assertIn("この skill からは回さない", s)
        self.assertIn("回すと返されたらコミットせずに終える", s)
        self.assertIn("`askUserQuestionTimeout`）の回答は選ばれたものとみなさない", s)

    def test_ask_user_question_is_allowed_on_both_entry_points(self):
        for path in (DW / "skills" / "git-commit-helper" / "SKILL.md", DW / "commands" / "commit.md"):
            head = path.read_text(encoding="utf-8").split("---")[1]
            self.assertIn("- AskUserQuestion", head, f"{path.name} の allowed-tools に AskUserQuestion が無い")


if __name__ == "__main__":
    unittest.main()
