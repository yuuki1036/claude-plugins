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
  - Write
  - Agent
  - EnterWorktree
  - ExitWorktree
  - AskUserQuestion
  - Skill
---

# Review

<!-- 正本依存（SSoT pin）。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: code-review/references/orchestration-guide.md#3.5 @90899a7e -->
<!-- SSOT: code-review/references/orchestration-measurement.md#16 @d5ab4ea2 -->
<!-- SSOT: code-review/references/scoring-guide.md#報告閾値を割った指摘の記録 @3cf8c3c4 -->

## 前提

- 現在のブランチに PR が存在すること（PR がなければ終了）
- 実行時 effort = `${CLAUDE_EFFORT}` を Phase 3 / 4 の reviewer 構成に反映する（後述の Phase 3 / 4 を参照）
- **effort のつまみは 2 つあり、別物**（GitHub issue #106）:
  - **skill frontmatter の `effort`** — オーケストレーター（メインループ）専用。**reviewer にも動的ラウンドにも効かない**
  - **実行時 `${CLAUDE_EFFORT}`** — reviewer / specialist の effort と、動的ラウンド（meta-reviewer / 冷や読み skeptic / 反証ゲート / Round 2 の段数）の**起動条件を支配する**
  - frontmatter を見て「high 運用のつもり」でいると、セッション effort が xhigh のときに meta-reviewer・skeptic・反証の拡大が全部走ってコストが想定と食い違う。**規模キャップが先に効くケースでは体数が変わらないぶん気づきにくい**（正本: orchestration-guide.md `## 5`）

## コスト×精度パイプライン設計（採用/不採用）

ルート CLAUDE.md「コスト×精度パイプライン設計指針」の 10 原則のうち **採用: 1（ファネル = Phase 0 triage で高コスト reviewer を通過分に絞る）/ 2（2 軸スコア化 = confidence × severity マトリクス）/ 3（段階予算 = `${CLAUDE_EFFORT}` → explorer/reviewer 体数）/ 4（モデルルーティング = explorer:sonnet / reviewer:opus / meta:opus / 反証:opus）/ 7（敵対的独立検証 = Phase 5.9 反証レイヤー、recall 側は Phase 5.8 冷や読み skeptic）**。**捨てた**: 5（暴走ガード）は反復・起票を持たない単発レビューのため不要、6（証拠ラダー）は指摘蓄積・昇格の責務を failure-journal に委ね、8（外部オラクル）は PR diff レビューが対象で型/テスト実行は feature-dev Phase 5.3 の役割と分離した。

## 実行手順

実行フェーズの共通詳細の正本 → Read `${CLAUDE_PLUGIN_ROOT}/references/orchestration-guide.md`（以下「orchestration-guide」）

**分冊されている。必要になった分冊だけをその時点で Read する**（全スキップなら読まない）:

| 分冊 | Read するタイミング |
|---|---|
| `orchestration-dynamic-rounds.md` | 動的ラウンド（Round 2 / meta-reviewer / skeptic / 反証）の**いずれかを実行すると決まったとき** |
| `orchestration-measurement.md` | **publish の直前**（締めフロー 4） |
| `orchestration-optional-flows.md` | Issue 必読 / Vault 照合 / 訂正の伝播前ガード / embed mode の**適用条件を満たしたとき** |

同じく `triage-guide.md` も Phase 0 用の中核だけを持ち、動的ラウンドの起動ゲートは `triage-dynamic-gates.md` にある（**起動可否を判断する段で Read する**）。


### 0. Worktree への移動

**EnterWorktree** ツールで worktree に移動する。作業ブランチを汚さず、レビュー中も並行作業を可能にする。

### 1. PR の取得と前提確認

```bash
# 所要時間計測の開始マーカー t0 を記録（締めフロー 4 の payload で使用）。
# 以降 t1（一括発行の直前）/ wave --explorer（explorer 回収直後）/ wave（agent wave 回収の直後・毎回）/ t2（初回レポート直後）を
# 同じスクリプトで追記する。パス導出・区間の意味の正本: orchestration-measurement.md `## 13.1` `## 14`
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" start --pr <PR番号>

# PR 番号指定時: worktree 内で checkout（作業ブランチに影響なし）。
# **失敗したら中止する** — 開発用 worktree が同じ PR ブランチを保持していると二重チェックアウト
# 禁止で落ちる。続行するとメインコンテキストだけが base branch を読み（子 agent は detach で
# 正しい HEAD に入るため）、規模判定・Phase 0・締めフローが全部 base 基準になる
gh pr checkout <PR番号> || echo "FATAL: PR ブランチを checkout できない（他 worktree が保持中の可能性）"

# PR メタ情報と base branch を取得。headRefOid は子 agent に渡す「期待 HEAD SHA」
# （子は detach で PR head に入るため、検証はブランチ名でなく SHA で行う。issue #98）
gh pr view <PR番号> --json number,title,url,author,state,headRefName,headRefOid,baseRefName,body
```

`gh pr checkout` が失敗した場合、または `headRefOid` が空の場合は **ExitWorktree して中止**する（原因と対処をユーザーに報告）。前者はメインコンテキストが base を読む状態、後者は全 agent が恒常的に HEAD 不一致 warning を出す状態になり、どちらも silent に品質が落ちる（orchestration-guide.md `## 1`）。

PR が存在しない場合は「PR が見つかりません」と報告して **ExitWorktree** で抜けて終了。
スキップ条件: closed、変更なしの PR

**【必須】PR 会話コンテキストの取得**:

以下のスクリプトを **必ず実行** し、出力を **ファイルに保存**する。LLM が個別 `gh` コマンドを組み立てて取得するのは **禁止**（取りこぼし防止のため）。

```bash
# 出力はファイルに落とし、reviewer にはこのパスだけを渡す（本文を N 体ぶんプロンプトへ
# 転記しない。理由の正本: orchestration-guide.md `## 3.5`）。--save は原子的に書いて
# パスを stdout に出す（失敗時は空ファイルを残さず FATAL）
bash "${CLAUDE_PLUGIN_ROOT}/scripts/fetch-pr-context.sh" <PR番号> --save
```

出力された**パスを控える**（以降 reviewer へ渡す。シェル変数は Bash 呼び出し間で消えるので実パスを使う）。

保存後、**メインコンテキストでも 1 回だけ Read する**（Phase 0 のタイプ判定に使うため。以降は reviewer 各自が同じファイルを読む）。スクリプトは PR 説明 / issue コメント / レビューサマリ / 行単位 review コメント（返信チェーン込み）を構造化 markdown で出力する。

`FATAL:` で終了した場合は **ExitWorktree して理由を報告し終了**する（PR コンテキスト無しでは re-flag 判定ができない）。書込のみ失敗した場合（ディスク・権限）は `--save` を外して標準出力に流し直し、**インライン注入にフォールバック**する（レビュー本体はブロックしない）。

**【任意】Issue ファイル必読フロー（issue-workflow 併用時）**:

Step 2 のダイジェスト `## issue-ids` に Issue ID があり、ローカルに Issue ファイルが実在する場合のみ、spec-compliance reviewer の prompt に同梱する（仕様・受入条件を踏まえた判定の精度が上がる。手順・親 Issue の 1 段追跡・スキップ条件: → orchestration-optional-flows.md `## 2`）。

### 2. diff の保存とシグナルダイジェストの取得

**diff 全文をメインコンテキストに載せない。** `triage-signals.sh` が diff をファイルへ保存し、Phase 0 に必要な**事実だけ**を compact に出力する。diff は reviewer / explorer へ**パスで渡す**（本文を転記しない。orchestration-guide.md `## 3.5`）。

**Step 2 と 2.4 は 1 つの Bash 呼び出しにまとめる**（GitHub issue #147）。間に LLM の判断が挟まらない — 後段は前段の**出力を読んで決める**のではなく、同じシェルが書いたファイルを読むだけなので、分けると往復ぶんの `cache_read` を払うだけになる。**Step 1 とは合流させない**（`gh pr checkout` の失敗＝中止経路を挟むため。失敗したまま `triage-signals.sh` を走らせると base branch の diff を掴む）。

