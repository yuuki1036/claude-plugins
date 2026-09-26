#!/usr/bin/env python3
"""`md-prose-lines.sh` の回帰テスト（GitHub issue #243）.

self-review の Markdown 推敲に渡す行を決める。**渡してはいけない行（フェンス内のコード・
frontmatter・HTML コメント・見出し）を渡すと、推敲が別の検査や参照を壊す**ので、黙る条件を厚く書く。
行番号は最終状態のファイルに対するもので、推敲の適用（Step 7 の Edit）の位置合わせに使われる。
"""

from __future__ import annotations

import json
import unittest

from test_code_review_diff_scripts import DiffScriptTestBase
from test_code_review_scripts import PLUGIN

MD = PLUGIN / "scripts" / "md-prose-lines.sh"


class MdProseTestBase(DiffScriptTestBase):
    def setUp(self) -> None:
        super().setUp()
        (self.root / "home").mkdir()

    def env(self, **extra: str) -> dict[str, str]:
        # **実ユーザーの settings.json を読ませない**（writing-polish の有効判定が開発機の設定で変わる）
        return self._env(HOME=str(self.root / "home"), **extra)

    def run_md(self, *args: str):
        return self.run_in(MD, *args, env=self.env())

    def rows(self, *args: str) -> list[tuple[str, int, str]]:
        # 未追跡のファイルは `git diff` に出ない（self-review の diff も同じ）ので追跡させる
        self.add()
        res = self.run_md("--base", "HEAD", *args)
        self.assertEqual(res.returncode, 0, res.stderr)
        out = []
        for line in res.stdout.splitlines():
            p, n, s = line.split("\t", 2)
            out.append((p, int(n) if n.isdigit() else n, s))
        return out

    def commit(self, msg: str = "c") -> None:
        self.add()
        self.git("commit", "-qm", msg)


class MdProseSelectionTest(MdProseTestBase):
    def test_added_prose_lines_come_out_with_final_line_numbers(self):
        self.write("docs/a.md", "既存の段落\n")
        self.commit()
        self.write("docs/a.md", "既存の段落\n追加した段落\n- 箇条の本文\n")
        self.assertEqual(self.rows(), [("docs/a.md", 2, "追加した段落"),
                                       ("docs/a.md", 3, "- 箇条の本文")])

    def test_unchanged_lines_are_not_targets(self):
        self.write("a.md", "一行目\n二行目\n")
        self.commit()
        self.write("a.md", "一行目\n二行目を直した\n")
        self.assertEqual([r[1] for r in self.rows()], [2])

    def test_non_markdown_files_are_ignored(self):
        self.write("docs/a.txt", "散文だが md ではない\n")
        self.write("src/a.py", "x = 1\n")
        self.assertEqual(self.rows(), [])

    def test_untracked_markdown_is_not_a_target(self):
        """self-review の diff（`git diff`）にも出ないので、推敲の対象にもしない."""
        self.write("a.md", "未追跡の段落\n")
        res = self.run_md("--base", "HEAD")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout, "")

    def test_deleted_markdown_file_is_ignored(self):
        self.write("a.md", "消える段落\n")
        self.commit()
        (self.root / "a.md").unlink()
        self.assertEqual(self.rows(), [])

    def test_line_numbers_follow_the_working_tree_not_the_committed_version(self):
        """コミット済みの変更の上に未コミットの挿入がある。番号は作業ツリーでの位置."""
        self.write("a.md", "一\n二\n三\n")
        self.commit("base")
        base = self.git("rev-parse", "HEAD").stdout.strip()
        self.write("a.md", "一\n二\n三を直した\n")
        self.commit("edit")
        self.write("a.md", "冒頭に足した\n一\n二\n三を直した\n")
        res = self.run_md("--base", base)
        self.assertEqual(res.returncode, 0, res.stderr)
        got = [tuple(l.split("\t")) for l in res.stdout.splitlines()]
        self.assertEqual(got, [("a.md", "1", "冒頭に足した"), ("a.md", "4", "三を直した")])


