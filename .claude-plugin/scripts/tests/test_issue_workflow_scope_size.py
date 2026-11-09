#!/usr/bin/env python3
"""issue-workflow 同梱 `scripts/scope-size.py` の CLI 境界テスト（GitHub issue #425）.

scope_size の上限と判定の正本。hook・issue-maintain・retrospective がこれを呼ぶので、
境界の取り違え（「超える」と「以上」）はここでしか見つからない。境界は両側から測る。
期待値はテスト側に直接書く（スクリプトの出力から作ると、壊れていても全件 pass する）。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "issue-workflow" / "scripts" / "scope-size.py"
BAND_LIB = REPO / "issue-workflow" / "hooks" / "issue-band-lib.ts"
# mod のテストと共有する fixture。`export default ` の後ろが JSON（mod は .json を import できない）
SHARED_CASES = Path(__file__).resolve().parent / "mods" / "issue-workflow" / "tests" / "scope-size-cases.ts"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["python3", str(SCRIPT), *args], capture_output=True, text=True, timeout=60)


def blocks(stdout: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for line in stdout.splitlines():
        key, _, val = line.partition("=")
        if key == "file":
            out.append({"file": val})
        elif out and key != "missing":
            out[-1][key] = val
    return out


class ScopeSizeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.n = 0

    def write(self, body: str) -> Path:
        self.n += 1
        p = self.tmp / f"ISS-{self.n}.md"
        p.write_text(body)
        return p

    def issue(self, scope: str | None, tasks: int = 0, done: int = 0,
              section: str = "進捗", fm_extra: str = "") -> Path:
        fm = "---\nid: ISS-1\n" + (f"scope_size: {scope}\n" if scope is not None else "") + fm_extra + "---\n"
        items = "\n".join(["- [x] done"] * done + ["- [ ] todo"] * (tasks - done))
        return self.write(f"{fm}\n# ISS-1: t\n\n## {section}\n\n{items}\n\n## メモ\n\n- [ ] 節の外\n")

    def check(self, path: Path, basis: str | None = None) -> dict[str, str]:
        args = ["check"] + (["--basis", basis] if basis else []) + [str(path)]
        res = run(*args)
        self.assertEqual(res.returncode, 0, res.stderr)
        (b,) = blocks(res.stdout)
        return b


class LimitsTest(ScopeSizeTestCase):
    def test_limits(self):
        res = run("limits")
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.splitlines(), ["small=3", "medium=7", "large=15"])

    def test_band_mod_copy_matches(self):
        """mod（TS）は python を呼べず値を複製している。複製がずれたらここで落ちる."""
        m = re.search(r"SCOPE_LIMIT[^=]*=\s*\{([^}]*)\}", BAND_LIB.read_text())
        self.assertIsNotNone(m, "issue-band-lib.ts に SCOPE_LIMIT が見つからない")
        copied = {k: int(v) for k, v in re.findall(r"(\w+)\s*:\s*(\d+)", m.group(1))}
        script = dict(line.split("=") for line in run("limits").stdout.splitlines())
        self.assertEqual(copied, {k: int(v) for k, v in script.items()})


class VerdictTest(ScopeSizeTestCase):
    def assertVerdict(self, scope: str, tasks: int, verdict: str, recommended: str):
        b = self.check(self.issue(scope, tasks))
        self.assertEqual((b["verdict"], b["recommended"]), (verdict, recommended),
                         f"{scope} {tasks} 件")

    def test_over_boundary(self):
        for scope, limit, up in (("small", 3, "medium"), ("medium", 7, "large"), ("large", 15, "split")):
            with self.subTest(scope=scope):
                self.assertNotEqual(self.check(self.issue(scope, limit))["verdict"], "over")
                self.assertVerdict(scope, limit + 1, "over", up)

    def test_under_boundary(self):
        self.assertVerdict("medium", 3, "under", "small")
        self.assertVerdict("medium", 4, "ok", "medium")
        self.assertVerdict("large", 7, "under", "medium")
        self.assertVerdict("large", 8, "ok", "large")

    def test_small_is_never_under(self):
        self.assertVerdict("small", 1, "ok", "small")

    def test_no_tasks_is_skip_not_under(self):
        """タスクを書いていない Issue を過大見積もりに数えない（retrospective の集計のノイズになる）."""
        for scope in ("small", "medium", "large"):
            with self.subTest(scope=scope):
                b = self.check(self.issue(scope, 0))
                self.assertEqual((b["verdict"], b["reason"], b["limit"], b["recommended"]),
                                 ("skip", "no_tasks", {"small": "3", "medium": "7", "large": "15"}[scope], ""))

    def test_done_zero_with_tasks_is_still_judged(self):
        """skip にするのはチェックリストが無いときだけ。書いたが 1 件も終えていない large は under."""
        self.assertEqual(self.check(self.issue("large", 5), "done")["verdict"], "under")

    def test_recommended(self):
        for tasks, rec in ((1, "small"), (3, "small"), (4, "medium"), (7, "medium"),
                           (8, "large"), (15, "large"), (16, "split")):
            with self.subTest(tasks=tasks):
                self.assertEqual(self.check(self.issue("large", tasks))["recommended"], rec)

    def test_fields(self):
        b = self.check(self.issue("small", 4, done=1))
        self.assertEqual({k: b[k] for k in ("id", "scope_size", "total", "done", "count", "limit")},
                         {"id": "ISS-1", "scope_size": "small", "total": "4", "done": "1",
                          "count": "4", "limit": "3"})


class BasisTest(ScopeSizeTestCase):
    def test_all_is_default_and_done_counts_checked_only(self):
        f = self.issue("small", 4, done=1)
        self.assertEqual(self.check(f)["verdict"], "over")
        self.assertEqual(self.check(f, "all")["verdict"], "over")
        b = self.check(f, "done")
        self.assertEqual((b["count"], b["verdict"]), ("1", "ok"))

    def test_done_can_be_under(self):
        self.assertEqual(self.check(self.issue("large", 10, done=3), "done")["verdict"], "under")

    def test_bad_basis_is_rejected(self):
        self.assertEqual(run("check", "--basis", "bogus", str(self.issue("small"))).returncode, 2)


class CountingTest(ScopeSizeTestCase):
    FM = "---\nscope_size: small\n---\n"

    def test_progress_wins_and_sections_are_not_summed(self):
        f = self.write(self.FM + "## 進捗\n- [ ] a\n- [ ] b\n## 完了条件\n- [ ] a\n- [ ] b\n- [ ] c\n")
        self.assertEqual(self.check(f)["total"], "2")

    def test_falls_back_to_done_criteria_when_progress_is_empty(self):
        f = self.write(self.FM + "## 進捗\n\n未記入\n## 完了条件\n- [x] a\n- [ ] b\n- [X] c\n- [ ] d\n")
        b = self.check(f)
        self.assertEqual((b["total"], b["done"], b["verdict"]), ("4", "2", "over"))

    def test_items_outside_the_sections_are_not_counted(self):
        f = self.write(self.FM + "- [ ] 前\n## 進捗\n- [ ] a\n## スコープ外\n- [ ] x\n- [ ] y\n- [ ] z\n")
        self.assertEqual(self.check(f)["total"], "1")

    def test_indented_items_and_uppercase_x(self):
        f = self.write(self.FM + "## 進捗\n- [X] a\n  - [x] b\n    - [ ] c\n- 普通の箇条書き\n")
        b = self.check(f)
        self.assertEqual((b["total"], b["done"]), ("3", "2"))

    def test_heading_with_suffix_is_another_section(self):
        f = self.write(self.FM + "## 進捗メモ\n- [ ] a\n- [ ] b\n- [ ] c\n- [ ] d\n")
        self.assertEqual(self.check(f)["total"], "0")


class FrontmatterTest(ScopeSizeTestCase):
    def test_trailing_comment_is_stripped(self):
        f = self.issue("small            # 必須。値: small / medium / large", 4)
        b = self.check(f)
        self.assertEqual((b["scope_size"], b["verdict"]), ("small", "over"))

    def test_quoted_value(self):
        self.assertEqual(self.check(self.issue('"medium"', 8))["verdict"], "over")

    def test_body_scope_size_is_not_read(self):
        f = self.write("---\nid: ISS-1\n---\n\nscope_size: small\n## 進捗\n- [ ] a\n")
        b = self.check(f)
        self.assertEqual((b["verdict"], b["reason"]), ("skip", "no_scope_size"))

    def test_frontmatter_must_start_on_the_first_line(self):
        f = self.write("\n---\nscope_size: small\n---\n## 進捗\n" + "- [ ] a\n" * 5)
        self.assertEqual(self.check(f)["verdict"], "skip")

    def test_key_lines_without_opening_fence_are_not_frontmatter(self):
        """1 行目が `---` でなければ、後ろにキーの行と `---` があっても frontmatter として読まない."""
        # キーの行は 2 行目に置く（2 行目が `---` だと、1 行目の判定を外しても読み取りがすぐ止まり区別できない）
        f = self.write("# ISS-1: t\nscope_size: small\n---\n## 進捗\n" + "- [ ] a\n" * 5)
        self.assertEqual((self.check(f)["scope_size"], self.check(f)["verdict"]), ("", "skip"))

    def test_non_key_lines_inside_frontmatter_are_skipped(self):
        """frontmatter の中の空行・`#` の行はキーとして読まずに飛ばし、後ろのキーを読む."""
        f = self.write("---\n\n# 注釈の行\nscope_size: small\n---\n## 進捗\n" + "- [ ] a\n" * 4)
        self.assertEqual((self.check(f)["scope_size"], self.check(f)["verdict"]), ("small", "over"))

    def test_missing_and_unknown_scope_size_skip(self):
        b = self.check(self.issue(None, 99))
        self.assertEqual((b["verdict"], b["reason"], b["limit"], b["recommended"]),
                         ("skip", "no_scope_size", "", ""))
        b = self.check(self.issue("gigantic", 99))
        self.assertEqual((b["verdict"], b["reason"]), ("skip", "unknown_scope_size"))

    def test_bom_is_stripped(self):
        f = self.issue("small", 4)
        f.write_bytes(b"\xef\xbb\xbf" + f.read_bytes())
        b = self.check(f)
        self.assertEqual((b["scope_size"], b["verdict"]), ("small", "over"))

    def test_linear_id_is_used_when_id_is_absent(self):
        f = self.write("---\nlinear: ABC-42\nscope_size: small\n---\n")
        self.assertEqual(self.check(f)["id"], "ABC-42")


class SharedCasesTest(ScopeSizeTestCase):
    """mod（issue-band-lib.ts）と同じ fixture を通し、数え方と超過判定が一致するかを見る.

    mod 側は issue-band.test.ts が同じファイルを import して確かめる。どちらかの実装だけを変えると片方が落ちる。
    """

    def test_matches_shared_cases(self):
        text = SHARED_CASES.read_text(encoding="utf-8")
        cases = json.loads(text.split("\nexport default ", 1)[1])["cases"]   # コメント中の同じ語に一致させない
        self.assertGreater(len(cases), 0)
        for c in cases:
            with self.subTest(c["name"]):
                b = self.check(self.write(c["text"]))
                self.assertEqual((int(b["total"]), int(b["done"]), b["verdict"] == "over"),
                                 (c["total"], c["done"], c["over"]))


class MultipleFilesTest(ScopeSizeTestCase):
    def test_blocks_follow_input_order_and_missing_does_not_stop(self):
        a = self.issue("small", 4)
        b = self.issue("small", 1)
        missing = self.tmp / "none.md"
        res = run("check", str(a), str(missing), str(b))
        self.assertEqual(res.returncode, 2)
        self.assertIn(f"missing={missing}", res.stdout.splitlines())
        got = blocks(res.stdout)
        self.assertEqual([(x["file"], x["verdict"]) for x in got],
                         [(str(a), "over"), (str(b), "ok")])

    def test_all_present_exits_zero(self):
        res = run("check", str(self.issue("small", 1)), str(self.issue("medium", 5)))
        self.assertEqual(res.returncode, 0)
        self.assertEqual(len(blocks(res.stdout)), 2)


if __name__ == "__main__":
    unittest.main()
