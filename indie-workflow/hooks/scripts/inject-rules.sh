#!/usr/bin/env bash
set -euo pipefail
cat > /dev/null

if [ ! -d ".claude/indie" ]; then
  exit 0
fi

# ルール注入
RULES_DIR="${CLAUDE_PLUGIN_ROOT}/rules"
if [ -f "${RULES_DIR}/project-rules.md" ]; then
  cat "${RULES_DIR}/project-rules.md"
fi
# 放置 Issue 検知（7日以上 last_active が更新されていない in-progress Issue）
echo ""
echo "---"
echo "## 放置 Issue 検知"
found=0
for issue_file in .claude/indie/*/issues/*.md; do
  [ -f "$issue_file" ] || continue
  status=$(head -20 "$issue_file" | grep -m1 '^status:' | sed 's/status: *//')
  [ "$status" = "in-progress" ] || continue
  last=$(head -20 "$issue_file" | grep -m1 '^last_active:' | sed 's/last_active: *//')
  [ -n "$last" ] || continue
  days_ago=$(( ($(date +%s) - $(date -j -f "%Y-%m-%d" "$last" +%s 2>/dev/null || echo 0)) / 86400 ))
  if [ "$days_ago" -ge 7 ]; then
    id=$(head -20 "$issue_file" | grep -m1 '^id:' | sed 's/id: *//')
    echo "- **${id}**: ${days_ago}日間未更新"
    found=1
  fi
done
if [ "$found" -eq 0 ]; then
  echo "(なし)"
fi
