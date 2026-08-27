#!/usr/bin/env bash
# check-scope-size.sh — PostToolUse hook (Edit|Write|MultiEdit)
# .claude/{indie,linear}/*/issues/*.md のチェックリスト数が scope_size 上限を超えたら警告
# （対象節は `## 進捗` と `## 完了条件` の両方 — テンプレ系統が 2 つあるため）
# 上限: small:3 / medium:7 / large:15（Issue #30 参照）
# issue-maintain の膨張閾値（5/8/16）とは別物で、こちらはリアルタイム初動警告

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "issue-workflow:check-scope-size"

INPUT=$(safe_hook_input)

if command -v jq &>/dev/null; then
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
else
  TOOL_NAME=$(echo "$INPUT" | grep -oE '"tool_name"[[:space:]]*:[[:space:]]*"[^"]+"' | sed 's/.*"\([^"]*\)"$/\1/' | head -1 || true)
  FILE_PATH=$(echo "$INPUT" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]+"' | sed 's/.*"\([^"]*\)"$/\1/' | head -1 || true)
fi

case "$TOOL_NAME" in
  Edit|Write|MultiEdit) ;;
  *) safe_hook_error Validation "not an edit tool: $TOOL_NAME" ;;
esac

[[ -z "$FILE_PATH" ]] && safe_hook_error Validation "empty file_path"

# .claude/{indie,linear}/*/issues/*.md にマッチするか（相対/絶対どちらでも）
if ! echo "$FILE_PATH" | grep -qE '\.claude/(indie|linear)/[^/]+/issues/[^/]+\.md$'; then
  safe_hook_error Validation "not an issue file: $FILE_PATH"
fi

[[ ! -f "$FILE_PATH" ]] && safe_hook_error NotFound "issue file missing: $FILE_PATH"

# frontmatter から scope_size と id を抽出
SCOPE_SIZE=$(awk '/^---$/{c++; next} c==1 && /^scope_size:/ {sub(/^scope_size:[[:space:]]*/, ""); print; exit}' "$FILE_PATH")
ISSUE_ID=$(awk '/^---$/{c++; next} c==1 && /^id:/ {sub(/^id:[[:space:]]*/, ""); print; exit}' "$FILE_PATH")
[ -n "$ISSUE_ID" ] || ISSUE_ID=$(awk '/^---$/{c++; next} c==1 && /^linear:/ {sub(/^linear:[[:space:]]*/, ""); print; exit}' "$FILE_PATH")

[[ -z "$SCOPE_SIZE" ]] && safe_hook_error Validation "scope_size not found"

case "$SCOPE_SIZE" in
  small)  LIMIT=3 ;;
  medium) LIMIT=7 ;;
  large)  LIMIT=15 ;;
  *) safe_hook_error Validation "unknown scope_size: $SCOPE_SIZE" ;;
esac

# チェックリスト行数をカウントする。
#
# **テンプレ系統が 2 つある**（GitHub issue #179）: issue-create の型別テンプレは
# `## 進捗`、issue-design の 9 セクションテンプレは `## 完了条件` にチェックリストを置く。
# `## 進捗` だけを数えていたため、**`/issue-design` でリライトした Issue では COUNT=0 に
# なり警告が無言で無効化**されていた（skills/issue-create/SKILL.md は「スコープサイズは
# 全 type で必須」と宣言しており、宣言と実装が食い違っていた）。
#
# 両方あるときは `## 進捗` を優先する（**足し合わせない** — 同じタスクが両節に現れる
# 移行途中のファイルで二重に数えると、上限超過を誤って警告する）
COUNT=$(awk '
  /^## 進捗[[:space:]]*$/     { sec="p"; next }
  /^## 完了条件[[:space:]]*$/ { sec="d"; next }
  /^## /                      { sec="";  next }
  sec != "" && /^[[:space:]]*-[[:space:]]*\[[[:space:]xX]\]/ { n[sec]++ }
  END { print (n["p"] > 0 ? n["p"] : n["d"]) + 0 }
' "$FILE_PATH")

if [[ "$COUNT" -le "$LIMIT" ]]; then
  safe_hook_error Validation "within limit: $COUNT <= $LIMIT ($SCOPE_SIZE)"
fi

# 警告注入（Issue ID 付きで文脈を残す）
safe_hook_emit_context "PostToolUse" "[scope-size] ${ISSUE_ID:-$(basename "$FILE_PATH")}: タスク ${COUNT} 件が scope_size=${SCOPE_SIZE} の上限 ${LIMIT} を超過しました。別 Issue 切り出しか scope_size 引き上げを検討してください（/issue-maintain で整理可能）。"
