#!/usr/bin/env python3
"""hook スクリプトを CLI 境界越しに叩く共通ハーネス.

**なぜ必要か**: hook は blast radius が最大のコンポーネントで、暴発すると
**すべてのツール呼び出し**に影響する（2026-07 の push-reminder が
`if: "Bash(git push *)"` の不発で全 Bash 呼び出しに additionalContext を注入した実績）。
それなのにリポジトリ内 38 本の hook スクリプトにテストが 1 本も無かった。

`validate_plugin_quality.py` の hook-self-judge チェックは「`safe_hook_input` を
参照しているか」しか見ない。**その自己判定が実際に効くか**は実行しないと分からない。

ここでは hooks.json を経由せず**スクリプトを直接叩く**。hooks.json の matcher / if:
が評価されない環境が実在する以上、**スクリプト単体で正しく黙る**ことが要求仕様だから。
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class HookResult:
    def __init__(self, proc: subprocess.CompletedProcess[str]):
        self.returncode = proc.returncode
        self.stdout = proc.stdout
        self.stderr = proc.stderr

    @property
    def context(self) -> str | None:
        """additionalContext として注入された文字列（無ければ None）."""
        out = self.stdout.strip()
        if not out:
            return None
        try:
            data = json.loads(out)
        except ValueError:
            return None
        return data.get("hookSpecificOutput", {}).get("additionalContext")

    @property
    def fired(self) -> bool:
        return self.context is not None or bool(self.stdout.strip())

    def __repr__(self) -> str:
        return f"HookResult(rc={self.returncode}, stdout={self.stdout!r}, stderr={self.stderr!r})"


class HookTestCase(unittest.TestCase):
    """hook スクリプト 1 本を対象にするテストの基底."""

    PLUGIN = ""      # 例: "dev-workflow"
    SCRIPT = ""      # 例: "hooks/scripts/push-reminder.sh"

    @property
    def plugin_root(self) -> Path:
        return ROOT / self.PLUGIN

    def run_hook(self, payload: dict, cwd: Path | None = None,
                 env_extra: dict | None = None) -> HookResult:
        env = dict(os.environ)
        env["CLAUDE_PLUGIN_ROOT"] = str(self.plugin_root)
        env.update(env_extra or {})
        proc = subprocess.run(
            ["bash", str(self.plugin_root / self.SCRIPT)],
            input=json.dumps(payload), capture_output=True, text=True,
            cwd=str(cwd or ROOT), env=env, timeout=30,
        )
        return HookResult(proc)

    def bash_payload(self, command: str, **extra) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}, **extra}

    def assertSilent(self, res: HookResult, msg: str = ""):
        """**何も注入しない**こと。hook の既定はこちら（暴発の反対側）."""
        self.assertEqual(res.stdout.strip(), "", f"注入してはいけない: {msg or res!r}")

    def assertFired(self, res: HookResult, contains: str = ""):
        ctx = res.context
        self.assertIsNotNone(ctx, f"注入されるはず: {res!r}")
        if contains:
            self.assertIn(contains, ctx)


class TempGitRepo:
    """使い捨ての git リポジトリ（hook が git を叩くので本物が要る）."""

    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name)
        for args in (["init", "-q"], ["config", "user.email", "t@example.com"],
                     ["config", "user.name", "t"]):
            subprocess.run(["git", *args], cwd=self.path, capture_output=True)
        return self.path

    def __exit__(self, *exc):
        self._tmp.cleanup()

    def commit(self, message: str, filename: str = "f.txt", body: str = "x") -> str:
        (self.path / filename).write_text(body)
        subprocess.run(["git", "add", "-A"], cwd=self.path, capture_output=True)
        subprocess.run(["git", "commit", "-qm", message], cwd=self.path, capture_output=True)
        return subprocess.run(["git", "log", "-1", "--format=%h"], cwd=self.path,
                              capture_output=True, text=True).stdout.strip()
