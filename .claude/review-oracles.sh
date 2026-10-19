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
#   - 実行時間は数分以内に収めること（既定 300 秒でタイムアウト＝欠測になる）
#
# 検査の並びは `.claude-plugin/scripts/machine-layer.sh` が正本（ここに複製しない）。
# **回帰テストは外している**（`--no-tests`）: 機械層の全体は 12 分 33 秒かかり、その大半が
# 回帰テストだった（2026-10-19 実測。導入時の 130 秒から伸びた）。300 秒で毎回打ち切られ、
# self-review は 5 分待ったうえで欠測になっていた。外すと静的検査だけで約 15 秒。
# 回帰テストは pre-commit と CI が必ず回す。feature-dev の Phase 5.3 もこの宣言を使うので、
# この repo ではそこでもテストは回らない（あちらの 600 秒でも打ち切られていた）。
# **変異テストも入れていない**: `--base` の解決が要る・実行時間が長い・「テストが何も
# 検証していない」の検出はレビュー前段の関心ではない（CI 側の役割）。
exec bash "$(git rev-parse --show-toplevel)/.claude-plugin/scripts/machine-layer.sh" --no-tests
