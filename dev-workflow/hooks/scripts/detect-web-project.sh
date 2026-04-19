#!/usr/bin/env bash
# detect-web-project.sh — SessionStart hook
# package.json に Web フレームワーク依存があれば ui-verify 連携を有効化
# （.claude/.ui-verify-enabled フラグを管理）

set -euo pipefail
cat > /dev/null

STATE_DIR=".claude"
ENABLED_FLAG="${STATE_DIR}/.ui-verify-enabled"

# package.json がなければ無効化
if [[ ! -f package.json ]]; then
  rm -f "$ENABLED_FLAG" 2>/dev/null || true
  exit 0
fi

# Web フレームワーク検出
WEB_FRAMEWORKS='^(next|react|vue|svelte|@angular/core|nuxt|astro|solid-js|remix|preact|qwik|@sveltejs/kit|gatsby)$'

if command -v jq &>/dev/null; then
  MATCH=$(jq -r '(.dependencies // {}) + (.devDependencies // {}) | keys | .[]' package.json 2>/dev/null \
    | grep -E "$WEB_FRAMEWORKS" | head -1 || true)
else
  # jq が無い場合の fallback（簡易 grep）
  MATCH=$(grep -oE '"(next|react|vue|svelte|nuxt|astro|remix|preact|qwik|gatsby)"' package.json 2>/dev/null | head -1 || true)
fi

if [[ -n "$MATCH" ]]; then
  mkdir -p "$STATE_DIR"
  touch "$ENABLED_FLAG"
else
  rm -f "$ENABLED_FLAG" 2>/dev/null || true
fi

# silent — context 注入しない
exit 0
