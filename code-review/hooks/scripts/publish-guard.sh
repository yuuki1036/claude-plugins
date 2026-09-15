#!/usr/bin/env bash
# publish-guard.sh — Stop hook（v2.115.0 / GitHub issue #219）+ PreToolUse（GitHub issue #232）
#
# `review-timing.sh start` の打点ファイルが「t0 あり・pub なし」のままターンが終わったら
# **1 回だけ**鳴らす。SKILL.md 側の `publish-pending` ガードは SKILL.md が読まれた回にしか
# 効かない — 同名の command と skill は `Skill` tool で呼んでも command 本文が返るため、
# 記憶から手順を再現した回は publish（review:completed）が丸ごと落ち、計測に「起きたこと」
# すら残らない（実測 2026-09-06 / yatima）。決定的に判定できる（ファイルの行を見るだけ）ので
# hook に置く（CLAUDE.md「決定的 hook > LLM 判定」）。
#
# PreToolUse 経路: Stop はターン終端でしか走らないので、親 skill（feature-dev 等）が
# self-review を回して**同じターンのまま次のフェーズへ進む**と、鳴るのは 10 分以上後で
# duration が欠測に倒れた後になる（#232）。そこで self-review の打点ファイル（`-prN` の無い
# もの）に `t2` があり `pub` が無い状態で Edit / Write / Skill / Agent を呼んだら、その場で鳴らす。
# `t2` 以降で正当な tool 呼び出しは publish（Bash）だけなので、Bash は対象にしない。
# review（`-prN` 付き）は t2 と publish の間に締めフロー 1〜3（writing-polish を Skill で呼ぶ）
# があるので対象にしない。
#
# 黙る条件を厚く: 打点ファイルが無い（計測していない / publish 済みで掃除された）/ `pub` が
# ある / 既に鳴らした（`nag` 行）/ `t0` すら無い。**鳴るのは 1 ファイルにつき 1 回**（両経路で
# `nag` を共有する）— 放置された打点ファイルは次の `start` まで残るので、毎ターン鳴らすと
# 「⚠️ が出たときだけ行動する」契約が壊れる。
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "code-review:publish-guard"

# hooks.json の matcher は実行環境によって評価されないことがある（dev-workflow で実測）ので
# tool_name を自己判定する。取れなければ Stop 経路として扱う（従来挙動）
INPUT=$(safe_hook_input)
TOOL_NAME=""
if command -v jq &>/dev/null; then
  TOOL_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
else
  TOOL_NAME=$(printf '%s' "$INPUT" | grep -oE '"tool_name"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*:[[:space:]]*"([^"]+)"/\1/' || true)
fi

# shellcheck source=../../scripts/lib/review-paths.sh
. "${CLAUDE_PLUGIN_ROOT}/scripts/lib/review-paths.sh" 2>/dev/null || safe_hook_error Dependency
review_paths_init "" || safe_hook_error Dependency

if [ -n "$TOOL_NAME" ]; then
  case "$TOOL_NAME" in
    Edit|Write|MultiEdit|NotebookEdit|Skill|Agent|Task) ;;
    *) safe_hook_error Validation "not a phase-advancing tool" ;;
  esac
  f="$(review_path timing)"
  if [ ! -f "$f" ]; then
    safe_hook_error NotFound "no self-review timing file"
  fi
  if ! grep -q '^t2 ' "$f" 2>/dev/null; then
    safe_hook_error NotFound "report not yet output"
  fi
  if grep -q '^pub ' "$f" 2>/dev/null || grep -q '^nag ' "$f" 2>/dev/null; then
    safe_hook_error NotFound "already published or nagged"
  fi
  echo "nag $(date +%s)" >> "$f"
  MSG="self-review のレポート出力（mark t2）の後、publish（review:completed / Step 6.4）を踏まずに ${TOOL_NAME} へ進もうとしている。先に \`bash \"\${CLAUDE_PLUGIN_ROOT}/scripts/publish-review-event.sh\"\` で publish を済ませる。レポートを Step 6 の定型（総合判定 / 総合評価 / レビュー構成 / 動的ラウンド / 指摘件数 / 反証）以外で出していたら、publish の前に定型で出し直す。他 skill から self-review を回している場合も、Step 6 と 6.4 は self-review の手順として踏む（GitHub issue #232）。"
  echo "WARN: ${MSG}" >&2
  safe_hook_emit_context PreToolUse "$MSG"
  exit 0
fi

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
