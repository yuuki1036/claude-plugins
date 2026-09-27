#!/usr/bin/env bash
# public-leak-guard.sh
#
# 公開リポジトリ・gist への書き込み（gh の書き込み系 / gh api / git push / GitHub MCP /
# run_in_terminal）に業務情報が入っていたら止める PreToolUse hook。判定は
# `detect-public-leak.py` の docstring（宛先の visibility・本文の取り方・照合）。
#
# **このガードは fail-closed**。safe-hook.sh の Validation / Unexpected / ERR trap は
# すべて exit 0 で通す作りなので、ここでは流用しない（stdin の消費だけ使う）:
#   - ERR trap を上書きし、公開につながる字面を含む入力なら exit 2 で止める
#   - python3 が無い・検出器が exit 0 / 2 以外で終わった → 同じく止める
# PreToolUse の hook は exit 2 以外の非ゼロでも timeout でも「止めずに通る」（公式 docs）ので、
# 判定できないときに exit 2 を返さないとガードごと外れる。
#
# 事前フィルタ: 引用符とバックスラッシュを除いた入力に gh / git / GUARDRAIL / 辞書・設定名 /
# mcp__ のどれも無ければ検出器を起動しない（全 Bash 呼び出しに python の起動を足さないため）。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "guardrail-protect:public-leak-guard"

input=$(safe_hook_input)

plg_relevant() {
  local flat
  # パス・ID の欄（cwd / transcript_path / session_id 等）は落としてから見る。
  # 一時ディレクトリ名や `~/github/` のような cwd に gh / git が入るだけで検出器を起動しない
  flat=$(printf '%s' "$input" \
    | sed -E 's/"(cwd|transcript_path|session_id|tool_use_id|hook_event_name|permission_mode|agent_id|agent_type)"[[:space:]]*:[[:space:]]*"([^"\\]|\\.)*"//g' \
    | tr -d '"'"'"'\\' 2>/dev/null) || flat="$input"
  case "$flat" in
    *gh*|*git*|*GUARDRAIL*|*guardrail-protect*|*sensitive-terms*|*public-leak*|*mcp__*) return 0 ;;
  esac
  if [ -n "${GUARDRAIL_SENSITIVE_DICT:-}" ]; then
    case "$flat" in *"$(basename "${GUARDRAIL_SENSITIVE_DICT}")"*) return 0 ;; esac
  fi
  return 1
}

plg_fail() {
  if plg_relevant; then
    echo "[guardrail-protect] public-leak-guard: ${1}。公開先への送信かを判定できないので止めた" >&2
    exit 2
  fi
  echo "[guardrail-protect:Unexpected] public-leak-guard: ${1}" >&2
  exit 0
}

# safe-hook の ERR trap（exit 0）を上書きする
trap 'plg_fail "exit $? at line $LINENO"' ERR

plg_relevant || exit 0

command -v python3 >/dev/null 2>&1 || plg_fail "python3 が無い"

detector="${CLAUDE_PLUGIN_ROOT}/hooks/scripts/detect-public-leak.py"
[ -f "$detector" ] || plg_fail "検出器が無い"

errf=$(mktemp "${TMPDIR:-/tmp}/public-leak-guard.XXXXXX") || plg_fail "一時ファイルを作れない"
out=$(printf '%s' "$input" | python3 "$detector" hook 2>"$errf") && rc=0 || rc=$?
err=$(cat "$errf" 2>/dev/null) || err=""
rm -f "$errf" 2>/dev/null || true

case "$rc" in
  0)
    if [ -n "$out" ]; then printf '%s\n' "$out"; fi
    if [ -n "$err" ]; then printf '%s\n' "$err" >&2; fi
    exit 0
    ;;
  2)
    printf '%s\n' "$err" >&2
    exit 2
    ;;
  *)
    if [ -n "$err" ]; then printf '%s\n' "$err" >&2; fi
    plg_fail "検出器が異常終了した (rc=${rc})"
    ;;
esac
