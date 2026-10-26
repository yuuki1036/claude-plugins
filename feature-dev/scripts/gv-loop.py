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
                 deferred は回をまたいで残す（delta を主に見る再レビューは、前の回の deferred を出し直さない）。
                 前回の修正のうち、対象の行の周辺の外を変えた hunk を「範囲外の変更」として数える（止めはしない）。
                 fix / ask の回は、再レビューに渡す `since=<修正前の tree>` と `prior_findings=<path>`（全回の対象を
                 重複なく並べた JSON）も出す。どちらかを用意できない回は `since=unavailable`（GitHub issue #313）
  finish --reason manual   利用者・メインスレッドが止めた
  summary        Step 4 と Phase 7 が読む集計
  prior-findings [--with-loop]
                 Phase 6.9 の再レビューに渡す前回の対象を書く。stdin の findings（Step 4 で利用者が直すと決めた指摘。
                 FINDINGS_JSON の形。空でよい）に、`--with-loop` のときだけループの deferred / remaining を足す。
                 `prior_findings=<path>` / 対象が無ければ `none` / 書けなければ `unavailable`

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
import stat
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
# self-review へは `--prior-findings=<path>` の 1 語で、手順書の行に埋めて渡す。シェルが解釈する文字を通さない
SAFE_PATH_RE = re.compile(r"[A-Za-z0-9._/-]+")
# ループの状態を使わない回（`prior-findings` を `--with-loop` なしで呼ぶ）の名前。毎回上書きし、init でも消す
NO_STATE_RUN = "nostate"


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


def has_control(text: str) -> bool:
    # ASCII の制御文字だけを見ると、行区切りとして読まれる U+2028 / U+0085 が通る
    return not text.isprintable()


