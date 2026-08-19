#!/usr/bin/env bash
# auto-quality-check.sh — Stop hook 用の自動品質チェック
#
# 目的:
#   プラグイン関連ファイルを変更して実装を終えたタイミングで、
#   機械的に検証可能な品質チェックを実行して早期に違反を検知する。
#
# 実行するチェック:
#   `machine-layer.sh` に委譲する（検査の並びの正本はあちら。ここに複製しない
#   — 同じ並びが Stop hook / pre-commit / CI / self-review 前段の 4 経路で要るため）。
#   **このスクリプトの責務は「いつ走らせるか」と「hook 向けにどう出すか」だけ。**
#
# トリガー条件（**走らせない条件は 3 つ**）:
#   ①変異テストの実行中はスキップする（ソースが書き換わっているので結果が嘘になる）
#   ②前回の実行から作業ツリーが変わっていなければスキップし、**前回の検出をキャッシュから
#     出し直す**（再走しない。黙るだけだと「直った」と読めてしまう）
#   ③working tree に以下のパターンの変更がある場合のみチェック実行
#     - */plugin.json
#     - .claude-plugin/marketplace.json
#     - */skills/** / */commands/** / */hooks/** / */agents/** / */references/**
#     - */scripts/**
#     - */CHANGELOG.md
#
# 出力:
#   - エラーなし: silent exit 0
#   - エラーあり: stderr に要修正項目を通知（ユーザー向け）+ stdout に
#     hookSpecificOutput.additionalContext で Claude にも注入（CC 2.1.163）。
#     いずれも exit 0 で Stop はブロックしない。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# safe-hook.sh で stdin 消費と trap 設定
source "$REPO_ROOT/.claude-plugin/lib/safe-hook.sh"
safe_hook_init "auto-quality-check"

# Git 情報が取れないなら何もしない
if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  exit 0
fi

CHANGED="$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null | cut -c4-)"

if [ -z "$CHANGED" ]; then
  exit 0
fi

if ! echo "$CHANGED" | grep -qE '(\.claude-plugin/.*\.json|/skills/|/commands/|/hooks/|/agents/|/references/|/scripts/|/CHANGELOG\.md|marketplace\.json)'; then
  exit 0
fi

# ---- 走らせない条件 1: 変異テストが実行中 ----------------------------------
# `mutation-test.py` は**対象ファイルを書き換えながら**テストを回す。その最中に検査を
# 走らせると、見ているのは変異したソースなので**結果が丸ごと嘘になる**（実測: 1 回の
# 作業中に 6 回発火し、6 回とも偽の失敗報告だった）。ジャーナルの存在＝変異を当てている
# 最中で、`pgrep` が引ければ変異と変異の隙間も塞ぐ（PATH を絞った環境では省略される）。
#
# **黙って exit しない**: Stop hook の正常系は silent exit 0 なので、無言だと「検査して
# 問題なし」と区別がつかない。1 行だけ理由を出す（additionalContext は出さない —
# Claude に修復させる材料が無いため）
if [ -f "$REPO_ROOT/.mutation-test-journal.json" ] ||
   { command -v pgrep >/dev/null 2>&1 && pgrep -f "mutation-test\.py" >/dev/null 2>&1; }; then
  echo "auto-quality-check: 変異テストの実行中なのでスキップした（結果が当てにならない）" >&2
  exit 0
fi

# ---- 走らせない条件 2: 前回から作業ツリーが変わっていない --------------------
# 検査は毎ターン終了時に走るので、質問に答えただけのターンでもフルスイート（実測 125 秒）が
# 回る。**前回と同じ内容なら結果も同じ**なので走らせ直さない。
#
# **前回の検出は握り潰さない**: clean だったときに黙るだけだと、検出のあったターンの次に
# 何も出なくなり「直った」と読めてしまう。結果ごとキャッシュして**再走せずに出し直す**。
#
# 指紋は「status の行 + 変更ファイルの中身」。`git diff` を使わないのは untracked の中身の
# 変化を拾うため。`cksum` が引けない環境では**キャッシュを使わない**（毎回走る側に倒す）
CACHE=""
FINGERPRINT=""
if command -v cksum >/dev/null 2>&1; then
  CACHE="${TMPDIR:-/tmp}/claude-auto-quality-check-$(printf '%s' "$REPO_ROOT" | cksum | cut -d' ' -f1)"
  # **`[ -f ] && cksum` と書かないこと**: status にはディレクトリ（`?? dir/` の畳み込み）や
  # rename の `old -> new` が来るので `-f` は普通に偽になる。偽の AND リストは終了コード 1 で
  # 終わり、`set -e`（safe-hook が張る）が**サブシェルをそこで殺す** — 指紋が空のまま
  # ERR trap で exit 0 し、**検査を一度も走らせずに「問題なし」に見える**（実測）。
  # `if` は条件が偽でも 0 で終わるのでこの形にする
  # 指紋には **`-uall`** の status を使う（既定は中身が全部 untracked な dir を `?? demo/` に
  # 畳むので、その下のファイルを編集しても指紋が動かない ＝ 新規スクリプトを書いている間
  # ずっと再走しない）。トリガー判定側の `$CHANGED` は既存の挙動のまま触らない
  CHANGED_ALL="$(git -C "$REPO_ROOT" status --porcelain -uall 2>/dev/null | cut -c4-)"
  FINGERPRINT="$({
    printf '%s\n' "$CHANGED_ALL"
    while IFS= read -r _f; do
      if [ -f "$REPO_ROOT/$_f" ]; then cksum < "$REPO_ROOT/$_f"; fi
    done <<< "$CHANGED_ALL"
  } | cksum | cut -d' ' -f1)"
  # 指紋を採れなかったらキャッシュを使わない（**走る側に倒す**）
  [ -n "$FINGERPRINT" ] || CACHE=""
