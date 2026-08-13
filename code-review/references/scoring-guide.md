# 2軸スコアリングガイド（confidence × severity）

## 設計思想

レビュー指摘の品質は **2 つの独立した軸** で判定する:

1. **confidence (確信度)** — *指摘が事実として正しい確率*。0-100。reviewer が証拠（diff・ファイル Read・explorer 結果）でどれだけ裏付けられるか
2. **severity (重大度)** — *指摘が現実に与える影響の大きさ*。BLOCKER / CRITICAL / MAJOR / MINOR の 4 段階。「もしこの指摘が当たっていた場合に何が起きるか」で判定

2 軸化により **「BLOCKER は不確実でも報告」「MINOR はほぼ確実な時だけ報告」** という非対称な報告ルールを表現できる（単一軸で起きるジレンマの整理: `design-notes/scoring-rationale.md`）。

---

## confidence (確信度) の定義

| スコア | 確信度 | 説明 |
|--------|--------|------|
| 0 | なし | 偽陽性、または既存の問題（今回の変更で導入されていない） |
| 25 | 低 | 可能性はあるが偽陽性かもしれない。規約に明記なし |
| 50 | 中 | 実際の問題だが nitpick または稀 |
| 75 | 高 | 検証済みの問題。実際に発生する |
| 100 | 確実 | 確実にバグ。証拠あり。高頻度で発生 |

reviewer が証拠（diff、ファイル Read、explorer 結果、ドキュメント参照）を踏まえて値を決める。**境界値（75-85）や他 reviewer と矛盾する場合は段階的に検討**（reviewer-prompts.md の共通指示を参照）。

---

## severity (重大度) の定義

| レベル | 説明 | 典型例 |
|--------|------|--------|
| **BLOCKER** | 本番投入で**確実に重大事故**になる。データ損失・セキュリティ脆弱性・サービス停止級 | SQL/コマンドインジェクション、シークレットの commit、データ削除、本番 DB の破壊的マイグレーション、認証バイパス |
| **CRITICAL** | 機能不全・重大な誤動作・パフォーマンス崖。ユーザー影響あり | Null 参照で落ちる、無限ループ、race condition、N+1 で API が止まる、CLAUDE.md 明示違反、暗号化の誤用 |
| **MAJOR** | 設計上の問題・将来のバグ温床・保守性悪化。当面は動くが負債化 | エラーハンドリング欠落、型設計の不変条件破れ、API 破壊的変更（軽微）、テスト不足、cross-cutting 影響 |
| **MINOR** | 改善提案・スタイル・微小な可読性・nitpick | 命名統一、コメント不一致、軽微な pattern-consistency、自明な refactor 提案 |

### severity 付与の原則

- **「もし指摘が真なら何が起きるか」で判定する**（confidence と独立）
- **付与の前に base 状態を確認する**（`prompts/reviewer-common.md`「severity を付ける前に: base 状態の確認」/ GitHub issue #114）。PR が触れていない不備は除外、PR 前から同じ・PR が意図した変更は 1 段階下げてから申告する。**影響を先に見積もってから base を見ると過大評価が入る**（実測値の正本: `design-notes/scoring-rationale.md`）
- **降格される典型 4 型**（同ファイルの「降格される典型パターン」/ v2.62.0・GitHub issue #123 A）: base 由来 / 読み違え / 影響の過大見積もり / カテゴリの取り違え。**反証レイヤーの verdict の過半が `severity_inflated`** という実測を受けて、下流で降格するより上流で severity 定義を精密にする方針。オーケストレーター側の調整規則（下記「severity 調整ルール」）は変えていない — reviewer が理由欄に降格の型を書くので、**二重適用ガードは従来どおり理由欄の記載で判別する**
- セキュリティ・データ整合性・本番事故に直結するものは原則 BLOCKER または CRITICAL
- 「動くけど将来困る」系は MAJOR
- 「あれば良い」程度は MINOR
- 観点ごとの目安は `prompts/focus/<focus>.md`に記載

---

## 報告マトリクス（フィルタリングルール）

報告対象は **severity と confidence の組み合わせ** で決まる:

| severity \ confidence | <60 | 60-79 | 80-94 | 95+ |
|---|:---:|:---:|:---:|:---:|
| **BLOCKER** | skip | **報告** | **報告** | **報告** |
| **CRITICAL** | skip | skip | **報告** | **報告** |
| **MAJOR** | skip | skip | skip | **報告** |
| **MINOR** | skip | skip | skip | **報告** |

