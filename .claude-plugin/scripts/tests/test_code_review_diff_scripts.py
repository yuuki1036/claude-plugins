#!/usr/bin/env python3
"""`diff-slice.sh` / `triage-signals.sh` の回帰テスト（GitHub issue #138）.

**なぜこの 2 本を先にやるか**: どちらも壊れても**出力が出る**種類の欠陥を持つ。

- `diff-slice.sh` は「レビュー対象の切り出し」。取りこぼすと**レビューしていない差分が
  「レビュー済み」になる**。空出力 + exit 0 を避ける設計（exit 3）は入っているが、
  **`--list` と切り出し本体が別実装**なので両者が食い違うと誰も気づけない。
- `triage-signals.sh` は Phase 0 の体数・観点・予算の入力。誤ると全体の配分が狂う。
  `size_tier` の帯境界は triage-guide.md `## 6.2` の複製なので**両側から測る**
  （片側だけだと `>` / `>=` の取り違えが素通りする）。

方針: 実際の git リポジトリ + 実際の diff を通す（awk の分岐は入力の形に強く依存するため、
合成の断片だけでは「本物の git 出力」との乖離を検出できない）。
"""

from __future__ import annotations

import subprocess
import json
import unittest
from pathlib import Path

from test_code_review_scripts import PLUGIN, ScriptTestBase

SLICE = PLUGIN / "scripts" / "diff-slice.sh"
TRIAGE = PLUGIN / "scripts" / "triage-signals.sh"


