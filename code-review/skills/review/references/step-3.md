<!-- 正本依存（SSoT pin）。この Step の本文が要約している正本。正本が変わったら本ファイルへの伝播を確認して pin を書き換える。`--update-ssot-pins` は repo 全体の pin を一括で打ち直すので、全消費サイトを確認したときだけ使う -->
<!-- SSOT: code-review/references/orchestration-measurement.md#16 @2a27f9ea -->
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
- **spec-compliance**: 自分で判定しない。Step 3.2 の plan が仕様ソースから決める（`--activated` に入れると plan が exit 2 で止まる / GitHub issue #351）。repo の仕様書は、diff が触ったものと session-context・Issue ファイル・PR 本文・PR に紐づく GitHub Issue の本文が言及したものを plan が自分で探す（GitHub issue #352 / #391。PR 本文は `--pr` を渡せば plan が Step 1 の PR コンテキストから読む。紐づく Issue の本文は `--pr-issue-body` で渡したものを読む）

Step 1 で Read した PR コンテキスト（説明・issue コメント・レビューサマリ・行単位コメント）もタイプ判定の参考にする（例: 説明に「セキュリティ修正」、行単位コメントで認可周りが議論されている → security reviewer を追加）。

#### 3.2 Stage 2: 体数・フォーカス・冗長度決定

