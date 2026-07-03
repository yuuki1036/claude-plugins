---
name: review
description: >
  Phase 0 トリアージ + 動的エージェント構成の PR コードレビュー。
  diff → explorer(sonnet) → reviewer(opus) を動的構成、severity×confidence マトリクスでフィルタ。
  トリガー: 「レビューして」「/review」「コードレビュー」
  引数: [PR番号] [--emergency] (省略時は現在ブランチのPRを自動取得。--emergency は本番ホットフィックス向けの最小構成レビュー)
effort: xhigh
allowed-tools:
  - Bash
  - Read
  - Agent
  - EnterWorktree
  - ExitWorktree
  - AskUserQuestion
---

# Review

## 前提

- 現在のブランチに PR が存在すること（PR がなければ終了）
- 実行時 effort = `${CLAUDE_EFFORT}` を Phase 3 / 4 の reviewer 構成に反映する（後述の Phase 3 / 4 を参照）

## コスト×精度パイプライン設計（採用/不採用）

ルート CLAUDE.md「コスト×精度パイプライン設計指針」の 10 原則のうち **採用: 1（ファネル = Phase 0 triage で高コスト reviewer を通過分に絞る）/ 2（2 軸スコア化 = confidence × severity マトリクス）/ 3（段階予算 = `${CLAUDE_EFFORT}` → explorer/reviewer 体数）/ 4（モデルルーティング = explorer:sonnet / reviewer:opus / meta:fable / 反証:opus）/ 7（敵対的独立検証 = Phase 5.9 反証レイヤー、recall 側は Phase 5.8 冷や読み skeptic）**。**捨てた**: 5（暴走ガード）は反復・起票を持たない単発レビューのため不要、6（証拠ラダー）は指摘蓄積・昇格の責務を failure-journal に委ね、8（外部オラクル）は PR diff レビューが対象で型/テスト実行は feature-dev Phase 5.3 の役割と分離した。

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

**【任意】Issue ファイル必読フロー（linear-workflow / indie-workflow 併用時）**:

PR head / base branch 名から Issue ID を抽出し、ローカルの Issue ファイルがあれば agent prompt に同梱する。仕様・受入条件・設計判断を踏まえた spec-compliance 判定の精度が上がる（GitHub issue #43）。

```bash
# 1. branch 名から [A-Z]+-\d+ パターンで Issue ID を抽出
HEAD_REF=$(gh pr view <PR番号> --json headRefName -q .headRefName)
BASE_REF=$(gh pr view <PR番号> --json baseRefName -q .baseRefName)
ISSUE_IDS=$(echo "$HEAD_REF $BASE_REF" | grep -oE '[A-Z]+-[0-9]+' | sort -u)

# 2. ローカル Issue ファイル探索（linear-workflow / indie-workflow 双方）
for ID in $ISSUE_IDS; do
  find .claude/linear -name "*.md" 2>/dev/null | xargs grep -l "$ID" 2>/dev/null
  find .claude/indie -name "*.md" 2>/dev/null | xargs grep -l "$ID" 2>/dev/null
done | sort -u
```

- ヒットしたファイルを Read で読み込み、内容を spec-compliance reviewer の prompt に `## Issue ファイル` セクションとして同梱する（reviewer-prompts.md の `## 2. セッションコンテキスト注入テンプレート` と同じ要領）
- Issue 本文内に「親 Issue: [FOO-1234](...)」「Parent: FOO-1234」のような親リンクがあれば **1 段だけ追跡** （深い再帰は禁止：トークン爆発防止）
- Issue ID が抽出できない / ファイルが存在しない場合は本フローをスキップ（best-effort）
- `.claude/linear/` と `.claude/indie/` 双方が無いリポジトリでは Glob が空配列を返すだけで no-op（後方互換）

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

#### 3.0 Stage 0: PR 種別分岐（先行判定）

**緊急モード先行判定**: 引数に `--emergency` が含まれる場合、triage-guide.md `## 2.5` の「緊急レビューモード」に従い最小構成（reviewer-bugs + reviewer-security のみ、explorer / 冗長ペア / Phase 5.5 / 5.6 をスキップ）を採用する。この判定は以下の PR 種別分岐より優先する。decided したモードは `emergency` として Step 3.3 / Step 7 に記録し、Step 7 レポート冒頭に必須バナーを出す。

triage-guide.md `## 2.5 PR 種別分岐ルール` を **Stage 1 より先に** 適用する。`gh pr diff <PR番号> --name-only` の結果からモード（`doc-review-mode` / `dba-mode` / `supply-chain-mode` / `skip-mode` / `default-mode`）を判定し、`default-mode` 以外の場合は推奨 agent 構成を Stage 2 の上限・最小保証より優先して採用する（GitHub issue #43）。

