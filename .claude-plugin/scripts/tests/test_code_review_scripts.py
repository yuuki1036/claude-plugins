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
  python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
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
    "below_threshold_counts": {"blocker": 0, "critical": 0, "major": 0, "minor": 0},
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
        # **リポジトリ内に author を設定する**。env の `GIT_AUTHOR_*` は init commit にしか
        # 効かず、テストが独自に `git commit` すると **CI（global config が無い環境）で
        # だけ失敗する**（実測: ubuntu で `git commit` が黙って失敗し、rename のはずの diff が
        # 「新規ファイル」になってテストが落ちた）
        for key, value in (("user.email", "t@example.com"), ("user.name", "t")):
            subprocess.run(["git", "config", key, value], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"],
                       cwd=self.root, check=True)

    # **git が hook 実行時に渡す変数を落とす**。`GIT_INDEX_FILE=.git/index` のような
    # **相対パス**が入っており、テスト内の使い捨てリポジトリで git を叩くと外側の index を
    # 掴もうとして落ちる（実測: pre-commit から本スイートを走らせると
    # `fatal: .git/index: index file open failed: Not a directory` で 21 件失敗した）。
    # **本スイートは pre-commit と CI で強制される**ので、その環境で通ることが要件。
    GIT_HOOK_ENV = ("GIT_DIR", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE",
                    "GIT_PREFIX", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                    "GIT_QUARANTINE_PATH", "GIT_REFLOG_ACTION", "GIT_EDITOR")

    def _env(self, **extra: str) -> dict[str, str]:
        env = {**os.environ, "TMPDIR": str(self.root / "tmp"), "CLAUDE_PLUGIN_ROOT": str(PLUGIN)}
        for key in self.GIT_HOOK_ENV:
            env.pop(key, None)
        # **ctype は UTF-8 に固定する**（実利用の通常環境に揃える）。C ロケールでは
        # `"$VAR（"` のような日本語隣接の展開が**動いてしまう**ため、UTF-8 でのみ出る
        # `unbound variable`（実測: detect-recent-review.sh の WARN が exit 1 になっていた）を
        # 取りこぼす。LC_ALL があると LC_CTYPE を上書きするので落とす
        env.pop("LC_ALL", None)
        env["LC_CTYPE"] = "C.UTF-8"
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

    def signals(self, out: str) -> str:
        """⚠️ シグナル欄だけを返す（欄が無ければ空文字）.

        **`assertNotIn` だけの否定テストは liveness ガードが要る** — 条件式で「欄が無ければ空」に
        倒すと, retro が異常終了して stdout が空でも恒久 pass になる（実測: `fc_total` を壊すと
        肯定系 9 件が落ちるのに否定系 3 件は緑のままだった）。欄の有無自体をここで表明する。
        """
        self.assertIn("## レビュー振り返り", out, "retro が出力していない")
        return out.split("⚠️ シグナル")[-1] if "⚠️ シグナル" in out else ""

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

    def test_success_removes_every_temp_file_of_the_review(self):
        """**掃除の対象は種別を増やすたびに漏れる**（残ると TMPDIR に溜まり続ける）.

        prctx / diff / agentctx / oracles を実在させてから publish し、全部消えることを見る。
        """
        ts = self.full_run()
        # パスは `lib/review-paths.sh` に問い合わせる（命名規則をテスト側に複製しない）
        made = []
        for kind in ("prctx", "diff", "agentctx", "oracles"):
            proc = subprocess.run(
                ["bash", "-c", '. "$1/scripts/lib/review-paths.sh"; review_paths_init ""; '
                               'review_path "$2"', "_", str(PLUGIN), kind],
                cwd=self.root, capture_output=True, text=True, env=self._env())
            self.assertEqual(proc.returncode, 0, proc.stderr)
            path = Path(proc.stdout.strip())
            path.write_text("x\n", encoding="utf-8")
            made.append(path)
        self.publish()
        leftovers = [p for p in made if p.exists()]
        self.assertEqual(leftovers, [], "publish 後に一時ファイルが残っている: %s" % leftovers)
        self.assertFalse(ts.exists(), "計測ファイルも消える")

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


