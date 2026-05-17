#!/usr/bin/env bash
# session-review.sh — Stop hook
# セッション終了時に instinct 記録のリマインダーを出す
# 追加: Event Bus subscriber として issue:completed を購読し、未消費があれば学習プロンプトを発行

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "instinct-memory:session-review"

# 既存の汎用 instinct リマインダー
cat <<'EOF'
セッション終了前の instinct チェック:
このセッションで、ユーザーの訂正・好み・繰り返しパターンはあったか？
あれば instinct-learning スキルに従って memory/instincts.md に記録を検討せよ。
ただし些末なもの（typo、一回限りの問題）は記録しない。
記録する場合はユーザーに確認を取ること。
EOF

# Event Bus subscriber: issue:completed の未消費イベントがあれば追加プロンプト
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
EVENTS_LOG="${PROJECT_DIR}/.claude/events.jsonl"
CURSOR_FILE="${PROJECT_DIR}/.claude/.instinct-memory-cursor"

if [ -f "$EVENTS_LOG" ]; then
  last_ts=""
  [ -f "$CURSOR_FILE" ] && last_ts=$(cat "$CURSOR_FILE" 2>/dev/null)

  # cursor より新しい issue:completed イベントを抽出
  new_events=$(grep '"event":"issue:completed"' "$EVENTS_LOG" 2>/dev/null | \
    awk -F'"ts":"' -v cur="$last_ts" '{
      split($2, a, "\"");
      ts = a[1];
      if (ts > cur) print $0;
    }')

  if [ -n "$new_events" ]; then
    count=$(printf '%s\n' "$new_events" | wc -l | tr -d ' ')
    issue_ids=$(printf '%s\n' "$new_events" | grep -oE '"issue_id":"[^"]+"' | sed -E 's/"issue_id":"([^"]+)"/\1/' | paste -sd ',' -)

    cat <<EOF

📌 Event Bus subscriber 通知 (instinct-memory):
前回チェック以降に \`issue:completed\` イベントを ${count} 件検知（${issue_ids}）。
これらの Issue から得られた学び・決定パターンを instincts.md に記録すべきか確認せよ:
  - 設計判断・実装方針 → \`reference\` メモリ
  - ユーザの好み・訂正パターン → \`feedback\` メモリ
  - プロジェクト固有の制約・経緯 → \`project\` メモリ
記録不要と判断した場合もユーザーに一言確認すること（学びの取りこぼし防止）。
EOF

    # cursor を最新 ts に更新（次セッションで重複通知しないため）
    latest_ts=$(printf '%s\n' "$new_events" | tail -1 | grep -oE '"ts":"[^"]+"' | head -1 | sed -E 's/"ts":"([^"]+)"/\1/')
    if [ -n "$latest_ts" ]; then
      printf '%s' "$latest_ts" > "$CURSOR_FILE" 2>/dev/null || true
    fi
  fi
fi
