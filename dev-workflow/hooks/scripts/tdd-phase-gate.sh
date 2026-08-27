#!/usr/bin/env bash
# tdd-phase-gate.sh — PreToolUse hook (Edit|Write|MultiEdit)
# opt-in: .claude/.tdd-phase-gate-enabled が存在する時のみ動作
# 実装ファイルを編集しようとしたが対応テストファイルが存在しない場合に Red phase 逸脱を警告
# ブロックはせず reminder を注入するのみ（false positive を許容）

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "dev-workflow:tdd-phase-gate"

STATE_DIR=".claude"
ENABLED_FLAG="${STATE_DIR}/.tdd-phase-gate-enabled"

[[ ! -f "$ENABLED_FLAG" ]] && safe_hook_error NotFound "tdd-phase-gate not enabled"

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

# 実装ファイル拡張子（テスト対象となりうる言語）
if ! echo "$FILE_PATH" | grep -qiE '\.(ts|tsx|js|jsx|mjs|mts|cjs|cts|py|go|rb|vue|svelte)$'; then
  safe_hook_error Validation "not a source file: $FILE_PATH"
fi

BASENAME=$(basename "$FILE_PATH")
DIRNAME=$(dirname "$FILE_PATH")

# テストファイル自身・設定ファイル・型定義は除外
case "$BASENAME" in
  *.test.*|*.spec.*|test_*|*.d.ts|*.config.*|vite.config.*|vitest.config.*|jest.config.*|playwright.config.*|next.config.*|tailwind.config.*|*.stories.*)
    safe_hook_error Validation "test/config/story file: $BASENAME"
    ;;
esac

# __tests__ / tests / test ディレクトリ配下は対象外
case "$FILE_PATH" in
  */__tests__/*|*/tests/*|*/test/*|*/__mocks__/*)
    safe_hook_error Validation "test dir: $FILE_PATH"
    ;;
esac

# base 名と拡張子を分離
STEM="${BASENAME%.*}"
EXT="${BASENAME##*.}"

# 対応テストファイルの候補。**場所 × 命名の直積で作る**（GitHub issue #180）:
# 以前は手書きの 9 通りで直積になっておらず、`tests/` 配下は `.test.` と `test_` しか
# 探していなかった。そのため **`tests/foo.spec.ts` 構成のプロジェクトはテストが実在しても
# 常に警告**が出ていた（README は直積を宣言しており、実装だけが狭かった）。
# 恒常的な誤警告は「⚠️ が出たときだけ行動する」契約を壊す（docs/rule-placement.md）
TEST_CANDIDATES=()
for _dir in "${DIRNAME}" "${DIRNAME}/__tests__" "${DIRNAME}/tests"; do
  TEST_CANDIDATES+=(
    "${_dir}/${STEM}.test.${EXT}"
    "${_dir}/${STEM}.spec.${EXT}"
    "${_dir}/test_${STEM}.${EXT}"
    "${_dir}/${STEM}_test.${EXT}"
  )
done
# ミラー配置（テスト用ディレクトリに同名で置く流儀）
TEST_CANDIDATES+=(
  "${DIRNAME}/__tests__/${BASENAME}"
  "${DIRNAME}/tests/${BASENAME}"
)

for candidate in "${TEST_CANDIDATES[@]}"; do
  if [[ -f "$candidate" ]]; then
    safe_hook_error Validation "test exists: $candidate"
  fi
done

# 新規作成の場合（Write で file_path がまだ存在しない）は Red phase として許容
# テストが書かれる前の空の実装ファイル作成は正常フローに含まれるため
if [[ ! -f "$FILE_PATH" ]] && [[ "$TOOL_NAME" == "Write" ]]; then
  safe_hook_error Validation "new file write: $FILE_PATH"
fi

# ここまで来たら: 既存の実装ファイルをテスト無しで編集しようとしている → 警告
# PreToolUse の plain stdout は到達保証が弱いため additionalContext で注入する（push-reminder.sh と同方式）
safe_hook_emit_context "PreToolUse" "[tdd-phase-gate] ${BASENAME} に対応するテストファイルが見つかりません。Red phase として先にテストを書くか、既存テストの位置を確認してください。（hook を止める: rm ${ENABLED_FLAG}）"
