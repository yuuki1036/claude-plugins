#!/usr/bin/env bash
# self-review（code-review プラグイン）が agent を起動する前に走らせる「安いオラクル」の宣言。
#
# **このファイルの存在自体が宣言**（GitHub issue #137 / ADR-20260817170000）。
# code-review 側は `.claude/review-oracles.sh` があれば実行し、無ければ完全に no-op する。
# 何を安いオラクルとみなすかはプロジェクトの判断なので、プラグイン側には持たせない。
#
# 契約:
#   - exit 0     … 緑（機械層で落ちるものは無い）
#   - exit 1     … 検出あり（stdout に内容。reviewer には「既知」として渡る）
#   - exit 2     … 判定不能（前提が無い等。**緑と区別される**）
#   - 実行時間は数分以内に収めること（既定 300 秒でタイムアウト＝欠測になる）。
#     **このリポジトリの実測は 130 秒**（大半が unittest 512 件）。倍に増えたら
#     検査を分けるか、レビュー前段では回さない層を切り出す
#
# 検査の並びは `.claude-plugin/scripts/machine-layer.sh` が正本（ここに複製しない）。
# **変異テストは入れていない**: `--base` の解決が要る・実行時間が検査 3 本の合計を
# 超える・「テストが何も検証していない」の検出はレビュー前段の関心ではない（CI 側の役割）。
exec bash "$(git rev-parse --show-toplevel)/.claude-plugin/scripts/machine-layer.sh"
