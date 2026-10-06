#!/usr/bin/env bash
# branch-setup.sh — start / issue-create がブランチを切るときの状態取得と worktree 作成（GitHub issue #280）
#
# 手順の正本は references/branch-setup.md。ここは決定的に書ける部分（状態の取得・worktree の作成・
# 未追跡の .env* の複製・依存を入れるコマンドの検出）だけを持つ。依存のインストールは時間がかかり
# 失敗の扱いを会話で決めたいので、コマンドを出すだけで実行はしない。
#
# 使い方:
#   branch-setup.sh status
#     → in_worktree=0|1 / dirty=<未コミットの変更の行数> / branch=<今のブランチ> /
#       main_root=<メインのチェックアウトの絶対パス> / default_branch=<既定ブランチ名。不明なら空>
#   branch-setup.sh worktree <branch> --name <dir 名> [--base <ref>]
#     → <main_root>/.claude/worktrees/<dir 名> に <branch> の worktree を作り、次を出す:
#       worktree=<絶対パス> / branch=<branch> / base=<ref。既存ブランチを使った回は -> /
#       created=1|0（0 は同じパスに worktree が既にあった）/ excluded=1|0（.claude/worktrees/ を
#       info/exclude に足したか）/ env_copied=<相対パス>（0 行以上）/ install=<コマンド>（0 行以上）
#
# 終了コード: 0 成功 / 1 作成できなかった（git の失敗・パスの衝突）/ 2 引数・前提の誤り

set -euo pipefail

die() { echo "ERROR: $2" >&2; exit "$1"; }

git rev-parse --git-dir >/dev/null 2>&1 || die 2 "git リポジトリの中で実行する"

# メインのチェックアウトの git dir（worktree の中からでもメイン側を指す）
common_dir() {
  local d
  if d=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null); then
    printf '%s' "$d"
  else
    # --path-format は git 2.31 から。古い git は相対パスを返すので cwd 基準で解決する
    (cd "$(git rev-parse --git-common-dir)" && pwd -P)
  fi
}

COMMON=$(common_dir)
# common dir が `<root>/.git` でない（submodule など）ときは親を root と見なせない
if [ "$(basename "$COMMON")" = ".git" ]; then
  MAIN_ROOT=$(dirname "$COMMON")
else
  MAIN_ROOT=$(git rev-parse --show-toplevel)
fi

default_branch() {
  local b
  if b=$(git symbolic-ref --short -q refs/remotes/origin/HEAD 2>/dev/null); then
    printf '%s' "${b#origin/}"
    return 0
  fi
  for b in main master; do
    if git show-ref --verify -q "refs/heads/${b}" || git show-ref --verify -q "refs/remotes/origin/${b}"; then
      printf '%s' "$b"
      return 0
    fi
  done
  return 0
}

cmd_status() {
  local gd in_wt=0 dirty br
  gd=$(git rev-parse --absolute-git-dir)
  if [ "$gd" != "$COMMON" ]; then in_wt=1; fi
  dirty=$(git status --porcelain | wc -l | tr -d ' ')
  br=$(git symbolic-ref --short -q HEAD || echo detached)
  echo "in_worktree=${in_wt}"
  echo "dirty=${dirty}"
  echo "branch=${br}"
  echo "main_root=${MAIN_ROOT}"
  echo "default_branch=$(default_branch)"
}

