---
name: self-review
description: >
  Phase 0 トリアージ + 動的エージェント構成のセルフレビュー。
  diff → explorer(sonnet) → reviewer(opus) を動的構成、severity×confidence マトリクスでフィルタ。
  トリガー: 「セルフレビュー」「/self-review」「自分の変更を確認」「コミット前にチェック」
  引数: [base branch] [--staged] [--focus <観点>] [--exclude <観点1,観点2>] [--embed] (省略時は自動検出)
effort: high
allowed-tools:
  - Bash
  - Read
  - Write
  - Agent
  - AskUserQuestion
  - Skill
---

# Self Review

<!-- 正本依存（SSoT pin）。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: code-review/references/orchestration-guide.md#3.5 @90899a7e -->
<!-- SSOT: code-review/references/orchestration-measurement.md#16 @9a0b0194 -->
<!-- SSOT: code-review/references/scoring-guide.md#報告閾値を割った指摘の記録 @3cf8c3c4 -->

## review との違い

- PR 不要。ローカルのみで完結
- コミット前・PR 作成前の品質ゲートとして使用
- **コメント推敲（B 系統）を出すのは self-review だけ**（v2.45.0）。diff で追加・変更したコメントを「読み手に必要な情報のみか / 冗長表現が無いか」の 2 観点で推敲し、severity マトリクスを通さない別枠セクションに before→after で出す。他人の PR に文面の推敲を投稿するのは越権になりやすいため review 側には入れない

## コスト×精度パイプライン設計（採用/不採用）

ルート CLAUDE.md「コスト×精度パイプライン設計指針」の 10 原則のうち **採用: 1（ファネル = Phase 0 triage で高コスト reviewer を通過分に絞る）/ 2（2 軸スコア化 = confidence × severity マトリクス。**ただしコメント推敲（B 系統）は 2 軸を持たずマトリクスを通さない別枠経路** / v2.45.0）/ 3（段階予算 = `${CLAUDE_EFFORT}` → explorer/reviewer 体数）/ 4（モデルルーティング = explorer:sonnet / reviewer:opus / meta:opus / 反証:opus）/ 7（敵対的独立検証 = Phase 4.9 反証レイヤー、recall 側は Phase 4.8 冷や読み skeptic）/ 8（外部オラクル = Step 1.7 の機械層先行実行。**プロジェクトが `.claude/review-oracles.sh` で宣言したときのみ**。宣言が無ければ no-op で、コマンドはプラグイン側で推測しない / v2.69.0・ADR-20260817170000）**。**捨てた**: 5（暴走ガード）は反復・起票を持たない単発レビューのため不要、6（証拠ラダー）は指摘蓄積・昇格の責務を failure-journal に委ねた。

## 設計原則: Generator と分離された Evaluator

self-review は `dev-workflow:git-commit-helper`（Generator: 変更を生成・コミットする側）から独立した Evaluator として機能する。同一コンテキストで生成と判定を行うと confirmation bias で見落としが増えるため、以下のフローを推奨する:

1. 実装・変更 → `/self-review` （別コンテキストで起動）
2. 指摘事項を修正
3. `/git-commit-helper` でコミット

Phase 0 の explorer/reviewer 並列起動も同じ思想で、reviewer は explorer の結果を「独立した観点として」受け取る（自分で diff を再探索させない）。

## 前提

- **effort のつまみは 2 つあり、別物**（GitHub issue #106）:
  - **skill frontmatter の `effort`** — オーケストレーター（メインループ）専用。**reviewer にも動的ラウンドにも効かない**
  - **実行時 `${CLAUDE_EFFORT}`** — reviewer / specialist の effort と、動的ラウンド（meta-reviewer / 冷や読み skeptic / 反証ゲート / Round 2 の段数）の**起動条件を支配する**（正本: orchestration-guide.md `## 5`）

## 実行手順

実行フェーズの共通詳細の正本:
→ Read `${CLAUDE_PLUGIN_ROOT}/references/orchestration-guide.md`（以下「orchestration-guide」）

**orchestration-guide は分冊されている。冒頭の「この分割の読み方」に従い、必要になった分冊だけをその時点で Read する**（条件付きフェーズを全部スキップするなら分冊は読まない）:

| 分冊 | Read するタイミング |
|---|---|
| `orchestration-dynamic-rounds.md` | 動的ラウンド（Round 2 / meta-reviewer / skeptic / 反証）の**いずれかを実行すると決まったとき** |
| `orchestration-measurement.md` | **publish の直前**（Step 6.4） |
| `orchestration-optional-flows.md` | Issue 必読 / Vault 照合 / 訂正の伝播前ガード / embed mode の**適用条件を満たしたとき** |

同じく `triage-guide.md` も Phase 0 用の中核だけを持ち、動的ラウンドの起動ゲートは `triage-dynamic-gates.md` にある（**起動可否を判断する段で Read する**）。

self-review では `isolation: "worktree"` を使わない等の差分は orchestration-guide `## 0` を参照。

### 1. diff 収集とコンテキスト準備

```bash
# 所要時間計測の開始マーカー t0 を記録（Step 6.4 の payload で使用）。
# 以降 t1（一括発行の直前）/ wave --explorer（explorer 回収直後）/ wave（agent wave 回収の直後・毎回）/ t2（レポート出力直後）を
# 同じスクリプトで追記する。パス導出・区間の意味の正本: orchestration-measurement.md `## 13.1` `## 14`
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" start

# 引数で base branch が指定されていればそれを使用
# 指定がなければデフォルトブランチを自動検出
git remote show origin | grep "HEAD branch" | sed 's/.*: //'
```

base branch が特定できない場合はユーザーに確認する。

**diff 全文をメインコンテキストに載せない。** `triage-signals.sh` が diff（コミット済み + 未コミット）をファイルへ保存し、Phase 0 に必要な**事実だけ**を compact に出力する。diff は reviewer / explorer へ**パスで渡す**（本文を転記しない。orchestration-guide.md `## 3.5`）。

```bash
# diff を $DIFF_FILE に保存し、シグナルダイジェストのみ stdout に出す
bash "${CLAUDE_PLUGIN_ROOT}/scripts/triage-signals.sh" --base "${BASE}"
```

出力セクション（`## meta` / `## size` / `## files` / `## hunks` / `## focus-signals` / `## red-flags` / `## surface` / `## explorer-signals` / `## agents-md` / `## issue-ids`）の意味と使い道の正本 → review SKILL.md `### 2`。self-review では `## issue-ids` はブランチ名から抽出され、`## meta` の `base` は指定した base branch になる。

- **`size_tier`** はスクリプトが triage-guide.md `## 6.2` の帯定義を機械適用した値をそのまま使う（core = lock・生成物・テスト・doc を除いた実質規模。GitHub issue #96）。Phase 0 の構成テーブル・Step 6 レポート冒頭・Step 6.4 の `size_tier` に記録する
- **シグナルは事実であって判定ではない**。観点採否・体数は triage-guide が決める。ヒット数 0 の観点は出力に現れない＝条件不成立、と読む
- **`diff_file=` と `agent_ctx_file=` の値はパス文字列そのものを控えておく**（後者は Step 4 の共通ブロック書き出し先。**slug は不透明な cksum 値なので、控え損ねると復元できない**）（シェル変数は Bash 呼び出し間で消えるため、`$DIFF_FILE` として引き回さず実パスを毎回書く）
- **判断が付かない場合のみ** `diff-slice.sh "<diff_file の実パス>" <path>` で必要なファイルの diff だけを読む（全文 Read はしない）
- **スクリプトが失敗した場合**は `git diff "${BASE}..HEAD" --name-only` と `--stat` でファイル一覧と規模を取り、triage-guide.md `## 6.4` のフォールバック構成に落とす。**diff 全文の Read はこの経路でも行わない**

