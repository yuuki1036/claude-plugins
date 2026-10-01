#!/usr/bin/env bash
# session-branch.sh — セッションごとの「直前に見たブランチ」の記録（GitHub issue #270）
#
# branch-drift-record.sh（PostToolUse）と branch-drift-guard.sh（PreToolUse）が source する。
# 記録先は作業ツリーの git dir（worktree ごとに分かれる）配下で、キーは hook 入力の session_id。
# `.claude/session-context.md` を照合元にしない — チェックアウト単位のファイルで、最後に
# start したセッションが上書きするため、共有チェックアウトでは別セッションの値になる。

# 作業ツリーの現在のブランチ。detached なら `detached:<sha>`、git でなければ空
session_branch_current() {
  local dir=$1 b
  if b=$(git -C "$dir" symbolic-ref --short -q HEAD 2>/dev/null); then
    printf '%s' "$b"
  elif b=$(git -C "$dir" rev-parse --short HEAD 2>/dev/null); then
    printf 'detached:%s' "$b"
  fi
  # 両方失敗した（git でない）ときも 0 で返す。`VAR=$(...)` の中で非ゼロを返すと、呼び出し側の
  # set -e（safe-hook）が発動して ERR trap → exit 0 になり、「該当なし」と区別できない
  return 0
}

# 記録ファイルのパス。session_id が安全な文字だけでないとき・git でないときは空
session_branch_file() {
  local dir=$1 sid=$2 gd
  case "$sid" in ''|*[!A-Za-z0-9_-]*) return 0 ;; esac
  gd=$(git -C "$dir" rev-parse --absolute-git-dir 2>/dev/null) || return 0
  [ -n "$gd" ] || return 0
  printf '%s/claude-session-branch/%s' "$gd" "$sid"
}

session_branch_write() {
  local file=$1 branch=$2
  mkdir -p "${file%/*}" 2>/dev/null || return 0
  printf '%s\n' "$branch" > "$file" 2>/dev/null || true
}
