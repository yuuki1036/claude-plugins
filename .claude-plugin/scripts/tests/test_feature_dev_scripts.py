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
    """Phase 6 の self-review に `--focus` を渡さない（GitHub issue #283 / #313）.

    `--focus` を付けると self-review は反証レイヤーと skeptic を `scope` でスキップし、triage が出す観点
    （`layer-responsibility` など）も起動しない。初回は観点選定を code-review の triage に任せ、G-V ループの
    再レビューは `--since` / `--prior-findings` で範囲を delta に絞る（観点と体数は triage が delta で選び直す）。
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

    def test_re_review_narrows_by_since_not_focus(self):
        """再レビューは `--since` / `--prior-findings` で範囲を絞り、`--focus` を付けない（GitHub issue #313）.

        self-review 側が引数の名前を変えたらここで気づけるよう、self-review の宣言とも突き合わせる.
        """
        loop = self.section(self.REVIEW_LOOP.read_text(), "5. **Re-review**", "6. Return to step 1")
        self.assertIn("`--since=<since>`", loop)
        self.assertIn("`--prior-findings=<prior_findings>`", loop)
        self.assertIn("`since=unavailable`", loop, "since を用意できない回の扱いが無い")
        self.assertNotIn("`--focus <", loop)
        self.assertNotIn("`--exclude <", loop)
        self.assertIn("`**範囲**:`", loop, "旧版の code-review を見分ける手順が無い")
        self_review = (REPO / "code-review" / "skills" / "self-review" / "SKILL.md").read_text()
        self.assertIn("**`--since=<tree>` / `--prior-findings=<path>`（", self_review, "self-review の引数から --since が消えた")
        self.assertIn("**範囲**:", self_review, "self-review のレポートに範囲の行が無い")

    def test_re_review_declares_itself(self):
        """再レビューは `--rereview` を渡し、計測で初回のレビューと分けて数えさせる（GitHub issue #296）.

        self-review 側が引数の名前を変えたらここで気づけるよう、self-review の宣言とも突き合わせる.
        """
        loop = self.section(self.REVIEW_LOOP.read_text(), "5. **Re-review**", "6. Return to step 1")
        self.assertIn("`--rereview`", loop)
        self_review = (REPO / "code-review" / "skills" / "self-review" / "SKILL.md").read_text()
        self.assertIn("**`--rereview`（", self_review, "self-review の引数から --rereview が消えた")

    def test_initial_call_does_not_declare_a_rereview(self):
        step2 = self.section(self.SKILL.read_text(), "### Step 2: Invoke code-review:self-review",
                             "self-review 内部の動き")
        self.assertNotIn("--rereview", step2)


class ScopeCutoffKeepsGatesTest(unittest.TestCase):
    """適用範囲で足切りした回も、実装の後の検証（Phase 5.3 以降）を通す（GitHub issue #319）.

    以前は足切りの節が「通常の実装に移る」で終わっていて、静的オラクルと self-review を一度も通らないまま
    コミットの確認に入った。承認した方針を実装中に替えたときに止まる規定も無かった。
    """

    SKILL = REPO / "feature-dev" / "skills" / "feature-dev" / "SKILL.md"

    def section(self, start: str, end: str) -> str:
        text = self.SKILL.read_text()
        i = text.index(start)
        return text[i:text.index(end, i)]

    def cutoff(self) -> str:
        return self.section("## 適用範囲", "## Core Principles")

    def test_cutoff_runs_every_gate_after_implementation(self):
        """後に通す phase の列は 1 段落で切り出す（停止点・TodoWrite の行にも同じ phase 番号が出るので、節全体では落としても通る）."""
        self.assertNotIn("通常の実装に移る", self.cutoff())
        gates = self.section("**足切りで飛ばすのは設計までで、検証は飛ばさない**", "**足切りしたときの停止点**")
        self.assertIn("Phase 5.3（静的オラクル）→ 5.5（動作確認）→ 6（self-review と G-V ループ）→ "
                      "6.7（コメント精査）→ 6.9（レビュー後の変更の確認）→ 7（申し送りと読み合わせ）", gates)

    def test_cutoff_tracks_remaining_gates_in_todos(self):
        self.assertIn("TodoWrite へ「実装 / Phase 5.3 / 5.5 / 6 / 6.7 / 6.9 / 7」を積む", self.cutoff())

    def test_cutoff_enters_normal_mode_then_static_oracle(self):
        modes = self.section("### Mode Detection", "### Normal Mode")
        self.assertIn("適用範囲で足切りした回は停止点の返信で入る", modes)
        self.assertIn("終えたら Phase 5.3 へ進む", modes)

    def test_stop_point_states_the_cutoff_and_offers_full_flow(self):
        stop = self.section("**足切りしたときの停止点**", "> 🔀")
        self.assertIn("足切りしたこと", stop)
        self.assertIn("8 phase で回すなら返信でそう書いてください", stop)

    def test_changing_the_approved_plan_stops_first(self):
        """方針を替える前に止まる規定は Normal Mode の 4. に 1 か所だけ置き、適用範囲と Fix Mode はそこを指す."""
        normal = self.section("### Normal Mode", "### Fix Mode")
        rule = normal[normal.index("4. **承認した方針を実装中に変えるときは、書き換える前に止まる**"):normal.index("\n5. ")]
        self.assertIn("足切りした回の停止点の承認", rule)
        self.assertIn("返信を待ってから書き換える", rule)
        self.assertIn("Normal Mode の 4. に従って止まる", self.cutoff())
        fix = self.section("### Fix Mode", "## Phase 5.3")
        self.assertIn("足切りした回は architect を起動しない", fix)

    def test_summary_reports_the_cutoff(self):
        handoff = self.section("2. **申し送り**", "3. **読み合わせの案内**")
        self.assertIn("**足切り** (適用範囲)", handoff)


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
        """読み合わせの後の 2 回目は修正確認の再レビューではない（#300 / #313）。`--embed` / `--focus` / `--rereview` / `--since` を付けない."""
        rerun = self.second_review_branches()["あり"]
        self.assertIn("`code-review:self-review`", rerun)
        self.assertIn("引数は base だけ", rerun)
        self.assertIn("省かない", rerun, "2 回目の self-review の定型レポートと publish を省かない旨が消えた（#232 / #250）")
        for flag in ("--embed", "--focus", "--rereview", "--since", "--prior-findings"):
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

    def test_rerun_narrows_by_since_and_keeps_untracked_as_unreviewed(self):
        """6.9 の回し直しは記録した tree を `--since` で渡し、未追跡の変更は Phase 7 に残す（GitHub issue #313）."""
        p = self.phase69()
        self.assertIn("`--since=<check が出した snapshot>`", p)
        self.assertNotIn("差分だけを self-review に通すことはできない", p)
        self.assertIn("`untracked_files=`", p)
        skill = self.SKILL.read_text()
        p7 = skill[skill.index("## Phase 7"):]
        self.assertIn("未追跡 N ファイル（self-review の対象外）", p7)

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

    def test_untracked_changes_are_counted_apart(self):
        """未追跡の変更は self-review の diff に入らないので別に数える（Phase 6.9 が Phase 7 に残す / #313）."""
        self.run_snap("save")
        (self.root / "spec.md").write_text("rule 1\nrule 2 changed\n", encoding="utf-8")
        self.assertEqual(self.run_snap("check")["untracked_files"], "0", "追跡済みの編集を未追跡に数えた")
        (self.root / "new.md").write_text("added\n", encoding="utf-8")
        got = self.run_snap("check")
        self.assertEqual((got["changed_files"], got["untracked_files"]), ("2", "1"))

    def test_a_same_size_rewrite_with_the_same_mtime_is_seen(self):
        """index の種を mtime ごと写さないと、git の racy の判定が効かず、同じ秒に同じサイズへ書き換えた
        ファイルを「変わっていない」と読む（G-V ループの行の写像のテストが、ときどき落ちていた）.

        秒が揃うかは運なので、ファイルと index の mtime を揃え、ctime を比べない設定にして確実に作る.
        """
        self.git("config", "core.trustctime", "false")
        spec = self.root / "spec.md"
        before = os.stat(spec)
        self.run_snap("save")
        spec.write_text("rule 1\nrule X\n", encoding="utf-8")  # 同じサイズ
        os.utime(spec, ns=(before.st_atime_ns, before.st_mtime_ns))
        os.utime(self.root / ".git" / "index", ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(self.run_snap("check")["changed_files"], "1")

    def test_untracked_files_is_zero_without_changes(self):
        (self.root / "draft.md").write_text("untracked before save\n", encoding="utf-8")
        self.run_snap("save")
        self.assertEqual(self.run_snap("check")["untracked_files"], "0", "保存前からある未追跡を変更に数えた")

    def test_a_rename_is_not_counted_as_all_untracked(self):
        """`mv` した回は、追跡済みファイルの削除（self-review の diff に入る）と未追跡の新しい名前の 2 つ。
        rename を 1 つに数えると `changed_files == untracked_files` になり、6.9 が「全部未追跡」と読む."""
        self.run_snap("save")
        (self.root / "spec.md").rename(self.root / "renamed.md")
        got = self.run_snap("check")
        self.assertEqual((got["changed_files"], got["untracked_files"]), ("2", "1"))

    def test_untracked_before_save_is_not_counted_next_to_a_tracked_edit(self):
        """変更が 0 件の回は突き合わせまで届かない。追跡済みの編集と並べて、保存前からある未追跡を数えないことを見る."""
        (self.root / "draft.md").write_text("untracked before save\n", encoding="utf-8")
        self.run_snap("save")
        (self.root / "spec.md").write_text("rule 1\nrule 2 changed\n", encoding="utf-8")
        got = self.run_snap("check")
        self.assertEqual((got["changed_files"], got["untracked_files"]), ("1", "0"))

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

    def test_tree_prints_the_same_tree_as_save_without_recording_it(self):
        """G-V ループ（gv-loop.py）が自分の状態に持つ tree。Phase 6.9 の記録を上書きしない（#310）."""
        (self.root / "untracked.md").write_text("u\n", encoding="utf-8")
        tree = self.run_snap("tree")["snapshot"]
        self.assertRegex(tree, r"^[0-9a-f]{40}$")
        self.assertEqual(self.run_snap("check")["snapshot"], "missing", "tree が記録を作った")
        self.assertEqual(self.run_snap("save")["snapshot"], tree)


GV_LOOP = REPO / "feature-dev" / "scripts" / "gv-loop.py"


class GvLoopTest(unittest.TestCase):
    """`gv-loop.py` — G-V ループを delta の中だけで続け、範囲外の変更を数える（GitHub issue #310）.

    実測ではループが収束しなかった: Fix Mode が対象外の指摘まで直し（34 件・17 件）、再レビューが
    diff 全体から新しい指摘を拾ってループを延ばした。**ループを延ばす条件（delta の中・前回の対象の残存）と、
    延ばさない条件（delta の外 → deferred）の境界**を厚く見る。
    """

    LINES = 60

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.env = scrub()
        # 再レビューに渡す前回の対象（`prior_findings`）は TMPDIR に書くので、使い捨ての dir に向ける
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        self.tmpdir = Path(tmp_dir.name)
        self.env["TMPDIR"] = str(self.tmpdir)
        for args in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"]):
            self.git(*args)
        self.write_lines("a.txt", [f"line {i}" for i in range(1, self.LINES + 1)])
        self.git("add", "-A")
        self.git("commit", "-qm", "init")

    def git(self, *args: str) -> str:
        res = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, env=self.env)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout

    def write_lines(self, name: str, lines: list[str]) -> None:
        (self.root / name).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def edit(self, *line_nos: int, name: str = "a.txt") -> None:
        path = self.root / name
        lines = path.read_text(encoding="utf-8").splitlines()
        for n in line_nos:
            lines[n - 1] += " (fixed)"
        self.write_lines(name, lines)

    def raw(self, *args: str, stdin: str = "", cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["python3", str(GV_LOOP), *args], cwd=cwd or self.root, input=stdin,
                              capture_output=True, text=True, env=self.env, timeout=60)

    def run_loop(self, *args: str, stdin: str = "", cwd: Path | None = None) -> dict:
        res = self.raw(*args, stdin=stdin, cwd=cwd)
        self.assertEqual(res.returncode, 0, res.stderr)
        out: dict = {"rows": []}
        for line in res.stdout.splitlines():
            if "\t" in line:
                out["rows"].append(line.split("\t"))
            else:
                k, _, v = line.partition("=")
                out[k] = v
        return out

    @staticmethod
    def findings(*items: tuple) -> str:
        """items: (severity, confidence, file, line, focus)."""
        return json.dumps({"schema_version": 1, "findings": [
            {"id": i, "severity": s, "confidence": c, "focus": fo, "file": f, "line": ln, "title": f"t{i}"}
            for i, (s, c, f, ln, fo) in enumerate(items, 1)], "missing_coverage": []})

    def review(self, *items: tuple) -> dict:
        return self.run_loop("review", stdin=self.findings(*items))

    @staticmethod
    def rows(out: dict, kind: str) -> list[list[str]]:
        return [r for r in out["rows"] if r[0] == kind]

    def start(self, max_iterations: int, *items: tuple) -> dict:
        self.assertEqual(self.run_loop("init", "--max", str(max_iterations))["loop"], "initialized")
        return self.review(*items)

    def test_initial_review_targets_blockers_and_confident_criticals(self):
        got = self.start(3, ("BLOCKER", 10, "a.txt", 5, "security"), ("CRITICAL", 90, "a.txt", 20, "bug-detection"),
                         ("CRITICAL", 89, "a.txt", 30, "bug-detection"), ("MAJOR", 100, "a.txt", 40, "security"))
        self.assertEqual((got["action"], got["iteration"]), ("fix", "1/3"))
        self.assertEqual([r[1] for r in self.rows(got, "target")],
                         ["a.txt:5:security", "a.txt:20:bug-detection"])
        self.assertTrue(got["notice"].startswith("🔄 Iteration 1/3: auto-fix 2 件"), got["notice"])

    def test_no_target_stops_with_success(self):
        got = self.start(3, ("MAJOR", 100, "a.txt", 5, "security"), ("CRITICAL", 80, "a.txt", 6, "security"))
        self.assertEqual((got["action"], got["reason"]), ("stop", "success"))
        self.assertNotIn("notice", got)
        self.assertNotIn("since", got, "止める回に再レビューの引数を出した")

    def state(self) -> dict:
        gd = self.git("rev-parse", "--absolute-git-dir").strip()
        return json.loads((Path(gd) / "feature-dev-loop-state.json").read_text(encoding="utf-8"))

    def test_fix_hands_since_and_prior_findings_for_the_rereview(self):
        """再レビューを delta に絞る材料（GitHub issue #313）: 修正前の tree と、前回の対象の JSON."""
        got = self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.assertEqual(got["action"], "fix")
        self.assertRegex(got["since"], r"^[0-9a-f]{40,64}$")
        self.assertEqual(got["since"], self.state()["iterations"][-1]["pre_fix_tree"])
        self.assertTrue(got["prior_findings"].startswith(str(self.tmpdir)))
        self.assertEqual(json.loads(Path(got["prior_findings"]).read_text(encoding="utf-8")),
                         [{"file": "a.txt", "line": 10, "focus": "bug-detection", "title": "t1"}])
        self.assertEqual(self.state()["iterations"][-1]["targets"][0]["focus"], "bug-detection")

    def test_prior_findings_accumulate_every_round_without_duplicates(self):
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10)
        got = self.review(("BLOCKER", 70, "a.txt", 12, "security"), ("BLOCKER", 70, "a.txt", 12, "security"))
        self.assertEqual(got["action"], "fix")
        self.assertEqual([(i["line"], i["focus"]) for i in
                          json.loads(Path(got["prior_findings"]).read_text(encoding="utf-8"))],
                         [(10, "bug-detection"), (12, "security")])

    def test_ask_also_hands_since(self):
        self.start(2, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10)
        got = self.review(("BLOCKER", 70, "a.txt", 12, "security"))
        self.assertEqual(got["action"], "ask")
        self.assertIn("prior_findings", got)
        self.assertRegex(got["since"], r"^[0-9a-f]{40,64}$")

    def test_since_is_unavailable_when_prior_findings_cannot_be_written(self):
        """空白を含む置き場所・ディレクトリを作れない回は、--since も渡さない（diff 全体に戻す）."""
        spaced = self.tmpdir / "a b"
        spaced.mkdir()
        blocker = self.tmpdir / "blocked"
        blocker.mkdir()
        (blocker / ("feature-dev-%d" % os.getuid())).write_text("x", encoding="utf-8")
        for name, tmp in (("space", spaced), ("file", blocker)):
            with self.subTest(name):
                self.env["TMPDIR"] = str(tmp)
                got = self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
                self.assertEqual((got["action"], got["since"]), ("fix", "unavailable"))
                self.assertNotIn("prior_findings", got)

    def test_deferred_outlives_a_rereview_that_does_not_report_it_again(self):
        """delta を主に見る再レビューは delta の外の指摘を出し直さない。前の回の deferred を残す（#313）."""
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10)
        got = self.review(("BLOCKER", 70, "a.txt", 40, "security"), ("BLOCKER", 70, "a.txt", 12, "security"))
        self.assertEqual(got["action"], "fix")
        self.assertEqual([r[1] for r in self.rows(got, "deferred")], ["a.txt:40:security"])
        self.edit(12)
        got = self.review()
        self.assertEqual((got["action"], got["reason"]), ("stop", "deferred"))
        self.assertEqual([r[1] for r in self.rows(got, "deferred")], ["a.txt:40:security"])
        self.assertEqual(self.run_loop("summary")["deferred"], "1")

    def test_a_deferred_reported_again_is_listed_once(self):
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10)
        self.review(("BLOCKER", 70, "a.txt", 40, "security"), ("BLOCKER", 70, "a.txt", 12, "security"))
        self.edit(12)
        got = self.review(("BLOCKER", 70, "a.txt", 40, "security"))
        self.assertEqual((got["action"], got["reason"]), ("stop", "deferred"))
        self.assertEqual([r[1] for r in self.rows(got, "deferred")], ["a.txt:40:security"])

    def insert_lines(self, after: int, count: int, name: str = "a.txt") -> None:
        path = self.root / name
        lines = path.read_text(encoding="utf-8").splitlines()
        lines[after:after] = [f"inserted {i}" for i in range(count)]
        self.write_lines(name, lines)

    def test_a_deferred_moved_by_the_fix_is_listed_once(self):
        """修正が上の行を足すと、出し直された同じ指摘は別の fingerprint になる。古い行を写してから突き合わせる."""
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10)
        self.review(("BLOCKER", 70, "a.txt", 40, "security"), ("BLOCKER", 70, "a.txt", 12, "security"))
        self.edit(12)
        self.insert_lines(12, 8)  # 40 行目が 48 行目へ動く（DELTA_MARGIN より大きくずらす）
        got = self.review(("BLOCKER", 70, "a.txt", 48, "security"))
        self.assertEqual((got["action"], got["reason"]), ("stop", "deferred"))
        self.assertEqual([r[1] for r in self.rows(got, "deferred")], ["a.txt:48:security"])
        self.assertEqual(self.run_loop("summary")["deferred"], "1")

    def test_a_carried_deferred_follows_the_lines_the_fix_moved(self):
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10)
        self.review(("BLOCKER", 70, "a.txt", 40, "security"), ("BLOCKER", 70, "a.txt", 12, "security"))
        self.edit(12)
        self.insert_lines(12, 3)
        got = self.review()
        self.assertEqual([r[1] for r in self.rows(got, "deferred")], ["a.txt:43:security"])

    def test_a_target_of_an_earlier_round_reported_again_is_a_regression(self):
        """再レビューには全回の対象を渡すので、後の修正が先の修正を戻した回も regression で止める."""
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10)
        self.assertEqual(self.review(("BLOCKER", 70, "a.txt", 12, "security"))["action"], "fix")
        self.edit(12)
        got = self.review(("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.assertEqual((got["action"], got["reason"]), ("stop", "regression"))

    def test_since_of_a_later_round_is_the_tree_before_that_fix(self):
        """delta は直前の修正からの差分。ループの起点の tree を渡すと、前の回の修正を毎回見直す."""
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10)
        res = subprocess.run(["bash", str(SNAPSHOT), "tree"], cwd=self.root, capture_output=True, text=True,
                             env=self.env, timeout=60)
        before = res.stdout.strip().removeprefix("snapshot=")
        got = self.review(("BLOCKER", 70, "a.txt", 12, "security"))
        self.assertEqual(got["since"], before)
        self.assertNotEqual(got["since"], self.state()["start_tree"])

    def test_null_focus_is_an_empty_key(self):
        """`"focus": null` を `None` という観点名にしない（再レビューで割り当て先が決まらなくなる）."""
        self.run_loop("init", "--max", "3")
        stdin = json.dumps({"findings": [{"severity": "BLOCKER", "confidence": 70, "focus": None,
                                          "file": "a.txt", "line": 10, "title": "x"}]})
        self.assertEqual([r[1] for r in self.rows(self.run_loop("review", stdin=stdin), "target")], ["a.txt:10:"])

    def private_dir(self) -> Path:
        return self.tmpdir / ("feature-dev-%d" % os.getuid())

    def test_prior_findings_are_private(self):
        got = self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        path = Path(got["prior_findings"])
        self.assertEqual(path.parent, self.private_dir())
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(path.parent).st_mode & 0o777, 0o700)

    def test_prior_findings_are_not_written_into_a_dir_someone_else_can_reach(self):
        """TMPDIR が無い環境は共有の /tmp に落ちる。先に作られた dir や symlink に書かず、diff 全体に戻す."""
        elsewhere = self.tmpdir / "elsewhere"
        elsewhere.mkdir()
        os.chmod(elsewhere, 0o777)

        def open_mode() -> None:
            self.private_dir().mkdir()
            os.chmod(self.private_dir(), 0o777)

        for name, make in (("symlink", lambda: self.private_dir().symlink_to(elsewhere)), ("open mode", open_mode)):
            with self.subTest(name):
                make()
                self.run_loop("init", "--max", "3")
                res = self.raw("review", stdin=self.findings(("BLOCKER", 70, "a.txt", 10, "bug-detection")))
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertIn("since=unavailable", res.stdout.splitlines())
                self.assertIn("WARN:", res.stderr)
                self.assertEqual(list(elsewhere.iterdir()), [])
                if self.private_dir().is_symlink():
                    self.private_dir().unlink()
                else:
                    shutil.rmtree(self.private_dir())

    def test_prior_findings_are_removed_when_the_loop_stops(self):
        for name in ("success", "finish"):
            with self.subTest(name):
                self.git("checkout", "-q", "--", ".")
                path = Path(self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))["prior_findings"])
                self.edit(10)
                if name == "success":
                    self.assertEqual(self.review()["reason"], "success")
                else:
                    self.run_loop("finish", "--reason", "manual")
                self.assertFalse(path.exists())

    def test_init_removes_only_the_previous_run_of_this_worktree(self):
        """6.9 の分は止めた後に書くので init で消す。dir は別の worktree のループと共有するので、そちらは残す."""
        self.start(3)
        mine = Path(self.run_loop("prior-findings", stdin=self.findings(("MINOR", 80, "a.txt", 3, "x")))
                    ["prior_findings"])
        other = self.private_dir() / "gv-prior-findings-another-run.json"
        other.write_text("[]", encoding="utf-8")
        self.run_loop("init", "--max", "3")
        self.assertFalse(mine.exists())
        self.assertTrue(other.exists())

    def prior_items(self, out: dict) -> list[tuple[int, str]]:
        return [(i["line"], i["focus"]) for i in json.loads(Path(out["prior_findings"]).read_text(encoding="utf-8"))]

    def test_prior_findings_for_phase_6_9_join_the_loop_leftovers_and_the_chosen_fixes(self):
        """6.9 の差分の主な中身は Step 4 で直すと決めた指摘への修正。前回の対象なしに delta だけを見せない."""
        self.start(1, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10)
        self.review(("BLOCKER", 70, "a.txt", 11, "security"), ("BLOCKER", 70, "a.txt", 50, "security"))
        got = self.run_loop("prior-findings", "--with-loop",
                            stdin=self.findings(("MAJOR", 95, "a.txt", 30, "doc-substance"),
                                                ("BLOCKER", 70, "a.txt", 11, "security")))
        # 古い順（後ろほど新しい）: deferred → remaining → 直すと決めた指摘
        self.assertEqual(self.prior_items(got), [(50, "security"), (11, "security"), (30, "doc-substance")])

    def test_prior_findings_ignore_the_loop_state_without_with_loop(self):
        """状態は作業ツリーに残り続ける。init を呼ばない run では前の run のものなので、既定では読まない."""
        self.start(1, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10)
        self.review(("BLOCKER", 70, "a.txt", 11, "security"))
        self.assertEqual(self.run_loop("prior-findings")["prior_findings"], "none")
        got = self.run_loop("prior-findings", stdin=self.findings(("MINOR", 80, "a.txt", 3, "x")))
        self.assertEqual(self.prior_items(got), [(3, "x")])
        self.assertTrue(got["prior_findings"].endswith("gv-prior-findings-nostate.json"), "uuid で書くと誰も消さない")

    def test_chosen_findings_without_a_line_are_kept_and_without_a_file_are_dropped(self):
        stdin = json.dumps({"findings": [{"severity": "MAJOR", "file": "a.txt", "line": None, "focus": "x", "title": "n"},
                                         {"severity": "MAJOR", "file": "", "line": 3, "focus": "x", "title": "e"}]})
        res = self.raw("prior-findings", stdin=stdin)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("WARN:", res.stderr)
        path = res.stdout.strip().removeprefix("prior_findings=")
        self.assertEqual(json.loads(Path(path).read_text(encoding="utf-8")),
                         [{"file": "a.txt", "line": None, "focus": "x", "title": "n"}])

    def test_chosen_findings_keep_line_1_and_drop_line_0(self):
        """1 行目は実在する行。0 以下だけを「行なし」にする."""
        stdin = json.dumps({"findings": [{"severity": "MAJOR", "file": "a.txt", "line": 1, "focus": "x", "title": "top"},
                                         {"severity": "MAJOR", "file": "a.txt", "line": 0, "focus": "y", "title": "zero"}]})
        res = self.raw("prior-findings", stdin=stdin)
        self.assertEqual(res.returncode, 0, res.stderr)
        path = res.stdout.strip().removeprefix("prior_findings=")
        self.assertEqual([(i["line"], i["focus"]) for i in json.loads(Path(path).read_text(encoding="utf-8"))],
                         [(1, "x"), (None, "y")])

    def test_a_file_with_a_newline_is_rejected(self):
        """1 行 1 項目の出力に偽の `since=` / `prior_findings=` 行を差し込ませない."""
        self.run_loop("init", "--max", "3")
        for bad in ("a.txt\nprior_findings=$(id)", "a.txt\u2028prior_findings=$(id)"):
            with self.subTest(bad=bad):
                res = self.raw("review", stdin=self.findings(("BLOCKER", 70, bad, 10, "security")))
                self.assertEqual(res.returncode, 2, res.stdout)
                self.assertNotIn("prior_findings=", res.stdout)

    def two_rounds(self) -> None:
        """2 回目に a.txt:40:security を deferred にし、a.txt:12 を直した状態にする."""
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10)
        self.review(("BLOCKER", 70, "a.txt", 40, "security"), ("BLOCKER", 70, "a.txt", 12, "security"))
        self.edit(12)

    def test_another_focus_on_the_deferred_line_does_not_drop_it(self):
        self.two_rounds()
        got = self.review(("BLOCKER", 70, "a.txt", 40, "error-handling"))
        self.assertEqual(sorted(r[1] for r in self.rows(got, "deferred")),
                         ["a.txt:40:error-handling", "a.txt:40:security"])

    def test_a_nearby_different_finding_of_the_same_focus_does_not_drop_the_deferred(self):
        """近いだけで同じとみなすと、別の指摘で deferred を捨てて `success` で止まりうる."""
        self.two_rounds()
        other = json.dumps({"findings": [{"severity": "BLOCKER", "confidence": 70, "focus": "security",
                                          "file": "a.txt", "line": 43, "title": "別の指摘"}]})
        got = self.run_loop("review", stdin=other)
        self.assertEqual(sorted(r[1] for r in self.rows(got, "deferred")), ["a.txt:40:security", "a.txt:43:security"])

    def test_an_insertion_right_above_moves_the_deferred(self):
        self.two_rounds()
        self.insert_lines(39, 3)
        self.assertEqual([r[1] for r in self.rows(self.review(), "deferred")], ["a.txt:43:security"])

    def test_a_rewritten_range_moves_the_deferred_to_its_start(self):
        self.two_rounds()
        lines = (self.root / "a.txt").read_text(encoding="utf-8").splitlines()
        lines[37:42] = ["rewritten a", "rewritten b"]
        self.write_lines("a.txt", lines)
        self.assertEqual([r[1] for r in self.rows(self.review(), "deferred")], ["a.txt:38:security"])

    def test_a_deferred_on_a_file_the_fix_removed_is_dropped(self):
        # ループの起点より前からあるファイル（起点の後に作ると delta に入り、deferred にならない）
        self.write_lines("b.txt", [f"b {i}" for i in range(1, 30)])
        self.git("add", "b.txt")
        self.git("commit", "-qm", "b")
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10)
        got = self.review(("BLOCKER", 70, "b.txt", 15, "security"), ("BLOCKER", 70, "a.txt", 12, "security"))
        self.assertEqual([r[1] for r in self.rows(got, "deferred")], ["b.txt:15:security"], "前提: deferred にした")
        self.edit(12)
        (self.root / "b.txt").unlink()
        got = self.review()
        self.assertEqual(self.rows(got, "deferred"), [])
        self.assertEqual(got["reason"], "success")

    def test_a_reverted_earlier_target_moved_by_a_later_fix_is_a_regression(self):
        """各回の対象は、その後の修正で動いた行へ写して持つ。写さないと、行がずれた戻しを見逃す."""
        self.start(3, ("BLOCKER", 70, "a.txt", 50, "bug-detection"))
        self.edit(50, 10)
        self.assertEqual(self.review(("BLOCKER", 70, "a.txt", 10, "security"))["action"], "fix")
        self.insert_lines(9, 3)
        got = self.review(("BLOCKER", 70, "a.txt", 53, "bug-detection"))
        self.assertEqual((got["action"], got["reason"]), ("stop", "regression"))

    def test_a_state_without_focus_is_still_read(self):
        """この版より前に作った状態（targets に focus が無い）を読んでも落ちない."""
        self.two_rounds()
        self.edit_state(lambda s: [t.pop("focus", None) for r in s["iterations"] for t in r["targets"]]
                        + [t.pop("focus", None) for t in s["deferred"]])
        res = self.raw("review", stdin=self.findings())
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("deferred\ta.txt:40:security", res.stdout)

    def test_prior_findings_for_phase_6_9_without_a_loop(self):
        got = self.run_loop("prior-findings", stdin=self.findings(("MINOR", 80, "a.txt", 3, "comment-accuracy")))
        self.assertEqual(self.prior_items(got), [(3, "comment-accuracy")])

    def test_prior_findings_for_phase_6_9_with_nothing_to_check(self):
        self.start(3)
        self.assertEqual(self.run_loop("prior-findings")["prior_findings"], "none")

    def test_prior_findings_for_phase_6_9_that_cannot_be_written(self):
        spaced = self.tmpdir / "a b"
        spaced.mkdir()
        self.env["TMPDIR"] = str(spaced)
        res = self.raw("prior-findings", stdin=self.findings(("MINOR", 80, "a.txt", 3, "x")))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "prior_findings=unavailable")
        self.assertIn("WARN:", res.stderr)

    def fixed_line_10(self) -> None:
        """a.txt:10 の対象を直した状態にする。init は前のループの状態を上書きするので subTest ごとに呼べる."""
        self.git("checkout", "-q", "--", ".")
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10)

    def test_target_near_the_loop_change_continues_the_loop(self):
        for line in (5, 15):  # 変えた行（10）から 5 行以内の両端
            with self.subTest(line=line):
                self.fixed_line_10()
                self.assertEqual(self.review(("BLOCKER", 70, "a.txt", line, "security"))["action"], "fix")

    def test_target_away_from_the_loop_change_is_deferred(self):
        """修正と関係ない箇所の新しい指摘ではループを延ばさない（#310 の 2 つ目の原因）."""
        for line in (4, 16):  # 変えた行（10）から 6 行離れた両端
            with self.subTest(line=line):
                self.fixed_line_10()
                got = self.review(("BLOCKER", 70, "a.txt", line, "security"))
                self.assertEqual((got["action"], got["reason"]), ("stop", "deferred"))
                self.assertEqual([r[1] for r in self.rows(got, "deferred")], [f"a.txt:{line}:security"])
                self.assertEqual(self.rows(got, "target"), [])

    def test_deferred_and_looped_targets_are_split(self):
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10)
        got = self.review(("BLOCKER", 70, "a.txt", 11, "security"), ("CRITICAL", 95, "a.txt", 50, "security"))
        self.assertEqual((got["action"], got["iteration"]), ("fix", "2/3"))
        self.assertEqual([r[1] for r in self.rows(got, "target")], ["a.txt:11:security"])
        self.assertEqual([r[1] for r in self.rows(got, "deferred")], ["a.txt:50:security"])
        self.assertIn("delta の外へ回した指摘 1 件", got["notice"])

    def test_file_created_in_the_loop_is_in_the_delta(self):
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.write_lines("b.txt", ["new 1", "new 2"])
        self.assertEqual(self.review(("BLOCKER", 70, "b.txt", 2, "security"))["action"], "fix")

    def test_same_fingerprint_again_is_a_regression(self):
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10)
        got = self.review(("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.assertEqual((got["action"], got["reason"]), ("stop", "regression"))
        self.assertEqual([r[1] for r in self.rows(got, "target")], ["a.txt:10:bug-detection"])

    def test_persisting_target_outside_the_delta_is_still_a_regression(self):
        """修正を別の場所に入れて対象が残った回を deferred に流さない."""
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(40)
        got = self.review(("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.assertEqual(got["reason"], "regression")

    def test_budget(self):
        self.assertEqual(self.start(1, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))["action"], "fix")
        self.edit(10)
        got = self.review(("BLOCKER", 70, "a.txt", 11, "security"))
        self.assertEqual((got["action"], got["reason"], got["iteration"]), ("stop", "budget", "1/1"))
        self.assertEqual([r[1] for r in self.rows(got, "target")], ["a.txt:11:security"])

    def test_last_round_asks_only_after_the_first(self):
        self.assertEqual(self.start(2, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))["action"], "fix")
        self.edit(10)
        got = self.review(("BLOCKER", 70, "a.txt", 11, "security"))
        self.assertEqual((got["action"], got["iteration"]), ("ask", "2/2"))
        self.assertTrue(got["notice"].startswith("🔄 Iteration 2/2"), got["notice"])

    def test_changes_away_from_the_target_are_counted_out_of_scope(self):
        """Fix Mode が対象外まで直した分を数える（#310 の 1 つ目の原因）。止めはしない."""
        self.start(3, ("BLOCKER", 70, "a.txt", 30, "bug-detection"))
        self.edit(18, 20, 30, 40, 42)  # 対象（30）から 10 行以内は 20 / 30 / 40
        self.write_lines("b.txt", ["unrelated"])
        got = self.review(("BLOCKER", 70, "a.txt", 30, "security"))
        self.assertEqual((got["action"], got["out_of_scope"]), ("fix", "3"))
        self.assertEqual(sorted(r[2] for r in self.rows(got, "out_of_scope")), ["a.txt:18-18", "a.txt:42-42", "b.txt:0-1"])
        self.assertIn("前回の範囲外の変更 3 か所", got["notice"])
        summary = self.run_loop("summary")
        self.assertEqual((summary["out_of_scope"], summary["auto_fix_targets"]), ("3", "1"))

    def test_first_round_has_no_out_of_scope_line(self):
        got = self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.assertNotIn("out_of_scope", got)
        self.assertNotIn("前回", got["notice"])

    def test_reads_the_block_out_of_the_self_review_output(self):
        self.run_loop("init", "--max", "3")
        body = self.findings(("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        text = f"## レポート\n...\n<!-- FINDINGS_JSON_START -->\n```json\n{body}\n```\n<!-- FINDINGS_JSON_END -->\n" \
               "[embed-mode: findings-only, no-prompt]\n"
        self.assertEqual(self.run_loop("review", stdin=text)["action"], "fix")

    def test_invalid_input_exits_2(self):
        self.run_loop("init", "--max", "3")
        cases = {
            "not json": "not json",
            "no end marker": "<!-- FINDINGS_JSON_START -->\n{}",
            "no findings": json.dumps({"schema_version": 1}),
            "target without line": json.dumps({"findings": [{"severity": "BLOCKER", "confidence": 70,
                                                             "focus": "security", "file": "a.txt"}]}),
        }
        for name, stdin in cases.items():
            with self.subTest(name):
                res = self.raw("review", stdin=stdin)
                self.assertEqual(res.returncode, 2, res.stdout)
                self.assertIn("error=", res.stderr)

    def test_target_on_the_first_line_is_accepted(self):
        self.assertEqual(self.start(3, ("BLOCKER", 70, "a.txt", 1, "security"))["action"], "fix")

    def test_target_with_an_empty_file_exits_2(self):
        self.run_loop("init", "--max", "3")
        res = self.raw("review", stdin=self.findings(("BLOCKER", 70, "", 3, "security")))
        self.assertEqual(res.returncode, 2, res.stdout)

    def test_usage_errors_exit_2(self):
        self.run_loop("init", "--max", "3")  # 状態が無いことによる exit 2 と取り違えない
        for args in ((), ("init",), ("finish",)):
            with self.subTest(args=args):
                self.assertEqual(self.raw(*args).returncode, 2)

    def edit_state(self, change) -> None:
        path = self.root / ".git" / "feature-dev-loop-state.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        change(state)
        path.write_text(json.dumps(state), encoding="utf-8")

    def test_unreadable_start_tree_loops_every_target(self):
        """delta を取れないときは deferred に回さず、以前どおり全対象でループする."""
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10)
        self.edit_state(lambda s: s.update(start_tree="0" * 40))
        got = self.review(("BLOCKER", 70, "a.txt", 50, "security"))
        self.assertEqual((got["action"], got["delta"]), ("fix", "unavailable"))
        self.assertEqual(self.rows(got, "deferred"), [])

    def test_round_without_a_pre_fix_tree_reports_out_of_scope_as_unavailable(self):
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10, 50)
        self.edit_state(lambda s: s["iterations"][-1].update(pre_fix_tree=None))
        self.assertEqual(self.review(("BLOCKER", 70, "a.txt", 11, "security"))["out_of_scope"], "unavailable")
        self.assertEqual(self.run_loop("summary")["out_of_scope"], "unavailable")

    def test_finish_before_the_first_review(self):
        self.run_loop("init", "--max", "3")
        got = self.run_loop("finish", "--reason", "manual")
        self.assertEqual((got["reason"], got["iteration"]), ("manual", "0/3"))

    def test_minor_without_location_is_not_an_input_error(self):
        """場所を検証するのは auto-fix 対象だけ（報告のみの指摘で止めない）."""
        got = self.start(3, ("MINOR", 50, "", 0, "readability"))
        self.assertEqual(got["reason"], "success")

    def test_review_before_init_and_after_stop_exits_2(self):
        self.assertEqual(self.raw("review", stdin=self.findings()).returncode, 2)
        self.start(3)
        self.assertEqual(self.raw("review", stdin=self.findings()).returncode, 2)

    def test_init_rejects_zero(self):
        self.assertEqual(self.raw("init", "--max", "0").returncode, 2)

    def test_finish_before_fixing_does_not_count_the_round(self):
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        got = self.run_loop("finish", "--reason", "manual")
        self.assertEqual((got["reason"], got["iteration"]), ("manual", "0/3"))
        summary = self.run_loop("summary")
        self.assertEqual((summary["reason"], summary["remaining"], summary["auto_fix_targets"]), ("manual", "1", "0"))

    def test_finish_after_a_partial_fix_closes_the_round(self):
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10, 50)
        self.assertEqual(self.run_loop("finish", "--reason", "manual")["iteration"], "1/3")
        summary = self.run_loop("summary")
        self.assertEqual((summary["iterations"], summary["out_of_scope"]), ("1/3", "1"))
        self.assertEqual(self.raw("finish", "--reason", "manual").returncode, 2, "止めた後にもう一度止められた")

    def test_summary_lists_remaining_and_deferred(self):
        self.start(1, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.edit(10)
        self.review(("BLOCKER", 70, "a.txt", 11, "security"), ("BLOCKER", 70, "a.txt", 50, "security"))
        got = self.run_loop("summary")
        self.assertEqual((got["loop"], got["reason"], got["iterations"]), ("terminated", "budget", "1/1"))
        self.assertEqual([r[1] for r in self.rows(got, "remaining")], ["a.txt:11:security"])
        self.assertEqual([r[1] for r in self.rows(got, "deferred")], ["a.txt:50:security"])
        self.assertEqual(self.rows(got, "iteration"), [["iteration", "1", "1", "0"]])

    def test_summary_without_a_loop(self):
        self.assertEqual(self.run_loop("summary")["loop"], "missing")

    def test_not_a_git_repo(self):
        with tempfile.TemporaryDirectory() as d:
            for args in (("init", "--max", "3"), ("review",), ("summary",)):
                with self.subTest(args=args):
                    self.assertEqual(self.run_loop(*args, stdin=self.findings(), cwd=Path(d))["loop"], "unavailable")

    def test_works_from_a_subdirectory(self):
        (self.root / "docs").mkdir()
        self.run_loop("init", "--max", "3", cwd=self.root / "docs")
        self.edit(10)
        self.assertEqual(self.run_loop("summary", cwd=self.root / "docs")["loop"], "running")

    def test_refs_and_index_are_untouched(self):
        (self.root / "untracked.md").write_text("u\n", encoding="utf-8")
        before = (self.git("rev-parse", "HEAD"), self.git("status", "--porcelain"))
        self.start(3, ("BLOCKER", 70, "a.txt", 10, "bug-detection"))
        self.review()
        self.run_loop("summary")
        self.assertEqual((self.git("rev-parse", "HEAD"), self.git("status", "--porcelain")), before)


class GvLoopProcedureTest(unittest.TestCase):
    """G-V ループの手順が `gv-loop.py` を通り、止め方と集計を落とさない（GitHub issue #310）."""

    SKILL = REPO / "feature-dev" / "skills" / "feature-dev" / "SKILL.md"
    REVIEW_LOOP = REPO / "feature-dev" / "references" / "review-loop.md"

    def test_loop_state_is_not_written_by_hand(self):
        for path in (self.SKILL, self.REVIEW_LOOP, REPO / "feature-dev" / "references" / "triage-guide.md"):
            with self.subTest(path=path.name):
                self.assertNotIn("/tmp/feature-dev-loop-state.json", path.read_text())

    def test_loop_calls_every_subcommand(self):
        text = self.REVIEW_LOOP.read_text()
        for cmd in ('gv-loop.py" init --max', 'gv-loop.py" review', 'gv-loop.py" finish --reason manual'):
            self.assertIn(cmd, text)
        self.assertIn('gv-loop.py" summary', self.SKILL.read_text())

    def test_every_action_and_reason_is_handled(self):
        loop, skill = self.REVIEW_LOOP.read_text(), self.SKILL.read_text()
        for value in ("`action=fix`", "`action=ask`", "`action=stop`"):
            self.assertIn(value, loop)
        step4 = skill[skill.index("### Step 4: Consolidate and present"):skill.index("## Phase 6.7")]
        for reason in ("`success`", "`regression`", "`budget`", "`deferred`", "`manual`"):
            self.assertIn(reason, step4)

    def test_step4_reads_every_rereview_report(self):
        """delta 中心の再レビューの最後の回だけを読むと、初回・途中の回の delta の外の指摘が落ちる（#313）."""
        skill = self.SKILL.read_text()
        step4 = skill[skill.index("### Step 4: Consolidate and present"):skill.index("## Phase 6.7")]
        self.assertIn("**各回の**再レビューのレポート", step4)
        self.assertIn("初回のレポート", step4)
        self.assertNotIn("self-review の最終出力（post-loop）", step4)

    def test_comment_polish_scans_the_whole_diff_after_a_rereview(self):
        skill = self.SKILL.read_text()
        p67 = skill[skill.index("## Phase 6.7"):skill.index("## Phase 6.9")]
        self.assertIn("`iterations` が 1 以上", p67)

    def test_fix_mode_leaves_non_targets_to_step4(self):
        skill = self.SKILL.read_text()
        fix = skill[skill.index("### Fix Mode"):skill.index("## Phase 5.3")]
        self.assertIn("Step 4", fix)
        self.assertIn("MAJOR / MINOR", fix)


if __name__ == "__main__":
    unittest.main()
