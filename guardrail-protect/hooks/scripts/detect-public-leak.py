#!/usr/bin/env python3
"""公開先への業務情報送信を止める判定本体（public-leak-guard / pre-push 共通）.

モード:
  hook                      PreToolUse の入力 JSON を stdin で受けて判定する
                            （exit 0 = 通す / exit 0 + JSON = 確認を求める / exit 2 = 止める）
  pre-push <remote> <url>   git の pre-push hook（stdin に ref の行）。exit 1 で push を止める
  scan-git [--repo DIR] <rev-list 引数...>
                            人が範囲を手で検査する（上限なし）。exit 1 = 検出あり
  scan-text [FILE]          本文を事前に検査する（FILE 省略時は stdin）。exit 1 = 検出あり

**判定の軸は宛先リポジトリの visibility**（owner ではない）。`gh api repos/<o>/<r>` の
`.visibility` を ~/.cache/guardrail-protect/ に TTL 付きで持つ。**private と確定した宛先だけ
素通し**し、宛先が決められないもの（gist・graphql の node ID・`/repositories/<id>`・
リポジトリ外の cwd・API が引けない等）は公開先として検査する。

**fail-closed**: 検査対象（公開先への書き込み）と分かった後の内部エラー・時間切れ・
解決できない本文は止める。PreToolUse の hook は timeout すると**止めずに通る**（公式 docs:
"A timed-out command … hook doesn't block the tool call"）ので、hook の timeout より前に
自分で打ち切って exit 2 にする。

**語そのものは出力しない**。辞書の行番号と本文の行番号、置き換え例だけを出す。

**自己保護**（宛先に関係なく止める）: 辞書・設定・visibility キャッシュと `GUARDRAIL_*` 変数、
code-review の publish 設定 dir（`~/.config/claude-review/`。`post-publish` は publish のたびに
実行される）の Bash での書き換えと、その場所を指す変数をシェル設定・settings に書き込む操作。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import public_leak_shell as sh  # noqa: E402

#: hook の timeout（hooks.json で 10 秒）より前に必ず結論を出す
DEADLINE_SECONDS = 7.0
#: visibility 問い合わせ 1 回の上限
GH_API_TIMEOUT = 2.5

HOME = os.path.expanduser("~")

CONFIG_DEFAULTS = {
    # 辞書が無い（または有効語 0 件）ときに公開先宛てを止めるか: block | warn
    "on_missing_dict": "block",
    # 汎用パターン・添付・文脈規則（確認を求めるもの）の扱い: block | ask
    # ask は対話セッションでだけ効く（auto / dontAsk / bypassPermissions / subagent では
    # 公式に defer へ落ちて通ってしまう）。-p を hook 入力から見分けられないので既定は block
    "confirm_action": "block",
    # Linear 形式 ID の許可接頭辞（自分のチーム。例: ["YAT"]）
    "allowed_id_prefixes": [],
    # 素通しする visibility（internal を足すかは組織次第）
    "pass_visibilities": ["private"],
    "visibility_ttl_seconds": 3600,
    # push の走査上限（超えたら止める）
    "max_push_commits": 300,
    "max_push_bytes": 4000000,
    # ブラウザ操作の入力（text / value / url）を辞書で照合するか: off | block
    "browser_input": "off",
    # 自分で打ち切るまでの秒数（hook の timeout 10 秒より前。0.5〜8 に丸める）
    "deadline_seconds": DEADLINE_SECONDS,
}

#: 汎用パターンの Linear 形式 ID から外す接頭辞（規格名・例示用の置き換え語）
BUILTIN_ID_PREFIXES = {
    "ADR", "UTF", "SHA", "ISO", "RFC", "CVE", "CWE", "GHSA", "HTTP", "TLS", "SSL", "IPV",
    "ES", "ECMA", "GPT", "AES", "RSA", "PEP", "WCAG", "JSR", "JEP", "KEP", "MD", "ARM",
    "TEAM", "PROJ", "ABC", "XXX", "FOO", "BAR", "MYAPP", "EXAMPLE", "ISSUE", "ID", "PR",
}

#: 置き換え例（出力に添える。語そのものは出さない代わりにこれを示す）
REPLACEMENTS = (
    "業務リポジトリ名 → 「業務リポジトリ A」（issue をまたいで同じ記号を使う）",
    "業務チームの Linear ID → 「TEAM-123」",
    "マシン名 → 会社 PC は「m2」、個人機は「m1」",
    "業務の PR 番号 → 「PR #N」（同じ PR を何度も指すなら「業務 PR-3」のような固定の呼び名）",
    "ローカルの絶対パス → 「~/…」か「<repo>/…」",
    "業務コードの識別子 → 「canDoX のような boolean 命名」のように一般化する",
)

GUARD_VAR_RE = re.compile(r"^GUARDRAIL_[A-Za-z0-9_]*$")
GUARD_VAR_TEXT_RE = re.compile(r"GUARDRAIL_[A-Za-z0-9_]*\s*=")
RC_FILE_RE = re.compile(r"(?:^|/)(?:\.zshrc|\.zshenv|\.zprofile|\.zlogin|\.bashrc|\.bash_profile|"
                        r"\.profile|\.envrc|settings(?:\.local)?\.json|\.claude\.json)$")
#: 自己保護するパス（辞書・設定・visibility キャッシュ）
PROTECTED_DIR_RE = re.compile(r"(?:^|/)\.(?:config|cache)/guardrail-protect(?:/|$)")
PROTECTED_BASENAMES = ("public-leak-guard.json",)
#: code-review の publish 設定 dir（post-publish・machine-label・salt）。post-publish は publish の
#: たびに切り離して実行されるので、agent が置くと以後の publish で黙って走る
REVIEW_CONFIG_DIR_RE = re.compile(r"(?:^|/)\.config/claude-review(?:/|$)")
#: その dir の場所を変える変数（code-review と計測リポジトリの同期スクリプトが読む）
REVIEW_CONFIG_ENVS = ("CLAUDE_REVIEW_CONFIG_DIR", "REVIEW_METRICS_CONFIG_DIR")
#: シェル設定・settings に書き込まれると迂回になる変数
RC_VAR_TEXT_RE = re.compile(r"(?:GUARDRAIL_[A-Za-z0-9_]*|CLAUDE_REVIEW_CONFIG_DIR|"
                            r"REVIEW_METRICS_CONFIG_DIR)\s*=")
#: gh / git push を含みうるインラインスクリプト（中身を解けないので公開の可能性として扱う）
MENTIONS_PUBLISH_RE = re.compile(
    r"(?<![\w.-])gh(?![\w.-])[\s\S]{0,80}?\b(issue|pr|api|gist|release|repo|project|label)\b"
    r"|(?<![\w.-])git(?![\w.-])[\s\S]{0,80}?\bpush\b")

#: 辞書照合の前に消す値（SRI の integrity・長い base64・16 進ハッシュ）。
#: 3 文字の語が `sha512-…` の中に偶然現れて push が止まる誤検知を避ける（語境界でも防げない:
#: `-` と `/` に挟まれると境界になる）
NOISE_RE = re.compile(r"\bsha(?:1|256|384|512)-[A-Za-z0-9+/=]+|[A-Za-z0-9+/]{40,}={0,2}|\b[0-9a-f]{12,}\b")
#: インラインスクリプトがプロセスを起動しているか（gh / git push の字面だけの解析スクリプトを止めない）
SPAWN_RE = re.compile(r"subprocess|os\.system|popen|execSync|execFileSync|spawn|child_process|"
                      r"\bsystem\s*\(|\bexec\s*\(|Open3|%x\{|`|do shell script|Deno\.Command|Bun\.spawn")
LINEAR_ID_RE = re.compile(r"\b([A-Z]{2,6})-(\d+)\b")
USER_PATH_RE = re.compile(r"/Users/([^/\s'\"`<>$]+)/")
USER_PATH_PLACEHOLDERS = {"shared", "<name>", "name", "user", "username", "you", "me", "xxx",
                          "foo", "example", "runner", "$user", "${user}", "<user>", "..."}
OTHER_PR_RE = re.compile(r"([A-Za-z0-9][A-Za-z0-9._/-]{1,99})(?:\s*の)?\s+PR\s*#\s*(\d+)")
OTHER_PR_STOPWORDS = {"the", "this", "that", "a", "an", "my", "our", "your", "draft", "open",
                      "closed", "merged", "same", "new", "old", "previous", "next", "upstream",
                      "each", "related", "linked", "parent", "child", "its", "their", "and", "or"}


class Deadline(Exception):
    pass


class GuardError(Exception):
    """設定・辞書が読めない等、検査を続けられない（公開先なら止める）."""


def _on_alarm(signum, frame):
    raise Deadline()


# ============================================================================
# 設定・辞書
# ============================================================================

def config_path():
    return os.environ.get("GUARDRAIL_PUBLIC_LEAK_CONFIG") or \
        os.path.join(HOME, ".config", "guardrail-protect", "public-leak-guard.json")


def load_config():
    cfg = dict(CONFIG_DEFAULTS)
    path = config_path()
    if not os.path.exists(path):
        return cfg
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise GuardError("設定ファイルを読めない（%s）" % type(e).__name__)
    if not isinstance(data, dict):
        raise GuardError("設定ファイルが JSON オブジェクトではない")
    for key, value in data.items():
        if key in cfg:
            cfg[key] = value
    return cfg


def dict_path():
    return os.environ.get("GUARDRAIL_SENSITIVE_DICT") or \
        os.path.join(HOME, ".config", "guardrail-protect", "sensitive-terms.txt")


def normalize(text):
    return unicodedata.normalize("NFKC", text).casefold()


class Term:
    __slots__ = ("lineno", "norm", "boundary", "regex")

    def __init__(self, lineno, term, boundary):
        self.lineno = lineno
        self.norm = normalize(term)
        self.boundary = boundary
        self.regex = re.compile(r"(?<![0-9a-z_])" + re.escape(self.norm) + r"(?![0-9a-z_])") \
            if boundary else None

    def hit(self, norm_line):
        if self.regex is not None:
            return bool(self.regex.search(norm_line))
        return self.norm in norm_line


def load_terms(path):
    """1 行 1 語。`#` 始まりはコメント、`w:` 接頭辞は語境界照合、3 文字未満は無視.

    ファイルが無ければ None、読めなければ GuardError（fail-closed）。
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except (OSError, UnicodeDecodeError) as e:
        raise GuardError("辞書を読めない（%s）" % type(e).__name__)
    terms = []
    for i, raw in enumerate(lines, 1):
        t = raw.strip()
        if not t or t.startswith("#"):
            continue
        boundary = t.startswith("w:")
        if boundary:
            t = t[2:].strip()
        if len(t) < 3:
            continue
        terms.append(Term(i, t, boundary))
    return terms


def local_hostname():
    """`hostname -s`（暗黙の辞書語）. 取れなければ None."""
    try:
        out = subprocess.run(["hostname", "-s"], capture_output=True, text=True, timeout=2)
        name = out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        name = ""
    if not name:
        import socket
        name = socket.gethostname().split(".")[0]
    if len(name) < 3 or name.lower() in ("localhost",):
        return None
    return name


# ============================================================================
# 照合
# ============================================================================

class Finding:
    __slots__ = ("severity", "kind", "label", "line", "dict_line", "detail")

    def __init__(self, severity, kind, label="", line=None, dict_line=None, detail=""):
        self.severity = severity      # block | confirm
        self.kind = kind
        self.label = label
        self.line = line
        self.dict_line = dict_line
        self.detail = detail

    def render(self):
        where = self.label
        if self.line is not None:
            where += " の %d 行目" % self.line
        if self.kind == "dict":
            return "辞書 %d 行目の語が %s にある" % (self.dict_line, where)
        if self.kind == "host":
            return "このマシンのホスト名（暗黙の辞書語）が %s にある" % where
        if self.kind == "linear":
            return "許可リスト外のチーム形式の ID（%s）が %s にある" % (self.detail, where)
        if self.kind == "userpath":
            return "ローカルのユーザーパス（/Users/<name>/）が %s にある" % where
        if self.kind == "otherpr":
            return "別リポジトリ名つきの PR 番号（<名前> PR #N）が %s にある" % where
        return "%s%s" % (self.detail, ("（" + where + "）") if where else "")


