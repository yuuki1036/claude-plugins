#!/usr/bin/env bash
# cc-catch-up Phase 3 frontmatter 決定的 pre-pass.
#
# 全プラグインの manifest / hooks / skills / agents / commands から「使用フィールド」を
# grep / jq で機械抽出し, 機能使用プロファイルを JSON 配列で出力する. Phase 3 の Agent
# fan-out はこの構造化出力を入力に「適用判定（判断・要約層）」だけを行い, frontmatter の
# 生抽出は LLM にさせない（決定的 hook > LLM 判定）.
#
# 実行: scan-frontmatter.sh [repo_root] [--plugin NAME]
#   repo_root 省略時はカレントディレクトリ（cc-catch-up は marketplace リポジトリで動く前提）
#   --plugin NAME 指定時はそのプラグインのみ出力
# 出力: stdout に JSON 配列（プラグインごとのプロファイル）
# Exit: 0 (成功) / 2 (jq 不在)

set -euo pipefail

ROOT="."
ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --plugin) ONLY="${2:-}"; shift 2 ;;
    *) ROOT="$1"; shift ;;
  esac
done

command -v jq >/dev/null 2>&1 || { echo "[scan-frontmatter] jq required" >&2; exit 2; }

# frontmatter（先頭の --- 〜 次の ---）のトップレベルキーを sort -u して JSON 配列で返す.
fm_keys_json() {
  awk '
    /^---[ \t]*$/ { c++; next }
    c==1 && /^[A-Za-z_][A-Za-z0-9_-]*:/ { k=$0; sub(/:.*/, "", k); print k }
    c>=2 { exit }
  ' "$1" 2>/dev/null | sort -u | jq -R -s 'split("\n") | map(select(length > 0))'
}

# 改行区切りの JSON オブジェクト群を配列にまとめる（空なら []）.
collect() {
  if [ "$#" -eq 0 ]; then echo '[]'; else printf '%s\n' "$@" | jq -s '.'; fi
}

profile_plugin() {
  local dir="$1"
  local name manifest manifest_keys hooks_json hooks
  name=$(basename "$dir")

  manifest="$dir/.claude-plugin/plugin.json"
  manifest_keys='[]'
  [ -f "$manifest" ] && manifest_keys=$(jq -c 'keys' "$manifest" 2>/dev/null || echo '[]')

  hooks_json="$dir/hooks/hooks.json"
  hooks='null'
  if [ -f "$hooks_json" ]; then
    local events types hascond
    events=$(jq -c '(.hooks // {}) | keys' "$hooks_json" 2>/dev/null || echo '[]')
    types=$(jq -c '[(.hooks // {}) | .[][]?.hooks[]?.type] | unique' "$hooks_json" 2>/dev/null || echo '[]')
    if grep -q '"condition"' "$hooks_json" 2>/dev/null; then hascond=true; else hascond=false; fi
    hooks=$(jq -nc --argjson e "$events" --argjson t "$types" --argjson h "$hascond" \
      '{events: $e, handler_types: $t, has_condition: $h}')
  fi

  local -a skills=() agents=() commands=()
  local f k
  for f in "$dir"/skills/*/SKILL.md; do
    [ -f "$f" ] || continue
    k=$(fm_keys_json "$f")
    skills+=("$(jq -nc --arg n "$(basename "$(dirname "$f")")" --argjson k "$k" '{name: $n, frontmatter_keys: $k}')")
  done
  for f in "$dir"/agents/*.md; do
    [ -f "$f" ] || continue
    k=$(fm_keys_json "$f")
    agents+=("$(jq -nc --arg n "$(basename "$f")" --argjson k "$k" '{file: $n, frontmatter_keys: $k}')")
  done
  for f in "$dir"/commands/*.md; do
    [ -f "$f" ] || continue
    k=$(fm_keys_json "$f")
    commands+=("$(jq -nc --arg n "$(basename "$f")" --argjson k "$k" '{file: $n, frontmatter_keys: $k}')")
  done

  jq -nc \
    --arg name "$name" \
    --argjson manifest_keys "$manifest_keys" \
    --argjson hooks "$hooks" \
    --argjson skills "$(collect ${skills[@]+"${skills[@]}"})" \
    --argjson agents "$(collect ${agents[@]+"${agents[@]}"})" \
    --argjson commands "$(collect ${commands[@]+"${commands[@]}"})" \
    '{plugin: $name, manifest_keys: $manifest_keys, hooks: $hooks, skills: $skills, agents: $agents, commands: $commands}'
}

profiles=()
for manifest in "$ROOT"/*/.claude-plugin/plugin.json; do
  [ -f "$manifest" ] || continue
  dir=$(dirname "$(dirname "$manifest")")
  pname=$(basename "$dir")
  if [ -n "$ONLY" ] && [ "$pname" != "$ONLY" ]; then continue; fi
  profiles+=("$(profile_plugin "$dir")")
done

collect ${profiles[@]+"${profiles[@]}"}
