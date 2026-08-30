#!/usr/bin/env bash
# hook-isolation-guard.sh
#
# Bash で **hook スクリプトを隔離せずに直接実行**しようとしたら exit 2 でブロックする。
#
# 動機（GitHub issue #194）: 検証・デバッグのために hook スクリプトを実プロジェクトで
# そのまま走らせ、`.claude/events.jsonl` に本物と区別できない行が混入する事故が
# 実測 2 件あった。うち 1 件は「隔離せよ」と prompt に明記した並列 agent の一部が
# 守らなかったもので、**指示ベースの隔離は守られない**ことが分かっている。
#
# 判定はパスの glob ではなく**中身**で行う（`detect-unisolated-hook-run.py` の docstring）。
# 実測でリポジトリ内 27 本のうち 1 本は skill から意図的に叩かれるユーティリティで、
# パスで切ると偽陽性になる。`safe_hook_init` を持つものだけを対象にすると偽陽性 0 だった。
#
# 通し方: 同一コマンドに値つきの `CLAUDE_PROJECT_DIR=<使い捨て dir>` を前置きする。
#
# fail-loud: jq / python3 が無い場合は silent skip せず Unexpected として stderr に
# 通知する（ガードが黙って無効化されるのを防ぐ / 他 2 本と同じ方針）。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "guardrail-protect:hook-isolation-guard"

command -v jq      >/dev/null 2>&1 || safe_hook_error Unexpected "jq not installed; guard cannot inspect command"
command -v python3 >/dev/null 2>&1 || safe_hook_error Unexpected "python3 not installed; guard cannot inspect command"

input=$(safe_hook_input)
# jq の失敗を暗黙の fail-open にしない（`pre-commit-guard.sh` と同じ理由 / issue #178）
tool_name=$(jq -r '.tool_name // empty' <<< "$input" 2>/dev/null || true)
cmd=$(jq -r '.tool_input.command // empty' <<< "$input" 2>/dev/null || true)

# **matcher 単独に依存しない**（CLAUDE.md Gotchas の二重ゲート規約）。ただし
# tool_name が無いときは弾かない（payload に載せない CC 版でガードごと無効化しない）
if [ -n "$tool_name" ] && [ "$tool_name" != "Bash" ]; then
  safe_hook_error Validation "not a Bash tool: ${tool_name}"
fi

[ -z "$cmd" ] && safe_hook_error Validation "no command in tool_input"

# 安価な事前フィルタ: hook スクリプトのパスらしき文字列が無ければ即 exit 0
case "$cmd" in
  *hooks/scripts/*) ;;
  *) exit 0 ;;
esac

detection=$(printf '%s' "$cmd" | python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/detect-unisolated-hook-run.py")

if [ -n "$detection" ]; then
  cat >&2 <<EOF
[guardrail-protect] Refusing to run a hook script without isolation

Detected:
${detection}

これらは hook の entry point で、書き込み先を \${CLAUDE_PROJECT_DIR:-\$PWD} から
導出します。そのまま実行すると、実プロジェクトの .claude/events.jsonl などへ
本物と区別できない行が混入します（計測の母集団が静かに汚れます）。

使い捨ての dir を明示してから実行してください:

  CLAUDE_PROJECT_DIR=/tmp/scratch-repo bash <script> < payload.json

hook の挙動を回帰テストとして書く場合は
.claude-plugin/scripts/tests/hook_harness.py を使ってください（隔離済みです）。

Tool: ${tool_name}
EOF
  exit 2
fi

exit 0
