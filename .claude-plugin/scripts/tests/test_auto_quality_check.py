#!/usr/bin/env python3
"""`auto-quality-check.sh`（Stop hook）の回帰テスト（GitHub issue #139）.

**このスクリプトの壊れ方は「静かに緑」**: Stop hook の正常系が silent exit 0 なので、
検査を走らせ損ねても通知が消えても端末には何も出ず、「問題なし」と区別がつかない。
v2.69.0 で中身を `machine-layer.sh` への委譲に書き換えたのにテストは 0 件で、実際に
**検出時の通知が丸ごと落ちる**欠陥が入っていた（`set -e` 下の `ML_OUT="$(...)"` が
machine-layer の exit 1 で ERR trap を踏み、report 部へ到達しない）。

**対象は実物をコピーしたもの**: このスクリプトは自分の位置から `REPO_ROOT` を導くので、
使い捨てリポジトリに置けばそのリポジトリを見る（本番コードにテスト専用の差し替え口を
足さずに隔離できる）。検査本体は `machine-layer.sh` の stub に差し替え、**hook の契約**
だけを見る — ①いつ走らせるか ②exit code をどう写すか ③常に exit 0（Stop を止めない）。
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from git_env import scrub

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude-plugin" / "scripts" / "auto-quality-check.sh"
SAFE_HOOK = ROOT / ".claude-plugin" / "lib" / "safe-hook.sh"

#: プラグイン関連とみなされ検査が走るべきパス（ヘッダのトリガー条件の実体）
TRIGGERING = (
    "demo/.claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    "demo/skills/s/SKILL.md",
    "demo/commands/c.md",
    "demo/hooks/hooks.json",
    "demo/agents/a.md",
    "demo/references/r.md",
    "demo/scripts/x.sh",
    "demo/CHANGELOG.md",
)

#: 走らせてはいけないパス（プラグインに関係しない変更でターンごとに検査を回さない）
NOT_TRIGGERING = ("README.md", "docs/pipeline-design.md", "evals/cases/a.yaml", "notes.txt")


class AutoQualityCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self._cache_tmp = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self._cache_tmp.name).resolve()
        self.addCleanup(self._cache_tmp.cleanup)
        (self.root / ".claude-plugin" / "lib").mkdir(parents=True)
        self.scripts = self.root / ".claude-plugin" / "scripts"
        self.scripts.mkdir(parents=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.set_pgrep()
        shutil.copy2(SAFE_HOOK, self.root / ".claude-plugin" / "lib" / "safe-hook.sh")
        shutil.copy2(SCRIPT, self.scripts / "auto-quality-check.sh")
        self.marker = self.root / "layer-invocations"
        self.set_layer(0)
        self.git("init", "-q", ".")
        # **author はリポジトリ側に設定する**（env の `GIT_AUTHOR_*` は init commit にしか
        # 効かず、global config の無い CI でだけ `git commit` が落ちる）
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.git("commit", "-q", "--allow-empty", "-m", "init")

    # ---- 使い捨てリポジトリの操作 -------------------------------------------
    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = scrub()   # git hook 由来の変数を落とす（正本と理由は `git_env`）
        return subprocess.run(["git", *args], cwd=str(self.root), capture_output=True,
                              text=True, env=env, check=True)

    def modify(self, rel: str) -> None:
        """`rel` を tracked にしてから変更する.

        **untracked のままにしない**: `git status --porcelain` は中身が全部 untracked な
        ディレクトリを `?? demo/` に畳むので、パターン照合の対象が実運用とずれる。
        """
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("baseline\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "add " + rel)
        path.write_text("changed\n", encoding="utf-8")

    def set_layer(self, code: int, output: str = "") -> None:
        """`machine-layer.sh` の stub を置く.

        **bash builtin だけで書く**（PATH を絞るテストがあり、`cat` すら引けない場面がある。
        stub が落ちると出力が空になり「検出なし」と区別できなくなる）。
        """
        body = "#!/usr/bin/env bash\n"
        body += 'printf \'x\' >> "${BASH_SOURCE[0]%/*}/../../layer-invocations"\n'
        if output:
            body += "printf '%%s\\n' %s\n" % shlex.quote(output)
        body += "exit %d\n" % code
        stub = self.scripts / "machine-layer.sh"
        stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)

    def set_pgrep(self, code: int = 1) -> None:
        r"""`pgrep` の stub を置く（既定の 1 = 該当なし＝変異テストは走っていない）.

        **テストを実プロセス表に依存させない**: `auto-quality-check.sh` は変異テスト中かを
        `pgrep -f "mutation-test\.py"` で判定する。本物を引かせると、このスイートが
        `mutation-test.py` の中から走る経路（CI の `mutation-test` ジョブ / ローカルの
        変異テスト）で**自分の親プロセスに引っかかり**、全ケースがスキップに落ちて
        「静かに緑」ではなく一斉に落ちる（実測: CI で 19 failures + 2 errors。使い捨て
        リポジトリで隔離できるのはジャーナル側だけで、プロセス表は隔離できない）。

        **PATH から外すのではなく stub を置く**: `command -v pgrep` が偽だとガードが
        ジャーナル判定だけに短絡し、pgrep 経路が一度も実行されないテストになる。
        """
        stub = self.bin / "pgrep"
        stub.write_text("#!/usr/bin/env bash\nexit %d\n" % code, encoding="utf-8")
        stub.chmod(0o755)

    @property
    def layer_ran(self) -> bool:
        return self.marker.exists()

    # ---- 実行 ---------------------------------------------------------------
    def run_hook(self, payload: str = '{"hook_event_name":"Stop"}',
                 env: dict[str, str] | None = None,
                 cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(self.scripts / "auto-quality-check.sh")],
            input=payload, capture_output=True, text=True, timeout=60,
            cwd=str(cwd or self.root), env=env or self.env(),
        )

    def env(self, with_encoder: bool = True) -> dict[str, str]:
        env = scrub()
        # **キャッシュの置き場をテスト専用に向ける**（実 `/tmp` を汚さない / リポジトリ
        # パスが鍵なので使い捨てリポジトリごとに別ファイルになる）。
        # **リポジトリの外に置く** — 中に置くとキャッシュを書いた事実が `git status` に
        # 現れて指紋が毎回変わり、debounce が永久に効かない状態をテストしてしまう
        env["TMPDIR"] = str(self.cache_dir)
        # **stub を PATH の先頭に置く**（`set_pgrep` の docstring 参照）。ここを実物の
        # `pgrep` に任せると、このスイートが変異テストの中から走る経路で全ケースが
        # スキップに落ちる
        if with_encoder:
            env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "")
            return env
        # **「このディレクトリには無いはず」に頼らない**（Linux の `/bin` は `/usr/bin` の
        # symlink で、CI には python3 も jq も入っている）。**引けるものを列挙する**側で作る。
        # スクリプトが外部に依存するのは git / cat（safe_hook_init）/ cut / grep / bash だけ
        for name in ("bash", "git", "cat", "cut", "grep", "dirname"):
            real = shutil.which(name)
            self.assertIsNotNone(real, "%s が見つからない" % name)
            dest = self.bin / name
            if not dest.exists():
                dest.symlink_to(real)
        env["PATH"] = str(self.bin)
        return env

    def context(self, res: subprocess.CompletedProcess[str]) -> str:
        """stdout を additionalContext として読む（**stdout 全体が単一 JSON** である契約）."""
        self.assertTrue(res.stdout.strip(), "Claude 向けの注入が無い: %r" % res.stdout)
        data = json.loads(res.stdout)
        hso = data["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "Stop")
        return hso["additionalContext"]

    # ---- いつ走らせるか -----------------------------------------------------
    def test_clean_tree_never_runs_the_layer(self):
        res = self.run_hook()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout, "")
        self.assertFalse(self.layer_ran, "変更が無いターンで検査を走らせない")

    def test_unrelated_changes_never_run_the_layer(self):
        for rel in NOT_TRIGGERING:
            with self.subTest(path=rel):
                self.setUp()
                self.modify(rel)
                res = self.run_hook()
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertEqual(res.stdout, "")
                self.assertFalse(self.layer_ran, "%s は検査対象外" % rel)

    def test_plugin_related_changes_run_the_layer(self):
        for rel in TRIGGERING:
            with self.subTest(path=rel):
                self.setUp()
                self.modify(rel)
                self.run_hook()
                self.assertTrue(self.layer_ran, "%s の変更で検査が走っていない" % rel)

    def test_outside_a_git_repository_is_a_silent_no_op(self):
        shutil.rmtree(self.root / ".git")
        env = {**self.env(), "GIT_CEILING_DIRECTORIES": str(self.root.parent)}
        res = self.run_hook(env=env)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout, "")
        self.assertFalse(self.layer_ran)

    def test_the_hook_does_not_depend_on_the_working_directory(self):
        """Stop hook の cwd は呼び出し側が決める（`REPO_ROOT` は自分の位置から導く契約）."""
        self.modify("demo/skills/s/SKILL.md")
        self.set_layer(1, "SSoT がずれている")
        outside = self.root / "elsewhere"
        outside.mkdir()
        res = self.run_hook(cwd=outside)
        self.assertEqual(res.returncode, 0)
        self.assertIn("SSoT がずれている", self.context(res))

    # ---- exit code をどう写すか ---------------------------------------------
    def test_green_layer_reports_nothing(self):
        self.modify("demo/skills/s/SKILL.md")
        self.set_layer(0)
        res = self.run_hook()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(self.layer_ran, "前提: 検査は走っている")
        self.assertEqual(res.stdout, "", "緑のときは注入しない")
        self.assertNotIn("auto-quality-check:", res.stderr)

    def test_detection_reaches_both_the_user_and_claude(self):
        """**検出が通知に化けて消えない**（v2.69.0 で実際に落ちていた経路）."""
        self.modify("demo/skills/s/SKILL.md")
        self.set_layer(1, "[quality] allowed-tools が一致しない")
        res = self.run_hook()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("[quality] allowed-tools が一致しない", res.stderr)
        self.assertIn("auto-quality-check", res.stderr)
        self.assertIn("[quality] allowed-tools が一致しない", self.context(res))

    def test_unknown_verdict_is_not_folded_into_green(self):
        """exit 2（判定不能）は**通過でも検出でもない**ものとして通知する.

        0 に倒すと「前提が壊れている」が「問題なし」に化け、1 に倒すと
        「python3 が無い」が「品質問題あり」として通知される。
        """
        self.modify("demo/skills/s/SKILL.md")
        self.set_layer(2, "[machine-layer] python3 が無いため実行できなかった")
        res = self.run_hook()
        self.assertEqual(res.returncode, 0, res.stderr)
        ctx = self.context(res)
        self.assertIn("判定不能", ctx)
        self.assertIn("exit 2", ctx)
        self.assertIn("python3 が無いため実行できなかった", ctx)
        self.assertIn("判定不能", res.stderr)

    def test_a_layer_that_cannot_run_at_all_is_reported(self):
        """スクリプトが消えた（exit 127）も「判定不能」側に倒す（黙って緑にしない）."""
        self.modify("demo/skills/s/SKILL.md")
        (self.scripts / "machine-layer.sh").unlink()
        res = self.run_hook()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("判定不能", self.context(res))

    def test_never_blocks_the_stop_hook(self):
        for code in (0, 1, 2, 127):
            with self.subTest(exit_code=code):
                self.setUp()
                self.modify("demo/skills/s/SKILL.md")
                self.set_layer(code, "何か")
                res = self.run_hook()
                self.assertEqual(res.returncode, 0, "Stop をブロックしてはいけない")

    # ---- 出力の形 -----------------------------------------------------------
    def test_additional_context_stays_valid_json_for_hostile_output(self):
        """検査の出力に JSON を壊す文字が混ざっても注入が消えない（エンコーダに委譲）."""
        hostile = '"引用符" と \\ と $HOME と 改行:\nnext line'
        self.modify("demo/skills/s/SKILL.md")
        self.set_layer(1, hostile)
        res = self.run_hook()
        ctx = self.context(res)
        self.assertIn('"引用符"', ctx)
        self.assertIn("$HOME", ctx)
        self.assertIn("next line", ctx)

    def test_multiline_findings_are_not_truncated_to_the_first_line(self):
        self.modify("demo/skills/s/SKILL.md")
        self.set_layer(1, "1 件目\n2 件目\n3 件目")
        ctx = self.context(self.run_hook())
        for line in ("1 件目", "2 件目", "3 件目"):
            self.assertIn(line, ctx)

    def test_without_an_encoder_the_user_notification_survives(self):
        """python3 も jq も無い環境では additionalContext を諦め、stderr 通知だけ残す.

        壊れた JSON を出すと hook 出力の解釈が丸ごと落ちるので、**出さない**方に倒す。
        """
        self.modify("demo/skills/s/SKILL.md")
        self.set_layer(1, "[quality] 何かがずれている")
        res = self.run_hook(env=self.env(with_encoder=False))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout, "", "JSON を組めないなら注入しない")
        self.assertIn("[quality] 何かがずれている", res.stderr)

    # ---- 走らせない条件: 変異テストの実行中 ---------------------------------
    def test_running_mutation_test_skips_the_layer(self):
        """変異中のソースを検査しても結果が嘘になる（実測: 1 作業中に 6 回の偽検出）."""
        self.modify("demo/skills/s/SKILL.md")
        (self.root / ".mutation-test-journal.json").write_text("{}", encoding="utf-8")
        res = self.run_hook()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse(self.layer_ran, "変異テストの実行中に検査を走らせている")
        self.assertIn("変異テスト", res.stderr, "黙って exit すると『問題なし』と読める")
        self.assertEqual(res.stdout, "", "修復材料が無いので Claude には注入しない")

    def test_running_mutation_test_is_detected_by_pgrep_without_a_journal(self):
        """ジャーナルが無い**変異と変異の隙間**も塞ぐ（そこも検査結果は当てにならない）."""
        self.modify("demo/skills/s/SKILL.md")
        self.assertFalse((self.root / ".mutation-test-journal.json").exists(), "前提")
        self.set_pgrep(0)
        res = self.run_hook()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse(self.layer_ran, "pgrep が引けているのに検査を走らせている")
        self.assertIn("変異テスト", res.stderr)

    def test_the_skip_does_not_poison_the_cache(self):
        """スキップした回を「clean だった」として記録しない（次のターンで検査が飛ぶ）."""
        self.modify("demo/skills/s/SKILL.md")
        journal = self.root / ".mutation-test-journal.json"
        journal.write_text("{}", encoding="utf-8")
        self.run_hook()
        journal.unlink()
        self.set_layer(1, "[quality] 変異とは無関係の本物の検出")
        res = self.run_hook()
        self.assertTrue(self.layer_ran, "スキップした回のせいで検査が飛んでいる")
        self.assertIn("本物の検出", self.context(res))

    # ---- 走らせない条件: 前回から作業ツリーが変わっていない -------------------
    def test_unchanged_tree_does_not_rerun_the_layer(self):
        """毎ターン走ると実測 125 秒のスイートが空回りする（同じ内容なら結果も同じ）."""
        self.modify("demo/skills/s/SKILL.md")
        self.run_hook()
        self.assertTrue(self.layer_ran, "前提: 1 回目は走る")
        self.marker.unlink()
        res = self.run_hook()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse(self.layer_ran, "作業ツリーが同じなのに再走している")

    def test_a_cached_detection_is_replayed_without_rerunning(self):
        """**黙るだけにしない**: 検出のあった次のターンで無言になると「直った」と読める."""
        self.modify("demo/skills/s/SKILL.md")
        self.set_layer(1, "[quality] SSoT pin がずれている")
        first = self.run_hook()
        self.assertIn("SSoT pin がずれている", self.context(first))
        self.marker.unlink()
        second = self.run_hook()
        self.assertFalse(self.layer_ran, "キャッシュがあるのに再走している")
        self.assertIn("SSoT pin がずれている", self.context(second), "検出が消えている")
        self.assertIn("SSoT pin がずれている", second.stderr)

    def test_changing_a_tracked_file_invalidates_the_cache(self):
        self.modify("demo/skills/s/SKILL.md")
        self.run_hook()
        self.marker.unlink()
        (self.root / "demo" / "skills" / "s" / "SKILL.md").write_text("changed again\n",
                                                                     encoding="utf-8")
        self.run_hook()
        self.assertTrue(self.layer_ran, "中身が変わったのに再走していない")

    def test_changing_an_untracked_file_invalidates_the_cache(self):
        """`git diff` ではなく**中身のハッシュ**で指紋を採る理由（untracked を拾う）."""
        self.modify("demo/skills/s/SKILL.md")
        new_file = self.root / "demo" / "scripts" / "x.sh"
        new_file.parent.mkdir(parents=True, exist_ok=True)
        new_file.write_text("echo a\n", encoding="utf-8")
        self.run_hook()
        self.marker.unlink()
        new_file.write_text("echo b\n", encoding="utf-8")
        self.run_hook()
        self.assertTrue(self.layer_ran, "untracked の中身の変化を拾えていない")

    def test_editing_a_renamed_file_invalidates_the_cache(self):
        """rename したファイルの編集を拾う（GitHub issue #175）.

        既定の porcelain は rename を `old -> new` の 1 行で返すので、パスとして扱うと
        実ファイルに解決できず**中身が指紋に入らない**。しかも status 行は XY（先頭 2 文字）が
        `R ` → `RM` と変わるだけなので、`cut -c4-` 後の文字列は同一 — つまり rename 済みの
        ファイルをいくら編集しても指紋が動かず、**機械層を一度も再走させない**。
        """
        self.modify("demo/skills/s/SKILL.md")
        self.git("add", "-A")
        self.git("commit", "-qm", "baseline")
        self.git("mv", "demo/skills/s/SKILL.md", "demo/skills/s/RENAMED.md")
        renamed = self.root / "demo" / "skills" / "s" / "RENAMED.md"
        self.run_hook()
        self.assertTrue(self.layer_ran, "前提: rename 自体で 1 回は走る")
        self.marker.unlink()
        renamed.write_text("edited after the rename\n", encoding="utf-8")
        self.run_hook()
        self.assertTrue(self.layer_ran, "rename 済みファイルの編集で再走していない")

    def test_editing_a_non_ascii_filename_invalidates_the_cache(self):
        """非 ASCII 名の編集を拾う（GitHub issue #175）.

        既定の porcelain は非 ASCII 名を `"\\346\\227\\245..."` とクオート付き 8 進
        エスケープで返すため、そのままではファイルに解決できず中身が指紋に入らない。
        """
        self.modify("demo/skills/s/SKILL.md")
        target = self.root / "demo" / "skills" / "s" / "日本語ノート.md"
        target.write_text("初版\n", encoding="utf-8")
        self.run_hook()
        self.assertTrue(self.layer_ran, "前提: 追加で 1 回は走る")
        self.marker.unlink()
        target.write_text("改訂\n", encoding="utf-8")
        self.run_hook()
        self.assertTrue(self.layer_ran, "非 ASCII 名ファイルの編集で再走していない")

    def test_backslashes_in_findings_are_delivered_verbatim(self):
        """検出内容のバックスラッシュをエスケープとして解釈しない（GitHub issue #175）.

        機械層の出力には unittest の失敗 diff（`'a\\nb' != 'a\\nc'` のような repr）が入る。
        `printf %b` に通すと実改行に化け、`\\c` が現れると**そこから先を丸ごと捨てる**ので、
        通知本文が黙って切れる。ユーザー向け（stderr）と Claude 向け（additionalContext）の
        両方で原文が保たれることを表明する。
        """
        finding = r"[unit-tests] AssertionError: 'a\nb' != 'a\nc' / tail\cAFTER"
        self.set_layer(1, finding)
        self.modify("demo/skills/s/SKILL.md")
        res = self.run_hook()
        self.assertIn(finding, res.stderr, "stderr の検出内容が原文と違う（%b で壊れている）")
        self.assertIn(finding, self.context(res),
                      "additionalContext の検出内容が原文と違う（%b で壊れている）")

    def test_without_cksum_the_layer_always_runs(self):
        """指紋を採れない環境では**走る側に倒す**（検査を飛ばす方に倒さない）."""
        self.modify("demo/skills/s/SKILL.md")
        env = self.env(with_encoder=False)      # PATH に cksum を置かない
        self.run_hook(env=env)
        self.assertTrue(self.layer_ran, "前提: 1 回目は走る")
        self.marker.unlink()
        self.run_hook(env=env)
        self.assertTrue(self.layer_ran, "指紋を採れないのにスキップしている")

    def test_stdin_is_consumed_so_the_hook_cannot_hang(self):
        """hook は stdin を消費してから処理を始める（消費しないとハングする）."""
        payload = json.dumps({"hook_event_name": "Stop", "transcript": "x" * 200_000})
        res = self.run_hook(payload=payload)   # timeout で落ちなければ消費できている
        self.assertEqual(res.returncode, 0, res.stderr)


if __name__ == "__main__":
    unittest.main()
