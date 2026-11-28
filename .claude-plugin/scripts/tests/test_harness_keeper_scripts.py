#!/usr/bin/env python3
"""`harness-keeper` 同梱スクリプトの回帰テスト（CLI 境界越しの subprocess テスト）.

**なぜあるか**（GitHub issue #187）: どちらも「決定的検査で LLM 判断を代替する」ために
置かれたスクリプトなのに、テストが 1 件も無かった。壊れても cc-catch-up の実行中にしか
分からず、しかも壊れ方が「schema 違反を見逃す」「プロファイルが空で返る」なので
**LLM 側が異常に気づけない**（空の入力を受け取ってもそれらしい判断を返す）。

置き場所が `skills/*/scripts/` で、`*/scripts/**` にも `*/hooks/**` にも掛からない位置に
あったため構文検査からも漏れていた（#177 で glob を広げて解消済み）。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from git_env import scrub

ROOT =Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "harness-keeper" / "skills" / "cc-catch-up" / "scripts"
VALIDATE = SCRIPTS / "validate-state.py"
SCAN = SCRIPTS / "scan-frontmatter.sh"
INIT = SCRIPTS / "init-state-dir.sh"
SCHEMA = ROOT / "harness-keeper" / "skills" / "cc-catch-up" / "references" / "state-schema.json"


def _valid_state() -> dict:
    """schema を満たす最小の state（**期待値はテスト側で独立に組む**）."""
    return {
        "lastCatchUpVersion": "2.1.100",
        "lastCatchUpModel": "claude-opus-5",
        "lastCatchUpDate": "2026-08-28",
        "lastPruningDate": "2026-08-28",
        "appliedFeatures": [],
        "skippedFeatures": [],
        "prunedConstraints": [],
        "preservedConstraints": [],
    }


class ValidateStateTest(unittest.TestCase):
    """`validate-state.py` の exit code 契約: 0 valid / 1 違反 / 2 読めない."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _run(self, state: object, *, raw: str | None = None) -> subprocess.CompletedProcess[str]:
        p = self.dir / "state.json"
        p.write_text(raw if raw is not None else json.dumps(state, ensure_ascii=False),
                     encoding="utf-8")
        return subprocess.run(
            ["python3", str(VALIDATE), str(p), "--schema", str(SCHEMA)],
            capture_output=True, text=True, timeout=30)

    def test_a_valid_state_passes(self):
        r = self._run(_valid_state())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_missing_required_key_is_a_violation(self):
        state = _valid_state()
        del state["appliedFeatures"]
        r = self._run(state)
        self.assertEqual(r.returncode, 1, "required 欠落を通している")
        self.assertIn("appliedFeatures", r.stdout + r.stderr)

    def test_an_unknown_key_is_a_violation(self):
        """`additionalProperties: false` — schema drift をここで弾くのが目的."""
        state = _valid_state()
        state["totallyNewField"] = 1
        r = self._run(state)
        self.assertEqual(r.returncode, 1, "未知キーを通している（drift を検出できない）")

    def test_a_wrong_type_is_a_violation(self):
        state = _valid_state()
        state["appliedFeatures"] = "配列であるべき"
        self.assertEqual(self._run(state).returncode, 1)

    def test_a_broken_json_is_unreadable_not_a_violation(self):
        """壊れた JSON は 2（読めない）。1 に畳むと「直せる違反」と区別できない."""
        r = self._run(None, raw="{ not json")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_a_missing_file_is_unreadable(self):
        r = subprocess.run(
            ["python3", str(VALIDATE), str(self.dir / "none.json"), "--schema", str(SCHEMA)],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 2)

    def test_the_shipped_schema_itself_is_loadable(self):
        """schema が壊れていたら全検証が無意味になるので、それ自体を読めることを見る."""
        data = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertIn("properties", data)
        self.assertIs(data.get("additionalProperties"), False,
                      "additionalProperties が false でないと drift を弾けない")


class ScanFrontmatterTest(unittest.TestCase):
    """`scan-frontmatter.sh` は Phase 3 の入力を作る。**空を返しても LLM は気づけない**."""

    def _run(self, *args: str, cwd: Path | None = None,
             env: dict | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(SCAN), *args], capture_output=True, text=True,
                              timeout=120, cwd=str(cwd or ROOT), env=env)

    def test_the_repository_scan_returns_every_plugin(self):
        r = self._run(str(ROOT))
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        data = json.loads(r.stdout)
        expected = {p.parents[1].name for p in ROOT.glob("*/.claude-plugin/plugin.json")}
        self.assertEqual({d["plugin"] for d in data}, expected,
                         "走査対象のプラグインが欠けている（空振りに気づけない型）")

    def test_a_single_plugin_can_be_selected(self):
        r = self._run(str(ROOT), "--plugin", "adr-keeper")
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        data = json.loads(r.stdout)
        self.assertEqual([d["plugin"] for d in data], ["adr-keeper"])

    def test_the_profile_carries_frontmatter_keys(self):
        """キー抽出が空だと Phase 3 が「機能を使っていない」と誤判断する."""
        r = self._run(str(ROOT), "--plugin", "adr-keeper")
        skills = json.loads(r.stdout)[0]["skills"]
        self.assertTrue(skills, "skills が空")
        self.assertIn("allowed-tools", skills[0]["frontmatter_keys"])

    def test_an_unknown_plugin_yields_an_empty_array(self):
        """存在しない名前でも壊れた JSON を吐かない（下流が JSON パース前提）."""
        r = self._run(str(ROOT), "--plugin", "no-such-plugin")
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertEqual(json.loads(r.stdout), [])

    def test_output_is_valid_json_even_for_an_empty_repository(self):
        with tempfile.TemporaryDirectory() as t:
            r = self._run(t)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            self.assertEqual(json.loads(r.stdout), [])

    def test_without_jq_it_reports_that_it_could_not_run(self):
        """`jq` 不在は 2（判定不能）。0 で空配列を返すと「機能ゼロ」と区別できない.

        **「このディレクトリには無いはず」に頼らない**（CLAUDE.md Gotchas）— 引ける側を
        列挙して PATH を作る。
        """
        with tempfile.TemporaryDirectory() as t:
            bin_dir = Path(t)
            for name in ("bash", "grep", "sed", "awk", "cat", "find", "sort", "head", "basename",
                         "dirname", "cut", "tr", "ls"):
                real = shutil.which(name)
                if real:
                    (bin_dir / name).symlink_to(real)
            r = self._run(str(ROOT), env={"PATH": str(bin_dir)})
            self.assertEqual(r.returncode, 2, "jq 不在を緑で返している: " + r.stdout[:200])


