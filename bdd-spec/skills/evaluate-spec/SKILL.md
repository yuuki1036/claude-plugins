---
name: evaluate-spec
description: >
  BDD spec (spec.md / epic.md) を 5 観点（Gherkin 構文・粒度一貫性・網羅性・トレーサビリティ・遷移カバレッジ）で静的レビューする品質ゲート。severity×confidence で評価する。
  トリガー: 「spec を評価」「spec 品質チェック」「BDD spec レビュー」「spec.md をレビュー」
  「同値分割の網羅性チェック」「spec の穴を見つけて」「/bdd-spec-evaluate」
effort: medium
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Edit
  - AskUserQuestion
---

# Evaluate Spec

`create-spec` が scaffold し、ユーザーが埋めた BDD spec を静的レビューするスキル。**spec を作り直す場ではなく、構文・粒度・網羅性・トレーサビリティ・遷移カバレッジの穴を根拠つきで挙げる場**。実装/テストに入る前の品質ゲートとして使う。

## いつ使う / いつ使わない

| 状況 | 使うスキル |
|------|-----------|
| 埋めた spec.md の品質を検証したい | **evaluate-spec**（本スキル） |
| 同値分割表と Scenario の対応漏れを見つけたい | **evaluate-spec**（本スキル） |
| user story を新規 scaffold する | `create-spec` |
| 実装したコード（diff / PR）をレビューする | `code-review:review` / `self-review` |
| 技術設計（HOW）をレビューする | `design-doc:design-review` |

## 参照する規範（references）

- `${CLAUDE_SKILL_DIR}/references/evaluation-rubric.md` — 5 観点の詳細チェックリストと severity×confidence 付与ルール（正本）

## コスト×精度パイプライン設計（採用/不採用）

ルート CLAUDE.md「コスト×精度パイプライン設計指針」の 10 原則のうち **採用: 1（ファネル = 観点 1 の機械構文チェックを先頭に置き、🔴 が出たら意味評価の前に是正を促す）/ 2（2 軸スコア化 = severity × confidence）/ 3（段階予算 = `${CLAUDE_EFFORT}` → 評価観点の深さ）/ 8（外部オラクル + fail-closed = リンク解決・表セル走査を grep で機械判定し、scaffold 状態は評価対象外に倒す）/ 10（確信度フィールド化 = 意味判断は confidence < 80 で「要確認」に倒す）**。**捨てた**: 4（モデルルーティング）は単一コンテキストの静的評価で fan-out しないため不要、5（暴走ガード）は反復を持たない単発評価のため不要、6（証拠ラダー）/ 7（敵対的独立検証）は単一 spec が対象で蓄積・多重検証の規模ではないため（誤検知抑制は confidence フィールドと修正の承認ゲートで代替）。

---

## Phase 0: 対象特定 + scaffold ゲート

1. `.claude/bdd-spec.json` を Read（無ければ default）。`featuresDir`（デフォルト `features`）を得る
2. 引数を解析: `[spec パス | story ディレクトリ | 省略]`
   - パス指定あり → その spec.md を対象。ディレクトリ指定なら配下の `spec.md`
   - 省略 → `{featuresDir}/*/spec.md` を Glob。1 件なら自動選択、複数なら AskUserQuestion で選択（`phase: current` を優先し最新を先頭 + `(Recommended)`）、0 件なら「評価対象の spec.md がありません。/bdd-spec-create で作成してください」と案内して終了
3. 対象 spec.md と、その frontmatter `epic:` が指す epic.md を Read する
4. **scaffold ゲート**（evaluation-rubric.md「scaffold 状態の扱い」）: 本文の過半が `{...}` プレースホルダ、または全 Scenario の Given/When/Then がプレースホルダのまま → **「まだ scaffold 段階」と判定**。観点 1（構造の存在）のみ評価し、観点 2-5 は「spec を埋めてから再実行してください」と案内してスキップする（scaffold 段階では状態遷移表もプレースホルダなので観点 5 も skip 対象に含める）

## Phase 1: 観点 1 — Gherkin 構文妥当性（機械 / ファネル第 1 段）

evaluation-rubric.md「観点 1」の 1.1〜1.8 を grep・構造走査で判定する。ほぼ confidence 100 の決定的チェック。

- Feature 行・各 Scenario の Given/When/Then・Scenario Outline の Examples・`<placeholder>` と列見出しの対応・gherkin フェンスの開閉・Background・frontmatter を機械的に確認する
- **ファネルの要**: ここで 🔴 critical（構文破綻）が 1 件以上出た場合、意味評価（Phase 2-4）に進む前にレポートで是正を促してよい（壊れた構文の上に網羅性を論じても無駄なため）。ただし effort=high 以上では続行して全観点をまとめて報告する

## Phase 2: 観点 2 — 粒度一貫性（意味）

