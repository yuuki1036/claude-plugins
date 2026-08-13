#!/usr/bin/env bash
# 同一 diff に対する直近のレビューを検出する（skill をまたぐ二重レビューの検知 / issue #123 D）。
#
# `--focus` / `--exclude` は同一 skill 内の重複しか防げない。self-review 直後に review
# （あるいは他プラグイン経由のレビュー）を回すと、互いを知らないまま同じ diff を 2 回舐める。
# 実測では独立した 2 経路が同じ 3 件に到達していた。
#
# **突合キーは 2 本ある**（強弱の意味とキー算出の正本: lib/review-paths.sh の `review_diff_keys`）:
#   - `diff_digest`（強）: diff 全文の cksum。**同一 skill の再実行でのみ一致する**
#   - `diff_files`（弱）: 変更ファイルパスの集合。**skill を跨いでも一致する**が、別内容でも
#     一致しうるので「重複の疑い」どまり
# review と self-review では diff の作り方自体が違う（`gh pr diff` vs 3 本連結の `git diff`）
# ため、強いキーだけでは skill 跨ぎを拾えない — この非対称は実測で確認済み。
#
# 使い方:
#   detect-recent-review.sh [--diff <diff ファイルの実パス>] [--window-hours N] [--pr N]
#
# **`--diff` は省略してよい**（省略時は `review_path diff` を自力導出する。`triage-signals.sh`
# の既定出力先・`publish-review-event.sh` の digest 算出元と同一関数なので、省略した方が
# 転記ずれの失敗モードが無い）。明示指定したパスが不在・空のときだけ stderr に警告する。
#
# 出力: 該当があれば `## recent-review` ブロック。無ければ何も出さず exit 0。
#       呼び出し側は**出力が空なら黙って続行**する（no-op を報告させない）。
set -uo pipefail

DIFF=""; DIFF_EXPLICIT=0; WINDOW=24; PR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --diff)         [ $# -ge 2 ] || { echo "FATAL: --diff に値が必要" >&2; exit 2; }; DIFF="$2"; DIFF_EXPLICIT=1; shift 2 ;;
    --window-hours) [ $# -ge 2 ] || { echo "FATAL: --window-hours に値が必要" >&2; exit 2; }; WINDOW="$2"; shift 2 ;;
    --pr)           [ $# -ge 2 ] || { echo "FATAL: --pr に値が必要" >&2; exit 2; }; PR="$2"; shift 2 ;;
    *) echo "FATAL: 未知の引数: $1" >&2; exit 2 ;;
  esac
done
case "$WINDOW" in ''|*[!0-9]*) echo "FATAL: --window-hours は数値のみ（受領: '$WINDOW'）" >&2; exit 2 ;; esac

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/review-paths.sh
. "$HERE/lib/review-paths.sh"
review_paths_init "$PR" || exit 2

[ -n "$DIFF" ] || DIFF=$(review_path diff)
if [ ! -s "$DIFF" ]; then
  # **明示指定の不在は caller のバグ**なので黙らない（重複が無いことの証明にはならない）。
  # 自力導出のフォールバックが空なのは「まだ diff を保存していない」だけなので silent。
  # publish 側は digest を作れなかったとき `measurement_gaps` に `diff-digest` を立てる
  [ "$DIFF_EXPLICIT" = "1" ] && \
    echo "WARN: --diff が空か存在しない: $DIFF（重複検出をスキップ。引数を省けば自力導出する）" >&2
  exit 0
fi

KEYS=$(review_diff_keys "$DIFF") || exit 0
read -r DIGEST FILES_KEY <<< "$KEYS"
[ -n "$DIGEST" ] || exit 0

review_event_logs || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

REVIEW_DIGEST="$DIGEST" REVIEW_FILES_KEY="$FILES_KEY" REVIEW_WINDOW="$WINDOW" \
  python3 - ${REVIEW_EVENT_LOGS[@]+"${REVIEW_EVENT_LOGS[@]}"} <<'PY'
import json, os, sys
from datetime import datetime, timedelta, timezone

digest = os.environ["REVIEW_DIGEST"]
files_key = os.environ.get("REVIEW_FILES_KEY") or ""
window = int(os.environ["REVIEW_WINDOW"])
cutoff = datetime.now(timezone.utc) - timedelta(hours=window)

hits, seen = [], set()
for path in sys.argv[1:]:
    try:
        # errors="replace" は必須。既定の strict だと UnicodeDecodeError（OSError ではなく
        # ValueError 系）が下の except を貫通し、**非 UTF-8 バイト 1 つで恒久クラッシュ**する。
        # events.jsonl は全プラグイン共有の追記ログで、payload は信頼前提で組まれている
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        continue
    # 直近から遡る。events.jsonl は追記のみなので後ろが新しい
    for line in reversed(lines[-2000:]):
        line = line.strip()
        if not line or '"review:completed"' not in line:
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue          # 壊れた 1 行で集計全体を落とさない
        if ev.get("event") != "review:completed":
            continue
        p = ev.get("payload") or {}
        if p.get("diff_digest") == digest:
            strength = "exact"
        elif files_key and p.get("diff_files") == files_key:
            strength = "files"   # skill 跨ぎで拾えるのはこちら
        else:
            continue
        ts = ev.get("ts") or ""
        try:
            when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when < cutoff:
            continue
        key = (ts, ev.get("plugin"))
        if key in seen:       # 2 つの候補パスが同一ファイルを指す場合の重複除去
            continue
        seen.add(key)
        hits.append((ts, ev.get("plugin", "?"), strength, p))

if not hits:
    sys.exit(0)

hits.sort(key=lambda h: h[0], reverse=True)
n_exact = sum(1 for h in hits if h[2] == "exact")
print("## recent-review")
print("直近 %d 時間以内に %d 件（うち diff 完全一致 %d 件 / 変更ファイル集合のみ一致 %d 件）:"
      % (window, len(hits), n_exact, len(hits) - n_exact))
for ts, plugin, strength, p in hits[:5]:
    counts = "B%s/C%s/M%s/m%s" % (
        p.get("blocker_count", "?"), p.get("critical_count", "?"),
        p.get("major_count", "?"), p.get("minor_count", "?"))
    label = "完全一致" if strength == "exact" else "ファイル集合のみ"
    print("- %s  %s  [%s]  effort=%s  size=%s  報告 %s  fleet=%s min" % (
        ts, plugin, label, p.get("effort", "?"), p.get("size_tier", "?"),
        counts, p.get("duration_fleet_min", "?")))
if n_exact < len(hits):
    print("※ 「ファイル集合のみ」は**別内容の変更でも一致しうる**（skill 跨ぎを拾うための弱いキー）。"
          "続行可否の判断材料であって、重複の証明ではない。")
PY
exit 0
