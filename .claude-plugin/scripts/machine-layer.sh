#!/usr/bin/env bash
# 機械層（決定的に判定できる検査）を 1 本にまとめて走らせ、**終了コードで結果を返す**。
#
# **なぜ独立したスクリプトにするか**: 同じ検査の並びが複数の経路で要る。並びを各経路に
# 書くと、検査を 1 本足したときに全経路を直す必要が出る（実際に `auto-quality-check.sh` の
# ヘッダは検査一覧の複製を抱えていた）。**呼び出し側は「いつ走らせるか」だけを決める。**
#
# 現在の呼び出し元（**自動で走る経路はどれも `--no-tests`**。既定の全検査は手で走らせる用）:
#   - Stop hook（`auto-quality-check.sh`）… プラグイン関連ファイルに変更があるターンの終了時
#   - self-review 前段（`.claude/review-oracles.sh` ← `code-review/scripts/run-oracles.sh`）
#   - issue-workflow の doc-sync（`.claude/doc-checks.sh`）
# **`.githooks/pre-commit` と CI は今も個別に呼んでいる**（検査ごとに別の案内文を出す・
# ステップ単位で結果を見せるため）。並びを増やすときはこの 2 つも見ること。
#
# 使い方:
#   machine-layer.sh             # 全検査。問題があれば stdout に出して exit 1（手で走らせる用）
#   machine-layer.sh --no-tests  # 回帰テスト（検査 3）を外す。Stop hook と self-review 前段が使う
#     （テストだけで約 12 分かかり、run-oracles.sh の 300 秒に収まらない。2026-10-19 実測。
#      回帰テストは CI の validate が ubuntu と macOS で回す。pre-commit からは 2026-11-08 に
#      外した / GitHub issue #436）
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

RUN_TESTS=1
case "${1:-}" in
  "") ;;
  --no-tests) RUN_TESTS=0 ;;
  # 知らない引数は判定不能（2）。黙って全検査に倒すと、綴りを誤った呼び出し側が 12 分待つ
  *) echo "FATAL: 知らない引数: $1" >&2; exit 2 ;;
esac

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
# **計測ストアの語彙の足し忘れは warning（exit 0）で出る**ので、rc だけ見ていると捨てられ、
# Stop hook にも self-review 前段にも届かない（#478）。exit 0 の回に `[metrics-vocab]` の行だけを拾う
# （語彙を読めず照合を飛ばした通知も同じ前置きで出るので一緒に拾う。どちらも計測ストア側で直す）。
# 要対応の warning を節ごと拾わないのは、ほかの要対応 warning まで毎回出すと
# 「⚠️ が出たときだけ行動する」契約を崩しうるため（2026-11-23 決定）。
# exit 1 の回は出力を丸ごと載せているので、拾い直すと同じ行が 2 回出る
if [ "$RC" -eq 0 ]; then
  VOCAB="$(printf '%s' "$OUT" | grep -F '[metrics-vocab]' || true)"
  if [ -n "$VOCAB" ]; then
    add "$VOCAB"
  fi
fi

