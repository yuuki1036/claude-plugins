# Plugin Handoffs（optional plugin 連携の詳細手順）

feature-dev の Phase 1.3 / 1.4 / 1.6 / 4.5 は、対応する optional plugin（または外部 CLI）が利用可能なときだけ通る handoff branch。SKILL.md 本文はそれぞれ「検出 → 該当すれば本ファイルの該当節を読んで従う / 非該当なら skip」に留め、詳細手順をここに置く（大半のセッションでは読まれない dormant branch なので、progressive disclosure で本文から分離している）。

本文が検出に使う変数（`BDD_SPEC_AVAILABLE` / `VAULT_AVAILABLE` / `DESIGN_DOC`）と、後続 Phase が消費する出力変数（`BDD_SPEC_PATH` / `VAULT_KNOWLEDGE` / `DESIGN_DOC_PATH`）は本文側に定義がある。ここではそれらがセット済み・該当プラグインが利用可能である前提で手順を書く。

---

## Phase 1.3: BDD Spec Creation (bdd-spec)

**Goal**: If `bdd-spec` plugin is installed, create a BDD `spec.md` (Feature / Scenario / Examples) as the authoritative requirements for downstream phases, then pass its path forward.

**Why this phase exists**: 「曖昧な Issue から実装が暴走する」失敗パターンを構造的に潰すため、Phase 4 architect が **spec.md を真実として読む** 構造に切り替える。bdd-spec 未インストール時は何もしない（後方互換）。

### Step 2: Check existing spec

ユーザーが既に spec.md を持っている場合は再生成しない:

1. 初期リクエストに `spec=<path>` が含まれていればそれを採用（Phase 4 へそのまま渡す）
2. 引数から user story の要素（`role` / `want` / `why`）が推測可能なら次の Step へ
3. 推測できない場合は Phase 1 で集めた discovery 情報から要素を抽出してユーザーに確認

### Step 3: Propose create-spec invocation

`AskUserQuestion` で確認:

- question: "bdd-spec plugin が利用可能です。BDD spec.md を Phase 4 architect の入力として生成しますか？"
- header: "BDD spec 生成"
- options:
  1. label: "生成する (推奨)" / description: "bdd-spec:create-spec を呼んで spec.md を作成。architect は spec を真実として読む"
  2. label: "skip" / description: "BDD spec を生成せず既存の Issue 解釈フローで進む"

### Step 4: Invoke bdd-spec:create-spec

ユーザーが「生成する」を選んだら `Skill` tool で `bdd-spec:create-spec` を呼ぶ。

**非対話 API（bdd-spec の安定保証セクション参照）に従い引数で値を渡す**:

- `role=<discovery で得た role>`
- `want=<discovery で得た want>`
- `why=<discovery で得た why、不明なら省略>`
- `shortPath=<true / false>` (省略時は bdd-spec 側設定に従う)

引数で全要素が埋まっていれば bdd-spec 側は AskUserQuestion を発火せず非対話実行する。

**Skill 呼び出し後**:
- 生成された spec.md のパス（`features/{dirname}/spec.md`）を `BDD_SPEC_PATH` 変数に保持
- Phase 1.7 トリアージへの signal: spec.md 完備 → explorer count を控えめに（spec の Scenario が要件を明確化しているため）

### Step 5: Fallback handling

- bdd-spec:create-spec が失敗（例: bdd-spec plugin の version 不整合、内部エラー）→ warning を出して fallback。Phase 1.5 以降は既存フローで継続
- ユーザーが skip を選択 → そのまま Phase 1.5 へ

### Output

- `BDD_SPEC_PATH=<path>` または `BDD_SPEC_PATH=""`（未生成）
- Phase 4 architect prompt の "BDD Spec Injection" に `BDD_SPEC_PATH` を渡す
- Phase 1.7 トリアージで Issue context completeness の判定材料に使う

---

## Phase 1.4: BDD Spec Evaluation (bdd-spec:evaluate-spec)

**Goal**: Phase 1.3 で spec.md を生成した場合、それを architect の入力にする前に品質ゲートを通す。網羅性（同値分割表 ⇔ Scenario）・トレーサビリティ（epic AC ⇔ Scenario）の穴を実装着手前に潰す。

**Why this phase exists**: 生成直後の spec は「もっともらしいが穴がある」状態になりやすい（AC に対応する Scenario 欠落・同値クラスの未カバー）。穴のある spec を真実として Phase 4 architect に渡すと、その穴が実装に伝播する。安いオラクル（機械的なリンク・表セル検証）を実装の前に挟む（Clearwing 原則 8）。bdd-spec 未インストール、または Phase 1.3 を skip した場合は何もしない（後方互換）。

### Step 1: Applicability check

- Phase 1.3 で `BDD_SPEC_PATH` が空（spec 未生成 / bdd-spec 未インストール / ユーザーが skip） → **Phase 1.4 を skip して Phase 1.5 へ**
- `BDD_SPEC_PATH` がセットされている → 次の Step へ

### Step 2: Invoke bdd-spec:evaluate-spec (embed)

`Skill` tool で `bdd-spec:evaluate-spec` を呼ぶ。安定 API に従い引数で対象と embed を渡す:

- `spec=<BDD_SPEC_PATH>`（Phase 0 の対象選択をスキップ）
- `--embed`（evaluate-spec 側の Phase 6 AskUserQuestion をスキップし、Phase 5 レポートをそのまま返す）

### Step 3: Gate on findings