### 設計意図

- **BLOCKER は confidence 60+ で報告**: 不確実でも「人間に確認してもらう価値がある」という判断。見落とした時の代償が大きすぎるため
- **CRITICAL は confidence 80+ で報告**: 従来の閾値を踏襲。妥当な確信度があれば報告
- **MAJOR は confidence 95+ で報告**: 確信度が低いと「正しい判断」と区別できないノイズになりがち
- **MINOR は confidence 95+ で報告**: ほぼ確実な時のみ。それ以下は nitpick として除外

### surface-aware 閾値（high-risk surface に限る recall 補正 / ADR-20260703204045）

**high-risk surface**（DB 書込 / 金銭・数量計算 / 認可・認証、または PR 自己申告 D1-High。判定は triage-dynamic-gates.md `## 8.5` の surface 判定）を含む指摘に限り、報告閾値を非対称に緩める:

| severity | 通常 surface | high-risk surface |
|---|:---:|:---:|
| **BLOCKER** | 60+ | 60+（変更なし） |
| **CRITICAL** | 80+ | **70+** |
| **MAJOR** | 95+ | **85+** |
| **MINOR** | 95+ | 95+（変更なし） |

- **目的**: high-risk surface では CRITICAL 見落としのコストが nit 偽陽性のコストを大きく上回るため、その層に限って recall を優先する（見落としコストが偽陽性コストを上回る層の非対称扱い）。低リスク surface の noise は据え置く
- **効かせる箇所は適用順序の手順 7 の一点のみ**（下記「適用順序」参照）。precision の本丸（手順 2〜6 = 反証 verdict 反映 / 加減算 / `[unverified] min75` / `≤40 好みクランプ`）と Phase 5.9 の specialist 反証除外は**不変**。緩和は報告マトリクスのフィルタ段でのみ適用する
- **緩和帯の反証吸収**: high-risk surface で新規報告化する CRITICAL 70-79 / MAJOR 85-94 は、effort=high でも反証レイヤー（Phase 5.9）の対象に含める（triage-dynamic-gates.md `## 9` の high-risk surface 例外ゲート）。緩めた recall を独立反証が吸収する二段構えを保つ

### severity が付与されていない指摘の扱い（後方互換）

reviewer が severity を付与しなかった場合は **CRITICAL とみなして** 従来の confidence ≥ 80 フィルタを適用する（過剰報告は避ける一方、見落としは避ける安全側のデフォルト）。Phase A 完了直後の移行期間中は両方式が混在する可能性がある。

---

## 除外対象（severity / confidence に関わらず報告しない）

- 今回の変更で導入されたものではない既存の問題
- バグに見えるが正常なコード
- linter が検出するもの（ESLint, Prettier 等）
- lint ignore コメント付きのコード
- 些末な nitpick（スペース、改行等。MINOR 以下扱い）
- **PR の行単位 review comment で既に指摘されている内容のうち、diff で修正済みのもの**（review skill のみ。再指摘しない）

---

## confidence スコア加減算ルール

reviewer が付与した confidence を、以下のルールで Step 6 でオーケストレーターが加減算する。**最終値は 0-100 にクランプ**。

### 加算

- CLAUDE.md に明示的に記載あり: **+20**
- 複数エージェントが同一指摘を検出: **+15**（反証レイヤーの `confirmed` verdict もこの発火源として扱う。同時成立でも +15 は一度だけ＝二重計上しない）
- git blame で過去に同様の修正あり: **+15**
- **指摘冒頭に `[re-flag: @<既指摘者>]` タグあり**（review skill のみ、PR 行単位 review comment で既指摘 かつ diff で未修正）: **+15**
- セキュリティ関連: **+10**
- 同一観点の冗長ペアが合意（独立した視点からの裏付け）: **+10**（冗長ペアの実起動は xhigh/max のみ。high 以下の angle 内挿 1 体には適用しない — triage-guide.md `## 7`）
- explorer の発見と一致する指摘（探索結果で裏付けあり）: **+10**（doc-substance の「主張がコードと食い違う」指摘を grounding explorer / reviewer が code:line で裏取りした場合もこの発火源。doc-substance 専用の新規加点は作らない）
- reviewer-security の CRITICAL/BLOCKER 判定: **+10**
- reviewer-migration のデータ損失判定: **+10**

