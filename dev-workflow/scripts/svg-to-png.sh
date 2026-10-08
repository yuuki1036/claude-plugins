#!/usr/bin/env bash
# svg-to-png.sh — PR に添付する説明図（SVG）を PNG に書き出す（pr-creator Step 4.6 / GitHub issue #287）
#
# 使い方:
#   svg-to-png.sh <svg>...
# 各 <svg> の隣に拡張子を .png に替えたファイルを書き、1 ファイルにつき 1 行出す:
#   png=<png のパス>               変換できた
#   failed=<svg のパス>\t<理由>     変換できなかった
# exit 0 = 全件変換 / 1 = 1 件以上失敗 / 2 = 引数なし・変換手段が無い（rsvg-convert も Chrome も無い）
#
# 変換手段は rsvg-convert → headless Chrome の順に試す。rsvg-convert は入っていない環境が多いので、
# Chrome を代わりに使う。Chrome は CHROME_BIN があればそれだけを使い（無ければ Chrome 無しとして扱う）、
# 無ければ PATH の google-chrome 系 → macOS のアプリの順に探す。
#
# headless Chrome は撮影を終えてもプロセスが終わらず残ることがある（#287 の実例）。終了を待たず、
# PNG の大きさが 2 回続けて同じになった時点で止める。起動ごとに専用の --user-data-dir を作り、
# そのパスを引数に持つプロセス（子プロセスも同じプロファイルを指す）をまとめて止める。

set -u

TIMEOUT="${SVG_TO_PNG_TIMEOUT:-30}"
# 0.2 秒刻みで待つので、上限の回数は秒数の 5 倍
MAX_POLLS=$((TIMEOUT * 5))

if [ $# -eq 0 ]; then
  echo "usage: svg-to-png.sh <svg>..." >&2
  exit 2
fi

find_chrome() {
  if [ -n "${CHROME_BIN+x}" ]; then
    if [ -x "$CHROME_BIN" ]; then
      printf '%s\n' "$CHROME_BIN"
    fi
    return 0
  fi
  local c
  for c in google-chrome google-chrome-stable chromium chromium-browser; do
    if command -v "$c" >/dev/null 2>&1; then
      command -v "$c"
      return 0
    fi
  done
  for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
           "/Applications/Chromium.app/Contents/MacOS/Chromium"; do
    if [ -x "$c" ]; then
      printf '%s\n' "$c"
      return 0
    fi
  done
  return 0
}

RSVG=""
if command -v rsvg-convert >/dev/null 2>&1; then
  RSVG=$(command -v rsvg-convert)
fi
CHROME=$(find_chrome)

if [ -z "$RSVG" ] && [ -z "$CHROME" ]; then
  echo "FATAL: SVG を PNG にする手段が無い（rsvg-convert も Chrome も見つからない）。SVG のまま添付するか、どちらかを入れる" >&2
  exit 2
fi

# ルート要素の width / height（px の数値）を取る。無ければ viewBox の幅・高さ、それも無ければ空
svg_size() {
  local tag w h vb
  tag=$(tr '\n' ' ' < "$1" | grep -o '<svg[^>]*>' | head -1)
  w=$(printf '%s' "$tag" | sed -n 's/.*[[:space:]]width="\([0-9][0-9.]*\)\(px\)\{0,1\}".*/\1/p')
  h=$(printf '%s' "$tag" | sed -n 's/.*[[:space:]]height="\([0-9][0-9.]*\)\(px\)\{0,1\}".*/\1/p')
  if [ -z "$w" ] || [ -z "$h" ]; then
    vb=$(printf '%s' "$tag" | sed -n 's/.*viewBox="\([^"]*\)".*/\1/p')
    if [ -n "$vb" ]; then
      w=$(printf '%s\n' "$vb" | awk '{print $3}')
      h=$(printf '%s\n' "$vb" | awk '{print $4}')
    fi
  fi
  # 小数は切り上げずに切り捨てる（Chrome の --window-size は整数しか受けない）
  if [ -n "$w" ] && [ -n "$h" ]; then
    printf '%s %s\n' "${w%%.*}" "${h%%.*}"
  fi
}

file_size() {
  wc -c < "$1" 2>/dev/null | tr -d ' '
}

with_rsvg() {
  "$RSVG" --zoom=2 --background-color=white -o "$2" "$1" >/dev/null 2>&1
}

# 成功なら 0。失敗の理由は REASON に入れる
with_chrome() {
  local svg="$1" png="$2" size w h abs profile pid polls=0 prev="" cur
  size=$(svg_size "$svg")
  if [ -z "$size" ]; then
    REASON="ルートの <svg> に width / height も viewBox も無い（Chrome の撮影範囲を決められない）"
    return 1
  fi
  w=${size% *}
  h=${size#* }
  abs="$(cd "$(dirname "$svg")" && pwd)/$(basename "$svg")"
  profile=$(mktemp -d "${TMPDIR:-/tmp}/svg-to-png.XXXXXX")
  rm -f "$png"
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run --no-default-browser-check \
    --user-data-dir="$profile" --window-size="${w},${h}" --force-device-scale-factor=2 \
    --default-background-color=ffffffff --screenshot="$png" "file://${abs}" >/dev/null 2>&1 &
  pid=$!
  REASON="Chrome が ${TIMEOUT} 秒以内に PNG を書かなかった"
  while [ "$polls" -lt "$MAX_POLLS" ]; do  # mutation-ok: 上限の 1 回（0.2 秒）の差は打ち切りの時刻から観測できない
    sleep 0.2
    polls=$((polls + 1))
    if [ -s "$png" ]; then
      cur=$(file_size "$png")
      if [ "$cur" = "$prev" ]; then  # mutation-ok: 書きかけの PNG を見せる Chrome を stub で決定的に作れない（時間依存で不安定になる）
        REASON=""
        break
      fi
      prev=$cur
    elif ! kill -0 "$pid" 2>/dev/null; then
      REASON="Chrome が PNG を書かずに終了した"
      break
    fi
  done
  kill "$pid" 2>/dev/null
  pkill -f -- "$profile" 2>/dev/null
  wait "$pid" 2>/dev/null
  rm -rf "$profile"
  if [ -n "$REASON" ]; then
    return 1
  fi
  return 0
}

RC=0
for svg in "$@"; do
  case "$svg" in
    *.svg) ;;
    *) printf 'failed=%s\t%s\n' "$svg" "拡張子が .svg でない"; RC=1; continue ;;
  esac
  if [ ! -f "$svg" ]; then
    printf 'failed=%s\t%s\n' "$svg" "ファイルが無い"
    RC=1
    continue
  fi
  png="${svg%.svg}.png"
  if [ -n "$RSVG" ] && with_rsvg "$svg" "$png" && [ -s "$png" ]; then
    printf 'png=%s\n' "$png"
    continue
  fi
  if [ -n "$CHROME" ]; then
    REASON=""
    if with_chrome "$svg" "$png"; then
      printf 'png=%s\n' "$png"
      continue
    fi
    printf 'failed=%s\t%s\n' "$svg" "$REASON"
  else
    printf 'failed=%s\t%s\n' "$svg" "rsvg-convert が失敗し、Chrome も無い"
  fi
  RC=1
done
exit "$RC"