# メインのチェックアウトにある未追跡の .env* を worktree へ写す。追跡済みのものは checkout で
# 既に入っており、worktree 側に同名のファイルがあれば上書きしない
copy_env() {
  local dest=$1 f rel
  while IFS= read -r -d '' f; do
    rel=${f#"${MAIN_ROOT}"/}
    if git -C "$MAIN_ROOT" ls-files --error-unmatch -- "$rel" >/dev/null 2>&1; then continue; fi
    if [ -e "${dest}/${rel}" ]; then continue; fi
    mkdir -p "$(dirname "${dest}/${rel}")"
    cp -p "$f" "${dest}/${rel}"
    echo "env_copied=${rel}"
  done < <(find "$MAIN_ROOT" -maxdepth 3 \
             \( -name node_modules -o -name .git -o -path "${MAIN_ROOT}/.claude" \) -prune \
             -o -name '.env*' -type f -print0)
}

# lockfile から依存を入れるコマンドを決める。lockfile を書き換えない形を選ぶ（新しいブランチに
# 意図しない lockfile の差分を作らないため）。yarn は v1 と v2 以降でフラグが違うので素の install
detect_install() {
  local dir=$1
  if [ -f "${dir}/pnpm-lock.yaml" ]; then echo "install=pnpm install --frozen-lockfile"
  elif [ -f "${dir}/yarn.lock" ]; then echo "install=yarn install"
  elif [ -f "${dir}/bun.lock" ] || [ -f "${dir}/bun.lockb" ]; then echo "install=bun install --frozen-lockfile"
  elif [ -f "${dir}/package-lock.json" ]; then echo "install=npm ci"
  fi
  if [ -f "${dir}/uv.lock" ]; then echo "install=uv sync --frozen"; fi
  if [ -f "${dir}/poetry.lock" ]; then echo "install=poetry install --no-root"; fi
  if [ -f "${dir}/Gemfile.lock" ]; then echo "install=bundle install"; fi
  return 0
}

cmd_worktree() {
  local branch="" name="" base=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --name) [ $# -ge 2 ] || die 2 "--name に値が無い"; name=$2; shift 2 ;;
      --base) [ $# -ge 2 ] || die 2 "--base に値が無い"; base=$2; shift 2 ;;
      -*) die 2 "未知のオプション: $1" ;;
      *) [ -z "$branch" ] || die 2 "ブランチ名は 1 つだけ: $1"; branch=$1; shift ;;
    esac
  done
  [ -n "$branch" ] || die 2 "ブランチ名が無い"
  git check-ref-format --branch "$branch" >/dev/null 2>&1 || die 2 "ブランチ名として不正: ${branch}"
  # EnterWorktree の name と同じ文字種に絞る（パスの外へ出る名前を作らない）
  case "$name" in
    ''|.|..|*[!A-Za-z0-9._-]*) die 2 "--name は英数字と . _ - だけ: '${name}'" ;;
  esac

  local path="${MAIN_ROOT}/.claude/worktrees/${name}" created=1 excluded=0 used_base="-"

  if [ -e "$path" ]; then
    git worktree list --porcelain | grep -qxF "worktree ${path}" \
      || die 1 "${path} は既にあるが worktree ではない"
    created=0
  fi

  if ! git -C "$MAIN_ROOT" check-ignore -q ".claude/worktrees/${name}"; then
    mkdir -p "${COMMON}/info"
    echo ".claude/worktrees/" >> "${COMMON}/info/exclude"
    excluded=1
  fi

  if [ "$created" = 1 ]; then
    local err
    if git show-ref --verify -q "refs/heads/${branch}"; then
      err=$(git worktree add -q "$path" "$branch" 2>&1) || die 1 "git worktree add が失敗した: ${err}"
    else
      if [ -z "$base" ]; then
        local def
        def=$(default_branch)
        [ -n "$def" ] || die 2 "既定ブランチを決められない。--base で起点を指定する"
        if git rev-parse -q --verify "refs/remotes/origin/${def}" >/dev/null; then
          base="origin/${def}"
        else
          base=$def
        fi
      fi
      err=$(git worktree add -q --no-track -b "$branch" "$path" "$base" 2>&1) \
        || die 1 "git worktree add が失敗した: ${err}"
      used_base=$base
    fi
  fi

  echo "worktree=${path}"
  echo "branch=${branch}"
  echo "base=${used_base}"
  echo "created=${created}"
  echo "excluded=${excluded}"
  copy_env "$path"
  detect_install "$path"
}

case "${1:-}" in
  status) shift; cmd_status "$@" ;;
  worktree) shift; cmd_worktree "$@" ;;
  *) die 2 "使い方: branch-setup.sh status | worktree <branch> --name <dir 名> [--base <ref>]" ;;
esac