`## size` の `total_files` が 0 なら変更なしとして終了。

`--staged` 引数が指定されている場合は `triage-signals.sh --base "${BASE}" --staged` を使う（`git diff --cached` のみが対象になり、未ステージの変更とコミット済みの差分は除外される）。

**`--embed`（他 plugin からの呼び出し）:**

`--embed` 引数が指定されている場合は、本 skill が他 plugin（例: feature-dev Phase 6）からプログラム的に呼び出されたと判断する。Step 7 の修正方針確認 AskUserQuestion と Step 8 の worktree teardown 連携を skip し、Step 6 のレポートをそのまま return する。呼び出し元側で findings を集約・後処理する前提。

return 仕様（**dual format**: 人間可読 markdown ＋ 機械可読 JSON、marker の位置、後方互換）の正本 → orchestration-optional-flows.md `## 15`。AskUserQuestion は呼ばない（呼び出し元の UX を阻害しない）。

**`--focus` / `--exclude`（同一セッションでの重複レビュー回避）:**

同一セッションで既に reviewer agent を走らせた後（コミット前並列レビュー等）に self-review を再実行する場合、既検証の観点を再報告しないよう以下の引数でスコープを制御する:

- `--focus <観点>`: レビュー対象を特定の観点に絞る（例: `--focus "comment-conciseness"`, `--focus "type-safety"`）。複数指定はカンマ区切り
- `--exclude <観点1,観点2>`: 既に他 agent でカバー済みの観点をスキップする

適用先:
- **Phase 0 (Step 2)**: `--focus` 指定時は該当観点の reviewer のみ構成する（最小保証の reviewer-bugs / reviewer-claude-md も `--focus` に含まれない限り起動しない）。`--exclude` 指定時は該当観点の reviewer を構成から外す
- **reviewer 起動時 (Step 4)**: 各 reviewer プロンプトに以下を注入する

  ```
  review focus: {{ focus or "全件" }}
  already verified (do not re-report): {{ exclude or "none" }}
  ```

**コンテキスト収集（並列で実行）:**
- CLAUDE.md・規約ファイル: `CLAUDE.md`, `.github/CONTRIBUTING.md`, `.eslintrc.*`, `prettier.config.*`
- `.claude/session-context.md` の存在確認（存在する場合、frontmatter の `branch` と現在のブランチ名を比較。一致すれば有効）
- Issue/knowledge ファイルの探索
- プロジェクト特性シグナル（`package.json` の存在確認と主要依存の確認）

### 1.4 直近レビューとの重複検出（skill 跨ぎ / 常時実行・agent なし。`--embed` ではスキップ）

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-recent-review.sh"
```

**出力が空なら何も報告せず Step 1.5 へ**。`## recent-review` が出た場合のみ **AskUserQuestion** で続行可否を確認する（question:「同一の diff が直近にレビュー済みです（<plugin> / <日時> / 報告 <件数>）。このままレビューを続けますか？」/ header:「重複レビュー」/ options: ①label「続行する」description「別観点・別 effort で見直す価値があると判断した場合」 ②label「中止する」description「前回のレポートで足りる。agent を 1 体も起動せず終了する」）。**「中止する」なら Phase 0 に進まず終了**。上の `--focus` / `--exclude` は同一 skill 内の重複しか防げないので、この経路が skill を跨ぐぶんを見る。突合キーの性質と背景: → orchestration-measurement.md `## 19`

### 1.5 Vault 照合（過去の指摘・落とし穴の retrieval / 任意・後方互換）

変更ファイルに関連する過去のレビュー指摘を vault から引いて reviewer に注入する（GitHub issue #68）。利用可否の検出（`kvault` / `/vault-recall` が無ければ skip）・照合手順・best-effort の注意事項 → orchestration-optional-flows.md `## 11`

### 1.7 機械層の先行実行（原則 8 / `.claude/review-oracles.sh` を置いたプロジェクトのみ・`--embed` では skip）

**agent の担当は「機械が決められないもの」に限る。** `bash "${CLAUDE_PLUGIN_ROOT}/scripts/run-oracles.sh"` を実行し、プロジェクトが宣言した機械層（lint / 型 / テスト等）を Phase 0 の**前に**通す。**出力が空なら宣言なし＝何も報告せず Phase 0 へ**（no-op を報告しない）。`status=green` は Step 6 レポート冒頭に `機械層: green (<elapsed>s)` を出すだけ。**`red` / `timeout` / `error` のときだけ** → Read `${CLAUDE_PLUGIN_ROOT}/references/machine-layer.md`（続行可否の確認・reviewer への「既知」の渡し方・計測規約の正本。設計判断は ADR-20260817170000）。`--embed` では呼び出し元が自分の品質ゲートを持つため skip する。

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
- explorer: 独立した探索対象の数に比例
- reviewer: 必要な観点数 × 対象コードの複雑さに応じた冗長度
- 冗長ペアには異なる angle（分析の切り口）を割り当てる（実起動は xhigh/max のみ。下記）
- 最小保証: reviewer-bugs + reviewer-claude-md の 2 体は常に起動

**実効上限 = min(effort 上限, 規模キャップ)**（体数の正本: triage-guide.md `## 7` / `## 6.2`）。**2 系統を必ず両方適用する**（effort 上限だけを見ると小さな変更に上限いっぱいの体数が張り付く。GitHub issue #96）。

第 2 系統 — **規模キャップ**（Step 1 で数えた core 規模。triage-guide.md `## 6`）:
- small（core ≤ 3 ファイル かつ ≤ 100 行）: explorer 0 / reviewer 3 / specialist 1
- medium（core 4-10 ファイル または 101-500 行）: explorer 2 / reviewer 5 / specialist 2
- large: キャップなし（effort 上限がそのまま実効上限）
- **最小保証の 2 体は規模キャップより優先**。キャップに収まらない観点は `missing_coverage` に識別子 `<focus>` として記録する（**規模キャップで落ちた旨はレポートの「⚠️ 欠損観点」へ** — payload は識別子のみ）
- **規模キャップが effort 上限を下回った場合、Round 2（Phase 4.5）は effort に関わらず 1 段圧縮経路**（追加 explorer なし）。一方 **reviewer 個々の effort・meta-reviewer・skeptic・反証レイヤーは削らない**（削るのは breadth のみ。triage-guide.md `## 6.3`）
- `--focus` / `--exclude` でスコープを絞った実行では、そもそも構成が観点指定で決まるため規模キャップは追加で効かせない（指定観点は必ず起動する）

第 1 系統 — **effort 上限**（現在の effort = `${CLAUDE_EFFORT}`）:
- `low` / `medium`: explorer 2 体、reviewer 4 体、specialist 3 体（束ね起動）（最小保証は維持）。深掘りより速度優先
- `high`（既定）: explorer 4 体、reviewer 6 体、specialist 3 体（束ね起動）。**冗長ペアは組まない**（ペア条件成立時は Angle A/B を 1 体に内挿）。上限を超える観点数は近接観点のバンドルで可能な限り吸収し、それでも収まらない観点は `missing_coverage` に必ず記録する（容量の算式は triage-guide.md `## 7`。脱落を silent にしない）
- `xhigh` / `max`: explorer 6 体、reviewer 10 体、specialist 6 体を full に使い、冗長ペアを積極投入

#### 2.3 観点カバレッジ検算と構成テーブル出力

**構成テーブルを確定する前に、起動前検算を実施する（orchestration-guide `### 8a`・常時実行）**: 観点判定表の各条件を diff シグナルに対して再評価し、条件を満たすのに構成に入っていない focus があれば構成テーブルに追加（またはバンドルで相乗り）してから確定する。v2.39.0 で旧 Phase 4.7 の補完起動から前倒し（起動後の直列 wave を無くすため。検算内容は同一）。`--focus` / `--exclude` 指定時はその範囲内でのみ検算する。

