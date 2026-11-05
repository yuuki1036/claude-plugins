#!/usr/bin/env python3
"""issue-workflow start の「着手の記録」（backlog → in-progress）の文言契約テスト.

discover の起票と issue-create の `--create-only` は Issue を `status: backlog` で書き、着手を start に任せる。
start が着手で in-progress に移さないと、ダッシュボードと放置検知から漏れ続ける（#364）。
ここでは次を本文で確かめる: 起票側が backlog で書くこと / start に着手の記録の Phase があり、
backlog → in-progress と last_active の書き換えを言うこと / 着手しない WORK_STATE（closed / detached / prunable）では
書き換えないこと / F7（進め方の選択。feature-dev・軽量フローへ処理を渡す）より前に並ぶこと /
`{DATA_DIR}` を git で追跡している repo で既存のブランチへ移る回だけは後回しにし、F7 の締め（起動の直前か F7 を終える時点）で
1 回だけ書き換えること（作業のあるブランチへ移らなかった回は書き換えず案内する）/ Linear 側は変えないこと /
書き換えに使う Edit が allowed-tools にあること。
否定の向きを取り違えた書き換えでも通らないよう、契約の語は動詞まで同じ行で確かめる。
モデルが本当に書き換えるかはここでは確かめられない（実機で確かめる）。
節は番号ではなく見出しの名前と並び順で探す（番号は Phase の挿入で動く）。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKILLS = REPO / "issue-workflow" / "skills"
START = SKILLS / "start" / "SKILL.md"
ISSUE_CREATE = SKILLS / "issue-create" / "SKILL.md"
DISCOVER = SKILLS / "discover" / "SKILL.md"

RECORD_PHASE = "着手の記録"
CHOOSE_PHASE = "進め方の確認"
READ_PHASE = "関連ファイル読み込み"
NOT_STARTED = ("closed", "detached", "prunable")


def phases(path: Path) -> list[tuple[str, str]]:
    """`### Phase <記号><番号>: <名前>` の見出しごとに (名前, 節の本文) を文書の順で返す."""
    text = path.read_text(encoding="utf-8")
    heads = list(re.finditer(r"(?m)^### Phase [A-Z]*[0-9.]+: (.+)$", text))
    return [(m.group(1), text[m.start():(heads[i + 1].start() if i + 1 < len(heads) else len(text))])
            for i, m in enumerate(heads)]


def index_of(path: Path, name: str) -> int:
    for i, (title, _) in enumerate(phases(path)):
        if title.startswith(name):
            return i
    raise AssertionError(f"{path.parent.name} の SKILL.md に「{name}」の Phase が無い")


def section(path: Path, name: str) -> str:
    return phases(path)[index_of(path, name)][1]


class CreatorsWriteBacklogTest(unittest.TestCase):
    def test_issue_create_only_writes_backlog_and_leaves_start_to_start(self):
        text = ISSUE_CREATE.read_text(encoding="utf-8")
        self.assertRegex(text, r"--create-only[^\n]*`backlog`")
        self.assertRegex(text, r"着手は start で行う")

    def test_discover_writes_backlog(self):
        self.assertRegex(DISCOVER.read_text(encoding="utf-8"), r"`status: backlog` ← \*\*必ず backlog\*\*")


class StartRecordsStartTest(unittest.TestCase):
    def test_backlog_is_rewritten_to_in_progress_with_last_active(self):
        sec = section(START, RECORD_PHASE)
        line = next((ln for ln in sec.splitlines() if ln.startswith("1. ")), "")
        self.assertRegex(line, r"`status: backlog`")
        self.assertRegex(line, r"`status` を `in-progress` に[^\n]*書き換える")
        self.assertRegex(line, r"`last_active` を今日の日付")

    def test_not_started_states_are_left_alone(self):
        sec = section(START, RECORD_PHASE)
        line = next((ln for ln in sec.splitlines() if ln.startswith("2. ")), "")
        for state in NOT_STARTED:
            self.assertIn(f"`{state}`", line)
        self.assertRegex(line, r"→ 書き換えない")
        first = next((ln for ln in sec.splitlines() if ln.startswith("1. ")), "")
        for state in NOT_STARTED:
            self.assertIn(f"`{state}`", first)
        self.assertRegex(first, r"のどれでもない →")

    def test_other_statuses_are_left_alone(self):
        sec = section(START, RECORD_PHASE)
        line = next((ln for ln in sec.splitlines() if ln.startswith("3. ")), "")
        for status in ("in-progress", "frozen", "completed", "canceled"):
            self.assertIn(f"`{status}`", line)
        self.assertRegex(line, r"→ 書き換えない")

    def test_only_the_local_file_is_written(self):
        self.assertRegex(section(START, RECORD_PHASE), r"Linear 側のステータスは変えない")

    def test_existing_branch_is_rewritten_after_moving(self):
        # {DATA_DIR} を git で追跡している repo で先に書き換えると、ブランチ側の Issue ファイルを上書きするか git switch が止まる
        sec = section(START, RECORD_PHASE)
        here = next((ln for ln in sec.splitlines() if ln.strip().startswith("- `none`")), "")
        for state in ("none", "here", "moved", "fresh", "branch"):
            self.assertIn(f"`{state}`", here)
        self.assertRegex(here, r"ここで書き換える[^\n]*F7 より前に済ませる")
        later = next((ln for ln in sec.splitlines() if ln.strip().startswith("- 後回しの回")), "")
        self.assertRegex(later, r"git で追跡している repo[^\n]*の `branch` と、選んだ候補がブランチだけの `fresh`")
        for state in ("none", "here", "moved"):
            self.assertNotIn(f"`{state}`", later)
        self.assertRegex(later, r"check-ignore -q \"\{DATA_DIR\}\"` が偽")
        self.assertRegex(later, r"ここでは書き換えない")
        self.assertRegex(later, r"F7 の「Phase F3\.2 の後回しの回」で 1 回だけ行う")

    def test_deferred_rewrite_happens_before_handing_off(self):
        # F7 は feature-dev・軽量フローに処理を渡して戻らないので、締めを起動の後に置くとその経路だけ backlog のまま残る
        sec = section(START, CHOOSE_PHASE)
        lines = sec.splitlines()
        i = next((k for k, ln in enumerate(lines) if ln.startswith("**Phase F3.2 の後回しの回**")), None)
        self.assertIsNotNone(i, "F7 に後回しの回の締めが無い")
        head = lines[i]
        cases = []
        for ln in lines[i + 1:]:
            if not ln.startswith("- "):
                break
            cases.append(ln)
        self.assertEqual(len(cases), 3, "後回しの回の場合分けは 3 つ")
        self.assertRegex(head, r"feature-dev・軽量フローを起動する回はその直前")
        self.assertRegex(head, r"どちらも起動しない回[^\n]*F7 を終える時点")
        self.assertRegex(head, r"起動した後には置かない")
        self.assertRegex(cases[0], r"^- ブランチへ移った回 → 移った先の Issue ファイル（まだ `status: backlog` なら書き換え")
        self.assertRegex(cases[1], r"^- 選んだ候補がブランチだけの `fresh` で、移らなかった回[^\n]*→ 今のチェックアウトの Issue ファイル")
        # 作業のあるブランチへ移らないまま書き換えると、利用者が後で移るときに git switch が止まる
        self.assertRegex(cases[2], r"^- `branch` で移らなかった回[^\n]*→ 書き換えず")
        self.assertRegex(cases[2], r"`/start \{ISSUE-ID\}` し直す")

    def test_moved_rewrites_the_destination(self):
        self.assertRegex(section(START, RECORD_PHASE),
                         r"既存の worktree へ移った回（`moved` と、worktree へ移った `fresh`）は、移り先の Issue ファイルを書き換える")

    def test_choose_phase_returns_to_record_after_redeciding(self):
        sec = section(START, CHOOSE_PHASE)
        redecide = next((pg for pg in sec.split("\n\n") if "`detached`" in pg), "")
        self.assertRegex(redecide, r"worktree を持つ `fresh` なら、先に同 doc の 3 でそこへ移る")
        self.assertRegex(redecide, r"Issue が `status: backlog` なら Phase F3\.2 の 1 を[^\n]*行って")

    def test_edit_is_allowed(self):
        # F3.2 は Edit で書き換える。宣言が無いと承認待ちか拒否で書き換えが落ちる
        for path in (START, REPO / "issue-workflow" / "commands" / "start.md"):
            fm = path.read_text(encoding="utf-8").split("\n---\n", 1)[0]
            self.assertRegex(fm, r"(?m)^  - Edit$", path.name)

    def test_recorded_after_reading_issue_and_before_choosing_how(self):
        # F7 は feature-dev・軽量フローに処理を渡して start に戻らないので、記録はその前に要る
        self.assertLess(index_of(START, READ_PHASE), index_of(START, RECORD_PHASE))
        self.assertLess(index_of(START, RECORD_PHASE), index_of(START, CHOOSE_PHASE))

    def test_report_shows_the_transition(self):
        sec = section(START, "作業準備完了報告")
        self.assertRegex(sec, r"status: backlog → in-progress")
        self.assertRegex(sec, r"後回しの回は「status: backlog（F7 の締めで in-progress にする。作業のあるブランチへ移らずに終える回は")


if __name__ == "__main__":
    unittest.main()
