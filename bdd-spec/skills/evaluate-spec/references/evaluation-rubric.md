# Evaluation Rubric（5 観点の詳細チェックリスト + スコアリング）

`evaluate-spec` スキルが spec.md / epic.md を静的レビューする際の判定基準の正本。SKILL.md 本文は Phase 構成に絞り、各観点の具体チェック項目・severity・confidence 付与ルールは本ファイルに置く。

---

## スコアリング（severity × confidence）

ルート CLAUDE.md「コスト×精度パイプライン設計指針」原則 2（2 軸スコア化）・原則 10（確信度フィールド化）に従う。

### severity（3 段階）

| severity | 意味 | 例 |
|---|---|---|
| 🔴 critical | spec が契約として破綻・誤誘導する。実装/テストが誤った前提で進む | 参照リンク切れ、Scenario Outline に Examples 不在、同値クラスが 1 つも Scenario にカバーされない |
| 🟡 major | 網羅性・トレーサビリティに穴。見落としを生むが致命的ではない | 表にあるのに未カバーの同値クラス、AC に対応する Scenario がない、境界値が表にない、状態遷移表にあるのに未カバーの遷移辺 |
| 🔵 minor | 粒度・スタイルの改善余地。読みやすさ・保守性の問題 | When が複数アクション、Then が実装詳細に踏み込む、Scenario 名が曖昧 |

### confidence（0-100）

- **機械判定できる指摘は confidence 100**（構文・リンク存在・表セル空欄・プレースホルダ残存など grep/構造で確定するもの）
- **意味判定を要する指摘は 0-100 で付与**（粒度の適否・Why が answered か・同値クラスの過不足など）。断定できないものは 60 未満にして「未検証」寄りに倒す

### 報告閾値マトリクス

| severity \ confidence | <60 | 60-79 | 80+ |
|---|:---:|:---:|:---:|
| 🔴 critical | 報告 | 報告 | 報告 |
| 🟡 major | skip | 報告 | 報告 |
| 🔵 minor | skip | skip | 報告 |

- critical は confidence が低くても報告する（「疑わしい」段階で人間判断を促す。code-review の BLOCKER と同思想）。ただし影響（なぜ critical か）を必ず添える。

---

## 観点 1: Gherkin 構文妥当性（機械 / ファネル第 1 段）

grep・構造走査で確定できる決定的チェック。ほぼ confidence 100。ここで 🔴 が出たら意味評価（観点 2-5）に進む前に是正を促してよい（安いオラクルを先頭に置くファネル）。

| # | チェック | 検出時 severity |
|---|---|---|
| 1.1 | `# Feature:` 行が 1 つ存在する | 🔴 critical |
| 1.2 | 各 `Scenario:` / `Scenario Outline:` に Given / When / Then が揃っている（最低 When と Then） | 🔴 critical |
| 1.3 | `Scenario Outline:` には `Examples` テーブルが対応して存在する | 🔴 critical |
| 1.4 | Scenario Outline 本文の `<placeholder>` が Examples テーブルの列見出しに全て存在する | 🔴 critical |
| 1.5 | ` ```gherkin ` フェンスが開閉ペアで閉じている（未クローズ検出） | 🔴 critical |
| 1.6 | `## Background` セクションが存在する | 🟡 major |
| 1.7 | frontmatter に `last-validated` / `phase` / `role` / `epic` が揃っている | 🟡 major |
| 1.8 | scaffold プレースホルダ（`{...}` / `{PLACEHOLDER}` 形式）が本文に残っていない | 🔵 minor（Phase 0 の scaffold ゲートで別途扱う） |

> gherkin キーワードは日英どちらでもよい（`前提/もし/ならば` も許容）。language 設定に依存せず Given/When/Then の三段が読み取れるかで判定する。

---

## 観点 2: 粒度一貫性（意味 / LLM）

各 Scenario が「1 振る舞い = 1 Scenario」の粒度に収まっているか。confidence は判断の明確さで付与する。