class DiffScriptTestBase(ScriptTestBase):
    """git 操作と出力パースのヘルパ."""

    def write(self, rel: str, body: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        return p

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True,
                              env=self._env())

    def add(self) -> None:
        self.git("add", "-A")

    def run_in(self, script: Path, *args: str, cwd: Path | None = None,
               env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        """`cwd` を差し替えられる runner（起動 dir 依存の検出に使う）."""
        return subprocess.run(["bash", str(script), *args], cwd=str(cwd or self.root),
                              capture_output=True, text=True, env=env or self._env(), timeout=60)

    @staticmethod
    def section(out: str, name: str) -> list[str]:
        """`## <name>` セクションの中身（次の `## ` 見出しまで）を行のリストで返す."""
        lines = out.splitlines()
        try:
            start = lines.index(name)
        except ValueError:
            return []
        body = []
        for line in lines[start + 1:]:
            if line.startswith("## "):
                break
            body.append(line)
        return body

    def kv(self, out: str, name: str) -> dict[str, str]:
        pairs = {}
        for line in self.section(out, name):
            if "=" in line:
                k, _, v = line.partition("=")
                pairs[k] = v
        return pairs


DIFF_HEADER = "diff --git a/{p} b/{p}\nindex 1111111..2222222 100644\n--- a/{p}\n+++ b/{p}\n"


def block(path: str, *added: str) -> str:
    """1 ファイルぶんの diff ブロック（本物の git 出力と同じ並び）."""
    body = "".join("+%s\n" % a for a in added)
    return DIFF_HEADER.format(p=path) + "@@ -1,1 +1,%d @@\n keep\n%s" % (len(added) + 1, body)


class DiffSliceListTest(DiffScriptTestBase):
    """`--list` は「diff に含まれるファイル一覧」の正本として使われる.

    `triage-signals.sh` の `## files` は 80 件で打ち切り、全件が要るときは `--list` を使えと
    案内している（＝ここが欠けると **capped の先が誰にも見えない**）。
    """

    def list_paths(self, diff_text: str) -> list[str]:
        d = self.write("d.diff", diff_text)
        res = self.run_in(SLICE, str(d), "--list")
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout.splitlines()

    def test_lists_every_changed_path(self):
        out = self.list_paths(block("src/a.ts", "x") + block("docs/b.md", "y"))
        self.assertEqual(out, ["src/a.ts", "docs/b.md"])

    def test_lists_new_and_deleted_files(self):
        diff = ("diff --git a/new.ts b/new.ts\nnew file mode 100644\n"
                "--- /dev/null\n+++ b/new.ts\n@@ -0,0 +1 @@\n+hello\n"
                "diff --git a/gone.ts b/gone.ts\ndeleted file mode 100644\n"
                "--- a/gone.ts\n+++ /dev/null\n@@ -1 +0,0 @@\n-bye\n")
        self.assertEqual(self.list_paths(diff), ["new.ts", "gone.ts"])

    def test_lists_path_containing_space_from_real_git_output(self):
        """**合成 diff では検出できない欠陥**: git は空白入りパスの `---` / `+++` 行の
        末尾にタブを 1 つ付ける（区切りのため）。手書き fixture にはそれが無かったので、
        「空白入りパスを扱える」というテストが実は何も検証していなかった。
        """
        self.write("sp ace.ts", "a\n")
        self.add()
        self.git("commit", "-qm", "init")
        self.write("sp ace.ts", "a\nb\n")
        self.add()
        diff = self.git("diff", "--cached").stdout
        self.assertRegex(diff, r"\+\+\+ b/sp ace\.ts\t", "前提: git が末尾にタブを付ける")
        self.assertEqual(self.list_paths(diff), ["sp ace.ts"])

    def test_lists_deleted_path_when_git_omits_the_a_b_prefix(self):
        """**`diff.noprefix=true` の環境で削除ファイルを引けるか**（#148 / nightly が検出）.

        削除は `+++ /dev/null` なので `plus` が立たず、`diff --git` 行も
        `diff --git gone.ts gone.ts`（prefix 無し）になって `sym_path` の対称形復元が
        効かない。**`---` 行を `minus` に取る経路が唯一の復元手段**になる。
        prefix がある通常の diff では `sym_path` のフォールバックが救ってしまうため、
        この経路は「削除 × prefix 無し」の組み合わせでしか観測できない
        （`--- ` 行の判定を反転させる変異が 2026-08-18 の nightly で生存した）。
        `diff.noprefix` はユーザーの git 設定なので、こちらから制御できない前提条件。
        """
        self.write("gone.ts", "a\n")
        self.add()
        self.git("commit", "-qm", "init")
        (self.root / "gone.ts").unlink()
        self.add()
        diff = self.git("-c", "diff.noprefix=true", "diff", "--cached").stdout
        self.assertIn("diff --git gone.ts gone.ts", diff, "前提: prefix が付いていない")
        self.assertEqual(self.list_paths(diff), ["gone.ts"])

    def test_body_lines_that_look_like_headers_are_not_paths(self):
        """**追加行の内容が `++ ...` だと diff 上は `+++ ...` になる。**

        ヘッダ判定を「行頭 `+++ `」だけで行うと、diff 本文が幻のパスとして一覧に載る。
        載ったパスは切り出し側では 0 件マッチ（exit 3）になるため、**一覧と切り出しが
        食い違う**（agent 側は「担当ファイルの diff が取れない」と報告して 1 体ぶん無駄になる）。
        """
        diff = block("docs/b.md", "+ nested marker", "++ looks like a header",
                     "-- looks like an old header")
        self.assertEqual(self.list_paths(diff), ["docs/b.md"])

    def test_lists_pure_rename(self):
        """内容変更を伴わない rename は `---` / `+++` を持たない（実測済み）."""
        self.write("old.txt", "a\nb\n")
        self.add()
        self.git("commit", "-qm", "init")
        self.git("mv", "old.txt", "new.txt")
        self.add()
        diff = self.git("diff", "--cached").stdout
        self.assertIn("rename to new.txt", diff, "前提: git が rename として出力する")
        self.assertEqual(self.list_paths(diff), ["new.txt"])

    def test_lists_mode_only_change(self):
        """mode 変更のみの diff も `---` / `+++` を持たない."""
        p = self.write("perm.sh", "x\n")
        self.add()
        self.git("commit", "-qm", "init")
        p.chmod(0o755)
        self.add()
        diff = self.git("diff", "--cached").stdout
        self.assertIn("new mode", diff, "前提: git が mode 変更として出力する")
        self.assertEqual(self.list_paths(diff), ["perm.sh"])

    def test_leading_commit_message_is_not_a_path(self):
        """`git show` 由来の diff は先頭にコミットメッセージが付く."""
        diff = "commit abc123\nAuthor: t <t@e>\n\n    subject line\n\n" + block("src/a.ts", "x")
        self.assertEqual(self.list_paths(diff), ["src/a.ts"])


class DiffSliceSelectionTest(DiffScriptTestBase):
    """切り出し本体（誰の担当ぶんを渡すか）."""

    def slice(self, diff_text: str, *paths: str) -> subprocess.CompletedProcess[str]:
        d = self.write("d.diff", diff_text)
        return self.run_in(SLICE, str(d), *paths)

    def test_emits_only_the_requested_file(self):
        res = self.slice(block("src/a.ts", "aaa") + block("src/b.ts", "bbb"), "src/a.ts")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("+aaa", res.stdout)
        self.assertNotIn("+bbb", res.stdout)
        self.assertNotIn("src/b.ts", res.stdout)

    def test_emits_the_last_block_in_the_diff(self):
        """末尾ブロックは「次の `diff --git` が来ない」境界。取りこぼしやすい."""
        res = self.slice(block("src/a.ts", "aaa") + block("src/b.ts", "bbb"), "src/b.ts")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("+bbb", res.stdout)
        self.assertNotIn("+aaa", res.stdout)

    def test_emits_multiple_requested_files(self):
        res = self.slice(block("a.ts", "aaa") + block("b.ts", "bbb") + block("c.ts", "ccc"),
                         "a.ts", "c.ts")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("+aaa", res.stdout)
        self.assertIn("+ccc", res.stdout)
        self.assertNotIn("+bbb", res.stdout)

    def test_emits_every_block_of_a_path_repeated_in_a_concatenated_diff(self):
        """self-review の diff は base..HEAD + staged + unstaged の **3 本連結**.

        同じファイルが複数ブロックに現れるので、1 つ目で止めると残りが未レビューになる。
        """
        res = self.slice(block("src/a.ts", "first") + block("src/a.ts", "second"), "src/a.ts")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("+first", res.stdout)
        self.assertIn("+second", res.stdout)

    def test_zero_match_exits_3_and_prints_nothing_to_stdout(self):
        res = self.slice(block("src/a.ts", "x"), "nope.ts")
        self.assertEqual(res.returncode, 3)
        self.assertEqual(res.stdout, "", "空出力 + exit 0 だと agent が「変更なし」と誤解する")
        self.assertIn("0 件", res.stderr)

    def test_partial_match_succeeds(self):
        """1 つでも当たれば exit 0（当たらなかったパスは黙って落とす）."""
        res = self.slice(block("src/a.ts", "x"), "src/a.ts", "nope.ts")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("+x", res.stdout)

    def test_path_with_space_can_be_sliced_from_real_git_output(self):
        self.write("sp ace.ts", "a\n")
        self.add()
        self.git("commit", "-qm", "init")
        self.write("sp ace.ts", "a\nadded\n")
        self.add()
        res = self.slice(self.git("diff", "--cached").stdout, "sp ace.ts")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("+added", res.stdout)

    def test_non_ascii_path_can_be_sliced_when_quoting_is_disabled(self):
        """git は非 ASCII パスを `"a/\\346..."` と C クォートする（`core.quotePath` 既定 true）.

        復元は awk の `%c` がロケール依存で移植できないため、**生成側で
        `-c core.quotePath=false`** を付けて生の UTF-8 で保存する規約にしてある
        （`triage-signals.sh`）。ここではその前提が成立することを確かめる。
        """
        self.write("日本語.ts", "a\n")
        self.add()
        self.git("commit", "-qm", "init")
        self.write("日本語.ts", "a\nadded\n")
        self.add()
        quoted = self.git("diff", "--cached").stdout
        self.assertIn('"b/\\346', quoted, "前提: 既定ではクォートされる")
        raw = self.git("-c", "core.quotePath=false", "diff", "--cached").stdout
        res = self.slice(raw, "日本語.ts")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("+added", res.stdout)

    def test_deleted_file_is_sliced_by_its_old_path(self):
        diff = ("diff --git a/gone.ts b/gone.ts\ndeleted file mode 100644\n"
                "--- a/gone.ts\n+++ /dev/null\n@@ -1 +0,0 @@\n-bye\n")
        res = self.slice(diff, "gone.ts")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("-bye", res.stdout)

    def test_missing_diff_file_exits_2(self):
        res = self.run_in(SLICE, str(self.root / "absent.diff"), "x.ts")
        self.assertEqual(res.returncode, 2)
        self.assertIn("usage", res.stderr)

    def test_no_argument_exits_2(self):
        res = self.run_in(SLICE)
        self.assertEqual(res.returncode, 2)

    def test_path_missing_exits_2(self):
        d = self.write("d.diff", block("a.ts", "x"))
        res = self.run_in(SLICE, str(d))
        self.assertEqual(res.returncode, 2)
        self.assertIn("usage", res.stderr)

    def test_every_listed_path_is_sliceable(self):
        """**`--list` と切り出しの整合**（別実装なので不変条件として表明する）.

        一覧に出たパスは必ず切り出せなければならない。ここが崩れると、agent は
        「担当と言われたファイルの diff が取れない」状態になる。
        """
        self.write("old.txt", "a\n")
        self.write("perm.sh", "x\n")
        self.write("src/a.ts", "keep\n")
        self.add()
        self.git("commit", "-qm", "init")
        self.git("mv", "old.txt", "new.txt")
        (self.root / "perm.sh").chmod(0o755)
        self.write("src/a.ts", "keep\n++ tricky body line\n")
        self.add()
        d = self.write("d.diff", self.git("diff", "--cached").stdout)
        listed = self.run_in(SLICE, str(d), "--list").stdout.splitlines()
        self.assertEqual(sorted(listed), ["new.txt", "perm.sh", "src/a.ts"])
        for path in listed:
            with self.subTest(path=path):
                res = self.run_in(SLICE, str(d), path)
                self.assertEqual(res.returncode, 0, f"{path}: {res.stderr}")


class TriageArgumentTest(DiffScriptTestBase):
    def test_unknown_argument_exits_2(self):
        res = self.run_in(TRIAGE, "--nope")
        self.assertEqual(res.returncode, 2)
        self.assertIn("未知の引数", res.stderr)

    def test_flag_without_value_exits_2(self):
        for flag in ("--pr", "--base", "--out"):
            with self.subTest(flag=flag):
                res = self.run_in(TRIAGE, flag)
                self.assertEqual(res.returncode, 2)
                self.assertIn("値が必要", res.stderr)

    def test_non_numeric_pr_exits_2(self):
        # パス組み立てに使う値なので `../../` 混入は入口で止める
        res = self.run_in(TRIAGE, "--pr", "../../etc")
        self.assertEqual(res.returncode, 2)
        self.assertIn("数値のみ", res.stderr)

    def test_no_pr_and_no_base_exits_2(self):
        res = self.run_in(TRIAGE)
        self.assertEqual(res.returncode, 2)
        self.assertIn("どちらかが必須", res.stderr)

    def test_unresolvable_base_exits_2(self):
        res = self.run_in(TRIAGE, "--base", "no-such-ref")
        self.assertEqual(res.returncode, 2)
        self.assertIn("base ref を解決できない", res.stderr)

    def test_empty_diff_exits_1(self):
        res = self.run_in(TRIAGE, "--base", "HEAD")
        self.assertEqual(res.returncode, 1)
        self.assertIn("diff が空", res.stderr)


class TriageStaleFileTest(DiffScriptTestBase):
    """「配る前に必ず消す」規約（縮退先は誤値ではなく欠測）."""

    def out_path(self) -> Path:
        self.write("src/a.ts", "x\n")
        self.add()
        res = self.run_in(TRIAGE, "--base", "HEAD")
        self.assertEqual(res.returncode, 0, res.stderr)
        return Path(self.kv(res.stdout, "## meta")["diff_file"])

    def test_stale_diff_is_removed_when_the_run_fails(self):
        diff = self.out_path()
        diff.write_text("STALE CONTENT\n", encoding="utf-8")
        res = self.run_in(TRIAGE, "--base", "no-such-ref")
        self.assertEqual(res.returncode, 2)
        self.assertFalse(diff.exists(), "失敗したのに前回の diff が残ると「古い diff で完走」する")

    def test_stale_agent_context_is_removed(self):
        self.write("src/a.ts", "x\n")
        self.add()
        first = self.run_in(TRIAGE, "--base", "HEAD")
        ctx = Path(self.kv(first.stdout, "## meta")["agent_ctx_file"])
        ctx.write_text("PREVIOUS RUN\n", encoding="utf-8")
        second = self.run_in(TRIAGE, "--base", "HEAD")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertFalse(ctx.exists(), "消さないと全 agent が「読めるが前回の値」を掴む")

    def test_out_override_is_honored(self):
        self.write("src/a.ts", "x\n")
        self.add()
        target = self.root / "custom.diff"
        res = self.run_in(TRIAGE, "--base", "HEAD", "--out", str(target))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.kv(res.stdout, "## meta")["diff_file"], str(target))
        self.assertIn("diff --git", target.read_text(encoding="utf-8"))

    def test_no_tmp_file_is_left_behind(self):
        self.write("src/a.ts", "x\n")
        self.add()
        target = self.root / "custom.diff"
        self.run_in(TRIAGE, "--base", "HEAD", "--out", str(target))
        self.assertFalse((self.root / "custom.diff.tmp").exists())


