#!/usr/bin/env python3
"""`validate-ssot.sh` / `validate_ssot.py` の回帰テスト（GitHub issue #139）.

**この検査の危ない壊れ方は「no-op なのに passed と出る」**: 対象ファイルが消える・
前提ライブラリが無い・照合パターンが効かなくなる、のどれでも**出力は緑のまま**になる。
実際に jsonschema 不在時のスキーマ検証 silent skip を踏んでおり、CI に
`pip install jsonschema` を足した経緯がある（#140 の「pre-commit と CI の環境差」）。

**対象は実物をコピーしたもの**: `ROOT` はスクリプト自身の位置から決まるので、使い捨ての
リポジトリに置けばそこを検査する（本番コードにテスト専用の差し替え口を足さずに隔離できる）。
実リポジトリを検査すると「今の repo が緑かどうか」を測ることになり、検査の**能力**は測れない。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SH = ROOT / ".claude-plugin" / "scripts" / "validate-ssot.sh"
PY = ROOT / ".claude-plugin" / "scripts" / "validate_ssot.py"
SCHEMA_DIR = ROOT / ".claude-plugin" / "schema"

try:
    import jsonschema  # noqa: F401
    HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover - 環境依存
    HAS_JSONSCHEMA = False


def manifest(name: str, version: str = "1.0.0") -> dict:
    return {"name": name, "version": version, "description": "%s の説明" % name,
            "author": {"name": "t"}}


class ValidateSsotTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        scripts = self.root / ".claude-plugin" / "scripts"
        scripts.mkdir(parents=True)
        shutil.copy2(SH, scripts / "validate-ssot.sh")
        shutil.copy2(PY, scripts / "validate_ssot.py")
        shutil.copytree(SCHEMA_DIR, self.root / ".claude-plugin" / "schema")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.plugins: dict[str, dict] = {"demo": manifest("demo")}
        self.sync()

    # ---- 整合した状態を作る（各テストはここから 1 箇所だけ壊す） -------------
    def sync(self) -> None:
        for name, m in self.plugins.items():
            d = self.root / name / ".claude-plugin"
            d.mkdir(parents=True, exist_ok=True)
            (d / "plugin.json").write_text(json.dumps(m, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
        (self.root / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps({
                "name": "test-marketplace", "description": "テスト", "owner": {"name": "t"},
                "plugins": [
                    {"name": n, "description": m["description"], "version": m["version"],
                     "author": m["author"], "source": "./%s" % n}
                    for n, m in sorted(self.plugins.items())
                ],
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        # ヘッダの「プラグイン数」も派生情報として検証されるので fixture に持たせる
        index = ["# INDEX", "", "- プラグイン数: %d" % len(self.plugins), "",
                 "| プラグイン | version | 説明 |", "|---|---|---|"]
        index += ["| [%s](#%s) | %s | 説明 |" % (n, n, m["version"])
                  for n, m in sorted(self.plugins.items())]
        (self.root / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
        claude = ["| プラグイン | コマンド | 説明 |", "|---|---|---|"]
        claude += ["| %s | 1 | 説明 |" % n for n in sorted(self.plugins)]
        (self.root / "CLAUDE.md").write_text("\n".join(claude) + "\n", encoding="utf-8")

    def edit_json(self, rel: str, mutate) -> None:
        path = self.root / rel
        data = json.loads(path.read_text(encoding="utf-8"))
        mutate(data)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def write(self, rel: str, body: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    # ---- 実行 ---------------------------------------------------------------
    def run_ssot(self, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(self.root / ".claude-plugin" / "scripts" / "validate-ssot.sh")],
            capture_output=True, text=True, timeout=60, cwd=str(self.root),
            env=env or dict(os.environ),
        )

    def env_without_jsonschema(self) -> dict[str, str]:
        """`import jsonschema` だけを失敗させる（PATH ではなく import を潰す）.

        **「入っていない環境を探す」ことに頼らない**: CI にも開発機にも入っているので、
        不在は**作る**側で再現する（`raise ImportError` する同名パッケージを先に置く）。
        """
        stub = self.root / "no-jsonschema" / "jsonschema"
        stub.mkdir(parents=True, exist_ok=True)
        (stub / "__init__.py").write_text(
            "raise ImportError('テスト用: jsonschema 不在を再現')", encoding="utf-8")
        return {**os.environ, "PYTHONPATH": str(self.root / "no-jsonschema")}

    def assertDetects(self, res: subprocess.CompletedProcess[str], fragment: str) -> None:
        self.assertEqual(res.returncode, 1, "検出は exit 1: %s%s" % (res.stdout, res.stderr))
        self.assertIn(fragment, res.stderr)
        self.assertNotIn("passed", res.stdout)

    # ---- 通過 ---------------------------------------------------------------
    def test_consistent_fixture_passes(self):
        res = self.run_ssot()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("SSoT validation passed", res.stdout)

    def test_every_plugin_is_checked_not_just_the_first(self):
        """**収集が 1 件目で止まる縮退**を検出する（GitHub issue #140 / M7）.

        実測: `collect_plugin_manifests()` のループに `break` を入れる変異を当てても
        28/28 が pass だった。この repo は 17 プラグインあるので、この縮退が入ると
        16 件が黙って未検証になる（「no-op なのに passed と出る」型そのもの）。
        `sorted()` の後ろに来る名前を壊すのが要点。
        """
        self.plugins["zeta"] = manifest("zeta")
        self.sync()
        self.edit_json(".claude-plugin/marketplace.json",
                       lambda d: next(p for p in d["plugins"]
                                      if p["name"] == "zeta").__setitem__("version", "9.9.9"))
        self.assertDetects(self.run_ssot(), "[marketplace:zeta] version mismatch")

    # ---- marketplace 同期 ---------------------------------------------------
    def test_version_drift_is_detected(self):
        self.edit_json(".claude-plugin/marketplace.json",
                       lambda d: d["plugins"][0].__setitem__("version", "9.9.9"))
        self.assertDetects(self.run_ssot(), "version mismatch")

    def test_description_drift_is_detected(self):
        self.edit_json(".claude-plugin/marketplace.json",
                       lambda d: d["plugins"][0].__setitem__("description", "ずれた説明"))
        self.assertDetects(self.run_ssot(), "description mismatch")

    def test_missing_marketplace_entry_is_detected(self):
        self.edit_json(".claude-plugin/marketplace.json", lambda d: d["plugins"].clear())
        self.assertDetects(self.run_ssot(), "missing entry for plugin: demo")

    def test_orphan_marketplace_entry_is_detected(self):
        self.edit_json(".claude-plugin/marketplace.json", lambda d: d["plugins"].append(
            {"name": "ghost", "description": "無い", "version": "1.0.0",
             "author": {"name": "t"}, "source": "./ghost"}))
        self.assertDetects(self.run_ssot(), "orphan entry")

    def test_source_path_drift_is_detected(self):
        self.edit_json(".claude-plugin/marketplace.json",
                       lambda d: d["plugins"][0].__setitem__("source", "./elsewhere"))
        self.assertDetects(self.run_ssot(), "source mismatch")

    def test_superseded_by_drift_is_detected(self):
        # deprecated 宣言は plugin.json 側だけに入りやすい（marketplace は手で足す）
        self.plugins["demo"]["_superseded_by"] = "successor"
        self.sync()
        self.assertDetects(self.run_ssot(), "_superseded_by mismatch")

    def test_missing_marketplace_file_is_detected(self):
        (self.root / ".claude-plugin" / "marketplace.json").unlink()
        self.assertDetects(self.run_ssot(), "[marketplace] not found")

    # ---- plugin.json の構造 -------------------------------------------------
    def test_name_directory_mismatch_is_detected(self):
        self.edit_json("demo/.claude-plugin/plugin.json",
                       lambda d: d.__setitem__("name", "other"))
        self.assertDetects(self.run_ssot(), "does not match directory")

    def test_non_semver_version_is_detected(self):
        self.plugins["demo"]["version"] = "1.0"
        self.sync()
        self.assertDetects(self.run_ssot(), "invalid version")

    def test_missing_required_key_is_detected(self):
        self.edit_json("demo/.claude-plugin/plugin.json", lambda d: d.pop("author"))
        self.assertDetects(self.run_ssot(), "missing required key: author")

    # ---- _requirements ↔ check-deps.sh --------------------------------------
    def test_requirement_missing_from_check_deps_is_detected(self):
        self.plugins["demo"]["_requirements"] = [
            {"name": "gh", "type": "cli_tool", "required": True, "description": "GitHub CLI"}]
        self.sync()
        self.write("demo/hooks/scripts/check-deps.sh",
                   '#!/usr/bin/env bash\ncheck_cli "jq" "任意"\n')
        self.assertDetects(self.run_ssot(), "requirement 'gh' not found in check-deps.sh")

    def test_check_deps_without_requirements_is_detected(self):
        self.write("demo/hooks/scripts/check-deps.sh",
                   '#!/usr/bin/env bash\ncheck_cli "gh" "GitHub CLI"\n')
        self.assertDetects(self.run_ssot(), "check-deps.sh calls check_* but")

    def test_requirements_without_check_deps_is_detected_only_when_hooks_exist(self):
        self.plugins["demo"]["_requirements"] = [
            {"name": "gh", "type": "cli_tool", "required": True, "description": "GitHub CLI"}]
        self.sync()
        # hooks/ が無いプラグインは check-deps.sh を必要としない（実行側フォールバック）
        self.assertEqual(self.run_ssot().returncode, 0)
        (self.root / "demo" / "hooks").mkdir()
        self.assertDetects(self.run_ssot(), "check-deps.sh missing")

    def test_an_undeclared_check_is_detected_even_when_others_are_declared(self):
        """双方向で突合する（GitHub issue #177）.

        以前は `_requirements` → check-deps.sh の片方向だけで、逆は `_requirements` が
        **完全に空のとき**しか見ていなかった。そのため「1 つでも宣言があれば、スクリプトが
        別の依存を必須として検査していても素通り」になっていた（実例: code-review の
        check-deps.sh が python3 を required で検査しているのに宣言が無かった）。
        宣言はインストール前の判断材料なので、実行時にだけ現れる依存は利用者から見えない。
        """
        self.plugins["demo"]["_requirements"] = [
            {"name": "gh", "type": "cli_tool", "required": True, "description": "GitHub CLI"}]
        self.sync()
        self.write("demo/hooks/scripts/check-deps.sh",
                   '#!/usr/bin/env bash\ncheck_cli "gh" "x"\ncheck_cli "python3" "y"\n')
        self.assertDetects(self.run_ssot(), "_requirements does not declare it")

    def test_a_fully_declared_pair_passes(self):
        """双方向にしても正しく揃っているものは通る（倒しすぎの禁止）."""
        self.plugins["demo"]["_requirements"] = [
            {"name": "gh", "type": "cli_tool", "required": True, "description": "GitHub CLI"},
            {"name": "jq", "type": "cli_tool", "required": True, "description": "JSON"}]
        self.sync()
        self.write("demo/hooks/scripts/check-deps.sh",
                   '#!/usr/bin/env bash\ncheck_cli "gh" "x"\ncheck_cli "jq" "y"\n')
        self.assertEqual(self.run_ssot().returncode, 0)

    def test_invalid_requirement_type_is_detected(self):
        self.plugins["demo"]["_requirements"] = [
            {"name": "gh", "type": "binary", "required": True, "description": "x"}]
        self.sync()
        self.assertDetects(self.run_ssot(), "invalid type: binary")

    # ---- hooks.json ---------------------------------------------------------
    def test_broken_hooks_json_is_detected(self):
        self.write("demo/hooks/hooks.json", "{ not json")
        self.assertDetects(self.run_ssot(), "invalid JSON")

    def test_a_broken_hooks_json_is_attributed_to_its_plugin(self):
        """指摘は `[hooks:<plugin>]` で出す（どのプラグインか分からないと直せない）."""
        self.write("demo/hooks/hooks.json", "{ not json")
        self.assertDetects(self.run_ssot(), "[hooks:demo]")

    def test_every_broken_hooks_json_is_reported_not_just_the_first(self):
        """1 つ目で中断しない（2 つ目以降が黙って検査されない状態を作らない）."""
        self.plugins["other"] = manifest("other")
        self.sync()
        self.write("demo/hooks/hooks.json", "{ not json")
        self.write("other/hooks/hooks.json", "{ not json either")
        res = self.run_ssot()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("[hooks:demo]", res.stderr)
        self.assertIn("[hooks:other]", res.stderr)

    def test_command_hook_without_command_is_detected(self):
        self.write("demo/hooks/hooks.json", json.dumps(
            {"hooks": {"SessionStart": [{"hooks": [{"type": "command"}]}]}}))
        self.assertDetects(self.run_ssot(), "requires 'command'")

    # ---- INDEX.md / CLAUDE.md ----------------------------------------------
    def test_a_stale_plugin_count_in_the_index_header_is_detected(self):
        """ヘッダの「プラグイン数」も派生情報として照合する（GitHub issue #184）.

        一覧表の行だけを見ていたため、実リポジトリではヘッダが 19 のまま実体 17 で
        2 ヶ月放置されていた。
        """
        index = (self.root / "INDEX.md").read_text(encoding="utf-8")
        self.write("INDEX.md", index.replace("プラグイン数: 1", "プラグイン数: 99"))
        self.assertDetects(self.run_ssot(), "ヘッダのプラグイン数が実体と違う")

    def test_a_missing_plugin_count_line_is_detected(self):
        """行ごと消して検査を無効化できないようにする（欠落を「違反なし」にしない）."""
        index = (self.root / "INDEX.md").read_text(encoding="utf-8")
        self.write("INDEX.md", "\n".join(
            l for l in index.splitlines() if "プラグイン数" not in l) + "\n")
        self.assertDetects(self.run_ssot(), "プラグイン数: N」の行が無い")

    def test_stale_index_version_is_detected(self):
        self.write("INDEX.md", "| [demo](#demo) | 0.0.1 | 説明 |\n")
        self.assertDetects(self.run_ssot(), "version mismatch")

    def test_plugin_missing_from_index_is_detected(self):
        self.write("INDEX.md", "| プラグイン | version |\n")
        self.assertDetects(self.run_ssot(), "[docs:INDEX.md] plugin missing")

    def test_unknown_plugin_in_index_is_detected(self):
        self.write("INDEX.md", "| [demo](#demo) | 1.0.0 | 説明 |\n"
                               "| [ghost](#ghost) | 1.0.0 | 説明 |\n")
        self.assertDetects(self.run_ssot(), "lists unknown plugin: ghost")

    def test_plugin_missing_from_claude_md_is_detected(self):
        self.write("CLAUDE.md", "# プロジェクト\n\n一覧なし\n")
        self.assertDetects(self.run_ssot(), "[docs:CLAUDE.md] plugin missing")

    def test_a_deleted_doc_is_not_silently_skipped(self):
        """**照合対象が消えたら no-op ではなく検出**（緑に見えるのが一番まずい）."""
        for rel, fragment in (("INDEX.md", "[docs:INDEX.md] not found"),
                              ("CLAUDE.md", "[docs:CLAUDE.md] not found")):
            with self.subTest(doc=rel):
                self.setUp()
                (self.root / rel).unlink()
                self.assertDetects(self.run_ssot(), fragment)

    # ---- 判定不能（前提が無い）----------------------------------------------
    def test_without_jsonschema_it_does_not_claim_passed(self):
        """スキーマ検証を**実行できなかった**回を「通過」と呼ばない（exit 2）.

        ここを 0 にすると「ローカルは緑・CI は赤」が push まで見えない（#140 事例 1 の型）。
        """
        res = self.run_ssot(env=self.env_without_jsonschema())
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertNotIn("passed", res.stdout)
        self.assertIn("incomplete", res.stderr)
        self.assertIn("pip install jsonschema", res.stderr)

    def test_detected_violations_win_over_the_unknown_verdict(self):
        """違反が見つかっていれば 1（直せるものがある方を優先して伝える）."""
        self.edit_json(".claude-plugin/marketplace.json",
                       lambda d: d["plugins"][0].__setitem__("version", "9.9.9"))
        res = self.run_ssot(env=self.env_without_jsonschema())
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("version mismatch", res.stderr)

    def test_no_plugin_at_all_is_unknown_not_pass(self):
        shutil.rmtree(self.root / "demo")
        res = self.run_ssot()
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertNotIn("passed", res.stdout)

    def test_wrapper_reports_missing_python3_as_unknown(self):
        """`validate-ssot.sh` 側の前提（python3）も「通過」と区別する."""
        for name in ("bash", "dirname"):
            real = shutil.which(name)
            self.assertIsNotNone(real, "%s が見つからない" % name)
            dest = self.bin / name
            if not dest.exists():
                dest.symlink_to(real)
        res = self.run_ssot(env={**os.environ, "PATH": str(self.bin)})
        self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
        self.assertIn("python3", res.stderr)

    # ---- 壊れた JSON を traceback で出さない（GitHub issue #176）-----------
    def test_broken_plugin_json_is_reported_as_a_readable_violation(self):
        """壊れた plugin.json は**読める指摘**として exit 1（traceback ではない）.

        以前は JSONDecodeError が素通しで抜け、pre-commit と machine-layer が
        traceback をそのまま「SSoT 違反」として提示していた。`check_hooks_json` は
        hooks.json に対して既に「invalid JSON」の指摘に変えており、扱いが非対称だった。
        """
        self.write("demo/.claude-plugin/plugin.json", "{ not json")
        res = self.run_ssot()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertNotIn("Traceback", res.stderr, "traceback が利用者に出ている")
        self.assertIn("invalid JSON", res.stderr)
        self.assertIn("plugin.json", res.stderr)

    def test_broken_marketplace_json_is_reported_as_a_readable_violation(self):
        self.write(".claude-plugin/marketplace.json", "{ not json")
        res = self.run_ssot()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertNotIn("Traceback", res.stderr, "traceback が利用者に出ている")
        self.assertIn("invalid JSON", res.stderr)

    # ---- スキーマ検証そのもの（jsonschema がある環境） ----------------------
    @unittest.skipUnless(HAS_JSONSCHEMA, "jsonschema 未導入（CI では pip install 済み）")
    def test_schema_violation_is_detected_when_jsonschema_is_available(self):
        """構造チェックでは拾えない違反（未知フィールド）をスキーマが拾う."""
        self.edit_json("demo/.claude-plugin/plugin.json",
                       lambda d: d.__setitem__("unknownField", "x"))
        self.assertDetects(self.run_ssot(), "schema:")

    @unittest.skipUnless(HAS_JSONSCHEMA, "jsonschema 未導入（CI では pip install 済み）")
    def test_missing_schema_file_is_detected(self):
        (self.root / ".claude-plugin" / "schema" / "plugin.schema.json").unlink()
        self.assertDetects(self.run_ssot(), "schema not found")


if __name__ == "__main__":
    unittest.main()
