#!/usr/bin/env bash
# review-guide（code-review プラグイン）の読み合わせの締めが `変異テスト: 提案する` を出すときに、
# 呼び出し元（issue-workflow の軽量フロー・feature-dev の Phase 7）が利用者の承認を得てから回す変異テストの宣言。
#
# **このファイルの存在自体が宣言**（GitHub issue #307。`.claude/review-oracles.sh` と同じ流儀）。
# code-review 側はこれがあれば推測しない。契約の正本は code-review/references/review-guide-format.md の
# 「変異テストの提案」。
#
# 契約:
#   - 呼び方: リポジトリのルートから `bash .claude/mutation-test.sh --base <ref>`
#   - 対象は `git diff <ref>` に出る変更（未追跡のファイルは対象外。review-guide の diff と同じ）
#   - exit 0 … 実行した変異に生存なし（上限・タイムアウトで未実行が残った回を含む）、または未計測（対象行・変異が 0 個）。どれかは stdout で見分ける
#   - exit 1 … 生存あり（`--strict`。stdout に file:line と変異）か、途中で止まった（stderr に中断の FATAL と実行済みの件数）。stdout と stderr の両方で見分ける
#   - exit 2 … 判定不能（変異前のテストが赤い・前提が無い）
#   - 見分ける手がかりは宣言が出す。mutation-test.py では、未実行が残った回は集計の「上限で未実行 N」「タイムアウト N」、
#     未計測の回は集計の代わりの「変異対象の変更行が無い」「変異 0 個」の 1 行、途中で止まった回は stderr の中断の FATAL
#
# 所要の目安の根拠: 変異前のフルスイートは手元で約 650 秒（mutation-test.py の BASELINE_TIMEOUT の注記）。
# `--related-first` は CI のスモークと同じ短縮。上限の 25 個は mutation-test.py の既定。
# 所要の目安: 変異前のフルスイート約 11 分 + 変異 1 個あたり関連テストで数十秒（関連テストを通った変異はフルスイートをもう 1 回）・上限 25 個
#
# 実行中の注意（ルート CLAUDE.md の Gotchas）: 変異体は作業ツリーの実ファイルへ in-place で書かれる。
# 回しているあいだは対象ファイルを編集しない・別のセッションでテストを走らせない・Ctrl-C で止めない
# （復元が飛んで変異がツリーに残る）。
# 変異させるのは .py と .sh だけで、テストファイルも変異させない（それ以外だけを変えた回は「変異対象の変更行が無い」の exit 0）。
exec python3 "$(git rev-parse --show-toplevel)/.claude-plugin/scripts/mutation-test.py" --strict --related-first "$@"
