#!/usr/bin/env python3
"""feature-dev 同梱スクリプトの CLI 境界テスト（導入判定 plugin-enabled.sh は正本 .claude-plugin/lib/ を叩く）.

有効判定を誤ると、無効化したプラグインの skill を呼びに行く（有効と誤認）か、project だけで
有効化したプラグインを使わない（取りこぼし）。以前の判定は `$HOME/.claude/settings.json` に
キーがあるかだけを見ていて、両方を起こしていた。**0 に倒すべき条件を厚く**書く。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from git_env import scrub

REPO = Path(__file__).resolve().parents[3]
# 正本を叩く。feature-dev / issue-workflow の scripts/plugin-enabled.sh は byte 一致の複製で、
# 一致は validate_plugin_quality.py の BYTE_REPLICAS が検証する
SCRIPT = REPO / ".claude-plugin" / "lib" / "plugin-enabled.sh"


class PluginEnabledTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / "home"
        self.proj = self.root / "proj"
        (self.home / ".claude").mkdir(parents=True)
        (self.proj / ".claude").mkdir(parents=True)

    def settings(self, where: str, plugins: dict[str, bool], *, compact: bool = False) -> None:
        base = self.home if where == "user" else self.proj
        name = "settings.local.json" if where == "local" else "settings.json"
        body = {"enabledPlugins": {f"{k}@mkt": v for k, v in plugins.items()}}
        text = json.dumps(body, separators=(",", ":")) if compact else json.dumps(body, indent=2)
        (base / ".claude" / name).write_text(text)

    def run_script(self, *args: str, project_env: bool = True,
                   cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        # 環境は組み立てて渡す（実機の HOME / CLAUDE_PROJECT_DIR を継承すると本物の settings を読む）
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home)}
        if project_env:
            env["CLAUDE_PROJECT_DIR"] = str(self.proj)
        return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True,
                              env=env, cwd=str(cwd or self.root))

    def assertState(self, plugin: str, expected: str, **kw) -> None:
        res = self.run_script(plugin, **kw)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), expected, res.stderr)

    # --- 1 に倒すもの ---
    def test_enabled_in_user_settings(self):
        self.settings("user", {"bdd-spec": True})
        self.assertState("bdd-spec", "1")

    def test_enabled_only_in_project_settings(self):
        """project だけで有効化したものを取りこぼさない（旧判定の取りこぼし）."""
        self.settings("project", {"bdd-spec": True})
        self.assertState("bdd-spec", "1")

    def test_local_true_overrides_user_false(self):
        self.settings("user", {"bdd-spec": False})
        self.settings("local", {"bdd-spec": True})
        self.assertState("bdd-spec", "1")

    def test_compact_json_is_read(self):
        self.settings("user", {"bdd-spec": True}, compact=True)
        self.assertState("bdd-spec", "1")

    def init_repo(self) -> dict[str, str]:
        env = scrub()
        for args in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"]):
            subprocess.run(["git", *args], cwd=self.proj, env=env, check=True, capture_output=True)
        (self.proj / "README").write_text("x\n")
        for args in (["add", "-A"], ["commit", "-qm", "init"]):
            subprocess.run(["git", *args], cwd=self.proj, env=env, check=True, capture_output=True)
        return env

    def test_project_dir_falls_back_to_the_repo_root_from_a_subdirectory(self):
        """CLAUDE_PROJECT_DIR が無く cwd がサブディレクトリでも、リポジトリ直下の .claude を読む."""
        self.init_repo()
        self.settings("local", {"design-doc": True})
        sub = self.proj / "src" / "deep"
        sub.mkdir(parents=True)
        self.assertState("design-doc", "1", project_env=False, cwd=sub)

    def test_project_dir_falls_back_to_the_main_checkout_from_a_linked_worktree(self):
        """linked worktree には gitignore された settings.local.json が無いので、メインのチェックアウトの値を読む."""
        env = self.init_repo()
        self.settings("user", {"code-review": True})
        self.settings("local", {"code-review": False})
        wt = self.root / "wt"
        subprocess.run(["git", "worktree", "add", "-q", str(wt)], cwd=self.proj, env=env, check=True, capture_output=True)
        self.assertState("code-review", "0", project_env=False, cwd=wt)

    def test_project_dir_is_the_toplevel_when_the_git_dir_is_not_dot_git(self):
        """submodule・--separate-git-dir では共通 dir の親に .claude/ が無いので、作業ツリーの直下を読む."""
        env = scrub()
        gitdir = self.root / "elsewhere.git"
        subprocess.run(["git", "init", "-q", f"--separate-git-dir={gitdir}", str(self.proj)], env=env, check=True, capture_output=True)
        self.settings("project", {"bdd-spec": True})
        sub = self.proj / "src"
        sub.mkdir()
        self.assertState("bdd-spec", "1", project_env=False, cwd=sub)

    def test_project_dir_env_wins_over_git(self):
        """CLAUDE_PROJECT_DIR があれば git から導かない（hook など本体が渡す文脈を優先する）."""
        self.init_repo()
        other = self.root / "other"
        (other / ".claude").mkdir(parents=True)
        (other / ".claude" / "settings.json").write_text('{"enabledPlugins": {"adr-keeper@mkt": true}}')
        self.settings("project", {"adr-keeper": False})
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(other)}
        res = subprocess.run(["bash", str(SCRIPT), "adr-keeper"], capture_output=True, text=True, env=env, cwd=str(self.proj))
        self.assertEqual(res.stdout.strip(), "1", res.stderr)

    def test_project_dir_falls_back_to_cwd(self):
        """CLAUDE_PROJECT_DIR が無く（Bash ツールの既定）、git の外のときは cwd の .claude を読む."""
        self.settings("project", {"design-doc": True})
        self.assertState("design-doc", "1", project_env=False, cwd=self.proj)

    # --- 0 に倒すもの ---
    def test_no_settings_at_all(self):
        self.assertState("bdd-spec", "0")

    def test_disabled_but_installed_is_not_enabled(self):
        """`false` で無効化したプラグインを有効と誤認しない（旧判定の誤認 / GitHub issue #74 と同型）."""
        self.settings("user", {"bdd-spec": False})
        self.assertState("bdd-spec", "0")

    def test_project_false_overrides_user_true(self):
        self.settings("user", {"code-review": True})
        self.settings("project", {"code-review": False})
        self.assertState("code-review", "0")

    def test_local_false_overrides_project_true(self):
        self.settings("project", {"code-review": True})
        self.settings("local", {"code-review": False})
        self.assertState("code-review", "0")

    def test_other_plugin_with_a_shared_suffix_does_not_count(self):
        """`bdd-spec` が有効でも `spec` は有効にならない（名前の前方を `"` で固定している）."""
        self.settings("user", {"bdd-spec": True})
        self.assertState("spec", "0")

    def test_other_plugin_with_a_shared_prefix_does_not_count(self):
        self.settings("user", {"bdd-spec-extra": True})
        self.assertState("bdd-spec", "0")

    def test_missing_argument_prints_zero_and_succeeds(self):
        res = self.run_script()
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "0")
        self.assertIn("usage", res.stderr)