class MdProseExclusionTest(MdProseTestBase):
    """推敲に渡してはいけない行（書き換えると別の検査や参照を壊す）."""

    def only_prose(self, body: str) -> list[str]:
        self.write("a.md", body)
        return [r[2] for r in self.rows()]

    def test_frontmatter_is_excluded(self):
        self.assertEqual(self.only_prose("---\nname: x\ndescription: 説明文\n---\n本文\n"), ["本文"])

    def test_frontmatter_ends_at_the_first_closing_line(self):
        """閉じた後の `---` は区切り線。そこまでを frontmatter に含めない."""
        self.assertEqual(self.only_prose("---\nname: x\n---\n本文A\n\n---\n\n本文B\n"),
                         ["本文A", "本文B"])

    def test_frontmatter_closed_with_dots_is_excluded(self):
        """YAML の文書終端 `...` でも閉じる。閉じ行そのものも本文ではない."""
        self.assertEqual(self.only_prose("---\nname: x\n...\n本文\n"), ["本文"])

    def test_frontmatter_only_counts_from_the_first_line(self):
        """2 行目以降の `---` は区切り線で、その間の行は本文."""
        self.assertEqual(self.only_prose("本文\n\n---\n\n次の段落\n"), ["本文", "次の段落"])

    def test_fenced_code_is_excluded(self):
        body = "前\n```bash\necho 散文に見える\n```\n後\n~~~\nチルダの中\n~~~\n最後\n"
        self.assertEqual(self.only_prose(body), ["前", "後", "最後"])

    def test_a_shorter_fence_does_not_close_a_longer_one(self):
        body = "前\n````md\n```\n内側\n```\n````\n後\n"
        self.assertEqual(self.only_prose(body), ["前", "後"])

    def test_a_fence_of_the_other_character_does_not_close(self):
        body = "前\n```\n~~~\n内側\n```\n後\n"
        self.assertEqual(self.only_prose(body), ["前", "後"])

    def test_a_fence_line_with_an_info_string_does_not_close(self):
        body = "前\n```\n```python\n内側\n```\n後\n"
        self.assertEqual(self.only_prose(body), ["前", "後"])

    def test_indented_fence_up_to_three_spaces_opens(self):
        body = "前\n   ```\n内側\n   ```\n後\n"
        self.assertEqual(self.only_prose(body), ["前", "後"])

    def test_html_comments_are_excluded(self):
        """SSoT pin やマーカー行、複数行のコメント。コメントと同じ行の散文も渡さない."""
        body = ("前\n<!-- SSOT: a.md#1 @abcd1234 -->\n<!-- 複数行の\nコメントの中\n-->\n"
                "<!-- 閉じ --> 同じ行の散文\n後\n")
        self.assertEqual(self.only_prose(body), ["前", "後"])

    def test_a_comment_closed_on_its_own_line_resumes_prose(self):
        self.assertEqual(self.only_prose("<!-- 1 行 -->\n本文\n"), ["本文"])

    def test_headings_are_excluded(self):
        body = "# 題\n## 16. 節\n   ### 字下げ見出し\n####### 7 個は見出しではない\n本文\n#タグ風\n"
        self.assertEqual(self.only_prose(body), ["####### 7 個は見出しではない", "本文", "#タグ風"])

    def test_table_separator_is_excluded_but_rows_are_kept(self):
        body = "| 項目 | 内容 |\n|------|:----:|\n| 認証 | OAuth |\n"
        self.assertEqual(self.only_prose(body), ["| 項目 | 内容 |", "| 認証 | OAuth |"])

    def test_link_only_lines_and_definitions_are_excluded(self):
        body = "[README](README.md)\n- [節](a.md#x)\n1. [手順](b.md)\n[ref]: https://example.com\n本文 [リンク](a.md) つき\n"
        self.assertEqual(self.only_prose(body), ["本文 [リンク](a.md) つき"])

    def test_marker_only_lines_are_excluded(self):
        body = "本文\n\n---\n\n* * *\n> \n- \n___\n"
        self.assertEqual(self.only_prose(body), ["本文"])

    def test_fences_indented_in_a_list_or_quoted_are_code(self):
        """箇条の中のフェンスは 4 桁以上字下げされる。引用の中のフェンスも同じ."""
        body = ("- 箇条\n    ```bash\n    echo 見つかりません\n    ```\n"
                "> ```python\n> print(1)\n> ```\n後\n")
        self.assertEqual(self.only_prose(body), ["- 箇条", "後"])

    def test_comment_marker_inside_inline_code_is_not_a_comment(self):
        body = "行頭が `<!--` のときはコメント扱い\n次の段落\n"
        self.assertEqual(self.only_prose(body), ["行頭が `<!--` のときはコメント扱い", "次の段落"])

    def test_duplicated_regions_are_excluded(self):
        """`<!-- NAME:START -->` 〜 `END` は byte 一致を検証される複製区間."""
        body = "前\n<!-- RULE:START -->\n複製された本文\n<!-- RULE:END -->\n後\n"
        self.assertEqual(self.only_prose(body), ["前", "後"])

    def test_setext_heading_text_is_excluded(self):
        """段落の直後の `===` / `---` は見出しの下線。本文もアンカーになる."""
        body = "見出し 1\n========\n\n本文\n\n見出し 2\n続きの行\n---\n\n最後\n"
        self.assertEqual(self.only_prose(body), ["本文", "最後"])

    def test_setext_heading_takes_the_whole_paragraph(self):
        """段落の途中の対象外の行（リンクだけの行）も段落の一部。その上の行まで見出しになる."""
        body = "前置き\n\n段落の 1 行目\n[リンク](a.md)\n段落の 3 行目\n---\n"
        self.assertEqual(self.only_prose(body), ["前置き"])

    def test_setext_heading_stops_at_an_atx_heading(self):
        """ATX 見出しは段落に入らない。その上の散文を見出し扱いにしない."""
        self.assertEqual(self.only_prose("前\n# 見出し\n本文\n---\n"), ["前"])

    def test_a_rule_after_a_list_item_does_not_make_it_a_heading(self):
        self.assertEqual(self.only_prose("- 箇条\n---\n"), ["- 箇条"])

    def test_vendored_and_generated_markdown_is_excluded(self):
        self.write("vendor/github.com/x/README.md", "第三者の文書\n")
        self.write("dist/a.md", "生成物\n")
        self.write("docs/api.generated.md", "生成物\n")
        self.write("docs/a.md", "自分の文書\n")
        self.assertEqual([r[0] for r in self.rows()], ["docs/a.md"])

    def test_tabs_in_a_line_are_kept_verbatim(self):
        """本文は置き換えずに出す（Step 7 が行の全文で位置を決める）。列は先頭 2 つのタブで切る."""
        self.write("a.md", "左\t右\n")
        self.assertEqual(self.rows(), [("a.md", 1, "左\t右")])

    def test_a_lone_carriage_return_does_not_shift_line_numbers(self):
        """git は LF で行を数える。行の途中の CR で割ると、変更していない行が出る."""
        (self.root / "a.md").write_bytes("一\rおまけ\n二\n三\n".encode("utf-8"))
        self.commit()
        (self.root / "a.md").write_bytes("一\rおまけ\n二\n三を直した\n".encode("utf-8"))
        self.assertEqual([r[1] for r in self.rows()], [3])

    def test_inline_code_with_backticks_at_the_start_is_not_a_fence(self):
        """行頭の行内コードに 3 連のバッククォートがあってもフェンスではない（info に ` は入らない）."""
        body = "```` ``` ```` で囲む\n次の段落\n"
        self.assertEqual(self.only_prose(body), ["```` ``` ```` で囲む", "次の段落"])

    def test_a_fence_right_after_a_list_marker_is_code(self):
        body = "- ```bash\n  echo コード\n  ```\n後\n"
        self.assertEqual(self.only_prose(body), ["後"])

    def test_a_rule_after_a_quote_table_or_html_is_not_a_heading(self):
        """引用・表・HTML ブロック・箇条の続きの直後の `---` は区切り線。手前の散文を落とさない."""
        body = ("> 引用の散文\n---\n\n| 列 |\n|----|\n| 値 |\n---\n\n"
                "- 項目\n  続きの行\n---\n\n<p>段落</p>\n---\n")
        self.assertEqual(self.only_prose(body),
                         ["> 引用の散文", "| 列 |", "| 値 |", "- 項目", "  続きの行", "<p>段落</p>"])


