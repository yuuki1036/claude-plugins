# Changelog

All notable changes to feature-dev plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-05-01

### Added

- claude-plugins-official/feature-dev からフォークし、yuuki1036-claude-plugins マーケットプレイス配下に取り込み
- `/feature-dev` コマンド（7 phase ワークフロー: Discovery → Codebase Exploration → Clarifying Questions → Architecture Design → Implementation → Quality Review → Summary）
- `code-explorer` agent（実行パス追跡・抽象層マッピング・依存関係分析）
- `code-architect` agent（既存パターン分析・実装ブループリント設計）
- `code-reviewer` agent（信頼度 ≥80 のみ報告するバグ・規約レビュー）

### Notes

- 本リリースは無改造の fork。本家はメタデータ未整備（version フィールド無し）のため、内製化により version 管理・linear-workflow との深い連携・モデル切り替え自由度を確保する
- 後続マイルストーンで code-reviewer と code-review プラグインの責務整理、Linear Issue メタの agent prompt 反映、モデル選択の柔軟化を検討予定
