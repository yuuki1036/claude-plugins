#!/usr/bin/env bash
# 変異テストの道具を探す（review-guide の読み合わせの締めの `変異テスト:` の行 / GitHub issue #307）。
#
# **宣言が先**: リポジトリのルートに `.claude/mutation-test.sh` が通常のファイルとしてあれば、それだけを
# 返して推測しない（`.claude/review-oracles.sh` と同じ流儀。何を回すかはプロジェクトが決める）。
# **推測は宣言が無いときだけ**で、ルートの設定ファイルだけを見る。下位のディレクトリ（monorepo の
# パッケージ）の設定は見ない。PATH 上の実行ファイルも見ない — 機械ごとに結果が変わり、そのプロジェクトが
# 道具を使っている印にもならない。
# **探すだけで回さない**（回すかは呼び出し元が利用者の承認を得て決める）。
#
# 使い方: detect-mutation-tool.sh（引数なし。引数があれば exit 2）
# 出力（stdout。引数エラーのほかは常に exit 0）:
#   mutation_tool=declared|inferred|none
#   declared=.claude/mutation-test.sh   … declared のときだけ
#   estimate=<値>                        … declared で、宣言に行頭の `# 所要の目安:` があるときだけ（最初の 1 行）
#   inferred=<道具><TAB><決め手のパス>   … inferred のとき。道具ごとに 1 行、stryker → mutmut → cargo-mutants の順。
#                                          パスはルートからの相対
set -uo pipefail

if [ "$#" -ne 0 ]; then
  echo "usage: detect-mutation-tool.sh" >&2
  exit 2
fi

ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [ -z "$ROOT" ]; then
  echo "mutation_tool=none"
  exit 0
fi

DECL=".claude/mutation-test.sh"
if [ -f "$ROOT/$DECL" ]; then
  echo "mutation_tool=declared"
  echo "declared=${DECL}"
  # 字下げした行や `echo "# 所要の目安: …"` のような本体の行は拾わない（行頭のコメントだけが目安の宣言）
  EST=$(sed -n 's/^# 所要の目安:[[:space:]]*//p' "$ROOT/$DECL" | head -n 1)
  if [ -n "$EST" ]; then
    echo "estimate=${EST}"
  fi
  exit 0
fi

# Stryker の既定の設定ファイル名は 4 通り × 拡張子 4 通り（StrykerJS docs/config-file.md。7.1 で
# `.config.*` が加わった）。最初に見つかった 1 つを決め手にする。無ければ package.json の依存を見る
# （`"@stryker-mutator/` の字面。`stryker` の語が description や scripts にあるだけでは使っている印にならない）
stryker_evidence() {
  local base ext
  for base in stryker.conf stryker.config .stryker.conf .stryker.config; do
    for ext in json js mjs cjs; do
      if [ -f "$ROOT/$base.$ext" ]; then
        echo "$base.$ext"
        return 0
      fi
    done
  done
  if grep -qsF '"@stryker-mutator/' "$ROOT/package.json"; then
    echo "package.json"
  fi
}

# mutmut の設定は pyproject.toml の `[tool.mutmut]` か setup.cfg の `[mutmut]`（mutmut README）。
# 見出しの行頭一致だけを見る（`[tool.mutmutx]`・コメントアウトした見出し・他の節の値に語があるだけ、は外す）
mutmut_evidence() {
  if grep -qs '^\[tool\.mutmut\]' "$ROOT/pyproject.toml"; then
    echo "pyproject.toml"
    return 0
  fi
  if grep -qs '^\[mutmut\]' "$ROOT/setup.cfg"; then
    echo "setup.cfg"
  fi
}

# cargo-mutants の設定は `.cargo/mutants.toml`（cargo-mutants book）。Cargo.toml だけでは使っている印にならない
cargo_mutants_evidence() {
  if [ -f "$ROOT/.cargo/mutants.toml" ]; then
    echo ".cargo/mutants.toml"
  fi
}

STRYKER=$(stryker_evidence)
MUTMUT=$(mutmut_evidence)
CARGO=$(cargo_mutants_evidence)

if [ -z "${STRYKER}${MUTMUT}${CARGO}" ]; then
  echo "mutation_tool=none"
  exit 0
fi
echo "mutation_tool=inferred"
if [ -n "$STRYKER" ]; then
  printf 'inferred=stryker\t%s\n' "$STRYKER"
fi
if [ -n "$MUTMUT" ]; then
  printf 'inferred=mutmut\t%s\n' "$MUTMUT"
fi
if [ -n "$CARGO" ]; then
  printf 'inferred=cargo-mutants\t%s\n' "$CARGO"
fi
