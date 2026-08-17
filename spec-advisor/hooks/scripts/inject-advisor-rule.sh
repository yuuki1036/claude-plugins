#!/usr/bin/env bash
# inject-advisor-rule.sh — SessionStart hook (once)
# 設計・計画系プラグイン（bdd-spec / design-doc / adr-keeper / feature-dev /
# issue-workflow）が 1 つでも導入されていれば、開発タスク検知時に
# spec ルーティングを促す ambient ルールを注入する。
#
# 設計方針:
#   - dormant ゲート: 提案先の設計プラグインが 1 つも「有効」でなければ advisor は inert（何も注入しない）。
#     毎セッションのノイズを避け、ルーティング先が実在する時だけ標準指示を載せる。
#   - 検出は enabled-only 判定（"<plugin>@…": true）。settings.json は無効化時に
#     '"<plugin>@…": false' としてキー文字列が残るため、キー存在だけを見る素朴な grep は
#     無効化プラグインを誤検知する（linear/indie #74 で学習済みの罠）。値が true の行だけを拾い、
#     形式差で拾えない時は fail-toward-silence（沈黙側 = noise を出さない安全側）に倒す。
#   - hook は軽量読み出しに徹し、判断は skill / メインループに委ねる。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "spec-advisor:inject-advisor-rule"

# stdin は使わないが safe_hook_init が消費済み

# グローバル + プロジェクトローカルの settings を見る（project-scoped 有効化の取りこぼし防止）
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
SETTINGS_FILES=(
  "$HOME/.claude/settings.json"
  "$PROJECT_DIR/.claude/settings.json"
  "$PROJECT_DIR/.claude/settings.local.json"
)

# dormant ゲート: 提案先が 1 つでも「有効」なら注入する（enabled-only）
installed=0
for p in bdd-spec design-doc adr-keeper feature-dev issue-workflow; do
  for f in "${SETTINGS_FILES[@]}"; do
    if grep -Eq "\"${p}@[^\"]*\"[[:space:]]*:[[:space:]]*true" "$f" 2>/dev/null; then
      installed=1
      break 2
    fi
  done
done
[ "$installed" -eq 1 ] || safe_hook_error Validation "no planning plugins enabled; advisor inert"

RULES_DIR="${CLAUDE_PLUGIN_ROOT}/rules"
[ -f "${RULES_DIR}/advisor-rule.md" ] || safe_hook_error NotFound "advisor-rule.md missing"

cat "${RULES_DIR}/advisor-rule.md"
