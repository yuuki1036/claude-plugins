#!/usr/bin/env bash
# branch-setup.sh — start / issue-create がブランチを切るときの状態取得・worktree 作成・既存の作業の検知
# （GitHub issue #280 / #305）
#
# 手順の正本は references/branch-setup.md（existing の出力の読み方は skills/start/references/existing-work.md）。
# ここは決定的に書ける部分（状態の取得・既存の作業の検知・worktree の作成・未追跡の .env* の複製・
# 依存を入れるコマンドの検出）だけを持つ。依存のインストールは時間がかかり失敗の扱いを会話で
# 決めたいので、コマンドを出すだけで実行はしない。
#
# 使い方:
#   branch-setup.sh status
#     → in_worktree=0|1 / dirty=<未コミットの変更の行数> / branch=<今のブランチ> /
#       main_root=<メインのチェックアウトの絶対パス> / default_branch=<既定ブランチ名。不明なら空>
#   branch-setup.sh worktree <branch> --name <dir 名> [--base <ref>]
#     → <main_root>/.claude/worktrees/<dir 名> に <branch> の worktree を作り、次を出す:
#       worktree=<絶対パス> / branch=<branch> /
#       base=<ref。既存ブランチを使った回は -、origin にだけあったブランチは origin/<branch>> /
#       created=1|0（0 は worktree が既にあった — 同じパス、または <branch> を checkout している
#       別のパス。メインのチェックアウトのこともある。別のパスなら .env* の複製も依存の検出もしない）/
#       excluded=1|0（.claude/worktrees/ を info/exclude に足したか）/
#       env_copied=<相対パス>（0 行以上）/ install=<コマンド>（0 行以上）
#     <branch> か <dir 名> のパスを、ディレクトリ（または中の .git）が消えて登録だけが残った worktree（prunable）が
#     持っていれば、何も書き換えずに exit 1 で、stderr に登録の消し方（git worktree prune。locked なら unlock も、
#     detached HEAD ならコミットを残す git branch も）を出す。<dir 名> のパスの worktree が別のブランチ
#     （detached HEAD を含む）を checkout していても exit 1
#   branch-setup.sh existing <ISSUE-ID>
#     → <ISSUE-ID> の作業が既にあるかを、今のチェックアウトに限らず探す（start の Phase F2.5）。
#       候補ごとに次の 9 行を同じ順で出し、最後に found=<候補の数> を出す:
#       worktree=<checkout している worktree の絶対パス。無ければ -（prunable の候補も -）> /
#       branch=<ブランチ名。detached HEAD は detached、origin にだけあれば origin/<名前>> /
#       ahead=<既定ブランチ（ローカルと origin/<既定> のどちらにも）に無いコミットの数。
#              既定ブランチが不明か、git が数えられない（まだコミットの無い HEAD など）なら -> /
#       dirty=<未コミットの変更の行数。.claude/ 配下の未追跡と、worktree サブコマンドが写した .env* は数えない。
#              worktree が無ければ -、git status が失敗しても -> /
#       matched=<結び付けた手がかり: branch（名前に ID）/ path（.claude/worktrees/<ID>）/
#               session-context（detached HEAD の worktree の .claude/session-context.md）のカンマ区切り> /
#       current=1|0（今いるチェックアウトか）/
#       prunable=<ディレクトリ（または中の .git）が消えて登録だけが残った worktree のパス。git はそのブランチを
#                 まだ checkout 済みと見るので、移ることも git switch も worktree の作成もできない。無ければ -> /
#       locked=1|0（worktree の登録が git worktree lock されているか。prunable の候補で 1 なら、git worktree prune は
#               その登録を消さない。worktree の無い候補は 0）/
#       head=<HEAD のコミット（ブランチだけの候補はその先端）。まだコミットの無い HEAD は -。detached HEAD の
#             prunable の候補では、ほかのブランチに無ければ prune でこのコミットがどの ref からも辿れなくなる>
#       順は worktree（登録だけが残ったものを含む。git worktree list の順）→ どこにも checkout されていない
#       ローカルのブランチ → origin にだけあるブランチ。fetch はしない
#   branch-setup.sh worktrees
#     → メインのチェックアウト以外の worktree のうち、ブランチ名に Issue ID を含むもの（start の Phase D2）。
#       1 件ごとに id=<Issue ID> / branch=<ブランチ名> / worktree=<絶対パス> の 3 行。detached HEAD と
#       登録だけが残った worktree は出さない。該当なしなら何も出さない
#
# 終了コード: 0 成功（existing / worktrees は該当なしも 0）/ 1 作成できなかった（git の失敗・パスの衝突・
#             登録だけが残った worktree）/ 2 引数・前提の誤り

