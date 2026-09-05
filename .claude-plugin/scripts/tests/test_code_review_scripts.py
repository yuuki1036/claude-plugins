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
import re
from datetime import datetime, timedelta, timezone
import subprocess
import sys
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
BACKFILL = PLUGIN / "scripts" / "review-backfill.sh"
MEASURE = PLUGIN / "scripts" / "measure-tokens.sh"

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
    # **報告件数 4 つは必須で 0 件でも省かない**（#215）。無いと publish が
    # `payload:report_counts.missing` を立てるので、既定の fixture は契約どおりにしておく
    "blocker_count": 0, "critical_count": 0, "major_count": 1, "minor_count": 0,
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

    def timeline(self, **markers: int) -> None:
        """計測ファイルを**任意の時間軸で**直接組み立てる.

        `mark` は `date +%s`（実行時刻）しか書けないので、fixture の transcript（固定の
        過去時刻）と別の軸になり、**整合ガードが常に偽になって補完経路を一度も通らない**。
        ここだけはファイルを直接書いて両者を同じ軸に乗せる。

        **`ScriptTestBase` に置く**（GitHub issue #161 のセルフレビュー指摘）: 同じ書式を
        組み立てる helper が 2 つあると、`review-timing.sh` のマーカー行書式が変わったとき
        直す箇所が 2 つになる。
        """
        path = Path(self.timing("start").stdout.strip())
        path.write_text("".join("%s %d\n" % (k, v) for k, v in markers.items()),
                        encoding="utf-8")

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



class DryRunTest(ScriptTestBase):
    """`--dry-run` は組み立てまで走らせて publish だけしない（GitHub issue #194）.

    動機は実測の汚染: 動作確認のため実リポジトリでこのスクリプトを素のまま叩き、計測の
    母集団に検証用の行が 1 件混入した。**`CLAUDE_PROJECT_DIR` を前置きしても効かない** —
    書込先は worktree 対策で `--git-common-dir` から導出した `MAIN_ROOT` に固定される。

    **肯定・否定の両側を置く**（片側だけだと `[ "$DRY_RUN" = "1" ]` の条件反転が生き残る）。
    """

    def dry(self, **kw) -> subprocess.CompletedProcess[str]:
        """`publish()` は第 1・2 引数が payload / plugin なので、追加フラグはその後ろに置く."""
        return self.publish(None, "code-review:self-review", "--dry-run", **kw)

    def test_dry_run_writes_no_event(self):
        self.full_run()
        r = self.dry()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.events(), [], "dry-run なのに events.jsonl に書かれている")

    def test_without_dry_run_still_publishes(self):
        """否定側。フラグを足したことで本番経路が壊れていないこと."""
        self.full_run()
        r = self.publish()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.events()), 1)

    def test_dry_run_prints_the_payload_as_one_json_line_on_stdout(self):
        """stdout は payload 1 行だけ（`| jq .` で読める契約）."""
        self.full_run()
        out = self.dry().stdout.strip()
        self.assertEqual(len(out.splitlines()), 1, "stdout が 1 行でない: %r" % out)
        json.loads(out)  # 壊れていれば例外で落ちる

    def test_dry_run_payload_matches_what_a_real_publish_would_store(self):
        """**dry-run の出力が本番と同じであること**が、この経路で検証する意味の前提.

        期待値を dry-run 自身から作らない（生成と検証が同じ経路を共有すると自己整合で
        通ってしまう / v2.63.1 の SSoT pin と同型）。実 publish の結果と突き合わせる。
        """
        self.full_run()
        dry = json.loads(self.dry().stdout.strip())
        self.full_run()
        self.publish()
        real = self.last_payload()
        # 実行ごとに変わる値は除いて比べる（所要時間・タイムスタンプ由来）
        volatile = {k for k in real if k.startswith("duration_")}
        for key in volatile:
            dry.pop(key, None)
            real.pop(key, None)
        self.assertEqual(dry, real, "dry-run の payload が本番と違う")

    def test_dry_run_does_not_consume_the_timing_file(self):
        """publish 済みマークも掃除もしない（dry-run が本番の状態を進めない）."""
        path = self.full_run()
        self.dry()
        self.assertTrue(path.exists(), "dry-run が計測ファイルを消している")
        # 続けて本番 publish が成立する = 状態が進んでいない
        self.assertEqual(self.publish().returncode, 0)
        self.assertEqual(len(self.events()), 1)
        self.assertFalse(path.exists(), "本番 publish 後は消える")

    def test_dry_run_reports_the_destination_it_skipped(self):
        """書込先を出す（どこを汚さずに済んだかが読めないと確認にならない）."""
        self.full_run()
        err = self.dry().stderr
        self.assertIn("dry-run", err)
        self.assertIn(str(self.root), err, "書込先が出ていない: %r" % err)


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


class TranscriptFixture(ScriptTestBase):
    """transcript fixture の組み立てだけを持つ土台（**テストは持たない**）.

    `TokenAndDispatchPayloadTest` に生えていた helper を切り出したもの。テスト同士が
    継承し合うと親のテストが子の名前で**もう一度**走る（実測: 14 件が二重実行された）。
    """

    def setUp(self) -> None:
        super().setUp()
        self.home = self.root / "home"
        (self.home / ".claude" / "projects").mkdir(parents=True)

    def env_home(self) -> dict[str, str]:
        return self._env(HOME=str(self.home))

    def write_transcript(self, waves: list[list[int]], scale: int = 1,
                         ends: dict[int, int] | None = None,
                         base: datetime | None = None,
                         main_models: tuple[str, ...] = ("claude-opus-5",),
                         sub_models: tuple[str, ...] | None = None) -> None:
        """cwd に対応する slug へ session + subagent を置く.

        `waves[i]` は**同一メッセージから発行した** agent の起動オフセット（秒）。
        transcript は 1 メッセージを tool_use ブロックごとに別行へ分解して書くので、
        fixture も「行は別・`message.id` は共通」の形に揃える（GitHub issue #149）。
        """
        slug = "".join(c if c.isalnum() else "-" for c in str(self.root))
        d = self.home / ".claude" / "projects" / slug
        d.mkdir(parents=True, exist_ok=True)
        # `base` を差し替えられるのは**打点との整合を実際に通すため**（GitHub issue #161）。
        # 補完値は `t0 <= v <= t2` を満たさないと採られないので、計測ファイルの時刻と
        # transcript の時刻を同じ時間軸に乗せる必要がある
        base = base or datetime(2026, 8, 18, 1, 0, 0)

        # **実 transcript の assistant 行は必ず `message.model` を持つ**（GitHub issue #169）。
        # fixture から落とすと publish が毎回 `models` 欠測になり、**欠測が既定の形**として
        # テストに焼き付く。既定で載せ、旧版・混在の経路は引数で明示的に作る
        def row(ts: str, model: str | None = "claude-opus-5") -> str:
            msg: dict = {"usage": {"output_tokens": 10 * scale,
                                   "cache_creation_input_tokens": 20 * scale,
                                   "cache_read_input_tokens": 30 * scale}}
            if model:
                msg["model"] = model
            return json.dumps({"type": "assistant", "timestamp": ts, "message": msg})

        # `main_models` が空タプルなら `model` を持たない行（`models` を引けない旧版の再現）。
        # 2 つ以上なら main 側が混在した回（実測: opus-5 → opus-4-8 → opus-5 の切替）
        subs = sub_models if sub_models is not None else main_models
        rows = [row((base + timedelta(seconds=i)).isoformat() + "Z", m)
                for i, m in enumerate(main_models or (None,))]
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
                sub_model = subs[idx % len(subs)] if subs else None
                lines = [row(ts, sub_model)]
                if end_off is not None:
                    lines.append(row((base + timedelta(seconds=end_off)).isoformat() + "Z",
                                     sub_model))
                (sub / ("agent-%d.jsonl" % idx)).write_text("\n".join(lines) + "\n",
                                                            encoding="utf-8")
                (sub / ("agent-%d.meta.json" % idx)).write_text(
                    json.dumps({"agentType": "general-purpose", "toolUseId": "tu-%d" % idx}),
                    encoding="utf-8")
                idx += 1
        (d / "s1.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")


class TokenAndDispatchPayloadTest(TranscriptFixture):
    """publish が `tokens` / `dispatch` を payload に載せる（GitHub issue #142 / #143）.

    - **#143**: self-review は `tokens` を構造的に載せていなかった（実測: このマシンの
      review:completed 37 件すべてで欠測）。体数削減・分冊の効果は全部そこに出るのに、
      主要レバーの効果が自動集計の外にあった
    - **#142**: `duration_fleet_min` は「9 体を逐次で回した 89 分」と「1 体が 89 分かかった」を
      区別できない。実測 16 回のうち 13 回が逐次発行で、累計 431 分を失っていた
    """

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
        self.assertEqual(d["schema"], 4, "schema を上げずにフィールドだけ足している")
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

    def test_a_bad_pre_adjust_vocabulary_raises_a_gap_without_blocking(self):
        """**契約外の `pre_adjust_counts` を可視化する**（GitHub issue #203）.

        `below_threshold_counts` は 4 severity 必須で `exit 1` するのに、対になる
        `pre_adjust_counts` は無検証だった。**fail-fast にはしない**（止めるとその回の計測が
        丸ごと消える / `agents-mismatch` と同じ判断）ので、gap を立てて集計側が外せる形にする。
        """
        p = {k: (dict(v) if isinstance(v, dict) else v) for k, v in BASE_PAYLOAD.items()}
        # 実データにあった形（2026-08-28T05:09:04Z）
        p["pre_adjust_counts"] = {"threshold": "MAJOR", "pre_major": 11, "pre_minor": 10}
        r = self.publish(p, env=self.env_home())
        self.assertEqual(r.returncode, 0, "fail-fast にしている（計測が丸ごと消える）")
        pub = self.last_payload()
        self.assertIn("payload:pre_adjust_counts.vocab", pub["measurement_gaps"])
        self.assertIn("pre_adjust_counts の語彙が契約外", r.stderr)
        self.assertIn("pre_major", r.stderr, "実際のキーを出していない（直す先が分からない）")

    def test_a_contract_shaped_pre_adjust_raises_no_vocab_gap(self):
        """契約どおりの回では立てない（**偽陽性を出さない**）."""
        self.publish(env=self.env_home())
        self.assertNotIn("payload:pre_adjust_counts.vocab",
                         self.last_payload()["measurement_gaps"])

    def test_a_sub_blank_run_falls_the_sub_side_to_null(self):
        """**sub 側の空振りを欠測に倒す**（GitHub issue #199）.

        `main.n > 0` を通っても、申告体数が 1 以上あるのに `sub_agents == 0` なら**窓が
        sub の transcript を覆っていない**。main 側は `main.n == 0` で守られているのに、
        sub 側は `main.n > 0` でありさえすれば `sub_output_k: 0.0` が素通りしていた（非対称）。
        `main_*` は生かし `sub_*` だけ None に倒し、`tokens-sub` で理由を残す。
        """
        # main セッションに usage 行はあるが sub agent は 1 体も窓に無い（`waves=[]`）。
        # `BASE_PAYLOAD` の `agents` は explorer 0 + reviewer 2 = 申告 2 体
        self.write_transcript([], scale=1000)
        self.publish(env=self.env_home())
        p = self.last_payload()
        self.assertIn("tokens", p, "main 側が生きているので tokens ごと落とさない")
        self.assertEqual(p["tokens"]["sub_agents"], 0, "前提: sub が空振りしている")
        self.assertIsNone(p["tokens"]["sub_output_k"], "sub 側の 0 を実値として載せている")
        self.assertIsNone(p["tokens"]["sub_cache_read_k"])
        self.assertIsNone(p["tokens"]["sub_cache_write_k"])
        self.assertIsNotNone(p["tokens"]["main_output_k"], "main 側まで落としている")
        self.assertIn("tokens-sub", p["measurement_gaps"])
        self.assertNotIn("tokens", p["measurement_gaps"], "main が生きているので tokens gap は立てない")

    def test_a_single_agent_review_still_flags_a_sub_blank(self):
        """**申告体数ちょうど 1 でも sub 空振りを倒す**（`>= 1` の境界 / GitHub issue #199）.

        reviewer 1 体だけの回（explorer なし）。ガードが `> 1` に狭まると、最小構成の
        レビューで sub 空振りが素通りする。
        """
        self.write_transcript([], scale=1000)
        p = {k: (dict(v) if isinstance(v, dict) else v) for k, v in BASE_PAYLOAD.items()}
        p["agents"] = {"explorer": 0, "reviewer": 1}     # 申告 1 体ちょうど
        self.publish(p, env=self.env_home())
        pub = self.last_payload()
        self.assertEqual(pub["tokens"]["sub_agents"], 0, "前提: sub が空振りしている")
        self.assertIn("tokens-sub", pub["measurement_gaps"])

    def test_a_zero_agent_review_does_not_flag_a_sub_blank(self):
        """申告 0 体の回では倒さない（sub を測る意味が無い ＝ ガードの下側）.

        `agents` が空 / 全ゼロの退化した回。sub が 0 なのは当然で、欠測ではない。
        """
        self.write_transcript([], scale=1000)
        p = {k: (dict(v) if isinstance(v, dict) else v) for k, v in BASE_PAYLOAD.items()}
        p["agents"] = {"explorer": 0, "reviewer": 0}
        self.publish(p, env=self.env_home())
        pub = self.last_payload()
        self.assertNotIn("tokens-sub", pub["measurement_gaps"],
                         "申告 0 体の回で sub 空振りを立てている")

    def test_a_healthy_sub_run_keeps_its_values(self):
        """sub が窓内にいる回では倒さない（**空振り判定が正常系を巻き込まない**）."""
        self.write_transcript([[0, 5]], scale=1000)
        self.publish(env=self.env_home())
        p = self.last_payload()
        self.assertEqual(p["tokens"]["sub_agents"], 2)
        self.assertEqual(p["tokens"]["sub_output_k"], 20.0)
        self.assertNotIn("tokens-sub", p["measurement_gaps"])

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
        self.assertEqual(p["dispatch"]["schema"], 4, "schema を上げたら retro の層別と契約 doc も直したか")
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


class AppendixCountTest(ScriptTestBase):
    """🔁 付録の件数を payload に載せる（GitHub issue #168）.

    **付録に列挙しただけでは「報告 0 件の回」と「価値 0 の回」が payload 上で同じ形になる。**
    実測（PR 398 / 21 体 / 62 分）は severity 4 バケツすべて 0 だが付録に 18 件が並び、
    うち 4 件は人間に推され 1 件はテストの穴が実証済みだった。集計側がこれを「報告 0 件」と
    読むと、体数キャップ・effort profile・閾値のどの打ち手も分子が欠けたまま過小評価に倒れる。
    """

    def test_the_counts_are_carried_with_a_schema_marker(self):
        self.publish(dict(BASE_PAYLOAD, appendix={"listed": 18, "recommended": 4}))
        a = self.last_payload()["appendix"]
        self.assertEqual((a["listed"], a["recommended"]), (18, 4))
        self.assertEqual(a["schema"], 1, "版マーカーが注入されていない")

    def test_a_recommendation_cannot_exceed_the_listing(self):
        """**構造の不変条件**（`※ 推奨:` は付録に並べた行に付けるマーカー）.

        この値は LLM の自己申告で機械計測へ寄せる経路が無い。検証できるのはここだけ。
        """
        r = self.publish(dict(BASE_PAYLOAD, appendix={"listed": 2, "recommended": 3}))
        self.assertNotEqual(r.returncode, 0, "listed を超える recommended が通っている")
        self.assertIn("recommended", r.stderr)

    def test_zero_counts_are_not_omittable(self):
        """0 件でもキーを省かせない（「推した指摘が無かった」と「数えなかった」を潰さない）."""
        r = self.publish(dict(BASE_PAYLOAD, appendix={"listed": 0}))
        self.assertNotEqual(r.returncode, 0, "recommended の欠落が通っている")

    def test_zero_counts_are_accepted(self):
        """**通る側の境界**（`< 0` → `<= 0` の変異を殺す）.

        `{0,0}` は「付録に 1 件も出なかった回」＝最も頻度の高い入力。ここで fail-fast
        すると `review:completed` が丸ごと欠測し、#168 で足した計測が消える。
        """
        r = self.publish(dict(BASE_PAYLOAD, appendix={"listed": 0, "recommended": 0}))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.last_payload()["appendix"],
                         {"listed": 0, "recommended": 0, "schema": 1})

    def test_all_listed_items_may_be_recommended(self):
        """**等号は通る**（`> listed` → `>= listed` の変異を殺す）.

        全件を推す回は正当（`AppendixRetroTest` の推奨率 100% ケースがその形）。
        """
        r = self.publish(dict(BASE_PAYLOAD, appendix={"listed": 5, "recommended": 5}))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_non_object_appendix_is_rejected(self):
        """非 dict は fail-fast（既存 3 フィールドと同じ形 / セルフレビュー指摘）.

        素通しすると値が payload に残ったまま `payload:appendix` gap ＝「フィールドごと
        落ちた回」に化け、#168 が消そうとした潰れを型の穴から再生産する。
        """
        for bad in (18, "18", [18, 4]):
            with self.subTest(bad=bad):
                r = self.publish(dict(BASE_PAYLOAD, appendix=bad))
                self.assertNotEqual(r.returncode, 0, "非 dict の appendix が通っている")
                self.assertIn("appendix", r.stderr)

    def test_a_boolean_is_not_accepted_as_a_count(self):
        """`True` は `int` の派生なので素の isinstance を素通りする.

        件数フィールド全般で明示的に弾いている（`check_demote_types` と同じ理由）。
        通すと `recommended: True` が 1 件として集計に混ざる。
        """
        r = self.publish(dict(BASE_PAYLOAD, appendix={"listed": True, "recommended": 0}))
        self.assertNotEqual(r.returncode, 0, "bool が件数として通っている")
        self.assertIn("listed", r.stderr)

    def test_a_non_integer_is_rejected_without_crashing(self):
        """非整数は比較の前に弾く（**比較まで進むと TypeError で落ちる**）."""
        r = self.publish(dict(BASE_PAYLOAD, appendix={"listed": "18", "recommended": 4}))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr, "型エラーで落ちている（弾いていない）")

    def test_a_negative_count_is_rejected(self):
        r = self.publish(dict(BASE_PAYLOAD, appendix={"listed": 3, "recommended": -1}))
        self.assertNotEqual(r.returncode, 0)

    def test_a_missing_appendix_is_visible(self):
        """フィールドごと落ちた回を可視化する（層のオブジェクトと同じ扱い）."""
        self.publish(BASE_PAYLOAD)
        p = self.last_payload()
        self.assertNotIn("appendix", p, "空のオブジェクトを捏造している")
        self.assertIn("payload:appendix", p["measurement_gaps"])