class Matcher:
    def __init__(self, terms, hostname, cfg):
        self.terms = terms or []
        self.host = normalize(hostname) if hostname else None
        allowed = cfg.get("allowed_id_prefixes") or []
        self.allowed_prefixes = BUILTIN_ID_PREFIXES | {str(p).upper() for p in allowed}

    def secret_hits(self, text):
        """(kind, dict_line) の列（辞書とホスト名だけ）."""
        norm = normalize(text)
        hits = []
        for t in self.terms:
            if t.hit(norm):
                hits.append(("dict", t.lineno))
        if self.host and self.host in norm:
            hits.append(("host", None))
        return hits

    def safe(self, label):
        """出力に載せる文字列（パス・ファイル名）に語が入っていれば伏せる."""
        if label and self.secret_hits(label):
            return "<伏せ字 sha=%s>" % hashlib.sha256(label.encode("utf-8")).hexdigest()[:8]
        return label

    def scan(self, text, label, generic=True, dest_name=None, linenos=None):
        """`linenos` を渡すと i 行目を linenos[i-1] 行目として報告する（diff の追加行用）."""
        out = []
        safe_label = self.safe(label)
        for i, line in enumerate(text.splitlines() or [text], 1):
            lineno = linenos[i - 1] if linenos and i - 1 < len(linenos) else i
            for kind, dline in self.secret_hits(NOISE_RE.sub(" ", line)):
                out.append(Finding("block", kind, safe_label, lineno, dline))
            if not generic:
                continue
            for m in LINEAR_ID_RE.finditer(line):
                if m.group(1) not in self.allowed_prefixes:
                    out.append(Finding("confirm", "linear", safe_label, lineno,
                                       detail="接頭辞 %d 文字" % len(m.group(1))))
            for m in USER_PATH_RE.finditer(line):
                if m.group(1).lower() not in USER_PATH_PLACEHOLDERS:
                    out.append(Finding("confirm", "userpath", safe_label, lineno))
            for m in OTHER_PR_RE.finditer(line):
                name = m.group(1).rstrip("/")
                base = name.split("/")[-1]
                if name.lower() in OTHER_PR_STOPWORDS or not re.search(r"[-_./]", name):
                    continue
                if dest_name and base.lower() == dest_name.lower():
                    continue
                out.append(Finding("confirm", "otherpr", safe_label, lineno))
        return out


# ============================================================================
# サブプロセス
# ============================================================================

class Budget:
    def __init__(self, seconds):
        self.end = time.monotonic() + seconds

    def left(self):
        return self.end - time.monotonic()


BUDGET = Budget(DEADLINE_SECONDS)


def run(args, cwd=None, timeout=3.0, env=None):
    """(rc, stdout)。起動できない・時間切れは rc=None."""
    t = min(timeout, max(0.2, BUDGET.left() - 0.5))
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=t,
                           env=env, errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None, ""
    return p.returncode, p.stdout


def git(args, cwd, timeout=3.0):
    return run(["git"] + args, cwd=cwd, timeout=timeout)


def git_toplevel(cwd):
    if not cwd or not os.path.isdir(cwd):
        return None
    rc, out = git(["rev-parse", "--show-toplevel"], cwd)
    return out.strip() if rc == 0 and out.strip() else None


# ============================================================================
# 宛先
# ============================================================================

class Dest:
    """kind: repo / candidates / gist / local / unknown / newrepo."""

    def __init__(self, kind, repos=None, reason="", vis=None):
        self.kind = kind
        self.repos = repos or []      # [(host, "owner/repo")]
        self.reason = reason
        self.vis = vis                # newrepo のときに指定された visibility

    def owners(self):
        return {slug.split("/")[0].lower() for _, slug in self.repos}

    def names(self):
        return {slug.split("/")[1] for _, slug in self.repos}

    def describe(self):
        if self.kind in ("repo", "candidates") and self.repos:
            return ", ".join("%s/%s" % r for r in self.repos)
        if self.kind == "gist":
            return "gist（secret でも URL で誰でも読めるので公開先として扱う）"
        return "宛先を特定できない（%s）" % (self.reason or "公開先として検査")