class TriageSizeTierTest(DiffScriptTestBase):
    """`size_tier` の帯境界（正本: triage-guide.md `## 6.2` / ここは機械適用の複製）.

    large = core ファイル > 10 **または** core 行数 > 500、medium = >= 4 または >= 101。
    **両側から測る**: 片側だけだと `>` と `>=` の取り違えが素通りする。
    """

    def tier_for(self, files: int = 1, lines_per_file: int = 1) -> str:
        for i in range(files):
            self.write("src/f%d.ts" % i, "".join("line %d\n" % n for n in range(lines_per_file)))
        self.add()
        res = self.run_in(TRIAGE, "--base", "HEAD")
        self.assertEqual(res.returncode, 0, res.stderr)
        return self.kv(res.stdout, "## size")["size_tier"]

    def test_three_core_files_is_small(self):
        self.assertEqual(self.tier_for(files=3), "small")

    def test_four_core_files_is_medium(self):
        self.assertEqual(self.tier_for(files=4), "medium")

    def test_ten_core_files_is_still_medium(self):
        self.assertEqual(self.tier_for(files=10), "medium")

    def test_eleven_core_files_is_large(self):
        self.assertEqual(self.tier_for(files=11), "large")

    def test_hundred_lines_is_small(self):
        self.assertEqual(self.tier_for(lines_per_file=100), "small")

    def test_hundred_and_one_lines_is_medium(self):
        self.assertEqual(self.tier_for(lines_per_file=101), "medium")

    def test_five_hundred_lines_is_still_medium(self):
        self.assertEqual(self.tier_for(lines_per_file=500), "medium")

    def test_five_hundred_and_one_lines_is_large(self):
        self.assertEqual(self.tier_for(lines_per_file=501), "large")

    def test_doc_only_change_does_not_reach_large_by_core_count(self):
        """帯は **core** で決まる（doc / gen は core に数えない）."""
        for i in range(12):
            self.write("docs/d%d.md" % i, "text\n")
        self.add()
        res = self.run_in(TRIAGE, "--base", "HEAD")
        size = self.kv(res.stdout, "## size")
        self.assertEqual(size["core_files"], "0")
        self.assertEqual(size["total_files"], "12")
        self.assertEqual(size["size_tier"], "small")

    def test_generated_and_test_files_are_classified(self):
        self.write("src/dist/bundle.js", "x\n")
        self.write("pnpm-lock.yaml", "x\n")
        self.write("src/a.test.ts", "x\n")
        self.write("docs/g.md", "x\n")
        self.write("src/real.ts", "x\n")
        self.add()
        res = self.run_in(TRIAGE, "--base", "HEAD")
        files = {line.split()[-1]: line.split()[0] for line in self.section(res.stdout, "## files")}
        self.assertEqual(files["src/dist/bundle.js"], "gen")
        self.assertEqual(files["pnpm-lock.yaml"], "gen")
        self.assertEqual(files["src/a.test.ts"], "test")
        self.assertEqual(files["docs/g.md"], "doc")
        self.assertEqual(files["src/real.ts"], "core")
        # **core は帯の判定に使う数**なので test / doc / gen を除く（triage-guide `## 6.1`）。
        # テスト・doc は観点判定の起動根拠にはなるが体数を押し上げる根拠にはしない
        size = self.kv(res.stdout, "## size")
        self.assertEqual(size["core_files"], "1")
        self.assertEqual(size["total_files"], "5")

    def test_many_test_files_do_not_push_the_tier(self):
        """テストのみの PR は core=0 → small（triage-guide `## 6.1` 末尾）."""
        for i in range(12):
            self.write("src/f%d.test.ts" % i, "".join("expect(%d)\n" % n for n in range(60)))
        self.add()
        res = self.run_in(TRIAGE, "--base", "HEAD")
        size = self.kv(res.stdout, "## size")
        self.assertEqual(size["core_files"], "0")
        self.assertEqual(size["size_tier"], "small")

    def test_same_file_staged_and_unstaged_is_counted_once(self):
        """3 系統連結の diff は同一パスを複数回含む。集約しないと帯が実態より大きく出る."""
        self.write("src/a.ts", "one\n")
        self.add()
        self.write("src/a.ts", "one\ntwo\n")
        res = self.run_in(TRIAGE, "--base", "HEAD")
        self.assertEqual(self.kv(res.stdout, "## size")["total_files"], "1")

    def test_binary_change_is_not_counted_in_the_size_bands(self):
        """numstat が `-\t-\tpath` を返す行（binary）は行数を持たないので集計に入れない.

        帯は行数と core ファイル数で決まるため、`-` を 0 として混ぜると
        `total_files` だけが増えて `md_ratio` / `generated_ratio` の分母がずれる。
        """
        (self.root / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(range(256)))
        self.write("src/a.ts", "x\n")
        self.add()
        res = self.run_in(TRIAGE, "--base", "HEAD")
        self.assertEqual(res.returncode, 0, res.stderr)
        numstat = self.git("diff", "--cached", "--numstat").stdout
        self.assertIn("-\t-\timg.png", numstat, "前提: git が binary を `-` で出す")
        size = self.kv(res.stdout, "## size")
        self.assertEqual(size["total_files"], "1")
        self.assertNotIn("img.png", "\n".join(self.section(res.stdout, "## files")))

    def test_non_ascii_paths_are_saved_and_listed_raw(self):
        """**生成側で `core.quotePath=false` を効かせる**（クォートされると使えないパスになる）.

        `## files` の一覧と保存した diff の両方が生の UTF-8 でなければ、agent が
        `diff-slice.sh <path>` で自分の担当ぶんを切り出せない（0 件マッチ = exit 3）。
        """
        self.write("src/日本語.ts", "const x = 1\n")
        self.add()
        res = self.run_in(TRIAGE, "--base", "HEAD")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("src/日本語.ts", "\n".join(self.section(res.stdout, "## files")))
        diff_file = self.kv(res.stdout, "## meta")["diff_file"]
        self.assertNotIn("\\346", Path(diff_file).read_text(encoding="utf-8"))
        sliced = self.run_in(SLICE, diff_file, "src/日本語.ts")
        self.assertEqual(sliced.returncode, 0, sliced.stderr)
        self.assertIn("+const x = 1", sliced.stdout)

    def test_generated_ratio_is_the_share_of_generated_files(self):
        # **gen と非 gen の数を変える**（1:1 にすると「gen を数える」と「非 gen を数える」が
        # 同じ 50% になり、取り違えを検出できない）
        self.write("pnpm-lock.yaml", "x\n")
        self.write("src/a.ts", "y\n")
        self.write("src/b.ts", "y\n")
        self.write("docs/c.md", "y\n")
        self.add()
        res = self.run_in(TRIAGE, "--base", "HEAD")
        size = self.kv(res.stdout, "## size")
        self.assertEqual(size["generated_ratio"], "25%")
        self.assertEqual(size["md_ratio"], "25%")

    def test_file_cap_reports_the_omitted_count(self):
        for i in range(85):
            self.write("src/f%d.ts" % i, "x\n")
        self.add()
        res = self.run_in(TRIAGE, "--base", "HEAD")
        body = self.section(res.stdout, "## files")
        self.assertEqual(len(body), 81, "80 件 + 省略行")
        self.assertIn("(+5 files 省略", body[-1])


