#!/usr/bin/env python3
"""`lib/live_ledger.py` と publish の `tokens_live`（code-review の mod がその場で数えた usage）.

記録の形は mod（`hooks/review-ledger.ts`）が書く契約で、mod 側のテスト
（`mods/code-review/tests/review-ledger.test.ts`）が同じ形を書き出すことを見ている。
ここは読む側: 窓の切り方・main / sub の分け方・transcript の値との突き合わせ。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from test_code_review_scripts import PLUGIN, TranscriptFixture

LIVE = PLUGIN / "scripts" / "lib" / "live_ledger.py"

T0 = 1_800_000_000


def ledger(steps: list, agents: dict | None = None, started: int = (T0 - 60) * 1000, **over) -> dict:
    return {"schema": 1, "session": "s1", "started": started, "written": started,
            "models": ["opus", "sonnet"], "steps": steps, "agents": agents or {},
            "truncated": False, **over}


def step(t_sec: float, agent: str = "", out: int = 1000, cw: int = 2000, cr: int = 30000) -> list:
    return [int(t_sec * 1000), agent, 0 if agent == "" else 1, 5, out, cw, cr]


def spawn(t_sec: float, background: bool = False) -> dict:
    return {"t": int(t_sec * 1000), "type": "general-purpose", "background": background,
            "fork": False, "parent": None}


class LiveLedgerCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def run_live(self, data, *args: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
        path = self.dir / "led.json"
        if data is not None:
            path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        argv = list(args) if args else [str(T0), str(path)]
        return subprocess.run([sys.executable, str(LIVE), *argv], capture_output=True, text=True,
                              env=env, timeout=30)

    def summary(self, data) -> dict:
        res = self.run_live(data)
        self.assertEqual(res.returncode, 0, res.stderr)
        return json.loads(res.stdout)

    def test_window_and_main_sub_split(self):
        out = self.summary(ledger(
            [step(T0 - 1, out=99_000),                     # 窓の外
             step(T0), step(T0 + 1, out=2500),
             step(T0 + 2, "a1"), step(T0 + 3, "a1"), step(T0 + 4, "a1"),
             step(T0 + 2, "a2", cr=1000)],
            # a3 は t0 ちょうど（窓に入る）。体の数と background の数をずらし、どちらを数えたか見分ける
            {"a1": spawn(T0 + 1), "a2": spawn(T0 + 1, background=True), "a3": spawn(T0),
             "old": spawn(T0 - 5, True)}))
        self.assertEqual(out, {
            "schema": 1, "covered": True, "truncated": False, "main_steps": 2,
            "main_output_k": 3.5, "main_cache_write_k": 4.0, "main_cache_read_k": 60.0,
            "sub_output_k": 4.0, "sub_cache_write_k": 8.0, "sub_cache_read_k": 91.0,
            "sub_agents": 2, "sub_turns": [3, 1], "sub_turns_max": 3, "sub_turns_median": 2,
            "spawns": 3, "background_spawns": 1,
        })

    def test_without_subagents(self):
        out = self.summary(ledger([step(T0)]))
        self.assertEqual((out["sub_agents"], out["sub_turns"], out["sub_turns_max"], out["sub_turns_median"]),
                         (0, [], 0, None))

    def test_the_step_at_t0_is_in_the_window(self):
        self.assertEqual(self.summary(ledger([step(T0)]))["main_steps"], 1)

    def test_a_ledger_started_after_t0_is_not_covered(self):
        """mod が途中で読み込まれた回は窓の頭が欠ける（値は小さめに出る）."""
        self.assertFalse(self.summary(ledger([step(T0 + 5)], started=(T0 + 1) * 1000))["covered"])
        self.assertTrue(self.summary(ledger([step(T0 + 5)], started=T0 * 1000))["covered"])

    def test_truncated_is_passed_through(self):
        self.assertTrue(self.summary(ledger([step(T0)], truncated=True))["truncated"])

    def test_malformed_steps_are_skipped(self):
        out = self.summary(ledger([step(T0), [T0 * 1000, "", 0, 1, 2, 3], ["x", "", 0, 1, 2, 3, 4],
                                   [T0 * 1000, None, 0, 1, 2, 3, 4], [T0 * 1000, "", 0, True, 2, 3, 4]]))
        self.assertEqual(out["main_steps"], 1)

    def test_nothing_is_printed_when_the_window_has_no_main_step(self):
        """窓の空振りを 0 として載せない（`tokens` の main.n == 0 と同じ扱い）."""
        for name, data in {
            "窓に main が無い": ledger([step(T0 - 1), step(T0 + 1, "a1")]),
            "版が違う": ledger([step(T0)], schema=2),
            "started が無い": ledger([step(T0)], started=None),
            "JSON でない": "{",
            "object でない": [1, 2],
            "ファイルが無い": None,
        }.items():
            with self.subTest(name):
                res = self.run_live(data)
                self.assertEqual((res.returncode, res.stdout), (1, ""), res.stderr)

    def test_the_path_comes_from_the_session_id_and_the_config_dir(self):
        cfg = self.dir / "cfg"
        (cfg / "live").mkdir(parents=True)
        (cfg / "live" / "sess-1.json").write_text(json.dumps(ledger([step(T0)])), encoding="utf-8")
        env = {"PATH": "/usr/bin:/bin", "CLAUDE_REVIEW_CONFIG_DIR": str(cfg)}
        res = self.run_live(None, str(T0), env={**env, "CLAUDE_CODE_SESSION_ID": "sess-1"})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(res.stdout)["main_steps"], 1)
        for sid in ("", "../live/sess-1", "sess 1"):
            with self.subTest(sid=sid):
                res = self.run_live(None, str(T0), env={**env, "CLAUDE_CODE_SESSION_ID": sid})
                self.assertEqual((res.returncode, res.stdout), (1, ""))

    def test_usage_errors_exit_2(self):
        for args in (["abc"], [], [str(T0), "a", "b"], ["-1"]):
            with self.subTest(args=args):
                res = subprocess.run([sys.executable, str(LIVE), *args], capture_output=True, text=True,
                                     timeout=30)
                self.assertEqual(res.returncode, 2)


class LivePublishTest(TranscriptFixture):
    """publish が mod の記録を `tokens_live` に載せ、transcript の `tokens` と突き合わせる."""

    def write_ledger(self, data: dict) -> None:
        live = self.review_config / "live"
        live.mkdir(exist_ok=True)
        (live / "s1.json").write_text(json.dumps(data), encoding="utf-8")

    def transcript_now(self, waves: list[list[int]], **kw) -> None:
        """transcript も打点（t0 = 実行時刻）の後ろに置く（既定の過去の日付だと `tokens` の窓が空になる）."""
        base = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=2)
        self.write_transcript(waves, base=base, **kw)

    def ledger_now(self, sub_turns: list[int]) -> dict:
        """打点（t0 = 実行時刻）の後ろに step を並べる."""
        now = time.time() + 1
        steps = [step(now, out=10_000)]
        for i, n in enumerate(sub_turns):
            steps += [step(now, "a%d" % i)] * n
        return ledger(steps, started=int((now - 600) * 1000))

    def test_live_numbers_are_published_beside_the_transcript(self):
        self.transcript_now([[0, 5]], scale=1000, ends={0: 20})     # transcript: sub_turns [2, 1]
        self.write_ledger(self.ledger_now([2, 1]))
        self.timing("start")
        self.publish(env=self.env_home())
        p = self.last_payload()
        live = p["tokens_live"]
        self.assertEqual((live["schema"], live["covered"], live["sub_turns"], live["sub_agents"]),
                         (1, True, [2, 1], 2))
        main_out = p["tokens"]["main_output_k"]
        self.assertEqual(live["agree"], {"sub_agents": True, "sub_turns": True,
                                         "main_output_ratio": round(10.0 / main_out, 2)})

    def test_disagreement_is_recorded(self):
        self.transcript_now([[0, 5]], scale=1000, ends={0: 20})
        self.write_ledger(self.ledger_now([3]))
        self.timing("start")
        self.publish(env=self.env_home())
        agree = self.last_payload()["tokens_live"]["agree"]
        self.assertEqual((agree["sub_agents"], agree["sub_turns"]), (False, False))

    def test_without_subagents_on_both_sides_turns_agree(self):
        self.transcript_now([])
        self.write_ledger(self.ledger_now([]))
        self.timing("start")
        self.publish(env=self.env_home())
        self.assertTrue(self.last_payload()["tokens_live"]["agree"]["sub_turns"])

    def test_live_numbers_survive_an_unresolved_transcript(self):
        """transcript を引けない回（#246 / #263）でも、mod の記録は載る（突き合わせる相手は無い）."""
        self.write_ledger(self.ledger_now([1]))
        self.timing("start")
        self.publish(env=self.env_home())
        p = self.last_payload()
        self.assertIn("session-unresolved", p["measurement_gaps"])
        self.assertNotIn("tokens", p)
        self.assertEqual(p["tokens_live"]["sub_turns"], [1])
        self.assertNotIn("agree", p["tokens_live"])

    def test_no_ledger_means_no_field_and_no_gap(self):
        """mods が無効な環境では記録が無いのが普通。呼び出し側が書いた値は捨てる."""
        self.transcript_now([[0]])
        self.timing("start")
        payload = {**json.loads(json.dumps(__import__("test_code_review_scripts").BASE_PAYLOAD)),
                   "tokens_live": {"schema": 1, "sub_turns": [99]}}
        self.publish(payload, env=self.env_home())
        p = self.last_payload()
        self.assertNotIn("tokens_live", p)
        self.assertFalse([g for g in p["measurement_gaps"] if "live" in g])

    def test_review_payload_also_carries_it(self):
        self.transcript_now([[0]])
        self.write_ledger(self.ledger_now([1]))
        self.timing("start", "--pr", "7")
        res = self.publish(None, "code-review:review", "--pr", "7", env=self.env_home())
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("tokens_live", self.last_payload())


if __name__ == "__main__":
    unittest.main()