### 減算

- テストコードでの指摘: **-10**
- コメントアウトされたコード: **-20**
- 自動生成コード: **-30**
- セッションコンテキストの設計判断と一致する指摘: **-30**
- セッションコンテキストの「スコープ外」に該当する指摘: **-50**
- 同一観点の冗長ペアで片方のみ検出（確信度が下がる）: **-5**（同上: xhigh/max の実ペアのみ。high 以下の angle 内挿 1 体には適用しない）
- reviewer-pattern-consistency のスタイル的指摘: **-15**
- **指摘冒頭に `[intent-conflict]` タグあり**（PR 説明の意図と矛盾、spec-compliance の仕様違反判定は対象外、review skill のみ）: **-20**
- **指摘冒頭に `[resolved: @<同意者>]` タグあり**（PR 会話で LGTM/resolved 等の同意あり、review skill のみ）: **-30**
- **指摘冒頭に `[scope:out]` タグあり**（PR 説明で「このPRではやらない」「別 PR」と明記された範囲、review skill のみ）: **-50**

### 上限クランプ: 好みベース指摘の抑制（principles over personal preference）

各指摘に **CLAUDE.md / style guide / 計測データ / file:line で示せる具体的な不具合** のいずれの根拠も無く、reviewer 個人のスタイル選好に過ぎない場合は **confidence を 40 で上限クランプ**する（報告マトリクス上 MINOR/MAJOR は 95+ でないと出ないため、実質的に自動除外される）。

- 目的: LLM レビュー最大の弱点である「根拠なき好みベースの偽陽性」を機械的に刈り取る（Google eng-practices "The Standard": 技術的事実とデータは意見・個人的好みに優先する）
- 同等に有効な代替実装が複数あり、純粋に好みが割れるだけのケースは著者の選択を尊重し、このクランプを適用する
- 規約違反・実害の証拠を伴う指摘はクランプ対象外（通常のスコアリングを行う）
- **doc-substance の主観抑制もこのクランプで行う（2 軸で扱いを分ける）**:
  - **A 軸（主張の真偽）**: doc の論理 / 有用性 / 内容誤り指摘で根拠（code:line または内部矛盾の doc:line ×2）を示せないものは「表現の好み」とみなしてクランプする
  - **B 軸（文書としての成立性 — 完全性 / doc 種別適合 / 読み手前提 / WHY 根拠 / ナビ）**: **doc:line（欠落・誤配置・孤立の発生箇所）＋ 破られた期待（doc 種別の契約 / その doc が宣言する対象読者・スコープ / 手順が参照する未記載の前提）を示せていればクランプしない**。裏取りの相手がコードではなく doc 種別の期待構造であるため、code:line が無いことだけを理由に「好み」とみなさない（`prompts/focus/doc-substance.md` の grounding 規則を参照）。逆に「**語句を最小差分で言い換えれば済む**」だけの指摘（writing-polish の領分）は B 軸を騙っていてもクランプする
  - doc-substance の MAJOR は既定 effort（high）では反証レイヤー対象外（triage-dynamic-gates.md `## 9` のゲートは BLOCKER 60-94 / CRITICAL 80-94 限定）。この場合は「最小差分 reword か否か」のクランプが B 軸ノイズの唯一の抑制機構になる。`xhigh`/`max` に escalation した場合のみ B 軸 MAJOR も反証レイヤー（Phase 5.9、xhigh/max で MAJOR まで拡大）で独立検証され、クランプ（一次抑制）＋ 反証（偽陽性摘出）の二段構えになる

### 上限クランプ: 未検証の外部状態主張（claim grounding / GitHub issue #71）

指摘冒頭に **`[unverified: <対象>]` タグ**が付いている場合（reviewer が「repo / 正本 doc では検証できない外部状態—DB/本番の現状態・外部数値・運用設定・環境依存—に依拠している」と申告したもの。`prompts/reviewer-common.md`「事実主張のツール接地」）は **confidence を 75 で上限クランプ**する。

