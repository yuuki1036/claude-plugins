"""mod（hooks/review-ledger.ts）がその場で数えた usage を、publish の窓で集計する.

publish の `tokens` / `dispatch` は transcript から事後に読むので、transcript を引けない・取り違える回
（GitHub issue #246 / #263）は欠測か誤値になる。mod はリクエスト 1 回ごとの usage と subagent の起動を
イベントから直接数えて `<設定 dir>/live/<session id>.json` に書く（publish の Bash の直前に 1 回）。
ここはそれを読み、publish が `tokens_live` として transcript の値と並べて載せる形にする。

mods が無効な環境では記録が無いのが普通なので、無ければ何も出さずに exit 1（gap は立てない）。

使い方:
  live_ledger.py <t0（epoch 秒）> [<記録のパス>]
  記録のパスを省くと、`CLAUDE_CODE_SESSION_ID` と設定 dir（`lib/machine_label.py` の config_dir）から引く
"""

from __future__ import annotations

import json
import os
import re
import statistics
import sys

sys.dont_write_bytecode = True    # mutation-ok: 配布物の `lib/` に `__pycache__` を作らせないだけで、判定にも出力にも効かない
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from machine_label import config_dir  # noqa: E402

#: mod 側（`ledgerPath`）と同じ検証。ファイル名に入るので、それ以外の文字を含む id は採らない
SESSION_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def ledger_path() -> str | None:
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not SESSION_RE.match(sid):
        return None
    return os.path.join(config_dir(), "live", sid + ".json")


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _steps(ledger: dict) -> list[list]:
    """形の合う step だけを返す（`[t, agentId, model, input, output, cache_write, cache_read]`）."""
    return [s for s in ledger.get("steps") or []
            if isinstance(s, list) and len(s) == 7 and isinstance(s[1], str)
            and all(_num(x) for x in s[:1] + s[2:])]


def summarize(ledger: dict, t0_ms: int) -> dict | None:
    """窓（t0 以降）の集計。窓に main の step が無ければ None（窓の空振りを 0 として載せない）."""
    if ledger.get("schema") != 1 or not _num(ledger.get("started")):
        return None
    steps = [s for s in _steps(ledger) if s[0] >= t0_ms]
    main = [s for s in steps if s[1] == ""]
    if not main:
        return None
    sub = [s for s in steps if s[1] != ""]

    def k(rows, i):
        return round(sum(r[i] for r in rows) / 1000.0, 1)

    turns: dict[str, int] = {}
    for s in sub:
        turns[s[1]] = turns.get(s[1], 0) + 1
    per_agent = sorted(turns.values(), reverse=True)
    spawns = [a for a in (ledger.get("agents") or {}).values()
              if isinstance(a, dict) and _num(a.get("t")) and a["t"] >= t0_ms]
    return {
        "schema": 1,
        # mod が数え始めたのが t0 より後（途中で読み込まれた・再読み込みされた）なら、窓の頭が欠けている
        "covered": ledger["started"] <= t0_ms,
        "truncated": ledger.get("truncated") is True,
        "main_steps": len(main),
        "main_output_k": k(main, 4),
        "main_cache_write_k": k(main, 5),
        "main_cache_read_k": k(main, 6),
        "sub_output_k": k(sub, 4),
        "sub_cache_write_k": k(sub, 5),
        "sub_cache_read_k": k(sub, 6),
        "sub_agents": len(per_agent),
        "sub_turns": per_agent,
        "sub_turns_max": per_agent[0] if per_agent else 0,
        "sub_turns_median": statistics.median(per_agent) if per_agent else None,
        "spawns": len(spawns),
        # `run_in_background: false` を省いて起動した体（結果を取りこぼす / orchestration-guide.md `## 0`）
        "background_spawns": sum(1 for a in spawns if a.get("background") is True),
    }


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3) or not re.fullmatch(r"\d+", argv[1]):
        print("usage: live_ledger.py <t0 epoch 秒> [<記録のパス>]", file=sys.stderr)
        return 2
    path = argv[2] if len(argv) == 3 else ledger_path()
    if path is None:
        return 1
    try:
        with open(path, encoding="utf-8") as f:
            ledger = json.load(f)
    except (OSError, ValueError):
        return 1
    out = summarize(ledger, int(argv[1]) * 1000) if isinstance(ledger, dict) else None
    if out is None:
        return 1
    print(json.dumps(out, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
