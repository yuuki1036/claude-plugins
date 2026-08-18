#!/usr/bin/env python3
"""guardrail-protect の判定本体（`detect-commit-bypass.pl`）と PreToolUse hook の回帰テスト.

**なぜ厚く見るか**: これは「commit をブロックするか」を決める唯一の判定で、
壊れ方が両方向に致命的:

- 検出漏れ → ガードが**黙って**無効化される（`--no-verify` が通る。気づく契機が無い）
- 誤検出 → 正当な commit が止まる（メッセージに `--no-verify` と書いただけで落ちる）

しかもこのファイルは「引用符=メッセージ」という素朴前提を廃するために自前の
シェル準拠トークナイザを持っている。テストが 1 本も無い状態で置いておく代物ではない。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from hook_harness import HookTestCase, ROOT

DETECTOR = ROOT / "guardrail-protect" / "hooks" / "scripts" / "detect-commit-bypass.pl"


class DetectorTest(unittest.TestCase):
    """perl 判定器を単体で叩く（stdout に理由が出れば検出）."""

    def detect(self, command: str) -> str:
        proc = subprocess.run(["perl", str(DETECTOR)], input=command,
                              capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, "呼び出し側の set -e を踏まないため常に exit 0")
        return proc.stdout.strip()

    def assertBypass(self, command: str):
        self.assertNotEqual(self.detect(command), "", f"検出されるべき: {command}")

    def assertClean(self, command: str):
        self.assertEqual(self.detect(command), "", f"誤検出: {command}")

    # --- 検出すべき（漏らすとガードが無言で外れる） ---
    def test_no_verify_long(self):
        self.assertBypass("git commit --no-verify -m 'x'")

    def test_no_verify_git_abbreviations(self):
        """git はオプションの一意な前方一致を受け付ける."""
        for flag in ("--no-ver", "--no-veri", "--no-verif"):
            with self.subTest(flag=flag):
                self.assertBypass(f"git commit {flag} -m 'x'")

    def test_short_n(self):
        self.assertBypass("git commit -n -m 'x'")

    def test_short_flag_cluster(self):
        for cmd in ("git commit -nm 'x'", "git commit -anm 'x'"):
            with self.subTest(cmd=cmd):
                self.assertBypass(cmd)

    def test_hooks_path_override(self):
        for cmd in ("git -c core.hooksPath=/dev/null commit -m 'x'",
                    "git -c 'core.hooksPath=/tmp/empty' commit -m 'x'"):
            with self.subTest(cmd=cmd):
                self.assertBypass(cmd)

    def test_nested_shell(self):
        for cmd in ("""bash -c 'git commit --no-verify -m x'""",
                    '''sh -c "git commit -n -m x"'''):
            with self.subTest(cmd=cmd):
                self.assertBypass(cmd)

    def test_command_prefix(self):
        for cmd in ("command git commit --no-verify -m x", r"\git commit --no-verify -m x"):
            with self.subTest(cmd=cmd):
                self.assertBypass(cmd)

    def test_line_continuation(self):
        self.assertBypass("git commit \\\n  --no-verify -m x")

    def test_quoted_flag_is_still_a_flag(self):
        """引用符で包んでも迂回は迂回（引用符=メッセージという素朴前提を廃す要）."""
        self.assertBypass("""git commit '--no-verify' -m x""")

    # --- 誤検出してはいけない（正当な commit を止めない） ---
    def test_message_mentioning_the_flag(self):
        for cmd in ("""git commit -m '--no-verify を使わない理由'""",
                    '''git commit -m "hook 迂回 (--no-verify) を禁止した"''',
                    """git commit -m 'fix: -n の誤爆を直す'"""):
            with self.subTest(cmd=cmd):
                self.assertClean(cmd)

    def test_value_taking_options_consume_next_token(self):
        """-m/-F/-C/-t は次のトークンを値として食う（そこに -n があっても値）."""
        for cmd in ("git commit -m -n", "git commit -F -n", "git commit -C -n"):
            with self.subTest(cmd=cmd):
                self.assertClean(cmd)

    def test_other_commands_with_n_flag(self):
        """複合コマンドの別セグメントの -n を誤爆しない."""
        for cmd in ("git commit -m x && git log -n 5",
                    "git log -n 5",
                    "tail -n 20 file.txt",
                    "git commit -m x; head -n 3 README.md"):
            with self.subTest(cmd=cmd):
                self.assertClean(cmd)

    def test_plain_commit(self):
        for cmd in ("git commit -m 'feat: x'", "git commit", "git add -A && git commit -m x"):
            with self.subTest(cmd=cmd):
                self.assertClean(cmd)

    def test_unrelated_commands(self):
        for cmd in ("ls -la", "npm test", "git push --force", ""):
            with self.subTest(cmd=cmd):
                self.assertClean(cmd)

    def test_config_file_tampering(self):
        """guardrail-protect.json 自体の改変を検出する（自己保護）."""
        for cmd in ("echo '{}' > .claude/guardrail-protect.json",
                    "rm .claude/guardrail-protect.json",
                    "sed -i '' 's/true/false/' .claude/guardrail-protect.json"):
            with self.subTest(cmd=cmd):
                self.assertBypass(cmd)


class PreCommitGuardTest(HookTestCase):
    """hook 本体: 検出時に exit 2 でブロックし、それ以外は素通りする."""

    PLUGIN = "guardrail-protect"
    SCRIPT = "hooks/scripts/pre-commit-guard.sh"

    def test_blocks_bypass(self):
        res = self.run_hook(self.bash_payload("git commit --no-verify -m x"))
        self.assertEqual(res.returncode, 2, "ブロックするべき")
        self.assertIn("Refusing to bypass git hooks", res.stderr)

    def test_allows_normal_commit(self):
        res = self.run_hook(self.bash_payload("git commit -m 'feat: x'"))
        self.assertEqual(res.returncode, 0)
        self.assertSilent(res)

    def test_allows_unrelated_command(self):
        for cmd in ("ls", "npm test", "git push"):
            with self.subTest(cmd=cmd):
                res = self.run_hook(self.bash_payload(cmd))
                self.assertEqual(res.returncode, 0)
                self.assertSilent(res)

    def test_message_mentioning_flag_is_allowed(self):
        res = self.run_hook(self.bash_payload("git commit -m '--no-verify は使わない'"))
        self.assertEqual(res.returncode, 0, f"正当な commit を止めた: {res.stderr}")

    def test_empty_command_is_ignored(self):
        self.assertEqual(self.run_hook({"tool_name": "Bash", "tool_input": {}}).returncode, 0)

    def test_malformed_input_does_not_block(self):
        """壊れた入力で**ブロック側に倒れない**（作業が止まる方が高コスト）."""
        self.assertEqual(self.run_hook({}).returncode, 0)


if __name__ == "__main__":
    unittest.main()