class MdProseDiffParsingTest(MdProseTestBase):
    def test_noprefix_git_config_does_not_drop_files(self):
        """`diff.noprefix` / `diff.mnemonicPrefix` の設定で `+++ b/` が付かなくても落とさない."""
        for key in ("diff.noprefix", "diff.mnemonicPrefix"):
            with self.subTest(key=key):
                self.git("config", key, "true")
                self.write("a.md", "段落 %s\n" % key)
                self.assertEqual([r[0] for r in self.rows()], ["a.md"])
                self.git("config", "--unset", key)

    def test_path_with_a_space_is_kept(self):
        """空白を含むパスには git が末尾にタブを付ける."""
        self.write("docs/Meeting Notes.md", "議事\n")
        self.assertEqual(self.rows(), [("docs/Meeting Notes.md", 1, "議事")])

    def test_an_added_line_starting_with_plus_plus_is_not_a_header(self):
        """本文の `++ ` で始まる行は diff 上で `+++ ` になる。後ろの hunk を落とさない."""
        self.write("a.md", "一\n二\n三\n四\n五\n")
        self.commit()
        self.write("a.md", "一\n++ 増分\n二\n三\n四\n五\n末尾に足した\n")
        self.assertEqual([r[1] for r in self.rows()], [2, 7])

    def test_non_utf8_markdown_is_skipped_without_breaking_the_count(self):
        """UTF-8 でない md は推敲に渡さない。落ちずに他のファイルを数える."""
        (self.root / "latin.md").write_bytes("caf\xe9 au lait\n".encode("latin-1"))
        self.write("a.md", "本文\n")
        self.add()
        res = self.run_md("--base", "HEAD", "--count")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("md_prose_lines=1", res.stdout)