class InitStateDirTest(unittest.TestCase):
    """`init-state-dir.sh`: state dir の用意と、追跡済みの state file の報告（GitHub issue #540）."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.state_dir = self.root / ".claude" / "harness-keeper"

    def tearDown(self):
        self._tmp.cleanup()

    def _env(self, **extra: str) -> dict[str, str]:
        # 作業中のセッションの CLAUDE_PROJECT_DIR を継承させない（既定の root が実 repo を指す）
        env = {k: v for k, v in scrub().items() if k != "CLAUDE_PROJECT_DIR"}
        env["HOME"] = str(self.root / "home")
        env.update(extra)
        return env

    def _run(self, *args: str, env: dict[str, str] | None = None):
        return subprocess.run(["bash", str(INIT), *args], capture_output=True, text=True,
                              env=env if env is not None else self._env(), timeout=30)

    def _git(self, *args: str):
        subprocess.run(["git", *args], cwd=self.root, env=self._env(), check=True,
                       capture_output=True, text=True)

    def _init_repo(self):
        self._git("init", "-q")
        self._git("config", "user.email", "t@example.com")
        self._git("config", "user.name", "t")

    def _tracked(self, out: str) -> list[str]:
        return [line.split("=", 1)[1] for line in out.splitlines() if line.startswith("tracked=")]

    def test_it_creates_the_dir_and_an_ignore_all_gitignore(self):
        r = self._run(str(self.root))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.state_dir / ".gitignore").read_text(), "*\n")
        self.assertIn(f"state_dir={self.state_dir}", r.stdout.splitlines())

    def test_an_existing_gitignore_is_left_as_is(self):
        self.state_dir.mkdir(parents=True)
        (self.state_dir / ".gitignore").write_text("own-rule\n")
        r = self._run(str(self.root))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.state_dir / ".gitignore").read_text(), "own-rule\n")

    def test_an_untracked_state_file_stays_out_of_git_status_and_is_not_reported(self):
        self._init_repo()
        r = self._run(str(self.root))
        (self.state_dir / "cc-catch-up-state.json").write_text("{}\n")
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                                cwd=self.root, env=self._env(), capture_output=True, text=True)
        self.assertEqual(status.stdout, "", "state file か .gitignore が未追跡として出ている")
        self.assertEqual(self._tracked(r.stdout), [])

    def test_a_tracked_state_file_is_reported(self):
        self._init_repo()
        self.state_dir.mkdir(parents=True)
        (self.state_dir / "cc-catch-up-state.json").write_text("{}\n")
        self._git("add", ".")
        self._git("commit", "-q", "-m", "init")
        r = self._run(str(self.root))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._tracked(r.stdout), [".claude/harness-keeper/cc-catch-up-state.json"])

    def test_a_tracked_state_file_at_the_old_path_is_reported(self):
        self._init_repo()
        old = self.root / ".claude" / "claude-meta"
        old.mkdir(parents=True)
        (old / "cc-catch-up-state.json").write_text("{}\n")
        self._git("add", ".")
        self._git("commit", "-q", "-m", "init")
        r = self._run(str(self.root))
        self.assertEqual(self._tracked(r.stdout), [".claude/claude-meta/cc-catch-up-state.json"])

    def test_a_root_outside_git_reports_nothing_and_succeeds(self):
        r = self._run(str(self.root))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._tracked(r.stdout), [])
        self.assertEqual(r.stderr, "")

    def test_without_an_argument_it_uses_claude_project_dir(self):
        project = self.root / "project"
        project.mkdir()
        r = self._run(env=self._env(CLAUDE_PROJECT_DIR=str(project)))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((project / ".claude" / "harness-keeper" / ".gitignore").is_file())
        self.assertFalse((self.root / "home" / ".claude").exists(), "HOME 側にも書いている")

    def test_an_uncreatable_dir_fails_with_exit_1(self):
        (self.root / ".claude").write_text("not a dir\n")
        r = self._run(str(self.root))
        self.assertEqual(r.returncode, 1)
        self.assertIn("FATAL", r.stderr)


if __name__ == "__main__":
    unittest.main()
