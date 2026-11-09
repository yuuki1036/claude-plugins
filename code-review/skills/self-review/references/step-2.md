### 2. Phase 0: トリアージ

`${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` を Read で読み込み、そのロジックに従ってエージェント構成を決定する。

**Phase 0 はメインコンテキストで実行する（Agent ツールは使わない）。**

#### 2.1 Stage 1: タイプ判定

diff の特性を分析し、必要なエージェントタイプを判定する（`--since` の回は explorer・reviewer の観点を `## delta` の中の `###` の節で判定する。spec-compliance と Markdown 推敲の判定は従来どおり / triage-guide.md `### 6.5`）:
- **explorer**: 巨大ファイル、複数関数、条件分岐追加、共通モジュール変更のいずれかに該当するか
- **reviewer**: 常に必要。diff パターンマッチでどの観点が必要かを判定
- **spec-compliance**: 自分で判定しない。Step 2.2 の plan が仕様ソース（session-context / Issue ファイル / `--spec` / `--spec-source` / repo の仕様書）から決める（`--activated` に入れると plan が exit 2 で止まる / GitHub issue #351）。repo の仕様書は、diff が触ったものと session-context・Issue ファイルが言及したものを plan が自分で探す（GitHub issue #352。diff が仕様書を触っただけでも起動する）
- **Markdown 推敲**: `## md-polish` と引数から起動するかを決める（**effort を問わない・体数の上限の外**）。起動するなら `md-polish-guide.md` を Read する。判定表と `skip_reason` の正本は同 guide の 1 節
- **決定系 doc の design-review 委譲**: `## decision-docs` に doc の行（`<数>\t<path>`）があれば `design-review-guide.md` を Read し、1 節で起動するかを決める（**体数の上限の外**。呼ぶのは Step 6.4 の後）。起動するなら、委譲する doc を doc-substance のプロンプトの可変部に「design-review に渡す doc: <path>」と書く

#### 2.2 Stage 2: 体数・フォーカス・冗長度決定

reviewer の体数・単独か束ねか・落とす観点は**自分で数えず**、`plan-reviewers.sh plan` に決めさせる（GitHub issue #351。triage-guide の表を読んで数えた回に、high の上限 6 を 5 と数え、仕様ソースがあるのに spec-compliance より security を先に取った）:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/plan-reviewers.sh" plan --effort "${CLAUDE_EFFORT}" --size-tier <Step 1 の size_tier> \
  --activated <Stage 1 で起動条件を満たした観点をカンマ区切り> \
  [--spec <path>] [--spec-source knowledge:<path>] [--focus <観点> | --exclude <観点>] [--prior <観点>] [--delta]
```

- `--activated` には最小保証の 2 体と spec-compliance を入れない（前者は plan が足す。後者は入れると exit 2 — 仕様ソースから plan が決める）
- `spec_source` の `repo-spec-touched`（diff が触った仕様書）/ `repo-spec-ref`（session-context・Issue ファイルが言及した仕様書）は plan が Step 1 の diff と参照から見つける。引数では渡さない
- `## prior-fixes` が出た回は `--prior <行の観点をカンマ区切り>` を渡す（`--focus` の回も。前回の対象は絞り込みの外に置き、上限に収まらなければ落とさず相乗りにする / prior-fixes-guide.md の 1 節）。`--since` の回（`scope_mode=delta`）はさらに `--size-tier` に `delta_size_tier` を渡して `--delta` を足す（前回の対象は規模キャップの外の専任になり、effort 上限を超える分は相乗りになる / triage-guide.md `### 6.5`）
- **delta が空（`delta_files=0`）の回は plan も check も呼ばない**。triage-guide.md `### 6.5` のとおり、前回の対象の観点の reviewer だけで直ったかを確かめる（前回の対象も無ければ agent を起動しない）。plan は最小保証と仕様ソースの spec-compliance を必ず足すので、この回の構成を表せない
- 出力の読み方（kind・`piggyback`・`dropped` の理由・`excluded`・`spare`）と check の規則の一覧は triage-guide.md `## 4` 末尾の「plan の出力の読み方」。`dropped` の観点は `missing_coverage` に識別子で記録し、理由をレポートの「⚠️ 欠損観点」に写す
- explorer と specialist の体数は従来どおり triage-guide で決める。上限は出力の `explorer_cap` / `specialist_cap`（effort 上限と規模キャップの min）
- exit 2 は引数の誤り（理由は stderr）。直して呼び直す