set -euo pipefail

die() { echo "ERROR: $2" >&2; exit "$1"; }

git rev-parse --git-dir >/dev/null 2>&1 || die 2 "git リポジトリの中で実行する"

# メインのチェックアウトの git dir（worktree の中からでもメイン側を指す）
common_dir() {
  local d
  if d=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null); then
    printf '%s' "$d"
  else
    # --path-format は git 2.31 から。古い git は相対パスを返すので cwd 基準で解決する
    (cd "$(git rev-parse --git-common-dir)" && pwd -P)
  fi
}

COMMON=$(common_dir)
# common dir が `<root>/.git` でない（submodule など）ときは親を root と見なせない
if [ "$(basename "$COMMON")" = ".git" ]; then
  MAIN_ROOT=$(dirname "$COMMON")
else
  MAIN_ROOT=$(git rev-parse --show-toplevel)
fi

default_branch() {
  local b
  if b=$(git symbolic-ref --short -q refs/remotes/origin/HEAD 2>/dev/null); then
    printf '%s' "${b#origin/}"
    return 0
  fi
  for b in main master; do
    if git show-ref --verify -q "refs/heads/${b}" || git show-ref --verify -q "refs/remotes/origin/${b}"; then
      printf '%s' "$b"
      return 0
    fi
  done
  return 0
}

# git worktree list --porcelain を 1 worktree 1 行の「<path>\t<HEAD>\t<gone>\t<locked>\t<branch>」にする（detached は
# branch が空。空になりうる branch を最後に置く — IFS のタブは連続すると 1 つに潰れ、後ろの欄がずれる）。
# bare は出さない。gone=1 はディレクトリ（または中の .git）が消えて登録だけが残った worktree（prunable）で、git は
# そのブランチをまだ checkout 済みと見る。prunable の注釈は git 2.31 からなので、古い git ではディレクトリの有無でも
# 見分ける。locked な登録には git が prunable を付けない（prune もしない）ので、ディレクトリの有無だけで見分ける —
# 中の .git だけが消えた locked な worktree は見分けられない。porcelain は 1 件ごとに空行で終わる（最後の 1 件も）
list_worktrees() {
  local line p="" sha="" b="" bare=0 gone=0 lk=0
  while IFS= read -r line; do
    case "$line" in
      "worktree "*) p=${line#worktree }; sha=""; b=""; bare=0; gone=0; lk=0 ;;
      "HEAD "*) sha=${line#HEAD } ;;
      "branch refs/heads/"*) b=${line#branch refs/heads/} ;;
      bare) bare=1 ;;
      prunable*) gone=1 ;;
      locked*) lk=1 ;;
      "")
        if [ "$bare" = 0 ]; then
          if [ ! -d "$p" ]; then gone=1; fi
          printf '%s\t%s\t%s\t%s\t%s\n' "$p" "$sha" "$gone" "$lk" "$b"
        fi ;;
    esac
  done < <(git worktree list --porcelain)
}

# <branch> を checkout している worktree のパス（無ければ空）。登録だけが残ったものは返さない（そこへは移れない）
checked_out_at() {
  local p sha gone lk b
  while IFS=$'\t' read -r p sha gone lk b; do
    if [ "$gone" = 0 ] && [ "$b" = "$1" ]; then printf '%s' "$p"; return 0; fi
  done < <(list_worktrees)
  return 0
}

# $1 が Issue ID $2 を含むか。TEAM-1 を feat/TEAM-12-x・XTEAM-1 には当てない
has_id() { local re="(^|[^A-Za-z0-9])${2}([^0-9]|$)"; [[ "$1" =~ $re ]]; }