検算後、triage-guide.md の出力フォーマット（`## 5`）に従い、エージェント構成テーブルを出力する。**「直列 wave」行を必ず含める**（見積もり方は triage-guide.md `## 5.1`）— 体数はトークンコストのレバー、wave 数は壁時計のレバーで、後者だけが従来ユーザーから見えなかった（GitHub issue #100 B）。

#### 2.4 high-risk surface 判定（冷や読み skeptic の相乗り判断 / 常時実行）

Phase 0 の最後に、triage-dynamic-gates.md `## 8.5` の surface 判定（diff への正規表現 grep。self-review は PR を持たないため自己申告経路は無い）を **必ず実施** する。安価な grep なので構成に関わらず常に行う（silent skip 防止・issue #85）。

- surface=true **かつ Phase 4.8 のスキップ条件（userConfig / effort / `--focus`・`--exclude` によるスコープ絞り込み）のいずれにも該当しない**場合、skeptic を **Step 4 の reviewer 一括発行に相乗りさせる**（同一メッセージ内で発火。1 wave 削減）。**条件は個別に列挙せず Phase 4.8 の定義を参照すること**（相乗りで起動が前倒しされるため、4.8 に到達してからスキップ判定しても手遅れ）
- surface=true だがスキップ条件に該当する場合は、`skip_reason` を記録して Step 6 レポートと payload に出す（従来どおり）
- reviewer の `[surface:high-risk]` フラグ由来で事後に surface=true になる経路は Phase 4.8 の fallback で拾う

### 3. 探索フェーズ（explorer 並列起動）

Phase 0 が explorer を 1 体以上配置した場合のみ実行。explorer が不要と判断された場合はスキップして Step 4 へ。

Phase 0 の構成テーブルに従い、各 explorer を `model: sonnet` で並列起動する:
- プロンプト冒頭で **`prompts/explorer-common.md` と `prompts/explorer/<focus>.md` の 2 パスを Read せよ**と指示する（本文は書かない。組み立て方の正本: `${CLAUDE_PLUGIN_ROOT}/references/explorer-prompts.md`）
- 可変部として Phase 0 が決定した focus・対象ファイル・関数、および **Step 1 の `$DIFF_FILE` のパスと担当ファイル名**を渡す（`diff-slice.sh` で自分の担当ぶんを切り出せることも明記する）
- `isolation: "worktree"` は使用しない（セルフレビューは未コミット変更を含むため）
- 全エージェントに `run_in_background: false` を明示し、**全 explorer の Agent call を同一メッセージ内で一括発行する**（orchestration-guide.md `## 0`。`run_in_background` 省略は取りこぼし、1 体ずつ別メッセージ発行は逐次実行＝実時間が合計に膨らむ。2 つは独立の要件）

一括発行の**直前**に fleet 区間の開始マーカーを記録する（**agent wave はすべて fleet 側に入れる**。explorer を triage 区間に含めると `duration_triage_min` が「メイン思考の代理指標」でなくなる。orchestration-measurement.md `## 14`）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark t1
```

全 explorer の完了を待ち、結果を収集する。**回収した直後**に explorer wave の終了マーカーを記録し（`t1`→ explorer 打点 = explorer wave の実時間。orchestration-measurement.md `## 14`。`TS_FILE` は Step 1 と同じ導出式）、各 explorer の `#### 確定事実` 欄を集約して **合計 10 行以内**にまとめておく（Step 4 で全 reviewer に注入する枠。無ければ no-op）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark wave --explorer   # 複数メッセージに分けてしまった場合も wave ごとに毎回打つ（行数が agents.explorer_waves になる・#122）
```

**部分失敗耐性:** orchestration-guide.md `## 5` に従う（個別失敗で全体を中止せず `missing_coverage` に記録して続行）。

### 3.9 AGENTS.md 階層動的選択（reviewer 起動前）

Step 1 のダイジェスト `## agents-md` に出ている**パス一覧**を reviewer プロンプトに渡し、agent 自身に Read させる（本文の転記はしない — 既にディスク上にあるので体数ぶんの複製がそのまま消える。orchestration-guide.md `## 3.5`）。ヒットが 0 件なら no-op（後方互換）。

注入セクション名・探索ロジックの詳細: → orchestration-guide.md `## 4`

### 4. レビューフェーズ（reviewer 並列起動）

**プロンプトテンプレートは Read しない。パスを渡して agent 自身に読ませる**（組み立て方の正本: `${CLAUDE_PLUGIN_ROOT}/references/reviewer-prompts.md`。共通指示だけで約 7.3k tokens あり、体数ぶん転記すると出力トークンが `(N-1) × 本文長` 膨らむ — orchestration-guide.md `## 3.5`）。

Phase 0 の構成テーブルに従い、各 reviewer を `model: opus` で並列起動する。effort は実行時 `${CLAUDE_EFFORT}` に連動させる（low/medium/high（既定）→ `high`、xhigh/max → `xhigh`。設計意図は orchestration-guide.md `## 5`）。**userConfig `reviewer_effort_profile` が `differentiated` のときは high 帯に限り低密度観点の reviewer を `medium` で起動する**（高密度観点・specialist・最小保証 2 体は `high` 維持。xhigh/max は無視。マップの正本は triage-guide.md `## 7.1`。A/B 実験フラグで既定 `uniform` は現行どおり）。プロンプトは **Read させるパスの列挙 + 可変部**だけで構成する:

- **必ず Read させる**: `prompts/reviewer-common.md` と `prompts/focus/<focus>.md`（self-review は PR を持たないので `pr-context-rules.md` は渡さない）。条件付きで加えるもの:
  - 観点バンドル時 → `prompts/bundle-rules.md` と束ねる focus ファイル群
  - **ペア条件が成立したとき → `prompts/angles.md`**（xhigh/max の実ペアだけでなく、**high 以下の angle 内挿でも渡す**）
  - セッションコンテキストが有効なとき → `prompts/session-context.md`（confidence −30 の規約はここにある）
- **`comment-accuracy` を担当する reviewer には `prompts/focus/comment-polish.md` を Read 対象に追加する**（単独起動・バンドル相乗りのどちらでも追加。B 系統は Focus テンプレートではないので前項では拾われない。追加漏れは機能の silent な不発になる）
- **可変部の共通ブロック（全 agent 共通の実値集合）は 1 ファイルに落としてパス渡しする**: Step 1 の `## meta` が出す `agent_ctx_file=` のパスに **Write で 1 回だけ**書き出し、各プロンプトには「まず `<agent_ctx_file>` を Read せよ」の 1 行だけを置く。**入れる項目・残す項目・フォールバックの正本は orchestration-guide.md `## 3.5`「可変部の共通ブロックに入れるもの」**（`{{PLUGIN_ROOT}}` / `{{SEVERITY_THRESHOLD}}` / `$DIFF_FILE` / AGENTS.md パス / session-context パス / 確定事実 など。#124 (c)）
  - **self-review 固有**: **PR 番号・HEAD SHA・`{{MAIN_ROOT}}` は入れない**（PR を持たず worktree も使わないので、テンプレートの worktree セットアップ節は適用外である旨を共通ブロックに明記する）
