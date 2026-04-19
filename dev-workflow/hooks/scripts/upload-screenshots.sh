#!/usr/bin/env bash
# upload-screenshots.sh — 指定ディレクトリの画像を GitHub Release にアップロード
# 使い方: upload-screenshots.sh <directory> [release-tag]
# 出力: <ファイル名><TAB><URL> を1行ずつ stdout に
#
# 挙動:
#   - cc-screenshots という prerelease タグに画像を蓄積
#   - 同名ファイルは --clobber で上書き
#   - directory 名を prefix にして衝突回避

set -euo pipefail

DIR=${1:-}
RELEASE_TAG=${2:-cc-screenshots}

if [[ -z "$DIR" || ! -d "$DIR" ]]; then
  echo "Usage: $0 <directory> [release-tag]" >&2
  exit 1
fi

command -v gh >/dev/null 2>&1 || {
  echo "ERROR: gh CLI not found" >&2
  exit 1
}

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null) || {
  echo "ERROR: not a GitHub repository or gh not authenticated" >&2
  exit 1
}

# Release 未作成なら作る（idempotent）
if ! gh release view "$RELEASE_TAG" >/dev/null 2>&1; then
  gh release create "$RELEASE_TAG" \
    --title "Claude Code Screenshots" \
    --notes "Automated screenshots from Claude Code ui-verify. Safe to delete any time." \
    --prerelease >/dev/null
fi

PREFIX=$(basename "$DIR")
TMPDIR_=$(mktemp -d)
trap 'rm -rf "$TMPDIR_"' EXIT

shopt -s nullglob
found=false
for f in "$DIR"/*.png "$DIR"/*.jpg "$DIR"/*.jpeg "$DIR"/*.webp; do
  [[ -f "$f" ]] || continue
  found=true
  BASE=$(basename "$f")
  UNIQUE="${PREFIX}-${BASE}"
  cp "$f" "${TMPDIR_}/${UNIQUE}"

  if ! gh release upload "$RELEASE_TAG" "${TMPDIR_}/${UNIQUE}" --clobber >/dev/null 2>&1; then
    echo "ERROR: failed to upload ${UNIQUE}" >&2
    continue
  fi

  URL="https://github.com/${REPO}/releases/download/${RELEASE_TAG}/${UNIQUE}"
  printf "%s\t%s\n" "$BASE" "$URL"
done

if [[ "$found" = false ]]; then
  echo "WARNING: no images (png/jpg/jpeg/webp) found in $DIR" >&2
  exit 0
fi

exit 0
