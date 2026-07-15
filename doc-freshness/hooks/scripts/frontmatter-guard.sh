#!/usr/bin/env bash
# frontmatter-guard.sh — PostToolUse hook (Edit|Write|MultiEdit)
# frontmatter 必須の project doc（.claude/designs/ ・ .claude/adr/ 等）に .md を
# 作成/編集した際、last-validated / phase frontmatter の欠落を非ブロッキングで警告する。
#
# 設計方針（issue #79 / CLAUDE.md「ルール配置の意思決定」）:
#   - 決定的検証（frontmatter キーの存在は grep で書ける）を Hook に置き遵守率 100% に寄せる
#   - 昇格するのは「frontmatter 欠落」のみ。stale 判定の閾値運用は既存 skill 側に残す
#   - ブロックはしない（PostToolUse は編集を巻き戻さない。警告注入のみ）
#   - 対象は frontmatter が必須の project doc に限定する。プラグイン内部 doc
#     （SKILL.md / references/ / README）は CLAUDE.md 規約で frontmatter 対象外なので含めない

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "doc-freshness:frontmatter-guard"

INPUT=$(safe_hook_input)

# tool_name と file_path を抽出（jq 優先、無ければ grep フォールバック）
if command -v jq >/dev/null 2>&1; then
  TOOL_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
  FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
else
  TOOL_NAME=$(printf '%s' "$INPUT" | grep -oE '"tool_name"[[:space:]]*:[[:space:]]*"[^"]+"' | sed 's/.*"\([^"]*\)"$/\1/' | head -1 || true)
  FILE_PATH=$(printf '%s' "$INPUT" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]+"' | sed 's/.*"\([^"]*\)"$/\1/' | head -1 || true)
fi

case "$TOOL_NAME" in
  Edit|Write|MultiEdit) ;;
  *) safe_hook_error Validation "not an edit tool: $TOOL_NAME" ;;
esac

[ -z "$FILE_PATH" ] && safe_hook_error Validation "empty file_path"
case "$FILE_PATH" in
  *.md) ;;
  *) safe_hook_error Validation "not a markdown file: $FILE_PATH" ;;
esac

# project-relative なパスに正規化（絶対パスなら project root prefix を除去）
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
REL_PATH="$FILE_PATH"
case "$FILE_PATH" in
  "$PROJECT_DIR"/*) REL_PATH="${FILE_PATH#"$PROJECT_DIR"/}" ;;
  /*) safe_hook_error Validation "outside project: $FILE_PATH" ;;
esac

# 設定ロード（.claude/doc-freshness.json）。無ければデフォルト。
# postToolUseCheck: false で本 hook を無効化。hookTargets で対象 prefix を上書き。
CONFIG="${PROJECT_DIR}/.claude/doc-freshness.json"
DEFAULT_TARGETS=".claude/designs/ .claude/adr/ .claude/living-specs/"
TARGETS="$DEFAULT_TARGETS"
if [ -f "$CONFIG" ] && command -v jq >/dev/null 2>&1; then
  if [ "$(jq -r '.postToolUseCheck // true' "$CONFIG" 2>/dev/null)" = "false" ]; then
    safe_hook_error Validation "postToolUseCheck disabled by config"
  fi
  CUSTOM=$(jq -r '.hookTargets[]? // empty' "$CONFIG" 2>/dev/null | tr '\n' ' ' || true)
  [ -n "$CUSTOM" ] && TARGETS="$CUSTOM"
fi

# 対象 prefix 配下か判定（そうでなければ no-op）
in_target=0
for t in $TARGETS; do
  case "$REL_PATH" in
    "$t"*) in_target=1; break ;;
  esac
done
[ "$in_target" -eq 0 ] && safe_hook_error Validation "not under a frontmatter-required target: $REL_PATH"

# 対象ファイルが実在するか（PostToolUse は書き込み後なので通常は存在する）
ABS_PATH="$FILE_PATH"
case "$FILE_PATH" in
  /*) ABS_PATH="$FILE_PATH" ;;
  *) ABS_PATH="${PROJECT_DIR}/${FILE_PATH}" ;;
esac
[ -f "$ABS_PATH" ] && [ -r "$ABS_PATH" ] || safe_hook_error NotFound "file not readable: $ABS_PATH"

# frontmatter の存在と last-validated / phase キーを確認する（決定的検証）
missing=""
first_line=$(head -1 "$ABS_PATH" 2>/dev/null || true)
if [ "$first_line" != "---" ]; then
  missing="frontmatter ブロック（先頭 --- が無い）"
else
  # 先頭 --- から次の --- までを frontmatter として抽出
  fm=$(awk 'NR==1{next} /^---[[:space:]]*$/{exit} {print}' "$ABS_PATH" 2>/dev/null || true)
  echo "$fm" | grep -qE '^last-validated:' || missing="${missing}${missing:+, }last-validated"
  echo "$fm" | grep -qE '^phase:' || missing="${missing}${missing:+, }phase"
fi

# 欠落なしなら silent exit
[ -z "$missing" ] && safe_hook_error Validation "frontmatter present"

BASENAME=$(basename "$FILE_PATH")
safe_hook_emit_context "PostToolUse" "[doc-freshness] ${BASENAME}（${REL_PATH}）に doc 鮮度 frontmatter が不足しています: ${missing}。frontmatter 必須の project doc です。冒頭に次を追加してください:
---
last-validated: $(date +%Y-%m-%d)
phase: current   # current | target | superseded
---
（詳細な閾値・免除ルールは /doc-freshness-check または doc-freshness skill の references を参照。この警告はブロックしません）"
