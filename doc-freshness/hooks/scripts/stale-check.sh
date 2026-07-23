#!/usr/bin/env bash
# stale-check.sh — SessionStart hook (once, opt-in)
# frontmatter 必須の project doc（.claude/designs/ ・ .claude/adr/ 等）を走査し、
# last-validated が phase 別閾値を超えた stale doc をまとめて 1 回警告する。
#
# 設計方針（issue #79）:
#   - opt-in（.claude/doc-freshness.json の sessionStartCheck: true が無ければ何もしない）。
#     stale 検出は毎セッションだとノイズになりうるため、継続監視したい人だけ有効化する
#   - 検出のみ。修正は既存 skill（/doc-freshness-check）に委ねる（hook は軽量読み出しに徹する）
#   - append_only: true / phase: superseded は stale 判定を免除（skill Phase 3 と同基準）

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "doc-freshness:stale-check"

# stdin は使わないが safe_hook_init が消費済み

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
CONFIG="${PROJECT_DIR}/.claude/doc-freshness.json"

# opt-in: config が無い、または sessionStartCheck が true でなければ silent exit
[ -f "$CONFIG" ] || safe_hook_error NotFound "no doc-freshness.json (session stale check is opt-in)"
command -v jq >/dev/null 2>&1 || safe_hook_error Dependency "jq required for session stale check"
[ "$(jq -r '.sessionStartCheck // false' "$CONFIG" 2>/dev/null)" = "true" ] \
  || safe_hook_error Validation "sessionStartCheck not enabled"

# 閾値と対象 prefix（config で上書き可、無ければデフォルト）
# jq 失敗（config 破損等）でも set -e で中断しないよう || true でガードし、空はデフォルトに倒す
CUR_THRESH=$(jq -r '.thresholds.current // 60' "$CONFIG" 2>/dev/null || true); CUR_THRESH=${CUR_THRESH:-60}
TGT_THRESH=$(jq -r '.thresholds.target // 15' "$CONFIG" 2>/dev/null || true); TGT_THRESH=${TGT_THRESH:-15}
TARGETS=$(jq -r '.hookTargets[]? // empty' "$CONFIG" 2>/dev/null | tr '\n' ' ' || true)
[ -z "$TARGETS" ] && TARGETS=".claude/designs/ .claude/adr/ .claude/living-specs/"

# 日付 → epoch 秒（macOS BSD date / Linux GNU date 両対応）
date_to_ts() {
  local d="$1"
  date -j -f "%Y-%m-%d" "$d" "+%s" 2>/dev/null || date -d "$d" "+%s" 2>/dev/null || echo ""
}
now=$(date "+%s")

stale_list=""
stale_count=0

for t in $TARGETS; do
  dir="${PROJECT_DIR}/${t%/}"   # t 末尾の / を除去して find の二重スラッシュを防ぐ
  [ -d "$dir" ] || continue
  # 対象 dir 配下の .md を走査（サブディレクトリ含む）
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    first_line=$(head -1 "$f" 2>/dev/null || true)
    [ "$first_line" = "---" ] || continue   # frontmatter 無しは frontmatter-guard の領分
    fm=$(awk 'NR==1{next} /^---[[:space:]]*$/{exit} {print}' "$f" 2>/dev/null || true)

    # 免除: append_only:true / phase:superseded は stale 判定しない
    echo "$fm" | grep -qE '^append_only:[[:space:]]*true' && continue
    # grep が空ヒット（exit 1）でも pipefail+set -e で中断しないよう || true でガードする
    # （phase / last-validated 行が無い doc で assignment が失敗し ERR trap が走ると走査全体が止まるため）
    phase=$(echo "$fm" | grep -E '^phase:' | head -1 | sed 's/^phase:[[:space:]]*//; s/[[:space:]].*$//' || true)
    [ "$phase" = "superseded" ] && continue

    validated=$(echo "$fm" | grep -E '^last-validated:' | head -1 | sed 's/^last-validated:[[:space:]]*//; s/[[:space:]].*$//' || true)
    [ -z "$validated" ] && continue   # last-validated 欠落は frontmatter-guard の領分
    ts=$(date_to_ts "$validated")
    [ -z "$ts" ] && continue

    age_days=$(( (now - ts) / 86400 ))
    case "$phase" in
      target) thresh=$TGT_THRESH ;;
      *)      thresh=$CUR_THRESH ;;   # current または未指定は current 扱い
    esac

    if [ "$age_days" -gt "$thresh" ]; then
      rel="${f#"$PROJECT_DIR"/}"
      stale_list="${stale_list}
  - ${rel}（phase: ${phase:-current}, ${age_days}日 > ${thresh}日）"
      stale_count=$((stale_count + 1))
    fi
  done < <(find "$dir" -type f -name '*.md' 2>/dev/null)
done

# stale が無ければ silent exit（ノイズを出さない）
[ "$stale_count" -eq 0 ] && safe_hook_error Validation "no stale docs"

safe_hook_emit_context "SessionStart" "[doc-freshness] stale な project doc が ${stale_count} 件あります（last-validated が phase 別閾値を超過）:${stale_list}

内容を読み直して問題なければ last-validated を更新するか、/doc-freshness-check で一括対応してください。"
