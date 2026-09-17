#!/usr/bin/env bash
# worktree-gc の列挙フェーズ。git worktree を 1 行 1 JSON で出力する。
#
# **副作用を持たない**（読み取りのみ）。分類判定（reap / keep）まで各行が自分で持ち、
# 実行フェーズ（reap.sh）は再判定しない。表に出したものだけが消える、を
# 「reap は scan の出力行しか受けない」入力契約で担保する（ADR-20260912142858）。
#
# 使い方:
#   scan.sh                        # 現リポの worktree を JSON Lines で出力
#   scan.sh --no-lsof              # 生存プロセス検査を省く（live_pids を unknown 扱いにし保守的に keep）
#   scan.sh --all [root]           # root 配下（既定 $HOME・maxdepth 4）の全リポの worktree を横断
#   scan.sh --all --depth 6        # find の深さを変える（effort xhigh/max 向け）
#   scan.sh --issue-status <file>  # ブランチ名から取った Issue ID → 状態の JSON（Linear 等）で分類を補う
#
# 出力 1 行の JSON（フィールド）:
#   repo path branch head kind nested_parent self primary dirty untracked
#   ahead_of_main pr merged_into_main issue live_pids live_unknown marker db_guess verdict reasons
#
# **外部由来文字列（branch / path / db 名 / Issue 状態）は jq に --arg で渡す**。シェルで再評価される
# 経路を作らない（branch 名は PR 作者が制御する外部入力で、git ref 規則は
# `$` / バッククォート / `;` / `|` を禁じない。detect-dev-worktree.sh と同じ脅威モデル）。
set -uo pipefail

USE_LSOF=1
ALL=0
ROOT=""
DEPTH=4
ISSUE_FILE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --no-lsof) USE_LSOF=0; shift ;;
    --all)
      ALL=1; shift
      # 次の引数が値（オプションでない）なら root として取る
      if [ $# -gt 0 ] && [ "${1#-}" = "$1" ]; then ROOT="$1"; shift; fi
      ;;
    --depth)
      [ $# -ge 2 ] || { echo "usage: --depth <N>" >&2; exit 2; }
      DEPTH="$2"; shift 2
      case "$DEPTH" in ''|*[!0-9]*) echo "FATAL: --depth は非負整数" >&2; exit 2 ;; esac
      ;;
    --issue-status)
      [ $# -ge 2 ] || { echo "usage: --issue-status <file>" >&2; exit 2; }
      ISSUE_FILE="$2"; shift 2
      ;;
    *) echo "usage: scan.sh [--no-lsof] [--all [root]] [--depth N] [--issue-status <file>]" >&2; exit 2 ;;
  esac
done

command -v jq >/dev/null 2>&1 || { echo "FATAL: jq が要る（JSON 出力に使う）" >&2; exit 2; }

# lsof が無ければ live_pids は取れないので unknown 扱いに倒す（保守的 keep の材料）
if [ "$USE_LSOF" = "1" ] && ! command -v lsof >/dev/null 2>&1; then
  USE_LSOF=0
fi
HAVE_GH=0
command -v gh >/dev/null 2>&1 && HAVE_GH=1

# Issue 状態ファイル（任意）。{"<ID>": {"state": "<名前>", "type": "<completed|canceled|...>"}} の辞書。
# 値は Linear MCP 等から呼び出し側が書く（scan は外部サービスを叩かない）。
# 指定されたのに読めない / 辞書でないときは黙って無視せず止める（「状態を見たつもり」で
# reap に倒れる経路を作らない）
ISSUE_JSON="{}"
if [ -n "$ISSUE_FILE" ]; then
  ISSUE_JSON=$(jq -c 'if type=="object" then . else error("not an object") end' "$ISSUE_FILE" 2>/dev/null) \
    || { echo "FATAL: --issue-status のファイルが読めないか JSON オブジェクトでない: $ISSUE_FILE" >&2; exit 2; }
