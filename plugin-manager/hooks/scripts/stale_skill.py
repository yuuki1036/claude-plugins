#!/usr/bin/env python3
"""読んだ skill の版を記録し、新しい版が入ったら読み直すよう知らせる（GitHub issue #416）.

入口は stale-skill.sh（前段の判定はそちら）。stdin に hook の payload、argv[1] にモード。

- record: PostToolUse の Read / Skill から、このセッションが読んだ版を記録する。stdout には何も書かない
  （PostToolUse の stdout が漏れると、プラグインのファイルを Read するたびに注入される）
- prompt / compact / session-start: 記録とインストール済みの版を比べ、違うものを plain stdout で知らせる。
  同じ (プラグイン, 新しい版) は 1 回だけ。compaction の後は通知も消えているので、もう一度出す

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
HEADING_RE = re.compile(r"^## \[([^\]]+)\]")
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")
# compaction の後は SessionStart(compact) と PostCompact の両方が来る版がある。この秒数の中の 2 回目は
# 通知済みを消し直さない（消し直すと同じ通知が 2 回出る）
REARM_WINDOW = 120
CHANGELOG_LIMIT = 5
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
    path.parent.mkdir(parents=True, exist_ok=True)
    # stale-skill.sh の掃除はこの `.*.tmp` の形を前提に書きかけを消す
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
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
        sm = SKILL_RE.match(rest)
        if sm:
            rec.setdefault("skills", {})[sm.group(1)] = ver
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
        rec.setdefault("version", ver)
        # command だけの名前（SKILL.md が無い）は skills に入れない。入れると読み直す先の無い
        # skill として外され、プラグイン単位の判定まで止まる
        install_path = entry.get("installPath")
        if isinstance(install_path, str) and (Path(install_path) / "skills" / skill / "SKILL.md").is_file():
            rec.setdefault("skills", {}).setdefault(skill, ver)
        return True
    return False


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
        # 旧版が複数ある（skill ごとに読んだ版が違う）ときは、一番古い旧版の手前まで出す
        # （新しい方の旧版の見出しも、古い版で読んだ skill から見れば新しい変更）
        if ver in old_versions:
            seen.add(ver)
            if seen >= old_versions:
                break
        # Unreleased や版ラベルのままの見出しは、入っている版の変更ではない
        if not SEMVER_RE.match(ver):
            continue
        # 旧版の見出しが CHANGELOG に無い（版を飛ばして書いた）ときも、旧版より古い見出しは出さない
        cur = semver(ver)
        if oldest is not None and cur is not None and cur <= oldest:
            break
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
        elif source != "resume":
            return
    changed = False
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
    mode = argv[1] if len(argv) > 1 else ""
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
