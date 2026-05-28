#!/usr/bin/env bash
# pre-config-guard.sh
#
# Edit/Write/MultiEdit ツールで lint/hook/static check 設定ファイルへの
# 編集を試みた場合、basename がプロジェクト設定の protected_basenames に
# 含まれていれば exit 2 でブロックする。
#
# 設定: <project>/.claude/guardrail-protect.json
#   {
#     "protected_basenames": [
#       ".golangci.yml",
#       "lefthook.yml",
#       ".eslintrc.json"
#     ]
#   }
#
# protected_basenames が未設定（または空配列）なら no-op。
# デフォルトでは保護対象ゼロ＝誤爆なし。プロジェクト側が opt-in で宣言する。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "guardrail-protect:pre-config-guard"

command -v jq >/dev/null 2>&1 || safe_hook_error Dependency "jq not installed"

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
CONFIG_FILE="${PROJECT_DIR}/.claude/guardrail-protect.json"

[ -f "$CONFIG_FILE" ] || safe_hook_error NotFound "no project config: $CONFIG_FILE"

input=$(safe_hook_input)
tool_name=$(jq -r '.tool_name // empty' <<< "$input")
target_path=$(jq -r '.tool_input.file_path // empty' <<< "$input")

[ -z "$target_path" ] && safe_hook_error Validation "no file_path in tool_input"

target_basename=$(basename "$target_path")

protected_basenames=$(jq -r '.protected_basenames[]? // empty' "$CONFIG_FILE" 2>/dev/null)
[ -z "$protected_basenames" ] && exit 0

if grep -Fxq "$target_basename" <<< "$protected_basenames"; then
  cat >&2 <<EOF
[guardrail-protect] Refusing to edit guardrail config file: $target_basename

This file is protected because it defines lint / hook / static check rules.
Weakening guardrails (rule removal, severity downgrade, scope reduction, block-judgement reversal)
is forbidden by the project's "no weakening" meta-rule.

If you genuinely need to change this file:
  1. Justify the change in commit body (specify WHY existing rules block the change)
  2. Remove the basename from .claude/guardrail-protect.json temporarily
  3. Restore protection after the change is committed

Tool: $tool_name
Path: $target_path
Config: $CONFIG_FILE
EOF
  exit 2
fi

exit 0
