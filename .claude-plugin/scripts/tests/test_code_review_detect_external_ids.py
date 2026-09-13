#!/usr/bin/env python3
"""code-review の detect-external-ids.sh を CLI 境界越しに叩く.

git 外の参照 ID（Linear ID / Linear URL）を diff の追加コメントから拾う検出器。
除去は comment-polish skill が人間承認で行うので、ここでは**検出の正確さ**を測る:

- 追加されたコメント行の Linear ID / URL を拾う（exit 1 + JSON Lines）
- コメントでないコード行の ID 様文字列は拾わない
- `Refs/Closes/Fixes` 行は除外する
- GitHub #N は既定で拾わず `--github` でのみ拾う（本 repo 実測で 100% 偽陽性だった型）
- 検出 0 件は exit 0

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from git_env import scrub

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "code-review" / "scripts" / "detect-external-ids.sh"


class DetectExternalIdsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self._git("init", "-q")
        self._git("config", "user.email", "t@example.com")
        self._git("config", "user.name", "t")

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=str(self.root),
                              capture_output=True, text=True, env=scrub())

    def _stage(self, filename: str, body: str) -> None:
        (self.root / filename).write_text(body)
        self._git("add", filename)

    def _run(self, *args: str) -> tuple[int, list[dict]]:
        res = subprocess.run(["bash", str(SCRIPT), "--staged", *args],
                             cwd=str(self.root), capture_output=True, text=True,
                             env=scrub(), timeout=30)
        rows = [json.loads(l) for l in res.stdout.splitlines() if l.strip()]
        return res.returncode, rows

    def test_detects_linear_id_in_comment(self):
        self._stage("f.ts", "// ABC-123 対応で追加\nconst x = 1;\n")
        rc, rows = self._run()
        self.assertEqual(rc, 1)
        self.assertTrue(any(r["match"] == "ABC-123" for r in rows))

    def test_detects_linear_url(self):
        self._stage("f.ts", "// https://linear.app/acme/issue/DEF-9 参照\n")
        rc, rows = self._run()
        self.assertEqual(rc, 1)
        self.assertTrue(any(r["match"].startswith("https://linear.app/") for r in rows))

    def test_ignores_id_in_non_comment_code(self):
        self._stage("f.ts", 'const u = "ABC-123";\n')
        rc, rows = self._run()
        self.assertEqual(rc, 0)
        self.assertEqual(rows, [])

    def test_excludes_refs_closes_fixes_lines(self):
        self._stage("f.ts", "// Refs ABC-999 正当な参照\n// Closes XYZ-1\n")
        rc, rows = self._run()
        self.assertEqual(rc, 0)

    def test_github_ref_off_by_default(self):
        self._stage("f.ts", "// 関連 #789 の残骸\n")
        rc, rows = self._run()
        self.assertEqual(rc, 0)  # 既定では拾わない

    def test_github_ref_opt_in(self):
        self._stage("f.ts", "// 関連 #789 の残骸\n")
        rc, rows = self._run("--github")
        self.assertEqual(rc, 1)
        self.assertTrue(any(r["match"] == "#789" for r in rows))

    def test_standard_tokens_are_not_false_positives(self):
        # UTF-8 / SHA-256 / ISO-8601 は LINEAR_ID の形に一致するが Linear ID ではない。
        # コメントに頻出するので拾わないこと（hook の誤発火を防ぐ）。
        self._stage("f.ts", "// UTF-8 の BOM を除去\n# SHA-256 で比較\n// ISO-8601 の日付\n")
        rc, rows = self._run()
        self.assertEqual(rc, 0, rows)
        self.assertEqual(rows, [])

    def test_real_linear_id_still_detected_among_standard_tokens(self):
        self._stage("f.ts", "// UTF-8 だが ABC-123 は拾う\n")
        rc, rows = self._run()
        self.assertEqual(rc, 1)
        self.assertEqual([r["match"] for r in rows], ["ABC-123"])

    def test_empty_diff_exit_zero(self):
        rc, rows = self._run()
        self.assertEqual(rc, 0)
        self.assertEqual(rows, [])

    def test_base_falls_back_to_main_when_no_origin_head(self):
        """base 未指定・origin/HEAD 不在のとき BASE を main に解決して diff を取る.

        `[ -z "$BASE" ] && { ... BASE=main || BASE=master; }` の `&&` が死ぬと BASE が空の
        まま `git diff ...HEAD` になり、main から分岐した追加コメントの ID を拾えなくなる。
        --staged を付けずに呼び、main より ahead のコメントが検出されることを測る。
        """
        # main 上に ID を含まない初期コミット
        (self.root / "f.ts").write_text("const x = 1;\n")
        self._git("add", "f.ts")
        self._git("commit", "-q", "-m", "init")
        self._git("branch", "-M", "main")
        # feat ブランチで Linear ID コメントを追加（main より ahead。origin/HEAD は張らない）
        self._git("checkout", "-q", "-b", "feat")
        (self.root / "f.ts").write_text("// ABC-123 対応\nconst x = 1;\n")
        self._git("add", "f.ts")
        self._git("commit", "-q", "-m", "feat")
        res = subprocess.run(["bash", str(SCRIPT)],  # --staged なし・base 引数なし
                             cwd=str(self.root), capture_output=True, text=True,
                             env=scrub(), timeout=30)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("ABC-123", res.stdout)

    def test_removed_comment_line_is_not_flagged(self):
        """削除行（先頭 -）の Linear ID は拾わない（追加行のみ対象）.

        `line.startswith("+") and not line.startswith("+++")` の `and` が `or` に倒れると
        削除行・コンテキスト行まで走査され、消したコメントの ID を誤検出する。
        一度コミットしてからコメント行を削除し、その削除 diff を拾わないことを測る。
        """
        self._stage("f.ts", "// ABC-123 対応\nconst x = 1;\n")
        self._git("commit", "-q", "-m", "init")
        (self.root / "f.ts").write_text("const x = 1;\n")  # コメント行を削除
        self._git("add", "f.ts")
        rc, rows = self._run()
        self.assertEqual(rc, 0, rows)  # 削除された `// ABC-123` は検出対象外
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