class TriageSignalTest(DiffScriptTestBase):
    """観点判定シグナル（triage-guide `## 3`）と red-flags."""

    def digest(self, cwd: Path | None = None) -> str:
        self.add()
        res = self.run_in(TRIAGE, "--base", "HEAD", cwd=cwd)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout

    def sig(self, out: str, section: str) -> dict[str, int]:
        got = {}
        for line in self.section(out, section):
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1].isdigit():
                got[parts[0]] = int(parts[1])
        return got

    def test_error_handling_is_detected_in_added_code(self):
        self.write("src/a.ts", "try {\n  run()\n} catch (e) {}\n")
        self.assertIn("error-handling", self.sig(self.digest(), "## focus-signals"))

    def test_signals_come_from_added_lines_not_from_removed_ones(self):
        self.write("src/a.ts", "try {\n  run()\n} catch (e) {}\n")
        self.add()
        self.git("commit", "-qm", "with try")
        self.write("src/a.ts", "plain()\n")
        self.assertNotIn("error-handling", self.sig(self.digest(), "## focus-signals"))

    def test_doc_prose_lines_count_text_bearing_md_lines_only(self):
        """語を持つ行だけを数える（空行・区切りのみの行は数えない）.

        **箇条書きは数える**（本文が箇条書きで書かれた doc が大半なので、除外すると
        doc-substance の起動閾値がほぼ届かなくなる）。数えないのは「マーカーだけの行」。
        """
        self.write("docs/g.md", "real prose line\n- list item\n\n---\n|---|---|\n> \n")
        self.write("src/a.ts", "const code = 1\n")
        got = self.sig(self.digest(), "## focus-signals")
        self.assertEqual(got.get("doc-prose-lines"), 2)

    def test_doc_prose_lines_ignore_code_files(self):
        self.write("src/a.ts", "const code = 1\nconst more = 2\n")
        self.assertNotIn("doc-prose-lines", self.sig(self.digest(), "## focus-signals"))

    def _commit_then_rewrite(self, path: str, before: str, after: str) -> str:
        self.write(path, before)
        self.add()
        self.git("commit", "-qm", "base")
        self.write(path, after)
        return self.digest()

    def test_behavior_change_fires_when_an_existing_condition_is_rewritten(self):
        """既存の判定を書き換えた（消えた側に条件がある）ら出す（GitHub issue #269 の型 2）."""
        out = self._commit_then_rewrite("src/a.ts", "if (x > 0) {\n  run()\n}\n",
                                        "if (x >= 1 && y) {\n  run()\n}\n")
        self.assertEqual(self.sig(out, "## focus-signals").get("behavior-change"), 1)

    def test_behavior_change_counts_a_rewritten_return(self):
        out = self._commit_then_rewrite("src/a.ts", "  return a\n", "  return b\n")
        self.assertEqual(self.sig(out, "## focus-signals").get("behavior-change"), 1)

    def test_behavior_change_stays_silent_on_pure_additions(self):
        """黙る条件: 判定を足しただけ（古い前提を述べる記述が無い）."""
        self.write("src/a.ts", "if (x > 0) { run() }\nreturn y\n")
        self.assertNotIn("behavior-change", self.sig(self.digest(), "## focus-signals"))

    def test_behavior_change_stays_silent_on_rewritten_plain_lines(self):
        """黙る条件: 消えた行に判定が無い（`interface` / `iffy` の語中一致も拾わない）."""
        out = self._commit_then_rewrite("src/a.ts", "const iffy = returned\n", "const iffy = 2\n")
        self.assertNotIn("behavior-change", self.sig(out, "## focus-signals"))

    def test_behavior_change_ignores_tests_and_docs(self):
        """テスト・doc の書き換えはコードの判定ではない."""
        self.write("src/a.test.ts", "if (x) {}\n")
        self.write("docs/g.md", "if x == 1 then y\n")
        self.add()
        self.git("commit", "-qm", "base")
        self.write("src/a.test.ts", "plain()\n")
        self.write("docs/g.md", "plain\n")
        self.assertNotIn("behavior-change", self.sig(self.digest(), "## focus-signals"))

    def test_ui_quality_fires_on_locale_files(self):
        """文言だけを変える diff でも ui-quality を起動する（GitHub issue #272）."""
        for path in ("locales/ja.json", "src/i18n/en.yml", "app-x/locale/ja.json", "public/messages/ja.json"):
            with self.subTest(path=path):
                f = self.write(path, '{"tip": "上位の設定を継承します"}\n')
                self.git("add", "-N", path)
                self.assertIn("ui-quality", self.sig(self.digest(), "## focus-signals"))
                self.git("rm", "-q", "--cached", path)
                f.unlink()  # 次の subTest に残さない（前のファイルで当たったと取り違えない）

    def test_ui_quality_stays_silent_on_lookalike_names(self):
        """黙る条件: ディレクトリでない `messages.ts` / 語中の `mylocales/` は文言ファイルとみなさない."""
        self.write("src/messages.ts", "export const a = 1\n")
        self.write("src/mylocales/x.json", "{}\n")
        self.assertNotIn("ui-quality", self.sig(self.digest(), "## focus-signals"))

    def test_doc_rewritten_lines_count_removed_prose_in_md(self):
        """既存の節を書き換えた行数（消えた側の語を持つ行。区切りだけの行は数えない / #269 の型 3）."""
        out = self._commit_then_rewrite("docs/spec.md", "rule one\nrule two\n---\nkeep\n",
                                        "rule ONE\nrule TWO\n\nkeep\n")
        self.assertEqual(self.sig(out, "## focus-signals").get("doc-rewritten-lines"), 2)

    def test_doc_rewritten_lines_stay_silent_on_appends(self):
        out = self._commit_then_rewrite("docs/spec.md", "rule one\n", "rule one\nrule two\n")
        self.assertNotIn("doc-rewritten-lines", self.sig(out, "## focus-signals"))

    def test_layer_signal_fires_when_agents_md_names_a_directory_role(self):
        """ディレクトリ名と役割語が同じ行にあれば、層の規約が文書化されているとみなす（#261）."""
        self.write("AGENTS.md", "- usecase/ は 1 ファイル = 1 行為に限る。判定ロジックは domain/ に置く\n")
        self.write("src/a.ts", "const x = 1\n")
        got = self.sig(self.digest(), "## focus-signals")
        self.assertEqual(got.get("layer-responsibility"), 1)

    def test_layer_signal_stays_silent_without_a_directory_role(self):
        """黙る条件: 役割語だけ・ディレクトリ名だけ・`階層` の行では出さない."""
        self.write("AGENTS.md", "責務を明確にする\nsrc/ を見よ\ndocs/ の情報階層を整える\n")
        self.write("src/a.ts", "const x = 1\n")
        self.assertNotIn("layer-responsibility", self.sig(self.digest(), "## focus-signals"))

    def test_layer_signal_stays_silent_without_core_changes(self):
        """doc だけの変更には照合するコードが無いので出さない."""
        self.write("AGENTS.md", "- usecase/ に判定ロジックを置かない\n")
        self.write("docs/g.md", "prose\n")
        self.assertNotIn("layer-responsibility", self.sig(self.digest(), "## focus-signals"))

    def test_layer_signal_counts_rules_across_nested_agents_md(self):
        """件数は変更ファイルの祖先にある AGENTS.md / CLAUDE.md の合算、根拠は `## agents-md` の並びで最初に当たった 1 件（下位ディレクトリが先）."""
        self.write("AGENTS.md", "- server/ の責務はドメイン判断\n")
        self.write("src/CLAUDE.md", "- features/ から server/ を import しない\n- shared/ の役割は型だけ\n")
        self.write("src/a.ts", "const x = 1\n")
        rows = {l.split("\t")[0]: l.split("\t")[1:] for l in
                self.section(self.digest(), "## focus-signals") if l.count("\t") == 2}
        self.assertEqual(rows.get("layer-responsibility"), ["3", "src/CLAUDE.md"])

    def test_layer_signal_evidence_skips_agents_md_without_rules(self):
        """根拠には当たりのあるファイルを出す。並びで先にある src/CLAUDE.md が 0 件なら AGENTS.md."""
        self.write("AGENTS.md", "- server/ の責務はドメイン判断\n")
        self.write("src/CLAUDE.md", "テストを書く\n")
        self.write("src/a.ts", "const x = 1\n")
        rows = {l.split("\t")[0]: l.split("\t")[1:] for l in
                self.section(self.digest(), "## focus-signals") if l.count("\t") == 2}
        self.assertEqual(rows.get("layer-responsibility"), ["1", "AGENTS.md"])

    def test_guardrail_bypass_pattern_starting_with_dash_is_detected(self):
        """`--no-verify` は grep のオプションに見える。`-e` で渡していないと黙って 0 件になる."""
        self.write("src/a.ts", 'run("git commit --no-verify")\n')
        self.assertIn("specialist-guardrail-bypass", self.sig(self.digest(), "## red-flags"))

    def test_injection_and_destructive_patterns_are_detected(self):
        self.write("src/a.ts", "child_process.execSync(cmd)\nfs.rmSync(dir)\n")
        got = self.sig(self.digest(), "## red-flags")
        self.assertIn("specialist-injection", got)
        self.assertIn("specialist-destructive-op", got)

    def test_surface_signals_are_detected(self):
        self.write("src/a.ts", "await db.insert(row)\nconst amount = 1\nif (isAdmin) {}\n")
        got = self.sig(self.digest(), "## surface")
        self.assertEqual(sorted(got), ["authz", "db-write", "money-numeric"])

    def test_path_based_signal_reports_the_matching_file_as_evidence(self):
        self.write("src/components/Button.tsx", "export const B = () => null\n")
        rows = {l.split("\t")[0]: l.split("\t")[2] for l in
                self.section(self.digest(), "## focus-signals") if l.count("\t") == 2}
        self.assertEqual(rows.get("ui-quality"), "src/components/Button.tsx")

    def test_hunks_exclude_non_core_files(self):
        self.write("src/a.ts", "x\n")
        self.write("docs/g.md", "y\n")
        self.write("src/b.test.ts", "z\n")
        hunks = "\n".join(self.section(self.digest(), "## hunks"))
        self.assertIn("src/a.ts", hunks)
        self.assertNotIn("docs/g.md", hunks)
        self.assertNotIn("src/b.test.ts", hunks)

    def test_issue_ids_are_extracted_from_the_branch_name(self):
        self.git("checkout", "-q", "-b", "feat/ENG-123-thing")
        self.write("src/a.ts", "x\n")
        self.assertIn("ENG-123", self.section(self.digest(), "## issue-ids"))

    def test_lowercase_ids_are_not_extracted(self):
        # `utf-8` / `sha-1` を Issue ID として拾わない（GitHub issue #107）
        self.git("checkout", "-q", "-b", "fix/utf-8-and-sha-1")
        self.write("src/a.ts", "x\n")
        self.assertEqual(self.section(self.digest(), "## issue-ids"), [])

    def test_staged_mode_ignores_unstaged_changes(self):
        self.write("src/staged.ts", "x\n")
        self.add()
        self.write("src/unstaged.ts", "y\n")
        res = self.run_in(TRIAGE, "--base", "HEAD", "--staged")
        self.assertEqual(res.returncode, 0, res.stderr)
        files = "\n".join(self.section(res.stdout, "## files"))
        self.assertIn("src/staged.ts", files)
        self.assertNotIn("src/unstaged.ts", files)


