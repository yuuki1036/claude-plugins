#!/usr/bin/env python3
"""adr-keeper の hook スクリプトの回帰テスト.

- `adr-write-guard.sh` — `.claude/adr/` 直下への**新規**作成（Write と、old_string 空の Edit）だけを見て、スキルの手順から
  外れた ADR（id とファイル名の不一致・現在時刻から離れた id・テンプレの見出しの欠落）を
  exit 2 で止める。**Write はすべてのファイル編集で鳴りうる**ので、黙る条件（ADR 以外の
  パス・既存ファイルの上書き・Edit・壊れた入力）を厚く書く
- `check-deps.sh` — jq が無いときだけ知らせる。任意依存の doc-freshness が無くても黙る

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import datetime
import unittest
from pathlib import Path

from hook_harness import HookTestCase, TempGitRepo

HEADINGS = [
    "## ステータス",
    "## コンテキスト / 背景",
    "## 決定",
    "## 影響 (Consequences)",
    "## 適用方法 (Enforcement)",
    "## 検討した代替案",
    "## 関連",
]


def ts(offset_sec: int = 0) -> str:
    """ローカル時刻の `date +%Y%m%d%H%M%S` 相当（hook も date のローカル時刻で比べる）."""
    t = datetime.datetime.now() + datetime.timedelta(seconds=offset_sec)
    return t.strftime("%Y%m%d%H%M%S")


def adr_body(id_: str, *, headings=HEADINGS, frontmatter_id: str | None = None) -> str:
    fm_id = id_ if frontmatter_id is None else frontmatter_id
    lines = [
        "---",
        f"id: {fm_id}",
        "status: accepted",
        "phase: current",
        "append_only: true",
        "---",
        "",
        f"# ADR-{id_}: テスト",
        "",
    ]
    for h in headings:
        lines += [h, "", "本文", ""]
    return "\n".join(lines)


class AdrWriteGuardTest(HookTestCase):
    PLUGIN = "adr-keeper"
    SCRIPT = "hooks/scripts/adr-write-guard.sh"

    def _write(self, root: Path, rel: str, content: str, tool: str = "Write", absolute: bool = True,
               tool_input: dict | None = None, env: dict | None = None):
        path = str(root / rel) if absolute else rel
        ti = {"file_path": path, "content": content} if tool_input is None else {"file_path": path, **tool_input}
        payload = {"tool_name": tool, "tool_input": ti}
        return self.run_hook(payload, cwd=root, env_extra={"CLAUDE_PROJECT_DIR": str(root), **(env or {})})

    def assertBlocked(self, res, contains: str = ""):
        self.assertEqual(res.returncode, 2, f"止めるはず: {res!r}")
        if contains:
            self.assertIn(contains, res.stderr)

    def assertPassed(self, res):
        self.assertEqual(res.returncode, 0, f"通すはず: {res!r}")
        self.assertEqual(res.stdout.strip(), "", f"注入してはいけない: {res!r}")
        self.assertNotIn("Unexpected", res.stderr, f"ERR trap に落ちている: {res!r}")

    # --- 通す（スキルの手順どおり） ---

    def test_passes_skill_shaped_new_adr(self):
        with TempGitRepo() as root:
            i = ts()
            self.assertPassed(self._write(root, f".claude/adr/{i}-api-versioning.md", adr_body(i)))

    def test_passes_relative_path(self):
        with TempGitRepo() as root:
            i = ts()
            self.assertPassed(self._write(root, f".claude/adr/{i}-x.md", adr_body(i), absolute=False))

    def test_passes_a_few_minutes_old_id(self):
        """date → 本文生成 → Write の間に数分かかっても止めない（窓の内側）."""
        with TempGitRepo() as root:
            i = ts(-240)
            self.assertPassed(self._write(root, f".claude/adr/{i}-x.md", adr_body(i)))

    def test_passes_template_comments_left_in_sections(self):
        """埋められない節はテンプレのコメントを残す仕様（SKILL.md 手順 6）なので、見出しだけを見る."""
        with TempGitRepo() as root:
            i = ts()
            body = adr_body(i).replace("本文", "<!-- 未記入 -->")
            self.assertPassed(self._write(root, f".claude/adr/{i}-x.md", body))

    # --- 黙る（対象外） ---

    def test_silent_for_non_adr_paths(self):
        with TempGitRepo() as root:
            for rel in ("README.md", ".claude/designs/20200101000000-x.md",
                        ".claude/adr/sub/20200101000000-x.md", "docs/adr/20200101000000-x.md",
                        ".claude/adr/notes.txt"):
                with self.subTest(rel=rel):
                    self.assertPassed(self._write(root, rel, "# 何でも"))

    def test_silent_for_overwrite_of_existing_adr(self):
        """既存 ADR（テンプレ以前の見出し構成を含む）を直すたびに止めない."""
        with TempGitRepo() as root:
            p = root / ".claude/adr/20200101000000-old.md"
            p.parent.mkdir(parents=True)
            p.write_text("# 古い ADR\n")
            self.assertPassed(self._write(root, ".claude/adr/20200101000000-old.md", "# 古い ADR（改）\n"))

    def test_silent_for_edit_tools(self):
        """supersede の旧 ADR 更新は既存ファイルへの Edit。matcher が評価されない環境でも自己判定で黙る."""
        with TempGitRepo() as root:
            p = root / ".claude/adr/20200101000000-x.md"
            p.parent.mkdir(parents=True)
            p.write_text("# 既存\n")
            edit = {"old_string": "", "new_string": "x"}
            for tool in ("Edit", "MultiEdit", "Read", ""):
                with self.subTest(tool=tool):
                    self.assertPassed(self._write(root, ".claude/adr/20200101000000-x.md", "",
                                                  tool=tool, tool_input=edit))

    def test_silent_for_edit_with_old_string_on_missing_file(self):
        """old_string のある Edit は新規作成ではない（Claude Code 側で失敗する）ので見ない."""
        with TempGitRepo() as root:
            self.assertPassed(self._write(root, ".claude/adr/20200101000000-x.md", "", tool="Edit",
                                          tool_input={"old_string": "a", "new_string": "b"}))

    def test_edit_creating_new_file_is_checked(self):
        """old_string 空の Edit は新規作成になる。Write と同じ検査を new_string に掛ける."""
        with TempGitRepo() as root:
            i = ts()
            self.assertPassed(self._write(root, f".claude/adr/{i}-x.md", "", tool="Edit",
                                          tool_input={"old_string": "", "new_string": adr_body(i)}))
            self.assertBlocked(self._write(root, f".claude/adr/{i}-y.md", "", tool="Edit",
                                           tool_input={"old_string": "", "new_string": "# 手書き\n"}))

    def test_silent_for_index_files(self):
        with TempGitRepo() as root:
            for name in ("README.md", "index.md", "Index.md"):
                with self.subTest(name=name):
                    self.assertPassed(self._write(root, f".claude/adr/{name}", "# 一覧\n"))

    def test_passes_relative_path_without_project_dir(self):
        """CLAUDE_PROJECT_DIR が無いときは $PWD（hook の cwd）を基準にする."""
        with TempGitRepo() as root:
            i = ts()
            env = {"CLAUDE_PROJECT_DIR": ""}
            self.assertPassed(self._write(root, f".claude/adr/{i}-x.md", adr_body(i), absolute=False, env=env))
            self.assertBlocked(self._write(root, f".claude/adr/{i}-y.md", "# 手書き\n", absolute=False, env=env))

    def test_passes_large_adr(self):
        """64KB を超える本文でも誤って止めない・素通りしない（pipefail 下の SIGPIPE。実測で両方起きた）."""
        with TempGitRepo() as root:
            i = ts()
            big = adr_body(i) + "\n" + ("| 長い表の行 | " + "x" * 80 + " |\n") * 3000
            self.assertGreater(len(big.encode()), 200_000)
            self.assertPassed(self._write(root, f".claude/adr/{i}-big.md", big))
            bad = big.replace("## 適用方法 (Enforcement)\n", "")
            self.assertBlocked(self._write(root, f".claude/adr/{i}-big2.md", bad), "適用方法")

    def test_passes_crlf_bom_and_trailing_spaces(self):
        with TempGitRepo() as root:
            i = ts()
            variants = {
                "crlf": adr_body(i).replace("\n", "\r\n"),
                "bom": "\ufeff" + adr_body(i),
                "trailing": adr_body(i).replace("## 決定\n", "## 決定  \n"),
            }
            for name, body in variants.items():
                with self.subTest(variant=name):
                    self.assertPassed(self._write(root, f".claude/adr/{i}-{name}.md", body))

    def test_passes_quoted_or_commented_id(self):
        with TempGitRepo() as root:
            i = ts()
            for n, line in enumerate((f'id: "{i}"', f"id: '{i}'", f"id: {i}  # 作成時刻")):
                with self.subTest(line=line):
                    body = adr_body(i).replace(f"id: {i}", line)
                    self.assertPassed(self._write(root, f".claude/adr/{i}-q{n}.md", body))

    def test_silent_for_broken_json(self):
        with TempGitRepo() as root:
            res = self.run_hook(raw="{not json", cwd=root, env_extra={"CLAUDE_PROJECT_DIR": str(root)})
            self.assertPassed(res)

    def test_silent_without_jq(self):
        """jq が無ければ検査できない。止めずに通す（check-deps が別途知らせる）."""
        with TempGitRepo() as root:
            payload = {"tool_name": "Write",
                       "tool_input": {"file_path": str(root / ".claude/adr/20200101000000-x.md"), "content": "x"}}
            res = self.run_hook(payload, cwd=root,
                                env_extra={"CLAUDE_PROJECT_DIR": str(root), "PATH": self.path_with_only("date", "awk")})
            self.assertPassed(res)

    # --- 止める ---

    def test_blocks_rounded_old_id(self):
        """手で丸めた時刻（実測: 12:07 に 120000 と書いた）."""
        with TempGitRepo() as root:
            i = ts(-420)[:-2] + "00"
            self.assertBlocked(self._write(root, f".claude/adr/{i}-x.md", adr_body(i)), "秒ずれている")

    def test_blocks_future_id(self):
        """実測: 21:44 に 223000 と書いた."""
        with TempGitRepo() as root:
            i = ts(46 * 60)
            self.assertBlocked(self._write(root, f".claude/adr/{i}-x.md", adr_body(i)), "秒ずれている")

    def test_window_boundaries(self):
        """前 300 秒・後 60 秒。現在時刻を固定して、境界の両側を秒単位で測る."""
        now = datetime.datetime(2026, 9, 24, 12, 0, 0)
        env = {"ADR_WRITE_GUARD_NOW": now.strftime("%Y%m%d%H%M%S")}
        with TempGitRepo() as root:
            for off, ok in ((-300, True), (-301, False), (60, True), (61, False), (0, True)):
                with self.subTest(off=off):
                    i = (now + datetime.timedelta(seconds=off)).strftime("%Y%m%d%H%M%S")
                    res = self._write(root, f".claude/adr/{i}-w.md", adr_body(i), env=env)
                    (self.assertPassed if ok else self.assertBlocked)(res)

    def test_blocks_normalized_path_variants(self):
        """`./` を挟む・ディレクトリ名の大文字小文字で素通りさせない."""
        with TempGitRepo() as root:
            for rel in (".claude/adr/./20200101000000-x.md", ".claude//adr/20200101000000-x.md",
                        ".claude/ADR/20200101000000-x.md"):
                with self.subTest(rel=rel):
                    # pathlib は `./` と `//` を畳むので、文字列のまま渡す（絶対・相対の両方）
                    self.assertBlocked(self._write(root, str(root) + "/" + rel, "# 手書き\n", absolute=False))
                    self.assertBlocked(self._write(root, rel, "# 手書き\n", absolute=False))

    def test_blocks_h1_id_mismatch(self):
        with TempGitRepo() as root:
            i = ts()
            body = adr_body(i).replace(f"# ADR-{i}:", "# ADR-20200101000000:")
            self.assertBlocked(self._write(root, f".claude/adr/{i}-x.md", body), "見出しの id")

    def test_blocks_id_filename_mismatch(self):
        with TempGitRepo() as root:
            i = ts()
            body = adr_body(i, frontmatter_id="20200101000000")
            self.assertBlocked(self._write(root, f".claude/adr/{i}-x.md", body), "と違う")

    def test_blocks_missing_frontmatter_id(self):
        with TempGitRepo() as root:
            i = ts()
            body = adr_body(i).replace(f"id: {i}\n", "")
            self.assertBlocked(self._write(root, f".claude/adr/{i}-x.md", body), "id が無い")

    def test_blocks_bad_filename(self):
        with TempGitRepo() as root:
            for name in ("2026-09-24-x.md", "adr-x.md", f"{ts()}_Upper_Case.md"):
                with self.subTest(name=name):
                    self.assertBlocked(self._write(root, f".claude/adr/{name}", adr_body(ts())), "ファイル名")

    def test_blocks_each_missing_heading(self):
        """実測: 適用方法 (Enforcement) の欠けた ADR が 3 件あった。見出しを 1 つずつ抜いて測る."""
        with TempGitRepo() as root:
            for h in HEADINGS:
                with self.subTest(heading=h):
                    i = ts()
                    body = adr_body(i, headings=[x for x in HEADINGS if x != h])
                    self.assertBlocked(self._write(root, f".claude/adr/{i}-x.md", body), h)

    def test_blocks_renamed_heading(self):
        """既存の手書き ADR にあった言い換え（却下した代替案 / 帰結）はテンプレの見出しではない."""
        with TempGitRepo() as root:
            i = ts()
            body = adr_body(i).replace("## 検討した代替案", "## 却下した代替案")
            self.assertBlocked(self._write(root, f".claude/adr/{i}-x.md", body), "検討した代替案")

    def test_heading_must_be_the_whole_line(self):
        """見出しは行全体で一致させる。`### 決定` や `## 決定事項` は `## 決定` の代わりにならない."""
        with TempGitRepo() as root:
            for repl in ("### 決定", "## 決定事項", "本文中で ## 決定 に触れただけ"):
                with self.subTest(repl=repl):
                    i = ts()
                    body = adr_body(i).replace("\n## 決定\n", "\n" + repl + "\n")
                    self.assertBlocked(self._write(root, f".claude/adr/{i}-x.md", body), "## 決定")

    def test_blocks_missing_h1(self):
        with TempGitRepo() as root:
            i = ts()
            body = adr_body(i).replace(f"# ADR-{i}: テスト", "# テスト")
            self.assertBlocked(self._write(root, f".claude/adr/{i}-x.md", body), "# ADR-")

    def test_block_message_points_to_skill(self):
        with TempGitRepo() as root:
            i = ts(-3600)
            res = self._write(root, f".claude/adr/{i}-x.md", adr_body(i))
            self.assertBlocked(res)
            self.assertIn("adr スキル", res.stderr)
            self.assertIn("date +%Y%m%d%H%M%S", res.stderr)

    def test_block_message_offers_hook_time_as_escape(self):
        """シェルと hook で TZ が違うと date を取り直しても合わない。hook の現在時刻を出して抜け道にする."""
        with TempGitRepo() as root:
            i = ts(-9 * 3600)
            res = self._write(root, f".claude/adr/{i}-x.md", adr_body(i), env={"ADR_WRITE_GUARD_NOW": "20260924120000"})
            self.assertBlocked(res)
            self.assertIn("現在時刻 20260924120000 を id", res.stderr)


class AdrCheckDepsTest(HookTestCase):
    PLUGIN = "adr-keeper"
    SCRIPT = "hooks/scripts/check-deps.sh"

    def test_silent_when_jq_present(self):
        """doc-freshness（任意依存）が無くても黙る。毎セッション鳴らさない."""
        res = self.run_hook({"hook_event_name": "SessionStart"},
                            env_extra={"HOME": str(self.isolated_project_dir())})
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "")
        self.assertNotIn("Unexpected", res.stderr)

    def test_warns_without_jq(self):
        res = self.run_hook({"hook_event_name": "SessionStart"},
                            env_extra={"PATH": self.path_with_only()})
        self.assertEqual(res.returncode, 0)
        self.assertIn("jq", res.stdout)
        self.assertNotIn("Unexpected", res.stderr)


if __name__ == "__main__":
    unittest.main()
