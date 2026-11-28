#!/usr/bin/env bash
# textlint-unresolved.sh — 同梱 textlintrc が参照するルールパッケージの解決可否を調べる
#
# 使い方: bash textlint-unresolved.sh [<textlintrc のパス>]
#   省略時は skills/writing-polish/references/textlintrc.json
#
# 出力（stdout。key=value を 1 行ずつ）と exit code:
#   status=ok                              exit 0  config 全体で JSON が返る
#   status=unresolved / missing=<pkg ...>  exit 1  解決できないルールのパッケージ名（空白区切り）
#   status=config-error                    exit 1  ルールは個別に解決できるのに config 全体で JSON が返らない（構文など。導入案内は出せない）
#   status=unavailable / reason=<理由>      exit 2  判定できない。reason は textlint-not-found / python3-not-found /
#                                                  python3-not-runnable / config-not-found /
#                                                  textlint-not-runnable（本体が起動しない。detail= に出力の 1 行目）
#
# 呼び出し元は SessionStart hook（check-deps.sh）と skill の手順（linter-integration.md）。
# textlint v15 は config のルールが 1 つでも解決できないと全ルールを黙って drop し、
# stdout に "== No rules found ==" を出して exit 0 する（stderr は空）ので、成否は stdout が JSON かだけで見る。
set -u

CONFIG="${1:-$(cd "$(dirname "$0")/.." && pwd)/skills/writing-polish/references/textlintrc.json}"

if ! command -v textlint >/dev/null 2>&1; then
  printf 'status=unavailable\nreason=textlint-not-found\n'
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  printf 'status=unavailable\nreason=python3-not-found\n'
  exit 2
fi
# shim が版を決められないと、PATH にあっても起動しない。JSON の判定が全部偽になり config-error に化ける
if ! python3 -c '' >/dev/null 2>&1; then
  printf 'status=unavailable\nreason=python3-not-runnable\n'
  exit 2
fi
if [ ! -f "$CONFIG" ]; then
  printf 'status=unavailable\nreason=config-not-found\n'
  exit 2
fi

# 空 stdin だと textlint は usage を出すので 1 文字流す。
# lint 指摘があると exit 1 になるが、ここで見るのは stdout の形だけ
probe() {
  printf '。' | textlint --stdin --stdin-filename probe.md "$@" --format json 2>/dev/null || true
}

is_json() {
  printf '%s' "$1" | python3 -c 'import json,sys; json.load(sys.stdin)' >/dev/null 2>&1
}

# ルールキー → npm パッケージ名（textlint の解決規則）
#   preset-foo          → textlint-rule-preset-foo
#   @scope/preset-foo   → @scope/textlint-rule-preset-foo
pkg_name() {
  case "$1" in
    @*/*) printf '%s/textlint-rule-%s' "${1%%/*}" "${1#*/}" ;;
    *)    printf 'textlint-rule-%s' "$1" ;;
  esac
}

out="$(probe --config "$CONFIG")"
if is_json "$out"; then
  printf 'status=ok\n'
  exit 0
fi

# 本体が起動しないと、ルールごとの probe も全部 JSON にならず「全ルール未解決」に化ける
# （実測: mise の shim が node の版を決められないと stdout 空・exit 1。ルールを入れても直らない）
if ! err="$(textlint --version 2>&1)"; then
  printf 'status=unavailable\nreason=textlint-not-runnable\ndetail=%s\n' "$(printf '%s\n' "$err" | sed -n '1p')"
  exit 2
fi

missing=""
for key in $(python3 -c 'import json,sys; print("\n".join(json.load(open(sys.argv[1]))["rules"].keys()))' "$CONFIG"); do
  out="$(probe --rule "$key")"
  if ! is_json "$out"; then
    missing="${missing:+${missing} }$(pkg_name "$key")"
  fi
done

if [ -z "$missing" ]; then
  printf 'status=config-error\n'
  exit 1
fi
printf 'status=unresolved\nmissing=%s\n' "$missing"
exit 1
