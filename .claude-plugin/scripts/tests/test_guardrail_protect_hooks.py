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

from hook_harness import HookTestCase, ROOT, TempGitRepo

DETECTOR = ROOT / "guardrail-protect" / "hooks" / "scripts" / "detect-commit-bypass.pl"


#: 検査対象の設定ファイル。**生の文字列で書かない** — このテストファイル自身が
#: hook の前段フィルタに掛かるのを避ける
CFG = ".claude/guardrail-" + "protect.json"

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


    # ---- 設定ファイル自己保護（トークン準拠 / 誤検出の修正）------------------
    #
    # **判定は $cmd 全体への正規表現では行わない。** 旧実装は引用符を見ずに
    # 「破壊的な語 → 設定ファイル名」の並びを探しており、ファイル名を**文字列として
    # 書いただけ**のコマンドをブロックしていた（README に当のファイル名を書こうとして
    # 実際に作業が止まった）。以下の「黙る側」を消すと、その誤検出が復活する。

    def test_mentioning_the_config_file_is_allowed(self):
        """ファイル名を言及・読み取りするだけでは発火しない."""
        for cmd in (f'echo "設定は {CFG} にある"',
                    f"echo 'rm は危険。{CFG} を参照'",
                    f"cat {CFG}",
                    f"grep hooks {CFG}",
                    f"jq . {CFG}",
                    f"ls -la {CFG}",
                    f"git add {CFG}",
                    f'git commit -m "docs: {CFG} の説明"',
                    f"diff {CFG} /tmp/other.json"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.detect(cmd), "", "言及しただけで検出している")

    def test_a_destructive_verb_in_a_quoted_string_is_allowed(self):
        """引用符の中に破壊的な語とファイル名が同居しても発火しない.

        実測の偽陽性: `echo 'rm は危険。... <config> にある'` が BLOCK されていた。
        区切り（| ; &）が間に無ければ距離を問わず一致する実装だった。
        """
        body = "python3 - <<'PY'\ns = " + "'''" + "`" + CFG + "` は制御しない（rm / mv / cp）" + "'''" + "\nPY"
        self.assertEqual(self.detect(body), "")

    def test_actual_writes_to_the_config_file_are_still_blocked(self):
        """**自己保護は弱めない。** 実際に書き換える形はすべて検出する."""
        cases = {
            "redirect": [f'echo "{{}}" > {CFG}', f"echo x >> {CFG}", f"echo x >{CFG}",
                         f"echo x >| {CFG}", f'echo x > "{CFG}"', f"echo x > '{CFG}'"],
            "rm": [f"rm -f {CFG}", f"command rm {CFG}", f"FOO=1 rm {CFG}",
                   f"/bin/rm {CFG}", f"git status && rm {CFG}"],
            "mv": [f"mv {CFG} /tmp/bak"],
            "cp": [f"cp /tmp/empty.json {CFG}"],
            "tee": [f"echo x | tee {CFG}"],
            "truncate": [f"truncate -s 0 {CFG}"],
            "sed -i": [f'sed -i "" "s/a/b/" {CFG}', f'sed -ni "s/a/b/" {CFG}'],
            "perl -i": [f'perl -pi -e "s/a/b/" {CFG}'],
        }
        for reason, cmds in cases.items():
            for cmd in cmds:
                with self.subTest(cmd=cmd):
                    got = self.detect(cmd)
                    self.assertIn("self-modification", got, f"検出漏れ: {cmd}")
                    self.assertIn(reason, got, f"理由が {reason} でない: {got}")

    def test_writes_inside_a_nested_shell_are_blocked(self):
        """`sh -c` / `eval` に埋め込まれた書き換えも再帰解析で捕まえる."""
        for cmd in (f"sh -c 'rm {CFG}'", f"bash -c 'echo x > {CFG}'", f"eval 'rm {CFG}'"):
            with self.subTest(cmd=cmd):
                self.assertIn("self-modification", self.detect(cmd))


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

    # ---- 不正 payload / ツール種別（GitHub issue #178）----------------------
    def test_invalid_json_passes_deliberately_not_by_accident(self):
        """切り詰め JSON でも通すが、**ERR trap 経由で通さない**.

        `|| true` が無いと jq の exit 5 が safe-hook の ERR trap を踏み、
        「ガードを通り抜けた」ことに誰も気づけないまま exit 0 する。通す方向自体は
        `test_malformed_input_does_not_block` で決まっているが、それは明示的に
        選んだ結果であるべきで、事故で通るのとは別物。
        """
        res = self.run_hook(raw='{"tool_name":"Bash","tool_input":{"command":"git commit --no-ver')
        self.assertEqual(res.returncode, 0, "壊れた入力でブロック側に倒れている")
        self.assertNotIn("Unexpected", res.stderr,
                         "ERR trap で落ちている（明示的に通したのではない）")

    def test_a_non_bash_tool_is_not_inspected(self):
        """matcher が評価されない環境への二重ゲート（CLAUDE.md Gotchas）."""
        res = self.run_hook({"tool_name": "Read",
                             "tool_input": {"command": "git commit --no-verify -m x"}})
        self.assertEqual(res.returncode, 0, "Bash 以外のツールを検査している")

    def test_a_missing_tool_name_does_not_disable_the_guard(self):
        """tool_name を載せない CC 版でガードごと無効化しない（過剰なゲートの禁止）."""
        res = self.run_hook({"tool_input": {"command": "git commit --no-verify -m x"}})
        self.assertEqual(res.returncode, 2, "tool_name が無いだけでガードが死んでいる")