class InitialSelfReviewScopeTest(unittest.TestCase):
    """Phase 6 の初回 self-review に `--focus` を渡さない（GitHub issue #283）.

    `--focus` を付けると self-review は反証レイヤーと skeptic を `scope` でスキップし、triage が出す観点
    （`layer-responsibility` など）も起動しない。初回は観点選定を code-review の triage に任せ、
    `--focus` は G-V ループの再レビュー（既検証の観点の見直し）だけで使う。
    """

    SKILL = REPO / "feature-dev" / "skills" / "feature-dev" / "SKILL.md"
    REVIEW_LOOP = REPO / "feature-dev" / "references" / "review-loop.md"

    @staticmethod
    def section(text: str, start: str, end: str) -> str:
        i = text.index(start)
        return text[i:text.index(end, i)]

    def test_initial_call_does_not_pass_focus(self):
        step2 = self.section(self.SKILL.read_text(), "### Step 2: Invoke code-review:self-review",
                             "self-review 内部の動き")
        args = [l for l in step2.splitlines() if l.startswith("- ")]
        self.assertTrue(args, "Step 2 の引数の箇条書きを拾えていない")
        self.assertFalse([l for l in args if l.startswith("- `--focus")], "初回の self-review に --focus を渡している")
        self.assertTrue([l for l in args if "`--embed`" in l])

    def test_re_review_keeps_focus(self):
        """再レビューは既検証の観点の見直しなので `--focus` を使う（初回の禁止を広げすぎない）."""
        loop = self.section(self.REVIEW_LOOP.read_text(), "7. **Re-review**", "8. **Update loop state**")
        self.assertIn("`--focus <persisting issue の focus 集合>`", loop)

    def test_re_review_declares_itself(self):
        """再レビューは `--rereview` を渡し、計測で初回のレビューと分けて数えさせる（GitHub issue #296）.

        self-review 側が引数の名前を変えたらここで気づけるよう、self-review の宣言とも突き合わせる.
        """
        loop = self.section(self.REVIEW_LOOP.read_text(), "7. **Re-review**", "8. **Update loop state**")
        self.assertIn("`--rereview`", loop)
        self_review = (REPO / "code-review" / "skills" / "self-review" / "SKILL.md").read_text()
        self.assertIn("**`--rereview`（", self_review, "self-review の引数から --rereview が消えた")

    def test_initial_call_does_not_declare_a_rereview(self):
        step2 = self.section(self.SKILL.read_text(), "### Step 2: Invoke code-review:self-review",
                             "self-review 内部の動き")
        self.assertNotIn("--rereview", step2)


