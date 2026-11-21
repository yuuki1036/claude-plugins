#!/usr/bin/env python3
"""読んだ skill の版を記録し、新しい版が入ったら読み直すよう知らせる（GitHub issue #416）.

入口は stale-skill.sh（前段の判定はそちら）。stdin に hook の payload、argv[1] にモード。

- record: PostToolUse の Read / Skill から、このセッションが読んだ版を記録する。stdout には何も書かない
  （PostToolUse の stdout が漏れると、プラグインのファイルを Read するたびに注入される）
- prompt / compact / session-start: 記録とインストール済みの版を比べ、違うものを plain stdout で知らせる。
  同じ (プラグイン, 新しい版) は 1 回だけ。compaction の後は通知も消えているので、もう一度出す
- session-start が fork で届いたら状態ファイルを作り、親が読んだ版を、transcript が書かれた後の hook で拾う
  （adopt_fork_transcript）。デスクトップアプリの fork は resume として届くので、状態ファイルが無く
  transcript が別のセッションから写されたもの（copied_transcript）なら、同じ取り込みを通す

どの失敗も黙って exit 0 にする（hook の失敗でセッションを止めない）。
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import sys
import time
from pathlib import Path

# パストラバーサル防止を兼ねる（状態ファイル名に使う）。stale-skill.sh の前段の grep と同じ文字種にする
SID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
# .../plugins/cache/<marketplace>/<plugin>/<version>/<版の中のファイル>
CACHE_RE = re.compile(r"/plugins/cache/([^/]+)/([^/]+)/([^/]+)/(.+)$")
SKILL_RE = re.compile(r"^skills/([^/]+)/SKILL\.md$")
# Skill tool が skill の本文を注入した transcript の行の先頭（パスは .../skills/<name> まで。
# CLAUDE_CONFIG_DIR に空白があってもよいよう、パスは行末まで取る）
SKILL_BASE = "Base directory for this skill: "
SKILL_BASE_RE = re.compile(re.escape(SKILL_BASE) + r"([^\n]*/skills/[^/\n]+?)[ \t]*(?:\n|$)")
HEADING_RE = re.compile(r"^## \[([^\]]+)\]")
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")
# compaction の後は SessionStart(compact) と PostCompact の両方が来る版がある。この秒数の中の 2 回目は
# 通知済みを消し直さない（消し直すと同じ通知が 2 回出る）
REARM_WINDOW = 120
CHANGELOG_LIMIT = 5
# 写された transcript かを見るのは先頭のこの行数まで（sessionId の無い行が先頭に並ぶことがある）。
# stale-skill.sh の前段の head -n と揃える
COPIED_HEAD_LINES = 5
SCHEMA_VERSION = 1

GUIDE = (
    "読み直したら、新しい版で足された手順のうち今の作業に効くもの（前段の確認・名前の直しなど）は、"
    "利用者に確かめずに先に済ませてから続ける。後から戻しにくい変更（設定やデータの移行など）だけは利用者に聞く。"
)


# 状態の置き場所は stale-skill.sh の DIR と揃える（bash の前段が見つけられないと通知だけが黙って消える）
def config_dir() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".claude"


def state_path(sid: object) -> Path | None:
    if not isinstance(sid, str) or not SID_RE.match(sid):
        return None
    return config_dir() / "plugin-manager" / "sessions" / f"{sid}.json"


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_state(path: Path) -> dict | None:
    """形の違う状態（壊れた・別の schema_version）は None。値の型が崩れた記録は捨てて読む."""
    data = load_json(path)
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        return None
    plugins = data.get("plugins") if isinstance(data.get("plugins"), dict) else {}
    for key, rec in list(plugins.items()):
        if not isinstance(rec, dict):
            del plugins[key]
            continue
        if not isinstance(rec.get("version", ""), str):
            del rec["version"]
        if "skills" in rec:
            skills = rec["skills"] if isinstance(rec["skills"], dict) else {}
            rec["skills"] = {k: v for k, v in skills.items() if isinstance(v, str)}
        if "skills_from_skill" in rec:
            names = rec["skills_from_skill"] if isinstance(rec["skills_from_skill"], list) else []
            rec["skills_from_skill"] = [n for n in names if isinstance(n, str)]
    data["plugins"] = plugins
    if not isinstance(data.get("notified"), dict):
        data["notified"] = {}
    return data


def new_state(sid: str) -> dict:
    return {"schema_version": SCHEMA_VERSION, "session_id": sid, "plugins": {}, "notified": {}}


def lock(path: Path):
    """同じターンの並列の Read で PostToolUse が重なると、読んで書くあいだに片方の記録が消えるので排他する."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path.parent / ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)  # mutation-ok: 呼び出し元はどれも先に lock() が parents=True で親を作っている
    # stale-skill.sh の掃除はこの `.*.tmp` の形を前提に書きかけを消す
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    # ensure_ascii は既定（True）のまま。False だと payload の `\ud800` のような対のないサロゲートが
    # utf-8 に符号化できず、その回の記録ごと落ちる（GitHub issue #455）
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_installed() -> dict | None:
    """plugins の値が entry の list の形（installed_plugins.json の version 2）だけを受け付ける."""
    data = load_json(config_dir() / "plugins" / "installed_plugins.json")
    if not isinstance(data, dict) or not isinstance(data.get("plugins"), dict):
        return None
    out = {}
    for key, entries in data["plugins"].items():
        if not isinstance(entries, list):
            return None
        valid = [e for e in entries if isinstance(e, dict) and isinstance(e.get("version"), str)]
        if valid:
            out[key] = valid
    return out