class PreConfigGuardTest(HookTestCase):
    """lint / hook 設定ファイルの編集ブロック（GitHub issue #178）.

    **判定に tool_name を使う**ことをここで固定する。以前は取得するだけで
    ブロック判定は file_path のみだったため、matcher が評価されない環境では
    保護対象ファイルの **Read まで**「Refusing to edit」で止まっていた。
    """

    PLUGIN = "guardrail-protect"
    SCRIPT = "hooks/scripts/pre-config-guard.sh"
    #: ガード自身の文字列マッチを避けるため連結で作る（この定数名で書くと Bash hook が反応する）
    SELF_CONFIG = "guardrail-protect" + ".json"

    def setUp(self) -> None:
        super().setUp()
        proj = self.isolated_project_dir()
        (proj / ".claude").mkdir(parents=True, exist_ok=True)
        (proj / ".claude" / self.SELF_CONFIG).write_text(
            '{"protected_basenames":[".eslintrc.json"]}', encoding="utf-8")

    def test_editing_a_protected_file_is_blocked(self):
        res = self.run_hook({"tool_name": "Edit",
                             "tool_input": {"file_path": "/p/.eslintrc.json"}})
        self.assertEqual(res.returncode, 2, "保護対象の編集を通している")

    def test_reading_a_protected_file_is_allowed(self):
        res = self.run_hook({"tool_name": "Read",
                             "tool_input": {"file_path": "/p/.eslintrc.json"}})
        self.assertEqual(res.returncode, 0, "Read をブロックしている（編集ガードの範囲外）")

    def test_reading_the_guard_config_itself_is_allowed(self):
        res = self.run_hook({"tool_name": "Read",
                             "tool_input": {"file_path": "/p/" + self.SELF_CONFIG}})
        self.assertEqual(res.returncode, 0, "自己保護が Read まで止めている")

    def test_writing_the_guard_config_itself_is_blocked(self):
        """自己保護は config の有無に依らず効く（2 段階バイパスを塞ぐ）."""
        res = self.run_hook({"tool_name": "Write",
                             "tool_input": {"file_path": "/p/" + self.SELF_CONFIG}})
        self.assertEqual(res.returncode, 2, "自己保護が効いていない")

    def test_an_unprotected_file_is_allowed(self):
        res = self.run_hook({"tool_name": "Edit",
                             "tool_input": {"file_path": "/p/src/main.ts"}})
        self.assertEqual(res.returncode, 0)

    def test_invalid_json_passes_deliberately_not_by_accident(self):
        res = self.run_hook(raw='{"tool_name":"Edit","tool_input":{"file_pa')
        self.assertEqual(res.returncode, 0, "壊れた入力でブロック側に倒れている")
        self.assertNotIn("Unexpected", res.stderr,
                         "ERR trap で落ちている（明示的に通したのではない）")



