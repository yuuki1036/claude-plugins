#!/usr/bin/env bash
# plugin-enabled.sh <plugin> — プラグインがこの作業で有効かを `1` / `0` で出す（判定できなくても exit 0）
#
# settings を user → project → local の順に読み、`"<plugin>@<marketplace>": true|false` の明示値を
# 後のファイルが上書きする（Claude Code の settings の優先順位と同じ向き）。キーの有無だけを見る判定は、
# `false` で無効化したプラグインを有効と誤認し、project だけで有効化したものを取りこぼす
# （spec-advisor の #74 と同じ型）。feature-dev の Phase 1.3 / 4 / 6 と worktree-flow が使う。
#
# project の場所は CLAUDE_PROJECT_DIR、無ければ cwd。行単位の grep なので、キーと値を別の行に
# 折り返した settings は拾えない（そのときは 0 ＝ 使わない側に倒れる）。

set -uo pipefail

plugin="${1:-}"
if [ -z "$plugin" ]; then
  echo "usage: plugin-enabled.sh <plugin>" >&2
  echo 0
  exit 0
fi

project="${CLAUDE_PROJECT_DIR:-$PWD}"
state=0
for f in "${HOME}/.claude/settings.json" "${project}/.claude/settings.json" "${project}/.claude/settings.local.json"; do
  if grep -Eq "\"${plugin}@[^\"]*\"[[:space:]]*:[[:space:]]*true" "$f" 2>/dev/null; then
    state=1
  elif grep -Eq "\"${plugin}@[^\"]*\"[[:space:]]*:[[:space:]]*false" "$f" 2>/dev/null; then
    state=0
  fi
done
echo "$state"
