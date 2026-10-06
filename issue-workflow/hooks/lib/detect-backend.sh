#!/usr/bin/env bash
# detect-backend.sh — issue-workflow の hook 共通 backend 判定
# SKILL.md の Phase 0（backend 検出）と同一述語:
#   「データ dir が存在し、かつ配下にプロジェクト slug dir を 1 つ以上持つ」場合のみ有効
# linked worktree の中で両方とも無効なら、メインのチェックアウトの下で判定し直す
# （Issue ファイルを gitignore している repo では worktree にデータ dir が無い / GitHub issue #280）
# 呼び出し後に以下の変数が設定される:
#   IW_BACKEND  … local | linear | both | none
#   IW_DATA_DIR … .claude/indie | .claude/linear | <メインのチェックアウト>/.claude/{indie,linear}
#                 | ""（both/none 時）

iw_has_slug_dir() {
  local d="$1"
  [ -d "$d" ] || return 1
  [ -n "$(find "$d" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | head -1)" ]
}

# linked worktree の中ならメインのチェックアウトの絶対パスを出す（それ以外は何も出さない）
iw_main_checkout() {
  local gd common
  gd=$(git rev-parse --absolute-git-dir 2>/dev/null) || return 0
  common=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || return 0
  # common dir が `<root>/.git` でない（submodule など）ときは親を root と見なせない
  if [ "$gd" != "$common" ] && [ "${common##*/}" = ".git" ]; then
    printf '%s' "${common%/.git}"
  fi
  return 0
}

iw_detect_backend() {
  local indie=0 linear=0 base=""
  iw_has_slug_dir ".claude/indie" && indie=1
  iw_has_slug_dir ".claude/linear" && linear=1
  if [ "$indie" = 0 ] && [ "$linear" = 0 ]; then
    base=$(iw_main_checkout)
    if [ -n "$base" ]; then
      iw_has_slug_dir "${base}/.claude/indie" && indie=1
      iw_has_slug_dir "${base}/.claude/linear" && linear=1
      base="${base}/"
    fi
  fi
  if [ "$indie" = 1 ] && [ "$linear" = 1 ]; then
    IW_BACKEND="both"; IW_DATA_DIR=""
  elif [ "$indie" = 1 ]; then
    IW_BACKEND="local"; IW_DATA_DIR="${base}.claude/indie"
  elif [ "$linear" = 1 ]; then
    IW_BACKEND="linear"; IW_DATA_DIR="${base}.claude/linear"
  else
    IW_BACKEND="none"; IW_DATA_DIR=""
  fi
}