class TriageExplorerSignalTest(DiffScriptTestBase):
    """`shared-module` の importers 概数（explorer の下限判定に使う / GitHub issue #122）.

    **誤差は両方向に出る**前提の粗い近似だが、「数えられなかった」を 0 に潰さないことが
    要求仕様（0 は下限判定を最も緩く通してしまう）。
    """

    def rows(self) -> dict[str, str]:
        self.add()
        res = self.run_in(TRIAGE, "--base", "HEAD")
        self.assertEqual(res.returncode, 0, res.stderr)
        got = {}
        for line in self.section(res.stdout, "## explorer-signals"):
            if line.startswith("shared-module\t"):
                body = line.split("\t", 1)[1]
                path, _, rest = body.partition(" (importers: ")
                got[path] = rest.rstrip(")")
        return got

    def test_zero_importers_is_reported_as_zero_not_unknown(self):
        """`git grep` の rc=1（該当なし）は「0 件」。`?`（数えられない）と区別する."""
        self.write("lib/lonely.ts", "export const x = 1\n")
        self.assertEqual(self.rows().get("lib/lonely.ts"), "0")

    def test_importers_are_counted_excluding_the_file_itself(self):
        self.write("lib/shared.ts", "export const x = 1\n")
        self.write("app/one.ts", "import { x } from '../lib/shared'\n")
        self.write("app/two.ts", "import { x } from '../lib/shared'\n")
        self.add()
        self.git("commit", "-qm", "importers")
        self.write("lib/shared.ts", "export const x = 2\n")
        self.assertEqual(self.rows().get("lib/shared.ts"), "2")

    def test_short_basenames_are_not_counted_at_all(self):
        """3 文字未満（`db` 等）は word 一致でも誤ヒットが多すぎるので数えない（`?`）.

        境界を両側から測る: 3 文字は数え、2 文字は数えない。
        """
        self.write("lib/db.ts", "export const db = 1\n")
        self.write("lib/abc.ts", "export const abc = 1\n")
        got = self.rows()
        self.assertEqual(got.get("lib/db.ts"), "?", "2 文字は数えない")
        self.assertEqual(got.get("lib/abc.ts"), "0", "3 文字は数える")


class TriageHostDepsTest(DiffScriptTestBase):
    """`## host-deps`（子 agent に渡すメインリポジトリ側の依存 dir）."""

    def run_digest(self) -> str:
        self.write("src/a.ts", "x\n")
        self.add()
        res = self.run_in(TRIAGE, "--base", "HEAD")
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout

    def test_main_root_is_reported(self):
        rows = self.section(self.run_digest(), "## host-deps")
        self.assertIn("main-root\t%s" % self.root, rows)

    def test_real_dependency_dir_is_reported(self):
        (self.root / "node_modules").mkdir()
        self.assertIn("dep-dir\t%s/node_modules" % self.root,
                      self.section(self.run_digest(), "## host-deps"))

    def test_symlinked_dependency_dir_is_not_reported(self):
        """CWE-59: `[ -d ]` は解決先を見るので、symlink はリポジトリ外を広告しうる."""
        outside = Path(self._tmp.name).parent / ("outside-%s" % self.root.name)
        outside.mkdir(exist_ok=True)
        self.addCleanup(outside.rmdir)
        (self.root / "node_modules").symlink_to(outside)
        rows = "\n".join(self.section(self.run_digest(), "## host-deps"))
        self.assertNotIn("dep-dir", rows)

    def test_changed_lockfile_is_reported(self):
        self.write("pnpm-lock.yaml", "lockfileVersion: 9\n")
        rows = self.section(self.run_digest(), "## host-deps")
        self.assertIn("lockfile-changed\tpnpm-lock.yaml", rows)


class TriageStartDirTest(DiffScriptTestBase):
    """**起動 dir がリポジトリルートでない場合**（self-review の通常経路）.

    review skill は Step 0 で EnterWorktree するが、self-review は worktree に入らず
    cwd はセッション起動 dir のまま。スクリプト自身が `git grep` の箇所でこの前提を
    明記している（`-C "$WT"` + `--full-name`）ので、**同じ前提が他のセクションにも
    要求される**。ここが崩れると Phase 0 の入力が黙って減る。
    """

    def setUp(self) -> None:
        super().setUp()
        self.write("CLAUDE.md", "root rules\n")
        self.write("src/CLAUDE.md", "src rules\n")
        self.write("src/big.ts", "".join("const x%d = 1\n" % i for i in range(600)))
        self.write("src/a.ts", "x\n")
        self.add()
        (self.root / "sub").mkdir(exist_ok=True)

    def digest_from(self, cwd: Path) -> str:
        res = self.run_in(TRIAGE, "--base", "HEAD", cwd=cwd)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout

    def test_large_file_signal_is_reported_from_repo_root(self):
        rows = "\n".join(self.section(self.digest_from(self.root), "## explorer-signals"))
        self.assertIn("large-file\tsrc/big.ts", rows)

    def test_large_file_boundary_is_measured_from_both_sides(self):
        """閾値は 500 行**超**。境界を両側から測らないと `-gt` / `-ge` の取り違えが素通りする."""
        self.write("src/exactly500.ts", "".join("x%d\n" % i for i in range(500)))
        self.write("src/over500.ts", "".join("x%d\n" % i for i in range(501)))
        self.add()
        rows = "\n".join(self.section(self.digest_from(self.root), "## explorer-signals"))
        self.assertIn("large-file\tsrc/over500.ts (501 lines)", rows)
        self.assertNotIn("exactly500", rows)

    def test_agents_md_is_listed_only_when_it_exists(self):
        """`[ -f ... ] && echo` の取り違えで**存在しない AGENTS.md を広告しない**こと."""
        rows = self.section(self.digest_from(self.root), "## agents-md")
        self.assertNotIn("AGENTS.md", rows, "この repo には AGENTS.md が無い")
        self.write("AGENTS.md", "root agents\n")
        self.write("src/AGENTS.md", "src agents\n")
        self.add()
        rows = self.section(self.digest_from(self.root), "## agents-md")
        self.assertIn("AGENTS.md", rows)
        self.assertIn("src/AGENTS.md", rows)

    def test_large_file_signal_survives_a_subdirectory_start(self):
        rows = "\n".join(self.section(self.digest_from(self.root / "sub"), "## explorer-signals"))
        self.assertIn("large-file\tsrc/big.ts", rows)

    def test_agents_md_is_reported_from_repo_root(self):
        rows = self.section(self.digest_from(self.root), "## agents-md")
        self.assertIn("CLAUDE.md", rows)
        self.assertIn("src/CLAUDE.md", rows)

    def test_agents_md_survives_a_subdirectory_start(self):
        """`## agents-md` は reviewer の CLAUDE.md 準拠観点の入力。空だと観点が丸ごと死ぬ."""
        rows = self.section(self.digest_from(self.root / "sub"), "## agents-md")
        self.assertIn("CLAUDE.md", rows)
        self.assertIn("src/CLAUDE.md", rows)