# detached HEAD の worktree を Issue に結び付ける手がかり（start の Phase CTX が書く）。ほかに当たりうるのは
# path（.claude/worktrees/<ID>）だけで、Claude アプリが作る worktree はそれに当たらない
sc_has_id() {
  local f="$1/.claude/session-context.md"
  if [ -f "$f" ]; then grep -qE "^issue_id:[[:space:]]*[\"']?${2}[\"']?[[:space:]]*$" "$f"; else return 1; fi
}

# 既定ブランチ（ローカルと origin のどちらにも）に無いコミットの数。既定ブランチが不明か、git が数えられない
# （まだコミットの無い HEAD の 0000… など）なら -。空や 0 で返すと、start は作業なしと読む。
# origin/<既定> も除くのは、worktree は origin/<既定> から切るので、ローカルの既定ブランチが
# 遅れている回に origin 側のコミットまで数えてしまうため
BASES=""
ahead() {
  if [ -n "$BASES" ]; then
    # shellcheck disable=SC2086 # BASES は ref を空白で並べたもので、分割させる
    git rev-list --count "$1" --not $BASES 2>/dev/null || echo -
  else
    echo -
  fi
}

# 未追跡の $2（$1 の worktree からの相対パス）が、worktree サブコマンドがメイン側から写した .env* のままか。
# $1 がメインのチェックアウト自身なら比べる相手が同じファイル（-ef）になるので、写したものとは見なさない
copied_env() {
  case "${2##*/}" in .env*) ;; *) return 1 ;; esac
  if [ "${1}/${2}" -ef "${MAIN_ROOT}/${2}" ]; then return 1; fi
  if [ -f "${1}/${2}" ]; then cmp -s "${1}/${2}" "${MAIN_ROOT}/${2}"; else return 1; fi
}

# porcelain の HEAD の値。まだコミットの無い HEAD は 0000… になるので -（その sha に git branch は打てない）
head_or_dash() { if [ -z "${1//0/}" ]; then echo -; else echo "$1"; fi; }

# 未コミットの変更の行数。git status が失敗したら -（0 と書くと作業なしに化ける）。数えないもの:
# - .claude/ 配下の未追跡（session-context.md・events.jsonl など start と hook が書くファイル）— gitignore して
#   いない repo で /start しただけの worktree が作業ありに化ける
# - worktree サブコマンドが写した未追跡の .env*（メイン側の同じパスと中身が同じもの）— 作った直後の worktree が
#   作業ありに化ける。メインのチェックアウト自身では数える。未追跡のディレクトリは `?? dir/` の 1 行に
#   まとまるので、写した .env* しか無いディレクトリでも 1 と数える
# --no-optional-locks: 別のセッションが作業中の worktree で index.lock を取らない（向こうの git が失敗する）
dirty_count() {
  local out line n=0
  out=$(git --no-optional-locks -C "$1" status --porcelain 2>/dev/null) || { echo -; return 0; }
  while IFS= read -r line; do
    case "$line" in
      ""|"?? .claude/"*) continue ;;
      "?? "*) if copied_env "$1" "${line:3}"; then continue; fi ;;
    esac
    n=$((n + 1))
  done <<< "$out"
  echo "$n"
}

# 候補 1 件を 9 行で出す（呼び出し側は同じキーの n 番目どうしを 1 件として読む）
emit_record() {
  echo "worktree=$1"; echo "branch=$2"; echo "ahead=$3"
  echo "dirty=$4"; echo "matched=$5"; echo "current=$6"; echo "prunable=$7"
  echo "locked=$8"; echo "head=$9"
}

cmd_status() {
  local gd in_wt=0 dirty br
  gd=$(git rev-parse --absolute-git-dir)
  if [ "$gd" != "$COMMON" ]; then in_wt=1; fi
  dirty=$(git status --porcelain | wc -l | tr -d ' ')
  br=$(git symbolic-ref --short -q HEAD || echo detached)
  echo "in_worktree=${in_wt}"
  echo "dirty=${dirty}"
  echo "branch=${br}"
  echo "main_root=${MAIN_ROOT}"
  echo "default_branch=$(default_branch)"
}