決定したモードと根拠は Step 3.3 の構成テーブルおよび Step 7 のレポート冒頭に必ず含める。

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
- **PR 番号注入（必須）**: agent prompt の冒頭に「PR 番号: `<PR_NUMBER>` / 対象 head ref: `<headRefName>`」を必ず明記し、explorer-prompts.md 共通指示の `{{PR_NUMBER}}` と `{{HEAD_REF}}` プレースホルダを実数値に置換する。`isolation: "worktree"` の子 worktree は親 branch を継承しないため、checkout 指示を欠かすと origin/default-branch を見て偽陽性を量産する（GitHub issue #56）。`{{HEAD_REF}}` 注入により、EnterWorktree 済みの親 worktree と二重 checkout になるケースを子 worktree 側でスキップできる（GitHub issue #69）

  ```bash
  # PR_NUMBER は Step 1 で取得済み（gh pr view --json number -q .number で再取得可能）
  PR_NUMBER=$(gh pr view --json number -q .number 2>/dev/null || echo "<番号>")
  ```

全 explorer の完了を待ち、結果を収集する。

**部分失敗耐性:** 個別 explorer が失敗しても全体を中止しない。失敗した explorer の type / focus / エラー要旨を `missing_coverage` リストに記録し、残った explorer の結果で続行する。該当 focus に依存する reviewer には、Step 5 で「探索結果なし（失敗理由）」を明示して渡す。

### 4.9 AGENTS.md 階層動的選択（reviewer 起動前）

変更ファイルパスから対応する `{dir}/AGENTS.md` を Bash で探索し、該当層だけを reviewer プロンプトに同梱する。リポジトリ全体の AGENTS.md / CLAUDE.md を毎回フルロードせず、変更があった層のみ拾うことで reviewer 入力 token を典型 30〜50% 削減する。

```bash
# 変更ファイルから親ディレクトリを抽出
git diff <base>...HEAD --name-only | xargs -n1 dirname 2>/dev/null | sort -u | while read dir; do
  # 当該ディレクトリから root まで遡って AGENTS.md / CLAUDE.md を探索
  while [ "$dir" != "." ] && [ "$dir" != "/" ]; do
    [ -f "$dir/AGENTS.md" ] && echo "$dir/AGENTS.md"
    [ -f "$dir/CLAUDE.md" ] && echo "$dir/CLAUDE.md"
    dir=$(dirname "$dir")
  done
done | sort -u
```

ヒットしたファイルのみ Read で読み込み、各 reviewer のプロンプトに `## 該当層の AGENTS.md / CLAUDE.md` セクションとして注入する。AGENTS.md が無いリポジトリでは探索結果が空になるだけで no-op（後方互換）。

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
- **PR 番号注入（必須）**: agent prompt の冒頭に「PR 番号: `<PR_NUMBER>` / 対象 head ref: `<headRefName>`」を必ず明記し、reviewer-prompts.md 共通指示の `{{PR_NUMBER}}` と `{{HEAD_REF}}` プレースホルダを実数値に置換する。`isolation: "worktree"` の子 worktree は親 branch を継承せず origin/default-branch から派生するため、checkout 指示を欠かすと PR の変更を観測できず偽陽性を量産する（GitHub issue #56）。`{{HEAD_REF}}` 注入により、EnterWorktree 済みの親 worktree と二重 checkout になるケースを子 worktree 側でスキップできる（GitHub issue #69）

**effort 設計意図**: reviewer は `max` で深い推論を優先（overthinking による偽陽性は Confidence ≥80 フィルタで刈り取る）。オーケストレーター（skill frontmatter）は `xhigh`。Opus 4.8 は `high` が既定 effort のため、demanding task 向けに一段引き上げた設定。

**diff-first 原則:** 各エージェントには `gh pr diff` の出力を渡す。エージェントのファイル Read は共通ユーティリティの仕様確認など、diff だけでは判断できない文脈把握に限定する。ただし、変更箇所を含む関数の全体確認は積極的に行うこと。

全 reviewer の完了を待ち、結果を収集する。

**出力形式の検証と auto-retry（GitHub issue #69）:** 各 reviewer の出力が「レビュー結果」として妥当か機械的に検証する。以下のいずれも欠く出力は **非レビュー出力**（空応答・system-reminder / skill 案内の断片・tool_use ゼロでの早期終了等）とみなす:

- `### レビュー結果` 見出し（または `#### 指摘事項` / `#### 総括` のいずれか）
- 指摘が 1 件以上ある場合、`[confidence: XX]` と `[severity: ...]` タグを含む行が存在する