- 🔴 critical（未カバー AC・リンク切れ・構文破綻）が 1 件以上 → **ユーザーに提示して確認**する。AskUserQuestion で「spec を修正してから設計に進む（推奨）/ このまま進む」を選ばせる。spec の穴は architect が読む前に埋めるのが安いため、修正を既定に置く
- 🟡 major 以下のみ → レポートを情報として提示し、そのまま Phase 1.5 へ進む（ブロックしない）
- 指摘 0 件 → 「spec は契約として妥当」と一言添えて Phase 1.5 へ

### Step 4: Fallback handling

- bdd-spec:evaluate-spec が失敗（version 不整合・内部エラー）→ warning を出して fallback。評価をスキップして Phase 1.5 へ継続する（評価は best-effort。設計フロー自体はブロックしない）

---

## Phase 1.6: Vault Recall (kvault)

**Goal**: 過去プロジェクト横断の知見（落とし穴・設計判断・移行ノウハウ）を knowledge vault から recall し、Phase 4 architect の入力に注入する。

**Why this phase exists**: recall 系の tool 呼び出しはモデルの文脈判断に任せると省略されうる（Opus 4.8 世代で顕著。Opus 5 でも「引くかどうか」を毎回モデル判断に委ねる理由はない）。設計着手の直前に **必須ステップ** として埋め込むことで「引き忘れ」を構造的に防ぐ。注入された知見は authoritative ではなく **advisory（参考情報）** で、現コードベースのパターンと矛盾する場合は現コードベースを優先する。

### Step 2: Build a keyword query（自然文ではなくキーワード寄せ）

Phase 1 discovery + Phase 1.5 Issue context から、設計判断に効きそうな **名詞・技術語を空白区切りで並べる**。

**運用知見（必読）**: vault の embedding は **JP の自然文クエリに弱い実測がある**。文章ではなく「`Prisma 初期化 マイグレーション ロールバック`」のような **キーワード列** にする。フレームワーク名・モジュール名・課題ドメイン語を優先する。

### Step 3: Execute recall

```bash
# stderr（HF token warning / weights loading progress）は捨て、stdout の JSON のみ取得する
kvault recall "<キーワード列>" --top 5 --min-sim 0 2>/dev/null
```

出力は JSON: `{ "query", "count", "results": [ { "path", "title", "similarity", "tags", "excerpt" }, ... ] }`。`--min-sim 0` で足切りせず top 5 を全件取得する（足切りは次の Step で rank ベースに行う）。

### Step 4: Relevance judgment（rank + gap、絶対閾値で切らない）

**運用知見（必読）**: `similarity` の絶対値は **クエリによって水準が変わる**（あるクエリでは 1 位が 60、別クエリでは 1 位が 35 のように）。だから **絶対閾値で足切りしない**。

判断は **rank + 1 位からの similarity gap** で行う:

- 1 位を基準に、後続の similarity が **大きく gap を開けて落ちたところ** を関連の切れ目とみなす
- gap が開かず緩やかに下がるだけなら top 全件を関連候補として残す
- 1 位ですら excerpt が明らかに無関係（別ドメイン）なら 0 件として扱ってよい

関連ありと判断した知見の `path` / `title` / `excerpt` を保持する。

### Step 5: Hand to Phase 4

- 関連知見を `VAULT_KNOWLEDGE` として保持（各エントリ: `path` + `title` + `excerpt` の 1〜2 行要約）
- 関連 0 件なら `VAULT_KNOWLEDGE=""`（注入なし）として Phase 1.7 へ
- Phase 4 architect prompt の "Vault Knowledge Injection" に `VAULT_KNOWLEDGE` を渡す

### Output

- `VAULT_KNOWLEDGE=<関連知見の要約>` または `VAULT_KNOWLEDGE=""`（未取得 / 関連なし / skip）
- Phase 1.7 へ進む

---

## Phase 4.5: Design Doc Export (design-doc)

**Goal**: Phase 4 の architect 比較とユーザー採用決定（プロンプト内で揮発する）を design doc として `.claude/designs/` に永続化する

**Why this phase exists**: architect 出力（代替案トレードオフ比較・採用案 blueprint）はセッション終了で消える。design doc 化しておくと、後続の同領域開発の参照元・実装後の as-built 記録（`phase: target → current`）として再利用できる。design-doc 未インストール時は何もしない（後方互換）。

**Actions**:

1. `DESIGN_DOC=1`（本文で判定済み）のとき **AskUserQuestion** で確認:
   - question: "採用した設計を design doc として永続化しますか？"
   - header: "design doc"
   - options:
     1. label: "永続化する (Recommended)" / description: "採用案 + 代替案比較を .claude/designs/ に export（後続開発の参照元・実装後の as-built 記録になる）"
     2. label: "skip" / description: "doc 化せず実装に進む（architect 出力はセッション限り）"
2. 「永続化する」選択時、`Skill` tool で `design-doc:design-doc` を **export 非対話 API**（design-doc の export API 安定保証セクション参照）で呼ぶ:
   - `mode=export` / `title=<feature の要約タイトル>` / `content=<採用案 blueprint + 全 architect 案のトレードオフ比較 + Phase 3 grill で確定した前提>`
   - `spec=<BDD_SPEC_PATH>`（Phase 1.3 で設定済みなら）/ `issue=<Issue ファイルパス>`（Phase 1.5 で検出済みなら）
   - 引数が全て埋まっていれば design-doc 側は AskUserQuestion を発火しない（非対話実行）
3. 生成された doc パスを `DESIGN_DOC_PATH` として保持し、Phase 7 のサマリに含める
4. fallback: 呼び出し失敗時は warning を出して Phase 5 へ続行する（doc 化は任意機能。実装フローを止めない）
