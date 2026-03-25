---
name: review
description: |
  2フェーズ構成の並列エージェントコードレビュー。
  Phase 1: コアレビュー（常時6+条件2エージェント）で基本的な問題を検出。
  Phase 2: Phase 1の結果とdiff特性に基づき、専門エージェントを動的に追加起動。
  全エージェント model: opus で品質最大化。
  Confidence scoring (0-100) で偽陽性をフィルタリングし、≥80の指摘のみ報告。
  React/Next.jsプロジェクトではvercel-best-practicesの観点も自動追加。
  トリガー: ユーザーが「レビューして」「/review」「コードレビュー」と言った時。
  引数: [PR番号] (省略時は現在のブランチに紐づくPRを自動取得)
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
  - mcp__github__pull_request_read
---

# Review

## 前提

- 現在のブランチにPRが存在すること（PRがなければ終了）

## 実行手順

### 1. PRの取得と前提確認

```bash
# PR番号指定時
gh pr checkout <PR番号>

# PRメタ情報とbase branchを取得
gh pr view --json number,title,url,author,state,headRefName,baseRefName,body
gh pr view --json comments
```

PRが存在しない場合は「PRが見つかりません」と報告して終了。
スキップ条件: closed、変更なしのPR

### 2. 差分とコンテキストの収集

**重要:** diff は `gh pr diff` で GitHub 上の正しい差分を取得する。ローカルの `git diff` はワーキングツリーの状態に依存するため、PR ブランチと異なる場合に偽陽性の原因になる。

```bash
# GitHub上のPR diffを取得（ローカル状態に依存しない）
gh pr diff <PR番号>
gh pr diff <PR番号> --name-only
```

並列で収集:
- PR description と comments（レビュー文脈として活用）
- CLAUDE.md・規約ファイル: `CLAUDE.md`, `.github/CONTRIBUTING.md`, `.eslintrc.*`, `prettier.config.*`

### 2.5. セッションコンテキスト読み込み

1. `.claude/session-context.md` の存在を確認する（Read）
2. ファイルが存在する場合:
   - frontmatter の `branch` と現在のブランチ名を比較する
   - **一致**: コンテキストを有効とし、Phase 1/Phase 2 の各エージェントプロンプトに追加する
   - **不一致**: stale なコンテキストとして無視する（ログ出力のみ）
3. ファイルが存在しない場合: 何もしない（従来通りの動作）

### 3. Phase 1 条件判定

- **React/Next.js判定**: `package.json`に`react`/`next`が含まれる → Agent #3にvercel-best-practices観点を追加
- **テストファイル判定**: diffにテストファイル(`.test.`, `.spec.`, `__tests__/`)が含まれる → Agent #7を起動
- **型定義判定**: diffに`type `または`interface `の追加/変更が含まれる → Agent #8を起動

### 4. Phase 1: コアレビュー（並列エージェント）

| Agent | 起動条件 | 役割 |
|-------|----------|------|
| #1 | 常時 | CLAUDE.md準拠チェック (1/2) |
| #2 | 常時 | CLAUDE.md準拠チェック (2/2) |
| #3 | 常時 | バグ・ロジックエラー検出 |
| #4 | 常時 | git blame/履歴コンテキスト分析 |
| #5 | 常時 | サイレント失敗・エラーハンドリング分析 |
| #6 | 常時 | コメント正確性・陳腐化分析 |
| #7 | テストファイル変更時 | テストカバレッジ・品質分析 |
| #8 | 型定義変更時 | 型設計・不変条件分析 |

エージェント起動前に、以下のファイルを Read ツールで読み込むこと:

- `${CLAUDE_PLUGIN_ROOT}/references/agent-prompts.md` - エージェントのプロンプト詳細
- `${CLAUDE_PLUGIN_ROOT}/references/scoring-guide.md` - スコアリング詳細

**エージェント設定:**

