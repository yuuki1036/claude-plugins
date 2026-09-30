"""レビューがどの経路で呼ばれたかを transcript で判定する（GitHub issue #265）.

定型レポートの省略（#250 / #232）は経路で率が違ったが、経路は payload に載らず、確かめるには
transcript を 1 本ずつ読むしかなかった（transcript は計測ストアに同期しないので、回したマシンでしか
読めない）。SKILL からは渡さない — `tokens` / `dispatch` と同じく機械判定だけを載せる。

`via` は最後の `review-timing.sh start` の呼び出しから遡って決める:

- `slash`: 人間の発話まで遡る間に `/code-review:*` の command 起動がある
- `skill-tool`: その間に assistant の `Skill` 呼び出し（`code-review:*`）がある
- `inline`: どちらも無い（SKILL を経由せずに start から手順を走らせた / #219 の型）
- `unknown`: start が見つからない・transcript を読めない

**slash を Skill より先に見る**。slash 起動では command 本文が「self-review スキルを使って」と
指示するので、モデルが直後に同じ skill を `Skill` で呼び直す（実測）。start の直前の起動だけを見ると
slash の回を `skill-tool` と取り違える。遡るのは人間の発話（slash 以外）か、前のレビューの start まで。

`parent` は start より前に最後に起動した code-review 以外の skill 名（`Skill` 呼び出しと slash の両方）。
値はこのマーケットプレイスの skill 名だけにし、それ以外は `other` にする（計測ストアの語彙に載らない
自由な名前を送らない）。
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.dont_write_bytecode = True    # mutation-ok: 配布物の `lib/` に `__pycache__` を作らせないだけで、判定にも出力にも効かない
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from report_template import START_RE, _blocks, _command  # noqa: E402

#: このマーケットプレイスのプラグイン名。`parent` はこの接頭辞を持つ名前だけを値にする
MARKETPLACE_PLUGINS = frozenset((
    "adr-keeper", "bdd-spec", "claude-meta", "code-review", "design-doc", "dev-workflow",
    "doc-freshness", "failure-journal", "feature-dev", "guardrail-protect", "issue-workflow",
    "living-spec-workflow", "notebooklm-workflow", "plugin-feedback", "plugin-manager",
    "spec-advisor", "writing-polish",
))
_NAME_RE = re.compile(r"([a-z0-9-]+):([a-z0-9-]+)")
_SLASH_RE = re.compile(r"<command-name>/([^<\s]+)</command-name>")


def _user_text(entry: dict) -> str | None:
    """人間の発話（slash を含む）の本文。tool_result・meta（command 本文の展開）・通知は None."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isCompactSummary"):
        return None
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [b.get("text") for b in content
                 if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)]
        if len(texts) == len(content) and texts:  # tool_result を 1 つでも含む行は発話ではない
            return "\n".join(texts)
    return None


def _slash(text: str) -> str | None:
    m = _SLASH_RE.search(text[:500])
    return m.group(1) if m else None


def _skill_calls(entry: dict):
    for b in _blocks(entry):
        if b.get("type") == "tool_use" and b.get("name") == "Skill":
            name = (b.get("input") or {}).get("skill")
            if isinstance(name, str):
                yield name


def _is_code_review(name: str) -> bool:
    return name.startswith("code-review:")


def _allowlisted(name: str) -> str:
    m = _NAME_RE.fullmatch(name)
    return name if m and m.group(1) in MARKETPLACE_PLUGINS else "other"


def judge_entries(entries: list) -> dict:
    """{"via": ..., "parent": ...} を返す（`entries` は transcript の行を json.loads したもの）."""
    starts = [i for i, e in enumerate(entries)
              if e.get("type") == "assistant"
              and any((c := _command(b)) is not None and START_RE.search(c) for b in _blocks(e))]
    if not starts:
        return {"via": "unknown", "parent": None}
    start, floor = starts[-1], (starts[-2] if len(starts) > 1 else -1)

    via, skill_seen = "inline", False
    for e in reversed(entries[floor + 1:start]):
        text = _user_text(e)
        if text is not None:
            cmd = _slash(text)
            if cmd is not None and _is_code_review(cmd):
                via = "slash"
                break
            # 人間の発話・他の slash が境界。通知（`<task-notification>` 等）は発話ではないので越える
            if cmd is not None or not text.lstrip().startswith("<"):
                break
        if any(_is_code_review(n) for n in _skill_calls(e)):
            skill_seen = True
    if via != "slash" and skill_seen:
        via = "skill-tool"

    parent = None
    for e in reversed(entries[:start]):
        # `Skill` の呼び出しはすべて skill。slash は `:` を持つもの（プラグインの command）だけで、
        # `/clear` などの組み込み command は skill ではないので数えない
        names = list(_skill_calls(e))
        text = _user_text(e)
        cmd = _slash(text) if text is not None else None
        if cmd is not None and ":" in cmd:
            names.append(cmd)
        others = [n for n in names if not _is_code_review(n)]
        if others:
            parent = _allowlisted(others[-1])
            break
    return {"via": via, "parent": parent}


def judge(path: str) -> dict:
    entries = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                # 判定に使うのは user / assistant だけ。大半の行（attachment 等）は読む前に落とす
                if '"user"' not in line and '"assistant"' not in line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if isinstance(e, dict):
                    entries.append(e)
    except OSError:
        return {"via": "unknown", "parent": None}
    return judge_entries(entries)


if __name__ == "__main__":
    print(json.dumps(judge(sys.argv[1]), separators=(",", ":")))