STALE_REF_DETECTOR = ROOT / "guardrail-protect" / "hooks" / "scripts" / "detect-stale-refs.py"

#: 参照先として使う doc。節番号が飛んでいる（分冊で番号を引き継ぐ本リポジトリの慣習）
SAMPLE_DOC = """# 計測（guide 分冊）

## 13. Event Bus publish 先の固定

```bash
# 合算するログの一覧を作る
#
```

``` `<file>.md ## <見出し>` ``` 形式の参照（行頭のインラインコードスパン）

## 15. 区間・wave 単価の実測ベースライン

#### P.1: 剪定候補スキャン

## 版マーカーの現行値

## 計測の基準値（改修効果はここと比べる）
"""


class StaleRefDetectorTest(unittest.TestCase):
    """見出し実在の判定本体を CLI 境界越しに叩く.

    **パス実在は検証しない**という設計判断がここの要。過去 issue 188 件 +
    コメント 213 件の実測で、パス実在検証は真の検出 0 件・偽陽性 41 件だった
    （正当なプラグインルート相対参照 / placeholder / 他リポジトリのパス /
    実行時生成ファイル / `React/Next.js` のような非パス）。**未解決パスで黙る**
    テストを消すと、その 41 件がそのまま block として復活する。
    """

    def setUp(self):
        self._repo = TempGitRepo()
        self.repo = self._repo.__enter__()
        self.addCleanup(self._repo.__exit__)
        (self.repo / "code-review" / "references").mkdir(parents=True)
        (self.repo / "code-review" / "references" / "measurement.md").write_text(
            SAMPLE_DOC, encoding="utf-8")
        self._repo.commit("add doc", filename="README.md", body="x")

    def detect(self, body: str) -> str:
        proc = subprocess.run(
            ["python3", str(STALE_REF_DETECTOR), str(self.repo)],
            input=body, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"判定器は常に exit 0: {proc.stderr}")
        return proc.stdout.strip()

    # ---- 検出する側 --------------------------------------------------------
    def test_missing_heading_is_detected(self):
        self.assertIn("measurement.md ## 5", self.detect("典拠は `measurement.md ## 5` にある"))

    def test_a_numeric_anchor_must_not_match_a_longer_number(self):
        """`## 1` を `## 13` に一致させない（番号違いが素通りするため）."""
        detected = self.detect("`measurement.md ## 1`")
        self.assertTrue(detected.startswith("measurement.md ## 1\t"),
                        f"`## 1` が `## 13` に吸われている: {detected!r}")

    def test_detected_across_plugin_root_relative_path(self):
        """プラグインルート相対（末尾一致）でも解決して見出しを見る."""
        self.assertIn("references/measurement.md ## 5",
                      self.detect("`references/measurement.md ## 5`"))


    def test_a_fenced_comment_is_not_a_heading(self):
        """コードフェンス内の `#` 行を見出しに採らない.

        採ると `## <番号>` 参照がシェルコメントに前方一致して**検出が黙って
        無効化される**。本リポジトリの `orchestration-measurement.md` は
        フェンス内に 2 本持っており、実際に採取されていた。
        """
        self.assertIn("measurement.md ## 合算",
                      self.detect("`measurement.md ## 合算するログの一覧を作る`"))

    def test_an_empty_heading_does_not_disable_detection(self):
        """裸の `#` 行（空見出し）で検出が丸ごと死なない.

        両方向の前方一致のうち `anchor.startswith(head)` に境界条件が無いと、
        空文字の見出しに**全参照が一致**してそのファイルの検出が消える。
        壊れ方が「黙って無効化」なので、テストが緑でも気づけない型。
        """
        detected = self.detect("`measurement.md ## 999`")
        self.assertTrue(detected.startswith("measurement.md ## 999\t"),
                        f"空見出しに吸われている: {detected!r}")

    def test_a_heading_after_an_inline_code_span_is_found(self):
        """行頭のインラインコードスパンをフェンス開始と誤認しない.

        誤認すると以降の実在見出しが全部消え、**正しい参照が block される**。
        実測でこのリポジトリ自身の README が該当し、`## 制限事項` への参照が
        exit 2 になっていた（fixture のフェンスが必ず閉じていたため未検知）。
        """
        for ref in ("measurement.md ## 15", "measurement.md ## 計測の基準値"):
            with self.subTest(ref=ref):
                self.assertEqual(self.detect(f"`{ref}`"), "")

    def test_an_unterminated_fence_makes_the_file_undecidable(self):
        """閉じないフェンスがある doc は「判定不能」として黙る.

        壊れた見出し一覧を正しい一覧として使うと偽陽性になる。
        """
        (self.repo / "broken.md").write_text(
            "# T\n\n```\n# not a heading\n\n## 実在する見出し\n", encoding="utf-8")
        self._repo.commit("add broken", filename="README.md", body="b")
        self.assertEqual(self.detect("`broken.md ## 実在する見出し`"), "")
        self.assertEqual(self.detect("`broken.md ## 存在しないZZZ`"), "",
                         "判定不能なファイルで検出している")

    def test_a_deep_heading_is_matched(self):
        """H4 以上（`####`）への正しい参照を検出しない.

        `#` を 3 個で打ち切ると 4 個目が anchor 側に漏れ、必ず不一致になる。
        """
        self.assertEqual(self.detect("`measurement.md #### P.1: 剪定候補スキャン`"), "")

    def test_a_compound_reference_is_silent(self):
        """複数節をまとめて指す書き方は判定しない（anchor が見出しになりえない）.

        この記法は `code-review/CHANGELOG.md` に実在する。
        """
        for ref in ("measurement.md ## 15 / ## 13", "measurement.md ## 6 / ## 8 / ## 2"):
            with self.subTest(ref=ref):
                self.assertEqual(self.detect(f"`{ref}`"), "")

    def test_a_github_anchor_slug_is_matched(self):
        """GitHub 標準の anchor slug（小文字ハイフン）を見出しに対応づける."""
        (self.repo / "en.md").write_text("# T\n\n## Installation Guide\n", encoding="utf-8")
        self._repo.commit("add en", filename="README.md", body="c")
        self.assertEqual(self.detect("`en.md#installation-guide`"), "")
        self.assertIn("en.md ## nope", self.detect("`en.md#nope`"))

    def test_an_exact_heading_match_is_silent(self):
        """見出しを 1 文字違わず引用した形（最も丁寧な書き方）を弾かない."""
        self.assertEqual(self.detect("`measurement.md ## 版マーカーの現行値`"), "")

    def test_a_path_with_spaces_or_non_ascii_resolves(self):
        """`git ls-files` の既定エスケープ・空白分割で解決不能にならない.

        `split()` のままだと非 ASCII パスは永久に解決できず**黙って無検査**になり、
        空白入りパスは 2 つに割れて無関係な参照の検出まで殺す。
        """
        (self.repo / "計測メモ.md").write_text("# T\n\n## 実在\n", encoding="utf-8")
        (self.repo / "my notes.md").write_text("# T\n\n## 実在\n", encoding="utf-8")
        self._repo.commit("add odd names", filename="README.md", body="d")
        self.assertIn("計測メモ.md ## 無いZZZ", self.detect("`計測メモ.md ## 無いZZZ`"))
        self.assertEqual(self.detect("`計測メモ.md ## 実在`"), "")
        self.assertEqual(self.detect("`measurement.md ## 15`"), "",
                         "空白入りパスが無関係な参照の検出を壊している")

    # ---- 黙る側（こちらが厚い。偽陽性 0 を維持する境界）--------------------
    def test_existing_heading_is_silent(self):
        for ref in ("measurement.md ## 15", "measurement.md ## 13",
                    "measurement.md ## 計測の基準値"):
            with self.subTest(ref=ref):
                self.assertEqual(self.detect(f"`{ref}`"), "")

    def test_a_heading_prefix_is_silent(self):
        self.assertEqual(self.detect("`measurement.md ## 15. 区間`"), "")

    def test_a_reference_longer_than_the_heading_is_silent(self):
        """参照が見出しより長い向きの前方一致（見出しを丸ごと含んで補足を足した形）."""
        self.assertEqual(
            self.detect("`measurement.md ## 13. Event Bus publish 先の固定 の話`"), "")

    def test_without_an_argument_it_falls_back_to_the_working_directory(self):
        """root 引数なしでも落ちない（既定は cwd）."""
        proc = subprocess.run(["python3", str(STALE_REF_DETECTOR)],
                              input="`measurement.md ## 5`", cwd=str(self.repo),
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"引数なしで落ちている: {proc.stderr}")
        self.assertIn("measurement.md ## 5", proc.stdout)

    def test_an_unresolvable_path_is_silent(self):
        """**パス実在は検証しない**（実測で偽陽性 41 件 / 真の検出 0 件だった）."""
        for ref in ("path/to/doc.md ## 1", "evals/reports/recall-YYYYMMDD.md ## x",
                    "src/lib/prisma.ts.md ## 3"):
            with self.subTest(ref=ref):
                self.assertEqual(self.detect(f"`{ref}`"), "")

    def test_an_ambiguous_filename_is_silent(self):
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "measurement.md").write_text("# other\n", encoding="utf-8")
        self._repo.commit("add dup", filename="README.md", body="y")
        self.assertEqual(self.detect("`measurement.md ## 5`"), "",
                         "複数に一致するファイル名で判定している")

    def test_a_url_fragment_is_silent(self):
        self.assertEqual(
            self.detect("`https://example.com/blob/main/measurement.md#5`"), "")

    def test_a_non_markdown_reference_is_silent(self):
        self.assertEqual(self.detect("`code-review/scripts/foo.sh ## 5`"), "")

    def test_outside_a_git_repository_it_is_silent(self):
        proc = subprocess.run(
            ["python3", str(STALE_REF_DETECTOR), "/"],
            input="`measurement.md ## 5`", capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")


class GhRefGuardTest(HookTestCase):
    """hook 本体: `gh` の外向き書き込みだけを検査し、それ以外は素通りする."""

    PLUGIN = "guardrail-protect"
    SCRIPT = "hooks/scripts/gh-ref-guard.sh"

    def setUp(self):
        self._repo = TempGitRepo()
        self.repo = self._repo.__enter__()
        self.addCleanup(self._repo.__exit__)
        (self.repo / "code-review" / "references").mkdir(parents=True)
        (self.repo / "code-review" / "references" / "measurement.md").write_text(
            SAMPLE_DOC, encoding="utf-8")
        self._repo.commit("add doc", filename="README.md", body="x")

    def gh(self, command: str):
        return self.run_hook(self.bash_payload(command), cwd=self.repo)

    # ---- ブロックする側 ----------------------------------------------------
    def test_blocks_a_missing_heading_in_an_issue_comment(self):
        res = self.gh("gh issue comment 1 --body '典拠は `measurement.md ## 5`'")
        self.assertEqual(res.returncode, 2, f"ブロックするべき: {res!r}")
        self.assertIn("heading that does not exist", res.stderr)

    def test_blocks_across_gh_write_subcommands(self):
        for sub in ("gh issue create --title t --body",
                    "gh pr create --title t --body",
                    "gh pr comment 1 --body",
                    "gh issue close 1 --comment"):
            with self.subTest(sub=sub):
                res = self.gh(f"{sub} '`measurement.md ## 5`'")
                self.assertEqual(res.returncode, 2, f"{sub} を検査していない")

    def test_body_file_contents_are_inspected(self):
        (self.repo / "body.md").write_text("典拠は `measurement.md ## 5`", encoding="utf-8")
        res = self.gh(f"gh issue comment 1 --body-file {self.repo / 'body.md'}")
        self.assertEqual(res.returncode, 2, "--body-file の中身を読んでいない")

    def test_a_command_that_only_looks_like_gh_is_not_inspected(self):
        """`gh` が単語の一部として現れるだけのコマンドを検査しない.

        部分文字列 glob（`*gh*issue*create*`）だと `hi(gh)light ... issue ... create` が
        一致し、**gh を呼んでいないコマンドを block** していた（実測）。
        """
        for cmd in ('echo "highlight the issue then create a note: `measurement.md ## ZZZ`"',
                    'echo "insight: issue tracking, then create `measurement.md ## ZZZ`"',
                    'grep -r "gh pr review" docs/'):
            with self.subTest(cmd=cmd):
                res = self.gh(cmd)
                self.assertEqual(res.returncode, 0, f"gh を呼ばないコマンドを止めた: {res.stderr}")

    def test_read_only_gh_subcommands_are_not_inspected(self):
        """`--comments` / `--json reviews` を持つ読み取り専用 gh を検査しない."""
        for cmd in ("gh issue view 1 --comments", "gh pr view 1 --comments",
                    "gh pr view 1 --json reviews", "gh issue list"):
            with self.subTest(cmd=cmd):
                self.assertEqual(
                    self.gh(f'{cmd} # `measurement.md ## ZZZ`').returncode, 0)

    def test_body_file_equals_form_is_inspected(self):
        """`--body-file=path` の `=` 形式も読み足す（gh が受け付ける形）."""
        (self.repo / "body.md").write_text("`measurement.md ## ZZZ`", encoding="utf-8")
        res = self.gh(f"gh issue comment 1 --body-file={self.repo / 'body.md'}")
        self.assertEqual(res.returncode, 2, "`=` 形式の --body-file を読んでいない")

    def test_a_broken_detector_is_loud(self):
        """検出器が壊れたら**黙って通さない**（rc だけでなく stderr を見る）.

        以前は `2>/dev/null || true` が握り潰し、検出器を消しても
        rc=0 / 出力 0 バイトでガードが黙って無効化されていた（実測）。
        """
        import shutil
        alt = self.isolated_project_dir() / "plugin-copy"
        if not alt.exists():
            shutil.copytree(ROOT / "guardrail-protect", alt)
        (alt / "hooks" / "scripts" / "detect-stale-refs.py").unlink()
        res = self.run_hook(
            self.bash_payload("gh issue comment 1 --body '`measurement.md ## ZZZ`'"),
            cwd=self.repo, env_extra={"CLAUDE_PLUGIN_ROOT": str(alt)})
        self.assertIn("Unexpected", res.stderr,
                      "検出器が壊れても無音で通している（ガードの silent 無効化）")

    def test_a_write_with_only_equals_flags_is_inspected(self):
        """位置引数を持たない書き込みも検査する（`--body-file=` と `--title=` だけの形）.

        prefilter は `gh` の後ろの**非フラグ**トークンで `<issue|pr> <write>` を判定する。
        `=` 形式のフラグは非フラグ扱いにならないので、この形では判定材料が
        ちょうど 2 個になる。境界を 1 つ狭めると**検査ごとスキップ**される
        （nightly の変異テストが検出 / GitHub issue #189）。
        """
        (self.repo / "body.md").write_text("`measurement.md ## ZZZ`", encoding="utf-8")
        res = self.gh(f"gh issue create --body-file={self.repo / 'body.md'} --title=t")
        self.assertEqual(res.returncode, 2, "位置引数の無い書き込みを検査していない")

    def test_an_unrelated_token_that_names_a_file_is_not_read(self):
        """`--body-file` / `-F` の**直後**以外のトークンをファイルとして読まない.

        読むと、たまたま実在するファイル名がどこかに現れただけで中身が検査対象に入り、
        **本文がきれいでも誤ブロック**する（nightly の変異テストが検出 / GitHub issue #189）。
        """
        (self.repo / "notes.md").write_text("`measurement.md ## ZZZ`", encoding="utf-8")
        res = self.gh("gh issue create --title notes.md --body clean")
        self.assertEqual(res.returncode, 0,
                         f"無関係なトークンをファイルとして読んでいる: {res.stderr}")

    # ---- 黙る側 ------------------------------------------------------------
    def test_allows_an_existing_heading(self):
        res = self.gh("gh issue comment 1 --body '典拠は `measurement.md ## 15`'")
        self.assertEqual(res.returncode, 0, f"正当な参照を止めた: {res.stderr}")
        self.assertSilent(res)
        self.assertNotIn("Unexpected", res.stderr,
                         "ERR trap で落ちている（黙ったのではなく死んでいる）")

    def test_read_only_gh_commands_are_not_inspected(self):
        for cmd in ("gh issue view 1", "gh issue list", "gh pr list",
                    "gh api repos/x/y"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.gh(f"{cmd} # `measurement.md ## 5`").returncode, 0)

    def test_unrelated_commands_are_not_inspected(self):
        for cmd in ("ls", "npm test", "git commit -m '`measurement.md ## 5`'"):
            with self.subTest(cmd=cmd):
                res = self.gh(cmd)
                self.assertEqual(res.returncode, 0)
                self.assertSilent(res)

    def test_empty_command_is_ignored(self):
        self.assertEqual(
            self.run_hook({"tool_name": "Bash", "tool_input": {}}, cwd=self.repo).returncode, 0)

    def test_malformed_input_does_not_block(self):
        self.assertEqual(self.run_hook({}, cwd=self.repo).returncode, 0)

    def test_invalid_json_passes_deliberately_not_by_accident(self):
        res = self.run_hook(
            raw='{"tool_name":"Bash","tool_input":{"command":"gh issue comment 1 --body',
            cwd=self.repo)
        self.assertEqual(res.returncode, 0, "壊れた入力でブロック側に倒れている")
        self.assertNotIn("Unexpected", res.stderr,
                         "ERR trap で落ちている（明示的に通したのではない）")

    def test_a_non_bash_tool_is_not_inspected(self):
        res = self.run_hook(
            {"tool_name": "Read",
             "tool_input": {"command": "gh issue comment 1 --body '`measurement.md ## 5`'"}},
            cwd=self.repo)
        self.assertEqual(res.returncode, 0, "Bash 以外のツールを検査している")

    def test_a_missing_tool_name_does_not_disable_the_guard(self):
        res = self.run_hook(
            {"tool_input": {"command": "gh issue comment 1 --body '`measurement.md ## 5`'"}},
            cwd=self.repo)
        self.assertEqual(res.returncode, 2, "tool_name が無いだけでガードが死んでいる")


class RealRepositoryRegressionTest(unittest.TestCase):
    """**このリポジトリの実 md に当てる回帰テスト**（合成 fixture の代替ではなく補完）.

    新規 26 テストをすり抜けたバグ 5 件は、すべて「参照先 doc の形」に起因していた
    （フェンス未終端 / 行頭インラインコードスパン / H4 / 複合参照 / slug）。
    参照テキスト側をいくら増やしても再現しない型で、**実データに当てる 1 本**が
    最も安く覆う。doc の記法が増えるたび母数が自動で増える点も合成 fixture に勝る。

    実測（修正前）: 実在見出し 3396 件中 87 件が偽陽性。
    """

    def test_every_real_heading_in_this_repository_is_accepted(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("d", STALE_REF_DETECTOR)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        root = str(ROOT)
        md_files = [f for f in mod.repo_files(root) if f.endswith(".md")]
        self.assertGreater(len(md_files), 50, "母集団が小さすぎる（走査に失敗している）")

        refs = []
        for path in md_files:
            for head in mod.headings(root, path):
                if "`" in head:          # 参照記法自体を壊すのでこのテストの対象外
                    continue
                refs.append(f"`{path} ## {head}`")
        self.assertGreater(len(refs), 500, "見出しが採れていない")

        hits = mod.detect("\n".join(refs), root)
        self.assertEqual(
            hits, [],
            "実在する見出しへの正しい参照を %d 件 block している（偽陽性 0 が設計要件）: %s"
            % (len(hits), [r for r, _ in hits[:5]]))


if __name__ == "__main__":
    unittest.main()