def pick_entry(entries: list[dict]) -> dict:
    """scope が user の entry を優先する（project scope は別の repo の分かもしれない）."""
    for e in entries:
        if e.get("scope") == "user":
            return e
    return entries[0]


def record(payload: dict, state: dict, installed: dict | None) -> bool:
    tool = payload.get("tool_name")
    tin = payload.get("tool_input")
    if not isinstance(tin, dict):
        return False
    plugins = state["plugins"]
    if tool == "Read":
        path = tin.get("file_path")
        if not isinstance(path, str):
            return False
        m = CACHE_RE.search(path)
        if not m:
            return False
        mp, plugin, ver, rest = m.groups()
        rec = plugins.setdefault(f"{plugin}@{mp}", {})
        rec["version"] = ver
        rec.pop("version_from", None)
        sm = SKILL_RE.match(rest)
        if sm:
            rec.setdefault("skills", {})[sm.group(1)] = ver
            if sm.group(1) in rec.get("skills_from_skill", []):
                rec["skills_from_skill"].remove(sm.group(1))
        return True
    if tool == "Skill":
        name = tin.get("skill")
        if not isinstance(name, str) or ":" not in name or installed is None:
            return False
        plugin, skill = name.split(":", 1)
        keys = [k for k in installed if k.startswith(f"{plugin}@")]
        # 同じ名前のプラグインが 2 つの marketplace にあると、どちらを読んだか決められない
        if len(keys) != 1 or not skill:
            return False
        entry = pick_entry(installed[keys[0]])
        ver = entry["version"]
        rec = plugins.setdefault(keys[0], {})
        # Read で記録した版を上書きしない。Skill の時点の installed は、更新済み・未再起動の
        # セッションでは実際に注入された版より新しいことがある
        # fork の取り込み（adopt_fork_transcript）が transcript の版より優先しないよう、取り込み前の記録にだけ印を付ける
        pending = bool(state.get("fork_pending"))
        if "version" not in rec:
            rec["version"] = ver
            if pending:
                rec["version_from"] = "skill"
        # command だけの名前（SKILL.md が無い）は skills に入れない。入れると読み直す先の無い
        # skill として外され、プラグイン単位の判定まで止まる
        install_path = entry.get("installPath")
        if isinstance(install_path, str) and (Path(install_path) / "skills" / skill / "SKILL.md").is_file():
            skills = rec.setdefault("skills", {})
            if skill not in skills:
                skills[skill] = ver
                if pending:
                    rec.setdefault("skills_from_skill", []).append(skill)
        return True
    return False


