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
- 全エージェントに `run_in_background: false` を明示する（orchestration-guide `## 0`。省略すると background 起動になり結果を取りこぼす）
- **PR 番号注入（必須）**: orchestration-guide `## 1` に従う（欠かすと偽陽性を量産する。GitHub issue #56 / #69）

全 explorer の完了を待ち、結果を収集する。

**部分失敗耐性:** orchestration-guide `## 5` に従う（個別失敗で全体を中止せず `missing_coverage` に記録して続行）。

### 4.9 AGENTS.md 階層動的選択（reviewer 起動前）

変更ファイルパスから対応する `{dir}/AGENTS.md` を Bash で探索し、該当層だけを reviewer プロンプトに同梱する（reviewer 入力 token を典型 30〜50% 削減）。

探索 bash・注入セクション名・no-op 条件（後方互換）の詳細: → orchestration-guide `## 4`

### 5. レビューフェーズ（reviewer 並列起動）

`${CLAUDE_PLUGIN_ROOT}/references/reviewer-prompts.md` を Read で読み込む。

Phase 0 の構成テーブルに従い、各 reviewer を `model: opus`、`effort: xhigh` で並列起動する:
- 各 reviewer に Phase 0 が決定した focus（と冗長ペアの場合は angle）を指示として渡す
- reviewer-prompts.md の該当する Focus テンプレートと共通指示をプロンプトに含める
- **explorer 結果の選択的注入**: 構成テーブルの「explorer 依存」列に記載された explorer の結果を、該当する reviewer のプロンプトに `## Explorer 結果` セクションとして注入する
- **PR コンテキスト注入**: Step 2.5 で構築した PR コンテキストブロックを、reviewer-prompts.md の「PR コンテキスト注入テンプレート」(#2.5) に従い全 reviewer のプロンプトに注入する（重複指摘の回避と著者意図の尊重ルールはテンプレート内に明記）
- セッションコンテキストが有効な場合、reviewer-prompts.md のセッションコンテキスト注入テンプレートに従い全 reviewer に注入する
- `gh pr diff` の出力を各 reviewer に渡す
- 全エージェントを `isolation: "worktree"` で起動する
- 全エージェントに `run_in_background: false` を明示する（orchestration-guide `## 0`）
- **PR 番号注入（必須）**: orchestration-guide `## 1` に従う

全 reviewer の完了を待ち、結果を収集する。

reviewer 起動の共通詳細（effort 設計意図・diff-first 原則・出力形式の検証と auto-retry・部分失敗耐性・最小保証の閾値）: → orchestration-guide `## 5`

**最小保証の閾値のみ抜粋**: Phase 0 の最小保証（reviewer-bugs と reviewer-claude-md）が **両方とも失敗** した場合のみレビュー中止とし、ユーザーに再実行を促してから ExitWorktree する。それ以外は欠損観点を明示しつつ Step 6 に進む。

### 5.5 Adaptive deepening: 追加 explorer ラウンド（v2.12.0 / 動的）

**スキップ条件**（いずれか満たせばこのフェーズ全体をスキップして Step 5.6 へ）:
- userConfig `enable_adaptive_rounds` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `low` または `medium`
- 全 reviewer の出力に `## unmet_information` セクションが 1 件もない

**実行する場合**: orchestration-guide `## 6` の手順に従う（unmet_information 集約 → 追加 explorer 最大 3 体 → 該当 reviewer 再起動 → 初回出力を置換。失敗時は初回結果のまま続行の best-effort）。レポートに「Round 2 trigger: <reason>」を記録（Step 7 で出力）。

### 5.6 Meta-reviewer ラウンド（v2.12.0 / 動的）

**スキップ条件**（いずれか満たせばスキップして Step 6 へ）:
- userConfig `enable_meta_reviewer` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `xhigh` または `max` **でない**
- Step 5.5 後の全指摘（フィルタリング前）に **BLOCKER も CRITICAL も 1 件もない**

**実行する場合**: orchestration-guide `## 7` の手順に従う（meta-reviewer を 1 体 `model: opus`, `effort: max` で起動 → 追加指摘を dedup して統合。失敗時は missing_coverage に追記して続行）。

### 5.7 観点カバレッジ・セルフチェック（メインコンテキスト / 常時実行）

Step 6 の直前に、**メインコンテキストで**（Agent は使わない・低コスト）起動 focus の妥当性を 1 回検査する。観点漏れは高 severity 指摘が無くても起こりうるため、meta-reviewer (5.6) の起動有無・effort・severity に依存せず **常時実行** する（meta-reviewer は起動条件が「effort=xhigh/max かつ BLOCKER/CRITICAL あり」と厳しく、観点漏れを取りこぼすため。GitHub issue #69）。

手順の詳細（観点判定表の再評価 → 未起動 focus 検出 → missing_coverage 追記 → high 以上での補完起動）: → orchestration-guide `## 8`

**スキップ条件**: `--emergency`（緊急モード）または `skip-mode`（生成物 PR）では構成が意図的に最小化されているため本チェックをスキップする。

### 5.8 冷や読み skeptic ラウンド（recall 補強 / 動的）

観点カバレッジ self-check の後・反証レイヤーの前に、**high-risk surface を含む変更に限り**、他 reviewer の findings も推論も渡さない独立 skeptic を 1 体起動し、fleet 共通の盲点（層跨ぎ値フロー等）を冷や読みで探す（`${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` `## 8.5 冷や読み skeptic ラウンド`）。反証レイヤー(5.9)が偽陽性を潰す係なのに対し、本フェーズは見落とし（false negative）を独立読み直しで足す係。meta-reviewer(5.6)が findings 注入で非独立なため fleet 共通盲点を引きずるのを、独立性で補う。

**スキップ条件**（いずれか満たせばスキップして 5.9 へ）:
- userConfig `enable_recall_skeptic` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `xhigh` または `max` **でない**（high 既定は当面スキップ。`review:completed` の頻度計測後に high 昇格を検討＝既存 5.6/5.9 と対称の fail-safe）
- `--emergency`（緊急モード）または `skip-mode`（生成物 PR）
- high-risk surface（triage-guide.md `## 8.5` の surface 判定）を含まない

**スキップ時も surface 判定は必ず実施（silent skip 防止・issue #85）**: 上記スキップ条件（effort / config / emergency）に該当して skeptic agent を起動しない場合でも、surface 判定（triage-guide.md `## 8.5` の正規表現。diff への grep で安価）だけは Phase 0 の構成判断（縮退構成・小 diff）と **独立に必ず実施** する。surface=true なら skeptic 未起動の事実と skip_reason（`effort` / `config` / `emergency`）を Step 7 レポートの「動的ラウンド」行に必ず出す（`review:completed` payload の `recall_skeptic` 記録と対を成す human レポート契約）。

**実行する場合**: orchestration-guide `## 9` の手順に従う（surface 判定 → skeptic を 1 体 `model: opus`, `effort: max` で起動。**findings / reviewer の推論は渡さない**のが独立性の核 → `[recall-skeptic]` タグ付き指摘を dedup して統合し、反証レイヤー(5.9)の対象にも含める）。

**失敗時 / スキップ時**: skeptic の失敗は `missing_coverage` に追記して続行。**起動条件（high-risk surface）を満たしたのに未実行だった事実は、失敗・effort/config/emergency スキップのいずれでも Step 7 レポートに必ず出す**（silent skip で「守ったつもり」の偽の安心を防ぐ）。

### 5.9 反証レイヤー（adversarial verification / 動的）

冷や読み skeptic の後・スコアリングの前に、reviewer の指摘を独立エージェントが反証する。偽陽性を人間が詰める前に先回りして摘出するフェーズ（`${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` `## 9 反証レイヤー`）。meta-reviewer (5.6) / skeptic (5.8) が見落とし（false negative）を足す係なのに対し、本フェーズは偽陽性（false positive）を独立に潰す鏡像。skeptic が足した指摘も本レイヤーの対象。

**スキップ条件**（いずれか満たせばスキップして Step 6 へ）:
- userConfig `enable_adversarial_verify` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `low` または `medium`
- `--emergency`（緊急モード）または `skip-mode`（生成物 PR）
- 反証対象（triage-guide.md `## 9` のゲート）に合致する指摘が 0 件

**実行する場合**: orchestration-guide `## 10` の手順に従う（triage-guide `## 9` の選定ルールで対象を選び、反証エージェントを `model: opus`, `effort: max` で並列起動。**reviewer の理由文は渡さない**＝アンカリング防止 → verdict を Step 6 のスコアリングに渡す。失敗した指摘は verdict なしのまま続行の best-effort）。レポートに「反証: 対象 N 件 / 係争 M 件 / 取り下げ K 件」を記録（Step 7 で出力）。

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

**冷や読み skeptic の観測可能性（issue #85）**: high-risk surface を含む変更では、冷や読み skeptic（Phase 5.8）の起動有無を「動的ラウンド」行に **必ず** 出す（起動＝追加件数 / 未起動＝skip 理由）。surface HIT かつ未起動の silent skip を作らない。

**skeptic 由来の帰属をレポートまで保つ（`findings_added` の計測妥当性）**: Phase 5.8 の skeptic 指摘に付いた由来タグは、**レポート本文の指摘行にもそのまま残す**（`[confidence][severity]` の後・カテゴリの前に置く）。タグを落とすと**締めフロー 4** の publish 時点で由来を再構成できず、`findings_added` が記憶頼みになって系統的に 0 へ潰れる（＝ skeptic の価値率が実態より低く出る）。**由来タグはレポート契約の一部**であり、任意の装飾ではない。

タグは 2 種（正本: orchestration-guide `## 9`）。**重複の有無で意味が正反対**になるため混ぜない:

- `[recall-skeptic]` — skeptic 単独由来（reviewer 指摘と重複しなかった）。**fleet 共通盲点を実際に破った＝ skeptic の価値**
- `[recall-skeptic:dup]` — 重複 survivor（reviewer も到達していた）。独立到達の記録としては残すが**盲点でなかった事例で recall の足し前はゼロ**

```
## レビュー結果

{emergency モード時のみ先頭に: **⚠️ 緊急レビュー（最小構成）: マージ後に通常の /review を必ず実施すること**}

**[mode: {emergency|doc-review|dba|supply-chain|skip|default}, agents: [<focus 名のリスト>]]**

**総合判定**: {Approve | Approve with nits | Needs work}（scoring-guide.md「レビュー結論（総合判定）」の表に従って決定）
**総合評価**: X/10 点
**レビュー構成**: Phase 0 (triage) → 探索 (N 起動 / M 成功) → レビュー (N 起動 / M 成功)
**動的ラウンド**: Round 2 探索 N 体起動 / Meta-reviewer {実行 | スキップ理由} / 冷や読み skeptic {実行（N 件追加）| skip（理由: effort/config/emergency）| 非該当（surface なし）} / 反証 {対象 N 件 | スキップ理由}
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

   「そのまま」なら 2 へ（**精査を行わなかった場合は報告マトリクス通過後の全指摘を「残存」とみなす**。以降のステップが参照する「残存・降格した指摘」はこの確定集合を指す）。「精査する」なら **メインコンテキストで**（Agent 不使用）各指摘を 3 分類する。判定には必ず根拠（カテゴリ + file:line / PR コンテキスト典拠）を添える:

   - **取り下げ（withdraw）** — 正しくても対応に値しない: 純粋な好み（CLAUDE.md / style guide / 計測 / 具体的不具合の根拠なし、≤40 クランプを擦り抜けた残滓）/ settled な設計判断の蒸し返し（session-context / Issue / PR 説明で確定済み）/ 実害極小の MINOR nitpick / 既存コード由来（この diff 非導入）
   - **降格（downgrade）** — 内容は妥当だが severity 過大: 1 段階下げ + `Optional:` / `Nit:` 化
   - **残存（keep）** — 実害・リスク・規約違反の根拠を伴い著者が知るべき。**BLOCKER / CRITICAL は降格はあっても取り下げない**（既存コード由来であっても残存させ `既存コード由来` の文脈を付記する。取り下げの「既存コード由来」は MAJOR 以下に限る。反証レイヤーの「高 severity 非削除」不変条件と整合）

   取り下げ・降格は **理由を明示し人間が覆せる形**で提示する（破棄しない）。精査後、`## 精査結果`（取り下げ N / 降格 M / 残存 K ＋ 取り下げた指摘の一覧と理由）を出力し、**残存 + 降格を反映した調整後レポートを再出力**する（総合判定・severity 別件数を残存指摘で再導出）。以降の返答ドラフト・publish は精査後（post）の確定値を使う。

2. **PR・指摘の解説（任意）**: 返答ドラフトを書く前に、PR の全体像や各指摘の背景を解説して判断材料を揃える。**解説はチャット出力のみで投稿コメントではない**ため `reply-tone-guide.md` は適用しない（署名・敬語テンプレは不要）。`--emergency` 時はスキップして 3 へ。

   精査（1）の確定後に **AskUserQuestion** で解説対象を確認する:

   - question: "返答ドラフトの前に解説しますか？（PR の全体像や指摘の背景を説明します。投稿はしません）"
   - header: "解説"
   - multiSelect: true
   - options:
     1. label: "解説不要" / description: "解説せず返答ドラフトの確認へ進む（既定）"
     2. label: "PR について" / description: "この PR が何をやっているか＝変更の全体像・設計意図・影響範囲を解説"
     3. label: "指摘について" / description: "対象の指摘番号を次に入力。なぜ問題か／直し方／取り下げ材料を解説"（**残存・降格した指摘が 1 件以上あるときのみ提示**）

   「解説不要」が選ばれたら（他と同時に選ばれていても優先して）3 へ。それ以外は選択された対象を解説する:

   - **PR について**: Step 2.5 で構築した PR コンテキストブロックと diff を典拠に、`変更の全体像`（何を・なぜ）/ `設計意図`（採用したアプローチと、そう読み取れる根拠）/ `変更の流れ`（主要ファイルの関係）/ `影響範囲`（波及先・リスク面）を解説する
   - **指摘について**: **AskUserQuestion** で「解説する指摘番号（例: `1,3,5` / `all`）」を free-text 入力させ、対象の**残存・降格指摘ごとに**以下 3 点を解説する（`all` = 残存・降格した指摘の全件。取り下げ済みは含まない。範囲外番号・空入力は対象なしとみなして 3 へ）:
     - **なぜ問題か**: 背景・原理・実害シナリオ。必ずコード根拠（`file:line`）を添える
     - **直し方**: 具体的な修正方針と代替案・トレードオフ（そのまま返答ドラフトの前提知識になる）
     - **取り下げ材料**: 反論・据置の根拠になりうる情報（既存コード由来か / settled な設計判断か / 実害が極小か）。**取り下げを推すのではなく、著者が指摘を覆すための材料を対称に置く**

   - **断定抑止（1 と同基準）**: 解説でも load-bearing な事実主張は断定で書かない。repo で確認できる主張は `file:line` を、正本 doc で確認できる主張は典拠を添える。repo / 正本で裏が取れない外部状態（DB / 本番 / 運用設定）は「要確認（典拠=X）」とし、元の指摘が `[unverified: ...]` 付きならその不確実性を解説にも引き継ぐ
   - 解説の結果ユーザーが取り下げ・降格を望んだ場合は、1 の 3 分類に差し戻して**調整後レポートを再出力**してから 3 へ進む（以降の返答ドラフト・publish は再確定値を使う）

3. **投稿コメントのドラフト生成（任意）**: 精査後に残存／降格した指摘が **1 件以上** ある、**または** 総合判定が **Approve / Approve with nits** の場合に実行（どちらにも該当しなければスキップして 4 へ）。生成する全文面は `reply-tone-guide.md` `## 0 必須ルール`（Claude 署名 / 作成者・他レビュアーへの敬意 / 簡潔さ / 良い点を 1 文 / メタ行 / 著者配慮チェックリスト）を**厳守**する。

   精査（1）・解説（2）の確定後に **AskUserQuestion** で要否を確認する（options は状態に応じて提示する）:

   - question: "投稿用コメントのドラフトを生成しますか？（投稿は行わず、コピペ可能な文面のみ出力します）"
   - header: "コメントドラフト"
   - multiSelect: false
   - options:
     1. label: "不要" / description: "ドラフトは生成しない（既定）"
     2. label: "承認コメント" / description: "簡潔な承認 + 良い点 1 文 + 署名"（**総合判定が Approve / Approve with nits のときのみ提示**）
     3. label: "重要指摘のみ" / description: "severity BLOCKER / CRITICAL の返答ドラフト"（**BLOCKER / CRITICAL が 1 件以上あるときのみ提示**。Approve with nits は定義上 BLOCKER/CRITICAL が無く本選択肢が空振りするため、残存指摘の有無では条件付けない）
     4. label: "全件" / description: "全残存指摘 ＋ 該当すれば承認コメント"（残存指摘があるときのみ）
     5. label: "個別選択" / description: "対象の指摘番号を入力する"（残存指摘があるときのみ）

   **選択肢数の不変条件**（AskUserQuestion は 2〜4 個が仕様上限。提示条件を変更するときは必ず再検算する）:

   | 総合判定 | 提示される options | 数 |
   |---|---|---|
   | Approve（報告指摘ゼロ） | 不要 / 承認コメント | 2 |
   | Approve with nits（BLOCKER・CRITICAL なし、残存 ≥ 1） | 不要 / 承認コメント / 全件 / 個別選択 | 4 |
   | Needs work（BLOCKER または CRITICAL ≥ 1） | 不要 / 重要指摘のみ / 全件 / 個別選択 | 4 |

   「不要」なら 4 へ。それ以外は以下を実行:

   - `${CLAUDE_PLUGIN_ROOT}/references/reply-tone-guide.md` を Read で読み込む
   - **承認コメント**（総合判定 Approve / Approve with nits、かつ「承認コメント」または「全件」選択時）: reply-tone-guide.md `### 2.7 承認メッセージ` のテンプレで生成。良い点は「良かった点」セクションから **1 文に圧縮**（file:line 添え）。Needs work では生成しない。**承認メッセージ本文で触れた nit は指摘返答ドラフトと重複させない**（全体コメントは要点のみ・詳細は inline スレッド側へ。reply-tone-guide 2.7「nits は詳述しない」と整合）
   - **指摘への返答**（残存指摘が対象。「個別選択」なら AskUserQuestion で「対象の指摘番号（例: 1,3,5）」を free-text 入力）: 対象指摘ごとにパターンと **voice（文面の声＝誰の発言か）** を選ぶ。voice はメタ行の要否を決める唯一の判定軸なので、パターン番号と**必ず対で**決める:

     | 状況 | パターン | voice | メタ行（0.5） |
     |---|---|---|---|
     | 著者対応 commit が PR にある | 解決度（完全/部分/未対応）に応じて 2.1〜2.5 | 著者 | なし |
     | 著者対応 commit がない | 2.4 / 2.5 | 著者 | なし |
     | `[re-flag: @user]` タグ付き（＝こちらのレポート由来の再指摘） | 2.5「再指摘の追補」 | **レビュアー** | **あり** |
     | レビュアー視点（自分発信の指摘） | 2.6 | **レビュアー** | **あり**（ただし残存指摘のない全面解決の確認文は不要） |

     **voice の決め方**: 指摘の出所で決める。**こちらのレポート由来の指摘を著者に伝える文面＝レビュアー発信**（`[re-flag]` はレポート由来なのでレビュアー発信）。**PR の他者 review comment に著者として返す文面＝著者発信**。
     - 1〜3 文で生成（長文化させない）
   - **レビュアー発信の文面には冒頭にメタ行を置く**（reply-tone-guide.md 0.5）: `**重大度: {severity} / 確信度: {confidence} / マージブロッカー: {はい|いいえ}**`。値は**精査（締めフロー 1）後の確定値**（降格していれば降格後）を引き継ぐ。マージブロッカー可否は severity から決定的に導く（BLOCKER / CRITICAL → はい、MAJOR / MINOR → いいえ。文面ごとに判断しない）。confidence 80 未満または反証メモ付きなら未確定である旨を 1 文添える。**上表で voice=著者 の文面・承認コメント・5 章の例外・2.6 の全面解決の確認文には付けない**（著者視点の文面に付けると相手の指摘を自分がスコアリングして返す形になり 0.2 の敬意と衝突する。全面解決は残存指摘がなく埋める確定値が存在しない）
   - **各文面の末尾に署名 `— Claude Code によるレビュー` を付す**（reply-tone-guide.md 0.1）
   - **著者への配慮を自己点検する**（reply-tone-guide.md 0.6 のチェックリスト全項目: 謝辞 / 敬称 / 判断委譲の余地 / 既存対応への言及 / 人でなくコードへの指摘 / 良い点 1 文 / 署名）。**1 つでも欠けたらドラフトを直してから次へ進む**。適用範囲はメタ行と同じで、**承認コメントと 5 章の例外は対象外**（署名のみ必須。簡潔さが正の文面に謝辞・判断委譲を足すと 2.7 / 5 章の特則を壊す）
   - **未検証主張の断定抑止（over-correction 防止 / GitHub issue #71）**: ドラフトに load-bearing な事実主張を書く場合、typo 級でない限り **断定で書かない**。repo で確認できる主張は `file:line` を、正本 doc で確認できる主張は典拠を添える。repo/正本で裏が取れない外部状態（DB/本番/運用設定）は「要確認（典拠=X）」とし、元の reviewer 指摘が `[unverified: ...]` 付きならその不確実性を返答にも引き継ぐ（確定済みであるかのように書かない）
   - **`writing-polish` で推敲してから提示する（必須 / 未導入時のみ skip）**: 初稿は冗長になりやすく、ユーザーが都度短縮を指示する手間が生じる。**ドラフトを提示する直前に必ず通す**。プラグイン独立性のため未インストール時のみ skip し、従来どおり提示する（dormant・後方互換）。

     1. インストール判定（check-deps.sh と同方式）:
        ```bash
        if grep -q '"writing-polish@' "$HOME/.claude/settings.json" 2>/dev/null; then
          WRITING_POLISH=1
        else
          WRITING_POLISH=0
        fi
        ```
        `WRITING_POLISH=0` → 本ステップを skip。
     2. `WRITING_POLISH=1` のとき、`Skill` tool で `writing-polish:writing-polish` を呼ぶ。`--embed` を必ず付け、`--tone review` を伝え、生成した全ドラフト文面を渡す。
     3. 返ってきた推敲済みテキスト（`POLISH_RESULT_START`〜`POLISH_RESULT_END` マーカー間のみ抽出。サマリ・変更点リストは含めない）を採用する。ただし **reply-tone-guide.md `## 0 必須ルール` を満たすこと**（メタ行 0.5・署名 0.1・謝辞・敬称・判断委譲が推敲で落ちていないか確認する）。満たさない結果は破棄して元案を使う。
     4. fallback: 呼び出しが失敗したら warning を出し、推敲前のドラフトで続行する。

   - **投稿は行わない**。ドラフト出力のみ。ユーザーが GitHub UI で手動投稿する

   出力フォーマット:
   ```
   ## 投稿コメントドラフト（投稿は手動で行ってください）

   ### 承認コメント（PR 全体コメント）
   > レビューしました。大筋問題なく、Approve とさせてください。
   > src/parser.ts:40-58 の境界値テストが手厚く、回帰検知が効きそうです。
   > 細かい点として変数名の統一がありますが、対応は任意で問題ありません（src/api.ts:12）。
   > — Claude Code によるレビュー

   ### @reviewer-a さんの review comment への返答
   対象: src/auth.ts:67-72 の inline スレッド
   パターン: 完全対応（2.1）/ voice: 著者 ※ メタ行なし

   > ご指摘ありがとうございます。
   > src/auth.ts:67 で null チェックを追加しました（{commit-sha}）。
   > 意図と合っているかご確認いただけると助かります。
   > — Claude Code によるレビュー

   ### 指摘 #4 への返答
   対象: src/repo.ts:88 / @author さん
   パターン: レビュアー視点・部分対応（2.6）/ voice: レビュアー ※ メタ行あり

   > **重大度: CRITICAL / 確信度: 85 / マージブロッカー: はい**
   >
   > ご対応ありがとうございます。src/repo.ts:88 の型変換は確認しました。
   > 空文字の draft が数値カラムに素通りする経路が残っていそうです（src/repo.ts:92）。マージ前にご確認いただけますか。
   > — Claude Code によるレビュー
   ```

   {**見出しの付け方が voice で異なる**: レビュアー発信（こちらのレポート由来）は `指摘 #N` ＝ Step 7 レポートの連番をそのまま使う（締めフロー 2 / 3 はこの番号でユーザーに対象を選ばせるため、レポートと一対一でなければならない。例の #4 は Step 7 レポート例の `4. [confidence: 85][severity: CRITICAL]... src/repo.ts:88` と severity / confidence まで一致させている）。著者発信（他者の review comment への返答）は**こちらのレポート由来ではないので指摘番号を振らず**、宛先スレッドで示す}

   生成中に reply-tone-guide.md に明示のないトーン判断が必要になった場合は、ドラフト末尾に `（補足: {判断点} はガイドに明示なし。ユーザー確認推奨）` を添える。

4. **Event Bus publish (`review:completed`)**: 集計結果を `.claude/events.jsonl` に追記する fire-and-forget の publisher。**指摘の精査を行った場合は精査後（post）の確定件数を使う**（取り下げ・降格を反映）。レポートに必要な数値（critical = confidence ≥ 90 件数、warning = 80 ≤ confidence < 90 件数、missing_coverage 配列）は既に手元にあるはず。`SAFE_HOOK_NAME` を `code-review:review` に上書きして event_bus_publish を直接呼ぶ。

   ```bash
   source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh" 2>/dev/null && \
     SAFE_HOOK_NAME="code-review:review" event_bus_publish "review:completed" \
     "{\"pr\":\"<number>\",\"blocker_count\":<n>,\"critical_count\":<n>,\"major_count\":<n>,\"minor_count\":<n>,\"missing_coverage\":[<json-array of focus names>],\"result_grid\":{\"high\":<n>,\"medium\":<n>,\"low\":<n>,\"skip\":<n>,\"error\":<n>},\"adversarial_verify\":{\"confirmed\":<n>,\"refuted\":<n>,\"uncertain\":<n>,\"contested\":<n>},\"recall_skeptic\":{\"attribution_schema\":2,\"surface\":<bool>,\"fired\":<bool>,\"skip_reason\":<string|null>,\"findings_added\":<n>,\"findings_overlap\":<n>}}"
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
   - `recall_skeptic` は冷や読み skeptic（Phase 5.8）の実行記録。skeptic の high 昇格判断（triage-guide.md `## 8.5` の effort ゲート見直し）の計測データになる:
     - `surface`: high-risk surface 判定の結果（bool）。**Phase 5.8 が effort / userConfig でスキップされた場合も、正規表現部分の surface 判定（triage-guide.md `## 8.5`。diff への grep で安価）だけは payload 構築時に必ず実施して記録する**。「surface=true なのに effort ゲートで skeptic が走らなかった頻度」が high 昇格判断の核心メトリクスのため
     - `fired`: skeptic agent が実際に起動したか（bool）
     - `skip_reason`: `fired=false` のときの理由。`"effort"`（xhigh/max 未満）/ `"config"`（`enable_recall_skeptic: false`）/ `"no-surface"` / `"emergency"`（緊急・skip モード）のいずれか。`fired=true` なら `null`
     - `attribution_schema`: 由来帰属の規約バージョン。**常に `2` を入れる**（2 = 由来タグがレポート書式に規定され dedup のタグ生存も定義された版 = 2.35.1 以降）。マーカー無し（schema 1 相当）の旧サンプルは `findings_added` が記憶依存で系統的に 0 へ潰れており判断に使えないため、下流の集計は本フィールドで濾す（triage-guide `## 8.5`）。**日付では切れない** — 配布ラグにより未更新マシンは修正日以降も schema 1 を publish し続けるため
     - `findings_added`: **skeptic 単独由来**（`[recall-skeptic]` タグ。reviewer 指摘と重複しなかった）の指摘のうち報告マトリクスを通過した件数。**「動的ラウンド」行の `実行（N 件追加）` の N と同値**（N はヘッダに置かれ本文より先に出力されるが、**本文確定後に数えてヘッダへ反映する**。二重管理にしない）。**skeptic の価値率の分子はこれのみ**（重複分は下の `findings_overlap` へ。混ぜると重複が常態のため価値率が 100% に張り付き、縮小分岐が原理的に発火しなくなる）
     - `findings_overlap`: **重複 survivor**（`[recall-skeptic:dup]` タグ。reviewer も同じ問題に到達していた）の件数。skeptic が独立に到達した記録として残すが、盲点でなかった事例なので**価値率には算入しない**
     - 両フィールドとも **Step 7 で最初に出力したレポート本文のタグ付き指摘を数えて求める**（Phase 5.8 の記憶から再構成しない。publish は Phase 5.8 から遠く、間に精査・解説・ドラフト生成が挟まるため、記憶依存にすると系統的に 0 へ潰れる）。**計測点は報告マトリクス通過時点（精査の前）＝ Step 7 の初回レポート**であり、精査（締めフロー 1）が再出力する調整後レポートではない。**精査で取り下げた分は減算しない** — 「skeptic が報告に値する指摘を出せたか」を測るフィールドで、必要性で落ちたかは別軸なので混ぜない
   - 失敗してもレポート自体は成功扱い（best-effort）
   - 後方互換: subscriber 側は `critical_count` の存在を仮定して良い（旧 payload との互換性のため必須）。`result_grid` / `adversarial_verify` / `recall_skeptic` は新規フィールド追加なので旧 subscriber 影響なし

5. **ExitWorktree** で worktree から抜ける。