fi

emit() {
  # 検出内容（`$1`）をユーザーと Claude の両方へ出す。**キャッシュ再生にも使う**ので
  # 検査の実行とは分けてある
  {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "⚠️  auto-quality-check: 修正が必要な問題があります"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    printf "%b" "$1"
    echo ""
    echo "詳細確認は /quality-check を実行してください"
  } >&2

  # stdout: Claude 向けに additionalContext で注入（CC 2.1.163, Stop hook）
  # Claude がその場で品質問題（SSoT drift / バージョンバンプ忘れ等）を修復できるようにする。
  # JSON 文字列エスケープは確実なエンコーダ（python3 → jq）に委譲。
  # どちらも無い環境では additionalContext は出さず stderr 通知のみ（後方互換）。
  MESSAGE="$(printf "%b" "auto-quality-check が修正の必要な品質問題を検出しました。以下を修正するか /quality-check で詳細を確認してください:\n${1}")"
  if command -v python3 >/dev/null 2>&1; then
    printf '%s' "$MESSAGE" | python3 -c 'import json,sys; print(json.dumps({"hookSpecificOutput":{"hookEventName":"Stop","additionalContext":sys.stdin.read()}}))'
  elif command -v jq >/dev/null 2>&1; then
    printf '%s' "$MESSAGE" | jq -Rsc '{hookSpecificOutput:{hookEventName:"Stop",additionalContext:.}}'
  fi
}

if [ -n "$CACHE" ] && [ -f "$CACHE" ]; then
  CACHED_FP="$(head -1 "$CACHE")"
  if [ "$CACHED_FP" = "$FINGERPRINT" ]; then
    CACHED_ISSUES="$(tail -n +2 "$CACHE")"
    [ -n "$CACHED_ISSUES" ] && emit "$CACHED_ISSUES"
    exit 0
  fi
fi

ISSUES=""

# 検査本体は machine-layer.sh（並びの正本）。exit 1 = 検出 / 2 = 判定不能。
# **判定不能も黙って通さない**（前提が壊れているのに緑に見えるのを避ける）
#
# **`VAR="$(...)"; RC=$?` と書かないこと**: safe-hook が `set -e` を張っているので、
# 非ゼロで終わる代入がそこで ERR trap を踏み、**以降の report 部を実行せず exit 0** する
# （＝検出したのに通知が消え、緑と区別がつかない。v2.69.0 で実際に落ちていた）。
# `&& RC=0 || RC=$?` は代入を AND-OR リストに入れるので `set -e` の対象外になる
ML_OUT="$(bash "$REPO_ROOT/.claude-plugin/scripts/machine-layer.sh" 2>&1)" && ML_RC=0 || ML_RC=$?
case "$ML_RC" in
  0) ;;
  1) ISSUES="${ML_OUT}\n" ;;
  *) ISSUES="[machine-layer] 判定不能（exit ${ML_RC}）:\n${ML_OUT}\n" ;;
esac

if [ -n "$ISSUES" ]; then
  emit "$ISSUES"
fi

# 次のターンで作業ツリーが同じなら再走しないための記録（検出内容ごと残す）。
# 書けなくても検査自体は済んでいるので握り潰してよい
if [ -n "$CACHE" ]; then
  # **展開前の生テキストで持つ**（再生側も `emit` の `%b` を通るので、ここで展開すると
  # `\n` が二重に処理される）
  { printf '%s\n' "$FINGERPRINT"; printf '%s' "$ISSUES"; } > "$CACHE" 2>/dev/null || true
fi

exit 0
