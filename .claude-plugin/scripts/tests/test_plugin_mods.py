#!/usr/bin/env python3
"""プラグインの mod（`hooks/hooks.json` の `modules`）を `claude plugin test` で走らせる.

mod のテスト（`*.test.ts`）は `claude-code/testing` を import し、`claude plugin test <dir>` が
プラグインのフォルダの中から拾う。**配布物にテストを混ぜない**（リポジトリの規約）ので、
テストは `mods/<plugin>/` にプラグインと同じ相対パスで置き、ここでプラグインの複製へ重ねて走らせる。

`claude` が無い環境では skip する。CI は CLI を入れたうえで `CLAUDE_PLUGIN_TEST_REQUIRED=1` を立て、
skip を失敗に変える（入れ損ねたまま緑になるのを防ぐ）。
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

ROOT = Path(__file__).resolve().parents[3]
MODS = Path(__file__).resolve().parent / "mods"
REQUIRED = os.environ.get("CLAUDE_PLUGIN_TEST_REQUIRED") == "1"


def plugins_with_modules() -> list[str]:
    names = []
    for hooks in sorted(ROOT.glob("*/hooks/hooks.json")):
        if json.loads(hooks.read_text(encoding="utf-8")).get("modules"):
            names.append(hooks.parent.parent.name)
    return names


class PluginModTest(unittest.TestCase):
    def test_every_mod_has_tests(self):
        plugins = plugins_with_modules()
        self.assertTrue(plugins, "modules を持つプラグインが見つからない（探し方が壊れている）")
        for plugin in plugins:
            with self.subTest(plugin):
                self.assertTrue(list((MODS / plugin).rglob("*.test.ts*")),
                                f"{plugin} の mod にテストが無い（{MODS / plugin} に置く）")

    def test_every_test_overlay_names_a_plugin(self):
        for overlay in sorted(p for p in MODS.iterdir() if p.is_dir()):
            with self.subTest(overlay.name):
                self.assertTrue((ROOT / overlay.name / ".claude-plugin" / "plugin.json").is_file(),
                                f"mods/{overlay.name} に対応するプラグインが無い")

    def test_mods_pass_claude_plugin_test(self):
        claude = shutil.which("claude")
        if claude is None:
            if REQUIRED:
                self.fail("claude CLI が無い（CLAUDE_PLUGIN_TEST_REQUIRED=1）")
            self.skipTest("claude CLI 未導入（CI では npm で入れる）")
        # 開発機のセッションの値を持ち込まない（プラグインが自分のフォルダ以外を読みに行く）
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT")}
        for overlay in sorted(p for p in MODS.iterdir() if p.is_dir()):
            with self.subTest(overlay.name), tempfile.TemporaryDirectory() as d:
                dst = Path(d) / overlay.name
                shutil.copytree(ROOT / overlay.name, dst, ignore=shutil.ignore_patterns("__pycache__", "evals"))
                shutil.copytree(overlay, dst, dirs_exist_ok=True)
                res = subprocess.run([claude, "plugin", "test", str(dst)], capture_output=True, text=True,
                                     env=env, stdin=subprocess.DEVNULL, timeout=300)
                out = res.stdout + res.stderr
                self.assertEqual(res.returncode, 0, out)
                self.assertRegex(out, r"\b[1-9]\d* pass\b", "1 件も走っていない")
                self.assertIsNone(re.search(r"\b[1-9]\d* fail\b", out), out)


if __name__ == "__main__":
    unittest.main()
