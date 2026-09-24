#!/usr/bin/env bash
# push-reminder.sh — PreToolUse hook (Bash: git push)
# push 前にセルフレビュー（/code-review:self-review）の実行を促す
#
# 注意: PreToolUse の plain stdout は Claude への到達保証が弱いため、
# additionalContext（safe_hook_emit_context）で確実に注入する（block しない）。
#
# hooks.json の `if: "Bash(git push *)"` は実行環境によって評価されない
# ことが実測されている（全 Bash 呼び出しで発火する暴発）。if:/matcher に
# 単独依存せず、スクリプト内で command を自己判定する（二重ゲート）。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "dev-workflow:push-reminder"

INPUT=$(safe_hook_input)
if command -v jq &>/dev/null; then
  COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
else
  COMMAND=$(echo "$INPUT" | grep -oE '"command"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*"command"[[:space:]]*:[[:space:]]*"([^"]+)"/\1/' || true)
fi
[ -z "$COMMAND" ] && safe_hook_error Validation "empty command"

# git push が**コマンドの位置**に出現する場合のみ通す（if: 不発時の暴発防止）。
# 1. heredoc の本文を除く（`git commit -F - <<'EOF'` の本文に書いた "git push" で鳴らさない。`<<<` は here-string なので除外）
# 2. クオート内文字列を除く（コミットメッセージ中の "git push" 等）
# 3. 行頭か区切り（; & | ( { ` $( と then/do/else）の直後に、環境変数の代入・env/command/exec/time/nohup
#    を挟んで git が来て、グローバルオプション（-C <dir> / -c <k=v> / --no-pager 等）の後に push が来る形だけ拾う。
#    `echo git push` のように引数として並んだだけのものは拾わない
# **パイプで grep -q に流さない**: pipefail 下で grep が途中で抜けると、64KB を超えるコマンドで
# printf が SIGPIPE で死に「一致なし」に化ける。here-string で渡す
CMD_NO_HEREDOC=$(awk '
  in_doc { line = $0; if (strip) sub(/^\t+/, "", line); if (line == delim) in_doc = 0; next }
  {
    print
    if (match($0, /(^|[^<])<<-?[ \t]*["\047]?[A-Za-z_][A-Za-z0-9_]*["\047]?/)) {
      tok = substr($0, RSTART, RLENGTH)
      sub(/^[^<]/, "", tok)
      strip = (tok ~ /^<<-/)
      sub(/^<<-?[ \t]*/, "", tok); gsub(/["\047]/, "", tok)
      delim = tok; in_doc = 1
    }
  }' <<< "$COMMAND")
# 全体を 1 つのパターン空間に読んでから消す（行ごとだと複数行にまたがるクオートが残る）
CMD_STRIPPED=$(sed -E -e ':a' -e '$!N' -e '$!ba' -e "s/'[^']*'//g; s/\"[^\"]*\"//g" <<< "$CMD_NO_HEREDOC")
PUSH_RE='(^|[;&|({`]|\$\(|(then|do|else)[[:space:]])[[:space:]]*(([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*|env|command|exec|time|nohup)[[:space:]]+)*git[[:space:]]+((-C|-c)[[:space:]]+[^[:space:]]+[[:space:]]+|--?[^[:space:]]+[[:space:]]+)*push([[:space:];&|)]|$)'
if ! grep -qE "$PUSH_RE" <<< "$CMD_STRIPPED"; then
  safe_hook_error Validation "not a git push command"
fi

safe_hook_emit_context "PreToolUse" \
  "push 前にセルフレビュー（/code-review:self-review）の実行を検討してください。"