- **プロンプト側に残す可変部**: 担当 focus（冗長ペアなら angle）と担当ファイル、**explorer 結果の選択的注入**（構成テーブルの「explorer 依存」列。複製係数がほぼ 1 なのでインラインのまま）
- **確定事実は共通ブロックに入れず、reviewer にだけインライン注入する**: Step 3 でまとめた `## 確定事実（explorer 共通・裏取り済み）` を**全 reviewer（specialist・skeptic を除く）**に合計 10 行以内で注入する。**skeptic に渡すと findings 非注入という層の設計核が壊れる**（triage-dynamic-gates.md `## 8.5`）。扱いの規約は `prompts/reviewer-common.md` 側（#122）
- **Vault 注入**: Step 1.5 で関連ありと判断した知見があれば、各 reviewer プロンプトに `## Vault prior findings（過去の関連指摘・落とし穴）` セクションとして注入する。reviewer には「過去に同種コードで指摘された観点を優先的に確認せよ。ただし現在の diff に該当しなければ無視してよい」と添える
- `isolation: "worktree"` は使用しない
- 全エージェントに `run_in_background: false` を明示し、**全 reviewer の Agent call を同一メッセージ内で一括発行する**（orchestration-guide.md `## 0` 並列発行の明示。1 体ずつ別メッセージで発行するとフェーズ実時間が相内最長でなく合計になる）
- **冷や読み skeptic の相乗り**: Step 2.4 で surface=true かつ Phase 4.8 のゲートを通過している場合、skeptic 1 体（`model: opus`, `effort: max`、プロンプトは `prompts/recall-skeptic.md` をパス渡し）を **この一括発行に含める**。skeptic は findings 非注入が設計の核で reviewer 出力に依存しないため、直列に置く理由がない（triage-dynamic-gates.md `## 8.5` 起動タイミング）。結果の統合は Phase 4.8 で行う

一括発行の**直前**に fleet 区間の開始マーカーを記録する（orchestration-measurement.md `## 14`。`TS_FILE` は Step 1 と同じ導出式で決める。Step 3 で explorer を起動していれば記録済みなので `grep` ガードで二重記録を防ぐ。`||` 形なのでガードが偽でもブロックは成功終了する）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark t1
```

全 reviewer の完了を待ち、結果を収集する。**回収した直後**に `bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark wave` を実行する（打点→`t2` = agent 非稼働が保証される synthesis 区間。**動的ラウンドの各回収点でも毎回繰り返す** — 後勝ちなので最後の wave を判断しなくてよい。orchestration-measurement.md `## 14`）。

reviewer 起動の共通詳細（effort 設計意図・diff-first 原則・出力形式の検証と auto-retry・部分失敗耐性・最小保証の閾値）: → orchestration-guide.md `## 5`

**最小保証の閾値のみ抜粋**: Phase 0 の最小保証（reviewer-bugs と reviewer-claude-md）が **両方とも失敗** した場合のみレビュー中止とし、ユーザーに再実行を促す。それ以外は欠損観点を明示しつつ Step 5 に進む。

### 4.5 Adaptive deepening: Round 2（unmet_information 起点 / 動的）

**スキップ条件**（いずれか満たせばこのフェーズ全体をスキップして Step 4.8 の skeptic 統合へ）:
- userConfig `enable_adaptive_rounds` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `low` または `medium`
- 全 reviewer の出力に `## unmet_information` セクションが 1 件もない
- **unmet の target が全件「到達不能」**（DB / 本番の実データ、このリポジトリに存在しないコード、意図的にスキップした lint / テスト実走など）で、追加探索が構造的に空振りする場合。分類表と「1 件でも到達可能なら起動する」根拠は triage-dynamic-gates.md `## 8`（GitHub issue #100 C）。スキップ時は `missing_coverage` に識別子 `round2` を記録し（**理由はレポート本文へ**）、レポートの「動的ラウンド」行にも出す。**⚠️ 「repo 外」≠「到達不能」（v2.60.0）** — 外部サービスの実挙動でも**その MCP / CLI がセッションで使えるなら到達可能**で、Round 2 の前に**メインで直接照会して解決してよい**（read-only）

**実行する場合**: **Read** `orchestration-dynamic-rounds.md` してその `## 6` の手順に従う（unmet_information 集約 → **high は 1 段圧縮**: 追加 explorer なしで該当 reviewer 最大 3 体を再起動し unmet ターゲットを自力探索させる / **xhigh・max は 2 段**: 追加 explorer 最大 3 体 → 該当 reviewer 再起動 → 初回出力を置換。失敗時は初回結果のまま続行の best-effort）。**回収した直後に `mark wave` を記録する**（Step 4 と同じ呼び出し。後勝ち。**追加 explorer を起動した場合も `--explorer` は付けない** — `agents.explorer_waves` は「初回 explorer の一括発行が守られたか」の指標で、Round 2 の追加 explorer を混ぜると規約どおりの起動が「一括発行違反」として誤検知される）。レポートに「Round 2 trigger: <reason>」を記録（Step 6 で出力）。

### 4.6 Meta-reviewer ラウンド（v2.12.0 / 動的・**4.9 反証と同一 wave**。実行順は `4.5 → 4.8 の skeptic 統合 → 4.6 meta + 4.9 反証を同一メッセージで一括発行 → mark wave → [meta 由来の追加反証バッチ] → 4.7 → Step 5`。両者は互いの出力に依存しないので直列に置かない / **片方がスキップでも他方はそのまま発行する** / #122）

**スキップ条件**（いずれか満たせばスキップし、同一 wave の 4.9 だけを発行する）:
- userConfig `enable_meta_reviewer` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `xhigh` または `max` **でない**
- **severity 側の起動条件を満たさない**（`skip_reason: "no-high-severity"` / `gate_schema: 3`）。起動条件は「Step 4.5 後の全指摘（フィルタリング前）に **BLOCKER** が 1 件以上」∨「**CRITICAL** が 1 件以上」∨「**報告マトリクス通過見込みの MAJOR が 3 件以上**」。MAJOR 経路は v2.62.0 で追加した（旧ゲートは高 severity の存在だけを条件にしていたため実測 14 件中 `fired=1` とほぼ常時不発だった / GitHub issue #123 C）
- **`size_tier` が `small` かつ BLOCKER が 1 件もない**（v2.60.0 / `skip_reason: "size-tier"`）。BLOCKER があれば帯に関わらず起動する。**この 1 条件だけが規模帯に連動する例外**で（triage-guide.md `## 6.3`）、根拠が n=1 のため**ロールバック条件つきの暫定ゲート** → `design-notes/triage-rationale.md`

**実行する場合**: **Read** `orchestration-dynamic-rounds.md` してその `## 7` の手順に従う（meta-reviewer を 1 体 `model: opus`, `effort: max` で **Step 4.9 の反証バッチと同一メッセージ内で**起動 → 追加指摘を dedup して統合。失敗時は missing_coverage に追記して続行）。**回収した直後に `mark wave` を記録する**（Step 4 と同じ呼び出し。後勝ち。反証と同一 wave なので打点は 1 回で足りる）。

### 4.7 観点カバレッジ・事後突合（メインコンテキスト / 常時実行・agent 追加起動なし）

Step 5 の直前に、**メインコンテキストで**（Agent は使わない・低コスト）Step 2.3 の起動前検算で確定した構成テーブルと実際に起動・完走した focus を突合し、差分を `missing_coverage` に追記する（orchestration-guide `### 8b`）。観点漏れの検出は Step 2.3 の起動前検算（`### 8a`）へ前倒し済みのため、**本フェーズで agent は追加起動しない**（v2.39.0。issue #69 の常時検査の意図は 8a で維持）。

**スキップ条件**: `--focus` / `--exclude` 指定時は意図的にスコープを絞り込んでいるため、その範囲外の観点は missing_coverage に記録するのみ。

### 4.8 冷や読み skeptic ラウンド（recall 補強 / 動的）