class TriageModelGenerationTest(DiffScriptTestBase):
    """Phase 0 に実行世代を出す（GitHub issue #210）.

    踏み下げた世代で回した回は検出が落ちるが、それが分かるのは publish 後の集計まで
    待たないといけなかった。ここで見えれば回す前に人が決められる。
    **警告も中止もしない** — どう扱うかは #210 が利用者側へ残した判断。

    測るのは「誤値を出さないこと」に寄せてある。**引けないより誤って引く方が悪い**
    （`orchestration-measurement.md ## 13.1`「縮退先は欠測であって誤値ではない」）。
    """

    SID = "11111111-2222-3333-4444-555555555555"

    def setUp(self) -> None:
        super().setUp()
        # triage は diff が空だと exit 1 なので、判定対象を 1 つ置く
        self.write("src/a.ts", "export const a = 1\n")
        self.add()

    def _env_with(self, *models: str, sid: str | None = None, write: bool = True) -> dict:
        """偽 HOME に transcript を置き、そこを指す env を返す.

        **実 transcript を掴ませない** — `git_env.scrub()` は `GIT_*` しか落とさないので、
        `HOME` と `CLAUDE_CODE_SESSION_ID` を明示しないとテストが開発機の実セッションを
        読んでしまう（環境の不在に頼らない / docs/testing-pitfalls.md）。
        """
        home = self.root / "home"
        if write:
            d = home / ".claude" / "projects" / "proj"
            d.mkdir(parents=True, exist_ok=True)
            (d / ("%s.jsonl" % self.SID)).write_text("\n".join(
                json.dumps({"type": "assistant", "timestamp": "2026-09-03T00:0%d:00Z" % i,
                            "message": {"model": m, "usage": {"output_tokens": 1}}})
                for i, m in enumerate(models)) + "\n", encoding="utf-8")
        else:
            home.mkdir(parents=True, exist_ok=True)
        env = self._env(HOME=str(home))
        if sid is not None:
            env["CLAUDE_CODE_SESSION_ID"] = sid
        else:
            env.pop("CLAUDE_CODE_SESSION_ID", None)
        return env

    def _models(self, env: dict) -> str | None:
        res = self.run_in(TRIAGE, "--base", "HEAD", env=env)
        self.assertEqual(res.returncode, 0, res.stderr)
        return self.kv(res.stdout, "## meta").get("models")

    def test_a_single_generation_is_reported(self):
        """引けたときは世代をそのまま出す."""
        self.assertEqual(
            self._models(self._env_with("claude-opus-5", sid=self.SID)), "claude-opus-5")

    def test_a_mixed_session_is_not_collapsed_to_one_generation(self):
        """途中で `/model` を切り替えた回を単一世代に倒さない（#169）."""
        got = self._models(self._env_with("claude-opus-4-8", "claude-opus-5", sid=self.SID))
        self.assertEqual(got, "混在（claude-opus-4-8/claude-opus-5）")

    def test_no_session_id_stays_silent(self):
        """縮退①: セッションを特定できない回は**行ごと出さない**."""
        self.assertIsNone(self._models(self._env_with("claude-opus-5", sid=None)))

    def test_an_unresolvable_session_stays_silent(self):
        """縮退②: id が transcript に解決しない回。

        **`ls -t` の最新へ倒さない** — 同一リポジトリで並行セッションがあると
        他セッションの世代を誤値として出す。
        """
        self.assertIsNone(self._models(
            self._env_with("claude-opus-5", sid="99999999-0000-0000-0000-000000000000")))

    def test_placeholder_models_stay_silent(self):
        """縮退③: 実モデル名が 1 つも無い回（`<synthetic>` 等のプレースホルダのみ）."""
        self.assertIsNone(self._models(self._env_with("<synthetic>", sid=self.SID)))

    def test_the_value_never_carries_the_sub_generation(self):
        """**Phase 0 の `sub` は「前回の fleet の世代」**なので値に混ぜない.

        混ぜると、これから起動する fleet の世代だと読まれる。
        """
        got = self._models(self._env_with("claude-opus-5", sid=self.SID))
        self.assertNotIn("sub", got or "")
        self.assertNotIn("/", got or "", "sub 側が値に漏れている")

    def _stderr(self, env: dict) -> str:
        res = self.run_in(TRIAGE, "--base", "HEAD", env=env)
        self.assertEqual(res.returncode, 0, "警告は rc を変えない（FATAL ではない）")
        return res.stderr

    def test_no_generation_warns(self):
        """世代では警告しない（#210 で 4 系の警告を外した）。`models=` の行は出し続ける."""
        for models in (("claude-opus-4-8",), ("claude-opus-5-5",), ("claude-opus-5",),
                       ("claude-opus-4-8", "claude-opus-5")):
            with self.subTest(models=models):
                env = self._env_with(*models, sid=self.SID)
                self.assertNotIn("世代", self._stderr(env))
                self.assertIsNotNone(self._models(env), "`models=` の行が消えている")

    def test_the_run_survives_a_missing_transcript_directory(self):
        """transcript ディレクトリごと無い環境でも Phase 0 は完走する."""
        env = self._env_with(sid=self.SID, write=False)
        res = self.run_in(TRIAGE, "--base", "HEAD", env=env)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("## size", res.stdout, "後続セクションが出ていない")


class DiffBaseFixture(DiffScriptTestBase):
    """origin を立てずに `refs/remotes/origin/*` を直接置いて、base の食い違いを作る."""

    def setUp(self) -> None:
        super().setUp()
        # 既定ブランチ名は git の設定で変わるので固定する
        self.git("branch", "-M", "main")
        self.init = self.head()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").stdout.strip()

    def commit_file(self, rel: str) -> str:
        # 中身をファイルごとに変える。同じだと git が削除 + 追加を rename にまとめ、
        # 逆向きに混ざった変更が b/ 側の 1 パスに隠れる
        self.write(rel, f"{rel}\n")
        self.add()
        self.git("commit", "-qm", rel)
        return self.head()

    def set_origin(self, branch: str, sha: str) -> None:
        self.git("update-ref", f"refs/remotes/origin/{branch}", sha)

    def advance_origin(self, *rels: str) -> str:
        """HEAD から一時ブランチでコミットを積み、その先端を origin/main にする（HEAD は動かさない）."""
        back = self.git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        self.git("checkout", "-qb", "tmp-origin")
        for rel in rels:
            tip = self.commit_file(rel)
        self.set_origin("main", tip)
        self.git("checkout", "-q", back)
        self.git("branch", "-D", "tmp-origin")
        return tip

    def stale_local_main(self) -> None:
        """origin/main から切ったブランチで作業し、ローカルの main だけが 2 commits 遅れている状態."""
        self.advance_origin("others1.txt", "others2.txt")
        self.git("checkout", "-qb", "feature", "refs/remotes/origin/main")
        self.commit_file("mine.txt")
        self.git("branch", "-f", "main", self.init)

    def diff_paths(self, out: str) -> set[str]:
        """diff に現れるパス（削除側の a/ も含める）. テストのパスは空白を含まない."""
        diff = Path(self.kv(out, "## meta")["diff_file"]).read_text(encoding="utf-8")
        paths: set[str] = set()
        for line in diff.splitlines():
            if line.startswith("diff --git "):
                _, _, a, b = line.split(" ")
                paths.update((a[2:], b[2:]))
        return paths

    def triage(self, base: str) -> subprocess.CompletedProcess[str]:
        res = self.run_in(TRIAGE, "--base", base)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res