- 全エージェントを `model: opus` で起動する
- 全エージェントを `isolation: "worktree"` で起動する（PR ブランチの状態でファイルを読むため）

**diff-first 原則:**

各エージェントには `gh pr diff` の出力を渡す。エージェントのファイル Read は共通ユーティリティの仕様確認など、diff だけでは判断できない文脈把握に限定する。diff の内容がレビューの真のソースである。

### 5. Phase 2 起動判定

Phase 1 の結果を集約した後、Phase 2 の起動を判定する。

**Phase 2 スキップ条件（全て満たす場合スキップ）:**
1. diff パターンマッチに該当するエージェントがない（Step 5.1）
2. Phase 1 の指摘が全て confidence < 70（深刻な懸念なし）
3. Phase 1 の指摘件数が 3 件以下

#### 5.1. diff パターンマッチ（静的判定）

変更ファイルのパスと diff 内容から、該当する専門エージェントを判定する。
判定マトリクスは `${CLAUDE_PLUGIN_ROOT}/references/agent-prompts.md` の「Phase 2 起動判定」セクションを参照。

#### 5.2. Phase 1 結果からの動的判定

Phase 1 エージェントの指摘内容に以下のパターンが含まれる場合、対応する Phase 2 エージェントを追加起動する:

| Phase 1 の指摘内容 | 追加起動するエージェント |
|---|---|
| セキュリティ脆弱性、インジェクション、認証バイパスへの言及 | セキュリティ分析 (#9) |
| N+1、パフォーマンス劣化、メモリリークへの言及 | パフォーマンス分析 (#10) |
| 破壊的変更、API互換性への言及 | API設計分析 (#11) |
| モジュール境界違反、循環依存への言及 | クロスカッティング影響分析 (#15) |

### 6. Phase 2: 専門レビュー（並列エージェント）

Phase 2 が起動する場合、該当するエージェントを並列で実行する。

| Agent | 起動条件 | 役割 |
|-------|----------|------|
| #9 | セキュリティ関連の変更 or Phase 1 で検出 | セキュリティ分析（OWASP） |
| #10 | パフォーマンスクリティカルな変更 or Phase 1 で検出 | パフォーマンス分析 |
| #11 | API/スキーマの変更 or Phase 1 で検出 | API設計・後方互換性分析 |
| #12 | 依存関係ファイルの変更 | 依存関係・サプライチェーン分析 |
| #13 | DB マイグレーションファイルの変更 | マイグレーション・データ整合性分析 |
| #14 | 設定ファイルの変更 | 設定・環境変数分析 |
| #15 | 共通モジュールの変更 or Phase 1 で検出 | クロスカッティング影響分析 |
| #16 | 変更ファイル数 ≥ 10 | パターン統一・一貫性分析 |

**エージェント設定:**

- 全エージェントを `model: opus` で起動する
- 全エージェントを `isolation: "worktree"` で起動する
- Phase 1 の指摘サマリを各エージェントのプロンプトに含める（引き継ぎ情報として）

プロンプト詳細は `${CLAUDE_PLUGIN_ROOT}/references/agent-prompts.md` の Phase 2 セクションを参照。

### 7. Confidenceスコアリングとフィルタリング

Phase 1 + Phase 2 の全指摘を統合し、各指摘に0-100のconfidenceスコアを付与。≥80のみ報告。

スコアリング詳細は `${CLAUDE_PLUGIN_ROOT}/references/scoring-guide.md` を参照。

### 8. レポート出力

```
## レビュー結果

**総合評価**: X/10点
**レビュー構成**: Phase 1 (N agents) + Phase 2 (M agents)

### 指摘事項 (confidence ≥80)

1. [confidence: 95][バグ] Missing error handling...
   ファイル: src/auth.ts:67-72

2. [confidence: 85][セキュリティ] SQL injection risk...
   ファイル: src/api.ts:23-25

### 総括
- 変更の目的と全体像
- 影響範囲
- 人間が最終確認すべき観点
```
