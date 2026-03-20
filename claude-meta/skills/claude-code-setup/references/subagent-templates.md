# Subagent推奨パターン

サブエージェントは並列で動く専門Claude。レビュー、分析、生成タスクに最適。
`.claude/agents/` に配置。

## コードレビュー系

| コードベースシグナル | エージェント | モデル | ツール |
|-------------------|------------|--------|--------|
| 大規模コードベース (>500ファイル) | code-reviewer | sonnet | Read, Grep, Glob, Bash |
| 認証/決済コード | security-reviewer | sonnet | Read, Grep, Glob |
| テストカバレッジ不足 | test-writer | sonnet | Read, Write, Grep, Glob |

## 専門系

| コードベースシグナル | エージェント | モデル | ツール |
|-------------------|------------|--------|--------|
| APIルート | api-documenter | sonnet | Read, Write, Grep, Glob |
| DB多用 | performance-analyzer | sonnet | Read, Grep, Glob, Bash |
| フロントエンドコンポーネント | ui-reviewer | sonnet | Read, Grep, Glob |

## ユーティリティ系

| コードベースシグナル | エージェント | モデル | ツール |
|-------------------|------------|--------|--------|
| 依存関係が古い | dependency-updater | sonnet | Read, Write, Bash, Grep |
| フレームワーク古い | migration-helper | opus | Read, Write, Grep, Glob, Bash |

## モデル選択ガイド

| モデル | 用途 | トレードオフ |
|-------|------|------------|
| haiku | シンプルな反復チェック | 高速・安価・精度低め |
| sonnet | 大半のレビュー/分析 | バランス（推奨デフォルト） |
| opus | 複雑な移行・設計 | 精度高・遅い・高価 |