class MdProseStagedTest(MdProseTestBase):
    def test_staged_crlf_file_keeps_frontmatter_out(self):
        """index の内容は改行を変換しない。CRLF でも frontmatter を本文と取り違えない."""
        (self.root / "a.md").write_bytes("---\r\nname: x\r\n---\r\n本文\r\n".encode("utf-8"))
        self.add()
        res = self.run_md("--staged")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.splitlines(), ["a.md\t4\t本文"])

    def test_staged_reads_the_index_not_the_working_tree(self):
        self.write("a.md", "一\n")
        self.commit()
        self.write("a.md", "一\nステージした\n")
        self.add()
        self.write("a.md", "一\nステージした\n未ステージ\n")
        res = self.run_md("--staged")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.splitlines(), ["a.md\t2\tステージした"])


class MdProseCapTest(MdProseTestBase):
    def test_rows_beyond_the_cap_are_counted_not_dropped_silently(self):
        self.write("a.md", "".join("段落 %d\n" % i for i in range(5)))
        self.add()
        res = self.run_md("--base", "HEAD", "--cap", "3")
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = res.stdout.splitlines()
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[-1], "# truncated\t2")

    def test_no_truncation_line_at_exactly_the_cap(self):
        self.write("a.md", "一\n二\n三\n")
        self.add()
        res = self.run_md("--base", "HEAD", "--cap", "3")
        self.assertNotIn("# truncated", res.stdout)
        self.assertEqual(len(res.stdout.splitlines()), 3)


