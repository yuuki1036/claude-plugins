#!/usr/bin/env bash
# 指定ブランチを保持している「開発用 worktree」を検出する（teardown 案内用）。
#
# ブランチ名一致だけでは、レビュー用に EnterWorktree した一時 worktree
# (`.claude/worktrees/` 配下) と区別できない。**パス除外 + worktree-setup マーカー**
# の 2 条件で dev-workflow:worktree-setup 由来のものだけに絞る。
#
# 使い方:
#   detect-dev-worktree.sh <branch>     # 該当 worktree のパスを 1 行ずつ出力（無ければ何も出さない）
set -uo pipefail

BRANCH="${1:-}"
[ -n "$BRANCH" ] || { echo "usage: detect-dev-worktree.sh <branch>" >&2; exit 2; }

git worktree list --porcelain 2>/dev/null \
  | awk -v ref="refs/heads/$BRANCH" '/^worktree /{wt=substr($0,10)} $0=="branch "ref{print wt}' \
  | while read -r wt; do
      # レビュー用の一時 worktree は対象外
      case "$wt" in */.claude/worktrees/*) continue;; esac
      # worktree-setup が置くマーカーがあるものだけを開発用とみなす
      [ -f "$wt/envs/.backend.env.worktree" ] && echo "$wt"
    done
exit 0
