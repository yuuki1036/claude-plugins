#!/usr/bin/env python3
r"""Bash tool のシェルが zsh のとき、bash のつもりで書くと黙って壊れる書き方を検出する（GitHub issue #254）.

stdin にコマンド文字列を受け取り、当たった罠を 1 行ずつ stdout に出す（無ければ何も出さない）。
常に exit 0 — 止めるかどうかは呼び出し側（zsh-trap-guard.sh）が決める。

検出するもの（どれもコマンド文字列だけで決まり、zsh で実測して壊れることを確かめた）:
- `$VAR:c` — 波括弧なしの展開の直後の `:` + 修飾子の文字を zsh は修飾子として読む
  （`"$sha:code-review/x"` は `:c` が食われて `<sha>ode-review/x` になる）。
  修飾子でない文字（`:b` `:8080`）と、引用の外に出た `:`（`"$sha":code`）は字面のまま残るので対象外
- `path` / `status` への代入 — `path` は PATH と連動する配列で、上書きや `local path` で以降の
  コマンドが command not found になる。`status` は読み取り専用で代入がエラーになる
- `echo` の引数のエスケープ — zsh の echo は `\n` `\t` `\c` などを解釈する（`-e` / `-E` を付けた回は対象外）
- 語頭の `=`（`[ a == b ]` の `==`、区切りの `=====`）— `=cmd` 展開で「= not found」になる。
  `[[ ]]` の中は条件式として読まれるので対象外
- オプションの値の引用なしグロブ（`--include=*.sh` / `find -name *.py`）— zsh は一致しない
  グロブをエラーにする（bash は字面のまま渡す）。ファイルを指すグロブ（`ls *.md`）は一致する
  ことが多く判定できないので対象外

**解析できないコマンドは黙る**（ParseError）。推測で当てにいくと、止めてはいけないコマンドを止める。
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import public_leak_shell as sh  # noqa: E402

#: zsh で `$VAR:<文字>ode/x` の形が字面のまま残らない文字（zsh 5.9 で a-z / A-Z / & を総当たりして実測）。
#: `s` は区切りが無いと bad substitution で落ちる。`f` `F` `g` `w` は後ろに続く形次第なので外した
MODIFIER_RE = re.compile(r":[acehlqrstuAPQ&]")
#: 代入すると壊れる zsh の特殊変数
SPECIAL_VARS = {"path": "PATH と連動する配列で、以降のコマンドが command not found になる",
                "status": "読み取り専用で、代入がエラーになる"}
DECLARERS = {"local", "typeset", "declare", "export", "readonly", "integer", "float"}
LOOP_WORDS = {"for", "select"}
#: `for` の前などに付き、パーサがコマンド名として読んでしまう予約語
RESERVED = {"then", "do", "else", "elif", "if", "while", "until", "!", "{", "time"}
#: zsh の echo が解釈するエスケープ（`\\` を含む）
ECHO_ESCAPE_RE = re.compile(r"\\[abcefnrtv0\\]")
#: 値にパターンを取る find のオプション
FIND_PATTERN_OPTS = {"-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename",
                     "-regex", "-iregex", "-lname", "-ilname"}


def _modifier_hits(word):
    """波括弧なしの `$NAME` / `$1` の直後が `:` + 修飾子の文字か."""
    for prev, nxt in zip(word.parts, word.parts[1:]):
        if (prev.kind == "param" and not prev.text.startswith("${") and nxt.kind == "lit"
                and prev.quoted == nxt.quoted and MODIFIER_RE.match(nxt.text)):
            yield "%s%s" % (prev.text, nxt.text[:2])


def _lit_value(word):
    """展開部分を除いた字面（引用は外した後の値）."""
    return "".join(p.text for p in word.parts if p.kind == "lit")


def _unquoted_head(word):
    """語頭の引用されていない字面（先頭の part が引用なしの lit なら、その text）."""
    if word.parts and word.parts[0].kind == "lit" and not word.parts[0].quoted:
        return word.parts[0].text
    return ""


def _check_command(cmd, out):
    for word in [w for _, w in cmd.assigns] + cmd.words + [r.target for r in cmd.redirs if r.target]:
        for hit in _modifier_hits(word):
            out.append("modifier\t%s — zsh は `:%s` を修飾子として読む。`${%s}%s` と波括弧で囲む"
                       % (hit, hit[-1], hit[1:hit.index(":")], hit[hit.index(":"):]))
        for part in word.substitutions():
            for sub in part.script or []:
                _check_command(sub, out)

    for name, _ in cmd.assigns:
        if name in SPECIAL_VARS:
            out.append("special-var\t%s= — zsh の `%s` は、%s。別の名前にする" % (name, name, SPECIAL_VARS[name]))

    words = cmd.words
    vals = [w.static() for w in words]
    i = 0
    while i < len(words) and vals[i] in RESERVED:
        i += 1
    rest, rest_vals = words[i:], vals[i:]
    if not rest:
        return
    head = rest_vals[0]

    # 予約語の後ろの代入（`then path=x`）はパーサが語として読む
    if i and rest[0].static() and re.match(r"(path|status)\+?=", rest_vals[0] or ""):
        name = rest_vals[0].split("=")[0].rstrip("+")
        out.append("special-var\t%s= — zsh の `%s` は、%s。別の名前にする" % (name, name, SPECIAL_VARS[name]))
    if head in LOOP_WORDS and len(rest) > 1 and rest_vals[1] in SPECIAL_VARS:
        name = rest_vals[1]
        out.append("special-var\t%s %s — zsh の `%s` は、%s。別の名前にする" % (head, name, name, SPECIAL_VARS[name]))
    if head in DECLARERS or head == "read":
        for v in rest_vals[1:]:
            name = (v or "").split("=")[0]
            if name in SPECIAL_VARS:
                out.append("special-var\t%s %s — zsh の `%s` は、%s。別の名前にする"
                           % (head, name, name, SPECIAL_VARS[name]))

    if head == "echo":
        opts = set()
        for v in rest_vals[1:]:
            if v and re.fullmatch(r"-[neE]+", v):
                opts.update(v[1:])
            else:
                break
        # `-e` は bash でも解釈させる意図なので、zsh で挙動が変わらない
        if not opts & {"e", "E"}:
            for w in rest[1:]:
                m = ECHO_ESCAPE_RE.search(_lit_value(w))
                if m:
                    out.append("echo-escape\techo の引数の `%s` — zsh の echo はエスケープを解釈する。"
                               "printf '%%s\\n' を使う" % m.group(0))

    if head not in ("[[",):
        for w in rest[1:]:
            h = _unquoted_head(w)
            if len(h) > 1 and h[0] == "=" and not w.raw.startswith("=("):
                out.append("equals\t%s — zsh は語頭の = をコマンドのパスに展開する（= not found）。"
                           "引用する（`[ ]` の比較は = を使う）" % w.raw)

    prev_val = None
    for w, v in zip(rest[1:], rest_vals[1:]):
        if w.glob and not w.quoted and (w.raw.startswith("-") or prev_val in FIND_PATTERN_OPTS):
            out.append("option-glob\t%s — zsh は一致しないグロブをエラーにする（no matches found）。"
                       "引用する" % w.raw)
        prev_val = v


def find_traps(command: str) -> list[str]:
    try:
        cmds = sh.parse(command)
    except (sh.ParseError, RecursionError):
        return []
    out: list[str] = []
    for cmd in cmds:
        _check_command(cmd, out)
    return list(dict.fromkeys(out))


def main() -> int:
    for line in find_traps(sys.stdin.read()):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