class TriageDiffBaseTest(DiffBaseFixture):
    """diff の起点（GitHub issue #253）。**起点を誤っても diff は出る**ので、中身で見る."""

    def test_stale_local_base_takes_the_origin_merge_base(self):
        """issue の再現: ローカルの main が遅れていると、他で取り込まれた変更まで混ざっていた."""
        self.stale_local_main()
        origin = self.git("rev-parse", "refs/remotes/origin/main").stdout.strip()
        res = self.triage("main")
        self.assertEqual(self.diff_paths(res.stdout), {"mine.txt"})
        # 規模は diff 本体と別の `git diff --numstat` で数える。片方だけ起点がずれても落とす
        self.assertEqual(self.kv(res.stdout, "## size")["total_files"], "1")
        meta = self.kv(res.stdout, "## meta")
        self.assertEqual(meta["base"], "origin/main")
        self.assertEqual(meta["diff_base"], origin)
        self.assertIn("⚠️ base: ローカルの main が origin/main より 2 commits 遅れている", res.stderr)

    def test_unpushed_local_base_is_not_replaced_by_origin(self):
        """origin を無条件に優先すると、未 push のコミットが逆向きに混ざる."""
        self.set_origin("main", self.init)
        self.commit_file("unpushed.txt")
        self.git("checkout", "-qb", "feature")
        self.commit_file("mine.txt")
        res = self.triage("main")
        self.assertEqual(self.diff_paths(res.stdout), {"mine.txt"})
        self.assertEqual(self.kv(res.stdout, "## meta")["base"], "main")
        self.assertNotIn("⚠️ base", res.stderr)

    def test_base_advanced_after_branching_is_not_reverse_diffed(self):
        """直接比較（`main..HEAD`）だと、切った後に main へ入った変更が削除として混ざる."""
        self.git("checkout", "-qb", "feature")
        self.commit_file("mine.txt")
        self.git("checkout", "-q", "main")
        self.commit_file("later.txt")
        self.git("checkout", "-q", "feature")
        res = self.triage("main")
        self.assertEqual(self.diff_paths(res.stdout), {"mine.txt"})
        self.assertEqual(self.kv(res.stdout, "## size")["total_files"], "1")

    def test_diff_base_matches_the_pre_image_when_base_advanced(self):
        """`base=` の ref の先端は切った後に進むので、agent の `git show` には `diff_base=` を渡す."""
        self.write("f.txt", "a\nguard\n")
        self.add()
        self.git("commit", "-qm", "f")
        branch_point = self.head()
        self.git("checkout", "-qb", "feature")
        self.commit_file("mine.txt")
        self.git("checkout", "-q", "main")
        self.write("f.txt", "a\n")
        self.add()
        self.git("commit", "-qm", "main drops guard")
        self.git("checkout", "-q", "feature")
        meta = self.kv(self.triage("main").stdout, "## meta")
        self.assertEqual(meta["base"], "main")
        self.assertEqual(meta["diff_base"], branch_point)
        self.assertEqual(self.git("show", f"{meta['diff_base']}:f.txt").stdout, "a\nguard\n")

    def test_staged_run_has_no_diff_base(self):
        """`--staged` は起点を解決しないので `diff_base=` を出さない（前回値や空値を出さない）."""
        self.write("mine.txt", "x\n")
        self.add()
        res = self.run_in(TRIAGE, "--base", "main", "--staged")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("diff_base", self.kv(res.stdout, "## meta"))
        self.assertEqual(self.kv(res.stdout, "## meta")["base"], "main", "meta 自体は出ている")

    def test_equal_merge_bases_keep_the_local_ref_without_warning(self):
        """base ブランチ上で未コミットの変更だけを見る回。origin が先にいても分岐点は同じ."""
        self.advance_origin("others.txt")
        self.write("mine.txt", "x\n")
        self.add()
        res = self.triage("main")
        self.assertEqual(self.diff_paths(res.stdout), {"mine.txt"})
        self.assertEqual(self.kv(res.stdout, "## meta")["base"], "main")
        self.assertNotIn("⚠️ base", res.stderr)

    def test_branch_only_on_origin_resolves_without_warning(self):
        """ローカルに無いブランチ名も origin 側で解決する（遅れを比べる相手が無いので鳴らさない）."""
        self.set_origin("develop", self.init)
        self.commit_file("mine.txt")
        res = self.triage("develop")
        self.assertEqual(self.diff_paths(res.stdout), {"mine.txt"})
        self.assertEqual(self.kv(res.stdout, "## meta")["base"], "origin/develop")
        self.assertNotIn("⚠️ base", res.stderr)

    def test_rev_expression_is_not_resolved_on_origin(self):
        """`HEAD~1` を `refs/remotes/origin/HEAD~1` として解決させない.

        origin/HEAD が HEAD より先にいると、そちらの分岐点が HEAD 自身になり diff が空になる。
        """
        self.commit_file("mine.txt")
        self.advance_origin("others1.txt", "others2.txt")
        self.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        res = self.triage("HEAD~1")
        self.assertEqual(self.diff_paths(res.stdout), {"mine.txt"})

    def test_unrelated_history_falls_back_to_a_direct_comparison(self):
        """共通の履歴が無い base は従来どおり先端と直接比べる（解決できない扱いにしない）."""
        self.git("checkout", "-q", "--orphan", "other")
        self.git("rm", "-rqf", "--ignore-unmatch", ".")
        self.commit_file("theirs.txt")
        self.git("checkout", "-q", "main")
        self.commit_file("mine.txt")
        res = self.triage("other")
        self.assertIn("mine.txt", self.diff_paths(res.stdout))


DIFF_BASE = PLUGIN / "scripts" / "lib" / "diff-base.sh"


class DiffBaseCliTest(DiffBaseFixture):
    """`bash lib/diff-base.sh <base>` — SKILL 本文でモデルが読む diff を、スクリプトと同じ起点に揃える出口."""

    def test_stale_local_base_prints_the_origin_merge_base_and_warns(self):
        self.stale_local_main()
        origin = self.git("rev-parse", "refs/remotes/origin/main").stdout.strip()
        res = self.run_in(DIFF_BASE, "main")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.splitlines(), ["base=origin/main", f"diff_base={origin}"])
        self.assertIn("⚠️ base: ローカルの main が origin/main より 2 commits 遅れている", res.stderr)

    def test_up_to_date_base_is_silent(self):
        self.git("checkout", "-qb", "feature")
        self.commit_file("mine.txt")
        res = self.run_in(DIFF_BASE, "main")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.splitlines(), ["base=main", f"diff_base={self.init}"])
        self.assertEqual(res.stderr, "")

    def test_unresolvable_base_exits_2_without_output(self):
        res = self.run_in(DIFF_BASE, "no-such-ref")
        self.assertEqual(res.returncode, 2)
        self.assertIn("base ref を解決できない", res.stderr)
        self.assertEqual(res.stdout, "")

    def test_sourcing_prints_nothing(self):
        """source されたときは黙る（出すと triage-signals.sh の `## meta` に混ざる）. 直接実行の対は上の 3 本."""
        res = subprocess.run(["bash", "-c", '. "$1" main', "sh", str(DIFF_BASE)], cwd=self.root,
                             capture_output=True, text=True, env=self._env(), timeout=60)
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, "", ""))


BASE_BRANCH = PLUGIN / "scripts" / "lib" / "base-branch.sh"