evaluation-rubric.md「観点 2」の 2.1〜2.6 を評価する。When の単一アクション性・Then が実装詳細に踏み込んでいないか・Scenario 群の抽象度の揃い・1 Scenario 1 振る舞いを見る。意味判断のため confidence を明確さに応じて付与する（断定できないものは 60 未満）。

## Phase 3: 観点 3 — 網羅性（同値分割表 ⇔ Scenario 双方向トレース）

evaluation-rubric.md「観点 3」の 3.1〜3.6 を評価する。**本スキルの核心**:

- **表 → Scenario**: 表の各同値クラス行の「カバー Scenario」列が実在 Scenario を指すか。空欄・どの Scenario からもカバーされない同値クラスを 🟡 で検出（confidence 100）
- **Scenario → 表**: 各 Scenario の「カバーする因子」が表に存在するか。orphan scenario を検出（confidence 100）
- 各因子の正常/異常/空・null の同値クラスの揃い、境界値の有無を評価（意味判断は confidence 付き）

表セルの走査とリンク解決は Grep/Bash で機械的に行う（外部オラクル）。

## Phase 4: 観点 4 — トレーサビリティ（epic.md ⇔ spec.md）

evaluation-rubric.md「観点 4」の 4.1〜4.7 を評価する。

- epic の `AC-N → spec.md:#scenario-N` リンク・spec の `Trace: epic.md AC-N` リンク・spec 内トレーサビリティ表の 3 者対応を機械的にリンク解決（confidence 100）
- 未カバー AC は 🔴 critical（実装が要件を取りこぼす）
- epic の What（成果物）が AC/Scenario に対応づくか、Why が Scenario 群で満たされるか、スコープ外を誤カバーしていないかを意味判断（confidence 付き）

## Phase 4.5: 観点 5 — 遷移カバレッジ（状態遷移表 ⇔ Scenario 双方向トレース・stateful のみ / dormant）

evaluation-rubric.md「観点 5」の 5.1〜5.5 を評価する。**dormant 発火ゲート**: spec.md に「状態遷移表」セクションが無い、または表に**実データ行が無い**（全データ行が `{...}` プレースホルダを含む、または `Scenario N` / `（未カバー）` 等の scaffold 定型リテラルのみ）なら本観点を丸ごと skip する（stateless spec・scaffold 直後の未記入テンプレにノイズを出さない）。判定は「プレースホルダ・定型リテラルを除いた実データ行の有無」を grep で機械化する（表セルの単純な非空判定では scaffold テンプレの `{draft}` を非空と誤判定するため使わない）。Phase 0 の scaffold ゲート該当時も skip する。

- **表 → Scenario / Scenario → 表**: 状態遷移表の各辺の「カバー Scenario」と、各 Scenario の構造化注記「カバーする辺」を双方向トレースし、未カバー辺・orphan transition を 🟡 で検出（confidence 100。注記が grep 一致するため）
- **注記欠落**: stateful spec の Scenario に「カバーする辺」注記が無ければ 🟡（fail-closed。意味判定にフォールバックしない）
- **巡回辺の取りこぼし**: 差し戻し・再編集・リトライ相当の後退辺 / 自己ループが 1 つも無い happy-path 偏重を意味判断で検出（stateful-but-acyclic は誤検知しないよう confidence を抑える）
- **構造矛盾（5.4）**: 終端状態から出る辺・到達不能状態・出口の無い非終端状態を意味判断で検出
- **glossary 整合（任意オラクル）**: `all_spec.md` に `遷移可能先` があり該当 entity を触る場合のみ、(遷移元, 遷移先) ペアの矛盾を照合

辺の再構成が決定的なのは Scenario 側の「カバーする辺」注記を必須化しているため（自由文 Given/When/Then からの辺抽出は意味判定になる）。表セルの走査とリンク解決は Grep/Bash で機械的に行う（外部オラクル）。

## Phase 5: レポート出力

各指摘を evaluation-rubric.md の報告閾値マトリクス（severity × confidence）でフィルタして出力する。

```
## BDD Spec Evaluation Report

**対象**: {featuresDir}/{dirname}/spec.md（+ epic.md）
**総合判定**: {契約として妥当 | 埋め残し・穴あり | 構文破綻（要是正）}
**スコア**: 構文 {🔴n/🟡n/🔵n} / 粒度 {…} / 網羅性 {…} / トレーサビリティ {…} / 遷移カバレッジ {… | stateful のみ・非該当なら「-」}
{scaffold 段階の場合: **⚠️ scaffold 段階のため観点 2-5 はスキップ。spec を埋めてから再実行してください**}

### 🔴 critical
1. [観点4/confidence 100] epic.md AC-2 に対応する Scenario が spec.md に存在しない
   位置: epic.md:38（AC-2 → spec.md:#scenario-2 が未解決）
   影響: 実装/テストが AC-2 を取りこぼす
   修正: spec.md に Scenario 2 を追加、またはトレーサビリティ表から AC-2 を見直す

### 🟡 major
2. [観点3/confidence 100] 同値分割表「因子1: 空/null」がどの Scenario からもカバーされない
   位置: spec.md:87（カバー Scenario 列が Scenario 4 を指すが Scenario 4 が不在）
   修正: 空入力を検証する Scenario 4 を追加する

### 🔵 minor
3. [観点2/confidence 70] Scenario 3 の When が 2 つの操作を含む（要確認）
   位置: spec.md:60
   修正: 操作ごとに Scenario を分割すると 1 Scenario 1 振る舞いになる

### 総括
- spec が契約として機能する状態か
- 実装/テスト前に埋めるべき穴（特に 🔴）
- 人間が最終判断すべき意味判断（confidence < 60 の指摘）
```

