---
name: review
description: |
  最大8つの専門エージェントを並列起動してコードレビューする。
  Confidence scoring (0-100) で偽陽性をフィルタリングし、≥80の指摘のみ報告。
  常時6エージェント: CLAUDE.md準拠x2、バグ検出、git blame、サイレント失敗、コメント分析。
  条件付き: テストファイル変更時にテスト分析、型定義変更時に型設計分析を追加。
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
   - **一致**: コンテキストを有効とし、Step 4 の各エージェントプロンプトに追加する
   - **不一致**: stale なコンテキストとして無視する（ログ出力のみ）
3. ファイルが存在しない場合: 何もしない（従来通りの動作）

### 3. 条件判定

- **React/Next.js判定**: `package.json`に`react`/`next`が含まれる → Agent #3にvercel-best-practices観点を追加
- **テストファイル判定**: diffにテストファイル(`.test.`, `.spec.`, `__tests__/`)が含まれる → Agent #7を起動
- **型定義判定**: diffに`type `または`interface `の追加/変更が含まれる → Agent #8を起動

### 4. エージェント並列レビュー

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

**エージェントの isolation 設定:**

全エージェントを `isolation: "worktree"` で起動する。これにより PR ブランチの状態でファイルを読めるため、ワーキングツリーとの不一致による偽陽性を防ぐ。

**diff-first 原則:**

各エージェントには `gh pr diff` の出力を渡す。エージェントのファイル Read は共通ユーティリティの仕様確認など、diff だけでは判断できない文脈把握に限定する。diff の内容がレビューの真のソースである。

### 5. Confidenceスコアリングとフィルタリング

各指摘に0-100のconfidenceスコアを付与。≥80のみ報告。

### 6. レポート出力

```
## レビュー結果

**総合評価**: X/10点

### 指摘事項 (confidence ≥80)

1. [confidence: 95][バグ] Missing error handling...
   ファイル: src/auth.ts:67-72

2. [confidence: 85][サイレント失敗] Empty catch block...
   ファイル: src/api.ts:23-25

### 総括
- 変更の目的と全体像
- 影響範囲
- 人間が最終確認すべき観点
```