```bash
# diff を $DIFF_FILE に保存し、シグナルダイジェストのみ stdout に出す。
# 出力に diff 本体は含まれない（large PR でもメインコンテキストは一定サイズ）
bash "${CLAUDE_PLUGIN_ROOT}/scripts/triage-signals.sh" --pr <PR番号>

# Step 2.4 の重複検出。triage-signals.sh が書いた diff ファイルを読むので**この順序**
bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-recent-review.sh" --pr <PR番号>
```

**`set -e` を張らないこと**（CLAUDE.md Gotchas の ERR trap family。前段が落ちても後段は無害に空で返る）。

出力セクションと使い道:

| セクション | 内容 | 使う場所 |
|---|---|---|
| `## meta` | `diff_file=` / **`agent_ctx_file=`** の**パス**、base ref | 以降の全 agent へ渡す |
| `## size` | `core_files` / `core_lines` / `size_tier` / `md_ratio` / `generated_ratio` / `migration_files` | Stage 0 のモード判定・Stage 2 の規模キャップ |
| `## files` | 変更ファイルの `class`(core/test/doc/gen) × 増減行数 | 担当ファイルの割り当て |
| `## hunks` | core ファイルの `@@` 行（関数コンテキスト付き） | 変更の性質の把握 |
| `## focus-signals` | 観点判定表（triage-guide.md `## 3`）のヒット数と根拠ファイル | Stage 1 のタイプ判定・Step 3.3 の起動前検算 |
| `## red-flags` | specialist 自動起動パターンのヒット | specialist 構成 |
| `## surface` | high-risk surface 判定（`db-write` / `money-numeric` / `authz`） | Step 3.4 の skeptic 相乗り判断 |
| `## explorer-signals` | 共通モジュール変更・500 行超ファイル | explorer の必要性判定 |
| `## agents-md` | 変更ファイル階層でヒットした AGENTS.md / CLAUDE.md のパス | Step 4.9（reviewer へパス渡し） |
| `## issue-ids` | branch 名から抽出した Issue ID | Issue ファイル必読フロー |

**`size_tier` はスクリプトが triage-guide.md `## 6.2` の帯定義を機械適用した値**をそのまま使う（core = lock・生成物・テスト・doc を除いた実質規模。テスト 5 + doc 1 を含む 9 ファイルの PR が実質 3 ファイル `+22 -13` なのに large 扱いで 17 体起動する事故を防ぐ。GitHub issue #96）。Phase 0 の構成テーブル・Step 7 レポート冒頭・締めフロー 4 の `size_tier` に記録する。

**シグナルは事実であって判定ではない。** モード決定・観点採否・体数は triage-guide が決める（スクリプトは policy を持たない）。ヒット数 0 の観点は出力に現れない＝条件不成立、と読む。

**`diff_file=` と `agent_ctx_file=` の値は以降ずっと使うので、パス文字列そのものを控えておく**（後者は Step 5 の共通ブロック書き出し先。**slug は不透明な cksum 値なので、控え損ねると復元できない**）（シェル変数は Bash 呼び出し間で消えるため、`$DIFF_FILE` として引き回さず実パスを毎回書く）。

**ダイジェストで判断が付かない場合のみ** `diff-slice.sh` で必要なファイルの diff だけを読む（全文 Read はしない）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/diff-slice.sh" "<diff_file の実パス>" path/to/file.ts
```

**その他のコンテキスト収集:**
- PR 会話データ（Step 1 の fetch-pr-context.sh 出力をそのまま使用）
- `.claude/session-context.md` の存在確認（存在する場合、frontmatter の `branch` と現在のブランチ名を比較。一致すれば有効）
- Issue/knowledge ファイルの探索（`## issue-ids` を起点にする）
- プロジェクト特性シグナル（`package.json` の `react` / `next` 有無 = triage-guide.md `## 3` の React/Next.js 判定）

**スクリプトが失敗した場合**（`FATAL:` で終了）は従来どおり `gh pr diff <PR番号> --name-only` と `--stat` でファイル一覧と規模を取り、triage-guide.md `## 6.4` のフォールバック構成に落とす。**diff 全文の Read はこの経路でも行わない**。

### 2.4. 直近レビューとの重複検出（skill 跨ぎ / 常時実行・agent なし）

**実行は Step 2 の Bash 呼び出しに同梱済み**（#147）。ここは出力の解釈だけを行う。

**出力が空なら何も報告せず Step 2.5 へ**。`## recent-review` が出た場合のみ **AskUserQuestion** で続行可否を確認する（question:「同一の diff が直近にレビュー済みです（<plugin> / <日時> / 報告 <件数>）。このままレビューを続けますか？」/ header:「重複レビュー」/ options: ①label「続行する」description「別観点・別 effort で見直す価値があると判断した場合」 ②label「中止する」description「前回のレポートで足りる。agent を 1 体も起動せず終了する」）。**「中止する」なら ExitWorktree して終了**（Phase 0 に進まない）。突合キーの性質と背景: → orchestration-measurement.md `## 19`

### 2.5. PR コンテキストの扱い

Step 1 が保存した `$PR_CTX_FILE` を PR コンテキストの**唯一の原本**として扱う（LLM による再構築・要約・編集は **禁止**：再現性と取りこぼし防止のため）。

- **Phase 0 のタイプ判定**: メインコンテキストが Step 1 で Read した内容を使う
- **reviewer への引き渡し**: 本文を転記せず**パスのみ**注入し、agent 自身に Read させる（バイト同一が保証され、転記リスクがゼロになる。orchestration-guide.md `## 3.5`）

スクリプト出力の構造（参考）: → design-notes/pr-context-format.md `## 3`

### 3. Phase 0: トリアージ

`${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` を Read で読み込み、そのロジックに従ってエージェント構成を決定する。

**Phase 0 はメインコンテキストで実行する（Agent ツールは使わない）。**

#### 3.0 Stage 0: PR 種別分岐（先行判定）

**緊急モード先行判定**: 引数に `--emergency` が含まれる場合、triage-guide.md `## 2.5` の「緊急レビューモード」に従い最小構成（reviewer-bugs + reviewer-security のみ、explorer / 冗長ペア / Phase 5.5〜5.9 をスキップ）を採用する。この判定は以下の PR 種別分岐より優先する。decided したモードは `emergency` として Step 3.3 / Step 7 に記録し、Step 7 レポート冒頭に必須バナーを出す。

triage-guide.md `## 2.5 PR 種別分岐ルール` を **Stage 1 より先に** 適用する。Step 2 のダイジェスト（`## files` の class 内訳と `## size` の `md_ratio` / `generated_ratio` / `migration_files`）からモード（`doc-review-mode` / `dba-mode` / `supply-chain-mode` / `skip-mode` / `default-mode`）を判定し、`default-mode` 以外の場合は推奨 agent 構成を Stage 2 の上限・最小保証より優先して採用する（GitHub issue #43）。

決定したモードと根拠は Step 3.3 の構成テーブルおよび Step 7 のレポート冒頭に必ず含める。

#### 3.1 Stage 1: タイプ判定

diff の特性を分析し、必要なエージェントタイプを判定する:
- **explorer**: 巨大ファイル、複数関数、条件分岐追加、共通モジュール変更のいずれかに該当するか
- **reviewer**: 常に必要。diff パターンマッチでどの観点が必要かを判定
- **spec-compliance**: session-context / Issue / knowledge が存在するか

Step 1 で Read した PR コンテキスト（説明・issue コメント・レビューサマリ・行単位コメント）もタイプ判定の参考にする（例: 説明に「セキュリティ修正」、行単位コメントで認可周りが議論されている → security reviewer を追加）。

#### 3.2 Stage 2: 体数・フォーカス・冗長度決定

