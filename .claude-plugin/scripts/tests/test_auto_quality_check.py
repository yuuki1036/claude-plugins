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

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude-plugin" / "scripts" / "auto-quality-check.sh"
SAFE_HOOK = ROOT / ".claude-plugin" / "lib" / "safe-hook.sh"

# git が hook 実行時に渡す変数（`GIT_INDEX_FILE=.git/index` の**相対パス**等）を落とす。
# 本スイートは pre-commit からも走るので、残すと使い捨てリポジトリで外側の index を掴む
GIT_HOOK_ENV = ("GIT_DIR", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE",
                "GIT_PREFIX", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_QUARANTINE_PATH", "GIT_REFLOG_ACTION", "GIT_EDITOR")

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
        (self.root / ".claude-plugin" / "lib").mkdir(parents=True)
        self.scripts = self.root / ".claude-plugin" / "scripts"
        self.scripts.mkdir(parents=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
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
        env = {k: v for k, v in os.environ.items() if k not in GIT_HOOK_ENV}
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
        env = {k: v for k, v in os.environ.items() if k not in GIT_HOOK_ENV}
        if with_encoder:
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

    def test_stdin_is_consumed_so_the_hook_cannot_hang(self):
        """hook は stdin を消費してから処理を始める（消費しないとハングする）."""
        payload = json.dumps({"hook_event_name": "Stop", "transcript": "x" * 200_000})
        res = self.run_hook(payload=payload)   # timeout で落ちなければ消費できている
        self.assertEqual(res.returncode, 0, res.stderr)


if __name__ == "__main__":
    unittest.main()
