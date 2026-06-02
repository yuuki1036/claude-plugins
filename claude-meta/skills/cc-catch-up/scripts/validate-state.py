#!/usr/bin/env python3
"""cc-catch-up state.json の決定的バリデータ.

references/state-schema.json を single source として読み込み, state.json が
それに準拠しているかを標準ライブラリのみで検証する（外部 jsonschema 非依存）.
Phase 7 で state.json を書き換えた直後に実行し, schema drift を機械的に弾く.

サポートする JSON Schema(draft-07) サブセット:
  type / required / properties / additionalProperties /
  items / enum / pattern / minLength / anyOf

実行: python3 validate-state.py [state.json] [--schema state-schema.json]
  引数無し: スクリプトからの相対パスで state.json / references/state-schema.json を解決
Exit code: 0 (valid) / 1 (違反) / 2 (ファイル不在・JSON 構文エラー)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
DEFAULT_STATE = SKILL_DIR / "state.json"
DEFAULT_SCHEMA = SKILL_DIR / "references" / "state-schema.json"

JSON_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "null": type(None),
}


def _type_ok(value: object, t: str) -> bool:
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    py = JSON_TYPES.get(t)
    return isinstance(value, py) if py is not None else True


def validate(value: object, schema: dict, path: str, errors: list[str]) -> None:
    if "anyOf" in schema:
        branch_errs: list[list[str]] = []
        for sub in schema["anyOf"]:
            local: list[str] = []
            validate(value, sub, path, local)
            if not local:
                break
            branch_errs.append(local)
        else:
            errors.append(f"{path}: anyOf のどの候補にも適合しない ({len(branch_errs)} 候補すべて不適合)")
        return

    t = schema.get("type")
    types = [t] if isinstance(t, str) else (t or [])
    if types and not any(_type_ok(value, one) for one in types):
        errors.append(f"{path}: 型不一致 (expected {types}, got {type(value).__name__})")
        return

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: enum 外の値 {value!r} (allowed: {schema['enum']})")

    if isinstance(value, str):
        pat = schema.get("pattern")
        if pat and not re.search(pat, value):
            errors.append(f"{path}: pattern 不一致 {value!r} (pattern: {pat})")
        ml = schema.get("minLength")
        if ml is not None and len(value) < ml:
            errors.append(f"{path}: minLength {ml} 未満 ({len(value)})")

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: 必須キー '{key}' が欠落")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append(f"{path}: 未知のキー '{key}' (additionalProperties: false)")
        for key, sub in props.items():
            if key in value:
                validate(value[key], sub, f"{path}.{key}", errors)

    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            validate(item, schema["items"], f"{path}[{i}]", errors)


def load_json(p: Path) -> object:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[validate-state] ファイルが見つからない: {p}", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"[validate-state] JSON 構文エラー: {p}: {e}", file=sys.stderr)
        sys.exit(2)


def main(argv: list[str]) -> int:
    state_path = DEFAULT_STATE
    schema_path = DEFAULT_SCHEMA
    rest = []
    i = 0
    while i < len(argv):
        if argv[i] == "--schema":
            schema_path = Path(argv[i + 1])
            i += 2
        else:
            rest.append(argv[i])
            i += 1
    if rest:
        state_path = Path(rest[0])

    schema = load_json(schema_path)
    state = load_json(state_path)
    if not isinstance(schema, dict):
        print(f"[validate-state] schema がオブジェクトでない: {schema_path}", file=sys.stderr)
        return 2

    errors: list[str] = []
    validate(state, schema, "state", errors)

    if errors:
        print(f"[validate-state] {state_path} は state-schema.json に違反:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(f"  total: {len(errors)} issue(s)", file=sys.stderr)
        return 1

    print(f"[validate-state] OK: {state_path} は state-schema.json に準拠")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