def adopt_fork_transcript(payload: dict, state: dict) -> bool:
    """fork したセッションの transcript に写った親の会話から、親が読んだ版を記録する（GitHub issue #487）.

    SessionStart の入力に親の session_id は無いので、親の状態ファイルは引けない。fork 先の transcript
    には親の会話が写っているが、SessionStart と最初の UserPromptSubmit の時点ではまだ書かれていない
    （CC 2.1.328 の `claude -p --resume --fork-session` で実測）。そこで SessionStart(fork) で
    `fork_pending` を立て、transcript が現れた hook（SessionStart の時点で既にあればその場）でここを 1 回通す。
    デスクトップアプリの fork は SessionStart(fork) を通らず、main が copied_transcript で見分けて
    fork_pending を立てる。
    拾うのは、プラグインのキャッシュのファイルへの Read と、Skill tool が注入した skill の
    `Base directory for this skill: <パス>` の行（パスに版が入っている）。同名の command の本文の注入には
    パスが残らないので拾えない（今の installed で埋めると、更新後に fork した回の旧版を新しい版と取り違えて黙る）。
    返り値は state を書き換えたか。transcript がまだ無ければ何もせず、次の hook で試し直す
    """
    if not state.get("fork_pending"):
        return False
    tp = payload.get("transcript_path")
    if not isinstance(tp, str) or not os.path.isfile(tp):
        return False
    found: dict = {}
    with open(tp, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            # json.loads は該当しうる行にだけかける（数十 MB の transcript を 5 秒の timeout に収める）
            if "/plugins/cache/" not in line or ('"tool_use"' not in line and SKILL_BASE not in line):  # mutation-ok: 速さのための前段。外しても後段の判定で同じ結果になる
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            for path in transcript_reads(entry):
                # 順に上書きするので、同じプラグインを何度か読んでいれば最後に読んだ版が残る
                record({"tool_name": "Read", "tool_input": {"file_path": path}}, {"plugins": found}, None)
    # fork した後に PostToolUse が記録した分は transcript の分より新しいので、そちらを勝たせる。
    # ただし Skill の記録の版は呼んだ時点の installed の値で、読み直した証拠ではないので、
    # transcript に版があればそちらを残す（plugin 単位の version も skill 単位も同じ）
    for key, rec in state["plugins"].items():
        base = found.setdefault(key, {})
        if "version" in rec and (rec.get("version_from") != "skill" or "version" not in base):
            base["version"] = rec["version"]
        from_skill = set(rec.get("skills_from_skill", []))
        skills = base.setdefault("skills", {})
        for name, ver in rec.get("skills", {}).items():
            if name not in from_skill or name not in skills:
                skills[name] = ver
        if not skills:
            del base["skills"]
    state["plugins"] = found
    del state["fork_pending"]
    return True


def copied_transcript(payload: dict) -> bool:
    """transcript が別のセッションから写されたものか（先頭の行の sessionId が自分のものでない）.

    デスクトップアプリの fork は、fork した時点で親の transcript を丸ごと新しいファイルへ写し（1 回で
    書き終わる。写した行の sessionId は親のまま）、最初の発言で CLI を `--resume=<fork 先の id>` で
    起動する（`--fork-session` は付かない）。SessionStart の source は fork にならず、fork 先には状態
    ファイルも無いので、ここで見分けて adopt_fork_transcript に回す（CC 2.1.330 のデスクトップアプリで
    実測。compaction の後の fork も、compaction の前の行まで写る / GitHub issue #517）
    """
    tp = payload.get("transcript_path")
    if not isinstance(tp, str) or not os.path.isfile(tp):
        return False
    with open(tp, encoding="utf-8", errors="replace") as fh:
        for _, line in zip(range(COPIED_HEAD_LINES), fh):
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict) and isinstance(entry.get("sessionId"), str):
                return entry["sessionId"] != payload.get("session_id")
    return False


