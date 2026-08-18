#!/usr/bin/env bash
# validate-ssot.sh — plugin.json を SSoT として派生物との整合性を検証する
#
# 検証内容:
#   1. plugin.json / marketplace.json / hooks.json のスキーマ準拠
#   2. marketplace.json の plugins[*] と各 plugin.json の name/version/description 一致
#   3. plugin.json の _requirements と hooks/scripts/check-deps.sh の登場名一致
#
# 実行: bash .claude-plugin/scripts/validate-ssot.sh
# Exit: 0 (pass) / 1 (違反あり) / 2 (判定不能: python3 や jsonschema が無く検査できなかった)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 が必要" >&2
  exit 2
fi

exec python3 "$ROOT/.claude-plugin/scripts/validate_ssot.py" "$@"
