#!/usr/bin/env python3
"""code-review 同梱スクリプトの回帰テスト（CLI 境界越し）.

**なぜ subprocess なのか**: 対象は bash の CLI サブコマンド（`review-timing.sh mark t2` /
`publish-review-event.sh --payload ...`）で、**実際の呼ばれ方をそのまま再現できる**のが
内部関数の直接テストより価値が高い。bats を入れれば bash 関数を直接叩けるが、
**新規の外部依存**になり CI（現状 python3 + bash のみ）にも入れる必要がある。
python の subprocess なら既存の `unittest discover` にそのまま載り、
pre-commit / CI / Stop hook の 3 経路に**設定変更なしで**乗る。

**なぜこの範囲なのか**: 全分岐の網羅は費用が見合わない（`review-retro.sh` だけで 720 行）。
**v2.66.0〜v2.67.1 のセルフレビューで「回帰テストがあれば捕まえられた」と分類された
6 件の経路**から始める — その 6 件は agent 8 体を回して見つけたもので、
ここが埋まればレビューは判断が要る層に集中できる（`findings_class` の `test` 比率で測る）。

実行:
  python3 -m unittest discover -s .claude-plugin/scripts/tests
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PLUGIN = REPO / "code-review"
TIMING = PLUGIN / "scripts" / "review-timing.sh"
PUBLISH = PLUGIN / "scripts" / "publish-review-event.sh"
RETRO = PLUGIN / "scripts" / "review-retro.sh"

# 最小構成の payload（層のオブジェクトは必ず入れる契約 / orchestration-measurement.md `## 16`）
BASE_PAYLOAD = {
    "pr": "local",
    "effort": "high",
    "size_tier": "medium",
    "missing_coverage": [],
    "pre_adjust_counts": {"blocker": 0, "critical": 0, "major": 1, "minor": 0},
    "adversarial_verify": {"fired": True, "skip_reason": None},
    "recall_skeptic": {"fired": False, "skip_reason": "no-surface"},
    "meta_reviewer": {"fired": False, "skip_reason": "effort"},
    "findings_class": {"lint": 0, "test": 0, "judgement": 1},
    "agents": {"explorer": 0, "reviewer": 2},
}


class ScriptTestBase(unittest.TestCase):
    """一時 git repo + 専用 TMPDIR で各テストを隔離する.

    `review-paths.sh` は `--show-toplevel` の cksum でパスを作るので、
    **テストごとに別ディレクトリなら計測ファイルも自動的に分かれる**（並行実行しても衝突しない）。
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        (self.root / "tmp").mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"],
                       cwd=self.root, check=True,
                       env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})

    def _env(self, **extra: str) -> dict[str, str]:
        env = {**os.environ, "TMPDIR": str(self.root / "tmp"), "CLAUDE_PLUGIN_ROOT": str(PLUGIN)}
        env.update(extra)
        return env

    def run_script(self, script: Path, *args: str, env: dict[str, str] | None = None
                   ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(script), *args], cwd=self.root, capture_output=True,
                              text=True, env=env or self._env(), timeout=60)

    def timing(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self.run_script(TIMING, *args)

    def publish(self, payload: dict | None = None, plugin: str = "code-review:self-review",
                *extra: str, env: dict[str, str] | None = None
                ) -> subprocess.CompletedProcess[str]:
        body = json.dumps(payload if payload is not None else BASE_PAYLOAD, ensure_ascii=False)
        return self.run_script(PUBLISH, "--plugin", plugin, *extra, "--payload", body, env=env)

    def events(self) -> list[dict]:
        log = self.root / ".claude" / "events.jsonl"
        if not log.is_file():
            return []
        return [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]

    def last_payload(self) -> dict:
        evs = self.events()
        self.assertTrue(evs, "events.jsonl が空")
        return evs[-1]["payload"]

    def ts_file(self) -> Path:
        """計測ファイルの実パス（`start` が stdout に返す）."""
        out = self.timing("start").stdout.strip()
        self.assertTrue(out, "start がパスを返していない")
        return Path(out)

    def full_run(self) -> Path:
        """t0 → t1 → wave → t2 まで打った状態を作る."""
        path = self.ts_file()
        self.timing("mark", "t1")
        self.timing("mark", "wave")
        self.timing("mark", "t2")
        return path


class PublishPendingTest(ScriptTestBase):
    """`publish-pending` の状態機械（GitHub issue #133 / v2.66.0 のセルフレビュー指摘）.

    旧版は「計測ファイルが残っているか」だけで判定しており、**publish を試みて失敗した回**
    （＝イベントが書かれず打点も消える最悪の回）を取りこぼしていた。
    """

    def test_silent_before_any_review(self):
        self.assertEqual(self.timing("publish-pending").stderr.strip(), "")

    def test_silent_when_report_not_yet_written(self):
        self.ts_file()
        self.timing("mark", "t1")
        self.assertEqual(self.timing("publish-pending").stderr.strip(), "")

    def test_warns_after_t2_without_publish(self):
        self.full_run()
        self.assertIn("未実施", self.timing("publish-pending").stderr)

    def test_silent_after_successful_publish(self):
        self.full_run()
        self.assertEqual(self.publish().returncode, 0)
        self.assertEqual(self.timing("publish-pending").stderr.strip(), "")

    def test_warns_when_publish_failed(self):
        """**publish を試みて失敗した回でも鳴ること**（旧版はここで無言だった）."""
        self.full_run()
        self.publish(env=self._env(CLAUDE_PLUGIN_ROOT="/nonexistent"))
        self.assertEqual(self.events(), [], "失敗回なのにイベントが書かれている")
        self.assertIn("未実施", self.timing("publish-pending").stderr)

    def test_silent_with_keep_temp_after_success(self):
        """`--keep-temp` は計測ファイルを残すが `pub` マーカーがあるので鳴らない."""
        self.full_run()
        self.publish(None, "code-review:self-review", "--keep-temp")
        self.assertEqual(self.timing("publish-pending").stderr.strip(), "")


class CleanupTest(ScriptTestBase):
    """掃除は publish 成功時のみ（v2.67.1）.

    旧版は成否に関わらず掃除しており、**イベントが書かれなかった回ほど痕跡が残らない**
    という逆向きの縮退だった（打点ごと消えて再 publish もできない）。
    """

    def test_success_removes_timing_file(self):
        path = self.full_run()
        self.publish()
        self.assertFalse(path.exists())

    def test_failure_keeps_timing_file_for_retry(self):
        path = self.full_run()
        self.publish(env=self._env(CLAUDE_PLUGIN_ROOT="/nonexistent"))
        self.assertTrue(path.exists(), "失敗回で計測ファイルが消えている（再 publish できない）")
        # 同じ引数で再実行すれば復旧できる
        self.assertEqual(self.publish().returncode, 0)
        self.assertEqual(len(self.events()), 1)


class MissingCoverageValidationTest(ScriptTestBase):
    """`missing_coverage` の語彙検証（GitHub issue #132）."""

    def _payload(self, mc) -> dict:
        p = dict(BASE_PAYLOAD)
        if mc is None:
            p.pop("missing_coverage")
        else:
            p["missing_coverage"] = mc
        return p

    def test_identifiers_pass(self):
        r = self.publish(self._payload(["error-handling", "explorer:value-flow-trace"]))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_free_text_is_rejected(self):
        r = self.publish(self._payload(["adversarial-verify: F2 未反証"]))
        self.assertEqual(r.returncode, 1)
        self.assertIn("識別子以外", r.stderr)
        self.assertEqual(self.events(), [], "FATAL なのに publish されている")

    def test_trailing_newline_is_rejected(self):
        """`re.match` + `$` は末尾改行を通す（`fullmatch` でないと綴り割れが復活する）."""
        r = self.publish(self._payload(["recall-skeptic\n"]))
        self.assertEqual(r.returncode, 1)
        self.assertIn("識別子以外", r.stderr)

    def test_non_list_is_rejected(self):
        r = self.publish(self._payload("none"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("配列でない", r.stderr)

    def test_missing_field_becomes_a_gap(self):
        """**フィールドごと落とす逃げ道**を塞ぐ（綴り割れが静かな全欠測に化けない）."""
        self.publish(self._payload(None))
        self.assertIn("payload:missing_coverage", self.last_payload()["measurement_gaps"])


class LatePublishTest(ScriptTestBase):
    """遅れて publish した self-review は `duration_min` を欠測に倒す（issue #133）."""

    def _stale_timing(self, closing_min: int) -> None:
        path = self.ts_file()
        now = int(time.time())
        path.write_text(
            "t0 %d\nt1 %d\nw %d\nt2 %d\n"
            % (now - 3600, now - 3500, now - 2000, now - closing_min * 60),
            encoding="utf-8",
        )

    def test_late_self_review_drops_duration_min(self):
        self._stale_timing(30)
        self.publish()
        p = self.last_payload()
        self.assertEqual(p["duration_min"], -1)
        self.assertIn("late-publish", p["measurement_gaps"])
        self.assertGreater(p["duration_fleet_min"], 0, "fleet は t2 で閉じているので影響を受けない")

    def test_prompt_self_review_keeps_duration_min(self):
        self._stale_timing(0)
        self.publish()
        p = self.last_payload()
        self.assertNotEqual(p["duration_min"], -1)
        self.assertNotIn("late-publish", p["measurement_gaps"])

    def test_review_is_not_affected(self):
        """review は締めフロー（人間待ち）込みが契約なので、長くても正常."""
        self._stale_timing(30)
        payload = dict(BASE_PAYLOAD, pr="1")
        self.publish(payload, "code-review:review")
        p = self.last_payload()
        self.assertNotEqual(p["duration_min"], -1)
        self.assertNotIn("late-publish", p["measurement_gaps"])


class SchemaMarkerInjectionTest(ScriptTestBase):
    """版マーカーはスクリプトが注入する（issue #125）— LLM の手書きに戻っていないこと."""

    def test_markers_are_injected(self):
        self.publish()
        p = self.last_payload()
        self.assertEqual(p["adversarial_verify"]["gate_schema"], 2)
        self.assertEqual(p["adversarial_verify"]["calibration_schema"], 2)
        self.assertEqual(p["meta_reviewer"]["gate_schema"], 3)
        self.assertEqual(p["findings_class"]["schema"], 1)

    def test_missing_layer_object_becomes_a_gap(self):
        """層のオブジェクトごと落ちた回は空 dict を捏造せず gap にする."""
        payload = {k: v for k, v in BASE_PAYLOAD.items() if k != "meta_reviewer"}
        self.publish(payload)
        self.assertIn("payload:meta_reviewer", self.last_payload()["measurement_gaps"])


class RetroTest(ScriptTestBase):
    """`review-retro.sh` の層別と分母（issue #131 / v2.66.0 のセルフレビュー指摘）."""

    def _events(self, rows: list[dict]) -> None:
        (self.root / ".claude").mkdir(exist_ok=True)
        (self.root / ".claude" / "events.jsonl").write_text(
            "\n".join(json.dumps({"ts": "2026-08-1%d T00:%02d:00Z".replace(" ", "") % (i // 60, i % 60),
                                  "plugin": r.pop("_plugin", "code-review:self-review"),
                                  "event": "review:completed", "payload": r},
                                 ensure_ascii=False)
                      for i, r in enumerate(rows)) + "\n",
            encoding="utf-8",
        )

    def _verdict(self, calib: int, inflated: int) -> dict:
        return {"effort": "high", "measurement_gaps": [],
                "adversarial_verify": {"fired": True, "skip_reason": None, "gate_schema": 2,
                                       "calibration_schema": calib, "confirmed": 1,
                                       "refuted": 0, "uncertain": 0,
                                       "severity_inflated": inflated, "contested": 0}}

    def test_signal_withheld_while_only_pre_measure_layer_exists(self):
        """層 1 しか無いうちは `severity_inflated` シグナルを出さない（doc が「使うな」と書く値）."""
        self._events([self._verdict(1, 5) for _ in range(6)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertNotIn("severity_inflated が", out)
        self.assertIn("対策前", out, "黙るだけでは「効果あり」と読まれる")

    def test_accumulating_layer_is_announced(self):
        """層 2 が現れても件数が足りない間は「蓄積中」を出す（無言区間を作らない）."""
        self._events([self._verdict(1, 5), self._verdict(2, 1)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("蓄積中", out)
        self.assertNotIn("severity_inflated が", out)

    def test_signal_fires_on_post_measure_layer(self):
        self._events([self._verdict(2, 5) for _ in range(6)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("severity_inflated が", out)

    def _signals(self, out: str) -> str:
        """⚠️ シグナル欄だけを返す（欄が無ければ空文字）.

        条件式で「欄が無ければ空」に倒すと, retro が異常終了して stdout が空でも
        恒久 pass になる。欄の有無自体をここで表明する。
        """
        self.assertIn("## レビュー振り返り", out, "retro が出力していない")
        return out.split("⚠️ シグナル")[-1] if "⚠️ シグナル" in out else ""

    def test_gap_signal_does_not_fire_on_a_single_sample(self):
        """`late-publish` は self-review 母集団で判定する（**単発で 100% 点灯しない**）."""
        rows = [{"effort": "high", "measurement_gaps": ["late-publish"]}]
        rows += [{"_plugin": "code-review:review", "effort": "high", "measurement_gaps": []}
                 for _ in range(4)]
        self._events(rows)
        self.assertNotIn("late-publish", self._signals(self.run_script(RETRO, env=self._env()).stdout))

    def test_gap_signal_fires_when_its_own_denominator_is_met(self):
        """**母集団が揃えば点灯する**（分母を分けた目的側。分母 0 で永久に沈黙しないこと）."""
        rows = [{"effort": "high", "measurement_gaps": ["late-publish"]} for _ in range(5)]
        rows += [{"_plugin": "code-review:review", "effort": "high", "measurement_gaps": []}
                 for _ in range(6)]
        self._events(rows)
        self.assertIn("late-publish", self._signals(self.run_script(RETRO, env=self._env()).stdout))

    def test_json_mode_always_returns_json(self):
        self._events([self._verdict(2, 1)])
        out = self.run_script(RETRO, "--json", env=self._env()).stdout
        self.assertIn("findings_class", json.loads(out))


if __name__ == "__main__":
    unittest.main()
