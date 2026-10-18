#!/usr/bin/env python3
"""issue-workflow の他プラグインの導入判定（scripts/plugin-enabled.sh への寄せ）を守るテスト.

キーの有無だけを見る grep（`grep -q '"<plugin>@' "$HOME/.claude/settings.json"`）は、`false` で
無効化したプラグインを有効と誤り、project / local だけで有効化したものを取りこぼす。14 か所を
scripts/plugin-enabled.sh に寄せたので、同じ書き方が戻ってこないことと、判定値を出力に出す形
（Bash の状態は呼び出しをまたいで残らないので、代入だけではモデルが値を読めない）を固定する。
判定そのものの振る舞いは正本 .claude-plugin/lib/plugin-enabled.sh を test_feature_dev_scripts.py が見る。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PLUGIN = REPO / "issue-workflow"
SCRIPT = PLUGIN / "scripts" / "plugin-enabled.sh"

KEY_ONLY = re.compile(r"""grep -q '"[a-z0-9-]+@'""")
INLINE_OR = re.compile("grep -Eq '\"[a-z0-9-]+@" + re.escape('[^"]*'))
FENCE = re.compile(r"^\s*```")


def docs() -> list[Path]:
    """モデルが Read して手順として実行する md（hook スクリプトは対象外）."""
    return sorted(p for sub in ("skills", "commands", "references")
                  for p in (PLUGIN / sub).rglob("*.md"))


def fenced_lines(path: Path):
    inside = False
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if FENCE.match(line):
            inside = not inside
            continue
        if inside:
            yield i, line


class NoKeyOnlyDetectionTest(unittest.TestCase):
    def test_key_only_grep_does_not_come_back(self):
        hits = [f"{p.relative_to(REPO)}:{i}" for p in docs()
                for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                if KEY_ONLY.search(line) or INLINE_OR.search(line)]
        self.assertEqual(hits, [], "導入判定は scripts/plugin-enabled.sh を使う（キーの有無・OR の判定は false を無視する）")

    def test_the_scan_still_finds_the_call_sites(self):
        """走査対象が空になって黙って通るのを防ぐ（呼び出しを持つ 9 ファイルのうち 8 以上）."""
        files = {p for p in docs() if "scripts/plugin-enabled.sh" in p.read_text(encoding="utf-8")}
        self.assertGreaterEqual(len(files), 8, sorted(str(f.relative_to(REPO)) for f in files))


class CallPrintsTheValueTest(unittest.TestCase):
    def test_fenced_calls_echo_the_value(self):
        bad = []
        for p in docs():
            for i, line in fenced_lines(p):
                runs = "plugin-enabled.sh" in line and not re.match(r'\s*P="\$\{CLAUDE_PLUGIN_ROOT\}/scripts/plugin-enabled\.sh"\s*$', line)
                if (runs or 'bash "$P"' in line) and 'echo "' not in line:
                    bad.append(f"{p.relative_to(REPO)}:{i}: {line.strip()}")
        self.assertEqual(bad, [], "判定値を echo で出力に出す（代入だけだと次の Bash 呼び出しで値が消える）")


class ReplicaSmokeTest(unittest.TestCase):
    """issue-workflow の複製そのものが動くこと（正本との byte 一致は BYTE_REPLICAS が見る）."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name) / "home"
        self.proj = Path(tmp.name) / "proj"
        for base in (self.home, self.proj):
            (base / ".claude").mkdir(parents=True)

    def write(self, base: Path, name: str, plugins: dict[str, bool]) -> None:
        body = {"enabledPlugins": {f"{k}@mkt": v for k, v in plugins.items()}}
        (base / ".claude" / name).write_text(json.dumps(body, indent=2))

    def state(self, plugin: str) -> str:
        # 実機の HOME / CLAUDE_PROJECT_DIR を継承すると本物の settings を読む
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.proj)}
        res = subprocess.run(["bash", str(SCRIPT), plugin], capture_output=True, text=True, env=env)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout.strip()

    def test_disabled_in_user_settings_is_0(self):
        self.write(self.home, "settings.json", {"code-review": False})
        self.assertEqual(self.state("code-review"), "0")

    def test_enabled_only_in_project_is_1(self):
        self.write(self.proj, "settings.json", {"dev-workflow": True})
        self.assertEqual(self.state("dev-workflow"), "1")

    def test_local_false_overrides_user_true(self):
        self.write(self.home, "settings.json", {"writing-polish": True})
        self.write(self.proj, "settings.local.json", {"writing-polish": False})
        self.assertEqual(self.state("writing-polish"), "0")


if __name__ == "__main__":
    unittest.main()