class AppendixRetroTest(ScriptTestBase):
    """retro が「報告 0 件のうち推奨ありの回」を出す（GitHub issue #168）."""

    def _events(self, rows: list[dict]) -> None:
        log = self.root / ".claude" / "events.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("\n".join(
            json.dumps({"ts": "2026-08-1%d T00:%02d:00Z".replace(" ", "") % (i // 60, i % 60),
                        "plugin": "code-review:self-review",
                        "event": "review:completed", "payload": r}, ensure_ascii=False)
            for i, r in enumerate(rows)) + "\n", encoding="utf-8")

    def _row(self, listed: int, rec: int, reported: int) -> dict:
        return {"effort": "high", "measurement_gaps": [],
                "appendix": {"listed": listed, "recommended": rec, "schema": 1},
                "blocker_count": 0, "critical_count": 0,
                "major_count": reported, "minor_count": 0}

    def test_a_silent_run_with_recommendations_is_called_out(self):
        """**報告 0 件でも推奨ありなら空振りではない**（費用対効果の分子）."""
        self._events([self._row(18, 4, 0), self._row(3, 0, 0), self._row(5, 1, 2)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("報告 0 件の回 2 件のうち 1 件は推奨あり", out)

    def test_the_recommendation_rate_is_reported(self):
        """**推奨率そのものを見る**（全件が推奨に膨らむ失敗モードの検出）."""
        self._events([self._row(10, 10, 0)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("推奨率 100%", out)

    def test_a_malformed_appendix_is_excluded_from_the_population(self):
        """壊れた `appendix` は母数に入れない（**retro は他マシンが書いた JSON も読む**）.

        publish の fail-fast は自マシンの publish 経路にしか掛からない。`--logs` で
        別リポジトリのログを合算する経路（#160）では検証を通っていない値が来うるので、
        読む側でも落とす。潰すと欠けた値が 0 件として推奨率の分母に混ざる。
        """
        self._events([self._row(18, 4, 0),
                      {"effort": "high", "measurement_gaps": [], "blocker_count": 0,
                       "critical_count": 0, "major_count": 0, "minor_count": 0,
                       "appendix": {"recommended": 2, "schema": 1}}])   # listed 欠落
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("n=1", out, "壊れた行を母数に入れている")
        self.assertIn("列挙 18 件 / うち人間に推した 4 件", out)

    def test_each_new_gap_identifier_names_its_own_fix(self):
        """新識別子は**それぞれ別の是正先**を出す（既定の「打点箇所の見直し」に落とさない）.

        `gap_hint` の docstring どおり gap の種類で是正先が違う。既定に落ちると
        `models`（transcript の引き当て）にも語彙の寄せ漏れにも「打点を見直せ」と言う。
        #167 が上流と下流で識別子を分けた目的が、読む側で消える。
        """
        cases = [("models", "transcript の引き当て"),
                 ("axis-unknown", "axis 語彙"),
                 ("demoted-unknown", "降格型名"),
                 # #208。**`startswith("payload:")` の既定に落ちてはならない** — 置き場所と
                 # 語彙の話なので「テンプレートの記述漏れ」は誤った是正先になる
                 ("payload:demoted_types.misplaced", "ネストの誤り"),
                 ("payload:agents.vocab", "語彙違反"),
                 ("payload:agents.empty", "体数のキーが 1 つも無い")]
        for ident, expected in cases:
            with self.subTest(ident=ident):
                # GAP_MIN_N=5 / GAP_RATIO=20 を超える母集団を作る
                self._events([dict(self._row(1, 0, 1), measurement_gaps=[ident])
                              for _ in range(6)])
                out = self.run_script(RETRO, env=self._env()).stdout
                self.assertIn(ident, out, "gap がシグナルに出ていない")
                self.assertIn(expected, out, "是正先が既定文言に落ちている")
                self.assertNotIn("打点箇所の見直し", out)

    def test_an_empty_appendix_does_not_break_the_rate_line(self):
        """`listed` 合計 0 でゼロ割しない（`if tot_listed:` → `if True:` の変異を殺す）.

        付録 0 件は毎回起きる形。ガードが外れると `ZeroDivisionError` で **retro が
        途中で死ぬ**（付録節より後ろの出力が全部消える）。
        """
        self._events([self._row(0, 0, 0)])
        r = self.run_script(RETRO, env=self._env())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("列挙 0 件", r.stdout)
        self.assertNotIn("推奨率", r.stdout, "分母 0 で推奨率を出している")
        self.assertIn("計測の健全性", r.stdout, "付録節より後ろが出力されていない")

    def test_an_absent_field_is_not_read_as_no_recommendations(self):
        """旧版（`appendix` 無し）を「推奨なし」に潰さない."""
        self._events([{"effort": "high", "measurement_gaps": [], "blocker_count": 0,
                       "critical_count": 0, "major_count": 0, "minor_count": 0}])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("フィールドが載っていない", out)
        self.assertNotIn("報告 0 件の回", out, "旧版を母数に入れている")


class AxisUnknownGapTest(ScriptTestBase):
    """軸を寄せ損ねた回を可視化する（GitHub issue #167）.

    `inflated_axes` / `demoted_types` は反証 agent・reviewer が返す語彙を 4 型へ寄せて
    数える契約だが、**寄せ漏れは静かに通る** — 合計の突合は `unknown` に落としても
    一致するので検出できない。実測では `intended` 2 件が `base_derived` に寄らず
    `unknown` に落ち、review 側の唯一の型付きサンプルで `base_derived` を 8% と読むか
    23% と読むかが変わっていた（#150 の判断材料そのもの）。
    """

    def _axes(self, unknown: int, base: int = 0) -> dict:
        return {"base_derived": base, "misread": 0, "overstated_impact": 0,
                "miscategorized": 0, "unknown": unknown}

    def test_an_unmapped_axis_raises_the_gap(self):
        self.publish(dict(BASE_PAYLOAD,
                          adversarial_verify={"fired": True, "skip_reason": None,
                                              "severity_inflated": 3,
                                              "inflated_axes": self._axes(2, base=1)}))
        self.assertIn("axis-unknown", self.last_payload()["measurement_gaps"])

    def test_a_fully_mapped_run_is_not_flagged(self):
        """**偽陽性を出さない**（鳴ると「⚠️ が出たときだけ行動する」契約が壊れる）."""
        self.publish(dict(BASE_PAYLOAD,
                          adversarial_verify={"fired": True, "skip_reason": None,
                                              "severity_inflated": 3,
                                              "inflated_axes": self._axes(0, base=3)}))
        self.assertNotIn("axis-unknown", self.last_payload()["measurement_gaps"])

    def test_the_upstream_side_has_its_own_gap(self):
        """`demoted_types`（上流降格）は別の識別子で立てる.

        是正先が違う（反証プロンプトの axis 語彙 / reviewer の型名）ので、
        1 つの識別子に混ぜると集計側が是正先を指せなくなる。
        """
        p = dict(BASE_PAYLOAD,
                 below_threshold_counts={"blocker": 0, "critical": 0, "major": 0, "minor": 2,
                                         "demoted_types": self._axes(2)})
        p["pre_adjust_counts"] = {"blocker": 0, "critical": 0, "major": 1, "minor": 2}
        self.publish(p)
        gaps = self.last_payload()["measurement_gaps"]
        self.assertIn("demoted-unknown", gaps)
        self.assertNotIn("axis-unknown", gaps, "上流と下流の是正先が同じ識別子に潰れている")

    def test_the_gap_does_not_block_the_publish(self):
        """**fail-fast にしない**（`unknown` は正当な回にも立つ。止めると計測が丸ごと消える）."""
        r = self.publish(dict(BASE_PAYLOAD,
                              adversarial_verify={"fired": True, "skip_reason": None,
                                                  "severity_inflated": 2,
                                                  "inflated_axes": self._axes(2)}))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.last_payload()["adversarial_verify"]["inflated_axes"]["unknown"], 2,
                         "内訳そのものが落ちている")


class ExplorerWaveWarnTest(ScriptTestBase):
    """explorer wave の打点と WARN（セルフレビューで変数の上書きを実測 / v2.88.2）.

    `waves` という変数名が dispatch ブロックの `waves = disp.get("waves")`（**総** wave 数）に
    上書きされ、末尾の WARN が総 wave 数を読んでいた。explorer + reviewer の 2 wave は
    設計上正当なので、**layered な全レビューで「一括発行が破られた」の偽陽性**が出続け、
    かつ `elif "explorer-wave" in gaps:` の本物の打点漏れ警告が到達不能になっていた。
    """

    def _marks(self, we: int) -> None:
        """`we` を指定本数だけ書く（`timeline` は kwargs なので同名キーを 2 本書けない）."""
        path = Path(self.timing("start").stdout.strip())
        rows = ["t0 1000\n", "t1 1100\n"] + ["we %d\n" % (1200 + i) for i in range(we)]
        path.write_text("".join(rows + ["w 1400\n", "t2 1500\n"]), encoding="utf-8")

    def _publish(self, explorer: int, we: int):
        self._marks(we)
        p = dict(BASE_PAYLOAD, agents={"explorer": explorer, "reviewer": 2})
        return self.publish(p)

    def test_one_wave_is_not_flagged(self):
        """**一括発行できている回で鳴らさない**（偽陽性を出さないことが契約）."""
        r = self._publish(explorer=2, we=1)
        self.assertEqual(self.last_payload()["agents"]["explorer_waves"], 1)
        self.assertNotIn("一括発行が破られた", r.stderr)
        self.assertNotIn("explorer-wave", self.last_payload()["measurement_gaps"])

    def test_two_waves_are_flagged(self):
        """explorer を 2 wave に分けた回だけ鳴る（境界は 2）."""
        r = self._publish(explorer=2, we=2)
        self.assertEqual(self.last_payload()["agents"]["explorer_waves"], 2)
        self.assertIn("explorer wave が 2 本ある", r.stderr)

    def test_a_missing_mark_raises_the_gap_when_explorers_ran(self):
        """explorer を起動したのに打点 0 なら gap（打点漏れは違反の証拠も消す / #135）."""
        r = self._publish(explorer=1, we=0)
        self.assertIn("explorer-wave", self.last_payload()["measurement_gaps"])
        self.assertIn("打点が無い", r.stderr)

    def test_no_explorer_means_no_gap(self):
        """explorer 未起動なら打点 0 は**該当なし**（欠測ではない）."""
        r = self._publish(explorer=0, we=0)
        self.assertNotIn("explorer-wave", self.last_payload()["measurement_gaps"])
        self.assertNotIn("打点が無い", r.stderr)

    def test_the_count_defaults_to_zero_when_unset(self):
        """環境変数が空でも 0 に倒れる（`or 0` の既定）."""
        r = self._publish(explorer=0, we=0)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.last_payload()["agents"]["explorer_waves"], 0)


class ModelGenerationTest(TranscriptFixture):
    """`review:completed` にモデル世代を機械計測で載せる（GitHub issue #169）.

    `effort` / `size_tier` の層別は、Opus 5 と 4.8 が混ざった
    瞬間に成立しなくなる（実測: 2026-08-24 の 1 日で 3 サンプル中 2 件が 4.8 で、1 体あたり
    cache_read の 7,853k と 3,7xx k の差が tier と世代で完全に交絡していた）。世代は
    ユーザーが実行時に選ぶもの（エイリアスは親世代を継ぐ / #170）なので**層別キー**として扱う。
    自己申告は無く、transcript の `message.model` からの機械計測。
    """

    def test_payload_carries_main_and_sub_generations(self):
        self.write_transcript([[0, 5]], main_models=("claude-opus-5",),
                              sub_models=("claude-opus-5", "claude-sonnet-5"))
        self.publish(env=self.env_home())
        m = self.last_payload()["models"]
        self.assertEqual(m["schema"], 1, "schema を上げずにフィールドだけ足している")
        self.assertEqual(m["main"], "claude-opus-5")
        self.assertEqual(m["main_distinct"], ["claude-opus-5"])
        self.assertEqual(m["sub_distinct"], ["claude-opus-5", "claude-sonnet-5"],
                         "ロール別ルーティングの世代が集合で残っていない")

    def test_sub_generation_follows_the_parent(self):
        """#170 の踏み下げ。親が 4.8 なら `opus` の sub も 4.8 で、両方 payload に残る.

        この経路が壊れると `CLAUDE_CODE_SUBAGENT_MODEL` などで前提が崩れた回を
        事後に検出できなくなる（`sub_distinct` はそのための証拠）。
        """
        self.write_transcript([[0, 5]], main_models=("claude-opus-4-8",),
                              sub_models=("claude-opus-4-8", "claude-sonnet-5"))
        self.publish(env=self.env_home())
        m = self.last_payload()["models"]
        self.assertEqual(m["main"], "claude-opus-4-8")
        self.assertEqual(m["sub_distinct"], ["claude-opus-4-8", "claude-sonnet-5"])

    def test_mixed_main_is_null_not_a_representative_value(self):
        """**片方を代表値に選ばない**（実測: opus-5 → opus-4-8 → opus-5 の切替）.

        選ぶと交絡したサンプルが単一世代の分布に混ざり、「深さのコストが下がった」と
        「世代が違うから軽い」が永久に分離できなくなる（#156 / #150）。
        """
        self.write_transcript([[0, 5]], main_models=("claude-opus-5", "claude-opus-4-8"))
        self.publish(env=self.env_home())
        m = self.last_payload()["models"]
        self.assertIsNone(m["main"], "混在した回に代表値を選んでいる")
        self.assertEqual(m["main_distinct"], ["claude-opus-4-8", "claude-opus-5"],
                         "混在の事実そのものが落ちている")

    def test_synthetic_placeholder_is_not_a_generation(self):
        """`<synthetic>` を素通しすると**単一世代の回まで mixed に落ちる**.

        実測: 160 transcript の走査で 11 件。除外しないと `main_distinct` が 2 件になり、
        上のテストが要求する「混在の検出」が偽陽性で埋まる。
        """
        self.write_transcript([[0, 5]], main_models=("claude-opus-5", "<synthetic>"))
        self.publish(env=self.env_home())
        m = self.last_payload()["models"]
        self.assertEqual(m["main"], "claude-opus-5")
        self.assertEqual(m["main_distinct"], ["claude-opus-5"])

    def test_missing_model_is_a_gap_not_a_guess(self):
        """世代を引けない回は欠測。**「単一世代だった」に倒さない**（`tokens` の 0 と同じ）."""
        self.write_transcript([[0, 5]], main_models=(), sub_models=())
        self.publish(env=self.env_home())
        p = self.last_payload()
        self.assertNotIn("models", p, "引けない回に models を捏造している")
        self.assertIn("models", p["measurement_gaps"])

    def test_a_run_without_subagents_still_records_the_main_generation(self):
        """**sub が 0 体でも main の世代は載る**（`main_distinct` か `sub_distinct` の**片方**で足りる）.

        Phase 0 で打ち切った回・skip-mode の回は sub が 1 体も出ない。両方を要求すると
        この経路が丸ごと `models` 欠測に落ち、**fleet を起動しなかった回の世代が残らない**。
        """
        self.write_transcript([])
        self.publish(env=self.env_home())
        p = self.last_payload()
        self.assertIn("models", p, "sub 0 体の回で世代を捨てている")
        self.assertEqual(p["models"]["main"], "claude-opus-5")
        self.assertEqual(p["models"]["sub_distinct"], [])

    def test_cli_prints_both_sides_of_the_generation(self):
        """人間向け出力にも世代を出す（`measure-tokens.sh` を直接叩く経路）.

        publish 経由でしか検証しないと、CLI として使ったときの表示（sub の世代が
        `-` に潰れる等）が無検証のまま残る。
        """
        self.write_transcript([[0, 5]], main_models=("claude-opus-4-8",),
                              sub_models=("claude-opus-4-8", "claude-sonnet-5"))
        out = self.run_script(MEASURE, env=self.env_home()).stdout
        self.assertIn("モデル世代", out)
        self.assertIn("main=claude-opus-4-8", out)
        self.assertIn("sub=claude-opus-4-8+claude-sonnet-5", out,
                      "sub 側の世代が潰れている")

    def test_cli_prints_the_generation_without_subagents(self):
        """sub が 0 体でも行を出す（main だけ分かっている回を黙らせない）."""
        self.write_transcript([])
        out = self.run_script(MEASURE, env=self.env_home()).stdout
        self.assertIn("main=claude-opus-5 / sub=-", out)

    def test_a_caller_supplied_generation_is_discarded(self):
        """呼び出し側が渡した `models` は捨てる（**自己申告を機械計測に化けさせない**）.

        `models` は「自己申告が無い」ことが値の意味そのもの。残すと transcript を
        引けなかった回に **LLM が書いた世代が機械計測のふりをして残る**（#154 の型）。
        """
        self.write_transcript([], main_models=())          # 世代を引けない transcript
        self.publish(dict(BASE_PAYLOAD,
                          models={"schema": 1, "main": "claude-opus-5",
                                  "main_distinct": ["claude-opus-5"], "sub_distinct": []}),
                     env=self.env_home())
        p = self.last_payload()
        self.assertNotIn("models", p, "呼び出し側の自己申告が payload に残っている")
        self.assertIn("models", p["measurement_gaps"])

    def test_models_is_independent_of_the_tokens_window(self):
        """`tokens` が欠測でも世代は載る（`dispatch` と同じ流儀）.

        世代を `tokens` にぶら下げると、窓が空振りした回で層別キーごと消える。
        """
        self.write_transcript([[0, 5]])
        self.publish(env=self.env_home())
        p = self.last_payload()
        self.assertIn("models", p)
        self.assertEqual(p["models"]["main"], "claude-opus-5")


class DerivedMarkerTest(TranscriptFixture):
    """打点が落ちた区間を agent の実測時刻で埋める（GitHub issue #161）.

    区間打点はオーケストレーターの記憶に依存しており、実測で **v2.62.0 以降の 10 件中
    5 件が 1 つ以上落としていた**（`t1` 1 / `wave` 2 / `explorer-wave` 2 / `t2` 1）。
    #156 が基準値の裏付けに使った回と #153 が初の schema 3 サンプルにした回が、**どちらも
    打点漏れで区間内訳を欠いていた**＝打ち手を決めるためのサンプルが打点漏れで削られていた。

    守る契約は 4 つ:

    1. **打点が有る側が常に勝つ**（補完は穴埋めであって上書きではない）
    2. **矛盾する値は採らない**（`t0 <= v <= t2` / 縮退先は欠測であって誤値ではない）
    3. **explorer wave は突合であって推定ではない**（体数が一致しなければ埋めない）
    4. **`measurement_gaps` は消さない**（打点漏れ率そのものが観測対象 / #123 B）
    """

    BASE = datetime(2026, 8, 18, 1, 0, 0)

    def epoch(self, off: int = 0) -> int:
        return int(self.BASE.replace(tzinfo=timezone.utc).timestamp()) + off

    def run_publish(self, payload: dict | None = None) -> dict:
        self.publish(payload, env=self.env_home())
        return self.last_payload()

    def two_waves(self, ends: dict[int, int] | None = None) -> None:
        """wave 1 = agent 0,1（終了 200 / 300）→ wave 2 = agent 2（600 起動 / 900 終了）."""
        self.write_transcript([[0, 5], [600]],
                              ends={0: 200, 1: 300, 2: 900} if ends is None else ends,
                              base=self.BASE)

    def test_a_value_taking_flag_needs_a_value(self):
        """値落ちを黙殺しない（`--pr` と `--derived-*` / `--since` と同じ規約）.

        黙って無視すると補完が効かないまま「打点も無い」回と区別がつかず、
        **計測が silent に壊れる**。境界（`$# >= 2`）を 1 つ狭める変異が生存していたので、
        **値ありの経路も同時に表明する**（publish は 3 つ並べて渡すため、単独で渡す形は
        結合テストからは一度も通らない）。
        """
        self.ts_file()
        # **3 フラグすべてを単独で通す**。publish は 3 つ並べて渡すので、1 つだけ渡す形は
        # 結合テストからは一度も通らない。`--derived-t1` だけ表明していたため
        # `--derived-explore` の境界変異が nightly まで生存した（GitHub issue #164）
        for flag in ("--pr", "--derived-t1", "--derived-explore", "--derived-wave"):
            self.assertEqual(self.timing("durations", flag).returncode, 2,
                             "値なしの `%s` を受理している" % flag)
            self.assertEqual(self.timing("durations", flag, "1").returncode, 0,
                             "値ありの `%s` を拒否している" % flag)

    def test_wave_marker_is_derived_from_the_last_wave_end(self):
        """`wave` 打点漏れ ＝ `duration_synthesis_min` 欠測、を実測時刻で埋める."""
        self.two_waves()
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10), t2=self.epoch(1200))
        p = self.run_publish()
        # t2(1200) − 最終 wave の終了(900) = 300 秒
        self.assertEqual(p["duration_synthesis_min"], 5)
        self.assertIn("wave", p["derived_markers"])
        self.assertIn("wave", p["measurement_gaps"],
                      "補完で打点漏れの事実まで消している（打点漏れ率が観測できなくなる）")

    def test_t1_marker_is_derived_from_the_first_agent_start(self):
        """`t1` 打点漏れは triage と fleet の**両方**を欠測にする（実測 1 件）."""
        self.two_waves()
        self.timeline(t0=self.epoch(-300), t2=self.epoch(1200))
        p = self.run_publish()
        self.assertEqual(p["duration_triage_min"], 5, "t0 → 最初の agent 起動 = 300 秒")
        self.assertEqual(p["duration_fleet_min"], 20, "最初の agent 起動 → t2 = 1200 秒")
        self.assertIn("t1", p["derived_markers"])

    def test_marker_wins_over_the_derived_value(self):
        """**補完は上書きではない**。打点が有る区間には触らない."""
        self.two_waves()
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10),
                      w=self.epoch(1140), t2=self.epoch(1200))
        p = self.run_publish()
        self.assertEqual(p["duration_synthesis_min"], 1, "打点(1140) ではなく実測(900) を使った")
        self.assertEqual(p["derived_markers"], [])

    def test_explorer_wave_is_matched_by_headcount_not_assumed(self):
        """先頭 wave 群の体数累計が `agents.explorer` と**一致したときだけ**埋める."""
        self.two_waves()
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10), t2=self.epoch(1200))
        payload = dict(BASE_PAYLOAD, agents={"explorer": 2, "reviewer": 1})
        p = self.run_publish(payload)
        # wave 1 の体数 2 == explorer 2 → その wave の終了(300) が explorer wave の終わり
        self.assertEqual(p["duration_explore_min"], 5, "t1(-10) → 300 = 310 秒")
        self.assertIn("explorer-wave", p["derived_markers"])

    def test_explorer_wave_is_not_derived_when_the_headcount_disagrees(self):
        """**「先頭 wave = explorer」と決め打たない**（一致しない回は欠測のまま）.

        これを推定に落とすと、Round 2 の追加 explorer が混ざった回や explorer を
        複数 wave に割った回で `duration_explore_min` が別物の区間に化ける。
        """
        self.write_transcript([[0, 5, 7], [600]], ends={0: 200, 1: 300, 2: 250, 3: 900},
                              base=self.BASE)
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10), t2=self.epoch(1200))
        payload = dict(BASE_PAYLOAD, agents={"explorer": 2, "reviewer": 2})
        p = self.run_publish(payload)
        self.assertEqual(p["duration_explore_min"], -1, "先頭 wave は 3 体で explorer 2 と不一致")
        self.assertNotIn("explorer-wave", p["derived_markers"])
        self.assertIn("wave", p["derived_markers"], "他のマーカーの補完まで巻き添えにしている")

    def test_wave_is_not_derived_when_an_end_is_missing(self):
        """最終 wave の体が 1 つでも終了時刻を持たなければ埋めない（#153 の縮退方向）."""
        self.two_waves(ends={0: 200, 1: 300})     # agent 2（最終 wave）に終了行が無い
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10), t2=self.epoch(1200))
        p = self.run_publish()
        self.assertEqual(p["duration_synthesis_min"], -1)
        self.assertNotIn("wave", p["derived_markers"])

    def test_a_value_after_t2_is_rejected_instead_of_going_negative(self):
        """**矛盾する補完はしない**。採ると `duration_synthesis_min` が負になる."""
        self.two_waves()
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10), t2=self.epoch(100))
        p = self.run_publish()
        self.assertEqual(p["duration_synthesis_min"], -1, "t2(100) より後(900)の値を採った")
        self.assertEqual(p["derived_markers"], [])

    def test_t2_is_never_derived(self):
        """`t2`（初回レポート出力）はメイン文脈のイベントで agent transcript に現れない.

        publish 時刻から逆算すれば欠測は消えるが、それが `## 14` の禁じている当のもの。
        """
        self.two_waves()
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10))
        p = self.run_publish()
        self.assertEqual(p["duration_fleet_min"], -1, "t2 を逆算で埋めている")
        self.assertEqual(p["duration_synthesis_min"], -1)
        self.assertIn("t2", p["measurement_gaps"])
        self.assertNotIn("t2", p["derived_markers"])

    def test_unresolvable_dispatch_does_not_derive(self):
        """wave 構成が確定しない回は埋めない（#142 の「どちらにも倒さない」を継承）."""
        self.two_waves()
        slug = "".join(c if c.isalnum() else "-" for c in str(self.root))
        (self.home / ".claude" / "projects" / slug / "s1" / "subagents"
         / "agent-2.meta.json").unlink()
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10), t2=self.epoch(1200))
        p = self.run_publish()
        self.assertIn("dispatch", p["measurement_gaps"], "前提（unresolved）が再現できていない")
        self.assertEqual(p["derived_markers"], [])
        self.assertEqual(p["duration_synthesis_min"], -1)

    # ---- ここから下は v2.82.0 のセルフレビューで「変異が生存した」経路（#161） --------
    # 肯定系（補完が効く経路）は守られていたのに、**`## 14` の「縮退先は欠測であって誤値では
    # ない」を実際に守っている行だけ**が全部テストの射程外だった（変異 8 件中 8 件が生存）。

    def test_a_session_window_run_is_not_derived(self):
        """**`t0` にアンカーされない窓の回は補完しない**（最も重い実欠陥だった）.

        `t0` 打点が欠けると `measure-tokens.sh` は `--since` なし＝セッション全体を窓に
        するので、`wave_clock` に同一セッションの無関係な agent が混ざる。しかも `ok()` は
        `t0` 欠測だと下限を飛ばすため、**何時間も前の別作業の起動時刻**が `t1` の補完値に
        なり `duration_fleet_min` が過大値として publish されていた（実測 10 分 → 120 分）。
        """
        self.two_waves()
        self.timeline(t1=self.epoch(-10), t2=self.epoch(1200))   # t0 を打たない
        p = self.run_publish()
        self.assertEqual(p["tokens"]["window"], "session", "前提（t0 欠測）が再現できていない")
        self.assertEqual(p["derived_markers"], [], "窓を絞れていない回で補完している")

    def test_a_non_dict_agents_does_not_break_derivation(self):
        """`payload.agents` が truthy な非 dict でも補完機構は死なない.

        `or {}` は falsy しか吸収しないため、旧版は `.get()` が try の**外**にあり未捕捉
        `AttributeError` で `--derived-*` が丸ごと渡らなくなっていた（publish 自体は
        `|| DERIVED=""` で成功するので**壊れても緑**）。
        """
        self.two_waves()
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10), t2=self.epoch(1200))
        r = self.publish(dict(BASE_PAYLOAD, agents="oops"), env=self.env_home())
        self.assertNotIn("Traceback", r.stderr, "補完 python が例外で落ちている")
        p = self.last_payload()
        self.assertIn("wave", p["derived_markers"], "型不正で補完全体が無効化されている")

    def test_durations_ignores_a_derived_value_when_the_marker_exists(self):
        """`durations` 側の **marker-wins**（publish 側とは独立した二段目）.

        publish は打点が有る区間に `--derived-*` を渡さないので、この二段目は結合テスト
        からは到達しない。`--derived-*` は usage に載った公開 CLI なので直接叩いて表明する。
        """
        self.timeline(t0=self.epoch(-300), t1=self.epoch(0),
                      we=self.epoch(600), w=self.epoch(900), t2=self.epoch(1200))
        out = self.timing("durations", "--derived-t1", str(self.epoch(60)),
                          "--derived-explore", str(self.epoch(60)),
                          "--derived-wave", str(self.epoch(60))).stdout.split()
        # **3 マーカーぶんすべてを表明する**。`t1` だけ抜けていたため、`t1` 行の
        # `&&` を `||` に緩める変異（＝実打点を補完値で上書きする）が生存していた
        # （GitHub issue #164）。上書きが起きると triage が 5 分から 6 分にずれる
        self.assertEqual(out[1], "5", "triage が打点(0) ではなく補完値(60) を採っている")
        self.assertEqual(out[4], "10", "explore が打点(600) ではなく補完値(60) を採っている")
        self.assertEqual(out[5], "5", "synthesis が打点(900) ではなく補完値(60) を採っている")

    def test_a_derived_value_after_t2_degrades_to_missing_not_negative(self):
        """`durations` の**負クランプ**（`review-timing.sh` 側の二段目）.

        publish 側の `ok()` が先に落とすため結合テストからは到達しない。`--derived-*` は
        usage に載った CLI なので、直接叩いて縮退を表明する。
        """
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10), t2=self.epoch(100))
        out = self.timing("durations", "--derived-wave", str(self.epoch(900))).stdout.split()
        self.assertEqual(out[5], "-1", "負の synthesis をそのまま返している")

    def test_a_non_numeric_derived_value_is_dropped_not_coerced(self):
        """**非数値スクラブ**。awk は文字列を 0 に coerce するので「1970 年に回収した」になる."""
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10), t2=self.epoch(1200))
        for bad in ("-", "abc"):
            out = self.timing("durations", "--derived-wave", bad).stdout.split()
            self.assertEqual(out[5], "-1", "非数値 %r を採用している" % bad)

    def test_a_value_before_the_t1_marker_is_rejected(self):
        """`ok()` の**下限**（`v < lo`）。上限だけがテストで守られていた.

        最終 wave の終了が `t1` 打点より前なら、その `wave_clock` は別の作業のもの。
        採ると `duration_synthesis_min` が過大になる（負にならないので `span()` の
        クランプでは捕まらない）。
        """
        self.two_waves()
        self.timeline(t0=self.epoch(-300), t1=self.epoch(1000), t2=self.epoch(1200))
        p = self.run_publish()
        self.assertEqual(p["duration_synthesis_min"], -1, "t1 より前の終了時刻を採っている")
        self.assertEqual(p["derived_markers"], [])

    def test_explorer_wave_marker_wins_over_the_derived_value(self):
        """explorer-wave の **marker-wins**。`t1` / `w` では守られていたのに `we` だけ無検証だった."""
        self.two_waves()
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10),
                      we=self.epoch(600), w=self.epoch(1000), t2=self.epoch(1200))
        payload = dict(BASE_PAYLOAD, agents={"explorer": 2, "reviewer": 1})
        p = self.run_publish(payload)
        self.assertEqual(p["duration_explore_min"], 10, "打点(600) ではなく実測(300) を使った")
        self.assertEqual(p["derived_markers"], [])

    def test_explorer_wave_is_not_derived_when_one_of_its_waves_lacks_an_end(self):
        """explorer 群の **`end` 完全性**。`wave` 行では守られていたが explorer 側は無検証だった.

        **explorer が 2 wave に割れた形で組む**。単一 wave だと `wave_clock` 側が既に
        `end=None` に倒しているので `all(...)` を外しても結果が変わらず（等価変異）、
        ガードを守れているかを観測できない。割れていれば `[300, None]` になり、
        ガードを外すと `max()` が int と None を比較して落ちる。
        """
        # wave 1 = explorer 1 体（終了 300）/ wave 2 = explorer 2 体（1 体に終了行が無い）
        # / wave 3 = reviewer 1 体。累計 1 → 3 で explorer 3 に一致する
        self.write_transcript([[0], [100, 105], [600]],
                              ends={0: 300, 1: 400, 3: 900}, base=self.BASE)
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10), t2=self.epoch(1200))
        payload = dict(BASE_PAYLOAD, agents={"explorer": 3, "reviewer": 1})
        p = self.run_publish(payload)
        self.assertEqual(p["duration_explore_min"], -1)
        self.assertNotIn("explorer-wave", p["derived_markers"])
        self.assertNotIn("derived", p["measurement_gaps"],
                         "補完が例外で落ちている（`all(...)` ガードが効いていない）")
        self.assertIn("wave", p["derived_markers"], "最終 wave の補完まで巻き添えにしている")

    def test_a_boolean_explorer_count_is_not_a_headcount(self):
        """`True` は `int` のサブクラス。体数として扱うと `explorer=1` に化ける.

        同モジュールの `DemoteTypesValidationTest` が確立している規約（bool を int と
        取り違えない）が `agents.explorer` にだけ適用されていなかった。
        """
        # **先頭 wave を 1 体にする**。`True == 1` なので、体数 1 の wave が先頭に無いと
        # 累計が一致せずガードの有無で結果が変わらない（等価変異になって観測できない）
        self.write_transcript([[0], [600]], ends={0: 300, 1: 900}, base=self.BASE)
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10), t2=self.epoch(1200))
        payload = dict(BASE_PAYLOAD, agents={"explorer": True, "reviewer": 1})
        p = self.run_publish(payload)
        self.assertNotIn("explorer-wave", p["derived_markers"], "bool を体数として扱っている")
        self.assertEqual(p["duration_explore_min"], -1)

    def test_an_explorer_wave_ending_after_the_last_wave_is_dropped(self):
        """`we > w` を通すと explore と synthesis が**重なる**（区間の二重計上）.

        `wave_clock` は **start でソート**されているので `clock[-1]` は「最後に起動した
        wave」であって「最後に終わった wave」とは限らない。
        """
        # wave 1（explorer 2 体）が 5000 まで走り、wave 2（1 体）は 900 で終わる
        self.write_transcript([[0, 5], [600]], ends={0: 4000, 1: 5000, 2: 900},
                              base=self.BASE)
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10), t2=self.epoch(6000))
        payload = dict(BASE_PAYLOAD, agents={"explorer": 2, "reviewer": 1})
        p = self.run_publish(payload)
        self.assertNotIn("explorer-wave", p["derived_markers"], "we > w を通している")
        self.assertEqual(p["duration_explore_min"], -1)

    def test_a_broken_derivation_is_recorded_as_a_gap(self):
        """補完 python の**異常終了**を「補完対象が無かった」と区別する.

        両方を `derived_markers == []` に潰すと、機構が落ちた回が retro の
        「補完条件を満たさなかった回」に紛れ、効果測定の当のフィールドが失敗を成功と
        同じ形で記録する。**payload を壊せない**ので `PATH` から python3 を外して再現する。
        """
        self.two_waves()
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10), t2=self.epoch(1200))
        stub = self.root / "stub"
        stub.mkdir()
        # **補完の呼び出しだけを落とす**。publish は payload のマージにも python3 を使うので、
        # 素朴に潰すとイベントごと消えて「gap が立ったか」を観測できない（実際に踏んだ）。
        # 補完側だけが `REVIEW_EPOCHS` を渡すので、それを見分けに使う。**本物は絶対パスで
        # exec する**（PATH 経由だと stub 自身に戻って無限再帰する）
        (stub / "python3").write_text(
            '#!/bin/bash\nif [ -n "${REVIEW_EPOCHS:-}" ]; then exit 9; fi\n'
            'exec %s "$@"\n' % sys.executable, encoding="utf-8")
        (stub / "python3").chmod(0o755)
        env = self.env_home()
        env["PATH"] = "%s:%s" % (stub, env.get("PATH", ""))
        self.publish(env=env)
        p = self.last_payload()
        self.assertIn("derived", p["measurement_gaps"], "補完の異常終了が記録されていない")

    def test_derived_markers_is_always_present(self):
        """フィールドの存在自体が補完機構の版マーカーになる（日付では切らない流儀）."""
        self.two_waves()
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10),
                      w=self.epoch(1000), t2=self.epoch(1200))
        p = self.run_publish()
        self.assertIn("derived_markers", p)
        self.assertEqual(p["derived_markers"], [])


