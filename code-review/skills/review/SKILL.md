---
name: review
description: >
  Phase 0 トリアージ + 動的エージェント構成の PR コードレビュー。
  diff → explorer(sonnet) → reviewer(opus) を動的構成、severity×confidence マトリクスでフィルタ。
  トリガー: 「レビューして」「/review」「コードレビュー」
  引数: [PR番号] [--emergency] (省略時は現在ブランチのPRを自動取得。--emergency は本番ホットフィックス向けの最小構成レビュー)
effort: high
allowed-tools:
  - Bash
  - Read
  - Agent
  - EnterWorktree
  - ExitWorktree
  - AskUserQuestion
  - Skill
---

# Review

## 前提

- 現在のブランチに PR が存在すること（PR がなければ終了）
- 実行時 effort = `${CLAUDE_EFFORT}` を Phase 3 / 4 の reviewer 構成に反映する（後述の Phase 3 / 4 を参照）

## コスト×精度パイプライン設計（採用/不採用）

ルート CLAUDE.md「コスト×精度パイプライン設計指針」の 10 原則のうち **採用: 1（ファネル = Phase 0 triage で高コスト reviewer を通過分に絞る）/ 2（2 軸スコア化 = confidence × severity マトリクス）/ 3（段階予算 = `${CLAUDE_EFFORT}` → explorer/reviewer 体数）/ 4（モデルルーティング = explorer:sonnet / reviewer:opus / meta:opus / 反証:opus）/ 7（敵対的独立検証 = Phase 5.9 反証レイヤー、recall 側は Phase 5.8 冷や読み skeptic）**。**捨てた**: 5（暴走ガード）は反復・起票を持たない単発レビューのため不要、6（証拠ラダー）は指摘蓄積・昇格の責務を failure-journal に委ね、8（外部オラクル）は PR diff レビューが対象で型/テスト実行は feature-dev Phase 5.3 の役割と分離した。

## 実行手順

実行フェーズの共通詳細（PR 番号注入・部分失敗耐性・auto-retry・動的ラウンドの実行手順）の正本:
→ Read `${CLAUDE_PLUGIN_ROOT}/references/orchestration-guide.md`（以下「orchestration-guide」）

### 0. Worktree への移動

**EnterWorktree** ツールで worktree に移動する。作業ブランチを汚さず、レビュー中も並行作業を可能にする。

### 1. PR の取得と前提確認

```bash
# 所要時間計測の開始マーカー t0 を記録（締めフロー 4 の payload で使用）
# シェル変数は Bash 呼び出し間で持続しないため、必ずファイルで受け渡す（変数だと
# publish 時に未定義 =0 と評価され epoch/60 のゴミ値が publish される）。
# パスは cwd ではなく「メインリポジトリのルート」から導出する（Step 0 で worktree に
# 入っているため cwd 基準だと publish 時と食い違う。導出式の正本: orchestration-guide `## 13`）
GCD=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
MAIN_ROOT=$([ -n "$GCD" ] && (cd "$GCD/.." && pwd) || pwd)
TS_FILE="${TMPDIR:-/tmp}/.review-start-$(printf %s "$MAIN_ROOT" | cksum | cut -d' ' -f1)"
echo "t0 $(date +%s)" > "$TS_FILE"
# 以降 t1（最初の agent 一括発行の直前。explorer があれば Step 4 / 無ければ Step 5）/
# t2（Step 7 の初回レポート出力の直後）を
# 同じファイルに追記する。3 分割の意味と算出式の正本: orchestration-guide `## 14`

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

**【任意】Issue ファイル必読フロー（issue-workflow 併用時）**:

PR head / base branch 名から Issue ID を抽出し、ローカルの Issue ファイルがあれば spec-compliance reviewer の prompt に同梱する。仕様・受入条件・設計判断を踏まえた判定の精度が上がる（GitHub issue #43）。

抽出・探索の bash 手順・親 Issue の 1 段追跡・スキップ条件（best-effort / 後方互換）の詳細:
→ orchestration-guide `## 2`

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

**規模帯の判定（Phase 0 の規模キャップに使う / 必須）**: 全体の変更量ではなく、lock・生成物・テスト・doc を除いた **core** で数える（triage-guide `## 6.1`）。テスト 5 ファイルと doc 1 ファイルを含む 9 ファイルの PR が、実質 3 ファイル `+22 -13` にもかかわらず large 相当に扱われて 17 体起動する事故を防ぐ（GitHub issue #96）:

```bash
BASE=$(gh pr view <PR番号> --json baseRefName -q .baseRefName)
git diff --numstat "origin/${BASE}...HEAD" \
  | grep -Ev '(^|/)(dist|build|vendor)/|\.lock$|package-lock\.json$|yarn\.lock$|pnpm-lock\.yaml$|\.snap$|\.generated\.' \
  | grep -Ev '\.(test|spec)\.|(^|/)(__tests__|tests)/|\.md$|(^|/)docs/' \
  | awk '{f++; l+=$1+$2} END {printf "core: %d files / %d lines\n", f+0, l+0}'
```

出力の core ファイル数・行数を triage-guide `## 6.2` の表に当てて帯（small / medium / large）を決め、Phase 0 の構成テーブル・Step 7 レポート冒頭・締めフロー 4 の `size_tier` に記録する。

### 2.5. PR コンテキストブロックの構築

Step 1 の `fetch-pr-context.sh` 出力をそのまま「PR コンテキストブロック」として保持する（LLM による再構築・要約・編集は **禁止**：再現性と取りこぼし防止のため）。このブロックは Phase 0 のタイプ判定と **全 reviewer のプロンプト注入** の両方に使用する。