非レビュー出力を検出した reviewer は、**同一プロンプトで 1 回だけ auto-retry** する（複数同時検出時はまとめて並列 retry）。retry 出力も非レビュー出力なら、その reviewer の focus / angle を `missing_coverage` に「非レビュー出力（auto-retry 後も形式不正）」として記録して続行する（欠損観点として扱い、フィルタを素通りさせない）。「指摘ゼロ」を明示的に報告した妥当な出力（`### レビュー結果` を持ち問題なしと結論）は非レビュー出力ではないため retry 対象にしない。

**部分失敗耐性:** 個別 reviewer が失敗しても成功した reviewer の結果で合成継続する。失敗した reviewer の focus / angle / エラー要旨を `missing_coverage` リストに追記する。

**最小保証の閾値:** Phase 0 の最小保証（reviewer-bugs と reviewer-claude-md）が **両方とも失敗** した場合のみレビュー中止とし、ユーザーに再実行を促してから ExitWorktree する。それ以外は欠損観点を明示しつつ Step 6 に進む。

### 5.5 Adaptive deepening: 追加 explorer ラウンド（v2.12.0 / 動的）

**スキップ条件**（いずれか満たせばこのフェーズ全体をスキップして Step 5.6 へ）:
- userConfig `enable_adaptive_rounds` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `low` または `medium`
- 全 reviewer の出力に `## unmet_information` セクションが 1 件もない

**実行する場合**:

1. 全 reviewer 出力をパースし、`## unmet_information` セクションを集約する
2. 集約結果から **最大 3 件** の追加探索ターゲットを選ぶ（多すぎる場合は BLOCKER 候補に関わる unmet を優先）
3. `${CLAUDE_PLUGIN_ROOT}/references/explorer-prompts.md` の `re-explore` テンプレートで追加 explorer を `model: sonnet` で並列起動する
   - 各 explorer に対応する unmet_information（focus, target, why, related_finding）を指示として渡す
   - `isolation: "worktree"` で起動（PR ブランチ）
   - **PR 番号注入（必須）**: Step 4 と同様に prompt 冒頭に PR_NUMBER / head ref を明記し `{{PR_NUMBER}}` を置換（issue #56）
4. 追加 explorer 完了後、unmet を申告した reviewer のみ（最大 3 体）を `model: opus`, `effort: max` で再起動する
   - 再起動 reviewer には初回指摘 + 追加 explorer 結果を context として渡し、「初回 confidence を再評価せよ」と指示
   - 再起動 reviewer の出力は **初回出力を置換**（dedup のため）
   - **PR 番号注入（必須）**: Step 5 と同様に prompt 冒頭に PR_NUMBER / head ref を明記し `{{PR_NUMBER}}` を置換（issue #56）
5. レポートに「Round 2 trigger: <reason>」を記録（Step 7 で出力）

**失敗時**: 追加 explorer / 再起動 reviewer が失敗した場合は初回結果のままで続行（missing_coverage には追記しない、Round 2 は best-effort）

### 5.6 Meta-reviewer ラウンド（v2.12.0 / 動的）

**スキップ条件**（いずれか満たせばスキップして Step 6 へ）:
- userConfig `enable_meta_reviewer` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `xhigh` または `max` **でない**
- Step 5.5 後の全指摘（フィルタリング前）に **BLOCKER も CRITICAL も 1 件もない**

**実行する場合**:

1. `${CLAUDE_PLUGIN_ROOT}/references/reviewer-prompts.md` の `## 6. Meta-reviewer テンプレート` を使用
2. meta-reviewer agent を 1 体、`model: fable`, `effort: max` で起動
   - 入力: diff、全 reviewer の指摘リスト（フィルタ前）、起動された focus 一覧、explorer 結果
   - `isolation: "worktree"` で起動
   - **PR 番号注入（必須）**: Step 5 と同様に prompt 冒頭に PR_NUMBER / head ref を明記し `{{PR_NUMBER}}` を置換（issue #56）
3. meta-reviewer の出力（追加指摘）を既存指摘に統合
   - 重複は dedup（同一ファイル ±5 行 + 類似内容）
   - meta-reviewer の指摘も通常のスコアリング・フィルタリング対象

**失敗時**: meta-reviewer が失敗した場合は missing_coverage に `meta-reviewer: <failure reason>` を追記して続行

### 5.7 観点カバレッジ・セルフチェック（メインコンテキスト / 常時実行）

