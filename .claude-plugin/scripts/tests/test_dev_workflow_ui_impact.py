#!/usr/bin/env python3
"""dev-workflow の `ui-impact.sh`（ui-verify の事前判定）の CLI テスト（GitHub issue #306）.

**何を守るか**: feature-dev の Phase 5.5 と軽量フローは、この結果で動作確認を走らせるかが決まる。
黙る側（`no`）に倒れすぎると画面の変更が動作確認を素通りし、鳴る側（`yes`）に倒れすぎると
画面に触れない変更のたびにブラウザが開く。**どちらも対で見る**。

見る範囲（未コミット + 未追跡）の取りこぼしは「`git diff HEAD` だけ」の素朴な実装で起きる型
（未追跡の新規ファイル / index だけの変更 / rename の旧名 / 非 ASCII のファイル名のエスケープ）
なので 1 つずつ固定する。拡張子の定義は ui-change-reminder.sh と共通（`scripts/lib/ui-paths.sh`）
なので、拡張子ごとの期待値をリテラルで持ち、hook を実際に叩いた結果と ui-impact.sh の結果の両方を
それと突き合わせる。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from git_env import scrub
from hook_harness import HookTestCase

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "dev-workflow" / "scripts" / "ui-impact.sh"


def parse(stdout: str) -> dict:
    out: dict = {"UI_FILE": []}
    for line in stdout.splitlines():
        key, sep, value = line.partition("=")
        if not sep:
            continue
        if key == "UI_FILE":
            out["UI_FILE"].append(value)
        else:
            out[key] = value
    return out


class Repo:
    """使い捨てリポジトリ（初期コミットに tsx / ts / .gitignore を持つ）."""

    def __init__(self, test: unittest.TestCase, commit: bool = True) -> None:
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.test = test
        self.path = Path(tmp.name).resolve()
        self.env = scrub()
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        # 開発機のグローバルな ignore に結果を左右させない
        self.git("config", "core.excludesFile", "/dev/null")
        if commit:
            self.write("src/app.tsx")
            self.write("src/util.ts")
            self.write(".gitignore", "build/\n.claude/\n")
            self.commit("init")

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=str(self.path), capture_output=True, text=True,
                              env=self.env, check=True)

    def write(self, rel: str, body: str = "x\n") -> None:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-qm", message)

    def impact(self, *args: str, cwd: Path | None = None, expect_rc: int = 0,
               script: Path | None = None) -> dict:
        proc = subprocess.run(["bash", str(script or SCRIPT), *args], cwd=str(cwd or self.path),
                              capture_output=True, text=True, env=self.env, timeout=30)
        self.test.assertEqual(proc.returncode, expect_rc, proc.stderr)
        self.last = proc
        return parse(proc.stdout)


class UiImpactTest(unittest.TestCase):
    def test_clean_tree_is_no(self):
        out = Repo(self).impact()
        self.assertEqual(out["UI_IMPACT"], "no")
        self.assertEqual((out["CHANGED_FILES"], out["UI_FILES"]), ("0", "0"))
        self.assertEqual(out["REASON"], "未コミットの変更なし")
        self.assertEqual(out["UI_FILE"], [])

    def test_non_ui_changes_are_no_until_a_ui_file_appears(self):
        repo = Repo(self)
        for name in ("a.ts", "b.py", "README.md", "c.json", "d.tsx.bak", "src/lib/e.ts"):
            repo.write(name)
        out = repo.impact()
        self.assertEqual(out["UI_IMPACT"], "no")
        self.assertEqual((out["CHANGED_FILES"], out["UI_FILES"]), ("6", "0"))
        self.assertEqual(out["REASON"], "変更 6 件に画面のファイルなし")
        repo.write("e.tsx")
        out = repo.impact()
        self.assertEqual(out["UI_IMPACT"], "yes")
        self.assertEqual((out["CHANGED_FILES"], out["UI_FILES"]), ("7", "1"))
        self.assertEqual(out["UI_FILE"], ["e.tsx"])
        self.assertEqual(out["REASON"], "")

    def test_modified_tracked_tsx_is_yes(self):
        repo = Repo(self)
        repo.write("src/app.tsx", "changed\n")
        out = repo.impact()
        self.assertEqual(out["UI_IMPACT"], "yes")
        self.assertEqual(out["UI_FILE"], ["src/app.tsx"])
        self.assertEqual(out["CHANGED_FILES"], "1")

    def test_untracked_new_vue_is_yes(self):
        """`git diff HEAD` だけでは未追跡の新規ファイルを落とす."""
        repo = Repo(self)
        repo.write("src/New.vue")
        out = repo.impact()
        self.assertEqual(out["UI_IMPACT"], "yes")
        self.assertEqual(out["UI_FILE"], ["src/New.vue"])

    def test_deleted_css_is_yes(self):
        repo = Repo(self)
        repo.write("src/style.css")
        repo.commit("css")
        (repo.path / "src" / "style.css").unlink()
        out = repo.impact()
        self.assertEqual(out["UI_IMPACT"], "yes")
        self.assertEqual(out["UI_FILE"], ["src/style.css"])

    def test_change_only_in_the_index_is_yes(self):
        """作業ツリーを HEAD に戻しても、index に残った変更はコミットに入る."""
        repo = Repo(self)
        repo.write("src/A.svelte", "v1\n")
        repo.commit("svelte")
        repo.write("src/A.svelte", "v2\n")
        repo.git("add", "src/A.svelte")
        repo.write("src/A.svelte", "v1\n")
        out = repo.impact()
        self.assertEqual(out["UI_IMPACT"], "yes")
        self.assertEqual(out["UI_FILE"], ["src/A.svelte"])

    def test_rename_counts_the_old_name(self):
        """.tsx を .ts に改名しても、消えた画面のファイルとして数える."""
        repo = Repo(self)
        repo.git("mv", "src/app.tsx", "src/app.ts")
        out = repo.impact()
        self.assertEqual(out["UI_IMPACT"], "yes")
        self.assertEqual(out["UI_FILE"], ["src/app.tsx"])
        self.assertEqual(out["CHANGED_FILES"], "2")

    def test_committed_ui_change_is_not_counted(self):
        repo = Repo(self)
        repo.write("src/app.tsx", "changed\n")
        repo.commit("ui")
        self.assertEqual(repo.impact()["UI_IMPACT"], "no")

    def test_ignored_ui_file_is_not_counted(self):
        repo = Repo(self)
        repo.write("build/x.css")
        self.assertEqual(repo.impact()["UI_IMPACT"], "no")
        repo.write("src/x.css")
        out = repo.impact()
        self.assertEqual(out["UI_IMPACT"], "yes")
        self.assertEqual(out["UI_FILE"], ["src/x.css"])

    def test_paths_are_toplevel_relative_from_subdirectory(self):
        """未追跡の一覧は cwd 基準で出るので、サブディレクトリから叩いても toplevel 相対に揃える."""
        repo = Repo(self)
        repo.write("src/components/B.tsx")
        repo.write("top.css")
        out = repo.impact(cwd=repo.path / "src")
        self.assertEqual(sorted(out["UI_FILE"]), ["src/components/B.tsx", "top.css"])

    def test_non_ascii_filename_is_detected(self):
        """core.quotePath の 8 進エスケープ（`"src/\\347\\224\\273…"`）で拡張子の照合を外さない."""
        repo = Repo(self)
        repo.write("src/画面.tsx")
        out = repo.impact()
        self.assertEqual(out["UI_IMPACT"], "yes")
        self.assertEqual(out["UI_FILE"], ["src/画面.tsx"])

    def test_uppercase_extension_matches_like_the_hook(self):
        repo = Repo(self)
        repo.write("Banner.TSX")
        self.assertEqual(repo.impact()["UI_IMPACT"], "yes")

    def test_script_under_a_ui_layer_directory_is_yes(self):
        for name in ("src/components/Button.ts", "src/hooks/useCart.js", "app/routes/home.mts",
                     "src/stores/cart.mjs", "store/a.ts", "pages/index.js", "src/views/a/b/c.ts",
                     "layouts/Main.TS", "composables/useX.ts"):
            with self.subTest(name=name):
                repo = Repo(self)
                repo.write(name)
                out = repo.impact()
                self.assertEqual(out["UI_IMPACT"], "yes")
                self.assertEqual(out["UI_FILE"], [name])

    def test_script_outside_a_ui_layer_directory_is_no(self):
        repo = Repo(self)
        for name in ("src/lib/util.ts", "scripts/build.js", "src/componentsx/a.ts",
                     "mycomponents/a.ts", "src/components/README.md", "src/components/data.json"):
            repo.write(name)
        out = repo.impact()
        self.assertEqual(out["UI_IMPACT"], "no", out)

    def test_repo_without_commits(self):
        repo = Repo(self, commit=False)
        out = repo.impact()
        self.assertEqual((out["UI_IMPACT"], out["CHANGED_FILES"]), ("no", "0"))
        repo.write("a.tsx")
        self.assertEqual(repo.impact()["UI_IMPACT"], "yes")
        repo.git("add", "a.tsx")
        out = repo.impact()
        self.assertEqual(out["UI_IMPACT"], "yes")
        self.assertEqual(out["UI_FILE"], ["a.tsx"])

    def test_outside_git_is_unknown(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = scrub(GIT_CEILING_DIRECTORIES=str(Path(tmp.name).resolve().parent))
        proc = subprocess.run(["bash", str(SCRIPT)], cwd=tmp.name, capture_output=True, text=True,
                              env=env, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = parse(proc.stdout)
        self.assertEqual(out["UI_IMPACT"], "unknown")
        self.assertEqual(out["REASON"], "git リポジトリ外")

    def copy_script(self, lib_body: str | None) -> Path:
        """ui-impact.sh の複製. lib_body が None なら lib/ui-paths.sh を置かない."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        scripts = Path(tmp.name) / "scripts"
        (scripts / "lib").mkdir(parents=True)
        shutil.copy(SCRIPT, scripts / SCRIPT.name)
        if lib_body is not None:
            (scripts / "lib" / "ui-paths.sh").write_text(lib_body)
        return scripts / SCRIPT.name

    def test_unreadable_or_broken_rules_are_unknown(self):
        """判定式を読めない・照合に失敗した回は no ではなく unknown（確かめる側に倒す）."""
        repo = Repo(self)
        repo.write("src/app.tsx", "changed\n")
        cases = {
            "lib なし": (None, "読めない"),
            "式が壊れている（grep の rc 2）": ("UI_PATH_ERE='('\nUI_SCRIPT_ERE='x'\n", "rc 2"),
            "式が欠けている": ("UI_PATH_ERE='\\.tsx$'\n", "UI_SCRIPT_ERE"),
        }
        for label, (body, reason) in cases.items():
            with self.subTest(label=label):
                out = repo.impact(script=self.copy_script(body))
                self.assertEqual(out["UI_IMPACT"], "unknown", repo.last.stderr)
                self.assertIn(reason, out["REASON"])
        # 対照: 同じ複製に本物の lib を置けば判定できる
        real = (SCRIPT.parent / "lib" / "ui-paths.sh").read_text()
        self.assertEqual(repo.impact(script=self.copy_script(real))["UI_IMPACT"], "yes")

    def test_unknown_argument_exits_2(self):
        repo = Repo(self)
        out = repo.impact("--base", "main", expect_rc=2)
        self.assertNotIn("UI_IMPACT", out)

    def test_ui_file_list_is_capped(self):
        repo = Repo(self)
        for i in range(25):
            repo.write(f"c{i:02d}.css")
        out = repo.impact()
        self.assertEqual((out["CHANGED_FILES"], out["UI_FILES"]), ("25", "25"))
        self.assertEqual(len(out["UI_FILE"]), 20)


