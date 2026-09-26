"""レポート出力の定型を publish の前に出したかを transcript で判定する（GitHub issue #250）。

定型の省略は payload に載らないので、publish は通るのに正常な回と区別がつかなかった（v2.125.0 以降の
self-review 26 件中 6 件。軽量フロー経由は 3/3、テンプレートがコンテキストに入らなかった回も 3/3）。

**判定は publish 本体で行う**（hook ではない）。PreToolUse の時点では、実行中のメッセージ（直前の本文と
publish の呼び出し）がまだ transcript に書き出されていない（実測: tool の開始から約 0.06 秒後に書き出される）。
publish は tool の実行中に走り、transcript を session id で確定できる（#246）ので、書き出しを短く待てば
直前の本文まで読める。

範囲は **最後の `review-timing.sh start` の呼び出しから、その後の最後の publish の呼び出しまで**の
assistant の本文。最後の publish を使うのは、fail-fast で落ちた publish を直して再実行した回で、定型を
出してから通した publish を判定するため。目印は定型の `**指摘件数**: BLOCKER` の行（review は Step 7・
self-review は Step 6 のテンプレート。両方にある）。tool_result の中のテンプレート（SKILL.md を Read した結果）・
コマンドの中の文字列・publish の後に出した定型は数えない。

**呼び出しはコマンドの位置にあるものだけを数える**。heredoc の本文（テストや SKILL を直す python / cat）や
grep の引数に `bash "…/review-timing.sh" start` の字面が出ても、起点にも publish にもしない。

**publish の呼び出しは直近のものだけを今回の publish と見なす**（`RECENT_SEC` 以内）。subagent は親と同じ
session id を持つので、subagent から publish すると親の main transcript が引かれ、そこにある古い
start → publish の組を今回の判定として使ってしまう。古い組しか無い回は待ったうえで判定しない。

判定できない回は None を返し、呼び出し側は gap を立てない（誤って鳴らさない）: 起点の start が無い /
待ちが切れても直近の publish の呼び出しが書き出されない / transcript を読めない。**待つのは start があって
直近の publish がまだ無いときだけ**（start が無い回は待っても書き出されてこない）。
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime

MARKER = "**指摘件数**: BLOCKER"
#: コマンドの位置（行頭・`&&` / `||` / `;` / `|` の後）にある `bash <path>` の呼び出しだけを数える
_CMD_POS = r"(?:^|&&|\|\||[;|])\s*"
START_RE = re.compile(_CMD_POS + r'bash\s+"?[^\s"]*review-timing\.sh"?\s+start\b', re.M)
PUBLISH_RE = re.compile(_CMD_POS + r'bash\s+"?[^\s"]*publish-review-event\.sh', re.M)
#: heredoc の本文（`<<'EOF'` … `EOF`）。中の字面は実行されるコマンドではない
_HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?^\s*\2\s*$", re.S | re.M)
#: 今回の publish と見なす呼び出しの古さの上限（秒）。publish は呼び出しの直後に走る
RECENT_SEC = 300


def _blocks(entry: dict):
    msg = entry.get("message") if isinstance(entry, dict) else None
    content = msg.get("content") if isinstance(msg, dict) else None
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _command(block: dict) -> str | None:
    if block.get("type") != "tool_use":
        return None
    cmd = (block.get("input") or {}).get("command")
    return _HEREDOC_RE.sub("", cmd) if isinstance(cmd, str) else None


def _epoch(entry: dict) -> float | None:
    try:
        return datetime.fromisoformat(str(entry.get("timestamp")).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def judge_lines(lines, now: float | None = None) -> tuple[bool | None, bool]:
    """(定型を出したか, 待つ価値があるか) を返す。判定できなければ前者は None.

    `now` を渡すと、それより `RECENT_SEC` 以上古い publish の呼び出しを今回のものと見なさない。
    """
    entries = []
    for line in lines:
        # 大半の行（tool_result 等）は json.loads する前に落とす。transcript は数 MB になる
        if "assistant" not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("type") == "assistant":
            entries.append(entry)
    start = None
    for i, entry in enumerate(entries):
        for b in _blocks(entry):
            cmd = _command(b)
            if cmd is not None and START_RE.search(cmd):
                start = i
    if start is None:
        return None, False
    text, verdict = [], None
    for entry in entries[start + 1:]:
        for b in _blocks(entry):
            if b.get("type") == "text" and isinstance(b.get("text"), str):  # mutation-ok: `text` キーを持つのは text ブロックだけ（thinking は `thinking`、tool_use は `input`）で、and と or を分ける入力が実 transcript に無い
                text.append(b["text"])
            cmd = _command(b)
            if cmd is not None and PUBLISH_RE.search(cmd):
                ts = _epoch(entry)
                recent = now is None or ts is None or now - ts < RECENT_SEC
                verdict = any(MARKER in t for t in text) if recent else None
    return verdict, verdict is None


def judge(path: str, wait_sec: float, now: float | None = None) -> bool | None:
    """直近の publish の呼び出しが書き出されるまで最大 `wait_sec` 秒待って判定する."""
    now = time.time() if now is None else now
    deadline = time.monotonic() + wait_sec
    while True:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                verdict, worth_waiting = judge_lines(f, now)
        except OSError:
            return None
        if not worth_waiting or time.monotonic() >= deadline:  # mutation-ok: 単調時計の値が deadline と一致する瞬間は観測できない（>= と > で結果が変わらない）
            return verdict
        time.sleep(0.05)


if __name__ == "__main__":
    _wait = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    _v = judge(sys.argv[1], _wait)
    print({True: "present", False: "absent", None: "unknown"}[_v])