- 効果: BLOCKER 級の「重大な疑い」だけが報告マトリクスを通過し（BLOCKER は confidence 60+ で報告）、CRITICAL 以下の未検証断定は自動除外される
- 目的: repo から確認できない主張を「事実」として高 confidence で報告させない（未検証断定の構造的抑止）。確証が必要なら reviewer は `## unmet_information` で正本確認を求める
- 好みベースクランプ（min 40）と未検証クランプ（min 75）が両方該当する場合は **より低い方（min 40）を採用**する

### 適用順序

1. reviewer が付与した base confidence を取得
2. **反証 verdict の反映**（反証レイヤー = Phase 5.9/4.9 が動いた場合のみ。下記「反証レイヤーの verdict 反映」を参照）。**高 severity の `refuted` はここで delta を適用せず注記のみ付与**して以降に進む。verdict が無い指摘は no-op
3. 上記の加算・減算をすべて適用（独立に加算、最後に合算）
4. **未検証クランプ**: `[unverified: ...]` タグ付きの指摘は confidence を `min(値, 75)` に制限
5. **好みベース上限クランプ**: 根拠が個人的好みのみの指摘は confidence を `min(値, 40)` に制限（両クランプ該当時はこちらが優先）
6. 0-100 にクランプ
7. severity と組み合わせて報告マトリクスでフィルタ。**このとき high-risk surface フラグ付きの指摘には surface-aware 閾値（CRITICAL 70+ / MAJOR 85+）を適用する**（surface 判定は triage-dynamic-gates.md `## 8.5`。手順 2〜6 の precision 機構は不変で、緩和はこの手順 7 の一点のみ）

---

## severity 調整ルール（軽微）

severity は基本的に reviewer の判定を尊重するが、以下の場合のみ Step 6 で調整する:

- **タグ `[scope:out]` または `[resolved: ...]` が付いた指摘**: severity を 1 段階下げる（BLOCKER → CRITICAL、CRITICAL → MAJOR、MAJOR → MINOR、MINOR → そのまま）
- **退行指摘で invariant が incidental と検算された場合**（`prompts/reviewer-common.md`「退行指摘の invariant 検算」: 隣接経路で同 invariant が未強制と確認）: severity を 1 段階下げる。reviewer が検算済みで既に下げている場合は二重適用しない（指摘理由の「incidental と判断」記載で判別）
- **pre-existing / intended と申告された指摘**（`prompts/reviewer-common.md`「severity を付ける前に: base 状態の確認」/ GitHub issue #114）: **reviewer が既に 1 段階下げているので追加調整しない**。理由欄の「pre-existing（`git blame` で PR 前のコミット由来）」「intended（典拠: …）」記載で判別する。**同じ軸で反証レイヤーが `severity-inflated` を返した場合も二重適用しない**（下記 `severity-inflated` の排他条件に合流させる）
- **複数 reviewer が同一指摘を BLOCKER と判定**: severity を BLOCKER のまま維持（混乱を防ぐ）
- **doc-substance の裏取り済み内容誤りの CRITICAL 昇格（grounding ガード付き）**: doc の主張とコードが code:line で矛盾し裏取りできた指摘は CRITICAL に昇格する。**ただし昇格は、矛盾の相手が「doc が実際に参照する・実在する・現行の」コード経路である場合に限る**。次のいずれかでは昇格させず MAJOR に留める / 取り下げる:
  - (a) 矛盾の相手が doc の参照しない別経路や stale なパス（grounding 誤読。例: doc は `src/api` を指すのに未参照の `src/legacy` と突き合わせている）
  - (b) この PR が当該参照先コードを doc と整合する形で**同時変更済み**（`git blame` で doc 行と当該コード行が同一 PR の同時変更＝実矛盾なし。見かけの矛盾は (a) の別経路由来）
  - (c) doc が当該挙動を「将来 / 計画中 / 既知の制約」と明示（intended）
  - **コードが doc より古いこと自体は昇格を妨げない**（安定した既存コードに対する doc の誤記は正当な CRITICAL 内容誤り。新しい doc 変更が古い安定コードと矛盾するのは典型的な「doc が間違っている」ケース）。昇格後は「高 severity 非削除」不変条件で反証 refuted でも残るため、入口で (a)-(c) を絞る
- それ以外: reviewer の判定をそのまま使用

severity の頻繁な上書きは reviewer のキャリブレーションを崩すため、原則として最小限の調整に留める。

---

## 反証レイヤーの verdict 反映（Phase 5.9 / 4.9）

