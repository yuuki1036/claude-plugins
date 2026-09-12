#!/usr/bin/env bash
# worktree-gc の列挙フェーズ。現リポの git worktree を 1 行 1 JSON で出力する。
#
# **副作用を持たない**（読み取りのみ）。分類判定（reap / keep）まで各行が自分で持ち、
# 実行フェーズ（reap.sh）は再判定しない。表に出したものだけが消える、を
# 「reap は scan の出力行しか受けない」入力契約で担保する（ADR-20260912142858）。
#
# 使い方:
#   scan.sh           # 現リポの worktree を JSON Lines で出力
#   scan.sh --no-lsof # 生存プロセス検査を省く（live_pids を unknown 扱いにし保守的に keep）
#
# 出力 1 行の JSON（フィールド）:
#   repo path branch kind nested_parent self primary dirty untracked
#   ahead_of_main pr merged_into_main live_pids live_unknown marker db_guess verdict reasons
#
# **外部由来文字列（branch / path / db 名）は jq に --arg で渡す**。シェルで再評価される
# 経路を作らない（branch 名は PR 作者が制御する外部入力で、git ref 規則は
# `$` / バッククォート / `;` / `|` を禁じない。detect-dev-worktree.sh と同じ脅威モデル）。
set -uo pipefail

USE_LSOF=1
while [ $# -gt 0 ]; do
  case "$1" in
    --no-lsof) USE_LSOF=0; shift ;;
    *) echo "usage: scan.sh [--no-lsof]" >&2; exit 2 ;;
  esac
done

command -v jq >/dev/null 2>&1 || { echo "FATAL: jq が要る（JSON 出力に使う）" >&2; exit 2; }

# lsof が無ければ live_pids は取れないので unknown 扱いに倒す（保守的 keep の材料）
if [ "$USE_LSOF" = "1" ] && ! command -v lsof >/dev/null 2>&1; then
  USE_LSOF=0
fi
HAVE_GH=0
command -v gh >/dev/null 2>&1 && HAVE_GH=1

GCD=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
[ -n "$GCD" ] || { echo "FATAL: git リポジトリではない" >&2; exit 2; }
REPO=$(dirname "$GCD")

# 起動時の worktree（自分自身）。cwd を含む worktree は消さない
SELF=$(git rev-parse --path-format=absolute --show-toplevel 2>/dev/null || echo "")

# origin/main の解決（merged / ahead 判定の基準）。無ければ判定を保守側に倒す
MAIN_REF=""
if git rev-parse --verify -q origin/main >/dev/null 2>&1; then
  MAIN_REF="origin/main"
elif git rev-parse --verify -q origin/master >/dev/null 2>&1; then
  MAIN_REF="origin/master"
fi

# merged 済みブランチ名の集合（origin/main..branch が空 = merged）を 1 回だけ引く
MERGED_SET=""
if [ -n "$MAIN_REF" ]; then
  MERGED_SET=$(git branch --merged "$MAIN_REF" --format='%(refname:short)' 2>/dev/null || echo "")
fi

# lsof は「cwd が path 配下のプロセス」を拾う（design doc 前提）。path ごとに 1 回。
live_pids_of() {
  local path=$1
  [ "$USE_LSOF" = "1" ] || return 0
  lsof -d cwd -a +D "$path" -t 2>/dev/null | tr '\n' ' ' | sed 's/ *$//'
}

