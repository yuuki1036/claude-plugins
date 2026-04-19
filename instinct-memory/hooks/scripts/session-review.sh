#!/usr/bin/env bash
# session-review.sh — Stop hook
# セッション終了時に instinct 記録のリマインダーを出す

source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"
safe_hook_init "instinct-memory:session-review"

cat <<'EOF'
セッション終了前の instinct チェック:
このセッションで、ユーザーの訂正・好み・繰り返しパターンはあったか？
あれば instinct-learning スキルに従って memory/instincts.md に記録を検討せよ。
ただし些末なもの（typo、一回限りの問題）は記録しない。
記録する場合はユーザーに確認を取ること。
EOF