class BaseBranchCliTest(DiffBaseFixture):
    """`bash lib/base-branch.sh [<base>]` — base branch の決め方（GitHub issue #274）.

    統合ブランチから切ったブランチで default branch（main）を掴むと、統合ブランチの他の変更まで
    diff に混ざり、editor でタスクの diff だけを見られない。**誤った候補を掴むより default に落ちる側を厚く見る**。
    """

    def resolve(self, *args: str) -> dict[str, str]:
        res = self.run_in(BASE_BRANCH, *args)
        self.assertEqual(res.returncode, 0, res.stderr)
        return dict(l.split("=", 1) for l in res.stdout.splitlines())

    def set_default(self, branch: str = "main") -> None:
        self.set_origin(branch, self.init)
        self.git("symbolic-ref", "refs/remotes/origin/HEAD", f"refs/remotes/origin/{branch}")

    def test_explicit_argument_wins(self):
        self.git("branch", "project/x")
        self.git("checkout", "-qb", "feat", "project/x")
        self.assertEqual(self.resolve("release"), {"base_branch": "release", "base_source": "arg"})

    def test_branch_created_from_an_integration_branch(self):
        self.set_default()
        self.git("branch", "project/x")
        self.git("checkout", "-qb", "feat", "project/x")
        self.assertEqual(self.resolve(), {"base_branch": "project/x", "base_source": "reflog"})

    def test_branch_created_from_the_remote_integration_branch(self):
        """`origin/` を外したブランチ名にする（diff-base.sh がローカルと origin の両方を見る）."""
        self.set_default()
        self.set_origin("project/x", self.init)
        self.git("checkout", "-qb", "feat", "refs/remotes/origin/project/x")
        self.assertEqual(self.resolve()["base_branch"], "project/x")

    def test_branch_created_without_a_start_point_uses_the_branch_it_was_on(self):
        self.set_default()
        self.git("checkout", "-qb", "project/x")
        self.git("checkout", "-qb", "feat")
        self.assertEqual(self.resolve(), {"base_branch": "project/x", "base_source": "reflog"})

    def test_worktree_branch_records_its_start_point(self):
        self.set_default()
        self.git("branch", "project/x")
        wt = self.root.parent / (self.root.name + "-wt")
        self.git("worktree", "add", "-q", "-b", "feat", str(wt), "project/x")
        self.addCleanup(lambda: self.git("worktree", "remove", "--force", str(wt)))
        res = self.run_in(BASE_BRANCH, cwd=wt)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("base_branch=project/x", res.stdout.splitlines())

    # --- default に落ちる条件 ---
    def test_own_upstream_is_not_a_base(self):
        """`git checkout -b feat origin/feat`（fetch で入ってきたブランチ）は自分自身を base にしない."""
        self.set_default()
        self.set_origin("feat", self.init)
        self.git("checkout", "-qb", "feat", "refs/remotes/origin/feat")
        self.assertEqual(self.resolve(), {"base_branch": "main", "base_source": "default"})

    def test_deleted_start_branch_falls_back(self):
        self.set_default()
        self.git("branch", "gone")
        self.git("checkout", "-qb", "feat", "gone")
        self.git("branch", "-D", "gone")
        self.assertEqual(self.resolve()["base_source"], "default")

    def test_start_point_given_as_a_commit_falls_back(self):
        self.set_default()
        self.git("checkout", "-qb", "feat", self.init)
        self.assertEqual(self.resolve()["base_source"], "default")

    def test_branch_created_from_detached_head_falls_back(self):
        self.set_default()
        self.git("checkout", "-q", "--detach")
        self.git("checkout", "-qb", "feat")
        self.assertEqual(self.resolve()["base_source"], "default")

    def test_detached_head_falls_back(self):
        self.set_default()
        self.git("checkout", "-q", "--detach")
        self.assertEqual(self.resolve(), {"base_branch": "main", "base_source": "default"})

    def test_nothing_resolvable_exits_2(self):
        self.git("checkout", "-q", "--detach")
        res = self.run_in(BASE_BRANCH)
        self.assertEqual(res.returncode, 2)
        self.assertIn("FATAL", res.stderr)
        self.assertEqual(res.stdout, "")

    def test_sourcing_prints_nothing(self):
        res = subprocess.run(["bash", "-c", '. "$1"', "sh", str(BASE_BRANCH)], cwd=self.root,
                             capture_output=True, text=True, env=self._env(), timeout=60)
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, "", ""))


class BaseBranchRefreshTest(DiffBaseFixture):
    """`--refresh`: origin から取り直し、ローカルの base を早送りできるときだけ進める（GitHub issue #274）.

    **ローカルを書き換えるのは早送りだけ**。別の作業ツリーでチェックアウト中・未 push のコミットがある・
    ブランチでない指定は進めない。origin は使い捨ての bare リポジトリ。
    """

    def setUp(self) -> None:
        super().setUp()
        self.origin_dir = self.root.parent / (self.root.name + "-origin.git")
        subprocess.run(["git", "init", "-q", "--bare", str(self.origin_dir)], capture_output=True,
                       env=self._env(), check=True)
        self.addCleanup(lambda: __import__("shutil").rmtree(self.origin_dir, ignore_errors=True))
        self.git("remote", "add", "origin", str(self.origin_dir))
        self.git("branch", "project/x")
        self.git("push", "-q", "origin", "main", "project/x")

    def advance_remote(self, branch: str) -> str:
        """origin の branch にだけコミットを 2 つ積む（ローカルの branch は古いまま）."""
        self.git("checkout", "-qb", "tmp", branch)
        self.commit_file("o1.txt")
        tip = self.commit_file("o2.txt")
        self.git("push", "-q", "origin", f"tmp:{branch}")
        self.git("checkout", "-q", "main")
        self.git("branch", "-D", "tmp")
        return tip

    def refresh(self, *args: str) -> dict[str, str]:
        res = self.run_in(BASE_BRANCH, "--refresh", *args)
        self.assertEqual(res.returncode, 0, res.stderr)
        return dict(l.split("=", 1) for l in res.stdout.splitlines())

    def local(self, branch: str) -> str:
        return self.git("rev-parse", f"refs/heads/{branch}").stdout.strip()

    def test_behind_local_base_is_fast_forwarded(self):
        tip = self.advance_remote("project/x")
        self.git("checkout", "-qb", "feat", "project/x")
        self.assertEqual(self.refresh()["base_refresh"], "fast-forwarded:2")
        self.assertEqual(self.local("project/x"), tip)

    def test_base_checked_out_elsewhere_is_not_moved(self):
        """別の作業ツリーで使っているブランチを動かすと、その作業ツリーの index とずれる."""
        old = self.local("project/x")
        self.advance_remote("project/x")
        self.git("checkout", "-qb", "feat", "project/x")
        wt = self.root.parent / (self.root.name + "-wt2")
        self.git("worktree", "add", "-q", str(wt), "project/x")
        self.addCleanup(lambda: self.git("worktree", "remove", "--force", str(wt)))
        self.assertEqual(self.refresh()["base_refresh"], "behind-checked-out:2")
        self.assertEqual(self.local("project/x"), old)

    def test_up_to_date(self):
        self.git("checkout", "-qb", "feat", "project/x")
        self.assertEqual(self.refresh()["base_refresh"], "up-to-date")

    def test_diverged_local_base_is_not_moved(self):
        self.advance_remote("project/x")
        self.git("checkout", "-q", "project/x")
        mine = self.commit_file("unpushed.txt")
        self.git("checkout", "-qb", "feat")
        self.assertEqual(self.refresh()["base_refresh"], "diverged")
        self.assertEqual(self.local("project/x"), mine)

    def test_non_branch_base_is_not_fetched(self):
        self.git("checkout", "-qb", "feat")
        self.assertEqual(self.refresh("HEAD~0")["base_refresh"], "not-a-branch")

    def test_local_only_base_is_reported_as_not_on_origin(self):
        """origin に無いブランチは「取り直せなかった」ではなく、取り直す相手が無い."""
        self.git("branch", "local-only")
        self.git("checkout", "-qb", "feat", "local-only")
        self.assertEqual(self.refresh()["base_refresh"], "not-on-origin")

    def test_origin_only_base_is_fetched_without_a_local_branch(self):
        self.git("checkout", "-qb", "feat", "project/x")
        self.git("branch", "-D", "project/x")
        self.assertEqual(self.refresh("project/x")["base_refresh"], "no-local")

    def test_without_origin(self):
        self.git("remote", "remove", "origin")
        self.git("checkout", "-qb", "feat", "project/x")
        self.assertEqual(self.refresh()["base_refresh"], "no-origin")


if __name__ == "__main__":
    unittest.main()
