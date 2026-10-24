#!/usr/bin/env bash
# review-snapshot.sh save|check|diff|tree — レビューした時点の作業ツリーを記録し、その後に変わった分を出す
# （GitHub issue #276）
#
# Phase 6 の self-review の後に入った変更（ユーザーの判断で入れた修正・別の決定の反映）は、
# G-V ループの再レビュー（auto-fix の対象だけ）を通らないまま Phase 7 で締められていた。
# 実測: 仕様書の改訂で、レビュー後の変更が原因の食い違いが 6 件、人の精読で見つかった。
#
#   save   作業ツリー（未追跡ファイルを含む。.gitignore は尊重）の tree を作り、git dir に記録する
#          ref も index も動かさない（一時 index に add して write-tree するだけ）
#   check  記録した tree と今の作業ツリーを比べ、変わったファイルと行数を出す:
#            snapshot=missing            記録が無い（Phase 6 が走らなかった等）
#            changed_files=N / changed_lines=M と、変わったファイルごとの `<追加>\t<削除>\t<path>`
#            untracked_files=K           変わったファイルのうち今は未追跡のもの。self-review の diff は未追跡を
#                                        含まないので、`--since` で回し直しても見ない（GitHub issue #313）
#   diff   check と同じ 2 つの tree の patch を出す（未追跡の新規ファイルも入る。`git diff <tree>` では
#          作業ツリー側の未追跡が落ちる）。Phase 6.9 が回し直すかを変更の中身で決めるため（GitHub issue #304）。
#          記録が無い・比べられないときは check と同じ `snapshot=missing` / `snapshot=unavailable`
#   tree   save と同じ tree を作って `snapshot=<tree>` を出すだけで、記録しない。G-V ループ（gv-loop.py）が
#          ループの起点と各回の修正前を自分の状態に持つため（GitHub issue #310）
#
# 記録先は作業ツリーごとの git dir（worktree ごとに分かれる）。出力は常に exit 0（判定できないときも
# Phase 7 を止めない）。git でないときは `snapshot=unavailable` を出す。
set -uo pipefail

mode="${1:-}"
gd=$(git rev-parse --absolute-git-dir 2>/dev/null) || gd=""
if [ -z "$gd" ]; then
  echo "snapshot=unavailable"
  exit 0
fi
store="$gd/feature-dev-review-snapshot"

current_tree() {
  local idx tmp tree
  idx=$(git rev-parse --git-path index)
  tmp=$(mktemp "${TMPDIR:-/tmp}/fd-snap-index.XXXXXX") || return 1
  # 今の index を種にすると add -A が速い（中身の正しさは add -A が保証する）。
  # -p で index の mtime を保つ: git は index より新しくないエントリを stat（サイズと mtime の秒）だけで
  # 「変わっていない」と読む。コピーで mtime を今にすると、同じ秒に同じサイズへ書き換えたファイルを見落とす
  if [ -f "$idx" ]; then
    cp -p "$idx" "$tmp"
  else
    rm -f "$tmp"
  fi
  if GIT_INDEX_FILE="$tmp" git add -A -- . >/dev/null 2>&1 \
     && tree=$(GIT_INDEX_FILE="$tmp" git write-tree 2>/dev/null); then
    rm -f "$tmp"
    printf '%s' "$tree"
    return 0
  fi
  rm -f "$tmp"
  return 1
}

case "$mode" in
  save|tree)
    # add -A はリポジトリ全体が対象なので、作業ツリーのルートで走らせる
    cd "$(git rev-parse --show-toplevel)" || { echo "snapshot=unavailable"; exit 0; }
    if tree=$(current_tree); then
      if [ "$mode" = save ]; then
        printf '%s\n' "$tree" > "$store"
      fi
      echo "snapshot=$tree"
    else
      echo "snapshot=unavailable"
    fi
    ;;
  check|diff)
    cd "$(git rev-parse --show-toplevel)" || { echo "snapshot=unavailable"; exit 0; }
    if [ ! -f "$store" ]; then
      echo "snapshot=missing"
      exit 0
    fi
    old=$(head -1 "$store")
    if ! git cat-file -e "${old}^{tree}" 2>/dev/null || ! new=$(current_tree); then
      echo "snapshot=unavailable"
      exit 0
    fi
    if [ "$mode" = diff ]; then
      git diff "$old" "$new" 2>/dev/null || true
      exit 0
    fi
    # rename は両側に分けて数える（`untracked_files=` と単位を揃える。`mv` した回に「全部未追跡」と読ませない）
    stat=$(git diff --no-renames --numstat "$old" "$new" 2>/dev/null || true)
    files=0; lines=0
    if [ -n "$stat" ]; then
      files=$(printf '%s\n' "$stat" | wc -l | tr -d ' ')
      # バイナリは `-` で数えられないので 0 として足す
      lines=$(printf '%s\n' "$stat" | awk -F'\t' '{ a = ($1 == "-") ? 0 : $1; d = ($2 == "-") ? 0 : $2; s += a + d } END { print s + 0 }')
    fi
    untracked=0
    if [ -n "$stat" ]; then
      # numstat のパスは rename の表記と引用符を含みうるので、名前は -z で取り直して突き合わせる
      untracked=$(comm -12 \
        <(git diff --no-renames --name-only -z "$old" "$new" 2>/dev/null | tr '\0' '\n' | sort -u) \
        <(git ls-files --others --exclude-standard -z 2>/dev/null | tr '\0' '\n' | sort -u) | grep -c . || true)
    fi
    echo "snapshot=$old"
    echo "changed_files=$files"
    echo "changed_lines=$lines"
    echo "untracked_files=${untracked:-0}"
    if [ -n "$stat" ]; then
      printf '%s\n' "$stat"
    fi
    ;;
  *)
    echo "usage: review-snapshot.sh save|check|diff|tree" >&2
    exit 2
    ;;
esac
exit 0
