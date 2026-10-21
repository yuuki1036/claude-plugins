#!/usr/bin/env python3
"""project-hub の状態ファイルを読み書きする CLI.

hub / report の skill と注入 hook がここを呼ぶ。ListAgents・SendMessage・トラッカーは
Claude のツールでスクリプトからは呼べないので、Claude が取った結果を JSON で受け取り、
照合・記録・表の生成だけを持つ（GitHub issue #308）。

root: ${PROJECT_HUB_DIR:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/project-hub}

サブコマンド（`hub.py <cmd> --help`）:
  init / takeover / refresh-hub / close / projects        PJ と hub の登録
  fact / facts / record                                    facts と brief・relay の記録
  ingest / reports / presence / snapshot / render / worktrees   hub status・brief の材料
  resolve                                                  宛先の照合（送る直前に毎回）
  report                                                   作業側の report（自己検査 → 登録 + inbox → 通知先）
  inject                                                   SessionStart / PostCompact hook 用

作業側・ListAgents・トラッカー由来の文面（report の本文・fact の主張・record の全文と宛先・
取得失敗の理由・ListAgents の抜き出し）は argv ではなく stdin の JSON で受ける。argv に載せると
シェルが展開し、平文の heredoc は本文中の区切り行で途切れる。宛先は名前ではなく ref で選ぶ。

session_id は --session-id か CLAUDE_CODE_SESSION_ID から取り、両方あって違えば止める。
hub 側で書くサブコマンドと hub → 作業側の宛先の照合は、今のセッションが hub.json の hub で
なければ止める（takeover の後に古い hub が書き続ける・送り続けるのを防ぐ）。

exit code: 0 成功 / 1 決まらない（宛先・PJ が 1 件に決まらない）/
           2 入力が不正・ListAgents の抜き出しが自己検査に合わない /
           3 状態の前提が違う（init 済み・未 init・別セッションの hub・active でない PJ への report）/
           4 想定外の失敗（書き込みの失敗など。原因は stderr）
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

JOURNAL_KINDS = ("relay", "brief", "report", "fact", "takeover", "close")
REPORT_STATES = ("hello", "in_progress", "blocked", "ready_for_review", "done")
SEND_RESULTS = ("accepted", "failed", "pasted", "unresolved")
# report の形の版。hub と作業側で入っている project-hub の版がずれうる（marketplace 版と inline 版）
REPORT_SCHEMA = 1
# どれも fullmatch で使う（re.match + `$` は末尾の改行 1 つを通す）
PROJECT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
SESSION_ID_RE = re.compile(r"[A-Za-z0-9_-]+")
SOURCE_NAME_RE = re.compile(r"[a-z][a-z0-9_-]*")
REF_RE = re.compile(r"[0-9A-Za-z]+")
PR_RE = re.compile(r"#?\d+")
FACT_ID_RE = re.compile(r"F(\d+)")
# 名前を付けていないセッションの既定名（`claude-plugins-96`）。判定は is_default_name
DEFAULT_NAME_RE = re.compile(r"\S+-\d+")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
STATE_HEADER_RE = re.compile(r"^<!-- project-hub-state generated_at=(\S+) journal_lines=(\d+) -->$")
NAME_MAX = 200
TITLE_MAX = 60
TABLE_MAX = 30
RECENT_JOURNAL = 10


class HubError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def root() -> Path:
    env = os.environ.get("PROJECT_HUB_DIR")
    if env:
        return Path(env)
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base) / "project-hub"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp() -> str:
    # 登録の updated と不在の absent_since は前後を文字列で比べるので、同じ秒に収まらない精度で揃える
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def emit(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise HubError(2, f"読めない: {path}（{e}）")


def read_obj(path: Path) -> dict:
    """JSON のオブジェクトを読む（無ければ {}）。オブジェクト以外は壊れたファイルとして exit 2."""
    data = read_json(path)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise HubError(2, f"JSON のオブジェクトではない: {path}")
    return data


def write_json(path: Path, data) -> None:
    # 一時名で書いてから rename する。読み手（hook・ingest・別セッションの report）が書きかけを掴まない。
    # 一時名は `.json` で終わらせない（ingest の `*.json` に当たらないように）
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def journal_lines(path: Path) -> list[str]:
    # 1 行 1 JSON の区切りは \n だけ。json.dumps(ensure_ascii=False) は U+2028 等をエスケープせずに書くので、
    # splitlines() や改行の変換で読むと行が割れて JSON として読めなくなる
    try:
        with path.open(encoding="utf-8", newline="") as f:
            text = f.read()
    except FileNotFoundError:
        return []
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def parse_jsonl(lines: list[str]) -> list[dict]:
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def read_jsonl(path: Path) -> list[dict]:
    return parse_jsonl(journal_lines(path))


def append_jsonl(path: Path, row: dict) -> None:
    line = json.dumps(row, ensure_ascii=False) + "\n"
    # 前の追記が途中で落ちて末尾に改行が無いと、この行がその断片とつながって読めなくなる
    if path.exists() and path.stat().st_size:
        with path.open("rb") as f:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                line = "\n" + line
    with path.open("a", encoding="utf-8", newline="") as f:
        f.write(line)


def project_dir(name: str, must_exist: bool = True) -> Path:
    if not PROJECT_RE.fullmatch(name or ""):
        raise HubError(2, f"PJ 名に使えない文字がある: {name!r}")
    path = root() / name
    if must_exist and not (path / "config.json").is_file():
        raise HubError(3, f"PJ が init されていない: {name}（hub init で作る）")
    return path


def current_session(arg: str | None) -> str:
    env = os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
    if arg and env and arg != env:
        raise HubError(2, f"--session-id と CLAUDE_CODE_SESSION_ID が違う（{arg} / {env}）")
    sid = arg or env
    if not SESSION_ID_RE.fullmatch(sid):
        # 展開されなかった `${CLAUDE_SESSION_ID}` の文字列もここで弾く
        raise HubError(2, "session_id が取れない（--session-id か CLAUDE_CODE_SESSION_ID）")
    return sid


def require_hub(pdir: Path, arg: str | None) -> dict:
    sid = current_session(arg)
    hub = read_obj(pdir / "hub.json")
    if not hub:
        raise HubError(3, "hub.json が無い。このセッションを hub にするなら takeover"
                          f"（state.md: {pdir / 'state.md'}）")
    if hub.get("session_id") != sid:
        raise HubError(3, f"この hub は別のセッション（{hub.get('name')}）で登録されている。"
                          f"このセッションに引き継ぐなら takeover（state.md: {pdir / 'state.md'}）")
    return hub


def load_config(pdir: Path) -> dict:
    config = read_json(pdir / "config.json")
    if not isinstance(config, dict):
        raise HubError(2, f"config.json がオブジェクトではない: {pdir}")
    return config


def is_active(config: dict) -> bool:
    return config.get("status") == "active"


def tracker_kind(config: dict) -> str | None:
    tracker = config.get("tracker")
    return tracker.get("kind") if isinstance(tracker, dict) else None


def journal_append(pdir: Path, kind: str, subject, body, source=None) -> None:
    if kind not in JOURNAL_KINDS:
        raise HubError(2, f"journal の kind が不正: {kind}")
    append_jsonl(pdir / "journal.jsonl",
                 {"ts": now(), "kind": kind, "subject": subject, "body": body, "source": source})


def run_git(path, *args) -> subprocess.CompletedProcess | None:
    # bytes で受けて自分で復号する。text=True は改行を変換し（-z のパスの \r が化ける）、
    # UTF-8 でないパスで UnicodeDecodeError を投げる
    try:
        return subprocess.run(["git", "-C", str(path), *args], capture_output=True)
    except OSError:
        return None


def git(path, *args) -> str | None:
    """成功したときの stdout。末尾の改行だけを落とす（先頭の空白は porcelain の列なので残す）."""
    proc = run_git(path, *args)
    if proc is None or proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace").rstrip("\n")


def git_common_dir(path) -> Path | None:
    # `--path-format=absolute`（git 2.31 以降）は使わない。古い git は未知のフラグをそのまま出力して
    # exit 0 し、偽のパスになる。相対で返る出力は -C の dir を起点に解決する
    out = git(path, "rev-parse", "--git-common-dir")
    if not out or "\n" in out:
        return None
    common = Path(out)
    if not common.is_absolute():
        common = Path(path) / common
    return common.resolve()


def read_body(arg: str | None) -> str:
    if arg is None or arg == "-":
        return sys.stdin.read()
    try:
        return Path(arg).read_text(encoding="utf-8")
    except (OSError, ValueError) as e:
        raise HubError(2, f"読めない: {arg}（{e}）")


def load_json_input(arg: str | None, what: str):
    try:
        return json.loads(read_body(arg))
    except ValueError as e:
        raise HubError(2, f"{what} が JSON として読めない: {e}")


def pending_count(pdir: Path) -> int:
    return sum(1 for p in (pdir / "inbox").glob("*.json") if p.is_file())


def load_registrations(pdir: Path) -> tuple[list[dict], list[str]]:
    """作業側の登録（sessions/*.json）。読めないファイルは飛ばして名前を返す（1 つで全体を止めない）."""
    regs, unreadable = [], []
    for path in sorted((pdir / "sessions").glob("*.json")):
        try:
            reg = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            unreadable.append(path.name)
            continue
        if isinstance(reg, dict) and isinstance(reg.get("session_id"), str):
            regs.append(reg)
        else:
            unreadable.append(path.name)
    return regs, unreadable


# ---------------------------------------------------------------- report の形


def name_problem(name) -> str | None:
    if not isinstance(name, str) or not name.strip():
        return "name が無い"
    if len(name) > NAME_MAX or CONTROL_RE.search(name) or name.splitlines() != [name]:
        return f"name に改行・制御文字がある、または {NAME_MAX} 字を超える"
    return None


def validate_report(data, project: str | None = None, kind: str | None = None) -> list[str]:
    if not isinstance(data, dict):
        return ["JSON のオブジェクトではない"]
    if data.get("schema") != REPORT_SCHEMA:
        return [f"schema が {REPORT_SCHEMA} ではない（hub と作業側で project-hub の版が違う）"]
    errs = []
    for key in ("session_id", "project", "issue"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            errs.append(f"{key} が無い")
    problem = name_problem(data.get("name"))
    if problem:
        errs.append(problem)
    if isinstance(data.get("session_id"), str) and not SESSION_ID_RE.fullmatch(data["session_id"]):
        errs.append("session_id に使えない文字がある")
    if project is not None and data.get("project") != project:
        errs.append(f"project が {project} ではない")
    # issue と pr は state.md の表に載って hub に注入されるので、自由文を入れられない形に限る
    if isinstance(data.get("issue"), str) and data["issue"].strip() and kind is not None \
            and issue_token(kind, data["issue"]) is None:
        errs.append(f"issue が tracker（{kind}）の Issue ID の形ではない")
    if data.get("state") not in REPORT_STATES:
        errs.append(f"state が {'|'.join(REPORT_STATES)} のどれでもない")
    pr = data.get("pr")
    if pr is not None and not (isinstance(pr, int) and not isinstance(pr, bool) and pr > 0) \
            and not (isinstance(pr, str) and PR_RE.fullmatch(pr)):
        errs.append("pr が PR 番号（数値か #<番号>）か null ではない")
    for key in ("needs_lead", "follow_ups"):
        value = data.get(key, [])
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            errs.append(f"{key} が文字列の配列ではない")
    claims = data.get("claims", [])
    if not isinstance(claims, list):
        errs.append("claims が配列ではない")
    else:
        for i, claim in enumerate(claims):
            if not isinstance(claim, dict) or not isinstance(claim.get("text"), str) \
                    or not claim["text"].strip():
                errs.append(f"claims[{i}] に text が無い")
            elif not isinstance(claim.get("source"), str) or not claim["source"].strip():
                errs.append(f"claims[{i}] に source が無い（path:line 等の出典は必須）")
    return errs


# ---------------------------------------------------------------- ListAgents の抜き出し


def check_agents(agents, peer_count) -> list[str]:
    """Claude が ListAgents から抜き出した JSON の自己検査（書式に契約が無いので、ずれたら止める）."""
    if not isinstance(agents, list):
        return ["配列ではない"]
    if not isinstance(peer_count, int) or isinstance(peer_count, bool):
        return ["見出しの件数が整数ではない"]
    problems = []
    if len(agents) != peer_count:
        problems.append(f"見出しの件数 {peer_count} と抜き出した行数 {len(agents)} が違う")
    for i, agent in enumerate(agents):
        if not isinstance(agent, dict):
            problems.append(f"[{i}] がオブジェクトではない")
            continue
        name, ref, state = agent.get("name"), agent.get("ref"), agent.get("state")
        if not isinstance(name, str) or not name.strip():
            problems.append(f"[{i}] に name が無い")
        if not isinstance(ref, str) or not REF_RE.fullmatch(ref):
            problems.append(f"[{i}] の ref が英数字ではない")
        if not isinstance(state, str) or not state.strip():
            problems.append(f"[{i}] に state が無い")
    return problems


def load_agents(arg: str, peer_count: int) -> list[dict]:
    agents = load_json_input(arg, "agents")
    problems = check_agents(agents, peer_count)
    if problems:
        raise HubError(2, "ListAgents の抜き出しが自己検査に合わない: " + "; ".join(problems))
    return agents


def issue_token(kind: str | None, issue: str) -> re.Pattern | None:
    """Issue ID がセッション名の中にトークンとして現れるかを見る正規表現（`ABC-1` は `ABC-12` に当たらない）."""
    issue = (issue or "").strip()
    if kind == "github":
        m = re.fullmatch(r"#?(\d+)", issue)
        if not m:
            return None
        # `\w` は日本語にも当たるので ASCII で書く（「対応#308」の # の前は境界として扱う）
        return re.compile(rf"(?<![A-Za-z0-9_#])#{m.group(1)}(?!\d)")
    m = re.fullmatch(r"([A-Za-z][A-Za-z0-9]*)-(\d+)", issue)
    if not m:
        return None
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(m.group(1))}-{m.group(2)}(?!\d)")


def is_default_name(name: str, token: re.Pattern | None) -> bool:
    """名前を付けていないセッションの既定名（`<dir>-<数字>`）か.

    名前が Issue ID で終わる（`ABC-12` / `fix-ABC-12`）なら、末尾の数字は Issue ID の一部で通し番号ではない。
    `ABC-12-3`（dir 名が Issue ID の worktree の既定名）は Issue ID の後ろに番号が付くので既定名
    """
    if not DEFAULT_NAME_RE.fullmatch(name):
        return False
    if token is None:
        return True
    return not any(m.end() == len(name) for m in token.finditer(name))


def default_name_warning(name: str) -> str | None:
    if is_default_name(name, None):
        return ("既定名（<dir>-<数字>）のままになっている。既定名は宛先の照合に使わないので、"
                "会話の題を付けてから登録し直す")
    return None


def absent_map(pdir: Path) -> dict:
    return read_obj(pdir / "presence.json")


def absent_since(reg: dict, absent: dict) -> str | None:
    """ListAgents に名前が無かった最初の時刻。その後に report が来ていれば不在ではない."""
    entry = absent.get(reg.get("session_id"))
    since = entry.get("absent_since") if isinstance(entry, dict) else None
    if since and since >= str(reg.get("updated") or ""):
        return since
    return None


# ---------------------------------------------------------------- PJ と hub の登録


def default_base(repo: Path) -> str:
    # hub は fetch / pull しないローカルの既定ブランチより、作業側が切る origin 側を base にする。
    # origin 側が無ければローカルに黙って落とさず、明示を求める
    ref = git(repo, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if ref:
        return ref
    for name in ("origin/main", "origin/master"):
        if git(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/{name}") is not None:
            return name
    raise HubError(2, f"base を決められない（origin/HEAD も origin/main も無い）: {repo}。"
                      "--repo <path>=<base> で指定する")


def gitignored(path: Path) -> bool | None:
    """path が置かれた git リポジトリで ignore されているか（git の外なら None）."""
    proc = run_git(path.parent, "check-ignore", "-q", str(path))
    if proc is None or proc.returncode not in (0, 1):
        return None
    return proc.returncode == 0


def cmd_init(args) -> int:
    pdir = project_dir(args.project, must_exist=False)
    if (pdir / "config.json").exists():
        raise HubError(3, f"PJ {args.project} は init 済み。このセッションに引き継ぐなら takeover")
    sid = current_session(args.session_id)
    problem = name_problem(args.name)
    if problem:
        raise HubError(2, problem)
    tracker = {"kind": args.tracker}
    if args.tracker == "github":
        if not args.tracker_repo:
            raise HubError(2, "tracker github には --tracker-repo <owner/name> が要る")
        tracker["repo"] = args.tracker_repo
    else:
        if not (args.tracker_team or args.tracker_project):
            raise HubError(2, "tracker linear には --tracker-team か --tracker-project が要る")
        if args.tracker_team:
            tracker["team"] = args.tracker_team
        if args.tracker_project:
            tracker["project"] = args.tracker_project
    if args.milestone:
        tracker["milestone"] = args.milestone
    repos = []
    for spec in args.repo or []:
        path, sep, base = spec.rpartition("=")
        if not sep:
            path, base = spec, ""
        resolved = Path(path).expanduser().resolve()
        if git_common_dir(resolved) is None:
            raise HubError(2, f"git リポジトリではない: {path}")
        base = base or default_base(resolved)
        # `-` で始まる値は git のオプションとして読まれる
        if base.startswith("-") or git(resolved, "rev-parse", "--verify", "--quiet",
                                       f"{base}^{{commit}}") is None:
            raise HubError(2, f"base が {path} に無い: {base}（origin/<既定ブランチ> などを指定する）")
        repos.append({"path": str(resolved), "base": base})
    if not repos:
        raise HubError(2, "--repo <path>[=<base>] を 1 つ以上指定する")

    base_dir = root()
    base_dir.mkdir(parents=True, exist_ok=True)
    ignore = base_dir / ".gitignore"
    if not ignore.exists():
        # ~/.claude は複数マシンで git 同期していることがあり、ここは同期の対象から外す（マシンごとのデータ）
        ignore.write_text("*\n", encoding="utf-8")
    for sub in ("inbox/done", "inbox/invalid", "sessions"):
        (pdir / sub).mkdir(parents=True, exist_ok=True)
    for name in ("journal.jsonl", "facts.jsonl"):
        (pdir / name).touch()
    write_json(pdir / "config.json", {
        "project": args.project, "status": "active", "tracker": tracker, "repos": repos,
        "approval": {"prefix": args.approval_prefix, "suffix": args.approval_suffix},
    })
    write_json(pdir / "hub.json", {"session_id": sid, "name": args.name, "updated": now()})
    out = {"project": args.project, "dir": str(pdir), "hub": args.name, "repos": repos,
           "gitignored": gitignored(pdir / "config.json")}
    warning = default_name_warning(args.name)
    if warning:
        out["warning"] = warning
    emit(out)
    return 0


def cmd_takeover(args) -> int:
    pdir = project_dir(args.project)
    sid = current_session(args.session_id)
    problem = name_problem(args.name)
    if problem:
        raise HubError(2, problem)
    old = read_obj(pdir / "hub.json")
    write_json(pdir / "hub.json", {"session_id": sid, "name": args.name, "updated": now()})
    journal_append(pdir, "takeover", sid,
                   {"from_session_id": old.get("session_id"), "from_name": old.get("name"),
                    "to_name": args.name})
    out = {"project": args.project, "hub": args.name, "previous": old.get("name")}
    warning = default_name_warning(args.name)
    if warning:
        out["warning"] = warning
    emit(out)
    return 0


def cmd_refresh_hub(args) -> int:
    """hub status の最初に呼ぶ。今のセッションが hub か確かめ、名前が変わっていれば hub.json を直す."""
    pdir = project_dir(args.project)
    hub = require_hub(pdir, args.session_id)
    problem = name_problem(args.name)
    if problem:
        raise HubError(2, problem)
    if hub.get("name") != args.name:
        # 読んでから書くまでの間に takeover が入っていたら、その hub.json を上書きしない
        hub = require_hub(pdir, args.session_id)
        hub.update({"name": args.name, "updated": now()})
        write_json(pdir / "hub.json", hub)
    config = load_config(pdir)
    out = {"project": args.project, "hub": args.name, "dir": str(pdir), "status": config.get("status"),
           "tracker": config.get("tracker"), "repos": config.get("repos"),
           "approval": config.get("approval")}
    warning = default_name_warning(args.name)
    if warning:
        out["warning"] = warning
    emit(out)
    return 0


def cmd_close(args) -> int:
    pdir = project_dir(args.project)
    require_hub(pdir, args.session_id)
    config = load_config(pdir)
    config["status"] = "closed"
    write_json(pdir / "config.json", config)
    journal_append(pdir, "close", args.project, "")
    emit({"project": args.project, "status": "closed"})
    return 0


def cmd_projects(args) -> int:
    out = []
    for cfg_path in sorted(root().glob("*/config.json")):
        pdir = cfg_path.parent
        try:
            config = json.loads(cfg_path.read_text(encoding="utf-8"))
            hub = json.loads((pdir / "hub.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out.append({"project": pdir.name, "status": "unreadable"})
            continue
        if not isinstance(config, dict) or not isinstance(hub, dict):
            out.append({"project": pdir.name, "status": "unreadable"})
            continue
        out.append({"project": pdir.name, "status": config.get("status"),
                    "hub": hub.get("name"), "hub_session_id": hub.get("session_id"),
                    "pending": pending_count(pdir), "dir": str(pdir)})
    emit(out)
    return 0


# ---------------------------------------------------------------- facts と送信の記録


def current_facts(facts: list[dict]) -> list[dict]:
    superseded = {f.get("supersedes") for f in facts if f.get("supersedes")}
    return [f for f in facts if f.get("id") not in superseded]


def next_fact_id(path: Path, facts: list[dict]) -> str:
    # 読めない行があっても既存の id と重ならないよう、行数と最大の番号の大きい方から振る
    numbers = [int(m.group(1)) for f in facts
               if isinstance(f.get("id"), str) and (m := FACT_ID_RE.fullmatch(f["id"]))]
    return f"F{max([len(journal_lines(path)), *numbers]) + 1}"


def config_repo(config: dict, path) -> dict | None:
    if not isinstance(path, str) or not path:
        return None
    want = Path(path).expanduser().resolve()
    return next((r for r in config.get("repos", [])
                 if isinstance(r, dict) and r.get("path") and Path(r["path"]) == want), None)


def fact_freshness(config: dict, fact: dict) -> bool | None:
    """確かめた時点から、出典のファイルが base 側で変わったか（判定できなければ None）."""
    repo = config_repo(config, fact.get("repo"))
    path, sha = fact.get("path"), fact.get("base_sha")
    if repo is None or not isinstance(path, str) or not path or not isinstance(sha, str):
        return None
    base = repo.get("base") or ""
    if base.startswith("-"):
        return None
    proc = run_git(repo["path"], "diff", "--quiet", sha, base, "--", path)
    if proc is None or proc.returncode not in (0, 1):
        return None
    return proc.returncode == 1


def cmd_fact(args) -> int:
    pdir = project_dir(args.project)
    require_hub(pdir, args.session_id)
    config = load_config(pdir)
    body = load_json_input(args.body_file, "fact の本文")
    claim = body.get("claim") if isinstance(body, dict) else None
    source = body.get("source") if isinstance(body, dict) else None
    if not isinstance(claim, str) or not claim.strip() or not isinstance(source, str) \
            or not source.strip():
        raise HubError(2, "claim と source の両方が要る（出典の無い事実は書かない）")
    # 出典が repo のファイルなら、確かめた時点の base の SHA を残す（brief がその後の変化を見る）
    repo = config_repo(config, body.get("repo"))
    if body.get("repo") is not None and repo is None:
        raise HubError(2, f"repo が config の repos に無い: {body.get('repo')}")
    source_path = body.get("path")
    if source_path is not None and (not isinstance(source_path, str) or not source_path.strip()
                                    or repo is None):
        raise HubError(2, "path は repo と一緒に、repo の中の相対パスで渡す")
    path = pdir / "facts.jsonl"
    facts = read_jsonl(path)
    if args.supersedes:
        if args.supersedes not in {f.get("id") for f in current_facts(facts)}:
            replaced = [f.get("id") for f in facts if f.get("supersedes") == args.supersedes]
            raise HubError(2, f"supersedes の id が有効な facts に無い: {args.supersedes}"
                              + (f"（既に {', '.join(map(str, replaced))} で置き換わっている）"
                                 if replaced else ""))
    fact_id = next_fact_id(path, facts)
    row = {"id": fact_id, "ts": now(), "claim": claim, "source": source,
           "checked_by": None if args.unchecked else "hub"}
    if repo is not None and source_path:
        row.update({"repo": repo["path"], "path": source_path,
                    "base_sha": git(repo["path"], "rev-parse", "--verify", "--quiet",
                                    f"{repo.get('base')}^{{commit}}")})
    if args.supersedes:
        row["supersedes"] = args.supersedes
    # 訂正の正本は facts。journal には id を指す行だけを置く
    append_jsonl(path, row)
    journal_append(pdir, "fact", fact_id, "")
    emit(row)
    return 0


def cmd_facts(args) -> int:
    pdir = project_dir(args.project)
    config = load_config(pdir)
    facts = current_facts(read_jsonl(pdir / "facts.jsonl"))
    if args.checked_only:
        facts = [f for f in facts if f.get("checked_by")]
    # stale: 確かめた後に出典のファイルが base 側で変わった（true）/ 変わっていない / 判定できない（null）
    emit([{**f, "stale": fact_freshness(config, f)} for f in facts])
    return 0


def cmd_record(args) -> int:
    """brief / relay の送った全文・宛先・送信の結果を journal に残す（{subject, text, to?, error?} を stdin で）."""
    pdir = project_dir(args.project)
    require_hub(pdir, args.session_id)
    body = load_json_input(args.body_file, "record の本文")
    if not isinstance(body, dict):
        raise HubError(2, "record の本文が JSON のオブジェクトではない")
    subject, text, to, error = body.get("subject"), body.get("text"), body.get("to"), body.get("error")
    if not isinstance(subject, str) or not subject.strip():
        raise HubError(2, "subject（Issue ID か宛先）が無い")
    if not isinstance(text, str) or not text.strip():
        raise HubError(2, "text（送った全文）が空")
    if to is not None and not (isinstance(to, dict) and isinstance(to.get("name"), str)
                               and isinstance(to.get("ref"), str) and REF_RE.fullmatch(to["ref"])):
        raise HubError(2, "to は {\"name\", \"ref\"} か null")
    if error is not None and not isinstance(error, str):
        raise HubError(2, "error は文字列か null")
    journal_append(pdir, args.kind, subject,
                   {"text": text, "to": to, "result": args.result, "error": error})
    emit({"kind": args.kind, "subject": subject, "result": args.result})
    return 0


# ---------------------------------------------------------------- status の材料


def cmd_ingest(args) -> int:
    pdir = project_dir(args.project)
    require_hub(pdir, args.session_id)
    kind = tracker_kind(load_config(pdir))
    inbox = pdir / "inbox"
    for sub in ("done", "invalid"):
        (inbox / sub).mkdir(parents=True, exist_ok=True)
    seen = {r.get("source") for r in read_jsonl(pdir / "journal.jsonl") if r.get("kind") == "report"}
    # reports は今回取り込んだ分の中身（status が lead に見せる）。state.md には写さない
    result = {"ingested": [], "duplicates": [], "invalid": [], "reports": []}
    for path in sorted(inbox.glob("*.json")):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            errs = validate_report(data, args.project, kind)
        except (OSError, ValueError) as e:
            errs = [f"JSON として読めない: {e}"]
        if errs:
            # 取り込めないファイルは invalid/ へ移す（消さない）。inbox に残すと未取り込みに数え続ける
            os.replace(path, inbox / "invalid" / path.name)
            result["invalid"].append({"file": path.name, "error": "; ".join(errs)})
            continue
        # journal へ追記してから移す。間で落ちても、次の回は journal の source で重複を飛ばす
        if path.name in seen:
            result["duplicates"].append(path.name)
        else:
            journal_append(pdir, "report", data["session_id"], data, source=path.name)
            seen.add(path.name)
            result["ingested"].append(path.name)
            result["reports"].append({"file": path.name, **{k: data.get(k) for k in (
                "name", "issue", "state", "pr", "needs_lead", "follow_ups", "claims")}})
        os.replace(path, inbox / "done" / path.name)
    emit(result)
    return 0


def latest_reports(rows: list[dict]) -> dict:
    latest = {}
    for row in rows:
        if row.get("kind") == "report" and isinstance(row.get("body"), dict):
            latest[row.get("subject")] = row
    return latest


def cmd_reports(args) -> int:
    """取り込み済みの report のうち、セッションごとの最新の中身（コンパクション・takeover の後に見直す）."""
    pdir = project_dir(args.project)
    out = []
    for sid, row in latest_reports(read_jsonl(pdir / "journal.jsonl")).items():
        if args.session and sid != args.session:
            continue
        body = row["body"]
        out.append({"session_id": sid, "file": row.get("source"), "ingested_at": row.get("ts"),
                    **{k: body.get(k) for k in (
                        "name", "issue", "state", "pr", "needs_lead", "follow_ups", "claims")}})
    emit(sorted(out, key=lambda r: str(r.get("ingested_at"))))
    return 0


def record_snapshot(pdir: Path, source: str, ok: bool, data=None, error: str | None = None,
                    truncated_at: int | None = None) -> None:
    path = pdir / "snapshot.json"
    snap = read_obj(path)
    sources = snap.setdefault("sources", {})
    if not isinstance(sources, dict):
        sources = snap["sources"] = {}
    prev = sources.get(source) if isinstance(sources.get(source), dict) else {}
    if ok:
        sources[source] = {"fetched_at": now(), "ok": True, "data": data}
        if truncated_at:
            sources[source]["truncated_at"] = truncated_at
    else:
        # 取得に失敗した回は前回の data を残す（表が空になると「何も無い」と読める）
        sources[source] = {"fetched_at": prev.get("fetched_at"), "ok": False, "failed_at": now(),
                           "error": error, "data": prev.get("data")}
    write_json(path, snap)


def normalize_prs(items, branches: set[str] | None) -> list:
    """PR 一覧（number,title,state,headRefName,isDraft,isCrossRepository）を表の形に揃える.

    branches を渡したら登録済みの branch を head に持つ PR だけを残す。fork の PR は head の branch 名
    だけが一致しうる（第三者の題が表に載る）ので、isCrossRepository が false と分かるものに限る
    """
    out = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        head = item.get("head", item.get("headRefName"))
        if branches is not None and (head not in branches or item.get("isCrossRepository") is not False):
            continue
        out.append({"number": item.get("number"), "title": item.get("title"), "state": item.get("state"),
                    "head": head, "draft": item.get("draft", item.get("isDraft"))})
    return out


def registered_branches(pdir: Path, config: dict) -> set[str]:
    regs, _ = load_registrations(pdir)
    # base のブランチ（main など）にいる登録は着手前で、その名前の PR は PJ のものと限らない
    bases = {str(r.get("base") or "").split("/")[-1] for r in config.get("repos", []) if isinstance(r, dict)}
    return {r["branch"] for r in regs if isinstance(r.get("branch"), str) and r["branch"] not in bases}


def cmd_snapshot(args) -> int:
    pdir = project_dir(args.project)
    require_hub(pdir, args.session_id)
    config = load_config(pdir)
    if not SOURCE_NAME_RE.fullmatch(args.source):
        raise HubError(2, f"source 名が不正: {args.source}")
    key = args.source
    if args.repo is not None:
        # repo ごとに取る source（prs）は repo ごとに持つ。同じ key で置き換えると前の repo の分が消える
        repo = config_repo(config, args.repo)
        if repo is None:
            raise HubError(2, f"repo が config の repos に無い: {args.repo}")
        key = f"{args.source}:{repo['path']}"
    body = load_json_input(args.data_file, "data")
    if args.failed:
        error = body.get("error") if isinstance(body, dict) else None
        record_snapshot(pdir, key, ok=False, error=error if isinstance(error, str) else "")
        emit({"source": key, "ok": False})
        return 0
    raw_count = len(body) if isinstance(body, list) else None
    data = body
    if args.source == "prs":
        branches = registered_branches(pdir, config) if args.registered_branches else None
        data = normalize_prs(body, branches)
    # 取得の上限に届いていたら、窓の外に出た分が黙って消えている可能性がある
    truncated = bool(args.limit and raw_count is not None and raw_count >= args.limit)
    record_snapshot(pdir, key, ok=True, data=data, truncated_at=args.limit if truncated else None)
    emit({"source": key, "ok": True, "count": len(data) if isinstance(data, list) else None,
          "truncated": truncated})
    return 0


def cmd_presence(args) -> int:
    """ListAgents に名前が無い登録へ absent_since を付け、戻ったものから外す."""
    pdir = project_dir(args.project)
    require_hub(pdir, args.session_id)
    try:
        agents = load_agents(args.agents_file, args.peer_count)
    except HubError as e:
        record_snapshot(pdir, "agents", ok=False, error=str(e))
        emit({"status": "parse_failed", "reason": str(e)})
        return 2
    names = {a["name"] for a in agents}
    # 不在は登録（sessions/。書き手は report）ではなく hub 専用の presence.json に持つ。
    # 同じファイルを hub と作業側が書き直すと、作業側の新しい名前を古い内容で上書きしうる
    old = absent_map(pdir)
    regs, unreadable = load_registrations(pdir)
    absent_now: dict = {}
    present, absent = [], []
    ts = stamp()
    kind = tracker_kind(load_config(pdir))
    for reg in regs:
        token = issue_token(kind, reg.get("issue") or "")
        # 既定名は別のセッションが同じ番号を名乗りうるので、名前の一致を在席の根拠にしない
        if reg.get("name") in names and not is_default_name(str(reg.get("name")), token):
            present.append(reg.get("name"))
            continue
        since = absent_since(reg, old) or ts
        absent_now[reg["session_id"]] = {"absent_since": since}
        absent.append({"name": reg.get("name"), "absent_since": since})
    write_json(pdir / "presence.json", absent_now)
    record_snapshot(pdir, "agents", ok=True, data=agents)
    emit({"status": "ok", "present": present, "absent": absent, "unreadable": unreadable})
    return 0


def changed_files(worktree: str, base: str) -> list[str] | None:
    if not base or base.startswith("-"):  # `-` で始まる値は git のオプションとして読まれる
        return None
    out = git(worktree, "diff", "--name-only", "-z", f"{base}...HEAD")
    return None if out is None else [p for p in out.split("\0") if p]


def uncommitted_files(worktree: str) -> list[str] | None:
    # --no-optional-locks: 作業側の index を書き直さない（作業側の git add と index.lock で衝突する）
    out = git(worktree, "--no-optional-locks", "status", "--porcelain", "-z")
    if out is None:
        return None
    fields = out.split("\0")
    files, i = [], 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        files.append(entry[3:])
        # rename / copy は次のフィールドが元のパス。触っている側（新しいパス）だけを取る
        if "R" in entry[:2] or "C" in entry[:2]:
            i += 1
    return files


def cmd_worktrees(args) -> int:
    """brief の材料: 各 repo の base の SHA と、登録済みセッションが触っているファイル."""
    pdir = project_dir(args.project)
    config = load_config(pdir)
    repos = []
    for repo in config.get("repos", []):
        if not isinstance(repo, dict):
            continue
        repos.append({"path": repo.get("path"), "base": repo.get("base"),
                      "base_sha": git(repo.get("path"), "rev-parse", "--verify", "--quiet",
                                      f"{repo.get('base')}^{{commit}}"),
                      "common_dir": str(git_common_dir(repo.get("path")) or "")})
    sessions = []
    absent = absent_map(pdir)
    regs, unreadable = load_registrations(pdir)
    shared = {w for w in (r.get("worktree") for r in regs)
              if w and sum(1 for r in regs if r.get("worktree") == w) > 1}
    for reg in regs:
        entry = {"session_id": reg.get("session_id"), "name": reg.get("name"),
                 "issue": reg.get("issue"), "branch": reg.get("branch"),
                 "worktree": reg.get("worktree"), "absent_since": absent_since(reg, absent),
                 "changed": None, "uncommitted": None}
        worktree = reg.get("worktree")
        common = git_common_dir(worktree) if worktree and Path(worktree).is_dir() else None
        repo = next((r for r in repos if common is not None and r["common_dir"] == str(common)), None)
        if repo is None:
            entry["note"] = "worktree が無いか、config の repos に当たらない"
        elif reg.get("branch") == str(repo["base"]).split("/")[-1] or worktree in shared:
            # hello は branch・worktree を作る前に出るので、その時点の登録のまま実装が進みうる
            entry["note"] = "着手前の登録のまま（base のブランチか、他のセッションと同じ worktree）。重なりは不明"
        else:
            entry["changed"] = changed_files(worktree, repo["base"])
            entry["uncommitted"] = uncommitted_files(worktree)
            if entry["changed"] is None or entry["uncommitted"] is None:
                # 取れなかったことを「変更なし」と区別する（重なりの判断を誤らせない）
                entry["note"] = f"git で変更を取れない（base: {repo['base']}）。重なりは不明"
        sessions.append(entry)
    emit({"repos": repos, "sessions": sessions, "unreadable": unreadable})
    return 0


# ---------------------------------------------------------------- state.md


def cell(value, limit: int | None = TITLE_MAX) -> str:
    text = "-" if value is None or value == "" else str(value)
    # 表の 1 セルに収める。splitlines() が行の区切りとみなす文字（\r・U+2028 等）を全部潰す。
    # 潰さないと、注入した表から作業側やトラッカー由来の文字列が独立した行（見出し）として抜け出す
    text = CONTROL_RE.sub(" ", " ".join(text.splitlines())).replace("|", "\\|")
    # 外部の文面にあるタグ（`</system-reminder>` 等）を、注入した文脈でタグとして読ませない
    text = text.replace("<", "＜").replace(">", "＞")
    if limit is not None and len(text) > limit:
        text = text[:limit - 1] + "…"
    return text


def more_rows(items: list, where: str) -> list[str]:
    # 注入する表を長くしない
    rest = len(items) - TABLE_MAX
    return [f"（ほか {rest} 件。全件は {where}）"] if rest > 0 else []


def state_name(value) -> str | None:
    # Linear の status はオブジェクト（{"name": ...}）で返ることがある
    if isinstance(value, dict):
        return value.get("name")
    return value


def render_state(pdir: Path) -> tuple[str, int]:
    config = load_config(pdir)
    hub = read_obj(pdir / "hub.json")
    snap = read_obj(pdir / "snapshot.json")
    lines = journal_lines(pdir / "journal.jsonl")
    rows = parse_jsonl(lines)
    latest = latest_reports(rows)
    sessions, unreadable = load_registrations(pdir)
    absent = absent_map(pdir)
    facts = read_jsonl(pdir / "facts.jsonl")
    current = current_facts(facts)
    ts = now()

    out = [f"<!-- project-hub-state generated_at={ts} journal_lines={len(lines)} -->",
           f"# project-hub: {cell(config.get('project'))}",
           "",
           f"- 生成: {ts}（journal の {len(lines)} 行目まで反映）",
           f"- hub: {cell(hub.get('name'))}（session {cell(hub.get('session_id'))}）",
           f"- PJ の状態: {cell(config.get('status'))}",
           f"- 未取り込みの report: {pending_count(pdir)} 件",
           "- 作業側から「report を置いた」の通知を受けたら、その場で取り込まない。"
           "未取り込みの件数を 1 行出すだけにし、取り込みは `hub status` で行う",
           "",
           "## 作業セッション",
           ""]
    if sessions:
        # report の自由文（needs_lead / follow_ups / claims）は写さず件数だけ載せる。
        # 作業側が読んだ外部の文面を、lead の承認なしに hub のコンテキストへ入れないため。
        # 中身は `hub.py reports` で見る
        out += ["| 名前 | Issue | 状態 | PR | ブランチ | 最終 report | 要判断・follow-up・主張 | 不在 |",
                "|---|---|---|---|---|---|---|---|"]
        ordered = sorted(sessions, key=lambda r: (absent_since(r, absent) is not None,
                                                  str(r.get("issue")), str(r.get("name"))))
        for reg in ordered[:TABLE_MAX]:
            rep = latest.get(reg.get("session_id"))
            body = rep["body"] if rep else {}
            counts = (f"{len(body.get('needs_lead') or [])}・{len(body.get('follow_ups') or [])}"
                      f"・{len(body.get('claims') or [])}") if rep else "-"
            out.append("| " + " | ".join([
                cell(reg.get("name")), cell(reg.get("issue")), cell(body.get("state")),
                cell(body.get("pr")), cell(reg.get("branch")), cell(rep and rep.get("ts")),
                counts, cell(absent_since(reg, absent))]) + " |")
        out += more_rows(ordered, "sessions/")
    else:
        out.append("（登録なし。作業側の report で登録される）")
    if unreadable:
        out.append(f"（読めない登録 {len(unreadable)} 件: {cell(', '.join(unreadable), None)}）")

    sources = snap.get("sources") if isinstance(snap.get("sources"), dict) else {}
    out += ["", "## 外部の状態", ""]
    if sources:
        out += ["| source | 取得 | 状態 | 件数 |", "|---|---|---|---|"]
        for name in sorted(sources):
            src = sources[name] if isinstance(sources[name], dict) else {}
            status = "ok" if src.get("ok") else f"取得失敗（{src.get('failed_at')}）"
            if src.get("truncated_at"):
                status += f"・上限 {src['truncated_at']} 件で打ち切った可能性"
            data = src.get("data")
            out.append(f"| {cell(name)} | {cell(src.get('fetched_at'))} | {cell(status)} | "
                       f"{len(data) if isinstance(data, list) else '-'} |")
        tracker = (sources.get("tracker") or {}).get("data")
        if isinstance(tracker, list) and tracker:
            out += ["", "### Issue", "", "| ID | 状態 | 担当 | PR | タイトル |", "|---|---|---|---|---|"]
            for item in tracker[:TABLE_MAX]:
                if isinstance(item, dict):
                    out.append("| " + " | ".join([
                        cell(item.get("id")), cell(state_name(item.get("state"))),
                        cell(item.get("assignee")), cell(item.get("pr")),
                        cell(item.get("title"))]) + " |")
            out += more_rows(tracker, "snapshot.json")
        prs = []
        for key in sorted(sources):
            data = sources[key].get("data") if isinstance(sources[key], dict) else None
            if (key == "prs" or key.startswith("prs:")) and isinstance(data, list):
                repo = Path(key.split(":", 1)[1]).name if ":" in key else ""
                prs += [{**item, "repo": repo} for item in data if isinstance(item, dict)]
        if prs:
            out += ["", "### PR", "", "| repo | # | 状態 | draft | ブランチ | タイトル |",
                    "|---|---|---|---|---|---|"]
            for item in prs[:TABLE_MAX]:
                out.append("| " + " | ".join([
                    cell(item.get("repo")), cell(item.get("number")), cell(item.get("state")),
                    cell(item.get("draft")), cell(item.get("head")), cell(item.get("title"))]) + " |")
            out += more_rows(prs, "snapshot.json")
    else:
        out.append("（未取得。`hub status` で集める）")

    checked = sum(1 for f in current if f.get("checked_by"))
    out += ["", "## facts", "",
            f"- 有効 {len(current)} 件（確かめた {checked} / 未確認 {len(current) - checked}）・"
            f"訂正で置き換わった {len(facts) - len(current)} 件。brief が引くのは確かめた行だけ",
            "", f"## journal（直近 {RECENT_JOURNAL} 件）", ""]
    if rows:
        out += ["| 時刻 | kind | subject |", "|---|---|---|"]
        for row in rows[-RECENT_JOURNAL:]:
            out.append(f"| {cell(row.get('ts'))} | {cell(row.get('kind'))} | {cell(row.get('subject'))} |")
    else:
        out.append("（まだ無い）")
    return "\n".join(out) + "\n", len(lines)


def cmd_render(args) -> int:
    pdir = project_dir(args.project)
    require_hub(pdir, args.session_id)
    text, count = render_state(pdir)
    path = pdir / "state.md"
    tmp = path.with_name(".state.md.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    emit({"state": str(path), "journal_lines": count})
    return 0


# ---------------------------------------------------------------- 宛先の照合


def unresolved(reason: str, **extra) -> int:
    emit({"status": "unresolved", "reason": reason, **extra})
    return 1


def candidates(rows: list[dict]) -> list[dict]:
    return [{"name": a["name"], "ref": a["ref"]} for a in rows]


def resolved(hit: dict, rule: str, expect_ref: str | None, warning: str | None = None) -> int:
    # 承認の画面に出した ref と違えば、同じ名前の別のセッションに入れ替わっている
    if expect_ref and hit["ref"] != expect_ref:
        return unresolved(f"名前は同じだが ref が承認時（{expect_ref}）と違う", candidates=candidates([hit]))
    out = {"status": "ok", "name": hit["name"], "ref": hit["ref"], "rule": rule}
    if warning:
        out["warning"] = warning
    emit(out)
    return 0


def foreign_names(pdir: Path) -> set[str]:
    """ほかの PJ の hub と作業セッションの名前（Issue 番号は PJ をまたいで重なりうる）."""
    names = set()
    for other in sorted(root().iterdir()):
        if other == pdir or not other.is_dir() or not PROJECT_RE.fullmatch(other.name):
            continue
        try:
            names.add(read_obj(other / "hub.json").get("name"))
        except HubError:
            pass
        regs, _ = load_registrations(other)
        names.update(r.get("name") for r in regs)
    return {n for n in names if isinstance(n, str)}


def pick_exact(agents: list[dict], name, rule: str, expect_ref: str | None = None) -> int:
    if not name:
        return unresolved("照合に使う名前が無い", candidates=candidates(agents))
    hits = [a for a in agents if a["name"] == name]
    if len(hits) == 1:
        return resolved(hits[0], rule, expect_ref)
    return unresolved(f"名前「{name}」に一致する行が {len(hits)} 件", name=name,
                      candidates=candidates(hits or agents))


def cmd_resolve(args) -> int:
    pdir = project_dir(args.project)
    config = load_config(pdir)
    if args.session is not None and not args.session.strip():
        raise HubError(2, "--session が空")
    if args.ref is not None and not REF_RE.fullmatch(args.ref):
        raise HubError(2, "--ref は ListAgents の [ref]（英数字）")
    if not args.hub:
        # hub → 作業側（brief / relay）。送るのは hub だけ（作業側の report の通知は --hub）
        require_hub(pdir, args.session_id)
    try:
        agents = load_agents(args.agents_file, args.peer_count)
    except HubError as e:
        emit({"status": "parse_failed", "reason": str(e)})
        return 2
    if args.hub:
        hub_name = read_obj(pdir / "hub.json").get("name")
        if not isinstance(hub_name, str) or is_default_name(hub_name, None):
            return unresolved(f"hub の名前「{hub_name}」が既定名なので宛先にしない", candidates=candidates(agents))
        return pick_exact(agents, hub_name, "hub_name", args.expect_ref)
    if args.ref is not None:
        # lead が候補から選んだ行。名前は変わりうるので ref で引き、今の名前を返す
        hits = [a for a in agents if a["ref"] == args.ref]
        if len(hits) == 1:
            return resolved(hits[0], "ref", None)
        return unresolved(f"ref「{args.ref}」に一致する行が {len(hits)} 件", candidates=candidates(agents))

    if not SESSION_ID_RE.fullmatch(args.session):
        raise HubError(2, "session_id に使えない文字がある")
    try:
        reg = read_obj(pdir / "sessions" / f"{args.session}.json") or None
    except HubError:
        reg = None
        unreadable = True
    else:
        unreadable = False
    registered = reg.get("name") if reg else None
    absent = absent_since(reg, absent_map(pdir)) if reg else None
    issue = args.issue or (reg.get("issue") if reg else None)
    token = issue_token(tracker_kind(config), issue) if issue else None
    # 既定名（<dir>-<数字>）だけの一致は使わない。開き直しで別のセッションが同じ番号を名乗りうる
    if registered and not absent and not is_default_name(registered, token):
        hits = [a for a in agents if a["name"] == registered]
        if len(hits) == 1:
            return resolved(hits[0], "registered_name", args.expect_ref)
        if len(hits) > 1:
            return unresolved(f"登録名「{registered}」に一致する行が {len(hits)} 件",
                              registered_name=registered, candidates=candidates(hits))

    if not issue:
        return unresolved("登録名で引けず、照合に使う Issue ID も無い", registered_name=registered,
                          absent_since=absent, registration_unreadable=unreadable,
                          candidates=candidates(agents))
    if token is None:
        return unresolved(f"Issue ID「{issue}」が tracker の形と合わない", registered_name=registered,
                          candidates=candidates(agents))
    foreign = foreign_names(pdir)
    hits = [a for a in agents if not is_default_name(a["name"], token) and token.search(a["name"])
            and a["name"] not in foreign]
    if len(hits) == 1:
        return resolved(hits[0], "issue_token", args.expect_ref,
                        warning=f"登録名ではなく、名前に含まれる Issue ID で引いた（「{hits[0]['name']}」）。"
                                "承認の画面で、この名前が宛先のセッションか lead に確かめてもらう")
    return unresolved(f"Issue ID「{issue}」を名前に含む行が {len(hits)} 件",
                      registered_name=registered, absent_since=absent, issue=issue,
                      candidates=candidates(hits or agents))


# ---------------------------------------------------------------- 作業側の report


def detect_project(cwd: Path) -> str:
    mine = git_common_dir(cwd)
    if mine is None:
        raise HubError(1, "cwd が git リポジトリではないので PJ を決められない。--project で指定する")
    hits = []
    for cfg_path in sorted(root().glob("*/config.json")):
        try:
            config = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(config, dict) or not is_active(config):
            continue
        if any(git_common_dir(r.get("path")) == mine for r in config.get("repos", [])
               if isinstance(r, dict) and r.get("path")):
            hits.append(cfg_path.parent.name)
    if len(hits) == 1:
        return hits[0]
    raise HubError(1, f"PJ が決まらない（cwd の repo を含む active な PJ が {len(hits)} 件"
                      f"{': ' + ', '.join(hits) if hits else ''}）。--project で指定する")


def cmd_report(args) -> int:
    sid = current_session(args.session_id)
    problem = name_problem(args.name)
    if problem:
        raise HubError(2, problem + "（ListAgents の「This session is ...」から取る）")
    cwd = Path(args.cwd or os.getcwd())
    project = args.project or detect_project(cwd)
    pdir = project_dir(project)
    config = load_config(pdir)
    if not is_active(config):
        raise HubError(3, f"PJ {project} は active ではない（status: {config.get('status')}）")
    body = load_json_input(args.body_file, "report の本文")
    if not isinstance(body, dict):
        raise HubError(2, "report の本文が JSON のオブジェクトではない")

    # ListAgents の抜き出しを先に検査し、合わなければ何も書かない（hub への通知先もここで決める）
    agents = body.get("agents")
    self_ref = body.get("self_ref")
    problems = check_agents(agents, body.get("peer_count"))
    if not isinstance(self_ref, str) or not REF_RE.fullmatch(self_ref):
        problems.append("self_ref（1 行目の This session is <name> [<ref>] の ref）が英数字ではない")
    elif not problems and any(a["ref"] == self_ref for a in agents):
        problems = ["自分の ref が Peer sessions の行にある（自分の行は 1 行目の This session is から取る）"]
    if problems:
        emit({"status": "parse_failed", "reason": "ListAgents の抜き出しが自己検査に合わない: "
                                                  + "; ".join(problems)})
        return 2

    kind = tracker_kind(config)
    report = {"schema": REPORT_SCHEMA, "session_id": sid, "name": args.name, "project": project,
              "issue": body.get("issue"), "state": body.get("state"), "pr": body.get("pr"),
              "needs_lead": body.get("needs_lead", []), "follow_ups": body.get("follow_ups", []),
              "claims": body.get("claims", [])}
    errs = validate_report(report, project, kind)
    if errs:
        raise HubError(2, "report の形が不正: " + "; ".join(errs))
    hub_name = read_obj(pdir / "hub.json").get("name")

    # 宛先にする欄は持たない（名前は毎回 ListAgents で引き直す / ADR-20261021154740）
    (pdir / "sessions").mkdir(exist_ok=True)
    write_json(pdir / "sessions" / f"{sid}.json", {
        "session_id": sid,
        "host_session_id": os.environ.get("CLAUDE_CODE_HOST_SESSION_ID") or None,
        "name": args.name, "project": project, "issue": report["issue"],
        "branch": git(cwd, "rev-parse", "--abbrev-ref", "HEAD"),
        "worktree": git(cwd, "rev-parse", "--show-toplevel"),
        "updated": stamp(),
    })
    name = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + f"-{sid}.json"
    (pdir / "inbox").mkdir(exist_ok=True)
    write_json(pdir / "inbox" / name, report)

    hits = [a for a in agents if hub_name and a["name"] == hub_name]
    if not isinstance(hub_name, str) or is_default_name(hub_name, None):
        # 既定名は開き直した別のセッションが名乗りうる（通知の先を取り違える）
        notify = {"status": "unresolved", "reason": f"hub の名前「{hub_name}」が既定名なので宛先にしない"}
    elif len(hits) == 1:
        notify = {"status": "ok", "name": hits[0]["name"], "ref": hits[0]["ref"]}
    else:
        notify = {"status": "unresolved", "reason": f"hub の名前「{hub_name}」に一致する行が {len(hits)} 件"}
    out = {"file": name, "project": project, "hub_name": hub_name, "notify": notify}
    warnings = []
    if is_default_name(args.name, issue_token(kind, report["issue"])):
        warnings.append("既定名で登録した。hub は既定名では宛先を引かないので、"
                        "会話の題に Issue ID を入れてから report し直すよう利用者に頼む")
    if any(a["name"] == args.name for a in agents):
        warnings.append("同じ名前の別のセッションがある。hub はこの名前では宛先を決められないので、"
                        "会話の題を変えてから report し直すよう利用者に頼む")
    if warnings:
        out["warning"] = " / ".join(warnings)
    emit(out)
    return 0


# ---------------------------------------------------------------- hook


def inject_text(pdir: Path, config: dict) -> str:
    out = [f"## project-hub: このセッションは PJ「{cell(config.get('project'))}」の hub", ""]
    reflected = 0
    try:
        state = (pdir / "state.md").read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        state = None
    if state is None:
        out.append("state.md がまだ無い。`/project-hub:hub status` で作る")
    else:
        m = STATE_HEADER_RE.match(state[0]) if state else None
        if m:
            reflected = int(m.group(2))
            state = state[1:]
        out += state
    later = parse_jsonl(journal_lines(pdir / "journal.jsonl")[reflected:])
    counts: dict[str, int] = {}
    for row in later:
        kind = cell(row.get("kind"))
        counts[kind] = counts.get(kind, 0) + 1
    summary = "・".join(f"{k} {v}" for k, v in sorted(counts.items())) or "なし"
    out += ["", "### state.md の生成後",
            f"- 増えた journal（kind 別）: {summary}",
            f"- 未取り込みの report: {pending_count(pdir)} 件"
            "（取り込みと表の作り直しは `/project-hub:hub status`）"]
    return "\n".join(out)


def cmd_inject(args) -> int:
    # hook から呼ぶ。stdin がどんな形でも exit 0 で、hub でないセッションには何も出さない。
    # 状態ファイルが壊れた PJ は飛ばす（1 つの PJ で他の PJ の注入まで止めない）
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    sid = payload.get("session_id") if isinstance(payload, dict) else None
    if not isinstance(sid, str) or not sid:
        return 0
    blocks = []
    for hub_path in sorted(root().glob("*/hub.json")):
        try:
            hub = json.loads(hub_path.read_text(encoding="utf-8"))
            if not isinstance(hub, dict) or hub.get("session_id") != sid:
                continue
            config = json.loads((hub_path.parent / "config.json").read_text(encoding="utf-8"))
            if not isinstance(config, dict) or not is_active(config):
                continue
            blocks.append(inject_text(hub_path.parent, config))
        except (OSError, ValueError) as e:
            print(f"project-hub: {hub_path.parent.name} を注入できない（{e}）", file=sys.stderr)
    if blocks:
        print("\n\n".join(blocks))
    return 0


# ---------------------------------------------------------------- CLI


SID_HELP = "既定は CLAUDE_CODE_SESSION_ID（両方あって違えば止める）"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hub.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add(name: str, func, help_text: str, project: bool = True,
            session: bool = True) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text, description=help_text)
        if project:
            p.add_argument("--project", required=True)
        if session:
            p.add_argument("--session-id", help=SID_HELP)
        p.set_defaults(func=func)
        return p

    p = add("init", cmd_init, "PJ を作り、このセッションを hub として登録する（config が無いときだけ）")
    p.add_argument("--name", required=True, help="ListAgents の「This session is <name>」")
    p.add_argument("--tracker", choices=("github", "linear"), required=True)
    p.add_argument("--tracker-repo", help="github: owner/name")
    p.add_argument("--tracker-team", help="linear: team")
    p.add_argument("--tracker-project", help="linear: project")
    p.add_argument("--milestone")
    p.add_argument("--repo", action="append",
                   help="<path>[=<base>]（複数可。base の既定は origin/HEAD が指すブランチ。repo に実在すること）")
    p.add_argument("--approval-prefix", default="")
    p.add_argument("--approval-suffix", default="")

    p = add("takeover", cmd_takeover, "hub.json を今のセッションに書き換え、journal に takeover を残す")
    p.add_argument("--name", required=True)

    p = add("refresh-hub", cmd_refresh_hub,
            "今のセッションが hub か確かめ、名前の変化を hub.json に反映する（config も出す）")
    p.add_argument("--name", required=True)

    add("close", cmd_close, "config の status を closed にする")
    add("projects", cmd_projects, "PJ の一覧（status・hub の名前・未取り込みの件数）",
        project=False, session=False)

    p = add("fact", cmd_fact, "確かめた事実を出典つきで facts に足す（{\"claim\", \"source\"} を stdin の JSON で）")
    p.add_argument("--supersedes", help="訂正する前の行の id（有効な行に限る）")
    p.add_argument("--unchecked", action="store_true",
                   help="作業側の主張をそのまま写す（checked_by: null。brief は引かない）")
    p.add_argument("--body-file", default="-")

    p = add("facts", cmd_facts, "有効な facts（訂正で置き換わった行を除く）", session=False)
    p.add_argument("--checked-only", action="store_true")

    p = add("record", cmd_record,
            "brief / relay の全文・宛先・送信の結果を journal に残す"
            "（{\"subject\", \"text\", \"to\", \"error\"} を stdin の JSON で）")
    p.add_argument("--kind", choices=("brief", "relay"), required=True)
    p.add_argument("--result", choices=SEND_RESULTS, required=True)
    p.add_argument("--body-file", default="-")

    add("ingest", cmd_ingest, "inbox の report を journal に取り込み done/ へ移す（不正なものは invalid/ へ）")

    p = add("reports", cmd_reports, "取り込み済みの report のセッションごとの最新の中身", session=False)
    p.add_argument("--session", help="session_id で絞る")

    p = add("snapshot", cmd_snapshot, "外部の状態を source ごとに snapshot.json へ（data は stdin の JSON）")
    p.add_argument("--source", required=True, help="tracker / prs など")
    p.add_argument("--data-file", default="-")
    p.add_argument("--repo", help="repo ごとに取る source（prs）の repo のパス（config の repos のどれか）")
    p.add_argument("--registered-branches", action="store_true",
                   help="prs: 登録済みセッションの branch を head に持つ、同じ repo からの PR だけを残す")
    p.add_argument("--limit", type=int, help="取得に付けた件数の上限（届いていたら打ち切りの可能性を残す）")
    p.add_argument("--failed", action="store_true",
                   help="取得に失敗した（前回の data を残す。stdin は {\"error\": ...}）")

    p = add("presence", cmd_presence, "ListAgents と登録を突き合わせて absent_since を付け外しする")
    p.add_argument("--agents-file", default="-")
    p.add_argument("--peer-count", type=int, required=True, help="見出し「Peer sessions (N)」の N")

    add("render", cmd_render, "journal・sessions・snapshot から state.md を作り直す")
    add("worktrees", cmd_worktrees, "base の SHA と、登録済みセッションが触っているファイル", session=False)

    p = add("resolve", cmd_resolve, "ListAgents から抜き出した JSON で宛先を 1 件に決める（送る直前に毎回）")
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("--hub", action="store_true", help="作業側 → hub")
    target.add_argument("--session", help="hub → 作業側（登録の session_id）")
    target.add_argument("--ref", help="lead が候補から選んだ行の ref（登録名でも Issue ID でも決まらないとき）")
    p.add_argument("--issue", help="登録名で引けないときに照合する Issue ID")
    p.add_argument("--expect-ref", help="承認の画面に出した ref。違えば送らない")
    p.add_argument("--agents-file", default="-")
    p.add_argument("--peer-count", type=int, required=True)

    p = add("report", cmd_report,
            "作業側の report。stdin の JSON に本文と ListAgents の抜き出し（agents / peer_count）を入れる",
            project=False)
    p.add_argument("--project", help="brief が渡した PJ。無ければ cwd の repo から決める")
    p.add_argument("--name", required=True, help="ListAgents の「This session is <name>」")
    p.add_argument("--cwd")
    p.add_argument("--body-file", default="-")

    add("inject", cmd_inject, "hook 用: stdin の session_id が hub なら state.md を出す",
        project=False, session=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except HubError as e:
        print(f"project-hub: {e}", file=sys.stderr)
        return e.code
    except Exception as e:  # 想定外の失敗を「決まらない」の 1 と取り違えさせない
        print(f"project-hub: 想定外の失敗: {type(e).__name__}: {e}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
