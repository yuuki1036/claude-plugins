#!/usr/bin/env bash
# 指定 PR のブランチを保持している「開発用 worktree」を検出する（teardown 案内用）。
#
# ブランチ名一致だけでは、レビュー用に EnterWorktree した一時 worktree
# (`.claude/worktrees/` 配下) と区別できない。**パス除外 + worktree-setup マーカー**
# の 2 条件で dev-workflow:worktree-setup 由来のものだけに絞る。
#
# 使い方:
#   detect-dev-worktree.sh --pr <N>          # PR のブランチ名は本スクリプトが gh で取得する
#   detect-dev-worktree.sh --branch <name>   # ブランチ名を直接指定（PR を持たない経路用）
#
# **`--pr` を優先して使うこと。** ブランチ名は PR 作者が完全に制御する外部入力であり、
# git の ref 名規則は `$` / バッククォート / `;` / `|` を禁じていない（`feat/$(...)` は
# 有効な ref 名）。SKILL 本文に `detect-dev-worktree.sh "<PR ブランチ名>"` と書いて
# LLM に実値を埋めさせると、その文字列がレビュアーのシェルで評価される経路ができる。
# `--pr` なら LLM が触るのは数値だけになり、ブランチ名はプロセス内に閉じる。
set -uo pipefail

PR=""; BRANCH=""
while [ $# -gt 0 ]; do
  case "$1" in
    --pr)     [ $# -ge 2 ] || { echo "FATAL: --pr に値が必要" >&2; exit 2; }; PR="$2"; shift 2 ;;
    --branch) [ $# -ge 2 ] || { echo "FATAL: --branch に値が必要" >&2; exit 2; }; BRANCH="$2"; shift 2 ;;
    *) echo "usage: detect-dev-worktree.sh --pr <N> | --branch <name>" >&2; exit 2 ;;
  esac
done

if [ -n "$PR" ]; then
  case "$PR" in
    ''|*[!0-9]*) echo "FATAL: --pr は数値のみ指定できる（受領: '$PR'）" >&2; exit 2 ;;
  esac
  BRANCH=$(gh pr view "$PR" --json headRefName -q .headRefName 2>/dev/null)
  [ -n "$BRANCH" ] || { echo "FATAL: PR #${PR} の head ref を取得できない" >&2; exit 1; }
fi
[ -n "$BRANCH" ] || { echo "usage: detect-dev-worktree.sh --pr <N> | --branch <name>" >&2; exit 2; }

# ブランチ名は awk へ -v で渡し、比較は文字列等価（正規表現ではない）。
# シェルで再評価される経路を持たない
git worktree list --porcelain 2>/dev/null \
  | awk -v ref="refs/heads/$BRANCH" '/^worktree /{wt=substr($0,10)} $0=="branch "ref{print wt}' \
  | while IFS= read -r wt; do
      # レビュー用の一時 worktree は対象外
      case "$wt" in */.claude/worktrees/*) continue;; esac
      # worktree-setup が置くマーカーがあるものだけを開発用とみなす
      # （backend / frontend いずれかの env があれば worktree-setup 由来）
      if [ -f "$wt/envs/.backend.env.worktree" ] || [ -f "$wt/envs/.frontend.env.worktree" ]; then
        echo "$wt"
      fi
    done
exit 0
