#!/usr/bin/env bash
# plugin-enabled.sh <plugin> — プラグインがこの作業で有効かを `1` / `0` で出す（判定できなくても exit 0）
#
# 正本は .claude-plugin/lib/plugin-enabled.sh。各プラグインの scripts/plugin-enabled.sh は byte 一致の
# 複製で、validate_plugin_quality.py の BYTE_REPLICAS が一致を検証する（プラグイン間依存禁止のため
# 他プラグインのものをパスで呼べない。複製側だけを直さない）。
#
# settings を user → project → local の順に読み、`"<plugin>@<marketplace>": true|false` の明示値を
# 後のファイルが上書きする（Claude Code の settings の優先順位と同じ向き）。キーの有無だけを見る判定は、
# `false` で無効化したプラグインを有効と誤認し、project だけで有効化したものを取りこぼす
# （GitHub issue #74 と同じ型）。
#
# project の場所は CLAUDE_PROJECT_DIR、無ければ git の共通 dir の親（メインのチェックアウト）、git の外なら cwd。
# Bash tool の環境には CLAUDE_PROJECT_DIR が無いので、cwd のままだとサブディレクトリでは .claude/ を見失い、
# linked worktree では gitignore された settings.local.json が無いので local の値が消える（issue-workflow の
# worktree はメインで開いたセッションから移る運用。worktree で起動したセッションでは本体の見え方とずれうる）。
# 行単位の grep なので、キーと値を別の行に折り返したファイルは判定に使われず、前に読んだファイルの値が残る。

set -uo pipefail

plugin="${1:-}"
if [ -z "$plugin" ]; then
  echo "usage: plugin-enabled.sh <plugin>" >&2
  echo 0
  exit 0
fi

project="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$project" ]; then
  common=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || common=""
  if [ -n "$common" ]; then project=$(dirname "$common"); else project="$PWD"; fi
fi
state=0
for f in "${HOME}/.claude/settings.json" "${project}/.claude/settings.json" "${project}/.claude/settings.local.json"; do
  if grep -Eq "\"${plugin}@[^\"]*\"[[:space:]]*:[[:space:]]*true" "$f" 2>/dev/null; then
    state=1
  elif grep -Eq "\"${plugin}@[^\"]*\"[[:space:]]*:[[:space:]]*false" "$f" 2>/dev/null; then
    state=0
  fi
done
echo "$state"
