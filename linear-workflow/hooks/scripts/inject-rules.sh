#!/usr/bin/env bash
# inject-rules.sh — SessionStart / PostCompact hook
# .claude/linear/ ディレクトリが存在するプロジェクトでのみ
# プロジェクト管理ルールと Knowledge インデックスを Claude のコンテキストに注入する

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "linear-workflow:inject-rules"

if [ ! -d ".claude/linear" ]; then
  safe_hook_error NotFound ".claude/linear directory missing"
fi

# ルールファイルを出力（stdout が Claude のコンテキストに入る）
RULES_DIR="${CLAUDE_PLUGIN_ROOT}/rules"
if [ -f "${RULES_DIR}/project-rules.md" ]; then
  cat "${RULES_DIR}/project-rules.md"
fi

# Knowledge インデックス注入
for index_file in .claude/linear/*/knowledge/index.md; do
  [ -f "$index_file" ] || continue
  slug=$(echo "$index_file" | sed 's|.claude/linear/\(.*\)/knowledge/index.md|\1|')
  echo ""
  echo "---"
  echo "## Knowledge（${slug}）"
  echo ""
  echo "以下の知見が蓄積されている。実装時に関連する knowledge があれば Read して活用すること。"
  echo ""
  cat "$index_file"
done
