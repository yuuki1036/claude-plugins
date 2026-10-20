#!/usr/bin/env python3
"""issue-workflow 軽量フローの文言契約テスト（Step 3 の動作確認・Step 5 の読み合わせ）.

軽量フローは `code-review:review-guide` を名前と引数で呼び、締めの `self-review 以降の変更:` の行で
2 回目の self-review を回すかを、`変異テスト:` の行で変異テストを提案するかを決める（#307）。
動作確認は `dev-workflow:ui-verify` を `--caller` 付きで呼び、最後の `UI_VERIFY_RESULT=` の行で分岐する（#306）。
どれも他プラグイン側の文言なので、向こうで名前や値が変わったらここで気づけるよう突き合わせる。
Step の数は見出しのほか TodoWrite の指示と start の F7 にも書かれているので、3 つを突き合わせる。
番号は Step の挿入で動くので、節は見出しの名前で探す。

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
UI_VERIFY = REPO / "dev-workflow" / "skills" / "ui-verify" / "SKILL.md"
UI_VERIFY_COMMAND = REPO / "dev-workflow" / "commands" / "ui-verify.md"
UI_PATHS = REPO / "dev-workflow" / "scripts" / "lib" / "ui-paths.sh"
MUTATION_TOOL = REPO / ".claude-plugin" / "scripts" / "mutation-test.py"

CLOSING_KEY = "self-review 以降の変更:"
VALUES = ("あり", "なし", "不明")
MUTATION_KEY = "変異テスト:"
MUTATION_VALUES = ("提案する", "不要", "道具なし")
MUTATION_OUTCOMES = ("生存 N 件", "一部未実行", "未計測", "判定不能")
MUTATION_PIN = re.compile(
    r"<!-- SSOT: code-review/references/review-guide-format\.md#変異テストの提案 @[0-9a-f]{8} -->")


def between(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i:text.index(end, i)]


def step(name: str) -> str:
    """見出しが `### Step <N>: <name>` の節を、次の `### Step` の見出しの手前まで返す."""
    flow = FLOW.read_text(encoding="utf-8")
    m = re.search(rf"(?m)^### Step \d+: {re.escape(name)}", flow)
    if m is None:
        raise AssertionError(f"軽量フローに「{name}」の Step が無い")
    nxt = re.compile(r"(?m)^### Step \d+:").search(flow, m.end())
    return flow[m.start():nxt.start() if nxt else len(flow)]


def walkthrough_step() -> str:
    return step("読み合わせ")


def report() -> str:
    flow = FLOW.read_text(encoding="utf-8")
    return flow[flow.index("## 報告"):]


def format_closing() -> str:
    return between(FORMAT.read_text(encoding="utf-8"), "## 読み合わせの締め", "## 回し直すかの判断")


def ui_verify_result_values() -> list[str]:
    """ui-verify の SKILL.md にある `UI_VERIFY_RESULT=` の定義行（値を `|` で並べた行）から値を独立に読む."""
    line = next((ln.strip() for ln in UI_VERIFY.read_text(encoding="utf-8").splitlines()
                 if ln.strip().startswith("UI_VERIFY_RESULT=") and "|" in ln), None)
    if line is None:
        raise AssertionError("ui-verify の SKILL.md から `UI_VERIFY_RESULT=` の定義行が消えた")
    return [v.strip(" <>`") for v in line.split("=", 1)[1].split("|")]


def ui_verify_browser_values() -> list[str]:
    """ui-verify の SKILL.md にある `UI_VERIFY_BROWSER=` の定義行から値を独立に読む."""
    line = next((ln.strip() for ln in UI_VERIFY.read_text(encoding="utf-8").splitlines()
                 if ln.strip().startswith("UI_VERIFY_BROWSER=") and "|" in ln), None)
    if line is None:
        raise AssertionError("ui-verify の SKILL.md から `UI_VERIFY_BROWSER=` の定義行が消えた")
    return [v.strip(" <>`") for v in line.split("=", 1)[1].split("|")]


def ui_script_dirs_and_exts() -> tuple[list[str], list[str]]:
    """ui-paths.sh の `UI_SCRIPT_ERE` から、画面の層のディレクトリと拡張子を読む（`stores?` は散文で `store(s)` と書く）."""
    line = next((ln for ln in UI_PATHS.read_text(encoding="utf-8").splitlines()
                 if ln.startswith("UI_SCRIPT_ERE=")), None)
    if line is None:
        raise AssertionError("ui-paths.sh から `UI_SCRIPT_ERE=` が消えた")
    groups = re.findall(r"\(([^()]*)\)", line)
    dirs = [d.replace("s?", "(s)") for d in groups[1].split("|")]
    return dirs, groups[-1].split("|")


def sentences_mentioning(text: str, word: str) -> list[str]:
    return [s for s in re.split(r"[。\n]", text) if word in s]


class WalkthroughCallTest(unittest.TestCase):
    """呼び出す skill と引数が review-guide の宣言と合っている."""

    def test_invokes_review_guide_with_walkthrough(self):
        s = walkthrough_step()
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
        s = walkthrough_step()
        self.assertIn(f"締めの `{CLOSING_KEY}` の行で分岐する", s)
        for value in VALUES:
            self.assertIn(value, line, f"締めの値から {value} が消えた")
            self.assertRegex(s, rf"(?m)^- `{value}", f"軽量フローに {value} の分岐が無い")

    def test_second_self_review_takes_base_only(self):
        """2 回目は修正確認の再レビューではないので、--focus / --rereview / --embed を付けない."""
        s = walkthrough_step()
        branch = between(s, "- `あり`", "\n- `なし`")
        self.assertIn("`--focus` / `--rereview` / `--embed` を付けない", branch)

    def test_skips_self_review_only_on_deterministic_next_step(self):
        """`あり` でも締めの `次の一手:` が `決定的な検証` なら Step 2 だけ通す（#304）。先頭の文言は format の正本と突き合わせる."""
        closing = between(FORMAT.read_text(encoding="utf-8"), "## 読み合わせの締め", "## 誤ガイド抑制")
        line = next((ln for ln in closing.splitlines() if ln.startswith("次の一手:")), None)
        self.assertIsNotNone(line, "review-guide-format.md の締めから `次の一手:` の行が消えた")
        self.assertIn("決定的な検証", line)
        branch = between(walkthrough_step(), "- `あり`", "\n- `なし`")
        self.assertIn("`次の一手:` が `決定的な検証` で始まるなら、Step 2（検証）だけ", branch)
        self.assertIn("それ以外なら Step 2（検証）と Step 4（self-review）をもう一度通す", branch)


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


