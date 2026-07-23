#!/usr/bin/env bash
# detect-backend.sh — issue-workflow の hook 共通 backend 判定
# SKILL.md の Phase 0（backend 検出）と同一述語:
#   「データ dir が存在し、かつ配下にプロジェクト slug dir を 1 つ以上持つ」場合のみ有効
# 呼び出し後に以下の変数が設定される:
#   IW_BACKEND  … local | linear | both | none
#   IW_DATA_DIR … .claude/indie | .claude/linear | ""（both/none 時）

iw_has_slug_dir() {
  local d="$1"
  [ -d "$d" ] || return 1
  [ -n "$(find "$d" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | head -1)" ]
}

iw_detect_backend() {
  local indie=0 linear=0
  iw_has_slug_dir ".claude/indie" && indie=1
  iw_has_slug_dir ".claude/linear" && linear=1
  if [ "$indie" = 1 ] && [ "$linear" = 1 ]; then
    IW_BACKEND="both"; IW_DATA_DIR=""
  elif [ "$indie" = 1 ]; then
    IW_BACKEND="local"; IW_DATA_DIR=".claude/indie"
  elif [ "$linear" = 1 ]; then
    IW_BACKEND="linear"; IW_DATA_DIR=".claude/linear"
  else
    IW_BACKEND="none"; IW_DATA_DIR=""
  fi
}