class MdProseCountTest(MdProseTestBase):
    def count(self, *args: str) -> dict[str, str]:
        self.add()
        res = self.run_md("--base", "HEAD", "--count", *args)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.splitlines()[0], "## md-polish")
        return self.kv(res.stdout, "## md-polish")

    def settings(self, where: str, enabled) -> None:
        path = {"user": self.root / "home" / ".claude" / "settings.json",
                "project": self.root / ".claude" / "settings.json",
                "local": self.root / ".claude" / "settings.local.json"}[where]
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {"enabledPlugins": {} if enabled is None else
                {"writing-polish@yuuki1036-claude-plugins": enabled}}
        path.write_text(json.dumps(body, indent=2), encoding="utf-8")

    def test_count_reports_the_number_of_prose_lines_beyond_the_cap(self):
        self.write("a.md", "".join("段落 %d\n" % i for i in range(5)))
        self.assertEqual(self.count("--cap", "2")["md_prose_lines"], "5")

    def test_count_is_zero_without_markdown(self):
        self.write("src/a.py", "x = 1\n")
        self.assertEqual(self.count()["md_prose_lines"], "0")

    def test_writing_polish_enabled_in_user_settings(self):
        self.settings("user", True)
        self.assertEqual(self.count()["writing_polish"], "1")

    def test_writing_polish_enabled_only_in_project_local_settings(self):
        self.settings("local", True)
        self.assertEqual(self.count()["writing_polish"], "1")

    def test_writing_polish_enabled_only_in_project_settings(self):
        self.settings("project", True)
        self.assertEqual(self.count()["writing_polish"], "1")

    def test_project_local_false_overrides_user_true(self):
        """優先順位の高い設定が勝つ（ローカルで無効にしたプロジェクトでは起動しない）."""
        self.settings("user", True)
        self.settings("local", False)
        self.assertEqual(self.count()["writing_polish"], "0")

    def test_project_true_overrides_user_false(self):
        self.settings("user", False)
        self.settings("project", True)
        self.assertEqual(self.count()["writing_polish"], "1")

    def test_a_file_without_the_key_does_not_decide(self):
        """キーの無い上位の設定は飛ばして、次の設定で決める."""
        self.settings("local", None)
        self.settings("user", True)
        self.assertEqual(self.count()["writing_polish"], "1")

    def test_disabled_or_absent_writing_polish_is_not_enabled(self):
        """`false` はインストール済みで無効化。キーの存在だけを見ると有効に化ける."""
        for enabled in (False, None):
            with self.subTest(enabled=enabled):
                self.settings("user", enabled)
                self.assertEqual(self.count()["writing_polish"], "0")

    def test_no_settings_file_is_not_enabled(self):
        self.assertEqual(self.count()["writing_polish"], "0")


class MdProseArgumentTest(MdProseTestBase):
    def test_base_or_staged_is_required(self):
        res = self.run_md()
        self.assertEqual(res.returncode, 2)
        self.assertIn("--base か --staged", res.stderr)

    def test_cap_must_be_numeric(self):
        res = self.run_md("--base", "HEAD", "--cap", "3x")
        self.assertEqual(res.returncode, 2)
        self.assertIn("--cap は数値のみ", res.stderr)

    def test_unknown_argument_is_rejected(self):
        res = self.run_md("--base", "HEAD", "--bogus")
        self.assertEqual(res.returncode, 2)

    def test_unknown_base_fails_loudly(self):
        res = self.run_md("--base", "no-such-ref")
        self.assertEqual(res.returncode, 1)
        self.assertIn("FATAL", res.stderr)


if __name__ == "__main__":
    unittest.main()