スクリプト出力の構造（参考）: → orchestration-guide `## 3`

### 3. Phase 0: トリアージ

`${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` を Read で読み込み、そのロジックに従ってエージェント構成を決定する。

**Phase 0 はメインコンテキストで実行する（Agent ツールは使わない）。**

#### 3.0 Stage 0: PR 種別分岐（先行判定）

**緊急モード先行判定**: 引数に `--emergency` が含まれる場合、triage-guide.md `## 2.5` の「緊急レビューモード」に従い最小構成（reviewer-bugs + reviewer-security のみ、explorer / 冗長ペア / Phase 5.5〜5.9 をスキップ）を採用する。この判定は以下の PR 種別分岐より優先する。decided したモードは `emergency` として Step 3.3 / Step 7 に記録し、Step 7 レポート冒頭に必須バナーを出す。

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
- explorer: 独立した探索対象の数に比例
- reviewer: 必要な観点数 × 対象コードの複雑さに応じた冗長度
- 冗長ペアには異なる angle（分析の切り口）を割り当てる（実起動は xhigh/max のみ。下記）
- 最小保証: reviewer-bugs + reviewer-claude-md の 2 体は常に起動

**実効上限 = min(effort 上限, 規模キャップ)**（体数の正本: triage-guide `## 7` / `## 6.2`）。**2 系統を必ず両方適用する**（effort 上限だけを見ると、小 PR に上限いっぱいの体数が張り付いて所要時間が数倍に膨らむ。GitHub issue #96 の実測は core 3 ファイル `+22 -13` の PR に 17 体 / 130 分）。

第 1 系統 — **effort 上限**（現在の effort = `${CLAUDE_EFFORT}`）:
- `low` / `medium`: explorer 2 体、reviewer 4 体、specialist 3 体（束ね起動）（最小保証は維持）。深掘りより速度優先
- `high`（既定）: explorer 4 体、reviewer 6 体、specialist 3 体（束ね起動）。**冗長ペアは組まない**（ペア条件成立時は Angle A/B を 1 体に内挿）。上限を超える観点数は近接観点のバンドルで可能な限り吸収し、それでも収まらない観点は `missing_coverage` に必ず記録する（容量の算式は triage-guide `## 7`。脱落を silent にしない）
- `xhigh` / `max`: explorer 6 体、reviewer 10 体、specialist 6 体を full に使い、冗長ペアを積極投入

第 2 系統 — **規模キャップ**（Step 2 で数えた core 規模。triage-guide `## 6`）:
- small（core ≤ 3 ファイル かつ ≤ 100 行）: explorer 0 / reviewer 3 / specialist 1
- medium（core 4-10 ファイル または 101-500 行）: explorer 2 / reviewer 5 / specialist 2
- large: キャップなし（effort 上限がそのまま実効上限）
- **最小保証の 2 体は規模キャップより優先**。キャップに収まらない観点は `missing_coverage` に「観点未起動: <focus>（規模キャップ: <帯>）」として記録する
- **規模キャップが effort 上限を下回った場合、Round 2（Step 5.5）は effort に関わらず 1 段圧縮経路**（追加 explorer なし）を使う。一方 **reviewer 個々の effort・meta-reviewer・skeptic・反証レイヤーは削らない**（規模キャップが削るのは breadth のみ。triage-guide `## 6.3`）

#### 3.3 観点カバレッジ検算と構成テーブル出力

**構成テーブルを確定する前に、起動前検算を実施する（orchestration-guide `### 8a`・default-mode のみ構成追加）**: 観点判定表の各条件を diff シグナルに対して再評価し、条件を満たすのに構成に入っていない focus があれば構成テーブルに追加（またはバンドルで相乗り）してから確定する。v2.39.0 で旧 Phase 5.7 の補完起動から前倒し（起動後の直列 wave を無くすため。検算内容は同一）。

**モード除外**: Stage 0 で `default-mode` 以外（`--emergency` / `doc-review-mode` / `dba-mode` / `supply-chain-mode` / `skip-mode`）に確定した場合、モードの推奨構成が観点判定表より優先するため**検算による構成追加は行わない**。検出した focus は `missing_coverage` に「観点未起動: <focus>（mode: <mode> により意図的縮退）」として記録のみする。

検算後、triage-guide.md の出力フォーマットに従い、エージェント構成テーブルを出力する。

#### 3.4 high-risk surface 判定（冷や読み skeptic の相乗り判断 / 常時実行）

Phase 0 の最後に、triage-guide `## 8.5` の surface 判定（diff への正規表現 grep + PR 自己申告 D1-High）を **必ず実施** する。安価な grep なので構成に関わらず常に行う（silent skip 防止・issue #85）。

- surface=true **かつ Phase 5.8 のスキップ条件（userConfig / effort / `--emergency`・`skip-mode`）のいずれにも該当しない**場合、skeptic を **Step 5 の reviewer 一括発行に相乗りさせる**（同一メッセージ内で発火。1 wave 削減）。**条件は個別に列挙せず Phase 5.8 の定義を参照すること** — 相乗りで起動が前倒しされる以上、5.8 に到達してからスキップ判定しても手遅れ（agent は既に走っている）。列挙の取りこぼしは `--emergency` で `effort: max` の skeptic が余計に走る事故に直結する
- surface=true だがスキップ条件に該当する場合は、`skip_reason` を記録して Step 7 レポートと payload に出す（従来どおり）
- reviewer の `[surface:high-risk]` フラグ由来で事後に surface=true になる経路は Phase 5.8 の fallback で拾う