| # | チェック | 検出時 severity | confidence の目安 |
|---|---|---|---|
| 2.1 | When が単一アクションに収まっている（`When ... When ...` / `And` で複数操作を連結していない） | 🔵 minor | 明確に複数操作なら 85+、判断微妙なら 50-70 |
| 2.2 | Given が状態（前提）で、操作を含んでいない | 🔵 minor | 70-85 |
| 2.3 | Then が観測可能な結果を assert し、実装詳細（内部関数呼び出し・DB カラム名等）に踏み込んでいない | 🟡 major | 実装語彙が明白なら 80+、曖昧なら 50-65 |
| 2.4 | Scenario 群が同じ抽象度で書かれている（UI 操作レベルと業務ルールレベルが混在していない） | 🔵 minor | 60-75 |
| 2.5 | Scenario 名が「何を検証するか」を表している（`Scenario 1` のような無名でない） | 🔵 minor | 80+ |
| 2.6 | 1 Scenario が 1 つの振る舞いに閉じている（複数の独立した検証を詰め込んでいない） | 🟡 major | 70-85 |

---

## 観点 3: 網羅性（同値分割表 ⇔ Scenario の双方向トレース）

「同値分割・境界値分析表」と Scenario 群の対応を双方向で検証する。表のセル走査は機械（confidence 100）、同値クラスの過不足判断は意味（0-100）。

| # | チェック | 検出時 severity | confidence |
|---|---|---|---|
| 3.1 | 表の各行の「カバー Scenario」列が空でなく、実在する Scenario を指している | 🟡 major | 100（機械） |
| 3.2 | 表にあるのに **どの Scenario からもカバーされない同値クラス**（表→Scenario 片方向切れ） | 🟡 major | 100（機械） |
| 3.3 | Scenario の「カバーする因子」が表に存在する（Scenario→表 片方向切れ、orphan scenario） | 🟡 major | 100（機械） |
| 3.4 | 各因子について正常（下限/中央/上限）・異常（下限外/上限外）・空/null の同値クラスが表に揃っている | 🟡 major | 過不足が明白なら 80+、ドメイン次第で不要な区分は 50-70 |
| 3.5 | 境界値（上限/下限そのものと ±1）が代表値として表にある（境界値分析の欠落） | 🟡 major | 70-85 |
| 3.6 | 表に列挙された同値クラスが実際に意味的に排他（同じ値域を 2 クラスに割っていない） | 🔵 minor | 55-75 |

> 3.2 / 3.3 が「網羅性」評価の核心（issue #78 が名指しした双方向トレース）。表とScenario の両方向から orphan を検出する。

---

## 観点 4: トレーサビリティ（epic.md ⇔ spec.md）

epic の Why/What/AC が spec で answered されているかを検証する。リンク解決は機械、Why-answered 判断は意味。

| # | チェック | 検出時 severity | confidence |
|---|---|---|---|
| 4.1 | epic.md の各 `AC-N: ... → spec.md:#scenario-N` リンクが実在する Scenario 見出しを指す | 🔴 critical | 100（機械） |
| 4.2 | spec.md の各 Scenario の `Trace: [epic.md AC-N]` リンクが実在する AC を指す | 🟡 major | 100（機械） |
| 4.3 | spec.md 内「トレーサビリティ」表の AC ↔ Scenario ↔ 因子 が 3 者とも実在を指す | 🟡 major | 100（機械） |
| 4.4 | epic の各 AC に対応する Scenario が最低 1 つ存在する（未カバー AC の検出） | 🔴 critical | 100（機械） |
| 4.5 | epic「What（成果物）」の各項目が、いずれかの AC / Scenario に対応づく | 🟡 major | 対応の明白さで 60-85 |
| 4.6 | epic「Why（動機）」が spec の Scenario 群で満たされる（動機に対して検証が十分か） | 🟡 major | 50-75（意味判断。断定しない） |
| 4.7 | epic「スコープ外」に書かれた項目を Scenario が誤ってカバーしていない（スコープ逸脱） | 🔵 minor | 60-80 |

---

## 観点 5: 遷移カバレッジ（状態遷移表 ⇔ Scenario の双方向トレース）※ stateful spec のみ・dormant

状態を持つフィーチャー（ワークフロー・ステータス機械・ウィザード等）で、状態遷移の網羅を検証する。判定の骨格は観点 3 と同型（表 ⇔ Scenario の双方向トレース）で、軸を「入力因子」から「状態遷移」に差し替えたもの。

**dormant 発火ゲート**: spec.md に「状態遷移表」セクションが無い、または表に**実データ行が無い**（全データ行が `{...}` プレースホルダを含む、または `Scenario N` / `（未カバー）` 等の scaffold 定型リテラルのみ）なら本観点を丸ごと skip する（stateless な CRUD / 参照系・scaffold 直後の未記入テンプレにノイズを出さない）。判定は「プレースホルダ・定型リテラルを除いた実データ行の有無」を grep で機械化する（表セルの単純な非空判定では scaffold テンプレの `{draft}` を非空と誤判定するため使わない）。Phase 0 の scaffold ゲート該当時も skip する。