各タイプの体数と各エージェントの具体的なフォーカスを決定する:
- explorer: 独立した探索対象の数に比例
- reviewer: 必要な観点数 × 対象コードの複雑さに応じた冗長度
- 冗長ペアには異なる angle（分析の切り口）を割り当てる（実起動は xhigh/max のみ。下記）
- 最小保証: reviewer-bugs + reviewer-claude-md の 2 体は常に起動

**実効上限 = min(effort 上限, 規模キャップ)**（体数の正本: triage-guide.md `## 7` / `## 6.2`）。**2 系統を必ず両方適用する**（effort 上限だけを見ると、小 PR に上限いっぱいの体数が張り付いて所要時間が数倍に膨らむ。GitHub issue #96 の実測は core 3 ファイル `+22 -13` の PR に 17 体 / 130 分）。

第 1 系統 — **effort 上限**（現在の effort = `${CLAUDE_EFFORT}`）:
- `low` / `medium`: explorer 2 体、reviewer 4 体、specialist 3 体（束ね起動）（最小保証は維持）。深掘りより速度優先
- `high`（既定）: explorer 4 体、reviewer 6 体、specialist 3 体（束ね起動）。**冗長ペアは組まない**（ペア条件成立時は Angle A/B を 1 体に内挿）。上限を超える観点数は近接観点のバンドルで可能な限り吸収し、それでも収まらない観点は `missing_coverage` に必ず記録する（容量の算式は triage-guide.md `## 7`。脱落を silent にしない）
- `xhigh` / `max`: explorer 6 体、reviewer 10 体、specialist 6 体を full に使い、冗長ペアを積極投入

第 2 系統 — **規模キャップ**（Step 2 で数えた core 規模。triage-guide.md `## 6`）:
- small（core ≤ 3 ファイル かつ ≤ 100 行）: explorer 0 / reviewer 3 / specialist 1
- medium（core 4-10 ファイル または 101-500 行）: explorer 2 / reviewer 5 / specialist 2
- large: キャップなし（effort 上限がそのまま実効上限）
- **最小保証の 2 体は規模キャップより優先**。キャップに収まらない観点は `missing_coverage` に識別子 `<focus>` として記録する（**規模キャップで落ちた旨はレポートの「⚠️ 欠損観点」へ** — payload は識別子のみ）
- **規模キャップが effort 上限を下回った場合、Round 2（Step 5.5）は effort に関わらず 1 段圧縮経路**（追加 explorer なし）を使う。一方 **reviewer 個々の effort・meta-reviewer・skeptic・反証レイヤーは削らない**（規模キャップが削るのは breadth のみ。triage-guide.md `## 6.3`）

#### 3.3 観点カバレッジ検算と構成テーブル出力

**構成テーブルを確定する前に、起動前検算を実施する（orchestration-guide `### 8a`・default-mode のみ構成追加）**: 観点判定表の各条件を diff シグナルに対して再評価し、条件を満たすのに構成に入っていない focus があれば構成テーブルに追加（またはバンドルで相乗り）してから確定する。v2.39.0 で旧 Phase 5.7 の補完起動から前倒し（起動後の直列 wave を無くすため。検算内容は同一）。

**モード除外**: Stage 0 で `default-mode` 以外（`--emergency` / `doc-review-mode` / `dba-mode` / `supply-chain-mode` / `skip-mode`）に確定した場合、モードの推奨構成が観点判定表より優先するため**検算による構成追加は行わない**。検出した focus は `missing_coverage` に識別子 `<focus>` のみ記録する（**mode による意図的縮退である旨はレポート本文へ**）。

検算後、triage-guide.md の出力フォーマット（`## 5`）に従い、エージェント構成テーブルを出力する。**「直列 wave」行を必ず含める**（見積もり方は triage-guide.md `## 5.1`）— 体数はトークンコストのレバー、wave 数は壁時計のレバーで、後者だけが従来ユーザーから見えなかった（GitHub issue #100 B）。

#### 3.4 high-risk surface 判定（冷や読み skeptic の相乗り判断 / 常時実行）

Phase 0 の最後に high-risk surface 判定を **必ず実施** する（安価なので構成に関わらず常に行う。silent skip 防止・issue #85）。**判定は Step 2 のダイジェスト `## surface` をそのまま読み、この判定のために triage-dynamic-gates.md を Read しない**（v2.60.0。分冊の Read は diff サイズと無関係な固定費で、小 PR では支配的になる）。ダイジェストに当該セクションが無い場合のみ定義の正本として `triage-dynamic-gates.md ## 8.5` を読む。**PR 自己申告 D1-High はダイジェストに含まれない**ので、Step 1 で Read 済みの PR コンテキスト（本文・ラベルの高リスク申告）から判定し、正規表現ヒットと **OR** で結合する。

- surface=true **かつ Phase 5.8 のスキップ条件（userConfig / effort / `--emergency`・`skip-mode`）のいずれにも該当しない**場合、skeptic を **Step 5 の reviewer 一括発行に相乗りさせる**（同一メッセージ内で発火。1 wave 削減）。**条件は個別に列挙せず Phase 5.8 の定義を参照すること** — 相乗りで起動が前倒しされる以上、5.8 に到達してからスキップ判定しても手遅れ（agent は既に走っている）。列挙の取りこぼしは `--emergency` で `effort: max` の skeptic が余計に走る事故に直結する
- surface=true だがスキップ条件に該当する場合は、`skip_reason` を記録して Step 7 レポートと payload に出す（従来どおり）
- reviewer の `[surface:high-risk]` フラグ由来で事後に surface=true になる経路は Phase 5.8 の fallback で拾う

### 4. 探索フェーズ（explorer 並列起動）

Phase 0 が explorer を 1 体以上配置した場合のみ実行。explorer が不要と判断された場合はスキップして Step 5 へ。

**プロンプトテンプレートは Read しない。パスを渡して agent 自身に読ませる**（組み立て方の正本: `${CLAUDE_PLUGIN_ROOT}/references/explorer-prompts.md`。本文の転記は体数ぶんの複製になる — orchestration-guide.md `## 3.5`）。

Phase 0 の構成テーブルに従い、各 explorer を `model: sonnet` で並列起動する:
- プロンプト冒頭で **`prompts/explorer-common.md` と `prompts/explorer/<focus>.md` の 2 パスを Read せよ**と指示する（本文は書かない）
- 可変部として Phase 0 が決定した focus・対象ファイル・関数、および **Step 2 の `$DIFF_FILE` のパスと担当ファイル名**を渡す（`diff-slice.sh` で自分の担当ぶんを切り出せることも明記する）
- 全エージェントを `isolation: "worktree"` で起動する（PR ブランチの状態でファイルを読むため）
- 全エージェントに `run_in_background: false` を明示し、**全 explorer の Agent call を同一メッセージ内で一括発行する**（orchestration-guide.md `## 0`。`run_in_background` 省略は取りこぼし、1 体ずつ別メッセージ発行は逐次実行＝実時間が合計に膨らむ。2 つは独立の要件）
- **PR 番号・期待 HEAD SHA・`{{MAIN_ROOT}}` 注入（必須）**: orchestration-guide.md `## 1` / `## 1.1` に従う（前者を欠かすと偽陽性を量産 #56 / #98、後者を欠かすと依存を読めず「検証不能」の誤申告で wave を 1 本失う #113）

一括発行の**直前**に fleet 区間の開始マーカーを記録する（**agent wave はすべて fleet 側に入れる**。explorer を triage 区間に含めると `duration_triage_min` が「メイン思考の代理指標」でなくなる。orchestration-measurement.md `## 14`）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark t1 --pr <PR番号>
```

全 explorer の完了を待ち、結果を収集する。**回収した直後**に explorer wave の終了マーカーを記録し（`t1`→ explorer 打点 = explorer wave の実時間。orchestration-measurement.md `## 14`。`TS_FILE` は Step 1 と同じ導出式）、各 explorer の `#### 確定事実` 欄を集約して **合計 10 行以内**にまとめておく（Step 5 で全 reviewer に注入する枠。無ければ no-op）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark wave --explorer --pr <PR番号>   # 複数メッセージに分けてしまった場合も wave ごとに毎回打つ（行数が agents.explorer_waves になる・#122）
```

**HEAD 検証の回収（必須）・部分失敗耐性**: orchestration-guide.md `## 5` に従う（各出力の `HEAD 検証:` 行を読み、不在・不一致は `missing_coverage` に記録して依存 reviewer に明示。個別失敗でも全体は中止しない）。