class LatePublishTest(ScriptTestBase):
    """遅れて publish した self-review は `duration_min` を欠測に倒す（issue #133）."""

    def _stale_timing(self, closing_min: int) -> None:
        """`timeline()` の薄いラッパ（マーカー行書式の正本を 1 箇所に保つ / #161）."""
        now = int(time.time())
        self.timeline(t0=now - 3600, t1=now - 3500, w=now - 2000,
                      t2=now - closing_min * 60)

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

    def test_the_ten_minute_boundary_is_late(self):
        """**閾値ちょうどは遅延側**（`## 16` の「10 分以上あけて publish した回」）.

        境界を 1 つ狭める変異が nightly まで生存していた（GitHub issue #164）。
        `duration_min` を落とすかどうかの判定なので、片側にずれると**契約が壊れた回を
        正常として集計に入れる**。
        """
        self._stale_timing(10)
        self.publish()
        self.assertIn("late-publish", self.last_payload()["measurement_gaps"])

    def test_just_under_the_boundary_is_not_late(self):
        """境界の反対側も同時に表明する（`assertIn` だけだと恒真に倒れても気づけない）."""
        self._stale_timing(9)
        self.publish()
        self.assertNotIn("late-publish", self.last_payload()["measurement_gaps"])

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
        self.assertEqual(p["adversarial_verify"]["calibration_schema"], 3)
        self.assertEqual(p["meta_reviewer"]["gate_schema"], 3)
        self.assertEqual(p["findings_class"]["schema"], 1)

    def test_missing_layer_object_becomes_a_gap(self):
        """層のオブジェクトごと落ちた回は空 dict を捏造せず gap にする."""
        payload = {k: v for k, v in BASE_PAYLOAD.items() if k != "meta_reviewer"}
        self.publish(payload)
        self.assertIn("payload:meta_reviewer", self.last_payload()["measurement_gaps"])


class RetroFixture(ScriptTestBase):
    """`review-retro.sh` 用の fixture だけを持つ土台（**テストは持たない**）.

    `RetroTest` は自前のテストを 52 本持つので、**そこを継承すると 52 本が子の名前で
    もう一度走る**（`TranscriptFixture` の docstring が記録している失敗と同型）。
    新しいテストクラスはこちらを継承する。
    """

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

    def _tokens_full(self, sub_output_k, sub_agents, main_output_k=100.0,
                     window: str = "since-t0", schema: int = 2,
                     sub_cache_read_k=100.0) -> dict:
        """sub 側の値と体数を明示できる tokens 行（GitHub issue #199）.

        publish が sub 空振りを倒した回は `sub_*` 系がすべて None になるので、その形を
        再現したいときは `sub_output_k` と `sub_cache_read_k` の両方に None を渡す。
        """
        return {"effort": "high", "size_tier": "medium", "measurement_gaps": [],
                "agents": {"explorer": 0, "reviewer": 2},
                "tokens": {"schema": schema, "window": window,
                           "main_output_k": main_output_k, "sub_output_k": sub_output_k,
                           "sub_cache_read_k": sub_cache_read_k, "sub_agents": sub_agents}}

    def test_a_sub_blank_run_is_excluded_from_the_sub_median(self):
        """**sub 空振りの回を sub 中央値の分母から外す**（GitHub issue #199）.

        publish は #199 以降 `sub_output_k` を None に倒すが、それ以前に焼かれた回は
        `sub_output_k: 0.0` が残っているので、集計側は `sub_agents == 0` を見て弾く。
        0 を混ぜると中央値が下振れする。
        """
        rows = [self._tokens_full(200.0, 2), self._tokens_full(220.0, 2),
                self._tokens_full(0.0, 0)]            # 旧データの 0（sub 空振り）
        self._events(rows)
        out = self.run_script(RETRO, "--json", env=self._env()).stdout
        tok = json.loads(out)["tokens"]
        self.assertEqual(tok["sub_output_k_median"], 210.0,
                         "sub 空振りの 0 を中央値の分母に入れている")

    def test_a_null_sub_output_is_also_excluded(self):
        """publish が None に倒した回も分母に入れない（`sub_*` が 3 つとも None の実形）."""
        rows = [self._tokens_full(200.0, 2), self._tokens_full(220.0, 2),
                self._tokens_full(None, 0, sub_cache_read_k=None)]
        self._events(rows)
        tok = json.loads(self.run_script(RETRO, "--json", env=self._env()).stdout)["tokens"]
        self.assertEqual(tok["sub_output_k_median"], 210.0)

    def test_a_sub_blank_run_is_excluded_from_the_agent_correlation(self):
        """体数 vs sub.output の相関の分母からも外す（#199）.

        `sub_agents == 0` の回を残すと (体数, 0) の点が相関に混ざる。
        """
        rows = [self._tokens_full(200.0, 2), self._tokens_full(400.0, 4),
                self._tokens_full(0.0, 0)]
        self._events(rows)
        tok = json.loads(self.run_script(RETRO, "--json", env=self._env()).stdout)["tokens"]
        self.assertEqual(tok["agents_sub_output_n"], 2, "sub 空振りを相関の分母に入れている")

    def test_a_healthy_sub_run_still_counts(self):
        """**空振り判定が正常系を落とさない**（sub_agents > 0 は分母に残る）."""
        self._events([self._tokens_full(200.0, 2), self._tokens_full(220.0, 3)])
        tok = json.loads(self.run_script(RETRO, "--json", env=self._env()).stdout)["tokens"]
        self.assertEqual(tok["sub_output_k_median"], 210.0)
        self.assertEqual(tok["agents_sub_output_n"], 2)

    # ---- モデル世代による層別（GitHub issue #169） --------------------------

    def _models(self, main):
        """`models` フィールド。`main=None` は混在・引き当て失敗の回."""
        return {"schema": 1, "main": main,
                "main_distinct": [main] if main else ["claude-opus-4-8", "claude-opus-5"],
                "sub_distinct": [main] if main else []}