反証レイヤー（review=Phase 5.9 / self-review=Phase 4.9）が動いた場合、対象指摘には独立反証エージェントの **verdict** が付く。Step 6 オーケストレーターは適用順序の冒頭（手順 2）でこれを **機械適用** する（reviewer 判断は介入させない）。**プロンプトではなくこの手順で「高 severity を消さない」を構造的に保証する**のが本機構の核。

### verdict → 操作の対応

| verdict | severity | 操作 |
|---|---|---|
| `refuted`（file:line 反証根拠あり） | **BLOCKER / CRITICAL** | **delta を適用しない。** 指摘本文の先頭に `⚠️ 反証メモ: <軸>（<根拠 file:line>、要確認）` を付与（= 係争中）。confidence / severity は据え置き → 報告マトリクス境界を跨がない |
| `refuted`（file:line 反証根拠あり） | **MAJOR / MINOR** | confidence **−40**（実質マトリクス外）。ただし **取り下げ理由を必ず付録に記録**（誤却下を人間が覆せる経路を残す。理由には軸名と反証 file:line を含める） |
| `confirmed`（独立にパス再現） | 全 severity | 既存「複数エージェント同一指摘 +15」の **発火源として扱う**。反証 confirm と複数エージェント検出が同時成立しても **+15 は一度だけ**（二重計上の排他） |
| `uncertain`（具体根拠なし） | 全 severity | confidence **−10** + 本文に `（反証: 未確定）` を付記。**単独では何も落とせない**（怠惰な却下で本物を殺さないため） |
| `severity-inflated`（影響過大の根拠あり） | **BLOCKER / CRITICAL** | **降格後に報告マトリクスを割る場合は severity を据え置き**、本文先頭に `⚠️ 反証メモ: severity 過大の疑い（<根拠 file:line>、要確認）` を付与する（= 係争中）。割らない場合のみ 1 段階下げる。判定は降格後の (severity, confidence) を報告マトリクスに当てて行う |
| `severity-inflated`（影響過大の根拠あり） | **MAJOR / MINOR** | **既存「severity 調整ルール（軽微）」の一項目として** severity を 1 段階下げる。**退行 invariant 検算・pre-existing / intended 申告（#114）で既に下げている場合は二重適用しない**（理由欄の記載で判別。同じ軸を 2 回引くと過小評価になる）。**降格の結果 severity が報告マトリクス / `review_severity_threshold` を割って脱落する場合は、`refuted` の MAJOR/MINOR と同じく取り下げ理由を付録（🔁）に記録する**（verdict 種別・軸名・反証 file:line を含める。降格で消える指摘だけ silent に落ちて `refuted` との透明性が食い違うのを防ぐ / GitHub issue #109） |

### 不変条件（機械保証）

- **高 severity（BLOCKER / CRITICAL）の指摘は反証レイヤーで報告から消えない。** `refuted` は confidence/severity を据え置き、`severity-inflated` は報告マトリクスを割る降格を行わない。いずれも本文に反証メモを付すのみで、最終判断は人間に残す（false-negative の構造的防止）
  - **この不変条件は反証レイヤーの effort 引き下げの前提になっている**（orchestration-guide.md `## 5`）。緩める変更をするときは反証 effort を `max` に戻すかを同時に判断する。→ 経緯: `design-notes/scoring-rationale.md`
  - **高 severity は仮に降格で消えても「🔁 反証で取り下げた指摘」には出さない**（あの節は MAJOR/MINOR が反証で報告閾値を割った場合に載る節 — `refuted` の −40 と `severity-inflated` の降格の両方を含む / issue #109）。高 severity は係争注記付きで本文に残すのが唯一の正しい扱い
- **security specialist 由来（specialist-injection / -secret-handling / -destructive-op / -input-validation / -guardrail-bypass）の指摘は反証対象外**（triage-dynamic-gates.md `## 9` のゲートで除外）。万一 verdict が付いても confidence / severity は据え置き、反証メモも付さない（誤反証の代償が非対称に大きい）
- 係争メモは `[...]` タグ語彙を増やさず本文の `⚠️ 反証メモ:` で表す（reviewer 自己申告タグ `[scope:out]` 等はオーケストレーターでなく reviewer が付与する系統。producer を記法で区別する）
- verdict が付いていない指摘（反証レイヤー未起動・対象外・反証失敗）は本ステップを no-op として素通りする（後方互換）

