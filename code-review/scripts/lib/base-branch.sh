#!/usr/bin/env bash
# base branch（diff を取る相手のブランチ名）と、その決め方を決める（正本 / GitHub issue #274）。
# review-guide（PR 未作成時）・self-review・comment-polish が使う。diff の起点（分岐点のコミット）を
# 決めるのは lib/diff-base.sh で、ここはその入力になるブランチ名だけを決める。
#
# 優先順:
#   1. 引数で明示されたもの                                    → source=arg
#   2. 現在のブランチを作ったときの reflog                       → source=reflog
#      `git checkout -b X <base>` / `git worktree add -b X <path> <base>` は `branch: Created from <base>`
#      を残す。起点を付けずに作ると `Created from HEAD` になるので、HEAD の reflog の
#      `checkout: moving from <Y> to X`（作ったときにいたブランチ）を使う
#   3. origin の default branch                               → source=default
# 統合ブランチから切ったブランチで default branch（main）を掴むと、統合ブランチに入った他の変更まで
# diff に混ざる（editor でタスクの diff だけを見たい、が動機）。reflog は期限切れ（既定 90 日）や、
# fetch で入ってきたブランチでは残っていないので、そのときは 3 に落ちる。
# reflog の候補は「ローカルか origin にブランチとして実在し、現在のブランチ自身でない」ものだけ採る
# （sha・HEAD・自分の upstream を掴まない）。
#
# 使い方:
#   . "$HERE/lib/base-branch.sh"
#   review_base_branch "$ARG" || { echo "FATAL: ..."; exit 2; }   # どれも決まらなければ 2
#   review_refresh_base "$REVIEW_BASE_BRANCH"   # origin から取り直し、ローカルを早送りできれば進める
#   bash lib/base-branch.sh [--refresh] [<base>]   # `base_branch=` / `base_source=` / `base_refresh=` を出す
# 設定する変数:
#   REVIEW_BASE_BRANCH  ブランチ名（`origin/` を付けない）
#   REVIEW_BASE_SOURCE  arg / reflog / default
#   REVIEW_BASE_REFRESH review_refresh_base の結果（下の関数の説明）