class TokenAndDispatchPayloadTest(ScriptTestBase):
    """publish が `tokens` / `dispatch` を payload に載せる（GitHub issue #142 / #143）.

    - **#143**: self-review は `tokens` を構造的に載せていなかった（実測: このマシンの
      review:completed 37 件すべてで欠測）。体数削減・分冊の効果は全部そこに出るのに、
      主要レバーの効果が自動集計の外にあった
    - **#142**: `duration_fleet_min` は「9 体を逐次で回した 89 分」と「1 体が 89 分かかった」を
      区別できない。実測 16 回のうち 13 回が逐次発行で、累計 431 分を失っていた
    """

    def setUp(self) -> None:
        super().setUp()
        self.home = self.root / "home"
        (self.home / ".claude" / "projects").mkdir(parents=True)

    def env_home(self) -> dict[str, str]:
        return self._env(HOME=str(self.home))

    def write_transcript(self, waves: list[list[int]]) -> None:
        """cwd に対応する slug へ session + subagent を置く.

        `waves[i]` は**同一メッセージから発行した** agent の起動オフセット（秒）。
        transcript は 1 メッセージを tool_use ブロックごとに別行へ分解して書くので、
        fixture も「行は別・`message.id` は共通」の形に揃える（GitHub issue #149）。
        """
        slug = "".join(c if c.isalnum() else "-" for c in str(self.root))
        d = self.home / ".claude" / "projects" / slug
        d.mkdir(parents=True, exist_ok=True)
        base = datetime(2026, 8, 18, 1, 0, 0)

        def row(ts: str) -> str:
            return json.dumps({"type": "assistant", "timestamp": ts,
                               "message": {"usage": {"output_tokens": 10,
                                                     "cache_creation_input_tokens": 20,
                                                     "cache_read_input_tokens": 30}}})

        rows = [row(base.isoformat() + "Z")]
        sub = d / "s1" / "subagents"
        sub.mkdir(parents=True, exist_ok=True)
        idx = 0
        for wave_no, offsets in enumerate(waves):
            for off in offsets:
                ts = (base + timedelta(seconds=off)).isoformat() + "Z"
                rows.append(json.dumps({
                    "type": "assistant", "timestamp": ts, "uuid": "u-%d" % idx,
                    "message": {"id": "msg-%d" % wave_no,
                                "content": [{"type": "tool_use", "id": "tu-%d" % idx,
                                             "name": "Agent"}]}}))
                (sub / ("agent-%d.jsonl" % idx)).write_text(row(ts) + "\n", encoding="utf-8")
                (sub / ("agent-%d.meta.json" % idx)).write_text(
                    json.dumps({"agentType": "general-purpose", "toolUseId": "tu-%d" % idx}),
                    encoding="utf-8")
                idx += 1
        (d / "s1.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")

    def test_self_review_carries_tokens(self):
        """**除外の撤回**（#143）。載らない回は「載せない」ではなく欠測として残す."""
        self.write_transcript([[0, 5]])
        self.publish(env=self.env_home())
        p = self.last_payload()
        self.assertIn("tokens", p, "self-review で tokens が載っていない")
        self.assertEqual(p["tokens"]["window"], "session", "t0 が無い回は session 窓")
        self.assertEqual(p["tokens"]["sub_agents"], 2)

    def test_missing_transcript_is_a_gap_not_a_zero(self):
        """transcript を引けない回に 0 を載せない（retro の中央値と相関を壊すため）."""
        self.publish(env=self.env_home())
        p = self.last_payload()
        self.assertNotIn("tokens", p)
        self.assertIn("tokens", p["measurement_gaps"])

    def test_serial_dispatch_lands_and_warns(self):
        """1 体ずつ別メッセージで発行した回（単独 wave が 3 連続）."""
        self.write_transcript([[0], [600], [1300]])
        res = self.publish(env=self.env_home())
        p = self.last_payload()
        self.assertEqual(p["dispatch"]["verdict"], "serial", p.get("dispatch"))
        self.assertEqual((p["dispatch"]["agents"], p["dispatch"]["waves"]), (3, 3))
        self.assertEqual(p["dispatch"]["schema"], 2, "版マーカーが無いと retro が層別できない")
        self.assertIn("逐次発行", res.stderr)
        self.assertIn("#142", res.stderr)

    def test_batched_dispatch_does_not_warn(self):
        """**守れた回は黙る**（⚠️ が出たときだけ行動する契約）."""
        self.write_transcript([[0, 3, 7]])
        res = self.publish(env=self.env_home())
        self.assertEqual(self.last_payload()["dispatch"]["verdict"], "batched")
        self.assertNotIn("逐次発行", res.stderr)

    def test_layered_dispatch_does_not_warn(self):
        """層ごとの wave は設計上正当（explorer → reviewer）。**ここで警告すると
        2 層以上のレビューが毎回警告になる**（GitHub issue #149）."""
        self.write_transcript([[0, 5], [600, 605, 610]])
        res = self.publish(env=self.env_home())
        self.assertEqual(self.last_payload()["dispatch"]["verdict"], "layered")
        self.assertNotIn("逐次発行", res.stderr)

    def test_undecidable_dispatch_is_a_gap_not_batched(self):
        """agent が居ない回を「一括だった」に倒さない（規約遵守の証拠が無い回）."""
        self.write_transcript([])
        self.publish(env=self.env_home())
        p = self.last_payload()
        self.assertNotIn("dispatch", p)
        self.assertIn("dispatch", p["measurement_gaps"])

    def test_late_publish_marks_the_window(self):
        """遅れて publish した回は窓に修正作業が混ざる。**別の名前で出す**（#143）."""
        self.write_transcript([[0, 5]])
        path = self.ts_file()
        now = int(time.time())
        path.write_text("t0 %d\nt1 %d\nw %d\nt2 %d\n"
                        % (now - 3600, now - 3500, now - 2000, now - 1800), encoding="utf-8")
        self.publish(env=self.env_home())
        p = self.last_payload()
        self.assertIn("late-publish", p["measurement_gaps"], "前提: 遅延 publish と判定されている")
        if "tokens" in p:
            self.assertEqual(p["tokens"]["window"], "since-t0-late")


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

    def _dispatch(self, verdict: str, waves: int = 3, agents: int = 3,
                  schema: int | None = 2, solo_run: int = 3) -> dict:
        d = {"agents": agents, "waves": waves, "wave_sizes": [1] * waves,
             "max_solo_run": solo_run, "max_inter_wave_sec": 600, "span_sec": 900,
             "verdict": verdict}
        if schema is not None:
            d["schema"] = schema
        return {"effort": "high", "measurement_gaps": [], "dispatch": d}

    def test_dispatch_rate_is_reported(self):
        """発行パターンの内訳を毎回の振り返りに出す（GitHub issue #142 / #149）."""
        self._events([self._dispatch("serial", solo_run=5),
                      self._dispatch("batched", waves=1, agents=4),
                      self._dispatch("serial", solo_run=3),
                      self._dispatch("layered", waves=2, agents=6, solo_run=1)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("**発行パターン**", out)
        self.assertIn("batched 1・layered 1・serial 2", out, "内訳が出ていない")
        # 1 wave あたりの体数（4/1, 6/2, 3/3, 3/3）の中央値 = 2.0
        self.assertIn("中央値 2.0 体", out)
        # **是正先の「何連続から」は serial の回だけで採る**（3 と 5 の小さい方）。
        # layered の solo_run=1 を混ぜると「1 連続以上」という無意味な閾値になる
        self.assertIn("単独 wave が 3 連続以上", out)

    def test_schema_1_samples_are_excluded_from_the_denominator(self):
        """**判定単位が誤っていた schema 1 を混ぜない**（GitHub issue #149）.

        schema 1 は wave 間ギャップを違反として数えており、実測 4 件すべてが `serial`。
        混ぜると「守られた割合」が構造的に 0% に張り付く。
        """
        self._events([self._dispatch("serial", schema=None),
                      self._dispatch("serial", schema=None),
                      self._dispatch("batched", waves=1, agents=4)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("batched 1・layered 0・serial 0", out, "旧 schema を分母に入れている")
        self.assertIn("schema 1 を 2 件除外", out, "除外したことを黙っている")

    def test_undecidable_dispatch_is_out_of_the_denominator(self):
        """`single` / `unknown` は分母に入れない（判定できないものを守れた側に数えない）."""
        self._events([self._dispatch("batched", waves=1, agents=4),
                      self._dispatch("single", waves=1, agents=1),
                      self._dispatch("unknown", waves=0, agents=0)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("n=1", out, "判定不能を分母に入れている")
        self.assertIn("batched 1・layered 0・serial 0", out)

    def test_no_dispatch_sample_says_so(self):
        """サンプル 0 件を「守られた」と読めない形で出す."""
        self._events([{"effort": "high", "measurement_gaps": []}])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("**発行パターン**: 判定対象なし", out)

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

    def test_gap_signal_does_not_fire_on_a_single_sample(self):
        """`late-publish` は self-review 母集団で判定する（**単発で 100% 点灯しない**）."""
        rows = [{"effort": "high", "measurement_gaps": ["late-publish"]}]
        rows += [{"_plugin": "code-review:review", "effort": "high", "measurement_gaps": []}
                 for _ in range(4)]
        self._events(rows)
        self.assertNotIn("late-publish", self.signals(self.run_script(RETRO, env=self._env()).stdout))

    def test_gap_signal_fires_when_its_own_denominator_is_met(self):
        """**母集団が揃えば点灯する**（分母を分けた目的側。分母 0 で永久に沈黙しないこと）."""
        rows = [{"effort": "high", "measurement_gaps": ["late-publish"]} for _ in range(5)]
        rows += [{"_plugin": "code-review:review", "effort": "high", "measurement_gaps": []}
                 for _ in range(6)]
        self._events(rows)
        self.assertIn("late-publish", self.signals(self.run_script(RETRO, env=self._env()).stdout))

    def test_json_mode_always_returns_json(self):
        self._events([self._verdict(2, 1)])
        out = self.run_script(RETRO, "--json", env=self._env()).stdout
        self.assertIn("findings_class", json.loads(out))


    # ---- 検出 → 報告の内訳（GitHub issue #146） -----------------------------
    SEVS = ("blocker", "critical", "major", "minor")

    def _yield_row(self, pre, post, below=None) -> dict:
        r = {"effort": "high", "measurement_gaps": [], "severity_threshold": "MAJOR",
             "pre_adjust_counts": {**dict(zip(self.SEVS, pre)), "schema": 2}}
        r.update(dict(zip(("%s_count" % s for s in self.SEVS), post)))
        if below is not None:
            r["below_threshold_counts"] = dict(zip(self.SEVS, below))
        return r

    def test_written_findings_are_separated_from_count_only(self):
        """合算では (a) 本文を書いてから捨てた と (b) 件数だけ返した を分けられない."""
        self._events([self._yield_row((0, 0, 10, 20), (0, 0, 4, 0), below=(0, 0, 0, 20))])
        out = self.run_script(RETRO, env=self._env()).stdout
        # **層別キーごと見る**（閾値が違う回を同じ列で比べると運用差が改善に見える）
        self.assertIn("schema>=2/threshold=MAJOR: n=1 / 本文を書いた 10", out)
        self.assertIn("本文を書いた 10（検出 30 − 件数のみ 20）→ 報告 4", out)
        self.assertIn("本文を書いてから捨てた: 6 件（60.0%）", out)

    def test_unknown_threshold_is_not_folded_into_the_default(self):
        """`severity_threshold` が無い回を `MAJOR` の列に混ぜない（`?` で別層にする）.

        どの severity が `## below-threshold` に回ったかは閾値で決まるので、
        閾値不明を既定と同じ列に入れると**運用差が施策の効果に見える**。
        """
        row = self._yield_row((0, 0, 10, 20), (0, 0, 4, 0), below=(0, 0, 0, 20))
        row.pop("severity_threshold")
        self._events([row])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("threshold=?: n=1", out)
        self.assertNotIn("threshold=MAJOR", out)

    def test_rows_without_the_field_are_out_of_the_denominator(self):
        """**持たない回を混ぜない** — 混ぜると pre だけ増えて (a) が過大に出る."""
        self._events([self._yield_row((0, 0, 10, 20), (0, 0, 4, 0), below=(0, 0, 0, 20)),
                      self._yield_row((0, 0, 99, 99), (0, 0, 1, 0))])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("n=1 / 本文を書いた 10", out)
        self.assertIn("検出 30 − 件数のみ 20", out)

    def test_negative_drop_is_not_rounded(self):
        """0 に丸めると「捨てていない」と読める（手順 1 の後で足す層があるため負が出る）."""
        self._events([self._yield_row((0, 0, 5, 0), (0, 0, 8, 0), below=(0, 0, 0, 0))])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("本文を書いてから捨てた: -3 件", out)
        self.assertIn("recall_skeptic / meta_reviewer", out, "負の理由を言わずに出さない")

    def test_zero_drop_is_not_labelled_as_negative(self):
        """捨てた 0 件は「負」ではない（注記が付くと後段の層が足したと誤読される）."""
        self._events([self._yield_row((0, 0, 4, 6), (0, 0, 4, 0), below=(0, 0, 0, 6))])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("本文を書いてから捨てた: 0 件（0.0%）", out)
        self.assertNotIn("recall_skeptic / meta_reviewer", out)

    def test_no_sample_says_it_cannot_be_judged_yet(self):
        """歩留まりだけ出して黙ると「分離できている」と読める（#131 と同じ型）."""
        self._events([self._yield_row((0, 0, 10, 20), (0, 0, 4, 0))])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("`below_threshold_counts` を持つサンプル待ち", out)
        # 待ちメッセージ自身が説明として同じ語を含むので、**集計行だけ**を指して見る
        self.assertNotIn("本文を書いた ", out)


class FindingsClassValidationTest(ScriptTestBase):
    """`findings_class` の publish 側検証（v2.68.0）.

    **変異テストが炙り出したギャップ**: 検証を追加したのに回帰テストが 1 件も無く、
    `if fc is not None:` を `is None` に反転しても `total != sum` を `==` にしても
    テストスイートが緑のままだった。
    """

    def _payload(self, fc, counts=(0, 0, 3, 1)) -> dict:
        p = dict(BASE_PAYLOAD)
        for k, v in zip(("blocker_count", "critical_count", "major_count", "minor_count"), counts):
            p[k] = v
        if fc is None:
            p.pop("findings_class", None)
        else:
            p["findings_class"] = fc
        return p

    def test_matching_total_passes(self):
        r = self.publish(self._payload({"lint": 1, "test": 2, "judgement": 1}))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_total_mismatch_is_rejected(self):
        """合計が報告件数と合わなければ publish を止める（契約に強制力を与える）."""
        r = self.publish(self._payload({"lint": 1, "test": 1, "judgement": 0}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("一致しない", r.stderr)
        self.assertEqual(self.events(), [])

    def test_non_integer_is_rejected(self):
        r = self.publish(self._payload({"lint": "1", "test": 2, "judgement": 1}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("非負整数でない", r.stderr)

    def test_bool_is_rejected(self):
        """`isinstance(True, int)` は真なので bool を弾かないと合計計算が静かに狂う."""
        r = self.publish(self._payload({"lint": True, "test": 2, "judgement": 1}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("非負整数でない", r.stderr)

    def test_missing_key_is_rejected(self):
        r = self.publish(self._payload({"lint": 1, "test": 3}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("非負整数でない", r.stderr)

    def test_absent_field_is_allowed(self):
        """**フィールド自体が無い回は落とさない**（契約の範囲外まで publish を止めない）."""
        r = self.publish(self._payload(None))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_counts_missing_skips_the_sum_check(self):
        """件数フィールドが揃っていない回は突合しない（型検証だけ効く）."""
        p = dict(BASE_PAYLOAD)
        p["findings_class"] = {"lint": 9, "test": 9, "judgement": 9}
        r = self.publish(p)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_schema_marker_is_injected(self):
        self.publish(self._payload({"lint": 1, "test": 2, "judgement": 1}))
        self.assertEqual(self.last_payload()["findings_class"]["schema"], 1)


class BelowThresholdCountsValidationTest(ScriptTestBase):
    """`below_threshold_counts` の publish 側検証（GitHub issue #146）.

    **このフィールドの唯一の用途は分離**（本文を書いてから捨てた / 件数だけ返した）なので、
    `pre_adjust_counts` を超える値が 1 件でも混ざると分離そのものが意味を失う。
    `findings_class` と同じ位置・同じ流儀で fail-fast する契約をここで固定する。
    """

    def _payload(self, bt, pre=(0, 0, 3, 5)) -> dict:
        p = dict(BASE_PAYLOAD)
        p["pre_adjust_counts"] = dict(zip(("blocker", "critical", "major", "minor"), pre))
        if bt is None:
            p.pop("below_threshold_counts", None)
        else:
            p["below_threshold_counts"] = bt
        return p

    def test_within_pre_adjust_passes(self):
        r = self.publish(self._payload({"blocker": 0, "critical": 0, "major": 1, "minor": 5}))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_exceeding_pre_adjust_is_rejected(self):
        """再掲が元を超えるのは足し忘れか二重計上（定義上ありえない）."""
        r = self.publish(self._payload({"blocker": 0, "critical": 0, "major": 4, "minor": 5}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("超えている", r.stderr)
        self.assertEqual(self.events(), [], "矛盾したサンプルを残さない")

    def test_equal_to_pre_adjust_passes(self):
        """**全部が閾値未満だった回**は等しくなる（境界を弾かない）."""
        r = self.publish(self._payload({"blocker": 0, "critical": 0, "major": 3, "minor": 5}))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_non_integer_is_rejected(self):
        r = self.publish(self._payload({"blocker": 0, "critical": 0, "major": "1", "minor": 5}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("非負整数でない", r.stderr)

    def test_bool_is_rejected(self):
        """`isinstance(True, int)` は真なので、弾かないと比較が静かに通る."""
        r = self.publish(self._payload({"blocker": True, "critical": 0, "major": 1, "minor": 5}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("非負整数でない", r.stderr)

    def test_missing_key_is_rejected(self):
        """0 件でもキーを省かせない（「無かった」と「数えなかった」を潰さない）."""
        r = self.publish(self._payload({"blocker": 0, "critical": 0, "major": 1}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("非負整数でない", r.stderr)

    def test_absent_field_is_allowed_but_recorded_as_a_gap(self):
        """フィールドごと落ちた回は publish を止めないが、**欠測として可視化する**."""
        r = self.publish(self._payload(None))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("payload:below_threshold_counts",
                      self.last_payload().get("measurement_gaps", []))

    def test_pre_adjust_missing_skips_the_comparison(self):
        """`pre_adjust_counts` が揃っていない回は突合しない（型検証だけ効く）."""
        p = dict(BASE_PAYLOAD)
        p["pre_adjust_counts"] = {"blocker": 0, "critical": 0, "major": 1}
        p["below_threshold_counts"] = {"blocker": 0, "critical": 0, "major": 9, "minor": 9}
        r = self.publish(p)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_schema_marker_is_injected(self):
        self.publish(self._payload({"blocker": 0, "critical": 0, "major": 1, "minor": 5}))
        self.assertEqual(self.last_payload()["below_threshold_counts"]["schema"], 1)


class FindingsClassSignalTest(ScriptTestBase):
    """`findings_class` シグナルの下限（v2.68.0 / 「1 回で点灯しない」が核）."""

    def _rows(self, n: int, per: dict) -> list[dict]:
        return [{"effort": "high", "measurement_gaps": [], "findings_class": dict(per, schema=1)}
                for _ in range(n)]

    def _write(self, rows: list[dict]) -> None:
        (self.root / ".claude").mkdir(exist_ok=True)
        (self.root / ".claude" / "events.jsonl").write_text(
            "\n".join(json.dumps({"ts": "2026-08-1%d T%02d:00:00Z".replace(" ", "") % (i // 24, i % 24),
                                   "plugin": "code-review:self-review",
                                   "event": "review:completed", "payload": r}, ensure_ascii=False)
                       for i, r in enumerate(rows)) + "\n", encoding="utf-8")

    def test_single_review_does_not_fire(self):
        """**指摘が何件あってもレビュー 1 回では点灯しない**（下限の単位が回数であること）."""
        self._write(self._rows(1, {"lint": 30, "test": 0, "judgement": 0}))
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertNotIn("lint で捕まる層", self.signals(out))

    def test_enough_reviews_and_findings_fire(self):
        self._write(self._rows(9, {"lint": 8, "test": 1, "judgement": 1}))
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("lint で捕まる層", out)

    def test_exactly_at_the_row_minimum_fires(self):
        """**下限ちょうどで点灯する**（`>=` を `>` に狭める変異を殺す境界テスト）."""
        self._write(self._rows(8, {"lint": 8, "test": 1, "judgement": 1}))
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("lint で捕まる層", out)

    def test_test_side_signal_at_the_row_minimum_fires(self):
        self._write(self._rows(8, {"lint": 1, "test": 8, "judgement": 1}))
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("回帰テストで捕まる層", out)

    def test_test_side_signal_does_not_fire_on_a_single_review(self):
        """test 側も**回数**の下限が効くこと（`and` を `or` に緩める変異を殺す）."""
        self._write(self._rows(1, {"lint": 0, "test": 30, "judgement": 0}))
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertNotIn("回帰テストで捕まる層", self.signals(out))

    def test_exactly_at_the_ratio_threshold_fires(self):
        """**しきい値ちょうど（55%）で点灯する**（`>=` を `>` に狭める変異を殺す）."""
        self._write(self._rows(11, {"lint": 11, "test": 5, "judgement": 4}))   # 11/20 = 55%
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("lint で捕まる層", self.signals(out))

    def test_just_below_the_ratio_does_not_fire(self):
        """**50% では点灯しない**（しきい値を実測ベースライン 43% 域まで下げる変異を殺す）."""
        self._write(self._rows(11, {"lint": 10, "test": 5, "judgement": 5}))   # 10/20 = 50%
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertNotIn("lint で捕まる層", self.signals(out))

    def test_below_the_ratio_does_not_fire(self):
        """ベースライン域（40%）でも点灯しないこと."""
        self._write(self._rows(9, {"lint": 4, "test": 3, "judgement": 3}))
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertNotIn("lint で捕まる層", self.signals(out))

    def test_schema_filter_is_currently_inert(self):
        """**版マーカー層別は現時点で何も除外しない**ことを表明する.

        `schema_of` は欠落・`0` を `1` に丸めるので `>= 1` は恒真。前方互換のフックとして
        正しいが、`dropped_schema: 0` を「層別が効いている」と読める形なので、
        **恒真であること自体をテストで固定**しておく（分類の定義を変えて 2 に上げたら
        このテストが落ちる＝そのとき初めて除外の挙動を書く）。
        """
        rows = [{"effort": "high", "measurement_gaps": [],
                 "findings_class": {"lint": 8, "test": 1, "judgement": 1, "schema": 0}}
                for _ in range(9)]
        self._write(rows)
        out = self.run_script(RETRO, "--json", env=self._env()).stdout
        fc = json.loads(out)["findings_class"]
        self.assertEqual(fc["dropped_schema"], 0, "schema 0 が除外されている（丸めの前提が変わった）")
        self.assertEqual(fc["n"], 9)

    def test_zero_findings_is_not_reported_as_missing(self):
        """**「指摘 0 件」と「未収録」を同一視しない**（`--json` だけ正しい状態を作らない）."""
        self._write(self._rows(3, {"lint": 0, "test": 0, "judgement": 0}))
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("n=3 回", out)
        self.assertNotIn("持つサンプルが 0 件", out)


if __name__ == "__main__":
    unittest.main()
