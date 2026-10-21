#!/usr/bin/env python3
"""ui-verify の確認（dev server の起動許可・期待ユーザー・ケース表・backend の隔離・既存ブラウザの停止）の契約テスト.

**何を守るか**: AskUserQuestion は無操作のまま自動続行する（askUserQuestionTimeout）ことがあり、その回答を
許可と読むと、利用者が見ていない間に port を占有し、自動続行の回答を期待ユーザーとして記録して次の実行へ
引き継ぎ、ケース表を確定させて実行し、実 Chrome プロファイルで破壊的操作を解禁し、別セッションのブラウザを止める。
既存ブラウザの停止確認にだけあった「自動続行の回答は確認ではない」を残りの確認にも置き、
`--caller` で呼ばれた回も省かないことを文言で固定する。回答が自動続行だったかは実行時にしか分からず、
hook で判定できない（ADR-20261020221214 の適用方法）ので、手順の文言が唯一の歯止めになる。
1 件も実行しなかった回に pending flag を `verified-snap` で上書きしない（commit 前の gate hook を黙らせない）ことも見る。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
UI_VERIFY = REPO / "dev-workflow" / "skills" / "ui-verify" / "SKILL.md"
AUTO = "askUserQuestionTimeout"


def section(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]


def line_starting(text: str, prefix: str) -> str:
    found = [l for l in text.splitlines() if l.lstrip().startswith(prefix)]
    if len(found) != 1:
        raise AssertionError(f"{prefix!r} で始まる行が 1 行でない: {len(found)} 行")
    return found[0]


class AutoContinueIsNotConsentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = UI_VERIFY.read_text(encoding="utf-8")

    def test_dev_server_start_needs_an_explicit_answer(self):
        step0 = section(self.text, "### Step 0:", "### Step 1:")
        rule = next((p for p in step0.split("\n\n") if AUTO in p), None)
        self.assertIsNotNone(rule, "Step 0 の表の許可・確認に自動続行の扱いが無い")
        for phrase in ("起動しない", "占有側を止めない", "worktree-setup を走らせない", "`ours` と見なさない",
                       "`--caller` の回も省かない"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rule)
        step2 = line_starting(self.text, "3. **ユーザーに起動許可を確認**")
        for phrase in (AUTO, "起動しない", "`--caller`", "`UI_VERIFY_BROWSER=unselected`"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, step2)
        detect = section(self.text, "##### 検出ロジック", "### Step 3:")
        self.assertIn("自動続行の回答は許可ではない", line_starting(detect, "- `SERVER_MATCH=none`"))

    def test_unselected_is_a_declared_browser_value(self):
        """起動を断った回に返す値は、呼び出し元が読む (f) の定義にある値に限る."""
        decl = line_starting(self.text, "UI_VERIFY_BROWSER=")
        self.assertIn("unselected", decl.split("=", 1)[1].split("|"))

    def test_case_table_needs_an_explicit_answer(self):
        cases = section(self.text, "##### (b) ケース列挙", "##### (c) 実行と判定")
        para = line_starting(cases, "列挙したケース表はユーザーに提示して")
        for phrase in (AUTO, "実行しない", "`blocked: ケース表の確認なし`", "`--caller` の回も省かない",
                       "pending flag を `verified-snap` で上書きしない"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, para)

    def test_pending_flag_stays_unverified_when_nothing_ran(self):
        """pass も fail も 0 件の回は上書きしない. 1 件でも実行した回の上書きは残す（対）."""
        record = section(self.text, "##### (e) verification.md への記録", "##### (f)")
        line = line_starting(record, "- 記録後に pending flag を")
        for phrase in ("`verified-snap` で上書きする", "pass も fail も 0 件の回", "は上書きしない",
                       "`unverified` のまま"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, line)
        step4 = line_starting(self.text, "- **pending flag の更新**")
        self.assertIn("verify で pass も fail も 0 件の回は上書きしない", step4)
        row = line_starting(self.text, "| `verified-snap` |")
        self.assertIn("verify は pass か fail が 1 件以上の回だけ", row)

    def test_expected_user_needs_an_explicit_answer(self):
        """自動続行の回答を期待ユーザーとして書くと、2 回目以降の実行に引き継がれる."""
        line = line_starting(self.text, "- **期待ユーザーの確認**")
        for phrase in (AUTO, "`expected_user` を null のまま", "`期待ユーザー未確認`", "`--caller` の回も省かない"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, line)

    def test_backend_isolation_needs_an_explicit_answer(self):
        """自動続行の回答で `confirmed` にすると、利用者の実 Chrome プロファイルで破壊的操作が解禁される."""
        line = line_starting(self.text, "- `--autoConnect` / Claude in Chrome")
        for phrase in (AUTO, "確認とみなさず `unconfirmed`", "`blocked: 書き込み先未確認`",
                       "`--caller` の回も省かない"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, line)

    def test_browser_stop_keeps_its_rule(self):
        self.assertIn(AUTO, line_starting(self.text, "- `stop` を呼ぶのは"))

    def test_absolute_rules_name_all_confirmations(self):
        rules = section(self.text, "## 絶対厳守ルール", "## Additional Resources")
        line = line_starting(rules, "- dev server の起動許可・期待ユーザーの確認・ケース表の確認・"
                                    "backend の隔離の確認・既存ブラウザの停止確認は")
        for phrase in (AUTO, "起動しない", "期待ユーザーとして記録しない", "実行しない", "破壊的操作を解禁しない",
                       "止めない", "`--caller` で呼ばれた回も"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, line)

    def test_caller_row_does_not_skip_confirmations(self):
        row = line_starting(self.text, "| `--caller=")
        self.assertIn("確認は省かない", row)
        for name in ("dev server の起動許可", "ケース表の確認", "期待ユーザー", "backend の隔離の確認",
                     "既存ブラウザの停止確認"):
            with self.subTest(name=name):
                self.assertIn(name, row)


if __name__ == "__main__":
    unittest.main()
