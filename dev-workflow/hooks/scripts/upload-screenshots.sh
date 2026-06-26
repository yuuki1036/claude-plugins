#!/usr/bin/env bash
# upload-screenshots.sh — 指定ディレクトリの画像を専用ブランチにアップロードして raw URL を返す
# 使い方: upload-screenshots.sh <directory> [branch]
# 出力: <ファイル名><TAB><URL> を1行ずつ stdout に
#
# 挙動:
#   - cc-screenshots という専用ブランチ（orphan）に画像を蓄積する
#   - GitHub Release/tag は一切作らない（tag はリリース運用に予約されているため）
#   - branch が無ければ orphan branch を初回作成（リポジトリソースを含まない）
#   - 同名ファイルは Contents API で上書き（既存 sha を引いて update）
#   - directory 名を prefix にして衝突回避
#
# 注意: raw.githubusercontent.com の URL は public repo でのみ PR 上に描画される
#       （private repo では release download URL と同様に認証が要りインライン描画されない）

set -euo pipefail

DIR=${1:-}
BRANCH=${2:-cc-screenshots}

if [[ -z "$DIR" || ! -d "$DIR" ]]; then
  echo "Usage: $0 <directory> [branch]" >&2
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

# --- branch を用意（無ければ orphan branch を作る。idempotent） ---
if ! gh api "repos/${REPO}/branches/${BRANCH}" >/dev/null 2>&1; then
  # orphan: リポジトリのソースを含まない、README だけの tree から親なしコミットを作る
  TREE_SHA=$(printf '{"tree":[{"path":"README.md","mode":"100644","type":"blob","content":"# Claude Code screenshots\n\nUI screenshots hosted for PR embedding by dev-workflow ui-verify / pr-creator.\nThis is an asset branch (no release tag). Safe to delete or reset any time."}]}' \
    | gh api -X POST "repos/${REPO}/git/trees" --input - -q .sha) || {
    echo "ERROR: failed to create tree for ${BRANCH}" >&2
    exit 1
  }
  COMMIT_SHA=$(printf '{"message":"init %s asset branch","tree":"%s"}' "$BRANCH" "$TREE_SHA" \
    | gh api -X POST "repos/${REPO}/git/commits" --input - -q .sha) || {
    echo "ERROR: failed to create commit for ${BRANCH}" >&2
    exit 1
  }
  gh api -X POST "repos/${REPO}/git/refs" \
    -f ref="refs/heads/${BRANCH}" -f sha="$COMMIT_SHA" >/dev/null 2>&1 || {
    echo "ERROR: failed to create branch ${BRANCH}" >&2
    exit 1
  }
fi

PREFIX=$(basename "$DIR")

shopt -s nullglob
found=false
for f in "$DIR"/*.png "$DIR"/*.jpg "$DIR"/*.jpeg "$DIR"/*.webp; do
  [[ -f "$f" ]] || continue
  found=true
  BASE=$(basename "$f")
  UNIQUE="${PREFIX}-${BASE}"
  REMOTE_PATH="screenshots/${UNIQUE}"

  CONTENT=$(base64 < "$f" | tr -d '\n')

  # 既存ファイルがあれば sha を引いて update（無ければ create）
  EXISTING_SHA=$(gh api "repos/${REPO}/contents/${REMOTE_PATH}?ref=${BRANCH}" -q .sha 2>/dev/null || true)
  if [[ -n "$EXISTING_SHA" ]]; then
    PAYLOAD=$(printf '{"message":"upload %s","branch":"%s","content":"%s","sha":"%s"}' \
      "$UNIQUE" "$BRANCH" "$CONTENT" "$EXISTING_SHA")
  else
    PAYLOAD=$(printf '{"message":"upload %s","branch":"%s","content":"%s"}' \
      "$UNIQUE" "$BRANCH" "$CONTENT")
  fi

  if ! printf '%s' "$PAYLOAD" | gh api -X PUT "repos/${REPO}/contents/${REMOTE_PATH}" --input - >/dev/null 2>&1; then
    echo "ERROR: failed to upload ${UNIQUE}" >&2
    continue
  fi

  URL="https://raw.githubusercontent.com/${REPO}/${BRANCH}/${REMOTE_PATH}"
  printf "%s\t%s\n" "$BASE" "$URL"
done

if [[ "$found" = false ]]; then
  echo "WARNING: no images (png/jpg/jpeg/webp) found in $DIR" >&2
  exit 0
fi

exit 0