Step 6 の直前に、**メインコンテキストで**（Agent は使わない・低コスト）起動 focus の妥当性を 1 回検査する。観点漏れは高 severity 指摘が無くても起こりうるため、meta-reviewer (5.6) の起動有無・effort・severity に依存せず **常時実行** する（meta-reviewer は起動条件が「effort=xhigh/max かつ BLOCKER/CRITICAL あり」と厳しく、観点漏れを取りこぼすため。GitHub issue #69）。

1. `triage-guide.md` の「reviewer の観点判定」表の各条件を、実際の diff シグナル（変更ファイルパス・diff 内文字列）に対して **メインコンテキストで再評価** する
2. **「条件を満たすのに起動されなかった focus」** を検出する（例: `migrations/` 変更があるのに migration 不在、`.tsx` 変更があるのに ui-quality 不在、`package.json` 変更があるのに dependency 不在）
3. 検出した観点漏れは `missing_coverage` に「観点未起動: <focus>（diff シグナル: <根拠>）」として追記する
4. effort が `high` 以上 かつ 追加 1 体で補える観点なら、その focus の reviewer を 1 体だけ追加起動して結果を Step 6 に合流させてよい（任意・best-effort。失敗しても missing_coverage 記載のまま続行）

**スキップ条件**: `--emergency`（緊急モード）または `skip-mode`（生成物 PR）では構成が意図的に最小化されているため本チェックをスキップする。

### 5.8 冷や読み skeptic ラウンド（recall 補強 / 動的）

観点カバレッジ self-check の後・反証レイヤーの前に、**high-risk surface を含む変更に限り**、他 reviewer の findings も推論も渡さない独立 skeptic を 1 体起動し、fleet 共通の盲点（層跨ぎ値フロー等）を冷や読みで探す（`${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` `## 8.5 冷や読み skeptic ラウンド`）。反証レイヤー(5.9)が偽陽性を潰す係なのに対し、本フェーズは見落とし（false negative）を独立読み直しで足す係。meta-reviewer(5.6)が findings 注入で非独立なため fleet 共通盲点を引きずるのを、独立性で補う。

**スキップ条件**（いずれか満たせばスキップして 5.9 へ）:
- userConfig `enable_recall_skeptic` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `xhigh` または `max` **でない**（high 既定は当面スキップ。`review:completed` の頻度計測後に high 昇格を検討＝既存 5.6/5.9 と対称の fail-safe）
- `--emergency`（緊急モード）または `skip-mode`（生成物 PR）
- high-risk surface（triage-guide.md `## 8.5` の surface 判定）を含まない

**実行する場合**:

1. **surface 判定**: 変更 diff に対し triage-guide.md `## 8.5` の判定を行う。DB 書込（`INSERT`/`UPDATE`/`DELETE` の生 SQL または ORM 書込 API `.create(`/`.update(`/`.save(`/`.upsert(` 等）/ 金銭・数量 numeric 演算 / 認可・認証、いずれかの正規表現ヒット、**または** reviewer が `[surface:high-risk]` フラグを返した（PR 自己申告 D1-High 含む）場合に high-risk surface と判定
2. `${CLAUDE_PLUGIN_ROOT}/references/reviewer-prompts.md` の `## 8 冷や読み skeptic テンプレート` を使用し、skeptic agent を **1 体**、`model: opus`, `effort: max`, `isolation: "worktree"` で起動
   - **findings / reviewer の推論は渡さない**（独立性の核）。diff と最小 focus、base ref のみ渡す
   - **PR 番号注入（必須）**: Step 5 と同様に prompt 冒頭に PR_NUMBER / head ref を明記し `{{PR_NUMBER}}` を置換（issue #56）
3. skeptic の指摘（`[recall-skeptic]` タグ付き）を既存指摘に統合。重複は dedup（同一ファイル ±5 行 + 類似内容）。skeptic の指摘も通常のスコアリング・報告マトリクス・**反証レイヤー(5.9)の対象**に含める

**失敗時**: skeptic が失敗 / タイムアウトした場合は `missing_coverage` に `recall-skeptic: <failure reason>` を追記して続行する。**起動条件（high-risk surface）を満たしたのに未実行だった事実は Step 7 レポートに必ず出す**（silent 失敗で偽の安心を防ぐ）。

### 5.9 反証レイヤー（adversarial verification / 動的）

冷や読み skeptic の後・スコアリングの前に、reviewer の指摘を独立エージェントが反証する。偽陽性を人間が詰める前に先回りして摘出するフェーズ（`${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` `## 9 反証レイヤー`）。meta-reviewer (5.6) / skeptic (5.8) が見落とし（false negative）を足す係なのに対し、本フェーズは偽陽性（false positive）を独立に潰す鏡像。skeptic が足した指摘も本レイヤーの対象。

