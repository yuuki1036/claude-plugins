#!/usr/bin/env bash
# ui-impact.sh — 未コミットの変更が画面に影響するかを判定する（ui-verify の事前判定）。
#
# なぜ要るか:
#   feature-dev の Phase 5.5 と issue-workflow の軽量フローは、動作確認を ui-verify に
#   `verify --caller=<…>` で頼むだけで、UI に影響するかの判定を持たない（プラグイン間で判定を
#   複製しない / GitHub issue #306）。判定の正本はここで、判定式は ui-change-reminder.sh と
#   共通の scripts/lib/ui-paths.sh にある。
#
# 見る範囲:
#   HEAD（無ければ空 tree）と作業ツリー・index の差、および未追跡で ignore されていないファイル。
#   `git diff HEAD` だけだと未追跡の新規ファイルを落とし、index だけにある変更（作業ツリーで
#   戻したもの）も落とす。rename は旧名と新名の両方を数える（.tsx → .ts の改名も画面の変更）。
#
# 使い方:
#   ui-impact.sh
#
# 出力（KEY=VALUE を 1 行ずつ）:
#   UI_IMPACT=yes|no|unknown        unknown = git リポジトリ外・git が失敗した・判定式を読めない / 照合に
#                                   失敗した（確かめる側に倒す）
#   CHANGED_FILES=<n>  UI_FILES=<n>
#   UI_FILE=<toplevel 相対パス>      画面のファイルを先頭 20 件まで繰り返す
#   REASON=<1 行>                   no / unknown の理由。yes は空
#
# exit: 0（判定できないときも 0 で unknown を返す）/ 2 引数不正

set -uo pipefail

while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "FATAL: 未知の引数: $1" >&2; exit 2 ;;
  esac
done

unknown() {
  printf 'UI_IMPACT=unknown\nCHANGED_FILES=0\nUI_FILES=0\nREASON=%s\n' "$1"
  exit 0
}

# 判定式を読めない配布（lib を欠いた複製など）は no ではなく unknown（確かめる側に倒す）
UI_PATHS_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/ui-paths.sh"
if [ ! -r "$UI_PATHS_LIB" ]; then
  unknown "判定式（lib/ui-paths.sh）を読めない"
fi
# shellcheck source=lib/ui-paths.sh
. "$UI_PATHS_LIB"
if [ -z "${UI_PATH_ERE:-}" ] || [ -z "${UI_SCRIPT_ERE:-}" ]; then
  unknown "判定式（lib/ui-paths.sh）に UI_PATH_ERE / UI_SCRIPT_ERE が無い"
fi

UI_FILE_LIMIT=20

TOPLEVEL=$(git rev-parse --show-toplevel 2>/dev/null) || unknown "git リポジトリ外"

BASE=$(git -C "$TOPLEVEL" rev-parse -q --verify HEAD 2>/dev/null) \
  || BASE=$(git -C "$TOPLEVEL" hash-object -t tree /dev/null 2>/dev/null) \
  || unknown "比較先（HEAD / 空 tree）を引けない"

# -z で受ける: 非 ASCII のファイル名を 8 進エスケープの引用付きで出されると拡張子の照合が外れる
list_changed() {
  git -C "$TOPLEVEL" diff --name-only -z --no-renames "$BASE" || return 1
  git -C "$TOPLEVEL" diff --cached --name-only -z --no-renames "$BASE" || return 1
  git -C "$TOPLEVEL" ls-files --others --exclude-standard -z || return 1
}
RAW=$(list_changed | tr '\0' '\n') || unknown "git の差分を取れない"
CHANGED=$(printf '%s\n' "$RAW" | sed '/^$/d' | sort -u)

if [ -z "$CHANGED" ]; then
  N=0
else
  N=$(printf '%s\n' "$CHANGED" | wc -l | tr -d ' ')
fi
# grep の rc 1 は一致なし。2（式の誤りなど）を一致なしと混ぜると no に化ける
UI=$(printf '%s\n' "$CHANGED" | grep -iE -e "$UI_PATH_ERE" -e "$UI_SCRIPT_ERE") && RC=0 || RC=$?
if [ "$RC" -gt 1 ]; then
  unknown "画面のファイルの照合に失敗した（grep の rc ${RC}）"
fi
if [ -z "$UI" ]; then
  M=0
else
  M=$(printf '%s\n' "$UI" | wc -l | tr -d ' ')
fi

if [ "$M" -gt 0 ]; then
  printf 'UI_IMPACT=yes\n'
else
  printf 'UI_IMPACT=no\n'
fi
printf 'CHANGED_FILES=%s\nUI_FILES=%s\n' "$N" "$M"
if [ "$M" -gt 0 ]; then
  printf '%s\n' "$UI" | head -n "$UI_FILE_LIMIT" | sed 's/^/UI_FILE=/'
  printf 'REASON=\n'
elif [ "$N" -eq 0 ]; then
  printf 'REASON=未コミットの変更なし\n'
else
  printf 'REASON=変更 %s 件に画面のファイルなし\n' "$N"
fi
