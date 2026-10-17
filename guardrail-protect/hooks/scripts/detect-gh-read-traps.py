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
  コメントだけを読む正当な呼び出しもあるので、止めずに知らせる側（呼び出し側が判断する）

**黙る条件**: gh の呼び出しでない（echo / grep / jq の引数に現れた文字列）/ 値が静的に決まらない
（変数・コマンド置換で渡した SHA）/ 完全な SHA / `--json` 付き / `--web` 付き / 解析できない（ParseError）。
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import public_leak_shell as sh  # noqa: E402

#: コマンド名より前に来る予約語（`until s=$(…)` / `do id=$(…)` の形）
RESERVED = {"then", "do", "else", "elif", "if", "while", "until", "!", "{", "time"}
#: 完全な SHA は 40 桁。4 桁未満は SHA の短縮形として扱わない（gh / git の最小は 4 桁）
SHORT_SHA_RE = re.compile(r"[0-9a-fA-F]{4,39}")


def _gh_calls(cmds):
    """`gh` を呼ぶコマンドの、`gh` より後ろの (語, 静的な値) を返す（コマンド置換の中も辿る）."""
    for cmd in cmds:
        for word in [w for _, w in cmd.assigns] + cmd.words + [r.target for r in cmd.redirs if r.target]:
            for part in word.substitutions():
                yield from _gh_calls(part.script or [])
        vals = [w.static() for w in cmd.words]
        i = 0
        while i < len(vals) and vals[i] in RESERVED:
            i += 1
        if i < len(vals) and vals[i] == "gh":
            yield vals[i + 1:]


def _commit_values(args):
    """`--commit X` / `--commit=X` / `-c X` の値（静的に決まらない値は None）."""
    for k, v in enumerate(args):
        if v in ("--commit", "-c") and k + 1 < len(args):
            yield args[k + 1]
        elif v is not None and v.startswith("--commit="):
            yield v.split("=", 1)[1]


def _check(args, out):
    if args[:2] == ["run", "list"]:
        for value in _commit_values(args[2:]):
            if value is not None and SHORT_SHA_RE.fullmatch(value):
                out.append("run-short-sha\t`gh run list --commit %s` — --commit は完全な SHA（40 桁）で"
                           "ないと 0 件を返す（エラーにならない）。`--commit \"$(git rev-parse %s)\"` で"
                           "展開して渡す" % (value, value))
    elif args[:2] in (["issue", "view"], ["pr", "view"]):
        rest = args[2:]
        has_json = any(v == "--json" or (v or "").startswith("--json=") for v in rest)
        if ("--comments" in rest or "-c" in rest) and not has_json and not {"--web", "-w"} & set(rest):
            out.append("view-comments\t`gh %s view --comments` — Bash tool は TTY を持たないので、本文が"
                       "出ずコメントだけが出る（コメント 0 件なら出力が空）。本文も要るなら "
                       "`gh %s view <番号> --json title,body,comments`" % (args[0], args[0]))


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