**スキップ条件**（いずれか満たせばスキップして Step 6 へ）:
- userConfig `enable_adversarial_verify` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `low` または `medium`
- `--emergency`（緊急モード）または `skip-mode`（生成物 PR）
- 反証対象（triage-guide.md `## 9` のゲート）に合致する指摘が 0 件

**実行する場合**:

1. triage-guide.md `## 9 反証レイヤー` の選定ルールで対象指摘を選ぶ（high: 非対称ゾーン BLOCKER 60-94 / CRITICAL 80-94、xhigh/max: 報告ゾーン全体 + MAJOR）。**specialist 由来の指摘は全 effort で除外**
2. 対象指摘ごとに `${CLAUDE_PLUGIN_ROOT}/references/reviewer-prompts.md` `## 7 Adversarial-verify テンプレート` で反証エージェントを `model: opus`, `effort: max`, `isolation: "worktree"` で並列起動する
   - 指摘の主張（severity / confidence / file:line / 内容）のみ渡し、**reviewer の理由文は渡さない**（アンカリング防止）
   - **PR 番号注入（必須）**: Step 5 と同様に prompt 冒頭に PR_NUMBER / head ref を明記し `{{PR_NUMBER}}` を置換（issue #56）
   - `pre-existing` / `intended` 鮮度の git 判定（`git show <base>:<file>` / `git blame`）を反証エージェントに許可する
3. 各 verdict（refuted / confirmed / uncertain / severity-inflated）を収集し、Step 6 のスコアリングに渡す
4. レポートに「反証: 対象 N 件 / 係争 M 件 / 取り下げ K 件」を記録（Step 7 で出力）

**失敗時**: 反証エージェントが失敗した指摘は verdict なし（= 反証スキップ）として元の confidence / severity のまま続行する（best-effort、missing_coverage には記録しない）

### 6. スコアリングとフィルタリング（2軸: confidence × severity）

全 reviewer の指摘を統合し、`${CLAUDE_PLUGIN_ROOT}/references/scoring-guide.md` を Read で読み込んでスコアリングを実施する。

1. **各指摘の base confidence と severity を取得**
   - reviewer 出力の `[confidence: XX]` と `[severity: BLOCKER|CRITICAL|MAJOR|MINOR]` をパース
   - severity が欠落している指摘は **CRITICAL とみなす**（後方互換 / 安全側デフォルト）
2. **反証 verdict の反映**（Phase 5.9 が動いた場合のみ。scoring-guide.md `## 反証レイヤーの verdict 反映` に従う）
   - **BLOCKER / CRITICAL の `refuted` は confidence / severity を据え置き**、指摘本文先頭に `⚠️ 反証メモ: <軸>（<根拠 file:line>、要確認）` を付与（**報告から消さない**）
   - **MAJOR / MINOR の `refuted`** は confidence −40（取り下げ理由を付録に記録）
   - `confirmed` は既存「複数エージェント +15」の発火源（二重計上しない）、`uncertain` は −10
   - verdict が無い指摘（対象外・反証失敗）は no-op
3. **confidence への加算・減算ルールを適用**
   - PR コンテキストタグ（`[re-flag: ...]` / `[resolved: ...]` / `[intent-conflict]` / `[scope:out]`）の加減算
   - 複数エージェント検出 / explorer 裏付け / セッションコンテキスト等の加減算
   - 最終 confidence を 0-100 にクランプ
4. **severity 調整**: `[scope:out]` / `[resolved: ...]` タグ付きは severity を 1 段階下げる（反証 `severity-inflated` もこのルールに統合。二重降格しない）
5. **報告マトリクスでフィルタ**:

   | severity \ confidence | <60 | 60-79 | 80-94 | 95+ |
   |---|:---:|:---:|:---:|:---:|
   | BLOCKER | skip | 報告 | 報告 | 報告 |
   | CRITICAL | skip | skip | 報告 | 報告 |
   | MAJOR | skip | skip | skip | 報告 |
   | MINOR | skip | skip | skip | 報告 |

6. **userConfig 適用**: `review_severity_threshold` (default: `MAJOR`) より低い severity は除外
7. **出力**: タグ（`[re-flag: @user]` 等）と severity ラベルを指摘文冒頭にそのまま残す。`⚠️ 反証メモ:` が付いた係争指摘は本文にメモを残したまま出力する

### 7. レポート出力

`missing_coverage` リストが空でない場合は「⚠️ 欠損観点」セクションを追加する（空なら省略）。