reviewer wave への相乗りで起動し、4.6 + 4.9 の一括発行より前に統合する。**high-risk surface を含む変更に限り**、reviewer の findings も推論も渡さない独立 skeptic を 1 体起動し、fleet 共通の盲点（層跨ぎ値フロー等）を冷や読みで探す（`${CLAUDE_PLUGIN_ROOT}/references/triage-dynamic-gates.md` `## 8.5 冷や読み skeptic ラウンド`）。反証レイヤー(4.9)が偽陽性を潰す係なのに対し、本フェーズは見落とし（false negative）を独立読み直しで足す係。self-review は PR を持たないため surface 判定は diff 正規表現 + reviewer の `[surface:high-risk]` フラグで行う（PR 自己申告 D1-High は無い）。

**スキップ条件**（いずれか満たせばスキップして 4.6 + 4.9 の一括発行へ）:
- userConfig `enable_recall_skeptic` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `low` または `medium`（**high は起動する**。v2.52.0 で昇格 — surface=true の 63% が effort ゲートで未起動だった一方、起動できた回の 50% が fleet 共通盲点を実際に破っていた。根拠: `design-notes/triage-rationale.md`）
- `--focus` / `--exclude` でスコープを絞り込んでいる
- high-risk surface（triage-dynamic-gates.md `## 8.5` の surface 判定）を含まない

**スキップ時も surface 判定は必ず実施（silent skip 防止・issue #85）**: 上記スキップ条件（effort / config / scope）に該当して skeptic agent を起動しない場合でも、surface 判定（triage-dynamic-gates.md `## 8.5` の正規表現。diff への grep で安価）だけは Phase 0 の構成判断（縮退構成・小 diff）と **独立に必ず実施** する。surface=true なら skeptic 未起動の事実と skip_reason（`effort` / `config` / `scope`）を Step 6 レポートの「動的ラウンド」行に必ず出す（`--embed` の有無に依存しない human レポート契約。JSON payload の `recall_skeptic` 記録と対を成す）。

**実行する場合**: **Read** `orchestration-dynamic-rounds.md` してその `## 9` の手順に従う。**起動は Step 4 の reviewer 一括発行に相乗り済み**（Step 2.4 で surface 判定・ゲート通過を確認している）なので、本フェーズで行うのは **結果の統合**（`[recall-skeptic]` / `[recall-skeptic:dup]` タグ付き指摘を dedup して統合し、反証レイヤー(4.9)の対象にも含める）。**この統合は 4.6 + 4.9 の同一 wave 発行より前に済ませる**（skeptic の指摘を反証対象に含めるため。統合はメインコンテキストの作業で agent を要さない）。

**fallback（直列起動）**: reviewer の `[surface:high-risk]` フラグ由来で**ここで初めて** surface=true になった場合のみ、skeptic を 1 体 `model: opus`, `effort: max` で単独起動する（**findings / reviewer の推論は渡さない**のが独立性の核）。**この経路で起動した場合は回収した直後に `mark wave` を記録する**（相乗り経路では Step 4 で記録済みなので不要）。正規表現で事前に HIT していれば相乗り済みなのでこの経路は走らない。

**失敗時 / スキップ時**: skeptic の失敗は `missing_coverage` に追記して続行。**起動条件（high-risk surface）を満たしたのに未実行だった事実は、失敗・effort/config/scope スキップのいずれでも Step 6 レポートに必ず出す**（silent skip で「守ったつもり」の偽の安心を防ぐ）。

### 4.9 反証レイヤー（adversarial verification / 動的・**meta-reviewer(4.6) と同一 wave**）

冷や読み skeptic の統合後・スコアリングの前に、reviewer の指摘を独立エージェントが反証する。偽陽性を先回りして摘出するフェーズ（`${CLAUDE_PLUGIN_ROOT}/references/triage-dynamic-gates.md` `## 9 反証レイヤー`）。meta-reviewer (4.6) / skeptic (4.8) が見落とし（false negative）を足す係なのに対し、本フェーズは独立読み直しで **severity を較正し偽陽性を摘出する**鏡像（実測は較正が主機能: `severity_inflated` 60% / `refuted` 6%。#114）。skeptic が足した指摘も本レイヤーの対象。

**スキップ条件**（いずれか満たせばスキップし、同一 wave の 4.6 だけを発行する）。**発火は起動有無にかかわらず payload（`fired` + 括弧内の `skip_reason`。起動時は `null`）と Step 6 レポートに記録する。4 つ目を他と同じ値に潰さないこと** — 既定 high では BLOCKER / CRITICAL が 0 件なら対象が構造的に 0 件になるため、潰すと「ゲートが狭いのか対象が無かったのか」を事後に切り分けられない（→ triage-dynamic-gates.md `## 9` / issue #129）:
- userConfig `enable_adversarial_verify` が `false`（`"config"`）
- 実行時 effort = `${CLAUDE_EFFORT}` が `low` または `medium`（`"effort"`）
- `--focus` / `--exclude` でスコープを絞り込んでいる（既検証の再評価を避ける）（`"scope"`）
- 反証対象（triage-dynamic-gates.md `## 9` のゲート）に合致する指摘が 0 件（**`"no-eligible-findings"`**）

**実行する場合**: **Read** `orchestration-dynamic-rounds.md` してその `## 10` の手順に従う（triage-dynamic-gates.md `## 9` の選定ルールで対象を選び、**5 件ずつのバッチ**に分けて反証エージェントを `model: opus`, `effort: high` で並列起動（上限 3 体）。**この一括発行に Step 4.6 の meta-reviewer を含める**（同一 wave）。**reviewer の理由文は渡さない**＝アンカリング防止 → verdict を finding_id で突合して Step 5 のスコアリングに渡す。失敗した指摘は verdict なしのまま続行の best-effort）。**回収した直後に `mark wave` を記録する**（Step 4 と同じ呼び出し。後勝ち。既定 effort ではこのフェーズが最後の agent wave になるため、ここを落とすと `duration_synthesis_min` が反証 wave を丸ごと含む）。レポートに「反証: 対象 N 件 / 係争 M 件 / 取り下げ K 件」を記録（Step 6 で出力）。 **meta 由来指摘の追加バッチ**（`[meta]` タグ付きが反証ゲートに該当する場合のみ 1 体・上限 5 件を直列起動。0 件なら wave は増えない。`## 10` 手順 3.5）を起動したときは、回収直後に再度 `mark wave` を記録する。

### 5. スコアリングとフィルタリング（2軸: confidence × severity）

全 reviewer の指摘を統合し、`${CLAUDE_PLUGIN_ROOT}/references/scoring-guide.md` を Read で読み込んでスコアリングを実施する。

1. **各指摘の base confidence と severity を取得**
   - reviewer 出力の `[confidence: XX]` と `[severity: BLOCKER|CRITICAL|MAJOR|MINOR]` をパース
   - severity が欠落している指摘は **CRITICAL とみなす**（後方互換 / 安全側デフォルト）。**ただし `## コメント推敲提案` ブロックはこの既定の対象外**（severity を持たないのが仕様。指摘として扱わず、手順 7 まで素通りさせる）
   - **この時点の severity 別件数を控える**（= `pre_adjust_counts`。統合・dedup 後、手順 2 以降の verdict 反映・加減算・降格・フィルタを**一切かける前**の生の分布）。Step 6.4 の publish で使う。**手順 5 通過後の件数との差が「調整で消えた分」**であり、これが無いと「reviewer が検出しなかった」と「検出したが調整で消えた」を事後に区別できない（orchestration-measurement.md `## 16`）
   - **base 検算は `pre_adjust_counts` を控えた後に行う**（降格が「調整で消えた分」として会計されるため）。`退行` / 「変更前は X だった」を根拠にする指摘は `git show <base>:<path>` で base 側を検算する（orchestration-guide.md `## 5`「origin 主張の base 検算」。**冷や読み skeptic は reviewer 側の base 確認規約を継承しない**ため、この層の主張が主対象。反証レイヤーは effort ≥ high でしか走らないので、この検算だけが effort 非依存 / #124 (d)）
