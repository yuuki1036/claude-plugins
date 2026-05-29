#!/usr/bin/env bash
# post-format-lint.sh — PostToolUse hook (Edit|Write|MultiEdit)
# opt-in: .claude/dev-workflow.json の lint.enabled=true の時のみ動作（未設定は完全 dormant）
#
# 3 段チェーン: fmt-fix → lint-fix → check
#   - fmt / lint 段は黙って直す（出力は捨てる）
#   - check 段で残った違反だけを block として Claude に返す
# 言語別コマンドは .claude/dev-workflow.json の lint.languages で定義（references/lint-config.md 参照）。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "dev-workflow:post-format-lint"
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/path-guard.sh"
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/json-block.sh"

CONFIG=".claude/dev-workflow.json"

# --- dormant 判定（opt-in。設定が無ければ即終了） ---
[[ -f "$CONFIG" ]] || safe_hook_error NotFound "lint config absent (dormant)"
command -v jq &>/dev/null || safe_hook_error Dependency "jq required for post-format-lint"
[[ "$(jq -r '.lint.enabled // false' "$CONFIG" 2>/dev/null)" == "true" ]] \
  || safe_hook_error Validation "lint disabled"

# --- 対象ファイル特定 ---
INPUT=$(safe_hook_input)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)

case "$TOOL_NAME" in
  Edit|Write|MultiEdit) ;;
  *) safe_hook_error Validation "not an edit tool: $TOOL_NAME" ;;
esac

[[ -z "$FILE_PATH" ]] && safe_hook_error Validation "empty file_path"
[[ -f "$FILE_PATH" ]] || safe_hook_error Validation "file not found: $FILE_PATH"
path_guard_is_excluded "$FILE_PATH" && safe_hook_error Validation "excluded path: $FILE_PATH"

# --- 言語判定（拡張子 → lint.languages のキー） ---
EXT=$(path_guard_ext "$FILE_PATH")
[[ -z "$EXT" ]] && safe_hook_error Validation "no extension: $FILE_PATH"

LINT_LANG=$(jq -r --arg e "$EXT" '
  (.lint.languages // {})
  | to_entries[]
  | select((.value.extensions // []) | index($e))
  | .key' "$CONFIG" 2>/dev/null | head -1)
[[ -z "$LINT_LANG" ]] && safe_hook_error Validation "no lint language for .$EXT"

# 言語別 on/off（個別無効化を許容）
# jq の `//` は false も空扱いするため `!= false` で判定（enabled 未指定=null は有効、明示 false のみ無効）
[[ "$(jq -r --arg l "$LINT_LANG" '(.lint.languages[$l].enabled) != false' "$CONFIG")" == "true" ]] \
  || safe_hook_error Validation "lint disabled for $LINT_LANG"

FMT_CMD=$(jq -r --arg l "$LINT_LANG" '.lint.languages[$l].fmt // ""' "$CONFIG")
LINT_CMD=$(jq -r --arg l "$LINT_LANG" '.lint.languages[$l].lint // ""' "$CONFIG")
CHECK_CMD=$(jq -r --arg l "$LINT_LANG" '.lint.languages[$l].check // ""' "$CONFIG")

# --- 3 段チェーン実行 ---
# 各コマンドは `|| ...` リストに入れて errexit / ERR trap の両方から免除する
# （set +e だけでは ERR trap が依然 fire するため不可）
[[ -n "$FMT_CMD" ]]  && { eval "$FMT_CMD \"$FILE_PATH\""  >/dev/null 2>&1 || true; }  # fmt-fix（黙って直す）
[[ -n "$LINT_CMD" ]] && { eval "$LINT_CMD \"$FILE_PATH\"" >/dev/null 2>&1 || true; }  # lint-fix（黙って直す）

CHECK_OUT=""
CHECK_RC=0
if [[ -n "$CHECK_CMD" ]]; then
  CHECK_OUT=$(eval "$CHECK_CMD \"$FILE_PATH\"" 2>&1) || CHECK_RC=$?
fi

# --- check 段で残った違反のみ block ---
if [[ "$CHECK_RC" -ne 0 ]]; then
  TOTAL=$(printf '%s\n' "$CHECK_OUT" | wc -l | tr -d ' ')
  HEAD=$(printf '%s\n' "$CHECK_OUT" | head -20 || true)
  REASON="[post-format-lint] ${FILE_PATH} の check (${LINT_LANG}) で違反が残っています:
${HEAD}"
  [[ "$TOTAL" -gt 20 ]] && REASON="${REASON}
… (全 ${TOTAL} 行中 先頭 20 行を表示)"
  emit_block_json "$REASON" "PostToolUse" "lint check failed for ${FILE_PATH}"
  exit 0
fi

# fmt/lint で自動修正済み・check 通過 → silent exit 0
