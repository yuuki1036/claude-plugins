#!/usr/bin/env bash
# 機械層（決定的に判定できる検査）を 1 本にまとめて走らせ、**終了コードで結果を返す**。
#
# **なぜ独立したスクリプトにするか**: 同じ検査の並びが複数の経路で要る。並びを各経路に
# 書くと、検査を 1 本足したときに全経路を直す必要が出る（実際に `auto-quality-check.sh` の
# ヘッダは検査一覧の複製を抱えていた）。**呼び出し側は「いつ走らせるか」だけを決める。**
#
# 現在の呼び出し元:
#   - Stop hook（`auto-quality-check.sh`）… プラグイン関連ファイルに変更があるターンの終了時
#   - self-review 前段（`.claude/review-oracles.sh` ← `code-review/scripts/run-oracles.sh`）
# **`.githooks/pre-commit` と CI は今も個別に呼んでいる**（検査ごとに別の案内文を出す・
# ステップ単位で結果を見せるため）。並びを増やすときはこの 2 つも見ること。
#
# 使い方:
#   machine-layer.sh            # 全検査。問題があれば stdout に出して exit 1
#
# 終了コード:
#   0 … すべて通過
#   1 … 検査が問題を検出した（＝直すべきものがある）
#   2 … 前提が無く**判定できなかった**（python3 が無い等。「通過」と区別する）
#
# 各検査の項目そのものの正本はここではない:
#   - `validate_plugin_quality.py` 冒頭 docstring（品質検査の項目）
#   - `validate-ssot.sh`（SSoT 同期の項目）
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT" || { echo "FATAL: リポジトリルートへ移動できない" >&2; exit 2; }

ISSUES=""
add() { ISSUES="${ISSUES}$1"$'\n'; }

# 1. SSoT 同期（スキーマ準拠 / marketplace 同期 / _requirements ↔ check-deps.sh / 一覧の同期）
if ! OUT="$(bash "$REPO_ROOT/.claude-plugin/scripts/validate-ssot.sh" 2>&1)"; then
  add "$OUT"
fi

# 2〜3 は python3 が前提。**無いときは「通過」ではなく「判定不能」**（exit 2）
if ! command -v python3 >/dev/null 2>&1; then
  printf '%s' "$ISSUES"
  echo "[machine-layer] python3 が無いため品質検査と回帰テストを実行できなかった" >&2
  exit 2
fi

# 2. プラグイン品質（allowed-tools / safe-hook 同期 / references 整合 / SSoT pin / ほか）
if ! OUT="$(python3 "$REPO_ROOT/.claude-plugin/scripts/validate_plugin_quality.py" 2>&1)"; then
  add "$OUT"
fi

# 3. 回帰テスト（検証スクリプト自身 + 同梱スクリプトの CLI テスト + hook テスト）
if [ -d "$REPO_ROOT/.claude-plugin/scripts/tests" ]; then
  if ! OUT="$(python3 -m unittest discover -s .claude-plugin/scripts/tests 2>&1)"; then
    add "[unit-tests] $(printf '%s' "$OUT" | tail -20)"
  fi
fi

# 4. CLI スキーマ（`claude` が無い環境ではこの検査だけ skip する。1〜3 は判定済みなので
#    全体を判定不能に倒さない）
if command -v claude >/dev/null 2>&1; then
  while IFS= read -r plugin_dir; do
    [ -z "$plugin_dir" ] && continue
    VAL_OUT="$(claude plugin validate "$plugin_dir" 2>&1 || true)"
    # `_requirements` / `_superseded_by` は SSoT 用の独自フィールドなので CLI 警告から除外する。
    # CC のバージョンで警告文言が変わるため、文言ではなくフィールド名の有無で除外する
    FILTERED="$(printf '%s' "$VAL_OUT" | grep -E '^\s*❯' | grep -Ev '_requirements|_superseded_by' || true)"
    if [ -n "$FILTERED" ]; then
      add "[schema:$(basename "$plugin_dir")] ${FILTERED}"
    fi
  done < <(find "$REPO_ROOT" -maxdepth 3 -name plugin.json -path '*/.claude-plugin/*' \
             -not -path '*/node_modules/*' -exec dirname {} \; \
             | xargs -I{} dirname {} 2>/dev/null | sort -u)
fi

if [ -n "$ISSUES" ]; then
  printf '%s' "$ISSUES"
  exit 1
fi
exit 0
