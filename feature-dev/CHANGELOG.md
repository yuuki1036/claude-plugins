# Changelog

All notable changes to feature-dev plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.1] - 2026-05-01

### Changed

- 全 3 agent (code-explorer / code-architect / code-reviewer) の `tools` を 10 個から 7 個に最小化。削除: `NotebookRead`（Jupyter 用途は本プラグインの主流ではない）、`KillShell`（Phase 内シーケンシャル実行で非同期タスク不要）、`BashOutput`（agent は Bash を保持しないため呼び出せず無効）。Permission Pruning の原則（claude-plugins CLAUDE.md の Hook > LLM 判定とも整合）に従い、宣言ツールを必要最小限に絞ることで判定精度を上げる

## [1.1.0] - 2026-05-01

### Changed

- `code-architect` agent のモデルを `sonnet` → `opus` に変更。設計推論・複数案比較で adaptive thinking の深さを活用する
- `code-reviewer` agent のモデルを `sonnet` → `opus` に変更。confidence ≥80 フィルタの判定精度を上げ、誤検知を最小化する
- `code-explorer` は `sonnet` 維持（並列 2-3 起動・量重視・コスト効率）

### Added

- `code-architect` system prompt に **Issue Context Injection** セクション追加。linear-workflow / indie-workflow から upfront 引き渡された Issue メタ・親 Issue サマリー・関連 knowledge・既存の `feature_dev_plan:` を設計の起点として使用する
- `code-architect` system prompt に **Hook-First Rule Placement** セクション追加。新ルール提案時に Hook → Skill/Agent → CLAUDE.md の優先順位で配置先を判定する（CLAUDE.md の決定的検証優先ルールに整合）
- `commands/feature-dev.md` に **Phase 1.5: Issue Context Detection** 追加。`Issue ファイル:` パスや `feature_dev_plan:` frontmatter を検出すると Phase 2 (Codebase Exploration) をスキップし、context を Phase 4 architect に直接引き渡す
- `commands/feature-dev.md` の frontmatter に `allowed-tools`（Bash, Read, Glob, Grep, TodoWrite, AskUserQuestion）を明示宣言（command はオーケストレーター責務、低レベル探索は agent 側に委譲）

## [1.0.1] - 2026-05-01

### Fixed

- `README.md` の Author セクションに残っていた本家元著者の連絡先を内製化後の表記に修正（quality-check の固有情報混入チェックで検出）。元著者情報は `CHANGELOG.md` の fork 経緯記述で参照する形に変更

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