def parse_repo_arg(value, default_host="github.com"):
    """`OWNER/REPO` / `HOST/OWNER/REPO` / URL → (host, slug) or None."""
    v = value.strip()
    m = re.match(r"^(?:https?://|ssh://git@|git@)?([^/:]+\.[^/:]+)[/:]([^/]+)/([^/#?]+?)"
                 r"(?:\.git)?(?:/.*)?$", v)
    if m and "." in m.group(1):
        return m.group(1).lower(), "%s/%s" % (m.group(2), m.group(3))
    m = re.match(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?$", v)
    if m:
        return default_host, "%s/%s" % (m.group(1), m.group(2))
    return None


def ssh_resolved_host(alias):
    rc, out = run(["ssh", "-G", alias], timeout=1.5)
    if rc != 0:
        return None
    for line in out.splitlines():
        if line.startswith("hostname "):
            return line.split(None, 1)[1].strip().lower()
    return None


def parse_remote_url(url):
    """→ ("github", host, slug) / ("gist", id) / ("local", path) / ("other", url)."""
    u = url.strip()
    m = re.match(r"^(?:https?://(?:[^@/]+@)?|ssh://(?:[^@/]+@)?|git://|(?:[^@/]+@))"
                 r"gist\.github\.com[:/]([0-9A-Za-z]+?)(?:\.git)?/?$", u)
    if m:
        return ("gist", m.group(1))
    m = re.match(r"^(?:https?|git|ssh)://(?:[^@/]+@)?([^/:]+)(?::\d+)?/([^/]+)/([^/]+?)(?:\.git)?/?$", u)
    if not m:
        m = re.match(r"^(?:[^@/]+@)?([^/:]+):([^/]+)/([^/]+?)(?:\.git)?/?$", u)
        if m and ("/" in m.group(1) or len(m.group(1)) == 1):
            m = None       # Windows ドライブ / ローカルパス
    if m:
        host = m.group(1).lower()
        slug = "%s/%s" % (m.group(2), m.group(3))
        if host == "github.com" or host == "ssh.github.com":
            return ("github", "github.com", slug)
        if host.startswith("gist."):
            return ("gist", m.group(3))
        resolved = ssh_resolved_host(host) if re.match(r"^[A-Za-z0-9_.-]+$", host) else None
        if resolved in ("github.com", "ssh.github.com"):
            return ("github", "github.com", slug)
        return ("other", u)
    if u.startswith("file://") or u.startswith("/") or u.startswith(".") or u.startswith("~"):
        return ("local", u)
    return ("other", u)


def remote_repos(repo_dir):
    """cwd のリポジトリの remote から gh が選びうる宛先の候補を列挙する.

    gh の暗黙の解決は GH_REPO → `gh repo set-default`（remote.<name>.gh-resolved）→
    remote の優先順（upstream > github > origin > その他）なので、**候補はこの repo の
    GitHub remote 全部**。どれを選ばれても private と言えるときだけ private にする。
    """
    rc, out = git(["config", "--get-regexp", r"^remote\..*\.(url|pushurl|gh-resolved)$"], repo_dir)
    repos, others = [], False
    if rc not in (0, 1):
        return None, True
    for line in out.splitlines():
        key, _, value = line.partition(" ")
        if key.endswith(".gh-resolved"):
            if value.strip() not in ("base", "") and "/" in value:
                r = parse_repo_arg(value)
                if r:
                    repos.append(r)
            continue
        kind = parse_remote_url(value)
        if kind[0] == "github":
            repos.append((kind[1], kind[2]))
        elif kind[0] != "local":
            others = True
    uniq = []
    for r in repos:
        key = (r[0], r[1].lower())
        if key not in [(a, b.lower()) for a, b in uniq]:
            uniq.append(r)
    return uniq, others


class Visibility:
    def __init__(self, cfg):
        self.cfg = cfg
        self.path = os.path.join(HOME, ".cache", "guardrail-protect", "visibility.json")
        self.cache = None
        self.memo = {}
        self.failed = set()       # visibility を取得できなかった宛先（案内に使う）

    def _load(self):
        if self.cache is None:
            try:
                with open(self.path, encoding="utf-8") as fh:
                    data = json.load(fh)
                self.cache = data if isinstance(data, dict) else {}
            except (OSError, ValueError):
                self.cache = {}
        return self.cache

    def _store(self, key, vis):
        cache = self._load()
        cache[key] = {"v": vis, "t": int(time.time())}
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".%d.tmp" % os.getpid()
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(cache, fh)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def lookup(self, host, slug):
        """"public" / "private" / "internal" / None（不明）."""
        key = "%s/%s" % (host, slug.lower())
        if key in self.memo:
            return self.memo[key]
        ttl = int(self.cfg.get("visibility_ttl_seconds") or 0)
        entry = self._load().get(key)
        if isinstance(entry, dict) and entry.get("v") in ("public", "private", "internal") \
                and isinstance(entry.get("t"), (int, float)) and time.time() - entry["t"] < ttl:
            self.memo[key] = entry["v"]
            return entry["v"]
        vis = None
        if BUDGET.left() > GH_API_TIMEOUT + 1.0:
            args = ["gh", "api"]
            if host != "github.com":
                args += ["--hostname", host]
            args += ["repos/%s" % slug, "--jq", ".visibility // (if .private then \"private\" else \"public\" end)"]
            env = dict(os.environ, GH_PROMPT_DISABLED="1", NO_COLOR="1")
            rc, out = run(args, timeout=GH_API_TIMEOUT, env=env)
            v = out.strip().lower()
            if rc == 0 and v in ("public", "private", "internal"):
                vis = v
                self._store(key, v)
        if vis is None:
            self.failed.add(key)
        self.memo[key] = vis
        return vis

    def is_public(self, dest):
        """True = 公開先として検査する / False = 素通し."""
        passing = set(self.cfg.get("pass_visibilities") or ["private"])
        if dest.kind == "local":
            return False
        if dest.kind == "newrepo":
            return not (dest.vis in passing)
        if dest.kind in ("repo", "candidates") and dest.repos:
            for host, slug in dest.repos:
                if self.lookup(host, slug) not in passing:
                    return True
            return False
        return True


# ============================================================================
# 解析の文脈
# ============================================================================

class Op:
    """公開先への書き込み 1 件."""

    def __init__(self, what, dest):
        self.what = what
        self.dest = dest
        self.texts = []           # [(label, text, generic)]
        self.unresolved = []      # 理由（公開先なら止める）
        self.confirms = []        # (detail)（公開先なら確認を求める）
        self.blocks = []          # 宛先に関係なく… ではなく公開先なら止める固定理由
        self.push = None          # PushSpec

    def text(self, label, text, generic=True):
        if text:
            self.texts.append((label, text, generic))


class PushSpec:
    def __init__(self, repo_dir, revs, exclude_remote, refnames, tags):
        self.repo_dir = repo_dir
        self.revs = revs
        self.exclude_remote = exclude_remote   # remote 名（None なら全 remote を除外しない）
        self.refnames = refnames
        self.tags = tags


UNKNOWN = object()


class Ctx:
    def __init__(self, cwd, session_cwd, env=None):
        self.cwd = cwd                 # None = 静的に決まらない
        self.session_cwd = session_cwd
        self.env = dict(env or {})     # 同じコマンド内の静的な代入
        self.vfs = {}                  # 同じコマンド内で書かれたファイル → 内容（UNKNOWN = 不明）
        self.opaque = False            # 前段に内容を変えうるコマンドがあった
        self.opaque_reason = ""
        self.ops = []
        self.bypass = []               # ガードの迂回（宛先に関係なく止める）

    def child(self):
        c = Ctx(self.cwd, self.session_cwd, self.env)
        c.vfs = self.vfs
        c.opaque = self.opaque
        c.opaque_reason = self.opaque_reason
        c.ops = self.ops
        c.bypass = self.bypass
        return c

    def abspath(self, path):
        if path.startswith("~/") or path == "~":
            return os.path.normpath(HOME + path[1:])
        if os.path.isabs(path):
            return os.path.normpath(path)
        if self.cwd is None:
            return None
        return os.path.normpath(os.path.join(self.cwd, path))


def env_for_resolution(ctx, local):
    env = {"HOME": HOME, "USER": os.environ.get("USER", ""), "TMPDIR": os.environ.get("TMPDIR", "")}
    if ctx.cwd:
        env["PWD"] = ctx.cwd
    env.update(ctx.env)
    env.update(local or {})
    return env


def word_value(w, ctx, env):
    """語の値（置換は `cat <file>` / heredoc / echo / printf だけ解く）. 解けなければ None."""
    out = []
    for p in w.parts:
        if p.kind == "lit":
            out.append(p.text)
        elif p.kind == "param" and p.name is not None and env.get(p.name) is not None:
            out.append(env[p.name])
        elif p.kind == "cmdsub":
            v = script_output(p.script, ctx, env)
            if v is None:
                return None
            out.append(v.rstrip("\n"))
        else:
            return None
    value = "".join(out)
    if w.tilde and (value == "~" or value.startswith("~/")):
        value = HOME + value[1:]
    return value


def read_file(path_word, ctx, env, stdin=None):
    """ファイル引数の中身 → (text or None, 理由)."""
    if path_word is None:
        return None, "ファイルの指定が無い"
    if path_word.parts and path_word.parts[0].kind == "procsub":
        v = script_output(path_word.parts[0].script, ctx, env)
        return (v, "") if v is not None else (None, "プロセス置換の出力を静的に決められない")
    value = word_value(path_word, ctx, env)
    if value is None:
        return None, "ファイルのパスに展開がある"
    if path_word.glob and not path_word.quoted:
        return None, "ファイルのパスにグロブがある"
    if value == "-":
        if stdin is None:
            return None, "標準入力（-）の中身を静的に決められない"
        return stdin, ""
    path = ctx.abspath(value)
    if path is None:
        return None, "相対パスの基準（cd 先）が静的に決まらない"
    if path in ctx.vfs:
        v = ctx.vfs[path]
        if v is UNKNOWN:
            return None, "同じコマンド内で書かれるファイルで、中身を静的に決められない"
        return v, ""
    if ctx.opaque:
        return None, "同じコマンド内の前段（%s）がファイルを書き換えうる" % ctx.opaque_reason
    try:
        if os.path.getsize(path) > 2_000_000:
            return None, "ファイルが大きすぎる"
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None, "ファイルを読めない（存在しない・権限）"
    try:
        return data.decode("utf-8"), ""
    except UnicodeDecodeError:
        return None, "バイナリで中身を検査できない"


def stdin_of(cmd, ctx, env):
    """コマンドの標準入力（heredoc / here-string / < file / パイプ元）. 解けなければ None."""
    for r in cmd.redirs:
        if r.fd not in (None, "0"):
            continue
        if r.op in ("<<", "<<-") and r.heredoc is not None:
            if r.heredoc.dynamic:
                return None
            return r.heredoc.body or ""
        if r.op == "<<<":
            v = word_value(r.target, ctx, env)
            return None if v is None else v + "\n"
        if r.op == "<":
            v, _ = read_file(r.target, ctx, env)
            return v
    if cmd.piped and cmd.prev is not None:
        return command_output(cmd.prev, ctx, env)
    return None


def command_output(cmd, ctx, env):
    """`cat` / `echo` / `printf` / `< file` の出力. それ以外は None."""
    words = cmd.words
    if not words:
        if any(r.op == "<" for r in cmd.redirs):   # `$(< file)`
            return stdin_of(cmd, ctx, env)
        return None
    name = word_value(words[0], ctx, env)
    if name is None:
        return None
    base = os.path.basename(name)
    args = words[1:]
    if base == "cat":
        files = [a for a in args if (word_value(a, ctx, env) or "").startswith("-") is False]
        if any(word_value(a, ctx, env) is None for a in args):
            return None
        if not files:
            return stdin_of(cmd, ctx, env)
        out = []
        for a in files:
            v, _ = read_file(a, ctx, env, stdin=stdin_of(cmd, ctx, env) if word_value(a, ctx, env) == "-" else None)
            if v is None:
                return None
            out.append(v)
        return "".join(out)
    if base == "echo":
        vals = [word_value(a, ctx, env) for a in args]
        if any(v is None for v in vals):
            return None
        newline = True
        while vals and re.fullmatch(r"-[neE]+", vals[0]):
            if "n" in vals[0]:
                newline = False
            vals = vals[1:]
        return " ".join(vals) + ("\n" if newline else "")
    if base == "printf":
        vals = [word_value(a, ctx, env) for a in args]
        if not vals or any(v is None for v in vals):
            return None
        fmt, rest = vals[0], vals[1:]
        if fmt in ("%s", "%s\n", "%s\\n"):
            return "".join(v + ("\n" if fmt != "%s" else "") for v in rest)
        if not rest and "%" not in fmt.replace("%%", ""):
            return fmt.replace("\\n", "\n").replace("\\t", "\t").replace("%%", "%")
        return None
    return None


def script_output(cmds, ctx, env):
    real = [c for c in cmds if c.words or c.redirs]
    if len(real) != 1:
        return None
    return command_output(real[-1], ctx, env)


# ============================================================================
# 走査（コマンド列 → Op）
# ============================================================================

RESERVED = {"!", "if", "then", "else", "elif", "fi", "do", "done", "while", "until", "for",
            "in", "case", "esac", "{", "}", "function", "select", "coproc", "[[", "]]"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
INTERPRETERS = {"python", "python3", "node", "ruby", "perl", "php", "deno", "bun", "osascript",
                "lua", "Rscript", "pwsh"}
#: 前段にあってもファイル内容・git 履歴を変えないコマンド
SAFE_COMMANDS = {"cd", "pushd", "popd", "echo", "printf", "cat", "true", "false", ":", "test",
                 "[", "ls", "pwd", "mkdir", "sleep", "export", "set", "unset", "head", "tail",
                 "wc", "grep", "rg", "which", "type", "command", "date", "env", "tee", "cp",
                 "mv", "diff", "cmp", "stat", "file", "jq", "sort", "uniq", "basename",
                 "dirname", "realpath", "readlink", "hostname", "whoami", "id", "uname"}
SAFE_GIT = {"status", "log", "diff", "show", "rev-parse", "remote", "branch", "config",
            "fetch", "ls-files", "ls-remote", "describe", "blame", "grep", "shortlog",
            "cat-file", "for-each-ref", "merge-base", "symbolic-ref", "name-rev",
            "rev-list", "add", "push", "worktree", "version", "help"}
WRITERS = {"rm", "mv", "cp", "tee", "truncate", "dd", "ln", "install", "shred", "chmod",
           "chown", "touch", "unlink", "rmdir", "sed", "perl"}


def static_words(words, ctx, env):
    return [word_value(w, ctx, env) for w in words]


def check_guard_assign(name, ctx, how):
    if GUARD_VAR_RE.match(name or ""):
        ctx.bypass.append("ガードの制御変数を %s している" % how)


def protected_kind(path):
    """自己保護の対象なら出力に使う名前、対象外なら None."""
    if not path:
        return None
    guard = "ガードの辞書・設定・キャッシュ"
    if PROTECTED_DIR_RE.search(path):
        return guard
    base = os.path.basename(path)
    if base in PROTECTED_BASENAMES:
        return guard
    norm = os.path.normpath(path)
    for env_name in ("GUARDRAIL_SENSITIVE_DICT", "GUARDRAIL_PUBLIC_LEAK_CONFIG"):
        v = os.environ.get(env_name)
        if v and os.path.normpath(os.path.expanduser(v)) == norm:
            return guard
    review = "code-review の publish 設定（post-publish・machine-label・salt）"
    if REVIEW_CONFIG_DIR_RE.search(path):
        return review
    for env_name in REVIEW_CONFIG_ENVS:
        v = os.environ.get(env_name)
        d = os.path.normpath(os.path.expanduser(v)) if v else ""
        if len(d) > 1 and (norm == d or norm.startswith(d + "/")):
            return review
    return None


def walk(cmds, ctx, depth=0):
    if depth > 6:
        ctx.bypass.append("入れ子が深すぎて解析できない")
        return
    for cmd in cmds:
        # 置換の中のコマンドも実行される（`$(gh issue create …)`）
        for w in [x for _, x in cmd.assigns] + cmd.words + [r.target for r in cmd.redirs if r.target]:
            for p in w.substitutions():
                walk(p.script, ctx.child(), depth + 1)
        for r in cmd.redirs:
            hd = r.heredoc
            if hd is not None and not hd.quoted and hd.body and ("$(" in hd.body or "`" in hd.body) \
                    and MENTIONS_PUBLISH_RE.search(hd.body):
                ctx.ops.append(_unresolved_op("heredoc 内のコマンド置換", "heredoc の中で gh / git push を実行している"))
        local = {}
        for name, w in cmd.assigns:
            check_guard_assign(name, ctx, "前置きで設定")
            local[name] = word_value(w, ctx, env_for_resolution(ctx, local))
        env = env_for_resolution(ctx, local)
        check_redirect_targets(cmd, ctx, env)
        if not cmd.words:
            ctx.env.update(local)
            track_writes(cmd, ctx, env)
            continue
        analyze_command(cmd, list(cmd.words), env, ctx, depth)
        track_writes(cmd, ctx, env)


def _unresolved_op(what, reason):
    op = Op(what, Dest("unknown", reason="コマンドを静的に解析できない"))
    op.unresolved.append(reason)
    return op


def check_redirect_targets(cmd, ctx, env):
    texts = [w.literal_text() for w in cmd.words]
    texts += [r.heredoc.body or "" for r in cmd.redirs if r.heredoc is not None]
    mentions_guard_var = any(RC_VAR_TEXT_RE.search(t) for t in texts)
    for r in cmd.redirs:
        if r.op in (">", ">>", ">|") or (r.op == ">&" and r.target is not None and
                                          not re.fullmatch(r"\d+|-", r.target.raw)):
            v = word_value(r.target, ctx, env)
            p = ctx.abspath(v) if v else None
            kind = protected_kind(p)
            if kind:
                ctx.bypass.append("%sをリダイレクトで書き換えている" % kind)
            if p and mentions_guard_var and RC_FILE_RE.search(p):
                ctx.bypass.append("ガードの制御変数か publish 設定の場所をシェル設定・settings に書き込んでいる")


def track_writes(cmd, ctx, env):
    """同じコマンド内で後から読まれるファイルの中身を追う（TOCTOU 対策）."""
    name = word_value(cmd.words[0], ctx, env) if cmd.words else None
    base = os.path.basename(name) if name else None
    for r in cmd.redirs:
        if r.fd in (None, "1", "&") and r.op in (">", ">>", ">|"):
            v = word_value(r.target, ctx, env)
            if v is None:
                ctx.opaque, ctx.opaque_reason = True, "書き込み先が静的に決まらないリダイレクト"
                continue
            p = ctx.abspath(v)
            if p is None:
                ctx.opaque, ctx.opaque_reason = True, "基準の決まらない相対パスへの書き込み"
                continue
            content = command_output(cmd, ctx, env)
            if content is None:
                ctx.vfs[p] = UNKNOWN
            elif r.op == ">>":
                prev = ctx.vfs.get(p)
                if prev is UNKNOWN:
                    continue
                if prev is None:
                    prev, _ = read_file(sh_lit_word(p), ctx, env)
                    if prev is None and os.path.exists(p):
                        ctx.vfs[p] = UNKNOWN
                        continue
                ctx.vfs[p] = (prev or "") + content
            else:
                ctx.vfs[p] = content
    if base is None:
        if cmd.words:
            ctx.opaque, ctx.opaque_reason = True, "コマンド名が静的に決まらない"
        return
    args = cmd.words[1:]
    vals = static_words(args, ctx, env)
    if base == "tee":
        content = stdin_of(cmd, ctx, env)
        append = any(v in ("-a", "--append") for v in vals if v)
        for v in vals:
            if v is None:
                ctx.opaque, ctx.opaque_reason = True, "tee の書き込み先が静的に決まらない"
            elif not v.startswith("-"):
                p = ctx.abspath(v)
                if p:
                    ctx.vfs[p] = UNKNOWN if (content is None or append) else content
        return
    if base in ("cp", "mv", "install"):
        paths = [v for v in vals if v is not None and not v.startswith("-")]
        if len(paths) != len([v for v in vals if v is None or not v.startswith("-")]) or len(paths) < 2:
            ctx.opaque, ctx.opaque_reason = True, "%s の引数が静的に決まらない" % base
            return
        dst = ctx.abspath(paths[-1])
        if dst and os.path.isdir(dst):
            dst = os.path.join(dst, os.path.basename(paths[0]))
        src_content = None
        if len(paths) == 2:
            src_content, _ = read_file(sh_lit_word(paths[0]), ctx, env)
        if dst:
            ctx.vfs[dst] = UNKNOWN if src_content is None else src_content
        return
    if base in SAFE_COMMANDS:
        return
    if base == "gh" and not ({"checkout", "clone", "sync", "develop", "--clone", "--checkout"}
                             & {v for v in vals if v}):
        return
    if base == "git":
        sub = git_subcommand([v for v in vals])
        if sub in SAFE_GIT:
            return
    ctx.opaque, ctx.opaque_reason = True, base


def sh_lit_word(text):
    w = sh.Word()
    w.add_lit(text, quoted=True)
    w.quoted = True
    w.raw = text
    return w


def git_subcommand(vals):
    i = 0
    while i < len(vals):
        v = vals[i]
        if v is None:
            return None
        if v in ("-C", "-c", "--git-dir", "--work-tree", "--namespace"):
            i += 2
            continue
        if v.startswith("-"):
            i += 1
            continue
        return v
    return None


def strip_wrappers(words, ctx, env):
    """command / env / xargs / find -exec などを剥がす → (words, extra) .

    extra: {"xargs": bool}（末尾に標準入力由来の引数が付く）/ {"find": bool}（{} がパスになる）
    """
    extra = {}
    for _ in range(8):
        while words and word_value(words[0], ctx, env) in RESERVED:
            words = words[1:]
        if not words:
            return words, extra
        name = word_value(words[0], ctx, env)
        if name is None:
            return words, extra
        base = os.path.basename(name).lstrip("\\")
        vals = static_words(words, ctx, env)
        if base in ("command", "builtin", "exec", "nohup", "caffeinate", "unbuffer", "time",
                    "noglob", "nocorrect"):
            i = 1
            while i < len(words) and (vals[i] or "").startswith("-"):
                i += 2 if vals[i] == "-a" and base == "exec" else 1
            words = words[i:]
            continue
        if base in ("nice", "stdbuf", "sudo", "doas", "timeout", "gtimeout", "chronic"):
            i = 1
            while i < len(words) and (vals[i] or "").startswith("-"):
                if vals[i] in ("-n", "-u", "-g", "-s", "-k") and base in ("nice", "sudo", "timeout", "gtimeout"):
                    i += 2
                else:
                    i += 1
            if base in ("timeout", "gtimeout") and i < len(words):
                i += 1       # DURATION
            words = words[i:]
            continue
        if base == "env":
            i = 1
            while i < len(words):
                v = vals[i]
                if v is None:
                    break
                if v in ("-u", "--unset"):
                    check_guard_assign(vals[i + 1] if i + 1 < len(vals) else "", ctx, "env -u で解除")
                    i += 2
                    continue
                if v.startswith("--unset="):
                    check_guard_assign(v.split("=", 1)[1], ctx, "env --unset で解除")
                    i += 1
                    continue
                if v in ("-C", "--chdir", "-S", "--split-string"):
                    i += 2
                    continue
                if v.startswith("-"):
                    i += 1
                    continue
                m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", v, re.S)
                if m:
                    check_guard_assign(m.group(1), ctx, "env で設定")
                    env[m.group(1)] = m.group(2)
                    i += 1
                    continue
                break
            words = words[i:]
            continue
        if base == "xargs":
            i = 1
            replace = None
            while i < len(words):
                v = vals[i]
                if v is None or not v.startswith("-"):
                    break
                if v in ("-I", "-L", "-n", "-P", "-s", "-E", "-d", "-a", "--arg-file",
                         "--max-args", "--max-procs", "--delimiter", "--eof", "--max-lines"):
                    if v == "-I":
                        replace = vals[i + 1] if i + 1 < len(vals) else None
                    i += 2
                    continue
                if v.startswith("--replace") or (v.startswith("-i") and len(v) >= 2):
                    replace = v.split("=", 1)[1] if "=" in v else (v[2:] or "{}")
                i += 1
            words = words[i:]
            extra["xargs"] = True
            extra["replace"] = replace
            continue
        if base == "find":
            for k, v in enumerate(vals):
                if v in ("-exec", "-execdir", "-ok", "-okdir"):
                    inner = []
                    for w2, v2 in zip(words[k + 1:], vals[k + 1:]):
                        if v2 in (";", "+"):
                            break
                        inner.append(w2)
                    extra["find"] = True
                    extra["replace"] = "{}"
                    return inner, extra
            return [], extra
        return words, extra
    return words, extra


def analyze_command(cmd, words, env, ctx, depth):
    words, extra = strip_wrappers(words, ctx, env)
    if not words:
        return
    name = word_value(words[0], ctx, env)
    raw_text = " ".join(w.literal_text() for w in words)
    if name is None:
        nxt = next((v for v in static_words(words[1:], ctx, env) if v and not v.startswith("-")), None)
        if nxt in ("issue", "pr", "api", "gist", "release", "repo", "project", "label", "push"):
            ctx.ops.append(_unresolved_op("名前が静的に決まらないコマンド",
                                          "コマンド名に展開があり、gh / git push かを判定できない"))
        return
    base = os.path.basename(name).lstrip("\\")
    args = words[1:]
    vals = static_words(args, ctx, env)

    if base in ("cd", "pushd"):
        target = vals[0] if vals else HOME
        if args and target is None:
            ctx.cwd = None
        elif target in (None, "-"):
            ctx.cwd = None if target == "-" else HOME
        else:
            p = ctx.abspath(target) if not target.startswith("-") else ctx.cwd
            ctx.cwd = p
        return
    if base in ("export", "declare", "typeset", "readonly", "local", "set"):
        for w, v in zip(args, vals):
            nm = (getattr(w, "assign_name", None) or (v or "").split("=", 1)[0])
            check_guard_assign(nm, ctx, "%s で設定" % base)
            if v and "=" in v and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", v):
                k, _, val = v.partition("=")
                ctx.env[k] = val
        return
    if base == "unset":
        for v in vals:
            check_guard_assign(v or "", ctx, "unset で解除")
        return
    if base == "launchctl" and vals[:1] == ["setenv"]:
        check_guard_assign(vals[1] if len(vals) > 1 and vals[1] else "", ctx, "launchctl setenv で設定")
        return
    if base in WRITERS:
        for v in vals:
            kind = protected_kind(ctx.abspath(v) or v) if v and not v.startswith("-") else None
            if kind:
                ctx.bypass.append("%sを %s で書き換えている" % (kind, base))
                break
    if base in SHELLS:
        analyze_shell(cmd, args, vals, env, ctx, depth)
        return
    if base == "eval":
        if all(v is not None for v in vals):
            _walk_source(" ".join(vals), ctx, depth)
        elif MENTIONS_PUBLISH_RE.search(raw_text):
            ctx.ops.append(_unresolved_op("eval", "eval の中身を静的に決められない"))
        return
    if base in INTERPRETERS or re.match(r"^python3?\.\d+$", base):
        inline = [w.literal_text() for w in args]
        inline += [r.heredoc.body or "" for r in cmd.redirs if r.heredoc is not None]
        joined = "\n".join(inline)
        if MENTIONS_PUBLISH_RE.search(joined) and SPAWN_RE.search(joined):
            ctx.ops.append(_unresolved_op("%s のインラインスクリプト" % base,
                                          "スクリプトの中から gh / git push を呼んでいて本文を検査できない"))
        return
    if base == "gh":
        analyze_gh(cmd, args, env, ctx, extra, depth)
        return
    if base == "git":
        analyze_git(cmd, args, env, ctx, depth)
        return


def _walk_source(src, ctx, depth):
    try:
        cmds = sh.parse(src)
    except sh.ParseError:
        if MENTIONS_PUBLISH_RE.search(src):
            ctx.ops.append(_unresolved_op("入れ子のスクリプト", "入れ子のスクリプトを構文解析できない"))
        return
    walk(cmds, ctx, depth + 1)


def analyze_shell(cmd, args, vals, env, ctx, depth):
    for k, v in enumerate(vals):
        if v is None:
            if MENTIONS_PUBLISH_RE.search(" ".join(a.literal_text() for a in args)):
                ctx.ops.append(_unresolved_op("シェルの -c", "シェルに渡すスクリプトを静的に決められない"))
            return
        if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", v) and not v.startswith("--"):
            if k + 1 < len(vals):
                if vals[k + 1] is None:
                    if MENTIONS_PUBLISH_RE.search(args[k + 1].literal_text()):
                        ctx.ops.append(_unresolved_op("シェルの -c", "シェルに渡すスクリプトに展開がある"))
                    return
                _walk_source(vals[k + 1], ctx, depth)
            return
        if v.startswith("-") or v.startswith("+"):
            continue
        if k > 0 and vals[k - 1] in ("-o", "+o", "-O", "+O", "--rcfile", "--init-file"):
            continue
        return          # スクリプトファイルの実行（中身は見ない。README の制限事項）
    script = stdin_of(cmd, ctx, env)
    if script is not None:
        _walk_source(script, ctx, depth)
    else:
        bodies = [r.heredoc.body or "" for r in cmd.redirs if r.heredoc is not None]
        if any(MENTIONS_PUBLISH_RE.search(b) for b in bodies):
            ctx.ops.append(_unresolved_op("シェルへの標準入力", "シェルに流すスクリプトに展開がある"))


# ============================================================================
# gh
# ============================================================================

GH_BUILTIN = {"auth", "browse", "codespace", "gist", "issue", "org", "pr", "project", "release",
              "repo", "cache", "run", "workflow", "alias", "api", "attestation", "completion",
              "config", "extension", "gpg-key", "label", "preview", "ruleset", "search",
              "secret", "ssh-key", "status", "variable", "agent-task", "copilot", "help",
              "accessibility", "licenses", "version", "discussion"}


class Spec:
    def __init__(self, text=(), files=(), attach=(), value=(), positional="ignore", editor=True):
        self.text = set(text)
        self.files = set(files)
        self.attach = set(attach)
        self.value = set(value) | {"-R", "--repo"}
        self.positional = positional
        self.editor = editor

    @property
    def takes_value(self):
        return self.text | self.files | self.attach | self.value


ISSUE_VALUE = ("-a", "--assignee", "-l", "--label", "-m", "--milestone", "-p", "--project",
               "-T", "--template", "--type", "--parent", "--blocked-by", "--blocking",
               "--add-assignee", "--remove-assignee", "--add-label", "--remove-label",
               "--add-project", "--remove-project", "--set-parent", "--duplicate-of", "-r",
               "--reason")
GH_SPECS = {
    ("issue", "create"): Spec(("-t", "--title", "-b", "--body"), ("-F", "--body-file", "--recover"),
                              ("--attach",), ISSUE_VALUE),
    ("issue", "comment"): Spec(("-b", "--body"), ("-F", "--body-file"), ("--attach",)),
    ("issue", "edit"): Spec(("-t", "--title", "-b", "--body"), ("-F", "--body-file"), (), ISSUE_VALUE),
    ("issue", "close"): Spec(("-c", "--comment"), (), (), ("-r", "--reason", "--duplicate-of")),
    ("issue", "reopen"): Spec(("-c", "--comment")),
    ("issue", "develop"): Spec(("-n", "--name"), (), (), ("-b", "--base", "--branch-repo")),
    # -T / --template はリポジトリ内のテンプレート（公開先と同じリポジトリにある）なので値として扱う
    ("pr", "create"): Spec(("-t", "--title", "-b", "--body"), ("-F", "--body-file", "--recover"),
                           ("--attach",), ("-a", "--assignee", "-B", "--base", "-H", "--head", "-l",
                                           "--label", "-m", "--milestone", "-p", "--project", "-r",
                                           "--reviewer", "-T", "--template")),
    ("pr", "comment"): Spec(("-b", "--body"), ("-F", "--body-file"), ("--attach",)),
    ("pr", "edit"): Spec(("-t", "--title", "-b", "--body"), ("-F", "--body-file"), (),
                         ("-B", "--base", "--add-assignee", "--remove-assignee", "--add-label",
                          "--remove-label", "--add-project", "--remove-project", "--add-reviewer",
                          "--remove-reviewer", "-m", "--milestone")),
    ("pr", "review"): Spec(("-b", "--body"), ("-F", "--body-file")),
    ("pr", "close"): Spec(("-c", "--comment")),
    ("pr", "reopen"): Spec(("-c", "--comment")),
    ("pr", "merge"): Spec(("-b", "--body", "-t", "--subject"), ("-F", "--body-file"), (),
                          ("-A", "--author-email", "--match-head-commit")),
    ("release", "create"): Spec(("-t", "--title", "-n", "--notes"), ("-F", "--notes-file"), (),
                                ("--target", "--discussion-category", "--notes-start-tag"),
                                positional="tag+assets"),
    ("release", "edit"): Spec(("-t", "--title", "-n", "--notes", "--tag"), ("-F", "--notes-file"), (),
                              ("--target", "--discussion-category")),
    ("release", "upload"): Spec(positional="tag+assets"),
    ("gist", "create"): Spec(("-d", "--desc", "-f", "--filename"), positional="files"),
    ("gist", "edit"): Spec(("-d", "--desc"), ("-a", "--add"), (), ("-f", "--filename", "-r", "--remove"),
                           positional="id+files"),
    ("gist", "rename"): Spec(positional="text"),
    ("repo", "create"): Spec(("-d", "--description", "-h", "--homepage"), (), (),
                             ("-g", "--gitignore", "-l", "--license", "-r", "--remote", "-s",
                              "--source", "-t", "--team", "-p", "--template"), positional="text"),
    ("repo", "edit"): Spec(("-d", "--description", "-h", "--homepage", "--add-topic"), (), (),
                           ("--visibility", "--default-branch", "--remove-topic",
                            "--squash-merge-commit-message")),
    ("repo", "rename"): Spec(positional="text"),
    ("repo", "sync"): Spec((), (), (), ("-b", "--branch", "-s", "--source")),
    ("label", "create"): Spec(("-d", "--description"), (), (), ("-c", "--color"), positional="text"),
    ("label", "edit"): Spec(("-d", "--description", "-n", "--name"), (), (), ("-c", "--color"),
                            positional="text"),
    ("issue", "transfer"): Spec(positional="text"),
}
PROJECT_WRITE = {"create", "edit", "item-create", "item-edit", "field-create", "copy", "item-add",
                 "mark-template"}
PROJECT_SPEC = Spec(("--title", "--body", "--text", "-d", "--description", "--readme", "--name",
                     "--single-select-options"), (), (),
                    ("--owner", "--id", "--project-id", "--field-id", "--number", "--format",
                     "--url", "--source-owner", "--target-owner", "--date", "--iteration-id",
                     "--single-select-option-id"))


def parse_flags(args, vals, spec):
    """→ (flags [(name, Word|None, from_eq_text)], positionals [Word])."""
    flags, pos = [], []
    i = 0
    takes = spec.takes_value
    while i < len(args):
        w, v = args[i], vals[i]
        if v is None:
            # `--body="$X"` / `-b"$X"`: 先頭の字面でフラグと分かるなら値が動的なフラグとして扱う
            head = ""
            for p in w.parts:
                if p.kind != "lit":
                    break
                head += p.text
            if head.startswith("--") and "=" in head:
                flags.append((head.split("=", 1)[0], w, None))
            elif head.startswith("-") and len(head) >= 2 and head[:2] in takes:
                flags.append((head[:2], w, None))
            else:
                pos.append(w)
            i += 1
            continue
        if v == "--":
            pos.extend(args[i + 1:])
            break
        if v.startswith("--"):
            name, eq, val = v.partition("=")
            if eq:
                flags.append((name, sh_lit_word(val), val))
            elif name in takes:
                flags.append((name, args[i + 1] if i + 1 < len(args) else None, None))
                i += 1
            else:
                flags.append((name, None, None))
            i += 1
            continue
        if v.startswith("-") and len(v) > 1:
            short = v[:2]
            if short in takes:
                if len(v) > 2:
                    flags.append((short, sh_lit_word(v[2:].lstrip("=")), v[2:]))
                else:
                    flags.append((short, args[i + 1] if i + 1 < len(args) else None, None))
                    i += 1
            else:
                found = False
                for k, ch in enumerate(v[1:], 1):
                    if "-" + ch in takes:
                        rest = v[k + 1:]
                        if rest:
                            flags.append(("-" + ch, sh_lit_word(rest), rest))
                        else:
                            flags.append(("-" + ch, args[i + 1] if i + 1 < len(args) else None, None))
                            i += 1
                        found = True
                        break
                    flags.append(("-" + ch, None, None))
                if not found:
                    pass
            i += 1
            continue
        pos.append(w)
        i += 1
    return flags, pos


_GH_ALIASES = None


def gh_aliases():
    global _GH_ALIASES
    if _GH_ALIASES is None:
        _GH_ALIASES = {}
        rc, out = run(["gh", "alias", "list"], timeout=2.0,
                      env=dict(os.environ, GH_PROMPT_DISABLED="1", NO_COLOR="1"))
        if rc == 0:
            for line in out.splitlines():
                m = re.match(r"^\s*([^\s:]+):\s*(.*)$", line)
                if m:
                    _GH_ALIASES[m.group(1)] = m.group(2).strip()
    return _GH_ALIASES


def dest_from_env(env):
    v = env.get("GH_REPO") if "GH_REPO" in env else os.environ.get("GH_REPO")
    if v is None:
        return None
    if v == "":
        return None
    r = parse_repo_arg(v)
    return Dest("repo", [r]) if r else Dest("unknown", reason="GH_REPO を解釈できない")


def implicit_dest(ctx, env):
    if "GH_REPO" in env and env["GH_REPO"] is None:
        return Dest("unknown", reason="GH_REPO に展開がある")
    d = dest_from_env(env)
    if d is not None:
        return d
    if ctx.cwd is None:
        return Dest("unknown", reason="cwd が静的に決まらない")
    top = git_toplevel(ctx.cwd)
    if top is None:
        return Dest("unknown", reason="cwd が git リポジトリの外")
    repos, _others = remote_repos(top)
    if not repos:
        return Dest("unknown", reason="GitHub の remote が無い")
    return Dest("candidates", repos, reason="cwd の remote から解決")


def url_dest(values):
    for v in values:
        if v and re.match(r"^https?://", v):
            r = parse_repo_arg(v)
            if r:
                return Dest("repo", [r])
    return None


def analyze_gh(cmd, args, env, ctx, extra, depth, alias_depth=0):
    vals = static_words(args, ctx, env)
    if not args:
        return
    group = vals[0]
    if group is None:
        if MENTIONS_PUBLISH_RE.search("gh " + " ".join(a.literal_text() for a in args)):
            ctx.ops.append(_unresolved_op("gh", "gh のサブコマンドに展開がある"))
        return
    if group not in GH_BUILTIN:
        expansion = gh_aliases().get(group)
        if expansion is not None and alias_depth < 3:
            if expansion.startswith("!"):
                _walk_source(expansion[1:], ctx, depth)
                return
            try:
                exp_words = [sh_lit_word(t) for t in shlex.split(expansion)]
            except ValueError:
                ctx.ops.append(_unresolved_op("gh alias", "gh の alias を解釈できない"))
                return
            rest = list(args[1:])
            used = set()
            out = []
            for w in exp_words:
                t = w.static()
                m = re.fullmatch(r"\$(\d+)", t or "")
                if m and int(m.group(1)) - 1 < len(rest):
                    out.append(rest[int(m.group(1)) - 1])
                    used.add(int(m.group(1)) - 1)
                else:
                    out.append(w)
            out += [w for k, w in enumerate(rest) if k not in used]
            analyze_gh(cmd, out, env, ctx, extra, depth, alias_depth + 1)
            return
        # 拡張・未知のサブコマンド: 宛先不明の書き込みとして全引数を検査する
        op = Op("gh %s" % group, dest_from_env(env) or Dest("unknown", reason="gh の拡張・未知のサブコマンド"))
        for k, (w, v) in enumerate(zip(args[1:], vals[1:])):
            if v is not None:
                op.text("gh %s の引数" % group, v)
        if any(v in ("--body", "-b", "--title", "-t", "--message", "-m") for v in vals) and \
                any(v is None for v in vals):
            op.unresolved.append("未知のサブコマンドの本文に展開がある")
        ctx.ops.append(op)
        return
    sub = vals[1] if len(vals) > 1 else None
    rest, rest_vals = args[2:], vals[2:]
    if group == "api":
        analyze_gh_api(cmd, args[1:], env, ctx)
        return
    if group == "project":
        if sub in PROJECT_WRITE:
            spec = PROJECT_SPEC
            op = Op("gh project %s" % sub, Dest("unknown", reason="Project は宛先の公開範囲を判定しない"))
            collect_gh(cmd, op, rest, rest_vals, spec, env, ctx, extra)
            ctx.ops.append(op)
        return
    if group == "repo" and sub == "fork":
        return
    key = (group, sub)
    spec = GH_SPECS.get(key)
    if spec is None:
        return       # 読み取り系・対象外
    flags, pos = parse_flags(rest, rest_vals, spec)
    fdict = {}
    for name, w, _ in flags:
        fdict.setdefault(name, []).append(w)

    def flag_val(*names):
        for n in names:
            for w in fdict.get(n, []):
                return w
        return None

    # ---- 宛先 ----
    dest = None
    repo_w = flag_val("-R", "--repo")
    if repo_w is not None:
        rv = word_value(repo_w, ctx, env)
        r = parse_repo_arg(rv) if rv else None
        dest = Dest("repo", [r]) if r else Dest("unknown", reason="--repo を静的に決められない")
    if dest is None and group in ("issue", "pr"):
        dest = url_dest([word_value(p, ctx, env) for p in pos])
    if group == "gist":
        dest = Dest("gist")
    if key == ("repo", "create"):
        vis = None
        names = {n for n, _, _ in flags}
        if "--private" in names:
            vis = "private"
        elif "--internal" in names:
            vis = "internal"
        elif "--public" in names:
            vis = "public"
        name = word_value(pos[0], ctx, env) if pos else None
        dest = Dest("newrepo", [], reason="新規リポジトリ", vis=vis)
        op = Op("gh repo create", dest)
        collect_gh(cmd, op, rest, rest_vals, spec, env, ctx, extra, flags=flags, pos=pos)
        if flag_val("-p", "--template") is not None:
            op.unresolved.append("テンプレートの中身を検査できない（テンプレートから公開リポジトリを作る）")
        src_w = flag_val("-s", "--source")
        if src_w is not None or "--push" in names:
            sv = word_value(src_w, ctx, env) if src_w is not None else "."
            src = ctx.abspath(sv) if sv else None
            if src is None:
                op.unresolved.append("--source を静的に決められない")
            else:
                op.push = PushSpec(src, ["--all"], None, [], True)
        if name is None and pos:
            op.unresolved.append("リポジトリ名に展開がある")
        ctx.ops.append(op)
        return
    if key in (("repo", "edit"), ("repo", "rename"), ("repo", "sync")):
        if pos:
            pv = word_value(pos[0], ctx, env)
            r = parse_repo_arg(pv) if pv else None
            if key != ("repo", "rename") or len(pos) > 1:
                dest = Dest("repo", [r]) if r else Dest("unknown", reason="対象リポジトリを静的に決められない")
    if dest is None:
        dest = implicit_dest(ctx, env)

    op = Op("gh %s %s" % (group, sub), dest)
    if key == ("repo", "edit"):
        vis_w = flag_val("--visibility")
        if vis_w is not None:
            vv = word_value(vis_w, ctx, env)
            if vv is None or vv.lower() == "public":
                op.blocks.append("リポジトリを公開に切り替える操作は中身を全部公開する。"
                                 "agent からは行わず、人が履歴を確認してから手で切り替える")
                op.dest = Dest("unknown", reason="公開化の対象")
    if key == ("repo", "sync"):
        src_w = flag_val("-s", "--source")
        if src_w is not None:
            sv = word_value(src_w, ctx, env)
            r = parse_repo_arg(sv) if sv else None
            src_dest = Dest("repo", [r]) if r else Dest("unknown", reason="--source を静的に決められない")
            op.sync_source = src_dest
        ctx.ops.append(op)
        return
    if key == ("issue", "transfer"):
        target = word_value(pos[1], ctx, env) if len(pos) > 1 else None
        r = parse_repo_arg(target) if target else None
        op.transfer_to = Dest("repo", [r]) if r else Dest("unknown", reason="移動先を静的に決められない")
        ctx.ops.append(op)
        return
    collect_gh(cmd, op, rest, rest_vals, spec, env, ctx, extra, flags=flags, pos=pos)
    if key == ("pr", "create"):
        head = flag_val("-H", "--head")
        hv = word_value(head, ctx, env) if head is not None else "HEAD"
        top = git_toplevel(ctx.cwd) if ctx.cwd else None
        if hv is None:
            op.unresolved.append("--head を静的に決められない")
        elif ":" not in hv and top:
            # 既にどこかの remote にある commit は公開済みか別の判定を通っている
            op.push = PushSpec(top, [hv], "*", [hv] if hv != "HEAD" else [], False)
            if ctx.opaque:
                op.unresolved.append("同じコマンド内の前段（%s）が push される履歴を変えうる" % ctx.opaque_reason)
        elif top is None and ":" not in hv:
            op.unresolved.append("gh pr create は head ブランチを push しうるが、cwd が git リポジトリの外")
    ctx.ops.append(op)


def collect_gh(cmd, op, rest, rest_vals, spec, env, ctx, extra, flags=None, pos=None):
    if flags is None:
        flags, pos = parse_flags(rest, rest_vals, spec)
    replace = extra.get("replace")
    stdin = None
    stdin_done = False

    def get_stdin():
        nonlocal stdin, stdin_done
        if not stdin_done:
            stdin = stdin_of(cmd, ctx, env)
            stdin_done = True
        return stdin

    for name, w, _ in flags:
        if name in ("-R", "--repo"):
            continue
        if name in ("-e", "--editor") and spec.editor and name not in spec.takes_value:
            op.unresolved.append("エディタで書く本文（%s）は検査できない" % name)
            continue
        if w is None:
            if name in spec.takes_value:
                if extra.get("xargs"):
                    op.unresolved.append("%s の値が xargs の入力から来る" % name)
                else:
                    op.unresolved.append("%s の値が無い" % name)
            continue
        v = word_value(w, ctx, env)
        if replace and v is not None and replace in v and (name in spec.text or name in spec.files):
            op.unresolved.append("%s の値が %s の置換で決まる" % (name, "find -exec" if extra.get("find") else "xargs -I"))
            continue
        if name in spec.text:
            if v is None:
                op.unresolved.append("%s の値に展開（変数・コマンド置換）がある" % name)
            else:
                op.text(name, v)
        elif name in spec.files:
            content, why = read_file(w, ctx, env, stdin=get_stdin() if v == "-" else None)
            if content is None:
                op.unresolved.append("%s: %s" % (name, why))
            else:
                op.text("%s %s" % (name, v or "<置換>"), content)
        elif name in spec.attach:
            op.confirms.append("画像・動画の添付（%s）は中身を検査できない" % name)
            if v and "#" in v:
                op.text("%s の代替テキスト" % name, v.split("#", 1)[1])
        elif v is not None:
            op.text(name, v, generic=True)
    # 位置引数
    pvals = [word_value(p, ctx, env) for p in (pos or [])]
    mode = spec.positional
    if extra.get("xargs") and not extra.get("replace"):
        if mode in ("files", "tag+assets", "id+files", "text"):
            op.unresolved.append("位置引数が xargs の入力から来る")
    if mode == "text":
        for p, v in zip(pos, pvals):
            if v is not None:
                op.text("位置引数", v)
    elif mode in ("files", "tag+assets", "id+files"):
        start = 1 if mode in ("tag+assets", "id+files") else 0
        if mode == "tag+assets" and pvals:
            if pvals[0] is None:
                op.unresolved.append("タグ名に展開がある")
            else:
                op.text("タグ名", pvals[0])
        for p, v in list(zip(pos, pvals))[start:]:
            if v is not None and mode == "tag+assets" and "#" in v:
                op.text("アセットの表示名", v.split("#", 1)[1])
                p = sh_lit_word(v.split("#", 1)[0])
            content, why = read_file(p, ctx, env, stdin=get_stdin() if v == "-" else None)
            if content is None:
                if mode == "tag+assets" and "バイナリ" in why:
                    op.confirms.append("バイナリのアセットは中身を検査できない")
                else:
                    op.unresolved.append("%s: %s" % ("アップロードするファイル", why))
            else:
                op.text("アップロードするファイル %s" % (v or ""), content)
        if mode == "files" and not pos:
            content = get_stdin()
            if content is None:
                op.unresolved.append("標準入力から作る gist の中身を静的に決められない")
            else:
                op.text("標準入力", content)
    else:
        for p, v in zip(pos or [], pvals):
            if v is not None and not re.fullmatch(r"#?\d+", v) and not v.startswith("http"):
                op.text("位置引数", v)


def analyze_gh_api(cmd, args, env, ctx):
    vals = static_words(args, ctx, env)
    spec = Spec((), (), (), ("-X", "--method", "-f", "--raw-field", "-F", "--field", "-H", "--header",
                             "--input", "-q", "--jq", "-t", "--template", "--hostname", "-p",
                             "--preview", "--cache"))
    flags, pos = parse_flags(args, vals, spec)
    method_w = None
    fields = []
    input_w = None
    host = "github.com"
    for name, w, _ in flags:
        if name in ("-X", "--method"):
            method_w = w
        elif name in ("-f", "--raw-field"):
            fields.append(("raw", w))
        elif name in ("-F", "--field"):
            fields.append(("typed", w))
        elif name == "--input":
            input_w = w
        elif name == "--hostname" and w is not None:
            host = word_value(w, ctx, env) or host
    if method_w is not None:
        method = word_value(method_w, ctx, env)
        method = method.upper() if method else None
    else:
        method = "POST" if (fields or input_w is not None) else "GET"
    if method in ("GET", "HEAD", "DELETE"):
        return
    endpoint = word_value(pos[0], ctx, env) if pos else None
    op = Op("gh api %s" % (method or "?"), Dest("unknown", reason="API の宛先"))
    stdin = stdin_of(cmd, ctx, env)
    parsed = {}
    for kind, w in fields:
        v = word_value(w, ctx, env) if w is not None else None
        if v is None:
            op.unresolved.append("gh api のフィールド値に展開がある")
            continue
        key, _, val = v.partition("=")
        if kind == "typed" and val.startswith("@"):
            content, why = read_file(sh_lit_word(val[1:]), ctx, env, stdin=stdin if val == "@-" else None)
            if content is None:
                op.unresolved.append("-F %s=@…: %s" % (key, why))
                continue
            val = content
        parsed[key] = val
        op.text("gh api のフィールド %s" % key, val)
    if input_w is not None:
        content, why = read_file(input_w, ctx, env, stdin=stdin)
        if content is None:
            op.unresolved.append("--input: %s" % why)
        else:
            op.text("--input", content)
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    parsed.update({k: v for k, v in data.items() if isinstance(v, (str, bool))})
            except ValueError:
                pass
    if endpoint is None:
        op.unresolved.append("エンドポイントに展開がある")
        ctx.ops.append(op)
        return
    ep = re.sub(r"^https?://[^/]+/", "", endpoint).lstrip("/")
    parts = ep.split("/")
    if ep == "graphql":
        q = parsed.get("query")
        if isinstance(q, str) and not re.search(r"\bmutation\b", q):
            return
        op.dest = Dest("unknown", reason="graphql の宛先は node ID で決まる")
    elif parts[0] == "repos" and len(parts) >= 3:
        owner, repo = parts[1], parts[2]
        if "{owner}" in (owner,) or "{repo}" in (repo,) or owner.startswith(":") or repo.startswith(":"):
            op.dest = implicit_dest(ctx, env)
        else:
            op.dest = Dest("repo", [(host, "%s/%s" % (owner, repo))])
        if len(parts) == 3 and method in ("PATCH", "POST", "PUT"):
            vis = str(parsed.get("visibility", "")).lower()
            priv = str(parsed.get("private", "")).lower()
            if vis == "public" or priv == "false":
                op.blocks.append("リポジトリを公開に切り替える操作は中身を全部公開する。"
                                 "agent からは行わず、人が履歴を確認してから手で切り替える")
                op.dest = Dest("unknown", reason="公開化の対象")
    elif parts[0] == "gists":
        op.dest = Dest("gist")
    elif parts[0] == "repositories":
        op.dest = Dest("unknown", reason="/repositories/<id> は数値 ID で宛先を決める")
    elif parts[0] in ("markdown",):
        return
    elif (parts[0] == "user" and parts[1:2] == ["repos"]) or (parts[0] == "orgs" and parts[2:3] == ["repos"]):
        priv = str(parsed.get("private", "")).lower()
        vis = str(parsed.get("visibility", "")).lower()
        v = "private" if (priv == "true" or vis == "private") else ("internal" if vis == "internal" else None)
        op.dest = Dest("newrepo", reason="新規リポジトリ", vis=v)
    ctx.ops.append(op)


# ============================================================================
# git
# ============================================================================

def analyze_git(cmd, args, env, ctx, depth, alias_depth=0):
    vals = static_words(args, ctx, env)
    repo_dir = ctx.cwd
    i = 0
    has_config = False
    while i < len(vals):
        v = vals[i]
        if v is None:
            if any(x == "push" for x in vals):
                ctx.ops.append(_unresolved_op("git push", "git の引数に展開がある"))
            return
        if v == "-C":
            d = vals[i + 1] if i + 1 < len(vals) else None
            if d is None:
                repo_dir = None
            else:
                base = repo_dir if repo_dir is not None else None
                if os.path.isabs(d) or d.startswith("~"):
                    repo_dir = os.path.normpath(os.path.expanduser(d))
                elif base is not None:
                    repo_dir = os.path.normpath(os.path.join(base, d))
                else:
                    repo_dir = None
            i += 2
            continue
        if v in ("-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"):
            has_config = has_config or v == "-c"
            i += 2
            continue
        if v.startswith("--git-dir=") or v.startswith("--work-tree="):
            has_config = True
            i += 1
            continue
        if v.startswith("-"):
            i += 1
            continue
        break
    if i >= len(vals):
        return
    sub = vals[i]
    rest, rest_vals = args[i + 1:], vals[i + 1:]
    if sub == "push":
        analyze_push(cmd, rest, rest_vals, repo_dir, env, ctx, has_config)
        return
    if sub == "subtree" and rest_vals[:1] == ["push"]:
        op = Op("git subtree push", Dest("unknown", reason="subtree push"))
        _push_dest_and_spec(op, repo_dir, [v for v in rest_vals[1:] if v and not v.startswith("-")][:1],
                            ["HEAD"], [], False, ctx)
        ctx.ops.append(op)
        return
    if sub not in KNOWN_GIT and alias_depth < 3 and repo_dir:
        rc, out = git(["config", "--get", "alias.%s" % sub], repo_dir)
        expansion = out.strip() if rc == 0 else ""
        if expansion:
            if expansion.startswith("!"):
                _walk_source(expansion[1:], ctx, depth)
                return
            try:
                exp = [sh_lit_word(t) for t in shlex.split(expansion)]
            except ValueError:
                return
            analyze_git(cmd, args[:i] + exp + list(rest), env, ctx, depth, alias_depth + 1)


KNOWN_GIT = {"add", "am", "archive", "bisect", "blame", "branch", "bundle", "cat-file", "check-ignore",
             "checkout", "cherry", "cherry-pick", "clean", "clone", "commit", "config", "count-objects",
             "describe", "diff", "diff-tree", "difftool", "fetch", "for-each-ref", "format-patch",
             "fsck", "gc", "grep", "help", "init", "log", "ls-files", "ls-remote", "ls-tree", "merge",
             "merge-base", "mergetool", "mv", "name-rev", "notes", "pull", "push", "range-diff",
             "rebase", "reflog", "remote", "repack", "replace", "reset", "restore", "rev-list",
             "rev-parse", "revert", "rm", "send-email", "shortlog", "show", "show-ref", "sparse-checkout",
             "stash", "status", "submodule", "subtree", "switch", "symbolic-ref", "tag", "update-index",
             "update-ref", "var", "verify-commit", "version", "whatchanged", "worktree", "lfs",
             "filter-repo", "maintenance", "hash-object", "apply", "annotate", "credential",
             "check-attr", "check-ref-format", "column", "commit-tree", "mktag", "mktree",
             "prune", "read-tree", "write-tree", "gui", "citool", "instaweb", "request-pull"}

PUSH_VALUE_OPTS = {"--repo", "-o", "--push-option", "--receive-pack", "--exec"}


def analyze_push(cmd, args, vals, repo_dir, env, ctx, has_config):
    flags = set()
    pos = []
    i = 0
    while i < len(vals):
        v = vals[i]
        if v is None:
            pos.append(None)
            i += 1
            continue
        if v in PUSH_VALUE_OPTS:
            i += 2
            continue
        if v.startswith("--"):
            flags.add(v.split("=", 1)[0])
            i += 1
            continue
        if v.startswith("-") and len(v) > 1:
            for ch in v[1:]:
                flags.add("-" + ch)
            i += 1
            continue
        pos.append(v)
        i += 1
    if "--dry-run" in flags or "-n" in flags:
        return
    op = Op("git push", Dest("unknown", reason="push 先"))
    if has_config:
        op.unresolved.append("git -c / --git-dir 付きの push は宛先・範囲を静的に決められない")
    if any(p is None for p in pos):
        op.unresolved.append("push の remote か refspec に展開がある")
        ctx.ops.append(op)
        return
    if ctx.opaque:
        op.unresolved.append("同じコマンド内の前段（%s）が push される履歴を変えうる。"
                             "commit と push は別の Bash 呼び出しに分ける" % ctx.opaque_reason)
    remote = pos[0] if pos else None
    refspecs = pos[1:]
    revs, names, tags = [], [], False
    if "--mirror" in flags:
        revs, tags = ["--all"], True
    elif "--all" in flags or "--branches" in flags:
        revs = ["--branches"]
    if "--tags" in flags:
        revs.append("--tags")
        tags = True
    if "--follow-tags" in flags:
        tags = True
    if "--delete" in flags or "-d" in flags:
        refspecs = []
    for rs in refspecs:
        rs = rs.lstrip("+")
        if rs == "tag":
            continue
        src, _, dst = rs.partition(":")
        if src == "":
            continue
        revs.append(src)
        names.append(src)
        if dst:
            names.append(dst)
        if src.startswith("refs/tags/") or (refspecs and refspecs[0] == "tag"):
            tags = True
    if not revs and not refspecs:
        revs = ["HEAD"]
    _push_dest_and_spec(op, repo_dir, [remote] if remote else [], revs, names, tags, ctx)
    ctx.ops.append(op)


def _push_dest_and_spec(op, repo_dir, remote_list, revs, names, tags, ctx):
    if repo_dir is None:
        op.unresolved.append("push するリポジトリ（cwd / -C）が静的に決まらない")
        return
    top = git_toplevel(repo_dir)
    if top is None:
        op.unresolved.append("cwd が git リポジトリの外で、push の範囲を決められない")
        return
    remote = remote_list[0] if remote_list else None
    if remote is None:
        branch = git(["symbolic-ref", "--quiet", "--short", "HEAD"], top)[1].strip()
        for key in ("branch.%s.pushRemote" % branch, "remote.pushDefault", "branch.%s.remote" % branch):
            if not branch and key.startswith("branch."):
                continue
            rc, out = git(["config", "--get", key], top)
            if rc == 0 and out.strip():
                remote = out.strip()
                break
        remote = remote or "origin"
        if branch and "HEAD" in revs:
            names.append(branch)
            rc, up = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{push}"], top)
            if rc == 0 and up.strip():
                names.append(up.strip().split("/", 1)[-1])
    rc, out = git(["remote", "get-url", "--push", "--all", remote], top)
    named = rc == 0
    urls = [u for u in out.splitlines() if u.strip()] if named else [remote]
    repos, other = [], []
    for u in urls:
        kind = parse_remote_url(u)
        if kind[0] == "github":
            repos.append((kind[1], kind[2]))
        elif kind[0] == "gist":
            other.append("gist")
        elif kind[0] == "local":
            continue
        else:
            other.append("other")
    if "gist" in other:
        op.dest = Dest("gist")
    elif other or not urls:
        op.dest = Dest("unknown", reason="GitHub 以外の push 先")
    elif repos:
        op.dest = Dest("repo", repos)
    else:
        op.dest = Dest("local")
    op.push = PushSpec(top, revs, remote if named else None, names, tags)


# ============================================================================
# push の走査
# ============================================================================

class LimitExceeded(Exception):
    pass


def scan_push(spec, cfg, limits=True):
    """push される範囲の本文を列挙する → [(label, text, generic)]. 上限超過は LimitExceeded."""
    texts = []
    base = list(spec.revs)
    if spec.exclude_remote == "*":
        exclude = ["--not", "--remotes"]
    elif spec.exclude_remote:
        exclude = ["--not", "--remotes=%s" % spec.exclude_remote]
    else:
        exclude = []
    max_commits = int(cfg.get("max_push_commits") or 0)
    max_bytes = int(cfg.get("max_push_bytes") or 0)
    count = 0
    if base:
        rc, out = git(["rev-list", "--count"] + base + exclude, spec.repo_dir, timeout=4.0)
        if rc != 0:
            raise LimitExceeded("push される範囲を数えられない（git rev-list が失敗）")
        count = int(out.strip() or 0)
    if limits and count > max_commits:
        raise LimitExceeded("push される commit が %d 件あり上限 %d を超える" % (count, max_commits))
    for n in spec.refnames:
        if n and n != "HEAD":
            texts.append(("push する ref 名", n, True))
    if count:
        fmt = "%x00C%x00%h%x00%an <%ae>%x00%cn <%ce>%x00%B%x00"
        args = ["git", "log", "--no-color", "--no-ext-diff", "--no-renames", "-p", "--format=" + fmt] + \
            base + exclude
        try:
            p = subprocess.Popen(args, cwd=spec.repo_dir, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL)
        except OSError:
            raise LimitExceeded("git log を起動できない")
        chunks, total = [], 0
        try:
            while True:
                buf = p.stdout.read(65536)
                if not buf:
                    break
                total += len(buf)
                if limits and total > max_bytes:
                    raise LimitExceeded("push される差分が %d バイトを超える" % max_bytes)
                chunks.append(buf)
        except BaseException:
            p.kill()        # 時間切れ（Deadline）でも子を残さない
            raise
        finally:
            try:
                p.stdout.close()
            except OSError:
                pass
            p.wait()
        texts.extend(parse_log("".join(c.decode("utf-8", "replace") for c in chunks)))
    if spec.tags:
        wanted = set(spec.tags) if isinstance(spec.tags, (list, tuple, set)) else None
        if wanted is None and spec.exclude_remote and spec.exclude_remote != "*":
            # remote に既にある tag は公開済み（毎回の --follow-tags で古い tag を蒸し返さない）。
            # 引けなければ全部見る
            env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
            env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
            rc, out = run(["git", "ls-remote", "--tags", "--refs", spec.exclude_remote],
                          cwd=spec.repo_dir, timeout=GH_API_TIMEOUT, env=env)
            if rc == 0:
                remote_tags = {line.split("refs/tags/", 1)[1] for line in out.splitlines()
                               if "refs/tags/" in line}
                rc2, local = git(["tag", "--list"], spec.repo_dir)
                if rc2 == 0:
                    wanted = {t for t in local.split() if t not in remote_tags}
        rc, out = git(["for-each-ref", "refs/tags",
                       "--format=%(refname:short)%00%(taggername) %(taggeremail)%00%(contents)%00%00"],
                      spec.repo_dir)
        if rc == 0:
            for rec in out.split("\0\0"):
                fields = rec.strip("\n").split("\0")
                if not fields or not fields[0]:
                    continue
                if wanted is not None and fields[0] not in wanted:
                    continue
                texts.append(("tag 名", fields[0], True))
                if len(fields) > 1 and fields[1].strip():
                    texts.append(("tag %s の作成者" % fields[0], fields[1], False))
                if len(fields) > 2 and fields[2].strip():
                    texts.append(("tag %s のメッセージ" % fields[0], fields[2], True))
    return texts


def parse_log(out):
    texts = []
    for chunk in out.split("\0C\0")[1:]:
        fields = chunk.split("\0", 4)
        if len(fields) < 5:
            continue
        short, author, committer, message, diff = fields
        texts.append(("commit %s のメッセージ" % short, message, True))
        texts.append(("commit %s の作者・コミッター" % short, author + "\n" + committer, False))
        path, lines, newno = None, [], 0
        file_index = 0

        def flush():
            if path is not None and lines:
                texts.append(("commit %s の変更ファイル %s の追加行" % (short, path),
                              "\n".join(t for _, t in lines), False, [n for n, _ in lines]))

        for line in diff.splitlines():
            if line.startswith("diff --git "):
                flush()
                path, lines = None, []
                file_index += 1
                continue
            if line.startswith("+++ "):
                p = line[4:]
                path = p[2:] if p.startswith("b/") else p
                if path != "/dev/null":
                    texts.append(("commit %s の %d 番目の変更ファイルの名前" % (short, file_index), path, False))
                continue
            if line.startswith("--- ") or line.startswith("index ") or line.startswith("new file") \
                    or line.startswith("deleted file") or line.startswith("similarity") \
                    or line.startswith("rename ") or line.startswith("old mode") \
                    or line.startswith("new mode"):
                continue
            if line.startswith("Binary files"):
                m = re.search(r" and b/(.*) differ$", line)
                if m:
                    texts.append(("commit %s の %d 番目の変更ファイルの名前" % (short, file_index),
                                  m.group(1), False))
                continue
            if line.startswith("@@"):
                m = re.search(r"\+(\d+)", line)
                newno = int(m.group(1)) if m else 0
                continue
            if line.startswith("+"):
                lines.append((newno, line[1:]))
                newno += 1
            elif line.startswith(" "):
                newno += 1
        flush()
    return texts


# ============================================================================
# 判定
# ============================================================================

class Verdict:
    def __init__(self):
        self.blocks = []      # (op, [Finding|str])
        self.confirms = []
        self.warnings = []


def evaluate(ops, matcher, vis, cfg, session_cwd, dict_state):
    """公開先の op だけを検査して Verdict を返す."""
    v = Verdict()
    for op in ops:
        public = vis.is_public(op.dest)
        sync_src = getattr(op, "sync_source", None)
        transfer_to = getattr(op, "transfer_to", None)
        if transfer_to is not None:
            # 移動先が公開で、移動元が公開と確定していなければ中身が公開される
            if vis.is_public(transfer_to) and not _surely_public(op.dest, vis):
                v.blocks.append((op, ["非公開かもしれない issue を公開リポジトリへ移動する"
                                      "（中身を検査できない）"]))
            continue
        if sync_src is not None:
            if public and not _surely_public(sync_src, vis):
                v.blocks.append((op, ["非公開かもしれない --source から公開リポジトリへ同期する"]))
            continue
        if not public:
            continue
        found = []
        found.extend(op.blocks)
        if dict_state == "missing" and cfg.get("on_missing_dict") != "warn":
            found.append("辞書が無い（または有効な語が 0 件）ので公開先への送信を止めた")
        elif dict_state == "missing":
            v.warnings.append("辞書が無いまま公開先へ送った（on_missing_dict=warn）")
        dest_name = next(iter(op.dest.names()), None)
        found.extend(scan_entries(matcher, op.texts, dest_name))
        if op.push is not None:
            try:
                found.extend(scan_entries(matcher, scan_push(op.push, cfg), dest_name))
            except LimitExceeded as e:
                found.append("%s。小さく分けて push するか、人が scan-git（README）で"
                             "確かめてから手で push する" % e)
        found.extend("本文を静的に解決できない: %s" % r for r in op.unresolved)
        blocks = [f for f in found if not isinstance(f, Finding) or f.severity == "block"]
        confirms = [f for f in found if isinstance(f, Finding) and f.severity == "confirm"]
        confirms.extend(op.confirms)
        ctx_reason = cross_context(session_cwd, op.dest, vis)
        if ctx_reason:
            confirms.append(ctx_reason)
        if blocks:
            v.blocks.append((op, blocks))
        if confirms:
            v.confirms.append((op, confirms))
    return v


def scan_entries(matcher, entries, dest_name):
    """[(label, text, generic[, linenos])] を照合する."""
    out = []
    for e in entries:
        out.extend(matcher.scan(e[1], e[0], generic=e[2], dest_name=dest_name,
                                linenos=e[3] if len(e) > 3 else None))
    return out


def _surely_public(dest, vis):
    if dest.kind in ("repo",) and dest.repos:
        return all(vis.lookup(h, s) == "public" for h, s in dest.repos)
    return False


def cross_context(session_cwd, dest, vis):
    """非公開・別 owner のリポジトリで作業中のセッションから公開先へ書くか（辞書で拾えない散文対策）."""
    if not session_cwd or BUDGET.left() < GH_API_TIMEOUT + 1.5:
        return None
    top = git_toplevel(session_cwd)
    if top is None:
        return None
    repos, others = remote_repos(top)
    if not repos:
        return None
    visibilities = [vis.lookup(h, s) for h, s in repos]
    if any(x not in ("private", "internal") for x in visibilities):
        return None
    here = {slug.split("/")[0].lower() for _, slug in repos}
    there = dest.owners()
    if dest.kind == "gist":
        there = {self_login()} - {None}
    if there and there <= here:
        return None
    return ("非公開リポジトリ（別の owner）で作業中のセッションから公開先へ書き込む。"
            "辞書に無い識別子・略称・ドメイン説明が混ざっていないか匿名化を確認する")


def self_login():
    cfg_dir = os.environ.get("GH_CONFIG_DIR") or os.path.join(
        os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"), "gh")
    try:
        with open(os.path.join(cfg_dir, "hosts.yml"), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    m = re.search(r"^github\.com:\s*\n(?:[ \t]+.*\n)*?[ \t]+user:\s*(\S+)", text, re.M)
    return m.group(1).lower() if m else None


# ============================================================================
# 出力
# ============================================================================

def render_items(items):
    out = []
    seen = set()
    for f in items:
        line = f.render() if isinstance(f, Finding) else str(f)
        if line not in seen:
            seen.add(line)
            out.append("  - " + line)
    return out


def block_message(verdict, dpath, confirm_as_block, matcher, vis=None):
    lines = ["[guardrail-protect] 公開先への送信を止めた（public-leak-guard）", ""]
    groups = list(verdict.blocks)
    if confirm_as_block:
        groups += verdict.confirms
    for op, items in groups:
        lines.append("操作: %s / 宛先: %s" % (op.what, matcher.safe(op.dest.describe())))
        lines.extend(render_items(items))
        if vis is not None and any("%s/%s" % (h, s_.lower()) in vis.failed for h, s_ in op.dest.repos):
            lines.append("  （宛先の visibility を取得できず公開先として検査した。gh auth status と"
                         " org の SSO 承認を確認する。取得できれば private は素通しになる）")
    lines += ["", "語そのものは表示しない。辞書 %s の行番号で照合すること。" % display_path(dpath),
              "置き換え例:"]
    lines += ["  - " + r for r in REPLACEMENTS]
    lines += ["",
              "本文を静的に解決できないときは、本文を Write ツールでファイルに書き出し、",
              "別の Bash 呼び出しで --body-file <絶対パス>（gh api なら -F body=@<path>）を渡す。",
              "commit と push は別の Bash 呼び出しに分ける。",
              "誤検知なら辞書・設定（~/.config/guardrail-protect/）を人が Claude の外で直す"
              "（Claude からの編集・環境変数での迂回は止まる）。"]
    if confirm_as_block and verdict.confirms:
        lines += ["確認が要る項目（汎用パターン・添付・作業文脈）は confirm_action=block のため止めた。"
                  "内容を置き換えるか、人が確認して手で投稿する。"]
        if any(isinstance(f, Finding) and f.kind == "linear" for _, items in verdict.confirms for f in items):
            lines += ["チーム形式の ID が自分のチーム（公開してよい）のものなら、人が設定の"
                      " allowed_id_prefixes に接頭辞を足す。"]
    return "\n".join(lines)


def display_path(p):
    return "~" + p[len(HOME):] if p.startswith(HOME + "/") else p


def ask_json(verdict, matcher):
    parts = []
    for op, items in verdict.confirms:
        parts.append("%s → %s" % (op.what, matcher.safe(op.dest.describe())))
        parts.extend(render_items(items))
    reason = "[guardrail-protect] 公開先への送信に確認が要る:\n" + "\n".join(parts)
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                              "permissionDecision": "ask",
                                              "permissionDecisionReason": reason}},
                      ensure_ascii=False)


# ============================================================================
# 入口（hook）
# ============================================================================

MCP_READ_RE = re.compile(r"^(get|list|search|read|download|fetch)_")


def mcp_parts(tool):
    """`mcp__<server>__<tool>` → (server, tool). MCP でなければ (None, None)."""
    if not tool.startswith("mcp__") or "__" not in tool[5:]:
        return None, None
    server, name = tool[5:].rsplit("__", 1)
    return server, name


def is_github_mcp(tool):
    server, _ = mcp_parts(tool)
    return server is not None and "github" in server.lower()


def is_browser_mcp(tool):
    server, _ = mcp_parts(tool)
    return server is not None and re.search(r"chrome|browser", server, re.I) is not None


def all_strings(obj, prefix=""):
    if isinstance(obj, str):
        yield prefix or "値", obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from all_strings(v, "%s.%s" % (prefix, k) if prefix else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from all_strings(v, "%s[%d]" % (prefix, i))


def mcp_github_op(tool, tool_input):
    name = mcp_parts(tool)[1] or tool
    if MCP_READ_RE.match(name) or name in ("update_pull_request_branch", "fork_repository"):
        return None
    owner, repo = tool_input.get("owner"), tool_input.get("repo")
    if name in ("create_repository",):
        dest = Dest("newrepo", reason="新規リポジトリ", vis="private" if tool_input.get("private") else None)
    elif "gist" in name:
        dest = Dest("gist")
    elif isinstance(owner, str) and isinstance(repo, str) and owner and repo:
        dest = Dest("repo", [("github.com", "%s/%s" % (owner, repo))])
    else:
        dest = Dest("unknown", reason="MCP の入力に owner / repo が無い")
    op = Op(tool, dest)
    for label, text in all_strings(tool_input):
        if label in ("owner", "repo"):
            continue
        # ファイルの中身（push_files / create_or_update_file）はコードなので汎用パターンを当てない
        op.text("%s の %s" % (name, label), text, generic="content" not in label)
    return op


def analyze_bash(command, cwd, session_cwd):
    ctx = Ctx(cwd, session_cwd)
    try:
        cmds = sh.parse(command)
    except sh.ParseError:
        if MENTIONS_PUBLISH_RE.search(command) or GUARD_VAR_TEXT_RE.search(command):
            ctx.ops.append(_unresolved_op("構文解析できないコマンド",
                                          "コマンドを構文解析できない（引用符・括弧の不一致）"))
        return ctx
    walk(cmds, ctx)
    return ctx


def relevant_text(command):
    # 引用符・バックスラッシュで語を割る形（`"g"h` / `g''h` / `\gh`）も拾う
    flat = re.sub(r"[\"'\\\\]", "", command)
    if re.search(r"(?<![\w-])(gh|git)(?![\w-])|GUARDRAIL_|guardrail-protect|"
                 r"sensitive-terms|public-leak|github\.com|claude-review|"
                 r"CLAUDE_REVIEW_CONFIG_DIR|REVIEW_METRICS_CONFIG_DIR", flat):
        return True
    for env_name in ("GUARDRAIL_SENSITIVE_DICT", "GUARDRAIL_PUBLIC_LEAK_CONFIG") + REVIEW_CONFIG_ENVS:
        base = os.path.basename((os.environ.get(env_name) or "").rstrip("/"))
        if base and base in command:
            return True
    return False


def hook_main(raw):
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        # 壊れた入力: 公開につながる字面があれば止める（fail-closed）
        if relevant_text(raw):
            sys.stderr.write("[guardrail-protect] public-leak-guard: hook 入力を解釈できないので止めた\n")
            return 2
        return 0
    tool = payload.get("tool_name") or ""
    tin = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    session_cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
    cfg = load_config_safely()
    ops = []
    bypass = []
    browser = False
    if tool in ("Bash", "") or tool.endswith("run_in_terminal"):
        command = tin.get("command")
        if not isinstance(command, str) or not command.strip():
            return 0
        cwd = session_cwd
        if tool.endswith("run_in_terminal") and isinstance(tin.get("cwd"), str) and tin["cwd"]:
            c = tin["cwd"]
            c = os.path.expanduser(c)
            cwd = c if os.path.isabs(c) else (os.path.join(session_cwd, c) if session_cwd else None)
        if not relevant_text(command) and "$'" not in command:
            return 0
        ctx = analyze_bash(command, cwd, session_cwd)
        ops, bypass = ctx.ops, ctx.bypass
    elif is_github_mcp(tool):
        op = mcp_github_op(tool, tin)
        if op is None:
            return 0
        ops = [op]
    elif is_browser_mcp(tool):
        if isinstance(cfg, dict) and cfg.get("browser_input") == "block":
            op = Op(tool, Dest("unknown", reason="ブラウザ操作は宛先を判定しない"))
            for label, text in all_strings(tin):
                if label in ("action", "tabId", "ref", "coordinate"):
                    continue
                op.text(label, text, generic=False)
            ops = [op]
            browser = True
        else:
            return 0
    else:
        return 0

    if bypass:
        lines = ["[guardrail-protect] ガードの迂回を止めた（public-leak-guard）", ""]
        lines += ["  - " + b for b in dict.fromkeys(bypass)]
        lines += ["", "辞書・設定・キャッシュと GUARDRAIL_* 変数、code-review の publish 設定",
                  "（~/.config/claude-review/ の post-publish・machine-label・salt）は Claude から変えない。",
                  "変える必要があるなら、人が Claude の外で編集する。"]
        sys.stderr.write("\n".join(lines) + "\n")
        return 2
    if not ops:
        return 0
    if isinstance(cfg, GuardError):
        sys.stderr.write("[guardrail-protect] public-leak-guard: %s。公開先への送信かを"
                         "判定できないので止めた（%s）\n" % (cfg, display_path(config_path())))
        return 2
    dpath = dict_path()
    try:
        terms = load_terms(dpath)
    except GuardError as e:
        sys.stderr.write("[guardrail-protect] public-leak-guard: %s（%s）。公開先への送信を止めた\n"
                         % (e, display_path(dpath)))
        return 2
    dict_state = "missing" if not terms else "ok"
    matcher = Matcher(terms, local_hostname(), cfg)
    vis = Visibility(cfg)
    verdict = evaluate(ops, matcher, vis, cfg, session_cwd if not browser else None, dict_state)
    if dict_state == "missing" and verdict.blocks:
        for i, (op, items) in enumerate(verdict.blocks):
            items.append("辞書を %s に置く（1 行 1 語・# コメント・w: は語境界・3 文字未満は無視）。"
                         "置けない機械では設定 on_missing_dict を warn にする" % display_path(dpath))
    confirm_action = cfg.get("confirm_action")
    interactive = payload.get("permission_mode") in ("default", "acceptEdits", "plan") \
        and not payload.get("agent_id")
    confirm_as_block = confirm_action != "ask" or not interactive
    if verdict.blocks or (verdict.confirms and confirm_as_block):
        sys.stderr.write(block_message(verdict, dpath, confirm_as_block, matcher, vis) + "\n")
        return 2
    if verdict.confirms:
        sys.stdout.write(ask_json(verdict, matcher) + "\n")
        return 0
    if verdict.warnings:
        sys.stdout.write(json.dumps({"systemMessage": "[guardrail-protect] " + " / ".join(
            dict.fromkeys(verdict.warnings))}, ensure_ascii=False) + "\n")
    return 0


def load_config_safely():
    try:
        return load_config()
    except GuardError as e:
        return e


# ============================================================================
# 入口（git hook / 手動）
# ============================================================================

def human_scan(ops_texts, dest_name, cfg, generic_block=True):
    """→ exit code（0 = 検出なし / 1 = 検出あり・検査不能）."""
    try:
        terms = load_terms(dict_path())
    except GuardError as e:
        sys.stderr.write("[guardrail-protect] %s\n" % e)
        return 1
    matcher = Matcher(terms, local_hostname(), cfg)
    found = []
    if not terms:
        msg = "辞書が無い（%s）" % display_path(dict_path())
        if cfg.get("on_missing_dict") == "warn":
            sys.stderr.write("[guardrail-protect] 警告: %s\n" % msg)
        else:
            found.append(msg + "。on_missing_dict=warn にするか辞書を置く")
    found.extend(scan_entries(matcher, ops_texts, dest_name))
    if not generic_block:
        found = [f for f in found if not isinstance(f, Finding) or f.severity == "block"]
    if found:
        sys.stderr.write("[guardrail-protect] 公開先に出せない内容がある:\n")
        sys.stderr.write("\n".join(render_items(found)) + "\n")
        sys.stderr.write("置き換え例:\n" + "\n".join("  - " + r for r in REPLACEMENTS) + "\n")
        return 1
    return 0


def prepush_main(argv):
    remote = argv[0] if argv else ""
    url = argv[1] if len(argv) > 1 else remote
    try:
        cfg = load_config()
    except GuardError as e:
        sys.stderr.write("[guardrail-protect] pre-push: %s\n" % e)
        return 1
    kind = parse_remote_url(url)
    vis = Visibility(cfg)
    if kind[0] == "local":
        return 0
    if kind[0] == "github":
        dest = Dest("repo", [(kind[1], kind[2])])
        if not vis.is_public(dest):
            return 0
    dest_name = kind[2].split("/")[-1] if kind[0] == "github" else None
    top = git_toplevel(os.getcwd()) or os.getcwd()
    texts = []
    lines = sys.stdin.read().splitlines()
    zero = re.compile(r"^0+$")
    for line in lines:
        parts = line.split()
        if len(parts) < 4:
            continue
        local_ref, local_sha, remote_ref, remote_sha = parts[:4]
        if zero.match(local_sha):
            continue
        revs = [local_sha]
        exclude_remote = remote if remote and not re.match(r"^[a-z]+://|^[^/]+@", remote) else None
        if not zero.match(remote_sha):
            rc, _ = git(["cat-file", "-e", remote_sha], top)
            if rc == 0:
                revs.append("^" + remote_sha)
        tag = [local_ref[len("refs/tags/"):]] if local_ref.startswith("refs/tags/") else None
        spec = PushSpec(top, revs, exclude_remote, [local_ref, remote_ref], tag)
        try:
            texts.extend(scan_push(spec, cfg, limits=False))
        except LimitExceeded as e:
            sys.stderr.write("[guardrail-protect] pre-push: %s\n" % e)
            return 1
    return human_scan(texts, dest_name, cfg,
                      generic_block=cfg.get("confirm_action") != "ask")


def scan_git_main(argv):
    repo = os.getcwd()
    if argv[:1] == ["--repo"] and len(argv) > 1:
        repo, argv = argv[1], argv[2:]
    cfg = load_config()
    spec = PushSpec(git_toplevel(repo) or repo, argv or ["HEAD"], None, [], True)
    try:
        texts = scan_push(spec, cfg, limits=False)
    except LimitExceeded as e:
        sys.stderr.write("[guardrail-protect] %s\n" % e)
        return 1
    return human_scan(texts, None, cfg)


def scan_text_main(argv):
    cfg = load_config()
    if argv:
        with open(argv[0], encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = sys.stdin.read()
    return human_scan([("本文", text, True)], None, cfg)


def deadline_seconds():
    try:
        value = float(load_config().get("deadline_seconds") or DEADLINE_SECONDS)
    except (GuardError, TypeError, ValueError):
        value = DEADLINE_SECONDS
    return min(8.0, max(0.5, value))


def main(argv):
    mode = argv[0] if argv else "hook"
    if mode == "hook":
        raw = sys.stdin.read()
        seconds = deadline_seconds()
        BUDGET.end = time.monotonic() + seconds
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        try:
            return hook_main(raw)
        except Deadline:
            sys.stderr.write("[guardrail-protect] public-leak-guard: %.1f 秒以内に検査を終えられなかった"
                             "ので止めた（push の範囲が大きい・API が遅い）。小さく分けて実行するか、"
                             "人が確認して手で実行する\n" % seconds)
            return 2
        except Exception as e:  # noqa: BLE001 — fail-closed の最後の砦
            if relevant_text(raw):
                sys.stderr.write("[guardrail-protect] public-leak-guard: 内部エラー（%s）。"
                                 "公開先への送信かを判定できないので止めた\n" % type(e).__name__)
                return 2
            sys.stderr.write("[guardrail-protect:Unexpected] public-leak-guard: %s\n" % type(e).__name__)
            return 0
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
    BUDGET.end = float("inf")        # 人が起動するモードは時間で打ち切らない
    if mode == "pre-push":
        return prepush_main(argv[1:])
    if mode == "scan-git":
        return scan_git_main(argv[1:])
    if mode == "scan-text":
        return scan_text_main(argv[1:])
    sys.stderr.write("usage: detect-public-leak.py hook|pre-push|scan-git|scan-text\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