class UiVerifyStepTest(unittest.TestCase):
    """Step 3 の動作確認は ui-verify を `--caller` で呼び、`UI_VERIFY_RESULT=` の全値で分岐する（GitHub issue #306）."""

    def test_step3_is_ui_verify_right_after_verification(self):
        names = re.findall(r"(?m)^### Step \d+: (\S+)", FLOW.read_text(encoding="utf-8"))
        self.assertEqual(names[1:4], ["検証", "動作確認", "セルフレビュー"],
                         "動作確認が検証の直後・セルフレビューの前に無い")

    def test_invokes_ui_verify_with_caller(self):
        """`DW=1` なら無条件に呼ぶ。UI に影響するかの判定を呼び出し元に複製しない（拡張子などの条件を挟ませない）."""
        s = step("動作確認")
        dw1 = next((ln for ln in s.splitlines() if ln.startswith("- `DW=1`")), None)
        self.assertIsNotNone(dw1, "動作確認の Step に `DW=1` の分岐が無い")
        self.assertTrue(
            dw1.startswith("- `DW=1`: `Skill` tool で `dev-workflow:ui-verify` を `verify --caller=lightweight-flow` で起動"),
            f"`DW=1` の呼び出しの前に条件が挟まっている: {dw1}")
        self.assertIn("ここに複製しない", s)

    def test_fail_is_left_to_the_user(self):
        """`fail` を報告に残すだけで素通りしない。直すか承知で進むかは利用者が決める."""
        fail = between(step("動作確認"), "- `fail`", "\n  - ")
        self.assertIn("利用者に決めてもらう", fail)
        self.assertIn("Step 2 から", fail, "直す回に検証からやり直していない")

    def test_ui_verify_still_declares_caller(self):
        """同名 command があるので `Skill` で呼ぶと command 本文が返る（#219）。SKILL.md と command の両方の `引数:` を見る.

        `lightweight-flow` の値は SKILL.md の `--caller` を説明する行のどれかにあること（値の綴りがずれると
        ui-verify が呼び出し元を見分けられない）.
        """
        for path in (UI_VERIFY, UI_VERIFY_COMMAND):
            m = re.search(r"引数: ([^\n\"]+)", path.read_text(encoding="utf-8"))
            self.assertIsNotNone(m, f"{path.name} に `引数:` が無い")
            self.assertIn("--caller", m.group(1), f"{path.name} の引数から --caller が消えた")
        caller_lines = [ln for ln in UI_VERIFY.read_text(encoding="utf-8").splitlines() if "--caller" in ln]
        self.assertTrue([ln for ln in caller_lines if "lightweight-flow" in ln],
                        "ui-verify の --caller の値に lightweight-flow が無い")

    def test_branches_on_every_result_value(self):
        values = ui_verify_result_values()
        self.assertEqual(set(values), {"pass", "fail", "blocked", "skipped"}, values)
        s = step("動作確認")
        for value in values:
            self.assertRegex(s, rf"(?m)^\s+- `{value}`", f"動作確認に {value} の分岐が無い")

    def test_keys_used_are_declared_by_ui_verify(self):
        """呼び出し元が読む `UI_VERIFY_*` のキーは、ui-verify が出すキーに限る（綴りのずれで黙って読み落とさない）."""
        declared = set(re.findall(r"(?m)^\s*(UI_VERIFY_[A-Z]+)=", UI_VERIFY.read_text(encoding="utf-8")))
        used = set(re.findall(r"(UI_VERIFY_[A-Z]+)=", FLOW.read_text(encoding="utf-8")))
        self.assertTrue(used, "軽量フローが `UI_VERIFY_*` の行を読んでいない")
        self.assertLessEqual(used, declared, f"ui-verify が出さないキーを読んでいる: {used - declared}")

    def test_blocked_without_browser_falls_back_to_manual(self):
        s = step("動作確認")
        blocked = between(s, "- `blocked`", "\n  - ")
        self.assertIn("`UI_VERIFY_BROWSER=none`", blocked)
        self.assertIn("`DW=0` の手動手順", blocked)
        self.assertIn("判定し直さない", blocked, "ui-verify が下した判定を呼び出し元が覆しうる")
        self.assertIn("`UI_VERIFY_RESULT=` の行が出ない", s, "旧版の dev-workflow の扱いが無い")

    def test_unselected_is_not_sent_to_manual_check(self):
        """基盤を選ぶ前に止まった blocked（dev server の起動を断られた等）で、手動確認を頼み直さない."""
        blocked = between(step("動作確認"), "- `blocked`", "\n  - ")
        key = "`UI_VERIFY_BROWSER=unselected`"
        self.assertIn(key, blocked, "基盤を選ぶ前に止まった回の分岐が無い")
        self.assertLess(blocked.index("`UI_VERIFY_BROWSER=none`"), blocked.index(key))
        rest = blocked[blocked.index(key):]
        self.assertIn("頼み直さない", rest)
        self.assertNotIn("手動手順", rest, f"unselected を手動手順に回している: {rest}")

    def test_browser_values_used_are_declared_by_ui_verify(self):
        """呼び出し元が分岐に使う `UI_VERIFY_BROWSER=` の値は、ui-verify が出す値に限る."""
        declared = set(ui_verify_browser_values())
        used = set(re.findall(r"UI_VERIFY_BROWSER=([a-z-]+)", FLOW.read_text(encoding="utf-8")))
        self.assertEqual(used, {"none", "unselected"}, used)
        self.assertLessEqual(used, declared, f"ui-verify が出さない値を読んでいる: {used - declared}")

    def test_ui_file_definition_matches_ui_paths(self):
        """ui-verify を通さずに判断する箇所の「画面のファイル」は ui-paths.sh の式に揃える.

        旧い散文（コンポーネント・スタイル・テンプレート）は hooks/ stores/ 配下の .ts を数えず、
        ui-verify が画面の変更と判定したものを呼び出し元が覆していた.
        """
        flow = FLOW.read_text(encoding="utf-8")
        para = between(step("動作確認"), "ui-verify を通さずに判断する箇所", "\n\n")
        dirs, exts = ui_script_dirs_and_exts()
        self.assertGreater(len(dirs), 5, dirs)
        for d in dirs:
            self.assertIn(f"`{d}/`", para, f"画面の層のディレクトリ {d}/ が定義に無い")
        for e in exts:
            self.assertIn(f"`.{e}`", para, f"拡張子 .{e} が定義に無い")
        self.assertNotIn("コンポーネント・スタイル・テンプレート", flow, "旧い散文の定義が残っている")
        self.assertIn("画面のファイルがあるか", step("動作確認")[step("動作確認").index("- `DW=0`"):])
        self.assertIn("画面のファイル（Step 3 の定義）", report().replace("\n", ""))

    def test_has_fallback_when_dev_workflow_is_disabled(self):
        s = step("動作確認")
        dw0 = s[s.index("- `DW=0`"):]
        self.assertIn("手動確認待ち", dw0)
        self.assertIn("UI_VERIFY_REASON", report(), "skip・blocked の理由を報告に残していない")

    def test_walkthrough_rerun_skips_ui_verify(self):
        branch = between(walkthrough_step(), "- `あり`", "\n- `なし`")
        self.assertIn("Step 3 の動作確認は通らない", branch)
        self.assertIn("Step 5 の読み合わせから戻った回は通らない", step("動作確認"))

    def test_report_flags_ui_changes_after_ui_verify(self):
        """Step 3 の後の修正は動作確認を通らないので、画面のファイルに触れたらその事実を残す.

        Step 4（1 回目の self-review）の修正も Step 3 の後に入る。読み合わせ以降だけに限ると落ちる.
        """
        r = report().replace("\n", "")
        self.assertIn("Step 3 の後の変更は動作確認を通していない", r)
        scope = between(r, "Step 3 の後に入れた変更（", "）")
        for fix in ("Step 4 の self-review での修正", "読み合わせでの修正", "2 回目の self-review での修正"):
            self.assertIn(fix, scope, f"{fix} が記録の対象に無い")