2. **反証 verdict の反映**（Phase 4.9 が動いた場合のみ。scoring-guide.md `## 反証レイヤーの verdict 反映` に従う）
   - **BLOCKER / CRITICAL の `refuted` は confidence / severity を据え置き**、指摘本文先頭に `⚠️ 反証メモ: <軸>（<根拠 file:line>、要確認）` を付与（**報告から消さない**）
   - **MAJOR / MINOR の `refuted`** は confidence −40（取り下げ理由を付録に記録）、`confirmed` は既存「複数エージェント +15」の発火源（二重計上しない）、`uncertain` は −10
   - verdict が無い指摘（対象外・反証失敗）は no-op
3. **confidence への加算・減算ルールを適用**して 0-100 にクランプ
4. **severity 調整**: `[scope:out]` / `[resolved: ...]` タグ付きは severity を 1 段階下げる（self-review では PR タグは通常出ない。反証 `severity-inflated` もこのルールに統合し二重降格しない）。**BLOCKER / CRITICAL の `severity-inflated` は降格後に報告マトリクスを割る場合のみ据え置き + 反証メモ**（scoring-guide の不変条件。高 severity を silent に消さない）。**MAJOR / MINOR が `severity-inflated` の降格で報告閾値を割って脱落する場合は、`refuted` の −40 脱落と同じく 🔁 付録に取り下げ理由を記録する**（scoring-guide.md `## 反証レイヤーの verdict 反映` / issue #109。降格で消える指摘が silent に落ちない）
4.5. **加減算で報告閾値を割った指摘を控える**（issue #128）: 手順 3〜4 の減算・クランプ・降格の結果、手順 5 の報告マトリクスを通過しなくなる指摘は、**severity を問わず** 🔁 付録に「調整前の (severity, confidence) / 適用した規則名 / 遷移後の値」を記録する。反証由来の脱落（手順 2）と同じ枠に、経路が分かる形で並べる。**反証の対象は既定 high では非対称ゾーン限定（xhigh / max で MAJOR まで拡大）なので、既定 high で MAJOR しか出ない回では本経路が脱落の全量になる**。正本: scoring-guide.md `## 報告閾値を割った指摘の記録`
5. **報告マトリクスでフィルタ**:

   | severity \ confidence | <60 | 60-79 | 80-94 | 95+ |
   |---|:---:|:---:|:---:|:---:|
   | BLOCKER | skip | 報告 | 報告 | 報告 |
   | CRITICAL | skip | skip | 報告 | 報告 |
   | MAJOR | skip | skip | skip | 報告 |
   | MINOR | skip | skip | skip | 報告 |

6. **userConfig 適用**: `review_severity_threshold` (default: `MAJOR`) より低い severity は除外。**`pre_adjust_counts` には各 reviewer の `## below-threshold` の件数を同名 severity のバケツへ足し、`severity_threshold` を併せて記録する**（足し込む分は dedup されないため版で非可換。版マーカー `schema` は**スクリプトが注入する**ので書かない。orchestration-measurement.md `## 16`）
7. **コメント推敲（B 系統）は本ステップを一切通さない**: `## コメント推敲提案` ブロックは手順 1〜6 と反証レイヤー（Phase 4.9）をすべてバイパスして Step 6 にそのまま流す。**severity / confidence を後付けしない**（付けた瞬間マトリクスの対象になり MINOR 95+ と好みクランプ 40 の 2 段で全滅する）。詳細は `prompts/focus/comment-polish.md`。**`review_severity_threshold` も B 系統には効かない**（severity を持たないため。推敲を止めるなら `--exclude comment-accuracy`）。オーケストレーター側で行う調整は次の 2 つだけ:
   - **二重掲載の除去**: **手順 5-6 を通過して Step 6 に残った指摘**と同一 file:line のコメントのみ B から落とす。**「A 系統が指摘として挙げた」だけでは落とさない** — A の冗長コメント指摘は MINOR 95+ で大半が skip されるため、それを理由に B からも消すと A でも B でも出ない（B 系統を作った理由そのものを打ち消す）
   - **掲載上限**: 10 件を超える場合はここで切り、末尾に「他 N 件」と添える（reviewer 側は全件出す規約。発見段階では間引かせない）。`comment_polish.suggested` には**切る前の総数**を入れる

### 6. レポート出力

`missing_coverage` リストが空でない場合は「⚠️ 欠損観点」セクションを追加する（空なら省略）。**理由・補足はこのセクション本文に書き、payload の `missing_coverage` 配列には識別子のみを入れる**（語彙は orchestration-measurement.md `## 16`。自由文を入れると綴りが割れて集計不能になる）。

**冷や読み skeptic の観測可能性（issue #85）**: high-risk surface を含む変更では、冷や読み skeptic（Phase 4.8）の起動有無を「動的ラウンド」行に **必ず** 出す（起動＝追加件数 / 未起動＝skip 理由）。surface HIT かつ未起動の silent skip を作らない。

**skeptic 由来の帰属をレポートまで保つ（`findings_added` の計測妥当性）**: Phase 4.8 の skeptic 指摘に付いた由来タグは、**レポート本文の指摘行にもそのまま残す**（`[confidence][severity]` の後・カテゴリの前に置く）。タグを落とすと **Step 6.4** の publish 時点で由来を再構成できず、`findings_added` が記憶頼みになって系統的に 0 へ潰れる（＝ skeptic の価値率が実態より低く出る）。**由来タグはレポート契約の一部**であり、任意の装飾ではない。

タグは 2 種（正本: orchestration-dynamic-rounds.md `## 9`）。**重複の有無で意味が正反対**になるため混ぜない:

- `[recall-skeptic]` — skeptic 単独由来（reviewer 指摘と重複しなかった）。**fleet 共通盲点を実際に破った＝ skeptic の価値**
- `[recall-skeptic:dup]` — 重複 survivor（reviewer も到達していた）。独立到達の記録としては残すが**盲点でなかった事例で recall の足し前はゼロ**

```
## セルフレビュー結果

**総合判定**: {Approve | Approve with nits | Needs work}（scoring-guide.md「レビュー結論（総合判定）」の表に従う。コミット前ゲートとして「このままコミットしてよいか」の指針）
**総合評価**: X/10 点
**レビュー構成**: Phase 0 (triage) → 探索 (N 起動 / M 成功) → レビュー (N 起動 / M 成功)
**実効上限**: explorer N / reviewer N / specialist N（**実行時** effort `{値}` の上限と規模キャップ `{帯}`（core N files / N lines）の min。どちらが効いたかを明記する）
  ※ reviewer の effort と動的ラウンド（meta / skeptic / 反証ゲート）は**実行時 effort に連動**する。skill frontmatter の effort はオーケストレーター用で別枠
**動的ラウンド**: Round 2 {未実行 | スキップ（unmet 全件が到達不能）| スキップ（unmet をメインで直接照会して解決）| 実行（再起動 reviewer N 体 / 追加 explorer M 体）} / Meta-reviewer {実行（N 件追加）| スキップ理由（`effort` / `config` / `no-high-severity` / `size-tier`）} / 冷や読み skeptic {実行（N 件追加）| skip（理由: effort/config/scope）| 非該当（surface なし）} / 反証 {対象 N 件（うち meta 由来の追加バッチ M 件）| スキップ理由}
**指摘件数**: BLOCKER N 件 / CRITICAL N 件 / MAJOR N 件 / MINOR N 件
**反証**: 対象 N 件 / 係争 M 件（BLOCKER/CRITICAL、本文に反証メモ）/ 取り下げ K 件（MAJOR以下、付録に理由）{**スキップ時もこの行を出す**（書式の正本は orchestration-dynamic-rounds.md `## 10` 手順 4）。`no-eligible-findings` は `未実施（対象帯に該当なし。MAJOR 以下の severity は較正されていない）` と書く — 「対象 0 件」は「検証したが問題なし」と読まれる}

