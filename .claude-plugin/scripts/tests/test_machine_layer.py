#!/usr/bin/env python3
"""`machine-layer.sh` の回帰テスト（GitHub issue #137）.

**exit code が契約**（0 = 緑 / 1 = 検出 / 2 = 判定不能）で、呼び出し側はこれで分岐する:

- Stop hook（`auto-quality-check.sh`）… 1 は問題として通知、2 は「判定不能」として通知
- self-review 前段（`run-oracles.sh` ← `.claude/review-oracles.sh`）… 2 を green に倒さない

**2 を 0 と混ぜると「機械層が死んでいる」と「通っている」が区別できない**ので、
そこを中心に固定する。検査本体は実行に数分かかるため、`MACHINE_LAYER_ROOT` で
stub を置いた使い捨てリポジトリに向けて契約だけを見る。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude-plugin" / "scripts" / "machine-layer.sh"

STUB_OK = "#!/usr/bin/env bash\nexit 0\n"


class MachineLayerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self.scripts = self.root / ".claude-plugin" / "scripts"
        self.scripts.mkdir(parents=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        # 既定はすべて通る stub（テストごとに必要なものだけ差し替える）
        self.write_stub("validate-ssot.sh", STUB_OK)
        self.write_stub("validate_plugin_quality.py", "import sys\nsys.exit(0)\n")
        # 回帰テストの起動口は本物を使う（stub にすると「テストを実際に走らせて
        # 失敗を拾う」という検査 3（回帰テスト）の要件そのものが検証されなくなる）
        shutil.copy2(ROOT / ".claude-plugin" / "scripts" / "run-tests.py",
                     self.scripts / "run-tests.py")

    def write_stub(self, name: str, body: str) -> Path:
        p = self.scripts / name
        p.write_text(body, encoding="utf-8")
        p.chmod(0o755)
        return p

    def with_tests_dir(self, passing: bool = True) -> None:
        """`unittest discover` の対象を置く（`python3 -m unittest` を実際に走らせる）."""
        d = self.scripts / "tests"
        d.mkdir(exist_ok=True)
        # 本物の `run-tests.py` は起動口で git hook 由来の env を落とすのに `git_env` を読む
        shutil.copy2(Path(__file__).resolve().parent / "git_env.py", d / "git_env.py")
        body = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n"
        body += "        self.assertTrue(True)\n" if passing else "        self.fail('わざと失敗')\n"
        (d / "test_stub.py").write_text(body, encoding="utf-8")

    def env(self, with_python: bool = True, with_claude: bool = False) -> dict[str, str]:
        """PATH を絞った環境を作る（本物の `claude` を引くと実リポジトリの検査が走る）.

        **「このディレクトリには無いはず」に頼らない。** Linux では `/bin` が `/usr/bin` の
        symlink なので、`/bin` を混ぜると python3 が引けてしまう（実測: `with_python=False`
        の 2 件が ubuntu でだけ落ちた）。**引けるものを列挙する**側で作る。
        """
        env = dict(os.environ)
        env["MACHINE_LAYER_ROOT"] = str(self.root)
        link = self.bin / "python3"
        if with_python:
            if not link.exists():
                link.symlink_to(sys.executable)
        else:
            link.unlink(missing_ok=True)
        # bash は常に要る。section 4（CLI スキーマ検査）は find / xargs / grep / sort /
        # basename を使うので、python3 がある構成だけそれらを足す
        needed = ["bash"]
        if with_python:
            needed += ["find", "xargs", "grep", "sort", "basename", "tail", "dirname"]
        for name in needed:
            real = shutil.which(name)
            self.assertIsNotNone(real, "%s が見つからない" % name)
            dest = self.bin / name
            if not dest.exists():
                dest.symlink_to(real)
        env["PATH"] = str(self.bin)
        if with_claude:
            self.write_claude_stub()
        return env

    def write_claude_stub(self, *findings: str) -> None:
        """`claude` の stub。指摘を渡せば manifest の error として rc=1 で返す."""
        if findings:
            self.write_claude_json_stub(1, errors=[self.item(f) for f in findings])
        else:
            self.write_claude_json_stub(0)

    @staticmethod
    def item(text: str) -> dict[str, object]:
        """`path: message` を `--json` の 1 件（`{path, message, code}`）にする."""
        path, _, message = text.partition(": ")
        return {"path": path, "message": message, "code": None}

    def write_claude_json_stub(self, code: int, errors: list | None = None,
                               warnings: list | None = None, contents: list | None = None,
                               notes: list | None = None) -> None:
        """`claude plugin validate --json` の stub。**形は CC 2.1.328 の実物に合わせる**.

        指摘は `manifest` と `contents[]`（ファイルごと）の `errors` / `warnings`。
        `notes`（mod の一覧）と `directory.findings`（ICON_MISSING）は件数に入らない
        """
        report = {
            "success": code == 0, "strict": False, "target": "demo/.claude-plugin/plugin.json",
            "manifest": {"file": "demo/.claude-plugin/plugin.json", "type": "plugin",
                         "errors": errors or [], "warnings": warnings or [],
                         "notes": notes or [], "gatingHooks": [], "wasm": [], "modules": []},
            "contents": contents or [],
            "directory": {"findings": [{"code": "ICON_MISSING", "severity": "warning",
                                        "message": "No icon found in the plugin."}]},
        }
        self.write_claude_raw_stub(code, json.dumps(report, ensure_ascii=False))

    def write_claude_raw_stub(self, code: int, stdout: str, stderr: str = "") -> None:
        """出力をそのまま返す `claude` stub。**bash builtin だけで書く**（PATH を絞るので `cat` は引けない）.

        実測: `cat <<EOF` の stub が `cat: command not found` で落ち、出力が空になったため
        「指摘なし」と区別できなかった。stub が壊れていても**テストは緑に見える**型なので、
        `test_..._reported_per_plugin` の assert が唯一の防壁になる。
        `--json` を付けずに呼ばれたら exit 64 で落ちる（表示を読む実装に戻ると判定不能になる）
        """
        def quote(text: str) -> str:
            return "'%s'" % text.replace("'", "'\\''")
        stub = self.bin / "claude"
        stub.write_text(
            "#!/usr/bin/env bash\n"
            "[ \"$3\" = --json ] || { printf '%%s\\n' 'no --json' >&2; exit 64; }\n"
            "printf '%%s\\n' %s\nprintf '%%s' %s >&2\nexit %d\n"
            % (quote(stdout), quote(stderr), code), encoding="utf-8")
        stub.chmod(0o755)

    def run_layer(self, env: dict[str, str] | None = None, args: tuple[str, ...] = ()
                  ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(SCRIPT), *args], cwd=str(self.root),
                              capture_output=True, text=True, env=env or self.env(), timeout=120)

    # ---- exit code の契約 --------------------------------------------------
    def test_all_green_exits_0_with_no_output(self):
        self.with_tests_dir(passing=True)
        res = self.run_layer()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(res.stdout, "", "緑のときは何も出さない（no-op を報告しない）")

    def test_ssot_failure_exits_1_and_reports(self):
        self.write_stub("validate-ssot.sh",
                        "#!/usr/bin/env bash\necho 'marketplace が同期していない'\nexit 1\n")
        self.with_tests_dir(passing=True)
        res = self.run_layer()
        self.assertEqual(res.returncode, 1)
        self.assertIn("marketplace が同期していない", res.stdout)

    def test_quality_failure_exits_1_and_reports(self):
        self.write_stub("validate_plugin_quality.py",
                      "print('allowed-tools が一致しない')\nimport sys; sys.exit(1)\n")
        self.with_tests_dir(passing=True)
        res = self.run_layer()
        self.assertEqual(res.returncode, 1)
        self.assertIn("allowed-tools が一致しない", res.stdout)

    def test_failing_tests_exit_1_and_are_labelled(self):
        self.with_tests_dir(passing=False)
        res = self.run_layer()
        self.assertEqual(res.returncode, 1)
        self.assertIn("[unit-tests]", res.stdout)

    # ---- --no-tests（self-review 前段の宣言が使う） --------------------------
    def test_no_tests_skips_the_regression_tests(self):
        """回帰テストが赤でも走らせない（全体で 12 分かかり、前段の 300 秒に収まらない）."""
        self.with_tests_dir(passing=False)
        res = self.run_layer(args=("--no-tests",))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn("[unit-tests]", res.stdout)

    def test_no_tests_still_reports_static_findings(self):
        """外すのは回帰テストだけ。静的検査の検出まで黙らせない."""
        self.write_stub("validate_plugin_quality.py",
                        "print('allowed-tools が一致しない')\nimport sys; sys.exit(1)\n")
        self.with_tests_dir(passing=True)
        res = self.run_layer(args=("--no-tests",))
        self.assertEqual(res.returncode, 1)
        self.assertIn("allowed-tools が一致しない", res.stdout)

    def test_no_tests_still_reports_an_unknown_verdict(self):
        self.write_stub("validate-ssot.sh",
                        "#!/usr/bin/env bash\necho 'jsonschema が無い'\nexit 2\n")
        res = self.run_layer(args=("--no-tests",))
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)

    def test_an_unknown_argument_is_unknown_not_a_full_run(self):
        """綴りを誤った引数で全検査（回帰テスト込み）に倒さない."""
        self.with_tests_dir(passing=False)
        res = self.run_layer(args=("--no-test",))
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("--no-test", res.stderr)
        self.assertNotIn("[unit-tests]", res.stdout)

    def test_ssot_unknown_verdict_is_not_reported_as_a_detection(self):
        """子の exit 2 を 1 に混ぜない（「直せるもの」と「判定できなかった」は別物）.

        `validate-ssot.sh` は jsonschema が無いと 2 を返す。ここで 1 に倒すと
        「品質問題あり」として通知され、直せない指摘が指摘欄に出る。
        """
        self.write_stub("validate-ssot.sh",
                        "#!/usr/bin/env bash\necho 'jsonschema が無い' >&2\nexit 2\n")
        self.with_tests_dir(passing=True)
        res = self.run_layer()
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("判定不能", res.stdout)
        self.assertIn("jsonschema が無い", res.stdout)

    def test_unknown_verdict_wins_over_detections(self):
        """判定不能と検出が同居したら 2（機械層を信用してよいかが呼び出し側の関心）."""
        self.write_stub("validate-ssot.sh", "#!/usr/bin/env bash\nexit 2\n")
        self.write_stub("validate_plugin_quality.py",
                        "print('allowed-tools が一致しない')\nimport sys; sys.exit(1)\n")
        self.with_tests_dir(passing=True)
        res = self.run_layer()
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("判定不能", res.stdout)
        self.assertIn("allowed-tools が一致しない", res.stdout, "検出内容も捨てない")

    def test_a_check_that_could_not_run_is_unknown_not_a_detection(self):
        """検査 2 / 3 の「実行できなかった」も 1 に畳まない（GitHub issue #140 / M5）.

        スクリプト不在（python の exit 2 / 127）を「品質問題あり」として通知すると、
        直せないものが指摘欄に出る。検査 1 だけに入れていた区別を全検査へ揃える。
        """
        cases = (("validate_plugin_quality.py", "品質検査が判定不能"),
                 ("run-tests.py", "回帰テストが判定不能"))
        for name, fragment in cases:
            with self.subTest(script=name):
                self.setUp()
                self.with_tests_dir(passing=True)
                (self.scripts / name).unlink()   # 実行できない状態にする
                res = self.run_layer()
                self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
                self.assertIn(fragment, res.stdout)

    def test_a_leaked_process_warning_is_not_swallowed(self):
        """`run-tests.py` の残留警告は **rc=0 でも捨てない**（#140 / M4）.

        残留は exit code に載らない契約なので、rc だけ見ていると Stop hook と
        self-review 前段の 2 経路で #140 の検出が丸ごと消える。
        """
        self.with_tests_dir(passing=True)
        self.write_stub("run-tests.py",
                        "import sys\n"
                        "print('[run-tests:leak] テスト終了後に 2 個のプロセスが残っている: 1, 2',"
                        " file=sys.stderr)\n"
                        "sys.exit(0)\n")
        res = self.run_layer()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("残っている", res.stdout)

    def test_missing_python_exits_2_not_0(self):
        """**「判定不能」を「通過」に倒さない.**

        python3 が無いと品質検査と回帰テストが走らないので、0 を返すと
        「機械層が通った」と読まれる（緑と欠測の区別が消える）。
        """
        res = self.run_layer(env=self.env(with_python=False))
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("python3", res.stderr)

    def test_missing_python_still_reports_what_it_managed_to_find(self):
        """判定不能でも、そこまでに検出したものは捨てない."""
        self.write_stub("validate-ssot.sh", "#!/usr/bin/env bash\necho 'SSoT NG'\nexit 1\n")
        res = self.run_layer(env=self.env(with_python=False))
        self.assertEqual(res.returncode, 2)
        self.assertIn("SSoT NG", res.stdout)

    def test_unreachable_root_exits_2(self):
        env = dict(os.environ, MACHINE_LAYER_ROOT=str(self.root / "no-such-dir"))
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 2)
        self.assertIn("FATAL", res.stderr)

    # ---- CLI スキーマ検査（`claude` があるときだけ） ------------------------
    def test_schema_findings_are_reported_per_plugin(self):
        (self.root / "demo" / ".claude-plugin").mkdir(parents=True)
        (self.root / "demo" / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
        self.with_tests_dir(passing=True)
        env = self.env(with_claude=True)
        self.write_claude_stub("name: 必須フィールドが無い")
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("[schema:demo]", res.stdout)

    def _demo(self) -> dict[str, str]:
        (self.root / "demo" / ".claude-plugin").mkdir(parents=True)
        (self.root / "demo" / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
        self.with_tests_dir(passing=True)
        return self.env(with_claude=True)

    def test_ssot_only_warnings_are_filtered_out(self):
        """`_requirements` / `_superseded_by` は独自フィールドなので警告から除外する（`path` で見る）."""
        env = self._demo()
        self.write_claude_json_stub(0, warnings=[
            self.item("_requirements: Unknown field '_requirements'. Claude Code ignores it at load time."),
            self.item("_superseded_by: Unknown field '_superseded_by'.")])
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertEqual(res.stdout, "")

    def test_a_message_naming_requirements_is_not_filtered_out(self):
        """除外は `path` で決める。文言に `_requirements` を含むだけの別の指摘は落とさない."""
        env = self._demo()
        self.write_claude_json_stub(0, warnings=[self.item("author: _requirements の隣に置く")])
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("author: _requirements の隣に置く", res.stdout)

    def test_other_warnings_are_reported(self):
        """`_requirements` 以外の warning は rc=0 でも検出（exit 1）."""
        env = self._demo()
        self.write_claude_json_stub(0, warnings=[
            self.item("_requirements: Unknown field '_requirements'."),
            self.item("author: 推奨フィールドが無い")])
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("[schema:demo] author: 推奨フィールドが無い", res.stdout)
        self.assertNotIn("_requirements", res.stdout)

    def test_findings_in_contents_are_reported(self):
        """hooks.json など manifest 以外のファイルの指摘は `contents[]` に入る."""
        env = self._demo()
        self.write_claude_json_stub(0, contents=[
            {"file": "demo/hooks/hooks.json", "type": "hooks", "errors": [], "warnings": [],
             "notes": ["./mod.ts hooks: session.start"]},
            {"file": "demo/hooks/lib.ts", "type": "module", "errors": [],
             "warnings": [self.item("line 86, column 57: error TS2532: Object is possibly 'undefined'.")]}])
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 1, res.stdout)
        # どのファイルの指摘かが分かるよう、プラグインからの相対パスが頭に付く
        self.assertIn("hooks/lib.ts: line 86, column 57: error TS2532", res.stdout)
        self.assertNotIn("mod.ts", res.stdout)

    def test_errors_and_warnings_are_both_reported(self):
        env = self._demo()
        self.write_claude_json_stub(1, errors=[self.item("name: 予約名"), self.item("version: 不正")],
                                    warnings=[self.item("author: 推奨")])
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 1, res.stdout)
        for want in ("name: 予約名", "version: 不正", "author: 推奨"):
            self.assertIn(want, res.stdout)

    def test_notes_and_directory_findings_are_not_findings(self):
        """mod の一覧（notes）と配布先の検査（ICON_MISSING）は「修正の必要な問題」にしない.

        CC 2.1.292 で表示の情報行を拾い、毎ターン Stop hook に載り続けた
        """
        env = self._demo()
        self.write_claude_json_stub(0, notes=["./mod.ts hooks: session.start, tool.call{tool=Bash}",
                                              "./mod.ts env reads: HOME"])
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(res.stdout, "")

    def test_broken_json_is_unknown_not_green(self):
        """JSON として読めなければ判定不能（exit 2）。rc=0 でも緑に倒さない."""
        env = self._demo()
        self.write_claude_raw_stub(0, '{"manifest": {"errors": [')
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 2, res.stdout)
        self.assertIn("JSON として読めなかった", res.stdout)

    def test_json_without_a_manifest_is_unknown(self):
        """形が違う JSON（`manifest` が無い）も判定不能。指摘 0 件として読まない."""
        env = self._demo()
        self.write_claude_raw_stub(0, json.dumps({"success": True}))
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 2, res.stdout)

    def test_an_old_cli_without_json_is_unknown(self):
        """`--json` を知らない古い claude（CC 2.1.259 より前）は判定不能。stderr を添える."""
        env = self._demo()
        self.write_claude_raw_stub(1, "", "error: unknown option '--json'")
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 2, res.stdout)
        self.assertIn("unknown option '--json'", res.stdout)

    def test_a_failing_cli_that_reports_nothing_is_unknown_not_green(self):
        """rc を捨てない（GitHub issue #176）: rc が非ゼロなのに指摘が 0 件なら判定不能（exit 2）."""
        env = self._demo()
        self.write_claude_json_stub(1)
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 2, "rc を捨てて緑に倒している: " + res.stdout)
        self.assertIn("指摘が 0 件", res.stdout)

    def test_a_successful_cli_with_no_findings_stays_green(self):
        """rc=0 で指摘も無ければ緑（判定不能に倒しすぎない）."""
        env = self._demo()
        self.write_claude_json_stub(0)
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(res.stdout, "")

    def test_missing_claude_cli_does_not_make_the_whole_run_unknown(self):
        """`claude` が無い環境ではこの検査だけ skip（1〜3 は判定済みなので 0 でよい）."""
        self.with_tests_dir(passing=True)
        res = self.run_layer(env=self.env(with_claude=False))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_every_plugin_is_validated_not_just_the_first(self):
        """空行スキップを「非空スキップ」に取り違えると**全件が黙って飛ぶ**."""
        for name in ("alpha", "beta"):
            (self.root / name / ".claude-plugin").mkdir(parents=True)
            (self.root / name / ".claude-plugin" / "plugin.json").write_text(
                "{}", encoding="utf-8")
        self.with_tests_dir(passing=True)
        env = self.env(with_claude=True)
        self.write_claude_stub("name: 必須フィールドが無い")
        res = self.run_layer(env=env)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("[schema:alpha]", res.stdout)
        self.assertIn("[schema:beta]", res.stdout)


if __name__ == "__main__":
    unittest.main()
