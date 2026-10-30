#!/usr/bin/env python3
r"""transcript を grep で数えて、system prompt のツール定義・スキル一覧に当たる書き方を検出する（GitHub issue #342）.

stdin にコマンド文字列を受け取り、当たったら `<種別>\t<当たった grep の区間>` を 1 行 stdout に出す
（無ければ何も出さない）。常に exit 0 — どう知らせるかは呼び出し側（transcript-count-guard.sh）が決める。

transcript（`~/.claude/projects/<slug>/*.jsonl`）には、呼び出し（tool_use）のほかに次の行が入る:
- ツール定義 — `prompt_snapshot` / `api-request-shape` の行に `{"name":"<tool>","description":…}` の JSON のまま
- スキル一覧 — `attachment` の `skill_listing` に素のスキル名（`<plugin>:<skill>`）
だから素の名前で数えても、`"name":"<tool>"` の形で数えても、呼び出しが 0 回の transcript に当たる。
当たらないのは tool_use ブロックの中にしか無い並び（`"skill":"…"` / `"name":"X","input"` /
`"type":"tool_use"…`）と、slash command の `command-name>/…` だけ。

検出するもの（`.claude/projects` を含むコマンドで、grep / rg が件数を取っている区間のパターン）:
- `tool` — ツール名（`"name":"<Tool>"` / `"name":"mcp__…"` / `mcp__…` / 素の組み込みツール名）
- `skill` — 素のスキル名（`<plugin>:<skill>`。前に `"skill":"` や `command-name>/` が付かないもの）
- `var-tool` / `var-skill` — パターンが `"$var"` で、`for x in …` のリストに上のどちらかがある

件数を取っている = grep の区間に `-c` / `--count`、または後ろ 3 段までのパイプに `wc -l` / `uniq -c`。

実測（m1 の transcript の Bash 呼び出し 59,907 件・2026-06-27〜10-30）: 発火 18 件・偽陽性 0 件で、
誤計数した既知の 3 件（10-21 / 10-24 / 10-25）をすべて捉える。issue 本文の案（`"name":"` を含めば黙る）は
213 件発火して既知の 1 件しか捉えなかった — 10-24 / 10-25 はどちらも `"name":"mcp__…"` の形で数えていた。

**黙る条件**: `.claude/projects` を含まない / 含むのが `memory/` の下だけ / jq・python で `tool_use` に
絞っている（`select(… tool_use …)` / `== "tool_use"`）/ 件数を取っていない（retro の transcript
サルベージは自己訂正の語を grep するだけ）/ パターンが上の安全な並びだけ / イベント名
（`issue:completed` など）。
**拾えない形**（どれも黙る側に倒れる）: ハイフンを含まないプラグイン名のスキル（`hookify:list`）/
組み込みでない素のツール名（`lighthouse_audit`）/ `bash -c '…'` の中を `'` で入れ子にした形。
"""

from __future__ import annotations

import re
import sys

#: `memory/` だけを指すなら transcript ではない
TRANSCRIPT_DIR = re.compile(r"\.claude/projects(?![^\s'\"]*/memory\b)")
#: 呼び出しに絞って数えているコマンドは丸ごと黙る
FILTERED = re.compile(r"""jq[^|]*select\([^)]*tool_use|==\s*["']tool_use["']""")
#: grep / rg の区間（引数）と、その後ろ 3 段までのパイプ
GREP_SEG = re.compile(r"(?:^|[|;&(`\s])(?:grep|rg|egrep)\s+([^|;]*)((?:\|[^|;]*){0,3})")
COUNT_FLAG = re.compile(r"(?:^|\s)-[a-zA-Z]*c[a-zA-Z]*\b|--count")
COUNT_PIPE = re.compile(r"\bwc\s+-l|uniq\s+-c")
#: tool_use ブロックの中にしか無い並び。取り除いた残りで判定する（`\"` はシェルの二重引用符の中の形）
SAFE_FORM = re.compile(
    r'\\?"skill\\?"\s*:\s*\??\s*\\?"[^"\s]*'
    r'|"type":"tool_use"[^\s]*?"name":"[^"]*"?'
    r'|"name":"[A-Za-z_]+","input"'
    r'|command-(?:name|message)>/?[^<\s]*'
)
#: 素の名前は一般語と紛れないものだけ（Read / Edit / Write / Grep / Glob は入れない）
BUILTIN_TOOLS = ("Skill|Bash|Agent|Task|TodoWrite|ToolSearch|AskUserQuestion|WebFetch|WebSearch"
                 "|NotebookEdit|ExitPlanMode|EnterPlanMode|SendMessage")
TOOL_NAME = re.compile(
    r'\\?"name\\?":\s*\\?"(?:mcp__|[A-Z][A-Za-z]+\\?")'
    r'|\bmcp__'
    r'|(?<![\w"/.-])(?:' + BUILTIN_TOOLS + r')(?![\w"])'
)
#: プラグイン名はハイフンを含むものに限る（`http:` / `type:assistant` と紛れないように）。
#: 後ろに `: ` が続くものは YAML のキー
BARE_SKILL = re.compile(r'(?<![\w/:."-])[a-z][a-z0-9]*-[a-z0-9-]+:[a-z][a-z0-9-]+(?!["\w-]*:\s)')
#: Event Bus のイベント名（`<domain>:<verb-past>`）はスキル名ではない
EVENT = re.compile(r":(?:completed|created|implemented|logged)\b")
VAR_PATTERN = re.compile(r'"\$\{?\w+')
FOR_LIST = re.compile(r"for\s+\w+\s+in\s+([^;]+);")


def _kind(text: str) -> str | None:
    rest = SAFE_FORM.sub(" ", text)
    if TOOL_NAME.search(rest):
        return "tool"
    m = BARE_SKILL.search(rest)
    if m and not EVENT.search(m.group(0)):
        return "skill"
    return None


def find(command: str) -> tuple[str, str] | None:
    if not TRANSCRIPT_DIR.search(command) or FILTERED.search(command):
        return None
    for m in GREP_SEG.finditer(command):
        seg, tail = m.group(1), m.group(2)
        if not (COUNT_FLAG.search(seg) or COUNT_PIPE.search(tail)):
            continue
        kind = _kind(seg)
        if kind is None and not SAFE_FORM.search(seg) and VAR_PATTERN.search(seg):
            listed = _kind(" ".join(FOR_LIST.findall(command[:m.start()])))
            kind = listed and "var-" + listed
        if kind:
            return kind, (seg + tail).strip()
    return None


def main() -> int:
    hit = find(sys.stdin.read())
    if hit:
        print("%s\t%s" % (hit[0], hit[1][:160].replace("\n", " ")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
