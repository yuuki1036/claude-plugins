#!/usr/bin/env bash
# fetch-pr-context.sh — PR 会話コンテキストを構造化 markdown で取得する
#
# Usage:
#   fetch-pr-context.sh <PR番号> [--repo OWNER/REPO]           # stdout に出力
#   fetch-pr-context.sh <PR番号> --save                        # ファイルに保存しパスを stdout に出す
#
# --save は「一時ファイルに書いて成功時のみ mv」する。`>` はスクリプトが失敗しても
# 空ファイルを残し、空ファイルは「読める」ため reviewer の「読めなかった場合」ガードを
# すり抜けて「過去指摘なし」と誤判定される（正本: orchestration-guide.md `## 3.5`）。
# パスの識別子は worktree のルート + PR 番号（並行セッションの衝突回避・同 `## 13.1`）。
#
# 取得対象:
#   - PR メタ情報（番号 / タイトル / 著者 / base / head / URL / body）
#   - issue コメント（PR 全体への議論）
#   - レビューサマリ（APPROVED / CHANGES_REQUESTED / COMMENTED）
#   - 行単位 review コメント（返信チェーン付き）
#
# 出力フォーマットは review SKILL.md Step 2.5 の「PR コンテキストブロック」に準拠。
# 各セクションは取得失敗時も「（なし）」を出力し、reviewer が項目の有無を判別できるようにする。

set -euo pipefail

# --save は本体の出力をファイルへ落とす薄いラッパー。本体ロジックには一切触れない。
# パス導出は lib/review-paths.sh が正本（式をここに複製しない）
SAVE=0
ARGS=()
for a in "$@"; do
  if [[ "$a" == "--save" ]]; then SAVE=1; else ARGS+=("$a"); fi
done
if [[ "$SAVE" == "1" ]]; then
  HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  # shellcheck source=lib/review-paths.sh
  . "$HERE/lib/review-paths.sh"
  # PR 番号は --save 除去後の第 1 引数（`--save 123` の順で呼ばれても取り違えない）
  review_paths_init "${ARGS[0]:-}" || exit 2
  OUT=$(review_path prctx)
  trap 'rm -f "$OUT.tmp"' EXIT
  if bash "$HERE/$(basename "${BASH_SOURCE[0]}")" ${ARGS[@]+"${ARGS[@]}"} > "$OUT.tmp" && [ -s "$OUT.tmp" ]; then
    mv "$OUT.tmp" "$OUT"
    echo "$OUT"
    exit 0
  fi
  echo "ERROR: PR コンテキストを取得できませんでした（PR=${ARGS[0]:-?}）" >&2
  exit 1
fi

PR_NUMBER="${1:-}"
if [[ -z "$PR_NUMBER" ]]; then
  echo "Usage: $0 <PR番号> [--repo OWNER/REPO]" >&2
  exit 1
fi
shift

REPO_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      if [[ -z "${2:-}" ]]; then
        echo "ERROR: --repo にはリポジトリ名を指定してください" >&2
        exit 1
      fi
      REPO_ARGS=(--repo "$2")
      shift 2
      ;;
    *)
      echo "ERROR: 未知の引数: $1" >&2
      exit 1
      ;;
  esac
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: $1 コマンドが見つかりません" >&2
    exit 1
  fi
}
require_cmd gh
require_cmd jq

fetch_or_fail() {
  local label="$1"
  shift
  local out
  if ! out=$("$@" 2>&1); then
    echo "ERROR: ${label} の取得に失敗しました: $out" >&2
    exit 1
  fi
  printf '%s' "$out"
}

META=$(fetch_or_fail "PR メタ情報" gh pr view "$PR_NUMBER" ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} \
  --json number,title,url,author,state,headRefName,baseRefName,body)
ISSUE_COMMENTS_JSON=$(fetch_or_fail "issue コメント" gh pr view "$PR_NUMBER" ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} --json comments)
REVIEWS_JSON=$(fetch_or_fail "レビューサマリ" gh pr view "$PR_NUMBER" ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} --json reviews)

# 行単位 review コメントは pulls API から（gh pr view では取得できない）
REPO_FULL=$(gh repo view ${REPO_ARGS[@]+"${REPO_ARGS[@]}"} --json nameWithOwner --jq '.nameWithOwner')
LINE_COMMENTS_JSON=$(fetch_or_fail "行単位 review コメント" \
  gh api "repos/${REPO_FULL}/pulls/${PR_NUMBER}/comments" --paginate)

echo "## PR コンテキスト"
echo ""

echo "### PR 情報"
echo "$META" | jq -r '
  "- #\(.number) \(.title)",
  "- 著者: @\(.author.login // "unknown")",
  "- Base → Head: \(.baseRefName) → \(.headRefName)",
  "- State: \(.state)",
  "- URL: \(.url)"
'
echo ""

echo "### PR 説明（著者が明示したスコープ・意図）"
BODY=$(echo "$META" | jq -r '.body // ""')
if [[ -z "$BODY" || "$BODY" == "null" ]]; then
  echo "（空）"
else
  echo "$BODY"
fi
echo ""

echo "### Issue コメント（PR 全体への議論）"
ISSUE_COUNT=$(echo "$ISSUE_COMMENTS_JSON" | jq '.comments | length')
if [[ "$ISSUE_COUNT" -eq 0 ]]; then
  echo "（なし）"
else
  echo "$ISSUE_COMMENTS_JSON" | jq -r '
    .comments | sort_by(.createdAt) | .[] |
    "- [@\(.author.login // "unknown"), \(.createdAt[:10])] \(.body | gsub("\n"; " "))"
  '
fi
echo ""

echo "### レビューサマリ"
REVIEW_COUNT=$(echo "$REVIEWS_JSON" | jq '.reviews | length')
if [[ "$REVIEW_COUNT" -eq 0 ]]; then
  echo "（なし）"
else
  echo "$REVIEWS_JSON" | jq -r '
    .reviews | sort_by(.submittedAt) | .[] |
    "- [@\(.author.login // "unknown"), \(.state), \((.submittedAt // "")[:10])] \(.body // "(no body)" | gsub("\n"; " "))"
  '
fi
echo ""

echo "### 行単位レビューコメント（過去の指摘）"
LINE_COUNT=$(echo "$LINE_COMMENTS_JSON" | jq 'length')
if [[ "$LINE_COUNT" -eq 0 ]]; then
  echo "（なし）"
else
  # ルートコメント（in_reply_to_id が無い）と返信を分離してインデント表示
  echo "$LINE_COMMENTS_JSON" | jq -r '
    sort_by(.created_at) | .[] |
    if .in_reply_to_id then
      "  - 返信 [#\(.in_reply_to_id) への返信] [@\(.user.login)] \(.body | gsub("\n"; " "))"
    else
      "- [#\(.id)] [@\(.user.login), \(.path):\(.line // .original_line // "?")] \(.body | gsub("\n"; " "))"
    end
  '
fi
