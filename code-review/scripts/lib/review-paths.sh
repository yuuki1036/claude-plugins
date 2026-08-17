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

# Event Bus のログ（`.claude/events.jsonl`）の実在パスを配列 REVIEW_EVENT_LOGS に入れる。
#
# **候補は 2 つある。** `publish-review-event.sh` は `--git-common-dir` の親へ書き、
# 上の `review_main_root` は `git worktree list` から導く。通常の worktree では一致するが
# submodule / `--separate-git-dir` では食い違うため、**読み側は両方を候補にする**
# （片方しか見ないと「書けているのに読めない」で検出が silent に死ぬ）。
#
# **パスは配列で持つ。** 空白区切り文字列に畳んで未クォート展開すると、空白を含む
# リポジトリパス（macOS の `~/My Drive/...` 等）で word splitting により壊れ、
# 「データが無い」という**誤った断定**を返す。実測で両新規スクリプトが再現した。
# 呼び出し側は `${REVIEW_EVENT_LOGS[@]+"${REVIEW_EVENT_LOGS[@]}"}` で展開すること
# （bash 3.2 + `set -u` では空配列の素の展開が落ちる）。
review_event_logs() {
  REVIEW_EVENT_LOGS=()
  local roots=() gcd r
  gcd=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
  if [ -n "$gcd" ]; then
    r=$(cd "$gcd/.." 2>/dev/null && pwd)
    [ -n "$r" ] && roots+=("$r")
  fi
  r=$(review_main_root 2>/dev/null) && [ -n "$r" ] && [ "$r" != "${roots[0]:-}" ] && roots+=("$r")
  local root
  for root in ${roots[@]+"${roots[@]}"}; do
    [ -f "$root/.claude/events.jsonl" ] && REVIEW_EVENT_LOGS+=("$root/.claude/events.jsonl")
  done
  [ ${#REVIEW_EVENT_LOGS[@]} -gt 0 ]
}

# diff ファイルの突合キーを 2 本出力する（`<digest> <files-key>`。算出不能なら空 + rc=1）。
#
# **2 本ある理由**: `diff_digest`（全文の cksum）は**同一 skill の再実行でしか一致しない**。
# review は `gh pr diff`、self-review は `git diff BASE..HEAD` + `--cached` + unstaged の
# **3 本連結**で diff を作るため、同じ変更でもバイト列が違う（実測: 同一 head の PR で
# `1462260100-1256` vs `2713407599-105966`）。skill を跨ぐ重複を拾うには**弱いキー**が要る。
#
# `files-key` は「変更ファイルパスの集合」だけを正規化したもの。連結や index 行の差、
# ハンクの分かれ方に影響されない代わりに、**別内容の変更でも一致しうる**（＝疑いどまり）。
# 呼び出し側は両者を区別して扱うこと。
review_diff_keys() {
  local f="$1"
  [ -s "$f" ] || return 1
  local digest files
  digest=$(cksum < "$f" 2>/dev/null | awk '{print $1"-"$2}')
  # `diff --git a/X b/X` の b 側パスを拾って一意化・ソートしてから cksum にかける。
  # 連結 diff で同じファイルが 2 回現れても集合としては 1 つに畳まれる
  files=$(awk '/^diff --git /{print $NF}' "$f" 2>/dev/null | sed 's|^b/||' | sort -u | cksum | awk '{print $1"-"$2}')
  [ -n "$digest" ] || return 1
  printf '%s %s' "$digest" "$files"
}

# review_path <diff|prctx|timing|agentctx|oracles>
review_path() {
  local kind="$1" suffix=""
  [ -n "${REVIEW_PR:-}" ] && suffix="-pr${REVIEW_PR}"
  case "$kind" in
    diff)   printf '%s/review-diff-%s%s.diff' "$REVIEW_TMPROOT" "$REVIEW_SLUG" "$suffix" ;;
    prctx)  printf '%s/review-prctx-%s%s.md'  "$REVIEW_TMPROOT" "$REVIEW_SLUG" "$suffix" ;;
    timing) printf '%s/review-start-%s%s'     "$REVIEW_TMPROOT" "$REVIEW_SLUG" "$suffix" ;;
    # oracles: 機械層（`run-oracles.sh`）の出力全文。digest は先頭数十行に切るので、
    # 全文を読みたい agent / 人間のためにパスを配る（GitHub issue #137）
    oracles) printf '%s/review-oracles-%s%s.log' "$REVIEW_TMPROOT" "$REVIEW_SLUG" "$suffix" ;;
    # agentctx: 全 agent 共通の可変部（実値集合）。オーケストレーターが 1 回書き、
    # 各 agent はパスを受け取って自分で Read する（orchestration-guide.md `## 3.5`）
    agentctx) printf '%s/review-agentctx-%s%s.md' "$REVIEW_TMPROOT" "$REVIEW_SLUG" "$suffix" ;;
    *) echo "FATAL: 未知の一時ファイル種別: $kind" >&2; return 2 ;;
  esac
}
