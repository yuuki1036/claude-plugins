#!/usr/bin/env bash
# inject-rules.sh — SessionStart / PostCompact hook
# .claude/indie/ ディレクトリが存在するプロジェクトでのみルール注入

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "issue-workflow:inject-rules"

if [ ! -d ".claude/indie" ]; then
  safe_hook_error NotFound ".claude/indie directory missing"
fi

# 排他チェック: 同一プロジェクトに linear-workflow のデータ (.claude/linear) も同居する時のみ警告。
# settings.json のキー存在判定は使わない（無効化＝":false" でも文字列が残り誤検知し、
# project-scoped 有効化は取りこぼすため）。実際に衝突しうるのは両者のデータが同居する時だけ（#74）。
if [ -d ".claude/linear" ]; then
  echo "⚠️ **プラグイン排他警告**: このプロジェクトに issue-workflow と linear-workflow のデータ（.claude/indie・.claude/linear）が同居しています。同名スキル（作業開始 / 知見 / プロジェクト整理 等）のトリガーが衝突しスキル選択が不安定になります。どちらか一方のワークフローに統一してください（ローカル管理=indie / Linear 連携=linear）。"
  echo ""
fi

# ルール注入
RULES_DIR="${CLAUDE_PLUGIN_ROOT}/rules"
if [ -f "${RULES_DIR}/project-rules.md" ]; then
  cat "${RULES_DIR}/project-rules.md"
fi

# Knowledge インデックス注入
for index_file in .claude/indie/*/knowledge/index.md; do
  [ -f "$index_file" ] || continue
  slug=$(echo "$index_file" | sed 's|.claude/indie/\(.*\)/knowledge/index.md|\1|')
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
for issue_file in .claude/indie/*/issues/*.md; do
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
    stale_issues="${stale_issues}\n- **${id}**: ${days_ago}日間未更新"
  fi
done
if [ -n "$stale_issues" ]; then
  echo ""
  echo "---"
  echo "## 放置 Issue 検知"
  echo -e "$stale_issues"
fi