### 4.9 AGENTS.md 階層動的選択（reviewer 起動前）

Step 2 のダイジェスト `## agents-md` に出ている**パス一覧**を reviewer プロンプトに渡し、agent 自身に Read させる（本文の転記はしない — 既にディスク上にあるので体数ぶんの複製がそのまま消える。orchestration-guide.md `## 3.5`）。ヒットが 0 件なら no-op（AGENTS.md が無いリポジトリでは後方互換）。

注入セクション名・探索ロジックの詳細: → orchestration-guide.md `## 4`

### 5. レビューフェーズ（reviewer 並列起動）

**プロンプトテンプレートは Read しない。パスを渡して agent 自身に読ませる**（組み立て方の正本: `${CLAUDE_PLUGIN_ROOT}/references/reviewer-prompts.md`。共通指示だけで約 7.3k tokens あり、体数ぶん転記すると出力トークンが `(N-1) × 本文長` 膨らむ — orchestration-guide.md `## 3.5`）。

Phase 0 の構成テーブルに従い、各 reviewer を `model: opus` で並列起動する。effort は実行時 `${CLAUDE_EFFORT}` に連動させる（low/medium/high（既定）→ `high`、xhigh/max → `xhigh`。設計意図は orchestration-guide.md `## 5`）。**userConfig `reviewer_effort_profile` が `differentiated` のときは high 帯に限り低密度観点の reviewer を `medium` で起動する**（高密度観点・specialist・最小保証 2 体は `high` 維持。xhigh/max は無視。マップの正本は triage-guide.md `## 7.1`。A/B 実験フラグで既定 `uniform` は現行どおり）。プロンプトは **Read させるパスの列挙 + 可変部**だけで構成する:

- **必ず Read させる**: `prompts/reviewer-common.md` と `prompts/focus/<focus>.md`。review では `prompts/pr-context-rules.md` も常に加える。条件付きで加えるもの:
  - 観点バンドル時 → `prompts/bundle-rules.md` と束ねる focus ファイル群
  - **ペア条件が成立したとき → `prompts/angles.md`**（xhigh/max の実ペアだけでなく、**high 以下の angle 内挿でも渡す**。渡さないと「ペアを削った代償を angle で補う」という縮小の前提が空振りする）
  - セッションコンテキストが有効なとき → `prompts/session-context.md`（confidence −30 の規約はここにある。パスだけ渡しても規約は届かない）
- **`prompts/focus/comment-polish.md` は Read 対象に入れない**（self-review 限定。他人の PR に文面の推敲を投稿するのは越権になりやすい）
- **可変部の共通ブロック（全 agent 共通の実値集合）は 1 ファイルに落としてパス渡しする**: Step 2 の `## meta` が出す `agent_ctx_file=` のパスに **Write で 1 回だけ**書き出し、各プロンプトには「まず `<agent_ctx_file>` を Read せよ」の 1 行だけを置く。**入れる項目・残す項目・フォールバックの正本は orchestration-guide.md `## 3.5`「可変部の共通ブロックに入れるもの」**（`{{PLUGIN_ROOT}}` / PR 番号 / `{{HEAD_SHA}}` / `{{MAIN_ROOT}}` / `{{SEVERITY_THRESHOLD}}` / `$DIFF_FILE` / `$PR_CTX_FILE` / AGENTS.md パス / 確定事実 など。実測で reviewer 5 + skeptic 1 + meta 1 + 反証 3 の計 10 本に手書きしていた — #124 (c)）
- **プロンプト側に残す可変部**: 担当 focus（冗長ペアなら angle）と担当ファイル、**explorer 結果の選択的注入**（構成テーブルの「explorer 依存」列。複製係数がほぼ 1 なのでインラインのまま）
- **確定事実は共通ブロックに入れず、reviewer にだけインライン注入する**: Step 4 でまとめた `## 確定事実（explorer 共通・裏取り済み）` を**全 reviewer（specialist・skeptic を除く）**に合計 10 行以内で注入する。**skeptic に渡すと findings 非注入という層の設計核が壊れる**（triage-dynamic-gates.md `## 8.5`）。扱いの規約は `prompts/reviewer-common.md` 側（#122）
- 全エージェントを `isolation: "worktree"` で起動する
- 全エージェントに `run_in_background: false` を明示し、**全 reviewer の Agent call を同一メッセージ内で一括発行する**（orchestration-guide.md `## 0` 並列発行の明示。1 体ずつ別メッセージで発行するとフェーズ実時間が相内最長でなく合計になる）
- **冷や読み skeptic の相乗り**: Step 3.4 で surface=true かつ Phase 5.8 のゲートを通過している場合、skeptic 1 体（`model: opus`, `effort: max`、プロンプトは `prompts/recall-skeptic.md` をパス渡し）を **この一括発行に含める**。skeptic は findings 非注入が設計の核で reviewer 出力に依存しないため、直列に置く理由がない（triage-dynamic-gates.md `## 8.5` 起動タイミング）。結果の統合は Phase 5.8 で行う
- **PR 番号・期待 HEAD SHA・`{{MAIN_ROOT}}`・`{{SEVERITY_THRESHOLD}}` は共通ブロックに含める（必須）**: 値の意味と欠落時の影響は orchestration-guide.md `## 1` / `## 1.1` / `## 2`（MAIN_ROOT を欠かすと「検証不能」の誤申告で wave を 1 本失う #113、SEVERITY_THRESHOLD を欠かすと閾値未満を書かせて捨てる #117）。**プロンプトに再掲しない**

一括発行の**直前**に fleet 区間の開始マーカーを記録する（orchestration-measurement.md `## 14`。`TS_FILE` は Step 1 と同じ導出式で決める。Step 4 で explorer を起動していれば記録済みなので `grep` ガードで二重記録を防ぐ。`||` 形なのでガードが偽でもブロックは成功終了する）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark t1 --pr <PR番号>
```

全 reviewer の完了を待ち、結果を収集する。**回収した直後**に `bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark wave --pr <PR番号>` を実行する（打点→`t2` = agent 非稼働が保証される synthesis 区間。**動的ラウンドの各回収点でも毎回繰り返す** — 後勝ちなので最後の wave を判断しなくてよい。orchestration-measurement.md `## 14`）。

**HEAD 検証の回収（必須）**: 各出力の `HEAD 検証:` 行を読み、不在・不一致なら `missing_coverage` に記録して当該 reviewer の指摘全件に `[unverified: HEAD 不一致]` を付ける。件数は締めフロー 4 の `head_verified` へ（手順の正本: orchestration-guide.md `## 5`）。

reviewer 起動の共通詳細（effort 設計意図・diff-first 原則・出力形式の検証と auto-retry・部分失敗耐性・最小保証の閾値）: → orchestration-guide.md `## 5`

**最小保証の閾値のみ抜粋**: Phase 0 の最小保証（reviewer-bugs と reviewer-claude-md）が **両方とも失敗** した場合のみレビュー中止とし、ユーザーに再実行を促してから ExitWorktree する。それ以外は欠損観点を明示しつつ Step 6 に進む。

### 5.5 Adaptive deepening: Round 2（unmet_information 起点 / 動的）