class ExtensionExpectationTest(HookTestCase):
    """拡張子ごとの「鳴る / 黙る」を固定し、hook（pending flag）と ui-impact.sh の両方をそれと突き合わせる.

    期待値を式（ui-paths.sh）から作らない: 同じ定数を読む 2 つを比べるだけだと、拡張子を削っても両方が
    同じ向きに変わって一致したまま通る（.jsx・.less・.html を削っても緑だった実測）.
    """

    PLUGIN = "dev-workflow"
    SCRIPT = "hooks/scripts/ui-change-reminder.sh"

    EXPECT = {
        "a.tsx": True, "a.jsx": True, "a.vue": True, "a.svelte": True, "a.css": True,
        "a.scss": True, "a.sass": True, "a.less": True, "a.html": True, "a.astro": True,
        "a.mdx": True, "a.module.css": True, "a.module.scss": True, "A.TSX": True,
        "a.ts": False, "a.js": False, "a.mts": False, "a.py": False, "a.md": False,
        "a.json": False, "a.tsx.bak": False, "a.htm": False,
    }

    def hook_fires(self, repo: Repo, name: str) -> bool:
        payload = {"tool_name": "Edit", "tool_input": {"file_path": str(repo.path / name)}}
        res = self.run_hook(payload, cwd=repo.path)
        self.assertNotIn("Unexpected", res.stderr)
        return "[ui-verify]" in res.stdout

    def enabled_repo(self) -> Repo:
        repo = Repo(self)
        (repo.path / ".claude").mkdir()
        (repo.path / ".claude" / ".ui-verify-enabled").touch()
        return repo

    def test_hook_and_ui_impact_match_the_expectation(self):
        for name, fires in self.EXPECT.items():
            with self.subTest(name=name):
                repo = self.enabled_repo()
                repo.write(name)
                self.assertEqual(self.hook_fires(repo, name), fires, "hook")
                self.assertEqual(repo.impact()["UI_IMPACT"], "yes" if fires else "no", "ui-impact")

    def test_script_in_a_ui_layer_directory_is_ui_impact_only(self):
        """画面の層の .ts は ui-impact.sh だけが数える（hook の reminder と gate は広げていない）."""
        repo = self.enabled_repo()
        repo.write("src/components/Button.ts")
        self.assertEqual(repo.impact()["UI_IMPACT"], "yes")
        self.assertFalse(self.hook_fires(repo, "src/components/Button.ts"))


if __name__ == "__main__":
    unittest.main()
