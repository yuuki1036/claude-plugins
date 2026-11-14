#!/usr/bin/env python3
"""measure-interventions.py — transcript から人の介入点を数える（AI-DLC v2 原則 1 の物差し）.

人がどこで判断・修正・差し戻しをしているかを数え、機械の検査へ移す候補を選ぶための計測。
入力は `~/.claude/projects/<slug>/*.jsonl` の main transcript（`subagents/` 配下と isSidechain の行は除く）。
transcript はマシンローカルなので、マシンごとに走らせる。

人の発話は `origin.kind == "human"` の user 行だけを数える。この欄が無い行は claude -p の eval・grader・
別セッションからの起動で、人の発話ではない（m1 の実測で、origin が無く promptSource=sdk の 1,281 行中
882 行が eval のプロンプトだった）。

出力（--out の下。既定は毎回新しく作る一時ディレクトリ。固定名にすると、共有の /tmp で他のユーザーが先に
置いた dir や symlink に書きうる）。集計（--merge 以外）の --out が git の作業ツリーの中なら exit 2 で止める
（本文を含む events.jsonl がコミットされうる。~/.claude も git で管理していることがある）:
- summary.md / summary.json — 件数だけ。共有してよい。既定でプロジェクト名・質問の見出し・
  このマーケットプレイス外のスキル名と hook のプラグイン名・MCP サーバー名を伏せる（--names で出す）
- events.jsonl — 1 介入 1 行。人の発話の本文と直前の assistant 発話の末尾を含むので**持ち出さない**

`--merge m1/summary.json m2/summary.json` はマシンごとの summary.json を足し合わせる（合算を LLM にさせない）。
期間の指定（since / until）が揃っていない・伏せ字なしの summary が混ざるときは stderr に警告する。
`--labels labels.jsonl` は、LLM が events.jsonl の発話に付けた分類（1 行 1 件の
`{"session", "ts", "qi", "label", "target"}`）を (session, ts, qi) で突き合わせて summary に件数として足す。
qi は AskUserQuestion の何問目か（prompt の行には無い）。1 回の呼び出しの質問はどれも同じ ts を持つため。
語彙は LABELS / TARGETS に固定し、外れた値は `(語彙外)`、修正・差し戻し・方針の指定で target が無いものは
`(未記入)`、突き合わない行は `unmatched_labels`、同じキーの 2 行目以降は `duplicate_labels` に数える
（綴りの揺れ・書き漏れ・重複で件数が黙って消えないように）。`check` などそれ以外の欄は summary に出さない。
分類の対象は本文を持つ prompt（start / free / reply / button-primary / button-alt）と question:free-text の行だけ。

介入の種別（kind:sub）:
- prompt:start — セッション最初の発話（作業の起動。介入ではなく分母）
- prompt:slash / prompt:bash — slash command / `!` で人が打ったシェル
- prompt:button-primary / prompt:button-alt — wrap_up のボタン。primary は actions[0]（Claude の推奨）
- prompt:reply — 直前に問いがあった応答（wrap_up の ask か、assistant の末尾 3 行に問いの記号か、
  問い・依頼の文末（ください・ますか 等））
- prompt:free — 問われずに出した発話。修正・差し戻し・方針の指定の候補で、中身は LLM が分類する
- prompt:card — 提案カードの「ここで実行」（アプリが送る定型文）
- prompt:resume — 利用上限の解除・要約後の続き（分母にも数えない）
- question:recommended / question:alternative / question:multi / question:free-text / question:unanswered —
  AskUserQuestion の 1 問。推奨は label に Recommended / 推奨 を含む選択肢、無ければ先頭
- interrupt:turn / interrupt:tool-use — 人が中断した
- reject:<tool> — 人が tool の呼び出しを拒否した（AskUserQuestion を閉じたものは reject:AskUserQuestion）
- hook-block:<plugin> — PreToolUse hook が止めた。人ではなく機械の介入で、比較のために数える

prompt には文の形（form）も付ける。sub（問われたか）とは独立:
continue（「次」「y」「進めて」等の続行だけ）/ poll（「まだ？」等の催促）/ routine（commit・push・merged 等の
定型操作の語だけ）/ choice（「1」「A」「1,2」等の番号か英字 1 文字の選び。「n」「no」「ng」は text）/ pasted（貼り付け）/
text（それ以外）。
continue・routine が多い所は、人が止まった工程を押し進めているだけで、機械に移す第一候補になる。

同じ uuid の行が別のファイルにもう一度出たら（fork・続きのセッションに複製された履歴）、2 回目以降は数えない。

スキルへの帰属: 同じセッションで直前に起動したスキル（Skill tool / 組み込みでない slash command）に、起動の後の人の
発話 5 回目まで帰属させる（slash は起動の発話自身も帰属する）。それより後と、起動の無いものは (no-skill)。

exit: 0 = 集計した / 2 = transcript の dir が無い・1 件も無い・期間に入るセッションが無い・--out が git の
作業ツリーの中・--merge / --labels の入力を読めない（0 件の集計を正常に見せない）。
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import re
import sys
import tempfile
from pathlib import Path

SKILL_WINDOW = 5
CONTEXT_CHARS = 400
NO_SKILL = "(no-skill)"
OTHER_SKILL = "(other-skill)"

REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
COMMAND_NAME = re.compile(r"<command-name>/?([^<\s]+)</command-name>")
RECOMMENDED = re.compile(r"Recommended|推奨")
REJECTED = "The user doesn't want to proceed with this tool use"
INTERRUPTED = "[Request interrupted by user"
# hook error の 1 行目: `[bash <path>/cache/<marketplace>/<plugin>/<ver>/hooks/scripts/<x>]: [<label>] ...`
# と `[command hook 14]: [<label>] ...` の 2 形がある
HOOK_PATH = re.compile(r"/cache/[^/]+/([^/]+)/[^/]+/hooks/scripts/")
HOOK_LABEL = re.compile(r"hook error: \[[^\]]*\]:\s*\[([^\]]+)\]")
RESUME_PREFIXES = ("I hit my usage limit", "This session is being continued", "作業中に利用制限に達しましたが")
CARD_PREFIX = "このタスクをここで実行してください"
ASK_TAIL = re.compile(r"(ください|しますか|ますか|でしょうか)[。.]?$")
CONTINUE_WORDS = frozenset(
    "y yes ok okay はい うん next 次 つぎ tugi 次へ continue 続けて 続き 進めて すすめて 進めてください やって "
    "お願い お願いします go どうぞ 次は".split()
)
POLL_WORDS = frozenset("まだ 状況 状況確認 どう 終わった できた 進捗".split())
ROUTINE_WORDS = frozenset(
    "commit push pr merge merged maintain done コミット プッシュ マージ マージした 完了 commitして pushして".split()
)
LABELS = ("修正", "差し戻し", "方針の指定", "追加の依頼", "新しい依頼", "質問", "情報の提供", "続行・承認")
TARGETS = ("決定的な検査", "LLM の判定", "人の判断")
NEEDS_TARGET = ("修正", "差し戻し", "方針の指定")
OUT_OF_VOCAB = "(語彙外)"
NO_TARGET = "(未記入)"
# 英字は 1 文字に限る（2 文字にすると「no」「ng」まで番号選びに入る）
CHOICE = re.compile(r"^([0-9]{1,2}|[a-z])(\s*[,、と]\s*([0-9]{1,2}|[a-z]))*$")
# y/n の問いへの「n」は選びではなく拒否（差し戻しの候補）なので text に残す
NEGATIVE_LETTERS = frozenset(("n",))
LABELABLE_SUBS = frozenset(("start", "free", "reply", "button-primary", "button-alt"))
# スキルではない組み込みの slash command（スキルの帰属を上書きさせない）
BUILTIN_COMMANDS = frozenset(
    "add-dir agents btw bug clear compact config context cost doctor effort exit export fast help hooks ide "
    "init login logout mcp memory model output-style permissions plugin plugins privacy-settings "
    "release-notes resume rewind status statusline terminal-setup theme todos upgrade usage vim".split()
)


def load_marketplace_plugins(path: Path | None = None) -> frozenset[str]:
    path = path or Path(__file__).resolve().parents[1] / "marketplace.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return frozenset(p["name"] for p in data.get("plugins", []) if isinstance(p, dict) and "name" in p)
    except (OSError, ValueError, KeyError, TypeError):
        return frozenset()


def text_of(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text") or "" for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def tool_result_text(block: dict) -> str:
    c = block.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(x.get("text") or "" for x in c if isinstance(x, dict))
    return ""


def asked(assistant_text: str) -> bool:
    """assistant の発話の末尾が問いで終わっているか（境界は LLM の分類で見直す前提の近似）."""
    lines = [ln.strip() for ln in assistant_text.splitlines() if ln.strip()]
    return any("？" in ln or ln.endswith("?") or ASK_TAIL.search(ln) for ln in lines[-3:])


def form_of(text: str) -> str:
    if text.startswith("<pasted_content"):
        return "pasted"
    norm = text.strip().lower().replace("ｙ", "y").rstrip("。.!！?？ ")
    # 語の一覧を番号選びより先に見る（CONTINUE_WORDS の「y」は CHOICE の英字 1 文字にも合う）
    if norm in CONTINUE_WORDS:
        return "continue"
    if norm in POLL_WORDS:
        return "poll"
    words = [w for w in re.split(r"[\s、,→]+", norm) if w]
    if words and all(w in ROUTINE_WORDS for w in words):
        return "routine"
    if norm not in NEGATIVE_LETTERS and CHOICE.match(norm):
        return "choice"
    return "text"


def button_index(text: str, wrap: dict | None) -> int | None:
    if not wrap:
        return None
    for i, a in enumerate(wrap.get("actions") or []):
        if not isinstance(a, dict):
            continue
        for key in ("label", "message"):
            v = a.get(key)
            if isinstance(v, str) and v.strip() and text == v.strip():
                return i
    return None


def classify_answer(question: dict, answer: object) -> tuple[str, bool]:
    """(sub, 推奨が明示されていたか) を返す."""
    labels = [o.get("label") or "" for o in question.get("options") or [] if isinstance(o, dict)]
    marked = [i for i, label in enumerate(labels) if RECOMMENDED.search(label)]
    rec = marked[0] if marked else 0
    if answer is None or answer == "" or answer == []:
        return "unanswered", bool(marked)
    if isinstance(answer, list):
        if answer and all(a in labels for a in answer):
            return "multi", bool(marked)
        return "free-text", bool(marked)
    if answer in labels:
        return ("recommended" if labels.index(answer) == rec else "alternative"), bool(marked)
    parts = [p.strip() for p in str(answer).split(",")]
    if question.get("multiSelect") and parts and all(p in labels for p in parts):
        return "multi", bool(marked)
    return "free-text", bool(marked)


def labelable(e: dict) -> bool:
    """分類の対象は本文を持つ人の発話と、AskUserQuestion の自由記述（同じ ts の他の介入に分類を波及させない）."""
    return (e["kind"] == "prompt" and e["sub"] in LABELABLE_SUBS) or (e["kind"] == "question" and e["sub"] == "free-text")


def label_key(e: dict) -> tuple:
    return (e["session"], e["ts"], e.get("qi"))


def hook_plugin(text: str) -> str:
    m = HOOK_PATH.search(text) or HOOK_LABEL.search(text)
    return m.group(1) if m else "(non-plugin)"


class Scanner:
    def __init__(self, since: str | None, until: str | None):
        self.since = since
        self.until = until
        self.events: list[dict] = []
        self.sessions: dict[str, dict] = {}
        self.activations: collections.Counter = collections.Counter()
        self.tool_calls = 0
        self.bad_lines = 0
        self.first_ts: str | None = None
        self.last_ts: str | None = None
        self.labels: dict[tuple, dict] | None = None
        self.unmatched_labels = 0
        self.duplicate_labels = 0
        self.seen_uuids: set[str] = set()

    def load_labels(self, path: Path) -> None:
        """events に無いキーを指す行は unmatched に数える（events を作り直した後の古い分類など）.

        行が object でないときは ValueError（main が exit 2 にする）。
        """
        keys = {label_key(e) for e in self.events if labelable(e)}
        self.labels = {}
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{n} 行目が object ではない")
            qi = row.get("qi")
            if not (isinstance(row.get("session"), str) and isinstance(row.get("ts"), str)
                    and (qi is None or (isinstance(qi, int) and not isinstance(qi, bool)))):
                self.unmatched_labels += 1
                continue
            key = (row["session"], row["ts"], qi)
            if key not in keys:
                self.unmatched_labels += 1
            elif key in self.labels:
                self.duplicate_labels += 1
            else:
                self.labels[key] = row

    def in_window(self, ts: str) -> bool:
        if not ts:
            return False
        if self.since and ts < self.since:
            return False
        if self.until and ts >= self.until:
            return False
        return True

    def scan(self, path: Path) -> None:
        sid = path.stem
        project = path.parent.name
        st = {"human": 0, "skill": None, "skill_turn": 0, "last_asst": "", "wrap": None, "tools": {}}
        session = {"project": project, "in_window": False, "human": 0}

        def emit(ts: str, kind: str, sub: str, **extra: object) -> None:
            skill = st["skill"]
            if not skill or st["human"] - st["skill_turn"] >= SKILL_WINDOW:
                skill = NO_SKILL
            self.events.append(
                {"session": sid, "project": project, "ts": ts, "kind": kind, "sub": sub, "skill": skill, **extra}
            )

        try:
            fh = open(path, encoding="utf-8", errors="replace")
        except OSError:
            return
        with fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except ValueError:
                    self.bad_lines += 1
                    continue
                if not isinstance(o, dict) or o.get("isSidechain"):
                    continue
                ts = o.get("timestamp") or ""
                win = self.in_window(ts)
                uid = o.get("uuid")
                if isinstance(uid, str):
                    # 複製された履歴は状態（発話の順番・直前の問い）だけ進め、数えない
                    if uid in self.seen_uuids:
                        win = False
                    self.seen_uuids.add(uid)
                if win:
                    session["in_window"] = True
                    self.first_ts = min(self.first_ts or ts, ts)
                    self.last_ts = max(self.last_ts or ts, ts)
                msg = o.get("message") if isinstance(o.get("message"), dict) else {}
                content = msg.get("content")
                kind = o.get("type")

                if kind == "assistant":
                    for b in content if isinstance(content, list) else []:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "text" and (b.get("text") or "").strip():
                            st["last_asst"] = b["text"]
                        elif b.get("type") == "tool_use":
                            name = b.get("name") or ""
                            inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                            st["tools"][b.get("id")] = name
                            if win:
                                self.tool_calls += 1
                            if name == "Skill" and inp.get("skill"):
                                st["skill"], st["skill_turn"] = inp["skill"], st["human"]
                                if win:
                                    self.activations[inp["skill"]] += 1
                            elif name.endswith("wrap_up"):
                                st["wrap"] = inp if inp.get("ask") else None
                    continue  # mutation-ok: 外しても直後の kind != "user" の continue で同じく読み飛ばす
                if kind != "user":
                    continue

                if isinstance(content, list):
                    for b in content:
                        if not isinstance(b, dict) or b.get("type") != "tool_result":
                            continue
                        txt = tool_result_text(b)
                        if txt.startswith(REJECTED) and win:
                            emit(ts, "reject", st["tools"].get(b.get("tool_use_id"), "(unknown)"))
                        elif txt.startswith("PreToolUse:") and "hook error" in txt[:200] and win:
                            emit(ts, "hook-block", hook_plugin(txt))
                result = o.get("toolUseResult")
                if isinstance(result, dict) and "questions" in result and "answers" in result and win:
                    answers = result.get("answers") if isinstance(result.get("answers"), dict) else {}
                    for qi, q in enumerate(result.get("questions") or []):
                        if not isinstance(q, dict):
                            continue
                        answer = answers.get(q.get("question"))
                        sub, marked = classify_answer(q, answer)
                        emit(ts, "question", sub, qi=qi, header=q.get("header") or "", question=q.get("question") or "",
                             answer=answer, options=len(q.get("options") or []), recommended_marked=marked)

                raw = text_of(content).lstrip()
                if raw.startswith(INTERRUPTED):
                    if win:
                        emit(ts, "interrupt", "tool-use" if "for tool use" in raw[:60] else "turn")
                    continue
                origin = o.get("origin")
                if o.get("isMeta") or not (isinstance(origin, dict) and origin.get("kind") == "human"):
                    continue
                text = REMINDER.sub("", text_of(content)).strip()
                if not text:
                    continue

                cmd = COMMAND_NAME.search(text) if text.startswith("<command-") else None
                if cmd:
                    sub = "slash"
                    name = cmd.group(1)
                    if name not in BUILTIN_COMMANDS:
                        # Skill tool は起動を促した発話を数えた後に立つので、slash も起動の発話の次から 5 回を数える
                        st["skill"], st["skill_turn"] = name, st["human"] + 1
                        if win:
                            self.activations[name] += 1
                elif text.startswith("<bash-input>"):
                    sub = "bash"
                elif text.startswith(RESUME_PREFIXES):
                    sub = "resume"
                elif text.startswith(CARD_PREFIX):
                    sub = "card"
                else:
                    idx = button_index(text, st["wrap"])
                    if idx is not None:
                        sub = "button-primary" if idx == 0 else "button-alt"
                    elif st["wrap"] or asked(st["last_asst"]):
                        sub = "reply"
                    elif st["human"] == 0:
                        sub = "start"
                    else:
                        sub = "free"
                if win:
                    extra: dict = {}
                    if sub in ("free", "reply", "button-primary", "button-alt", "start"):
                        extra = {"form": form_of(text), "text": text, "context": st["last_asst"][-CONTEXT_CHARS:]}
                    emit(ts, "prompt", sub, **extra)
                    if sub != "resume":
                        session["human"] += 1
                if sub != "resume":
                    st["human"] += 1
                st["wrap"] = None
                st["last_asst"] = ""
        if session["in_window"]:
            self.sessions[f"{project}/{sid}"] = session  # 同じ sid のファイルが別 project dir にもあることがある


def public_skill(name: str, market: frozenset[str], names: bool) -> str:
    if names or name in (NO_SKILL, OTHER_SKILL):
        return name
    plugin, sep, _ = name.partition(":")
    return name if sep and plugin in market else OTHER_SKILL


def public_tool(name: str, names: bool) -> str:
    if names or not name.startswith("mcp__"):
        return name
    return "mcp__(server)__" + name.rsplit("__", 1)[-1]


def summarize(sc: Scanner, market: frozenset[str], names: bool, args: argparse.Namespace) -> dict:
    by_kind: collections.Counter = collections.Counter()
    by_skill: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    headers: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    projects_raw: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    forms: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    skill_forms: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for e in sc.events:
        sub = e["sub"]
        if e["kind"] == "reject":
            sub = public_tool(sub, names)
        elif e["kind"] == "hook-block" and not names and sub not in market:
            sub = "(other)"
        key = f'{e["kind"]}:{sub}'
        by_kind[key] += 1
        by_skill[public_skill(e["skill"], market, names)][key] += 1
        projects_raw[e["project"]][key] += 1
        if e["kind"] == "question":
            headers[e["header"] or "(no-header)"][sub] += 1
        if "form" in e:
            forms[sub][e["form"]] += 1
            skill_forms[public_skill(e["skill"], market, names)][e["form"]] += 1
    order = sorted(projects_raw, key=lambda p: -sum(projects_raw[p].values()))
    projects = {
        (p if names else f"P{i + 1}"): dict(projects_raw[p]) for i, p in enumerate(order)
    }
    activations: collections.Counter = collections.Counter()
    for k, v in sc.activations.items():
        activations[public_skill(k, market, names)] += v
    with_human = sum(1 for s in sc.sessions.values() if s["human"])
    out = {
        "schema": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": {"since": args.since, "until": args.until, "first_ts": sc.first_ts, "last_ts": sc.last_ts},
        "anonymized": not names,
        "sessions": {"total": len(sc.sessions), "with_human": with_human,
                     "without_human": len(sc.sessions) - with_human},
        "human_prompts": sum(v for k, v in by_kind.items() if k.startswith("prompt:") and k != "prompt:resume"),
        "tool_calls": sc.tool_calls,
        "unreadable_lines": sc.bad_lines,
        "by_kind": dict(by_kind.most_common()),
        "skill_activations": dict(activations.most_common()),
        "by_skill": {s: dict(c.most_common()) for s, c in sorted(by_skill.items(), key=lambda x: -sum(x[1].values()))},
        "prompt_forms": {k: dict(c.most_common()) for k, c in forms.items()},
        "skill_prompt_forms": {k: dict(c.most_common()) for k, c in skill_forms.items()},
        "projects": projects,
    }
    if sc.labels is not None:
        labels: collections.Counter = collections.Counter()
        by_skill_label: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        targets: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for e in sc.events:
            lab = sc.labels.get(label_key(e)) if labelable(e) else None
            if not lab:
                continue
            label = lab.get("label") if lab.get("label") in LABELS else OUT_OF_VOCAB
            labels[label] += 1
            by_skill_label[public_skill(e["skill"], market, names)][label] += 1
            target = lab.get("target")
            if target:
                targets[label][target if target in TARGETS else OUT_OF_VOCAB] += 1
            elif label in NEEDS_TARGET:
                targets[label][NO_TARGET] += 1
        out["labels"] = dict(labels.most_common())
        out["labels_by_skill"] = {k: dict(c.most_common()) for k, c in by_skill_label.items()}
        out["label_targets"] = {k: dict(c.most_common()) for k, c in targets.items()}
        out["unmatched_labels"] = sc.unmatched_labels
        out["duplicate_labels"] = sc.duplicate_labels
    if names:
        out["question_headers"] = {
            h: dict(c.most_common()) for h, c in sorted(headers.items(), key=lambda x: -sum(x[1].values()))
        }
    return out


def table(rows: list[list[object]], head: list[str]) -> list[str]:
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return lines


INTERVENTION_KEYS = [
    "prompt:free", "prompt:reply", "prompt:button-primary", "prompt:button-alt",
    "question:recommended", "question:alternative", "question:multi", "question:free-text",
    "interrupt:turn", "interrupt:tool-use",
]


def render_md(s: dict) -> str:
    w = s["window"]
    lines = [
        "# 人の介入点の計測",
        "",
        f'- 期間: {w["first_ts"]} 〜 {w["last_ts"]}（指定 since={w["since"]} until={w["until"]}）',
        f'- セッション {s["sessions"]["total"]}（人の発話あり {s["sessions"]["with_human"]}）'
        f' / 人の発話 {s["human_prompts"]} / tool 呼び出し {s["tool_calls"]}',
        f'- 伏せ字: {"あり（--names で解除）" if s["anonymized"] else "なし（共有しない）"}',
        "",
        "## 種別ごとの件数",
        "",
    ]
    lines += table([[k, v] for k, v in s["by_kind"].items()], ["kind:sub", "件数"])
    form_keys = ["continue", "routine", "choice", "poll", "pasted", "text"]
    lines += ["", "## 人の発話の形（sub × form）", "",
              "continue・routine は、人が止まった工程を押し進めているだけの発話。", ""]
    lines += table([[k] + [c.get(f, 0) for f in form_keys] for k, c in s["prompt_forms"].items()], ["sub"] + form_keys)
    lines += ["", "## スキルごとの介入", "",
              "列は主な介入の種別。起動はスキルの起動回数（Skill tool と slash command）。"
              "continue / routine は free・reply・ボタンを合わせた発話の形の件数。", ""]
    head = (["スキル", "起動"] + [k.split(":", 1)[1] for k in INTERVENTION_KEYS]
            + ["continue", "routine", "reject", "hook-block"])
    rows = []
    for skill, c in s["by_skill"].items():
        rej = sum(v for k, v in c.items() if k.startswith("reject:"))
        hook = sum(v for k, v in c.items() if k.startswith("hook-block:"))
        fm = s["skill_prompt_forms"].get(skill, {})
        rows.append([skill, s["skill_activations"].get(skill, "-")] + [c.get(k, 0) for k in INTERVENTION_KEYS]
                    + [fm.get("continue", 0), fm.get("routine", 0), rej, hook])
    lines += table(rows, head)
    if "question_headers" in s:
        lines += ["", "## AskUserQuestion の見出しごと（推奨を選んだ割合が高いものは自動化の候補）", ""]
        hrows = []
        for h, c in s["question_headers"].items():
            total = sum(c.values())
            rec = c.get("recommended", 0)
            hrows.append([h, total, rec, f"{rec / total:.0%}" if total else "-",
                          c.get("alternative", 0), c.get("free-text", 0), c.get("multi", 0)])
        lines += table(hrows, ["見出し", "回数", "推奨", "推奨率", "別の選択肢", "自由記述", "複数選択"])
    if "labels" in s:
        lines += ["", "## 発話の分類（LLM が付けたラベル）", "",
                  f'突き合わなかった分類の行: {s.get("unmatched_labels", 0)}'
                  f' / 同じキーの 2 行目以降: {s.get("duplicate_labels", 0)}', ""]
        lines += table([[k, v] for k, v in s["labels"].items()], ["ラベル", "件数"])
        tkeys = list(TARGETS) + [NO_TARGET, OUT_OF_VOCAB]
        lines += ["", "移し先（修正・差し戻し・方針の指定に付ける）", ""]
        lines += table([[k] + [c.get(t, 0) for t in tkeys] for k, c in s.get("label_targets", {}).items()],
                       ["ラベル"] + tkeys)
        lkeys = list(LABELS) + [OUT_OF_VOCAB]
        lines += ["", "スキルごと", ""]
        lines += table([[k] + [c.get(x, 0) for x in lkeys] for k, c in s.get("labels_by_skill", {}).items()],
                       ["スキル"] + lkeys)
    lines += ["", "## プロジェクトごと", ""]
    prow = [[p, sum(c.values()), c.get("prompt:free", 0), sum(v for k, v in c.items() if k.startswith("question:"))]
            for p, c in s["projects"].items()]
    lines += table(prow, ["プロジェクト", "全件", "free", "question"])
    return "\n".join(lines) + "\n"


COUNTER_KEYS = ("by_kind", "skill_activations", "by_skill", "prompt_forms", "skill_prompt_forms", "question_headers",
                "labels", "labels_by_skill", "label_targets")
OPTIONAL_KEYS = ("question_headers", "labels", "labels_by_skill", "label_targets")
SCALAR_KEYS = ("human_prompts", "tool_calls", "unreadable_lines", "unmatched_labels", "duplicate_labels")


def add_counts(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if isinstance(v, dict):
            add_counts(dst.setdefault(k, {}), v)
        else:
            dst[k] = dst.get(k, 0) + v


def by_total(d: dict) -> dict:
    def total(v: object) -> int:
        return sum(total(x) for x in v.values()) if isinstance(v, dict) else int(v)
    return {k: (by_total(v) if isinstance(v, dict) else v) for k, v in sorted(d.items(), key=lambda x: -total(x[1]))}


def merge_warnings(parts: list[dict]) -> list[str]:
    warn = []
    for key in ("since", "until"):
        vals = {(p.get("window") or {}).get(key) for p in parts}
        if len(vals) > 1:
            warn.append(f"{key} が揃っていない: {sorted(map(str, vals))}（期間の違う集計を足している）")
    plain = [str(i) for i, p in enumerate(parts, 1) if not p.get("anonymized")]
    if plain:
        warn.append(f"伏せ字なしの summary が混ざっている（{', '.join(plain)} 番目）。合算の結果も共有しない")
    return warn


def common_window_value(parts: list[dict], key: str) -> str | None:
    vals = {(p.get("window") or {}).get(key) for p in parts}
    return vals.pop() if len(vals) == 1 else None


def merge_summaries(parts: list[dict]) -> dict:
    """マシンごとの summary.json を足し合わせる。プロジェクトは M<n>- を前に付けて分けたまま残す.

    since / until は全 part で同じときだけ残す（違えば None。merge_warnings が警告する）。
    """
    out: dict = {"schema": 1, "merged_from": len(parts),
                 "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "window": {"since": common_window_value(parts, "since"), "until": common_window_value(parts, "until"),
                            "first_ts": None, "last_ts": None},
                 "anonymized": all(p.get("anonymized") for p in parts),
                 "sessions": {}, "projects": {}}
    for k in COUNTER_KEYS:
        if k not in OPTIONAL_KEYS or any(k in p for p in parts):
            out[k] = {}
    for k in SCALAR_KEYS:
        out[k] = 0
    for i, p in enumerate(parts, 1):
        w = p.get("window") or {}
        for key, pick in (("first_ts", min), ("last_ts", max)):
            vals = [v for v in (out["window"][key], w.get(key)) if v]
            out["window"][key] = pick(vals) if vals else None
        add_counts(out["sessions"], p.get("sessions") or {})
        for k in COUNTER_KEYS:
            if k in p:
                add_counts(out[k], p[k])
        for k in SCALAR_KEYS:
            out[k] += p.get(k) or 0
        for name, c in (p.get("projects") or {}).items():
            out["projects"][f"M{i}-{name}"] = c
    for k in COUNTER_KEYS:
        if k in out:
            out[k] = by_total(out[k])
    return out


def inside_git_worktree(path: Path) -> bool:
    p = path.expanduser().resolve()
    return any((d / ".git").exists() for d in (p, *p.parents))


def write_summary(out: Path, summary: dict) -> str:
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = render_md(summary)
    (out / "summary.md").write_text(md, encoding="utf-8")
    return md


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="transcript から人の介入点を数える")
    ap.add_argument("--merge", nargs="+", metavar="SUMMARY_JSON",
                    help="transcript を読まず、マシンごとの summary.json を足し合わせて --out に書く")
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--since", help="この日時以降（YYYY-MM-DD か ISO 8601。UTC）")
    ap.add_argument("--until", help="この日時より前（YYYY-MM-DD か ISO 8601。UTC）")
    ap.add_argument("--days", type=int, help="直近 N 日（--since より優先）")
    ap.add_argument("--project", help="slug にこの文字列を含むプロジェクトだけ")
    ap.add_argument("--names", action="store_true", help="プロジェクト名・見出し・スキル名を伏せない")
    ap.add_argument("--labels", help="LLM が付けた分類の JSONL（events.jsonl の session・ts と突き合わせる）")
    ap.add_argument("--out", help="出力 dir（既定は毎回新しく作る一時 dir）")
    args = ap.parse_args(argv)
    # 検査と書き込みで同じパスを使う（`--out=~/x` はシェルが展開しない）
    if args.out:
        args.out = os.path.expanduser(args.out)
    if args.days is not None:
        args.since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.days)).strftime("%Y-%m-%d")

    if args.merge:
        parts = []
        for f in args.merge:
            try:
                p = json.loads(Path(f).read_text(encoding="utf-8"))
                if not isinstance(p, dict):
                    raise ValueError("object ではない")
            except (OSError, ValueError) as e:
                print(f"summary.json を読めません: {f}（{e}）", file=sys.stderr)
                return 2
            parts.append(p)
        try:
            merged = merge_summaries(parts)
            render_md(merged)  # 書き出す前に描画できるかを見る（中身の形が違うと半端な出力が残る）
        except (TypeError, ValueError, AttributeError, KeyError) as e:
            print(f"summary.json の形が違います（{e}）", file=sys.stderr)
            return 2
        for w in merge_warnings(parts):
            print(f"WARN: {w}", file=sys.stderr)
        out = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="intervention-merge-"))
        sys.stdout.write(write_summary(out, merged))
        print(f"\nsummary: {out / 'summary.md'}")
        return 0

    if args.out and inside_git_worktree(Path(args.out)):
        print(f"--out が git の作業ツリーの中です: {args.out}（本文を含む events.jsonl がコミットされうる。"
              "リポジトリの外を指す）", file=sys.stderr)
        return 2

    root = Path(args.root)
    if not root.is_dir():
        print(f"transcript の dir がありません: {root}", file=sys.stderr)
        return 2
    files = sorted(
        p for p in root.glob("*/*.jsonl")
        if not args.project or args.project in p.parent.name
    )
    if not files:
        print(f"transcript が 1 件もありません: {root}（--project={args.project}）", file=sys.stderr)
        return 2

    sc = Scanner(args.since, args.until)
    for p in files:
        sc.scan(p)
    if not sc.sessions:
        print(f"期間に入るセッションがありません（since={args.since} until={args.until}）", file=sys.stderr)
        return 2
    if args.labels:
        try:
            sc.load_labels(Path(args.labels))
        except (OSError, ValueError) as e:
            print(f"分類の JSONL を読めません: {args.labels}（{e}）", file=sys.stderr)
            return 2
    summary = summarize(sc, load_marketplace_plugins(), args.names, args)

    out = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="intervention-measure-"))
    md = write_summary(out, summary)
    events_path = out / "events.jsonl"
    fd = os.open(events_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for e in sc.events:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    sys.stdout.write(md)
    print(f"\nsummary: {out / 'summary.md'}（共有してよい）\nevents:  {events_path}（本文を含む。持ち出さない）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
