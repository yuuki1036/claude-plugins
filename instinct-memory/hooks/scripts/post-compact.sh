#!/usr/bin/env bash
# post-compact.sh — PostCompact hook
# コンテキスト圧縮後に instincts を再注入する
# 長いセッションでコンテキスト圧縮されると instincts の情報が失われるため

set -euo pipefail

# stdin から hook 入力を読む（消費する必要がある）
cat > /dev/null

# instincts.md が存在する場合のみ注入
INSTINCTS_DIR=""
for dir in .claude/projects/*/memory; do
  if [ -f "${dir}/instincts.md" ]; then
    INSTINCTS_DIR="${dir}"
    break
  fi
done

if [ -z "$INSTINCTS_DIR" ]; then
  exit 0
fi

cat <<'EOF'
コンテキスト圧縮後の instinct 再注入:
memory/instincts.md に候補パターンが存在する。
instinct-learning スキルに従い、セッション中の観察を継続せよ。
確認が必要な場合は instincts.md を Read すること。
EOF
