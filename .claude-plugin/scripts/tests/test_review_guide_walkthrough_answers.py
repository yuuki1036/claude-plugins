#!/usr/bin/env python3
"""review-guide の読み合わせで「答える側」が利用者に確かめる入口を渡す、という文言契約のテスト.

読み合わせは難点とレビュー観点を作った本人がその場で答えるので、手元で決まらない問いまで「問題なし」で
閉じ、読解だけの答えを実行したかのように書き、本命を直しても確かめ方を渡さない回があった
（recall fixture での再現: 設計書 `.claude/designs/20260916-code-review-review-guide-skill.md` の追記 (g)）。
手順（SKILL.md Step 6・7）と書式（review-guide-format.md）の両方にその出口があることを見る。
締めの契約行（`変異テスト:` / `self-review 以降の変更:` / `次の一手:`）の並びと、変異テストを提案するかの
判断（「変異テストの提案」の節 / GitHub issue #307）もここで見る。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / "code-review" / "skills" / "review-guide" / "SKILL.md"
FORMAT = REPO / "code-review" / "references" / "review-guide-format.md"


def between(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i:text.index(end, i)]


def step6() -> str:
    return between(SKILL.read_text(encoding="utf-8"), "### 6. 精読の解説", "### 7. 読み合わせの締め")


def step7() -> str:
    return between(SKILL.read_text(encoding="utf-8"), "### 7. 読み合わせの締め", "## Additional Resources")


def explain_template() -> str:
    return between(FORMAT.read_text(encoding="utf-8"), "## 精読の解説", "### 置き場所")


def closing_template() -> str:
    return between(FORMAT.read_text(encoding="utf-8"), "## 読み合わせの締め", "## 回し直すかの判断")


def mutation_section() -> str:
    return between(FORMAT.read_text(encoding="utf-8"), "## 変異テストの提案", "## 誤ガイド抑制")


class TemplateLineMixin:
    def template_line(self, text: str, marker: str) -> str:
        line = next((l for l in text.splitlines() if marker in l), None)
        self.assertIsNotNone(line, f"書式に `{marker}` の行が無い")
        return line


class AnswerValuesTest(TemplateLineMixin, unittest.TestCase):
    def test_unconfirmed_is_an_answer_value(self):
        self.assertIn("「未確認」のどれか", step6(), "答えの値に未確認が無い")
        self.assertIn("未確認にする前に、手元で決められるか", step6(), "読めば決まる問いを未確認に逃がせる")
        self.assertIn("どこを見れば", self.template_line(explain_template(), "→ 未確認:"))

    def test_unconfirmed_does_not_absorb_judgement(self):
        """答えしだいでコードを変えるかが分かれる問いは「判断が要る」（このまま を含む）。未確認に逃がさない."""
        self.assertIn("仕様が未決でも「判断が要る」", step6())

    def test_how_it_was_checked_is_written_once_per_reading(self):
        self.assertIn("走らせられないとは書かない", step6(), "走らせなかった理由を事実で書かせていない")
        line = self.template_line(explain_template(), "確かめた手段:")
        self.assertIn("読解のみ", line)
        self.assertNotIn("読解のみ", self.template_line(explain_template(), "→ 問題なし:"),
                         "答えの行ごとに読解のみを繰り返す書式に戻っている")

    def test_needs_judgement_always_offers_keep_as_is(self):
        self.assertIn("**`このまま`（変えない）を必ず含め**", step6())
        self.assertIn("このまま", self.template_line(explain_template(), "→ 判断が要る:"))

    def test_unfixed_defects_have_their_own_line(self):
        self.assertIn("「直すべき（未修正）」", step6())
        self.template_line(explain_template(), "→ 直すべき（未修正）:")

    def test_restated_questions_are_not_answered(self):
        self.assertIn("難点の言い換えだけの問いは答えの対象から外す", step6())
        self.template_line(explain_template(), "（言い換え: 答えは難点")
        report_points = between(FORMAT.read_text(encoding="utf-8"), "### レビュー観点\n", "### 前提・決定")
        self.assertIn("難点の言い換えだけの問いは書かない", report_points)
        self.assertIn("難点に含む", report_points, "言い換えしか立たない精読の書き方が無い")


class MainFixTest(unittest.TestCase):
    def test_behavior_changing_fix_has_how_to_verify_and_side_effects(self):
        self.assertIn("確かめ方と副作用も添える", step6())
        fix = between(explain_template(), "修正:", "確認したいこと:")
        for label in ("確かめ方:", "副作用:"):
            self.assertIn(label, fix, f"修正の書式に {label} が無い")

    def test_fix_by_user_instruction_also_has_them(self):
        self.assertIn("直して結果を示す（挙動を変える修正なら確かめ方と副作用も）", step6())


class CarryOverTest(unittest.TestCase):
    def test_one_question_per_reading_is_kept(self):
        self.assertIn("解説の最後に**1 問だけ**聞く", step6())

    def test_unasked_and_unanswered_questions_are_carried(self):
        s = step6()
        self.assertIn("聞いたのに答えが返らなかった問いは、**持ち越した確認**として控えに積み", s)
        self.assertIn("「次」と返しても捨てない", s)

    def test_resolved_items_leave_the_notes(self):
        self.assertIn("答えに書き換えて控えから外す", step6())


class ClosingTest(unittest.TestCase):
    def test_closing_lists_open_checks_then_asks_one(self):
        closing = closing_template()
        listed = closing.index("まだ答えの無い確認:")
        ask = closing.index("確認したいこと: <1 問だけ")
        self.assertLess(listed, ask, "一覧より先に聞いている")
        self.assertIn("残った確認（", closing)
        s7 = step7()
        self.assertIn("**1 問だけ**聞いてターンを終える", s7, "締めで確認をまとめて聞いている")
        self.assertIn("「要確認」を含む", s7, "解説の要確認が締めに集まらない")
        self.assertIn("「残った確認」に残す", s7)

    def test_same_check_is_not_restated(self):
        """同じ確認を解説の答え・確認したいこと・持ち越し・締めで言い直すと、読む量が繰り返しの分だけ増える（再現で最大 9 回）."""
        fmt = FORMAT.read_text(encoding="utf-8")
        self.assertIn("同じ事実・同じ問いは 1 か所に書く", fmt)
        self.assertIn("選択肢は繰り返さない", explain_template())
        self.assertIn("前の精読から持ち越しているものは載せ直さない", explain_template())
        self.assertIn("下の「確認したいこと」で聞く 1 問は載せない", closing_template())

    def test_contract_lines_stay_last(self):
        """呼び出し元が読む 2 行（`self-review 以降の変更:` / `次の一手:`）の後ろに新しい行を足していない."""
        block = closing_template().split("```")[1]
        lines = [l for l in block.splitlines() if l.strip()]
        self.assertTrue(lines[-2].startswith("self-review 以降の変更:"), lines[-2])
        self.assertTrue(lines[-1].startswith("次の一手:"), lines[-1])

    def test_mutation_line_sits_just_before_the_contract_lines(self):
        """`変異テスト:` は 3 本目の契約行（#307）。既存の 2 行の後ろではなく直前に置く."""
        block = closing_template().split("```")[1]
        lines = [l for l in block.splitlines() if l.strip()]
        self.assertTrue(lines[-3].startswith("変異テスト:"), lines[-3])
        for value in ("提案する", "不要", "道具なし"):
            self.assertIn(value, lines[-3], f"締めの変異テストの値から {value} が消えた")
        self.assertIn("回し方:", lines[-3])
        self.assertIn("所要の目安:", lines[-3])
        bullets = closing_template().split("```")[2]
        self.assertIn("`変異テスト:` の行も呼び出し元", bullets, "変異テストの行が契約だと書いていない")

    def test_mutation_section_follows_the_pinned_section(self):
        """新しい節は SSoT pin 先（回し直すかの判断）の後ろに同じ `##` で置く。`###` にすると pin 先の節に入る."""
        fmt = FORMAT.read_text(encoding="utf-8")
        heads = [l for l in fmt.splitlines() if l.startswith("## ")]
        names = [h.split("（")[0] for h in heads]
        i = names.index("## 回し直すかの判断")
        self.assertEqual(names[i + 1], "## 変異テストの提案", heads)
        self.assertEqual(names[i + 2], "## 誤ガイド抑制", heads)
        self.assertIn("## 変異テストの提案", heads,
                      "見出しが変わると、呼び出し元 2 か所の SSoT pin（#変異テストの提案）が当たらない")
        section = mutation_section()
        self.assertIn("要るときだけ", section)
        self.assertIn("導入は提案しない", section, "道具が無いプロジェクトに導入を勧める余地が残っている")
        self.assertIn("detect-mutation-tool.sh", section)
        self.assertIn("`npx --no stryker run --mutate", section,
                      "ローカルに無い Stryker を npx が registry から取りに行く")
        self.assertIn("判定不能", section)

    def test_mutmut_is_narrowed_to_changed_modules(self):
        """mutmut 3 の `run` は mutant 名のワイルドカードを受ける。素の `mutmut run` は設定の範囲全体を変異させる."""
        bullet = next((l for l in mutation_section().splitlines() if l.startswith("- mutmut")), None)
        self.assertIsNotNone(bullet, "推測した道具の回し方に mutmut の行が無い")
        self.assertIn("`mutmut run '<module>.*'", bullet, "変更したモジュールに絞っていない")
        self.assertIn("先頭の `src.` を落とした", bullet, "モジュール名の作り方が無い")
        self.assertIn("判定不能", bullet, "名前が当たらずに止まった回の扱いが無い")

    def test_mutation_section_does_not_start_contract_lines(self):
        """呼び出し元のテストは締めから最初に一致した行を拾う。節の本文に同じ書き出しの行を置かない."""
        for line in mutation_section().splitlines():
            for key in ("変異テスト:", "self-review 以降の変更:", "次の一手:"):
                self.assertFalse(line.startswith(key), line)

    def test_test_coverage_none_is_a_reason_not_to_propose(self):
        """テスト対応表の「なし」は提案の理由ではなく `不要` の理由（壊せば全部生存すると分かっている）."""
        need = between(mutation_section(), "### 要るか", "### 道具")
        self.assertIn("テスト対応表で「あり」", need)
        self.assertIn("すべて「なし」", need)
        self.assertIn("先にテストを足す", need)

    def test_unmeasured_exit_zero_is_not_survivor_zero(self):
        """宣言の exit 0 は「生存 0」のほかに一部未実行（上限・タイムアウト）と未計測を含む。呼び出し元に分けて報告させる."""
        contract = mutation_section()[mutation_section().index("### 宣言の契約"):]
        self.assertIn("0 は実行した変異に生存なし（上限・タイムアウトで未実行が残った回を含む", contract)
        self.assertIn("または未計測（対象行・変異が 0 個）", contract)
        self.assertIn("呼び出し元は exit 0 だけで「生存 0」と書かない", contract)
        self.assertIn("全件を実行して生存が無い回だけを生存 0 とし、一部未実行", contract)
        self.assertNotIn("exit 0 を「生存 0」と書かず", contract,
                         "全件を実行して生存が無い回まで「生存 0」と書かせない文言に読める（呼び出し元と食い違う）")
        self.assertIn("途中で止まった（stderr に中断の FATAL", contract, "途中で止まった回の手がかりが stderr にあると書いていない")
        self.assertIn("未追跡のファイルは対象外", contract)

    def test_unquotable_paths_are_left_out_of_the_command(self):
        """パスの `'` で単引用符が閉じ、承認したコマンドの中でコマンド置換が走る（実測）。引用を組み立てさせず、外す."""
        section = mutation_section()
        for tool in ("- Stryker", "- mutmut"):
            bullet = next((l for l in section.splitlines() if l.startswith(tool)), None)
            self.assertIsNotNone(bullet, f"推測した道具の回し方に {tool} の行が無い")
            self.assertRegex(bullet, r"'<(file|module)>", f"{tool} の名前を単引用符で囲んでいない")
        self.assertIn("パスに `'`・改行・制御文字を含むファイルは回し方に入れず", section)
        self.assertIn("理由に外したことを書く", section)
        self.assertIn("`'` を `'\\''` に置き換えて引用を組み立て直すことはしない", section)
        self.assertIn("回せるファイルが 1 つも残らなければ `道具なし`", section)

    def test_pr_mode_ref_is_taken_from_the_pr_head(self):
        """PR モードの `<ref>` を手元の HEAD から求めると、手元が PR head でない回に base のコミットが対象に混ざる.

        式が本物の git で PR の変更だけを選ぶかは test_code_review_mutation_tool.py の PrModeRefTest で見る.
        """
        bullet = next((l for l in mutation_section().splitlines() if l.startswith("- `<ref>` は")), None)
        self.assertIsNotNone(bullet, "道具の節に `<ref>` の決め方の行が無い")
        self.assertIn("PR モードなら `git merge-base origin/<baseRefName> <headRefOid>` の値", bullet)
        self.assertNotIn("`git merge-base origin/<baseRefName> HEAD`", bullet, "手元の HEAD から求めている")
        self.assertIn("手元の `HEAD` で求めない", bullet)
        self.assertIn("`FIX_OK=0` なら理由に「PR head を checkout してから回す」を添える", bullet,
                      "手元が PR head と違う回に checkout を促す規則が消えた（起点が正しくても別のコードを測る）")
        self.assertIn("merge-base が失敗する", bullet, "手元に PR head のコミットが無い回の扱いが無い")
        self.assertIn("`HEAD` で代えない", bullet, "式が失敗した回に手元の HEAD へ戻る余地が残っている")
        skill = SKILL.read_text(encoding="utf-8")
        meta = next((l for l in skill.splitlines() if "gh pr view" in l and "--json" in l), None)
        self.assertIsNotNone(meta, "Step 0 に META を取る行が無い")
        fields = meta.split("--json", 1)[1].split()[0].split(",")
        for field in ("baseRefName", "headRefOid"):
            with self.subTest(field=field):
                self.assertIn(field, fields, "式に埋める値を META が取っていない")
        step0 = between(skill, "### 0. 入力確定と diff 収集", "### 1. PR コンテキスト")
        self.assertIn("`baseRefName` と `headRefOid` の実値を控えている", step0,
                      "Step 7 まで値が残らない（シェル変数は Bash 呼び出し間で消える）")

    def test_unresolvable_ref_is_not_proposed(self):
        """`<ref>` が求まらない回に `提案する` を出すと、`<ref>` が残った回し方を呼び出し元が承認後にそのまま回して必ず失敗する.

        `提案する` の回し方は「そのまま実行できるコマンド」という契約を崩さず、その回は `道具なし` に倒す。
        倒す対象は回し方に `<ref>` を埋める道具だけで、その一覧は回し方の書式から数え直して突き合わせる.
        """
        bullets = closing_template().split("```")[2]
        self.assertIn("`回し方:`（リポジトリのルートでそのまま実行できるコマンド）", bullets,
                      "`提案する` の回し方が実行できるコマンドだという契約が消えた")
        section = mutation_section()
        bullet = next((l for l in section.splitlines() if l.startswith("- `<ref>` は")), None)
        self.assertIsNotNone(bullet, "道具の節に `<ref>` の決め方の行が無い")
        self.assertIn("`道具なし` にして回し方を付けない", bullet, "`<ref>` が求まらない回にも `提案する` を出せる")
        self.assertNotIn("埋めずに残し", bullet, "`<ref>` が埋まらない回し方を出させている（承認しても必ず失敗する）")
        self.assertIn("PR head を checkout してから `git merge-base origin/<baseRefName> <headRefOid>`", bullet,
                      "回さない回に利用者が自分で回す手順を渡していない")
        no_tool = next((l for l in section.splitlines() if l.startswith("- `道具なし` では")), None)
        self.assertIsNotNone(no_tool, "道具の節に `道具なし` の理由の行が無い")
        self.assertIn("`<ref>` を求められない", no_tool, "`道具なし` の理由の並びにこの回が無い")

        lines = section.splitlines()
        commands = {
            "宣言": next(l for l in lines if l.startswith("| `declared`")),
            "Stryker": next(l for l in lines if l.startswith("- Stryker")),
            "cargo-mutants": next(l for l in lines if l.startswith("- cargo-mutants")),
            "mutmut": next(l for l in lines if l.startswith("- mutmut")),
        }
        uses_ref = [name for name, line in commands.items() if "<ref>" in line]
        self.assertEqual(uses_ref, ["宣言", "cargo-mutants"], "回し方に `<ref>` を埋める道具が変わった")
        self.assertIn("回し方が `<ref>` を使う道具（" + "・".join(uses_ref) + "）", bullet,
                      "`道具なし` に倒す道具の一覧が、回し方に `<ref>` を埋める道具と合っていない")

    def test_cargo_mutants_writes_the_diff_to_a_fresh_temp_dir(self):
        """決め打ちの一時ファイル名は、同時に回した worktree と上書きし合い、共有の /tmp では先回りされうる."""
        bullet = next((l for l in mutation_section().splitlines() if l.startswith("- cargo-mutants")), None)
        self.assertIsNotNone(bullet, "推測した道具の回し方に cargo-mutants の行が無い")
        self.assertIn('`d=$(mktemp -d) && git diff <ref> > "$d/mutants.diff" && '
                      'cargo mutants --in-diff "$d/mutants.diff"`', bullet)
        self.assertNotIn("${TMPDIR:-/tmp}/mutants.diff", bullet)

    def test_review_guide_only_proposes(self):
        s7 = step7()
        self.assertIn("detect-mutation-tool.sh", s7)
        self.assertIn("**この skill からは回さない**", s7)
        done = s7[s7.index("**完了基準**"):]
        self.assertIn("決定的な検証も変異テストも commit も起動していない", done)
        self.assertIn("`変異テスト:` が `提案する` / `不要` / `道具なし` のどれかで始まり", done)
        skill = SKILL.read_text(encoding="utf-8")
        cost = between(skill, "## コスト×精度パイプライン設計", "## 実行手順")
        self.assertIn("提案だけで回すのは呼び出し元なので捨てたまま", cost,
                      "原則 8（外部オラクル）の扱いを書いていない")

    def test_step7_numbers_stay_consistent(self):
        """締めを出すのは 5.。1. の「残った確認」の参照が番号のずれに追随している."""
        s7 = step7()
        self.assertIn("4. **変異テストを提案するかを決める**", s7)
        self.assertIn("5. **締めを出す**", s7)
        self.assertIn("5. の締めの「残った確認」", s7)


if __name__ == "__main__":
    unittest.main()
