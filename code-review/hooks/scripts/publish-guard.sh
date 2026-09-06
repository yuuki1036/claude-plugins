#!/usr/bin/env bash
# publish-guard.sh — Stop hook（v2.115.0 / GitHub issue #219）
#
# `review-timing.sh start` の打点ファイルが「t0 あり・pub なし」のままターンが終わったら
# **1 回だけ**鳴らす。SKILL.md 側の `publish-pending` ガードは SKILL.md が読まれた回にしか
# 効かない — 同名の command と skill は `Skill` tool で呼んでも command 本文が返るため、
# 記憶から手順を再現した回は publish（review:completed）が丸ごと落ち、計測に「起きたこと」
# すら残らない（実測 2026-09-06 / yatima）。決定的に判定できる（ファイルの行を見るだけ）ので
# hook に置く（CLAUDE.md「決定的 hook > LLM 判定」）。
#
# 黙る条件を厚く: 打点ファイルが無い（計測していない / publish 済みで掃除された）/ `pub` が
# ある / 既に鳴らした（`nag` 行）/ `t0` すら無い。**鳴るのは 1 ファイルにつき 1 回** —
# 放置された打点ファイルは次の `start` まで残るので、毎ターン鳴らすと「⚠️ が出たときだけ
# 行動する」契約が壊れる。
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "code-review:publish-guard"

# shellcheck source=../../scripts/lib/review-paths.sh
. "${CLAUDE_PLUGIN_ROOT}/scripts/lib/review-paths.sh" 2>/dev/null || safe_hook_error Dependency
review_paths_init "" || safe_hook_error Dependency

pending=""
for f in "$REVIEW_TMPROOT"/review-start-"$REVIEW_SLUG"*; do
  if [ ! -f "$f" ]; then
    continue
  fi
  if ! grep -q '^t0 ' "$f" 2>/dev/null; then
    continue
  fi
  if grep -q '^pub ' "$f" 2>/dev/null; then
    continue
  fi
  if grep -q '^nag ' "$f" 2>/dev/null; then
    continue
  fi
  echo "nag $(date +%s)" >> "$f"
  pending="${pending} $(basename "$f")"
done

if [ -z "$pending" ]; then
  exit 0
fi

MSG="code-review の計測が start されたまま publish（review:completed）されていない:${pending}。レビューが継続中なら無視してよい（この通知は打点ファイルごとに 1 回だけ）。レビューが終わっているなら publish を踏む（self-review Step 6.4 / review 締めフロー 4 — \`bash \"\${CLAUDE_PLUGIN_ROOT}/scripts/publish-review-event.sh\"\`）。レポート出力から時間が経つほど duration が伸び、self-review は 10 分以上で欠測に倒れる。SKILL.md を読まずに記憶から手順を再現した回は publish が丸ごと落ちる（GitHub issue #219）。"
echo "WARN: ${MSG}" >&2
safe_hook_emit_context Stop "$MSG"
