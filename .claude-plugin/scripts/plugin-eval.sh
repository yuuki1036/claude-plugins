#!/usr/bin/env bash
# plugin-eval.sh — `claude plugin eval` の起動口 + 「どの内容に対して走らせたか」の記録
#
# 使い方:
#   bash .claude-plugin/scripts/plugin-eval.sh <plugin> [claude plugin eval の追加引数...]
#   bash .claude-plugin/scripts/plugin-eval.sh --fingerprint <plugin>   # 指紋だけ出す
#
# なぜ素の `claude plugin eval` を直接叩かないか:
#   pre-commit は「スキル本文を変えたのに eval を回していない」を止めたいが、eval の
#   実行ログ（`<plugin>/evals/results/`）は gitignore なので、mtime や存在では判定できない。
#   ここで eval を回した時点の**入力の指紋**を `<plugin>/evals/results/.last-eval` に残し、
#   pre-commit が同じ関数で指紋を取り直して突合する（指紋の算法はこのファイルだけが持つ）。
#
# 指紋の入力: `<plugin>/{skills,commands,agents,references,evals}` 配下の全ファイル内容
#   （`evals/results/` は除く）。eval の結果に効く入力だけを見る — hooks / scripts /
#   CHANGELOG を変えても eval は要求しない。**作業ツリーの内容**で取る（index ではない）。
#   eval が実際に読んだのは作業ツリーなので、eval 後に 1 文字でも直せば指紋がずれて
#   pre-commit が止める（= 直した後の状態を測り直させる）
#
# 既定フラグ:
#   --no-publish   … レポートを claude.ai に上げない（結果は手元の HTML で読む）
#   --trust-plugin … 自作プラグインなので初回の信頼確認を出さない
#   追加引数はそのまま `claude plugin eval` に渡す（`--runs 1` / `--case` / `--threshold` 等）
#
# 終了コード: `claude plugin eval` のものをそのまま返す（0 全 case 閾値以上 / 1 閾値未満あり /
#   2 コスト上限で中断）。`.last-eval` にも同じ値を書くので、閾値未満のまま commit しようと
#   すれば pre-commit が止める

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

usage() {
  echo "usage: $0 PLUGIN [claude plugin eval args...]" >&2
  echo "       $0 --fingerprint PLUGIN" >&2
  exit 2
}

# 指紋: 対象パス配下の（results/ を除く）全ファイルを**パス順**に cksum し、その一覧を
# さらに cksum する。`find` の出力順は FS 依存なので sort を挟む。ファイルが 1 つも無い
# ディレクトリ（agents/ が無い等）は find が非ゼロを返すので 2>/dev/null で握る
fingerprint() {
  local plugin="$1" dir
  local dirs=()
  for dir in skills commands agents references evals; do
    if [ -d "$REPO_ROOT/$plugin/$dir" ]; then dirs+=("$REPO_ROOT/$plugin/$dir"); fi
  done
  if [ ${#dirs[@]} -eq 0 ]; then
    echo "none"
    return 0
  fi
  (
    cd "$REPO_ROOT" &&
    find "${dirs[@]}" -type f -not -path "*/evals/results/*" 2>/dev/null \
      | LC_ALL=C sort \
      | while IFS= read -r f; do
          printf '%s ' "${f#"$REPO_ROOT"/}"
          cksum < "$f"
        done \
      | cksum | cut -d' ' -f1
  )
}

if [ $# -lt 1 ]; then usage; fi

if [ "$1" = "--fingerprint" ]; then
  [ $# -eq 2 ] || usage
  fingerprint "$2"
  exit 0
fi

PLUGIN="$1"; shift
if [ ! -f "$REPO_ROOT/$PLUGIN/.claude-plugin/plugin.json" ]; then
  echo "plugin-eval: $PLUGIN はプラグインではありません（.claude-plugin/plugin.json が無い）" >&2
  exit 2
fi
if [ ! -d "$REPO_ROOT/$PLUGIN/evals" ]; then
  echo "plugin-eval: $PLUGIN/evals/ が無い。まず 'cd $PLUGIN && claude plugin eval init --bare <case>' でケースを作る" >&2
  exit 2
fi
if ! command -v claude >/dev/null 2>&1; then
  echo "plugin-eval: claude CLI が PATH に無い" >&2
  exit 2
fi

# eval が読むのは実行時点の作業ツリーなので、指紋は**実行前**に取る（実行中に編集されたら
# 次の pre-commit でずれて止まる。それが望ましい）
FP="$(fingerprint "$PLUGIN")"

(cd "$REPO_ROOT/$PLUGIN" && claude plugin eval . --no-publish --trust-plugin "$@") && RC=0 || RC=$?

mkdir -p "$REPO_ROOT/$PLUGIN/evals/results"
{
  echo "fingerprint=$FP"
  echo "exit=$RC"
  echo "at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$REPO_ROOT/$PLUGIN/evals/results/.last-eval"

exit "$RC"
