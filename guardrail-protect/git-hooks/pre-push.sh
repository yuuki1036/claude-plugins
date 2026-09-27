#!/usr/bin/env bash
# pre-push.sh — 公開リポジトリへの push に業務情報が入っていないかを検査する git hook
#
# PreToolUse の public-leak-guard は Claude が打つ push しか見ない。人の手の push・GUI クライアント・
# 他のエージェントの push はここで止める。**公開リポジトリごとに手で入れる**（README の手順）。
# global の core.hooksPath は業務リポジトリの husky 等を上書きするので使わない。
#
# 判定は PreToolUse と同じ検出器（hooks/scripts/detect-public-leak.py の pre-push モード）:
# push 先が private と確定すれば素通し。公開・不明なら push される commit の追加行・メッセージ・
# 作者・ファイル名・ref 名・tag を辞書とホスト名で照合し、当たれば push を止める（exit 1）。
# 検出器が見つからないときも止める（検査していないものを「問題なし」にしない）。
#
# 一時的に外すのは人の判断で `git push --no-verify`。

set -uo pipefail

self="$0"
if command -v python3 >/dev/null 2>&1; then
  self=$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$0" 2>/dev/null) || self="$0"
fi
root="${GUARDRAIL_PROTECT_ROOT:-$(dirname "$(dirname "$self")")}"
detector="${root}/hooks/scripts/detect-public-leak.py"

if ! command -v python3 >/dev/null 2>&1 || [ ! -f "$detector" ]; then
  echo "[guardrail-protect] pre-push: 検出器を起動できない（python3 / ${detector}）。push を止めた" >&2
  echo "  導入手順は guardrail-protect の README（公開リポジトリの pre-push）を参照" >&2
  exit 1
fi

python3 "$detector" pre-push "$@"
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "[guardrail-protect] pre-push: push を止めた。内容を置き換えて commit し直すか、" >&2
  echo "  確認のうえで意図して出すなら人が git push --no-verify で通す" >&2
  exit 1
fi
exit 0
