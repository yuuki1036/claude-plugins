#!/usr/bin/env python3
"""Bash コマンド文字列から「隔離せずに hook スクリプトを直接実行している」箇所を検出する.

stdin にコマンド文字列を受け取り、検出したスクリプトのパスを 1 行ずつ stdout に出す。
検出が無ければ何も出さない（呼び出し側の `set -e` を踏まないよう常に exit 0）。

## 何を対象にするか

**パスの glob ではなく中身で切る。** リポジトリ実測（GitHub issue #194）で
`*/hooks/scripts/*.sh` は 27 本あり、うち 26 本が `safe_hook_init` を呼ぶ真の hook
entry point、残り 1 本（`upload-screenshots.sh`）は skill から意図的に Bash で叩かれる
ユーティリティだった。パスで切ると**この 1 本が偽陽性になる**。

`safe_hook_init` を呼ぶスクリプトは stdin を hook payload として消費し、書き込み先を
`${CLAUDE_PROJECT_DIR:-$PWD}` から導出する。したがって隔離せずに実行すると、実プロジェクトの
`.claude/events.jsonl` 等へ本物と区別できない行が混入する（実測 2 件）。

## 何を「隔離済み」と見なすか

同一セグメント内に **値が空でない** `CLAUDE_PROJECT_DIR=<dir>` の env 代入があること。
`CLAUDE_PROJECT_DIR=` だけ（空値）は `${CLAUDE_PROJECT_DIR:-$PWD}` の `:-` が効いて
$PWD へ倒れるので**隔離になっていない**。判定は**セグメント単位**で行う
（`CLAUDE_PROJECT_DIR=/tmp/x bash a.sh && bash b.sh` の b.sh は隔離されていない）。

## 実行位置だけを見る（参照は止めない）

**パスが現れただけでは検出しない。** `cat x.sh` / `grep foo x.sh` / `wc -l x.sh` は
読むだけで副作用が無く、これを止めるとガードがただの邪魔になる。セグメントの
**コマンド位置**（env 代入を除いた先頭）か、`bash` / `sh` 等のインタプリタの
**最初の非フラグ引数**にあるものだけを実行と見なす。

## 通す方向に倒す場面（fail-open を明示的に選んでいる箇所）

- **トークン化できないコマンド**（クォート未閉じ）… 判定材料が無い
- **解決できないパス**（`${CLAUDE_PLUGIN_ROOT}/hooks/scripts/x.sh` 等の未展開の変数）
  … 中身を読めないので `safe_hook_init` の有無を判定できない
- **開けるが読めないファイル**（権限・I/O エラー）… 同じく中身で判定できない。
  ここを止める方向に倒すと、判定材料が無いだけのファイルで正当な実行を巻き込む
  （GitHub issue #197。この選択を検証していなかったため変異が生存した）

いずれも「読めないから止める」に倒すと、実測で偽陽性 0 だった水準を自分で壊す。
実測で問題になったのは**リポジトリ相対の直叩き**で、そちらは解決できる。
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

ENV_KEY = "CLAUDE_PROJECT_DIR="
#: hook entry point の目印。safe-hook.sh を source して初期化する関数名
HOOK_MARKER = "safe_hook_init"
#: スクリプトを引数に取って実行するもの（`source` / `.` も副作用は同じ）
INTERPRETERS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "source", "."})
#: コマンドの区切り。ここでセグメントを割る（env 代入の作用範囲もセグメント単位）
SEPARATORS = frozenset({"&&", "||", ";", "|", "&"})


def is_assignment(token: str) -> bool:
    name, sep, _ = token.partition("=")
    return bool(sep) and name.isidentifier()


def segments(tokens: list[str]) -> list[list[str]]:
    out: list[list[str]] = [[]]
    for token in tokens:
        if token in SEPARATORS:
            out.append([])
        else:
            out[-1].append(token)
    return [s for s in out if s]


def is_isolated(segment: list[str]) -> bool:
    """このセグメントに値つきの CLAUDE_PROJECT_DIR 代入があるか."""
    return any(t.startswith(ENV_KEY) and len(t) > len(ENV_KEY) for t in segment)


def executed_paths(segment: list[str]) -> list[str]:
    """セグメントの中で**実行される**パスを返す（引数として現れただけのものは含めない）."""
    index = 0
    while index < len(segment) and is_assignment(segment[index]):
        index += 1
    if index >= len(segment):
        return []
    command = segment[index]
    if command not in INTERPRETERS:
        return [command]          # `./x.sh` / `path/x.sh` の直接実行
    for arg in segment[index + 1:]:
        if arg.startswith("-"):
            continue              # `bash -x x.sh`
        return [arg]              # インタプリタの最初の非フラグ引数
    return []


def is_hook_entry_point(token: str) -> bool:
    """実在して `safe_hook_init` を含む .sh か."""
    if not token.endswith(".sh"):
        return False
    path = Path(token)
    try:
        if not path.is_file():
            return False
        body = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return HOOK_MARKER in body


def detect(command: str) -> list[str]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    found = []
    for segment in segments(tokens):
        if is_isolated(segment):
            continue
        found.extend(p for p in executed_paths(segment) if is_hook_entry_point(p))
    return found


def main() -> int:
    for hit in detect(sys.stdin.read()):
        print(hit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