fi

# 起動時の worktree（自分自身）。cwd を含む worktree は消さない
SELF=$(git rev-parse --path-format=absolute --show-toplevel 2>/dev/null || echo "")

# --- リポ単位の状態（scan_repo が入るたびに張り替える）---
REPO=""
MAIN_REF=""
MERGED_SET=""
PR_DICT="[]"

# lsof は「cwd が path 配下のプロセス」を拾う（design doc 前提）。path ごとに 1 回。
live_pids_of() {
  local path=$1
  [ "$USE_LSOF" = "1" ] || return 0
  lsof -d cwd -a +D "$path" -t 2>/dev/null | tr '\n' ' ' | sed 's/ *$//'
}

# ブランチ名から Issue ID（`PRE-1` / `CFP-1878` 型）を 1 つ取る。無ければ空
issue_ref_of() {
  printf '%s' "$1" | grep -oE '[A-Z][A-Z0-9]+-[0-9]+' | head -1
}

# Issue 状態の「閉じている」判定。type（Linear の workflow state type）を優先し、
# type が無いときだけ名前で判定する（名前は利用者がカスタマイズできるので type が正）
issue_is_closed() {
  local id=$1
  printf '%s' "$ISSUE_JSON" | jq -e --arg id "$id" '
    .[$id] as $v
    | if $v == null then false
      elif ($v|type) == "string" then ($v | ascii_downcase | test("^(done|completed|canceled|cancelled|closed|duplicate)$"))
      elif ($v.type // "") != "" then (($v.type | ascii_downcase) | IN("completed","canceled","cancelled"))
      else (($v.state // "") | ascii_downcase | test("^(done|completed|canceled|cancelled|closed|duplicate)$"))
      end' >/dev/null 2>&1
}

issue_state_name_of() {
  local id=$1
  printf '%s' "$ISSUE_JSON" | jq -r --arg id "$id" '
    .[$id] as $v
    | if $v == null then "" elif ($v|type) == "string" then $v else ($v.state // $v.name // "") end' 2>/dev/null
}

# PR 状態の解決（gh があるときだけ）。
# ブランチあり: リポごとに 1 回引いた辞書（headRefName → PR）を先に見る。辞書に無ければ
#   `gh pr list --head` を 1 回だけ叩く（--limit 200 に収まらない古い PR の取りこぼし対策）
# detached（review / agent worktree）: HEAD の sha に紐づく PR を commits/<sha>/pulls で引く。
#   review worktree は `git checkout --detach FETCH_HEAD` で作られブランチを持たないため、
#   ブランチ名から PR へ辿れない（issue #224）。
# 出力: "<number> <STATE>"（無ければ空）
pr_of() {
  local path=$1 branch=$2 head=$3
  [ "$HAVE_GH" = "1" ] || return 0
  local hit=""
  if [ -n "$branch" ]; then
    hit=$(printf '%s' "$PR_DICT" | jq -r --arg b "$branch" \
      '[.[] | select(.headRefName == $b)] | .[0] | select(. != null) | "\(.number) \(.state)"' 2>/dev/null || echo "")
    if [ -z "$hit" ]; then
      hit=$( (cd "$path" && gh pr list --head "$branch" --state all --json number,state --limit 1) 2>/dev/null \
        | jq -r '.[0] | select(. != null) | "\(.number) \(.state)"' 2>/dev/null || echo "")
    fi
  elif [ -n "$head" ]; then
    # merged_at があれば MERGED、open なら OPEN、それ以外は CLOSED（gh pr list の state 語彙に揃える）
    hit=$( (cd "$path" && gh api "repos/{owner}/{repo}/commits/${head}/pulls") 2>/dev/null \
      | jq -r '.[0] | select(. != null)
               | "\(.number) \(if (.merged_at // null) != null then "MERGED"
                                elif ((.state // "") | ascii_downcase) == "open" then "OPEN"
                                else "CLOSED" end)"' 2>/dev/null || echo "")
  fi
  printf '%s' "$hit"
}

# 1 worktree ぶんを JSON 1 行にして出す
emit() {
  local path=$1 branch=$2 prunable=$3 head=$4

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

  # dirty / untracked（prunable は dir が無いので判定不能→ false 固定で無条件 reap に乗る）。
  # ネストした agent worktree の dir（`.claude/worktrees/`）は untracked に数えない —
  # 親 review worktree はそれを抱えるだけで dirty keep になり掃除できなかった（issue #224）。
  # ネスト側は別の行として自分の dirty を持つので、親で二重に見る必要は無い
  local dirty=false untracked=false status_out=""
  if [ "$prunable" != "1" ] && [ -d "$path" ]; then  # mutation-ok: prunable=1 は dir 消失が前提なので [ -d path ] は常に偽。&& / || で net 不変
    status_out=$(git -C "$path" status --porcelain 2>/dev/null | grep -v '^?? \.claude/worktrees/' || echo "")
    # `.claude/` 全体が untracked だと porcelain は `?? .claude/` に畳む。中身が worktrees だけなら同じ扱い
    if [ "$status_out" = "?? .claude/" ] && [ "$(ls -A "$path/.claude" 2>/dev/null)" = "worktrees" ]; then
      status_out=""
    fi
    [ -n "$status_out" ] && dirty=true
    printf '%s\n' "$status_out" | grep -q '^??' && untracked=true
  fi

  # ahead_of_main（detached は HEAD sha で測る）
  local ref="$branch"
  [ -z "$ref" ] && ref="$head"
  local ahead=0
  if [ -n "$MAIN_REF" ] && [ -n "$ref" ]; then  # mutation-ok: 片方空なら rev-list の range が不正になり || echo 0 で ahead=0。&& / || で net 不変
    ahead=$(git -C "$REPO" rev-list --count "${MAIN_REF}..${ref}" 2>/dev/null || echo 0)
    case "$ahead" in ''|*[!0-9]*) ahead=0 ;; esac
  fi

  # merged_into_main（detached は HEAD が MAIN_REF の祖先か）
  local merged=false
  if [ -n "$branch" ]; then
    printf '%s\n' "$MERGED_SET" | grep -qxF "$branch" && merged=true
  elif [ -n "$MAIN_REF" ] && [ -n "$head" ]; then
    git -C "$REPO" merge-base --is-ancestor "$head" "$MAIN_REF" 2>/dev/null && merged=true
  fi

  # pr 状態
  local pr_number="" pr_state="" pr_hit
  if [ "$prunable" != "1" ]; then
    pr_hit=$(pr_of "$path" "$branch" "$head")
    pr_number="${pr_hit%% *}"
    pr_state="${pr_hit#* }"
    [ "$pr_hit" = "$pr_number" ] && pr_state=""
  fi

  # issue（ブランチ名の Issue ID と、--issue-status で渡された状態）
  local issue_id="" issue_state="" issue_closed=false
  if [ -n "$branch" ]; then
    issue_id=$(issue_ref_of "$branch")
    if [ -n "$issue_id" ]; then
      issue_state=$(issue_state_name_of "$issue_id")
      issue_is_closed "$issue_id" && issue_closed=true
    fi
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
  # Issue が閉じている（Done / Canceled）ブランチは「PR が無く未マージ」でも keep 要因にしない
  # （調査だけで完結し PR を作らない Issue の worktree / issue #240）。worktree remove は
  # ブランチを消さないので、ahead のコミットは失われない
  local reasons=() verdict="reap"
  [ "$is_self" = "true" ] && reasons+=("self")
  [ "$primary" = "true" ] && reasons+=("primary-worktree")
  { [ "$dirty" = "true" ] || [ "$untracked" = "true" ]; } && reasons+=("dirty")
  { [ -n "$live" ] || [ "$live_unknown" = "true" ]; } && [ "$prunable" != "1" ] && reasons+=("live-or-unknown-process")
  [ "$pr_state" = "OPEN" ] && reasons+=("pr-open")
  if [ "$issue_closed" != "true" ]; then
    [ -z "$pr_state" ] && [ "$merged" != "true" ] && reasons+=("no-pr-not-merged")
    [ -z "$pr_state" ] && [ "$ahead" -gt 0 ] && reasons+=("no-pr-ahead")
  fi
  # Issue の状態は keep / reap どちらでも reasons に添える（表で Issue を開かずに判断できるように）
  if [ -n "$issue_id" ] && [ -n "$issue_state" ]; then
    if [ "$issue_closed" = "true" ]; then
      reasons+=("issue-closed:${issue_id}:${issue_state}")
    else
      reasons+=("issue-open:${issue_id}:${issue_state}")
    fi
  fi

  if [ "$prunable" = "1" ]; then
    # dir が消えた残骸。git worktree prune で回収するだけ
    verdict="reap"; reasons=("prunable")
  else
    # issue-* は情報であって keep 要因ではない。それ以外の reason が 1 つでもあれば keep
    local gate_hits=0 r
    for r in "${reasons[@]+"${reasons[@]}"}"; do
      case "$r" in issue-closed:*|issue-open:*) ;; *) gate_hits=$((gate_hits+1)) ;; esac
    done
    if [ "$gate_hits" -gt 0 ]; then
      verdict="keep"
    else
      verdict="reap"
      # PR が merged / closed なら ahead が正でも reap（統合ブランチ経由 merge の落とし穴 / #223）
      reasons=("reapable" "${reasons[@]+"${reasons[@]}"}")
    fi
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
    --arg head "$head" \
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
    --arg issue_id "$issue_id" \
    --arg issue_state "$issue_state" \
    --argjson issue_closed "$issue_closed" \
    --arg live "$live" \
    --argjson live_unknown "$live_unknown" \
    --arg db_name "$db_name" \
    --arg verdict "$verdict" \
    '{
      repo: $repo,
      path: $path,
      branch: (if $branch == "" then null else $branch end),
      head: (if $head == "" then null else $head end),
      kind: $kind,
      nested_parent: (if $nested_parent == "" then null else $nested_parent end),
      self: $self,
      primary: $primary,
      dirty: $dirty,
      untracked: $untracked,
      ahead_of_main: $ahead,
      pr: (if $pr_number == "" then null else {number: ($pr_number|tonumber), state: $pr_state} end),
      merged_into_main: $merged,
      issue: (if $issue_id == "" then null
              else {id: $issue_id, state: (if $issue_state == "" then null else $issue_state end), closed: $issue_closed} end),
      live_pids: (if $live == "" then [] else ($live | split(" ") | map(select(length>0) | tonumber)) end),
      live_unknown: $live_unknown,
      marker: (if $db_name == "" then null else {db_name: $db_name} end),
      db_guess: (if $db_name == "" then [] else [$db_name] end),
      verdict: $verdict,
      reasons: $ARGS.positional
    }' \
    --args "${reasons[@]+"${reasons[@]}"}"
}

# 1 リポ（main repo のパス）の worktree を全部 emit する。
# `git worktree list --porcelain` をブロック単位でパースする。各ブロックは `worktree <path>` で
# 始まり、`HEAD <sha>` / `branch refs/heads/<name>` / `detached` / `prunable <reason>` を持ち、
# 空行で区切られる。
scan_repo() {
  local repo=$1
  REPO="$repo"

  # origin/main の解決（merged / ahead 判定の基準）。無ければ判定を保守側に倒す
  MAIN_REF=""
  if git -C "$repo" rev-parse --verify -q origin/main >/dev/null 2>&1; then
    MAIN_REF="origin/main"
  elif git -C "$repo" rev-parse --verify -q origin/master >/dev/null 2>&1; then
    MAIN_REF="origin/master"
  fi

  # merged 済みブランチ名の集合（origin/main..branch が空 = merged）を 1 回だけ引く
  MERGED_SET=""
  if [ -n "$MAIN_REF" ]; then
    MERGED_SET=$(git -C "$repo" branch --merged "$MAIN_REF" --format='%(refname:short)' 2>/dev/null || echo "")
  fi

  # PR 辞書（headRefName → number/state）をリポごとに 1 回だけ引く
  PR_DICT="[]"
  if [ "$HAVE_GH" = "1" ]; then
    PR_DICT=$( (cd "$repo" && gh pr list --state all --limit 200 --json number,state,headRefName) 2>/dev/null \
      | jq -c 'if type=="array" then . else [] end' 2>/dev/null || echo "[]")
    [ -n "$PR_DICT" ] || PR_DICT="[]"
  fi

  local path="" branch="" prunable=0 head="" line
  flush() {
    [ -n "$path" ] || return 0
    emit "$path" "$branch" "$prunable" "$head"
    path=""; branch=""; prunable=0; head=""
  }
  while IFS= read -r line; do
    case "$line" in
      "worktree "*) flush; path="${line#worktree }" ;;
      "HEAD "*) head="${line#HEAD }" ;;
      "branch refs/heads/"*) branch="${line#branch refs/heads/}" ;;
      "prunable "*) prunable=1 ;;
      "") flush ;;
    esac
  done < <(git -C "$repo" worktree list --porcelain 2>/dev/null)
  flush
}