> **バッチはパネルではない**: 現行は全 effort で **1 指摘 1 verdict**（反証エージェント 1 体が最大 5 件を担当するバッチ運用）。同じ指摘に複数 verdict が付くことは無いので、**バッチ内の verdict 同士を合算・相殺してはならない**（triage-dynamic-gates.md `## 9`）。パネル運用（1 指摘を複数体で反証）は将来拡張で、集計規則は `design-notes/scoring-rationale.md`。

---

## userConfig との連携

`plugin.json` の `userConfig` で報告閾値をユーザーがカスタマイズ可能:

- `review_confidence_threshold` (number, default: 80): CRITICAL 以下の最低 confidence（後方互換のため残置）
- `review_severity_threshold` (string, default: "MAJOR"): 報告対象の最低 severity。`BLOCKER` / `CRITICAL` / `MAJOR` / `MINOR` のいずれか
- `enable_recall_skeptic` (bool, default: true): 冷や読み skeptic ラウンド（Phase 5.8 / 4.8）の有効化。`false` で強制スキップ。high-risk surface でも起動しなくなり、surface-aware 閾値は据え置き（surface-aware 閾値自体はこの config で無効化しない＝閾値と skeptic 起動は別機構）

`review_severity_threshold = "CRITICAL"` を設定すると MAJOR 以下を完全に除外（厳しめ運用）。`"MINOR"` にすると全 severity を報告（緩め運用）。デフォルトの `"MAJOR"` は上記マトリクス通り。

### 実効閾値を reviewer に伝える（GitHub issue #117）

**実効値を `{{SEVERITY_THRESHOLD}}` として reviewer プロンプトに注入する**（規約の正本は `prompts/reviewer-common.md` の「実効報告閾値」）。閾値未満の指摘は reviewer が本文を書かず `## below-threshold` に件数だけ返す。

- 報告マトリクスと `review_severity_threshold` は**直列に掛かる 2 段のフィルタ**で、既定 `MAJOR` では MINOR が構造的にほぼ全滅する（実測: 調整前 60 → 報告 9 件 = 85% 破棄。うち confidence 95+ が 7 件）。reviewer は実効値を知らされていなかったため抑制もできず、**書かせて捨てるという最も損な組み合わせ**になっていた
- **`pre_adjust_counts` は `## below-threshold` の件数を足して求める**（`orchestration-measurement.md ## 16`）。足さないと「reviewer が検出しなかった」と「閾値未満なので列挙しなかった」が 0 に潰れ、**この issue の根拠になった計測そのものが今後取れなくなる**
- **抑制は列挙だけで、判定は従来どおり**。閾値未満を理由にした severity の繰り上げは較正の破壊として扱う（reviewer 側にも明記済み）

---

## レビュー結論（総合判定）

Google eng-practices "The Standard of Code Review" の **継続的改善（continuous improvement）** 原則を採用する: **変更がシステム全体のコード健全性を確実に向上させるなら、完璧でなくとも Approve を優先する**。完璧な CL は存在せず「より良いコード」があるだけ。MINOR / nit の積み残しを理由に承認を保留しない。

報告マトリクス通過後（＝実際にレポートに出る）の指摘から、総合判定を **決定的に** 導出する:

| 残存指摘 | 総合判定 | 意味 |
|---|---|---|
| BLOCKER または CRITICAL が 1 件以上 | **Needs work** | コード健全性を損なう。マージ前に対応必須 |
| BLOCKER/CRITICAL なし・MAJOR が 1 件以上 | **Approve with nits** | 健全性は向上している。MAJOR は追跡 Issue / TODO を添えて対応推奨 |
| MINOR のみ残存 | **Approve with nits** | 著者裁量で対応（LGTM with comments）。nit を理由にブロックしない |
| 報告指摘ゼロ | **Approve** | — |

- レポート冒頭の `総合判定` 行はこの表に従い決定する。`総合評価 X/10 点` は併記してよいが、**承認可否の一次情報は総合判定**とする
- `result_grid`（event payload）との対応: `high>0` → Needs work / `high=0 && (medium>0 || low>0)` → Approve with nits / すべて 0 → Approve
- self-review でも同じ判定軸を用いる（コミット前のゲートとして「このままコミットしてよいか」の指針になる）
