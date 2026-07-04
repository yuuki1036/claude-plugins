#!/usr/bin/env bash
# recall fixture の検証用 temp git repo を構築する
#
# Usage:
#   ./setup.sh <fixture-id> [target-dir]
#   ./setup.sh 01-value-flow-insert /tmp/recall-01
#
# 動作:
#   1. target-dir に git repo を作成
#   2. base/ を commit（レビュー対象外のベースライン）
#   3. changed/ を working tree に上書き（未コミット diff = self-review の対象）
#   4. 決定的チェック: diff が surface 判定（triage-guide.md §8.5 の正規表現）に
#      ヒットするかを表示（skeptic 起動条件の事前検証）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURE_ID="${1:?usage: setup.sh <fixture-id> [target-dir]}"
FIXTURE_DIR="${SCRIPT_DIR}/${FIXTURE_ID}"
TARGET="${2:-$(mktemp -d "${TMPDIR:-/tmp}/recall-${FIXTURE_ID}.XXXX")}"

[ -d "${FIXTURE_DIR}/base" ] || { echo "fixture not found: ${FIXTURE_DIR}/base" >&2; exit 1; }

mkdir -p "${TARGET}"
if [ -d "${TARGET}/.git" ]; then
  echo "target already initialized: ${TARGET}" >&2
  exit 1
fi

# 1-2. base を commit
git -C "${TARGET}" init -q -b main
cp -R "${FIXTURE_DIR}/base/." "${TARGET}/"
git -C "${TARGET}" add -A
git -C "${TARGET}" -c user.name=fixture -c user.email=fixture@example.com \
  commit -q -m "base: ${FIXTURE_ID}"

# 3. changed を working tree に上書き（未コミットのまま残す）
cp -R "${FIXTURE_DIR}/changed/." "${TARGET}/"

echo "== fixture repo ready: ${TARGET}"
echo
echo "== working tree diff (self-review の対象) =="
git -C "${TARGET}" add -N . # untracked も diff に含める
git -C "${TARGET}" diff --stat
echo

# 4. 決定的チェック: surface 判定の発火確認
#    triage-guide.md §8.5: 生 SQL の INSERT/UPDATE/DELETE、ORM 書込 API、
#    金銭・数量 numeric 演算、認可・認証
DIFF="$(git -C "${TARGET}" diff)"
SURFACE=""
if grep -qE 'INSERT[[:space:]]+INTO|UPDATE[[:space:]]+.+SET|DELETE[[:space:]]+FROM' <<<"${DIFF}"; then
  SURFACE="${SURFACE}db-write(raw-sql) "
fi
if grep -qE '\.(create|update|save|insert|upsert)\(' <<<"${DIFF}"; then
  SURFACE="${SURFACE}db-write(orm) "
fi
if grep -qiE 'amount|price|balance|quantity|stock|currency|minorUnit' <<<"${DIFF}"; then
  SURFACE="${SURFACE}money "
fi
if grep -qiE 'authoriz|authenticat|permission|session|token|role' <<<"${DIFF}"; then
  SURFACE="${SURFACE}auth "
fi

if [ -n "${SURFACE}" ]; then
  echo "== surface 判定: HIT [${SURFACE% }] → skeptic 起動条件を満たす（effort=xhigh 時）"
else
  echo "== surface 判定: MISS → skeptic は起動しない（correct only for 07）"
fi
echo
echo "== 次のステップ =="
echo "  cd ${TARGET} && claude"
echo "  プロンプト: 「コミット前にセルフレビューして」（self-review が起動する）"
echo "  期待値は evals/fixtures/recall/expected.yaml の ${FIXTURE_ID} を参照"
