# shellcheck shell=bash
# 画面に影響するファイルの判定式（正本）。hooks/scripts/ui-change-reminder.sh（pending flag）と
# scripts/ui-impact.sh（動作確認を走らせるか）が source する。
# **他所へ複製しない**: 片方だけ直すと、flag は立つのに動作確認が skipped になる（またはその逆）。
# 照合は呼び出し側が `grep -iE` で行う（大文字小文字を区別しない。hook の従来の挙動）。

# 拡張子だけで画面のファイルと分かるもの。hook と ui-impact.sh の両方が使う
UI_PATH_ERE='\.(tsx|jsx|vue|svelte|css|scss|sass|less|html|astro|mdx|module\.css|module\.scss)$'

# ui-impact.sh だけが足す式: 画面の層のディレクトリ配下の .ts / .js（React の hooks・store・route など。
# 拡張子だけでは画面への影響が分からない / GitHub issue #306）。hook には使わない — 編集のたびに
# reminder と commit 前の gate を鳴らす側まで広げると、画面に触れない編集でも鳴る範囲が増える
UI_SCRIPT_ERE='(^|/)(components|pages|app|routes|views|layouts|hooks|composables|stores?)/(.*/)?[^/]+\.(ts|js|mts|mjs)$'