class SummaryReadingGuideTest(unittest.TestCase):
    """Phase 7 は独自サマリの代わりに code-review:review-guide を案内する（GitHub issue #290）.

    PR がまだ無い段階なので base モード（`--base`）で呼ぶ。PR モードは PR に push 済みのコミットしか
    見ないので、feature-dev が作った未コミットの変更が読み順から落ちる。`--base` は review-guide 側の
    引数なので、向こうで名前が変わったらここで気づけるよう、review-guide の引数の宣言と突き合わせる。
    """

    SKILL = REPO / "feature-dev" / "skills" / "feature-dev" / "SKILL.md"
    GUIDE = REPO / "code-review" / "skills" / "review-guide" / "SKILL.md"

    def phase7(self) -> str:
        text = self.SKILL.read_text()
        i = text.index("## Phase 7: Summary")
        return text[i:text.index("**Event Bus publish", i)]

    def test_invokes_review_guide_in_base_mode(self):
        self.assertIn("`code-review:review-guide` を `--base <BASE>` 付きで呼ぶ", self.phase7())

    def test_review_guide_still_accepts_base(self):
        guide = self.GUIDE.read_text()
        front = guide[:guide.index("\n---", 4)]
        self.assertIn("--base <ref>", front, "review-guide の引数から --base が消えた")

    def test_falls_back_to_plain_summary(self):
        """code-review が無効・「出さない」・呼び出しの失敗のときは従来のサマリを出す."""
        p7 = self.phase7()
        fallback = p7[p7.index("**従来のサマリ**"):]
        for cond in ("code-review が無効", "「出さない」", "呼び出しが失敗"):
            self.assertIn(cond, fallback)
        self.assertIn("Files modified", fallback)

    COMMAND = REPO / "code-review" / "commands" / "review-guide.md"
    FORMAT = REPO / "code-review" / "references" / "review-guide-format.md"
    VERDICT = "self-review 以降の変更:"

    def test_invokes_review_guide_as_walkthrough(self):
        """読み合わせとして呼ぶ。base が分からず `--base` を外す回も `--walkthrough` は落とさない."""
        call = next(l for l in self.phase7().splitlines()
                    if "`code-review:review-guide` を `--base <BASE>` 付きで呼ぶ" in l)
        with_base = next(s for s in call.split("。") if "`--base <BASE>` 付きで呼ぶ" in s)
        self.assertIn("`--walkthrough`", with_base, "base 付きの呼び出しに --walkthrough が無い")
        no_base = [s for s in call.split("。") if "`--base` を付けずに" in s]
        self.assertTrue(no_base, "base が分からない回の呼び方を拾えていない")
        self.assertIn("`--walkthrough`", no_base[0], "base が分からない回に --walkthrough を落としている")

    def test_review_guide_still_accepts_walkthrough(self):
        """同名 command があるので `Skill` で呼ぶと command 本文が返る（#219）。skill と command の両方の宣言を見る."""
        for path in (self.GUIDE, self.COMMAND):
            text = path.read_text()
            front = text[:text.index("\n---", 4)]
            self.assertIn("--walkthrough", front, f"{path.name} の引数から --walkthrough が消えた")

    def second_review_branches(self) -> dict[str, str]:
        p7 = self.phase7()
        section = p7[p7.index(f"`{self.VERDICT}` の行で分岐"):p7.index("**従来のサマリ**")]
        return {l.strip()[3:].split("`")[0]: l for l in section.splitlines() if l.strip().startswith("- `")}

    def test_branches_on_walkthrough_verdict(self):
        """締めの `self-review 以降の変更:` の 3 値で 2 回目の self-review を回すか決める.

        行の文言と値は review-guide 側の契約（review-guide-format.md「読み合わせの締め」）。向こうで言い換えたら
        ここで気づけるよう、format の正本と突き合わせる.
        """
        branches = self.second_review_branches()
        self.assertEqual(set(branches), {"あり", "なし", "不明（…）"})
        fmt = self.FORMAT.read_text()
        closing = fmt[fmt.index("## 読み合わせの締め"):fmt.index("## 誤ガイド抑制")]
        line = next((l for l in closing.splitlines() if l.startswith(self.VERDICT)), None)
        self.assertIsNotNone(line, "review-guide-format.md の締めのテンプレートから判定の行が消えた")
        for value in ("あり", "なし", "不明（"):
            self.assertIn(value, line, f"締めの判定の値から {value} が消えた")
        self.assertIn("`あり` と同じ", branches["不明（…）"], "修正を入れた回の `不明` を `あり` に倒していない")

    def test_walkthrough_changes_are_measured_with_review_snapshot(self):
        """読み合わせの間の変更だけを数える。review-guide の締めの行は直近の self-review 以降の全変更を数えるので、
        Phase 6.9 で「回さずに締める」を選んだ変更まで `あり` に入り、利用者の判断を上書きしてしまう.
        """
        p7 = self.phase7()
        call = p7.index("`code-review:review-guide` を `--base <BASE>` 付きで呼ぶ")
        save = p7.index("review-snapshot.sh\" save", call)
        self.assertLess(save, p7.index("4. **読み合わせで入った修正を self-review に通す**"),
                        "review-guide を呼ぶ直前に作業ツリーを記録していない")
        step4 = p7[p7.index("4. **読み合わせで入った修正を self-review に通す**"):p7.index("**従来のサマリ**")]
        check = step4.index("review-snapshot.sh\" check")
        self.assertLess(check, step4.index(f"`{self.VERDICT}` の行で分岐"),
                        "記録との差より先に締めの行で分岐している")
        self.assertIn("snapshot=missing", step4, "記録が取れなかった回に締めの行へ倒す条件が無い")

    def test_second_self_review_passes_base_only(self):
        """読み合わせの後の 2 回目は修正確認の再レビューではない（#300）。`--embed` / `--focus` / `--rereview` を付けない."""
        rerun = self.second_review_branches()["あり"]
        self.assertIn("`code-review:self-review`", rerun)
        self.assertIn("引数は base だけ", rerun)
        self.assertIn("省かない", rerun, "2 回目の self-review の定型レポートと publish を省かない旨が消えた（#232 / #250）")
        for flag in ("--embed", "--focus", "--rereview"):
            mentions = [s for s in rerun.split("。") if flag in s]
            self.assertTrue(mentions, f"{flag} を付けないことが書かれていない")
            for s in mentions:
                self.assertIn("付けない", s, f"2 回目の self-review に {flag} を渡している: {s}")

    NEXT = "次の一手:"
    DETERMINISTIC = "決定的な検証"

    def test_skips_second_self_review_only_on_deterministic_next_step(self):
        """`あり` でも、review-guide が挙動を変えないと判断した回は静的オラクルだけ回す（#304）.

        先頭の文言は review-guide 側の契約（review-guide-format.md「読み合わせの締め」）なので正本と突き合わせる。
        self-review を外すのは `決定的な検証` のときだけで、行が無い・別の値なら self-review に倒す.
        """
        fmt = self.FORMAT.read_text()
        closing = fmt[fmt.index("## 読み合わせの締め"):fmt.index("## 誤ガイド抑制")]
        line = next((l for l in closing.splitlines() if l.startswith(self.NEXT)), None)
        self.assertIsNotNone(line, "review-guide-format.md の締めのテンプレートから次の一手の行が消えた")
        self.assertIn(self.DETERMINISTIC, line, "締めの次の一手から決定的な検証が消えた")
        rerun = self.second_review_branches()["あり"]
        self.assertIn(f"`{self.NEXT}` が `{self.DETERMINISTIC}` で始まる", rerun)
        skip = rerun.index(self.DETERMINISTIC)
        review = rerun.index("`code-review:self-review` を呼ぶ")
        self.assertIn("Phase 5.3", rerun[skip:review], "self-review の代わりに静的オラクルを回していない")
        self.assertIn("それ以外", rerun[skip:review], "決定的な検証以外を self-review に倒していない")

    MUTATION = "変異テスト:"
    MUTATION_VALUES = ("提案する", "不要", "道具なし")

    UI_AFTER_WALKTHROUGH = "**読み合わせ以降の画面の変更を残す**"

    def step4(self) -> str:
        p7 = self.phase7()
        return p7[p7.index("4. **読み合わせで入った修正を self-review に通す**"):p7.index("**従来のサマリ**")]

    def mutation_block(self) -> str:
        """4. のうち、締めの `変異テスト:` の行で分岐する段落から、次の段落か「2 回目の self-review の後は」の手前まで.

        画面の変更の段落が消えた回も、その検出は test_flags_ui_changes_after_walkthrough に任せてここでは落ちない.
        """
        step4 = self.step4()
        start = step4.index(f"締めの `{self.MUTATION}` の行で")
        ends = [i for i in (step4.find(self.UI_AFTER_WALKTHROUGH, start),
                            step4.find("2 回目の self-review の後は", start)) if i != -1]
        return step4[start:min(ends) if ends else len(step4)]

    def test_mutation_line_is_read_before_the_next_step(self):
        """締めの `変異テスト:` の行で、次の一手の前に変異テストを提案するかを決める（GitHub issue #307）.

        値は review-guide 側の契約（review-guide-format.md「読み合わせの締め」）なので正本と突き合わせる.
        """
        fmt = self.FORMAT.read_text()
        closing = fmt[fmt.index("## 読み合わせの締め"):fmt.index("## 回し直すかの判断")]
        line = next((l for l in closing.splitlines() if l.startswith(self.MUTATION)), None)
        self.assertIsNotNone(line, f"review-guide-format.md の締めのテンプレートに `{self.MUTATION}` の行が無い")
        block = self.mutation_block()
        for value in self.MUTATION_VALUES:
            self.assertIn(value, line, f"締めの `{self.MUTATION}` の値から {value} が消えた")
            self.assertIn(f"`{value}`", block, f"{value} の分岐が無い")
        self.assertIn("承認の返信が無ければ回さない", block)
        self.assertIn("run_in_background", block)
        mentions = [s for s in block.split("。") if "AskUserQuestion" in s]
        self.assertTrue(mentions, "AskUserQuestion にしないことが書かれていない")
        for s in mentions:
            self.assertIn("しない", s, f"変異テストの承認を AskUserQuestion で取っている: {s}")
        p7 = self.phase7()
        self.assertLess(p7.index("締めにこの行が無い"), p7.index(f"締めの `{self.MUTATION}` の行で"))

    def test_mutation_runs_regardless_of_snapshot(self):
        """snapshot が無い回だけの分岐（`self-review 以降の変更:` の箇条）に入れない。読み合わせた回はすべて通る."""
        block = self.mutation_block()
        self.assertIn("`review-snapshot.sh check` の結果によらず", block)
        head = next(l for l in self.phase7().splitlines() if f"締めの `{self.MUTATION}` の行で" in l)
        self.assertFalse(head.lstrip().startswith("- "), f"snapshot の分岐の箇条の中に入っている: {head}")
        for line in block.splitlines()[1:]:
            self.assertFalse(line.strip().startswith("- `"),
                             f"下位の箇条を「- `」で書き出すと 2 回目の self-review の分岐に数えられる: {line}")

    def test_added_tests_do_not_rerun_self_review(self):
        block = self.mutation_block()
        self.assertIn("足したテストを走らせ", block)
        self.assertIn("self-review は回し直さない", block)

    MUTATION_OUTCOMES = ("生存 N 件", "一部未実行", "未計測", "判定不能")

    def test_mutation_reports_four_outcomes(self):
        """結果は 4 区分で書く。exit 0 は、上限・タイムアウトで一部しか回していない回と未計測の回でも返る.

        3 区分（生存 / 未計測 / 判定不能）だと、25 個だけ回して全部殺した回が「生存 0」と報告される.
        """
        block = self.mutation_block()
        for label in self.MUTATION_OUTCOMES:
            self.assertIn(f"`{label}`（", block, f"変異テストの結果に {label} の区分が無い")
        partial = block[block.index("`一部未実行`（"):block.index("`未計測`（")]
        self.assertIn("「生存 0」と書かず", partial)
        self.assertIn("実行した数と未実行の数", partial)
        aborted = block[block.index("`判定不能`（"):block.index("回す前と後の")]
        self.assertIn("stderr に中断の FATAL", aborted, "途中で止まった exit 1 を判定不能に入れていない")
        self.assertIn("変異が当たったまま", aborted)
        self.assertIn("次の一手へ進まない", aborted, "変異が残ったツリーのままコミットへ進みうる")

    def test_mutation_summary_is_pinned_to_the_canonical(self):
        """Phase 7 の変異テストの分岐は review-guide-format.md「変異テストの提案」の要約。正本が変わったら pin の検査で気づく."""
        self.assertRegex(
            self.SKILL.read_text(),
            r"<!-- SSOT: code-review/references/review-guide-format\.md#変異テストの提案 @[0-9a-f]{8} -->")

    def test_mutation_reports_tool_output(self):
        """道具の出力ファイルをコミットに混ぜない."""
        block = self.mutation_block()
        self.assertIn("`git status --porcelain` の出力を控えてから", block)
        self.assertIn("回す前と後の `git status --porcelain` を突き合わせ", block)
        self.assertIn("コミットに混ぜない", block)

    def test_flags_ui_changes_after_walkthrough(self):
        """読み合わせ以降の修正は Phase 5.5 を通らないので、画面のファイルに触れたらその事実を残す（#306）.

        `決定的な検証` の経路は 2 回目の self-review を回さないので、条件を「2 回目の self-review の後は」の
        箇条に置くと掛からない。分岐の箇条の外の段落にあり、両方の経路を名指ししていることを見る.
        """
        step4 = self.step4()
        para = next((l for l in step4.splitlines() if self.UI_AFTER_WALKTHROUGH in l), None)
        self.assertIsNotNone(para, "読み合わせ以降の画面の変更を残す段落が無い")
        self.assertFalse(para.lstrip().startswith("- "), f"分岐の箇条の中に入っている: {para}")
        self.assertIn("読み合わせ後の変更は動作確認を通していない", para)
        for path in ("2 回目の self-review", f"`{self.DETERMINISTIC}`"):
            self.assertIn(path, para, f"{path} の経路に条件が掛かっていない")
        self.assertLess(step4.index("- 行が無い（"), step4.index(self.UI_AFTER_WALKTHROUGH),
                        "読み合わせ以降の画面の変更の段落が、変異テストの分岐の後に無い")
        after = next(l for l in step4.splitlines() if "2 回目の self-review の後は" in l)
        self.assertNotIn("動作確認を通していない", after,
                         "条件が 2 回目の self-review の経路の箇条に残っている")