```
## レビュー結果

{emergency モード時のみ先頭に: **⚠️ 緊急レビュー（最小構成）: マージ後に通常の /review を必ず実施すること**}

**[mode: {emergency|doc-review|dba|supply-chain|skip|default}, agents: [<focus 名のリスト>]]**

**総合判定**: {Approve | Approve with nits | Needs work}（scoring-guide.md「レビュー結論（総合判定）」の表に従って決定）
**総合評価**: X/10 点
**レビュー構成**: Phase 0 (triage) → 探索 (N 起動 / M 成功) → レビュー (N 起動 / M 成功)
**動的ラウンド**: Round 2 探索 N 体起動 / Meta-reviewer {実行 | スキップ理由} / 反証 {対象 N 件 | スキップ理由}
**指摘件数**: BLOCKER N 件 / CRITICAL N 件 / MAJOR N 件 / MINOR N 件
**反証**: 対象 N 件 / 係争 M 件（BLOCKER/CRITICAL、本文に反証メモ）/ 取り下げ K 件（MAJOR以下、付録に理由）{反証スキップ時はこの行を省略}

### 🚨 BLOCKER 指摘

1. [confidence: 65][severity: BLOCKER][セキュリティ] 潜在的な SQL injection の疑い
   ファイル: src/api.ts:23-25
   影響: 攻撃成立時に DB 全体の漏洩・破壊
   修正案: parameterized query への変更

### ⚠️ CRITICAL 指摘

2. [confidence: 95][severity: CRITICAL][バグ] Missing error handling
   ファイル: src/auth.ts:67-72
   影響: 認証失敗時に null 参照で落ちる

3. [confidence: 90][severity: CRITICAL][re-flag: @reviewer-1] xxx（2026-04-22 に既指摘、diff で未修正）
   ファイル: src/api.ts:30-35

### 📋 MAJOR 指摘

4. [confidence: 95][severity: MAJOR][設計] ...

### ⚠️ 欠損観点（Agent 失敗による未カバー領域）
- reviewer-security: ネットワーク I/O エラーで失敗 → 認証まわりの観点は未検査
- explorer-<focus>: timeout → 依存していた reviewer-<focus> には探索結果なしで実行

### 🔁 反証で取り下げた指摘（参考・人間が覆せる）
{反証レイヤーが MAJOR/MINOR を refuted で取り下げた場合のみ。0 件なら省略}
- [取り下げ前: confidence XX / severity MAJOR] xxx の指摘
  ファイル: path/to/file:行番号
  取り下げ理由: <軸>（反証根拠 file:line）
  ※ 反証が誤りと思えばこの指摘は有効。再評価してよい

### 良かった点
- [src/auth.ts:67-72] 認証失敗の異常系を網羅的に分岐していて堅牢
- [src/parser.ts] 境界値テストが追加されており回帰検知が効く

### 総括
- 変更の目的と全体像
- 影響範囲
- 人間が最終確認すべき観点（特に BLOCKER の低 confidence 指摘）
```

**重要**: BLOCKER は confidence が低くても報告される設計。「疑わしい」段階で人間判断を促す目的なので、必ず「影響」フィールドで重大度の根拠を示すこと。

**良かった点の扱い**: 著者が意図的に良くした箇所を **0〜2 件** 具体的に挙げる（該当ファイル:行を添える）。設計判断・テストの充実・エッジケース対応・可読性の工夫など、レビューを通して見えた優れた点を拾う。指摘ばかりに偏らずメンタリング効果を持たせる狙いだが、「全体的に良い」のような中身のない称賛はノイズになるので書かない。特筆すべき点がなければセクションごと省略する。

レポート出力後、以下の順で締める。

