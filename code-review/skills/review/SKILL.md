---
name: review
description: >
  Phase 0 トリアージ + 動的エージェント構成の PR コードレビュー。
  diff → explorer(sonnet) → reviewer(opus) を動的構成、Confidence ≥80 の指摘のみ報告。
  トリガー: 「レビューして」「/review」「コードレビュー」
  引数: [PR番号] (省略時は現在ブランチのPRを自動取得)
effort: xhigh
allowed-tools:
  - Bash
  - Read
  - EnterWorktree
  - ExitWorktree
---

# Review

## 前提

- 現在のブランチに PR が存在すること（PR がなければ終了）
- 実行時 effort = `${CLAUDE_EFFORT}` を Phase 3 / 4 の reviewer 構成に反映する（後述の Phase 3 / 4 を参照）

## 実行手順

### 0. Worktree への移動

**EnterWorktree** ツールで worktree に移動する。作業ブランチを汚さず、レビュー中も並行作業を可能にする。

### 1. PR の取得と前提確認

```bash
# PR 番号指定時: worktree 内で checkout（作業ブランチに影響なし）
gh pr checkout <PR番号>

# PR メタ情報と base branch を取得
gh pr view <PR番号> --json number,title,url,author,state,headRefName,baseRefName,body
```

PR が存在しない場合は「PR が見つかりません」と報告して **ExitWorktree** で抜けて終了。
スキップ条件: closed、変更なしの PR

**【必須】PR 会話コンテキストの取得**:

以下のスクリプトを **必ず実行** し、出力を Step 2.5 でそのまま PR コンテキストブロックとして使用する。LLM が個別 `gh` コマンドを組み立てて取得するのは **禁止**（取りこぼし防止のため）。

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/fetch-pr-context.sh" <PR番号>
```

スクリプトは PR 説明 / issue コメント / レビューサマリ / 行単位 review コメント（返信チェーン込み）を構造化 markdown で出力する。スクリプトが失敗した場合は ExitWorktree して、失敗理由をユーザーに報告し終了（PR コンテキスト無しでは re-flag 判定ができないため、レビュー継続は許可しない）。

### 2. diff とコンテキストの収集

**重要:** diff は `gh pr diff` で GitHub 上の正しい差分を取得する。ローカルの `git diff` は使用しない。

```bash
# GitHub 上の PR diff を取得
gh pr diff <PR番号>
gh pr diff <PR番号> --name-only
```

**コンテキスト収集（並列で実行）:**
- PR 会話データ（Step 1 の fetch-pr-context.sh 出力をそのまま使用）
- CLAUDE.md・規約ファイル: `CLAUDE.md`, `.github/CONTRIBUTING.md`, `.eslintrc.*`, `prettier.config.*`
- `.claude/session-context.md` の存在確認（存在する場合、frontmatter の `branch` と現在のブランチ名を比較。一致すれば有効）
- Issue/knowledge ファイルの探索
- プロジェクト特性シグナル（`package.json` の存在確認と主要依存の確認）
- 変更ファイルの行数: `wc -l <changed_files>`

### 2.5. PR コンテキストブロックの構築

Step 1 の `fetch-pr-context.sh` 出力をそのまま「PR コンテキストブロック」として保持する（LLM による再構築・要約・編集は **禁止**：再現性と取りこぼし防止のため）。このブロックは Phase 0 のタイプ判定と **全 reviewer のプロンプト注入** の両方に使用する。

スクリプト出力の構造（参考）:

```
## PR コンテキスト

### PR 情報
- #<番号> <タイトル>
- 著者: @<author>
- Base → Head: <base> → <head>
- State: <state>
- URL: <url>

### PR 説明（著者が明示したスコープ・意図）
<body 全文。空なら「（空）」>

### Issue コメント（PR 全体への議論）
- [@user, YYYY-MM-DD] body
- ...

### レビューサマリ
- [@reviewer, STATE, YYYY-MM-DD] body
- ...

