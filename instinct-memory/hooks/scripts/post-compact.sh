#!/usr/bin/env bash
# post-compact.sh — PostCompact hook
# コンテキスト圧縮後に instincts を再注入する

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "instinct-memory:post-compact"

# instincts.md が存在する場合のみ注入
INSTINCTS_DIR=""
for dir in .claude/projects/*/memory; do
  if [ -f "${dir}/instincts.md" ]; then
    INSTINCTS_DIR="${dir}"
    break
  fi
done

if [ -z "$INSTINCTS_DIR" ]; then
  safe_hook_error NotFound "instincts.md not found under .claude/projects/*/memory"
fi

cat <<'EOF'
コンテキスト圧縮後の instinct 再注入:
memory/instincts.md に候補パターンが存在する。
instinct-learning スキルに従い、セッション中の観察を継続せよ。
確認が必要な場合は instincts.md を Read すること。
EOF