### 4. 探索フェーズ（explorer 並列起動）

Phase 0 が explorer を 1 体以上配置した場合のみ実行。explorer が不要と判断された場合はスキップして Step 5 へ。

`${CLAUDE_PLUGIN_ROOT}/references/explorer-prompts.md` を Read で読み込む。

Phase 0 の構成テーブルに従い、各 explorer を `model: sonnet` で並列起動する:
- 各 explorer に Phase 0 が決定した focus と対象ファイル・関数を指示として渡す
- explorer-prompts.md の該当する Focus テンプレートをプロンプトに含める
- 全エージェントを `isolation: "worktree"` で起動する（PR ブランチの状態でファイルを読むため）
- 全エージェントに `run_in_background: false` を明示し、**全 explorer の Agent call を同一メッセージ内で一括発行する**（orchestration-guide `## 0`。`run_in_background` 省略は取りこぼし、1 体ずつ別メッセージ発行は逐次実行＝実時間が合計に膨らむ。2 つは独立の要件）
- **PR 番号注入（必須）**: orchestration-guide `## 1` に従う（欠かすと偽陽性を量産する。GitHub issue #56 / #69）

一括発行の**直前**に fleet 区間の開始マーカーを記録する（**agent wave はすべて fleet 側に入れる**。explorer を triage 区間に含めると `duration_triage_min` が「メイン思考の代理指標」でなくなる。orchestration-guide `## 14`）:

```bash
grep -q '^t1 ' "$TS_FILE" 2>/dev/null || echo "t1 $(date +%s)" >> "$TS_FILE"
```

全 explorer の完了を待ち、結果を収集する。

**部分失敗耐性:** orchestration-guide `## 5` に従う（個別失敗で全体を中止せず `missing_coverage` に記録して続行）。

### 4.9 AGENTS.md 階層動的選択（reviewer 起動前）

変更ファイルパスから対応する `{dir}/AGENTS.md` を Bash で探索し、該当層だけを reviewer プロンプトに同梱する（reviewer 入力 token を典型 30〜50% 削減）。

探索 bash・注入セクション名・no-op 条件（後方互換）の詳細: → orchestration-guide `## 4`

### 5. レビューフェーズ（reviewer 並列起動）

`${CLAUDE_PLUGIN_ROOT}/references/reviewer-prompts.md` を Read で読み込む。

