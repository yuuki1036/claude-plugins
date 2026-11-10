#!/usr/bin/env bash
# exploration-file.sh path|clear — Phase 2 の explorer の結果を Phase 4 の architect に渡す作業ファイル
# （GitHub issue #427）
#
#   path   作業ファイルの絶対パスを `EXPLORATION_PATH=<path>` で出す。前の run の残りも消す
#          （Write は読んでいない既存のファイルを上書きできず、立て直しで読むと古い結果が混ざる）
#   clear  作業ファイルを消す。Phase 4 の後と Phase 5 Normal Mode の 2. が呼ぶ
#
# パスの正本はこのスクリプト。phase ファイルに式を書き下ろすと、1 か所だけ変えたときに
# clear が黙って空振りし、残ったファイルが Phase 5.5 の判定とコミットに入る。
# 作業ツリーの中（`.claude/`）に置くのは、外（/tmp 等）だと作業ディレクトリの外への Write が承認待ちになり、
# background の architect の Read が拒否されると探索結果が渡らないまま進むため。
# git でないディレクトリでは cwd を起点にする。path / clear は常に exit 0（手順を止めない）。引数の誤りだけ exit 2。
set -uo pipefail

top=$(git rev-parse --show-toplevel 2>/dev/null) || top=$(pwd)
file="$top/.claude/.feature-dev-exploration.md"

case "${1:-}" in
  path)
    rm -f "$file"
    mkdir -p "$top/.claude" 2>/dev/null
    echo "EXPLORATION_PATH=$file"
    ;;
  clear)
    rm -f "$file"
    echo "cleared=$file"
    ;;
  *)
    echo "usage: exploration-file.sh path|clear" >&2
    exit 2
    ;;
esac
