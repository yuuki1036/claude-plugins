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
# **jq の失敗を暗黙の fail-open にしない**（GitHub issue #178）: `|| true` が無いと
# 不正 JSON での jq exit 5 が safe-hook の ERR trap を踏み、**ガードを通り抜けたことに
# 誰も気づけないまま exit 0** する。通す方向自体は決まっている
# （`test_malformed_input_does_not_block`: 壊れた入力で作業を止める方が高コスト）が、
# それは**明示的に選んだ結果**であるべきで、事故で通るのとは別物
tool_name=$(jq -r '.tool_name // empty' <<< "$input" 2>/dev/null || true)
cmd=$(jq -r '.tool_input.command // empty' <<< "$input" 2>/dev/null || true)

# **matcher 単独に依存しない**（CLAUDE.md Gotchas の二重ゲート規約）。ただし
# **tool_name が無いときは弾かない** — payload に tool_name を載せない CC 版で
# ガードごと無効化するのは、防ごうとしている暴発より悪い
if [ -n "$tool_name" ] && [ "$tool_name" != "Bash" ]; then
  safe_hook_error Validation "not a Bash tool: $tool_name"
fi

[ -z "$cmd" ] && safe_hook_error Validation "no command in tool_input"

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