**スキップ条件**（いずれか満たせばこのフェーズ全体をスキップして Step 5.8 の skeptic 統合へ）:
- userConfig `enable_adaptive_rounds` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `low` または `medium`
- 全 reviewer の出力に `## unmet_information` セクションが 1 件もない
- **unmet の target が全件「到達不能」**（DB / 本番の実データ、このリポジトリに存在しないコード、意図的にスキップした lint / テスト実走など）で、追加探索が構造的に空振りする場合。分類表と「1 件でも到達可能なら起動する」根拠は triage-dynamic-gates.md `## 8`（GitHub issue #100 C）。スキップ時は `missing_coverage` に識別子 `round2` を記録し（**理由はレポート本文へ**）、レポートの「動的ラウンド」行にも出す。**⚠️ 「repo 外」≠「到達不能」（v2.60.0）** — 外部サービスの実挙動でも**その MCP / CLI がセッションで使えるなら到達可能**で、Round 2 の前に**メインで直接照会して解決してよい**（read-only）

**実行する場合**: **Read** `orchestration-dynamic-rounds.md` してその `## 6` の手順に従う（unmet_information 集約 → **high は 1 段圧縮**: 追加 explorer なしで該当 reviewer 最大 3 体を再起動し unmet ターゲットを自力探索させる / **xhigh・max は 2 段**: 追加 explorer 最大 3 体 → 該当 reviewer 再起動 → 初回出力を置換。失敗時は初回結果のまま続行の best-effort）。**回収した直後に `mark wave` を記録する**（Step 5 と同じ呼び出し。後勝ち。**追加 explorer を起動した場合も `--explorer` は付けない** — `agents.explorer_waves` は「初回 explorer の一括発行が守られたか」の指標で、Round 2 の追加 explorer を混ぜると規約どおりの起動が「一括発行違反」として誤検知される）。レポートに「Round 2 trigger: <reason>」を記録（Step 7 で出力）。

### 5.6 Meta-reviewer ラウンド（v2.12.0 / 動的・**5.9 反証と同一 wave**。実行順は `5.5 → 5.8 の skeptic 統合 → 5.6 meta + 5.9 反証を同一メッセージで一括発行 → mark wave → [meta 由来の追加反証バッチ] → 5.7 → Step 6`。両者は互いの出力に依存しないので直列に置かない / **片方がスキップでも他方はそのまま発行する** / #122）

**スキップ条件**（いずれか満たせばスキップし、同一 wave の 5.9 だけを発行する）:
- userConfig `enable_meta_reviewer` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `xhigh` または `max` **でない**
- **severity 側の起動条件を満たさない**（`skip_reason: "no-high-severity"` / `gate_schema: 3`）。起動条件は「Step 5.5 後の全指摘（フィルタリング前）に **BLOCKER** が 1 件以上」∨「**CRITICAL** が 1 件以上」∨「**報告マトリクス通過見込みの MAJOR が 3 件以上**」。MAJOR 経路は v2.62.0 で追加した（旧ゲートは高 severity の存在だけを条件にしていたため実測 14 件中 `fired=1` とほぼ常時不発だった / GitHub issue #123 C）
- **`size_tier` が `small` かつ BLOCKER が 1 件もない**（v2.60.0 / `skip_reason: "size-tier"`。BLOCKER があれば帯に関わらず起動する。**規模帯に連動する唯一の例外**で triage-guide.md `## 6.3`、根拠が n=1 のため**ロールバック条件つきの暫定ゲート** → `design-notes/triage-rationale.md`）

**実行する場合**: **Read** `orchestration-dynamic-rounds.md` してその `## 7` の手順に従う（meta-reviewer を 1 体 `model: opus`, `effort: max` で **Step 5.9 の反証バッチと同一メッセージ内で**起動 → 追加指摘を dedup して統合。失敗時は missing_coverage に追記して続行）。**回収した直後に `mark wave` を記録する**（Step 5 と同じ呼び出し。後勝ち。反証と同一 wave なので打点は 1 回で足りる）。

### 5.7 観点カバレッジ・事後突合（メインコンテキスト / 常時実行・agent 追加起動なし）

Step 6 の直前に、**メインコンテキストで**（Agent は使わない・低コスト）Step 3.3 の起動前検算で確定した構成テーブルと実際に起動・完走した focus を突合し、差分を `missing_coverage` に追記する（orchestration-guide `### 8b`）。観点漏れの検出は Step 3.3 の起動前検算（`### 8a`）へ前倒し済みのため、**本フェーズで agent は追加起動しない**（v2.39.0。issue #69 の常時検査の意図は 8a で維持）。

**スキップ条件**: `--emergency`（緊急モード）または `skip-mode`（生成物 PR）では構成が意図的に最小化されているため本チェックをスキップする。

### 5.8 冷や読み skeptic ラウンド（recall 補強 / 動的）

reviewer wave への相乗りで起動し、5.6 + 5.9 の一括発行より前に統合する。**high-risk surface を含む変更に限り**、他 reviewer の findings も推論も渡さない独立 skeptic を 1 体起動し、fleet 共通の盲点（層跨ぎ値フロー等）を冷や読みで探す（`${CLAUDE_PLUGIN_ROOT}/references/triage-dynamic-gates.md` `## 8.5 冷や読み skeptic ラウンド`）。反証レイヤー(5.9)が偽陽性を潰す係なのに対し、本フェーズは見落とし（false negative）を独立読み直しで足す係。meta-reviewer(5.6)が findings 注入で非独立なため fleet 共通盲点を引きずるのを、独立性で補う。

**スキップ条件**（いずれか満たせばスキップして 5.6 + 5.9 の一括発行へ）:
- userConfig `enable_recall_skeptic` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `low` または `medium`（**high は起動する**。v2.52.0 で昇格 — surface=true の 63% が effort ゲートで未起動だった一方、起動できた回の 50% が fleet 共通盲点を実際に破っていた。根拠: `design-notes/triage-rationale.md`）
- `--emergency`（緊急モード）または `skip-mode`（生成物 PR）
- high-risk surface（triage-dynamic-gates.md `## 8.5` の surface 判定）を含まない

**スキップ時も surface 判定は必ず実施（silent skip 防止・issue #85）**: 上記スキップ条件（effort / config / emergency）に該当して skeptic agent を起動しない場合でも、surface 判定（triage-dynamic-gates.md `## 8.5` の正規表現。diff への grep で安価）だけは Phase 0 の構成判断（縮退構成・小 diff）と **独立に必ず実施** する。surface=true なら skeptic 未起動の事実と skip_reason（`effort` / `config` / `emergency`）を Step 7 レポートの「動的ラウンド」行に必ず出す（`review:completed` payload の `recall_skeptic` 記録と対を成す human レポート契約）。

**実行する場合**: **Read** `orchestration-dynamic-rounds.md` してその `## 9` の手順に従う。**起動は Step 5 の reviewer 一括発行に相乗り済み**（Step 3.4 で surface 判定・ゲート通過を確認している）なので、本フェーズで行うのは **結果の統合**（`[recall-skeptic]` / `[recall-skeptic:dup]` タグ付き指摘を dedup して統合し、反証レイヤー(5.9)の対象にも含める）。**この統合は 5.6 + 5.9 の同一 wave 発行より前に済ませる**（skeptic の指摘を反証対象に含めるため。統合はメインコンテキストの作業で agent を要さない）。

**fallback（直列起動）**: reviewer の `[surface:high-risk]` フラグ由来で**ここで初めて** surface=true になった場合のみ、skeptic を 1 体 `model: opus`, `effort: max` で単独起動する（**findings / reviewer の推論は渡さない**のが独立性の核）。正規表現・PR 自己申告で事前に HIT していれば相乗り済みなのでこの経路は走らない。**この経路で起動した場合は回収した直後に `mark wave` を記録する**。

**失敗時 / スキップ時**: skeptic の失敗は `missing_coverage` に追記して続行。**起動条件（high-risk surface）を満たしたのに未実行だった事実は、失敗・effort/config/emergency スキップのいずれでも Step 7 レポートに必ず出す**（silent skip で「守ったつもり」の偽の安心を防ぐ）。

### 5.9 反証レイヤー（adversarial verification / 動的・**meta-reviewer(5.6) と同一 wave**）