**モデル観**: アプリのワークフローは DAG ではなく巡回する FSM であり、巡回辺（差し戻し・再編集・リトライ）こそバグの温床。カバレッジ基準は**辺**（全 transition を最低 1 Scenario でカバー）を既定とし、全パスは要求しない（巡回でパスが指数爆発するため）。

| # | チェック | 検出時 severity | confidence |
|---|---|---|---|
| 5.1 | 状態遷移表の各辺の「カバー Scenario」列が空でなく、実在する Scenario を指している | 🟡 major | 100（機械） |
| 5.2 | 各 Scenario の構造化注記「**カバーする辺**」（`S1 --action--> S2`）から回収した辺が状態遷移表に宣言されている（表→Scenario / Scenario→表 の双方向。未カバー辺・orphan transition を検出） | 🟡 major | 100（機械。注記が grep 文字列一致するため） |
| 5.2b | stateful spec（表が非空）の Scenario に「カバーする辺」注記が無い | 🟡 major | 100（機械。注記欠落＝再構成不能。意味判定にフォールバックせず fail-closed） |
| 5.3 | reject / 戻る / リトライ相当の**巡回辺**（後退辺・自己ループ）が状態遷移表に 1 つも無い → happy-path 偏重の疑い | 🟡 major | 巡回が業務上自明なら 75+、stateful-but-acyclic の可能性がある場合 50-70 |
| 5.4 | 終端状態から出る辺がある等の構造矛盾（到達不能状態・出口の無い非終端状態） | 🟡 major | 明白なら 80+、曖昧なら 55-70 |
| 5.5 | glossary（`all_spec.md`）に `遷移可能先` があり、かつこの spec が該当 entity を触る場合、状態遷移表の (遷移元, 遷移先) ペアが glossary と矛盾しない（整合オラクルが在るときだけ発火） | 🟡 major | ペア照合は 100（機械）、entity 該当判定は 60-80 |

> 5.2 / 5.2b が本観点の核心（観点 3 の 3.2/3.3 と同型の双方向トレース）。辺の再構成を決定的にするため Scenario 側の「カバーする辺」注記を必須化している（自由文 Given/When/Then からの辺抽出は意味判定になり confidence 100 が成立しないため）。
> 「種別」（前方/巡回/自己）は表に手書きさせず、再構成グラフから導出する（自己 = 遷移元==遷移先、巡回 = 後退辺）。手動列は drift 源になるため置かない。
> 未カバー巡回辺は既定 🟡（advisory）。stateful-but-acyclic spec への誤検知を避け、fail 方向を見逃し許容側に倒す判断。真に業務フロー上の差し戻し等を欠く場合は confidence を上げて報告する。

---

## 修正提案の付け方（原則: 理由付き）

各指摘には「どう直すか」を根拠付きで添える（issue #78 の「どこに Example を追加すべきか根拠付き」）。断定できない意味判断は「要確認」を明示する。

- 🔴/🟡 で機械確定（confidence 100）→ 具体的な追加/修正箇所を提示（例: 「同値分割表 因子1『空/null』行のカバー Scenario 列が空。Scenario 4 を追加するか既存 Scenario にこの因子を割り当てる」）
- 意味判断（confidence < 80）→ 「〜の可能性（要確認）」と不確実性を残す。over-correction を避ける
- **spec を勝手に書き換えない**。修正は Phase 6 の AskUserQuestion 承認後のみ（frontmatter / 見出し構造 / gherkin フェンスは保全）

---

## scaffold 状態の扱い（Phase 0 ゲート）

`create-spec` で scaffold した直後の spec.md はプレースホルダ（`{...}`）だらけの空骨格。これを全観点で評価するとノイズが大量に出る。

- 本文の過半が `{...}` プレースホルダ、または Scenario の Given/When/Then が全てプレースホルダ → **「まだ scaffold 段階」と判定**
- この場合は観点 1（構造の存在）のみ評価し、観点 2-5 は「spec を埋めてから再実行してください」と案内してスキップする（空骨格に網羅性・トレーサビリティ・遷移カバレッジを問うても無意味）