class MutationLineTest(unittest.TestCase):
    """締めの `変異テスト:` の行で、コミットの前に変異テストを提案するかを決める（GitHub issue #307）.

    値は review-guide-format.md の正本と突き合わせる。承認の取り方（通常のメッセージで聞き、
    `AskUserQuestion` にしない）は feature-dev 側と同じ理由で固定する.
    """

    def proposal(self) -> str:
        return between(walkthrough_step(), "- `提案する`", "\n- `不要`")

    def test_values_match_format(self):
        line = next((ln for ln in format_closing().splitlines() if ln.startswith(MUTATION_KEY)), None)
        self.assertIsNotNone(line, f"review-guide-format.md の締めに `{MUTATION_KEY}` の行が無い")
        for value in MUTATION_VALUES:
            self.assertIn(value, line, f"締めの `{MUTATION_KEY}` の値から {value} が消えた")
        s = walkthrough_step()
        self.assertIn(f"締めの `{MUTATION_KEY}` の行で分岐する", s)
        self.assertRegex(s, r"(?m)^- `提案する`")
        self.assertRegex(s, r"(?m)^- `不要` / `道具なし`")

    def test_runs_only_after_approval(self):
        p = self.proposal()
        self.assertIn("承認の返信が無ければ回さない", p)
        self.assertIn("run_in_background", p)
        self.assertIn("通常のメッセージで聞いて", p)
        mentions = sentences_mentioning(p, "AskUserQuestion")
        self.assertTrue(mentions, "AskUserQuestion にしないことが書かれていない")
        for s in mentions:
            self.assertIn("しない", s, f"変異テストの承認を AskUserQuestion で取っている: {s}")

    def test_comes_after_self_review_branches(self):
        s = walkthrough_step()
        branch = s.index(f"締めの `{MUTATION_KEY}` の行で分岐する")
        self.assertLess(s.index("- `不明"), branch)
        self.assertLess(s.index("締めの行が出ないまま"), branch)

    def test_added_tests_get_verification_not_self_review(self):
        p = self.proposal()
        self.assertIn("Step 2（検証）をもう一度", p)
        self.assertIn("self-review は回し直さない", p)

    def test_reports_four_outcomes(self):
        """結果は 4 区分で書く。exit 0 は、上限・タイムアウトで一部しか回していない回と未計測の回でも返る.

        3 区分（生存 / 未計測 / 判定不能）だと、25 個だけ回して全部殺した回が「生存 0」と報告される.
        """
        p = self.proposal()
        for label in MUTATION_OUTCOMES:
            self.assertRegex(p, rf"(?m)^\s+- `{re.escape(label)}`", f"変異テストの結果に {label} の区分が無い")
        partial = between(p, "- `一部未実行`", "\n    - ")
        self.assertIn("「生存 0」と書かず", partial)
        self.assertIn("実行した数と未実行の数", partial)
        aborted = between(p, "- `判定不能`", "\n  - ")
        self.assertIn("stderr に中断の FATAL", aborted, "途中で止まった exit 1 を判定不能に入れていない")
        self.assertIn("変異が当たったまま", aborted)
        self.assertIn("Step 6 へ進まない", aborted, "変異が残ったツリーのままコミットへ進みうる")
        r = report().replace("\n", "")
        for label in MUTATION_OUTCOMES:
            self.assertIn(f"`{label}`", r, f"報告に {label} の区分が無い")

    def test_quoted_output_exists_in_the_declared_tool(self):
        """区分の手がかりに引く出力の文言は、この repo の宣言が回す mutation-test.py の出力と突き合わせる."""
        p = self.proposal()
        tool = MUTATION_TOOL.read_text(encoding="utf-8")
        for phrase in ("上限で未実行", "タイムアウト", "変異が当たったまま"):
            self.assertIn(f"「{phrase}", p)
            self.assertIn(phrase, tool, f"mutation-test.py の出力から「{phrase}」が消えた")

    def test_tool_output_files_are_kept_out_of_the_commit(self):
        p = self.proposal()
        self.assertIn("`git status --porcelain` の出力を控えてから", p, "回す前の状態を控えていない")
        self.assertIn("回す前と後の `git status --porcelain` を突き合わせ", p)
        self.assertIn("コミットに混ぜない", p)

    def test_summary_is_pinned_to_the_canonical(self):
        """変異テストの分岐は review-guide-format.md「変異テストの提案」の要約。正本が変わったら pin の検査で気づく.

        pin は最初の見出しより前に置く（docs/ssot-pin.md）.
        """
        flow = FLOW.read_text(encoding="utf-8")
        m = MUTATION_PIN.search(flow)
        self.assertIsNotNone(m, "変異テストの提案への SSoT pin が無い")
        self.assertLess(m.start(), re.search(r"(?m)^#+ ", flow).start(), "pin が最初の見出しより後にある")

    def test_not_needed_does_not_ask(self):
        s = walkthrough_step()
        not_needed = between(s, "- `不要` / `道具なし`", "\n- ")
        self.assertIn("聞かずに", not_needed)
        absent = s[s.index("- 行が無い"):]
        self.assertIn("何もしない", absent)
        self.assertIn("変異テスト", report(), "変異テストを回さなかった理由を報告に残していない")


if __name__ == "__main__":
    unittest.main()
