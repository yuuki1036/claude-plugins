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

# 既定はスクリプトの位置から導く。`MACHINE_LAYER_ROOT` は**テスト用の差し替え口**で、
# stub を置いた使い捨てリポジトリに向けて exit code の契約（0/1/2）を検証するために要る
# （検査本体は実行に数分かかるので、本物を走らせるテストは書けない）
REPO_ROOT="${MACHINE_LAYER_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO_ROOT" || { echo "FATAL: リポジトリルートへ移動できない" >&2; exit 2; }

ISSUES=""
UNKNOWN=0
add() { ISSUES="${ISSUES}$1"$'\n'; }

# 1. SSoT 同期（スキーマ準拠 / marketplace 同期 / _requirements ↔ check-deps.sh / 一覧の同期）
#
# **子の exit 2（判定不能）を 1（検出）に混ぜない**: jsonschema が無い等で検査を
# 実行できなかった回を「品質問題あり」として通知すると、直せないものが指摘欄に出る。
# 逆に 0 へ倒すと「違反が無い」と「見ていない」の区別が消える。
# なお `RC=$?` を別の文にすると `set -e` 環境で ERR trap を踏むので、代入は AND-OR リストに入れる
OUT="$(bash "$REPO_ROOT/.claude-plugin/scripts/validate-ssot.sh" 2>&1)" && RC=0 || RC=$?
case "$RC" in
  0) ;;
  1) add "$OUT" ;;
  *) UNKNOWN=1; add "[machine-layer] SSoT 検査が判定不能（exit ${RC}）:"$'\n'"$OUT" ;;
esac

# 2〜3 は python3 が前提。**無いときは「通過」ではなく「判定不能」**（exit 2）
if ! command -v python3 >/dev/null 2>&1; then
  printf '%s' "$ISSUES"
  echo "[machine-layer] python3 が無いため品質検査と回帰テストを実行できなかった" >&2
  exit 2
fi

# 2. プラグイン品質（allowed-tools / safe-hook 同期 / references 整合 / SSoT pin / ほか）
#    検査 1 と同じ扱い（0/1 以外は「実行できなかった」= 判定不能。python は
#    ファイルを開けないと 2、実行不能なら 126/127 を返す）
OUT="$(python3 "$REPO_ROOT/.claude-plugin/scripts/validate_plugin_quality.py" 2>&1)" && RC=0 || RC=$?
case "$RC" in
  0) ;;
  1) add "$OUT" ;;
  *) UNKNOWN=1; add "[machine-layer] 品質検査が判定不能（exit ${RC}）:"$'\n'"$OUT" ;;
esac

# 3. 回帰テスト（検証スクリプト自身 + 同梱スクリプトの CLI テスト + hook テスト）。
#    **起動は run-tests.py に寄せる**: テストが起動したプロセスの残留をそこで回収する
#    （テストが緑でも外に副作用が残る型は、テストの成否では検出できない / #140）
if [ -d "$REPO_ROOT/.claude-plugin/scripts/tests" ]; then
  OUT="$(python3 "$REPO_ROOT/.claude-plugin/scripts/run-tests.py" 2>&1)" && RC=0 || RC=$?
  case "$RC" in
    0) ;;
    1) add "[unit-tests] $(printf '%s' "$OUT" | tail -20)" ;;
    # スクリプト不在（2 / 127）や「テストが 1 件も走らなかった」（5）は失敗ではなく
    # **測れなかった**。1 に畳むと「直せない指摘」として通知される
    *) UNKNOWN=1; add "[machine-layer] 回帰テストが判定不能（exit ${RC}）:"$'\n'"$(printf '%s' "$OUT" | tail -20)" ;;
  esac
  # **残留プロセスの警告は exit code に載らない契約**（run-tests.py）。rc だけ見ていると
  # ここで捨てられ、Stop hook と self-review 前段の 2 経路で #140 の検出が不可視になる
  # `[run-tests:leak]` だけを拾う（`pgrep` 不在の skip 通知は同じ `[run-tests]` 前置きで
  # 出るので、前方一致にすると PATH を絞った環境で常時発火する）
  LEAK="$(printf '%s' "$OUT" | grep -F '[run-tests:leak]' || true)"
  if [ -n "$LEAK" ]; then
    add "$LEAK"
  fi
fi

# 4. CLI スキーマ（`claude` が無い環境ではこの検査だけ skip する。1〜3 は判定済みなので
#    全体を判定不能に倒さない）
if command -v claude >/dev/null 2>&1; then
  while IFS= read -r plugin_dir; do
    VAL_OUT="$(claude plugin validate "$plugin_dir" 2>&1 || true)"
    # `_requirements` / `_superseded_by` は SSoT 用の独自フィールドなので CLI 警告から除外する。
    # CC のバージョンで警告文言が変わるため、文言ではなくフィールド名の有無で除外する
    FILTERED="$(printf '%s' "$VAL_OUT" | grep -E '^\s*❯' | grep -Ev '_requirements|_superseded_by' || true)"
    if [ -n "$FILTERED" ]; then
      add "[schema:$(basename "$plugin_dir")] ${FILTERED}"
    fi
  # 空行はパイプライン側で落とす（ループ内で `[ -z ] && continue` と書くと、
  # その 1 行が反転したときに**全プラグインを黙って skip する**経路になる）
  done < <(find "$REPO_ROOT" -maxdepth 3 -name plugin.json -path '*/.claude-plugin/*' \
             -not -path '*/node_modules/*' -exec dirname {} \; \
             | xargs -I{} dirname {} 2>/dev/null | grep -v '^[[:space:]]*$' | sort -u)
fi

if [ -n "$ISSUES" ]; then
  printf '%s' "$ISSUES"
  # **判定不能が混ざっていたら 2 が勝つ**（python3 不在の分岐と同じ倒し方）。
  # 呼び出し側が知りたいのは「機械層を信用してよいか」で、そこが崩れている回は
  # 検出の有無に関わらず「判定できなかった」として扱う
  # （消費側の対応: Stop hook は「判定不能」表示 / run-oracles は `status=error`）
  if [ "$UNKNOWN" -eq 1 ]; then
    exit 2
  fi
  exit 1
fi
exit 0