# 1 worktree ぶんを JSON 1 行にして出す
emit() {
  local path=$1 branch=$2 prunable=$3

  # kind 判定（前提 1）。review 配下の agent-* はネスト子
  local kind nested_parent=""
  case "$path" in
    */.claude/worktrees/*/*)
      # review worktree 配下にさらにネストした agent worktree。
      # 親 review worktree = `.../.claude/worktrees/<review-name>` まで
      kind="agent"
      nested_parent=$(printf '%s' "$path" | sed -E 's#(/.claude/worktrees/[^/]+)/.*#\1#')
      ;;
    */.claude/worktrees/*)
      kind="review" ;;
    *)
      if [ -f "$path/envs/.backend.env.worktree" ] || [ -f "$path/envs/.frontend.env.worktree" ]; then
        kind="dev"
      else
        kind="other"
      fi
      ;;
  esac
  [ "$prunable" = "1" ] && kind="prunable"

  # primary worktree（メインの作業ツリー）判定: そこでの --git-dir == --git-common-dir
  local primary=false gd gcd
  gd=$(git -C "$path" rev-parse --path-format=absolute --git-dir 2>/dev/null || echo "")
  gcd=$(git -C "$path" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || echo "")
  if [ -n "$gd" ] && [ "$gd" = "$gcd" ]; then
    primary=true
  fi

  local is_self=false
  [ -n "$SELF" ] && [ "$path" = "$SELF" ] && is_self=true

  # dirty / untracked（prunable は dir が無いので判定不能→ false 固定で無条件 reap に乗る）
  local dirty=false untracked=false status_out=""
  if [ "$prunable" != "1" ] && [ -d "$path" ]; then
    status_out=$(git -C "$path" status --porcelain 2>/dev/null || echo "")
    [ -n "$status_out" ] && dirty=true
    printf '%s\n' "$status_out" | grep -q '^??' && untracked=true
  fi

  # ahead_of_main
  local ahead=0
  if [ -n "$MAIN_REF" ] && [ -n "$branch" ]; then
    ahead=$(git rev-list --count "${MAIN_REF}..${branch}" 2>/dev/null || echo 0)
    case "$ahead" in ''|*[!0-9]*) ahead=0 ;; esac
  fi

  # merged_into_main
  local merged=false
  if [ -n "$branch" ] && printf '%s\n' "$MERGED_SET" | grep -qxF "$branch"; then
    merged=true
  fi

  # pr 状態（gh があるときだけ）。branch は --arg 相当で gh に渡す（シェル再評価しない）
  local pr_number="" pr_state=""
  if [ "$HAVE_GH" = "1" ] && [ -n "$branch" ]; then
    local pr_json
    pr_json=$(gh pr list --head "$branch" --state all --json number,state --limit 1 2>/dev/null || echo "[]")
    pr_number=$(printf '%s' "$pr_json" | jq -r '.[0].number // empty' 2>/dev/null || echo "")
    pr_state=$(printf '%s' "$pr_json" | jq -r '.[0].state // empty' 2>/dev/null || echo "")
  fi

  # live_pids
  local live="" live_unknown=false
  if [ "$USE_LSOF" = "1" ] && [ "$prunable" != "1" ] && [ -d "$path" ]; then
    live=$(live_pids_of "$path")
  else
    live_unknown=true
  fi

  # marker（dev worktree の DB 名）。marker のある行だけ DB drop 候補になる（F1）
  local db_name=""
  if [ -f "$path/envs/.backend.env.worktree" ]; then
    db_name=$(grep -E '^DB_NAME=' "$path/envs/.backend.env.worktree" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || echo "")
  fi

  # --- 分類（安全ゲート。1 つでも真なら keep）---
  local reasons=() verdict="reap"
  [ "$is_self" = "true" ] && reasons+=("self")
  [ "$primary" = "true" ] && reasons+=("primary-worktree")
  { [ "$dirty" = "true" ] || [ "$untracked" = "true" ]; } && reasons+=("dirty")
  { [ -n "$live" ] || [ "$live_unknown" = "true" ]; } && [ "$prunable" != "1" ] && reasons+=("live-or-unknown-process")
  [ "$pr_state" = "OPEN" ] && reasons+=("pr-open")
  [ -z "$pr_state" ] && [ "$merged" != "true" ] && reasons+=("no-pr-not-merged")
  [ -z "$pr_state" ] && [ "$ahead" -gt 0 ] && reasons+=("no-pr-ahead")

  if [ "$prunable" = "1" ]; then
    # dir が消えた残骸。git worktree prune で回収するだけ
    verdict="reap"; reasons=("prunable")
  elif [ "${#reasons[@]}" -gt 0 ]; then
    verdict="keep"
  else
    verdict="reap"
    # PR が merged / closed なら ahead が正でも reap（統合ブランチ経由 merge の落とし穴 / #223）
    reasons=("reapable")
  fi

  # 分類に必要な git 呼び出しが軒並み失敗した行（path が dir なのに status も取れない等）は
  # 安全側に keep へ倒す。誤って残す方が誤って消すより安い
  if [ "$prunable" != "1" ] && [ ! -d "$path" ]; then
    verdict="keep"; reasons=("unclassified")
  fi

  # db_guess: marker のある行の db_name のみ（marker 無し行は DB に触れない / F1）
  jq -nc \
    --arg repo "$REPO" \
    --arg path "$path" \
    --arg branch "$branch" \
    --arg kind "$kind" \
    --arg nested_parent "$nested_parent" \
    --argjson self "$is_self" \
    --argjson primary "$primary" \
    --argjson dirty "$dirty" \
    --argjson untracked "$untracked" \
    --argjson ahead "$ahead" \
    --arg pr_number "$pr_number" \
    --arg pr_state "$pr_state" \
    --argjson merged "$merged" \
    --arg live "$live" \
    --argjson live_unknown "$live_unknown" \
    --arg db_name "$db_name" \
    --arg verdict "$verdict" \
    '{
      repo: $repo,
      path: $path,
      branch: (if $branch == "" then null else $branch end),
      kind: $kind,
      nested_parent: (if $nested_parent == "" then null else $nested_parent end),
      self: $self,
      primary: $primary,
      dirty: $dirty,
      untracked: $untracked,
      ahead_of_main: $ahead,
      pr: (if $pr_number == "" then null else {number: ($pr_number|tonumber), state: $pr_state} end),
      merged_into_main: $merged,
      live_pids: (if $live == "" then [] else ($live | split(" ") | map(select(length>0) | tonumber)) end),
      live_unknown: $live_unknown,
      marker: (if $db_name == "" then null else {db_name: $db_name} end),
      db_guess: (if $db_name == "" then [] else [$db_name] end),
      verdict: $verdict,
      reasons: $ARGS.positional
    }' \
    --args "${reasons[@]+"${reasons[@]}"}"
}

# git worktree list --porcelain をブロック単位でパースする。
# 各ブロックは `worktree <path>` で始まり、`branch refs/heads/<name>` / `detached` /
# `prunable <reason>` を持ち、空行で区切られる。
path=""; branch=""; prunable=0
flush() {
  [ -n "$path" ] || return 0
  emit "$path" "$branch" "$prunable"
  path=""; branch=""; prunable=0
}
while IFS= read -r line; do
  case "$line" in
    "worktree "*) flush; path="${line#worktree }" ;;
    "branch refs/heads/"*) branch="${line#branch refs/heads/}" ;;
    "prunable "*) prunable=1 ;;
    "") flush ;;
  esac
done < <(git worktree list --porcelain 2>/dev/null)
flush

exit 0
