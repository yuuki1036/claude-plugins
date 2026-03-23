#!/usr/bin/env bash
# inject-rules.sh — SessionStart hook
# .claude/linear/ ディレクトリが存在するプロジェクトでのみ
# プロジェクト管理ルールを Claude のコンテキストに注入する

set -euo pipefail

# stdin から hook 入力を読む（消費する必要がある）
cat > /dev/null

# .claude/linear/ が存在しない場合は何も出力しない
if [ ! -d ".claude/linear" ]; then
  exit 0
fi

# ルールファイルを出力（stdout が Claude のコンテキストに入る）
RULES_DIR="${CLAUDE_PLUGIN_ROOT}/rules"
if [ -f "${RULES_DIR}/project-rules.md" ]; then
  cat "${RULES_DIR}/project-rules.md"
fi
if [ -f "${RULES_DIR}/issue-create-interaction.md" ]; then
  echo ""
  cat "${RULES_DIR}/issue-create-interaction.md"
fi
