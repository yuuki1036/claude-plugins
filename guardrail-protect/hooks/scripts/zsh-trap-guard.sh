#!/usr/bin/env bash
# zsh-trap-guard.sh
#
# Bash tool のシェルが zsh のとき、bash のつもりで書くと黙って壊れる書き方を PreToolUse で止める
# （GitHub issue #254）。判定は `detect-zsh-traps.py`（規則ごとの根拠はその docstring）。
#
# 実測（過去の transcript の Bash 呼び出し 22,307 回）: オプション値の未引用グロブ 296 回
# （うち 292 回が結果に no matches found）/ 語頭の = 100 回 / `$VAR:c` 10 回 / path・status への代入 4 回。
# 目視で誤検出は 0。後ろ 2 つはエラーが出ずに空出力・PATH 破壊で**黙って結果を誤る**型で、
# 止めないと気づけない。echo のエスケープだけは 3 回・実害未確認なので止めず、コンテキストに警告を出す。
#
# 黙る条件: シェルが zsh でない（`CLAUDE_CODE_SHELL` → `SHELL` の順で見る）/ 事前フィルタに
# 当たらない / 解析できない（検出器が何も返さない）。
#
# fail-open: jq / python3 が無ければ Unexpected を通知して通す。このガードが守るのは結果の正しさで、
# 安全性ではない（止められなくても、壊れたコマンドが失敗するだけ）。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "guardrail-protect:zsh-trap-guard"

shell_path="${CLAUDE_CODE_SHELL:-${SHELL:-}}"
case "${shell_path##*/}" in
  zsh|zsh-*) ;;
  *) exit 0 ;;
esac

command -v jq      >/dev/null 2>&1 || safe_hook_error Unexpected "jq not installed; zsh-trap-guard skipped"
command -v python3 >/dev/null 2>&1 || safe_hook_error Unexpected "python3 not installed; zsh-trap-guard skipped"

input=$(safe_hook_input)
tool_name=$(jq -r '.tool_name // empty' <<< "$input" 2>/dev/null || true)
cmd=$(jq -r '.tool_input.command // empty' <<< "$input" 2>/dev/null || true)

# **matcher 単独に依存しない**（CLAUDE.md Gotchas の二重ゲート規約）
if [ -n "$tool_name" ] && [ "$tool_name" != "Bash" ]; then
  safe_hook_error Validation "not a Bash tool: ${tool_name}"
fi
[ -z "$cmd" ] && safe_hook_error Validation "no command in tool_input"

# 安価な事前フィルタ: どの規則にも当たりえないコマンドは python を起動しない。
# 規則を足したら、ここにも当たる形を足すこと（漏れると検出器に届かない）
prefilter='\$[A-Za-z_0-9]+:|(^|[^A-Za-z0-9_])(path|status)([^A-Za-z0-9_]|$)|(^|[[:space:]])=[^[:space:]]|-[^[:space:]]*[][*?]|(^|[^A-Za-z0-9_])-i?(name|path|wholename|regex|lname)[[:space:]]|echo'
if ! grep -Eq -- "$prefilter" <<< "$cmd"; then
  exit 0
fi

detection=$(printf '%s' "$cmd" | python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/detect-zsh-traps.py")
[ -n "$detection" ] || exit 0

blocking=$(grep -v '^echo-escape	' <<< "$detection" | cut -f2- || true)
advisory=$(grep '^echo-escape	' <<< "$detection" | cut -f2- || true)

if [ -n "$blocking" ]; then
  # `[ ] && …` を `$( )` の最後に置かない（CLAUDE.md Gotchas）
  lines=$(sed 's/^/  - /' <<< "$blocking")
  if [ -n "$advisory" ]; then lines="${lines}"$'\n'$(sed 's/^/  - /' <<< "$advisory"); fi
  cat >&2 <<EOF
[guardrail-protect] zsh で意図どおりに動かない書き方がある（zsh-trap-guard）

${lines}

Bash tool のシェルは ${shell_path} です。bash の前提で書くと、エラーになるか、黙って別の値になります。
上の箇所を書き直してから実行してください。
EOF
  exit 2
fi

safe_hook_emit_context PreToolUse "[guardrail-protect] zsh-trap-guard: $(tr '\n' ' ' <<< "$advisory")"
exit 0
