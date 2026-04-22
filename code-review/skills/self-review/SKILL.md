---
name: self-review
description: >
  Phase 0 トリアージ + 動的エージェント構成のセルフレビュー。
  diff → explorer(sonnet) → reviewer(opus) を動的構成、Confidence ≥80 の指摘のみ報告。
  トリガー: 「セルフレビュー」「/self-review」「自分の変更を確認」「コミット前にチェック」
  引数: [base branch] (省略時は自動検出)
effort: xhigh
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
  - AskUserQuestion
---

# Self Review

## review との違い

- PR 不要。ローカルのみで完結
- コミット前・PR 作成前の品質ゲートとして使用

## 設計原則: Generator と分離された Evaluator

self-review は `dev-workflow:git-commit-helper`（Generator: 変更を生成・コミットする側）から独立した Evaluator として機能する。同一コンテキストで生成と判定を行うと confirmation bias で見落としが増えるため、以下のフローを推奨する:

1. 実装・変更 → `/self-review` （別コンテキストで起動）
2. 指摘事項を修正
3. `/git-commit-helper` でコミット

Phase 0 の explorer/reviewer 並列起動も同じ思想で、reviewer は explorer の結果を「独立した観点として」受け取る（自分で diff を再探索させない）。

## 実行手順

### 1. diff 収集とコンテキスト準備

```bash
# 引数で base branch が指定されていればそれを使用
# 指定がなければデフォルトブランチを自動検出
git remote show origin | grep "HEAD branch" | sed 's/.*: //'
```

base branch が特定できない場合はユーザーに確認する。

```bash
# base branch との全差分（コミット済み + 未コミット）
git diff "${BASE}..HEAD"
git diff
git diff --cached
git diff "${BASE}..HEAD" --name-only
git diff --name-only
git diff --cached --name-only

# 変更ファイルの行数
wc -l <changed_files>
```

変更がなければ終了。

`--staged` 引数が指定されている場合は `git diff --cached` のみを対象とし、未ステージの変更は除外する。

**コンテキスト収集（並列で実行）:**
- CLAUDE.md・規約ファイル: `CLAUDE.md`, `.github/CONTRIBUTING.md`, `.eslintrc.*`, `prettier.config.*`
- `.claude/session-context.md` の存在確認（存在する場合、frontmatter の `branch` と現在のブランチ名を比較。一致すれば有効）
- Issue/knowledge ファイルの探索
- プロジェクト特性シグナル（`package.json` の存在確認と主要依存の確認）

### 2. Phase 0: トリアージ

`${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` を Read で読み込み、そのロジックに従ってエージェント構成を決定する。

**Phase 0 はメインコンテキストで実行する（Agent ツールは使わない）。**

#### 2.1 Stage 1: タイプ判定

diff の特性を分析し、必要なエージェントタイプを判定する:
- **explorer**: 巨大ファイル、複数関数、条件分岐追加、共通モジュール変更のいずれかに該当するか
- **reviewer**: 常に必要。diff パターンマッチでどの観点が必要かを判定
- **spec-compliance**: session-context / Issue / knowledge が存在するか

#### 2.2 Stage 2: 体数・フォーカス・冗長度決定

各タイプの体数と各エージェントの具体的なフォーカスを決定する:
- explorer: 独立した探索対象の数に比例（上限 6 体）
- reviewer: 必要な観点数 × 対象コードの複雑さに応じた冗長度（上限 10 体）
- 冗長ペアには異なる angle（分析の切り口）を割り当てる
- 最小保証: reviewer-bugs + reviewer-claude-md の 2 体は常に起動

#### 2.3 構成テーブル出力

triage-guide.md の出力フォーマットに従い、エージェント構成テーブルを出力する。

### 3. 探索フェーズ（explorer 並列起動）

Phase 0 が explorer を 1 体以上配置した場合のみ実行。explorer が不要と判断された場合はスキップして Step 4 へ。

`${CLAUDE_PLUGIN_ROOT}/references/explorer-prompts.md` を Read で読み込む。

Phase 0 の構成テーブルに従い、各 explorer を `model: sonnet` で並列起動する:
- 各 explorer に Phase 0 が決定した focus と対象ファイル・関数を指示として渡す
- explorer-prompts.md の該当する Focus テンプレートをプロンプトに含める
- `isolation: "worktree"` は使用しない（セルフレビューは未コミット変更を含むため）

全 explorer の完了を待ち、結果を収集する。