UI_VERIFY = REPO / "dev-workflow" / "skills" / "ui-verify" / "SKILL.md"
UI_VERIFY_COMMAND = REPO / "dev-workflow" / "commands" / "ui-verify.md"
UI_PATHS = REPO / "dev-workflow" / "scripts" / "lib" / "ui-paths.sh"


class RuntimeSmokeAndUiVerifyTest(unittest.TestCase):
    """Phase 5.5 は聞かずに `dev-workflow:ui-verify` を `--caller` で呼び、`UI_VERIFY_*` の行で分岐する（GitHub issue #306）.

    `--caller` と `UI_VERIFY_RESULT=` の値は ui-verify 側の契約なので、向こうの宣言と突き合わせる.
    """

    SKILL = REPO / "feature-dev" / "skills" / "feature-dev" / "SKILL.md"
    SMOKE = REPO / "feature-dev" / "references" / "smoke-test.md"

    def phase55(self) -> str:
        text = self.SKILL.read_text()
        i = text.index("## Phase 5.5")
        return text[i:text.index("## Phase 6", i)]

    def step(self, n: int) -> str:
        p = self.phase55()
        i = p.index(f"### Step {n}:")
        nxt = p.find("### Step", i + 1)
        return p[i:nxt if nxt != -1 else len(p)]

    @staticmethod
    def result_values() -> list[str]:
        line = next((l.strip() for l in UI_VERIFY.read_text().splitlines()
                     if l.strip().startswith("UI_VERIFY_RESULT=") and "|" in l), None)
        if line is None:
            raise AssertionError("ui-verify の SKILL.md から `UI_VERIFY_RESULT=` の定義行が消えた")
        return [v.strip(" <>`") for v in line.split("=", 1)[1].split("|")]

    def test_calls_ui_verify_with_caller(self):
        s = self.step(3)
        self.assertIn("`dev-workflow:ui-verify` を `verify --caller=feature-dev` で呼ぶ", s)

    def test_ui_verify_still_declares_caller(self):
        """同名 command があるので `Skill` で呼ぶと command 本文が返る（#219）。SKILL.md と command の両方の `引数:` を見る."""
        for path in (UI_VERIFY, UI_VERIFY_COMMAND):
            m = re.search(r"引数: ([^\n\"]+)", path.read_text())
            self.assertIsNotNone(m, f"{path.name} に `引数:` が無い")
            self.assertIn("--caller", m.group(1), f"{path.name} の引数から --caller が消えた")
        caller_lines = [l for l in UI_VERIFY.read_text().splitlines() if "--caller" in l]
        self.assertTrue([l for l in caller_lines if "feature-dev" in l],
                        "ui-verify の --caller の値に feature-dev が無い")

    def test_required_passes_require(self):
        require = next((l for l in self.step(3).splitlines() if "`--require=" in l), None)
        self.assertIsNotNone(require, "REQUIRED の回に --require を渡していない")
        self.assertIn("REQUIRED のときだけ", require)
        self.assertIn("当たった pattern を保持し、Step 3 の `--require` に渡す", self.phase55())

    def test_does_not_ask_whether_to_run(self):
        """以前は既定 skip で聞いていたため、画面を触る変更でもほとんど走らなかった.

        Phase 5.5 のどこで聞いても同じことになるので、Step 2 に限らず全体を見る。ui-verify 内の確認
        （dev server の起動許可など）は ui-verify 側の手順で出るので、Phase 5.5 の本文には要らない.
        """
        self.assertNotIn("AskUserQuestion", self.phase55())
        self.assertNotIn("smoke test を実行しますか", self.phase55())

    def test_optional_also_calls_ui_verify(self):
        """runtime の pattern に当たらない OPTIONAL の回も呼ぶ。UI に影響するかは ui-verify が判定する."""
        line = next((l for l in self.step(2).splitlines() if l.startswith("- `DEV_WORKFLOW=1` →")), None)
        self.assertIsNotNone(line, "Step 2 に `DEV_WORKFLOW=1` の分岐が無い")
        self.assertIn("OPTIONAL でも", line, f"OPTIONAL の回に ui-verify を呼んでいない: {line}")
        self.assertIn("ui-verify を呼ぶ", line)

    def test_fail_waits_for_the_user(self):
        """`fail` を known issue に倒して素通りしない。直すか承知で進むかは利用者が決める."""
        s = self.step(4)
        fail = s[s.index("- `fail`"):s.index("\n- `", s.index("- `fail`"))]
        self.assertIn("利用者が決めるまで", fail)
        self.assertIn("Phase 6 へ進まない", fail)

    def test_checks_dev_workflow_enabled(self):
        self.assertIn('plugin-enabled.sh" dev-workflow', self.step(2))

    def test_branches_on_every_result_value(self):
        values = self.result_values()
        self.assertEqual(set(values), {"pass", "fail", "blocked", "skipped"}, values)
        s = self.step(4)
        for value in values:
            self.assertRegex(s, rf"(?m)^- `{value}`", f"Step 4 に {value} の分岐が無い")

    def test_keys_used_are_declared_by_ui_verify(self):
        declared = set(re.findall(r"(?m)^\s*(UI_VERIFY_[A-Z]+)=", UI_VERIFY.read_text()))
        used = set(re.findall(r"(UI_VERIFY_[A-Z]+)", self.SKILL.read_text()))
        self.assertTrue(used, "Phase 5.5 が `UI_VERIFY_*` の行を読んでいない")
        self.assertLessEqual(used, declared, f"ui-verify が出さないキーを読んでいる: {used - declared}")

    def test_falls_back_to_manual_check(self):
        manual = self.step(3)[self.step(3).index("**手動手順**"):]
        for cond in ("`DEV_WORKFLOW=0`", "`UI_VERIFY_RESULT=` の行が無い", "`UI_VERIFY_BROWSER=none`"):
            self.assertIn(cond, manual)
        self.assertIn("manual check pending", manual)
        self.assertIn("hard fail しない", manual)

    def test_blocked_without_browser_is_not_judged_again(self):
        """blocked かつ BROWSER=none は ui-verify が画面に影響すると判定した回。呼び出し元の散文で覆さない（軽量フローと同じ）."""
        manual = self.step(3)[self.step(3).index("**手動手順**"):]
        ask = next((l for l in manual.splitlines() if l.strip().startswith("- 手動確認を頼む回")), None)
        self.assertIsNotNone(ask, "手動確認を頼む回の箇条が無い")
        head = ask[:ask.index("それ以外は")]
        self.assertIn("`UI_VERIFY_BROWSER=none`", head)
        self.assertIn("判定し直さない", head)

    def test_unselected_is_not_sent_to_manual_check(self):
        """基盤を選ぶ前に止まった blocked（dev server の起動を断られた等）で、手動確認を頼み直さない."""
        key = "`UI_VERIFY_BROWSER=unselected`"
        blocked = next((l for l in self.step(4).splitlines() if l.startswith("- `blocked`")), None)
        self.assertIsNotNone(blocked, "Step 4 に blocked の分岐が無い")
        self.assertIn(key, blocked)
        self.assertIn("頼み直さない", blocked[blocked.index(key):])
        conds = self.step(3)[self.step(3).index("**手動手順**"):].splitlines()[0]
        self.assertIn("`unselected` は入れない", conds, f"手動手順の条件に unselected を除く旨が無い: {conds}")

    def test_browser_values_used_are_declared_by_ui_verify(self):
        """分岐に使う `UI_VERIFY_BROWSER=` の値は、ui-verify が出す値に限る."""
        line = next((l.strip() for l in UI_VERIFY.read_text().splitlines()
                     if l.strip().startswith("UI_VERIFY_BROWSER=") and "|" in l), None)
        self.assertIsNotNone(line, "ui-verify の SKILL.md から `UI_VERIFY_BROWSER=` の定義行が消えた")
        declared = {v.strip(" <>`") for v in line.split("=", 1)[1].split("|")}
        used = set(re.findall(r"UI_VERIFY_BROWSER=([a-z-]+)", self.SKILL.read_text()))
        self.assertEqual(used, {"none", "unselected"}, used)
        self.assertLessEqual(used, declared, f"ui-verify が出さない値を読んでいる: {used - declared}")

    def test_targets_are_passed_regardless_of_required(self):
        """architect の smoke target は OPTIONAL の回にも渡す（ui-verify は `--targets` があれば早期終了しない）."""
        line = next((l for l in self.step(3).splitlines() if "`--targets=" in l), None)
        self.assertIsNotNone(line, "Step 3 に --targets が無い")
        self.assertIn("REQUIRED でも OPTIONAL でも必ず渡す", line)

    def test_screenshot_default_matches_ui_verify(self):
        """`--screenshot` を省いたときの意味は ui-verify の定義に合わせる（省いても撮らないとは限らない）."""
        line = next((l for l in self.step(3).splitlines() if "`--screenshot=need`" in l), None)
        self.assertIsNotNone(line, "Step 3 に --screenshot が無い")
        self.assertIn("省くと ui-verify が依頼・Issue から決める", line)
        decl = next((l for l in UI_VERIFY.read_text().splitlines() if l.startswith("| `--screenshot=")), None)
        self.assertIsNotNone(decl, "ui-verify の引数の表から --screenshot が消えた")
        self.assertIn("省くと依頼から決める", decl)

    def test_ui_file_definition_matches_ui_paths(self):
        """手動手順と Phase 7 の申し送りが見る「画面のファイル」は ui-paths.sh の式に揃える.

        旧い散文（コンポーネント・スタイル・テンプレート）は hooks/ stores/ 配下の .ts を数えず、
        ui-verify が画面の変更と判定したものを呼び出し元が覆していた.
        """
        text = self.SKILL.read_text()
        step3 = self.step(3)
        para = step3[step3.index("画面のファイルは、ui-verify の事前判定が"):]
        para = para[:para.index("\n")]
        line = next((l for l in UI_PATHS.read_text().splitlines() if l.startswith("UI_SCRIPT_ERE=")), None)
        self.assertIsNotNone(line, "ui-paths.sh から `UI_SCRIPT_ERE=` が消えた")
        groups = re.findall(r"\(([^()]*)\)", line)
        dirs = [d.replace("s?", "(s)") for d in groups[1].split("|")]
        self.assertGreater(len(dirs), 5, dirs)
        for d in dirs:
            self.assertIn(f"`{d}/`", para, f"画面の層のディレクトリ {d}/ が定義に無い")
        for e in groups[-1].split("|"):
            self.assertIn(f"`.{e}`", para, f"拡張子 .{e} が定義に無い")
        self.assertNotIn("コンポーネント・スタイル・テンプレート", text, "旧い散文の定義が残っている")
        p7 = text[text.index("## Phase 7: Summary"):]
        self.assertEqual(p7.count("画面のファイル（Phase 5.5 Step 3 の定義）"), 2,
                         "Phase 7 の申し送りと読み合わせ以降の段落が Step 3 の定義を指していない")

    def test_phase7_carries_the_reason(self):
        text = self.SKILL.read_text()
        p7 = text[text.index("## Phase 7: Summary"):]
        handoff = p7[p7.index("2. **申し送り**"):p7.index("3. **読み合わせの案内**")]
        item = next((l for l in handoff.splitlines() if "**動作確認** (Phase 5.5)" in l), None)
        self.assertIsNotNone(item, "申し送りに動作確認の項目が無い")
        self.assertIn("UI_VERIFY_REASON", item)
        self.assertIn("UI_VERIFY_UNCOVERED", item)
        self.assertIn("動作確認を通していない", item, "Phase 5.5 の後の画面の変更を残していない")

    def test_runtime_patterns_are_kept(self):
        """REQUIRED / OPTIONAL の接頭辞と 4 パターンの決定的な判定は残す（`--require` に渡す根拠）."""
        smoke = self.SMOKE.read_text()
        step1 = smoke[smoke.index("## Step 1"):]
        for prefix in ('echo "REQUIRED:', 'echo "OPTIONAL:'):
            self.assertIn(prefix, step1)
        for n in range(1, 5):
            self.assertIn(f"# Pattern {n}:", step1)