1. **指摘の精査（必要性ゲート / 任意）**: 報告マトリクス通過後の指摘が **1 件以上** ある場合のみ実行（指摘 0 件、または `--emergency` 時はスキップして 2 へ）。

   Step 6（severity×confidence の機械フィルタ）と Phase 5.9 反証レイヤー（正しさ＝偽陽性の独立検証）が「閾値を超えるか」「事実として正しいか」を判定するのに対し、本ステップは **第 3 軸＝必要性（signal/noise）** を人間に委ねる。「正しい指摘ではあるが、本当に著者の対応に値するか」を問う（Google eng-practices "The Standard": コード健全性を向上させるなら nit でブロックしない／technical fact は preference に優先）。settled な設計判断の蒸し返しや既存コード由来の nit は**反証では refuted にならない**（事実は正しい）が、必要性軸では取り下げ対象になる。

   レポート全文を出力した直後に **AskUserQuestion**（返答ドラフトより先）で精査の要否を確認する:

   - question: "報告された指摘を精査しますか？（各指摘が本当に著者の対応に値するか＝必要性を観点に取り下げ・降格を再評価します。返答ドラフトはこの後に確認します）"
   - header: "指摘の精査"
   - multiSelect: false
   - options:
     1. label: "精査する（推奨）" / description: "純粋な好み・settled な蒸し返し・実害極小の nit・既存コード由来を再評価し取り下げ／降格を提案"
     2. label: "そのまま" / description: "再評価せず現状の指摘を確定する"

   「そのまま」なら 2 へ。「精査する」なら **メインコンテキストで**（Agent 不使用）各指摘を 3 分類する。判定には必ず根拠（カテゴリ + file:line / PR コンテキスト典拠）を添える:

   - **取り下げ（withdraw）** — 正しくても対応に値しない: 純粋な好み（CLAUDE.md / style guide / 計測 / 具体的不具合の根拠なし、≤40 クランプを擦り抜けた残滓）/ settled な設計判断の蒸し返し（session-context / Issue / PR 説明で確定済み）/ 実害極小の MINOR nitpick / 既存コード由来（この diff 非導入）
   - **降格（downgrade）** — 内容は妥当だが severity 過大: 1 段階下げ + `Optional:` / `Nit:` 化
   - **残存（keep）** — 実害・リスク・規約違反の根拠を伴い著者が知るべき。**BLOCKER / CRITICAL は降格はあっても取り下げない**（既存コード由来であっても残存させ `既存コード由来` の文脈を付記する。取り下げの「既存コード由来」は MAJOR 以下に限る。反証レイヤーの「高 severity 非削除」不変条件と整合）

   取り下げ・降格は **理由を明示し人間が覆せる形**で提示する（破棄しない）。精査後、`## 精査結果`（取り下げ N / 降格 M / 残存 K ＋ 取り下げた指摘の一覧と理由）を出力し、**残存 + 降格を反映した調整後レポートを再出力**する（総合判定・severity 別件数を残存指摘で再導出）。以降の返答ドラフト・publish は精査後（post）の確定値を使う。

2. **投稿コメントのドラフト生成（任意）**: 精査後に残存／降格した指摘が **1 件以上** ある、**または** 総合判定が **Approve / Approve with nits** の場合に実行（どちらにも該当しなければスキップして 3 へ）。生成する全文面は `reply-tone-guide.md` `## 0 必須ルール`（Claude 署名 / 作成者・他レビュアーへの敬意 / 簡潔さ / 良い点を 1 文）を**厳守**する。

   レポート出力直後に **AskUserQuestion** で要否を確認する（options は状態に応じて提示する）:

   - question: "投稿用コメントのドラフトを生成しますか？（投稿は行わず、コピペ可能な文面のみ出力します）"
   - header: "コメントドラフト"
   - multiSelect: false
   - options:
     1. label: "不要" / description: "ドラフトは生成しない（既定）"
     2. label: "承認コメント" / description: "簡潔な承認 + 良い点 1 文 + 署名"（**総合判定が Approve / Approve with nits のときのみ提示**）
     3. label: "重要指摘のみ" / description: "severity BLOCKER / CRITICAL の返答ドラフト"（残存指摘があるときのみ）
     4. label: "全件" / description: "全残存指摘 ＋ 該当すれば承認コメント"（残存指摘があるときのみ）
     5. label: "個別選択" / description: "対象の指摘番号を入力する"（残存指摘があるときのみ）

   「不要」なら 3 へ。それ以外は以下を実行:

   - `${CLAUDE_PLUGIN_ROOT}/references/reply-tone-guide.md` を Read で読み込む
   - **承認コメント**（総合判定 Approve / Approve with nits、かつ「承認コメント」または「全件」選択時）: reply-tone-guide.md `### 2.7 承認メッセージ` のテンプレで生成。良い点は「良かった点」セクションから **1 文に圧縮**（file:line 添え）。Needs work では生成しない。**承認メッセージ本文で触れた nit は指摘返答ドラフトと重複させない**（全体コメントは要点のみ・詳細は inline スレッド側へ。reply-tone-guide 2.7「nits は詳述しない」と整合）
   - **指摘への返答**（残存指摘が対象。「個別選択」なら AskUserQuestion で「対象の指摘番号（例: 1,3,5）」を free-text 入力）: 対象指摘ごとにパターンを選ぶ
     - 著者対応 commit が PR にある → 解決度（完全/部分/未対応）に応じて 2.1〜2.5
     - 著者対応 commit がない → 2.4 / 2.5
     - `[re-flag: @user]` タグ付き → 2.5「再指摘の追補」
     - レビュアー視点（自分発信の指摘）→ 2.6
     - 1〜3 文で生成（長文化させない）
   - **各文面の末尾に署名 `— Claude Code によるレビュー` を付す**（reply-tone-guide.md 0.1）
   - **未検証主張の断定抑止（over-correction 防止 / GitHub issue #71）**: ドラフトに load-bearing な事実主張を書く場合、typo 級でない限り **断定で書かない**。repo で確認できる主張は `file:line` を、正本 doc で確認できる主張は典拠を添える。repo/正本で裏が取れない外部状態（DB/本番/運用設定）は「要確認（典拠=X）」とし、元の reviewer 指摘が `[unverified: ...]` 付きならその不確実性を返答にも引き継ぐ（確定済みであるかのように書かない）
   - **投稿は行わない**。ドラフト出力のみ。ユーザーが GitHub UI で手動投稿する

   出力フォーマット:
   ```
   ## 投稿コメントドラフト（投稿は手動で行ってください）

   ### 承認コメント（PR 全体コメント）
   > レビューしました。大筋問題なく、Approve とさせてください。
   > src/parser.ts:40-58 の境界値テストが手厚く、回帰検知が効きそうです。
   > 細かい点として変数名の統一がありますが、対応は任意で問題ありません（src/api.ts:12）。
   > — Claude Code によるレビュー

   ### 指摘 #1 への返答
   対象: src/auth.ts:67-72 / @reviewer-a さん
   パターン: 完全対応（2.1）

   > ご指摘ありがとうございます。
   > src/auth.ts:67 で null チェックを追加しました（{commit-sha}）。
   > 意図と合っているかご確認いただけると助かります。
   > — Claude Code によるレビュー
   ```

   生成中に reply-tone-guide.md に明示のないトーン判断が必要になった場合は、ドラフト末尾に `（補足: {判断点} はガイドに明示なし。ユーザー確認推奨）` を添える。