cmd_existing() {
  [ $# -eq 1 ] || die 2 "Issue ID を 1 つ渡す"
  local id=$1 idre='^[A-Z]+-[0-9]+$' def r here n=0 seen=" " p sha gone lk b m cur
  # 正規表現に埋め込むので、F1 の抽出（[A-Z]+-\d+）と同じ形だけを通す
  [[ "$id" =~ $idre ]] || die 2 "Issue ID として不正: '${id}'"
  def=$(default_branch)
  if [ -n "$def" ]; then
    for r in "refs/heads/${def}" "refs/remotes/origin/${def}"; do
      if git show-ref --verify -q "$r"; then BASES="${BASES} ${r}"; fi
    done
  fi
  here=$(git rev-parse --show-toplevel)

  while IFS=$'\t' read -r p sha gone lk b; do
    m=""
    if [ -n "$b" ] && has_id "$b" "$id"; then m="branch"; fi
    if [ "$p" = "${MAIN_ROOT}/.claude/worktrees/${id}" ]; then m="${m:+${m},}path"; fi
    # session-context で結び付けるのは detached HEAD の worktree だけ。main で /start {ID} を呼ぶと
    # Phase CTX がメイン側に issue_id を書くので、ブランチを持つチェックアウトにも当てると
    # main の無関係な未コミットの変更が「続き」に化ける
    if [ -z "$b" ] && sc_has_id "$p" "$id"; then m="${m:+${m},}session-context"; fi
    if [ -z "$m" ]; then continue; fi
    seen="${seen}${b} "
    if [ "$gone" = 1 ]; then
      # 登録だけが残った worktree。ブランチだけの候補（worktree=-）として出すと、start はそのブランチへ
      # git switch するか worktree を作りに行き、どちらも already used で失敗する。prunable= で知らせる
      emit_record - "${b:-detached}" "$(ahead "$sha")" - "$m" 0 "$p" "$lk" "$(head_or_dash "$sha")"
    else
      cur=0
      if [ "$p" = "$here" ]; then cur=1; fi
      emit_record "$p" "${b:-detached}" "$(ahead "$sha")" "$(dirty_count "$p")" "$m" "$cur" - \
        "$lk" "$(head_or_dash "$sha")"
    fi
    n=$((n + 1))
  done < <(list_worktrees)

  # どの worktree にも checkout されていないブランチ（登録だけが残った worktree のブランチは上で出した）。
  # origin のものは同名のローカルが無いときだけ（origin/HEAD は lstrip=3 で HEAD になり has_id で落ちる）
  while IFS= read -r b; do
    if ! has_id "$b" "$id"; then continue; fi
    case "$seen" in *" ${b} "*) continue ;; esac
    seen="${seen}${b} "
    emit_record - "$b" "$(ahead "refs/heads/${b}")" - branch 0 - 0 \
      "$(git rev-parse -q --verify "refs/heads/${b}" || echo -)"
    n=$((n + 1))
  done < <(git for-each-ref --format='%(refname:lstrip=2)' refs/heads)
  while IFS= read -r b; do
    if ! has_id "$b" "$id"; then continue; fi
    case "$seen" in *" ${b} "*) continue ;; esac
    emit_record - "origin/${b}" "$(ahead "refs/remotes/origin/${b}")" - branch 0 - 0 \
      "$(git rev-parse -q --verify "refs/remotes/origin/${b}" || echo -)"
    n=$((n + 1))
  done < <(git for-each-ref --format='%(refname:lstrip=3)' refs/remotes/origin)

  echo "found=${n}"
}

