#!/usr/bin/env bash
# pick-screenshot-dir.sh — pr-creator の Step 4.5 が PR に添付する撮影ディレクトリを選ぶ。
#
# なぜ要るか:
#   `.claude/screenshots/` はチェックアウトに 1 つで、ブランチを切り替えても残る。最新の
#   {snap,verify,tune}-* をそのまま添付すると、同じチェックアウトで前に別のブランチで撮った画面が
#   この PR に載る（public repo なら誰でも見られる）。今のブランチで撮ったものに限る。
#
# 「今のブランチで撮った」の判定:
#   ディレクトリの mtime が、このチェックアウトが今のブランチに切り替わった時刻（SINCE）より後。
#   SINCE は HEAD の reflog（worktree ごとに別）から取る:
#     checkout      最も新しい `checkout: moving from <a> to <b>` の時刻。a と b が同じもの
#                   （今のブランチへの checkout し直し）は切り替えではないので飛ばす
#     reflog-start  checkout の記録が無ければ、reflog の最も古い記録の時刻（worktree の作成・clone）
#     none          reflog が無い / 読めない。どれも選ばない（取り違えを添付するより撮り直す側に倒す）
#   分岐点のコミット時刻は使わない: base の最後のコミットが古いと、その後に別のブランチで撮った
#   ものまで通す。verification.md の last_updated も使わない: verify は撮った後に記録を書くので、
#   それより後という条件では verify 自身の撮影が落ちる。
#   今のブランチで撮った後に別のブランチへ移って戻った回は、その撮影も外れる（撮り直しになる）
#
# 見る場所は cwd の .claude/screenshots（git のトップではない）:
#   ui-verify は撮影を cwd からの相対パス `.claude/screenshots/...` に書き、pr-creator は返したパスを
#   そのまま `--attach` に渡す（`$VERI` も cwd 基準）。トップを見ると、cwd がトップでないセッション
#   （monorepo のサブパッケージを開いた回など）で今のブランチの撮影が見えず、返したパスも cwd から引けない
#
# 使い方:
#   pick-screenshot-dir.sh      # pr-creator と同じ cwd で呼ぶ
#
# 出力（KEY=VALUE を 1 行ずつ）:
#   SCREENSHOT_DIR=<cwd からの相対パス>|none   条件に合ううち mtime が最も新しいもの
#   SINCE=<epoch 秒>（SINCE_SOURCE=none なら空）
#   SINCE_SOURCE=checkout|reflog-start|none
#   SKIPPED=<n>    SINCE より前の撮影として外したディレクトリの数
#   REASON=<1 行>  SCREENSHOT_DIR=none の理由（ほかは空）
#
# exit: 0 判定できた（none を含む）/ 2 git リポジトリ外・引数不正

set -uo pipefail

case "${1:-}" in
  "") ;;
  -h|--help) sed -n '2,36p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "FATAL: 未知の引数: $1" >&2; exit 2 ;;
esac

git rev-parse --show-toplevel >/dev/null 2>&1 || { echo "FATAL: git リポジトリ外" >&2; exit 2; }
ROOT=".claude/screenshots"

# GNU（Linux）は -c、BSD（macOS）は -f。GNU の -f はファイルシステムの情報で %m を `?` にするので、
# 数字でなければ取れなかった扱い
mtime() {
  local t
  t=$(stat -c %Y -- "$1" 2>/dev/null) || t=$(stat -f %m -- "$1" 2>/dev/null) || t=""
  if [[ "$t" =~ ^[0-9]+$ ]]; then
    printf '%s\n' "$t"
  fi
}

SINCE=""; SINCE_SOURCE=none; OLDEST=""
# HEAD の reflog が無いと、git reflog は今のブランチの reflog を代わりに出す（作成時刻が SINCE に
# なり、作成から今の checkout までに別のブランチで撮ったものを通す）ので、ファイルの有無を先に見る
HEAD_LOG=$(git rev-parse --git-path logs/HEAD 2>/dev/null || true)
if [ -n "$HEAD_LOG" ] && [ -s "$HEAD_LOG" ]; then
  # 新しい順に並ぶ。`%gd` は --date=unix で `HEAD@{<epoch>}` になる
  while IFS=$'\t' read -r sel subj; do
    ts="${sel##*@\{}"
    ts="${ts%\}}"
    [[ "$ts" =~ ^[0-9]+$ ]] || continue  # mutation-ok: git は --date=unix の %gd に常に数字を出す（数字でない時刻を下の比較に渡さないための守り）
    OLDEST="$ts"
    case "$subj" in
      "checkout: moving from "*" to "*)
        # ref 名は空白を含めないので " to " で切れる
        rest="${subj#checkout: moving from }"
        if [ "${rest%% to *}" != "${rest#* to }" ]; then
          SINCE="$ts"; SINCE_SOURCE=checkout
          break
        fi
        ;;
    esac
  done < <(git reflog show --date=unix --format='%gd%x09%gs' HEAD 2>/dev/null)
fi
if [ -z "$SINCE" ] && [ -n "$OLDEST" ]; then
  SINCE="$OLDEST"; SINCE_SOURCE=reflog-start
fi

FOUND=0; SKIPPED=0; BEST=""; BEST_T=""
for d in "$ROOT"/snap-* "$ROOT"/verify-* "$ROOT"/tune-*; do
  [ -d "$d" ] || continue
  FOUND=$((FOUND + 1))
  t=$(mtime "$d")
  if [ -z "$SINCE" ] || [ -z "$t" ] || [ "$t" -le "$SINCE" ]; then
    SKIPPED=$((SKIPPED + 1))
    continue
  fi
  if [ -z "$BEST" ] || [ "$t" -gt "$BEST_T" ]; then  # mutation-ok: -ge にすると同じ mtime の 2 つのうち後に見た方を採る。どちらも SINCE より後に撮ったもので、選び方の契約は「最も新しいもの」まで
    BEST="$d"; BEST_T="$t"
  fi
done

REASON=""
if [ -n "$BEST" ]; then
  SCREENSHOT_DIR="$BEST"
else
  SCREENSHOT_DIR=none
  if [ "$FOUND" -eq 0 ]; then
    REASON="撮影ディレクトリ（.claude/screenshots/ の snap-* / verify-* / tune-*）が無い"
  elif [ "$SINCE_SOURCE" = none ]; then
    REASON="HEAD の reflog が読めず、今のブランチに切り替わった時刻が分からない"
  else
    REASON="今のブランチに切り替わった後に撮ったものが無い（${SKIPPED} 件はそれより前）"
  fi
fi

printf 'SCREENSHOT_DIR=%s\nSINCE=%s\nSINCE_SOURCE=%s\nSKIPPED=%s\nREASON=%s\n' \
  "$SCREENSHOT_DIR" "$SINCE" "$SINCE_SOURCE" "$SKIPPED" "$REASON"
exit 0
