#!/usr/bin/env python3
"""feature-dev Phase 6 の G-V ループの状態を持ち、続けるか止めるかを決める CLI（GitHub issue #310）.

以前はループの状態を Claude が手書きの JSON で持ち、Fix Mode の範囲（auto-fix 対象の file:line）も
文面の指示だけだった。実測（core 12 ファイル・effort xhigh）では各回で対象外の MAJOR / MINOR まで
直し（34 件・17 件）、その修正が次のレビューの材料になった。再レビューは diff 全体を見直すので、
修正と関係ない箇所の新しい指摘でもループが延びていた。

  init --max N   ループの起点の作業ツリーを記録する（初回の self-review の直後）
  review         self-review の findings（stdin。self-review の出力をそのまま渡してよい）を受け、次の一手を出す:
                   action=fix   auto-fix 対象を直して再レビューする
                   action=ask   2 回目以降で上限の回。続けるかを利用者に聞く
                   action=stop  reason=success / regression / budget / deferred
                 2 回目以降は、ループの起点からの差分（delta）の外にある対象をループに入れず deferred に回す。
                 前回の修正のうち、対象の行の周辺の外を変えた hunk を「範囲外の変更」として数える（止めはしない）
  finish --reason manual   利用者・メインスレッドが止めた
  summary        Step 4 と Phase 7 が読む集計

状態は作業ツリーごとの git dir に置く（worktree ごとに分かれる）。git でない・作業ツリーを記録できない
ときは `loop=unavailable` を出して exit 0。
exit code: 0 成功 / 2 入力が不正・状態の前提が違う（init 前の review、止めた後の review など）
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

STATE_NAME = "feature-dev-loop-state.json"
SNAPSHOT = Path(__file__).resolve().parent / "review-snapshot.sh"
SCHEMA = 1
CRITICAL_MIN_CONFIDENCE = 90
# 対象がループの起点から変えた行の何行以内にあれば「ループの修正が作った指摘」と見るか。
# 外と判定した対象は deferred として Step 4 に残るので、狭すぎても指摘は失われない（ループが延びないだけ）
DELTA_MARGIN = 5
# 修正の hunk が auto-fix 対象の行の何行以内にあれば対象の修正と見るか。数えて Step 4 に並べるだけで止めない
SCOPE_MARGIN = 10
# バイナリ・モードだけの変更は hunk が出ないので、ファイル全体を変えたものとして扱う
WHOLE_FILE = (1, 10**9)
HUNK_RE = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
JSON_START = "<!-- FINDINGS_JSON_START -->"
JSON_END = "<!-- FINDINGS_JSON_END -->"
FENCE_RE = re.compile(r"```[A-Za-z]*\n(.*?)\n?```", re.S)
TREE_RE = re.compile(r"snapshot=([0-9a-f]{40,64})")


class InputError(Exception):
    """入力・状態の前提が違う（exit 2）."""


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def git(*args: str) -> subprocess.CompletedProcess:
    return run(["git", *args])


def enter_repo() -> Path | None:
    """作業ツリーのルートへ移り、git dir を返す。git でなければ None."""
    res = git("rev-parse", "--show-toplevel", "--absolute-git-dir")
    if res.returncode != 0:
        return None
    top, gd = res.stdout.splitlines()
    os.chdir(top)
    return Path(gd)


def snapshot() -> str | None:
    m = TREE_RE.fullmatch(run(["bash", str(SNAPSHOT), "tree"]).stdout.strip())
    return m.group(1) if m else None


def span(start: str, count: str | None) -> tuple[int, int]:
    """hunk の片側の行範囲。0 行（片側にしか無い挿入・削除）は前後の行の間として扱う."""
    s = int(start)
    n = 1 if count is None else int(count)
    return (s, s + 1) if n == 0 else (s, s + n - 1)


def hunks(old: str, new: str) -> dict[str, list[dict]] | None:
    """old → new の変更を、ファイルごとの hunk（旧側・新側の行範囲と増減）で返す。比べられなければ None.

    パスはパッチの見出しから読まず `--name-only -z` で取る（引用・エスケープされたパスを解かずに済む）。
    """
    names = git("--literal-pathspecs", "diff", "--no-renames", "--name-only", "-z", old, new)
    if names.returncode != 0:
        return None
    out: dict[str, list[dict]] = {}
    for path in filter(None, names.stdout.split("\0")):
        res = git("--literal-pathspecs", "diff", "--no-color", "--no-ext-diff", "--no-textconv",
                  "--no-renames", "-U0", old, new, "--", path)
        if res.returncode != 0:
            return None  # mutation-ok: 同じ 2 つの tree で --name-only が通った後にこの diff だけが失敗する状態は作れない
        found = []
        for line in res.stdout.splitlines():
            m = HUNK_RE.match(line)
            if m:
                a, b, c, d = m.groups()
                found.append({"old": span(a, b), "new": span(c, d),
                              "added": 1 if d is None else int(d), "deleted": 1 if b is None else int(b)})
        out[path] = found or [{"old": WHOLE_FILE, "new": WHOLE_FILE, "added": 0, "deleted": 0}]
    return out


def near(rng: list[int] | tuple[int, int], line: int, margin: int) -> bool:
    return rng[0] <= line + margin and rng[1] >= line - margin


def read_findings(text: str) -> list[dict]:
    i = text.find(JSON_START)
    if i != -1:
        j = text.find(JSON_END, i)
        if j == -1:
            raise InputError(f"{JSON_START} の後に {JSON_END} が無い")
        text = text[i + len(JSON_START):j]
    text = text.strip()
    m = FENCE_RE.fullmatch(text)
    if m:
        text = m.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise InputError(f"findings の JSON を読めない: {e}") from None
    findings = data.get("findings") if isinstance(data, dict) else None
    if not isinstance(findings, list):
        raise InputError("findings の配列が無い（self-review の FINDINGS_JSON の形で渡す）")
    return [f for f in findings if isinstance(f, dict)]


def confidence(f: dict) -> int:
    try:
        return int(f.get("confidence"))
    except (TypeError, ValueError):
        return 0


def is_target(f: dict) -> bool:
    severity = str(f.get("severity", "")).upper()
    if severity == "BLOCKER":
        return True
    return severity == "CRITICAL" and confidence(f) >= CRITICAL_MIN_CONFIDENCE


def target(f: dict) -> dict:
    path, focus = f.get("file"), str(f.get("focus", ""))
    try:
        line = int(f.get("line"))
    except (TypeError, ValueError):
        line = 0
    if not isinstance(path, str) or not path or line < 1:
        raise InputError(f"auto-fix 対象に file / line が無い: {f.get('title', '')}")
    title = " ".join(str(f.get("title", "")).split())
    return {"fingerprint": f"{path}:{line}:{focus}", "file": path, "line": line,
            "severity": str(f.get("severity")).upper(), "confidence": confidence(f), "title": title}


def in_delta(t: dict, delta: dict[str, list[dict]]) -> bool:
    return any(near(h["new"], t["line"], DELTA_MARGIN) for h in delta.get(t["file"], []))


def out_of_scope(targets: list[dict], changes: dict[str, list[dict]]) -> list[dict]:
    """修正前 → 修正後の hunk のうち、どの対象の行の周辺にも掛からないもの（行番号は修正前の側で比べる）."""
    found = []
    for path, hs in changes.items():
        lines = [t["line"] for t in targets if t["file"] == path]
        for h in hs:
            if not any(near(h["old"], line, SCOPE_MARGIN) for line in lines):
                found.append({"file": path, "old": list(h["old"]), "added": h["added"], "deleted": h["deleted"]})
    return found


def state_path(gd: Path) -> Path:
    return gd / STATE_NAME


def load(gd: Path) -> dict | None:
    try:
        return json.loads(state_path(gd).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save(gd: Path, state: dict) -> None:
    tmp = state_path(gd).with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, state_path(gd))


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def close_round(state: dict, tree: str | None) -> dict | None:
    """修正中の回があれば、修正前からの変更で範囲外の hunk を数えて閉じる。閉じた回を返す."""
    rounds = state["iterations"]
    if not rounds or rounds[-1]["closed"]:
        return None
    r = rounds[-1]
    changes = hunks(r["pre_fix_tree"], tree) if r["pre_fix_tree"] and tree else None
    r["out_of_scope"] = None if changes is None else out_of_scope(r["targets"], changes)
    r["closed"] = True
    return r


def stop(state: dict, reason: str, remaining: list[dict]) -> None:
    state["terminated"] = {"at": now_iso(), "reason": reason}
    state["remaining"] = remaining


def closed_rounds(state: dict) -> list[dict]:
    return [r for r in state["iterations"] if r["closed"]]


def target_row(kind: str, t: dict) -> str:
    return f"{kind}\t{t['fingerprint']}\t{t['severity']}\t{t['confidence']}\t{t['title']}"


def scope_rows(r: dict) -> list[str]:
    return [f"out_of_scope\t{r['iteration']}\t{h['file']}:{h['old'][0]}-{h['old'][1]}\t+{h['added']} -{h['deleted']}"
            for h in r["out_of_scope"] or []]


def scope_count(r: dict) -> str:
    if r["out_of_scope"] is None:
        return "unavailable"
    return str(len(r["out_of_scope"]))


def cmd_init(args: argparse.Namespace) -> int:
    if args.max < 1:
        raise InputError("--max は 1 以上（0 の effort は Step 3 自体を飛ばす）")
    gd = enter_repo()
    tree = snapshot() if gd else None
    if tree is None:
        print("loop=unavailable")
        return 0
    save(gd, {"schema": SCHEMA, "run_id": str(uuid.uuid4()), "started_at": now_iso(),
              "max_iterations": args.max, "current_iteration": 0, "start_tree": tree,
              "iterations": [], "deferred": [], "remaining": [], "terminated": None})
    print("loop=initialized")
    print(f"max_iterations={args.max}")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    gd = enter_repo()
    if gd is None:
        print("loop=unavailable")
        return 0
    state = load(gd)
    if state is None:
        raise InputError("ループの状態が無い（先に init）")
    if state["terminated"]:
        raise InputError(f"ループは止まっている（reason={state['terminated']['reason']}）。新しいループは init から")
    findings = read_findings(sys.stdin.read())
    tree = snapshot()
    closed = close_round(state, tree)
    targets = [target(f) for f in findings if is_target(f)]
    n, limit = state["current_iteration"], state["max_iterations"]

    loop, deferred, delta_state = targets, [], "n/a"
    if n >= 1:
        delta = hunks(state["start_tree"], tree) if tree else None
        if delta is None:
            delta_state = "unavailable"
        else:
            delta_state = "ok"
            loop = [t for t in targets if in_delta(t, delta)]
    previous = {t["fingerprint"] for t in state["iterations"][-1]["targets"]} if state["iterations"] else set()
    # 前回の対象がまた出たら、delta の外でも残っている指摘として扱う（deferred に回すと regression を見逃す）
    persisting = [t for t in targets if t["fingerprint"] in previous]
    loop = loop + [t for t in persisting if t not in loop]
    deferred = [t for t in targets if t not in loop]
    state["deferred"] = deferred

    if persisting:
        action, reason = "stop", "regression"
        stop(state, reason, loop)
    elif not loop:
        action, reason = "stop", "deferred" if deferred else "success"
        stop(state, reason, [])
    elif n >= limit:
        action, reason = "stop", "budget"
        stop(state, reason, loop)
    else:
        action, reason = ("ask" if n >= 1 and n + 1 == limit else "fix"), None
        state["iterations"].append({"iteration": n + 1, "targets": loop, "pre_fix_tree": tree,
                                    "out_of_scope": None, "closed": False})
        state["current_iteration"] = n + 1
    save(gd, state)

    print(f"action={action}")
    if reason:
        print(f"reason={reason}")
        print(f"iteration={len(closed_rounds(state))}/{limit}")
    else:
        print(f"iteration={n + 1}/{limit}")
    print(f"delta={delta_state}")
    if closed:
        print(f"out_of_scope={scope_count(closed)}")
    if action != "stop":
        notice = f"🔄 Iteration {n + 1}/{limit}: auto-fix {len(loop)} 件"
        if closed:
            notice += f"（前回の範囲外の変更 {scope_count(closed)} か所・delta の外へ回した指摘 {len(deferred)} 件）"
        print(f"notice={notice}")
    for t in loop:
        print(target_row("target", t))
    for t in deferred:
        print(target_row("deferred", t))
    if closed:
        for row in scope_rows(closed):
            print(row)
    return 0


def cmd_finish(args: argparse.Namespace) -> int:
    gd = enter_repo()
    if gd is None:
        print("loop=unavailable")
        return 0
    state = load(gd)
    if state is None:
        raise InputError("ループの状態が無い")
    if state["terminated"]:
        raise InputError(f"ループは止まっている（reason={state['terminated']['reason']}）")
    remaining = state["remaining"]
    rounds = state["iterations"]
    if rounds and not rounds[-1]["closed"]:
        pending = rounds[-1]
        remaining = pending["targets"]
        tree = snapshot()
        if tree is not None and tree == pending["pre_fix_tree"]:
            # 直す前に止めた回は数えない
            rounds.pop()
            state["current_iteration"] -= 1
        else:
            close_round(state, tree)
    stop(state, args.reason, remaining)
    save(gd, state)
    print("action=stop")
    print(f"reason={args.reason}")
    print(f"iteration={len(closed_rounds(state))}/{state['max_iterations']}")
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    gd = enter_repo()
    if gd is None:
        print("loop=unavailable")
        return 0
    state = load(gd)
    if state is None:
        print("loop=missing")
        return 0
    rounds = closed_rounds(state)
    scopes = [r["out_of_scope"] for r in rounds]
    print(f"loop={'terminated' if state['terminated'] else 'running'}")
    if state["terminated"]:
        print(f"reason={state['terminated']['reason']}")
    print(f"iterations={len(rounds)}/{state['max_iterations']}")
    print(f"auto_fix_targets={sum(len(r['targets']) for r in rounds)}")
    print("out_of_scope=" + ("unavailable" if None in scopes else str(sum(len(s) for s in scopes))))
    print(f"remaining={len(state['remaining'])}")
    print(f"deferred={len(state['deferred'])}")
    for r in rounds:
        print(f"iteration\t{r['iteration']}\t{len(r['targets'])}\t{scope_count(r)}")
    for t in state["remaining"]:
        print(target_row("remaining", t))
    for t in state["deferred"]:
        print(target_row("deferred", t))
    for r in rounds:
        for row in scope_rows(r):
            print(row)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="feature-dev Phase 6 の G-V ループ")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="ループの起点を記録する")
    p.add_argument("--max", type=int, required=True)
    p.set_defaults(func=cmd_init)
    sub.add_parser("review", help="self-review の findings（stdin）から次の一手を出す").set_defaults(func=cmd_review)
    p = sub.add_parser("finish", help="ループを止める")
    p.add_argument("--reason", choices=["manual"], required=True)
    p.set_defaults(func=cmd_finish)
    sub.add_parser("summary", help="Step 4 と Phase 7 の集計").set_defaults(func=cmd_summary)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except InputError as e:
        print(f"error={e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
