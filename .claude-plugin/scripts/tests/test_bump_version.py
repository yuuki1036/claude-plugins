#!/usr/bin/env python3
"""`bump-version.sh` の回帰テスト（CLI 境界越しの subprocess テスト）.

**なぜあるか**: `vNEXT` プレースホルダの解決は「置換してよい `vNEXT`」の判定を
`bump-version.sh`（置換側）と `validate_plugin_quality.py`（残存検査側）が
**別々に実装している**。同じ規約の二重実装は必ずずれる — 実際にセルフレビューで
「フェンス内除外の条件が片方だけ緩い」形のずれが出た。ずれた瞬間に
「置換されないのに検査は鳴らない `vNEXT`」＝**永久に古い版ラベル**が生まれる。

置換側はここで、残存検査側は `test_validate_plugin_quality.py` で、
**同じ入力に対する期待を独立に**書く（片方の実装を流用して期待値を作らない）。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from git_env import scrub

SCRIPT = Path(__file__).resolve().parents[1] / "bump-version.sh"


class BumpVersionSandbox(unittest.TestCase):
    """本物の git リポジトリを立てて CLI をそのまま叩く."""

    PLUGIN = "demo-plugin"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._git("init", "-q")
        self._git("config", "user.email", "t@example.com")
        self._git("config", "user.name", "t")
        d = self.root / self.PLUGIN / ".claude-plugin"
        d.mkdir(parents=True)
        (d / "plugin.json").write_text(json.dumps(
            {"name": self.PLUGIN, "version": "1.2.3", "description": "demo"}), encoding="utf-8")
        (self.root / ".claude-plugin").mkdir(exist_ok=True)
        (self.root / ".claude-plugin" / "marketplace.json").write_text(json.dumps(
            {"plugins": [{"name": self.PLUGIN, "source": f"./{self.PLUGIN}",
                          "version": "1.2.3", "description": "demo"}]}), encoding="utf-8")
        (self.root / "INDEX.md").write_text(
            f"| [{self.PLUGIN}](#{self.PLUGIN}) | 1.2.3 | 1 | 1 | - | - | - | demo |\n", encoding="utf-8")
        (self.root / self.PLUGIN / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [1.2.3] - 2026-01-01\n\n- 初版\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True,
                              env=self._env())

    def _env(self) -> dict[str, str]:
        """git hook 由来の変数を落とした env（正本と理由は `git_env` の docstring）.

        **`bump-version.sh` 自身も git を叩く**ので、`_git` だけでなくスクリプトの起動にも
        通す（linked worktree から commit すると `demo-plugin` の `init` コミットが
        **実リポジトリ**に乗っていた / GitHub issue #158）。
        """
        return scrub()

    def _commit_all(self):
        self._git("add", "-A")
        self._git("commit", "-qm", "init")

    def _bump(self, *args, expect_ok: bool = True):
        r = subprocess.run(["bash", str(SCRIPT), self.PLUGIN, *args],
                           cwd=self.root, capture_output=True, text=True, env=self._env())
        if expect_ok:
            # **異常終了を「変わっていない」で素通りさせない**。中断しても
            # 「置換されないこと」を確かめる系のテストは全部緑になってしまう
            self.assertEqual(r.returncode, 0, f"bump が失敗した: {r.stderr}")
        return r

    def _write(self, rel: str, body: str) -> Path:
        p = self.root / self.PLUGIN / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body), encoding="utf-8")
        return p


class VnextResolutionTest(BumpVersionSandbox):
    """`vNEXT` を実版に解決する（置換側の仕様）."""

    def test_bare_placeholder_is_replaced(self):
        f = self._write("references/note.md", "この挙動は vNEXT で入った\n")
        self._commit_all()
        r = self._bump("patch")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(f.read_text(), "この挙動は v1.2.4 で入った\n")

    def test_inline_code_is_not_replaced(self):
        """行内コードの `vNEXT` は規約の説明なので触らない."""
        f = self._write("references/note.md", "プレースホルダは `vNEXT` と書く\n")
        self._commit_all()
        self._bump("patch")
        self.assertEqual(f.read_text(), "プレースホルダは `vNEXT` と書く\n")

    def test_fenced_block_is_not_replaced(self):
        f = self._write("references/note.md", """\
            例:

            ```markdown
            この挙動は vNEXT で入った
            ```
            """)
        self._commit_all()
        self._bump("patch")
        self.assertIn("この挙動は vNEXT で入った", f.read_text())

    def test_tilde_fence_is_not_replaced(self):
        """フェンスは ``` だけではない（~~~ を取りこぼすと説明文が壊れる）."""
        f = self._write("references/note.md", """\
            ~~~
            この挙動は vNEXT で入った
            ~~~
            """)
        self._commit_all()
        self._bump("patch")
        self.assertIn("vNEXT", f.read_text())

    def test_only_target_plugin_is_touched(self):
        """他プラグイン / repo 直下は解決しない（どの版に解決すべきか決まらない）."""
        other = self.root / "other-plugin" / ".claude-plugin"
        other.mkdir(parents=True)
        (other / "plugin.json").write_text(json.dumps(
            {"name": "other-plugin", "version": "9.9.9", "description": "x"}), encoding="utf-8")
        outside = self.root / "other-plugin" / "note.md"
        outside.write_text("この挙動は vNEXT で入った\n", encoding="utf-8")
        repo_level = self.root / "README.md"
        repo_level.write_text("この挙動は vNEXT で入った\n", encoding="utf-8")
        self._write("references/note.md", "この挙動は vNEXT で入った\n")
        self._commit_all()
        self._bump("patch")
        self.assertIn("vNEXT", outside.read_text())
        self.assertIn("vNEXT", repo_level.read_text())

    def test_sh_and_py_are_covered(self):
        """md だけでなく同梱スクリプトのコメントも対象."""
        sh = self._write("scripts/x.sh", "# vNEXT で追加\n")
        py = self._write("scripts/x.py", "# vNEXT で追加\n")
        self._commit_all()
        self._bump("patch")
        self.assertEqual(sh.read_text(), "# v1.2.4 で追加\n")
        self.assertEqual(py.read_text(), "# v1.2.4 で追加\n")

    def test_multiple_hits_on_one_line(self):
        f = self._write("references/note.md", "vNEXT と vNEXT\n")
        self._commit_all()
        self._bump("patch")
        self.assertEqual(f.read_text(), "v1.2.4 と v1.2.4\n")

    def test_dry_run_writes_nothing(self):
        """--dry-run は**どのファイルにも**書かない（版もプレースホルダも）."""
        f = self._write("references/note.md", "この挙動は vNEXT で入った\n")
        self._commit_all()
        r = self._bump("patch", "--dry-run")
        self.assertIn("vNEXT", f.read_text())
        self.assertIn("1.2.3", (self.root / self.PLUGIN / ".claude-plugin" / "plugin.json").read_text())
        self.assertIn("dry-run", r.stdout)

    def test_reports_hit_count(self):
        self._write("references/a.md", "vNEXT\nvNEXT\n")
        self._write("references/b.md", "vNEXT\n")
        self._commit_all()
        r = self._bump("patch")
        self.assertIn("3 箇所 / 2 ファイル", r.stdout)

    def test_version_files_are_updated_together(self):
        """4 ファイル同時更新（vNEXT 解決を後段に足しても壊れていないこと）."""
        self._commit_all()
        self._bump("patch")
        self.assertEqual(json.loads(
            (self.root / self.PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"], "1.2.4")
        self.assertIn("1.2.4", (self.root / ".claude-plugin" / "marketplace.json").read_text())
        self.assertIn("1.2.4", (self.root / "INDEX.md").read_text())
        self.assertIn("[1.2.4]", (self.root / self.PLUGIN / "CHANGELOG.md").read_text())

    def test_file_mode_is_preserved(self):
        """置換で実行ビットを落とさない."""
        sh = self._write("scripts/x.sh", "# vNEXT\n")
        os.chmod(sh, 0o755)
        self._commit_all()
        self._bump("patch")
        self.assertEqual(oct(os.stat(sh).st_mode & 0o777), "0o755")


class ChangelogHeadingAndVnextTest(BumpVersionSandbox):
    """見出し挿入（4）と `vNEXT` 解決（5）が**同じファイル**に乗るケース（GitHub issue #174）.

    2 つの変更を別エントリで積むと書き込みが後勝ちになり、先に積んだ見出し挿入が
    「挿入した」と報告したまま消える。**報告と実物の一致**をここで固定する。
    """

    def test_heading_survives_vnext_resolution_in_changelog(self):
        """CHANGELOG 本文に `vNEXT` があっても新規見出しは消えない.

        期待値はテスト側で独立に組む（実装から導かない）: bump 後の CHANGELOG は
        ①新版の見出しを持ち ②旧版の見出しも残り ③本文の `vNEXT` が解決されている。
        """
        cl = self.root / self.PLUGIN / "CHANGELOG.md"
        cl.write_text("# Changelog\n\n## [1.2.3] - 2026-01-01\n\n- vNEXT で入った\n", encoding="utf-8")
        self._commit_all()
        self._bump("patch")
        body = cl.read_text()
        self.assertIn("## [1.2.4]", body, "新規見出しが vNEXT 解決に上書きされて消えている")
        self.assertIn("## [1.2.3]", body, "旧版の見出しが消えている")
        self.assertIn("- v1.2.4 で入った", body, "本文の vNEXT が解決されていない")
        self.assertNotIn("vNEXT", body)

    def test_report_matches_what_was_written(self):
        """「見出しのみ挿入した」と報告したなら実際に入っていること（虚偽報告の禁止）."""
        cl = self.root / self.PLUGIN / "CHANGELOG.md"
        cl.write_text("# Changelog\n\n## [1.2.3] - 2026-01-01\n\n- vNEXT\n", encoding="utf-8")
        self._commit_all()
        r = self._bump("patch")
        self.assertIn("CHANGELOG は見出しのみ挿入した", r.stdout)
        self.assertIn("## [1.2.4]", cl.read_text())

    def test_the_heading_note_is_absent_when_no_heading_was_inserted(self):
        """見出しを挿入していない実行で「見出しのみ挿入した」と言わない.

        報告と実物の一致は双方向で要る（挿入したのに言わない／言ったのに挿入しない）。
        `--sync` は CHANGELOG を正とするので見出しを触らない。
        """
        self._write("references/note.md", "この挙動は vNEXT で入った\n")
        self._commit_all()
        r = self._bump("--sync")
        self.assertNotIn("CHANGELOG は見出しのみ挿入した", r.stdout,
                         "挿入していないのに挿入したと報告している")

    def test_the_heading_note_is_absent_when_the_heading_already_exists(self):
        """既に同じ版の見出しがある next 実行でも報告しない."""
        cl = self.root / self.PLUGIN / "CHANGELOG.md"
        cl.write_text("# Changelog\n\n## [1.2.4] - 2026-01-02\n\n- 先に書いた\n\n"
                      "## [1.2.3] - 2026-01-01\n\n- 初版\n", encoding="utf-8")
        self._write("references/note.md", "この挙動は vNEXT で入った\n")
        self._commit_all()
        r = self._bump("patch")
        self.assertNotIn("CHANGELOG は見出しのみ挿入した", r.stdout,
                         "既存見出しを挿入したと報告している")

    def test_changelog_without_placeholder_is_unaffected(self):
        """`vNEXT` を含まない CHANGELOG の挙動は変わらない（畳み込みの副作用が無いこと）."""
        cl = self.root / self.PLUGIN / "CHANGELOG.md"
        self._commit_all()
        self._bump("patch")
        body = cl.read_text()
        self.assertIn("## [1.2.4]", body)
        self.assertIn("## [1.2.3]", body)
        self.assertIn("- 初版", body)


class SyncResolvesVnextTest(BumpVersionSandbox):
    """4 ファイルが同期済みでも `vNEXT` の解決だけは進む（GitHub issue #174）.

    版が動かないことを理由に打ち切ると、`--sync` では `vNEXT` が永久に残る
    （検査側は残存を鳴らすのに、解決手段が効かない状態になる）。
    """

    def test_sync_resolves_vnext_when_versions_already_match(self):
        f = self._write("references/note.md", "この挙動は vNEXT で入った\n")
        self._commit_all()
        r = self._bump("--sync")
        self.assertEqual(f.read_text(), "この挙動は v1.2.3 で入った\n",
                         "同期済みを理由に打ち切られ vNEXT が残っている")
        self.assertIn("既に同期済み", r.stdout)

    def test_sync_does_not_move_the_version(self):
        """解決のついでに版を動かさない（--sync は CHANGELOG を正とする契約）."""
        self._write("references/note.md", "vNEXT\n")
        self._commit_all()
        r = self._bump("--sync")
        self.assertEqual(json.loads(
            (self.root / self.PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"], "1.2.3")
        self.assertIn("版は据え置き", r.stdout, "版が動いたかのように報告している")

    def test_a_real_bump_reports_the_transition(self):
        """版が動く実行では遷移を出す（据え置きの文言と取り違えない）."""
        self._commit_all()
        r = self._bump("patch")
        self.assertIn("1.2.3 → 1.2.4", r.stdout)
        self.assertNotIn("版は据え置き", r.stdout)

    def test_sync_dry_run_writes_nothing(self):
        f = self._write("references/note.md", "この挙動は vNEXT で入った\n")
        self._commit_all()
        self._bump("--sync", "--dry-run")
        self.assertIn("vNEXT", f.read_text())

    def test_no_placeholder_still_reports_no_change(self):
        """`vNEXT` が無ければ従来どおり「変更なし」で終わる（無駄な書き込みをしない）."""
        self._commit_all()
        r = self._bump("--sync")
        self.assertIn("変更なし", r.stdout)


class VnextAgreesWithResidualCheckTest(BumpVersionSandbox):
    """置換側と残存検査側の判定が一致すること（二重実装のずれを直接測る）.

    **置換されない `vNEXT` を検査側も無視する**なら安全（説明文）。
    **置換されないのに検査側が鳴らす**のは偽陽性、
    **置換されるのに検査側が見ない**のは取りこぼし。ここでは前者の合意だけ固定する
    — 「行内コード / フェンス内は両方とも対象外」が規約の核だから。
    """

    def test_protected_forms_survive_and_are_not_flagged(self):
        f = self._write("references/note.md", """\
            プレースホルダは `vNEXT` と書く

            ```markdown
            この挙動は vNEXT で入った
            ```
            """)
        self._commit_all()
        self._bump("patch")
        self.assertEqual(f.read_text().count("vNEXT"), 2, "保護された 2 箇所は置換されない")

        import importlib.util
        import sys
        spec = importlib.util.spec_from_file_location(
            "_vq_for_bump_test", Path(__file__).resolve().parents[1] / "validate_plugin_quality.py")
        vq = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = vq
        spec.loader.exec_module(vq)
        errors: list[str] = []
        # 検査側は「bump 済みか」を git で見るので、ここでは走査部だけを同じ入力に当てる
        lines = f.read_text().splitlines()
        live = "\n".join(vq.INLINE_CODE_RE.sub("", line) for _, line in vq._iter_unfenced_lines(lines))
        self.assertNotIn("vNEXT", live, "置換されない形は検査側も鳴らさない（偽陽性の禁止）")
        self.assertEqual(errors, [])


class VnextHeadingTest(BumpVersionSandbox):
    """CHANGELOG 先頭の `## [vNEXT]` 見出しを実版へ解決する（issue #237）.

    以前は数値版の見出ししか見ておらず、`## [vNEXT]` を書いて `--sync` すると先頭が前版と
    判定され、「既に同期済み」＋ 一括置換で `## [v1.2.3]`（前版・v 接頭辞・日付なし）に
    化けていた。exit 0 で成功に見えるのが最悪だったので、結果の見出しと版を直接見る。
    """

    def _changelog(self) -> Path:
        return self.root / self.PLUGIN / "CHANGELOG.md"

    def _write_vnext_changelog(self, body: str = "- 新しい何か\n"):
        self._changelog().write_text(
            "# Changelog\n\n## [vNEXT]\n\n" + body + "\n## [1.2.3] - 2026-01-01\n\n- 初版\n",
            encoding="utf-8")

    def _plugin_version(self) -> str:
        return json.loads(
            (self.root / self.PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]

    def test_sync_resolves_vnext_heading_to_next_patch(self):
        self._write_vnext_changelog()
        self._commit_all()
        r = self._bump("--sync")
        text = self._changelog().read_text()
        self.assertEqual(self._plugin_version(), "1.2.4")
        self.assertIn("1.2.3 → 1.2.4", r.stdout)
        self.assertNotIn("## [vNEXT]", text)
        self.assertNotIn("## [v1.2.4]", text, "v 接頭辞つきの不正な見出しに化けている")
        self.assertEqual(text.count("## [1.2.3]"), 1, "前版の見出しが重複している")
        self.assertRegex(text, r"(?m)^## \[1\.2\.4\] - \d{4}-\d{2}-\d{2}$")

    def test_sync_keeps_body_below_resolved_heading(self):
        """見出し行だけを書き換え、本文は動かさない."""
        self._write_vnext_changelog("- 本文 A\n- 本文 B\n")
        self._commit_all()
        self._bump("--sync")
        text = self._changelog().read_text()
        self.assertLess(text.index("## [1.2.4]"), text.index("- 本文 A"))
        self.assertLess(text.index("- 本文 B"), text.index("## [1.2.3]"))

    def test_level_resolves_vnext_heading_instead_of_inserting(self):
        """`minor` 指定なら vNEXT 見出しがその版になり、見出しは増えない."""
        self._write_vnext_changelog()
        self._commit_all()
        r = self._bump("minor")
        text = self._changelog().read_text()
        self.assertEqual(self._plugin_version(), "1.3.0")
        self.assertRegex(text, r"(?m)^## \[1\.3\.0\] - \d{4}-\d{2}-\d{2}$")
        self.assertEqual(len([l for l in text.splitlines() if l.startswith("## [")]), 2,
                         "見出しが挿入されて 3 つになっている")
        self.assertNotIn("見出しのみ挿入した", r.stdout)

    def test_vnext_heading_and_body_placeholder_resolve_to_the_same_version(self):
        self._write_vnext_changelog("- この挙動は vNEXT で入った\n")
        self._commit_all()
        self._bump("--sync")
        text = self._changelog().read_text()
        self.assertNotIn("vNEXT", text)
        self.assertIn("この挙動は v1.2.4 で入った", text)

    def test_sync_dry_run_leaves_vnext_heading(self):
        self._write_vnext_changelog()
        self._commit_all()
        r = self._bump("--sync", "--dry-run")
        self.assertIn("## [vNEXT]", self._changelog().read_text())
        self.assertEqual(self._plugin_version(), "1.2.3")
        self.assertIn("1.2.4", r.stdout)

    def test_vnext_heading_below_top_is_fatal(self):
        """先頭以外の vNEXT 見出しは解決先が決まらないので止める."""
        self._changelog().write_text(
            "# Changelog\n\n## [1.2.3] - 2026-01-01\n\n- 初版\n\n## [vNEXT]\n\n- 迷子\n",
            encoding="utf-8")
        self._commit_all()
        r = self._bump("--sync", expect_ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("FATAL", r.stderr)
        self.assertEqual(self._plugin_version(), "1.2.3")
        self.assertIn("## [vNEXT]", self._changelog().read_text(), "止めたのに書き換わっている")

    def test_level_with_a_newer_numeric_heading_is_fatal(self):
        """`patch` の計算結果より新しい見出しが先頭にあれば --sync の取り違えとして止める."""
        self._changelog().write_text(
            "# Changelog\n\n## [1.2.5] - 2026-02-02\n\n- x\n\n## [1.2.3] - 2026-01-01\n\n- 初版\n",
            encoding="utf-8")
        self._commit_all()
        r = self._bump("patch", expect_ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--sync のつもりでは", r.stderr)
        self.assertEqual(self._plugin_version(), "1.2.3")

    def test_numeric_heading_sync_is_unchanged(self):
        """従来の数値見出しの --sync 経路は影響を受けない."""
        self._changelog().write_text(
            "# Changelog\n\n## [1.2.4] - 2026-02-02\n\n- x\n\n## [1.2.3] - 2026-01-01\n\n- 初版\n",
            encoding="utf-8")
        self._commit_all()
        self._bump("--sync")
        self.assertEqual(self._plugin_version(), "1.2.4")
        self.assertIn("## [1.2.4] - 2026-02-02", self._changelog().read_text())


class DocOnlyAdviceTest(BumpVersionSandbox):
    """docs-only 助言（「変更が *.md のみだが MINOR」）の判定は untracked も見る."""

    ADVICE = "変更が *.md のみ"

    def test_untracked_script_is_not_doc_only(self):
        """新規 .sh を足した回（git diff には出ない）を *.md のみと誤警告しない."""
        self._commit_all()
        self._write("scripts/new.sh", "#!/bin/sh\n")
        self._write("references/note.md", "x\n")
        r = self._bump("minor")
        self.assertNotIn(self.ADVICE, r.stdout)

    def test_md_only_change_still_advises(self):
        self._commit_all()
        self._write("references/note.md", "x\n")
        r = self._bump("minor")
        self.assertIn(self.ADVICE, r.stdout)

    def test_ignored_untracked_file_does_not_count(self):
        """.gitignore 対象（ビルド生成物等）はコード変更として数えない."""
        (self.root / ".gitignore").write_text("*.log\n")
        self._commit_all()
        self._write("scripts/debug.log", "noise\n")
        self._write("references/note.md", "x\n")
        r = self._bump("minor")
        self.assertIn(self.ADVICE, r.stdout)


if __name__ == "__main__":
    unittest.main()
