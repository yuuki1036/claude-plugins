#!/usr/bin/env python3
"""guardrail-protect の public-leak-guard（公開先への業務情報送信ガード）の回帰テスト.

**語はすべてダミー**（AcmeCorp / ProjectFalcon / zork / falcon-devbox）。実際の辞書は
リポジトリに入れない。

構成:
- 突破パターン（反証レビューで見つかった穴）ごとに「止まること」を 1 本以上
- private 宛・読み取り専用・無関係なコマンドが**素通しになること**（暴発の反対側）
- 出力に語そのものが出ないこと

gh / hostname / ssh は PATH の先頭に置いたスタブで置き換える（ネットワークに出ない）。
HOME も使い捨てにするので、開発機の辞書・設定・visibility キャッシュには触れない。

実行: python3 .claude-plugin/scripts/run-tests.py
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from git_env import scrub
from hook_harness import HookTestCase, ROOT

PLUGIN_ROOT = ROOT / "guardrail-protect"
DETECTOR = PLUGIN_ROOT / "hooks" / "scripts" / "detect-public-leak.py"
PREPUSH = PLUGIN_ROOT / "git-hooks" / "pre-push.sh"
PERL_DETECTOR = PLUGIN_ROOT / "hooks" / "scripts" / "detect-commit-bypass.pl"

#: ダミー辞書（4 行目 = AcmeCorp）
DICT = """# テスト用のダミー辞書
# 空行とコメントは数えない

