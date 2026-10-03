#!/usr/bin/env bash
# review-guide の読み順を記録する（GitHub issue #274 の続き / guide-diff mod の入力）
#
# review-guide を PR 前（base モード）で回した後、editor に移らずタスクの diff だけを読み順に送れるように、
# 読み順と比較先（分岐点のコミット）を作業ツリーごとの git dir に 1 ファイルで残す。読むのは code-review の
# mod（hooks/guide-diff.tsx の `/guide-diff`）で、mods が無い環境ではこのファイルは読まれないだけで害はない。
#
# 使い方:
#   guide-order.sh --diff-base <commit> --base <branch> [--source arg|reflog|default] \
#     --read <path>... [--skim <path>...] [--skip <path>...]
#   （--read / --skim / --skip の後ろのパスは、次の -- オプションまでその群に入る。--read は実装の流れ順）
# 出力: `guide_order=<書いたファイルの絶対パス>`。引数の誤り・比較先が commit でない・git でないときは exit 2
set -uo pipefail

command -v jq >/dev/null 2>&1 || { echo "FATAL: jq が要る（記録の JSON を組む）" >&2; exit 2; }

diff_base=""; base=""; source="unknown"; group=""
files_json='[]'
while [ $# -gt 0 ]; do
  case "$1" in
    --diff-base) [ $# -ge 2 ] || { echo "FATAL: --diff-base に値が要る" >&2; exit 2; }; diff_base="$2"; shift 2 ;;
    --base)      [ $# -ge 2 ] || { echo "FATAL: --base に値が要る" >&2; exit 2; }; base="$2"; shift 2 ;;
    --source)    [ $# -ge 2 ] || { echo "FATAL: --source に値が要る" >&2; exit 2; }; source="$2"; shift 2 ;;
    --read)  group="read"; shift ;;
    --skim)  group="skim"; shift ;;
    --skip)  group="skip"; shift ;;
    --*) echo "FATAL: 未知の引数: $1" >&2; exit 2 ;;
    *)
      if [ -z "$group" ]; then
        echo "FATAL: パスの前に --read / --skim / --skip のどれかを置く: $1" >&2; exit 2
      fi
      # パスは外部入力（ブランチの中身が決める）なので jq に --arg で渡す
      files_json=$(jq -c --arg p "$1" --arg g "$group" '. + [{path: $p, group: $g}]' <<< "$files_json")
      shift ;;
  esac
done

if [ -z "$diff_base" ] || [ -z "$base" ]; then
  echo "FATAL: --diff-base と --base は必須" >&2; exit 2
fi
if [ "$(jq 'length' <<< "$files_json")" = "0" ]; then
  echo "FATAL: ファイルが 1 つも無い（--read で精読のファイルを渡す）" >&2; exit 2
fi
gd=$(git rev-parse --absolute-git-dir 2>/dev/null) || { echo "FATAL: git の作業ツリーではない" >&2; exit 2; }
commit=$(git rev-parse --verify -q "${diff_base}^{commit}") || { echo "FATAL: 比較先が commit として解決できない: ${diff_base}" >&2; exit 2; }
head=$(git rev-parse -q --verify HEAD 2>/dev/null || echo "")

out="$gd/claude-review-guide.json"
jq -n --arg base "$base" --arg source "$source" --arg diff_base "$commit" --arg head "$head" \
  --arg created "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --argjson files "$files_json" \
  '{schema: 1, base_branch: $base, base_source: $source, diff_base: $diff_base, head: $head,
    created_at: $created, files: $files}' > "$out" || { echo "FATAL: 書き込めない: $out" >&2; exit 2; }
echo "guide_order=$out"
exit 0