冷や読み skeptic の統合後・スコアリングの前に、reviewer の指摘を独立エージェントが反証する。偽陽性を人間が詰める前に先回りして摘出するフェーズ（`${CLAUDE_PLUGIN_ROOT}/references/triage-dynamic-gates.md` `## 9 反証レイヤー`）。meta-reviewer (5.6) / skeptic (5.8) が見落とし（false negative）を足す係なのに対し、本フェーズは独立読み直しで **severity を較正し偽陽性を摘出する**鏡像（実測は較正が主機能: `severity_inflated` 60% / `refuted` 6%。#114）。skeptic が足した指摘も本レイヤーの対象。

**スキップ条件**（いずれか満たせばスキップし、同一 wave の 5.6 だけを発行する）。**発火は起動有無にかかわらず payload（`fired` + 括弧内の `skip_reason`。起動時は `null`）と Step 7 レポートに記録する。4 つ目を他と同じ値に潰さないこと** — 既定 high では BLOCKER / CRITICAL が 0 件なら対象が構造的に 0 件になるため、潰すと「ゲートが狭いのか対象が無かったのか」を事後に切り分けられない（→ triage-dynamic-gates.md `## 9` / issue #129）:
- userConfig `enable_adversarial_verify` が `false`（`"config"`）
- 実行時 effort = `${CLAUDE_EFFORT}` が `low` または `medium`（`"effort"`）
- `--emergency`（緊急モード）または `skip-mode`（生成物 PR）（`"emergency"`）
- 反証対象（triage-dynamic-gates.md `## 9` のゲート）に合致する指摘が 0 件（**`"no-eligible-findings"`**）

**実行する場合**: **Read** `orchestration-dynamic-rounds.md` してその `## 10` の手順に従う（triage-dynamic-gates.md `## 9` の選定ルールで対象を選び、**5 件ずつのバッチ**に分けて反証エージェントを `model: opus`, `effort: high` で並列起動（上限 3 体）。**この一括発行に Step 5.6 の meta-reviewer を含める**（同一 wave）。**reviewer の理由文は渡さない**＝アンカリング防止 → verdict を finding_id で突合して Step 6 のスコアリングに渡す。失敗した指摘は verdict なしのまま続行の best-effort）。**回収した直後に `mark wave` を記録する**（Step 5 と同じ呼び出し。後勝ち。既定 effort ではこのフェーズが最後の agent wave になるため、ここを落とすと `duration_synthesis_min` が反証 wave を丸ごと含む）。レポートに「反証: 対象 N 件 / 係争 M 件 / 取り下げ K 件」を記録（Step 7 で出力）。 **meta 由来指摘の追加バッチ**（`[meta]` タグ付きが反証ゲートに該当する場合のみ 1 体・上限 5 件を直列起動。0 件なら wave は増えない。`## 10` 手順 3.5）を起動したときは、回収直後に再度 `mark wave` を記録する。

### 6. スコアリングとフィルタリング（2軸: confidence × severity）

全 reviewer の指摘を統合し、`${CLAUDE_PLUGIN_ROOT}/references/scoring-guide.md` を Read で読み込んでスコアリングを実施する。

1. **各指摘の base confidence と severity を取得**
   - reviewer 出力の `[confidence: XX]` と `[severity: BLOCKER|CRITICAL|MAJOR|MINOR]` をパース
   - severity が欠落している指摘は **CRITICAL とみなす**（後方互換 / 安全側デフォルト）
   - **この時点の severity 別件数を控える**（= `pre_adjust_counts`。統合・dedup 後、手順 2 以降の verdict 反映・加減算・降格・フィルタを**一切かける前**の生の分布）。締めフロー 4 の publish で使う。**手順 5 通過後の件数との差が「調整で消えた分」**であり、これが無いと「reviewer が検出しなかった」と「検出したが調整で消えた」を事後に区別できない（orchestration-measurement.md `## 16`）
   - **base 検算は `pre_adjust_counts` を控えた後に行う**（降格が「調整で消えた分」として会計されるため）。`退行` / 「変更前は X だった」を根拠にする指摘は `git show <base>:<path>` で base 側を検算する（orchestration-guide.md `## 5`「origin 主張の base 検算」。**冷や読み skeptic は reviewer 側の base 確認規約を継承しない**ため、この層の主張が主対象。反証レイヤーは effort ≥ high でしか走らないので、この検算だけが effort 非依存 / #124 (d)）
2. **反証 verdict の反映**（Phase 5.9 が動いた場合のみ。scoring-guide.md `## 反証レイヤーの verdict 反映` に従う）
   - **BLOCKER / CRITICAL の `refuted` は confidence / severity を据え置き**、指摘本文先頭に `⚠️ 反証メモ: <軸>（<根拠 file:line>、要確認）` を付与（**報告から消さない**）
   - **MAJOR / MINOR の `refuted`** は confidence −40（取り下げ理由を付録に記録）
   - `confirmed` は既存「複数エージェント +15」の発火源（二重計上しない）、`uncertain` は −10
   - verdict が無い指摘（対象外・反証失敗）は no-op
3. **confidence への加算・減算ルールを適用**
   - PR コンテキストタグ（`[re-flag: ...]` / `[resolved: ...]` / `[intent-conflict]` / `[scope:out]`）の加減算
   - 複数エージェント検出 / explorer 裏付け / セッションコンテキスト等の加減算
   - 最終 confidence を 0-100 にクランプ
4. **severity 調整**: `[scope:out]` / `[resolved: ...]` タグ付きは severity を 1 段階下げる（反証 `severity-inflated` もこのルールに統合。二重降格しない）。**BLOCKER / CRITICAL の `severity-inflated` は降格後に報告マトリクスを割る場合のみ据え置き + 反証メモ**（scoring-guide の不変条件。高 severity を silent に消さない）。**MAJOR / MINOR が `severity-inflated` の降格で報告閾値を割って脱落する場合は、`refuted` の −40 脱落と同じく 🔁 付録に取り下げ理由を記録する**（scoring-guide.md `## 反証レイヤーの verdict 反映` / issue #109。降格で消える指摘が silent に落ちない）
4.5. **加減算で報告閾値を割った指摘を控える**（issue #128）: 手順 3〜4 の減算・クランプ・降格の結果、手順 5 の報告マトリクスを通過しなくなる指摘は、**severity を問わず** 🔁 付録に「調整前の (severity, confidence) / 適用した規則名 / 遷移後の値」を記録する。反証由来の脱落（手順 2）と同じ枠に、経路が分かる形で並べる。正本: scoring-guide.md `## 報告閾値を割った指摘の記録`
5. **報告マトリクスでフィルタ**:

   | severity \ confidence | <60 | 60-79 | 80-94 | 95+ |
   |---|:---:|:---:|:---:|:---:|
   | BLOCKER | skip | 報告 | 報告 | 報告 |
   | CRITICAL | skip | skip | 報告 | 報告 |
   | MAJOR | skip | skip | skip | 報告 |
   | MINOR | skip | skip | skip | 報告 |

6. **userConfig 適用**: `review_severity_threshold` (default: `MAJOR`) より低い severity は除外。**`pre_adjust_counts` には各 reviewer の `## below-threshold` の件数を同名 severity のバケツへ足し、`severity_threshold` を併せて記録する**（足し込む分は dedup されないため版で非可換。版マーカー `schema` は**スクリプトが注入する**ので書かない。orchestration-measurement.md `## 16`）。**足し込んだその件数を `below_threshold_counts` にも同じバケツで再掲し、`## below-threshold` の `demoted-across-threshold:` 行の型名を `demoted_types` に型別で数える**（どちらも 0 件でもキーを省かない / GitHub issue #146・#150）。合算しか残らないと **(a) 本文を書いてから捨てた**（出力トークンの純損失）と **(b) 件数だけ返した**（既に節約できている）が分離できず、閾値注入の効果を判定できない。**`pre_adjust_counts` を超える値は publish が fail-fast する**。**`adversarial_verify.inflated_axes` は反証 agent の `axis` を同じ 4 型へ寄せて数える**（`pre-existing` / `intended` → `base_derived` / `misread` → `misread` / `overstated-impact` → `overstated_impact` / `miscategorized` → `miscategorized`。**`unknown` は「軸が返らなかった・語彙外だった」件だけ**で、`unreachable` / `pre-validated` / `none` は`severity-inflated` の軸ではないのでここに落ちる）。**語彙内の値を寄せ忘れても合計の突合は通る**ので、`unknown` が 1 件以上あると `measurement_gaps` に `axis-unknown` / `demoted-unknown` が立つ / GitHub issue #167
7. **出力**: タグ（`[re-flag: @user]` 等）と severity ラベルを指摘文冒頭にそのまま残す。`⚠️ 反証メモ:` が付いた係争指摘は本文にメモを残したまま出力する