# reflog の起点の名前を、実在するブランチ名に寄せる。採れなければ空
_review_base_candidate() {
  local c="$1" cur="$2"
  c=${c#refs/heads/}
  c=${c#refs/remotes/origin/}
  c=${c#origin/}
  if [ -z "$c" ] || [ "$c" = "HEAD" ] || [ "$c" = "$cur" ]; then
    return 0
  fi
  if git show-ref --verify -q "refs/heads/$c" || git show-ref --verify -q "refs/remotes/origin/$c"; then
    printf '%s' "$c"
  fi
  return 0
}

review_base_branch() {
  local explicit="${1:-}" cur from c
  REVIEW_BASE_BRANCH=""; REVIEW_BASE_SOURCE=""
  if [ -n "$explicit" ]; then
    REVIEW_BASE_BRANCH="$explicit"; REVIEW_BASE_SOURCE="arg"
    return 0
  fi
  cur=$(git symbolic-ref --short -q HEAD 2>/dev/null || true)
  if [ -n "$cur" ]; then
    # reflog は新しい順なので、作成時の行は最後
    from=$(git reflog show --format=%gs "refs/heads/$cur" 2>/dev/null | tail -1 | sed -n 's/^branch: Created from //p' || true)
    if [ "$from" = "HEAD" ]; then
      # ブランチ名は空白を含められないので、`checkout: moving from <Y> to <X>` は空白区切りで読める
      from=$(git reflog show --format=%gs HEAD 2>/dev/null \
        | awk -v c="$cur" '$1 == "checkout:" && $2 == "moving" && $3 == "from" && $5 == "to" && $6 == c { y = $4 } END { print y }' || true)
    fi
    c=$(_review_base_candidate "$from" "$cur")
    if [ -n "$c" ]; then
      REVIEW_BASE_BRANCH="$c"; REVIEW_BASE_SOURCE="reflog"
      return 0
    fi
  fi
  c=$(git symbolic-ref --short -q refs/remotes/origin/HEAD 2>/dev/null || true)
  c=${c#origin/}
  if [ -z "$c" ]; then
    c=$(git remote show origin 2>/dev/null | sed -n 's/.*HEAD branch: //p' || true)
  fi
  if [ -z "$c" ] || [ "$c" = "(unknown)" ]; then
    return 2
  fi
  REVIEW_BASE_BRANCH="$c"; REVIEW_BASE_SOURCE="default"
  return 0
}

# origin から base を取り直し、ローカルの base を早送りできれば進める。結果を REVIEW_BASE_REFRESH に入れる:
#   up-to-date / fast-forwarded:<N>（N commits 進めた）/ behind-checked-out:<N>（別の作業ツリーで
#   チェックアウト中なので進めていない）/ diverged（ローカルに未 push のコミットがある）/ no-local /
#   not-a-branch / not-on-origin（ローカルにだけあるブランチ）/ no-origin / fetch-failed
# ローカルを書き換えるのは早送りだけ。diff の起点はこの結果に関係なく lib/diff-base.sh が HEAD に近い方を選ぶ
review_refresh_base() {
  local b="$1" old new n
  REVIEW_BASE_REFRESH=""
  if ! git remote get-url origin >/dev/null 2>&1; then
    REVIEW_BASE_REFRESH="no-origin"; return 0
  fi
  # `--base HEAD~3` のようなブランチでない指定は取り直す対象が無い
  if ! git show-ref --verify -q "refs/heads/$b" && ! git show-ref --verify -q "refs/remotes/origin/$b"; then
    REVIEW_BASE_REFRESH="not-a-branch"; return 0
  fi
  if ! git fetch -q origin "+refs/heads/$b:refs/remotes/origin/$b" 2>/dev/null; then
    # 取り直せないのが「origin にそのブランチが無い」からなら、ローカルだけのブランチ（未 push の統合
    # ブランチ等）で、取り直す相手がそもそも無い。通信の失敗とは分けて出す
    if git show-ref --verify -q "refs/remotes/origin/$b"; then
      REVIEW_BASE_REFRESH="fetch-failed"
    else
      REVIEW_BASE_REFRESH="not-on-origin"
    fi
    return 0
  fi
  if ! git show-ref --verify -q "refs/heads/$b"; then
    REVIEW_BASE_REFRESH="no-local"; return 0
  fi
  old=$(git rev-parse "refs/heads/$b")
  new=$(git rev-parse "refs/remotes/origin/$b")
  if [ "$old" = "$new" ]; then
    REVIEW_BASE_REFRESH="up-to-date"; return 0
  fi
  if ! git merge-base --is-ancestor "$old" "$new"; then
    REVIEW_BASE_REFRESH="diverged"; return 0
  fi
  n=$(git rev-list --count "$old..$new")
  if git worktree list --porcelain | grep -qxF "branch refs/heads/$b"; then
    REVIEW_BASE_REFRESH="behind-checked-out:$n"; return 0
  fi
  if git update-ref "refs/heads/$b" "$new" "$old"; then
    REVIEW_BASE_REFRESH="fast-forwarded:$n"
  else
    REVIEW_BASE_REFRESH="fetch-failed"
  fi
  return 0
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  _refresh=0
  if [ "${1:-}" = "--refresh" ]; then
    _refresh=1; shift
  fi
  review_base_branch "${1:-}" || { echo "FATAL: base branch を決められない（origin の default branch も引けない）。base branch を指定して呼び直す" >&2; exit 2; }
  echo "base_branch=${REVIEW_BASE_BRANCH}"
  echo "base_source=${REVIEW_BASE_SOURCE}"
  if [ "$_refresh" = "1" ]; then
    review_refresh_base "$REVIEW_BASE_BRANCH"
    echo "base_refresh=${REVIEW_BASE_REFRESH}"
  fi
fi
