#!/usr/bin/env bash
# self-review の diff の起点を決める（正本）。triage-signals.sh と md-prose-lines.sh が共有する —
# 2 箇所で起点がずれると、Phase 0 の規模と Markdown 推敲の対象行が別の diff を指す。
#
# **ローカルの base ref だけで取らない**（GitHub issue #253）。ローカルの main が origin/main より
# 遅れていると、origin/main から切ったブランチの diff に、他で取り込まれた変更まで混ざる
# （実測: 変更 4 files が 161 files に膨張。ローカルの main は 135 commits 遅れていた）。
#
# 起点は HEAD と base の分岐点（merge-base）。ローカルの `<base>` と `origin/<base>` の両方で取り、
# **HEAD に近い方**を使う。origin を無条件に優先しないのは、ローカルの base に未 push のコミットが
# あり、そこから切ったブランチでは origin 側の分岐点が古く、未 push のコミットが混ざるから
# （逆向きの膨張）。2 つの分岐点に祖先関係が無ければローカルを使う。
# 2 ドットの直接比較（`base..HEAD`）にもしない — ブランチを切った後に base が進むと、
# base 側の新しいコミットが逆向きの差分として混ざる。
#
# 使い方:
#   . "$HERE/lib/diff-base.sh"
#   review_diff_base "$BASE" || { echo "FATAL: ..."; exit 2; }   # どちらの ref も解決できなければ 2
# 設定する変数:
#   REVIEW_BASE_REF     使った ref（`<base>` か `origin/<base>`）
#   REVIEW_BASE_COMMIT  diff の起点のコミット（分岐点。共通の履歴が無ければ ref の先端）
#   REVIEW_BASE_BEHIND  origin 側を使い、かつローカルの `<base>` もあるとき、ローカルに無い
#                       origin 側のコミット数。それ以外は空

review_diff_base() {
  local base="$1" ref full c mb
  REVIEW_BASE_REF=""; REVIEW_BASE_COMMIT=""; REVIEW_BASE_BEHIND=""
  for ref in "$base" "origin/$base"; do
    full="$ref"
    if [ "$ref" = "origin/$base" ]; then
      # ブランチ名のときだけ remote 側を見る。`HEAD~3` を `refs/remotes/origin/HEAD~3` として
      # 解決させると、origin の先端から数えた別のコミットを起点に取る
      git show-ref --verify -q "refs/remotes/origin/$base" || continue
      full="refs/remotes/origin/$base"
    fi
    c=$(git rev-parse --verify -q "${full}^{commit}") || continue
    mb=$(git merge-base HEAD "$c" 2>/dev/null) || mb="$c"
    if [ -z "$REVIEW_BASE_COMMIT" ] \
       || { [ "$mb" != "$REVIEW_BASE_COMMIT" ] && git merge-base --is-ancestor "$REVIEW_BASE_COMMIT" "$mb"; }; then
      REVIEW_BASE_REF="$ref"; REVIEW_BASE_COMMIT="$mb"
    fi
  done
  if [ -z "$REVIEW_BASE_COMMIT" ]; then
    return 2
  fi
  if [ "$REVIEW_BASE_REF" = "origin/$base" ] && git rev-parse --verify -q "${base}^{commit}" >/dev/null; then
    REVIEW_BASE_BEHIND=$(git rev-list --count "${base}..refs/remotes/origin/${base}")
  fi
  return 0
}
