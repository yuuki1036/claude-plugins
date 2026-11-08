#!/usr/bin/env python3
"""`evals/fixtures/recall/judge.py` の回帰テスト（GitHub issue #400）.

judge.py は recall fixture の測定器で、壊れても判定結果からは見えない（`test_evals_runner.py` と同じ事情）。
self-review を fixture に通す実計測は paid なので、保存したレポートの形を合成して入力にする。
レポートの形の正本は `code-review/skills/self-review/SKILL.md` の Step 6 の定型。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import builtins
import importlib.util
import io
import re
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
JUDGE = ROOT / "evals" / "fixtures" / "recall" / "judge.py"
TSX = "src/app/projects/[slug]/ProjectSettings.tsx"


def _load():
    # @dataclass が sys.modules[cls.__module__] を引くので、登録してから exec する
    spec = importlib.util.spec_from_file_location("_recall_judge_under_test", JUDGE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


j = _load()


def report(*findings: str, counts: str | None = None) -> str:
    """self-review の定型レポート。findings は `### ` 見出しの下に並べる 1 件ぶんの文字列.

    「指摘件数」の行は findings の severity から作る（counts を渡せばその値に差し替える）。
    """
    sev = [m for f in findings for m in re.findall(r"\[severity: (\w+)\]", f)]
    if counts is None:
        counts = " / ".join(f"{s} {sev.count(s)} 件" for s in ("BLOCKER", "CRITICAL", "MAJOR", "MINOR"))
    return "\n".join(
        [
            "## セルフレビュー結果",
            "",
            f"**指摘件数**: {counts}",
            "**動的ラウンド**: Round 2 未実行 / Meta-reviewer スキップ / 冷や読み skeptic 実行（1 件追加） / 反証 対象 1 件",
            "",
            "### 📋 MAJOR 指摘",
            "",
            *findings,
            "",
            "### 総括",
            "- 変更の概要",
        ]
    )


def finding(n: int, severity: str, title: str, file: str, *body: str) -> str:
    lines = [f"{n}. [confidence: 85][severity: {severity}][バグ] {title}", f"   ファイル: {file}"]
    lines += [f"   {b}" for b in body]
    return "\n".join(lines) + "\n"


# 08 の期待指摘（48 行目の投げ直し）
HIT_08 = finding(1, "MAJOR", "投げ直しの経路で closeDialog が呼ばれない", f"{TSX}:48", "影響: ダイアログが遷移先に残る")


def fx08() -> dict:
    return j.load_fixture("08")


class ParseReport(unittest.TestCase):
    def test_finding_fields_are_read_from_the_template(self):
        r = j.parse_report(report(HIT_08))
        self.assertTrue(r.is_self_review)
        self.assertEqual(len(r.findings), 1)
        f = r.findings[0]
        self.assertEqual((f.number, f.severity), (1, "MAJOR"))
        self.assertEqual(f.files, {TSX: {48}})
        self.assertIn("ダイアログが遷移先に残る", f.text)
        self.assertEqual(r.skeptic, "実行（1 件追加）")

    def test_range_and_bare_numbers_expand_to_every_line(self):
        self.assertEqual(j.parse_file_field(f"`{TSX}:48-51`"), {TSX: {48, 49, 50, 51}})
        self.assertEqual(j.parse_file_field("src/a.ts:10, 12, src/b.ts:3"), {"src/a.ts": {10, 12}, "src/b.ts": {3}})
        self.assertEqual(j.parse_file_field("src/a.ts:L7"), {"src/a.ts": {7}})
        self.assertEqual(j.parse_file_field("src/a.ts:48〜50"), {"src/a.ts": {48, 49, 50}})
        self.assertEqual(j.parse_file_field("src/a.ts（48 行目）"), {"src/a.ts": {48}})
        self.assertEqual(j.parse_file_field("src/a.ts L51"), {"src/a.ts": {51}})
        self.assertEqual(j.parse_file_field("src/a.ts（catch 節）"), {"src/a.ts": set()})

    def test_skeptic_value_keeps_slashes_inside_the_item(self):
        text = report().replace("冷や読み skeptic 実行（1 件追加）", "冷や読み skeptic skip（理由: effort/config/scope）")
        self.assertEqual(j.parse_report(text).skeptic, "skip（理由: effort/config/scope）")

    def test_lines_before_the_report_heading_are_ignored(self):
        text = "冷や読み skeptic 前置き / x\n1. [confidence: 90][severity: MAJOR] 前置き\n" + report()
        r = j.parse_report(text)
        self.assertEqual((r.skeptic, r.findings), ("実行（1 件追加）", []))

    def test_declared_counts_are_read(self):
        r = j.parse_report(report(HIT_08))
        self.assertEqual(r.declared, {"BLOCKER": 0, "CRITICAL": 0, "MAJOR": 1, "MINOR": 0})
        self.assertIsNone(r.count_mismatch())

    def test_items_without_lines_or_with_bare_numbers_keep_their_place(self):
        # 番号だけの項は直前のパスの行、パスの項は行なしのパスとして残す（取り違えると例外か別ファイル扱いになる）
        self.assertEqual(j.parse_file_field("src/a.ts:1, src/b.ts"), {"src/a.ts": {1}, "src/b.ts": set()})
        self.assertEqual(j.parse_file_field("57"), {"57": set()})
        self.assertEqual(j.parse_file_field("src/a.ts:5, 10 12"), {"src/a.ts": {5, 10}})
        self.assertEqual(j.parse_file_field("src/a.ts:1,"), {"src/a.ts": {1}})

    def test_has_line_when_only_some_paths_have_lines(self):
        f = j.parse_report(report(finding(1, "MAJOR", "t", "src/a.ts, src/b.ts:3"))).findings[0]
        self.assertTrue(f.has_line)

    def test_lines_in_matches_any_of_several_targets(self):
        f = j.parse_report(report(finding(1, "MAJOR", "t", "src/b.ts:3"))).findings[0]
        self.assertEqual(f.lines_in(["src/a.ts", "src/b.ts"]), {3})

    def test_label_shows_lines_and_paths(self):
        f = j.parse_report(report(finding(1, "MAJOR", "題", "src/a.ts:3-4, src/b.ts"))).findings[0]
        self.assertEqual(f.label(), "#1 [MAJOR] 題 — src/a.ts:3,4, src/b.ts")
        self.assertEqual(j.Finding(2, "MINOR", "題").label(), "#2 [MINOR] 題 — （ファイル欄なし）")

    def test_file_without_line_is_kept_with_no_lines(self):
        f = j.parse_report(report(finding(1, "MAJOR", "t", TSX))).findings[0]
        self.assertEqual(f.files, {TSX: set()})
        self.assertFalse(f.has_line)

    def test_appendix_below_threshold_is_not_counted(self):
        # 🔁 付録は報告外。番号を持たず `- [調整前: …]` で始まる。その下の「ファイル:」を直前の指摘に足さない
        text = report(HIT_08) + "\n".join(
            [
                "",
                "### 🔁 報告閾値を割った指摘（参考・人間が覆せる）",
                "- [調整前: confidence 60 / severity MAJOR] InputError の return で closeDialog が飛ばされる",
                f"  ファイル: {TSX}:51",
            ]
        )
        r = j.parse_report(text)
        self.assertEqual(len(r.findings), 1)
        self.assertEqual(r.findings[0].files, {TSX: {48}})

    def test_heading_ends_the_previous_finding(self):
        text = report(HIT_08) + "\n### ✏️ コメント推敲\n\n1. src/foo.ts:12 [不要]\n   ファイル: src/foo.ts:12\n"
        r = j.parse_report(text)
        self.assertEqual(len(r.findings), 1)
        self.assertEqual(r.findings[0].files, {TSX: {48}})

    def test_text_without_report_heading_is_not_a_self_review(self):
        self.assertFalse(j.parse_report("plain transcript").is_self_review)


class Recall08(unittest.TestCase):
    def verdict(self, *runs: str):
        return j.judge(fx08(), [j.parse_report(r, f"run{i}") for i, r in enumerate(runs, 1)])

    def test_two_of_three_hits_pass(self):
        v = self.verdict(report(HIT_08), report(HIT_08), report())
        self.assertEqual(v.status, "PASS")
        self.assertEqual(v.exit_code, 0)

    def test_one_of_three_hits_fail(self):
        v = self.verdict(report(HIT_08), report(), report())
        self.assertEqual(v.status, "FAIL")
        self.assertEqual(v.exit_code, 1)

    def test_cleanup_line_alone_is_not_a_hit(self):
        # 57 行目（closeDialog）だけを指す指摘は合致に数えない（expected.yaml の rationale）
        only57 = finding(1, "MAJOR", "closeDialog が飛ばされる", f"{TSX}:57")
        run = j.judge_run(j.parse_report(report(only57)), fx08())
        self.assertEqual(run.hits, [])

    def test_below_severity_or_without_keyword_is_not_a_hit(self):
        minor = finding(1, "MINOR", "closeDialog が呼ばれない", f"{TSX}:48")
        no_kw = finding(2, "MAJOR", "redirect の扱い", f"{TSX}:48")
        other_file = finding(3, "MAJOR", "closeDialog が呼ばれない", "src/other.tsx:48")
        run = j.judge_run(j.parse_report(report(minor, no_kw, other_file)), fx08())
        self.assertEqual(run.hits, [])

    def test_range_including_expected_line_is_a_hit(self):
        ranged = finding(1, "MAJOR", "closeDialog が呼ばれない", f"{TSX}:47-50")
        run = j.judge_run(j.parse_report(report(ranged)), fx08())
        self.assertEqual(len(run.hits), 1)

    def test_contrast_line_without_expected_line_fails_even_once(self):
        c = finding(2, "MAJOR", "入力エラーで閉じない", f"{TSX}:51")
        v = self.verdict(report(HIT_08, c), report(HIT_08), report(HIT_08))
        self.assertEqual(v.status, "FAIL")
        self.assertEqual(v.runs[0].contrast_fails[0][1], "対照の行を指す")

    def test_contrast_line_is_minor_only_does_not_count(self):
        c = finding(2, "MINOR", "入力エラーで閉じない", f"{TSX}:51")
        v = self.verdict(report(HIT_08, c), report(HIT_08), report(HIT_08))
        self.assertEqual(v.status, "PASS")

    def test_pattern_on_unrelated_line_fails(self):
        c = finding(2, "MAJOR", "InputError のとき closeDialog されない", f"{TSX}:40")
        run = j.judge_run(j.parse_report(report(c)), fx08())
        self.assertEqual(len(run.contrast_fails), 1)
        self.assertIn("false_positive_patterns", run.contrast_fails[0][1])

    def test_unrelated_line_without_pattern_is_ignored(self):
        c = finding(2, "MAJOR", "pending の型が広い", f"{TSX}:40")
        run = j.judge_run(j.parse_report(report(c)), fx08())
        self.assertEqual((run.contrast_fails, run.review), ([], []))

    def test_expected_or_cleanup_line_or_no_line_goes_to_review(self):
        # 本文の読みが要る: 機械で FAIL にせず、パターンは手がかりとして添える
        body = "影響: InputError でも closeDialog を finally へ移すべき"
        on48 = finding(2, "MAJOR", "後片付けの漏れ", f"{TSX}:48", body)
        on57 = finding(3, "MAJOR", "後片付けの漏れ", f"{TSX}:57", body)
        noline = finding(4, "MAJOR", "後片付けの漏れ", TSX, body)
        run = j.judge_run(j.parse_report(report(on48, on57, noline)), fx08())
        self.assertEqual(run.contrast_fails, [])
        self.assertEqual([f.number for f, _ in run.review], [2, 3, 4])
        self.assertTrue(all(pats for _, pats in run.review))

    def test_cleanup_or_no_line_is_a_candidate_even_without_mentioning_contrast(self):
        # 「closeDialog を無条件に finally へ移す」は対照に触れずに対照を壊す（README の [人] の例）
        body = "影響: closeDialog() を finally へ移し、どの経路でも必ず閉じる"
        on57 = finding(2, "MAJOR", "後片付けの漏れ", f"{TSX}:57", body)
        noline = finding(3, "MAJOR", "後片付けの漏れ", TSX, body)
        run = j.judge_run(j.parse_report(report(on57, noline)), fx08())
        self.assertEqual([f.number for f, _ in run.review], [2, 3])

    def test_expected_and_contrast_lines_together_are_not_narrowed(self):
        # 48 と 51 を両方指す指摘は「期待の行だけ」ではないので、対照に触れていなくても候補にする
        body = "影響: closeDialog() を finally へ移し、どの経路でも必ず閉じる"
        both = finding(2, "MAJOR", "後片付けの漏れ", f"{TSX}:48, 51", body)
        span = finding(3, "MAJOR", "後片付けの漏れ", f"{TSX}:45-55", body)
        run = j.judge_run(j.parse_report(report(both, span)), fx08())
        self.assertEqual([f.number for f, _ in run.review], [2, 3])

    def test_slash_and_to_separate_lines(self):
        self.assertEqual(j.parse_file_field("a.tsx:48 / 51"), {"a.tsx": {48, 51}})
        self.assertEqual(j.parse_file_field("a.tsx:48 と 51"), {"a.tsx": {48, 51}})

    def test_target_file_without_line_beside_other_file_with_line_goes_to_review(self):
        f = finding(2, "MAJOR", "InputError でも closeDialog されない", f"{TSX}, src/other.ts:10")
        run = j.judge_run(j.parse_report(report(f)), fx08())
        self.assertEqual((run.contrast_fails, [x.number for x, _ in run.review]), ([], [2]))

    def test_finding_not_mentioning_contrast_is_not_a_review_candidate(self):
        # 期待指摘そのもの（48 行目・対照に触れない）は本文を読む候補にしない
        v = self.verdict(report(HIT_08), report(HIT_08), report(HIT_08))
        self.assertEqual(v.status, "PASS")
        self.assertEqual([r.review for r in v.runs], [[], [], []])

    def test_review_candidates_make_verdict_needs_review(self):
        cmp = finding(2, "MAJOR", "投げ直しの後片付け", f"{TSX}:48", "影響: InputError の return は意図した残し")
        v = self.verdict(report(HIT_08, cmp), report(HIT_08), report())
        self.assertEqual((v.status, v.exit_code), ("要確認", 3))

    def test_without_mentions_any_every_touching_finding_is_a_candidate(self):
        fx = fx08()
        del fx["expect"]["must_not_flag"]["mentions_any"]
        run = j.judge_run(j.parse_report(report(HIT_08)), fx)
        self.assertEqual(len(run.review), 1)


class Precision90(unittest.TestCase):
    def fx(self):
        return j.load_fixture("90")

    def test_pattern_match_at_major_fails_once(self):
        fp = finding(1, "MAJOR", "minorUnitDigits が 0 のときバグ", "src/money.ts:10")
        v = j.judge(self.fx(), [j.parse_report(report(fp)), j.parse_report(report()), j.parse_report(report())])
        self.assertEqual(v.status, "FAIL")

    def test_minor_pattern_match_passes(self):
        fp = finding(1, "MINOR", "minorUnitDigits が 0 のときバグ", "src/money.ts:10")
        v = j.judge(self.fx(), [j.parse_report(report(fp))] + [j.parse_report(report())] * 2)
        self.assertEqual(v.status, "PASS")


class Inputs(unittest.TestCase):
    def test_count_mismatch_is_undecidable(self):
        # 書式が変わって指摘を読めない回を、precision の PASS や recall の FAIL にしない
        drifted = report(counts="BLOCKER 0 件 / CRITICAL 1 件 / MAJOR 0 件 / MINOR 0 件")
        v = j.judge(j.load_fixture("90"), [j.parse_report(drifted)] + [j.parse_report(report())] * 2)
        self.assertEqual((v.status, v.exit_code), ("判定不能", 2))
        self.assertIn("CRITICAL 0/1", v.reasons[0])

    def test_unreadable_counts_line_is_undecidable(self):
        drifted = report(counts="BLOCKER: 0 / CRITICAL: 0 / MAJOR: 0 / MINOR: 0")
        r = j.parse_report(drifted)
        self.assertIn("4 つの severity", r.count_mismatch())

    def test_missing_counts_line_is_undecidable(self):
        no_counts = "\n".join(l for l in report(HIT_08).splitlines() if "指摘件数" not in l)
        v = j.judge(fx08(), [j.parse_report(no_counts)] + [j.parse_report(report(HIT_08))] * 2)
        self.assertEqual(v.status, "判定不能")

    def test_missing_pyyaml_exits_2(self):
        real = builtins.__import__

        def no_yaml(name, *a, **kw):
            if name == "yaml":
                raise ImportError("no yaml")
            return real(name, *a, **kw)

        err = io.StringIO()
        with unittest.mock.patch("builtins.__import__", no_yaml), redirect_stderr(err):
            self.assertEqual(j.main(["08", str(JUDGE)]), 2)
        self.assertIn("PyYAML", err.getvalue())

    def test_broken_expected_yaml_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "expected.yaml"
            bad.write_text("fixtures: [\n", encoding="utf-8")
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertEqual(j.main(["08", str(JUDGE), "--expected", str(bad)]), 2)

    def test_fixture_missing_a_key_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "expected.yaml"
            bad.write_text("fixtures:\n  - id: 08-x\n    kind: recall\n    expect: {}\n", encoding="utf-8")
            rep_path = Path(d) / "r.md"
            rep_path.write_text(report(HIT_08), encoding="utf-8")
            err = io.StringIO()
            with redirect_stderr(err):
                rc = j.main(["08", str(rep_path), str(rep_path), str(rep_path), "--expected", str(bad)])
        self.assertEqual(rc, 2)

    def test_malformed_fixtures_and_patterns_exit_2(self):
        bad_cases = [
            "fixtures:\n  - just-a-string\n",
            "fixtures:\n  - id: 8\n",
            "fixtures:\n  - id: 08-x\n    kind: precision\n    expect:\n      false_positive_patterns: ['(unclosed']\n",
        ]
        with tempfile.TemporaryDirectory() as d:
            rep_path = Path(d) / "r.md"
            rep_path.write_text(report(finding(1, "MAJOR", "t", "src/a.ts:1")), encoding="utf-8")
            for text in bad_cases:
                bad = Path(d) / "expected.yaml"
                bad.write_text(text, encoding="utf-8")
                err = io.StringIO()
                with self.subTest(text=text), redirect_stderr(err):
                    rc = j.main(["08", str(rep_path), str(rep_path), str(rep_path), "--expected", str(bad)])
                    self.assertEqual(rc, 2)

    def test_non_utf8_report_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.md"
            p.write_bytes(b"\xff\xfe\x00")
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertEqual(j.main(["08", str(p), str(p), str(p)]), 2)

    def test_k_other_than_three_is_undecidable(self):
        v = j.judge(fx08(), [j.parse_report(report(HIT_08))] * 2)
        self.assertEqual((v.status, v.exit_code), ("判定不能", 2))

    def test_non_report_is_undecidable(self):
        v = j.judge(fx08(), [j.parse_report("no report")] + [j.parse_report(report(HIT_08))] * 2)
        self.assertEqual(v.status, "判定不能")

    def test_fixture_id_resolves_by_number_and_full_id(self):
        self.assertEqual(j.load_fixture("08")["id"], "08-rethrow-skips-cleanup")
        self.assertEqual(j.load_fixture("01-value-flow-insert")["kind"], "recall")
        with self.assertRaises(LookupError):
            j.load_fixture("99")

    def test_real_expected_yaml_has_fields_judge_reads(self):
        # expected.yaml の形が変わって judge.py が黙って何も見なくなるのを止める
        e = fx08()["expect"]
        self.assertEqual(e["target_lines_any"], [48])
        self.assertEqual(e["cleanup_lines"], [57])
        self.assertEqual(e["must_not_flag"]["target_lines_any"], [51])
        self.assertTrue(e["must_not_flag"]["false_positive_patterns"])

    def test_cli_prints_table_and_returns_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            paths = []
            cmp = finding(2, "MAJOR", "後片付け", f"{TSX}:57", "影響: 入力エラーでも閉じるべき")
            for i, body in enumerate([report(HIT_08, cmp), report(HIT_08), report()], 1):
                p = Path(d) / f"run{i}.md"
                p.write_text(body, encoding="utf-8")
                paths.append(str(p))
            out = io.StringIO()
            with redirect_stdout(out):
                rc = j.main(["08", *paths])
        self.assertEqual(rc, 3)
        self.assertIn("| 08 | 1/3 | ✅ #1 | MAJOR | - |", out.getvalue())
        self.assertIn("総合: 08 要確認", out.getvalue())

    def test_cli_unknown_fixture_exits_2(self):
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(j.main(["99", str(JUDGE)]), 2)
        self.assertIn("1 つに決まらない", err.getvalue())


if __name__ == "__main__":
    unittest.main()
