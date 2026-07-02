#!/usr/bin/env bash
# pre-commit-guard.sh
#
# Bash で git commit を実行する際、git hook を迂回するフラグ／設定を検出して
# exit 2 でブロックする。検出対象:
#   - --no-verify / その git 省略形（--no-ver, --no-veri, ...）
#   - -n を含む短フラグクラスタ（-n, -nm, -anm ...）
#   - `git -c core.hooksPath=...` によるインライン hooksPath 上書き
#   - 変数間接（f=--no-verify; git commit $f）
#   - `bash -c '...'` / `sh -c "..."` 等のクォート内スクリプト
#
# commit message / justify 説明は quoted string / heredoc body を剥がしてから
# 検査するため誤検知しない。複合コマンド（`git commit -m x && git log -n 5`）は
# git commit セグメントだけを対象にするため、他コマンドの -n を誤爆しない。
#
# fail-loud: jq / perl が無い場合は silent skip せず Unexpected として stderr に
# 通知する（ガードが黙って無効化されるのを防ぐ）。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "guardrail-protect:pre-commit-guard"

command -v jq   >/dev/null 2>&1 || safe_hook_error Unexpected "jq not installed; guard cannot inspect command"
command -v perl >/dev/null 2>&1 || safe_hook_error Unexpected "perl not installed; guard cannot inspect command"

input=$(safe_hook_input)
tool_name=$(jq -r '.tool_name // empty' <<< "$input" 2>/dev/null)
cmd=$(jq -r '.tool_input.command // empty' <<< "$input" 2>/dev/null)

[ -z "$cmd" ] && exit 0

# 安価な事前フィルタ: git commit 迂回か guardrail-protect.json 改変に関係しなければ即 return
case "$cmd" in
  *git*commit*|*guardrail-protect.json*) ;;
  *) exit 0 ;;
esac

# 検出ロジックは別ファイルの perl に委譲（bash 3.2 は $() 内 heredoc の
# quote 追跡でバグるため、インライン heredoc ではなく独立スクリプトにする）。
# bypass を検出したら理由文字列を stdout に出し、それ以外は何も出さない
# （perl は常に exit 0＝set -e を踏まない）。
detection=$(printf '%s' "$cmd" | perl "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/detect-commit-bypass.pl")

if [ -n "$detection" ]; then
  cat >&2 <<EOF
[guardrail-protect] Refusing to bypass git hooks

Detected: ${detection}
Bypassing pre-commit / commit-msg hooks (or overriding core.hooksPath) weakens
the project's quality guardrails.

If hooks fail, fix the underlying issue rather than bypassing.
If bypass is genuinely required:
  1. Justify in commit body (why bypassing is necessary, what was checked manually)
  2. Temporarily disable this hook via Claude Code permissions, NOT --no-verify
  3. Document the bypass in CHANGELOG / commit log

Tool: ${tool_name}
EOF
  exit 2
fi

exit 0