class SmokeDetectionTest(unittest.TestCase):
    """smoke-test.md Step 1 の判定を、doc の bash をそのまま取り出して使い捨てリポジトリで回す.

    Phase 5 は `git add` しないので、新しく作ったファイルは `git diff HEAD` に出ない。未追跡の新規ファイルの
    名前と中身も判定に入ることを見る（入らないと、新規ファイルで足した DB client が OPTIONAL に落ち、
    ui-verify も UI 変更なしで skipped を返す）。`/tmp/` の固定パスは一時 dir に差し替える
    （同じ機で動いている feature-dev の判定ファイルを上書きしない）.
    """

    SMOKE = REPO / "feature-dev" / "references" / "smoke-test.md"

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.repo = root / "repo"
        self.out = root / "out"
        self.repo.mkdir()
        self.out.mkdir()
        self.env = scrub()
        for args in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"]):
            self.git(*args)
        self.write(".gitignore", "gen/\n")
        self.write("README", "x\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")

    def git(self, *args: str) -> str:
        res = subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout

    def write(self, rel: str, text: str) -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def script(self) -> str:
        smoke = self.SMOKE.read_text(encoding="utf-8")
        m = re.search(r"```bash\n(.*?)```", smoke[smoke.index("## Step 1"):], re.S)
        self.assertIsNotNone(m, "smoke-test.md の Step 1 に bash のブロックが無い")
        body = m.group(1)
        self.assertIn("/tmp/feature-dev-diff.txt", body, "前提: 判定の入力を /tmp に書く")
        return body.replace("/tmp/", f"{self.out}/")

    def detect(self, shell: tuple[str, ...] = ("bash",), cwd: Path | None = None) -> str:
        res = subprocess.run([*shell, "-c", self.script()], cwd=cwd or self.repo, capture_output=True,
                             text=True, env=self.env, timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout

    # --- REQUIRED に倒すもの ---
    def test_untracked_new_file_content_is_matched(self):
        self.write("lib/db.ts", 'import { PrismaClient } from "@prisma/client"\nexport const db = new PrismaClient()\n')
        out = self.detect()
        self.assertTrue(out.startswith("REQUIRED:"), out)
        self.assertIn("DB client / ORM 初期化変更", out)

    def test_untracked_new_route_name_is_matched(self):
        self.write("pages/settings.tsx", "export default function Page() { return null }\n")
        self.assertIn("新規 route の追加・変更", self.detect())

    def test_untracked_file_with_a_space_in_its_name(self):
        self.write("my lib/env config.ts", "export const url = process.env.DB_URL\n")
        self.assertIn("環境変数依存の追加・変更", self.detect())

    def test_run_from_a_subdirectory_sees_the_whole_tree(self):
        """ls-files は cwd 配下しか出さないので、toplevel から回してサブディレクトリの外の未追跡の中身も読む."""
        self.write("lib/db.ts", "export const db = new PrismaClient()\n")
        (self.repo / "docs").mkdir()
        self.assertIn("DB client / ORM 初期化変更", self.detect(cwd=self.repo / "docs"))

    def test_run_from_a_subdirectory_sees_untracked_names_outside_it(self):
        """名前の列挙も toplevel から回す。中身はパターンに当たらないので、名前の照合（Pattern 4）だけで鳴る.

        上の中身の側だけを見るテストでは、名前の側の `-C` を外しても緑のままだった.
        """
        self.write("pages/settings.tsx", "export default function Page() { return null }\n")
        (self.repo / "docs").mkdir()
        self.assertIn("新規 route の追加・変更", self.detect(cwd=self.repo / "docs"))

    def test_tracked_change_is_still_matched(self):
        self.write("README", "x\napp.use(handler)\n")
        self.assertIn("middleware / proxy / lazy-init 変更", self.detect())

    def test_runs_the_same_under_zsh(self):
        """Bash tool のシェルは利用者の既定（macOS では zsh）なので、zsh でも同じ判定になる."""
        if shutil.which("zsh") is None:
            self.skipTest("zsh が無い")
        self.write("lib/db.ts", "export const db = new PrismaClient()\n")
        out = self.detect(("zsh", "-f"))  # -f: 利用者の .zshenv を読ませない
        self.assertTrue(out.startswith("REQUIRED:"), out)
        self.assertEqual(out, self.detect())

    # --- OPTIONAL のまま黙るもの ---
    def test_clean_tree_stays_optional(self):
        self.assertTrue(self.detect().startswith("OPTIONAL:"))

    def test_untracked_file_without_patterns_stays_optional(self):
        self.write("lib/add.ts", "export const add = (a: number, b: number) => a + b\n")
        self.assertTrue(self.detect().startswith("OPTIONAL:"))

    def test_ignored_file_is_not_read(self):
        self.write("gen/client.ts", "export const db = new PrismaClient()\n")
        self.assertTrue(self.detect().startswith("OPTIONAL:"))

    def test_index_and_tree_are_untouched(self):
        self.write("lib/db.ts", "export const db = new PrismaClient()\n")
        before = self.git("status", "--porcelain")
        self.detect()
        self.assertEqual(self.git("status", "--porcelain"), before)


class PostReviewChangeTest(unittest.TestCase):
    """Phase 6.9 の推奨は差の中身で決める（GitHub issue #304）。差があるだけで self-review を推奨に固定しない."""

    SKILL = REPO / "feature-dev" / "skills" / "feature-dev" / "SKILL.md"

    def phase69(self) -> str:
        text = self.SKILL.read_text()
        i = text.index("## Phase 6.9")
        return text[i:text.index("## Phase 7", i)]

    def test_reads_the_diff_before_asking(self):
        p = self.phase69()
        self.assertLess(p.index('review-snapshot.sh" diff'), p.index("`AskUserQuestion`"),
                        "中身を読む前に推奨を決めて聞いている")

    def test_recommendation_is_not_fixed_to_self_review(self):
        p = self.phase69()
        self.assertNotIn("回す（推奨）", p, "self-review を推奨に固定している")
        for option in ("「self-review をもう一度回す」", "「静的オラクルだけ回す」", "「回さずに締める」"):
            self.assertIn(option, p)


SNAPSHOT = REPO / "feature-dev" / "scripts" / "review-snapshot.sh"


class ReviewSnapshotTest(unittest.TestCase):
    """`review-snapshot.sh save|check` — レビュー後に入った変更を出す（GitHub issue #276）.

    **ref も index も動かさない**こと、未追跡の新規ファイルを数えること、.gitignore を数えないことを見る。
    """

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.env = scrub()
        for args in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"]):
            self.git(*args)
        (self.root / ".gitignore").write_text("build/\n", encoding="utf-8")
        (self.root / "spec.md").write_text("rule 1\nrule 2\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")

    def git(self, *args: str) -> str:
        res = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout

    def run_snap(self, mode: str, cwd: Path | None = None) -> dict:
        res = subprocess.run(["bash", str(SNAPSHOT), mode], cwd=cwd or self.root, capture_output=True,
                             text=True, env=self.env, timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        out = {"rows": []}
        for line in res.stdout.splitlines():
            if "\t" in line:
                out["rows"].append(line.split("\t"))
            else:
                k, _, v = line.partition("=")
                out[k] = v
        return out

    def test_unchanged_after_save(self):
        (self.root / "spec.md").write_text("rule 1\nrule 2 edited\n", encoding="utf-8")  # レビュー前の未コミット変更
        self.run_snap("save")
        got = self.run_snap("check")
        self.assertEqual((got["changed_files"], got["changed_lines"]), ("0", "0"))

    def test_edits_and_new_files_after_save_are_reported(self):
        self.run_snap("save")
        (self.root / "spec.md").write_text("rule 1\nrule 2 changed\nrule 3\n", encoding="utf-8")
        (self.root / "new.md").write_text("added\n", encoding="utf-8")
        got = self.run_snap("check")
        self.assertEqual(got["changed_files"], "2")
        self.assertEqual(got["changed_lines"], "4")  # spec.md +2 -1 / new.md +1
        self.assertEqual(sorted(r[2] for r in got["rows"]), ["new.md", "spec.md"])

    def test_deleted_file_is_reported(self):
        self.run_snap("save")
        (self.root / "spec.md").unlink()
        self.assertEqual(self.run_snap("check")["changed_files"], "1")

    def test_ignored_files_are_not_counted(self):
        self.run_snap("save")
        (self.root / "build").mkdir()
        (self.root / "build" / "out.txt").write_text("x\n", encoding="utf-8")
        self.assertEqual(self.run_snap("check")["changed_files"], "0")

    def test_refs_and_index_are_untouched(self):
        (self.root / "spec.md").write_text("unstaged\n", encoding="utf-8")
        (self.root / "untracked.md").write_text("u\n", encoding="utf-8")
        before = (self.git("rev-parse", "HEAD"), self.git("status", "--porcelain"), self.git("stash", "list"))
        self.run_snap("save")
        self.run_snap("check")
        self.assertEqual((self.git("rev-parse", "HEAD"), self.git("status", "--porcelain"),
                          self.git("stash", "list")), before)

    def test_commit_after_save_without_content_change_is_not_a_change(self):
        """レビュー後にコミットしただけなら中身は変わっていない（tree で比べる）."""
        (self.root / "spec.md").write_text("reviewed\n", encoding="utf-8")
        self.run_snap("save")
        self.git("commit", "-qam", "commit reviewed state")
        self.assertEqual(self.run_snap("check")["changed_files"], "0")

    def test_check_from_a_subdirectory_sees_the_whole_tree(self):
        (self.root / "docs").mkdir()
        self.run_snap("save", cwd=self.root / "docs")
        (self.root / "spec.md").write_text("changed\n", encoding="utf-8")
        self.assertEqual(self.run_snap("check", cwd=self.root / "docs")["changed_files"], "1")

    def test_missing_snapshot(self):
        self.assertEqual(self.run_snap("check")["snapshot"], "missing")

    def run_diff(self) -> str:
        res = subprocess.run(["bash", str(SNAPSHOT), "diff"], cwd=self.root, capture_output=True,
                             text=True, env=self.env, timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout

    def test_diff_shows_the_content_changed_after_save(self):
        """Phase 6.9 は中身で回し直すかを決める（#304）。未追跡の新規ファイルも入る（`git diff <tree>` では落ちる）."""
        (self.root / "spec.md").write_text("rule 1\nrule 2 before review\n", encoding="utf-8")  # レビュー前の変更は出さない
        self.run_snap("save")
        (self.root / "spec.md").write_text("rule 1\nrule 2 after review\n", encoding="utf-8")
        (self.root / "new.md").write_text("added after review\n", encoding="utf-8")
        out = self.run_diff()
        self.assertIn("-rule 2 before review", out)
        self.assertIn("+rule 2 after review", out)
        self.assertIn("+added after review", out)
        self.assertNotIn("snapshot=", out, "patch に check の集計行が混ざっている")

    def test_diff_is_empty_when_nothing_changed(self):
        self.run_snap("save")
        self.assertEqual(self.run_diff(), "")

    def test_diff_without_snapshot_reports_missing(self):
        self.assertEqual(self.run_diff().strip(), "snapshot=missing")

    def test_diff_leaves_refs_and_index_untouched(self):
        self.run_snap("save")
        (self.root / "spec.md").write_text("unstaged\n", encoding="utf-8")
        (self.root / "untracked.md").write_text("u\n", encoding="utf-8")
        before = (self.git("rev-parse", "HEAD"), self.git("status", "--porcelain"))
        self.run_diff()
        self.assertEqual((self.git("rev-parse", "HEAD"), self.git("status", "--porcelain")), before)

    def test_not_a_git_repo(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.run_snap("check", cwd=Path(d))["snapshot"], "unavailable")

    def test_snapshots_are_per_worktree(self):
        wt = self.root.parent / (self.root.name + "-wt")
        self.git("worktree", "add", "-q", "-b", "other", str(wt))
        self.addCleanup(lambda: subprocess.run(["git", "worktree", "remove", "--force", str(wt)],
                                               cwd=self.root, capture_output=True, env=self.env))
        self.run_snap("save")
        self.assertEqual(self.run_snap("check", cwd=wt)["snapshot"], "missing")


if __name__ == "__main__":
    unittest.main()