def target(f: dict) -> dict:
    path = f.get("file")
    # 観点は空白を潰す。改行入りの file は止める — 1 行 1 項目の出力（target 行・prior_findings）に
    # 偽の `since=` / `prior_findings=` 行を差し込める
    focus = "".join(str(f.get("focus") or "").split())
    try:
        line = int(f.get("line"))
    except (TypeError, ValueError):
        line = 0
    if not isinstance(path, str) or not path or line < 1:
        raise InputError(f"auto-fix 対象に file / line が無い: {f.get('title', '')}")
    if has_control(path):
        raise InputError(f"file に制御文字がある: {path!r}")
    title = " ".join(str(f.get("title", "")).split())
    return {"fingerprint": f"{path}:{line}:{focus}", "file": path, "line": line, "focus": focus,
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


def close_round(state: dict, tree: str | None) -> tuple[dict | None, dict[str, list[dict]] | None]:
    """修正中の回があれば、修正前からの変更で範囲外の hunk を数えて閉じる。閉じた回とその変更を返す."""
    rounds = state["iterations"]
    if not rounds or rounds[-1]["closed"]:
        return None, None
    r = rounds[-1]
    changes = hunks(r["pre_fix_tree"], tree) if r["pre_fix_tree"] and tree else None
    r["out_of_scope"] = None if changes is None else out_of_scope(r["targets"], changes)
    r["closed"] = True
    return r, changes


def moved(line: int, hs: list[dict]) -> int:
    """修正前の行番号を、修正後の行番号へ写す。書き換えた範囲の中の行は、新しい側の先頭に寄せる."""
    shift = 0
    for h in hs:
        start, end = h["old"]
        if h["deleted"] == 0:
            # 挿入だけの hunk の旧側は「start 行の後」を表す（span を参照）
            if line > start:
                shift += h["added"]
        elif line > end:
            shift += h["added"] - h["deleted"]
        elif line >= start:
            return h["new"][0]
    return line + shift


def focus_of(t: dict) -> str:
    # 状態に focus が無い（この版より前に作った）回は fingerprint の末尾から取る
    return t.get("focus") or t["fingerprint"].rsplit(":", 1)[-1]


def remap(old: list[dict], changes: dict[str, list[dict]] | None) -> list[dict]:
    """前の回の対象を、直前の修正で動いた行へ写す。修正がファイルごと消したものは落とす."""
    out = []
    for t in old:
        if changes and t["file"] in changes and not Path(t["file"]).exists():
            continue
        line = moved(t["line"], changes.get(t["file"], [])) if changes else t["line"]
        focus = focus_of(t)
        out.append({**t, "line": line, "focus": focus, "fingerprint": f"{t['file']}:{line}:{focus}"})
    return out


def same_finding(t: dict, u: dict) -> bool:
    """写した後の行で同じ指摘か。行が同じか、行が近くて要旨も同じなら同じとみなす.

    近いだけで同じとみなすと、同じ観点で近くに出た別の指摘で前の回の deferred を捨て、`success` で止まりうる。
    """
    if t["file"] != u["file"] or t["focus"] != u["focus"]:
        return False
    return t["line"] == u["line"] or (abs(t["line"] - u["line"]) <= DELTA_MARGIN and t["title"] == u["title"])


def carry_deferred(old: list[dict], targets: list[dict], changes: dict[str, list[dict]] | None) -> list[dict]:
    """前の回の deferred を、直前の修正で動いた行へ写してから、今回の対象に出直していないものだけ残す.

    fingerprint は行番号を含むので、修正が上の行を足し引きすると、出し直された同じ指摘が別の fingerprint になる。
    写さずに突き合わせると、古い行の分と新しい行の分が 2 件並ぶ（どちらも deferred で止まり方は変わらない）。
    """
    return [t for t in remap(old, changes) if not any(same_finding(t, u) for u in targets)]


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


def prior_dir() -> Path | None:
    """前回の対象を置く一時ディレクトリ。自分だけが読み書きできる実ディレクトリでなければ None.

    TMPDIR が無い環境は共有の /tmp に落ちる。他の利用者が先に作った dir や symlink に書くと、直していない
    指摘の要旨を読まれ、差し替えた JSON が reviewer のプロンプトに入る（code-review の review-paths.sh と同じ脅威）。
    """
    d = Path(os.environ.get("TMPDIR") or "/tmp") / f"feature-dev-{os.getuid()}"
    if not SAFE_PATH_RE.fullmatch(str(d)):
        warn(f"一時ディレクトリのパスに使えない文字がある: {d}")
        return None
    try:
        d.mkdir(mode=0o700, exist_ok=True)
        st = os.lstat(d)
    except OSError as e:
        warn(f"一時ディレクトリを作れない: {e}")
        return None
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        warn(f"一時ディレクトリが自分専用でない（symlink・持ち主・モード）: {d}")
        return None
    return d


def warn(msg: str) -> None:
    print(f"WARN: {msg}。再レビューは diff 全体で回す", file=sys.stderr)


def write_items(run_id: str, items: list[dict]) -> str | None:
    """self-review の `--prior-findings` の形（`[{file, line, focus, title}]`）で書く。書けなければ None."""
    d = prior_dir()
    if d is None:
        return None
    path = d / f"gv-prior-findings-{run_id}.json"
    tmp = path.with_suffix(".tmp")
    try:
        tmp.unlink(missing_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(items, ensure_ascii=False))
        os.replace(tmp, path)
    except OSError as e:
        warn(f"前回の対象を書けない: {e}")
        return None
    return str(path)


def drop_prior_findings(run_id: str) -> None:
    """その run の前回の対象のファイルを消す。自分が持ち主の実ディレクトリでなければ触らない。消せなくても続ける."""
    d = Path(os.environ.get("TMPDIR") or "/tmp") / f"feature-dev-{os.getuid()}"
    try:
        st = os.lstat(d)
    except OSError:
        return
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
        return
    try:
        (d / f"gv-prior-findings-{run_id}.json").unlink(missing_ok=True)  # mutation-ok: False でも FileNotFoundError は直下の except OSError が受ける
    except OSError:
        pass


def unique_items(targets: list[dict]) -> list[dict]:
    seen, items = set(), []
    for t in targets:
        if t["fingerprint"] in seen:
            continue
        seen.add(t["fingerprint"])
        items.append({"file": t["file"], "line": t["line"], "focus": focus_of(t), "title": t["title"]})
    return items


def write_prior_findings(state: dict) -> str | None:
    """全回の対象を重複なく並べて書く。直前の回の分だけにすると、後の修正が先の修正を戻したときに見落とす."""
    return write_items(state["run_id"], unique_items([t for r in state["iterations"] for t in r["targets"]]))


def cmd_init(args: argparse.Namespace) -> int:
    if args.max < 1:
        raise InputError("--max は 1 以上（0 の effort は Step 3 自体を飛ばす）")
    gd = enter_repo()
    tree = snapshot() if gd else None
    if tree is None:
        print("loop=unavailable")
        return 0
    # 前のループが残した前回の対象（6.9 の分）はここで消す。止めた時点では 6.9 がまだ使う。
    # dir は利用者ごとで、別の worktree のループと共有するので、この作業ツリーの前の run の分だけを消す
    old = load(gd)
    if isinstance(old, dict) and old.get("run_id"):
        drop_prior_findings(old["run_id"])
    drop_prior_findings(NO_STATE_RUN)
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
    closed, changes = close_round(state, tree)
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
    # 前の回の対象がまた出たら、delta の外でも残っている指摘として扱う（deferred に回すと regression を見逃す）。
    # 直前の回に限らない: 再レビューには全回の対象を渡すので、後の修正が先の修正を戻した回もここで止める。
    # 各回の対象は、その後の修正で動いた行へ毎回写して持つ（`seen`。無い状態は全回の対象から作る）
    seen = state.get("seen")
    if seen is None:
        seen = [t for r in state["iterations"] for t in r["targets"]]
    seen = remap(seen, changes)
    persisting = [t for t in targets if any(same_finding(t, u) for u in seen)]
    loop = loop + [t for t in persisting if t not in loop]
    deferred = [t for t in targets if t not in loop]
    # 前の回の deferred は、今回の対象に出直していなければ残す。delta を主に見る再レビューは delta の外の
    # 指摘を出し直さないので、上書きすると Step 4 から消え、`success` で止まりうる（GitHub issue #313）
    deferred = deferred + carry_deferred(state["deferred"], targets, changes)
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
        seen = seen + loop
    state["seen"] = seen
    save(gd, state)
    if action == "stop":
        drop_prior_findings(state["run_id"])

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
        prior = write_prior_findings(state) if tree else None
        if prior:
            print(f"since={tree}")
            print(f"prior_findings={prior}")
        else:
            print("since=unavailable")
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
    drop_prior_findings(state["run_id"])
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


def cmd_prior_findings(args: argparse.Namespace) -> int:
    """Phase 6.9 の再レビューに渡す前回の対象を書く（GitHub issue #313）.

    6.9 の差分の主な中身は、Step 4 で利用者が直すと決めた指摘への修正。前回の対象なしに delta だけを見ると、
    修正が対象の行に触れなかった回に、直っていない指摘を誰も見ない（triage-signals.sh の縮退と同じ理由）。
    """
    text = sys.stdin.read()
    chosen = [c for c in (chosen_item(f) for f in read_findings(text)) if c] if text.strip() else []
    gd = enter_repo()
    # 状態は作業ツリーに残り続け、init を呼ばない run（low effort など）では前の run のものになる。
    # ループの分は、今回の run で Step 3 が走ったと呼び出し元が言ったときだけ足す
    state = load(gd) if gd and args.with_loop else None
    loop = (state["deferred"] + state["remaining"]) if state else []
    # 古い順（後ろほど新しい）に並べる。code-review は上限を超えたら後ろを残す
    items = unique_items(loop + chosen)
    if not items:
        print("prior_findings=none")
        return 0
    path = write_items(state["run_id"] if state else NO_STATE_RUN, items)
    print(f"prior_findings={path or 'unavailable'}")
    return 0


def chosen_item(f: dict) -> dict | None:
    """利用者が直すと決めた指摘。auto-fix 対象と違い、行が無くても受ける。使えない項目は WARN を出して捨てる."""
    path = f.get("file")
    if not isinstance(path, str) or not path or has_control(path):
        print(f"WARN: 前回の対象に使えない項目を捨てた: {f.get('title', '')}", file=sys.stderr)
        return None
    try:
        line = int(f.get("line"))
    except (TypeError, ValueError):
        line = 0
    focus = "".join(str(f.get("focus") or "").split())
    title = " ".join(str(f.get("title", "")).split())
    return {"fingerprint": f"{path}:{line}:{focus}", "file": path, "line": line if line >= 1 else None,
            "focus": focus, "title": title}


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
    p = sub.add_parser("prior-findings", help="Phase 6.9 の再レビューに渡す前回の対象を書く（stdin: 直すと決めた指摘）")
    p.add_argument("--with-loop", action="store_true", help="今回の run で Step 3 が走ったときだけ付ける")
    p.set_defaults(func=cmd_prior_findings)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except InputError as e:
        print(f"error={e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
