#!/usr/bin/env python3
"""issue-workflow 軽量フローの文言契約テスト（Step 4 の読み合わせ）.

軽量フローは `code-review:review-guide` を名前と引数で呼び、締めの `self-review 以降の変更:` の行で
2 回目の self-review を回すかを決める。どちらも code-review 側の文言なので、向こうで名前や値が
変わったらここで気づけるよう突き合わせる。Step の数は見出しのほか TodoWrite の指示と start の F7 にも書かれているので、3 つを突き合わせる。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FLOW = REPO / "issue-workflow" / "skills" / "start" / "references" / "lightweight-flow.md"
START = REPO / "issue-workflow" / "skills" / "start" / "SKILL.md"
GUIDE = REPO / "code-review" / "skills" / "review-guide" / "SKILL.md"
FORMAT = REPO / "code-review" / "references" / "review-guide-format.md"
COMMAND = REPO / "code-review" / "commands" / "review-guide.md"

CLOSING_KEY = "self-review 以降の変更:"
VALUES = ("あり", "なし", "不明")


def between(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i:text.index(end, i)]


def step4() -> str:
    return between(FLOW.read_text(encoding="utf-8"), "### Step 4: 読み合わせ", "### Step 5:")


class WalkthroughCallTest(unittest.TestCase):
    """呼び出す skill と引数が review-guide の宣言と合っている."""

    def test_invokes_review_guide_with_walkthrough(self):
        s = step4()
        self.assertIn("`code-review:review-guide`", s)
        self.assertRegex(s, r"--base <[^>]+> --walkthrough")

    def test_review_guide_still_declares_arguments(self):
        """引数の宣言行だけを見る（description の散文にも同じ語があるので frontmatter 全体では外れても気づけない）.

        同名 command があるので `Skill` で呼ぶと command 本文が返る（#219）。skill と command の両方を見る.
        """
        decl = {
            GUIDE: r"(?m)^\s*引数: (.+)$",
            COMMAND: r"(?m)^argument-hint: (.+)$",
        }
        for path, pattern in decl.items():
            m = re.search(pattern, path.read_text(encoding="utf-8"))
            self.assertIsNotNone(m, f"{path.name} に引数の宣言が無い")
            for arg in ("--walkthrough", "--base <ref>"):
                self.assertIn(arg, m.group(1), f"{path.name} の引数から {arg} が消えた")


class ClosingLineTest(unittest.TestCase):
    """分岐に使う締めの行の文字列と値が review-guide-format.md の正本と一致する."""

    def test_key_and_values_match_format(self):
        closing = between(FORMAT.read_text(encoding="utf-8"), "## 読み合わせの締め", "## 誤ガイド抑制")
        line = next((ln for ln in closing.splitlines() if ln.startswith(CLOSING_KEY)), None)
        self.assertIsNotNone(line, f"review-guide-format.md の締めから `{CLOSING_KEY}` の行が消えた")
        s = step4()
        self.assertIn(f"締めの `{CLOSING_KEY}` の行で分岐する", s)
        for value in VALUES:
            self.assertIn(value, line, f"締めの値から {value} が消えた")
            self.assertRegex(s, rf"(?m)^- `{value}", f"軽量フローに {value} の分岐が無い")

    def test_second_self_review_takes_base_only(self):
        """2 回目は修正確認の再レビューではないので、--focus / --rereview / --embed を付けない."""
        s = step4()
        branch = between(s, "- `あり`", "\n- `なし`")
        self.assertIn("`--focus` / `--rereview` / `--embed` を付けない", branch)


class StepCountTest(unittest.TestCase):
    """「以下 N Step」・見出し・start F7 の「その N Step（…）」がずれない."""

    def test_counts_agree(self):
        flow = FLOW.read_text(encoding="utf-8")
        declared = int(re.search(r"以下 (\d+) Step", flow).group(1))
        headings = [int(n) for n in re.findall(r"(?m)^### Step (\d+):", flow)]
        self.assertEqual(headings, list(range(1, declared + 1)))
        m = re.search(r"その (\d+) Step（([^）]+)）", START.read_text(encoding="utf-8"))
        self.assertIsNotNone(m, "start SKILL.md に「その N Step（…）」が無い")
        self.assertEqual(int(m.group(1)), declared)
        self.assertEqual(len(m.group(2).split("→")), declared, m.group(2))


if __name__ == "__main__":
    unittest.main()
