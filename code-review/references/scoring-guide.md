# 2軸スコアリングガイド（confidence × severity）

## 設計思想

レビュー指摘の品質は **2 つの独立した軸** で判定する:

1. **confidence (確信度)** — *指摘が事実として正しい確率*。0-100。reviewer が証拠（diff・ファイル Read・explorer 結果）でどれだけ裏付けられるか
2. **severity (重大度)** — *指摘が現実に与える影響の大きさ*。BLOCKER / CRITICAL / MAJOR / MINOR の 4 段階。「もしこの指摘が当たっていた場合に何が起きるか」で判定

この 2 軸を混同すると次のジレンマが起きる:

| ケース | 単一軸 (confidence のみ) の問題 |
|---|---|
| **重大だが不確実** (race condition の疑い) | confidence 中程度 → 80 未満で**落ちる**。致命的見落とし |
| **軽微だが確実** (typo) | confidence 高い → 報告される。ノイズ |

2 軸化により **「BLOCKER は不確実でも報告」「MINOR はほぼ確実な時だけ報告」** という非対称な報告ルールを表現できる。

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
- セキュリティ・データ整合性・本番事故に直結するものは原則 BLOCKER または CRITICAL
- 「動くけど将来困る」系は MAJOR
- 「あれば良い」程度は MINOR
- 観点ごとの目安は reviewer-prompts.md の Focus テンプレートに記載

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
- 複数エージェントが同一指摘を検出: **+15**
- git blame で過去に同様の修正あり: **+15**
- **指摘冒頭に `[re-flag: @<既指摘者>]` タグあり**（review skill のみ、PR 行単位 review comment で既指摘 かつ diff で未修正）: **+15**
- セキュリティ関連: **+10**
- 同一観点の冗長ペアが合意（独立した視点からの裏付け）: **+10**
- explorer の発見と一致する指摘（探索結果で裏付けあり）: **+10**
- reviewer-security の CRITICAL/BLOCKER 判定: **+10**
- reviewer-migration のデータ損失判定: **+10**

### 減算

- テストコードでの指摘: **-10**
- コメントアウトされたコード: **-20**
- 自動生成コード: **-30**
- セッションコンテキストの設計判断と一致する指摘: **-30**
- セッションコンテキストの「スコープ外」に該当する指摘: **-50**
- 同一観点の冗長ペアで片方のみ検出（確信度が下がる）: **-5**
- reviewer-pattern-consistency のスタイル的指摘: **-15**
- **指摘冒頭に `[intent-conflict]` タグあり**（PR 説明の意図と矛盾、spec-compliance の仕様違反判定は対象外、review skill のみ）: **-20**
- **指摘冒頭に `[resolved: @<同意者>]` タグあり**（PR 会話で LGTM/resolved 等の同意あり、review skill のみ）: **-30**
- **指摘冒頭に `[scope:out]` タグあり**（PR 説明で「このPRではやらない」「別 PR」と明記された範囲、review skill のみ）: **-50**

### 適用順序

1. reviewer が付与した base confidence を取得
2. 上記の加算・減算をすべて適用（独立に加算、最後に合算）
3. 0-100 にクランプ
4. severity と組み合わせて報告マトリクスでフィルタ

---

## severity 調整ルール（軽微）

severity は基本的に reviewer の判定を尊重するが、以下の場合のみ Step 6 で調整する:

- **タグ `[scope:out]` または `[resolved: ...]` が付いた指摘**: severity を 1 段階下げる（BLOCKER → CRITICAL、CRITICAL → MAJOR、MAJOR → MINOR、MINOR → そのまま）
- **複数 reviewer が同一指摘を BLOCKER と判定**: severity を BLOCKER のまま維持（混乱を防ぐ）
- それ以外: reviewer の判定をそのまま使用

severity の頻繁な上書きは reviewer のキャリブレーションを崩すため、原則として最小限の調整に留める。

---

## userConfig との連携

`plugin.json` の `userConfig` で報告閾値をユーザーがカスタマイズ可能:

- `review_confidence_threshold` (number, default: 80): CRITICAL 以下の最低 confidence（後方互換のため残置）
- `review_severity_threshold` (string, default: "MAJOR"): 報告対象の最低 severity。`BLOCKER` / `CRITICAL` / `MAJOR` / `MINOR` のいずれか

`review_severity_threshold = "CRITICAL"` を設定すると MAJOR 以下を完全に除外（厳しめ運用）。`"MINOR"` にすると全 severity を報告（緩め運用）。デフォルトの `"MAJOR"` は上記マトリクス通り。
