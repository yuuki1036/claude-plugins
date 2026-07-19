#!/usr/bin/env bash
# sync-linear-from-indie.sh — indie-workflow を正として linear-workflow の共有ファイルを検証・生成する
#
# 背景:
#   indie-workflow と linear-workflow は「ローカル Issue 管理」の双子プラグインで、
#   共有ロジックがコピペで並存している。片側にだけ修正が入る drift が実際に発生している
#   （2026-07 精査で knowledge-guide.md / writing-polish-integration.md 等に片側修正を検出）。
#   プラグイン機構はプラグイン間のファイル共有を許さないため、safe-hook.sh と同じ
#   「正本 + 機械同期 + drift チェック」方式で管理する。
#
# 対象（マニフェスト）:
#   SHARED    — byte-identical であるべきファイル（コピー）
#   TRANSFORM — indie 版に語句置換を適用すると linear 版が完全再現できるファイル
#   ここに載っていない twin ファイル（SKILL.md 大半・issue-create テンプレ・hooks.json 等）は
#   意図的に分岐しているため対象外。新たに共通化できたらマニフェストに追記する。
#
# 置換ルール（適用順が重要。フレーズ→パスの順）:
#   1. 「ローカル (.claude/indie) プロジェクト」 → 「Linear 連携プロジェクト」
#   2. /indie-issue-maintain → /issue-maintain
#   3. indie-workflow → linear-workflow
#   4. .claude/indie → .claude/linear
#
# 使い方:
#   bash .claude-plugin/scripts/sync-linear-from-indie.sh          # --check と同じ
#   bash .claude-plugin/scripts/sync-linear-from-indie.sh --check  # drift 検出のみ（CI 用）
#   bash .claude-plugin/scripts/sync-linear-from-indie.sh --write  # linear 側を indie から再生成
#
# 注意:
#   --write で linear-workflow の内容が変わったら、plugin.json のバージョンバンプと
#   CHANGELOG.md 更新が必要（pre-commit / CI が検査する）。
#
# Exit: 0 (drift なし / 書き込み完了) / 1 (drift あり)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

MODE="${1:---check}"

# "indie相対パス:linear相対パス" の組。パスが同じでも明示する。
# safe-hook.sh は validate_plugin_quality.py の safe-hook-sync が検証するため対象外。
SHARED=(
  "agents/code-context.md:agents/code-context.md"
  "skills/issue-design/references/design-rules.md:skills/issue-design/references/design-rules.md"
  "skills/issue-design/references/template-9sections.md:skills/issue-design/references/template-9sections.md"
  "skills/indie-issue-maintain/references/cleanup-criteria.md:skills/issue-maintain/references/cleanup-criteria.md"
)

TRANSFORM=(
  "commands/knowledge.md:commands/knowledge.md"
  "commands/knowledge-lint.md:commands/knowledge-lint.md"
  "hooks/scripts/on-knowledge-change.sh:hooks/scripts/on-knowledge-change.sh"
  "hooks/scripts/on-issue-change.sh:hooks/scripts/on-issue-change.sh"
  "hooks/scripts/set-session-title.sh:hooks/scripts/set-session-title.sh"
  "skills/knowledge-lint/SKILL.md:skills/knowledge-lint/SKILL.md"
)

apply_transform() {
  sed \
    -e 's|ローカル (\.claude/indie) プロジェクト|Linear 連携プロジェクト|g' \
    -e 's|/indie-issue-maintain|/issue-maintain|g' \
    -e 's|indie-workflow|linear-workflow|g' \
    -e 's|\.claude/indie|.claude/linear|g' \
    "$1"
}

drift=0
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

check_pair() {
  local kind="$1" src="indie-workflow/$2" dst="linear-workflow/$3"
  if [ ! -f "$src" ]; then
    echo "ERROR [$kind] 正本が存在しない: $src" >&2
    drift=1
    return
  fi
  if [ "$kind" = "shared" ]; then
    cp "$src" "$tmp"
  else
    apply_transform "$src" > "$tmp"
  fi
  if [ ! -f "$dst" ]; then
    echo "DRIFT [$kind] linear 側が存在しない: $dst" >&2
    drift=1
  elif ! cmp -s "$tmp" "$dst"; then
    echo "DRIFT [$kind] $dst が indie 正本と不一致（diff は以下）" >&2
    diff "$dst" "$tmp" | head -20 >&2 || true
    drift=1
  fi
  if [ "$MODE" = "--write" ]; then
    cp "$tmp" "$dst"
  fi
}

for pair in "${SHARED[@]}"; do
  check_pair "shared" "${pair%%:*}" "${pair#*:}"
done
for pair in "${TRANSFORM[@]}"; do
  check_pair "transform" "${pair%%:*}" "${pair#*:}"
done

total=$(( ${#SHARED[@]} + ${#TRANSFORM[@]} ))
if [ "$MODE" = "--write" ]; then
  echo "sync 完了 (${total} files)。linear-workflow に変更が出た場合はバージョンバンプを忘れずに"
  exit 0
fi

if [ "$drift" -eq 0 ]; then
  echo "indie/linear sync check passed (${total} files)"
else
  echo "" >&2
  echo "drift を解消するには: 正しい内容を indie-workflow 側に反映してから" >&2
  echo "  bash .claude-plugin/scripts/sync-linear-from-indie.sh --write" >&2
fi
exit "$drift"
