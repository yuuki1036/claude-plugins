#!/usr/bin/env bash
# worktree-gc の実行フェーズ。scan.sh が出した JSON 行のうち、承認されたものを
# stdin で受け取り削除する。**判定を再実行しない**（ADR-20260912142858）。
#
# 使い方:
#   scan.sh | <承認で絞る> | reap.sh            # 削除する
#   scan.sh | <承認で絞る> | reap.sh --dry-run  # 削除内容を列挙するだけ
#
# 入力契約:
#   - stdin は scan.sh の出力行（1 行 1 JSON）。呼び出し側は行を **選ぶ**ことはできるが
#     **書き換えない**（表に出したものだけが消える）
#   - `verdict != "reap"` の行が 1 行でも混じれば全体を拒否して exit 2
#     （承認フローの迂回を機械的に塞ぐ）
#   - `path` が現在の `git worktree list` に実在しない行は SKIP + WARN（stale な承認を弾く）
#   - 削除直前に live_pids を再取得し、非空なら SKIP + WARN（became-live race を塞ぐ）
#   - 順序は nested（agent）→ 親（review）。同一 repo で remove を終えてから prune
#   - DB drop は marker のある行の db_name のみ。marker 無し行は DB に触れない
set -uo pipefail

DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1; shift ;;
    *) echo "usage: reap.sh [--dry-run] < <scan の承認済み行>" >&2; exit 2 ;;
  esac
done

command -v jq >/dev/null 2>&1 || { echo "FATAL: jq が要る" >&2; exit 2; }

INPUT=$(cat)
if [ -z "${INPUT//[$'\n\t ']/}" ]; then
  echo "対象なし（stdin が空）"
  exit 0
fi

# **全行がオブジェクトかつ verdict==reap でなければ全体を拒否**（承認フロー迂回の防止）。
# **fail-closed**: パース不能な行が混じると jq -s 自体が非ゼロで落ち `!` が真になり reject する
# （`jq -e 'select(.verdict!="reap")'` 型は非 JSON 混入で exit 5 になり「非 reap 無し(4)」と
#  区別できず素通りする fail-open だった）
if ! printf '%s\n' "$INPUT" | jq -e -s 'all(.[]; type=="object" and .verdict=="reap")' >/dev/null 2>&1; then
  echo "FATAL: reap 以外の行またはパース不能な行が含まれる（scan の出力をそのまま渡すこと）" >&2
  exit 2
fi

# 現在の worktree 一覧（実在チェック用。stale な承認を弾く）
LIVE_WORKTREES=$(git worktree list --porcelain 2>/dev/null | awk '/^worktree /{print substr($0,10)}')

have_lsof=0
command -v lsof >/dev/null 2>&1 && have_lsof=1
have_psql=0
command -v psql >/dev/null 2>&1 && have_psql=1

removed=0; skipped=0; failed=0; db_dropped=0; db_warned=0

# nested（agent）を先に、親を後に。sort_by(.nested_parent == null) は
# false(nested あり) < true(nested なし) で nested が先に来る
# 多重防御: verdict==reap のオブジェクトだけをループ対象にする（上のガードを通っても
# 万一 reap 以外が残らないよう、ループ入力側でも絞る）
SORTED=$(printf '%s\n' "$INPUT" | jq -c 'select(type=="object" and .verdict=="reap")' 2>/dev/null | jq -s -c 'sort_by(.nested_parent == null) | .[]' 2>/dev/null)

while IFS= read -r row; do
  [ -n "$row" ] || continue
  path=$(printf '%s' "$row" | jq -r '.path')
  kind=$(printf '%s' "$row" | jq -r '.kind')
  db_name=$(printf '%s' "$row" | jq -r '.db_guess[0] // empty')

  # prunable は dir が無いので prune に任せる（remove しない）
  if [ "$kind" = "prunable" ]; then
    echo "  prune 対象  $path"
    continue
  fi

  # 実在チェック（stale な承認を弾く）
  if ! printf '%s\n' "$LIVE_WORKTREES" | grep -qxF "$path"; then
    echo "  SKIP   $path （worktree list に無い。scan 後に消えた可能性）" >&2
    skipped=$((skipped+1)); continue
  fi

  # 削除直前の live_pids 再取得（became-live race）
  if [ "$have_lsof" = "1" ] && [ -d "$path" ]; then
    live=$(lsof -d cwd -a +D "$path" -t 2>/dev/null | tr '\n' ' ' | sed 's/ *$//')
    if [ -n "$live" ]; then
      echo "  SKIP   ${path} （生存プロセス: ${live}。scan 後に使い始めた）" >&2
      skipped=$((skipped+1)); continue
    fi
  fi

  # dirty 再確認（承認済みでも --force の前に WARN を残す）
  force=""
  if [ -d "$path" ] && [ -n "$(git -C "$path" status --porcelain 2>/dev/null)" ]; then
    echo "  WARN   $path に未コミット変更がある。--force で削除する" >&2
    force="--force"
  fi

  if [ "$DRY" = "1" ]; then
    echo "  would remove  $path${force:+ (--force)}"
    removed=$((removed+1))
  else
    if git worktree remove ${force:+$force} "$path" 2>/dev/null; then
      echo "  removed  $path"
      removed=$((removed+1))
    else
      echo "  FAILED $path （手動: git worktree remove --force '$path'）" >&2
      failed=$((failed+1)); continue
    fi
  fi

  # DB drop（marker のある行の db_name のみ。PostgreSQL 前提。他 engine は手動案内）
  if [ -n "$db_name" ]; then
    # db_name は外部入力（env ファイル由来）なので SQL に内挿する前に identifier 検証する。
    # 許可文字以外を含む値は自動 drop せず手動案内に落とす（DROP DATABASE インジェクション防止）
    if ! printf '%s' "$db_name" | grep -qE '^[A-Za-z_][A-Za-z0-9_]*$'; then
      echo "    WARN DB 名 '${db_name}' が識別子として不正。自動 drop しない（手動確認）" >&2
      db_warned=$((db_warned+1))
    elif [ "$have_psql" = "1" ] && psql -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${db_name}'" 2>/dev/null | grep -q 1; then
      if [ "$DRY" = "1" ]; then
        echo "    would drop db  $db_name"; db_dropped=$((db_dropped+1))
      elif psql -U postgres -c "DROP DATABASE IF EXISTS ${db_name};" >/dev/null 2>&1; then
        echo "    dropped db  $db_name"; db_dropped=$((db_dropped+1))
      else
        echo "    WARN db drop 失敗: ${db_name} （手動: psql -U postgres -c 'DROP DATABASE ${db_name};'）" >&2
        db_warned=$((db_warned+1))
      fi
    else
      echo "    WARN DB ${db_name} を自動 drop しない（psql 不在 or 別 engine）。残っていれば手動で drop" >&2
      db_warned=$((db_warned+1))
    fi
  fi

  # 親 dir が空になったら片付ける（best-effort）
  parent=$(dirname "$path")
  [ "$DRY" = "1" ] || rmdir "$parent" 2>/dev/null || true
done <<< "$SORTED"

# prune は repo ごとに 1 回（remove 後の残骸回収）
[ "$DRY" = "1" ] || git worktree prune 2>/dev/null || true

printf '完了: %d 件%s / SKIP %d 件 / 失敗 %d 件、DB: %d drop / %d 手動案内\n' \
  "$removed" "$([ "$DRY" = 1 ] && echo ' (dry-run)' || echo ' 削除')" \
  "$skipped" "$failed" "$db_dropped" "$db_warned"
exit 0