### 🚨 BLOCKER 指摘

1. [confidence: 70][severity: BLOCKER][セキュリティ] Hardcoded secret の疑い
   ファイル: src/config.ts:15
   影響: コミット時にシークレット漏洩

### ⚠️ CRITICAL 指摘

2. [confidence: 95][severity: CRITICAL][バグ] Missing null check
   ファイル: src/utils.ts:42
   影響: 特定入力で関数が落ちる

3. [confidence: 85][severity: CRITICAL][recall-skeptic][バグ] 空文字の draft が numeric 列へ素通りする
   ファイル: src/repo.ts:88
   影響: 22P02 で INSERT が落ちる
   {由来タグ: skeptic 単独由来は `[recall-skeptic]` / reviewer と重複した survivor は `[recall-skeptic:dup]`。Step 6.4 の publish で `findings_added` / `findings_overlap` を数える唯一の根拠なので落とさない。番号は他の指摘と通し連番にする}

### 📋 MAJOR 指摘

4. [confidence: 95][severity: MAJOR][設計] ...

### ✏️ コメント推敲（severity 対象外・採否はあなたが決める）
{`comment-accuracy` が構成に入っていれば（**バンドル相乗りを含む**）必ず見出しを出す（0 件なら「該当なし」。省略すると silent skip と区別できない）。構成に無ければ見出しごと省略し、**diff にコメントの追加・変更があるのに未起動だった場合のみ** `comment-accuracy` を欠損観点に記録する（トリガ不成立の未起動は正常系。記録すると `missing_coverage` の偏り集計が潰れる）。掲載上限 10 件、超過分は末尾に「他 N 件」}

1. src/foo.ts:12 [不要]
   before: `// カウンタをインクリメント`
   after: (削除)
   理由: `count++` が自明でコードの同語反復
{タグは 2 種: `[不要]`=読み手に必要な情報を含まない / `[冗長]`=情報は必要だが表現が冗長。以降も同形式}

### ⚠️ 欠損観点（Agent 失敗による未カバー領域）
- reviewer-security: ネットワーク I/O エラーで失敗 → 認証まわりの観点は未検査
- explorer-<focus>: timeout → 依存していた reviewer-<focus> には探索結果なしで実行

### 🔁 報告閾値を割った指摘（参考・人間が覆せる）
{reviewer が列挙した指摘が報告マトリクスを通過しなかった場合に載る。**経路（反証 verdict / 加減算）を問わず記録し、severity 別の扱いは正本に従う** → scoring-guide.md `## 報告閾値を割った指摘の記録`。0 件なら省略}
- [調整前: confidence XX / severity MAJOR] xxx の指摘
  ファイル: path/to/file:行番号
  脱落理由: <verdict: refuted | severity-inflated> — <軸>（反証根拠 file:line）／ <加減算: 規則名> — confidence XX → YY
  ※ 判断が誤りと思えばこの指摘は有効。再評価してよい

### 総括
- 変更の概要
- コミット前に修正すべき項目（特に BLOCKER）
- 確認推奨の観点
```

**レポートを出力した直後に fleet 区間の終了マーカーを記録する**（Step 7 の修正方針確認＝人間の応答待ちを混ぜないため。orchestration-measurement.md `## 14`。`TS_FILE` は Step 1 と同じ導出式）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" mark t2
```

> **「レポート出力 → `mark t2` → 6.4 の publish」は不可分の締めで、Step 6 はここまで**（GitHub issue #133）。番号は分かれているが 6.4 は独立した任意ステップではない。**publish を踏む前に Step 7（修正方針確認・修正作業）へ進まないこと** — publish は副作用のみで標準出力に何も足さないため、**脱落しても実行中は誰も気づかない**（実測: MAJOR 4 件を報告して全件修正した回が丸ごと欠測になり、meta 起動サンプルを 1 件失った）。ユーザーが事前に「指摘は全部修正して」と伝えている回ほど落ちやすい。

### 6.4. Event Bus publish（`review:completed` / 計測用）

**このステップの直前に `${CLAUDE_PLUGIN_ROOT}/references/orchestration-measurement.md` を Read する**（publish 先の固定・`TS_FILE` のパス導出・区間の算出式・payload 契約の正本。レビュー本体の実行には不要なのでここまで読まない）。

レポート出力後、集計結果を `.claude/events.jsonl` に追記する fire-and-forget の publisher。**embed / 非 embed の両モードで実行する**（LLM 駆動 fan-out の「観点取りこぼし」「severity/confidence のパース安定性」を後から定量化するための計測データを蓄積する目的。review skill と同じ `review:completed` イベントで集計を揃える）。副作用のみで標準出力にレポート文字を足さないため embed mode の出力フォーマット（Step 6.5 の JSON ブロック → marker の順序）には影響しない。self-review は PR を持たないため `pr` は `"local"` 固定とする。

**publish は専用スクリプトで行う**（書込先の固定・所要時間の算出・一時ファイルの掃除をまとめて担当する）。`duration_*` と **`agents.explorer_waves`** は**渡さない** — スクリプトが計測ファイル（explorer wave の打点）から算出して注入する。self-review では `duration_closing_min` を `-1`（測定不能）に固定する:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/publish-review-event.sh" \
  --plugin code-review:self-review --payload '<orchestration-measurement.md `## 16` の self-review 用テンプレートを実値で埋めたもの。effort は '"${CLAUDE_EFFORT}"' の実値>'
```

- スクリプトは payload の JSON 妥当性と **`missing_coverage` の語彙**を検証してから書く（不正なら publish せず `FATAL:` で落ちる。識別子以外＝理由つき自由文は弾かれるので、**理由はレポートの「⚠️ 欠損観点」に書き、フィールドごと落として通さない** / issue #132）。**`measurement_gaps` / `diff_digest` も渡さない**（計測ファイルと一時 diff から算出して注入される）。計測ファイルと diff の一時ファイルもスクリプトが掃除する
- **版マーカーの整数も渡さない**（`schema` / `gate_schema` / `attribution_schema` / `calibration_schema`。v2.65.0 でスクリプト注入に移した — 定数の手書きは version drift 中に落ち、サンプルが逆の版バケツに入る / issue #125）。**渡すのは実行時の事実だけ**で、層のオブジェクト自体（`adversarial_verify` / `recall_skeptic` / `meta_reviewer` / `pre_adjust_counts`）と各層の `fired` は**必ず入れる**（落ちると `measurement_gaps` に `payload:<field>` が立つ）。なお **`tokens` は review 限定**でここには載らない（**publish の後に Step 7 の修正方針確認と修正作業が続くため、窓の外に本作業が残る** / issue #126）。トークンを見たいときは `measure-tokens.sh` を手動実行する（→ 同 `## 17`）
- **報告した指摘を `findings_class` に分類して入れる**（`lint` / `test` / `judgement`。合計は報告件数と一致。分類の基準と「0 件を目標にしない」理由は orchestration-measurement.md `## 16` の「`findings_class` の使い方」）
- **書込先はメインリポジトリのルートに固定される**。self-review は worktree に入らないが、dev-workflow の作業用 worktree 内から実行されると cwd 相対では Step 8 の teardown で消える（→ orchestration-measurement.md `## 13`）。**publish の WARN に `⚠️ 計測:` の追記指示が出たら、レポート末尾にその 1 行を追記する**（#135。explorer の一括発行違反・wave 打点漏れは実行中に何も起きず、しかも打点漏れは違反の証拠自体を消す）

