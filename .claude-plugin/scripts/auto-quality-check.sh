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
# トリガー条件:
#   working tree に以下のパターンの変更がある場合のみチェック実行
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
  # stderr: ユーザー向け通知（端末に表示）
  {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "⚠️  auto-quality-check: 修正が必要な問題があります"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    printf "%b" "$ISSUES"
    echo ""
    echo "詳細確認は /quality-check を実行してください"
  } >&2

  # stdout: Claude 向けに additionalContext で注入（CC 2.1.163, Stop hook）
  # Claude がその場で品質問題（SSoT drift / バージョンバンプ忘れ等）を修復できるようにする。
  # JSON 文字列エスケープは確実なエンコーダ（python3 → jq）に委譲。
  # どちらも無い環境では additionalContext は出さず stderr 通知のみ（後方互換）。
  MESSAGE="$(printf "%b" "auto-quality-check が修正の必要な品質問題を検出しました。以下を修正するか /quality-check で詳細を確認してください:\n${ISSUES}")"
  if command -v python3 >/dev/null 2>&1; then
    printf '%s' "$MESSAGE" | python3 -c 'import json,sys; print(json.dumps({"hookSpecificOutput":{"hookEventName":"Stop","additionalContext":sys.stdin.read()}}))'
  elif command -v jq >/dev/null 2>&1; then
    printf '%s' "$MESSAGE" | jq -Rsc '{hookSpecificOutput:{hookEventName:"Stop",additionalContext:.}}'
  fi
fi

exit 0
