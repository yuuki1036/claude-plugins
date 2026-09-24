#!/usr/bin/env python3
"""feature-dev 同梱スクリプトの CLI 境界テスト（`scripts/plugin-enabled.sh`）.

有効判定を誤ると、無効化したプラグインの skill を呼びに行く（有効と誤認）か、project だけで
有効化したプラグインを使わない（取りこぼし）。以前の判定は `$HOME/.claude/settings.json` に
キーがあるかだけを見ていて、両方を起こしていた。**0 に倒すべき条件を厚く**書く。

実行:
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "feature-dev" / "scripts" / "plugin-enabled.sh"


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

    def test_project_dir_falls_back_to_cwd(self):
        """CLAUDE_PROJECT_DIR が無い（Bash ツールの既定）ときは cwd の .claude を読む."""
        self.settings("project", {"design-doc": True})
        self.assertState("design-doc", "1", project_env=False, cwd=self.proj)

    # --- 0 に倒すもの ---
    def test_no_settings_at_all(self):
        self.assertState("bdd-spec", "0")

    def test_disabled_but_installed_is_not_enabled(self):
        """`false` で無効化したプラグインを有効と誤認しない（旧判定の誤認 / spec-advisor #74 と同型）."""
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


class ReviewerFocusVocabularyTest(unittest.TestCase):
    """feature-dev が self-review に渡す focus 名が、code-review の focus 語彙に収まっているか.

    語彙外の名前（旧 `migration-safety` / `vercel-best-practices`）を渡すと、self-review は
    その reviewer を起動できない。feature-dev は code-review を参照できない（プラグイン間依存禁止）ので
    語彙を本文に書き写しており、片側だけ変わると同じずれが再発する。
    """

    SKILL = REPO / "feature-dev" / "skills" / "feature-dev" / "SKILL.md"
    FOCUS_DIR = REPO / "code-review" / "references" / "prompts" / "focus"

    def code_review_vocabulary(self) -> set[str]:
        # comment-polish は Focus テンプレートではなく comment-accuracy に連結する追加ブロック
        return {p.stem for p in self.FOCUS_DIR.glob("*.md")} - {"comment-polish"}

    def test_declared_vocabulary_matches_code_review(self):
        import re
        line = next(l for l in self.SKILL.read_text().splitlines() if "focus 名は code-review の語彙に限る" in l)
        declared = set(re.findall(r"`([a-z-]+)`", line.split("（code-review の")[0]))
        self.assertEqual(declared, self.code_review_vocabulary())

    def test_every_focus_added_in_phase_6_is_in_the_vocabulary(self):
        import re
        added = set(re.findall(r"→ (?:add|upgrade) `([a-z-]+)`", self.SKILL.read_text()))
        self.assertTrue(added, "Phase 6 Step 1 の追加ルールを拾えていない")
        self.assertLessEqual(added, self.code_review_vocabulary())


if __name__ == "__main__":
    unittest.main()
