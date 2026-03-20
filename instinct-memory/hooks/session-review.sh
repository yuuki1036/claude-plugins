#!/usr/bin/env bash
# session-review.sh — Stop hook
# セッション終了時に instinct 記録のリマインダーを出す
# 長いセッション（Claude の判断に委ねる）の場合のみ意味がある

set -euo pipefail

# stdin から hook 入力を読む（使わないが消費する必要がある）
cat > /dev/null

# リマインダーメッセージを stdout に出力
# Stop hook の stdout が Claude のコンテキストに入る
cat <<'EOF'
セッション終了前の instinct チェック:
このセッションで、ユーザーの訂正・好み・繰り返しパターンはあったか？
あれば instinct-learning スキルに従って memory/instincts.md に記録を検討せよ。
ただし些末なもの（typo、一回限りの問題）は記録しない。
記録する場合はユーザーに確認を取ること。
EOF
