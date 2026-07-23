#!/usr/bin/env bash
# inject-rules.sh — SessionStart / PostCompact hook
# backend（local: .claude/indie / linear: .claude/linear）を判定し、有効なプロジェクトでのみ
# プロジェクト管理ルール・Knowledge インデックス・放置 Issue 検知を注入する

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "issue-workflow:inject-rules"
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/detect-backend.sh"

iw_detect_backend

case "$IW_BACKEND" in
  none)
    safe_hook_error NotFound "no valid backend data dir (.claude/indie|.claude/linear)"
    ;;
  both)
    # 両 backend が有効（両方に slug dir がある）はエラー相当: 片寄せまでスキル実行が止まるため、
    # ルール注入は行わず衝突の解消手順だけを注入する
    echo "⚠️ **backend 衝突**: このプロジェクトには \`.claude/indie\` と \`.claude/linear\` の両方に有効なプロジェクトデータが存在します。issue-workflow の各スキルは backend を特定できずエラー停止します。どちらを正とするか決め、他方のディレクトリを退避（rename）または削除して片寄せしてください。"
    exit 0
    ;;
esac

# 残骸 dir の警告（有効 backend の反対側に無効な dir だけが残っているケース）
if [ "$IW_BACKEND" = "local" ] && [ -d ".claude/linear" ]; then
  echo "（注意: \`.claude/linear\` に空の残骸ディレクトリがあります。混乱防止のため削除を推奨します）"
  echo ""
elif [ "$IW_BACKEND" = "linear" ] && [ -d ".claude/indie" ]; then
  echo "（注意: \`.claude/indie\` に空の残骸ディレクトリがあります。混乱防止のため削除を推奨します）"
  echo ""
fi

# backend の明示（rules 内の {DATA_DIR} 表記を具体化する）
echo "issue-workflow backend: ${IW_BACKEND}（DATA_DIR=${IW_DATA_DIR}）"
echo ""

# ルール注入
RULES_DIR="${CLAUDE_PLUGIN_ROOT}/rules"
if [ -f "${RULES_DIR}/project-rules.md" ]; then
  cat "${RULES_DIR}/project-rules.md"
fi

# Knowledge インデックス注入
for index_file in ${IW_DATA_DIR}/*/knowledge/index.md; do
  [ -f "$index_file" ] || continue
  slug=$(echo "$index_file" | sed "s|${IW_DATA_DIR}/\(.*\)/knowledge/index.md|\1|")
  echo ""
  echo "---"
  echo "## Knowledge（${slug}）"
  echo ""
  echo "以下の知見が蓄積されている。実装時に関連する knowledge があれば Read して活用すること。"
  echo ""
  cat "$index_file"
done

# 放置 Issue 検知（7日以上 last_active が更新されていない in-progress Issue）
# 検出 0 件のときはセクションごと省略する（ノイズ注入を避ける）
stale_issues=""
for issue_file in ${IW_DATA_DIR}/*/issues/*.md; do
  [ -f "$issue_file" ] || continue
  # grep はマッチ 0 件で exit 1 を返す。set -euo pipefail 下で代入に伝播すると
  # ERR trap が発火しフック全体がサイレント終了するため、|| true で握る
  # （status: 行を欠く不正な issue ファイル 1 つで放置 Issue 検知が丸ごと落ちるのを防ぐ）
  status=$(head -20 "$issue_file" | grep -m1 '^status:' | sed 's/status: *//' || true)
  [ "$status" = "in-progress" ] || continue
  last=$(head -20 "$issue_file" | grep -m1 '^last_active:' | sed 's/last_active: *//' || true)
  [ -n "$last" ] || continue
  last_epoch=$(date -j -f "%Y-%m-%d" "$last" +%s 2>/dev/null || date -d "$last" +%s 2>/dev/null || echo 0)
  [ "$last_epoch" -eq 0 ] && continue  # パース不能な last_active は stale 判定をスキップ（Linux/macOS 両対応・誤検知防止）
  days_ago=$(( ($(date +%s) - last_epoch) / 86400 ))
  if [ "$days_ago" -ge 7 ]; then
    id=$(head -20 "$issue_file" | grep -m1 '^id:' | sed 's/id: *//' || true)
    [ -n "$id" ] || id=$(head -20 "$issue_file" | grep -m1 '^linear:' | sed 's/linear: *//' || true)
    stale_issues="${stale_issues}\n- **${id}**: ${days_ago}日間未更新"
  fi
done
if [ -n "$stale_issues" ]; then
  echo ""
  echo "---"
  echo "## 放置 Issue 検知"
  echo -e "$stale_issues"
fi