数値を含まない規則は従来どおり:
- explorer は独立した探索対象の数に比例させる。冗長ペア（x2）を組むのは `redundant_pairs=allowed`（xhigh / max）の回だけで、high 以下でペア条件が成立したら Angle A/B を 1 体に内挿する
- `cap_source=size`（規模キャップが effort 上限を下回った）回は、Round 2（Phase 4.5）を effort に関わらず 1 段圧縮経路にする。reviewer 個々の effort・meta-reviewer・skeptic・反証レイヤーは削らない（削るのは breadth のみ。triage-guide.md `## 6.3`）

#### 2.3 観点カバレッジ検算と構成テーブル出力

**構成テーブルを確定する前に、起動前検算をする（orchestration-guide `### 8a`・毎回。delta が空で plan を呼ばない回（Step 2.2）だけは検算せず、レポートの「実効上限」「仕様整合」には `delta が空・前回の対象のみ` と書く）**: 観点判定表の各条件を diff シグナルに対して再評価し、条件を満たすのに構成に入っていない focus があれば、`--activated` に足して plan を引き直してから確定する（テーブルに直接書き足さない。spec-compliance は足さない — plan が仕様ソースから決める）。v2.39.0 で旧 Phase 4.7 の補完起動から前倒し（起動後の直列 wave を無くすため。検算内容は同一）。`--focus` / `--exclude` を指定した回は、指定した範囲の観点だけを検算する。

確定したテーブル（plan の `reviewer` / `piggyback` / `dropped` の行。xhigh / max で冗長ペアを組んだらその行も足す）を `check` に流してから起動する:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/plan-reviewers.sh" check <<'TABLE'
<確定テーブルの行>
TABLE
```

`ok`（exit 0）なら確定。exit 1 なら `NG	<規則>	<詳細>	<直し方>` の行に従って直し、もう一度 check する（`spec-missing` = 仕様ソースがあるのに spec-compliance の単独の行が無い / `over-cap` = 上限超過 / `wrong-reason` = 落とした理由が plan と違う、など）。上限を超えたか・spec-compliance が欠けたかを自分で判定して check を飛ばさない。exit 2 は plan が無い（Step 1 の triage-signals.sh が前の回の plan を消す）か、テーブルの形が違う。

検算後、triage-guide.md の出力フォーマット（`## 5`）に従い、エージェント構成テーブルを出力する。**「直列 wave」行を必ず含める**（見積もり方は triage-guide.md `## 5.1`）— 体数はトークンコストのレバー、wave 数は壁時計のレバーで、後者だけが従来ユーザーから見えなかった（GitHub issue #100 B）。

#### 2.4 high-risk surface 判定（冷や読み skeptic の相乗り判断 / 常時実行）

Phase 0 の最後に、triage-dynamic-gates.md `## 8.5` の surface 判定（diff への正規表現 grep。self-review は PR を持たないため自己申告経路は無い。`--since` の回は `## delta` の `### surface` で判定する）を **必ず実施** する。安価な grep なので構成に関わらず常に行う（silent skip 防止・issue #85）。

- surface=true **かつ Phase 4.8 のスキップ条件（userConfig / effort / `--focus`・`--exclude` によるスコープ絞り込み）のいずれにも該当しない**場合、skeptic を **Step 4 の reviewer 一括発行に相乗りさせる**（同一メッセージ内で発火。1 wave 削減）。**条件は個別に列挙せず Phase 4.8 の定義を参照すること**（Step ごとにファイルを読む構成では 4.8 の本文をまだ読んでいないので、この時点で `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-4.8.md` のスキップ条件を Read して判定する / GitHub issue #426）（相乗りで起動が前倒しされるため、4.8 に到達してからスキップ判定しても手遅れ）
- surface=true だがスキップ条件に該当する場合は、`skip_reason` を記録して Step 6 レポートと payload に出す（従来どおり）
- reviewer の `[surface:high-risk]` フラグ由来で事後に surface=true になる経路は Phase 4.8 の fallback で拾う

**次は Step 3**（SKILL.md に戻り、その見出しを見る）