Phase 0 の構成テーブルに従い、各 reviewer を `model: opus` で並列起動する。effort は実行時 `${CLAUDE_EFFORT}` に連動させる（low/medium/high（既定）→ `high`、xhigh/max → `xhigh`。設計意図は orchestration-guide `## 5`）:
- 各 reviewer に Phase 0 が決定した focus（と冗長ペアの場合は angle）を指示として渡す
- reviewer-prompts.md の該当する Focus テンプレートと共通指示をプロンプトに含める
- **explorer 結果の選択的注入**: 構成テーブルの「explorer 依存」列に記載された explorer の結果を、該当する reviewer のプロンプトに `## Explorer 結果` セクションとして注入する
- **PR コンテキスト注入**: Step 2.5 で構築した PR コンテキストブロックを、reviewer-prompts.md の「PR コンテキスト注入テンプレート」(#2.5) に従い全 reviewer のプロンプトに注入する（重複指摘の回避と著者意図の尊重ルールはテンプレート内に明記）
- セッションコンテキストが有効な場合、reviewer-prompts.md のセッションコンテキスト注入テンプレートに従い全 reviewer に注入する
- `gh pr diff` の出力を各 reviewer に渡す
- 全エージェントを `isolation: "worktree"` で起動する
- 全エージェントに `run_in_background: false` を明示し、**全 reviewer の Agent call を同一メッセージ内で一括発行する**（orchestration-guide `## 0` 並列発行の明示。1 体ずつ別メッセージで発行するとフェーズ実時間が相内最長でなく合計になる）
- **冷や読み skeptic の相乗り**: Step 3.4 で surface=true かつ Phase 5.8 のゲートを通過している場合、skeptic 1 体（`model: opus`, `effort: max`、reviewer-prompts.md `## 8`）を **この一括発行に含める**。skeptic は findings 非注入が設計の核で reviewer 出力に依存しないため、直列に置く理由がない（triage-guide `## 8.5` 起動タイミング）。結果の統合は Phase 5.8 で行う
- **PR 番号注入（必須）**: orchestration-guide `## 1` に従う

一括発行の**直前**に fleet 区間の開始マーカーを記録する（orchestration-guide `## 14`。`TS_FILE` は Step 1 と同じ導出式で決める。Step 4 で explorer を起動していれば既に記録済みなので、`grep` ガードで二重記録を防ぐ）:

```bash
grep -q '^t1 ' "$TS_FILE" 2>/dev/null || echo "t1 $(date +%s)" >> "$TS_FILE"
```

全 reviewer の完了を待ち、結果を収集する。

reviewer 起動の共通詳細（effort 設計意図・diff-first 原則・出力形式の検証と auto-retry・部分失敗耐性・最小保証の閾値）: → orchestration-guide `## 5`

**最小保証の閾値のみ抜粋**: Phase 0 の最小保証（reviewer-bugs と reviewer-claude-md）が **両方とも失敗** した場合のみレビュー中止とし、ユーザーに再実行を促してから ExitWorktree する。それ以外は欠損観点を明示しつつ Step 6 に進む。

### 5.5 Adaptive deepening: Round 2（unmet_information 起点 / 動的）

**スキップ条件**（いずれか満たせばこのフェーズ全体をスキップして Step 5.6 へ）:
- userConfig `enable_adaptive_rounds` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `low` または `medium`
- 全 reviewer の出力に `## unmet_information` セクションが 1 件もない

**実行する場合**: orchestration-guide `## 6` の手順に従う（unmet_information 集約 → **high は 1 段圧縮**: 追加 explorer なしで該当 reviewer 最大 3 体を再起動し unmet ターゲットを自力探索させる / **xhigh・max は 2 段**: 追加 explorer 最大 3 体 → 該当 reviewer 再起動 → 初回出力を置換。失敗時は初回結果のまま続行の best-effort）。レポートに「Round 2 trigger: <reason>」を記録（Step 7 で出力）。

### 5.6 Meta-reviewer ラウンド（v2.12.0 / 動的）

**スキップ条件**（いずれか満たせばスキップして Step 6 へ）:
- userConfig `enable_meta_reviewer` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `xhigh` または `max` **でない**
- Step 5.5 後の全指摘（フィルタリング前）に **BLOCKER も CRITICAL も 1 件もない**

**実行する場合**: orchestration-guide `## 7` の手順に従う（meta-reviewer を 1 体 `model: opus`, `effort: max` で起動 → 追加指摘を dedup して統合。失敗時は missing_coverage に追記して続行）。

### 5.7 観点カバレッジ・事後突合（メインコンテキスト / 常時実行・agent 追加起動なし）

Step 6 の直前に、**メインコンテキストで**（Agent は使わない・低コスト）Step 3.3 の起動前検算で確定した構成テーブルと実際に起動・完走した focus を突合し、差分を `missing_coverage` に追記する（orchestration-guide `### 8b`）。観点漏れの検出は Step 3.3 の起動前検算（`### 8a`）へ前倒し済みのため、**本フェーズで agent は追加起動しない**（v2.39.0。issue #69 の常時検査の意図は 8a で維持）。

**スキップ条件**: `--emergency`（緊急モード）または `skip-mode`（生成物 PR）では構成が意図的に最小化されているため本チェックをスキップする。

### 5.8 冷や読み skeptic ラウンド（recall 補強 / 動的）

観点カバレッジ self-check の後・反証レイヤーの前に、**high-risk surface を含む変更に限り**、他 reviewer の findings も推論も渡さない独立 skeptic を 1 体起動し、fleet 共通の盲点（層跨ぎ値フロー等）を冷や読みで探す（`${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` `## 8.5 冷や読み skeptic ラウンド`）。反証レイヤー(5.9)が偽陽性を潰す係なのに対し、本フェーズは見落とし（false negative）を独立読み直しで足す係。meta-reviewer(5.6)が findings 注入で非独立なため fleet 共通盲点を引きずるのを、独立性で補う。

**スキップ条件**（いずれか満たせばスキップして 5.9 へ）:
- userConfig `enable_recall_skeptic` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `xhigh` または `max` **でない**（high 既定は当面スキップ。`review:completed` の頻度計測後に high 昇格を検討＝既存 5.6/5.9 と対称の fail-safe）
- `--emergency`（緊急モード）または `skip-mode`（生成物 PR）
- high-risk surface（triage-guide.md `## 8.5` の surface 判定）を含まない

**スキップ時も surface 判定は必ず実施（silent skip 防止・issue #85）**: 上記スキップ条件（effort / config / emergency）に該当して skeptic agent を起動しない場合でも、surface 判定（triage-guide.md `## 8.5` の正規表現。diff への grep で安価）だけは Phase 0 の構成判断（縮退構成・小 diff）と **独立に必ず実施** する。surface=true なら skeptic 未起動の事実と skip_reason（`effort` / `config` / `emergency`）を Step 7 レポートの「動的ラウンド」行に必ず出す（`review:completed` payload の `recall_skeptic` 記録と対を成す human レポート契約）。

**実行する場合**: orchestration-guide `## 9` の手順に従う。**起動は Step 5 の reviewer 一括発行に相乗り済み**（Step 3.4 で surface 判定・ゲート通過を確認している）なので、本フェーズで行うのは **結果の統合**（`[recall-skeptic]` / `[recall-skeptic:dup]` タグ付き指摘を dedup して統合し、反証レイヤー(5.9)の対象にも含める）。

**fallback（直列起動）**: reviewer の `[surface:high-risk]` フラグ由来で**ここで初めて** surface=true になった場合のみ、skeptic を 1 体 `model: opus`, `effort: max` で単独起動する（**findings / reviewer の推論は渡さない**のが独立性の核）。正規表現・PR 自己申告で事前に HIT していれば相乗り済みなのでこの経路は走らない。

**失敗時 / スキップ時**: skeptic の失敗は `missing_coverage` に追記して続行。**起動条件（high-risk surface）を満たしたのに未実行だった事実は、失敗・effort/config/emergency スキップのいずれでも Step 7 レポートに必ず出す**（silent skip で「守ったつもり」の偽の安心を防ぐ）。

### 5.9 反証レイヤー（adversarial verification / 動的）

冷や読み skeptic の後・スコアリングの前に、reviewer の指摘を独立エージェントが反証する。偽陽性を人間が詰める前に先回りして摘出するフェーズ（`${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` `## 9 反証レイヤー`）。meta-reviewer (5.6) / skeptic (5.8) が見落とし（false negative）を足す係なのに対し、本フェーズは偽陽性（false positive）を独立に潰す鏡像。skeptic が足した指摘も本レイヤーの対象。

**スキップ条件**（いずれか満たせばスキップして Step 6 へ）:
- userConfig `enable_adversarial_verify` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `low` または `medium`
- `--emergency`（緊急モード）または `skip-mode`（生成物 PR）
- 反証対象（triage-guide.md `## 9` のゲート）に合致する指摘が 0 件

**実行する場合**: orchestration-guide `## 10` の手順に従う（triage-guide `## 9` の選定ルールで対象を選び、**5 件ずつのバッチ**に分けて反証エージェントを `model: opus`, `effort: high` で並列起動（上限 3 体）。**reviewer の理由文は渡さない**＝アンカリング防止 → verdict を finding_id で突合して Step 6 のスコアリングに渡す。失敗した指摘は verdict なしのまま続行の best-effort）。レポートに「反証: 対象 N 件 / 係争 M 件 / 取り下げ K 件」を記録（Step 7 で出力）。

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
4. **severity 調整**: `[scope:out]` / `[resolved: ...]` タグ付きは severity を 1 段階下げる（反証 `severity-inflated` もこのルールに統合。二重降格しない）。**BLOCKER / CRITICAL の `severity-inflated` は降格後に報告マトリクスを割る場合のみ据え置き + 反証メモ**（scoring-guide の不変条件。高 severity を silent に消さない）
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

**冷や読み skeptic の観測可能性（issue #85）**: high-risk surface を含む変更では、冷や読み skeptic（Phase 5.8）の起動有無を「動的ラウンド」行に **必ず** 出す（起動＝追加件数 / 未起動＝skip 理由）。surface HIT かつ未起動の silent skip を作らない。

**skeptic 由来の帰属をレポートまで保つ（`findings_added` の計測妥当性）**: Phase 5.8 の skeptic 指摘に付いた由来タグは、**レポート本文の指摘行にもそのまま残す**（`[confidence][severity]` の後・カテゴリの前に置く）。タグを落とすと**締めフロー 4** の publish 時点で由来を再構成できず、`findings_added` が記憶頼みになって系統的に 0 へ潰れる（＝ skeptic の価値率が実態より低く出る）。**由来タグはレポート契約の一部**であり、任意の装飾ではない。

タグは 2 種（正本: orchestration-guide `## 9`）。**重複の有無で意味が正反対**になるため混ぜない:

- `[recall-skeptic]` — skeptic 単独由来（reviewer 指摘と重複しなかった）。**fleet 共通盲点を実際に破った＝ skeptic の価値**
- `[recall-skeptic:dup]` — 重複 survivor（reviewer も到達していた）。独立到達の記録としては残すが**盲点でなかった事例で recall の足し前はゼロ**

```
## レビュー結果

{emergency モード時のみ先頭に: **⚠️ 緊急レビュー（最小構成）: マージ後に通常の /review を必ず実施すること**}

**[mode: {emergency|doc-review|dba|supply-chain|skip|default}, size: {small|medium|large} (core N files / N lines), agents: [<focus 名のリスト>]]**

**総合判定**: {Approve | Approve with nits | Needs work}（scoring-guide.md「レビュー結論（総合判定）」の表に従って決定）
**総合評価**: X/10 点
**レビュー構成**: Phase 0 (triage) → 探索 (N 起動 / M 成功) → レビュー (N 起動 / M 成功)
**実効上限**: explorer N / reviewer N / specialist N（effort `{値}` の上限と規模キャップ `{帯}` の min。どちらが効いたかを明記する）
**動的ラウンド**: Round 2 {未実行 | 実行（再起動 reviewer N 体 / 追加 explorer M 体）} / Meta-reviewer {実行 | スキップ理由} / 冷や読み skeptic {実行（N 件追加）| skip（理由: effort/config/emergency）| 非該当（surface なし）} / 反証 {対象 N 件 | スキップ理由}
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

4. [confidence: 85][severity: CRITICAL][recall-skeptic][バグ] 空文字の draft が numeric 列へ素通りする
   ファイル: src/repo.ts:88
   影響: 22P02 で INSERT が落ちる
   {由来タグ: skeptic 単独由来は `[recall-skeptic]` / reviewer と重複した survivor は `[recall-skeptic:dup]`。締めフロー 4 の publish で `findings_added` / `findings_overlap` を数える唯一の根拠なので落とさない。番号は他の指摘と通し連番にする}

### 📋 MAJOR 指摘

5. [confidence: 95][severity: MAJOR][設計] ...

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

**レポートを出力した直後に fleet 区間の終了マーカーを記録する**（締めフロー＝人間の応答待ちを混ぜないため。orchestration-guide `## 14`。`TS_FILE` は Step 1 と同じ導出式）:

```bash
echo "t2 $(date +%s)" >> "$TS_FILE"
```

レポート出力後、以下の順で締める。締めフロー 1〜3 の詳細手順（AskUserQuestion の文言・options 提示条件・3 分類の判定基準・解説の観点・ドラフトのパターン×voice・メタ行・署名・writing-polish 推敲・出力フォーマット）の正本:
→ Read `${CLAUDE_PLUGIN_ROOT}/references/closing-flow-guide.md`（以下「closing-flow-guide」。1〜3 のいずれかを実行する場合のみ読む）

1. **指摘の精査（必要性ゲート / 任意）**: 報告マトリクス通過後の指摘が **1 件以上** ある場合のみ実行（指摘 0 件、または `--emergency` 時はスキップして 2 へ）。Step 6 の機械フィルタ（閾値を超えるか）と Phase 5.9 反証（事実として正しいか）に対し、**第 3 軸＝必要性（signal/noise）** を人間に委ねるステップ。closing-flow-guide `## 1` に従い AskUserQuestion で要否を確認し、「精査する」なら各指摘を取り下げ / 降格 / 残存に 3 分類して `## 精査結果` と調整後レポートを再出力する。**精査を行わなかった場合は報告マトリクス通過後の全指摘を「残存」とみなす**（以降のステップが参照する「残存・降格した指摘」はこの確定集合を指す）。以降の返答ドラフト・publish は精査後（post）の確定値を使う。

2. **PR・指摘の解説（任意）**: 返答ドラフトの前に PR の全体像や指摘の背景を解説して判断材料を揃える（チャット出力のみ・投稿はしない）。`--emergency` 時はスキップして 3 へ。closing-flow-guide `## 2` に従い AskUserQuestion で対象（PR について / 指摘について）を確認して解説する。解説の結果ユーザーが取り下げ・降格を望んだ場合は 1 の 3 分類に差し戻して調整後レポートを再出力してから 3 へ進む。

3. **投稿コメントのドラフト生成（任意）**: 精査後に残存／降格した指摘が **1 件以上** ある、**または** 総合判定が **Approve / Approve with nits** の場合に実行（どちらにも該当しなければスキップして 4 へ）。closing-flow-guide `## 3` に従い AskUserQuestion で要否と対象を確認し、`reply-tone-guide.md` `## 0 必須ルール` を厳守した文面を生成する（パターン×voice 選定・メタ行・署名・断定抑止・`Skill` tool 経由の writing-polish 推敲を含む）。**投稿は行わずドラフト出力のみ**。ユーザーが GitHub UI で手動投稿する。

4. **Event Bus publish (`review:completed`)**: 集計結果を `.claude/events.jsonl` に追記する fire-and-forget の publisher。**指摘の精査を行った場合は精査後（post）の確定件数を使う**（取り下げ・降格を反映）。レポートに必要な数値（critical = confidence ≥ 90 件数、warning = 80 ≤ confidence < 90 件数、missing_coverage 配列）は既に手元にあるはず。`SAFE_HOOK_NAME` を `code-review:review` に上書きして event_bus_publish を直接呼ぶ。

   **書込先はメインリポジトリのルートに固定する（必須。GitHub issue #96）**: この時点の cwd は Step 0 で入った worktree であり、`event_bus_publish` は `CLAUDE_PROJECT_DIR` 未設定時に cwd 相対で書く。素のまま publish すると worktree 側の `.claude/events.jsonl` に書かれ、直後の締めフロー 5 `ExitWorktree(remove)` で**計測ごと消える**（2026-07-31 時点で review 由来のサンプルが 1 件も残っていない原因）。導出式と落とし穴（`GCD` 空時に `/` へ cd する事故）の正本: → orchestration-guide `## 13`

   ```bash
   # events.jsonl と開始時刻ファイルの基準を「メインリポジトリのルート」に固定する。
   # worktree 内の --show-toplevel は worktree 自身を返すので使わない（--git-common-dir を使う）
   GCD=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
   MAIN_ROOT=$([ -n "$GCD" ] && (cd "$GCD/.." && pwd) || pwd)
   # 区間マーカーは Step 1 / 4-5 / 7 が書いたファイルから読む（シェル変数は呼び出し間で消えるため）
   # 欠測はすべて -1（0 と区別する）。算出式の正本: orchestration-guide `## 14`
   TS_FILE="${TMPDIR:-/tmp}/.review-start-$(printf %s "$MAIN_ROOT" | cksum | cut -d' ' -f1)"
   NOW=$(date +%s)
   DURS=$(awk -v now="$NOW" '{t[$1]=$2} END {
     printf "%d %d %d %d",
       ("t0" in t) ? int((now - t["t0"])/60) : -1,
       ("t0" in t && "t1" in t) ? int((t["t1"] - t["t0"])/60) : -1,
       ("t1" in t && "t2" in t) ? int((t["t2"] - t["t1"])/60) : -1,
       ("t2" in t) ? int((now - t["t2"])/60) : -1
   }' "$TS_FILE" 2>/dev/null)
   # 分割代入は read を使う（zsh は `set -- $VAR` で語分割しないため壊れる）
   read DUR DUR_TRIAGE DUR_FLEET DUR_CLOSING <<< "${DURS:--1 -1 -1 -1}"
   source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh" 2>/dev/null && \
     CLAUDE_PROJECT_DIR="$MAIN_ROOT" SAFE_HOOK_NAME="code-review:review" event_bus_publish "review:completed" \
     "{\"pr\":\"<number>\",\"effort\":\"${CLAUDE_EFFORT}\",\"size_tier\":\"<small|medium|large>\",\"duration_min\":$DUR,\"duration_triage_min\":$DUR_TRIAGE,\"duration_fleet_min\":$DUR_FLEET,\"duration_closing_min\":$DUR_CLOSING,\"agents\":{\"explorer\":<n>,\"reviewer\":<n>,\"specialist\":<n>,\"round2\":<n>,\"verify\":<n>,\"verify_findings\":<n>},\"blocker_count\":<n>,\"critical_count\":<n>,\"major_count\":<n>,\"minor_count\":<n>,\"missing_coverage\":[<json-array of focus names>],\"result_grid\":{\"high\":<n>,\"medium\":<n>,\"low\":<n>,\"skip\":<n>,\"error\":<n>},\"adversarial_verify\":{\"confirmed\":<n>,\"refuted\":<n>,\"uncertain\":<n>,\"severity_inflated\":<n>,\"contested\":<n>},\"recall_skeptic\":{\"attribution_schema\":2,\"surface\":<bool>,\"fired\":<bool>,\"skip_reason\":<string|null>,\"findings_added\":<n>,\"findings_overlap\":<n>}}"
   rm -f "$TS_FILE"   # 中断したレビューの残骸が次回の duration を汚さないよう掃除する
   ```

   payload 規約:
   - `pr` は PR 番号の文字列（Step 1 で取得済み）。PR 番号取得に失敗した場合は `"local"` とする
   - `effort` は実行時 `${CLAUDE_EFFORT}` の文字列（`low`〜`max`。山括弧などの装飾は付けず実値をそのまま入れる）。体数上限・動的ラウンドの起動有無を左右する条件変数なので、下流の集計は本フィールドで層別する（v2.39.0 追加）
   - `size_tier` は Phase 0 が判定した規模帯（`small` / `medium` / `large`。triage-guide `## 6.1` の core 基準）。規模キャップの効果測定と `duration_min` の層別に使う（v2.40.0 追加。所要時間は規模と体数の両方に効かれるため、帯を混ぜた比較はキャップの効果を検出できない）
   - `duration_min` は Step 1 が `$TS_FILE`（TMPDIR 配下・**メインリポジトリのルートから決定的に導出**）に書いた `t0` から publish 時点までの分（整数・全体）。**シェル変数での受け渡しは禁止**（Bash 呼び出し間で変数は消え、bash 算術が未定義変数を 0 と評価して epoch/60 のゴミ値が入るため）。ファイルが無い・マーカーが欠ける場合は `-1`（欠測を 0 と区別する）。パス導出を cwd 基準にすると Step 1（worktree 内）と publish 時で食い違って常に欠測になるため、両方で同じ `MAIN_ROOT` 導出式を使う
   - `duration_triage_min` / `duration_fleet_min` / `duration_closing_min` は所要時間の 3 分割（v2.41.0 追加。正本: orchestration-guide `## 14`）。**この 3 つを混ぜて比較しない**:
     - `duration_triage_min`（t0→t1）: PR/diff 収集・Phase 0・起動前検算・プロンプト構築＝**メインコンテキストの思考時間の代理指標**
     - `duration_fleet_min`（t1→t2）: reviewer 発火から初回レポートまで＝**agent wave の実時間 + scoring/レポート生成**
     - `duration_closing_min`（t2→t3）: 締めフロー＝**大半が人間の応答待ち**。改善の効果測定には使わない（人間の都合で 10 倍振れる）
     - 3 区間の和は `duration_min` と一致しないことがある（マーカー欠測時）。一致を仮定した検算をしない
   - `agents` は実際に**起動した** agent 体数（成功・失敗を問わず起動数。v2.39.0 の上限調整の効果測定に使う）:
     - `explorer`: Step 4 の初回 explorer 体数
     - `reviewer`: Step 5 の初回 reviewer 体数（specialist を含めない）
     - `specialist`: red-flag specialist の実起動体数（束ね後）
     - `round2`: Phase 5.5 の再起動 reviewer + 追加 explorer の合計（レポート「動的ラウンド」行の N + M と一致させる）
     - `verify`: Phase 5.9 の反証エージェント体数（**バッチ化後は体数 ≒ ceil(実施件数/5)** なので指摘数の代理指標にならない）。**v2.41.0 前後で意味が変わる**（旧: 指摘ごと 1 体）ため、集計時は `duration_triage_min` の有無で層別してから使う
     - `verify_findings`: Phase 5.9 で**実際に verdict が返った件数**（v2.41.0 追加。バッチ化で体数と件数が分離したため別フィールドにする）。**レポート反証行の「うち実施 X 件」と一致させる**（ゲートで選ばれた対象 N 件ではない。予算超過・反証失敗で verdict が無い分は含めない）
     - meta-reviewer / skeptic は含めない（skeptic は `recall_skeptic.fired`、meta はレポートの「動的ラウンド」行で観測可能）
   - `blocker_count` / `critical_count` / `major_count` / `minor_count` は数値（severity 別件数）
   - `missing_coverage` は文字列配列（reviewer focus 名）。空なら `[]`
   - `result_grid` は 5 値の集計オブジェクト（後段 hook / PR コメント自動投稿の dispatch 用）:
     - `high`: BLOCKER または CRITICAL 件数（即対応必要）
     - `medium`: MAJOR 件数（PR ブロックはしないが対応推奨）
     - `low`: MINOR 件数（nitpick / 提案）
     - `skip`: severity スコープ外でフィルタされた件数
     - `error`: reviewer / explorer が失敗した件数（`missing_coverage` の length と一致）
   - `adversarial_verify` は反証レイヤー（Phase 5.9）の verdict 集計（`confirmed` / `refuted` / `uncertain` / `severity_inflated` / `contested`=高 severity の係争件数）。反証スキップ時は全 0。**review / self-review 両 publisher で同一フィールド名を揃える**（後から偽却下率を計測するため）。`severity_inflated` は v2.41.0 追加（4 つ目の verdict が集計から漏れていた。バッチ化 + effort 引き下げのロールバック判断に使う。triage-guide `## 9`）
   - `recall_skeptic` は冷や読み skeptic（Phase 5.8）の実行記録。skeptic の high 昇格判断（triage-guide.md `## 8.5` の effort ゲート見直し）の計測データになる:
     - `surface`: high-risk surface 判定の結果（bool）。**Phase 5.8 が effort / userConfig でスキップされた場合も、正規表現部分の surface 判定（triage-guide.md `## 8.5`。diff への grep で安価）だけは payload 構築時に必ず実施して記録する**。「surface=true なのに effort ゲートで skeptic が走らなかった頻度」が high 昇格判断の核心メトリクスのため
     - `fired`: skeptic agent が実際に起動したか（bool）
     - `skip_reason`: `fired=false` のときの理由。`"effort"`（xhigh/max 未満）/ `"config"`（`enable_recall_skeptic: false`）/ `"no-surface"` / `"emergency"`（緊急・skip モード）のいずれか。`fired=true` なら `null`
     - `attribution_schema`: 由来帰属の規約バージョン。**常に `2` を入れる**（2 = 由来タグがレポート書式に規定され dedup のタグ生存も定義された版 = 2.35.1 以降）。マーカー無し（schema 1 相当）の旧サンプルは `findings_added` が記憶依存で系統的に 0 へ潰れており判断に使えないため、下流の集計は本フィールドで濾す（triage-guide `## 8.5`）。**日付では切れない** — 配布ラグにより未更新マシンは修正日以降も schema 1 を publish し続けるため
     - `findings_added`: **skeptic 単独由来**（`[recall-skeptic]` タグ。reviewer 指摘と重複しなかった）の指摘のうち報告マトリクスを通過した件数。**「動的ラウンド」行の `実行（N 件追加）` の N と同値**（N はヘッダに置かれ本文より先に出力されるが、**本文確定後に数えてヘッダへ反映する**。二重管理にしない）。**skeptic の価値率の分子はこれのみ**（重複分は下の `findings_overlap` へ。混ぜると重複が常態のため価値率が 100% に張り付き、縮小分岐が原理的に発火しなくなる）
     - `findings_overlap`: **重複 survivor**（`[recall-skeptic:dup]` タグ。reviewer も同じ問題に到達していた）の件数。skeptic が独立に到達した記録として残すが、盲点でなかった事例なので**価値率には算入しない**
     - 両フィールドとも **Step 7 で最初に出力したレポート本文のタグ付き指摘を数えて求める**（Phase 5.8 の記憶から再構成しない。publish は Phase 5.8 から遠く、間に精査・解説・ドラフト生成が挟まるため、記憶依存にすると系統的に 0 へ潰れる）。**計測点は報告マトリクス通過時点（精査の前）＝ Step 7 の初回レポート**であり、精査（締めフロー 1）が再出力する調整後レポートではない。**精査で取り下げた分は減算しない** — 「skeptic が報告に値する指摘を出せたか」を測るフィールドで、必要性で落ちたかは別軸なので混ぜない
   - 失敗してもレポート自体は成功扱い（best-effort）
   - 後方互換: subscriber 側は `critical_count` の存在を仮定して良い（旧 payload との互換性のため必須）。`result_grid` / `adversarial_verify` / `recall_skeptic` / `effort` / `duration_min` / `agents` / `size_tier` / `duration_*_min` / `agents.verify_findings` は新規フィールド追加なので旧 subscriber 影響なし。**`duration_triage_min` の存在が v2.41.0 以降の publish マーカー**（縮小前後の層別に使う。日付では切らない）

5. **ExitWorktree** で worktree から抜ける。

6. **関連 worktree の teardown 案内（任意・非ブロッキング）**: ExitWorktree 後（main clone 上）、PR ブランチに紐づく**開発用 worktree**（dev-workflow:worktree-setup で作成したもの）が残っていないか検出する。ブランチ名一致だけではレビュー用に EnterWorktree した一時 worktree（`.claude/worktrees/` 配下）と区別できないため、**パス除外 + worktree-setup マーカーの 2 条件**で開発用 worktree に限定する:

   ```bash
   # PR ブランチを保持する worktree を列挙 → 一時 worktree を除外 → worktree-setup 由来のみ残す
   git worktree list --porcelain \
     | awk -v ref="refs/heads/<PR ブランチ名>" '/^worktree /{wt=substr($0,10)} $0=="branch "ref{print wt}' \
     | while read -r wt; do
         case "$wt" in */.claude/worktrees/*) continue;; esac   # レビュー用一時 worktree
         [ -f "$wt/envs/.backend.env.worktree" ] && echo "$wt"  # worktree-setup マーカー
       done
   ```

   - 検出した場合のみ、最後に一言案内する: 「関連する開発用 worktree が残っています: `<path>`。作業が完了していれば該当 worktree 内で `/worktree-teardown` を実行して片付けられます」
   - dev-workflow の有効判定は self-review Step 8 と同じ enabled-only 判定（`grep -Eq '"dev-workflow@[^"]*"[[:space:]]*:[[:space:]]*true'` を global / project / local の settings 3 ファイルに対して実行）。無効なら `git worktree remove <path>` の手動案内に切り替える
   - worktree-teardown は worktree 内からしか実行できないため、ここでは**自動起動しない**（案内のみ）
   - 未検出なら何も出力しない
   - 補足: 開発用 worktree が PR ブランチを checkout したままだと、Step 1 の `gh pr checkout` は二重チェックアウト禁止で失敗する（レビュー自体は `gh pr diff` ベースで劣化続行できる）。その経路でも本ステップの検出は機能する