- 検出 0 件なら「spec は健全です（契約として実装/テストに進めます）」と報告
- 良い点があれば 0〜2 件添える（網羅性が高い・トレーサビリティが明快など）。中身のない称賛は書かない

## Phase 6: 修正提案（任意 / 承認後のみ）

報告マトリクス通過後の指摘が 1 件以上ある場合のみ **AskUserQuestion** で対応方針を確認する:

- question: "検出された spec の問題への対応方針を選んでください"
- header: "対応方針"
- multiSelect: false
- options:
  1. label: "機械確定分を修正" / description: "confidence 100 の構文・リンク切れ・表セル空欄を Edit で修正（frontmatter / 見出し / gherkin フェンスは保全）"
  2. label: "個別対応" / description: "レポートだけ残してユーザーが手で直す"
  3. label: "対応しない" / description: "レポート確認のみ"

- **自動修正は confidence 100 の機械確定分のみ**（リンク先の追記・空セルの穴埋め提案）。意味判断（粒度・Why-answered）は over-correction を避けて提案に留める
- 修正時も frontmatter・見出し階層・gherkin コードフェンス・テンプレート構造は変更しない（構造を壊す結果は破棄）

---

## 処理フロー

```
1. Phase 0: 対象 spec.md / epic.md 特定 + scaffold ゲート
2. Phase 1: 観点1 構文（機械・ファネル第1段）
3. Phase 2: 観点2 粒度（意味）           ┐ scaffold 段階なら
4. Phase 3: 観点3 網羅性（双方向トレース）  │ 観点 2-5 を
5. Phase 4: 観点4 トレーサビリティ         ┤ スキップ
6. Phase 4.5: 観点5 遷移カバレッジ         ┘（4.5 は状態遷移表なし / 未記入でも skip）
7. Phase 5: severity×confidence でフィルタしてレポート
8. Phase 6: 修正提案（任意・AskUserQuestion 承認後のみ）
```

## effort 適応

実行時 effort = `${CLAUDE_EFFORT}` に応じて評価の深さを変える:

| effort | 構成 |
|---|---|
| `low` / `medium` | 観点 1（機械構文）+ 観点 3 の機械判定分（表⇔Scenario 双方向トレースのリンク切れ・空セル、confidence 100）+ 観点 4 のリンク解決 + 観点 5 の機械判定分（表 ⇔「カバーする辺」注記の双方向トレース・注記欠落、stateful spec のみ）に絞る。意味判断（観点 2 粒度・観点 3 の同値クラス過不足・観点 4 の Why-answered・観点 5 の巡回辺取りこぼし）は skip し「深掘りは effort を上げて再実行」と案内 |
| `high`（既定） | 全 5 観点を実施（機械 + 意味判断の全チェック項目） |
| `xhigh` / `max` | 上記に加え、依存 spec（`関連` セクションの他 spec）とのトレーサビリティ横断検証、境界値分析の過不足を因子ごとに精査、epic の Why に対する Scenario 群の十分性、状態遷移の臨界パス（正常完了 + 主要な差し戻し 1 本）の path 観点まで踏み込んで評価 |

---

## 注意事項

- **読み取り中心、書き込みは Phase 6 承認後のみ**: Phase 5 まではすべて read-only。Phase 6 の機械確定分修正だけが Edit を使う
- **scaffold と評価の責務分離**: 空骨格の生成は `create-spec`、埋めた後の評価が本スキル。Generator（create-spec）と Evaluator（evaluate-spec）を分けることで、生成時の思い込みに引きずられず独立に穴を見つける
- **機械判定を意味判定より先に**: 構文・リンク・表セルは grep で確定できる（外部オラクル）。意味判断（粒度・Why-answered）に LLM コストを割く前に、安いオラクルで確定分を落とす
- **over-correction 抑制**: 意味判断の指摘は confidence < 80 で「要確認」を明示し、断定で高 severity を作らない。修正は機械確定分のみ自動化する
- **API 安定保証（feature-dev 連携）**: `feature-dev` からの `Skill bdd-spec:evaluate-spec` 呼び出しを安定 API として扱う。引数で `spec=<path>` を渡すと Phase 0 の対象選択をスキップし非対話実行する（feature-dev Phase 1.4 embed 用途）。`--embed` 指定時は Phase 6 の AskUserQuestion をスキップし Phase 5 レポートをそのまま return する