AcmeCorp
ProjectFalcon
w:zork
ab
"""
DICT_LINE_ACME = 4
HOSTNAME = "falcon-devbox"
SECRET_WORDS = ("AcmeCorp", "acmecorp", "ProjectFalcon", "zork", HOSTNAME)

VIS = {
    "acme-user/public-repo": "public",
    "acme-user/private-repo": "private",
    "acme-user/upstream-pub": "public",
    "acme-work/secret-app": "private",
    "other-org/oss-lib": "public",
}

GH_STUB = r'''#!/usr/bin/env python3
import json, os, sys, time
fx = json.load(open(os.environ["PLG_FIXTURE"]))
with open(fx["log"], "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\n")
args = sys.argv[1:]
if args[:2] == ["alias", "list"]:
    for k, v in fx.get("aliases", {}).items():
        print("%s: %s" % (k, v))
    sys.exit(0)
if args and args[0] == "api":
    time.sleep(fx.get("sleep", 0))
    rest = args[1:]
    if "--hostname" in rest:
        i = rest.index("--hostname")
        del rest[i:i + 2]
    ep = rest[0] if rest else ""
    if ep.startswith("repos/"):
        v = fx.get("repos", {}).get(ep[len("repos/"):])
        if v is None:
            sys.stderr.write("HTTP 404: Not Found\n")
            sys.exit(1)
        print(v)
        sys.exit(0)
sys.exit(1)
'''

SSH_STUB = r'''#!/bin/sh
if [ "$1" = "-G" ]; then
  case "$2" in
    github-work) echo "hostname github.com" ;;
    *) echo "hostname $2" ;;
  esac
  exit 0
fi
exit 255
'''


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class PublicLeakBase(HookTestCase):
    PLUGIN = "guardrail-protect"
    SCRIPT = "hooks/scripts/public-leak-guard.sh"

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.home = self.tmp / "home"
        (self.home / ".config" / "guardrail-protect").mkdir(parents=True)
        (self.home / ".config" / "gh").mkdir(parents=True)
        (self.home / ".config" / "gh" / "hosts.yml").write_text(
            "github.com:\n    user: acme-user\n    git_protocol: https\n", encoding="utf-8")
        self.dict_path = self.home / ".config" / "guardrail-protect" / "sensitive-terms.txt"
        self.dict_path.write_text(DICT, encoding="utf-8")
        self.config_path = self.home / ".config" / "guardrail-protect" / "public-leak-guard.json"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.gh_log = self.tmp / "gh.log"
        self.fixture = {"repos": dict(VIS), "aliases": {}, "sleep": 0, "log": str(self.gh_log)}
        self._save_fixture()
        _write_exec(self.bin / "gh", GH_STUB)
        _write_exec(self.bin / "hostname", "#!/bin/sh\necho %s\n" % HOSTNAME)
        _write_exec(self.bin / "ssh", SSH_STUB)
        self.repo = self.make_repo("public", "git@github.com:acme-user/public-repo.git")
        self.priv = self.make_repo("private", "https://github.com/acme-user/private-repo.git")
        self.plain = self.tmp / "plain"          # git 管理外
        self.plain.mkdir()

    # ---- 準備 -----------------------------------------------------------------
    def _save_fixture(self) -> None:
        self.fixture_path = self.tmp / "fixture.json"
        self.fixture_path.write_text(json.dumps(self.fixture), encoding="utf-8")

    def set_config(self, **cfg) -> None:
        self.config_path.write_text(json.dumps(cfg), encoding="utf-8")

    def git(self, *args: str, cwd: Path) -> str:
        return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                              env=scrub(), check=True).stdout

    def make_repo(self, name: str, origin: str | None) -> Path:
        path = self.tmp / name
        path.mkdir()
        self.git("init", "-q", "-b", "main", cwd=path)
        self.git("config", "user.email", "t@example.com", cwd=path)
        self.git("config", "user.name", "t", cwd=path)
        (path / "README.md").write_text("clean\n", encoding="utf-8")
        self.git("add", "-A", cwd=path)
        self.git("commit", "-qm", "init", cwd=path)
        if origin:
            self.git("remote", "add", "origin", origin, cwd=path)
            self.git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=path)
        return path

    def commit(self, repo: Path, message: str, filename: str = "f.txt", body: str = "x\n") -> None:
        (repo / filename).write_text(body, encoding="utf-8")
        self.git("add", "-A", cwd=repo)
        self.git("commit", "-qm", message, cwd=repo)

    def env(self, **extra: str) -> dict:
        env = {
            "HOME": str(self.home),
            "PATH": "%s:%s" % (self.bin, os.environ.get("PATH", "")),
            "PLG_FIXTURE": str(self.fixture_path),
            "GH_CONFIG_DIR": str(self.home / ".config" / "gh"),
            "GH_REPO": "",
            "GUARDRAIL_SENSITIVE_DICT": "",
            "GUARDRAIL_PUBLIC_LEAK_CONFIG": "",
        }
        env.update(extra)
        return env

    # ---- 叩く -----------------------------------------------------------------
    def bash(self, command: str, cwd: Path | None = None, **payload_extra):
        payload = {"tool_name": "Bash", "tool_input": {"command": command},
                   "cwd": str(cwd or self.repo), "permission_mode": "default"}
        payload.update(payload_extra)
        env_extra = payload.pop("_env", {})
        return self.run_hook(payload, cwd=self.tmp, env_extra=self.env(**env_extra))

    def tool(self, name: str, tool_input: dict, cwd: Path | None = None, **payload_extra):
        payload = {"tool_name": name, "tool_input": tool_input, "cwd": str(cwd or self.repo),
                   "permission_mode": "default"}
        payload.update(payload_extra)
        return self.run_hook(payload, cwd=self.tmp, env_extra=self.env())

    def gh_calls(self) -> list[str]:
        if not self.gh_log.exists():
            return []
        return [x for x in self.gh_log.read_text(encoding="utf-8").splitlines() if x]

    # ---- 判定 -----------------------------------------------------------------
    def assertBlocked(self, res, contains: str = ""):
        self.assertEqual(res.returncode, 2, "止めるべき: %r" % res)
        for word in SECRET_WORDS:
            self.assertNotIn(word, res.stderr, "出力に語そのものが出ている")
            self.assertNotIn(word, res.stdout, "出力に語そのものが出ている")
        if contains:
            self.assertIn(contains, res.stderr)

    def assertPassed(self, res):
        self.assertEqual(res.returncode, 0, "通すべき: %r" % res)
        self.assertEqual(res.stdout.strip(), "", "確認・警告を出してはいけない: %r" % res)
        self.assertNotIn("Unexpected", res.stderr, "ERR trap を踏んでいる: %r" % res)


PUB = "-R acme-user/public-repo"
PRIV = "-R acme-user/private-repo"


class SilentTest(PublicLeakBase):
    """**黙る側**。暴発はすべての Bash 呼び出しに効くので最も厚く見る."""

    def test_unrelated_commands_pass_without_calling_gh(self):
        for cmd in ("ls -la", "npm test", "echo hello", "python3 -m unittest", "cat README.md"):
            with self.subTest(cmd=cmd):
                self.assertPassed(self.bash(cmd))
        self.assertEqual(self.gh_calls(), [], "無関係なコマンドで API を引いている")

    def test_read_only_gh_and_git_pass(self):
        for cmd in ("gh issue list", "gh pr view 1 --comments", "gh api repos/acme-user/public-repo",
                    "gh api graphql -f query='query { viewer { login } }'",
                    "git status", "git log -n 5", "git push --dry-run", "gh repo view"):
            with self.subTest(cmd=cmd):
                self.assertPassed(self.bash(cmd + " # AcmeCorp"))

    def test_private_destination_passes_even_with_a_dictionary_word(self):
        self.assertPassed(self.bash("gh issue create %s -t t --body 'AcmeCorp の件'" % PRIV))

    def test_implicit_destination_in_a_private_repository_passes(self):
        self.commit(self.priv, "AcmeCorp の修正")
        self.assertPassed(self.bash("gh pr create -t t -b 'AcmeCorp'", cwd=self.priv))
        self.assertPassed(self.bash("git push", cwd=self.priv))

    def test_clean_body_to_a_public_repository_passes(self):
        self.assertPassed(self.bash("gh issue create %s -t 'ok' --body 'ただの本文'" % PUB))

    def test_short_terms_and_comments_in_the_dictionary_are_ignored(self):
        self.assertPassed(self.bash("gh issue comment 1 %s --body 'ab と # と 空行'" % PUB))

    def test_word_boundary_terms(self):
        self.assertPassed(self.bash("gh issue comment 1 %s --body 'zorky'" % PUB))
        self.assertBlocked(self.bash("gh issue comment 1 %s --body 'zork-1'" % PUB))

    def test_integrity_hashes_do_not_trigger_short_terms(self):
        """短い語が `sha512-…` に偶然入って止まる誤検知を避ける（`-` と `/` は語境界になる）."""
        for body in ("sha512-zork/AbCdEf+012345==", "sha512-xAcmeCorpQ+AbCdEf=="):
            with self.subTest(body=body):
                self.assertPassed(self.bash("gh issue comment 1 %s --body '%s'" % (PUB, body)))

    def test_non_bash_tools_are_ignored(self):
        res = self.tool("Read", {"file_path": "/x", "command": "gh issue create --body AcmeCorp"})
        self.assertPassed(res)

    def test_reading_the_guard_files_is_allowed(self):
        self.assertPassed(self.bash("cat ~/.config/guardrail-protect/public-leak-guard.json"))


class BodyTest(PublicLeakBase):
    """本文の取り方ごとに、辞書語が入れば止まる."""

    def test_inline_body_and_title(self):
        for cmd in ("gh issue create %s -t 'AcmeCorp' -b x" % PUB,
                    "gh issue create %s --title x --body='ProjectFalcon'" % PUB,
                    "gh pr comment 3 %s -b\"AcmeCorp\"" % PUB,
                    "gh issue close 3 %s --comment 'AcmeCorp'" % PUB,
                    "gh issue reopen 3 %s -c 'AcmeCorp'" % PUB,
                    "gh pr review 3 %s -c -b 'AcmeCorp'" % PUB,
                    "gh pr merge 3 %s --squash --subject 'AcmeCorp'" % PUB,
                    "gh pr merge 3 %s -b 'AcmeCorp'" % PUB,
                    "gh pr edit 3 %s --title 'AcmeCorp'" % PUB,
                    "gh release create v1 %s --notes 'AcmeCorp'" % PUB,
                    "gh label create 'AcmeCorp' %s" % PUB):
            with self.subTest(cmd=cmd):
                self.assertBlocked(self.bash(cmd))

    def test_output_names_the_dictionary_line_and_body_line_only(self):
        res = self.bash("gh issue create %s -t t --body $'1 行目\\n2 行目 AcmeCorp'" % PUB)
        self.assertBlocked(res, "辞書 %d 行目" % DICT_LINE_ACME)
        self.assertIn("2 行目", res.stderr)
        self.assertIn("TEAM-123", res.stderr, "置き換え例を添える")
        self.assertIn("m2", res.stderr)

    def test_hostname_is_an_implicit_term(self):
        res = self.bash("gh issue comment 1 %s --body '集計 @ %s'" % (PUB, HOSTNAME))
        self.assertBlocked(res, "ホスト名")

    def test_body_file_is_resolved_against_the_hook_cwd(self):
        sub = self.plain / "sub"
        sub.mkdir()
        (sub / "b.md").write_text("本文\nAcmeCorp\n", encoding="utf-8")
        self.assertBlocked(self.bash("gh issue create %s -t t --body-file b.md" % PUB, cwd=sub))
        self.assertBlocked(self.bash("gh issue create %s -t t -F b.md" % PUB, cwd=sub))

    def test_cd_then_relative_body_file(self):
        sub = self.plain / "sub2"
        sub.mkdir()
        (sub / "b.md").write_text("AcmeCorp\n", encoding="utf-8")
        self.assertBlocked(self.bash("cd sub2 && gh issue comment 1 %s -F b.md" % PUB, cwd=self.plain))

    def test_heredoc_written_in_the_same_command_is_read_from_the_command(self):
        """TOCTOU: 同じコマンド内で書くファイルは、ディスクではなくコマンドの heredoc を読む."""
        cmd = ("cat > %s/new.md <<'EOF'\nAcmeCorp\nEOF\n"
               "gh issue create %s -t t --body-file %s/new.md") % (self.plain, PUB, self.plain)
        self.assertBlocked(self.bash(cmd))
        # ディスクの古い中身（語あり）ではなく、これから書く中身（語なし）で判定する
        (self.plain / "stale.md").write_text("AcmeCorp\n", encoding="utf-8")
        cmd = ("cat > %s/stale.md <<'EOF'\nきれいな本文\nEOF\n"
               "gh issue create %s -t t --body-file %s/stale.md") % (self.plain, PUB, self.plain)
        self.assertPassed(self.bash(cmd))

    def test_command_substitutions(self):
        (self.plain / "b.md").write_text("AcmeCorp\n", encoding="utf-8")
        for body in ('"$(cat %s/b.md)"', '"$(< %s/b.md)"'):
            with self.subTest(body=body):
                self.assertBlocked(self.bash("gh issue comment 1 %s --body %s" % (PUB, body % self.plain)))
        cmd = "gh pr create %s -t t --body \"$(cat <<'EOF'\n## 概要\n(括弧) AcmeCorp\nEOF\n)\"" % PUB
        self.assertBlocked(self.bash(cmd))

    def test_stdin_bodies(self):
        (self.plain / "b.md").write_text("AcmeCorp\n", encoding="utf-8")
        for cmd in ("cat %s/b.md | gh issue create %s -t t -F -" % (self.plain, PUB),
                    "gh issue create %s -t t --body-file - < %s/b.md" % (PUB, self.plain),
                    "gh issue create %s -t t -F - <<'EOF'\nAcmeCorp\nEOF" % PUB):
            with self.subTest(cmd=cmd):
                self.assertBlocked(self.bash(cmd))

    def test_unresolvable_bodies_are_blocked_on_public_destinations(self):
        for cmd in ('gh issue create %s -t t --body "$BODY"' % PUB,
                    'gh issue comment 1 %s --body "$(date)"' % PUB,
                    'gh issue comment 1 %s --body="$X"' % PUB,
                    "gh issue create %s -t t -F -" % PUB,
                    "gh issue create %s -t t -F <(python3 gen.py)" % PUB):
            with self.subTest(cmd=cmd):
                self.assertBlocked(self.bash(cmd), "静的に解決できない")

    def test_an_unquoted_heredoc_expands_but_a_quoted_one_is_literal(self):
        """引用なし区切りの heredoc は本文の `$(…)` を展開するので静的に決まらない。引用付きは字面のまま読む."""
        cmd = "gh issue create %s -t t -F - <<%s\n$(cat notes.md)\nEOF"
        self.assertBlocked(self.bash(cmd % (PUB, "EOF")), "静的に解決できない")
        self.assertPassed(self.bash(cmd % (PUB, "'EOF'")))

    def test_unresolvable_body_to_private_passes(self):
        self.assertPassed(self.bash('gh issue create %s -t t --body "$BODY"' % PRIV))

    def test_a_variable_set_in_the_same_command_is_resolved(self):
        self.assertPassed(self.bash("B='きれい'; gh issue comment 1 %s --body \"$B\"" % PUB))
        self.assertBlocked(self.bash("B='AcmeCorp'; gh issue comment 1 %s --body \"$B\"" % PUB))

    def test_an_opaque_preceding_command_makes_body_files_unresolvable(self):
        (self.plain / "b.md").write_text("きれい\n", encoding="utf-8")
        self.assertBlocked(self.bash(
            "python3 gen.py && gh issue create %s -t t --body-file %s/b.md" % (PUB, self.plain)))

    def test_missing_body_file_is_blocked(self):
        self.assertBlocked(self.bash("gh issue create %s -t t --body-file /no/such.md" % PUB))

    def test_gh_api_fields_and_input(self):
        (self.plain / "b.md").write_text("AcmeCorp\n", encoding="utf-8")
        (self.plain / "p.json").write_text('{"body": "ProjectFalcon"}', encoding="utf-8")
        ep = "repos/acme-user/public-repo/issues"
        for cmd in ("gh api %s -f title=x -f body='AcmeCorp'" % ep,
                    "gh api %s --raw-field body='AcmeCorp'" % ep,
                    "gh api %s -F body=@%s/b.md" % (ep, self.plain),
                    "gh api -X PATCH %s/1 --field body=AcmeCorp" % ep,
                    "gh api %s --input %s/p.json" % (ep, self.plain),
                    "gh api /%s -f body=\"$B\"" % ep):
            with self.subTest(cmd=cmd):
                self.assertBlocked(self.bash(cmd))

    def test_patch_with_an_input_file_written_beforehand(self):
        """本文の書き換え手順（JSON を別の呼び出しで書き出し、`--input <file>` で PATCH）が通る."""
        (self.plain / "clean.json").write_text('{"body": "書き換え後の本文"}', encoding="utf-8")
        (self.plain / "dirty.json").write_text('{"body": "AcmeCorp の件"}', encoding="utf-8")
        for ep in ("repos/acme-user/public-repo/issues/1", "repos/acme-user/public-repo/issues/comments/9"):
            with self.subTest(ep=ep):
                self.assertPassed(self.bash("gh api -X PATCH %s --input %s/clean.json" % (ep, self.plain)))
                self.assertBlocked(self.bash("gh api -X PATCH %s --input %s/dirty.json" % (ep, self.plain)))

    def test_gist_is_always_checked(self):
        (self.plain / "g.md").write_text("AcmeCorp\n", encoding="utf-8")
        (self.plain / "clean.md").write_text("きれい\n", encoding="utf-8")
        for cmd in ("gh gist create %s/g.md" % self.plain,
                    "gh gist create -d 'AcmeCorp' %s/clean.md" % self.plain,
                    "gh gist edit abc123 -a %s/g.md" % self.plain,
                    "gh api gists -f description=AcmeCorp"):
            with self.subTest(cmd=cmd):
                self.assertBlocked(self.bash(cmd))
        self.assertPassed(self.bash("gh gist create %s/clean.md" % self.plain))

    def test_attachments_need_confirmation(self):
        (self.plain / "shot.png").write_bytes(b"\x89PNG\r\n")
        self.assertBlocked(self.bash("gh pr comment 1 %s --attach %s/shot.png" % (PUB, self.plain)),
                           "画像・動画の添付")


class DestinationTest(PublicLeakBase):
    """宛先は owner ではなく visibility で決め、決められなければ公開先として扱う."""

    def test_third_party_public_repository_is_checked(self):
        self.assertBlocked(self.bash("gh issue create -R other-org/oss-lib -t t -b AcmeCorp"))

    def test_unknown_visibility_is_treated_as_public(self):
        self.assertBlocked(self.bash("gh issue create -R acme-user/nowhere -t t -b AcmeCorp"),
                           "visibility を取得できず")
        self.assertPassed(self.bash("gh issue create -R acme-user/nowhere -t t -b clean"))

    def test_issue_url_argument_names_the_destination(self):
        self.assertBlocked(self.bash(
            "gh issue comment https://github.com/acme-user/public-repo/issues/3 -b AcmeCorp", cwd=self.priv))
        self.assertPassed(self.bash(
            "gh issue comment https://github.com/acme-user/private-repo/issues/3 -b AcmeCorp"))

    def test_gh_repo_environment_variable(self):
        self.assertPassed(self.bash("GH_REPO=acme-user/private-repo gh issue create -t t -b AcmeCorp"))
        self.assertBlocked(self.bash("GH_REPO=acme-user/public-repo gh issue create -t t -b AcmeCorp",
                                     cwd=self.priv))
        self.assertBlocked(self.bash('GH_REPO="$R" gh issue create -t t -b AcmeCorp', cwd=self.priv))

    def test_an_upstream_remote_makes_the_implicit_destination_public(self):
        """gh は upstream を origin より優先する。origin が private でも upstream が公開なら検査する."""
        self.git("remote", "add", "upstream", "https://github.com/acme-user/upstream-pub.git", cwd=self.priv)
        self.assertBlocked(self.bash("gh issue create -t t -b AcmeCorp", cwd=self.priv))

    def test_set_default_resolution_is_a_candidate(self):
        self.git("config", "remote.origin.gh-resolved", "other-org/oss-lib", cwd=self.priv)
        self.assertBlocked(self.bash("gh issue create -t t -b AcmeCorp", cwd=self.priv))

    def test_outside_a_git_repository(self):
        self.assertBlocked(self.bash("gh issue create -t t -b AcmeCorp", cwd=self.plain))
        self.assertBlocked(self.bash("cd /tmp && gh issue create %s -t t -b AcmeCorp" % PUB, cwd=self.plain))

    def test_graphql_mutation_and_numeric_repository_ids(self):
        q = 'mutation { addComment(input: {subjectId: "X", body: "AcmeCorp"}) { clientMutationId } }'
        self.assertBlocked(self.bash("gh api graphql -f query='%s'" % q, cwd=self.priv))
        self.assertBlocked(self.bash("gh api repositories/123/issues -f body=AcmeCorp", cwd=self.priv))

    def test_placeholders_follow_the_cwd_remotes(self):
        cmd = "gh api 'repos/{owner}/{repo}/issues' -f body=AcmeCorp"
        self.assertPassed(self.bash(cmd, cwd=self.priv))
        self.assertBlocked(self.bash(cmd, cwd=self.repo))

    def test_ssh_host_alias_is_resolved(self):
        self.git("remote", "set-url", "origin", "git@github-work:acme-user/private-repo.git", cwd=self.priv)
        self.assertPassed(self.bash("gh issue create -t t -b AcmeCorp", cwd=self.priv))

    def test_visibility_is_cached_with_a_ttl(self):
        cmd = "gh issue create %s -t t -b clean" % PUB
        self.assertPassed(self.bash(cmd))
        self.assertPassed(self.bash(cmd))
        api = [c for c in self.gh_calls() if c.startswith("api repos/acme-user/public-repo")]
        self.assertEqual(len(api), 1, "キャッシュが効いていない: %s" % api)
        self.set_config(visibility_ttl_seconds=0)
        self.assertPassed(self.bash(cmd))
        api = [c for c in self.gh_calls() if c.startswith("api repos/acme-user/public-repo")]
        self.assertEqual(len(api), 2, "TTL 切れで引き直していない")


class ExecutionFormTest(PublicLeakBase):
    """gh / git の呼び方を変えてもすり抜けない."""

    def test_wrappers_and_paths(self):
        for head in ("env gh", "command gh", "/opt/homebrew/bin/gh", "\\gh", '"g"h', "g''h",
                     "nohup gh", "timeout 5 gh", "FOO=1 gh", "exec gh", "time gh", "env -i gh",
                     "sudo -u me gh", "nice -n 5 gh"):
            cmd = "%s issue create %s -t t -b AcmeCorp" % (head, PUB)
            with self.subTest(cmd=cmd):
                self.assertBlocked(self.bash(cmd))

    def test_gh_aliases(self):
        self.fixture["aliases"] = {"ic": "issue create", "co": "pr checkout",
                                   "post": "!gh issue create -R acme-user/public-repo -t t -b AcmeCorp"}
        self._save_fixture()
        self.assertBlocked(self.bash("gh ic %s -t t -b AcmeCorp" % PUB))
        self.assertBlocked(self.bash("gh post"))
        self.assertPassed(self.bash("gh co 12"))

    def test_xargs_and_find_exec(self):
        (self.plain / "b.md").write_text("AcmeCorp\n", encoding="utf-8")
        for cmd, why in (("echo 1 | xargs -I{} gh issue comment {} %s --body AcmeCorp" % PUB, "辞書"),
                         ("echo AcmeCorp | xargs gh issue comment 1 %s --body" % PUB, "xargs の入力"),
                         ("find %s -name b.md -exec gh issue comment 1 %s --body-file {} \\;"
                          % (self.plain, PUB), "find -exec")):
            with self.subTest(cmd=cmd):
                self.assertBlocked(self.bash(cmd), why)

    def test_nested_shells_and_eval(self):
        for cmd in ("bash -c 'gh issue create %s -t t -b AcmeCorp'" % PUB,
                    "sh -lc \"gh issue create %s -t t -b AcmeCorp\"" % PUB,
                    "eval \"gh issue create %s -t t -b AcmeCorp\"" % PUB,
                    "bash <<'EOF'\ngh issue create %s -t t -b AcmeCorp\nEOF" % PUB,
                    "echo \"$(gh issue create %s -t t -b AcmeCorp)\"" % PUB):
            with self.subTest(cmd=cmd):
                self.assertBlocked(self.bash(cmd))

    def test_inline_interpreter_scripts_are_unresolvable(self):
        cmd = "python3 -c \"import subprocess; subprocess.run(['gh', 'issue', 'create', '-b', x])\""
        self.assertBlocked(self.bash(cmd))
        # プロセスを起動しない解析スクリプトは止めない（字面に gh / git push があるだけ）
        self.assertPassed(self.bash("python3 - <<'EOF'\nprint('git push の回数を数える')\nEOF"))

    def test_dynamic_command_names(self):
        self.assertBlocked(self.bash("G=gh; $G issue create %s -t t -b AcmeCorp" % PUB))
        self.assertBlocked(self.bash("\"$(command -v gh)\" issue create %s -t t -b clean" % PUB))

    def test_run_in_terminal_is_inspected_like_bash(self):
        res = self.tool("mcp__terminal__run_in_terminal",
                        {"command": "gh issue create %s -t t -b AcmeCorp" % PUB})
        self.assertBlocked(res)
        (self.plain / "b.md").write_text("AcmeCorp\n", encoding="utf-8")
        res = self.tool("mcp__terminal__run_in_terminal",
                        {"command": "gh issue create %s -t t -F b.md" % PUB, "cwd": str(self.plain)})
        self.assertBlocked(res)
        self.assertPassed(self.tool("mcp__terminal__run_in_terminal", {"command": "npm run dev"}))


class PushTest(PublicLeakBase):
    """git push は rev-list の範囲の追加行・メッセージ・ファイル名・ref 名・tag を見る."""

    def test_clean_push_passes(self):
        self.commit(self.repo, "feat: きれい")
        self.assertPassed(self.bash("git push"))

    def test_commit_message(self):
        self.commit(self.repo, "fix: AcmeCorp 向けの修正")
        self.assertBlocked(self.bash("git push origin main"), "メッセージ")

    def test_added_line_reports_the_file_line(self):
        self.commit(self.repo, "feat: x", "src.txt", "a\nb\nProjectFalcon\n")
        res = self.bash("git push")
        self.assertBlocked(res, "3 行目")

    def test_file_name_is_checked_and_masked(self):
        self.commit(self.repo, "feat: x", "acmecorp-notes.txt", "x\n")
        res = self.bash("git push")
        self.assertBlocked(res, "ファイルの名前")
        self.assertNotIn("notes.txt", res.stderr, "語を含むパスを伏せていない")

    def test_branch_name(self):
        self.git("checkout", "-qb", "feature/acmecorp-1", cwd=self.repo)
        self.commit(self.repo, "feat: x")
        self.assertBlocked(self.bash("git push -u origin feature/acmecorp-1"))

    def test_own_team_ids_in_the_branch_and_message_pass_when_allowed(self):
        self.git("checkout", "-qb", "fix/ZZT-83-timeout", cwd=self.repo)
        self.commit(self.repo, "fix: timeout を直す（ZZT-83・ZZT-78）")
        cmd = "git push -u origin fix/ZZT-83-timeout"
        self.assertBlocked(self.bash(cmd), "チーム形式")
        self.set_config(allowed_id_prefixes=["ZZT"])
        self.assertPassed(self.bash(cmd))

    def test_tags(self):
        self.git("tag", "-a", "v1", "-m", "release for AcmeCorp", cwd=self.repo)
        for cmd in ("git push --tags", "git push --follow-tags", "git push --mirror",
                    "git push origin tag v1", "git push origin refs/tags/v1"):
            with self.subTest(cmd=cmd):
                self.assertBlocked(self.bash(cmd))

    def test_tags_already_on_the_remote_are_not_rescanned(self):
        """`--follow-tags` のたびに公開済みの古い tag を蒸し返さない（remote に同名 tag がある）."""
        bare = self.tmp / "bare.git"
        self.git("init", "-q", "--bare", str(bare), cwd=self.tmp)
        self.git("tag", "-a", "v0", "-m", "old release for AcmeCorp", cwd=self.repo)
        self.git("push", "-q", str(bare), "refs/tags/v0", cwd=self.repo)
        self.git("remote", "add", "mirror", str(bare), cwd=self.repo)
        self.git("remote", "set-url", "--push", "mirror", "git@github.com:acme-user/public-repo.git",
                 cwd=self.repo)
        self.git("fetch", "-q", "mirror", cwd=self.repo)
        self.assertPassed(self.bash("git push mirror main --follow-tags"))
        self.git("tag", "-a", "v1", "-m", "new release for AcmeCorp", cwd=self.repo)
        self.assertBlocked(self.bash("git push mirror main --follow-tags"))

    def test_author_email(self):
        self.git("config", "user.email", "dev@acmecorp.example", cwd=self.repo)
        self.commit(self.repo, "feat: x")
        self.assertBlocked(self.bash("git push"))

    def test_git_dash_c_and_aliases(self):
        self.commit(self.repo, "fix: AcmeCorp")
        self.assertBlocked(self.bash("git -C %s push" % self.repo, cwd=self.plain))
        self.git("config", "alias.p", "push", cwd=self.repo)
        self.assertBlocked(self.bash("git p"))
        self.git("config", "alias.sp", "!git push origin main", cwd=self.repo)
        self.assertBlocked(self.bash("git sp"))

    def test_push_to_a_gist_remote_is_checked(self):
        self.git("remote", "add", "g", "https://gist.github.com/0123abcd.git", cwd=self.priv)
        self.commit(self.priv, "AcmeCorp")
        self.assertBlocked(self.bash("git push g main", cwd=self.priv))

    def test_commit_and_push_in_one_command_is_blocked(self):
        res = self.bash("git add -A && git commit -m x && git push")
        self.assertBlocked(res, "前段")

    def test_scan_limit_blocks(self):
        self.set_config(max_push_commits=1)
        self.commit(self.repo, "a")
        self.commit(self.repo, "b", "g.txt")
        self.assertBlocked(self.bash("git push"), "上限")

    def test_binary_content_is_not_scanned_but_its_name_is(self):
        (self.repo / "img.bin").write_bytes(b"\x00\x01AcmeCorp\x00")
        self.git("add", "-A", cwd=self.repo)
        self.git("commit", "-qm", "bin", cwd=self.repo)
        self.assertPassed(self.bash("git push"))

    def test_gh_pr_create_pushes_the_head_branch(self):
        self.commit(self.repo, "fix: AcmeCorp")
        self.assertBlocked(self.bash("gh pr create -t t -b clean"))

    def test_gh_pr_create_after_an_opaque_command(self):
        """前段が commit を作りうるなら、hook の時点の履歴では push される範囲を決められない."""
        self.assertPassed(self.bash("gh pr create -t t -b clean"))
        self.assertBlocked(self.bash("make release && gh pr create -t t -b clean"), "前段")

    def test_repo_create_public_with_source_push(self):
        self.commit(self.priv, "fix: AcmeCorp")
        self.assertBlocked(self.bash(
            "gh repo create acme-user/new --public --source . --push", cwd=self.priv))
        self.assertPassed(self.bash(
            "gh repo create acme-user/new --private --source . --push", cwd=self.priv))

    def test_repo_visibility_change_to_public_is_always_blocked(self):
        self.assertBlocked(self.bash("gh repo edit acme-user/private-repo --visibility public "
                                     "--accept-visibility-change-consequences"), "公開に切り替える")
        self.assertBlocked(self.bash("gh api -X PATCH repos/acme-user/private-repo -F private=false"))

    def test_repo_sync_from_a_private_source(self):
        self.assertBlocked(self.bash(
            "gh repo sync acme-user/public-repo --source acme-user/private-repo"))

    def test_deadline_blocks_instead_of_timing_out(self):
        """hook の timeout は「止めずに通る」ので、その前に自分で打ち切って止める."""
        slow = self.tmp / "slowbin"
        slow.mkdir()
        real_git = shutil.which("git")
        _write_exec(slow / "git", '#!/bin/sh\nif [ "$1" = "log" ]; then exec sleep 5; fi\nexec %s "$@"\n' % real_git)
        self.set_config(deadline_seconds=1.0)
        self.commit(self.repo, "feat: x")
        res = self.bash("git push", _env={"PATH": "%s:%s:%s" % (slow, self.bin, os.environ["PATH"])})
        self.assertBlocked(res, "秒以内")


class McpTest(PublicLeakBase):
    def test_github_write_tools(self):
        base = {"owner": "acme-user", "repo": "public-repo"}
        cases = {
            "create_issue": {"title": "t", "body": "AcmeCorp"},
            "add_issue_comment": {"issue_number": 1, "body": "AcmeCorp"},
            "update_issue": {"issue_number": 1, "title": "AcmeCorp"},
            "create_pull_request": {"title": "t", "body": "AcmeCorp", "head": "x", "base": "main"},
            "create_pull_request_review": {"pull_number": 1, "event": "COMMENT", "body": "AcmeCorp"},
            "merge_pull_request": {"pull_number": 1, "commit_title": "AcmeCorp"},
            "push_files": {"branch": "main", "message": "m",
                           "files": [{"path": "a.txt", "content": "ProjectFalcon"}]},
            "create_or_update_file": {"path": "a.txt", "content": "AcmeCorp", "message": "m",
                                      "branch": "main"},
            "create_branch": {"branch": "feature/acmecorp"},
        }
        for name, extra in cases.items():
            with self.subTest(tool=name):
                self.assertBlocked(self.tool("mcp__github__" + name, {**base, **extra}))

    def test_private_destination_and_read_tools_pass(self):
        self.assertPassed(self.tool("mcp__github__create_issue",
                                    {"owner": "acme-user", "repo": "private-repo", "body": "AcmeCorp"}))
        self.assertPassed(self.tool("mcp__github__get_issue",
                                    {"owner": "acme-user", "repo": "public-repo", "issue_number": 1}))

    def test_create_repository(self):
        self.assertBlocked(self.tool("mcp__github__create_repository",
                                     {"name": "x", "description": "AcmeCorp", "private": False}))
        self.assertPassed(self.tool("mcp__github__create_repository",
                                    {"name": "x", "description": "AcmeCorp", "private": True}))


class ConfirmTest(PublicLeakBase):
    """汎用パターン・添付・作業文脈は「確認」。ask は対話でしか効かないので既定は block."""

    def test_team_style_ids(self):
        res = self.bash("gh issue comment 1 %s --body 'ZZT-12 の件'" % PUB)
        self.assertBlocked(res, "チーム形式")
        self.assertNotIn("ZZT", res.stderr, "ID そのものを出している")
        self.assertPassed(self.bash("gh issue comment 1 %s --body 'UTF-8 と ADR-3 と TEAM-123'" % PUB))
        self.set_config(allowed_id_prefixes=["ZZT"])
        self.assertPassed(self.bash("gh issue comment 1 %s --body 'ZZT-12'" % PUB))

    def test_replacement_placeholders_pass_with_the_recommended_prefixes(self):
        """README の推奨設定（自分の接頭辞 + 公開 issue の置き換え用の架空接頭辞）で置き換え済みの本文が通る."""
        self.assertPassed(self.bash("gh issue comment 1 %s --body '業務 PR-3 と PR-4'" % PUB))
        body = "業務 PR-3 と TEAM-123・TEAMB-45・TEAME-6 の件。計測は m2.jsonl、パスは ~/<work>/src/x.ts"
        cmd = "gh issue comment 1 %s --body '%s'" % (PUB, body)
        self.assertBlocked(self.bash(cmd), "チーム形式")
        self.set_config(allowed_id_prefixes=["ZZT", "TEAM", "TEAMB", "TEAMC", "TEAMD", "TEAME"])
        self.assertPassed(self.bash(cmd))
        self.assertBlocked(self.bash("gh issue comment 1 %s --body 'ZZQ-12'" % PUB), "チーム形式")

    def test_user_paths_and_other_repository_prs(self):
        self.assertBlocked(self.bash("gh issue comment 1 %s --body '/Users/someone/x'" % PUB))
        self.assertPassed(self.bash("gh issue comment 1 %s --body '/Users/Shared/x'" % PUB))
        self.assertBlocked(self.bash("gh issue comment 1 %s --body 'widget-app PR #12'" % PUB))
        self.assertPassed(self.bash("gh issue comment 1 %s --body 'public-repo PR #12'" % PUB))

    def test_ask_only_in_interactive_sessions(self):
        self.set_config(confirm_action="ask")
        cmd = "gh issue comment 1 %s --body 'ZZT-12'" % PUB
        res = self.bash(cmd)
        self.assertEqual(res.returncode, 0, res)
        out = json.loads(res.stdout)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")
        # 公式 docs: auto / dontAsk / bypassPermissions / subagent では ask が defer に落ちて通る
        for extra in ({"permission_mode": "auto"}, {"permission_mode": "dontAsk"},
                      {"permission_mode": "bypassPermissions"}, {"agent_id": "a1"},
                      {"permission_mode": None}):
            with self.subTest(extra=extra):
                self.assertBlocked(self.bash(cmd, **extra))

    def test_cross_context_from_a_private_repository_of_another_owner(self):
        work = self.make_repo("work", "git@github.com:acme-work/secret-app.git")
        res = self.bash("gh issue create %s -t t -b 'きれい'" % PUB, cwd=work)
        self.assertBlocked(res, "匿名化")
        # 同じ owner の private リポジトリからなら文脈規則は掛けない
        self.assertPassed(self.bash("gh issue create %s -t t -b 'きれい'" % PUB, cwd=self.priv))


class DictionaryAndConfigTest(PublicLeakBase):
    def test_missing_dictionary_blocks_public_writes_by_default(self):
        self.dict_path.unlink()
        self.assertBlocked(self.bash("gh issue create %s -t t -b clean" % PUB), "辞書が無い")
        self.assertPassed(self.bash("gh issue create %s -t t -b clean" % PRIV))

    def test_missing_dictionary_can_warn(self):
        self.dict_path.unlink()
        self.set_config(on_missing_dict="warn")
        res = self.bash("gh issue create %s -t t -b clean" % PUB)
        self.assertEqual(res.returncode, 0, res)
        self.assertIn("systemMessage", res.stdout)
        self.assertBlocked(self.bash("gh issue comment 1 %s -b '集計 @ %s'" % (PUB, HOSTNAME)))

    def test_dictionary_from_the_environment(self):
        other = self.tmp / "other-terms.txt"
        other.write_text("Globex\n", encoding="utf-8")
        res = self.bash("gh issue create %s -t t -b Globex" % PUB,
                        _env={"GUARDRAIL_SENSITIVE_DICT": str(other)})
        self.assertEqual(res.returncode, 2, res)

    def test_unreadable_dictionary_or_config_blocks(self):
        self.dict_path.unlink()
        self.dict_path.mkdir()
        self.assertBlocked(self.bash("gh issue create %s -t t -b clean" % PUB), "辞書を読めない")
        self.dict_path.rmdir()
        self.dict_path.write_text(DICT, encoding="utf-8")
        self.config_path.write_text("{broken", encoding="utf-8")
        self.assertBlocked(self.bash("gh issue create %s -t t -b clean" % PUB), "設定ファイルを読めない")


class BypassTest(PublicLeakBase):
    """agent がガードの設定・辞書・キャッシュを変えて抜けようとしたら、宛先に関係なく止める."""

    def test_guard_variables(self):
        for cmd in ("GUARDRAIL_SENSITIVE_DICT=/dev/null gh issue create %s -t t -b x" % PRIV,
                    "export GUARDRAIL_SENSITIVE_DICT=/dev/null",
                    "env GUARDRAIL_PUBLIC_LEAK_CONFIG=/tmp/c.json gh issue list",
                    "env -u GUARDRAIL_SENSITIVE_DICT gh issue list",
                    "unset GUARDRAIL_SENSITIVE_DICT",
                    "launchctl setenv GUARDRAIL_SENSITIVE_DICT /dev/null",
                    "echo 'export GUARDRAIL_SENSITIVE_DICT=/dev/null' >> ~/.zshrc"):
            with self.subTest(cmd=cmd):
                self.assertBlocked(self.bash(cmd), "ガードの迂回を止めた")

    def test_writing_the_guard_files(self):
        for cmd in ("rm ~/.config/guardrail-protect/sensitive-terms.txt",
                    "cd ~/.config/guardrail-protect && rm sensitive-terms.txt",
                    "echo '{}' > ~/.cache/guardrail-protect/visibility.json",
                    "echo '{}' > $HOME/.config/guardrail-protect/public-leak-guard.json",
                    "mv ~/.config/guardrail-protect/sensitive-terms.txt /tmp/x"):
            with self.subTest(cmd=cmd):
                self.assertBlocked(self.bash(cmd), "ガードの迂回を止めた")

    def test_writing_the_review_publish_config(self):
        """publish のたびに実行される post-publish を agent が置けないようにする（label・salt も）."""
        for cmd in ("printf '#!/bin/sh\\n' > ~/.config/claude-review/post-publish",
                    "chmod +x ~/.config/claude-review/post-publish",
                    "echo m9 > $HOME/.config/claude-review/machine-label",
                    "rm -f ~/.config/claude-review/salt",
                    "cd ~/.config/claude-review && tee post-publish < /dev/null",
                    "echo 'export CLAUDE_REVIEW_CONFIG_DIR=/tmp/x' >> ~/.zshrc"):
            with self.subTest(cmd=cmd):
                self.assertBlocked(self.bash(cmd), "ガードの迂回を止めた")
        cfg = self.tmp / "review-cfg"
        res = self.bash("echo x > %s/post-publish" % cfg, _env={"CLAUDE_REVIEW_CONFIG_DIR": str(cfg)})
        self.assertBlocked(res, "publish 設定")

    def test_reading_the_review_config_and_isolated_runs_pass(self):
        for cmd in ("cat ~/.config/claude-review/machine-label", "ls -la ~/.config/claude-review/",
                    "CLAUDE_REVIEW_CONFIG_DIR=/tmp/x bash publish-review-event.sh --dry-run",
                    "echo x > /tmp/claude-review-notes.txt"):
            with self.subTest(cmd=cmd):
                self.assertPassed(self.bash(cmd))


class FailClosedTest(PublicLeakBase):
    def test_missing_python_blocks_only_relevant_commands(self):
        path = self.path_with_only("tr", "mktemp", "rm")
        res = self.bash("gh issue create %s -t t -b clean" % PUB, _env={"PATH": path})
        self.assertEqual(res.returncode, 2, res)
        self.assertIn("python3", res.stderr)
        # cwd や一時ディレクトリ名に gh / git が入っていても、コマンドが無関係なら通す
        # （以前は入力 JSON 全体を見ていて、乱数の一時ディレクトリ名で落ちることがあった）
        odd = self.tmp / "tmpghgit-github"
        odd.mkdir()
        res = self.bash("ls -la", cwd=odd, _env={"PATH": path})
        self.assertEqual(res.returncode, 0, res)

    def test_a_broken_detector_blocks(self):
        alt = self.tmp / "plugin-copy"
        shutil.copytree(PLUGIN_ROOT, alt)
        (alt / "hooks" / "scripts" / "detect-public-leak.py").write_text("raise SystemExit(1)\n",
                                                                         encoding="utf-8")
        res = self.bash("gh issue create %s -t t -b clean" % PUB,
                        _env={"CLAUDE_PLUGIN_ROOT": str(alt)})
        self.assertEqual(res.returncode, 2, "検出器が壊れても通している: %r" % res)
        res = self.bash("ls", _env={"CLAUDE_PLUGIN_ROOT": str(alt)})
        self.assertEqual(res.returncode, 0)

    def test_malformed_input(self):
        res = self.run_hook(raw='{"tool_name":"Bash","tool_input":{"command":"gh issue create -b',
                            cwd=self.tmp, env_extra=self.env())
        self.assertEqual(res.returncode, 2, res)
        res = self.run_hook(raw="{ not json", cwd=self.tmp, env_extra=self.env())
        self.assertEqual(res.returncode, 0, res)

    def test_hooks_json_registration(self):
        data = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        entries = [(m["matcher"], h) for m in data["hooks"]["PreToolUse"] for h in m["hooks"]
                   if "public-leak-guard.sh" in " ".join(h.get("args", []))]
        matchers = {m for m, _ in entries}
        self.assertIn("Bash", matchers)
        import re
        other = [m for m in matchers if m != "Bash"]
        self.assertEqual(len(other), 1)
        for tool in ("mcp__github__create_issue", "mcp__terminal__run_in_terminal",
                     "mcp__claude-in-chrome__computer"):
            self.assertTrue(re.fullmatch(other[0], tool), tool)
        self.assertTrue(all(h["timeout"] == 10 for _, h in entries), "hook の timeout は 10 秒")


class BrowserTest(PublicLeakBase):
    def test_browser_input_is_opt_in(self):
        inp = {"action": "type", "text": "AcmeCorp"}
        self.assertPassed(self.tool("mcp__claude-in-chrome__computer", inp))
        self.set_config(browser_input="block")
        self.assertBlocked(self.tool("mcp__claude-in-chrome__computer", inp))
        self.assertPassed(self.tool("mcp__claude-in-chrome__computer", {"action": "type", "text": "hi"}))


class PrePushHookTest(PublicLeakBase):
    """人の push を止める git hook（同じ検出器を呼ぶ）."""

    def prepush(self, url: str, repo: Path, script: Path = PREPUSH):
        sha = self.git("rev-parse", "HEAD", cwd=repo).strip()
        base = self.git("rev-parse", "origin/main", cwd=repo).strip()
        line = "refs/heads/main %s refs/heads/main %s\n" % (sha, base)
        return subprocess.run(["bash", str(script), "origin", url], input=line, cwd=str(repo),
                              capture_output=True, text=True, env=scrub(**self.env()), timeout=60)

    def test_blocks_a_dictionary_word_and_passes_clean_pushes(self):
        url = "git@github.com:acme-user/public-repo.git"
        self.commit(self.repo, "feat: きれい")
        self.assertEqual(self.prepush(url, self.repo).returncode, 0)
        self.commit(self.repo, "fix: AcmeCorp", "g.txt")
        res = self.prepush(url, self.repo)
        self.assertEqual(res.returncode, 1, res)
        self.assertNotIn("AcmeCorp", res.stderr)

    def test_private_remote_passes(self):
        self.commit(self.priv, "fix: AcmeCorp")
        self.assertEqual(self.prepush("https://github.com/acme-user/private-repo.git",
                                      self.priv).returncode, 0)

    def test_works_through_a_symlink(self):
        link = self.tmp / "hooks-dir" / "pre-push"
        link.parent.mkdir()
        link.symlink_to(PREPUSH)
        self.commit(self.repo, "fix: AcmeCorp", "g.txt")
        res = self.prepush("git@github.com:acme-user/public-repo.git", self.repo, script=link)
        self.assertEqual(res.returncode, 1, res)
        self.assertNotIn("検出器を起動できない", res.stderr)


class SelfProtectionTest(unittest.TestCase):
    """辞書・設定・キャッシュを既存の自己保護（perl / pre-config-guard）にも足した."""

    def detect(self, command: str, env: dict | None = None) -> str:
        proc = subprocess.run(["perl", str(PERL_DETECTOR)], input=command, capture_output=True,
                              text=True, timeout=20, env=env)
        self.assertEqual(proc.returncode, 0)
        return proc.stdout.strip()

    def test_perl_detector_blocks_writes(self):
        for cmd in ("rm ~/.config/guardrail-protect/sensitive-terms.txt",
                    "echo x > ~/.cache/guardrail-protect/visibility.json",
                    "sed -i '' s/a/b/ /h/.config/guardrail-protect/public-leak-guard.json",
                    "cp /dev/null ./public-leak-guard.json"):
            with self.subTest(cmd=cmd):
                self.assertIn("self-modification", self.detect(cmd))

    def test_perl_detector_follows_the_dictionary_env_path(self):
        env = dict(os.environ, GUARDRAIL_SENSITIVE_DICT="/vault/terms-x.txt")
        self.assertIn("self-modification", self.detect("rm /vault/terms-x.txt", env))
        self.assertEqual(self.detect("cat /vault/terms-x.txt", env), "")

    def test_perl_detector_blocks_review_config_writes(self):
        for cmd in ("echo x > ~/.config/claude-review/post-publish",
                    "rm -f /h/.config/claude-review/salt",
                    "cp /tmp/hook /h/.config/claude-review/post-publish",
                    "mv /tmp/cfg /h/.config/claude-review"):
            with self.subTest(cmd=cmd):
                self.assertIn("self-modification", self.detect(cmd))
        env = dict(os.environ, CLAUDE_REVIEW_CONFIG_DIR="/vault/review-cfg/")
        self.assertIn("self-modification", self.detect("tee /vault/review-cfg/post-publish", env))
        self.assertEqual(self.detect("cat /vault/review-cfg/salt", env), "")
        self.assertEqual(self.detect("cat ~/.config/claude-review/machine-label"), "")
        self.assertEqual(self.detect("echo x > /tmp/claude-review-notes.txt"), "")

    def test_perl_detector_allows_reads(self):
        for cmd in ("cat ~/.config/guardrail-protect/sensitive-terms.txt",
                    "grep x ~/.config/guardrail-protect/public-leak-guard.json"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.detect(cmd), "")


class PreCommitGuardPrefilterTest(HookTestCase):
    """perl 層に届く前の事前フィルタが publish 設定 dir への書き込みを落とさない."""
    PLUGIN = "guardrail-protect"
    SCRIPT = "hooks/scripts/pre-commit-guard.sh"

    def test_review_config_writes_reach_the_detector(self):
        res = self.run_hook({"tool_name": "Bash", "tool_input": {"command": "rm -f ~/.config/claude-review/salt"}})
        self.assertEqual(res.returncode, 2, res)
        res = self.run_hook({"tool_name": "Bash", "tool_input": {"command": "tee /vault/review-cfg/post-publish"}},
                            env_extra={"CLAUDE_REVIEW_CONFIG_DIR": "/vault/review-cfg"})
        self.assertEqual(res.returncode, 2, res)
        res = self.run_hook({"tool_name": "Bash", "tool_input": {"command": "cat ~/.config/claude-review/salt"}})
        self.assertEqual(res.returncode, 0, res)
        self.assertNotIn("Unexpected", res.stderr)

    def test_an_env_path_lets_only_commands_naming_it_reach_the_detector(self):
        """環境変数で場所を指しても、その名前を含まないコマンドは perl に渡さない（事前フィルタ）.

        perl を「常に検出する」スタブに差し替えて、届いたかを exit code で見る。
        """
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        alt = Path(tmp.name) / "plugin-copy"
        shutil.copytree(PLUGIN_ROOT, alt)
        (alt / "hooks" / "scripts" / "detect-commit-bypass.pl").write_text(
            'print "stub-detected\\n";\n', encoding="utf-8")
        env = {"CLAUDE_PLUGIN_ROOT": str(alt), "GUARDRAIL_SENSITIVE_DICT": "/vault/terms-x.txt"}
        res = self.run_hook({"tool_name": "Bash", "tool_input": {"command": "ls -la"}}, env_extra=env)
        self.assertEqual(res.returncode, 0, res)
        res = self.run_hook({"tool_name": "Bash", "tool_input": {"command": "cat /vault/terms-x.txt"}},
                            env_extra=env)
        self.assertEqual(res.returncode, 2, "スタブに届いていない（差し替えが効いていない）: %r" % res)


class PreConfigGuardProtectionTest(HookTestCase):
    PLUGIN = "guardrail-protect"
    SCRIPT = "hooks/scripts/pre-config-guard.sh"

    def test_guard_files_are_protected(self):
        for path in ("/h/.config/guardrail-protect/sensitive-terms.txt",
                     "/h/.config/guardrail-protect/public-leak-guard.json",
                     "/h/.cache/guardrail-protect/visibility.json"):
            with self.subTest(path=path):
                res = self.run_hook({"tool_name": "Write", "tool_input": {"file_path": path, "content": ""}})
                self.assertEqual(res.returncode, 2, res)

    def test_the_env_dictionary_path_is_protected(self):
        res = self.run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/vault/terms-x.txt"}},
                            env_extra={"GUARDRAIL_SENSITIVE_DICT": "/vault/terms-x.txt"})
        self.assertEqual(res.returncode, 2, res)
        res = self.run_hook({"tool_name": "Edit", "tool_input": {"file_path": "/p/src/other.txt"}},
                            env_extra={"GUARDRAIL_SENSITIVE_DICT": "/vault/terms-x.txt"})
        self.assertEqual(res.returncode, 0, "変数が設定されているだけで無関係なパスを止めている: %r" % res)

    def test_guard_variables_in_shell_rc_or_settings_are_blocked(self):
        for path, key in (("/h/.zshrc", "new_string"), ("/h/.claude/settings.json", "content")):
            with self.subTest(path=path):
                res = self.run_hook({"tool_name": "Edit" if key == "new_string" else "Write",
                                     "tool_input": {"file_path": path,
                                                    key: "export GUARDRAIL_SENSITIVE_DICT=/dev/null"}})
                self.assertEqual(res.returncode, 2, res)

    def test_review_publish_config_is_protected(self):
        for path in ("/h/.config/claude-review/post-publish", "/h/.config/claude-review/machine-label",
                     "/h/.config/claude-review/salt"):
            with self.subTest(path=path):
                res = self.run_hook({"tool_name": "Write", "tool_input": {"file_path": path, "content": "x"}})
                self.assertEqual(res.returncode, 2, res)
                self.assertIn("claude-review", res.stderr)
        res = self.run_hook({"tool_name": "Write",
                             "tool_input": {"file_path": "/vault/review-cfg/post-publish", "content": "x"}},
                            env_extra={"CLAUDE_REVIEW_CONFIG_DIR": "/vault/review-cfg"})
        self.assertEqual(res.returncode, 2, res)
        res = self.run_hook({"tool_name": "Edit", "tool_input": {
            "file_path": "/h/.zshrc", "new_string": "export CLAUDE_REVIEW_CONFIG_DIR=/tmp/x"}})
        self.assertEqual(res.returncode, 2, res)

    def test_unrelated_edits_pass(self):
        for tin in ({"file_path": "/h/.zshrc", "new_string": "export PATH=/x:$PATH"},
                    {"file_path": "/p/src/terms.txt", "new_string": "x"},
                    {"file_path": "/p/README.md", "new_string": "GUARDRAIL_SENSITIVE_DICT=~/x を設定する"},
                    {"file_path": "/p/README.md", "new_string": "CLAUDE_REVIEW_CONFIG_DIR=/tmp/x で隔離する"},
                    {"file_path": "/h/.config/claude-review-notes/x.md", "new_string": "x"}):
            with self.subTest(tin=tin):
                self.assertEqual(self.run_hook({"tool_name": "Edit", "tool_input": tin}).returncode, 0)


if __name__ == "__main__":
    unittest.main()
