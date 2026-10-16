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
自由な名前を送らない）。**遡りはレビューを頼む人間の発話で止める**（code-review の slash か、
`review` / `レビュー` を含む発話。止めたら `None`）。境界が無かった頃は、利用者が「self-review 回して」と
頼んだ回を、数時間前に起動した feature-dev / writing-polish の配下として記録していた（実測 7 回 /
GitHub issue #301）。feature-dev の phase 境界の「OK」「進めて」は越える — どの発話でも止めると、
Phase 6 の初回 self-review が parent を失う。代償として、レビューに触れた発話を挟んだ skill 経由の回は
`None` になる。

`rereview` は、修正を確かめる再レビューの申告（`--rereview`）があるか（GitHub issue #296）。修正を
確かめる再レビュー（feature-dev の G-V ループ）は 0 件が望ましい回なのに、初回と同じ母集団で数えられて
いた。推定ではなく申告を読む — 「同じセッションの 2 回目で `--focus` 付き」は、手で観点を絞った回も拾う。
**申告として読むのは次のどちらかだけ**（GitHub issue #300）:

- slash の `<command-args>`（利用者が打った引数）
- `Skill` の `args` で、前のレビューの start（無ければセッションの先頭）からその呼び出しまでに人間の発話が
  無いもの（呼び出し元 skill の手順の中）。発話を挟んだら、その発話が `rereview` / `再レビュー` を
  含むときだけ読む

利用者が「self-review 回して」としか言っていないのに、モデルが前回の構成から推して `--rereview` を足した
回があった（3 回中 2 回は修正確認ではなかった / #300）。start が無い回は `None`（判定できない）。SKILL を
経由しない回は引数を持たないので `False`。

`schema` は判定規則の版。上の 2 つの境界（#300 / #301）を入れた規則が 2 で、鍵の無い回は 1（境界の無い
規則）として読む。計測ストアは append-only で過去の回を書き換えないので、retro はこの値で層別する。

**同じ `uuid` の行は最初の 1 行だけを読む**（`report_template.drop_replayed` / #301）。セッションの先頭から
の行が同じ `uuid` のまま後ろへ書き足された transcript をそのまま遡ると、再生された古い skill の起動に当たる。
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.dont_write_bytecode = True    # mutation-ok: 配布物の `lib/` に `__pycache__` を作らせないだけで、判定にも出力にも効かない
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from report_template import START_RE, _blocks, _command, drop_replayed  # noqa: E402

#: 判定規則の版（鍵の無い回は 1）
SCHEMA = 2

#: このマーケットプレイスのプラグイン名（いまの名前）
CURRENT_PLUGINS = frozenset((
    "adr-keeper", "bdd-spec", "code-review", "design-doc", "dev-workflow",
    "doc-freshness", "failure-journal", "feature-dev", "guardrail-protect", "harness-keeper",
    "issue-workflow", "living-spec-workflow", "notebooklm-workflow", "plugin-feedback",
    "plugin-manager", "spec-advisor", "writing-polish",
))
#: 改名した旧名。改名前の transcript を読むので残す（`claude-meta` → `harness-keeper` は
#: Claude Code 2.1.292 の予約名を避けた改名）
FORMER_PLUGINS = frozenset(("claude-meta",))
#: `parent` はこの接頭辞を持つ名前だけを値にする
MARKETPLACE_PLUGINS = CURRENT_PLUGINS | FORMER_PLUGINS
_NAME_RE = re.compile(r"([a-z0-9-]+):([a-z0-9-]+)")
_SLASH_RE = re.compile(r"<command-name>/([^<\s]+)</command-name>")
_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.S)
#: 再レビューの申告（self-review の引数。feature-dev の G-V ループが渡す）
REREVIEW_FLAG = "--rereview"
#: 利用者が発話で再レビューを明示したか（`--rereview` も含む）
_REREVIEW_ASK_RE = re.compile(r"rereview|再レビュー", re.I)
#: レビューを頼む発話。`(?<![a-z])` は `preview` を拾わないため（`self-review` は `-` の後なので拾う）
_REVIEW_ASK_RE = re.compile(r"(?<![a-z])review|レビュー", re.I)


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
    for name, _ in _skill_calls_with_args(entry):
        yield name


def _skill_calls_with_args(entry: dict):
    for b in _blocks(entry):
        if b.get("type") == "tool_use" and b.get("name") == "Skill":
            inp = b.get("input") or {}
            name, args = inp.get("skill"), inp.get("args")
            if isinstance(name, str):
                yield name, args if isinstance(args, str) else ""


def _declares_rereview(args: str) -> bool:
    return REREVIEW_FLAG in args.split()


def _is_code_review(name: str) -> bool:
    return name.startswith("code-review:")


def _allowlisted(name: str) -> str:
    m = _NAME_RE.fullmatch(name)
    return name if m and m.group(1) in MARKETPLACE_PLUGINS else "other"


def _unjudged() -> dict:
    return {"via": "unknown", "parent": None, "rereview": None, "schema": SCHEMA}


def judge_entries(entries: list) -> dict:
    """{"via", "parent", "rereview", "schema"} を返す（`entries` は transcript の行を json.loads したもの）."""
    entries = drop_replayed(entries)
    starts = [i for i, e in enumerate(entries)
              if e.get("type") == "assistant"
              and any((c := _command(b)) is not None and START_RE.search(c) for b in _blocks(e))]
    if not starts:
        return _unjudged()
    start, floor = starts[-1], (starts[-2] if len(starts) > 1 else -1)

    via, skill_seen, skill_rereview, rereview = "inline", False, False, False
    prompt = None    # 遡りを止めた人間の発話（None = 前の start かセッションの先頭まで発話が無い）
    for e in reversed(entries[floor + 1:start]):
        text = _user_text(e)
        if text is not None:
            cmd = _slash(text)
            if cmd is not None and _is_code_review(cmd):
                via = "slash"
                m = _ARGS_RE.search(text)
                # slash の後にモデルが Skill で呼び直すときの args は利用者の申告ではない（#300）
                rereview = bool(m and _declares_rereview(m.group(1)))
                break
            # 人間の発話・他の slash が境界。通知（`<task-notification>` 等）は発話ではないので越える
            if cmd is not None or not text.lstrip().startswith("<"):
                prompt = text
                break
        for name, args in _skill_calls_with_args(e):
            if _is_code_review(name):
                skill_seen = True
                skill_rereview = skill_rereview or _declares_rereview(args)
    if via != "slash":
        if skill_seen:
            via = "skill-tool"
        rereview = skill_rereview and (prompt is None or bool(_REREVIEW_ASK_RE.search(prompt)))

    parent = None
    for e in reversed(entries[:start]):
        # `Skill` の呼び出しはすべて skill。slash は `:` を持つもの（プラグインの command）だけで、
        # `/clear` などの組み込み command は skill ではないので数えない
        names = list(_skill_calls(e))
        text = _user_text(e)
        cmd = _slash(text) if text is not None else None
        if cmd is not None and ":" in cmd:
            if _is_code_review(cmd):
                break
            names.append(cmd)
        elif text is not None and not text.lstrip().startswith("<") and _REVIEW_ASK_RE.search(text):
            break
        others = [n for n in names if not _is_code_review(n)]
        if others:
            parent = _allowlisted(others[-1])
            break
    return {"via": via, "parent": parent, "rereview": rereview, "schema": SCHEMA}


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
        return _unjudged()
    return judge_entries(entries)


if __name__ == "__main__":
    print(json.dumps(judge(sys.argv[1]), separators=(",", ":")))