class RetroTest(RetroFixture):
    """`review-retro.sh` の層別と分母（issue #131 / v2.66.0 のセルフレビュー指摘）."""

    def test_generation_is_not_a_key_while_the_population_is_uniform(self):
        """**1 種しか無い期間は層別しない**（既存バケツを n=1 に砕かない）.

        分割の目的は交絡を切ることであって、キーを増やすことではない。ここが壊れると
        `effort × size_tier` の中央値が全部 n=1 になり、読めるものが何も残らない。
        """
        self._events([dict(self._tokens("medium", 1000.0, 2),
                           models=self._models("claude-opus-5")) for _ in range(3)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("| high/medium | 3 |", out, "1 種なのに世代でキーが割れている")
        self.assertIn("1 種のみなので層別しない", out)

    def test_generation_becomes_a_key_once_two_are_present(self):
        """**2 種以上あれば層別キーに入る**（世代跨ぎで中央値を累計しない / #156）."""
        self._events([dict(self._tokens("medium", 1000.0, 2),
                           models=self._models("claude-opus-5")),
                      dict(self._tokens("medium", 8000.0, 2),
                           models=self._models("claude-opus-4-8"))])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("high/medium/opus-5", out)
        self.assertIn("high/medium/opus-4-8", out)
        self.assertIn("層別キーに含めている", out)
        self.assertNotIn("| high/medium | 2 |", out,
                         "世代跨ぎのバケツが残っている（累計すると較正効果と世代差が混ざる）")

    def test_unrecorded_generation_is_not_folded_into_a_known_one(self):
        """旧版（`models` 無し）を既知の世代と同じバケツに入れない.

        「たぶん opus-5 だった」は観測ではない。畳むと**新フィールドを入れた意味が消える**。
        """
        self._events([dict(self._tokens("medium", 1000.0, 2),
                           models=self._models("claude-opus-5")),
                      self._tokens("medium", 8000.0, 2)])           # 旧版 = models 無し
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("high/medium/unrecorded", out)
        self.assertIn("high/medium/opus-5", out)

    def test_an_empty_generation_string_is_treated_as_mixed(self):
        """`main: ""` も mixed（**外部の payload を読む側なので値の形を仮定しない**）.

        `models` は他マシン・旧版・後付けスクリプトが書いた JSON としても入ってくる。
        空文字を素通しすると `""` という名前のバケツができ、**世代不明の回が
        独立した「世代」として中央値を持つ**。
        """
        self._events([dict(self._tokens("medium", 1000.0, 2),
                           models=self._models("claude-opus-5")),
                      dict(self._tokens("medium", 8000.0, 2),
                           models={"schema": 1, "main": "", "main_distinct": [],
                                   "sub_distinct": []})])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("high/medium/mixed", out)
        self.assertNotIn("high/medium//", out, "空文字がそのままバケツ名になっている")

    def test_mixed_generation_gets_its_own_bucket(self):
        """`main` が null の回は `mixed`。単一世代の分布に混ぜない."""
        self._events([dict(self._tokens("medium", 1000.0, 2),
                           models=self._models("claude-opus-5")),
                      dict(self._tokens("medium", 8000.0, 2), models=self._models(None))])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("high/medium/mixed", out)
        self.assertIn("`mixed` 1 件", out, "混在の件数が母集団の内訳に出ていない")

    def test_derived_markers_are_counted_separately_from_gaps(self):
        """補完済みの内訳を出す（GitHub issue #161）.

        `measurement_gaps` と**排他ではない**（補完できた回は両方に載る）。混ぜると
        「打点規約が守られているか」と「区間データが使えるか」のどちらの話か読めなくなる。
        """
        # **2 つの行を非対称にする**（セルフレビューで検出 / #161）。旧版は `measurement_gaps`
        # と `derived_markers` に同じ識別子を入れていたため、`assertIn(..., out)` が既存の
        # 「欠測内訳」行だけで満たされ、**打点補完の内訳を丸ごと殺しても緑**だった
        # （`for m in dm:` → `for m in []:` の変異が RetroTest 42 件を素通りした）
        self._events([
            {"effort": "high", "measurement_gaps": ["wave", "explorer-wave", "t2"],
             "derived_markers": ["wave"]},
            {"effort": "high", "measurement_gaps": ["t1"], "derived_markers": ["t1"]},
        ])
        out = self.run_script(RETRO).stdout
        line = self.derived_line(out)
        self.assertIn("wave=1", line)
        self.assertIn("t1=1", line)
        self.assertNotIn("explorer-wave", line,
                         "補完していない識別子を補完済みとして数えている")
        self.assertNotIn("t2", line, "補完対象外のマーカーが補完済みに混ざっている")
        self.assertIn("欠測内訳", out, "補完で打点漏れの内訳まで消している")
        self.assertIn("explorer-wave=1", out, "欠測内訳の側が消えている")

    def test_no_derived_field_is_told_apart_from_nothing_derived(self):
        """**待ち行の 3 状態を潰さない**（#153 / #156 で同じ縮退を踏んでいる）.

        「フィールドを持つ回が 0（旧版のみ）」と「持っているが 1 件も補完していない」は
        別の状態で、後者を「判定対象なし」と言うと**補完機構が入っているのに一度も
        効いていない**を見逃す。
        """
        self._events([{"effort": "high", "measurement_gaps": ["wave"]}])
        self.assertIn("判定対象なし", self.derived_line(self.run_script(RETRO).stdout))
        self._events([{"effort": "high", "measurement_gaps": [], "derived_markers": []}])
        out = self.run_script(RETRO).stdout
        self.assertIn("1 件中 0 件", out)
        self.assertNotIn("打点補完: 判定対象なし", out)

    def derived_line(self, out: str) -> str:
        """`打点補完` 行だけを取り出す（他セクションの「判定対象なし」と混同しないため）."""
        self.assertIn("## レビュー振り返り", out, "retro が出力していない")
        return "\n".join(l for l in out.splitlines() if "打点補完" in l)

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
    def _axes_row(self, plugin: str, calib: int = 2, **types) -> dict:
        d = {k: 0 for k in ("base_derived", "misread", "overstated_impact",
                            "miscategorized", "unknown")}
        d.update(types)
        return {"_plugin": plugin, "effort": "high", "measurement_gaps": [],
                "adversarial_verify": {"fired": True, "skip_reason": None, "gate_schema": 2,
                                       "calibration_schema": calib, "confirmed": 0, "refuted": 0,
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

    def test_demote_types_split_across_calibration_layers(self):
        """`miscategorized` の判別条件は版で変わるので層 2 と層 3 を合算しない（#150 / v2.90.0）.

        版を上げた目的が層別なのに、効果測定の主指標である型別内訳テーブルが層を混ぜると
        バンプが無意味になる。単一層のとき（他テスト）はキーを砕かず、2 層あるときだけ分割する.
        """
        self._events([self._axes_row("code-review:review", calib=2, miscategorized=7, base_derived=3),
                      self._axes_row("code-review:review", calib=3, miscategorized=1, base_derived=1)])
        out = self.run_script(RETRO, env=self._env()).stdout
        # 層 2（PR 398 世代・旧判別条件）と層 3（新判別条件）が別行に分かれる
        self.assertIn("| review/calib2 | 1 | 10 |", out)
        self.assertIn("| review/calib3 | 1 | 2 |", out)
        # 合算した「| review | 1 | 12 |」は出てはならない（同じキーの意味の違う値の混合）
        self.assertNotIn("| review | 1 | 12 |", out)

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
        """件数フィールドが揃っていない回は突合しない（型検証だけ効く）.

        `BASE_PAYLOAD` は #215 以降 4 つとも持つ（契約準拠）ので、**この経路は明示的に
        落として作る**。欠測は fail-fast ではなく gap（`payload:report_counts.missing`）で残る。
        """
        p = dict(BASE_PAYLOAD)
        for k in ("blocker_count", "critical_count", "major_count", "minor_count"):
            p.pop(k, None)
        p["findings_class"] = {"lint": 9, "test": 9, "judgement": 9}
        r = self.publish(p)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("payload:report_counts.missing", self.last_payload()["measurement_gaps"],
                      "突合をスキップした事実が gap に残っていない（#215）")

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


class RetroGenerationRecallTest(RetroTest):
    """検出・報告側の世代層別（GitHub issue #191）.

    #169 は世代キーを**コスト側だけ**に入れたため、報告 0 件率・歩留まり・反証 verdict は
    世代をまたいで累計されていた。実測で踏み下げの前後に大きな落差が出ており
    （`pre_adjust` の MAJOR 中央値 7 → 0 / 報告 0 件率 42% → 91%）、累計すると平均に
    埋もれる。**「安くなった」だけが見えて「効かなくなった」が見えない**非対称になる。
    """

    def _row(self, gen: str | None, pre_major: int | None, reported: int | None,
             calib: int = 2, inflated: int = 1) -> dict:
        """`reported=None` で**報告件数フィールドを 1 つも持たない回**（旧版 payload）を作る。
        `pre_major=None` で `pre_adjust_counts.major` の欠測を作る。"""
        r = {"effort": "high", "size_tier": "medium", "measurement_gaps": [],
             "severity_threshold": "MAJOR",
             "pre_adjust_counts": {"schema": 2, "blocker": 0, "critical": 0,
                                   "minor": 0},
             "adversarial_verify": {"fired": True, "skip_reason": None, "gate_schema": 2,
                                    "calibration_schema": calib, "confirmed": 1,
                                    "refuted": 0, "uncertain": 0,
                                    "severity_inflated": inflated, "contested": 0}}
        if pre_major is not None:
            r["pre_adjust_counts"]["major"] = pre_major
        if reported is not None:
            r["major_count"] = reported
        if gen is not None:
            r["models"] = self._models("claude-%s" % gen)
        return r

    def _layer_row(self, gen: str, fired: bool, reason: str | None = None) -> dict:
        """反証層の発火 / skip を持つ 1 回（世代つき）."""
        av = {"gate_schema": 2, "calibration_schema": 3, "fired": fired,
              "skip_reason": reason}
        if fired:
            av.update({"confirmed": 2, "refuted": 0, "uncertain": 0,
                       "severity_inflated": 1, "contested": 0})
        return {"effort": "high", "size_tier": "medium", "measurement_gaps": [],
                "models": self._models("claude-%s" % gen),
                "adversarial_verify": av}

    def test_dynamic_layer_firing_is_split_by_generation(self):
        """**動的層の発火率と skip 理由も世代で層別する**（#191 期待動作 1 の 3 項目目）.

        踏み下げの崩壊はここに最も鋭く出る — 上流の MAJOR がほぼゼロになると反証は
        `no-eligible-findings` で不発になる（実測: calib=3 の 7 件中 6 件）。累計だけだと
        「反証 7/13 = 54%」に見え、**ゲート幅が広すぎる**という別の是正先を指してしまう。
        """
        rows = [self._layer_row("opus-4-8", i == 4,
                                None if i == 4 else "no-eligible-findings")
                for i in range(7)]
        rows += [self._layer_row("opus-5", True) for _ in range(6)]
        self._events(rows)
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("反証 7/13", out, "前提: 累計では落差が見えない")
        self.assertIn("反証 / opus-4-8: 発火 1/7（14%） / skip: no-eligible-findings=6", out,
                      "踏み下げ側の不発が世代別に出ていない")
        self.assertIn("反証 / opus-5: 発火 6/6（100%）", out)

    def test_no_generation_breakdown_when_a_single_generation(self):
        """世代が 1 種なら内訳を出さない（本体の 1 行と同じ内容になる / no-op 行を足さない）."""
        self._events([self._layer_row("opus-5", True) for _ in range(4)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("反証 4/4", out, "前提: 本体の集計は出ている")
        self.assertNotIn("反証 / opus-5:", out, "世代 1 種なのに内訳行を出している")

    def test_no_breakdown_when_only_one_generation_reaches_the_layer(self):
        """**母集団は 2 世代でも、その層に 1 世代しか届かなければ内訳を出さない**.

        層のフィールド自体を持たない回（旧版 payload）は `layer_stats` の母集団に入らないので、
        `GEN_SPLIT` が真でも `by_gen` が 1 世代になりうる。そこで内訳を出すと本体の 1 行と
        同じ内容が 2 度並ぶ（`GEN_SPLIT` だけを条件にすると起きる）。
        """
        # 旧世代側は `adversarial_verify` を持たない = 層の母集団に入らないが、世代の
        # 種類数（`GEN_SPLIT`）には数えられる
        rows = [{"effort": "high", "size_tier": "medium", "measurement_gaps": [],
                 "models": self._models("claude-opus-4-8")} for _ in range(3)]
        rows += [self._layer_row("opus-5", True) for _ in range(4)]
        self._events(rows)
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("層別キーに含めている", out, "前提: 母集団は 2 世代（GEN_SPLIT が真）")
        self.assertIn("反証 4/4", out, "前提: 層の集計は出ている")
        self.assertNotIn("反証 / opus-5:", out,
                         "その層に 1 世代しか届いていないのに内訳行を出している")

    def test_the_generation_breakdown_sums_to_the_aggregate(self):
        """世代別の分母の合計が本体の `n` と一致する（母集団をずらさない）.

        ずれると読み手が原因を探すことになる。スコープ外スキップは本体でも内訳でも
        分母から外れる。
        """
        rows = [self._layer_row("opus-4-8", False, "no-eligible-findings") for _ in range(3)]
        rows += [self._layer_row("opus-5", True) for _ in range(2)]
        self._events(rows)
        d = json.loads(self.run_script(RETRO, "--json", env=self._env()).stdout)
        adv = d["adversarial_verify"]
        self.assertEqual(sum(g["n"] for g in adv["by_gen"].values()), adv["n"])
        self.assertEqual(sum(g["fired"] for g in adv["by_gen"].values()), adv["fired"])

    def test_zero_report_rate_is_split_by_generation(self):
        """報告 0 件率を世代別に出す（recall の粗い代理）."""
        self._events([self._row("opus-5", 8, 3), self._row("opus-5", 7, 2),
                      self._row("opus-4-8", 0, 0), self._row("opus-4-8", 0, 0)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("報告 0 件率", out)
        rows = {l.split("|")[1].strip(): l for l in out.splitlines()
                if l.startswith("| opus-")}
        self.assertIn("0（0%）", rows["opus-5"], "Opus 5 側が 0 件率 0% になっていない")
        self.assertIn("2（100%）", rows["opus-4-8"], "4.8 側が 0 件率 100% になっていない")

    def test_yield_is_split_by_generation(self):
        """歩留まり（pre_adjust → 報告）の層別キーに世代が入る."""
        self._events([self._row("opus-5", 8, 3), self._row("opus-4-8", 0, 0)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("threshold=MAJOR/opus-5", out)
        self.assertIn("threshold=MAJOR/opus-4-8", out)

    def test_verdict_layers_are_split_by_generation(self):
        """反証 verdict の層キーに世代が入る（calib と世代の交絡を切る）."""
        self._events([self._row("opus-5", 8, 3, calib=2),
                      self._row("opus-4-8", 0, 0, calib=3)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("2/opus-5", out)
        self.assertIn("3/opus-4-8", out)

    def test_the_newest_layer_is_chosen_by_calibration_not_by_string_order(self):
        """層キーが複合文字列でも `calib` 最大の層を代表に取る.

        単純な `max()` だと辞書順で `unrecorded` が勝ち、**対策前の層を「最新」として
        扱ってしまう**。閾値比較（`>= CALIB_MIN`）も文字列では TypeError になる。
        """
        self._events([self._row(None, 8, 3, calib=1),          # unrecorded / 対策前
                      self._row("opus-5", 8, 3, calib=3)])     # 最新の層
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertNotIn("Traceback", out)
        self.assertIn("層 3/opus-5 を蓄積中", out,
                      "calib 最大の層が代表に選ばれていない")

    def test_a_single_generation_does_not_split_the_keys(self):
        """世代が 1 種しか無い母集団ではキーを割らない（既存の流儀を踏襲）."""
        self._events([self._row("opus-5", 8, 3), self._row("opus-5", 7, 2)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("threshold=MAJOR", out)
        self.assertNotIn("threshold=MAJOR/opus-5", out,
                         "1 世代しか無いのにキーを割っている")

    # ---- レビューで見つかった欠陥を pin する（#191 のセルフレビュー）----------

    def test_missing_report_counts_are_excluded_not_counted_as_zero(self):
        """報告件数フィールドを 1 つも持たない回を「報告 0 件」として数えない.

        **実データで陽性セルの 3/3 が偽陽性だった。** 0 件率は構造的に上振れし、
        しかも古い版ほど欠測が多いので「新しい世代ほど recall が落ちた」を機構が
        自分で作り出す（CLAUDE.md「0 と欠測を潰さない」）。
        """
        self._events([self._row("opus-5", 8, 3), self._row("opus-5", 7, 2),
                      self._row("opus-5", 9, None)])          # 旧版 = 報告件数なし
        out = self.run_script(RETRO, env=self._env()).stdout
        line = [l for l in out.splitlines() if l.startswith("| opus-5")][0]
        self.assertIn("| 2 |", line, "欠測の回を母数に入れている")
        self.assertIn("0（0%）", line, "欠測を報告 0 件として数えている")
        self.assertIn("1 件は母数から外した", out, "除外件数を黙って落としている")

    def test_a_generation_with_only_missing_counts_gets_no_row(self):
        """全件が欠測の世代に n=0 の行を作らない（比率が 0/0 になる）."""
        self._events([self._row("opus-5", 8, 3), self._row("opus-4-8", 9, None)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertNotIn("| opus-4-8 |", out, "n=0 の行が出ている")

    def test_the_table_is_shown_for_a_single_generation(self):
        """世代が 1 種でも表を出す（平常状態で指標が消えると劣化を見る手段が無い）."""
        self._events([self._row("opus-5", 8, 0), self._row("opus-5", 7, 0)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("報告 0 件率", out, "世代 1 種で表が消えている")
        self.assertIn("2（100%）", out)

    def test_the_median_column_shows_its_own_denominator(self):
        """中央値の分母は行の n と違う（`pre_adjust_counts.major` の欠測がある）."""
        self._events([self._row("opus-5", 8, 3), self._row("opus-5", None, 2)])
        out = self.run_script(RETRO, env=self._env()).stdout
        line = [l for l in out.splitlines() if l.startswith("| opus-5")][0]
        self.assertIn("| 2 |", line)
        self.assertIn("n=1", line, "中央値の分母が併記されていない")

    def test_a_generation_without_any_pre_major_shows_a_dash(self):
        """`pre_adjust_counts.major` が全件欠測なら中央値欄はハイフン."""
        self._events([self._row("opus-5", None, 3), self._row("opus-5", None, 2)])
        out = self.run_script(RETRO, env=self._env()).stdout
        line = [l for l in out.splitlines() if l.startswith("| opus-5")][0]
        self.assertTrue(line.rstrip().endswith("| - |"), "欠測が数値に化けている: %s" % line)

    def test_every_qualifying_layer_emits_a_signal(self):
        """閾値を超えた層は**すべて**シグナルに出す（代表 1 層だけ見ない）.

        層キーに世代が入って同じ calib に複数層が並ぶので、代表だけを見ると
        条件を満たした別世代が黙って落ちる。
        """
        rows = []
        for gen in ("opus-5", "opus-4-8"):
            for _ in range(10):
                rows.append(self._row(gen, 8, 3, calib=2, inflated=1))
        self._events(rows)
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("層=2/opus-5", out)
        self.assertIn("層=2/opus-4-8", out, "片方の世代のシグナルが落ちている")

    def test_the_split_table_matches_the_yield_table_granularity(self):
        """内訳（splits）の粒度を歩留まり（yields）に揃える.

        片方だけ割ると、隣り合う 2 表のどの行を分解した数字なのか対応付かない。
        """
        rows = []
        for gen in ("opus-5", "opus-4-8"):
            r = self._row(gen, 8, 3)
            r["below_threshold_counts"] = {"blocker": 0, "critical": 0,
                                           "major": 0, "minor": 5}
            rows.append(r)
        self._events(rows)
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("threshold=MAJOR/opus-5: n=1 / 本文を書いた", out)
        self.assertIn("threshold=MAJOR/opus-4-8: n=1 / 本文を書いた", out)

    def test_the_heading_does_not_claim_a_generation_split_when_there_is_none(self):
        """世代が 1 種のときは見出しで「× 世代で層別」と言わない（中身と矛盾する）."""
        self._events([self._row("opus-5", 8, 3), self._row("opus-5", 7, 2)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("（版マーカー × 閾値で層別", out)
        self.assertNotIn("版マーカー × 閾値 × 世代で層別", out)


class PreAdjustVocabTest(RetroTest):
    """`pre_adjust_counts` の語彙違反（GitHub issue #203）.

    契約は `{blocker, critical, major, minor}`。`below_threshold_counts` には厳密な検証が
    あるのに **対になる `pre_adjust_counts` には無く**、契約外のキー（実データに
    `{threshold, pre_major, pre_minor}` の例がある）が素通りしていた。しかも `schema` は
    publish が無条件に注入するので、下流からは「旧版の回」と区別が付かない。
    結果、`pre_major: 11` ＝ MAJOR 11 件の検出が `pre.get("major")` → **0 として計上**される。
    """

    #: 実データにあった契約外のキー体系（2026-08-28T05:09:04Z）
    BAD_PRE = {"threshold": "MAJOR", "pre_major": 11, "pre_minor": 10}

    def _ok(self, major: int, reported: int, below: int = 0) -> dict:
        return {"effort": "high", "size_tier": "medium", "measurement_gaps": [],
                "severity_threshold": "MAJOR",
                "pre_adjust_counts": {"schema": 2, "blocker": 0, "critical": 0,
                                      "major": major, "minor": 0},
                "below_threshold_counts": {"blocker": 0, "critical": 0,
                                           "major": below, "minor": 0},
                "major_count": reported}

    def _bad(self) -> dict:
        r = self._ok(0, 0)
        r["pre_adjust_counts"] = dict(self.BAD_PRE, schema=2)
        r["below_threshold_counts"] = {"blocker": 0, "critical": 0, "major": 0, "minor": 10}
        return r

    def test_a_bad_vocab_run_is_excluded_from_the_yield(self):
        """**語彙違反を歩留まりの分母・分子に入れない**（実数が 0 として計上される）."""
        self._events([self._ok(10, 4), self._ok(10, 4), self._bad()])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("n=2 / 検出 20 → 報告 8", out, "語彙違反を歩留まりに混ぜている")
        self.assertIn("1 件は `pre_adjust_counts` の語彙が契約外で母集団から外した", out,
                      "除外を silent に落としている")

    def test_a_bad_vocab_run_is_excluded_from_the_split(self):
        """検出内訳からも外す。**混ぜると `本文を書いた` が負に振れる**（実測 -10）."""
        self._events([self._ok(10, 4, below=2), self._bad()])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertNotIn("本文を書いた -", out, "語彙違反由来の負値が残っている")
        self.assertIn("1 件は `pre_adjust_counts` の語彙が契約外で母集団から外した", out)

    def test_a_negative_written_shows_no_percentage(self):
        """**負の分母に百分率を出さない**（`pct(-10, -10)` は 100.0% を返す）.

        負値そのものは残す（0 に丸めると「捨てていない」と読める）。正当な負値は
        「手順 1 の後に走る層が足したぶん」で、語彙違反は上で母集団から外してある。
        """
        # `below` が `pre` を超える形は publish が落とすので、集計側だけを直接叩く
        r = self._ok(0, 0)
        r["below_threshold_counts"] = {"blocker": 0, "critical": 0, "major": 0, "minor": 5}
        self._events([r])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("本文を書いた -5", out, "前提: 負の written が出ている")
        self.assertIn("本文を書いてから捨てた: -5 件（-）", out,
                      "負の分母に百分率を出している")
        self.assertNotIn("-5 件（100.0%）", out)

    def test_a_zero_written_shows_no_percentage_either(self):
        """**分母 0 でも百分率を出さない**（`pct` のゼロガードが `0.0%` に化ける）.

        `written == 0` は「本文を書いた指摘が 1 件も無い」= 比率が定義できない状態。
        `0.0%` と出すと「書いたうち 0% を捨てた」と読め、`-`（判定不能）と区別が付かない。
        """
        r = self._ok(0, 0)
        r["pre_adjust_counts"] = {"schema": 2, "blocker": 0, "critical": 0,
                                  "major": 0, "minor": 5}
        r["below_threshold_counts"] = {"blocker": 0, "critical": 0, "major": 0, "minor": 5}
        self._events([r])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("本文を書いた 0（検出 5 − 件数のみ 5）", out, "前提: written が 0")
        self.assertIn("本文を書いてから捨てた: 0 件（-）", out, "分母 0 に百分率を出している")

    def test_the_remediation_hint_is_vocabulary_not_omission(self):
        """是正先が `payload:` の既定（記述漏れ）に落ちない（語彙違反は直し方が違う）."""
        rows = [dict(self._ok(1, 0),
                     measurement_gaps=["payload:pre_adjust_counts.vocab"]) for _ in range(6)]
        self._events(rows)
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("記述漏れではなく語彙違反", out, "既定の是正先に落ちている")


class RetroLayerTableCapTest(RetroTest):
    """層別表の表示上限と省略の可視化（GitHub issue #198）.

    `effort × size_tier` と `1 体あたり cache_read` の 2 表は上位 8 層で切られていたが、
    **落とした層数も件数もどこにも出ていなかった**。切ると落ちるのは必ず n の小さい層 ＝
    **新しい世代**なので、世代交絡を消すための層別（#191）が新世代の観測を消していた
    （実測 n=108 で opus-5 が 2 表とも 0 行）。
    """

    def _row(self, effort: str, tier: str, gen: str, fleet: int) -> dict:
        return {"effort": effort, "size_tier": tier, "measurement_gaps": [],
                "duration_fleet_min": fleet,
                "agents": {"explorer": 2, "reviewer": 5},
                "models": {"schema": 1, "main": "claude-" + gen,
                           "main_distinct": ["claude-" + gen], "sub_distinct": []},
                "tokens": {"schema": 2, "window": "since-t0", "main_output_k": 100.0,
                           "sub_output_k": 200.0, "sub_cache_read_k": 7550.0,
                           "sub_agents": 2}}

    #: 上限（8 層）を超えるだけの層を作る effort × tier の組
    TIERS = [("high", "medium"), ("high", "small"), ("high", "large"),
             ("xhigh", "medium"), ("xhigh", "small"), ("xhigh", "large"),
             ("medium", "medium"), ("medium", "small"), ("low", "small")]

    def _population(self, old_gen: str = "opus-4-8", new_gen: str | None = "opus-5"):
        """旧世代を各層 n=5 で 9 層 + 新世代を n=1 で 1 層（新世代は必ず上限外に落ちる形）."""
        rows = []
        for i, (e, t) in enumerate(self.TIERS):
            rows += [self._row(e, t, old_gen, 20 + i) for _ in range(5)]
        if new_gen:
            rows.append(self._row("xhigh", "large", new_gen, 42))
        return rows

    def test_the_dropped_layers_are_reported(self):
        """**切ったら省略行を出す**（層数と件数の両方）.

        「どのログから何件採ったかは必ず出力する」という本スクリプトの流儀に、この 2 表だけが
        従っていなかった。母集団が言えないと「⚠️ が出たときだけ行動する」契約が成立しない。
        """
        self._events(self._population())
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("他 1 層（計 5 件）を省略", out, "省略を silent に落としている")

    def test_a_new_generation_survives_the_cap(self):
        """**世代ごとに最低 1 行は残す**（#198 の本題）.

        新世代は必ず n が小さいので、裸の上限では旧世代 9 層（各 n=5）に押し出されて
        表から丸ごと消える。世代比較のための層別が世代の観測を消しては本末転倒。
        """
        self._events(self._population())
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("| xhigh/large/opus-5 | 1 |", out,
                      "新世代の層が上限で落ちている（fleet 表）")
        self.assertIn("| xhigh/large/opus-5 | 1 | 3775 k |", out,
                      "新世代の層が上限で落ちている（1 体あたり cache_read 表）")

    def test_no_omission_note_when_nothing_is_dropped(self):
        """上限に収まる母集団では省略行を出さない（常時出ると読み飛ばされる）."""
        self._events([self._row("high", "medium", "opus-5", 20) for _ in range(3)])
        self.assertNotIn("を省略", self.run_script(RETRO, env=self._env()).stdout)

    def test_the_cap_still_applies_without_a_generation_split(self):
        """世代が 1 種のときも上限は効き、省略行は出る（救済だけが無効になる）.

        `GEN_SPLIT` が偽なら層別キーに世代が入らないので救済対象が無い。上限そのものは
        可読性のために残す。
        """
        self._events(self._population(old_gen="opus-4-8", new_gen=None))
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("1 種のみなので層別しない", out, "前提: 世代が 1 種")
        self.assertIn("他 1 層（計 5 件）を省略", out)
        self.assertNotIn("世代ごとの最低 1 行", out,
                         "世代を層別していないのに救済を名乗っている")


class RetroWaveSplitDenominatorTest(RetroTest):
    """wave-split の分母と是正先（GitHub issue #192）.

    wave-split は measurement_gaps に積まれるが、**他の gap と母集団の意味が違う**。
    他は「フィールドが載っていたか」なので gap 保持者全体でよいが、wave-split は
    「wave 判定が成立した回」が母集団。全体を分母にすると比率が薄まり、実測 50% が
    18% に見えて閾値を下回っていた。

    **fixture は `agents` まで整合させること**（#200）。集計側は payload の
    `waves_expected` ではなく `agents` から**現行式で再計算**して判定するので、
    `waves_expected` だけ立てた fixture は再計算値（reviewer 層の 1 本のみ）で
    判定され、**テストが意図と違う形で通る / 落ちる**。
    """

    @staticmethod
    def _agents_for(expected: int) -> dict:
        """再計算後の期待本数が `expected` になる `agents` を作る（#200）.

        reviewer 層の 1 本は常に見込まれるので、そこからの差分を層で埋める。
        """
        assert 1 <= expected <= 3, "この構成で作れるのは 1〜3 本"
        a = {"reviewer": 3}
        if expected >= 2:
            a["explorer"] = 2
        if expected >= 3:
            a["verify"] = 1
        return a

    def _run(self, waves: int, expected: int, gaps: list[str],
             agents: int = 3) -> dict:
        return {"effort": "high", "size_tier": "medium", "measurement_gaps": gaps,
                "agents": self._agents_for(expected),
                "dispatch": {"schema": 3, "agents": agents, "waves": waves,
                             "wave_sizes": [1] * waves, "max_solo_run": 1,
                             "max_inter_wave_sec": 60, "span_sec": 120,
                             "verdict": "layered", "waves_expected": expected}}

    def test_a_non_dict_agents_does_not_crash_retro(self):
        """**異形ログの非 dict `agents` で retro が沈黙死しない**（GitHub issue #200 のセルフレビュー）.

        retro は `--logs` で他マシン・他リポジトリのログも読むので `agents` が dict である
        保証は無い。`(agents or {}).get(...)` は truthy な非 dict で AttributeError になり、
        末尾の無条件 `exit 0` が例外を握って**出力 0 行・終了コード 0**（＝「該当なし」と
        区別がつかない沈黙死）に倒れる。`agents_dict` で正規化して防ぐ。
        """
        broken = self._run(3, 2, ["wave-split"])
        broken["agents"] = ["explorer"]          # dict でない agents（違反も立っている回）
        self._events([broken] + [self._run(3, 2, ["wave-split"]) for _ in range(4)])
        r = self.run_script(RETRO, env=self._env())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("一括発行", r.stdout, "retro が途中で沈黙死している（出力が欠けている）")

    def test_the_signal_stays_silent_below_the_sample_floor(self):
        """`GAP_MIN_N = 5` の直下（n=4）では点灯しない（`>= 5` → `>= 4` 変異を殺す）."""
        self._events([self._run(3, 2, ["wave-split"]) for _ in range(4)])
        self.assertNotIn("一括発行の規約違反が",
                         self.run_script(RETRO, env=self._env()).stdout,
                         "下限直下の 4 件で点灯している")

    def test_the_denominator_is_the_number_of_judged_runs(self):
        """分母は wave 判定が成立した回（gap 保持者全体ではない）."""
        rows = [self._run(3, 2, ["wave-split"]), self._run(2, 2, [])]
        # 判定が成立しない回（dispatch を持たない）を混ぜても分母は増えない
        rows += [{"effort": "high", "measurement_gaps": ["t1"]} for _ in range(8)]
        self._events(rows)
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("判定できた 2 件中 1 件が規約違反", out)

    def test_a_run_missing_waves_expected_is_not_judged(self):
        """`waves` と `waves_expected` の**両方**が揃った回だけを判定対象にする.

        片方だけで判定成立とみなすと、期待本数が無いのに分母へ入る。
        """
        rows = [self._run(3, 2, ["wave-split"]) for _ in range(2)]
        half = self._run(3, 2, [])
        del half["dispatch"]["waves_expected"]          # 期待本数が載っていない回
        rows.append(half)
        self._events(rows)
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("判定できた 2 件中 2 件が規約違反", out,
                      "waves_expected の無い回を分母に入れている")

    def test_suppressed_runs_are_reported_not_silently_dropped(self):
        """agents-mismatch で判定を抑止された回を明示する.

        分母にも分子にも入らないので、黙って落とすと「守られている」と読まれる
        （#154 のコメントが求めた処理が実装されていなかった）。
        """
        self._events([self._run(3, 2, ["wave-split"]),
                      self._run(8, 2, ["agents-mismatch"])])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("判定できた 1 件中 1 件が規約違反", out)
        self.assertIn("1 件は `agents-mismatch` で判定を抑止", out)
        self.assertIn("測れていない", out, "抑止を「守られた」と読ませない注記が無い")

    def test_the_verdict_is_recomputed_not_read_from_the_payload(self):
        """**判定は payload の `waves_expected` ではなく現行式の再計算**（GitHub issue #200）.

        `waves_expected` は publish 時点の式で焼き付くが**式の版マーカーが無い**ので、
        式を直しても過去のイベントは旧値のまま数え続けられ、**一度出た偽陽性が固定化する**
        （実測: `[6,10,4,1]` の回が #166 で解決済みの偽陽性なのに違反として残っていた）。
        """
        # 現行式なら 2 本（explorer + reviewer）＝ 実 2 本で違反にならない回に、
        # 旧式の値 1 が焼かれている形
        stale = self._run(2, 2, [])
        stale["dispatch"]["waves_expected"] = 1
        self._events([stale] + [self._run(3, 2, ["wave-split"]) for _ in range(4)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("判定できた 5 件中 4 件が規約違反", out,
                      "payload の旧い `waves_expected` で判定している")
        self.assertIn("1 件は payload の `waves_expected` と判定が食い違う", out,
                      "食い違いを黙って飲み込んでいる")

    def test_the_stale_note_is_absent_when_nothing_disagrees(self):
        """食い違いが無ければ注記も出さない（常時出ると注記が読み飛ばされる）."""
        self._events([self._run(3, 2, ["wave-split"]) for _ in range(5)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertNotIn("判定が食い違う", out)

    def test_a_single_explorer_leading_solo_is_a_layer_split_not_explorer(self):
        """explorer 1 体の先頭単独 wave は「explorer を 1 体ずつ」ではない（`>= 2` の境界）.

        explorer の 1 体ずつ発行は**2 体以上を別 wave に割った**形。explorer 1 体で先頭が
        単独 wave なのは通常の explorer wave であって、分割は別の層で起きている ＝「同一層の
        wave 分割」。閾値が `>= 1` に緩むとこれを explorer 型に誤分類する。
        """
        row = self._run(3, 2, ["wave-split"])
        row["agents"] = {"explorer": 1, "reviewer": 3}   # explorer ちょうど 1 体
        row["dispatch"]["wave_sizes"] = [1, 2, 4]         # 先頭が単独 wave・違反（3 > 2）
        self._events([row] + [self._run(2, 2, []) for _ in range(4)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("判定できた 5 件中 1 件が規約違反", out, "前提: この回だけが違反")
        self.assertIn("同一層の wave 分割 1 件", out)
        self.assertNotIn("explorer を 1 体ずつ発行", out,
                         "explorer 1 体を「1 体ずつ発行」に誤分類している")

    def test_the_violation_kinds_are_broken_out(self):
        """**違反の型ごとに件数を出す**（GitHub issue #200 の期待動作 3）.

        検知は #172 / #192 で整ったが、打ち手は型で違う（explorer を 1 体ずつ出したのか、
        同一層の wave が割れたのか）。層の割り当ては payload に無いので**推定**と名乗る。
        """
        # 先頭が単独 wave かつ explorer 2 体 → explorer 型 / 先頭が 2 体 → 層の分割型
        explorer_split = self._run(3, 2, ["wave-split"])
        explorer_split["dispatch"]["wave_sizes"] = [1, 1, 4]
        layer_split = self._run(3, 2, ["wave-split"])
        layer_split["dispatch"]["wave_sizes"] = [2, 2, 4]
        self._events([explorer_split] + [layer_split for _ in range(4)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("内訳（**推定**）: 同一層の wave 分割 4 件 / "
                      "explorer を 1 体ずつ発行 1 件", out)

    def test_a_non_list_wave_sizes_degrades_to_unknown(self):
        """`wave_sizes` がリストでない回で**型判定を諦める**（retro ごと落とさない）.

        retro は `--logs` で他マシン・他リポジトリのログも読むので、形の保証は無い。
        ガードが外れると添字アクセスで `TypeError` になり、**retro が出力 0 行 / 終了コード 0**
        で死ぬ（例外は python 側で起きるがシェルは `exit 0` する）。
        """
        broken = self._run(3, 2, ["wave-split"])
        broken["dispatch"]["wave_sizes"] = 3           # 数値（壊れた / 別実装のログ）
        empty = self._run(3, 2, ["wave-split"])
        empty["dispatch"]["wave_sizes"] = []
        self._events([broken, empty] + [self._run(3, 2, ["wave-split"]) for _ in range(3)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("判定できた 5 件中 5 件が規約違反", out, "retro が途中で死んでいる")
        self.assertIn("型不明", out, "型を判定できない回を既定の型に混ぜている")

    def test_the_signal_needs_the_sample_floor(self):
        """シグナル欄は `GAP_MIN_N = 5` ちょうどで点く（単発点灯の防止と両立させる）."""
        self._events([self._run(3, 2, ["wave-split"]) for _ in range(5)])
        self.assertIn("一括発行の規約違反が 100%",
                      self.run_script(RETRO, env=self._env()).stdout,
                      "下限ちょうどの回で点灯しない")

    def test_the_signal_needs_both_the_floor_and_the_ratio(self):
        """**件数と比率の両方**を要求する（片方だけで点くと 0 件でもシグナルが出る）."""
        self._events([self._run(2, 2, []) for _ in range(5)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("判定できた 5 件中 0 件が規約違反", out, "前提: 違反 0 件で判定は成立している")
        self.assertNotIn("一括発行の規約違反が", out, "違反 0 件でシグナルが点いている")

    def test_the_remediation_hint_is_not_the_default(self):
        """是正先が既定の「打点箇所の見直し」に落ちない（打点とは無関係）.

        シグナル欄は `GAP_MIN_N = 5`（単発点灯の防止）を要求するので、判定が成立する回を
        下限以上そろえる。
        """
        self._events([self._run(3, 2, ["wave-split"]) for _ in range(6)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("1 メッセージで一括発行", out)
        self.assertNotIn("打点箇所の見直しが要る", out, "既定の是正先に落ちている")
        # **「欠測」と呼ばない**（規約違反であって計測は取れている / #192）
        self.assertIn("一括発行の規約違反が 100%", out)
        self.assertNotIn("計測マーカー `wave-split` の欠測", out)


class RetroAgentFieldDenominatorTest(RetroTest):
    """`agents` を版プロキシに使う分母と、その境界（GitHub issue #204）.

    ここは **`--json` にしか出ない数**で、本文には比率としてしか現れない。変異が 5 件
    生存していた区間で、どれも「分母が静かに入れ替わる」型の壊れ方をする — 母集団が
    反転しても出力の体裁は変わらず数字だけ動くので、目視では気づけない。
    """

    @staticmethod
    def _row(agents: dict | None = None, gaps: list[str] | None = None) -> dict:
        p = {"effort": "high", "size_tier": "medium",
             "measurement_gaps": [] if gaps is None else gaps}
        if agents is not None:
            p["agents"] = agents
        return p

    def _json(self) -> dict:
        r = self.run_script(RETRO, "--json", env=self._env())
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    # ---- round2（`agents.round2` のキー存在が版プロキシ / #127 と同型）---------

    def test_round2_scope_holds_only_runs_that_record_the_field(self):
        """分母は `agents.round2` を**記録している回**だけ.

        キーごと無い旧版を混ぜると「起動しなかった」と同じ扱いになり、発火率が構造的に
        薄まる。母集団が反転しても件数の体裁は変わらないので、**両側の件数を非対称に**
        して向きまで固定する。
        """
        self._events([self._row({"reviewer": 2}), self._row({"reviewer": 2}),
                      self._row({"reviewer": 2, "round2": 1})])
        out = self._json()
        self.assertEqual(out["round2_scope"], 1, "記録の無い旧版を分母に入れている")
        self.assertEqual(out["round2_fired"], 1)

    def test_round2_fired_counts_positive_values_only(self):
        """発火は「1 本以上起動した回」。0 本の回は分母に残して分子から外す."""
        self._events([self._row({"round2": 2}), self._row({"round2": 0})])
        out = self._json()
        self.assertEqual(out["round2_scope"], 2)
        self.assertEqual(out["round2_fired"], 1, "起動本数が正の回を数えていない")

    # ---- explorer_waves（欠測率の生カウント）----------------------------------

    def test_have_explorer_waves_counts_runs_that_record_the_field(self):
        """`have_explorer_waves` は**フィールドを持つ回**。0 も「記録あり」に数える.

        打点が無くても 0 が必ず入るフィールドなので、値ではなく存在で数える。ここが
        反転すると欠測率の分母が旧版だけになる。
        """
        self._events([self._row({"reviewer": 2}), self._row({"reviewer": 2}),
                      self._row({"reviewer": 2, "explorer_waves": 0})])
        self.assertEqual(self._json()["measurement"]["have_explorer_waves"], 1,
                         "記録の無い旧版を「記録あり」と数えている")

    def test_two_waves_already_counts_as_split(self):
        """境界は「2 波以上」。3 波以上に狭めない（2 波が最頻の分割形）."""
        self._events([self._row({"explorer_waves": 1}), self._row({"explorer_waves": 2})])
        m = self._json()["measurement"]
        self.assertEqual(m["have_explorer_waves"], 2, "前提: どちらも記録はある")
        self.assertEqual(m["split_explorer_waves"], 1, "2 波を分割として数えていない")

    # ---- modern 側の explorer 起動回（健全性表示の分母）------------------------

    def test_a_single_explorer_run_is_in_the_health_denominator(self):
        """explorer を **1 体でも**起動した回は分母に入る（未起動だけを外す）.

        「該当なし」として外すのは 0 体の回だけ。1 体の回まで落とすと、explorer を絞った
        セッションの打点漏れが健全性表示から丸ごと消える。
        """
        self._events([self._row({"explorer": 0}), self._row({"explorer": 1})])
        m = self._json()["measurement"]
        self.assertEqual(m["modern_explorer_waves_scope"], 1,
                         "explorer 1 体の回を分母から落としている")
        self.assertEqual(m["modern_explorer_waves"], 1)


class RetroUnreachableWaitTest(RetroTest):
    """達成不能な待ち行を明示する（GitHub issue #191 期待動作 2）."""

    def _v(self, gen: str, calib: int, total: int = 1) -> dict:
        r = {"effort": "high", "measurement_gaps": [],
             "models": self._models("claude-%s" % gen),
             "adversarial_verify": {"fired": True, "skip_reason": None, "gate_schema": 2,
                                    "calibration_schema": calib, "confirmed": total,
                                    "refuted": 0, "uncertain": 0,
                                    "severity_inflated": 0, "contested": 0}}
        return r

    def test_a_layer_present_in_only_one_generation_is_flagged(self):
        """対策後の層が 1 世代にしか無いとき、待つだけでは分離できないと出す."""
        self._events([self._v("opus-5", 2), self._v("opus-4-8", 3)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("にしか存在しない", out)
        self.assertIn("達成不能", out)

    def test_the_flag_counts_layers_of_the_same_calibration(self):
        """同じ calib の層を数える（別 calib を数えると判定が逆転する）.

        calib=2 が 1 世代・calib=3 が 2 世代にあるとき、最新層 calib=3 は
        両世代に存在するので**警告は出ない**。別 calib を数えると 1 件になり誤って出る。
        """
        self._events([self._v("opus-5", 2), self._v("opus-5", 3), self._v("opus-4-8", 3)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertNotIn("達成不能", out, "別 calib の層を数えている")

    def test_a_layer_present_in_both_generations_is_not_flagged(self):
        """両世代にサンプルがあるなら分離できるので警告を出さない."""
        self._events([self._v("opus-5", 3), self._v("opus-4-8", 3)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertNotIn("達成不能", out)


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

    # ---- 母集団の範囲を明示する（issue #173）--------------------------------
    def test_explicit_logs_do_not_get_the_scope_note(self):
        """`--logs` は利用者が範囲を決めているので注記を出さない（ノイズにしない）."""
        a = self.write_log("repo-a/.claude/events.jsonl", self.base_rows(2))
        out = self.retro("--logs", str(a))
        self.assertNotIn("母集団はこのリポジトリのログに限られている", out)
        self.assertNotIn("このリポジトリのログのみ", out)

    def test_explicit_logs_report_scope_in_json(self):
        a = self.write_log("repo-a/.claude/events.jsonl", self.base_rows(2))
        got = json.loads(self.retro("--logs", str(a), "--json"))
        self.assertEqual(got["sources_scope"], "explicit")


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


class RetroScopeNoteTest(ScriptTestBase):
    """自動探索の回に**母集団の範囲**を明示する（GitHub issue #173）.

    読んだものだけを書くと「これが全部」と読まれる。実測では、プラグインを開発している
    リポジトリが最も母数を持たず（素の実行で n=2 / `--logs` 合算で n=99）、出力が
    「サンプル待ち」で埋まったため**判定可能なデータがあるのに 2 セッション判断が
    先送りされた**。探索は既定にしない（#160 の判断を維持）ので、消すのは誤読だけ。
    """

    def _write(self, rows: list[dict]) -> None:
        log = self.root / ".claude" / "events.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("\n".join(
            json.dumps({"ts": "2026-08-%02dT00:00:00Z" % (i + 1),
                        "plugin": "code-review:self-review",
                        "event": "review:completed", "payload": r}, ensure_ascii=False)
            for i, r in enumerate(rows)) + "\n", encoding="utf-8")

    def _retro(self, *args: str):
        # `run_script` は `cwd=self.root` 固定なので、自動探索は使い捨てリポジトリ側を見る
        res = self.run_script(RETRO, *args, env=self._env())
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout

    def test_auto_discovery_says_the_population_is_this_repo_only(self):
        self._write([{"effort": "high", "size_tier": "medium", "measurement_gaps": []}
                     for _ in range(3)])
        out = self._retro()
        self.assertIn("このリポジトリのログのみ", out, "母集団の行に範囲が出ていない")
        self.assertIn("母集団はこのリポジトリのログに限られている", out)
        self.assertIn("--logs", out, "合算する手段を案内していない")
        self.assertIn("events.jsonl", out, "パス一覧の作り方を出していない")

    def test_the_note_also_appears_when_there_are_no_samples(self):
        """**0 件の回が最も誤読されやすい**（「まだ回っていない」と読まれる）."""
        self._write([])
        out = self._retro()
        self.assertIn("母集団はこのリポジトリのログに限られている", out)

    def test_auto_discovery_reports_scope_in_json(self):
        self._write([{"effort": "high", "size_tier": "medium", "measurement_gaps": []}])
        got = json.loads(self._retro("--json"))
        self.assertEqual(got["sources_scope"], "this-repo")

    def test_the_note_is_not_gated_on_sample_count(self):
        """**閾値を置かない** — 下で黙る区間がまさに誤読の起きる帯になる.

        件数が多い回でも他リポジトリを含まないことは変わらないので、常に出す。
        """
        self._write([{"effort": "high", "size_tier": "medium", "measurement_gaps": []}
                     for _ in range(30)])
        out = self._retro()
        self.assertIn("n=30", out, "前提: 件数の多い母集団になっている")
        self.assertIn("母集団はこのリポジトリのログに限られている", out)


class WaveSplitTest(TranscriptFixture):
    """wave 本数の期待値との突合（一括発行違反の全層検出）.

    既存の 2 経路はどちらも一部しか見ていなかった:

    - `dispatch.verdict == "serial"` は**単独 wave 3 連続**を要求する → 「reviewer 5 体の
      うち 1 体だけ先に出した」型を取り逃す（実測: fleet span の 20% ＝ 9 分を失った回が
      `layered`（正常）判定だった）
    - `agents.explorer_waves` は explorer 層しか数えない

    規約（`orchestration-guide.md ## 0`）は全 agent に掛かるので、**層を同定せず
    既存フィールドの算術**で見る。`meta.json` の `description` による層分類は採らない —
    LLM の自由文で書式が安定せず（実測 25 セッションで大半が分類不能）、分類器は
    **静かに何も検出しない**方向に倒れる。
    """

    BASE = datetime(2026, 8, 18, 1, 0, 0)

    def epoch(self, off: int = 0) -> int:
        return int(self.BASE.replace(tzinfo=timezone.utc).timestamp()) + off

    def run_publish(self, payload: dict | None = None) -> dict:
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10), t2=self.epoch(1200))
        self.publish(payload, env=self.env_home())
        return self.last_payload()

    def agents(self, **over) -> dict:
        a = {"explorer": 1, "reviewer": 3, "verify": 1}
        a.update(over)
        return dict(BASE_PAYLOAD, agents=a)

    def test_a_split_layer_raises_the_gap(self):
        """reviewer が 2 wave に割れた形（実測 08-22 の型）を検出する."""
        self.write_transcript([[0], [100], [200, 210], [300]], base=self.BASE)
        p = self.run_publish(self.agents())
        self.assertEqual(p["dispatch"]["waves"], 4)
        self.assertEqual(p["dispatch"]["waves_expected"], 3)
        self.assertIn("wave-split", p["measurement_gaps"])

    def test_the_canonical_shape_is_not_flagged(self):
        """explorer → reviewer → 反証 は設計上正当（**偽陽性を出さない**）.

        ここが鳴ると「⚠️ が出たときだけ行動する」契約が壊れる。
        """
        self.write_transcript([[0], [100, 110, 120], [200]], base=self.BASE)
        p = self.run_publish(self.agents())
        self.assertEqual(p["dispatch"]["waves"], 3)
        self.assertNotIn("wave-split", p["measurement_gaps"])

    def test_round_two_is_allowed_extra_waves(self):
        """Round 2 の再起動は `## 8` で正当に wave を増やす（見込みに入れる）."""
        self.write_transcript([[0], [100], [200, 210], [300]], base=self.BASE)
        p = self.run_publish(self.agents(reviewer=2, round2=1))
        self.assertEqual(p["dispatch"]["waves_expected"], 5)
        self.assertNotIn("wave-split", p["measurement_gaps"])

    def test_meta_added_findings_expect_one_more_wave(self):
        """**meta 由来指摘の反証バッチは構造的な直列**（GitHub issue #166）.

        実運用で初めて `wave-split` が立った回（`[6,10,4,1]` / PR 398）が偽陽性だった。
        wave 4 は meta が足した指摘を反証にかけるバッチで、**meta の出力が存在しない
        時点では発行できない**。`meta_reviewer` は `agents` に計上しない契約なので、
        この 1 本は既存の式のどの項にも現れていなかった。
        """
        # meta 発火は `declared` に +1 されるので transcript も 6 体にする
        # （`agents-mismatch` が立つと wave 判定そのものが抑止される）
        self.write_transcript([[0], [100, 105], [200, 210], [300]], base=self.BASE)
        p = dict(self.agents(),
                 meta_reviewer={"fired": True, "skip_reason": None, "findings_added": 2})
        published = self.run_publish(p)
        self.assertNotIn("agents-mismatch", published["measurement_gaps"], "前提: 申告が揃っている")
        self.assertEqual(published["dispatch"]["waves"], 4)
        self.assertEqual(published["dispatch"]["waves_expected"], 4,
                         "meta が足した指摘の反証 wave を見込んでいない")
        self.assertNotIn("wave-split", published["measurement_gaps"])

    def test_meta_without_added_findings_does_not_raise_the_expectation(self):
        """`findings_added` 0 の回では増やさない（**見込み過多は検出漏れになる**）."""
        self.write_transcript([[0], [100, 105], [200, 210], [300]], base=self.BASE)
        p = dict(self.agents(),
                 meta_reviewer={"fired": True, "skip_reason": None, "findings_added": 0})
        published = self.run_publish(p)
        self.assertEqual(published["dispatch"]["waves_expected"], 3)
        self.assertIn("wave-split", published["measurement_gaps"],
                      "既知の違反を取り逃している")

    def test_an_unfired_meta_does_not_raise_the_expectation(self):
        """meta 未発火なら増やさない（`findings_added` が残っていても発火が優先）."""
        self.write_transcript([[0], [100], [200, 210], [300]], base=self.BASE)
        p = dict(self.agents(),
                 meta_reviewer={"fired": False, "skip_reason": "effort", "findings_added": 3})
        published = self.run_publish(p)
        self.assertEqual(published["dispatch"]["waves_expected"], 3)
        self.assertIn("wave-split", published["measurement_gaps"])

    def test_the_known_reviewer_split_is_still_caught_with_meta(self):
        """**判定そのものを緩めない**（#166 の補足）.

        v2.84.0 が拾った既知の違反（reviewer が単独 wave に割れる `[1,1,...]` 型）は
        meta と無関係なので、meta の項を足しても取り逃さない。
        """
        # 6 体 / 5 wave（[1,1,1,2,1]）に対し meta 込みの見込みは 4
        self.write_transcript([[0], [100], [200], [300, 310], [400]], base=self.BASE)
        p = dict(self.agents(),
                 meta_reviewer={"fired": True, "skip_reason": None, "findings_added": 2})
        published = self.run_publish(p)
        self.assertEqual(published["dispatch"]["waves_expected"], 4)
        self.assertIn("wave-split", published["measurement_gaps"],
                      "meta の項を足したせいで既知の違反を取り逃している")

    # ---- skeptic fallback の末尾単独 wave 控除（issue #172）--------------------
    def _skeptic(self, fired: bool = True) -> dict:
        return {"fired": fired, "skip_reason": None if fired else "no-surface",
                "attribution_schema": 2, "findings_added": 0}

    def test_skeptic_fallback_tail_solo_wave_is_deducted(self):
        """skeptic の fallback は**末尾の単独 wave**なので偽陽性（実測 08-24T05:40 / `[2,5,1]`）.

        `triage-dynamic-gates.md ## 8.5` で reviewer 完了後の単独 1 体と規約で決まっている。
        """
        self.write_transcript([[0, 10], [100, 110, 120, 130, 140], [200]], base=self.BASE)
        p = dict(self.agents(explorer=2, reviewer=5, verify=0),
                 recall_skeptic=self._skeptic())
        published = self.run_publish(p)
        # **`agents-mismatch` が立つと wave 判定が抑止される** = 下の assertNotIn が
        # 理由の違うまま通る（空虚な pass）。前提を明示的に縛る
        self.assertNotIn("agents-mismatch", published["measurement_gaps"], "前提: 申告が揃っている")
        self.assertEqual(published["dispatch"]["wave_sizes"], [2, 5, 1])
        self.assertEqual(published["dispatch"]["waves_expected"], 3,
                         "末尾の単独 wave 1 本を控除していない")
        self.assertNotIn("wave-split", published["measurement_gaps"])

    def test_deduction_does_not_hide_a_leading_split(self):
        """**末尾が「唯一の」単独 wave のときだけ控除する**（実測 08-25T08:32 / `[1,1,6,1]`）.

        explorer 2 体が先頭で 2 wave に割れた**本物の違反**。控除で消してはならない。

        **fixture は実サンプルの記録 expected 3 を再現する**（`verify=1` を含む構成）。
        v2.91.0 の初版はこのテストを `verify=0`（= 基礎 expected 2）で組んでいたため、
        `sizes[-1] == 1` だけで控除する実装でも通ってしまい、**docstring が名指しした
        当のサンプルが実装で消えている**ことを検出できなかった（セルフレビューで発覚）。
        名指しした実測回を守るテストは、その回の**層構成まで**再現すること。
        """
        # explorer 1+1（分割）/ reviewer 6 / verify 1 = 9 体。skeptic 発火の +1 込みで
        # 申告も 9 に揃える（`agents-mismatch` が立つと wave 判定そのものが抑止される）
        self.write_transcript([[0], [100], [200, 210, 220, 230, 240, 250], [300]],
                              base=self.BASE)
        p = dict(self.agents(explorer=2, reviewer=5, verify=1),
                 recall_skeptic=self._skeptic())
        published = self.run_publish(p)
        self.assertNotIn("agents-mismatch", published["measurement_gaps"], "前提: 申告が揃っている")
        self.assertEqual(published["dispatch"]["wave_sizes"], [1, 1, 6, 1])
        self.assertEqual(published["dispatch"]["waves_expected"], 3,
                         "先頭に単独 wave が残っているのに控除している")
        self.assertIn("wave-split", published["measurement_gaps"],
                      "先頭の explorer 分割を末尾控除で消している")

    def test_a_verify_wave_after_the_skeptic_still_deducts(self):
        """**skeptic の後ろに反証 wave が付いても控除する**（実測 08-28T00:28 / `[2,5,1,1]`）.

        初版（v2.91.0）の条件は「末尾が**唯一の**単独 wave」だったので、後ろに反証 wave が
        1 本付いた瞬間に効かなくなり偽陽性を出していた（GitHub issue #200 / #172 が
        「既知の残存限界②」として予告していた形）。末尾から連続する単独 wave は
        **入力が揃うまで発行できない層**が並ぶ場所なので、そこは控除の対象にする。
        """
        # explorer 2 / reviewer 5 / 反証 1 / skeptic 1 = 9 体。申告も skeptic 込みで 9 に揃える
        # （`agents-mismatch` が立つと wave 判定そのものが抑止される）
        self.write_transcript([[0, 10], [100, 110, 120, 130, 140], [200], [300]],
                              base=self.BASE)
        p = dict(self.agents(explorer=2, reviewer=5, verify=1),
                 recall_skeptic=self._skeptic())
        published = self.run_publish(p)
        self.assertNotIn("agents-mismatch", published["measurement_gaps"], "前提: 申告が揃っている")
        self.assertEqual(published["dispatch"]["wave_sizes"], [2, 5, 1, 1])
        self.assertEqual(published["dispatch"]["waves_expected"], 4,
                         "末尾に連なる単独 wave のうち 1 本を控除していない")
        self.assertNotIn("wave-split", published["measurement_gaps"])

    def test_no_deduction_when_the_tail_is_not_solo(self):
        """末尾が単独でなければ控除しない（実測 08-25T13:42 `[2,2,4]` / 08-26T06:07 `[2,3]`）.

        skeptic fallback は単独 1 体なので、末尾が 2 体以上ならその形では説明できない。
        """
        # 申告は transcript の 8 体と合わせる（skeptic 発火の +1 込み。
        # `agents-mismatch` が立つと wave 判定そのものが抑止される）
        self.write_transcript([[0, 10], [100, 110], [200, 210, 220, 230]], base=self.BASE)
        p = dict(self.agents(explorer=2, reviewer=5, verify=0),
                 recall_skeptic=self._skeptic())
        published = self.run_publish(p)
        self.assertNotIn("agents-mismatch", published["measurement_gaps"], "前提: 申告が揃っている")
        self.assertEqual(published["dispatch"]["wave_sizes"], [2, 2, 4])
        self.assertEqual(published["dispatch"]["waves_expected"], 2)
        self.assertIn("wave-split", published["measurement_gaps"])

    def test_no_deduction_when_skeptic_did_not_fire(self):
        """未発火なら末尾が単独でも控除しない（形だけで引くと本物を取り逃す）."""
        self.write_transcript([[0, 10], [100, 110, 120, 130, 140], [200]], base=self.BASE)
        p = dict(self.agents(explorer=2, reviewer=6, verify=0),
                 recall_skeptic=self._skeptic(fired=False))
        published = self.run_publish(p)
        self.assertNotIn("agents-mismatch", published["measurement_gaps"], "前提: 申告が揃っている")
        self.assertEqual(published["dispatch"]["waves_expected"], 2)
        self.assertIn("wave-split", published["measurement_gaps"])

    def test_wave_split_now_warns(self):
        """**WARN 化した**（#172）— 偽陽性 2 型が同定できたので測定段階を抜けた."""
        self.write_transcript([[0], [100], [200, 210], [300]], base=self.BASE)
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10), t2=self.epoch(1200))
        r = self.publish(self.agents(), env=self.env_home())
        self.assertIn("wave-split", self.last_payload()["measurement_gaps"])
        self.assertIn("一括発行の規約違反", r.stderr)
        self.assertIn("#172", r.stderr)

    def test_the_canonical_shape_stays_silent(self):
        """正当な形では WARN も出さない（「⚠️ が出たときだけ行動する」契約）.

        **否定 2 本だけだと liveness ガードが無い** — 頭数が崩れて `agents-mismatch` に
        落ちれば WARN 経路が丸ごと死んだまま緑になる（このファイル冒頭の `signals()` が
        同じ教訓を持つ）。前提と実測値を先に表明してから否定を置く。
        """
        self.write_transcript([[0], [100, 110, 120], [200]], base=self.BASE)
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10), t2=self.epoch(1200))
        r = self.publish(self.agents(), env=self.env_home())
        published = self.last_payload()
        self.assertNotIn("agents-mismatch", published["measurement_gaps"], "前提: 申告が揃っている")
        self.assertEqual(published["dispatch"]["waves"], 3)
        self.assertEqual(published["dispatch"]["waves_expected"], 3)
        self.assertNotIn("wave-split", published["measurement_gaps"])
        self.assertNotIn("#172", r.stderr)

    def test_a_broken_headcount_suppresses_the_verdict(self):
        """`agents-mismatch` の回では判定しない.

        期待本数は `agents` の**自己申告**から作るので、申告が壊れている回に重ねると
        原因の違う 2 つの信号が混ざり、是正先を指せなくなる。
        """
        self.write_transcript([[0], [100], [200, 210], [300]], base=self.BASE)
        p = self.run_publish(self.agents(reviewer=1))
        self.assertIn("agents-mismatch", p["measurement_gaps"], "前提: 申告が壊れている")
        self.assertNotIn("wave-split", p["measurement_gaps"])

    def test_a_run_without_explorers_expects_one_wave_fewer(self):
        """explorer 0 体の回で見込みを 1 つ減らす（**見込み過多は検出漏れになる**）.

        既存テストが全部 explorer 1 体だったため、`explorer > 0` を `>= 0` に広げる変異
        （＝常に 1 wave 多く見込む）が CI の変異スモークまで生存した。広げると
        `[5,1]` 型（explorer 無し）の分割が丸ごと見えなくなる。
        """
        self.write_transcript([[0], [100, 110], [200]], base=self.BASE)
        p = self.run_publish(self.agents(explorer=0, reviewer=3))
        self.assertEqual(p["dispatch"]["waves_expected"], 2)
        self.assertIn("wave-split", p["measurement_gaps"])

    def test_a_run_without_verification_expects_one_wave_fewer(self):
        """反証 0 体の回も同じ（`verify` 側の境界を独立に表明する）."""
        self.write_transcript([[0], [100], [200, 210]], base=self.BASE)
        p = self.run_publish(self.agents(reviewer=3, verify=0))
        self.assertEqual(p["dispatch"]["waves_expected"], 2)
        self.assertIn("wave-split", p["measurement_gaps"])

    def test_waves_expected_is_always_present(self):
        """**常に載る**ので、フィールドの存在自体が版マーカーになる（`derived_markers` と同じ流儀）."""
        self.write_transcript([[0], [100, 110, 120], [200]], base=self.BASE)
        p = self.run_publish(self.agents())
        self.assertIn("waves_expected", p["dispatch"])

    def test_the_gap_does_not_fail_the_publish(self):
        """**fail-fast にしない** — 止めると計測が丸ごと消える（`agents-mismatch` と同じ）."""
        self.write_transcript([[0], [100], [200, 210], [300]], base=self.BASE)
        self.timeline(t0=self.epoch(-300), t1=self.epoch(-10), t2=self.epoch(1200))
        r = self.publish(self.agents(), env=self.env_home())
        self.assertEqual(r.returncode, 0, r.stderr)


class ReviewBackfillTest(TranscriptFixture):
    """後付け計測 CLI（`review-backfill.sh` / GitHub issue #153・#156）.

    **守りたいのは「誤値を出すより欠測に倒す」**。窓は payload の `duration_*` からの
    逆算なので、窓が汚れた回を通すと**もっともらしい過大値**が判断に混ざる。除外の
    3 経路（区間欠測 / 窓外の agent / 窓が別レビューを内包）と、突合式が publish と
    同一であることを固定する。
    """

    BASE = datetime(2026, 8, 18, 1, 0, 0)
    TS = "2026-08-18T02:00:00Z"

    def payload(self, **over) -> dict:
        """`t0` が `BASE` に一致する窓を作る payload（60 分 = triage 1 + fleet 50 + closing）."""
        p = {"pr": "local", "effort": "high", "size_tier": "medium",
             "duration_min": 60, "duration_triage_min": 1, "duration_fleet_min": 50,
             "agents": {"explorer": 1, "reviewer": 1},
             "recall_skeptic": {"fired": False}, "meta_reviewer": {"fired": False}}
        p.update(over)
        return p

    def write_events(self, *payloads: dict, ts: str | None = None) -> Path:
        log = self.root / "events.jsonl"
        log.write_text("".join(
            json.dumps({"ts": ts or self.TS, "plugin": "code-review:self-review",
                        "event": "review:completed", "payload": p}) + "\n"
            for p in payloads), encoding="utf-8")
        return log

    def backfill(self, log: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return self.run_script(BACKFILL, "--logs", str(log), *args, env=self.env_home())

    def test_rows_carry_the_model_generation(self):
        """後付け行に世代を持たせる（GitHub issue #169）.

        `cache_read_k_per_agent` は **tier と世代が交絡する**（実測: 7,853k と 3,7xx k）。
        世代キーが無いと「深さのコストが下がった」と「4.8 だから軽い」を永久に分離できない。
        """
        self.write_transcript([[120], [200], [280, 290]], base=self.BASE,
                              main_models=("claude-opus-4-8",),
                              sub_models=("claude-opus-4-8", "claude-sonnet-5"))
        rows = json.loads(self.backfill(self.write_events(self.payload()), "--json").stdout)["backfilled"]
        self.assertEqual(len(rows), 1, "前提: 後付けが成立していない")
        self.assertEqual(rows[0]["model_main"], "claude-opus-4-8")

    def test_a_mixed_generation_row_is_not_given_a_representative_value(self):
        """混在した回は `None`。**単一世代の中央値に混ぜない**（表示は `mixed` バケツ）."""
        self.write_transcript([[120], [200], [280, 290]], base=self.BASE,
                              main_models=("claude-opus-5", "claude-opus-4-8"))
        log = self.write_events(self.payload())
        rows = json.loads(self.backfill(log, "--json").stdout)["backfilled"]
        self.assertIsNone(rows[0]["model_main"], "混在した回に代表値を選んでいる")
        self.assertIn("mixed", self.backfill(log).stdout)

    def test_the_mixed_bucket_is_the_one_marked_unusable(self):
        """注記は **mixed 行にだけ**付き、中央値は実数で出る.

        注記が単一世代の行へ回ると「比較に使うな」が逆向きに掛かり、**mixed の
        バケツが比較可能に見える**。中央値が `-` に潰れる変異も同時に殺す。
        """
        self.write_transcript([[120], [200], [280, 290]], base=self.BASE,
                              main_models=("claude-opus-5", "claude-opus-4-8"))
        mixed = self.backfill(self.write_events(self.payload())).stdout
        self.assertRegex(mixed, r"mixed\s+n=1\s+中央値 [0-9.]+k\s+←",
                         "mixed 行に実数の中央値と注記が並んでいない")

    def test_a_single_generation_row_is_not_marked_unusable(self):
        """単一世代の行には注記を付けない（`## 世代別` の対になるケース）."""
        self.write_transcript([[120], [200], [280, 290]], base=self.BASE,
                              main_models=("claude-opus-4-8",))
        out = self.backfill(self.write_events(self.payload())).stdout
        # **否定系の前に行の存在を表明する**（liveness ガード）。後付けが 1 行も成立しない
        # 状態でも `assertNotIn` は真になるので、それだけだと恒久 pass になる
        self.assertRegex(out, r"後付け成立 1 件",
                         "前提: 後付けが 1 行も成立していない（注記の有無を見る意味が無い）")
        self.assertIn("世代は opus-4-8 の 1 種のみ", out,
                      "前提: 世代が解決できていない")
        self.assertNotIn("←", out, "単一世代の行に「比較に使わない」の注記が付いている")

    def test_a_missing_wave_end_does_not_abort_the_row(self):
        """終了時刻が取れない wave があっても行ごと落とさない.

        `wave_clock` の `end` は **wave 内に終了時刻を取れない体が 1 体でもいれば `None`**
        （`measure-tokens.sh` の縮退 / #153）。素で引き算すると `TypeError` で**途中まで
        出力して落ちる**。実データが全部埋まっていたため表に出ていなかった経路。
        """
        self.write_transcript([[120], [200], [280, 290]], base=self.BASE, ends={0: 150})
        r = self.backfill(self.write_events(self.payload()), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = json.loads(r.stdout)["backfilled"]
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["tail_wave_share"], "欠測を実数に倒している")
        self.assertIsNotNone(rows[0]["waves_expected"], "他の値まで巻き添えにしている")

    def test_projects_needs_a_value(self):
        """`--projects` も値落ちを黙殺しない（`--logs` と同じ規約）.

        **テストを書かずに足したため、CI の変異スモークで引数パースの境界 3 件が
        生存した**（`--logs` 側だけ表明していた）。値を取るフラグは全部同じ形で縛る。
        """
        r = self.run_script(BACKFILL, "--logs", str(self.write_events(self.payload())),
                            "--projects", env=self.env_home())
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_a_missing_projects_dir_is_fatal(self):
        """存在しない探索先で黙って 0 件に倒さない（タイプミスを「サンプルが少ない」にしない）."""
        r = self.run_script(BACKFILL, "--logs", str(self.write_events(self.payload())),
                            "--projects", str(self.root / "nope"), env=self.env_home())
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_projects_overrides_the_search_path(self):
        """`--projects` が実際に探索先を差し替える（空の dir を渡せば 0 件になる）."""
        empty = self.root / "empty-projects"
        empty.mkdir()
        self.write_transcript([[60], [300]], ends={0: 180, 1: 420}, base=self.BASE)
        r = self.run_script(BACKFILL, "--logs", str(self.write_events(self.payload())),
                            "--projects", str(empty), "--json", env=self.env_home())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["backfilled"], [],
                         "`--projects` が既定の探索先を上書きしていない")

    def test_the_human_summary_reports_the_aggregates(self):
        """**既定（人間向け）出力の集計行を表明する**.

        テストが全部 `--json` 経由だったため、集計行（突合の一致数 / 中央値 / ギャップ
        内訳の抽出条件）が**丸ごと未検証**で、nightly が 13 件の生存を出した。
        既定出力こそこのツールの主インターフェース。
        """
        self.write_transcript([[60], [300]], ends={0: 180, 1: 420}, base=self.BASE)
        r = self.backfill(self.write_events(self.payload()))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("後付け成立 1 件", r.stdout)
        self.assertIn("一致 1 / 不一致 0", r.stdout, "突合の集計が壊れている")
        self.assertIn("0 / 1 件", r.stdout, "違反判定の分母が壊れている")
        # **値まで見る**。行の存在だけだと `tok.get("sub") and {}` のような既定値の
        # 潰し方の変異が生き残る（合計 0 でも行は出る）
        med = re.search(r"1 体あたり cache_read の中央値\*\*: ([0-9.]+)k", r.stdout)
        self.assertIsNotNone(med, "cache_read の中央値行が出ていない")
        self.assertGreater(float(med.group(1)), 0, "cache_read を 0 に潰している")
        self.assertIn("最大 wave 間ギャップに占める agent 実行の中央値", r.stdout,
                      "ギャップ内訳の抽出条件が壊れている")
        # 表の行に cr/体 の実数が出る（`is not None` の三項が反転すると `-` になる）
        self.assertNotRegex(r.stdout, r"\+0\s+-\s", "cr/体 を欠測扱いにしている")

    def test_a_mismatched_run_is_excluded_from_the_split_denominator(self):
        """`agents` の申告が壊れた回は違反判定の分母から外す（集計行の対称性）."""
        self.write_transcript([[60], [300]], ends={0: 180, 1: 420}, base=self.BASE)
        p = self.payload(agents={"explorer": 1, "reviewer": 9})
        r = self.backfill(self.write_events(p))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("一致 0 / 不一致 1", r.stdout)
        self.assertIn("0 / 0 件", r.stdout, "判定対象外の回を分母に入れている")

    def test_logs_needs_a_value(self):
        """`--logs` も値落ちを黙殺しない（`--projects` と対称に表明する）."""
        r = self.run_script(BACKFILL, "--logs", env=self.env_home())
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_the_default_discovery_finds_the_repo_log(self):
        """**`--logs` 省略時の既定経路**（`review_event_logs`）が効く.

        テストが全部 `--logs` を渡していたため、既定経路の分岐が丸ごと未検証だった。
        利用者が最初に打つのは引数なしの形。
        """
        self.write_transcript([[60], [300]], ends={0: 180, 1: 420}, base=self.BASE)
        log = self.root / ".claude" / "events.jsonl"
        log.parent.mkdir(exist_ok=True)
        log.write_text(json.dumps({"ts": self.TS, "plugin": "code-review:self-review",
                                   "event": "review:completed", "payload": self.payload()}) + "\n",
                       encoding="utf-8")
        r = self.run_script(BACKFILL, "--json", env=self.env_home())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(json.loads(r.stdout)["backfilled"]), 1,
                         "既定の探索でリポジトリのログを見つけられていない")

    def test_no_log_at_all_exits_zero_with_a_message(self):
        """ログが 1 つも無い環境では **exit 0 + 説明**（異常終了にしない）."""
        r = self.run_script(BACKFILL, env=self.env_home())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("イベントログが無い", r.stderr)

    def test_agent_start_uses_the_first_timestamp(self):
        """agent の**起動時刻は先頭行**（末尾行ではない）.

        末尾を採ると窓の判定が「終了時刻」で行われ、**窓内で起動した回が丸ごと
        transcript 無しに化ける**。
        """
        # 終了行だけを窓（t2）の外へ置く。先頭行を見ていれば窓内に入る
        self.write_transcript([[60]], ends={0: 4000}, base=self.BASE)
        r = self.backfill(self.write_events(self.payload(agents={"explorer": 1})), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(json.loads(r.stdout)["backfilled"]), 1,
                         "終了時刻で窓を判定している")

    def test_rows_are_ordered_by_timestamp(self):
        """出力は ts 昇順（ログの並び順に依存しない）."""
        self.write_transcript([[60], [300]], ends={0: 180, 1: 420}, base=self.BASE)
        log = self.root / "events.jsonl"
        # **2 件とも同じ窓を張る**（`duration_min` を伸ばして t0 を揃える）。片方が窓外だと
        # 行が 1 本しか出ず、並び順の表明が**空振りする**（実際に一度そう書いて生存させた）
        later = ({"ts": "2026-08-18T02:30:00Z"}, self.payload(duration_min=90))
        first = ({"ts": self.TS}, self.payload())
        log.write_text("".join(
            json.dumps({"ts": h["ts"], "plugin": "code-review:self-review",
                        "event": "review:completed", "payload": pl}) + "\n"
            for h, pl in (later, first)), encoding="utf-8")
        rows = json.loads(self.backfill(log, "--json").stdout)["backfilled"]
        self.assertEqual(len(rows), 2, "前提: 2 件とも窓を作れている")
        self.assertEqual([r["ts"] for r in rows], sorted(r["ts"] for r in rows),
                         "ログの並び順をそのまま出している")

    def test_dedup_is_independent_of_key_order(self):
        """同一イベントの重複排除は **payload のキー順に依存しない**.

        複数ログを合算すると同じイベントが別の書き出し順で入りうる。キー順で
        別物と見なすと**母数が水増しされる**（実測で ad-hoc 集計が n を倍にした）。
        """
        self.write_transcript([[60], [300]], ends={0: 180, 1: 420}, base=self.BASE)
        a = {"pr": "local", "effort": "high", "size_tier": "medium",
             "duration_min": 60, "duration_triage_min": 1, "duration_fleet_min": 50,
             "agents": {"explorer": 1, "reviewer": 1},
             "recall_skeptic": {"fired": False}, "meta_reviewer": {"fired": False}}
        b = {k: a[k] for k in reversed(list(a))}
        log = self.root / "events.jsonl"
        log.write_text("".join(
            json.dumps({"ts": self.TS, "plugin": "code-review:self-review",
                        "event": "review:completed", "payload": p}) + "\n" for p in (a, b)),
            encoding="utf-8")
        out = json.loads(self.backfill(log, "--json").stdout)
        self.assertEqual(out["candidates"], 1, "キー順違いを別イベントとして数えている")

    def test_the_window_includes_its_boundaries(self):
        """窓は**閉区間**（`t0` / `t2` ちょうどに起動した agent を落とさない）.

        **両端を別々に表明する** — 片側だけだともう片方の境界変異が生き残る。
        """
        # payload の 60 分 = triage 1 + fleet 50 → t0 は BASE / t2 は t0 + 3060 秒
        for off in (0, 3060):
            with self.subTest(offset=off):
                self.setUp()
                self.write_transcript([[off]], ends={0: off + 40}, base=self.BASE)
                r = self.backfill(self.write_events(self.payload(agents={"explorer": 1})), "--json")
                self.assertEqual(len(json.loads(r.stdout)["backfilled"]), 1,
                                 "境界の agent を落としている")

    def test_the_near_window_guard_includes_its_boundary(self):
        """別レビュー混入の判定帯も**閉区間**（境界ちょうどの agent を「遠い」に倒さない）."""
        # 窓内 1 体 + 窓の 6 時間ちょうど手前に 1 体
        self.write_transcript([[-6 * 3600], [60]], ends={0: -6 * 3600 + 40, 1: 180},
                              base=self.BASE)
        r = self.backfill(self.write_events(self.payload()), "--json")
        out = json.loads(r.stdout)
        self.assertEqual(out["backfilled"], [], "境界の agent を混入と見なしていない")

    def test_a_window_swallowing_another_review_is_excluded(self):
        """wave 間ギャップが時間単位の回は窓が別レビューを内包している（除外）.

        レビュー中の wave 間隔ではありえない値。この経路が死ぬと、**別レビューの
        agent を含んだ行がそのまま集計に入る**（実測で 27 時間の回を踏んだ）。
        """
        self.write_transcript([[60], [9000]], ends={0: 180, 1: 9100}, base=self.BASE)
        # 窓が両方の agent を含むように張る（t0 = BASE / t2 = t0 + 191 分）
        log = self.write_events(self.payload(duration_min=200, duration_fleet_min=190),
                                ts="2026-08-18T04:20:00Z")
        r = self.backfill(log, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["backfilled"], [])
        self.assertTrue(any("内包" in k for k in out["skipped"]), out["skipped"])

    def test_expected_waves_drop_when_no_explorer_ran(self):
        """explorer 0 体なら見込みを 1 つ減らす（publish 側と同じ境界）."""
        self.write_transcript([[60], [300]], ends={0: 180, 1: 420}, base=self.BASE)
        r = self.backfill(self.write_events(self.payload(agents={"reviewer": 2})), "--json")
        rows = json.loads(r.stdout)["backfilled"]
        self.assertEqual(rows[0]["waves_expected"], 1, "explorer 0 体で 1 wave 多く見込んでいる")

    def test_expected_waves_include_the_meta_batch(self):
        """meta が指摘を足した回は後付け側も 1 本多く見込む（publish と同じ境界 / #166）.

        式は publish が正本でここは複製。**片方だけ直すと静かにずれる**ので、
        境界そのものを両側で表明する。
        """
        self.write_transcript([[60], [300]], ends={0: 180, 1: 420}, base=self.BASE)
        p = self.payload(agents={"explorer": 1, "reviewer": 1},
                         meta_reviewer={"fired": True, "skip_reason": None,
                                        "findings_added": 2})
        rows = json.loads(self.backfill(self.write_events(p), "--json").stdout)["backfilled"]
        self.assertEqual(rows[0]["waves_expected"], 3, "meta の追加反証 wave を見込んでいない")

    def test_expected_waves_ignore_a_meta_that_added_nothing(self):
        """`findings_added` 0 なら増やさない（**見込み過多は検出漏れになる**）."""
        self.write_transcript([[60], [300]], ends={0: 180, 1: 420}, base=self.BASE)
        p = self.payload(agents={"explorer": 1, "reviewer": 1},
                         meta_reviewer={"fired": True, "skip_reason": None,
                                        "findings_added": 0})
        rows = json.loads(self.backfill(self.write_events(p), "--json").stdout)["backfilled"]
        self.assertEqual(rows[0]["waves_expected"], 2)

    def test_the_tail_share_is_reported_when_ends_exist(self):
        """終了時刻が揃った回は末尾 wave の占有率を**実数で**出す.

        `wave_clock` の既定値の潰し方（`or []`）が壊れると、行は出るのに
        中身だけ欠測に化ける。
        """
        self.write_transcript([[60], [300]], ends={0: 180, 1: 420}, base=self.BASE)
        rows = json.loads(self.backfill(self.write_events(self.payload()), "--json").stdout)["backfilled"]
        self.assertIsNotNone(rows[0]["tail_wave_share"], "wave_clock を空に潰している")
        self.assertEqual(rows[0]["tail_wave_n"], 1)

    def test_the_summary_reports_the_tail_and_gap_lines(self):
        """末尾 1 体 wave とギャップ内訳の行が**値つきで**出る（抽出条件の表明）."""
        self.write_transcript([[60], [300]], ends={0: 180, 1: 420}, base=self.BASE)
        out = self.backfill(self.write_events(self.payload())).stdout
        self.assertRegex(out, r"末尾 1 体 wave が fleet span に占める割合の中央値\*\*: [0-9.]+%",
                         "末尾 1 体の抽出条件が壊れている")
        self.assertRegex(out, r"agent 実行の中央値\*\*: [0-9.]+%（n=[1-9]",
                         "ギャップ内訳の抽出条件が壊れている")

    def test_waves_expected_agrees_with_publish(self):
        """**期待 wave 本数の式が publish と後付けで一致する**（複製の乖離を縛る）.

        式の正本は `lib/wave_expect.py`（publish / backfill / retro が共有）。後付け側も同じ関数を呼ぶので、
        **意味から再構成すると静かにずれる**（実装中に `declared` を deny-list で書き直して
        偽の食い違いを出した）。publish が書いたイベントをそのまま後付けに読ませ、
        両者が同じ値を出すことを表明する。

        **1 形状だけでは乖離を捕まえられない**（実測）: skeptic 項（#172）を publish にだけ
        入れて後付けを直し忘れたとき、`recall_skeptic.fired=False` の単一 fixture では
        両者が同じ値を出して**素通りした**。式に項が増えるたび、**その項が効く形状と
        効かない形状の両方**を足すこと（片側だけだと項の有無が値に出ない）。

        **形状ごとに `agents-mismatch` が立たないことを確かめる**（セルフレビューで検出）:
        申告と transcript 体数がずれると publish 側も後付け側も判定を抑止するので、
        `wave_split` の比較が**両側 False で空虚に一致**し、ゲートの乖離が素通りする。
        申告合計は `agents` の内訳 + `recall_skeptic` / `meta_reviewer` の `fired` ぶん。
        """
        # (label, agents, extra payload, wave の起動オフセット)
        SK = {"recall_skeptic": {"fired": True, "skip_reason": None,
                                 "attribution_schema": 2, "findings_added": 0}}
        shapes = [
            ("explorer+reviewer", {"explorer": 1, "reviewer": 3, "verify": 0}, {},
             [[120], [200], [280, 290]]),
            # skeptic fallback の末尾単独 wave（#172 の控除項が効く形 / 申告 3+1=4 体）
            ("skeptic-tail-solo", {"explorer": 0, "reviewer": 3, "verify": 0}, SK,
             [[120, 130, 140], [280]]),
            # 末尾が単独でない = 控除しない形（同じ項の裏側 / 申告 3+1=4 体）
            ("skeptic-tail-batch", {"explorer": 0, "reviewer": 3, "verify": 0}, SK,
             [[120, 130], [280, 290]]),
            # **末尾は単独だが他にも単独 wave がある** = 控除しない形（#172 のセルフレビュー修正）
            ("skeptic-tail-solo-but-not-unique", {"explorer": 0, "reviewer": 3, "verify": 0}, SK,
             [[120], [200, 210], [280]]),
            # meta が指摘を足した回（#166 の項が効く形）
            ("meta-added", {"explorer": 0, "reviewer": 3, "verify": 0},
             {"meta_reviewer": {"fired": True, "skip_reason": None, "findings_added": 2}},
             [[120, 130, 140], [280]]),
            # **verify 項が効く形**（この形状が無かったため、backfill から verify 項を
            # 削っても本テストが緑のままだった / セルフレビューで実測）
            ("verify", {"explorer": 0, "reviewer": 3, "verify": 2}, {},
             [[120, 130, 140], [280, 290]]),
            # **round2 項（+2）が効く形**（同上）
            ("round2", {"explorer": 0, "reviewer": 3, "verify": 0, "round2": 2}, {},
             [[120, 130, 140], [280, 290]]),
        ]
        for label, agents, extra, waves in shapes:
            with self.subTest(shape=label):
                self.setUp()  # 形状ごとにリポジトリと計測ファイルを作り直す
                base = (datetime.now(timezone.utc).replace(tzinfo=None)
                        - timedelta(minutes=20))
                # 先頭 agent を t0 から離す（窓は分オーダーで丸まるので、境界に置くと外れる）
                self.write_transcript(waves, base=base)
                t0 = int(base.replace(tzinfo=timezone.utc).timestamp())
                self.timeline(t0=t0, t1=t0 + 60, t2=t0 + 900)
                payload = dict(BASE_PAYLOAD, agents=agents, **extra)
                self.publish(payload, env=self.env_home())
                published = self.last_payload()
                # 立つと publish 側も後付け側も判定を抑止するので、両側 False で
                # 空虚に一致する（ゲートの乖離が素通りする）
                self.assertNotIn("agents-mismatch", published["measurement_gaps"],
                                 "前提: 申告と transcript 体数が揃っている")

                log = self.root / ".claude" / "events.jsonl"
                self.assertTrue(log.is_file(), "前提: publish がイベントを書いている")
                r = self.backfill(log, "--json")
                self.assertEqual(r.returncode, 0, r.stderr)
                rows = json.loads(r.stdout)["backfilled"]
                self.assertEqual(len(rows), 1,
                                 "後付けが窓を作れていない（fixture の時刻がずれた）")
                self.assertEqual(rows[0]["waves_expected"],
                                 published["dispatch"]["waves_expected"],
                                 "期待 wave 本数の式が publish と後付けでずれている")
                self.assertEqual(rows[0]["wave_split"],
                                 "wave-split" in published["measurement_gaps"])

    def test_unreadable_log_is_fatal(self):
        """**明示指定したログが読めなければ止める。** 黙って 0 件に倒すと、タイプミスが
        「サンプルが少ない」に化けて判断そのものを誤らせる（`review-retro.sh` と同じ流儀）."""
        r = self.run_script(BACKFILL, "--logs", str(self.root / "nope.jsonl"),
                            env=self.env_home())
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_backfills_dispatch_from_a_surviving_transcript(self):
        """窓が清潔な回は `dispatch` を後付けする（本スクリプトの存在理由）."""
        self.write_transcript([[60], [300]], ends={0: 180, 1: 420}, base=self.BASE)
        r = self.backfill(self.write_events(self.payload()), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = json.loads(r.stdout)["backfilled"]
        self.assertEqual(len(rows), 1, r.stdout)
        self.assertEqual(rows[0]["dispatch"]["agents"], 2)
        self.assertEqual(rows[0]["dispatch"]["wave_sizes"], [1, 1])

    def test_declared_counts_only_the_publish_allow_list(self):
        """**突合式は `publish-review-event.sh` の `declared` と同一**（allow-list 5 キー）.

        `agents` は SKILL テンプレートを LLM が埋めるので、契約に無いキー（実データに
        `skeptic` の例がある）が混ざる。**deny-list で書くとそれを足してしまい**、
        #154 が検知したい「review 側だけ内訳が足りない」信号と同じ形のノイズを作る。
        実装時に実際に踏んで `-1` の偽の食い違いを出した。
        """
        self.write_transcript([[60], [300]], ends={0: 180, 1: 420}, base=self.BASE)
        p = self.payload(agents={"explorer": 1, "reviewer": 1, "skeptic": 5,
                                 "verify_findings": 9, "explorer_waves": 1})
        rows = json.loads(self.backfill(self.write_events(p), "--json").stdout)["backfilled"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["declared"], 2, "allow-list 外のキーを足している")
        self.assertEqual(rows[0]["agents_diff"], 0)

    def test_agents_outside_the_window_exclude_the_run(self):
        """**窓の外にも同セッションの agent がいる回は使わない。** `measure-tokens.sh` の
        `--since` に上限が無いので、別レビューの agent が `wave_clock` の末尾に入る
        （実測: 1 セッションに 3 レビューが入った回で末尾が翌日の agent になった）."""
        self.write_transcript([[60], [300], [10800]], ends={0: 180, 1: 420, 2: 11000},
                              base=self.BASE)
        r = self.backfill(self.write_events(self.payload()), "--json")
        out = json.loads(r.stdout)
        self.assertEqual(out["backfilled"], [])
        self.assertTrue(any("別レビュー混入" in k for k in out["skipped"]), out["skipped"])

    def test_missing_durations_are_excluded_with_a_reason(self):
        """区間が欠測した回は窓を作れない。**除外は理由つきで数える**（母数を言えないと
        「⚠️ が出たときだけ行動する」契約が成立しない）."""
        r = self.backfill(self.write_events(self.payload(duration_fleet_min=-1)))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("区間欠測で窓を作れない", r.stdout)
        self.assertIn("後付け成立 0 件", r.stdout)

    def test_zero_rows_still_returns_valid_json(self):
        """0 件でも JSON を返す（`review-retro.sh --json` と同じ契約）."""
        r = self.backfill(self.write_events(self.payload(duration_min=-1)), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["backfilled"], [])
        self.assertEqual(out["candidates"], 1)

    def test_zero_rows_does_not_read_as_broken_measurement(self):
        """後付けできないことを「計測が壊れている」と読ませない（原理的に不可能な回がある）."""
        r = self.backfill(self.write_events(self.payload(duration_min=-1)))
        self.assertIn("原理的に後付けできない", r.stdout)


class RetroSilentDeathTest(ScriptTestBase):
    """`review-retro.sh` が **rc 0 のまま黙って死ぬ**経路（GitHub issue #211）.

    **rc を見るテストは構造上いつも緑になる** — retro は `set -uo pipefail` に `-e` が無く
    末尾が無条件 `exit 0` なので、python ブロックが例外で落ちても 0 を返していた。しかも
    top-level の最初の `print` は集計を全部済ませたあとなので、**途中で落ちると stdout が
    丸ごと空**になり「⚠️ が出なかった」が「該当なし」と読まれる。
    ここで見るのは **印字そのもの**（liveness）と、**落ちたときに鳴ること**（FATAL / rc 2）。
    """

    BASE = {"effort": "high", "size_tier": "medium", "measurement_gaps": []}

    def _log(self, rows: list[dict]) -> Path:
        path = self.root / "events.jsonl"
        path.write_text("\n".join(json.dumps(
            {"ts": "2026-08-%02dT00:00:00Z" % (i + 1), "plugin": "code-review:self-review",
             "event": "review:completed", "payload": r}, ensure_ascii=False)
            for i, r in enumerate(rows)) + "\n", encoding="utf-8")
        return path

    def _retro(self, rows: list[dict], *args: str) -> subprocess.CompletedProcess[str]:
        """**rc を assert しない**（上の docstring）。生存の証拠は印字と traceback の不在."""
        r = self.run_script(RETRO, "--logs", str(self._log(rows)), *args)
        self.assertNotIn("Traceback", r.stderr, "python ブロックが例外で死んでいる")
        self.assertTrue(r.stdout.strip(), "stdout が空（rc 0 のまま黙って死んでいる）")
        return r

    def _rows(self, n: int, **extra) -> list[dict]:
        return [dict(self.BASE, **extra) for _ in range(n)]

    def test_an_abandoned_agent_marker_does_not_kill_the_run(self):
        """`agents-abandoned` の marker で落ちない（`gap_denom` が str を返していた）."""
        out = self._retro(self._rows(6, measurement_gaps=["agents-abandoned"])).stdout
        self.assertIn("捨てられた試行がある回 6 件", out)

    def test_a_nested_agent_marker_does_not_kill_the_run(self):
        """`agents-nested` も同じ経路（識別子が違うだけ）."""
        out = self._retro(self._rows(6, measurement_gaps=["agents-nested"])).stdout
        self.assertIn("孫 agent がある回 6 件", out)

    def test_the_decomposition_is_never_called_a_missing_measurement(self):
        """**分解は欠測ではない**ので、欠測の分母にも ⚠️ の枠にも入れない（#211 / #154）.

        入れると ①シグナル文言が「計測マーカー … の**欠測**が」で固定なので呼称が誤りになり
        ②上位 2 件枠を両方占有して**本物の欠測を締め出す**（実測: `pre_adjust_counts.vocab`
        の 30% がシグナル欄から消えた）。ここでは②を直接表明する。
        """
        rows = (self._rows(6, measurement_gaps=["agents-abandoned", "agents-nested"])
                + self._rows(3, measurement_gaps=["payload:pre_adjust_counts.vocab"])
                + self._rows(1))
        r = self._retro(rows, "--json")
        payload = json.loads(r.stdout)
        self.assertEqual(payload["agents_decomposition"],
                         {"abandoned_marker": 6, "nested_marker": 6})
        self.assertNotIn("agents-abandoned", payload["measurement"]["gaps"],
                         "欠測の分母に混ぜている")
        signals = " ".join(payload["signals"])
        self.assertIn("pre_adjust_counts.vocab", signals, "本物の欠測が枠から締め出されている")
        self.assertNotIn("agents-abandoned", signals)

    def test_demoted_types_without_the_verify_layer_does_not_kill_the_run(self):
        """`below_threshold_counts` はあるが `adversarial_verify` が無い payload（#211 経路 B）.

        publish は層オブジェクトの欠落を `payload:<field>` の gap にして**通す**設計なので、
        この形は正規に作られる。`schema_of(None)` の `AttributeError` は
        except（`TypeError` / `ValueError`）をすり抜けていた。
        **行を落として黙って分母を減らさない**ことも併せて表明する。
        """
        rows = self._rows(3, below_threshold_counts={
            "blocker": 0, "critical": 0, "major": 0, "minor": 2,
            "demoted_types": {"base_derived": 1, "misread": 0, "overstated_impact": 0,
                              "miscategorized": 1, "unknown": 0}})
        payload = json.loads(self._retro(rows, "--json").stdout)
        row = payload["demoted_types"]["code-review:self-review"]
        self.assertEqual((row["n"], row["total"]), (3, 6), "層が落ちた回を母数から外している")

    def test_a_crash_inside_the_python_block_is_loud(self):
        """**未捕捉例外を rc 0 に潰さない**（#211 期待動作 4 / クラスごと塞ぐ側）.

        fixture は `dispatch.agents` が str の回（他マシン・旧版のログで起こりうる形）で、
        retro はここで割り算に入り `TypeError` になる。**この経路が将来ガードされたら、
        別の落ちる payload に差し替える** — assertion を消すとガード自体が無検証に戻る。
        """
        rows = self._rows(3, dispatch={"agents": "9", "waves": 3, "wave_sizes": [3, 3, 3],
                                       "schema": 3, "verdict": "batched", "span_sec": 900,
                                       "max_solo_run": 1, "max_inter_wave_sec": 60})
        r = self.run_script(RETRO, "--logs", str(self._log(rows)))
        self.assertEqual(r.returncode, 2, "異常終了を rc 0 に潰している")
        self.assertIn("FATAL", r.stderr)
        self.assertTrue(r.stdout.strip(), "部分出力まで捨てている")

    def test_the_fatal_guard_stays_on_the_heredoc_line(self):
        """`||` を改行して `{ }` に展開すると**中身がヒアドキュメント本体に食われる**.

        実際にそれで構文エラーになった（`bash -n` が捕捉）。同じ物理行に置く制約を固定する。
        """
        lines = RETRO.read_text(encoding="utf-8").splitlines()
        heredoc = [l for l in lines if "<<'PY'" in l]
        self.assertEqual(len(heredoc), 1, "ヒアドキュメントの開始行が 1 本でない")
        self.assertIn("|| retro_fatal", heredoc[0], "ガードが同じ行から外れている")
        self.assertTrue(any(l.startswith("retro_fatal()") for l in lines),
                        "retro_fatal が定義されていない")


class MisplacedAndVocabGapTest(ScriptTestBase):
    """payload の**置き場所**と**語彙**の検証（GitHub issue #208）.

    どちらも「記述漏れ」とは是正先が違うので別識別子で立てる。**fail-fast にしない**
    （止めるとその回の計測が丸ごと消える / `pre_adjust_counts` と同じ判断）。
    """

    def _payload(self, **extra) -> dict:
        p = {k: (dict(v) if isinstance(v, dict) else v) for k, v in BASE_PAYLOAD.items()}
        p.update(extra)
        return p

    TYPES = {"base_derived": 1, "misread": 0, "overstated_impact": 0,
             "miscategorized": 0, "unknown": 0}

    def test_a_misplaced_demoted_types_is_not_called_a_missing_record(self):
        """トップレベル誤置は `.misplaced`。**不在 gap は立てない**（排他）.

        排他にしないと、欠測内訳の最多項目が是正先の違う 2 系統に割れて読めなくなる
        （#208 が観測した当の症状）。
        """
        self.publish(self._payload(
            demoted_types=dict(self.TYPES),
            below_threshold_counts={"blocker": 0, "critical": 0, "major": 1, "minor": 0}))
        gaps = self.last_payload()["measurement_gaps"]
        self.assertIn("payload:demoted_types.misplaced", gaps)
        self.assertNotIn("payload:below_threshold_counts.demoted_types", gaps,
                         "誤置と不在の両方を立てている（是正先が 2 系統に割れる）")

    def test_a_misplaced_inflated_axes_is_detected_too(self):
        """同型の穴を一巡する（#208 の期待動作 3）— `inflated_axes` 側も塞ぐ."""
        self.publish(self._payload(
            inflated_axes=dict(self.TYPES),
            adversarial_verify={"fired": True, "skip_reason": None, "severity_inflated": 1}))
        gaps = self.last_payload()["measurement_gaps"]
        self.assertIn("payload:inflated_axes.misplaced", gaps)
        self.assertNotIn("payload:adversarial_verify.inflated_axes", gaps)

    def test_a_genuinely_missing_breakdown_is_still_recorded(self):
        """誤置の排他を足しても、**本当に不在の回の gap は残る**（#150 の記録漏れ検知）.

        排他条件の付け方を誤ると「内訳が要る回なのに記録が無い」が丸ごと鳴らなくなる。
        """
        self.publish(self._payload(
            adversarial_verify={"fired": True, "skip_reason": None, "severity_inflated": 1}))
        self.assertIn("payload:adversarial_verify.inflated_axes",
                      self.last_payload()["measurement_gaps"])

    def test_the_warning_names_the_parent_the_value_belongs_in(self):
        """**是正先を名指しする**（#208 の目的そのもの）— 親を取り違えると誘導が逆になる."""
        res = self.publish(self._payload(inflated_axes=dict(self.TYPES)))
        self.assertIn("adversarial_verify", res.stderr)
        self.assertNotIn("below_threshold_counts の中", res.stderr, "親を取り違えている")

    def test_the_misplaced_value_is_not_moved_into_place(self):
        """**値は救わない**。publish が直すと埋める側は誤りに気づかず誤置を続ける.

        `missing_coverage` の「黙って正規化はしない」に揃えた判断。
        """
        self.publish(self._payload(demoted_types=dict(self.TYPES)))
        p = self.last_payload()
        self.assertIn("demoted_types", p, "トップレベルの値を消している")
        self.assertNotIn("demoted_types", p["below_threshold_counts"], "黙って移送している")

    def test_a_correctly_nested_payload_raises_neither_gap(self):
        """正しくネストした回では両方とも立たない（偽陽性の契約表明）."""
        self.publish(self._payload(
            below_threshold_counts={"blocker": 0, "critical": 0, "major": 1, "minor": 0,
                                    "demoted_types": dict(self.TYPES)}))
        gaps = self.last_payload()["measurement_gaps"]
        self.assertNotIn("payload:demoted_types.misplaced", gaps)
        self.assertNotIn("payload:below_threshold_counts.demoted_types", gaps)

    def test_the_contract_vocabulary_has_seven_keys_not_five(self):
        """**体数 5 キーを語彙 allow-list に流用しない**（#208 の最大の落とし穴）.

        `explorer_waves` は publish 自身が注入し、`verify_findings` は件数として契約内。
        5 キーで判定すると**将来のすべての publish が偽陽性**になる（実測: ローカルの
        判定対象 15 件すべてが 5 キー外を持ち 100%。7 キー契約なら 2 件）。
        """
        self.publish(self._payload(
            agents={"explorer": 2, "reviewer": 5, "verify": 1, "verify_findings": 7}))
        gaps = self.last_payload()["measurement_gaps"]
        self.assertNotIn("payload:agents.vocab", gaps,
                         "契約内のキー（verify_findings / explorer_waves）で発火している")

    def test_an_out_of_contract_agent_key_is_named_a_vocabulary_violation(self):
        """契約外のキーは黙って 0 として集計される（`agents` は全分母の分母）."""
        res = self.publish(self._payload(
            agents={"explorer": 2, "reviewer": 5, "skeptic": 1, "meta": 1}))
        self.assertIn("payload:agents.vocab", self.last_payload()["measurement_gaps"])
        self.assertIn("skeptic", res.stderr, "どのキーが契約外かを言っていない")

    def test_no_count_key_at_all_is_recorded_rather_than_silently_dropped(self):
        """体数キーが 1 つも無い回。集計側は落とすが、**落ちた事実**を残す（#208）."""
        self.publish(self._payload(agents={}))
        self.assertIn("payload:agents.empty", self.last_payload()["measurement_gaps"])

    def test_a_normal_payload_raises_no_agents_gap(self):
        """既定の payload では `agents` 系の gap が 1 つも立たない（偽陽性の契約表明）."""
        self.publish()
        gaps = self.last_payload()["measurement_gaps"]
        self.assertNotIn("payload:agents.vocab", gaps)
        self.assertNotIn("payload:agents.empty", gaps)


class FleetSpanGuardTest(TranscriptFixture):
    """fleet 区間が agent の起動スパンを覆えていない回（GitHub issue #207）.

    `dispatch.span_sec` は transcript 由来の実測なので自己申告ではない。覆えていない回は
    t1 か t2 の打点が区間の外にあり、**汚染は欠測ではなく「もっともらしい小さい値」**
    として入る（`## 13.1`）ので、0 のまま中央値と相関の分母に混ざる。
    """

    def _marks(self, t0: int, t1: int, t2: int) -> None:
        self.ts_file().write_text("t0 %d\nt1 %d\nw %d\nt2 %d\n" % (t0, t1, t1 + 1, t2),
                                  encoding="utf-8")

    def _run(self, fleet_sec: int, span_sec: int, t2_ago: int = 60) -> dict:
        now = int(time.time())
        t2 = now - t2_ago
        t1 = t2 - fleet_sec
        t0 = t1 - 600
        base = datetime.fromtimestamp(t0 + 10, tz=timezone.utc).replace(tzinfo=None)
        self.write_transcript([[0], [span_sec]], base=base)
        self._marks(t0, t1, t2)
        self.publish(env=self.env_home())
        return self.last_payload()

    def test_a_contradicting_fleet_is_dropped_to_missing(self):
        """0 を実値として載せない。**警告だけでは分母から外れない**."""
        p = self._run(fleet_sec=10, span_sec=2457)
        self.assertEqual(p["tokens"]["window"], "since-t0", "前提: 判定対象の窓")
        self.assertEqual(p["duration_fleet_min"], -1, "0 が実値として残っている")
        self.assertIn("fleet-span-mismatch", p["measurement_gaps"])

    def test_a_consistent_fleet_keeps_its_value(self):
        """正常な回は倒さない（偽陽性は「⚠️ が出たときだけ行動する」契約を壊す）."""
        p = self._run(fleet_sec=3600, span_sec=2457)
        self.assertEqual(p["duration_fleet_min"], 60)
        self.assertNotIn("fleet-span-mismatch", p["measurement_gaps"])

    def test_the_rounding_margin_is_one_minute(self):
        """区間の分は秒を 60 で割って切り捨てるので、真に等しい回でも最大 59 秒はみ出す.

        丸めぶんの余裕を取らないと、**打点が正しい回を欠測に倒す**。
        """
        p = self._run(fleet_sec=2400, span_sec=2459)          # 40 分ちょうど + 59 秒
        self.assertEqual(p["duration_fleet_min"], 40, "余裕の内側で倒している")
        self.assertNotIn("fleet-span-mismatch", p["measurement_gaps"])

    def test_one_second_past_the_margin_fires(self):
        """境界の外側は倒す（`+ 1` を削る変異・比較の向きを反転する変異を殺す）."""
        p = self._run(fleet_sec=2400, span_sec=2460)
        self.assertEqual(p["duration_fleet_min"], -1)
        self.assertIn("fleet-span-mismatch", p["measurement_gaps"])

    def test_a_late_publish_window_is_not_judged(self):
        """`since-t0-late` は締めのあとに起動した agent が窓へ入るので判定しない."""
        p = self._run(fleet_sec=10, span_sec=2457, t2_ago=1800)
        self.assertIn("late-publish", p["measurement_gaps"], "前提: 遅延 publish")
        self.assertNotIn("fleet-span-mismatch", p["measurement_gaps"],
                         "窓のゲートが効いていない")


class RetroFleetSpanTest(RetroFixture):
    """矛盾した回を中央値・相関の分母から外す（GitHub issue #207 の期待動作 4）.

    **既に publish 済みの回にも効かせる** — publish 側のガードはこれから publish する回に
    しか掛からないが、汚染された値はもう集計に入っている（#199 と同じ理由）。
    """

    def _row(self, fleet: int, span: int, agents: int = 8, window: str = "since-t0",
             gaps: list | None = None) -> dict:
        return {"effort": "high", "size_tier": "medium",
                "measurement_gaps": [] if gaps is None else gaps,
                "duration_fleet_min": fleet,
                "agents": {"explorer": 2, "reviewer": agents - 2},
                "tokens": {"schema": 2, "window": window, "main_output_k": 10.0,
                           "sub_output_k": 20.0, "sub_cache_read_k": 30.0, "sub_agents": agents},
                "dispatch": {"agents": agents, "waves": 2, "wave_sizes": [2, agents - 2],
                             "schema": 4, "verdict": "batched", "span_sec": span,
                             "max_solo_run": 1, "max_inter_wave_sec": 60}}

    def _json(self) -> dict:
        r = self.run_script(RETRO, env=self._env())
        self.assertNotIn("Traceback", r.stderr, "retro が例外で死んでいる")
        return json.loads(self.run_script(RETRO, "--json", env=self._env()).stdout)

    def test_a_contradicting_row_is_kept_in_the_denominator_of_the_gap(self):
        """**倒したあとの回も判定母数に残す** — 外すと分子だけ消えて欠測率が常に 0 になる."""
        self._events([self._row(-1, 2457, gaps=["fleet-span-mismatch"]),
                      self._row(46, 1902)])
        self.assertEqual(self._json()["fleet_span"]["judged"], 2,
                         "倒した回が分母から抜けている（自己参照で欠測率が 0 になる）")

    def test_an_already_published_contradiction_is_excluded_from_the_medians(self):
        """publish 前に焼かれた 0 も集計から外す（ガードだけでは既存データが直らない）."""
        self._events([self._row(0, 2457), self._row(40, 2400), self._row(42, 2400)])
        j = self._json()
        self.assertEqual(j["fleet_span"]["conflict"], 1, "矛盾を検出できていない")
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("判定できた 3 件中 1 件", out, "分母と矛盾件数を出していない")

    def test_a_session_window_is_never_judged(self):
        """窓が `session` の回は起点に下限が無いので突合できない（判定対象にしない）."""
        self._events([self._row(0, 2457, window="session") for _ in range(3)])
        self.assertEqual(self._json()["fleet_span"], {"judged": 0, "conflict": 0})

    def test_a_dropped_row_without_the_marker_is_not_judgeable(self):
        """欠測（-1）でマーカーも無い回は**判定できていない**（判定して問題無しではない）.

        ここを緩めると、別の理由で欠測に倒れた回（late-publish 等）が分母に入り、
        欠測率が実際より低く出る。`and` を `or` に緩める変異 2 つを殺す。
        """
        self._events([self._row(-1, 2457, gaps=[]),
                      self._row(-1, 2457, gaps=["late-publish"])])
        self.assertEqual(self._json()["fleet_span"], {"judged": 0, "conflict": 0})

    def test_a_row_without_dispatch_is_not_judgeable(self):
        """突合の材料（`dispatch`）が無い回は判定対象にしない."""
        rows = []
        for _ in range(3):
            r = self._row(0, 2457)
            del r["dispatch"]
            rows.append(r)
        self._events(rows)
        self.assertEqual(self._json()["fleet_span"]["judged"], 0)

    def test_a_zero_span_is_not_judgeable(self):
        """`span_sec` が 0 の回（agent 1 体 = `verdict: single`）は突合できない.

        幅が 0 なら「区間が覆えていない」は原理的に成立しない。境界を 1 つ狭める変異を殺す。
        """
        self._events([self._row(0, 0) for _ in range(3)])
        self.assertEqual(self._json()["fleet_span"], {"judged": 0, "conflict": 0})

    def test_a_non_integer_span_does_not_kill_the_run(self):
        """`--logs` は他マシン・他版のログも読むので型の保証が無い（#211 と同型）.

        ガードが緩むと `span_sec` の比較で `TypeError` になり、**retro が rc 0 のまま
        出力ごと消える**。判定を諦めて集計は続ける。
        """
        self._events([self._row(0, 0) | {"dispatch": dict(self._row(0, 0)["dispatch"],
                                                          span_sec="2457")}
                      for _ in range(3)])
        r = self.run_script(RETRO, env=self._env())
        self.assertNotIn("Traceback", r.stderr, "型判定が緩んで retro が死んでいる")
        self.assertTrue(r.stdout.strip(), "stdout が空（沈黙死）")
        self.assertEqual(self._json()["fleet_span"]["judged"], 0)

    def test_an_already_dropped_row_is_not_counted_as_a_conflict(self):
        """倒し済みの回を矛盾として二重に数えない（`measured` が既に外している）.

        数えると「publish 後も矛盾が残っている」と読まれ、ガードが効いていないように見える。
        """
        self._events([self._row(-1, 2457, gaps=["fleet-span-mismatch"]),
                      self._row(46, 1902)])
        self.assertEqual(self._json()["fleet_span"]["conflict"], 0,
                         "倒し済みの回を矛盾として再計上している")

    def test_the_conflict_boundary_is_inclusive(self):
        """スパンが余裕ちょうどに等しい回は矛盾（`>=` を `>` に狭める変異を殺す）.

        publish 側の境界（`FleetSpanGuardTest`）と同じ式を集計側でも持つので、
        片方だけ緩むと publish 済みデータと再計算がずれる。
        """
        self._events([self._row(40, 2460), self._row(40, 2459), self._row(40, 2400)])
        self.assertEqual(self._json()["fleet_span"]["conflict"], 1,
                         "境界ちょうどの回を矛盾として数えていない")

    def test_a_zero_minute_fleet_is_still_a_measurement(self):
        """fleet が 0 分の回は**実測**であって欠測ではない（相関の分母に入れる）.

        `fleet >= 0` を `fleet > 0` に狭める変異を殺す。0 を落とすと「速い回」だけが
        構造的に相関から消える。
        """
        self._events([self._row(0, 30), self._row(10, 300), self._row(20, 600)])
        self.assertEqual(self._json()["agents_fleet_n"], 3, "fleet 0 分の回を落としている")

    def test_the_denominator_is_an_integer(self):
        """`gap_denom` は int を返す契約（#211 — str を返すと retro が沈黙死する）."""
        self._events([self._row(-1, 2457, gaps=["fleet-span-mismatch"]) for _ in range(6)])
        out = self.run_script(RETRO, env=self._env()).stdout
        self.assertIn("fleet-span-mismatch", out, "シグナルに出ていない（分母が壊れている）")
        self.assertIn("t2 を全 agent の回収後に", out, "是正先が既定文言に落ちている")


class RetroLayeredSignalTest(RetroFixture):
    """⚠️ の発火判定を世代で層別する（GitHub issue #209）.

    表は #191 で世代別になったが**判定だけ累計のまま**で、母集団の違う層を平均する形が
    残っていた（実測: 反証不発が opus-4-8 で 78% あったのに累計 43% で閾値 50 に届かず、
    9 日 18 レビューの検出崩壊が一度もシグナルに載らなかった）。

    **累計フォールバックを消さない**のがこの実装の核心。既定母集団ではどの層も下限に
    届かないので、層別だけにすると**いま鳴っている行が消えて「該当なし」と読まれる**。
    """

    def _adv(self, gen: str, dry: bool) -> dict:
        """反証層の 1 回。`dry` が真なら `no-eligible-findings` で不発."""
        av = {"gate_schema": 2, "calibration_schema": 3,
              "fired": not dry, "skip_reason": "no-eligible-findings" if dry else None}
        if not dry:
            av.update({"confirmed": 2, "refuted": 0, "uncertain": 0,
                       "severity_inflated": 0, "contested": 0})
        return {"effort": "high", "size_tier": "medium", "measurement_gaps": [],
                "models": self._models("claude-%s" % gen), "adversarial_verify": av}

    def _rows(self, spec: list[tuple[str, int, int]]) -> None:
        """`(世代, 総数, 不発数)` の並びからイベントを作る."""
        rows = []
        for gen, total, dry in spec:
            rows += [self._adv(gen, True) for _ in range(dry)]
            rows += [self._adv(gen, False) for _ in range(total - dry)]
        self._events(rows)

    def _out(self) -> str:
        r = self.run_script(RETRO, env=self._env())
        self.assertNotIn("Traceback", r.stderr, "retro が例外で死んでいる")
        self.assertTrue(r.stdout.strip(), "stdout が空（沈黙死）")
        return r.stdout

    def test_a_broken_layer_fires_even_when_the_total_is_diluted(self):
        """**層別判定の本体**。崩れた層が健全な層に薄められて消えない.

        累計 8/30 = 27% は閾値 50 に届かないが、`opus-4-8` 層は 80% で超えている。
        """
        self._rows([("opus-4-8", 10, 8), ("opus-5", 20, 0)])
        out = self._out()
        self.assertIn("不発だった回が 80%（`opus-4-8` 層", out, "崩れた層が鳴っていない")
        self.assertNotIn("累計で判定", out, "層で鳴ったのに累計へ落ちている")

    def test_every_layer_over_the_threshold_is_reported(self):
        """閾値を超えた層は全部出す（1 層だけ出すと残りが黙って落ちる）."""
        self._rows([("opus-4-8", 10, 9), ("fable-5", 12, 11), ("opus-5", 20, 0)])
        out = self._out()
        self.assertIn("`opus-4-8` 層", out)
        self.assertIn("`fable-5` 層", out)

    def test_the_total_still_fires_when_no_layer_is_judgeable(self):
        """**利用者が決めた方針の核心**。層別で判定できない間は累計で鳴らす.

        ここを落とすと、既定母集団では全層が下限未満なのでシグナルが丸ごと消える。
        """
        self._rows([("opus-4-8", 8, 6), ("opus-5", 4, 3)])
        out = self._out()
        self.assertIn("累計 / 9/12", out, "累計フォールバックが消えている")
        self.assertIn("層別では判定不能", out, "なぜ累計で判定したかを言っていない")
        self.assertIn("最大層 `opus-4-8` の分母 8・下限 10", out)

    def test_the_note_says_below_threshold_when_a_layer_was_judgeable(self):
        """判定できた層があったが閾値に届かなかった回は、注記の理由が変わる.

        「判定不能」と「判定したが閾値未満」は別の状態で、潰すと次に何を待てばよいかが
        読めなくなる。
        """
        self._rows([("opus-5", 10, 4), ("opus-4-8", 2, 2)])
        out = self._out()
        self.assertIn("累計 / 6/12", out)
        self.assertIn("`opus-5` が下限に達したが閾値に届かない", out)

    def test_a_hot_but_small_layer_is_held_rather_than_dropped(self):
        """**判定できる層が健全だと、崩れた少数層が累計にも埋もれる**（反証で検出）.

        `opus-5` は n=10 で健全、`unrecorded` は n=8 で全件不発。累計 8/18 = 44% は
        閾値に届かないので ⚠️ は出ない。**⚠️ に出さないのは正しい**（下限未満は
        「まだ行動しない」という判断）が、黙ると「該当なし」と読まれるので保留として残す。
        """
        self._rows([("opus-5", 10, 0)])
        rows = [self._adv("opus-5", False) for _ in range(10)]
        bare = self._adv("opus-5", True)
        del bare["models"]
        rows += [dict(bare) for _ in range(8)]
        self._events(rows)
        out = self._out()
        self.assertNotIn("既定 high のゲート幅を再検討", out, "下限未満の層で ⚠️ を出している")
        self.assertIn("判定を保留", out, "崩れた層が黙って落ちている")
        self.assertIn("`unrecorded` 層が閾値を超えている（8/8）", out)

    def test_the_hold_floor_is_inclusive(self):
        """保留の下限は「その値を含む」（境界を 1 つ狭める変異を殺す）.

        下限ちょうどの層を落とすと、単発点灯を防ぐつもりで**拾うべき層まで捨てる**。
        """
        self._rows([("opus-5", 10, 0), ("opus-4-8", 5, 5)])
        out = self._out()
        self.assertNotIn("既定 high のゲート幅を再検討", out, "前提: ⚠️ は出ない（累計 33%）")
        self.assertIn("`opus-4-8` 層が閾値を超えている（5/5）", out, "下限ちょうどの層を捨てている")

    def _meta(self, gen: str, fired: bool) -> dict:
        return {"effort": "high", "size_tier": "medium", "measurement_gaps": [],
                "models": self._models("claude-%s" % gen),
                "meta_reviewer": {"gate_schema": 3, "fired": fired,
                                  "skip_reason": None if fired else "effort-band",
                                  "findings_added": 1 if fired else 0}}

    def test_a_layer_that_never_fired_meta_is_reported(self):
        """meta の起動ゼロも層別で判定する（`== 0` を反転する変異を殺す）."""
        self._events([self._meta("opus-4-8", False) for _ in range(8)]
                     + [self._meta("opus-5", True) for _ in range(8)])
        out = self._out()
        self.assertIn("起動対象 8 件（`opus-4-8` 層", out, "起動ゼロの層が鳴っていない")

    def test_a_layer_that_did_fire_meta_is_not_reported_as_dead(self):
        """起動している層を「1 度も起動していない」と言わない（判定の反転を殺す）."""
        self._events([self._meta("opus-5", True) for _ in range(12)])
        self.assertNotIn("1 度も起動していない", self._out())

    def test_a_single_sample_layer_is_not_held(self):
        """保留にも下限を置く（**単発点灯の防止** / `GAP_MIN_N` と同じ流儀）.

        置かないと n=1 の層が毎回並び、「⚠️ が出たときだけ行動する」契約の可読性が落ちる
        （実測: 既定母集団で n=1 の層が 3 本並んだ）。
        """
        self._rows([("opus-5", 10, 0), ("opus-4-8", 2, 2)])
        self.assertNotIn("判定を保留", self._out(), "単発の層を保留に出している")


class RetroMissingReportCountTest(RetroFixture):
    """報告件数の欠測を「報告 0」と読まない（GitHub issue #212）.

    #203 が `pre_adjust_counts` の語彙違反について同じ理由で母集団から外したのと同型。
    そちらのコメントが失敗の形をそのまま書いている（実数が 0 として分子に入り歩留まりを
    下振れさせる）。**縮退先は欠測であって誤値ではない**（`## 13.1`）。

    実害の実例: このリポジトリの唯一の opus-4-8 サンプルが、報告件数フィールドを
    持たないだけで**歩留まり 0.0%** として表に出ていた（#210 の「4.8 で検出が死んでいる」
    という読みを裏付ける形で）。
    """

    def _row(self, pre_major: int, reported: int | None, appendix: bool = False) -> dict:
        r = {"effort": "high", "size_tier": "medium", "measurement_gaps": [],
             "severity_threshold": "MAJOR",
             "pre_adjust_counts": {"schema": 2, "blocker": 0, "critical": 0,
                                   "major": pre_major, "minor": 0}}
        if reported is not None:
            r.update({"blocker_count": 0, "critical_count": 0,
                      "major_count": reported, "minor_count": 0})
        if appendix:
            r["appendix"] = {"schema": 1, "listed": 3, "recommended": 1}
        return r

    def _out(self) -> str:
        r = self.run_script(RETRO, env=self._env())
        self.assertNotIn("Traceback", r.stderr, "retro が例外で死んでいる")
        self.assertTrue(r.stdout.strip(), "stdout が空（沈黙死）")
        return r.stdout

    def test_a_run_without_report_counts_is_not_a_zero_yield(self):
        """**欠測の回を歩留まりの母集団に入れない**（検出したのに全部捨てた回に化ける）."""
        self._events([self._row(9, None), self._row(10, 5)])
        out = self._out()
        self.assertNotIn("検出 9 → 報告 0", out, "欠測の回が 0% の行を作っている")
        self.assertIn("1 件は報告件数を 1 つも申告しておらず母集団から外した", out,
                      "除外した事実を残していない")
        # **判定できた行があるなら「判定対象なし」を出さない**。両方出ると、
        # 除外の通知が「歩留まりを測れていない」という別の意味に読まれる
        self.assertNotIn("歩留まり**: 判定対象なし", out,
                         "行があるのに判定対象なしを併記している")

    def test_a_genuinely_zero_report_is_still_counted(self):
        """**本当に 0 件の回は従来どおり数える**（非退行の表明）.

        ここを一緒に落とすと、recall が落ちた回まで母集団から消えて
        「歩留まりは健全」に見える — 直そうとしている誤読の裏返しになる。
        """
        self._events([self._row(9, 0), self._row(10, 5)])
        out = self._out()
        self.assertIn("検出 19 → 報告 5", out, "本当に 0 件の回まで外している")
        self.assertNotIn("報告件数を 1 つも申告しておらず", out)

    def _row_bt(self, pre_major: int, below_major: int, reported: int | None) -> dict:
        r = self._row(pre_major, reported)
        r["below_threshold_counts"] = {"blocker": 0, "critical": 0, "major": below_major,
                                       "minor": 0}
        return r

    def test_a_missing_count_is_not_a_written_then_dropped_finding(self):
        """内訳（#146）でも欠測を「本文を書いてから捨てた」に数えない（#213 / 3 箇所目）.

        `or 0` で `post` が 0 に化けると `written − post` が全部 `dropped` になり、
        申告していないだけの回が 100% の行を作る（実測: mixed 世代の 1 行）。
        """
        self._events([self._row_bt(7, 6, None), self._row_bt(10, 4, 5)])
        out = self._out()
        self.assertNotIn("本文を書いてから捨てた: 1 件（100.0%）", out, "欠測が dropped に入っている")
        self.assertIn("本文を書いてから捨てた: 1 件（16.7%）", out, "本当の値が出ていない")
        self.assertIn("1 件は報告件数を 1 つも申告しておらず母集団から外した", out)

    def test_yield_and_breakdown_share_the_same_n_per_layer(self):
        """**隣り合う 2 表の同一層の n を揃える**（#191 のセルフレビュー指摘 / #213 の発見経緯）.

        欠測ゲートが片方にしか無いと、同一層で n=21 と n=23 のように割れる。
        """
        self._events([self._row_bt(7, 6, None), self._row_bt(10, 4, 5), self._row_bt(3, 1, 2)])
        out = self._out()
        y = re.search(r"schema>=2/threshold=MAJOR: n=(\d+) / 検出", out)
        b = re.search(r"schema>=2/threshold=MAJOR: n=(\d+) / 本文を書いた", out)
        self.assertTrue(y and b, "両表の行が出ていない")
        self.assertEqual(y.group(1), b.group(1), "歩留まりと内訳で同一層の n が割れている")

    def test_the_breakdown_notice_survives_total_exclusion(self):
        """全件除外で 0 行になっても通知は出す（#212 が踏んだ穴を繰り返さない）."""
        self._events([self._row_bt(7, 6, None), self._row_bt(5, 5, None)])
        out = self._out()
        self.assertIn("検出 → 報告の内訳**: 判定対象なし（**2 件は報告件数を", out)

    def test_a_missing_count_is_not_counted_as_a_silent_run(self):
        """付録側も同じ（`apx_silent` は #210 の看板の数字の分子）."""
        self._events([self._row(9, None, appendix=True) for _ in range(2)])
        out = self._out()
        self.assertIn("報告件数を 1 つも申告しておらず母集団から外した", out)
        self.assertNotIn("報告 0 件の回 2 件", out, "欠測を空振りに数えている")

    def test_a_genuinely_silent_run_with_an_appendix_is_still_counted(self):
        """付録側でも本当に 0 件の回は数える（#168 の「付録に救われた回」の判定）."""
        self._events([self._row(9, 0, appendix=True) for _ in range(2)])
        out = self._out()
        self.assertIn("報告 0 件の回 2 件のうち 2 件は推奨あり", out)


class ReportCountContractTest(ScriptTestBase):
    """報告件数 4 フィールドの契約（GitHub issue #215）.

    `below_threshold_counts` / `appendix` / `findings_class` は fail-fast で検証しているのに、
    **全指標の分子であるこの 4 つだけ検証が無かった**。#203 と同じく fail-fast にはしない
    （止めるとその回の計測が丸ごと消える）。
    """

    def _payload(self, **counts) -> dict:
        p = {k: (dict(v) if isinstance(v, dict) else v) for k, v in BASE_PAYLOAD.items()}
        for k in ("blocker_count", "critical_count", "major_count", "minor_count"):
            p.pop(k, None)
        p.update(counts)
        # `findings_class` の合計は報告件数と一致させる契約（不一致は fail-fast）。
        # ここで測りたいのは欠測の検出なので、突合の方は常に整合させておく
        total = sum(v for v in counts.values() if isinstance(v, int) and not isinstance(v, bool))
        p["findings_class"] = {"lint": 0, "test": 0, "judgement": total}
        return p

    def test_a_missing_count_raises_a_gap_not_a_fatal(self):
        """欠測は gap + WARN。publish は止めない."""
        res = self.publish(self._payload(blocker_count=0, critical_count=0, major_count=1))
        self.assertEqual(res.returncode, 0, "欠測で publish を止めている")
        self.assertIn("payload:report_counts.missing", self.last_payload()["measurement_gaps"])
        self.assertIn("minor_count", res.stderr, "どのフィールドが欠けたかを言っていない")

    def test_zero_is_not_missing(self):
        """**0 件は欠測ではない**（4 つとも 0 の回は正当）."""
        self.publish(self._payload(blocker_count=0, critical_count=0, major_count=0,
                                   minor_count=0))
        self.assertNotIn("payload:report_counts.missing", self.last_payload()["measurement_gaps"])

    def test_a_complete_payload_raises_no_gap(self):
        self.publish(self._payload(blocker_count=0, critical_count=1, major_count=2,
                                   minor_count=3))
        self.assertNotIn("payload:report_counts.missing", self.last_payload()["measurement_gaps"])

    def test_a_boolean_is_not_a_count(self):
        """`true` は件数ではない（JSON の bool を int と読まない）."""
        self.publish(self._payload(blocker_count=0, critical_count=0, major_count=True,
                                   minor_count=0))
        self.assertIn("payload:report_counts.missing", self.last_payload()["measurement_gaps"])


class RetroMissingCountAttributionTest(RetroFixture):
    """除外した欠測を「旧版」と「現行版の埋め落とし」に分けて出す（#215）.

    除外は正しいが説明が誤っていた（全部「旧版の payload」）。現行版の埋め落としは
    **サンプルの損失**で、増えるなら SKILL 側を直す根拠になる。
    """

    def _row(self, gaps: list) -> dict:
        return {"effort": "high", "size_tier": "medium", "measurement_gaps": gaps,
                "severity_threshold": "MAJOR",
                "pre_adjust_counts": {"schema": 2, "blocker": 0, "critical": 0,
                                      "major": 3, "minor": 0}}

    def _out(self) -> str:
        r = self.run_script(RETRO, env=self._env())
        self.assertNotIn("Traceback", r.stderr)
        self.assertTrue(r.stdout.strip())
        return r.stdout

    def test_current_version_omissions_are_named_separately(self):
        self._events([self._row([]), self._row(["payload:report_counts.missing"]),
                      self._row(["payload:report_counts.missing"])])
        out = self._out()
        self.assertIn("3 件は母数から外した", out)
        self.assertIn("うち 2 件は現行版の埋め落とし", out, "旧版と現行版を分けていない")

    def test_the_table_and_the_empty_notice_are_exclusive(self):
        """判定できた行があるなら「判定対象なし」を併記しない（`and` を `or` に緩める変異を殺す）.

        両方出ると、除外の注記が「報告 0 件率を測れていない」という別の意味に読まれる。
        """
        with_counts = dict(self._row([]), blocker_count=0, critical_count=0,
                           major_count=1, minor_count=0)
        self._events([with_counts, self._row(["payload:report_counts.missing"])])
        out = self._out()
        self.assertIn("| 世代 | n | 報告 0 件 |", out, "前提: 表が出ている")
        self.assertIn("1 件は母数から外した", out)
        self.assertNotIn("報告 0 件率**: 判定対象なし", out, "行があるのに判定対象なしを併記している")

    def test_legacy_only_exclusions_do_not_claim_a_loss(self):
        """gap を持たない旧版だけなら「埋め落とし」とは言わない."""
        self._events([self._row([]), self._row([])])
        out = self._out()
        self.assertIn("2 件は母数から外した", out)
        self.assertNotIn("現行版の埋め落とし", out)

    def test_the_gap_names_its_own_fix(self):
        """`gap_hint` が既定の「テンプレートの記述漏れ」ではなく 4 つ必須の是正先を返す."""
        self._events([self._row(["payload:report_counts.missing"]) for _ in range(6)])
        out = self._out()
        self.assertIn("payload:report_counts.missing", out)
        self.assertIn("4 つとも必須で 0 件でも省かない", out, "是正先が既定文言に落ちている")


class RetroAppendixLayerTest(RetroFixture):
    """付録（真の空振り）を世代で層別し ⚠️ に載せる（GitHub issue #214）.

    #210 の判定基準「preMAJ 中央値 1 以上 かつ 真の空振り率 20% 未満」のうち、後者だけが
    機械化されていなかった（表にも出ず、読み手が引き算していた）。#209 の趣旨どおり、
    表に出ていても鳴らなければ行動につながらない。
    """

    def _row(self, gen: str, reported: int, recommended: int) -> dict:
        return {"effort": "high", "size_tier": "medium", "measurement_gaps": [],
                "models": self._models("claude-%s" % gen),
                "blocker_count": 0, "critical_count": 0, "major_count": reported, "minor_count": 0,
                "appendix": {"schema": 1, "listed": 3, "recommended": recommended}}

    def _out(self) -> str:
        r = self.run_script(RETRO, env=self._env())
        self.assertNotIn("Traceback", r.stderr, "retro が例外で死んでいる")
        self.assertTrue(r.stdout.strip(), "stdout が空（沈黙死）")
        return r.stdout

    def test_a_hot_layer_fires_with_its_name(self):
        """閾値超えの層が層名つきで鳴る（opus-4-8 10 件中 5 件が真の空振り = 50%）."""
        rows = [self._row("opus-4-8", 0, 0) for _ in range(5)] \
             + [self._row("opus-4-8", 1, 0) for _ in range(5)] \
             + [self._row("opus-5", 1, 0) for _ in range(12)]
        self._events(rows)
        out = self._out()
        self.assertIn("真の空振り率（報告 0 件かつ付録推奨 0）が 50%（`opus-4-8` 層 / 5/10）", out)

    def test_the_threshold_is_inclusive_at_twenty_percent(self):
        """#210 の回復サインは「20% **未満**」なので、ちょうど 20% はまだ鳴る（境界を狭める変異を殺す）."""
        rows = [self._row("opus-4-8", 0, 0) for _ in range(2)] \
             + [self._row("opus-4-8", 1, 0) for _ in range(8)] \
             + [self._row("opus-5", 1, 0) for _ in range(12)]
        self._events(rows)
        self.assertIn("真の空振り率（報告 0 件かつ付録推奨 0）が 20%（`opus-4-8` 層 / 2/10）",
                      self._out(), "境界ちょうどで鳴っていない")

    def test_a_rescued_run_is_not_a_true_silent_one(self):
        """報告 0 でも推奨があれば空振りではない（#168）— 分子に入れない."""
        rows = [self._row("opus-4-8", 0, 1) for _ in range(10)]
        self._events(rows)
        out = self._out()
        self.assertNotIn("真の空振り率", out.split("⚠️ シグナル")[-1], "救われた回を空振りに数えている")
        j = json.loads(self.run_script(RETRO, "--json", env=self._env()).stdout)
        self.assertEqual(j["appendix_by_gen"]["opus-4-8"],
                         {"n": 10, "silent": 10, "rescued": 10, "true_silent": 0})

    def test_a_layer_below_the_floor_does_not_fire_alone(self):
        """下限未満の層だけでは鳴らない（n=4 で 100% でも判定しない）."""
        self._events([self._row("opus-4-8", 0, 0) for _ in range(4)])
        self.assertNotIn("真の空振り率", self._out().split("⚠️ シグナル")[-1])

    def test_the_generation_table_is_shown_when_layers_differ(self):
        """世代が 2 種以上あれば表を割って出す（読み手に引き算させない）."""
        rows = [self._row("opus-4-8", 0, 0), self._row("opus-4-8", 0, 1), self._row("opus-5", 1, 0)]
        self._events(rows)
        out = self._out()
        self.assertIn("| 世代 | n | 報告 0 件 | うち推奨あり | 真の空振り |", out)
        self.assertIn("| opus-4-8 | 2 | 2 | 1 | 1（50%） |", out)

    def test_the_json_carries_per_generation_values(self):
        rows = [self._row("opus-4-8", 0, 0), self._row("opus-5", 1, 0)]
        self._events(rows)
        j = json.loads(self.run_script(RETRO, "--json", env=self._env()).stdout)
        self.assertEqual(j["appendix_by_gen"]["opus-4-8"]["true_silent"], 1)
        self.assertEqual(j["appendix_by_gen"]["opus-5"]["true_silent"], 0)


if __name__ == "__main__":
    unittest.main()