### 7. レポート出力

`missing_coverage` リストが空でない場合は「⚠️ 欠損観点」セクションを追加する（空なら省略）。**理由・補足はこのセクション本文に書き、payload の `missing_coverage` 配列には識別子のみを入れる**（語彙は orchestration-measurement.md `## 16`。自由文を入れると綴りが割れて集計不能になる）。

**冷や読み skeptic の観測可能性（issue #85）**: surface を含む変更では skeptic（Phase 5.8）の起動有無を「動的ラウンド」行に **必ず** 出す（起動＝追加件数 / 未起動＝skip 理由）。surface HIT かつ未起動の silent skip を作らない。

**skeptic 由来の帰属をレポートまで保つ（`findings_added` の計測妥当性）**: Phase 5.8 の skeptic 指摘に付いた由来タグは、**レポート本文の指摘行にもそのまま残す**（`[confidence][severity]` の後・カテゴリの前に置く）。タグを落とすと**締めフロー 4** の publish 時点で由来を再構成できず、`findings_added` が記憶頼みになって系統的に 0 へ潰れる（＝ skeptic の価値率が実態より低く出る）。**由来タグはレポート契約の一部**であり、任意の装飾ではない。

タグは 2 種（正本: orchestration-dynamic-rounds.md `## 9`）。**重複の有無で意味が正反対**になるため混ぜない:

- `[recall-skeptic]` — skeptic 単独由来（reviewer 指摘と重複しなかった）。**fleet 共通盲点を実際に破った＝ skeptic の価値**
- `[recall-skeptic:dup]` — 重複 survivor（reviewer も到達していた）。独立到達の記録としては残すが**盲点でなかった事例で recall の足し前はゼロ**

```
## レビュー結果

{emergency モード時のみ先頭に: **⚠️ 緊急レビュー（最小構成）: マージ後に通常の /review を必ず実施すること**}

**[mode: {emergency|doc-review|dba|supply-chain|skip|default}, size: {small|medium|large} (core N files / N lines), agents: [<focus 名のリスト>]]**

**総合判定**: {Approve | Approve with nits | Needs work}（scoring-guide.md「レビュー結論（総合判定）」の表に従って決定）
**総合評価**: X/10 点
**レビュー構成**: Phase 0 (triage) → 探索 (N 起動 / M 成功) → レビュー (N 起動 / M 成功)
**実効上限**: explorer N / reviewer N / specialist N（**実行時** effort `{値}` の上限と規模キャップ `{帯}` の min。どちらが効いたかを明記する）
  ※ reviewer の effort と動的ラウンド（meta / skeptic / 反証ゲート）は**実行時 effort に連動**する。skill frontmatter の effort はオーケストレーター用で別枠
**動的ラウンド**: Round 2 {未実行 | スキップ（unmet 全件が到達不能）| スキップ（unmet をメインで直接照会して解決）| 実行（reviewer N 体 / explorer M 体）} / Meta-reviewer {実行（N 件追加）| skip 理由（`effort` / `config` / `no-high-severity` / `size-tier` / `emergency`）} / 冷や読み skeptic {実行（N 件追加）| skip（理由: config/emergency）| 非該当（surface なし）} / 反証 {対象 N 件（うち meta 由来の追加バッチ M 件）| skip 理由}
**指摘件数**: BLOCKER N 件 / CRITICAL N 件 / MAJOR N 件 / MINOR N 件
**反証**: 対象 N 件 / 係争 M 件（BLOCKER/CRITICAL、本文に反証メモ）/ 取り下げ K 件（MAJOR以下、付録に理由）{**スキップ時もこの行を出す**（書式の正本は orchestration-dynamic-rounds.md `## 10` 手順 4）。`no-eligible-findings` は `未実施（対象帯に該当なし。MAJOR 以下の severity は較正されていない）` と書く — 「対象 0 件」は「検証したが問題なし」と読まれる}

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

### 🔁 報告閾値を割った指摘（参考・人間が覆せる）
{reviewer が列挙した指摘が報告マトリクスを通過しなかった場合に載る。**経路（反証 verdict / 加減算）を問わず記録し、severity 別の扱いは正本に従う** → scoring-guide.md `## 報告閾値を割った指摘の記録`。0 件なら省略}
- [調整前: confidence XX / severity MAJOR] xxx の指摘
  ファイル: path/to/file:行番号
  脱落理由: <verdict: refuted | severity-inflated> — <軸>（反証根拠 file:line）／ <加減算: 規則名> — confidence XX → YY
  ※ 判断が誤りと思えばこの指摘は有効。再評価してよい

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

**レポートを出力した直後に fleet 区間の終了マーカーを記録する**（締めフロー＝人間の応答待ちを混ぜないため。orchestration-measurement.md `## 14`。`TS_FILE` は Step 1 と同じ導出式）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark t2 --pr <PR番号>
```

レポート出力後、以下の順で締める。締めフロー 1〜3 の詳細手順（AskUserQuestion の文言・options 提示条件・3 分類の判定基準・解説の観点・ドラフトのパターン×voice・メタ行・署名・writing-polish 推敲・出力フォーマット）の正本:
→ Read `${CLAUDE_PLUGIN_ROOT}/references/closing-flow-guide.md`（以下「closing-flow-guide」。1〜3 のいずれかを実行する場合のみ読む）

1. **指摘の精査（必要性ゲート / 任意）**: 報告マトリクス通過後の指摘が **1 件以上** ある場合のみ実行（指摘 0 件、または `--emergency` 時はスキップして 2 へ）。Step 6 の機械フィルタ（閾値を超えるか）と Phase 5.9 反証（事実として正しいか）に対し、**第 3 軸＝必要性（signal/noise）** を人間に委ねるステップ。closing-flow-guide `## 1` に従い AskUserQuestion で要否を確認し、「精査する」なら各指摘を取り下げ / 降格 / 残存に 3 分類して `## 精査結果` と調整後レポートを再出力する。**精査を行わなかった場合は報告マトリクス通過後の全指摘を「残存」とみなす**（以降のステップが参照する「残存・降格した指摘」はこの確定集合を指す）。以降の返答ドラフト・publish は精査後（post）の確定値を使う。

2. **PR・指摘の解説（任意）**: 返答ドラフトの前に PR の全体像や指摘の背景を解説して判断材料を揃える（チャット出力のみ・投稿はしない）。`--emergency` 時はスキップして 3 へ。closing-flow-guide `## 2` に従い AskUserQuestion で対象（PR について / 指摘について）を確認して解説する。解説の結果ユーザーが取り下げ・降格を望んだ場合は 1 の 3 分類に差し戻して調整後レポートを再出力してから 3 へ進む。

3. **投稿コメントのドラフト生成（任意）**: 精査後に残存／降格した指摘が **1 件以上** ある、**または** 総合判定が **Approve / Approve with nits** の場合に実行（どちらにも該当しなければスキップして 4 へ）。closing-flow-guide `## 3` に従い AskUserQuestion で要否と対象を確認し、`reply-tone-guide.md` `## 0 必須ルール` を厳守した文面を生成する（パターン×voice 選定・メタ行・署名・断定抑止・`Skill` tool 経由の writing-polish 推敲を含む）。**投稿は行わずドラフト出力のみ**。ユーザーが GitHub UI で手動投稿する。

