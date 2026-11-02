#!/usr/bin/env python3
"""issue-workflow issue-create の `--create-only`（起票だけで終える引数）の文言契約テスト.

project-hub の repo hub は、lead が hub のセッションで issue-create を `--create-only` 付きで呼び、
最後の `起票だけで終えた:` / `起票せずに終えた:` の行で引数が効いたか（issue-workflow が古くないか）を見分ける
（`.claude/designs/20261102-project-hub-repo-hub.md` の「起票と Issue の保守」）。
契約は終わり方で決めてある。該当する Phase の本文に次の 2 つが書いてあるかを見る: Phase 6 の書き込みの後
（ブランチ作成・feature-dev 連携・次のアクション・spec の選択）に進まないこと / 承認を Phase 6 の 1 回に絞ること。
否定の向きを取り違えた書き換えでも通らないよう、`--create-only` と否定の語を同じ行で確かめる。
モデルが本当にそこで止まるかはここでは確かめられない（実機で確かめる）。
節は番号ではなく見出しの名前と並び順で探す（番号は Phase の挿入で動く）。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / "issue-workflow" / "skills" / "issue-create" / "SKILL.md"
COMMAND = REPO / "issue-workflow" / "commands" / "issue-create.md"

FLAG = "--create-only"
END_PREFIX = "起票だけで終えた:"
ABORT_PREFIX = "起票せずに終えた:"
STEPS = ("ブランチ作成", "feature-dev 連携", "次のアクション", "spec の選択")
WRITE_PHASE = "Issue ファイル生成"
# 入力が足りないときの確認だけを持つ Phase。承認ではないので `--create-only` でも残す（SKILL.md の「引数」節）
INPUT_PHASES = ("Linear MCP 利用可能性チェック", "プロジェクトスラッグの特定", "Issue ID の確定")
# 利用者に聞く文の書き方。SKILL.md は AskUserQuestion のほか「ユーザーに確認する」「ユーザーに…依頼する」とも書く
QUESTION = re.compile(r"AskUserQuestion|ユーザーに確認|ユーザーから受け取る|ユーザーに[^\n。]*依頼")
SKIPS_QUESTION = re.compile(rf"{re.escape(FLAG)}[^\n]*聞かず")


def frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if m is None:
        raise AssertionError(f"{path.name} に frontmatter が無い")
    return m.group(1)


def body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return text[text.index("\n---\n", 4) + 5:]


def description(path: Path) -> str:
    """frontmatter の description を、折り返しの改行を詰めて返す（`description: >` の複数行も 1 行も）."""
    fm = frontmatter(path)
    m = re.search(r"(?ms)^description:[ \t]*(.*?)(?=^\S)", fm + "\n_:")
    if m is None:
        raise AssertionError(f"{path.name} の frontmatter に description が無い")
    return " ".join(ln.strip() for ln in m.group(1).splitlines())


def phases() -> list[tuple[str, str]]:
    """`### Phase <番号>: <名前>` の見出しごとに (名前, 節の本文) を文書の順で返す."""
    text = SKILL.read_text(encoding="utf-8")
    heads = list(re.finditer(r"(?m)^### Phase [0-9.]+: (.+)$", text))
    return [(m.group(1), text[m.start():(heads[i + 1].start() if i + 1 < len(heads) else len(text))])
            for i, m in enumerate(heads)]


def phase(name: str) -> str:
    """見出しの名前が `name` で始まる節を返す."""
    for title, sec in phases():
        if title.startswith(name):
            return sec
    raise AssertionError(f"issue-create の SKILL.md に「{name}」の Phase が無い")


def before_write() -> list[tuple[str, str]]:
    """Issue ファイル生成より前に並ぶ Phase（書き込みの前に通る節）."""
    secs = phases()
    idx = next((i for i, (title, _) in enumerate(secs) if title.startswith(WRITE_PHASE)), None)
    if idx is None:
        raise AssertionError(f"issue-create の SKILL.md に「{WRITE_PHASE}」の Phase が無い")
    return secs[:idx]


def arguments_section() -> str:
    text = SKILL.read_text(encoding="utf-8")
    m = re.search(r"(?m)^## 引数\n", text)
    if m is None:
        raise AssertionError("issue-create の SKILL.md に「## 引数」節が無い")
    nxt = re.compile(r"(?m)^## ").search(text, m.end())
    return text[m.start():nxt.start() if nxt else len(text)]


class CreateOnlyArgumentTest(unittest.TestCase):
    def test_argument_hint_lists_flag(self):
        m = re.search(r'(?m)^argument-hint:\s*"(.*)"', frontmatter(COMMAND))
        self.assertIsNotNone(m, "command に argument-hint が無い")
        self.assertIn(FLAG, m.group(1))

    def test_both_descriptions_mention_flag(self):
        # 同名ペアでスキル選択に載るのは command 側（CLAUDE.md の Gotchas）。片方だけ直すと食い違う
        for path in (SKILL, COMMAND):
            with self.subTest(path=path.name):
                self.assertIn(FLAG, description(path))

    def test_end_lines_are_defined_in_arguments_section(self):
        sec = arguments_section()
        self.assertIn(FLAG, sec)
        fenced = re.findall(r"(?ms)^ *```\n(.*?)^ *```", sec)
        lines = [ln.strip() for block in fenced for ln in block.splitlines()]
        self.assertEqual([ln for ln in lines if ln.startswith((END_PREFIX, ABORT_PREFIX))],
                         [f"{END_PREFIX} {{ISSUE-ID}} {{Issue ファイルの絶対パス}}", f"{ABORT_PREFIX} {{理由}}"],
                         "終わりの 2 行の書式がフェンスの中に 1 つずつ定義されていない")

    def test_skipped_steps_match_between_skill_and_command(self):
        # SKILL.md を読み損ねても、command 本文だけで書き込みで終えることと終わりの行が分かるようにする。
        # 進まない手順の列挙は 2 か所に複製されているので、片方だけ増減したらここで落とす
        text = body(COMMAND)
        self.assertRegex(text, rf"{re.escape(FLAG)}[^\n]*進まず", "command 本文に `--create-only` で進まない旨が無い")
        self.assertIn(END_PREFIX, text)
        self.assertIn(ABORT_PREFIX, text)
        sec = arguments_section()
        for step in STEPS:
            with self.subTest(step=step):
                self.assertIn(step, text)
                self.assertIn(step, sec)

    def test_issue_is_written_as_backlog(self):
        sec = phase(WRITE_PHASE)
        self.assertRegex(sec, rf"status: in-progress[^\n]*{re.escape(FLAG)}[^\n]*backlog",
                         "Phase 6 の frontmatter に `--create-only` のときの backlog が無い")
        self.assertRegex(body(COMMAND), r"status: backlog")

    def test_postprocess_ends_after_reporting_the_path(self):
        sec = phase("後処理")
        first = sec[sec.index("\n1. "):sec.index("\n2. ")]
        self.assertIn(FLAG, first, "Phase 7 の 1 に `--create-only` で終える指示が無い")
        self.assertIn("ここで終える", first)
        self.assertIn(END_PREFIX, first)

    def test_spec_selection_is_not_entered(self):
        sec = phase("spec 選択")
        intro = sec[:sec.index("\n1. ")]
        self.assertRegex(intro, rf"{re.escape(FLAG)}[^\n]*入らない",
                         "Phase 8 の冒頭に `--create-only` の回は入らないと書いていない")

    def test_the_only_approval_handles_deferred_replies(self):
        sec = phase(WRITE_PHASE)
        approval = sec[sec.index("\n4. "):]
        self.assertIn(FLAG, approval, "Phase 6 の 4 に `--create-only` のときの承認の扱いが無い")
        self.assertIn(ABORT_PREFIX, approval)

    def test_every_question_before_writing_is_handled(self):
        # 承認を Phase 6 の 1 回に絞るので、書き込みより前の Phase で利用者に聞くなら、その Phase に
        # `--create-only` のときは聞かない行が要る（入力の確認だけを持つ Phase は逆に、聞かない行を持たない）。
        # 拾えるのは QUESTION の書き方で書いた質問だけ
        checked = []
        for title, sec in before_write():
            with self.subTest(phase=title):
                if title.startswith(INPUT_PHASES):
                    self.assertIsNone(SKIPS_QUESTION.search(sec), "入力の確認まで `--create-only` で省いている")
                    continue
                if QUESTION.search(sec) is None:
                    continue
                checked.append(title)
                self.assertRegex(sec, SKIPS_QUESTION)
        for name in ("テンプレート選択", "Issue 情報のヒアリング", "コードベース現状確認"):
            with self.subTest(expected=name):
                self.assertTrue(any(t.startswith(name) for t in checked), f"「{name}」の質問を検査していない")
        for name in INPUT_PHASES:
            with self.subTest(input_phase=name):
                self.assertTrue(any(t.startswith(name) for t, _ in before_write()),
                                f"入力の確認の Phase「{name}」が書き込みの前に無い")


if __name__ == "__main__":
    unittest.main()
