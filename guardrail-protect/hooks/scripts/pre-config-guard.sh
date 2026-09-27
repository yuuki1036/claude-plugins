#!/usr/bin/env bash
# pre-config-guard.sh
#
# Edit/Write/MultiEdit ツールで lint/hook/static check 設定ファイルへの
# 編集を試みた場合、basename がプロジェクト設定の protected_basenames に
# 含まれていれば exit 2 でブロックする。
#
# 設定: <project>/.claude/guardrail-protect.json
#   {
#     "protected_basenames": [
#       ".golangci.yml",
#       "lefthook.yml",
#       ".eslintrc.json"
#     ]
#   }
#
# protected_basenames が未設定（または空配列）なら no-op。
# デフォルトでは保護対象ゼロ＝誤爆なし。プロジェクト側が opt-in で宣言する。

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "guardrail-protect:pre-config-guard"

# fail-loud: jq が無いとガードが機能しない。silent skip せず stderr に通知する
command -v jq >/dev/null 2>&1 || safe_hook_error Unexpected "jq not installed; config guard cannot function"

input=$(safe_hook_input)
# **jq の失敗を暗黙の fail-open にしない**（GitHub issue #178。理由は pre-commit-guard と同じ）
tool_name=$(jq -r '.tool_name // empty' <<< "$input" 2>/dev/null || true)
target_path=$(jq -r '.tool_input.file_path // empty' <<< "$input" 2>/dev/null || true)

# **tool_name を判定に使う**（GitHub issue #178）: 以前は取得するだけでエラー文面にしか
# 使っておらず、ブロック判定は file_path だけだった。hooks.json の matcher が唯一の
# ツール種別フィルタになっており、matcher が評価されない環境（実測あり）では
# **保護対象ファイルの Read まで「Refusing to edit」でブロック**される。
# tool_name が無いときは弾かない（載せない CC 版でガードを殺さないため）
case "$tool_name" in
  ""|Edit|Write|MultiEdit) ;;
  *) safe_hook_error Validation "not an edit tool: $tool_name" ;;
esac

[ -z "$target_path" ] && safe_hook_error Validation "no file_path in tool_input"

target_basename=$(basename "$target_path")

# 自己保護: guardrail-protect.json 自体は常に保護対象（config を編集して
# basename を外す 2 段階バイパスを塞ぐ）。解除は Claude 外で人間が行う運用。
if [ "$target_basename" = "guardrail-protect.json" ]; then
  cat >&2 <<EOF
[guardrail-protect] Refusing to edit the guardrail config itself: guardrail-protect.json

This file defines which files are protected. Editing it via Claude would allow
disabling the guardrail in-session (remove a basename, then edit the target).
Change it outside Claude (a human edit) if protection scope genuinely needs to change.

Tool: ${tool_name}
Path: ${target_path}
EOF
  exit 2
fi

# 自己保護（public-leak-guard）: 辞書・設定・visibility キャッシュ。書き換えると公開先ガードが
# 黙って外れる（語を消す / 宛先を private と書き込む）。場所を環境変数で変えた場合はその先も守る
plg_self=0
case "$target_path" in
  */.config/guardrail-protect/*|*/.cache/guardrail-protect/*|*/public-leak-guard.json) plg_self=1 ;;
esac
for plg_env_path in "${GUARDRAIL_SENSITIVE_DICT:-}" "${GUARDRAIL_PUBLIC_LEAK_CONFIG:-}"; do
  if [ -n "$plg_env_path" ] && [ "$target_path" = "$plg_env_path" ]; then plg_self=1; fi
done

# 自己保護（code-review の publish 設定）: `post-publish` は publish のたびに切り離して実行されるので、
# agent が置くと以後の publish で黙って走る。machine-label・salt は計測に載るマシンの label を決める。
# 場所を変える変数（CLAUDE_REVIEW_CONFIG_DIR / REVIEW_METRICS_CONFIG_DIR）が hook の環境にあればその先も守る
review_self=0
case "$target_path" in
  */.config/claude-review|*/.config/claude-review/*) review_self=1 ;;
esac
for review_dir in "${CLAUDE_REVIEW_CONFIG_DIR:-}" "${REVIEW_METRICS_CONFIG_DIR:-}"; do
  review_dir=${review_dir%/}
  if [ -n "$review_dir" ] && { [ "$target_path" = "$review_dir" ] || [[ "$target_path" == "$review_dir"/* ]]; }; then
    review_self=1
  fi
done

# ガードの制御変数（GUARDRAIL_*）と publish 設定の場所を変える変数をシェル設定・settings に書き込んで
# 迂回する経路
plg_env_inject=0
case "$target_basename" in
  .zshrc|.zshenv|.zprofile|.zlogin|.bashrc|.bash_profile|.profile|.envrc|settings.json|settings.local.json|.claude.json)
    plg_new_text=$(jq -r '[.tool_input.content?, .tool_input.new_string?, (.tool_input.edits[]?.new_string)] | map(select(. != null)) | join("\n")' <<< "$input" 2>/dev/null || true)
    if grep -Eq 'GUARDRAIL_[A-Za-z0-9_]*|CLAUDE_REVIEW_CONFIG_DIR|REVIEW_METRICS_CONFIG_DIR' <<< "$plg_new_text"; then plg_env_inject=1; fi
    ;;
esac

if [ "$plg_self" = "1" ] || [ "$plg_env_inject" = "1" ]; then
  cat >&2 <<EOF
[guardrail-protect] Refusing to edit the public-leak-guard dictionary / config / cache

公開先ガード（public-leak-guard）の辞書・設定・visibility キャッシュ、または
GUARDRAIL_* 変数・publish 設定の場所を変える変数（CLAUDE_REVIEW_CONFIG_DIR 等）を
Claude から変えると、ガードが黙って外れる。
変える必要があるなら、人が Claude の外で編集する。

Tool: ${tool_name}
Path: ${target_path}
EOF
  exit 2
fi

if [ "$review_self" = "1" ]; then
  cat >&2 <<EOF
[guardrail-protect] Refusing to edit the code-review publish config (~/.config/claude-review/)

post-publish は review の publish のたびに自動で実行される。Claude が置くと以後の publish で
黙って走る。machine-label・salt は計測に載るマシンの label を決める。
置く・変える必要があるなら、人が Claude の外で編集する（手順は code-review と計測リポジトリの README）。

Tool: ${tool_name}
Path: ${target_path}
EOF
  exit 2
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
CONFIG_FILE="${PROJECT_DIR}/.claude/guardrail-protect.json"

[ -f "$CONFIG_FILE" ] || safe_hook_error NotFound "no project config: $CONFIG_FILE"

protected_basenames=$(jq -r '.protected_basenames[]? // empty' "$CONFIG_FILE" 2>/dev/null)
[ -z "$protected_basenames" ] && exit 0

if grep -Fxq "$target_basename" <<< "$protected_basenames"; then
  cat >&2 <<EOF
[guardrail-protect] Refusing to edit guardrail config file: $target_basename

This file is protected because it defines lint / hook / static check rules.
Weakening guardrails (rule removal, severity downgrade, scope reduction, block-judgement reversal)
is forbidden by the project's "no weakening" meta-rule.

If you genuinely need to change this file:
  1. Justify the change in commit body (specify WHY existing rules block the change)
  2. Remove the basename from .claude/guardrail-protect.json temporarily
  3. Restore protection after the change is committed

Tool: $tool_name
Path: $target_path
Config: $CONFIG_FILE
EOF
  exit 2
fi

exit 0