# メインのチェックアウト以外の worktree で、ブランチ名に Issue ID を含むもの（start の Phase D2 が
# 「worktree で作業中」に出す）。detached HEAD は Issue を引けず、登録だけが残ったものは移れないので出さない
cmd_worktrees() {
  [ $# -eq 0 ] || die 2 "worktrees は引数を取らない"
  local main_wt p sha gone lk b
  # 左の境界は has_id と同じ（abcTEAM-1 は ID にしない）。右は [0-9]+ が最長で取るので TEAM-12 を TEAM-1 にしない
  local re='(^|[^A-Za-z0-9])([A-Z]+-[0-9]+)'
  # porcelain の先頭がメインのチェックアウト（bare の repo なら bare の dir）
  main_wt=$(git worktree list --porcelain | sed -n '1s/^worktree //p')
  while IFS=$'\t' read -r p sha gone lk b; do
    if [ "$p" = "$main_wt" ] || [ "$gone" = 1 ] || [ -z "$b" ]; then continue; fi
    if [[ "$b" =~ $re ]]; then
      echo "id=${BASH_REMATCH[2]}"; echo "branch=${b}"; echo "worktree=${p}"
    fi
  done < <(list_worktrees)
}

# メインのチェックアウトにある未追跡の .env* を worktree へ写す。追跡済みのものは checkout で
# 既に入っており、worktree 側に同名のファイルがあれば上書きしない
copy_env() {
  local dest=$1 f rel
  while IFS= read -r -d '' f; do
    rel=${f#"${MAIN_ROOT}"/}
    if git -C "$MAIN_ROOT" ls-files --error-unmatch -- "$rel" >/dev/null 2>&1; then continue; fi
    if [ -e "${dest}/${rel}" ]; then continue; fi
    mkdir -p "$(dirname "${dest}/${rel}")"
    cp -p "$f" "${dest}/${rel}"
    echo "env_copied=${rel}"
  done < <(find "$MAIN_ROOT" -maxdepth 3 \
             \( -name node_modules -o -name .git -o -path "${MAIN_ROOT}/.claude" \) -prune \
             -o -name '.env*' -type f -print0)
}

# lockfile から依存を入れるコマンドを決める。lockfile を書き換えない形を選ぶ（新しいブランチに
# 意図しない lockfile の差分を作らないため）。yarn は v1 と v2 以降でフラグが違うので素の install
detect_install() {
  local dir=$1
  if [ -f "${dir}/pnpm-lock.yaml" ]; then echo "install=pnpm install --frozen-lockfile"
  elif [ -f "${dir}/yarn.lock" ]; then echo "install=yarn install"
  elif [ -f "${dir}/bun.lock" ] || [ -f "${dir}/bun.lockb" ]; then echo "install=bun install --frozen-lockfile"
  elif [ -f "${dir}/package-lock.json" ]; then echo "install=npm ci"
  fi
  if [ -f "${dir}/uv.lock" ]; then echo "install=uv sync --frozen"; fi
  if [ -f "${dir}/poetry.lock" ]; then echo "install=poetry install --no-root"; fi
  if [ -f "${dir}/Gemfile.lock" ]; then echo "install=bundle install"; fi
  return 0
}

cmd_worktree() {
  local branch="" name="" base=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --name) [ $# -ge 2 ] || die 2 "--name に値が無い"; name=$2; shift 2 ;;
      --base) [ $# -ge 2 ] || die 2 "--base に値が無い"; base=$2; shift 2 ;;
      -*) die 2 "未知のオプション: $1" ;;
      *) [ -z "$branch" ] || die 2 "ブランチ名は 1 つだけ: $1"; branch=$1; shift ;;
    esac
  done
  [ -n "$branch" ] || die 2 "ブランチ名が無い"
  git check-ref-format --branch "$branch" >/dev/null 2>&1 || die 2 "ブランチ名として不正: ${branch}"
  # EnterWorktree の name と同じ文字種に絞る（パスの外へ出る名前を作らない）
  case "$name" in
    ''|.|..|*[!A-Za-z0-9._-]*) die 2 "--name は英数字と . _ - だけ: '${name}'" ;;
  esac

  local path="${MAIN_ROOT}/.claude/worktrees/${name}" created=1 excluded=0 used_base="-" other p sha gone lk b msg

  # 別のパスで checkout 済みなら git worktree add は落ちるので、作らずにそこを返す（#305）。
  # 既存のチェックアウトなので .env* の複製も依存の検出もしない — メインのチェックアウトが
  # 返った回に install= を出すと、呼び出し側が node_modules を入れ直してしまう。
  # 登録だけが残った（prunable な）worktree は返せない（そこへは移れない）ので、すぐ下で止める
  other=$(checked_out_at "$branch")
  if [ -n "$other" ] && [ "$other" != "$path" ]; then
    echo "worktree=${other}"
    echo "branch=${branch}"
    echo "base=-"
    echo "created=0"
    echo "excluded=0"
    return 0
  fi

  # 登録だけが残った worktree が <branch> を持つか <path> にあると、git worktree add は already used /
  # already registered で落ちる（今のチェックアウトでの git switch も同じ）。prune はディレクトリが一時的に
  # 見えないだけの worktree の登録も消すので利用者に任せ、info/exclude に書く前に止める。
  # locked な登録は prune では消えない（案内が prune だけだと、打っても同じ所で止まり続ける）。
  # detached HEAD のコミットは登録の HEAD からしか辿れないことがあり、そのときは prune で登録と一緒に辿れなくなる
  while IFS=$'\t' read -r p sha gone lk b; do
    if [ "$gone" = 1 ] && { [ "$b" = "$branch" ] || [ "$p" = "$path" ]; }; then
      msg="${p} の worktree はディレクトリ（または中の .git）が無く、git に登録だけが残っている（${b:-detached HEAD}）。"
      if [ "$lk" = 1 ]; then
        msg="${msg}locked なので git worktree prune では消えない。外付けのディスクなどならつなぎ直して再実行する。不要なら上のパスを git worktree unlock してから git worktree prune し、再実行する"
      else
        msg="${msg}git worktree prune の後に再実行する"
      fi
      if [ -z "$b" ]; then
        msg="${msg}（detached HEAD のコミット ${sha} は、ほかのブランチに無ければ prune でどの ref からも辿れなくなる。要るなら先に git branch <名前> ${sha} で残す）"
      fi
      die 1 "$msg"
    fi
  done < <(list_worktrees)

  if [ -e "$path" ]; then
    git worktree list --porcelain | grep -qxF "worktree ${path}" \
      || die 1 "${path} は既にあるが worktree ではない"
    # 同じパスの worktree が別のブランチなら、頼まれたブランチの名前で created=0 を返すと、呼び出し側は
    # 判定と違うブランチで作業を続けてしまう（#305）
    [ "$other" = "$path" ] || die 1 "${path} は別のブランチ（または detached HEAD）の worktree。${branch} を checkout していない"
    created=0
  fi

  if ! git -C "$MAIN_ROOT" check-ignore -q ".claude/worktrees/${name}"; then
    mkdir -p "${COMMON}/info"
    echo ".claude/worktrees/" >> "${COMMON}/info/exclude"
    excluded=1
  fi

  if [ "$created" = 1 ]; then
    local err
    if git show-ref --verify -q "refs/heads/${branch}"; then
      err=$(git worktree add -q "$path" "$branch" 2>&1) || die 1 "git worktree add が失敗した: ${err}"
    elif git show-ref --verify -q "refs/remotes/origin/${branch}"; then
      # origin にだけあるブランチは既定ブランチから同名で切り直さず、それを追跡して取り出す（#305）。
      # 切り直すと別のマシンで積んだコミットと分岐する
      err=$(git worktree add -q --track -b "$branch" "$path" "origin/${branch}" 2>&1) \
        || die 1 "git worktree add が失敗した: ${err}"
      used_base="origin/${branch}"
    else
      if [ -z "$base" ]; then
        local def
        def=$(default_branch)
        [ -n "$def" ] || die 2 "既定ブランチを決められない。--base で起点を指定する"
        if git rev-parse -q --verify "refs/remotes/origin/${def}" >/dev/null; then
          base="origin/${def}"
        else
          base=$def
        fi
      fi
      err=$(git worktree add -q --no-track -b "$branch" "$path" "$base" 2>&1) \
        || die 1 "git worktree add が失敗した: ${err}"
      used_base=$base
    fi
  fi

  echo "worktree=${path}"
  echo "branch=${branch}"
  echo "base=${used_base}"
  echo "created=${created}"
  echo "excluded=${excluded}"
  copy_env "$path"
  detect_install "$path"
}

case "${1:-}" in
  status) shift; cmd_status "$@" ;;
  worktree) shift; cmd_worktree "$@" ;;
  existing) shift; cmd_existing "$@" ;;
  worktrees) shift; cmd_worktrees "$@" ;;
  *) die 2 "使い方: branch-setup.sh status | worktree <branch> --name <dir 名> [--base <ref>] | existing <ISSUE-ID> | worktrees" ;;
esac
