"""計測の出所に載せるマシンの別名（label）と、表示するパスの伏せ字化（publish / retro が共有）。

**生の hostname を payload にも retro の出力にも出さない。** 以前は `machine_id` に `hostname -s`
をそのまま入れており、retro の「集計」行と「マシン / 版」行（issue に貼る規約がある）を通じて
マシンの hostname が公開 issue に載っていた。`--logs` の母集団行も渡したパスをそのまま出していた。

label の決め方（上から順に採る）:

1. `<設定 dir>/machine-label` に明示した label（`m1` / `m2` のような `m` + 数字）。
   形が違う値は使わない（hostname を書いてしまった回に生の値へ戻さないため。値は出力しない）
2. 未設定なら `m-` + HMAC-SHA256(salt, `hostname -s`) の先頭 8 hex。salt は初回に
   `<設定 dir>/salt` へ乱数で作る。**sha256(hostname) のような決定的な値にしない** —
   公開済みの生の hostname から誰でも計算して突合できてしまう
3. どちらも決められない（hostname が取れない / salt を保存できない）なら None
   （publish は `null` + gap `machine-id` に倒す。推測で埋めない）

設定 dir は `~/.config/claude-review`（リポジトリの外）。`CLAUDE_REVIEW_CONFIG_DIR` で差し替えられる
（テストが実機の設定と salt に触れないための口）。

読み側（retro）は、計測ストアに残っている過去の生の値を**表示の時点で**置き換える（ストアは
append-only で過去行を書き換えない）: ローカルの hostname と一致する生の値と、ローカルの既定 label は
自分の label に、label の形でない他の生の値は `m-` + HMAC に寄せる。salt を保存できない環境では、
その実行の間だけ使う乱数で HMAC を取る（同じ実行の中では同じ値が同じ別名になる）。

CLI（bash から呼ぶ）:
    python3 machine_label.py label        # 自分の label（決められなければ出力なし・exit 1）
    python3 machine_label.py config-dir   # 設定 dir
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import subprocess
import sys

#: label の形（全体一致で使う）。明示 label（`m1` / `m2` …）と、未設定時の既定（`m-` + 8 hex）
LABEL_RE = re.compile(r"m(?:[0-9]{1,4}|-[0-9a-f]{8})")
#: salt の形（32 バイト以上の乱数を hex で書いたもの）
SALT_RE = re.compile(r"[0-9a-f]{64,}")
LABEL_FILE = "machine-label"
SALT_FILE = "salt"
#: 計測ストア（マシンごとのファイルを置く private リポジトリ / 旧 gist の clone）の dir 名
STORE_DIR = "review-metrics"
#: 生のパスを出すときに先頭へ置く注記（`--show-paths`）
RAW_PATHS_WARNING = ("生のパスを出している（--show-paths）。ホーム配下のリポジトリ名などが含まれるので、"
                     "issue・PR・gist・チャットなどの公開先に貼らない")


def config_dir() -> str:
    return (os.environ.get("CLAUDE_REVIEW_CONFIG_DIR")
            or os.path.join(os.path.expanduser("~"), ".config", "claude-review"))


def is_label(value: object) -> bool:
    return isinstance(value, str) and bool(LABEL_RE.fullmatch(value))


def read_label() -> str | None:
    """明示 label を読む。無い・空・形が違うときは None（形が違う値そのものは出力しない）."""
    try:
        with open(os.path.join(config_dir(), LABEL_FILE), encoding="utf-8") as f:
            value = f.readline().strip()
    except (OSError, UnicodeDecodeError):
        return None
    if not value:
        return None
    if not is_label(value):
        sys.stderr.write("WARN: %s の値が label の形（m1 / m2 のような m + 数字）でないので使わない"
                         "（既定の m-<HMAC> に倒す）\n" % os.path.join(config_dir(), LABEL_FILE))
        return None
    return value


def _read_salt(path: str) -> str | None:
    try:
        with open(path, encoding="ascii") as f:
            value = f.read().strip()
    except (OSError, UnicodeDecodeError):
        return None
    # 形が違う salt は上書きしない（利用者が置いたものかもしれない）。使わずに None
    return value if SALT_RE.fullmatch(value) else None


def load_salt() -> str | None:
    """salt を返す。無ければ乱数で作る（0600）。読めない・作れない・形が違うときは None.

    作成は `O_EXCL` で行い、既にあれば（初回以外・並行 publish が先に作った回）その中身を読む
    """
    path = os.path.join(config_dir(), SALT_FILE)
    try:
        os.makedirs(config_dir(), mode=0o700, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return _read_salt(path)
    except OSError:
        return None
    value = secrets.token_hex(32)
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write(value + "\n")
    return value


def hmac8(salt: str, text: str) -> str:
    return hmac.new(salt.encode("ascii"), text.encode("utf-8"), hashlib.sha256).hexdigest()[:8]


def hashed_label(salt: str, host: str) -> str:
    return "m-" + hmac8(salt, host)


def local_hostname() -> str | None:
    """`hostname -s`（過去の payload に入っている生の値と同じ取り方）。取れなければ None."""
    try:
        r = subprocess.run(["hostname", "-s"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    value = r.stdout.strip() if r.returncode == 0 else ""
    return value or None


def local_label() -> str | None:
    """publish が payload に載せる label。salt を保存できない回は None（その場限りの値を載せない）."""
    label = read_label()
    if label:
        return label
    host = local_hostname()
    if not host:
        return None
    salt = load_salt()
    return hashed_label(salt, host) if salt else None


class Aliaser:
    """読み側の表示用。生の値・パスを label と HMAC に置き換える（1 回の retro で 1 つ作る）."""

    def __init__(self) -> None:
        self.host = local_hostname()
        salt = load_salt()
        #: 保存できなければこの実行の間だけ使う乱数（同じ実行の中では同じ値が同じ別名になる）
        self.salt = salt or secrets.token_hex(32)
        self.hashed_self = hashed_label(self.salt, self.host) if self.host else None
        self.local = read_label() or self.hashed_self
        self.home = os.path.expanduser("~")

    def machine(self, value: object) -> str | None:
        """payload の `machine_id` を表示用の label にする（未記録は None のまま）."""
        if not isinstance(value, str) or not value:
            return None
        if self.host and value in (self.host, self.hashed_self):
            return self.local
        if is_label(value):
            return value
        return hashed_label(self.salt, value)

    def _tilde(self, path: str) -> str:
        home = self.home.rstrip(os.sep)
        if home and path.startswith(home + os.sep):
            return "~" + path[len(home):]
        return path

    def path(self, path: str) -> str:
        """`--logs` に渡したパスを表示用にする.

        - `<repo>/.claude/events.jsonl` → `<repo sha=xxxxxxxx>/.claude/events.jsonl`
          （リポジトリのパスを HMAC に。リポジトリの名前をそのまま出さない）
        - 計測ストア（`review-metrics/` か `review-metrics/events/` 直下の `*.jsonl`）→ ファイル名を label に、
          `$HOME` を `~` に（旧 gist の `<hostname>.jsonl` も label 名で出る）
        - それ以外 → `<log sha=xxxxxxxx>`（ファイル名にも何が入っているか分からない）
        """
        absolute = os.path.abspath(path)
        parent, base = os.path.split(absolute)
        if base == "events.jsonl" and os.path.basename(parent) == ".claude":
            repo = os.path.realpath(os.path.dirname(parent))
            return "<repo sha=%s>/.claude/events.jsonl" % hmac8(self.salt, repo)
        store = (os.path.basename(parent) == STORE_DIR
                 or (os.path.basename(parent) == "events"
                     and os.path.basename(os.path.dirname(parent)) == STORE_DIR))
        stem, ext = os.path.splitext(base)
        if store and ext == ".jsonl":
            return "%s/%s.jsonl" % (self._tilde(parent), self.machine(stem))
        return "<log sha=%s>" % hmac8(self.salt, os.path.realpath(absolute))


def main(argv: list[str]) -> int:
    cmd = (argv[1:] or [""])[0]
    if cmd == "label":
        label = local_label()
        if not label:
            return 1
        print(label)
        return 0
    if cmd == "config-dir":
        print(config_dir())
        return 0
    sys.stderr.write("usage: machine_label.py label|config-dir\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
