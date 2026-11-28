#!/usr/bin/env bash
# cc-catch-up の state file を置く dir を用意する（Phase 0 の 1）。
#
#   bash init-state-dir.sh [<root>]      # 既定の root は ${CLAUDE_PROJECT_DIR:-$HOME}
#
# - <root>/.claude/harness-keeper/ を作り、中身が `*` の .gitignore が無ければ置く。
#   repo の .gitignore を書き換えずに、state file と .gitignore 自身を追跡から外すため（GitHub issue #540）
# - .gitignore は未追跡のファイルにしか効かない。新旧どちらかのパスの state file が既に追跡されていれば
#   `tracked=<root からの相対パス>` を 1 行ずつ出す（`git rm --cached` で外す案内に使う）。
#   root が git 管理下に無ければ何も出さない
#
# 出力: `state_dir=<dir の絶対パス>` と、0 行以上の `tracked=...`。exit 0 / dir を作れなければ exit 1
set -u

ROOT="${1:-${CLAUDE_PROJECT_DIR:-$HOME}}"
DIR="$ROOT/.claude/harness-keeper"

if ! mkdir -p "$DIR"; then
  echo "FATAL: ${DIR} を作れない" >&2
  exit 1
fi
if [ ! -e "$DIR/.gitignore" ]; then
  printf '*\n' > "$DIR/.gitignore"
fi
echo "state_dir=${DIR}"

# 旧パスはプラグイン名を claude-meta から改名する前の置き場所（SKILL.md Phase 0 の 1 が新パスへ移す）
for rel in .claude/harness-keeper/cc-catch-up-state.json .claude/claude-meta/cc-catch-up-state.json; do
  if git -C "$ROOT" ls-files --error-unmatch -- "$rel" >/dev/null 2>&1; then
    echo "tracked=${rel}"
  fi
done
exit 0
