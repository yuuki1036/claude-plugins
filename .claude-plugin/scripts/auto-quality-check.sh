#!/usr/bin/env bash
# auto-quality-check.sh — Stop hook 用の自動品質チェック
#
# 目的:
#   プラグイン関連ファイルを変更して実装を終えたタイミングで、
#   機械的に検証可能な品質チェックを実行して早期に違反を検知する。
#
# 実行するチェック:
#   1. validate-ssot.sh
#      - plugin.json / marketplace.json / hooks.json のスキーマ準拠
#      - marketplace.json と plugin.json の name/version/description 同期
#      - _requirements と check-deps.sh の一致
#   2. validate_plugin_quality.py
#      - allowed-tools の存在と command <-> skill ペア一致
#      - hooks.json で参照されるスクリプトの safe_hook_init 呼び出し
#      - safe-hook.sh canonical と replica の byte-identical
#      - SKILL.md の ${CLAUDE_PLUGIN_ROOT}/... 参照の実在
#      - SKILL.md description の「トリガー:」存在
#   3. claude plugin validate
#      - plugin.json の CLI スキーマバリデーション（_requirements 警告は除外）
#
# トリガー条件:
#   working tree に以下のパターンの変更がある場合のみチェック実行
#     - */plugin.json
#     - .claude-plugin/marketplace.json
#     - */skills/** / */commands/** / */hooks/** / */references/**
#     - */CHANGELOG.md
#
# 出力:
#   - エラーなし: silent exit 0
#   - エラーあり: stderr に要修正項目を通知（exit 0、Stop はブロックしない）

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# safe-hook.sh で stdin 消費と trap 設定
source "$REPO_ROOT/.claude-plugin/lib/safe-hook.sh"
safe_hook_init "auto-quality-check"

# Git 情報が取れないなら何もしない
if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  exit 0
fi

CHANGED="$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null | awk '{print $NF}')"

if [ -z "$CHANGED" ]; then
  exit 0
fi

if ! echo "$CHANGED" | grep -qE '(\.claude-plugin/.*\.json|/skills/|/commands/|/hooks/|/references/|/CHANGELOG\.md|marketplace\.json)'; then
  exit 0
fi

ISSUES=""

# 1. SSoT 同期チェック
if ! SSOT_OUT="$(bash "$REPO_ROOT/.claude-plugin/scripts/validate-ssot.sh" 2>&1)"; then
  ISSUES="${ISSUES}${SSOT_OUT}\n"
fi

# 2. プラグイン品質チェック（決定的検証項目）
if command -v python3 >/dev/null 2>&1; then
  if ! PQ_OUT="$(python3 "$REPO_ROOT/.claude-plugin/scripts/validate_plugin_quality.py" 2>&1)"; then
    ISSUES="${ISSUES}${PQ_OUT}\n"
  fi
fi

# 3. claude plugin validate（_requirements 警告は仕様により除外）
if command -v claude >/dev/null 2>&1; then
  while IFS= read -r plugin_dir; do
    [ -z "$plugin_dir" ] && continue
    VAL_OUT="$(claude plugin validate "$plugin_dir" 2>&1 || true)"
    FILTERED="$(echo "$VAL_OUT" | grep -E '^\s*❯' | grep -v 'Unrecognized key: "_requirements"' || true)"
    if [ -n "$FILTERED" ]; then
      name="$(basename "$plugin_dir")"
      ISSUES="${ISSUES}[schema:${name}] ${FILTERED}\n"
    fi
  done < <(find "$REPO_ROOT" -maxdepth 3 -name plugin.json -path '*/.claude-plugin/*' -not -path '*/node_modules/*' -exec dirname {} \; | xargs -I{} dirname {} 2>/dev/null | sort -u)
fi

if [ -n "$ISSUES" ]; then
  {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "⚠️  auto-quality-check: 修正が必要な問題があります"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    printf "%b" "$ISSUES"
    echo ""
    echo "詳細確認は /quality-check を実行してください"
  } >&2
fi

exit 0