# 3. 回帰テスト（検証スクリプト自身 + 同梱スクリプトの CLI テスト + hook テスト）。
#    **起動は run-tests.py に寄せる**: テストが起動したプロセスの残留をそこで回収する
#    （テストが緑でも外に副作用が残る型は、テストの成否では検出できない / #140）
if [ "$RUN_TESTS" -eq 1 ] && [ -d "$REPO_ROOT/.claude-plugin/scripts/tests" ]; then
  OUT="$(python3 "$REPO_ROOT/.claude-plugin/scripts/run-tests.py" 2>&1)" && RC=0 || RC=$?
  case "$RC" in
    0) ;;
    1) add "[unit-tests] $(printf '%s' "$OUT" | tail -20)" ;;
    # スクリプト不在（2 / 127）や「テストが 1 件も走らなかった」（5）は失敗ではなく
    # **測れなかった**。1 に畳むと「直せない指摘」として通知される
    *) UNKNOWN=1; add "[machine-layer] 回帰テストが判定不能（exit ${RC}）:"$'\n'"$(printf '%s' "$OUT" | tail -20)" ;;
  esac
  # **残留プロセスの警告は exit code に載らない契約**（run-tests.py）。rc だけ見ていると
  # ここで捨てられ、引数なしで走らせた回に #140 の検出が不可視になる
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
    # `--json`（CC 2.1.259+）の結果を読む。以前は表示の `❯` 行を awk で拾っていて、表示が
    # 変わるたびに壊れた（CC 2.1.292 では mod の一覧の情報行を拾い、Stop hook に出し続けた / #482）。
    # 終了コード: 0 指摘なし / 3 指摘あり（stdout に 1 行 1 件）/ それ以外は判定不能（stdout に理由）。
    # 指摘ありを 1 にしないのは、python が未捕捉の例外で落ちた回（exit 1）と分けるため
    SCHEMA_OUT="$(python3 - "$plugin_dir" 2>&1 <<'PY'
import json
import os
import re
import subprocess
import sys

plugin_dir = sys.argv[1]
name = os.path.basename(plugin_dir.rstrip("/"))
# SSoT 用の独自フィールド。CLI は「Unknown field」の warning を出すが、直すものではない
IGNORED = {"_requirements", "_superseded_by"}


def unknown(why, proc=None):
    print("[machine-layer] claude plugin validate --json を判定できなかった（%s）: %s" % (why, name))
    if proc is not None:
        print((proc.stdout[-2000:] + proc.stderr[-2000:]).rstrip())
    sys.exit(2)


try:
    proc = subprocess.run(["claude", "plugin", "validate", "--json", plugin_dir],
                          capture_output=True, text=True, stdin=subprocess.DEVNULL)
except OSError as exc:
    unknown("起動できなかった: %s" % exc)

# 指摘は manifest（plugin.json）と contents（hooks.json などファイルごと）の errors / warnings。
# notes（mod の一覧など）と directory.findings（ICON_MISSING など配布先の検査）は指摘に数えない。
# JSON が読めない・形が合わない（`--json` を知らない古い claude など）回は判定不能に倒す
try:
    report = json.loads(proc.stdout)
    # contents の指摘の `path` は「line 86, column 57」の形でファイルを含まないので、
    # プラグインからの相対パスを頭に付ける（無いと Stop hook の通知からどのファイルか分からない）
    sections = [("", report["manifest"])]
    for section in report.get("contents") or []:
        sections.append((os.path.relpath(section["file"], plugin_dir), section))
    findings = []
    for label, section in sections:
        for item in [*section["errors"], *section["warnings"]]:
            path = item.get("path") or ""
            if re.split(r"[.\[]", path, maxsplit=1)[0] in IGNORED:
                continue
            text = "%s: %s" % (path, item["message"]) if path else item["message"]
            findings.append("%s: %s" % (label, text) if label else text)
except (ValueError, KeyError, TypeError, AttributeError) as exc:
    unknown("JSON として読めなかった: %s: %s, exit %d" % (type(exc).__name__, exc, proc.returncode), proc)

if findings:
    print("\n".join(findings))
    sys.exit(3)
# rc を捨てない（#176）: 非ゼロなのに指摘が 0 件なら「違反なし」ではなく「読めなかった」
if proc.returncode != 0:
    unknown("exit %d だが指摘が 0 件" % proc.returncode, proc)
PY
)" && SCHEMA_RC=0 || SCHEMA_RC=$?
    case "$SCHEMA_RC" in
      0) ;;
      3) add "[schema:$(basename "$plugin_dir")] ${SCHEMA_OUT}" ;;
      2) UNKNOWN=1; add "$SCHEMA_OUT" ;;
      *) UNKNOWN=1; add "[machine-layer] CLI スキーマ検査が判定不能（exit ${SCHEMA_RC}）: $(basename "$plugin_dir")"$'\n'"$SCHEMA_OUT" ;;
    esac
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
