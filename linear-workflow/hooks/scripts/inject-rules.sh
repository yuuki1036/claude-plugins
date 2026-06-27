#!/usr/bin/env bash
# inject-rules.sh — SessionStart / PostCompact hook
# .claude/linear/ ディレクトリが存在するプロジェクトでのみ
# プロジェクト管理ルールと Knowledge インデックスを Claude のコンテキストに注入する

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "linear-workflow:inject-rules"

if [ ! -d ".claude/linear" ]; then
  safe_hook_error NotFound ".claude/linear directory missing"
fi

# 排他チェック: 同一プロジェクトに indie-workflow のデータ (.claude/indie) も同居する時のみ警告。
# settings.json のキー存在判定は使わない（無効化＝":false" でも文字列が残り誤検知し、
# project-scoped 有効化は取りこぼすため）。実際に衝突しうるのは両者のデータが同居する時だけ（#74）。
if [ -d ".claude/indie" ]; then
  echo "⚠️ **プラグイン排他警告**: このプロジェクトに linear-workflow と indie-workflow のデータ（.claude/linear・.claude/indie）が同居しています。同名スキル（作業開始 / 知見 / プロジェクト整理 等）のトリガーが衝突しスキル選択が不安定になります。どちらか一方のワークフローに統一してください（Linear 連携=linear / ローカル管理=indie）。"
  echo ""
fi

# ルールファイルを出力（stdout が Claude のコンテキストに入る）
RULES_DIR="${CLAUDE_PLUGIN_ROOT}/rules"
if [ -f "${RULES_DIR}/project-rules.md" ]; then
  cat "${RULES_DIR}/project-rules.md"
fi

# Knowledge インデックス注入
for index_file in .claude/linear/*/knowledge/index.md; do
  [ -f "$index_file" ] || continue
  slug=$(echo "$index_file" | sed 's|.claude/linear/\(.*\)/knowledge/index.md|\1|')
  echo ""
  echo "---"
  echo "## Knowledge（${slug}）"
  echo ""
  echo "以下の知見が蓄積されている。実装時に関連する knowledge があれば Read して活用すること。"
  echo ""
  cat "$index_file"
done