if [ "$ALL" = "0" ]; then
  GCD=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
  [ -n "$GCD" ] || { echo "FATAL: git リポジトリではない" >&2; exit 2; }
  scan_repo "$(dirname "$GCD")"
  exit 0
fi

# --- --all: root 配下の main repo を find で見つけ、worktree の列挙は各 repo の git に委ねる ---
# root の既定: 環境変数 → .claude/dev-workflow.json の worktree_gc_root → $HOME
if [ -z "$ROOT" ]; then
  ROOT="${DEV_WORKFLOW_WORKTREE_GC_ROOT:-}"
fi
if [ -z "$ROOT" ] && [ -f ".claude/dev-workflow.json" ]; then
  ROOT=$(jq -r '.worktree_gc_root // empty' .claude/dev-workflow.json 2>/dev/null || echo "")
fi
[ -n "$ROOT" ] || ROOT="$HOME"
[ -d "$ROOT" ] || { echo "FATAL: root がディレクトリではない: $ROOT" >&2; exit 2; }

# `.git` がディレクトリなら main repo。ファイル（gitlink）なら worktree か submodule なので
# common-dir を辿り、それが `<repo>/.git` の形なら main repo として採用する
# （submodule の common-dir は `<super>/.git/modules/<name>` で basename が .git にならない → 除外。
#  design doc open 5: find は main repo の発見にだけ使い、worktree 列挙は git に委ねる）
REPOS=""
while IFS= read -r g; do
  [ -n "$g" ] || continue
  if [ -d "$g" ]; then
    REPOS="$REPOS$(dirname "$g")"$'\n'
  elif [ -f "$g" ]; then
    gcd=$(git -C "$(dirname "$g")" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || echo "")
    if [ -n "$gcd" ] && [ "$(basename "$gcd")" = ".git" ]; then
      REPOS="$REPOS$(dirname "$gcd")"$'\n'
    fi
  fi
done < <(find "$ROOT" -maxdepth "$DEPTH" \
           \( -name node_modules -o -name Library -o -name .Trash -o -name .cache -o -name .npm \) -prune \
           -o -name .git -print 2>/dev/null)

printf '%s' "$REPOS" | sort -u | while IFS= read -r repo; do
  [ -n "$repo" ] || continue
  scan_repo "$repo"
done

exit 0
