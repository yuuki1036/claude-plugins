#!/usr/bin/env python3
"""plugin.json SSoT 検証.

plugin.json を SSoT として、marketplace.json / check-deps.sh / hooks.json との整合性を検証する.

検証内容:
  1. スキーマ準拠 (jsonschema が無い環境では最小限の構造チェックに fallback)
  2. marketplace.json の plugins[*] と各 plugin.json の name/version/description 一致
  3. plugin.json の _requirements と hooks/scripts/check-deps.sh の登場名一致
  4. source ディレクトリと plugin.json の存在一致
  5. INDEX.md / CLAUDE.md のプラグイン記載が plugin.json と整合
     (INDEX.md は一覧表の version 列・記載漏れ・余分行、CLAUDE.md は一覧表への記載漏れ)

Exit code: 0 (pass) / 1 (違反あり) / 2 (実行環境エラー)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / ".claude-plugin" / "schema"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


_SCHEMA_SKIP_WARNED = False


def try_validate_schema(instance: dict, schema_name: str, errors: list[str], label: str) -> None:
    """jsonschema ライブラリがあれば利用、無ければスキップ (構造チェックで代替)."""
    global _SCHEMA_SKIP_WARNED
    try:
        import jsonschema  # type: ignore
    except ImportError:
        # silent skip にすると「ローカルでは落ちるが CI では通る」逆転に気づけない
        if not _SCHEMA_SKIP_WARNED:
            print(
                "warning: jsonschema が無いためスキーマ検証を skip（pip install jsonschema）",
                file=sys.stderr,
            )
            _SCHEMA_SKIP_WARNED = True
        return
    schema_path = SCHEMA_DIR / schema_name
    if not schema_path.exists():
        errors.append(f"[{label}] schema not found: {schema_path}")
        return
    schema = load_json(schema_path)
    validator = jsonschema.Draft7Validator(schema)
    for err in validator.iter_errors(instance):
        path = ".".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"[{label}] schema: {path}: {err.message}")


def collect_plugin_manifests() -> dict[str, dict]:
    """{plugin_name: manifest} を返す. ディレクトリ名と manifest.name の不一致もチェックする."""
    manifests: dict[str, dict] = {}
    for plugin_json in sorted(ROOT.glob("*/.claude-plugin/plugin.json")):
        plugin_dir = plugin_json.parts[-3]
        data = load_json(plugin_json)
        data["__path"] = str(plugin_json.relative_to(ROOT))
        data["__dir"] = plugin_dir
        manifests[plugin_dir] = data
    return manifests


SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def structural_check_plugin(manifest: dict, errors: list[str]) -> None:
    label = f"plugin:{manifest['__dir']}"
    for key in ("name", "version", "description", "author"):
        if key not in manifest:
            errors.append(f"[{label}] missing required key: {key}")
    name = manifest.get("name")
    if name and not NAME_RE.match(name):
        errors.append(f"[{label}] invalid name pattern: {name}")
    if name and name != manifest["__dir"]:
        errors.append(f"[{label}] name '{name}' does not match directory '{manifest['__dir']}'")
    version = manifest.get("version")
    if version and not SEMVER_RE.match(version):
        errors.append(f"[{label}] invalid version (expected semver): {version}")
    reqs = manifest.get("_requirements", [])
    if not isinstance(reqs, list):
        errors.append(f"[{label}] _requirements must be array")
        return
    for i, req in enumerate(reqs):
        for k in ("name", "type", "required", "description"):
            if k not in req:
                errors.append(f"[{label}] _requirements[{i}] missing: {k}")
        if "type" in req and req["type"] not in ("mcp_server", "cli_tool", "plugin"):
            errors.append(f"[{label}] _requirements[{i}] invalid type: {req['type']}")


def check_marketplace_sync(manifests: dict[str, dict], errors: list[str]) -> None:
    if not MARKETPLACE.exists():
        errors.append(f"[marketplace] not found: {MARKETPLACE}")
        return
    mp = load_json(MARKETPLACE)
    try_validate_schema(mp, "marketplace.schema.json", errors, "marketplace")
    entries = {p["name"]: p for p in mp.get("plugins", []) if isinstance(p, dict) and "name" in p}

    missing_in_mp = set(manifests) - set(entries)
    for name in sorted(missing_in_mp):
        errors.append(f"[marketplace] missing entry for plugin: {name}")

    orphan_in_mp = set(entries) - set(manifests)
    for name in sorted(orphan_in_mp):
        errors.append(f"[marketplace] orphan entry (no plugin dir): {name}")

    for name, entry in sorted(entries.items()):
        if name not in manifests:
            continue
        m = manifests[name]
        for field in ("version", "description"):
            mp_val = entry.get(field)
            pj_val = m.get(field)
            if mp_val != pj_val:
                errors.append(
                    f"[marketplace:{name}] {field} mismatch: marketplace='{mp_val}' plugin.json='{pj_val}'"
                )
        expected_source = f"./{name}"
        if entry.get("source") != expected_source:
            errors.append(
                f"[marketplace:{name}] source mismatch: expected='{expected_source}' actual='{entry.get('source')}'"
            )


def check_requirements_vs_check_deps(manifests: dict[str, dict], errors: list[str]) -> None:
    for name, m in manifests.items():
        reqs = m.get("_requirements", [])
        check_deps = ROOT / name / "hooks" / "scripts" / "check-deps.sh"
        has_hooks = (ROOT / name / "hooks").is_dir()
        # check-deps.sh は hook が呼び出す前提のスクリプト。hooks/ を持たないプラグインは
        # 任意依存（required:false 等）を _requirements に宣言しても check-deps.sh を必要としない
        # （未導入時は実行側でフォールバックする設計）。hooks/ がある場合のみ存在を必須にする。
        if reqs and not check_deps.exists():
            if has_hooks:
                errors.append(
                    f"[deps:{name}] _requirements declared but hooks/scripts/check-deps.sh missing"
                )
            continue
        if not reqs and check_deps.exists():
            text = check_deps.read_text(encoding="utf-8")
            if re.search(r"check_(mcp|cli|plugin)\s+", text):
                errors.append(
                    f"[deps:{name}] check-deps.sh calls check_* but plugin.json has no _requirements"
                )
            continue
        if not reqs:
            continue
        text = check_deps.read_text(encoding="utf-8")
        for req in reqs:
            req_name = req.get("name")
            if not req_name:
                continue
            pattern = rf'check_(mcp|cli|plugin)\s+"{re.escape(req_name)}"'
            if not re.search(pattern, text):
                errors.append(
                    f"[deps:{name}] requirement '{req_name}' not found in check-deps.sh "
                    f"(expected: check_xxx \"{req_name}\" ...)"
                )


def check_hooks_json(errors: list[str]) -> None:
    for hooks_json in sorted(ROOT.glob("*/hooks/hooks.json")):
        plugin = hooks_json.parts[-3]
        try:
            data = load_json(hooks_json)
        except json.JSONDecodeError as e:
            errors.append(f"[hooks:{plugin}] invalid JSON: {e}")
            continue
        try_validate_schema(data, "hooks.schema.json", errors, f"hooks:{plugin}")
        hooks = data.get("hooks")
        if not isinstance(hooks, dict):
            errors.append(f"[hooks:{plugin}] top-level 'hooks' must be object")
            continue
        for event, matchers in hooks.items():
            if not isinstance(matchers, list):
                errors.append(f"[hooks:{plugin}] {event}: must be array")
                continue
            for i, matcher in enumerate(matchers):
                if "hooks" not in matcher:
                    errors.append(f"[hooks:{plugin}] {event}[{i}]: missing 'hooks'")
                    continue
                for j, h in enumerate(matcher["hooks"]):
                    if h.get("type") == "command" and "command" not in h:
                        errors.append(
                            f"[hooks:{plugin}] {event}[{i}].hooks[{j}]: type=command requires 'command'"
                        )


def check_docs_sync(manifests: dict[str, dict], errors: list[str]) -> None:
    """INDEX.md / CLAUDE.md のプラグイン記載が plugin.json と整合するか検証する.

    ドキュメントは plugin.json から派生する情報（プラグイン一覧・version）を持つため、
    marketplace.json と同様に SSoT との同期を機械検証する。実装変更時のドキュメント
    追従漏れ（新規プラグインの一覧追記忘れ、version 列の陳腐化）を検出する。
    """
    plugin_names = set(manifests)

    # INDEX.md: 一覧表 `| [name](#name) | version | ...` の version 列を照合する
    index_path = ROOT / "INDEX.md"
    if index_path.exists():
        text = index_path.read_text(encoding="utf-8")
        found: dict[str, str] = {}
        row_re = re.compile(
            r"^\|\s*\[([a-z][a-z0-9-]*)\]\([^)]*\)\s*\|\s*(\d+\.\d+\.\d+)\s*\|",
            re.MULTILINE,
        )
        for mt in row_re.finditer(text):
            found[mt.group(1)] = mt.group(2)
        for name in sorted(plugin_names):
            if name not in found:
                errors.append(f"[docs:INDEX.md] plugin missing from 一覧表: {name}")
            elif found[name] != manifests[name].get("version"):
                errors.append(
                    f"[docs:INDEX.md] {name} version mismatch: "
                    f"INDEX='{found[name]}' plugin.json='{manifests[name].get('version')}'"
                )
        for name in sorted(set(found) - plugin_names):
            errors.append(f"[docs:INDEX.md] 一覧表 lists unknown plugin: {name}")

    # CLAUDE.md: 一覧表セル `| name |` の存在のみ照合する（version 列は持たない）
    claude_path = ROOT / "CLAUDE.md"
    if claude_path.exists():
        text = claude_path.read_text(encoding="utf-8")
        for name in sorted(plugin_names):
            cell_re = re.compile(rf"^\|\s*{re.escape(name)}\s*\|", re.MULTILINE)
            if not cell_re.search(text):
                errors.append(f"[docs:CLAUDE.md] plugin missing from 一覧表: {name}")


def main() -> int:
    errors: list[str] = []
    manifests = collect_plugin_manifests()
    if not manifests:
        print("ERROR: no plugin.json found", file=sys.stderr)
        return 2

    for m in manifests.values():
        structural_check_plugin(m, errors)
        try_validate_schema(
            {k: v for k, v in m.items() if not k.startswith("__")},
            "plugin.schema.json",
            errors,
            f"plugin:{m['__dir']}",
        )

    check_marketplace_sync(manifests, errors)
    check_requirements_vs_check_deps(manifests, errors)
    check_hooks_json(errors)
    check_docs_sync(manifests, errors)

    if errors:
        print("SSoT validation failed:", file=sys.stderr)
        print("", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print("", file=sys.stderr)
        print(f"  total: {len(errors)} issue(s)", file=sys.stderr)
        return 1

    print(f"SSoT validation passed ({len(manifests)} plugins)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
