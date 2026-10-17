#!/usr/bin/env bash
# gh-read-guard.sh
#
# gh の読み取りで、エラーにならずに結果が黙って欠ける書き方を PreToolUse で知らせる（GitHub issue #299）。
# 判定は `detect-gh-read-traps.py`（規則ごとの根拠はその docstring）。
#
# 実測（m1 の transcript の Bash 呼び出し 27,575 回）: `gh run list --commit <短縮 SHA>` 22 回（全件 0 件を
# 返す）/ `gh issue|pr view --comments` を `--json` なし 81 回（非 TTY で本文が出ない。出力が空だった回は
# 15 回以上）。前者は止める（短縮 SHA で困る呼び出しは無い）。後者はコメントだけを読む正当な回が
# あるので止めず、コンテキストに注意を出す。
#
# 黙る条件: gh の呼び出しでない / 事前フィルタに当たらない / 解析できない（検出器が何も返さない）。
#
# fail-open: jq / python3 が無ければ Unexpected を通知して通す。このガードが守るのは結果の正しさで、
# 安全性ではない（止められなくても、欠けた結果が返るだけ）。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "guardrail-protect:gh-read-guard"

command -v jq      >/dev/null 2>&1 || safe_hook_error Unexpected "jq not installed; gh-read-guard skipped"
command -v python3 >/dev/null 2>&1 || safe_hook_error Unexpected "python3 not installed; gh-read-guard skipped"

input=$(safe_hook_input)
tool_name=$(jq -r '.tool_name // empty' <<< "$input" 2>/dev/null || true)
cmd=$(jq -r '.tool_input.command // empty' <<< "$input" 2>/dev/null || true)

# **matcher 単独に依存しない**（CLAUDE.md Gotchas の二重ゲート規約）
if [ -n "$tool_name" ] && [ "$tool_name" != "Bash" ]; then
  safe_hook_error Validation "not a Bash tool: ${tool_name}"
fi
[ -z "$cmd" ] && safe_hook_error Validation "no command in tool_input"

# 安価な事前フィルタ: どの規則にも当たりえないコマンドは python を起動しない。行単位の grep にしない
# （行継続で gh と引数が別の行に分かれると取りこぼす）。規則を足したら、ここにも当たる形を足すこと
case "$cmd" in
  *gh*) ;;
  *) exit 0 ;;
esac
case "$cmd" in
  *-c*) ;;    # `-c` / `--commit` / `--comments` のどれかを含む
  *) exit 0 ;;
esac

detection=$(printf '%s' "$cmd" | python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/detect-gh-read-traps.py") && rc=0 || rc=$?
if [ "$rc" -ne 0 ]; then
  safe_hook_error Unexpected "gh read-trap detector failed (rc=${rc})"
fi
[ -n "$detection" ] || exit 0

blocking=$(grep '^run-short-sha	' <<< "$detection" | cut -f2- || true)
advisory=$(grep -v '^run-short-sha	' <<< "$detection" | cut -f2- || true)

if [ -n "$blocking" ]; then
  lines=$(sed 's/^/  - /' <<< "$blocking")
  if [ -n "$advisory" ]; then lines="${lines}"$'\n'$(sed 's/^/  - /' <<< "$advisory"); fi
  cat >&2 <<EOF
[guardrail-protect] gh の読み取りで結果が黙って欠ける書き方がある（gh-read-guard）

${lines}

エラーにならず空・欠けた結果を正常として返すので、出力を見ても気づけない。書き直してから実行してください。
EOF
  exit 2
fi

safe_hook_emit_context PreToolUse "[guardrail-protect] gh-read-guard: $(tr '\n' ' ' <<< "$advisory")"
exit 0
