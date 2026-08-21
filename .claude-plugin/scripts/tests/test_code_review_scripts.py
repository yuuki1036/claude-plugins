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
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from git_env import scrub

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
        # **ここも `_env()` を通す**。`_env()` にだけスクラブが入っていて `setUp` に
        # 入っていなかったため、linked worktree から commit すると `git init` 以降が
        # **実リポジトリ**に当たっていた（GitHub issue #158 / 詳細は `git_env` の docstring）
        env = self._env()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True, env=env)
        # **リポジトリ内に author を設定する**。env の `GIT_AUTHOR_*` は init commit にしか
        # 効かず、テストが独自に `git commit` すると **CI（global config が無い環境）で
        # だけ失敗する**（実測: ubuntu で `git commit` が黙って失敗し、rename のはずの diff が
        # 「新規ファイル」になってテストが落ちた）
        for key, value in (("user.email", "t@example.com"), ("user.name", "t")):
            subprocess.run(["git", "config", key, value], cwd=self.root, check=True, env=env)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"],
                       cwd=self.root, check=True, env=env)

    def _env(self, **extra: str) -> dict[str, str]:
        env = scrub(TMPDIR=str(self.root / "tmp"), CLAUDE_PLUGIN_ROOT=str(PLUGIN))
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


class SkipReasonValidationTest(ScriptTestBase):
    """動的層の `skip_reason` の語彙検証（`missing_coverage` / #132 と同型）.

    **期待値はスクリプトの `SKIP_REASONS` を読まず、doc（`## 16`）から独立に書く** —
    検証機構の期待値をその機構自身で作ると、壊れていても全件 pass する（CLAUDE.md）。
    """

    def _payload(self, field: str, value, *, fired=False) -> dict:
        p = {k: (dict(v) if isinstance(v, dict) else v) for k, v in BASE_PAYLOAD.items()}
        p[field] = {"fired": fired}
        if value is not ...:                      # `...` はキーごと落とす
            p[field]["skip_reason"] = value
        return p

    def test_canonical_vocabulary_passes(self):
        """doc `## 16` が列挙する値は 3 層とも通る."""
        for field, allowed in (
                ("adversarial_verify",
                 ("effort", "config", "scope", "emergency", "no-eligible-findings")),
                ("recall_skeptic", ("effort", "config", "no-surface", "emergency", "scope")),
                ("meta_reviewer", ("effort", "config", "no-high-severity", "size-tier",
                                   "emergency", "scope"))):
            for reason in allowed:
                with self.subTest(field=field, reason=reason):
                    r = self.publish(self._payload(field, reason))
                    self.assertEqual(r.returncode, 0, r.stderr)

    def test_drifted_spelling_is_rejected(self):
        """実データに出た綴り割れ（`no-surface` → `surface-none` 等）を落とす."""
        for bad in ("surface-none", "surface-not-detected"):
            with self.subTest(bad=bad):
                r = self.publish(self._payload("recall_skeptic", bad))
                self.assertEqual(r.returncode, 1)
                self.assertIn("語彙外", r.stderr)
                self.assertEqual(self.events(), [], "FATAL なのに publish されている")

    def test_vocabulary_is_per_layer(self):
        """**層をまたいだ流用も落とす** — 層ごとにゲートの意味が違う."""
        r = self.publish(self._payload("recall_skeptic", "no-high-severity"))
        self.assertEqual(r.returncode, 1, "meta の語彙が skeptic で通っている")
        r = self.publish(self._payload("meta_reviewer", "no-surface"))
        self.assertEqual(r.returncode, 1, "skeptic の語彙が meta で通っている")

    def test_free_text_is_rejected(self):
        bad = "effort（high 以下のため）"
        r = self.publish(self._payload("meta_reviewer", bad))
        self.assertEqual(r.returncode, 1)
        self.assertIn("語彙外", r.stderr)
        # **値をそのまま見せる**（`ensure_ascii=True` だと `\uXXXX` になり、日本語の混入では
        # 何を直せばいいのか読めないメッセージになる）
        self.assertIn(bad, r.stderr)

    def test_fired_true_is_not_validated(self):
        """`fired=true` の回は見ない（skip 理由の集計に入らないので実害が無い）.

        ここを厳格にすると、計測に影響しない書き方の揺れで publish が丸ごと死ぬ。
        **語彙外の値で確かめる** — 語彙内の値だと「見ていない」と「見て通した」が同じ結果になる。
        """
        r = self.publish(self._payload("recall_skeptic", "起動したので理由なし", fired=True))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_missing_reason_becomes_a_gap_not_a_failure(self):
        """書き忘れは**寄せ先を推測できない**ので落とさず可視化する（実測 8/49 件）."""
        for value in (None, ...):
            with self.subTest(value=value):
                r = self.publish(self._payload("recall_skeptic", value))
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("payload:recall_skeptic.skip_reason",
                              self.last_payload()["measurement_gaps"])

    def test_recorded_reason_does_not_raise_a_gap(self):
        """**理由が書けている回に gap を立てない** — 立てると欠測率が常時 100% になり、
        「⚠️ が出たときだけ行動する」契約が壊れる（否定側の liveness ガード）."""
        r = self.publish(self._payload("recall_skeptic", "no-surface"))
        self.assertEqual(r.returncode, 0, r.stderr)
        gaps = self.last_payload()["measurement_gaps"]
        self.assertNotIn("payload:recall_skeptic.skip_reason", gaps)
        # gap 欄そのものが消えていたら上の assertNotIn は恒真になる
        self.assertIsInstance(gaps, list)

    def test_fired_missing_keeps_the_fired_gap(self):
        """`fired` ごと落ちた回は `.fired` 側の gap のまま（是正先が違う）."""
        p = {k: (dict(v) if isinstance(v, dict) else v) for k, v in BASE_PAYLOAD.items()}
        p["recall_skeptic"] = {"surface": False}
        self.publish(p)
        gaps = self.last_payload()["measurement_gaps"]
        self.assertIn("payload:recall_skeptic.fired", gaps)
        self.assertNotIn("payload:recall_skeptic.skip_reason", gaps,
                         "同じ欠落に 2 つの是正先が立っている")


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

    def write_transcript(self, waves: list[list[int]], scale: int = 1,
                         ends: dict[int, int] | None = None) -> None:
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
                               "message": {"usage": {"output_tokens": 10 * scale,
                                                     "cache_creation_input_tokens": 20 * scale,
                                                     "cache_read_input_tokens": 30 * scale}}})

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
                # agent transcript は「起動行 + 終了行」の 2 行。**末尾行の timestamp が
                # 終了時刻**（GitHub issue #153）。`ends` にその体の index が
                # 無ければ終了行を持たない（欠測経路の再現）
                end_off = None if ends is None else ends.get(idx)
                lines = [row(ts)]
                if end_off is not None:
                    lines.append(row((base + timedelta(seconds=end_off)).isoformat() + "Z"))
                (sub / ("agent-%d.jsonl" % idx)).write_text("\n".join(lines) + "\n",
                                                            encoding="utf-8")
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

    def test_wave_gap_is_split_into_agent_and_idle(self):
        """**wave 間ギャップの内訳を分ける**（GitHub issue #153）.

        `max_inter_wave_sec` は「wave N 起動 → wave N+1 起動」なので、agent が回って
        いた時間とオーケストレーターの統合作業時間が合算されている。どちらが支配的かで
        打ち手が正反対（wave を減らす / 往復を減らす）なので、分けないまま是正すると
        「wave を消したのに fleet が縮まない」を踏む。
        """
        # wave 1 = agent 0,1（0 秒起動 / 終了は 500 と 600 = 最後は 600）→ wave 2 = agent 2（1000 秒起動）
        # ギャップ 1000 秒 = agent 実行 600 + オーケストレーター 400
        self.write_transcript([[0, 0], [1000]], ends={0: 500, 1: 600, 2: 1200})
        self.publish(env=self.env_home())
        d = self.last_payload()["dispatch"]
        self.assertEqual(d["schema"], 3, "schema を上げずにフィールドだけ足している")
        self.assertEqual(d["max_inter_wave_sec"], 1000)
        self.assertEqual(d["inter_wave_agent_sec"], 600, "wave 内の**最後**の終了で測る")
        self.assertEqual(d["inter_wave_idle_sec"], 400)
        self.assertEqual(d["inter_wave_agent_sec"] + d["inter_wave_idle_sec"],
                         d["max_inter_wave_sec"], "内訳の和が総和と一致していない")

    def test_wave_gap_picks_the_largest_gap_not_the_first(self):
        """**argmax を守る**（セルフレビューで検出 / 変異 `i = 0` が生存していた）.

        既存の gap fixture は全部 2 wave（ギャップ 1 本）で、`max(range(...), key=...)` が
        恒等になるため「最大を選ぶ」振る舞いを一度も観測していなかった。explorer →
        reviewer → 反証 は設計上 3 wave 以上なので、破れるのは例外系ではなく主経路。
        壊れると内訳の和 == 総和が破れ、retro の agent 側比率がそのまま歪む。
        """
        # ギャップは 200（wave1→2）と 1000（wave2→3）。内訳は**後者**について出す
        self.write_transcript([[0], [200], [1200]], ends={0: 100, 1: 300, 2: 1300})
        self.publish(env=self.env_home())
        d = self.last_payload()["dispatch"]
        self.assertEqual(d["max_inter_wave_sec"], 1000)
        self.assertEqual((d["inter_wave_agent_sec"], d["inter_wave_idle_sec"]), (100, 900))
        self.assertEqual(d["inter_wave_agent_sec"] + d["inter_wave_idle_sec"],
                         d["max_inter_wave_sec"], "内訳の和が総和と一致していない")

    def test_wave_gap_is_zero_for_a_batched_run(self):
        """1 wave の回は `(0, 0)`（**欠測ではなく実値**）. retro 側の除外根拠になる契約."""
        self.write_transcript([[0, 5]], ends={0: 300, 1: 400})
        self.publish(env=self.env_home())
        d = self.last_payload()["dispatch"]
        self.assertEqual(d["verdict"], "batched")
        self.assertEqual((d["inter_wave_agent_sec"], d["inter_wave_idle_sec"]), (0, 0))

    def test_wave_gap_is_missing_when_an_end_is_unavailable(self):
        """終了時刻が 1 体でも取れなければ**両方 -1**（欠測）.

        取れた体だけで max を採ると「まだ回っていた時間」が短く出て **idle が過大**に
        なり、「オーケストレーターが遅い」という誤った打ち手を選ばせる。
        """
        self.write_transcript([[0, 0], [1000]], ends={0: 500, 2: 1200})   # agent 1 に終了行が無い
        self.publish(env=self.env_home())
        d = self.last_payload()["dispatch"]
        self.assertEqual(d["inter_wave_agent_sec"], -1)
        self.assertEqual(d["inter_wave_idle_sec"], -1)
        # wave 構成そのものは起動時刻だけで決まるので判定は生きている
        self.assertEqual(d["wave_sizes"], [2, 1])
        self.assertEqual(d["max_inter_wave_sec"], 1000)

    def test_wave_gap_absorbs_an_overrunning_agent(self):
        """次の wave 起動時点でまだ回っている agent がいたら、ギャップは**全部 agent 側**.

        `min(last_end, 次の起動)` でクランプしないと `idle` が負になり、`max(0, ...)` で
        0 に潰れて内訳の和が総和と合わなくなる。
        """
        self.write_transcript([[0], [600]], ends={0: 900, 1: 1000})
        self.publish(env=self.env_home())
        d = self.last_payload()["dispatch"]
        self.assertEqual(d["inter_wave_agent_sec"], 600)
        self.assertEqual(d["inter_wave_idle_sec"], 0)

    def test_tokens_carry_cache_read(self):
        """**重み付け最大の項を落とさない**（GitHub issue #156）.

        schema 1 は `output` と main の `cache_write` しか載せておらず、コスト比で
        45% を占める `cache_read` が payload の外にあった（`pending-optimizations.md
        ## 計測の基準値`）。`measure-tokens.sh --json` は元から返しているので、
        **落としていたのは publish 側**。
        """
        # 1k tokens 単位で丸めるので、fixture も k オーダーまで持ち上げる
        # （10/20/30 のままだと全部 0.0 に潰れ、「載っている」と「0」を区別できない）
        self.write_transcript([[0, 5]], scale=1000)
        self.publish(env=self.env_home())
        t = self.last_payload()["tokens"]
        self.assertEqual(t["schema"], 2, "schema を上げずにフィールドだけ足している")
        # main は 1 メッセージ / sub は 2 体 × 1 メッセージ
        self.assertEqual(t["main_cache_read_k"], 30.0)
        self.assertEqual(t["sub_cache_read_k"], 60.0)
        self.assertEqual(t["sub_cache_write_k"], 40.0)
        # 既存フィールドを壊していない
        self.assertEqual(t["sub_output_k"], 20.0)
        self.assertEqual(t["sub_agents"], 2)

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
        # **現行値をリテラルで固定する**（`>= 2` に緩めない）。集計側は `>=` で前方互換に
        # 読むが、publisher 側は版を上げたときにここが落ちて「集計の層別と契約 doc も
        # 直したか」を問う trip wire になる（実測: #153 で schema 3 に上げた回に発火した）
        self.assertEqual(p["dispatch"]["schema"], 3, "schema を上げたら retro の層別と契約 doc も直したか")
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

    # ---- `agents`（自己申告）と `dispatch.agents`（機械計測）の突合 / issue #154 ----

    def _with_agents(self, agents: dict, **layers) -> dict:
        p = {k: (dict(v) if isinstance(v, dict) else v) for k, v in BASE_PAYLOAD.items()}
        p["agents"] = agents
        for field, fired in layers.items():
            p[field] = {"fired": fired, "skip_reason": None if fired else "effort"}
        return p

    def test_matching_agent_counts_raise_no_gap(self):
        """一致する回に gap を立てない（立つと発生率が常時 100% になり信号が死ぬ）."""
        self.write_transcript([[0, 5]])                     # 実測 2 体
        self.publish(self._with_agents({"explorer": 0, "reviewer": 2}), env=self.env_home())
        p = self.last_payload()
        self.assertEqual(p["dispatch"]["agents"], 2, "前提: 機械計測が 2 体")
        self.assertNotIn("agents-mismatch", p["measurement_gaps"])

    def test_mismatch_is_recorded_without_failing_publish(self):
        """**fail-fast にしない** — 止めるとその回の計測が丸ごと消える（#154）."""
        self.write_transcript([[0, 5, 9]])                  # 実測 3 体 / 申告 2 体
        r = self.publish(self._with_agents({"explorer": 0, "reviewer": 2}), env=self.env_home())
        self.assertEqual(r.returncode, 0, r.stderr)
        p = self.last_payload()
        self.assertIn("agents-mismatch", p["measurement_gaps"])
        # **両フィールドが残っていること**が「差の大きさを gap に載せない」判断の前提
        self.assertEqual(p["dispatch"]["agents"], 3)
        self.assertEqual(p["agents"]["reviewer"], 2)

    def test_fired_layers_are_added_before_comparing(self):
        """`agents` は meta / skeptic を含まない契約なので `fired` ぶんを足してから比べる.

        補正しないと self-review まで恒常的にずれ、**review 固有という信号が埋もれる**。
        """
        self.write_transcript([[0, 5, 9, 12]])              # 実測 4 体 = reviewer 2 + 動的層 2
        self.publish(self._with_agents({"explorer": 0, "reviewer": 2},
                                       recall_skeptic=True, meta_reviewer=True),
                     env=self.env_home())
        p = self.last_payload()
        self.assertEqual(p["dispatch"]["agents"], 4, "前提: 機械計測が 4 体")
        self.assertNotIn("agents-mismatch", p["measurement_gaps"],
                         "動的層を足さずに比べている")

    def test_non_headcount_keys_are_not_summed(self):
        """`verify_findings` / `explorer_waves` は**体数ではない**ので足さない.

        どちらも `agents` の中に整数で同居しているため、キー名で絞らずに整数を拾うと
        黙って加算され、**一致しているのに `agents-mismatch` が立ち続ける**（＝欠測率が
        飽和して #154 の観測目的そのものが消える）。
        """
        self.write_transcript([[0, 5]])                     # 実測 2 体
        self.publish(self._with_agents(
            {"explorer": 0, "reviewer": 2, "verify_findings": 10}), env=self.env_home())
        p = self.last_payload()
        self.assertEqual(p["agents"]["explorer_waves"], 0, "前提: 打点由来の値も同居している")
        self.assertNotIn("agents-mismatch", p["measurement_gaps"])

    def test_unfired_layers_are_not_added(self):
        """`fired=false` の層は起動していないので足さない（逆方向の取り違え）."""
        self.write_transcript([[0, 5]])                     # 実測 2 体
        self.publish(self._with_agents({"explorer": 0, "reviewer": 2},
                                       recall_skeptic=False, meta_reviewer=False),
                     env=self.env_home())
        self.assertNotIn("agents-mismatch", self.last_payload()["measurement_gaps"])

    def test_undeterminable_dispatch_does_not_raise_the_mismatch_gap(self):
        """発行パターンを引けない回は `dispatch` gap のまま（是正先が違う）."""
        self.publish(self._with_agents({"explorer": 0, "reviewer": 2}), env=self.env_home())
        gaps = self.last_payload()["measurement_gaps"]
        self.assertIn("dispatch", gaps, "前提: 判定不能な回")
        self.assertNotIn("agents-mismatch", gaps)


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
                  schema: int | None = 2, solo_run: int = 3,
                  gap: tuple[int, int] | None = None) -> dict:
        d = {"agents": agents, "waves": waves, "wave_sizes": [1] * waves,
             "max_solo_run": solo_run, "max_inter_wave_sec": 600, "span_sec": 900,
             "verdict": verdict}
        if gap is not None:
            d["inter_wave_agent_sec"], d["inter_wave_idle_sec"] = gap
        if schema is not None:
            d["schema"] = schema
        return {"effort": "high", "measurement_gaps": [], "dispatch": d}

    def _tokens(self, tier: str, cache_read_k, agents, effort: str = "high",
                schema: int = 2) -> dict:
        return {"effort": effort, "size_tier": tier, "measurement_gaps": [],
                "tokens": {"schema": schema, "window": "since-t0",
                           "main_output_k": 100.0, "sub_output_k": 200.0,
                           "sub_cache_read_k": cache_read_k, "sub_agents": agents}}

    def test_per_agent_cache_read_is_layered_by_effort_and_tier(self):
        """**1 体あたり**で出す（GitHub issue #156）.

        総量だけでは「体数が多い」と「1 体が読みすぎ」を切り分けられない。tier は担当
        ファイル数を、effort は 1 体あたりの探索量を決めるので、層別しない中央値は
        両方の交絡を負う（`## 3` の r を tier 内で取るのと同じ理由 / issue #151）。
        """
        self._events([self._tokens("medium", 50000.0, 10),   # 5,000k/体
                      self._tokens("medium", 42000.0, 6),    # 7,000k/体 → 中央値 6,000k
                      self._tokens("small", 9000.0, 3, effort="xhigh")])  # 3,000k/体
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("**1 体あたり cache_read**", out)
        self.assertIn("| high/medium | 2 | 6000 k |", out)
        self.assertIn("| xhigh/small | 1 | 3000 k |", out)

    def test_per_agent_cache_read_never_divides_by_zero(self):
        """`sub_agents` が 0 / 欠測の回は**除算せず落とす**.

        0 で割ると集計全体が例外で死ぬ（その回だけ静かに欠測、にはならない）。
        欠測を 1 体に倒すのも不可 — 1 体あたりが総量に化けて基準値比較を壊す。
        """
        self._events([self._tokens("medium", 50000.0, 0),
                      self._tokens("medium", 50000.0, None),
                      self._tokens("medium", 20000.0, 4)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.signals(out)
        self.assertIn("| high/medium | 1 | 5000 k |", out,
                      "除算できない回を分母に入れているか、落としすぎている")

    def test_waiting_line_names_the_actual_reason(self):
        """待ち行は**落とした理由を件数で出し分ける**（セルフレビューで検出）.

        旧実装は「`sub_cache_read_k` を持つサンプル待ち（schema 2）」と原因を版マーカーに
        断定していたが、この else には ①版が古い ②`sub_agents` が 0 / 欠測で除算不可 の
        2 経路が落ちる。②を①と報告すると publisher を直しにいく誤診になる。
        """
        self._events([self._tokens("medium", None, 5, schema=1),        # 版が古い
                      self._tokens("medium", 50000.0, 0)])              # 除算不可
        out = self.run_script(RETRO, env=self._env()).stdout
        self.signals(out)
        self.assertIn("`tokens.schema >= 2` 未満で除外 1", out)
        self.assertIn("除算不可 1", out)
        self.assertNotIn("**1 体あたり cache_read**（effort", out, "表が出てしまっている")

    def test_per_agent_cache_read_survives_a_half_missing_payload(self):
        """`sub_cache_read_k` だけ `null` の回で**落ちない**（nightly 変異 #157）.

        `cr < 0` を `cr is None` より先に評価すると `TypeError`。retro は
        `set -uo pipefail`（`-e` なし）+ 末尾 `exit 0` なので **rc 0 のまま出力が途中で
        切れる**。dispatch 側（`test_wave_gap_survives_a_half_missing_payload`）と同じ型で、
        そちらだけ塞いで**こちらを塞いでいなかった**。版ゲートを通る schema 2 で作る
        （schema 1 だと先に `continue` してこの行に到達しない）。
        """
        self._events([self._tokens("medium", None, 5),
                      self._tokens("medium", 20000.0, 4)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.signals(out)                     # 途中で死んでいないこと
        self.assertIn("| high/medium | 1 | 5000 k |", out, "落ちない回まで捨てている")

    def test_per_agent_cache_read_gates_on_schema(self):
        """版マーカーで先に切る（フィールド在否で代用しない / 冒頭の層別の原則）."""
        self._events([self._tokens("medium", 99999.0, 1, schema=1),   # 旧版は混ぜない
                      self._tokens("medium", 20000.0, 4)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("| high/medium | 1 | 5000 k |", out, "旧 schema を分母に入れている")

    def test_wave_gap_breakdown_is_reported(self):
        """最大ギャップの内訳を出す（GitHub issue #153）— 支配側で打ち手が正反対になる."""
        self._events([self._dispatch("layered", schema=3, waves=2, agents=7, solo_run=1,
                                     gap=(900, 100)),
                      self._dispatch("layered", schema=3, waves=2, agents=5, solo_run=1,
                                     gap=(700, 300))])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("**最大ギャップの内訳**（n=2）", out)
        self.assertIn("agent 実行 中央値 800 秒", out)
        self.assertIn("オーケストレーター 中央値 200 秒", out)
        self.assertIn("**agent 側 80%**（回ごとの比の中央値）", out)

    def test_wave_gap_share_is_a_median_of_per_run_ratios_not_a_pool(self):
        """**比率は回ごとの比の中央値**（総和プールではない / セルフレビューで検出）.

        プールド比 `sum(a)/sum(a+i)` は巨大ギャップ 1 件に支配され、同じ行に並ぶ中央値と
        逆の結論を出す。この fixture は 5 件中 4 件が idle 支配（10:90）で、外れ値 1 件だけが
        agent 支配。プールドなら 85% 前後（= agent 支配）に反転する。
        """
        rows = [self._dispatch("layered", schema=3, waves=2, agents=5, solo_run=1, gap=g)
                for g in [(10, 90), (11, 89), (12, 88), (13, 87), (3000, 200)]]
        self._events(rows)
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("**agent 側 12%**（回ごとの比の中央値）", out,
                      "プールド比に戻っている（外れ値 1 件が結論を握る）")
        self.assertIn("**idle 支配**", out, "n=5 は下限を満たすので打ち手を出す")

    def test_wave_gap_withholds_the_verdict_below_the_sample_floor(self):
        """n < 5 では**数値だけ出して打ち手を出さない**（このファイルの他の打ち手行と同じ流儀）."""
        self._events([self._dispatch("layered", schema=3, waves=2, agents=5, solo_run=1,
                                     gap=(900, 100))])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("**agent 側 90%**", out, "数値は n=1 でも出す（観測の可視化）")
        self.assertIn("**打ち手は出さない**（n < 5", out)
        self.assertNotIn("agent 支配", out, "下限未満で打ち手を出している")

    def test_wave_gap_breakdown_drops_missing_not_zeroes_it(self):
        """欠測（-1）は**分母から外す**. 0 に倒すと idle 支配の誤読になる."""
        self._events([self._dispatch("layered", schema=3, waves=2, agents=7, solo_run=1,
                                     gap=(-1, -1)),
                      self._dispatch("layered", schema=3, waves=2, agents=5, solo_run=1,
                                     gap=(600, 400))])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("**最大ギャップの内訳**（n=1）", out, "欠測を分母に入れている")
        self.assertIn("**agent 側 60%**", out)

    def test_wave_gap_breakdown_keeps_zero_agent_time(self):
        """`agent 実行 0 秒` は**実測値**であって欠測ではない（変異テストで生存した経路）.

        agent が既に終わっていてギャップ全部がオーケストレーター作業、という回こそ
        idle 支配の証拠。0 を欠測扱いで落とすと**分母が agent 支配側に偏る**。
        """
        self._events([self._dispatch("layered", schema=3, waves=2, agents=5, solo_run=1,
                                     gap=(0, 900))])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("**最大ギャップの内訳**（n=1）", out, "agent 0 秒の回を落としている")
        self.assertIn("**agent 側 0%**", out)

    def test_wave_gap_excludes_batched_zero_gap_without_dying(self):
        """`batched` の回は `(0, 0)` で載る（1 wave = ギャップ無し）. 分母に入れない.

        入れると `sum(a+i) == 0` で ZeroDivisionError。しかも retro は `set -uo pipefail`
        （`-e` なし）+ 末尾 `exit 0` なので、**rc 0 のまま stdout が途中で切れる** —
        `signals()` の docstring が警告している型そのもの。liveness ガードを付ける。
        """
        self._events([self._dispatch("batched", schema=3, waves=1, agents=3, solo_run=1,
                                     gap=(0, 0))])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.signals(out)                     # 途中で死んでいないこと
        self.assertIn("`batched` でギャップ無し 1", out, "除外理由を潰している")
        self.assertNotIn("agent 側", out)

    def test_wave_gap_counts_missing_separately_from_no_gap(self):
        """除外理由の**2 つのカウンタが独立に効く**（変異テストで 3 件生存した経路）.

        全件が欠測（-1）の回は「終了時刻の欠測」であって「`batched` でギャップ無し」ではない。
        両者を取り違えると、是正先が transcript 側か wave 構成側かで正反対になる。
        """
        self._events([self._dispatch("layered", schema=3, waves=2, agents=6, solo_run=1,
                                     gap=(-1, -1)),
                      self._dispatch("layered", schema=3, waves=2, agents=6, solo_run=1,
                                     gap=(-1, -1))])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.signals(out)
        self.assertIn("終了時刻の欠測 2", out)
        self.assertIn("`batched` でギャップ無し 0", out, "欠測をギャップ無しに数えている")

    def test_wave_gap_survives_a_half_missing_payload(self):
        """片側だけ `null` の payload で**落ちない**（`or` の短絡が None 比較を守っている）.

        `a < 0` を `a is None` より先に評価すると `TypeError`。retro は `set -uo pipefail`
        （`-e` なし）+ 末尾 `exit 0` なので、**rc 0 のまま出力が途中で切れる**。
        """
        self._events([self._dispatch("layered", schema=3, waves=2, agents=6, solo_run=1,
                                     gap=(None, 5))])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.signals(out)                     # 途中で死んでいないこと
        self.assertIn("終了時刻の欠測 1", out)

    def test_wave_gap_verdict_boundaries_are_inclusive(self):
        """支配側の判定は **60% / 40% ちょうどを含む**（境界を狭めると「支配側なし」に落ちる）."""
        for gap, expected in [((600, 400), "**agent 支配**"), ((400, 600), "**idle 支配**")]:
            with self.subTest(gap=gap):
                self._events([self._dispatch("layered", schema=3, waves=2, agents=5,
                                             solo_run=1, gap=gap)] * 5)
                out = self.run_script(RETRO, env=self._env()).stdout
                self.assertIn(expected, out)
                self.assertNotIn("支配側なし", out)

    def test_wave_gap_waiting_line_separates_absence_from_exclusion(self):
        """「まだ載っていない」と「載ったが全件除外」を区別する（原因の断定をやめる）."""
        self._events([self._dispatch("layered", waves=2, agents=6, solo_run=1)])  # schema 2
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("`dispatch.schema >= 3` が 0 件", out)
        self.assertIn("終了時刻の欠測 0", out)


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

    # ---- 降格の型別内訳（issue #150）----------------------------------------
    def _axes_row(self, plugin: str, **types) -> dict:
        d = {k: 0 for k in ("base_derived", "misread", "overstated_impact",
                            "miscategorized", "unknown")}
        d.update(types)
        return {"_plugin": plugin, "effort": "high", "measurement_gaps": [],
                "adversarial_verify": {"fired": True, "skip_reason": None, "gate_schema": 2,
                                       "calibration_schema": 2, "confirmed": 0, "refuted": 0,
                                       "uncertain": 0, "contested": 0,
                                       "severity_inflated": sum(d.values()),
                                       "inflated_axes": d}}

    def test_demote_types_are_broken_down_by_skill(self):
        """**非対称そのものが観測対象**なので skill を潰して合算しない（#150）."""
        self._events([self._axes_row("code-review:review", base_derived=8, misread=2),
                      self._axes_row("code-review:self-review", overstated_impact=1,
                                     miscategorized=1)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("反証 `severity_inflated` の型別内訳", out)
        self.assertIn("| review | 1 | 10 | 80% | 20% | 0% | 0% | 0% |", out)
        self.assertIn("| self-review | 1 | 2 | 0% | 0% | 50% | 50% | 0% |", out)

    def test_upstream_demotions_use_the_same_vocabulary(self):
        """上流（reviewer の閾値跨ぎ降格）と下流（反証）を同じ軸で並べて読む."""
        row = self._axes_row("code-review:review", base_derived=1)
        row["below_threshold_counts"] = {
            "blocker": 0, "critical": 0, "major": 0, "minor": 9,
            "demoted_types": {"base_derived": 0, "misread": 3, "overstated_impact": 0,
                              "miscategorized": 0, "unknown": 0}}
        self._events([row])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("上流降格（`## below-threshold` 跨ぎ）の型別内訳", out)
        self.assertIn("| review | 1 | 3 | 0% | 100% | 0% | 0% | 0% |", out)

    def test_missing_breakdown_says_it_is_waiting(self):
        """黙ると「型は取れている」と読まれる（#131 と同じ型の誤読）."""
        self._events([self._verdict(2, 5) for _ in range(3)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("`inflated_axes` / `demoted_types` を持つサンプル待ち", out)
        self.assertNotIn("反証 `severity_inflated` の型別内訳", out)

    def test_no_verdict_sample_does_not_announce_waiting(self):
        """反証が 1 度も走っていない回まで待ち行を出さない（待ち行がノイズになる）."""
        self._events([{"effort": "high", "measurement_gaps": []} for _ in range(3)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertNotIn("`inflated_axes` / `demoted_types` を持つサンプル待ち", out)

    # ---- 体数 vs fleet 時間の相関（issue #151）------------------------------
    # `size_tier` は体数と fleet の**両方**を決めるので、層別しない相関は tier の効果を
    # 体数の効果として計上する。下の fixture は tier 内 r=0.000 / 層別なし r=0.944 で、
    # まさにその交絡だけを取り出したもの
    def _corr_rows(self, tier: str, base_agents: int, base_fleet: int, n: int = 12) -> list[dict]:
        return [{"effort": "high", "measurement_gaps": [], "size_tier": tier,
                 "duration_fleet_min": base_fleet + (i * 3) % 10,
                 "agents": {"reviewer": base_agents + i % 6}} for i in range(n)]

    def test_correlation_is_stratified_by_size_tier(self):
        """tier 内で無相関なら、層別なしの r が高くてもシグナルを出さない."""
        self._events(self._corr_rows("small", 2, 10) + self._corr_rows("large", 12, 100))
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("| small | 12 | 0.000 | 体数はレバーではない |", out)
        self.assertIn("| large | 12 | 0.000 | 体数はレバーではない |", out)
        self.assertIn("層別なしの r = 0.944", out, "参考値としての層別なしが消えている")
        self.assertIn("発火条件には使わない", out)
        self.assertNotIn("体数と fleet 時間の相関が tier 内で高い", self.signals(out))

    def test_strong_correlation_inside_a_tier_still_fires(self):
        """層別で黙らせすぎない liveness — tier 内で高ければ従来どおり鳴る."""
        rows = [{"effort": "high", "measurement_gaps": [], "size_tier": "medium",
                 "duration_fleet_min": 10 + 3 * i, "agents": {"reviewer": 2 + i}}
                for i in range(12)]
        self._events(rows)
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("| medium | 12 | 1.000 | ⚠️ 高い |", out)
        self.assertIn("体数と fleet 時間の相関が tier 内で高い（medium r=1.00 n=12）",
                      self.signals(out))

    def test_tier_at_exactly_the_minimum_is_judged(self):
        """`n == R_MIN_N` は判定する側（境界を 1 つ狭めると 10 件貯めても黙る）."""
        self._events(self._corr_rows("small", 2, 10, n=10))
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("| small | 10 | 0.232 | 体数はレバーではない |", out)
        self.assertNotIn("体数と壁時計の関係は判定しない", out)

    def test_correlation_exactly_at_the_strong_threshold_fires(self):
        """`|r| == R_STRONG` は発火する側（`>` に狭めると閾値ちょうどが漏れる）.

        fixture は **r がちょうど 0.6 になる**ように作ってある（偏差平方和 100 / 100・
        積和 60 で `60/(10*10)`）。乱数で近い値を取ると境界を跨いだか分からない
        """
        agents = [13, 3, 13, 3, 8, 8, 8, 8, 8, 8]
        fleet = [27, 13, 19, 21, 20, 20, 20, 20, 20, 20]
        self._events([{"effort": "high", "measurement_gaps": [], "size_tier": "medium",
                       "duration_fleet_min": f, "agents": {"reviewer": a}}
                      for a, f in zip(agents, fleet)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("| medium | 10 | 0.600 | ⚠️ 高い |", out)
        self.assertIn("体数と fleet 時間の相関が tier 内で高い（medium r=0.60 n=10）",
                      self.signals(out))

    def test_thin_tier_is_undecidable_rather_than_a_signal(self):
        """n < 10 の tier は r が 1.0 でも判定不能に倒す（単発点灯の防止）."""
        rows = [{"effort": "high", "measurement_gaps": [], "size_tier": "large",
                 "duration_fleet_min": 10 + 3 * i, "agents": {"reviewer": 2 + i}}
                for i in range(9)]
        self._events(rows)
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("| large | 9 | 1.000 | 判定不能（n < 10） |", out)
        self.assertIn("体数と壁時計の関係は判定しない", out)
        self.assertNotIn("体数と fleet 時間の相関が tier 内で高い", self.signals(out))


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


class DemoteTypesValidationTest(ScriptTestBase):
    """降格の型別内訳の publish 側検証（GitHub issue #150）.

    **用途は打ち手の選択**（`base_derived` が支配的なら直すのは prompt の表現ではなく
    reviewer に渡る base 側の情報）。内訳が本体とずれると「型が取れなかった件」と
    「数え漏らした件」が混ざり、その切り分けが消える。
    """

    TYPES = ("base_derived", "misread", "overstated_impact", "miscategorized", "unknown")

    def _axes(self, **over) -> dict:
        d = {k: 0 for k in self.TYPES}
        d.update(over)
        return d

    def _payload(self, axes=None, inflated=2, demoted=None, below=(0, 0, 0, 4)) -> dict:
        p = dict(BASE_PAYLOAD)
        p["pre_adjust_counts"] = {"blocker": 0, "critical": 0, "major": 1, "minor": 9}
        p["below_threshold_counts"] = dict(zip(("blocker", "critical", "major", "minor"), below))
        if demoted is not None:
            p["below_threshold_counts"]["demoted_types"] = demoted
        av = dict(BASE_PAYLOAD["adversarial_verify"])
        av.update({"confirmed": 0, "refuted": 0, "uncertain": 0,
                   "severity_inflated": inflated, "contested": 0})
        if axes is not None:
            av["inflated_axes"] = axes
        p["adversarial_verify"] = av
        return p

    def test_matching_axes_total_passes(self):
        r = self.publish(self._payload(self._axes(base_derived=2), demoted=self._axes()))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.last_payload()["adversarial_verify"]["inflated_axes"]["base_derived"], 2)
        # **記録されている回に gap を立てない**（立てると retro が母集団から外し、
        # 内訳を書いた回ほど集計から消える）
        self.assertNotIn("payload:adversarial_verify.inflated_axes",
                         self.last_payload()["measurement_gaps"])

    def test_axes_total_mismatch_is_rejected(self):
        """合計が `severity_inflated` と合わなければ止める（型不明は `unknown` へ）."""
        r = self.publish(self._payload(self._axes(misread=1)))
        self.assertEqual(r.returncode, 1)
        self.assertIn("severity_inflated", r.stderr)
        self.assertEqual(self.events(), [])

    def test_unknown_bucket_absorbs_a_missing_axis(self):
        """軸が返らなかった件を捨てずに数える経路（合計は維持される）."""
        r = self.publish(self._payload(self._axes(base_derived=1, unknown=1)))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_missing_type_key_is_rejected(self):
        axes = self._axes(base_derived=2)
        axes.pop("unknown")
        r = self.publish(self._payload(axes))
        self.assertEqual(r.returncode, 1)
        self.assertIn("非負整数でない", r.stderr)

    def test_bool_is_rejected(self):
        """`isinstance(True, int)` は真なので、弾かないと合計が静かに狂う."""
        r = self.publish(self._payload(self._axes(base_derived=True, unknown=1)))
        self.assertEqual(r.returncode, 1)
        self.assertIn("非負整数でない", r.stderr)

    def test_absent_axes_is_allowed_but_recorded_as_a_gap(self):
        """内訳が要る回（降格が起きた回）の記録漏れは gap にする."""
        r = self.publish(self._payload(None))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("payload:adversarial_verify.inflated_axes",
                      self.last_payload()["measurement_gaps"])

    def test_no_inflated_verdict_does_not_raise_a_gap(self):
        """降格が 0 件の回まで gap にすると、記録漏れの信号がノイズに埋もれる."""
        self.publish(self._payload(None, inflated=0, below=(0, 0, 0, 0)))
        self.assertNotIn("payload:adversarial_verify.inflated_axes",
                         self.last_payload()["measurement_gaps"])

    def test_demoted_types_exceeding_below_threshold_is_rejected(self):
        """跨ぐ降格で落ちた分は `## below-threshold` に計上済み — 超えるのは二重計上."""
        r = self.publish(self._payload(self._axes(base_derived=2),
                                       demoted=self._axes(misread=5), below=(0, 0, 0, 4)))
        self.assertEqual(r.returncode, 1)
        self.assertIn("below_threshold_counts の合計", r.stderr)

    def test_absent_demoted_types_is_recorded_as_a_gap(self):
        self.publish(self._payload(self._axes(base_derived=2)))
        self.assertIn("payload:below_threshold_counts.demoted_types",
                      self.last_payload()["measurement_gaps"])

    def test_empty_below_threshold_does_not_raise_a_gap(self):
        self.publish(self._payload(self._axes(base_derived=2), below=(0, 0, 0, 0)))
        self.assertNotIn("payload:below_threshold_counts.demoted_types",
                         self.last_payload()["measurement_gaps"])


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


class RetroExplicitLogsTest(ScriptTestBase):
    """`--logs` による複数ログの合算（GitHub issue #160）.

    **判断に足りるサンプル数は合算しないと出ない**（実測: 判定に `fired >= 15` を要求する
    シグナルがあるのに、1 リポジトリ単独では構造的に届かない）。合算そのものは 30 行の
    jq で書けるが、それを毎回手で組むと**母集団が記録に残らない**（#150 の「83 件」と
    #160 の「91 件」はどのファイルを拾ったか再現できない）。ここで測るのは
    ①複数ログを足せるか ②重複を落とすか ③**母集団を言えるか**の 3 点。
    """

    def write_log(self, rel: str, rows: list[dict], start: int = 0) -> Path:
        """`self.root` 配下の任意の位置にログを置く（別リポジトリの events.jsonl 相当）."""
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(
            json.dumps({"ts": "2026-08-%02dT00:00:00Z" % (start + i + 1),
                        "plugin": "code-review:self-review",
                        "event": "review:completed", "payload": r}, ensure_ascii=False)
            for i, r in enumerate(rows)) + "\n", encoding="utf-8")
        return path

    def base_rows(self, n: int) -> list[dict]:
        return [{"effort": "high", "size_tier": "medium", "measurement_gaps": []}
                for _ in range(n)]

    def retro(self, *args: str) -> str:
        res = self.run_script(RETRO, *args, env=self._env())
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout

    def test_sums_events_across_logs(self):
        a = self.write_log("repo-a/.claude/events.jsonl", self.base_rows(2))
        b = self.write_log("repo-b/.claude/events.jsonl", self.base_rows(3), start=10)
        out = self.retro("--logs", str(a), str(b))
        self.assertIn("n=5", out)

    def test_reports_which_log_contributed_how_many(self):
        """**母集団を言えないと「⚠️ が出たときだけ行動する」契約が成立しない**."""
        a = self.write_log("repo-a/.claude/events.jsonl", self.base_rows(2))
        b = self.write_log("repo-b/.claude/events.jsonl", self.base_rows(3), start=10)
        out = self.retro("--logs", str(a), str(b))
        self.assertIn("ログ 2 本", out)
        self.assertIn("`%s` … 2 件" % a, out)
        self.assertIn("`%s` … 3 件" % b, out)

    def test_a_log_with_no_samples_is_still_listed(self):
        """0 件のログを黙って消さない（「見ていない」と「見たが 0 件」は別）."""
        a = self.write_log("repo-a/.claude/events.jsonl", self.base_rows(2))
        empty = self.write_log("repo-b/.claude/events.jsonl", [])
        out = self.retro("--logs", str(a), str(empty))
        self.assertIn("`%s` … 0 件" % empty, out)

    def test_the_same_event_in_two_files_is_counted_once(self):
        """worktree へコピーされた events.jsonl は同一イベントを持つ（実測: 3 本が同じ 70 件）."""
        a = self.write_log("repo-a/.claude/events.jsonl", self.base_rows(3))
        copy = self.root / "wt" / ".claude" / "events.jsonl"
        copy.parent.mkdir(parents=True)
        copy.write_text(a.read_text(encoding="utf-8"), encoding="utf-8")
        out = self.retro("--logs", str(a), str(copy))
        self.assertIn("n=3", out)
        self.assertIn("重複イベント除外 3 件", out)
        self.assertIn("`%s` … 0 件" % copy, out)

    def test_the_same_path_twice_is_read_once(self):
        """**合計が n を超える表示を作らない**。glob が重なるだけで起きる."""
        a = self.write_log("repo-a/.claude/events.jsonl", self.base_rows(3))
        out = self.retro("--logs", str(a), "./" + str(a.relative_to(self.root)))
        self.assertIn("n=3", out)
        self.assertIn("ログ 1 本（同一ファイルの重複指定 1 本を除外）", out)

    def test_json_carries_the_population(self):
        a = self.write_log("repo-a/.claude/events.jsonl", self.base_rows(2))
        b = self.write_log("repo-b/.claude/events.jsonl", self.base_rows(3), start=10)
        got = json.loads(self.retro("--logs", str(a), str(b), "--json"))
        self.assertEqual(got["n"], 5)
        self.assertEqual(got["sources"], [{"path": str(a), "n": 2}, {"path": str(b), "n": 3}])
        self.assertEqual(got["sources_dropped_duplicates"], 0)

    def test_flags_after_logs_are_still_parsed(self):
        """`--logs` は後続の非フラグ引数だけを取る（`--last` を食べない）."""
        a = self.write_log("repo-a/.claude/events.jsonl", self.base_rows(5))
        got = json.loads(self.retro("--logs", str(a), "--last", "2", "--json"))
        self.assertEqual(got["n"], 2)

    def test_an_unreadable_path_is_fatal(self):
        """**明示指定の誤りを「サンプルが少ない」に化けさせない**（exit 2 = 判定不能）."""
        res = self.run_script(RETRO, "--logs", str(self.root / "nope.jsonl"), env=self._env())
        self.assertEqual(res.returncode, 2)
        self.assertIn("読めない", res.stderr)

    def test_logs_without_a_value_is_fatal(self):
        res = self.run_script(RETRO, "--logs", env=self._env())
        self.assertEqual(res.returncode, 2)
        self.assertIn("パスが必要", res.stderr)

    def test_explicit_logs_replace_discovery(self):
        """**探索結果と混ぜない**（再現性のために「渡したものだけ」を見る）."""
        self.write_log(".claude/events.jsonl", self.base_rows(4))   # 探索で拾われる側
        a = self.write_log("repo-a/.claude/events.jsonl", self.base_rows(2))
        got = json.loads(self.retro("--logs", str(a), "--json"))
        self.assertEqual(got["n"], 2)
        self.assertEqual([r["path"] for r in got["sources"]], [str(a)])

    def test_discovery_still_reports_its_source(self):
        """`--logs` を使わない既定の経路でも母集団は出す."""
        self.write_log(".claude/events.jsonl", self.base_rows(3))
        out = self.retro()
        self.assertIn("ログ 1 本", out)
        self.assertIn(".claude/events.jsonl` … 3 件", out)


if __name__ == "__main__":
    unittest.main()
