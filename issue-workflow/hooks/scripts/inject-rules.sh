#!/usr/bin/env bash
# inject-rules.sh — SessionStart / PostCompact hook
# backend（local: .claude/indie / linear: .claude/linear）を判定し、有効なプロジェクトでのみ
# プロジェクト管理ルール・Knowledge インデックス・放置 Issue 検知を注入する
# 全体は INJECT_LIMIT 字に収める。規約は必ず全文、knowledge は残りに入る分だけ（hooks/scripts/inject-budget.py）

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

# Claude Code は hook の stdout を 10,000 字で打ち切り、先頭 2,000 字のプレビューしか渡さない。
# 500 字は JS の UTF-16 長（BMP 外の文字を 2 と数える）と len の差の分の余裕
INJECT_LIMIT=9500

# 放置 Issue 検知（7日以上 last_active が更新されていない in-progress Issue）
# 検出 0 件のときはセクションごと省略する（ノイズ注入を避ける）
stale_issues=""
for issue_file in "${IW_DATA_DIR}"/*/issues/*.md; do
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
    stale_issues="${stale_issues}- **${id}**: ${days_ago}日間未更新"$'\n'
  fi
done

# Knowledge インデックス（slug と index.md の組を inject-budget.py へ渡す）
# IW_DATA_DIR は worktree からメインのチェックアウトを指す絶対パスにもなる（空白を含みうるので引用する）
index_args=()
for index_file in "${IW_DATA_DIR}"/*/knowledge/index.md; do
  [ -f "$index_file" ] || continue
  slug=${index_file#"${IW_DATA_DIR}"/}
  slug=${slug%%/*}
  index_args+=("$slug" "$index_file")
done

# 必ず出す部分: 残骸 dir の警告・backend の行・規約の本文
emit_required() {
  # 有効 backend の反対側に無効な dir だけが残っているケース
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

  local rules="${CLAUDE_PLUGIN_ROOT}/rules/project-rules.md"
  if [ -f "$rules" ]; then
    # {PLUGIN_ROOT} は同梱スクリプトのパス。cat では展開されないので、そのまま実行できる形に置き換える
    sed "s|{PLUGIN_ROOT}|${CLAUDE_PLUGIN_ROOT}|g" "$rules"
  fi
}

# 字数を数えられない回の出力。knowledge は出さず、規約と放置 Issue だけを出す
# （見出しは inject-budget.py の例外の経路と揃える。理由はそれぞれ実際に起きたことを書く）
emit_without_budget() {
  printf '%s' "$required"
  if [ "${#index_args[@]}" -gt 0 ]; then
    echo ""
    echo "---"
    echo "## Knowledge"
    echo ""
    echo "knowledge の index は注入していない（字数を数えられず、注入の上限に収められない）。\`/knowledge\` で一覧を見る。"
  fi
  if [ -n "$stale_issues" ]; then
    echo ""
    echo "---"
    echo "## 放置 Issue 検知"
    echo ""
    printf '%s' "$stale_issues"
  fi
}

# 規約は先に変数へ読み込む。パイプの左側で出すと、左側だけが失敗した回（sed が規約を読めない等）に
# python が書き終えた後で縮退の経路がもう一度規約を出す。$( ) は末尾の改行を落とすので番兵 x を足して外す
required="$(emit_required; printf x)"
required=${required%x}

# python3 が PATH にあっても起動に失敗する環境がある（CLT の無い macOS のスタブ・pyenv の shim・3.6 以前）。
# 失敗を if の条件で受けて、set -e と ERR trap に規約ごと落とさせない。inject-budget.py は
# 最後に 1 回だけ書くので、失敗した回に途中までの出力は残らない
# 空配列の "${a[@]}" は bash 3.2 の set -u で unbound になるので ${a[@]+...} で展開する
if command -v python3 >/dev/null 2>&1 \
  && printf '%s' "$required" | IW_STALE="$stale_issues" python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/inject-budget.py" \
    "$INJECT_LIMIT" ${index_args[@]+"${index_args[@]}"}; then
  :
else
  emit_without_budget
fi
