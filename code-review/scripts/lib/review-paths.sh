#!/usr/bin/env bash
# レビュー用一時ファイルのパス導出（正本）。
#
# **この式を他所へ複製しないこと。** 作成側と削除側でパスが食い違うと一時ファイルが
# 恒久的に残る。以前は 4 スクリプト + ガイドの bash スニペットに同じ式が散っており、
# `fetch-pr-context.sh` だけ空値ハンドリングが違う（`-pr${1:-0}` vs `${PR:+-pr$PR}`）
# という乖離が実際に発生していた。
#
# 使い方（各スクリプトの冒頭で source する）:
#   . "$(dirname "$0")/lib/review-paths.sh"
#   review_paths_init "$PR"          # PR 番号（空可）を検証して SLUG / TMPROOT を用意
#   echo "$(review_path diff)"       # → $TMPROOT/review-diff-<slug>[-prN].diff
#
# 識別子は「今いる worktree のルート」(+ PR 番号)。`--git-common-dir` は全 worktree で
# 同じ値を返すので識別子にならず、ブランチ名は detached HEAD で "HEAD" に潰れる。
# 導出に失敗したときの縮退先は「別ファイル = 欠測」であって「他セッションの値」ではない。

# 一時ファイルは 0700 の専用ディレクトリに閉じ込める。
# `${TMPDIR:-/tmp}` 直下に 0644 の固定名で置くと、TMPDIR が無い環境（Linux / CI の多く）
# では world-writable な /tmp に落ち、symlink 先置きによる上書きと未コミットコードの
# 読み取りの両方が成立する。専用 dir 一枚で両方塞げる。
review_paths_init() {
  local pr="${1:-}"
  # --pr は数値のみ。パス組み立てに使う値なので、ここで弾かないと
  # `--pr ../../foo` のような値が書込・削除パスへそのまま流れる
  if [ -n "$pr" ]; then
    case "$pr" in
      ''|*[!0-9]*) echo "FATAL: --pr は数値のみ指定できる（受領: '$pr'）" >&2; return 2 ;;
    esac
  fi
  REVIEW_PR="$pr"
  REVIEW_WT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  REVIEW_SLUG=$(printf %s "$REVIEW_WT" | cksum | cut -d' ' -f1)
  REVIEW_TMPROOT="${TMPDIR:-/tmp}/claude-code-review-$(id -u)"
  mkdir -p "$REVIEW_TMPROOT" 2>/dev/null && chmod 700 "$REVIEW_TMPROOT" 2>/dev/null
  umask 077
  return 0
}

# メイン作業ツリーのルートを返す（導出できなければ空文字 + rc=1）。
#
# **`--git-common-dir` の親を使わないこと**（GitHub issue #113 のセルフレビュー指摘）。
# 通常の worktree では一致するが、submodule では `<super>/.git/modules` を、
# `--separate-git-dir` では gitdir 置き場の親を返し、**リポジトリ外や `.git` 内部**を指す。
# `git worktree list --porcelain` の 1 行目は linked worktree からでもメイン側を返す。
#
# **導出失敗時の縮退は「空」であって `pwd` ではない。** review は EnterWorktree 後に
# 呼ばれるため `pwd` は worktree 側であり、`pwd` に倒すと「メインリポジトリのパス」を
# 名乗る誤値が agent プロンプトへ注入される（#113 の失敗が無シグナルで再発する）。
# 呼び出し側は空を受け取ったら**その行ごと出力しない**こと。
#
# 注: 上の `review_paths_init` が一時ファイル名に `--show-toplevel` を使うのとは
# 目的が違う（あちらは worktree ごとに異なる識別子が要る。こちらは全 worktree で
# 同じメインルートを指す必要がある）。両者を取り違えないこと。
review_main_root() {
  local root
  root=$(git worktree list --porcelain 2>/dev/null \
    | awk 'NR==1 && $1=="worktree" {print $2; exit}')
  [ -n "$root" ] && [ -d "$root" ] || return 1
  printf '%s' "$root"
}

# review_path <diff|prctx|timing>
review_path() {
  local kind="$1" suffix=""
  [ -n "${REVIEW_PR:-}" ] && suffix="-pr${REVIEW_PR}"
  case "$kind" in
    diff)   printf '%s/review-diff-%s%s.diff' "$REVIEW_TMPROOT" "$REVIEW_SLUG" "$suffix" ;;
    prctx)  printf '%s/review-prctx-%s%s.md'  "$REVIEW_TMPROOT" "$REVIEW_SLUG" "$suffix" ;;
    timing) printf '%s/review-start-%s%s'     "$REVIEW_TMPROOT" "$REVIEW_SLUG" "$suffix" ;;
    *) echo "FATAL: 未知の一時ファイル種別: $kind" >&2; return 2 ;;
  esac
}
