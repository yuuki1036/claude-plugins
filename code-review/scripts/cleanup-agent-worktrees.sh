#!/usr/bin/env bash
# レビュー用 worktree の配下に残った agent worktree とブランチを掃除する。
#
# **なぜプラグイン側で片付けるか**（GitHub issue #105）:
# Agent tool の `isolation: "worktree"` は「変更が無ければ自動削除」する仕様だが、
# reviewer / explorer の必須セットアップ（`git fetch origin refs/pull/N/head` +
# `git checkout --detach FETCH_HEAD`）が作業ツリーの中身を入れ替えるため、
# 作成時の状態から「変更あり」になり自動削除の対象外になる。
# つまり残留を作っているのはプラグイン自身なので、プラグインが片付ける。
# detach をやめれば自動削除に任せられるが、それは issue #98 で「子 agent が base branch を
# 読む」偽陽性を潰すために入れた機構なので戻せない。
#
# 使い方（レビュー用 worktree の**中から**実行する）:
#   cleanup-agent-worktrees.sh            # 削除する
#   cleanup-agent-worktrees.sh --dry-run  # 対象を列挙するだけ
#
# 安全条件（3 つすべてを満たすものだけ削除する）:
#   1. **現在の worktree の配下**にあること（並行する別レビューや開発用 worktree に触れない）
#   2. **未コミット変更が無い**こと（万一 agent が何か書いていたら残す）
#   3. 現在の worktree 自身ではないこと
set -uo pipefail

DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1; shift ;;
    *) echo "usage: cleanup-agent-worktrees.sh [--dry-run]" >&2; exit 2 ;;
  esac
done

GD=$(git rev-parse --path-format=absolute --git-dir 2>/dev/null)
GCD=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
[ -n "$GD" ] && [ -n "$GCD" ] || { echo "FATAL: git リポジトリではない" >&2; exit 2; }  # mutation-ok: 2 つは同じ git 呼び出しで同時に成否が決まり、片方だけ空にする入力を作れない

# **メインリポジトリ上では実行しない。** そこで「配下の worktree」を対象にすると
# レビュー用 worktree 自体と開発用 worktree まで巻き込む
if [ "$GD" = "$GCD" ]; then
  echo "skip: メインリポジトリ上では実行しない（レビュー用 worktree の中から呼ぶこと）" >&2
  exit 0
fi

SELF=$(git rev-parse --show-toplevel 2>/dev/null)
[ -n "$SELF" ] || { echo "FATAL: worktree のルートを取得できない" >&2; exit 2; }

removed=0; kept=0; failed=0
# **dry-run 専用**の集合。下の `INUSE` は削除ループの**後**に数えるので、実削除した
# worktree のブランチはその時点で既に「未使用」として現れる。dry-run では何も削除しない
# ぶん INUSE に残り続けるため、この集合が無いと「消せるはずのブランチ」を報告できない
FREED=""

# --- 1. 配下の agent worktree ---
while IFS= read -r wt; do
  [ -n "$wt" ] || continue
  [ "$wt" = "$SELF" ] && continue                 # 自分自身は対象外
  case "$wt" in "$SELF"/*) ;; *) continue;; esac  # 配下のものだけ
  if [ -n "$(git -C "$wt" status --porcelain 2>/dev/null)" ]; then
    echo "  keep   $wt （未コミット変更あり）"
    kept=$((kept+1)); continue
  fi
  br=$(git -C "$wt" symbolic-ref --short -q HEAD 2>/dev/null)
  if [ "$DRY" = "1" ]; then
    echo "  would remove  $wt"; removed=$((removed+1))
    [ -n "$br" ] && FREED="$FREED$br"$'\n'
    continue
  fi
  # 未コミット変更が無いことは上で確認済み。--force は locked worktree 対策
  if git worktree remove --force "$wt" 2>/dev/null; then
    removed=$((removed+1))
    # ここで FREED へ足す必要は無い（実削除後は INUSE 側から消えている）。
    # 足しても結果が変わらない = テストで守れない行になるので置かない
  else
    echo "  FAILED $wt （手動で git worktree remove --force してください）" >&2
    failed=$((failed+1))
  fi
done < <(git worktree list --porcelain 2>/dev/null | awk '/^worktree /{print substr($0,10)}')

# --- 2. どの worktree にも checkout されていない agent-* ブランチ ---
# agent は detach で作業するのでブランチ側は使われないまま残る。
# 指すのは PR head なので、削除しても失われるコミットは無い。
# **checkout 中のものは触らない**ので、並行レビューの生きた worktree は保護される。
INUSE=$(git worktree list --porcelain 2>/dev/null | awk '/^branch /{sub(/^branch refs\/heads\//,""); print}')
bdel=0; bfail=0
while IFS= read -r br; do
  [ -n "$br" ] || continue
  printf '%s\n' "$INUSE" | grep -qxF "$br" && ! printf '%s\n' "$FREED" | grep -qxF "$br" && continue
  if [ "$DRY" = "1" ]; then
    echo "  would delete branch  $br"; bdel=$((bdel+1)); continue
  fi
  # **失敗を件数から落とさない。** worktree 側は `失敗 N 件` を報告するのに、
  # ブランチ側だけ黙って「0 件削除」になると残骸が積もっても誰も気づけない
  if git branch -D "$br" >/dev/null 2>&1; then
    bdel=$((bdel+1))
  else
    echo "  FAILED branch $br （手動で git branch -D してください）" >&2
    bfail=$((bfail+1))
  fi
done < <(git branch --list 'agent-*' --format='%(refname:short)' 2>/dev/null)

[ "$DRY" = "1" ] || git worktree prune 2>/dev/null

# **必ず件数を報告する**（silent skip で「片付いたつもり」を作らない）
printf 'agent worktree: %d 件%s / 保持 %d 件 / 失敗 %d 件、agent-* ブランチ: %d 件%s / 失敗 %d 件\n' \
  "$removed" "$([ "$DRY" = 1 ] && echo ' (dry-run)' || echo ' 削除')" \
  "$kept" "$failed" \
  "$bdel" "$([ "$DRY" = 1 ] && echo ' (dry-run)' || echo ' 削除')" "$bfail"
exit 0
