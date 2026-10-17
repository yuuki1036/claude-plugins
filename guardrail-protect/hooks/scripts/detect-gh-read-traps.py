#!/usr/bin/env python3
r"""gh の読み取りで、エラーにならずに結果が黙って欠ける書き方を検出する（GitHub issue #299）.

stdin にコマンド文字列を受け取り、当たった書き方を 1 行ずつ `<種別>\t<説明>` で stdout に出す
（無ければ何も出さない）。常に exit 0 — 止めるかどうかは呼び出し側（gh-read-guard.sh）が決める。

検出するもの:
- `run-short-sha` — `gh run list --commit <40 桁未満の 16 進>`。`--commit` は完全な SHA でないと
  0 件を返す（実測: 短縮 SHA で 0 件・`git rev-parse` で展開した SHA で 2 件）。CI 待ちのループが
  空のまま回る、0 件の後に最新の run へ落ちて別の SHA の結果を拾う、の 2 つの形で実害があった
- `view-comments` — `gh issue view` / `gh pr view` の `--comments` を `--json` なしで使う。
  Bash tool は TTY を持たないので、本文が出ずコメントだけが出る（コメント 0 件なら出力が空）。
  コメントだけを読む正当な呼び出しもあるので、止めずに知らせる側

gh の呼び出しは、コマンドの位置（予約語と `env` / `timeout` などの前置きを飛ばした先）にある `gh` で
見つける。コマンド置換・プロセス置換の中も辿る。サブコマンドは `-R` / `--repo` の値を除いた位置引数で
決める（`gh run -R o/r list` も `run list`）。

**黙る条件**: gh の呼び出しでない（echo / grep / jq の引数に現れた文字列）/ 値が静的に決まらない
（変数・コマンド置換で渡した SHA）/ 完全な SHA / `--json` 付き / `--web` 付き / 解析できない（ParseError）。
**拾えない形**（どれも黙る側に倒れる）: `bash -c '…'` の文字列の中・heredoc の本文・パラメータ展開の中の
コマンド置換（`${x:-$(gh …)}`）・値を取る前置きのオプション（`sudo -u root gh …`）・値を連結した短いフラグ
（`-cabc1234`）・`--comments=…`。
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import public_leak_shell as sh  # noqa: E402

#: コマンド名より前に来る予約語（`then gh …` / `time gh …` の形）
RESERVED = {"then", "do", "else", "elif", "if", "while", "until", "!", "{", "time"}
#: 後ろのコマンドを実行する前置き。CI 待ちを `timeout` / `watch` で包む形が実際にある
WRAPPERS = {"env", "sudo", "command", "exec", "nohup", "coproc", "xargs", "timeout", "watch"}
#: 前置きのオプションと引数として飛ばす語（`-n` / `VAR=1` / `60` / `5m`）。値を取るオプションの値
#: （`sudo -u root`）は見分けられないので、そこで止まる
WRAPPER_ARG_RE = re.compile(r"-.*|[A-Za-z_][A-Za-z0-9_]*=.*|\d+(\.\d+)?[smhd]?")
#: 完全な SHA は 40 桁。4 桁未満は SHA の短縮形として扱わない（gh / git の最小は 4 桁）
SHORT_SHA_RE = re.compile(r"[0-9a-fA-F]{4,39}")


def _gh_index(vals):
    """コマンドの位置にある `gh` の添字（無ければ None）. 予約語と前置き（とその引数）を飛ばす."""
    i, wrapped = 0, False
    while i < len(vals):
        v = vals[i]
        if v == "gh":
            return i
        if v in RESERVED and not wrapped:
            pass
        elif v in WRAPPERS:
            wrapped = True
        elif not (wrapped and v is not None and WRAPPER_ARG_RE.fullmatch(v)):
            return None
        i += 1
    return None


def _subcommand(args):
    """`-R` / `--repo` とその値を除いた位置引数（サブコマンドの判定用）."""
    out, skip = [], False
    for v in args:
        if skip:
            skip = False
        elif v in ("-R", "--repo"):
            skip = True
        elif not (v or "").startswith("--repo="):
            out.append(v)
    return out


def _gh_calls(cmds):
    """`gh` を呼ぶコマンドごとに、`gh` より後ろの語の静的な値のリスト（決まらない語は None）を返す.

    コマンド置換・プロセス置換の中も辿る。
    """
    for cmd in cmds:
        for word in [w for _, w in cmd.assigns] + cmd.words + [r.target for r in cmd.redirs if r.target]:
            for part in word.substitutions():
                yield from _gh_calls(part.script or [])
        vals = [w.static() for w in cmd.words]
        i = _gh_index(vals)
        if i is not None:
            yield vals[i + 1:]


def _commit_values(args):
    """`--commit X` / `--commit=X` / `-c X` の値（静的に決まらない値は None）."""
    for k, v in enumerate(args):
        if v in ("--commit", "-c") and k + 1 < len(args):
            yield args[k + 1]
        elif v is not None and v.startswith("--commit="):
            yield v.split("=", 1)[1]


def _check(args, out):
    sub = _subcommand(args)[:2]
    if sub == ["run", "list"]:
        for value in _commit_values(args):
            if value is not None and SHORT_SHA_RE.fullmatch(value):
                out.append("run-short-sha\t`gh run list --commit %s` — --commit は完全な SHA（40 桁）で"
                           "ないと 0 件を返す（エラーにならない）。`--commit \"$(git rev-parse %s)\"` で"
                           "展開して渡す" % (value, value))
    elif sub in (["issue", "view"], ["pr", "view"]):
        has_json = any(v == "--json" or (v or "").startswith("--json=") for v in args)
        if ("--comments" in args or "-c" in args) and not has_json and not {"--web", "-w"} & set(args):
            out.append("view-comments\t`gh %s view --comments` — Bash tool は TTY を持たないので、本文が"
                       "出ずコメントだけが出る（コメント 0 件なら出力が空）。本文も要るなら "
                       "`gh %s view <番号> --json title,body,comments`" % (sub[0], sub[0]))


def find_traps(command: str) -> list[str]:
    try:
        cmds = sh.parse(command)
    except (sh.ParseError, RecursionError):
        return []
    out: list[str] = []
    for args in _gh_calls(cmds):
        _check(args, out)
    return list(dict.fromkeys(out))


def main() -> int:
    for line in find_traps(sys.stdin.read()):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