3. **Event Bus publish (`review:completed`)**: 集計結果を `.claude/events.jsonl` に追記する fire-and-forget の publisher。**指摘の精査を行った場合は精査後（post）の確定件数を使う**（取り下げ・降格を反映）。レポートに必要な数値（critical = confidence ≥ 90 件数、warning = 80 ≤ confidence < 90 件数、missing_coverage 配列）は既に手元にあるはず。`SAFE_HOOK_NAME` を `code-review:review` に上書きして event_bus_publish を直接呼ぶ。

   ```bash
   source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh" 2>/dev/null && \
     SAFE_HOOK_NAME="code-review:review" event_bus_publish "review:completed" \
     "{\"pr\":\"<number>\",\"blocker_count\":<n>,\"critical_count\":<n>,\"major_count\":<n>,\"minor_count\":<n>,\"missing_coverage\":[<json-array of focus names>],\"result_grid\":{\"high\":<n>,\"medium\":<n>,\"low\":<n>,\"skip\":<n>,\"error\":<n>},\"adversarial_verify\":{\"confirmed\":<n>,\"refuted\":<n>,\"uncertain\":<n>,\"contested\":<n>}}"
   ```

   payload 規約:
   - `pr` は PR 番号の文字列（Step 1 で取得済み）。PR 番号取得に失敗した場合は `"local"` とする
   - `blocker_count` / `critical_count` / `major_count` / `minor_count` は数値（severity 別件数）
   - `missing_coverage` は文字列配列（reviewer focus 名）。空なら `[]`
   - `result_grid` は 5 値の集計オブジェクト（後段 hook / PR コメント自動投稿の dispatch 用）:
     - `high`: BLOCKER または CRITICAL 件数（即対応必要）
     - `medium`: MAJOR 件数（PR ブロックはしないが対応推奨）
     - `low`: MINOR 件数（nitpick / 提案）
     - `skip`: severity スコープ外でフィルタされた件数
     - `error`: reviewer / explorer が失敗した件数（`missing_coverage` の length と一致）
   - `adversarial_verify` は反証レイヤー（Phase 5.9）の verdict 集計（`confirmed` / `refuted` / `uncertain` / `contested`=高 severity の係争件数）。反証スキップ時は全 0。**review / self-review 両 publisher で同一フィールド名を揃える**（後から偽却下率を計測するため）
   - 失敗してもレポート自体は成功扱い（best-effort）
   - 後方互換: subscriber 側は `critical_count` の存在を仮定して良い（旧 payload との互換性のため必須）。`result_grid` / `adversarial_verify` は新規フィールド追加なので旧 subscriber 影響なし

4. **ExitWorktree** で worktree から抜ける。