**payload 契約の正本は orchestration-measurement.md `## 16`**（フィールドの意味・版マーカー・後方互換をここに複写しない）。self-review 固有の点のみ:
- `pr` は常に `"local"`（PR を持たない）
- **`duration_closing_min` は常に `-1`（測定不能）**: publish（Step 6.4）が Step 7 の修正方針確認より前にあるため t2→t3 に人間の応答待ちが入らない。0 を publish すると「人間待ちが無かった」と誤読される
- **`duration_min`（全体）の意味は publisher 間で非対称**（review は締めフロー込み / self-review は Step 7 手前まで）。**`plugin` で層別してから比較する**。`head_verified` は publish しない（checkout を行わないため）。`recall_skeptic.skip_reason` は `"scope"`（`--focus`/`--exclude` 指定）も取りうる
- `recall_skeptic.findings_added` / `meta_reviewer.findings_added` はレポートの「動的ラウンド」行の数値と一致させる（それぞれ `[recall-skeptic]` / `[meta]` タグ付き指摘を数える。#121）
- **`comment_polish` は self-review のみのフィールド**（v2.45.0。`fired` / `suggested` の定義と計数基準は orchestration-measurement.md `## 16` が正本）

**publish の直後に `bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-retro.sh"` を実行する**（→ 同 `## 18`。**`--embed` ではスキップ** — Step 6.5 の出力フォーマットに集計テキストを混ぜない）。出力は**そのままレポートの後ろに出す**（要約・再解釈をしない）。**⚠️ シグナル行が出たときだけ**戻り先ドキュメントを示して 1〜2 行の所見を添え、無い回は集計表だけ出す。失敗しても続行（best-effort）。

### 6.5. 構造化 findings JSON（embed mode のみ）

**`--embed` が指定されている場合のみ**、Step 6 の markdown レポート直後に機械可読な findings ブロックを出力する（非 embed 実行では出力しない）。呼び出し元（feature-dev Phase 6 等）はこの JSON を決定的にパースし、markdown の正規表現パースに依存しない。

出力テンプレート・フィールド契約（schema_version: 1）・`<!-- FINDINGS_JSON_START/END -->` マーカーの規約: → orchestration-optional-flows.md `## 15`（embed 分岐でのみ読む）


### 7. 修正方針の確認

**publish 済みかのガード（`--embed` / 指摘 0 件でも必ず実行する / GitHub issue #133）**: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/review-timing.sh" publish-pending` で 6.4 の脱落を捕まえる。**下の skip 条件はこのガードには掛からない** — 本ステップの他の判定（embed / 指摘件数）より前に、レポート出力後 1 回だけ無条件で実行する。**警告が出たら他を中断して 6.4 を先に完了させる**（計測ファイルはまだ残っているので、この時点なら損失なく復旧できる。修正作業に入ってから気づいた回は `duration_min` が欠測に倒れる）。**embed 経路こそ落ちやすい**（publish の後に呼び出し元の作業が続くため）ので、ここを条件分岐の内側に入れない。

**embed mode skip**: 引数で `--embed` が指定されている場合は、上のガードを実行したうえで本ステップの残りを skip する。Step 6 の markdown レポート → **Step 6.5 の構造化 JSON ブロック** → `[embed-mode: findings-only, no-prompt]` の 1 行 marker、の順で出力して完了。AskUserQuestion を呼ばないことで呼び出し元 plugin の UX を阻害しない。

**以下の修正方針フローは**指摘事項が 1 件以上ある場合のみ実行する。指摘が 0 件なら（上のガードを実行したうえで）「問題なし」で完了。

レポート全文を出力し終えた直後に **AskUserQuestion** で修正方針を確認する:
- question: "指摘事項への対応方針を選択してください（コミット前の作業優先度を整理します）"
- header: "修正方針"
- options:
  1. label: "すべて修正" / description: "指摘事項をすべて今すぐ修正する"
  2. label: "BLOCKER/CRITICAL のみ" / description: "severity BLOCKER または CRITICAL の指摘だけ修正する"
  3. label: "このまま" / description: "修正はせず、このままコミットする"

各選択肢の後処理:
- **すべて修正**: 全指摘を一覧化し、ファイルごとにまとめて修正を実施する
- **BLOCKER/CRITICAL のみ**: 該当 severity の指摘のみ再表示し、ファイルごとにまとめて修正を実施する
- **このまま**: 完了（BLOCKER 指摘が 1 件以上残っている場合は「BLOCKER 指摘を残したままコミットしますか？」と AskUserQuestion で再確認する）

**訂正の伝播前ガード（over-correction 防止 / GitHub issue #71）**: findings をコード/文書本文に**反映する前に**、その修正が依拠する load-bearing な事実主張を一次ソースで再確認する。判定ルール（repo で確認できる/できない主張の扱い・暫定入力の非伝播・1 箇所先行確認・複数観点の独立一致）の詳細: → orchestration-optional-flows.md `## 12`

**修正の指針（Fix the code, not the reviewer）**: 「分かりにくい」「誤解を招く」「意図が読めない」系の指摘に対しては、説明コメントを足して取り繕うのではなく、**コード・命名・型・構造そのものを直して解消する**ことを優先する。将来の読み手（半年後の自分・別コンテキストの Claude）も同じ箇所でつまずくため（Google eng-practices "Handling reviewer comments: fix the code, not the reviewer"）。

### 8. worktree teardown 連携（非 embed のみ）

レビュー完了後に作業用 worktree（dev-workflow:worktree-setup で作成。識別マーカー: worktree 内の `envs/.backend.env.worktree`）が放置されるのを防ぐ後片付け。Step 7 の修正方針フロー（修正を選んだ場合はその実施）まで**すべて完了した後**の最終ステップとして実行する（teardown は cwd＝worktree 自体を削除するため、後続ステップを残した状態で起動してはならない）。

**発動条件（すべて満たす場合のみ。欠けたら silent skip）**:

1. `--embed` 指定なし（embed mode では呼び出し元の UX を阻害しないため skip）
2. worktree 内で実行中: `git rev-parse --git-dir` ≠ `git rev-parse --git-common-dir`
3. worktree-setup 由来である: `[ -f envs/.backend.env.worktree ]`（マーカーの無い無関係な worktree でレビューのたびに削除プロンプトを出さない）
4. 未コミット変更が無い: `git status --porcelain` が空（self-review はコミット前ゲートであり、指摘修正やコミット前の作業が残る状態で削除を提案するのは 1 手早い。dirty なら黙って skip する）
5. dev-workflow が**有効**である:
   ```bash
   DEV_WORKFLOW=0
   for f in "$HOME/.claude/settings.json" ".claude/settings.json" ".claude/settings.local.json"; do
     grep -Eq '"dev-workflow@[^"]*"[[:space:]]*:[[:space:]]*true' "$f" 2>/dev/null && DEV_WORKFLOW=1
   done
   ```
   キー存在だけを見る grep は使わない（`": false"` の無効化済みを導入済みと誤判定し、project-scoped 有効化を取りこぼすため。enabled-only 判定）

発動時、**AskUserQuestion** で削除の意思を確認する（worktree・DB・env は git で復元できない不可逆操作のため、「止めない」原則の例外として確認する。teardown 自身は clean tree の `git worktree remove` を確認なしで実行するため、削除の同意は必ずここで取る）:

- question: "この worktree での作業は完了していますか？worktree を削除（teardown）できます"
- header: "worktree"
- multiSelect: false
- options:
  1. label: "残す" / description: "worktree を維持する（マージ・push 等が残っている場合はこちら）"
  2. label: "削除する" / description: "dev-workflow:worktree-teardown を起動して DB / port / worktree を片付ける"

「削除する」が選ばれたら `Skill` tool で `dev-workflow:worktree-teardown` を起動する。プロセス kill / DB drop / `--force` remove の個別確認は teardown 側の cleanup チェックリストに従う。