**部分失敗耐性:** 個別 explorer が失敗しても全体を中止しない。失敗した explorer の type / focus / エラー要旨を `missing_coverage` リストに記録し、残った explorer の結果で続行する。該当 focus に依存する reviewer には、Step 4 で「探索結果なし（失敗理由）」を明示して渡す。

### 4. レビューフェーズ（reviewer 並列起動）

`${CLAUDE_PLUGIN_ROOT}/references/reviewer-prompts.md` を Read で読み込む。

Phase 0 の構成テーブルに従い、各 reviewer を `model: opus`、`effort: max` で並列起動する:
- 各 reviewer に Phase 0 が決定した focus（と冗長ペアの場合は angle）を指示として渡す
- reviewer-prompts.md の該当する Focus テンプレートと共通指示をプロンプトに含める
- **explorer 結果の選択的注入**: 構成テーブルの「explorer 依存」列に記載された explorer の結果を、該当する reviewer のプロンプトに `## Explorer 結果` セクションとして注入する
- セッションコンテキストが有効な場合、reviewer-prompts.md のセッションコンテキスト注入テンプレートに従い全 reviewer に注入する
- diff 全文を各 reviewer に渡す
- `isolation: "worktree"` は使用しない

**effort 設計意図**: reviewer は `max` で深い推論を優先（overthinking による偽陽性は Confidence ≥80 フィルタで刈り取る）。オーケストレーター（skill frontmatter）は `xhigh` で Opus 4.7 のコーディング向け推奨設定。

**diff-first 原則:** 各エージェントには diff の出力を渡す。エージェントのファイル Read は共通ユーティリティの仕様確認など、diff だけでは判断できない文脈把握に限定する。ただし、変更箇所を含む関数の全体確認は積極的に行うこと。

全 reviewer の完了を待ち、結果を収集する。

**部分失敗耐性:** 個別 reviewer が失敗しても成功した reviewer の結果で合成継続する。失敗した reviewer の focus / angle / エラー要旨を `missing_coverage` リストに追記する。

**最小保証の閾値:** Phase 0 の最小保証（reviewer-bugs と reviewer-claude-md）が **両方とも失敗** した場合のみレビュー中止とし、ユーザーに再実行を促す。それ以外は欠損観点を明示しつつ Step 5 に進む。

### 5. Confidence スコアリングとフィルタリング

全 reviewer の指摘を統合し、`${CLAUDE_PLUGIN_ROOT}/references/scoring-guide.md` を Read で読み込んでスコアリングを実施する。

- 各指摘のベーススコア（reviewer が付与した confidence）に加算・減算ルールを適用
- confidence ≥ 80 のみ報告

### 6. レポート出力

`missing_coverage` リストが空でない場合は「⚠️ 欠損観点」セクションを追加する（空なら省略）。

```
## セルフレビュー結果

**総合評価**: X/10 点
**レビュー構成**: Phase 0 (triage) → 探索 (N 起動 / M 成功) → レビュー (N 起動 / M 成功)

### 指摘事項 (confidence ≥ 80)

1. [confidence: 95][バグ] Missing null check...
   ファイル: src/utils.ts:42

2. [confidence: 82][セキュリティ] Hardcoded secret...
   ファイル: src/config.ts:15

### ⚠️ 欠損観点（Agent 失敗による未カバー領域）
- reviewer-security: ネットワーク I/O エラーで失敗 → 認証まわりの観点は未検査
- explorer-<focus>: timeout → 依存していた reviewer-<focus> には探索結果なしで実行

### 総括
- 変更の概要
- コミット前に修正すべき項目
- 確認推奨の観点
```

### 7. 修正方針の確認

指摘事項が 1 件以上ある場合のみ実行する。指摘が 0 件なら「問題なし」で完了。

レポート全文を出力し終えた直後に **AskUserQuestion** で修正方針を確認する:
- question: "指摘事項への対応方針を選択してください（コミット前の作業優先度を整理します）"
- header: "修正方針"
- options:
  1. label: "すべて修正" / description: "指摘事項をすべて今すぐ修正する"
  2. label: "重要のみ" / description: "confidence >= 90 の指摘だけ修正する"
  3. label: "このまま" / description: "修正はせず、このままコミットする"

各選択肢の後処理:
- **すべて修正**: 全指摘を一覧化し、ファイルごとにまとめて修正を実施する
- **重要のみ**: confidence >= 90 の指摘のみ再表示し、ファイルごとにまとめて修正を実施する
- **このまま**: 完了