4. **このステップの直前に `${CLAUDE_PLUGIN_ROOT}/references/orchestration-measurement.md` を Read する**（publish 先の固定・`TS_FILE` のパス導出・区間の算出式・payload 契約の正本。レビュー本体の実行には不要なのでここまで読まない）。**Event Bus publish (`review:completed`)**: 集計結果を `.claude/events.jsonl` に追記する fire-and-forget の publisher。**指摘の精査を行った場合は精査後（post）の確定件数を使う**（取り下げ・降格を反映）。レポートに必要な数値（critical = confidence ≥ 90 件数、warning = 80 ≤ confidence < 90 件数、missing_coverage 配列）は既に手元にあるはず。

   **publish は専用スクリプトで行う**（書込先の固定・所要時間の算出・一時ファイルの掃除をまとめて担当する）。`duration_*` と **`agents.explorer_waves`** は**渡さない** — スクリプトが計測ファイル（explorer wave の打点）から算出して注入する:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/publish-review-event.sh" \
     --plugin code-review:review --pr <PR番号> --payload '<orchestration-measurement.md `## 16` の review 用テンプレートを実値で埋めたもの。effort は '"${CLAUDE_EFFORT}"' の実値>'
   ```

   - **報告した指摘を `findings_class` に分類して入れる**（`lint` / `test` / `judgement`。合計は報告件数と一致。分類の基準と「0 件を目標にしない」理由は orchestration-measurement.md `## 16` の「`findings_class` の使い方」）
   - **publish の WARN に `⚠️ 計測:` の追記指示が出たら、レポート末尾にその 1 行を追記する**（#135。explorer の一括発行違反・wave 打点漏れは実行中に何も起きず、しかも打点漏れは違反の証拠自体を消す）
   - スクリプトが payload の JSON 妥当性検証・**`missing_coverage` の語彙検証**（識別子以外＝理由つき自由文は `FATAL` で弾く。**理由はレポートの「⚠️ 欠損観点」に書き、フィールドごと落として通さない** / issue #132）・**動的層の `skip_reason` の語彙検証**（`adversarial_verify` / `recall_skeptic` / `meta_reviewer` の許容値は orchestration-measurement.md `## 16` が正本。**外れると `FATAL` で publish せず落ちる**ので、理由の補足はレポート本文に書く。`fired=false` で理由を書き忘れた回だけは落とさず `measurement_gaps` に倒す）・書込先のメインリポジトリ固定・一時ファイルの掃除まで行う（→ orchestration-measurement.md `## 13`）。**`measurement_gaps` / `derived_markers` / `diff_digest` / `tokens` / `models`（**モデル世代**。transcript の `message.model` からの機械計測で、渡しても捨てられる / issue #169）と版マーカーの整数（`schema` / `gate_schema` / `attribution_schema` / `calibration_schema`）も渡さない**（`derived_markers` は**打点が落ちた区間を agent の実測時刻で埋めた記録**で、`measurement_gaps` とは排他ではない / issue #161） — 計測ファイル・一時 diff・transcript から算出して注入される（定数の手書きは version drift 中に落ちサンプルが逆の版バケツに入るため v2.65.0 で移した / issue #125）。**渡すのは実行時の事実だけ**で、層のオブジェクト自体（`adversarial_verify` / `recall_skeptic` / `meta_reviewer` / `pre_adjust_counts` / `below_threshold_counts`）と各層の `fired` は**必ず入れる**（落ちると `measurement_gaps` に `payload:<field>` が立つ）。**`agents` の内訳は transcript 由来の `dispatch.agents` と突合される**（issue #154）— 合わないと `agents-mismatch` が立つので、`specialist` / `round2` を実際に起動したのに 0 のままにしない（publish は止まらないが、`agents` は体数と時間・トークンの相関すべての分母なので申告漏れがそのまま集計を歪める）

   **payload 契約の正本は orchestration-measurement.md `## 16`**（フィールドの意味・版マーカー・後方互換をここに複写しない）。review 固有の点のみ:
   - `pr` は Step 1 で取得した PR 番号の文字列（失敗時は `"local"`）。`head_verified` は review のみ（Step 4 / Step 5 の `HEAD 検証:` 行の集計）。`duration_closing_min` は締めフロー（人間の応答待ち）を捉えるが**改善の効果測定には使わない**（人間の都合で 10 倍振れる）
   - `agents.round2` / `recall_skeptic.findings_added` はレポートの「動的ラウンド」行の数値と一致させる。**`meta_reviewer.findings_added` も同様**（`[meta]` タグ付き指摘を数える。#121）

   **publish の直後に `bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-retro.sh"` を実行する**（→ 同 `## 18`）。出力は**そのままレポートの後ろに出す**（要約・再解釈をしない）。**⚠️ シグナル行が出たときだけ**戻り先ドキュメントを示して 1〜2 行の所見を添え、無い回は集計表だけ出す。失敗しても続行（best-effort）。

5. **agent worktree の掃除（ExitWorktree の直前 / 必須）**: agent は `isolation: "worktree"` で起動するため体数ぶんの worktree が配下に残り、**この状態では `ExitWorktree(remove)` が state 検証に失敗して worktree を畳めない**（GitHub issue #105）。**同じブロックで publish 済みかを確認する**（4 の publish は副作用のみで出力に何も足さないため、脱落しても実行中は気づけない。ここは必須ステップなので通過が保証される / GitHub issue #133。**警告が出たら ExitWorktree の前に 4 へ戻る** — `TS_FILE` の slug は worktree のパス由来なので、抜けた後では同じ計測ファイルを引けなくなる / orchestration-measurement.md `## 13.1`）:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" publish-pending --pr <PR番号>
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/cleanup-agent-worktrees.sh"
   ```

   削除対象は **①現在の worktree の配下 ②未コミット変更なし ③自分自身ではない** の 3 条件を満たすものだけ（並行レビューや開発用 worktree には触れない）。**出力の件数をレポートに 1 行残し**、失敗が 1 件以上なら手動 remove を案内する。掃除に失敗しても続行する（best-effort）。→ 残留する理由: `design-notes/orchestration-rationale.md`

6. **ExitWorktree** で worktree から抜ける。

7. **関連 worktree の teardown 案内（任意・非ブロッキング）**: ExitWorktree 後（main clone 上）、PR ブランチに紐づく**開発用 worktree**（dev-workflow:worktree-setup で作成したもの）が残っていないか検出する。ブランチ名一致だけではレビュー用に EnterWorktree した一時 worktree（`.claude/worktrees/` 配下）と区別できないため、**パス除外 + worktree-setup マーカーの 2 条件**で開発用 worktree に限定する:

   ```bash
   # ブランチ名を SKILL 本文に埋めない（PR 作者が制御する文字列がシェルで評価される経路になる）。
   # PR 番号だけ渡し、ブランチ名の取得はスクリプト内に閉じる
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-dev-worktree.sh" --pr <PR番号>
   ```

   - 検出した場合のみ、最後に一言案内する: 「関連する開発用 worktree が残っています: `<path>`。作業が完了していれば該当 worktree 内で `/worktree-teardown` を実行して片付けられます」
   - dev-workflow の有効判定は self-review Step 8 と同じ enabled-only 判定（`grep -Eq '"dev-workflow@[^"]*"[[:space:]]*:[[:space:]]*true'` を global / project / local の settings 3 ファイルに対して実行）。無効なら `git worktree remove <path>` の手動案内に切り替える
   - worktree-teardown は worktree 内からしか実行できないため、ここでは**自動起動しない**（案内のみ）
   - 未検出なら何も出力しない
   - 補足: 開発用 worktree が PR ブランチを checkout したままだと、Step 1 の `gh pr checkout` は二重チェックアウト禁止で失敗する（レビュー自体は `gh pr diff` ベースで劣化続行できる）。その経路でも本ステップの検出は機能する
