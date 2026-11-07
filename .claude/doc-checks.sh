#!/usr/bin/env bash
# issue-workflow の doc-sync が回す「文書の機械チェック」の宣言（GitHub issue #365）。
#
# **このファイルの存在自体が宣言**。doc-sync は `.claude/doc-checks.sh` があれば実行し、無ければ
# 「宣言なし」と出して飛ばす。どの検査を文書の検査とみなすかはプロジェクトの判断なので、プラグイン側には持たせない。
#
# 契約:
#   - exit 0 … 緑 / exit 1 … 検出あり（stdout に内容）/ exit 2 … 判定不能（前提が無い等。緑と区別される）
#
# この repo の文書の検査（INDEX.md・CLAUDE.md の一覧の同期・区間の同期・SSoT pin・frontmatter）は
# 機械層の静的検査に入っているので、`.claude/review-oracles.sh` と同じ呼び方をする（約 15 秒。回帰テストは含まない）。
exec bash "$(git rev-parse --show-toplevel)/.claude-plugin/scripts/machine-layer.sh" --no-tests