**default-mode の回だけ**、reviewer の体数・単独か束ねか・落とす観点を**自分で数えず** `plan-reviewers.sh plan` に決めさせる（GitHub issue #351。triage-guide の表を読んで数えた回に、high の上限 6 を 5 と数え、仕様ソースがあるのに spec-compliance より security を先に取った）。それ以外のモードはモードの推奨構成に従い、構成を決めるためには plan も check も呼ばない。ただし spec-compliance を起動するモード（skip-mode など）は、仕様ソース（Issue ファイル・紐づく Issue の本文が言及した仕様書）を得るために plan を呼び（`--pr` / `--size-tier` と、仕様ソースの引数 `--issue-id` / `--spec-source` / `--pr-issue-body`。`--activated` は空でよい）、`spec_source` の行だけを使う（構成の行は読まず、check も呼ばない / orchestration-optional-flows.md `## 2`）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/plan-reviewers.sh" plan --pr <PR番号> --effort "${CLAUDE_EFFORT}" --size-tier <Step 2 の size_tier> \
  --activated <Stage 1 で起動条件を満たした観点をカンマ区切り> --issue-id <## issue-ids の ID>... \
  [--spec-source pr-issue:#N --pr-issue-body <本文を保存したファイル>]... [--spec-source knowledge:<path>]
```

- `--activated` には最小保証の 2 体と spec-compliance を入れない（前者は plan が足す。後者は入れると exit 2 — 仕様ソースから plan が決める）。`--issue-id` は `## issue-ids` の ID ごとに 1 つ（PR の head / base のブランチ名から取った ID。plan は worktree の今のブランチ名からも取る）
- 出力の読み方（kind・`piggyback`・`dropped` の理由・`spare`）と check の規則の一覧は `${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` の `## 4` 末尾「plan の出力の読み方」。`dropped` の観点は `missing_coverage` に識別子で記録し、理由をレポートの「⚠️ 欠損観点」に写す
- explorer と specialist の体数は従来どおり triage-guide で決める。上限は出力の `explorer_cap` / `specialist_cap`
- exit 2 は引数の誤り（理由は stderr）。直して呼び直す

数値を含まない規則は従来どおり:
- explorer は独立した探索対象の数に比例させる。冗長ペア（x2）を組むのは `redundant_pairs=allowed`（xhigh / max）の回だけで、high 以下でペア条件が成立したら Angle A/B を 1 体に内挿する
- `cap_source=size`（規模キャップが effort 上限を下回った）回は、Round 2（Step 5.5）を effort に関わらず 1 段圧縮経路にする。reviewer 個々の effort・meta-reviewer・skeptic・反証レイヤーは削らない（規模キャップが削るのは breadth のみ。triage-guide.md `## 6.3`）

#### 3.3 観点カバレッジ検算と構成テーブル出力

**構成テーブルを確定する前に、起動前検算をする（orchestration-guide `### 8a`・default-mode のみ構成追加）**: 観点判定表の各条件を diff シグナルに対して再評価し、条件を満たすのに構成に入っていない focus があれば、`--activated` に足して plan を引き直してから確定する（テーブルに直接書き足さない。spec-compliance は足さない — plan が仕様ソースから決める）。v2.39.0 で旧 Phase 5.7 の補完起動から前倒し（起動後の直列 wave を無くすため。検算内容は同一）。確定したテーブル（plan の `reviewer` / `piggyback` / `dropped` の行。xhigh / max で冗長ペアを組んだらその行も足す）を `check` に流してから起動する:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/plan-reviewers.sh" check --pr <PR番号> <<'TABLE'
<確定テーブルの行>
TABLE
```

`ok`（exit 0）なら確定。exit 1 なら `NG	<規則>	<詳細>	<直し方>` の行に従って直し、もう一度 check する。上限を超えたか・spec-compliance が欠けたかを自分で判定して check を飛ばさない。exit 2 は plan が無い（Step 2 の triage-signals.sh が前の回の plan を消す）か、テーブルの形が違う。

**非 default-mode の回**: Stage 0 で `default-mode` 以外（`--emergency` / `doc-review-mode` / `dba-mode` / `supply-chain-mode` / `skip-mode`）に確定した回は、モードの推奨構成が観点判定表より優先するため、**構成を決めるためには plan も check も呼ばず、検算で構成も足さない**（spec-compliance を起動するモードが仕様ソースを得るために plan を呼ぶのは別。Step 3.2 の但し書き / GitHub issue #389）。検出した focus は `missing_coverage` に識別子 `<focus>` だけを記録する（**mode による意図的な縮退である旨はレポート本文へ**）。

**決定系 doc の design-review 委譲**: `## decision-docs` に doc の行（`<数>\t<path>`）があれば `design-review-guide.md` を Read し、1 節で起動するかを決めて構成テーブルに `design-review` の行を足す（**体数の上限の外**。呼ぶのは締めフロー 4 の後）。起動するなら、委譲する doc を doc-substance のプロンプトの可変部に「design-review に渡す doc: <path>」と書く。

検算後、triage-guide.md の出力フォーマット（`## 5`）に従い、エージェント構成テーブルを出力する。**「直列 wave」行を必ず含める**（見積もり方は triage-guide.md `## 5.1`）— 体数はトークンコストのレバー、wave 数は壁時計のレバーで、後者だけが従来ユーザーから見えなかった（GitHub issue #100 B）。

#### 3.4 high-risk surface 判定（冷や読み skeptic の相乗り判断 / 常時実行）

Phase 0 の最後に high-risk surface 判定を **必ず実施** する（安価なので構成に関わらず常に行う。silent skip 防止・issue #85）。**判定は Step 2 のダイジェスト `## surface` をそのまま読み、この判定のために triage-dynamic-gates.md を Read しない**（v2.60.0。分冊の Read は diff サイズと無関係な固定費で、小 PR では支配的になる）。ダイジェストに当該セクションが無い場合のみ定義の正本として `triage-dynamic-gates.md ## 8.5` を読む。**PR 自己申告 D1-High はダイジェストに含まれない**ので、Step 1 で Read 済みの PR コンテキスト（本文・ラベルの高リスク申告）から判定し、正規表現ヒットと **OR** で結合する。

- surface=true **かつ Phase 5.8 のスキップ条件（userConfig / effort / `--emergency`・`skip-mode`）のいずれにも該当しない**場合、skeptic を **Step 5 の reviewer 一括発行に相乗りさせる**（同一メッセージ内で発火。1 wave 削減）。**条件は個別に列挙せず Phase 5.8 の定義を参照すること** — 相乗りで起動が前倒しされる以上、5.8 に到達してからスキップ判定しても手遅れ（agent は既に走っている）。列挙の取りこぼしは `--emergency` で `effort: max` の skeptic が余計に走る事故に直結する
- surface=true だがスキップ条件に該当する場合は、`skip_reason` を記録して Step 7 レポートと payload に出す（従来どおり）
- reviewer の `[surface:high-risk]` フラグ由来で事後に surface=true になる経路は Phase 5.8 の fallback で拾う

**次は Step 4**（SKILL.md に戻り、その見出しを見る）