def transcript_reads(entry: object) -> list[str]:
    """transcript の 1 行から、読んだファイルのパスを返す（assistant の Read と、Skill が注入した行）."""
    if not isinstance(entry, dict) or not isinstance(entry.get("message"), dict):
        return []
    content = entry["message"].get("content")
    if not isinstance(content, list):
        return []
    out = []
    if entry.get("type") == "assistant":
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Read":
                tin = block.get("input")
                if isinstance(tin, dict) and isinstance(tin.get("file_path"), str):
                    out.append(tin["file_path"])
    # 利用者の発言に同じ字面が引用されても拾わないよう、CC が注入した行（isMeta）の先頭だけを見る
    elif entry.get("type") == "user" and entry.get("isMeta") is True:
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                m = SKILL_BASE_RE.match(block["text"])
                if m:
                    out.append(f"{m.group(1)}/SKILL.md")
    return out


def semver(ver: str) -> tuple[int, int, int] | None:
    m = SEMVER_RE.match(ver)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def changelog_headings(install_path: str, old_versions: set[str]) -> list[str]:
    try:
        text = (Path(install_path) / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    seen: set[str] = set()
    parsed = [semver(v) for v in old_versions]
    oldest = min(parsed) if parsed and None not in parsed else None
    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if not m:
            continue
        ver = m.group(1)
        # 古さを比べられない（semver でない旧版がある）ときだけ、並び順に頼って旧版の見出しで止める
        if ver in old_versions:
            seen.add(ver)
            if oldest is None and seen >= old_versions:
                break
        # Unreleased や版ラベルのままの見出しは、入っている版の変更ではない
        if not SEMVER_RE.match(ver):
            continue
        # 並び順に頼らず、一番古い旧版より新しい見出しを全部拾う。backport を時系列の位置に挟んだ
        # CHANGELOG では、旧版以下の見出しの下にも新しい見出しがある（GitHub issue #464）。
        # 旧版が複数ある（skill ごとに読んだ版が違う）ときは、新しい方の旧版の見出しも出す
        # （古い版で読んだ skill から見れば新しい変更）
        if oldest is not None and semver(ver) <= oldest:
            continue
        out.append(line.strip())
        if len(out) >= CHANGELOG_LIMIT:
            break
    return out


def build_notices(state: dict, installed: dict) -> list[str]:
    lines: list[str] = []
    notified = state["notified"]
    for key, rec in sorted(state["plugins"].items()):
        if not isinstance(rec, dict) or key not in installed:
            continue
        entries = installed[key]
        versions = {e["version"] for e in entries}
        entry = pick_entry(entries)
        new_ver = entry["version"]
        if notified.get(key) == new_ver:
            continue
        install_path = entry.get("installPath")
        if not isinstance(install_path, str):
            continue
        plugin = key.split("@", 1)[0]
        skills = rec.get("skills") if isinstance(rec.get("skills"), dict) else {}
        stale = {}
        for s, v in sorted(skills.items()):
            if v in versions:
                continue
            # 新しい版でその skill が消えていれば、読み直す先が無い
            if (Path(install_path) / "skills" / s / "SKILL.md").is_file():
                stale[s] = v
        if stale:
            old = set(stale.values())
            body = [
                f"  - {plugin}:{s} → {install_path}/skills/{s}/SKILL.md" for s in stale
            ]
        else:
            # skill 単位で古いものが無くても、Read で読んだ旧版のファイル（references など）が残っていれば知らせる
            v = rec.get("version")
            if not isinstance(v, str) or not v or v in versions:
                continue
            old = {v}
            body = [f"  - {install_path}/skills/ の、使う skill の SKILL.md"]
        lines.append(f"- {plugin}: {', '.join(sorted(old))} → {new_ver}")
        lines.extend(body)
        headings = changelog_headings(install_path, old)
        if headings:
            lines.append("  更新内容（CHANGELOG の見出し）:")
            lines.extend(f"    {h}" for h in headings)
        notified[key] = new_ver
    if not lines:
        return []
    return [
        "[plugin-manager] このセッションで読んだ skill より新しい版のプラグインが入った。"
        "次にその skill を使う前に、下の SKILL.md（新しい版）を Read し直してから続ける。",
        *lines,
        GUIDE,
    ]


def notify(payload: dict, mode: str, path: Path, state: dict) -> None:
    # 発言のたびに更新し、Read の無い日が続く常設のセッションの記録を 14 日の掃除で消さない
    os.utime(path)
    rearm = mode == "compact"
    if mode == "session-start":
        source = payload.get("source")
        if source == "compact":
            rearm = True
        elif source not in ("resume", "fork"):
            return
    changed = adopt_fork_transcript(payload, state)
    if changed and not state["plugins"]:
        # 前段（stale-skill.sh）は状態ファイルがあれば python を起動するので、記録の無いファイルを残さない
        # （写された transcript の経路だけは main が残し直す。理由はそちら）
        path.unlink(missing_ok=True)
        return
    now = int(time.time())
    if rearm:
        last = state.get("rearm_at")
        if not isinstance(last, int) or now - last > REARM_WINDOW:
            state["notified"] = {}
            state["rearm_at"] = now
            changed = True
    installed = load_installed()
    if installed is None:
        if changed:
            save_state(path, state)
        return
    out = build_notices(state, installed)
    if out or changed:
        save_state(path, state)
    if out:
        print("\n".join(out))


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else ""  # mutation-ok: stale-skill.sh は既知の mode だけを "$MODE" で 1 個渡すので argv は常に 2 要素
    try:
        payload = json.loads(sys.stdin.read())
    except ValueError:
        print("[plugin-manager:stale-skill] stdin is not JSON", file=sys.stderr)
        return 0
    if not isinstance(payload, dict):
        return 0
    path = state_path(payload.get("session_id"))
    if path is None:
        return 0
    try:
        if mode == "record":
            fd = lock(path)
            try:
                state = load_state(path) or new_state(payload["session_id"])
                installed = load_installed() if payload.get("tool_name") == "Skill" else None
                if record(payload, state, installed):
                    save_state(path, state)
            finally:
                os.close(fd)
        elif (forked := mode == "session-start" and payload.get("source") == "fork") or (
            (mode == "prompt" or (mode == "session-start" and payload.get("source") == "resume"))
            and not path.exists()
            and copied_transcript(payload)
        ):
            # fork 先は session_id が新しく、状態ファイルがまだ無い。親の記録は adopt_fork_transcript が拾う
            fd = lock(path)
            try:
                state = load_state(path) or new_state(payload["session_id"])
                state["fork_pending"] = True
                save_state(path, state)
                notify(payload, mode, path, state)
                # 写された transcript から親の Read が 1 件も出なくても、記録の無い状態ファイルを残す。
                # 消すと前段は次の発言でもまた写された transcript と判定し、そのたびに transcript を
                # 最後まで読み直す。残せば次からは取り込み済みの経路を通る
                if not forked and not path.exists():
                    save_state(path, state)
            finally:
                os.close(fd)
        elif mode in ("prompt", "compact", "session-start") and path.exists():
            fd = lock(path)
            try:
                state = load_state(path)
                if state is not None:
                    notify(payload, mode, path, state)
            finally:
                os.close(fd)
    except Exception as exc:  # hook の失敗でセッションを止めない
        print(f"[plugin-manager:stale-skill] {type(exc).__name__}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
