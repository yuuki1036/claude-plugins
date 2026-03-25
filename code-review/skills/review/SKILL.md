---
name: review
description: |
  Phase 0 トリアージ + 動的エージェント構成の PR コードレビュー。
  Phase 0 で diff を分析し、explorer（探索）→ reviewer（レビュー）を動的に構成。
  対象コードの複雑さに応じて同一観点の reviewer を冗長化し、複数視点のマージで確度を向上。
  全エージェント model: opus で品質最大化。
  Confidence scoring (0-100) で偽陽性をフィルタリングし、≥80 の指摘のみ報告。
  React/Next.js プロジェクトでは vercel-best-practices の観点も自動追加。
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

- 現在のブランチに PR が存在すること（PR がなければ終了）

## 実行手順

### 1. PR の取得と前提確認

```bash
# PR 番号指定時
gh pr checkout <PR番号>

# PR メタ情報と base branch を取得
gh pr view --json number,title,url,author,state,headRefName,baseRefName,body
gh pr view --json comments
```

PR が存在しない場合は「PR が見つかりません」と報告して終了。
スキップ条件: closed、変更なしの PR

### 2. diff とコンテキストの収集

**重要:** diff は `gh pr diff` で GitHub 上の正しい差分を取得する。ローカルの `git diff` は使用しない。

```bash
# GitHub 上の PR diff を取得
gh pr diff <PR番号>
gh pr diff <PR番号> --name-only
```

**コンテキスト収集（並列で実行）:**
- PR description と comments（レビュー文脈として活用）
- CLAUDE.md・規約ファイル: `CLAUDE.md`, `.github/CONTRIBUTING.md`, `.eslintrc.*`, `prettier.config.*`
- `.claude/session-context.md` の存在確認（存在する場合、frontmatter の `branch` と現在のブランチ名を比較。一致すれば有効）
- Issue/knowledge ファイルの探索
- プロジェクト特性シグナル（`package.json` の存在確認と主要依存の確認）
- 変更ファイルの行数: `wc -l <changed_files>`

### 3. Phase 0: トリアージ

`${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` を Read で読み込み、そのロジックに従ってエージェント構成を決定する。

**Phase 0 はメインコンテキストで実行する（Agent ツールは使わない）。**

#### 3.1 Stage 1: タイプ判定

diff の特性を分析し、必要なエージェントタイプを判定する:
- **explorer**: 巨大ファイル、複数関数、条件分岐追加、共通モジュール変更のいずれかに該当するか
- **reviewer**: 常に必要。diff パターンマッチでどの観点が必要かを判定
- **spec-compliance**: session-context / Issue / knowledge が存在するか

PR description と comments の内容もタイプ判定の参考にする（例: 「セキュリティ修正」と記載されていれば security reviewer を追加）。

#### 3.2 Stage 2: 体数・フォーカス・冗長度決定

各タイプの体数と各エージェントの具体的なフォーカスを決定する:
- explorer: 独立した探索対象の数に比例（上限 6 体）
- reviewer: 必要な観点数 × 対象コードの複雑さに応じた冗長度（上限 10 体）
- 冗長ペアには異なる angle（分析の切り口）を割り当てる
- 最小保証: reviewer-bugs + reviewer-claude-md の 2 体は常に起動

#### 3.3 構成テーブル出力

triage-guide.md の出力フォーマットに従い、エージェント構成テーブルを出力する。

### 4. 探索フェーズ（explorer 並列起動）

Phase 0 が explorer を 1 体以上配置した場合のみ実行。explorer が不要と判断された場合はスキップして Step 5 へ。

`${CLAUDE_PLUGIN_ROOT}/references/explorer-prompts.md` を Read で読み込む。

Phase 0 の構成テーブルに従い、各 explorer を `model: opus` で並列起動する:
- 各 explorer に Phase 0 が決定した focus と対象ファイル・関数を指示として渡す
- explorer-prompts.md の該当する Focus テンプレートをプロンプトに含める
- 全エージェントを `isolation: "worktree"` で起動する（PR ブランチの状態でファイルを読むため）

全 explorer の完了を待ち、結果を収集する。

### 5. レビューフェーズ（reviewer 並列起動）

`${CLAUDE_PLUGIN_ROOT}/references/reviewer-prompts.md` を Read で読み込む。

Phase 0 の構成テーブルに従い、各 reviewer を `model: opus` で並列起動する:
- 各 reviewer に Phase 0 が決定した focus（と冗長ペアの場合は angle）を指示として渡す
- reviewer-prompts.md の該当する Focus テンプレートと共通指示をプロンプトに含める
- **explorer 結果の選択的注入**: 構成テーブルの「explorer 依存」列に記載された explorer の結果を、該当する reviewer のプロンプトに `## Explorer 結果` セクションとして注入する
- セッションコンテキストが有効な場合、reviewer-prompts.md のセッションコンテキスト注入テンプレートに従い全 reviewer に注入する
- `gh pr diff` の出力を各 reviewer に渡す
- 全エージェントを `isolation: "worktree"` で起動する

**diff-first 原則:** 各エージェントには `gh pr diff` の出力を渡す。エージェントのファイル Read は共通ユーティリティの仕様確認など、diff だけでは判断できない文脈把握に限定する。ただし、変更箇所を含む関数の全体確認は積極的に行うこと。

全 reviewer の完了を待ち、結果を収集する。

### 6. Confidence スコアリングとフィルタリング

全 reviewer の指摘を統合し、`${CLAUDE_PLUGIN_ROOT}/references/scoring-guide.md` を Read で読み込んでスコアリングを実施する。

- 各指摘のベーススコア（reviewer が付与した confidence）に加算・減算ルールを適用
- confidence ≥ 80 のみ報告

### 7. レポート出力

```
## レビュー結果

**総合評価**: X/10 点
**レビュー構成**: Phase 0 (triage) → 探索 (N agents) → レビュー (M agents)

### 指摘事項 (confidence ≥ 80)

1. [confidence: 95][バグ] Missing error handling...
   ファイル: src/auth.ts:67-72

2. [confidence: 85][セキュリティ] SQL injection risk...
   ファイル: src/api.ts:23-25

### 総括
- 変更の目的と全体像
- 影響範囲
- 人間が最終確認すべき観点
```