### 行単位レビューコメント（過去の指摘）
- [#id] [@reviewer, path:line] body
  - 返信 [#親id への返信] [@user] body
- ...
```

データが無い項目は `fetch-pr-context.sh` が「（なし）」を出力する。

### 3. Phase 0: トリアージ

`${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` を Read で読み込み、そのロジックに従ってエージェント構成を決定する。

**Phase 0 はメインコンテキストで実行する（Agent ツールは使わない）。**

#### 3.1 Stage 1: タイプ判定

diff の特性を分析し、必要なエージェントタイプを判定する:
- **explorer**: 巨大ファイル、複数関数、条件分岐追加、共通モジュール変更のいずれかに該当するか
- **reviewer**: 常に必要。diff パターンマッチでどの観点が必要かを判定
- **spec-compliance**: session-context / Issue / knowledge が存在するか

Step 2.5 の PR コンテキストブロック（説明・issue コメント・レビューサマリ・行単位コメント）もタイプ判定の参考にする（例: 説明に「セキュリティ修正」、行単位コメントで認可周りが議論されている → security reviewer を追加）。

#### 3.2 Stage 2: 体数・フォーカス・冗長度決定

各タイプの体数と各エージェントの具体的なフォーカスを決定する:
- explorer: 独立した探索対象の数に比例（上限 6 体）
- reviewer: 必要な観点数 × 対象コードの複雑さに応じた冗長度（上限 10 体）
- 冗長ペアには異なる angle（分析の切り口）を割り当てる
- 最小保証: reviewer-bugs + reviewer-claude-md の 2 体は常に起動

**effort 適応の上限調整**: 現在の effort = `${CLAUDE_EFFORT}` に応じて上記上限を調整する:
- `low` / `medium`: explorer 上限 2 体、reviewer 上限 4 体（最小保証は維持）。深掘りより速度優先
- `high`（既定）: 上記の上限をそのまま採用
- `xhigh` / `max`: explorer 上限 6 体、reviewer 上限 10 体を full に使い、冗長ペアを積極投入

#### 3.3 構成テーブル出力

triage-guide.md の出力フォーマットに従い、エージェント構成テーブルを出力する。

### 4. 探索フェーズ（explorer 並列起動）

Phase 0 が explorer を 1 体以上配置した場合のみ実行。explorer が不要と判断された場合はスキップして Step 5 へ。

`${CLAUDE_PLUGIN_ROOT}/references/explorer-prompts.md` を Read で読み込む。

Phase 0 の構成テーブルに従い、各 explorer を `model: sonnet` で並列起動する:
- 各 explorer に Phase 0 が決定した focus と対象ファイル・関数を指示として渡す
- explorer-prompts.md の該当する Focus テンプレートをプロンプトに含める
- 全エージェントを `isolation: "worktree"` で起動する（PR ブランチの状態でファイルを読むため）

全 explorer の完了を待ち、結果を収集する。

**部分失敗耐性:** 個別 explorer が失敗しても全体を中止しない。失敗した explorer の type / focus / エラー要旨を `missing_coverage` リストに記録し、残った explorer の結果で続行する。該当 focus に依存する reviewer には、Step 5 で「探索結果なし（失敗理由）」を明示して渡す。

### 5. レビューフェーズ（reviewer 並列起動）

`${CLAUDE_PLUGIN_ROOT}/references/reviewer-prompts.md` を Read で読み込む。

Phase 0 の構成テーブルに従い、各 reviewer を `model: opus`、`effort: max` で並列起動する:
- 各 reviewer に Phase 0 が決定した focus（と冗長ペアの場合は angle）を指示として渡す
- reviewer-prompts.md の該当する Focus テンプレートと共通指示をプロンプトに含める
- **explorer 結果の選択的注入**: 構成テーブルの「explorer 依存」列に記載された explorer の結果を、該当する reviewer のプロンプトに `## Explorer 結果` セクションとして注入する
- **PR コンテキスト注入**: Step 2.5 で構築した PR コンテキストブロックを、reviewer-prompts.md の「PR コンテキスト注入テンプレート」(#2.5) に従い全 reviewer のプロンプトに注入する（重複指摘の回避と著者意図の尊重ルールはテンプレート内に明記）
- セッションコンテキストが有効な場合、reviewer-prompts.md のセッションコンテキスト注入テンプレートに従い全 reviewer に注入する
- `gh pr diff` の出力を各 reviewer に渡す
- 全エージェントを `isolation: "worktree"` で起動する

**effort 設計意図**: reviewer は `max` で深い推論を優先（overthinking による偽陽性は Confidence ≥80 フィルタで刈り取る）。オーケストレーター（skill frontmatter）は `xhigh` で Opus 4.7 のコーディング向け推奨設定。

**diff-first 原則:** 各エージェントには `gh pr diff` の出力を渡す。エージェントのファイル Read は共通ユーティリティの仕様確認など、diff だけでは判断できない文脈把握に限定する。ただし、変更箇所を含む関数の全体確認は積極的に行うこと。

全 reviewer の完了を待ち、結果を収集する。

**部分失敗耐性:** 個別 reviewer が失敗しても成功した reviewer の結果で合成継続する。失敗した reviewer の focus / angle / エラー要旨を `missing_coverage` リストに追記する。

**最小保証の閾値:** Phase 0 の最小保証（reviewer-bugs と reviewer-claude-md）が **両方とも失敗** した場合のみレビュー中止とし、ユーザーに再実行を促してから ExitWorktree する。それ以外は欠損観点を明示しつつ Step 6 に進む。

### 6. Confidence スコアリングとフィルタリング

全 reviewer の指摘を統合し、`${CLAUDE_PLUGIN_ROOT}/references/scoring-guide.md` を Read で読み込んでスコアリングを実施する。

- 各指摘のベーススコア（reviewer が付与した confidence）に加算・減算ルールを適用
- PR コンテキストタグ（`[re-flag: ...]` / `[resolved: ...]` / `[intent-conflict]` / `[scope:out]`）が付いた指摘は scoring-guide.md の該当ルールで加減算
- confidence ≥ 80 のみ報告
- 出力時はタグ（`[re-flag: @user]` 等）を指摘文冒頭にそのまま残す（ユーザーが既指摘との関連を把握できるようにする）

### 7. レポート出力

`missing_coverage` リストが空でない場合は「⚠️ 欠損観点」セクションを追加する（空なら省略）。

```
## レビュー結果

**総合評価**: X/10 点
**レビュー構成**: Phase 0 (triage) → 探索 (N 起動 / M 成功) → レビュー (N 起動 / M 成功)

### 指摘事項 (confidence ≥ 80)

1. [confidence: 95][バグ] Missing error handling...
   ファイル: src/auth.ts:67-72

2. [confidence: 90][セキュリティ][re-flag: @reviewer-1] SQL injection risk（2026-04-22 に既指摘、diff で未修正）
   ファイル: src/api.ts:23-25

### ⚠️ 欠損観点（Agent 失敗による未カバー領域）
- reviewer-security: ネットワーク I/O エラーで失敗 → 認証まわりの観点は未検査
- explorer-<focus>: timeout → 依存していた reviewer-<focus> には探索結果なしで実行

### 総括
- 変更の目的と全体像
- 影響範囲
- 人間が最終確認すべき観点
```

レポート出力後、以下の順で締める。

1. **Event Bus publish (`review:completed`)**: 集計結果を `.claude/events.jsonl` に追記する fire-and-forget の publisher。レポートに必要な数値（critical = confidence ≥ 90 件数、warning = 80 ≤ confidence < 90 件数、missing_coverage 配列）は既に手元にあるはず。`SAFE_HOOK_NAME` を `code-review:review` に上書きして event_bus_publish を直接呼ぶ。

   ```bash
   source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh" 2>/dev/null && \
     SAFE_HOOK_NAME="code-review:review" event_bus_publish "review:completed" \
     "{\"pr\":\"<number>\",\"critical_count\":<n>,\"warning_count\":<n>,\"missing_coverage\":[<json-array of focus names>]}"
   ```

   payload 規約:
   - `pr` は PR 番号の文字列（Step 1 で取得済み）。PR 番号取得に失敗した場合は `"local"` とする
   - `critical_count` / `warning_count` は数値
   - `missing_coverage` は文字列配列（reviewer focus 名）。空なら `[]`
   - 失敗してもレポート自体は成功扱い（best-effort）

2. **ExitWorktree** で worktree から抜ける。
