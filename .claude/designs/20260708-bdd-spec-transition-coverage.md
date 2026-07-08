---
id: 20260708-bdd-spec-transition-coverage
title: FSM ベースの状態遷移カバレッジを bdd-spec の第5評価観点として追加する
status: approved
phase: current
last-validated: 2026-07-08
supersedes: []
superseded-by: null
issue: null
spec: null
adrs: []
tags: [bdd-spec, test-coverage, fsm, state-machine]
---

# FSM ベースの状態遷移カバレッジを bdd-spec の第5評価観点として追加する

## TL;DR

アプリのワークフローを FSM（巡回可）としてモデル化し、「全 transition を最低1 Scenario でカバー」する辺カバレッジをテスト網羅基準にする。グラフは別成果物として保守せず各 Scenario の `Given/When/Then` から再構成し、bdd-spec の実証済み「表 ⇔ Scenario 双方向トレース」機構に第5観点「遷移カバレッジ」を dormant で載せる。

## 背景 / 課題

このリポジトリのテスト導出は入力空間しか見ていない。

- bdd-spec の同値分割・境界値分析表（`bdd-spec/skills/create-spec/references/spec-template.md:76-98`）は「因子 × 同値クラス」＝入力の網羅を、evaluate-spec の観点3（`bdd-spec/skills/evaluate-spec/references/evaluation-rubric.md:70-84`）で双方向トレース機械検証する。
- 一方、状態遷移（フロー空間）の網羅を検証する仕組みは create/evaluate のどちらにも無い。評価4観点に「遷移カバレッジ」「状態網羅」「シーケンス順序」に相当する項目は0件。
- feature-dev の Phase 5.5 smoke test（`feature-dev/commands/feature-dev.md:564-604`）は diff への正規表現マッチで単一ページの初期化を叩くだけで、ユーザーフローを辿らない。ui-verify（`dev-workflow/skills/ui-verify/SKILL.md:134`）も人間がシナリオを手渡す。

惜しいことに、`bdd-spec/.../references/glossary-ssot.md:28-36` に `draft→review, review→approved/rejected, rejected→draft` という状態遷移表が既にあるのに、それを Scenario に照合する仕組みが無い。「入力の同値クラスは表化され双方向トレースで機械検証されるのに、状態遷移は辞書に列挙されるだけで Scenario への網羅トレースが設計されていない」という非対称が、この設計が埋める空白地帯。

## ゴール / 非ゴール

- **ゴール**: bdd-spec に「状態遷移の網羅を Scenario に対して双方向トレースで機械検証する」第5観点を追加する。既存の同値分割表機構と対称な、低コストで drift しない形で。
- **ゴール**: 巡回辺（差し戻し・再編集・リトライ）の抜けを構造的に検出可能にする ── ここがバグの温床であり、DAG モデルが原理的に取りこぼす箇所。
- **非ゴール**: 実行時のフロー辿り E2E（ui-verify / Playwright 駆動）は対象外。本設計は静的な spec レビュー層に閉じる。理由: 実行時検証はモデル保守コストとスコープが跳ね上がり、bdd-spec の軽量さを損なう。
- **非ゴール**: 全パスカバレッジは要求しない。理由: 巡回があるとパスが指数爆発する。辺カバレッジを既定にする。
- **非ゴール**: 依存 DAG による smoke test 対象選定（feature-dev Phase 5.5 の高度化）は別テーマとして切り離す。これは本当に非巡回な軸で、フローのテスト導出とは別問題。

## 確定した前提

- **フロー/遷移カバレッジは bdd-spec に現状存在しない**（agent 探索で確認。`evaluation-rubric.md` の4観点に該当項目0件、`spec-template.md` の表の軸は入力因子のみ）。
- **各 Scenario は辺の情報を内包するが、機械抽出には構造化注記が要る**（design-review BLOCKER F1 で確定）: `Given/When/Then` は概念的には辺 `S1 --action--> S2` だが、自由文 prose からの (遷移元, action, 遷移先) 抽出は意味判定になる（`evaluation-rubric.md:61-63` が Given/When/Then を意味判定として扱う）。そこで Scenario に構造化注記「**カバーする辺**: `draft --submit--> review`」を必須化し、観点3.3 と同じ grep 文字列一致に落とす。これで「グラフを Scenario から機械再構成し別管理不要」が本当に決定的になる（当初の「新記法は不要」前提は撤回）。
- **glossary-ssot に状態遷移表の前例がある**（`glossary-ssot.md:28-36` の `遷移可能先` 列）。ただし evaluate 側にこの列を消費する判定は無い（grep で確認）。
- **create/evaluate は責務分離済み**（Generator/Evaluator。`create-spec/SKILL.md:199`, `evaluate-spec/SKILL.md:163`）。第5観点は scaffold 側（表の空骨格）と評価側（トレース検証）に分けて載せる。
- **既存スコアリングは severity×confidence + 報告閾値マトリクス**（`evaluation-rubric.md:26-30`）。第5観点もこれに乗せる。
- **SSoT は spec ローカル自完結**（grill で確定）: 状態遷移表は spec.md 内に置き、同値分割表と同じく自完結。glossary の `遷移可能先` は任意の整合オラクル。
- **新プラグインは作らない**: CLAUDE.md の component-addition-advisor 原則。bdd-spec への機能追加が退路（既存拡張で解ける）。

## 採用案

bdd-spec を拡張し、状態遷移カバレッジを create（scaffold）+ evaluate（第5観点）に分けて dormant で載せる。

### (A) create-spec: spec.md に状態遷移表を dormant scaffold

同値分割表の隣に、stateful なフィーチャーのときだけ埋める表を scaffold する（`spec-template.md` に追記）:

```markdown
### 状態遷移表（stateful なフィーチャーのみ。無ければ空のまま）
| 遷移元 | action | 遷移先 | カバー Scenario |
|--------|--------|--------|----------------|
| draft  | submit | review | #scenario-1 |
| review | reject | draft  | #scenario-3 |
| draft  | save   | draft  | （未カバー）  |
```

- 各 Scenario に構造化注記「**カバーする辺**: `draft --submit--> review`」を必須化する（同値分割表の「カバーする因子」注記と対称）。これで 5.2 の辺抽出が grep 文字列一致になり、状態名も正規形で書かれるので prose↔表の名寄せ問題（旧 design-review F3）が同時に消える。
- 「種別」（前方 / 巡回 / 自己）は表に手書きしない。evaluate 側が再構成グラフから導出する（自己 = 遷移元==遷移先、巡回 = 後退辺）。手動列は誤記入源で drift 原則に反するため置かない（design-review F5）。
- 空なら stateless と判断し、評価側の第5観点は丸ごと skip（dormant 発火ゲート）。ただし「stateful なのに空」の偽陰性を検出する発火条件は open 参照（design-review F2）。

### (B) evaluate-spec: 第5観点「遷移カバレッジ」を追加

既存4観点のファネルにそのまま乗せる（`evaluation-rubric.md` に観点5 を追記、`SKILL.md` の Phase 構成に追加）。

**機械判定（confidence 100・ファネル第1段。観点3 と同型の grep リンク解決）**
- 5.1 表の各辺の「カバー Scenario」が実在 Scenario を指すか。未カバー辺 = 🟡。
- 5.2 各 Scenario の構造化注記「カバーする辺」から辺を回収し、表に宣言されているか照合する。orphan transition（表に無い辺を Scenario が踏む）= 🟡。注記が grep 一致するので confidence 100 が成立する。
- 5.2b stateful spec（表が非空）の Scenario に「カバーする辺」注記が無い → 「注記欠落」を 🟡（意味判定にフォールバックせず fail-closed。注記必須の裏返し）。

**意味判定（confidence 付き）**
- 5.3 stateful spec（表が非空）なのに、reject/戻る/リトライ相当の巡回辺が表に1つも無い → 「巡回辺の取りこぼし疑い」を 🟡 で指摘。DAG 的な happy-path 偏重の検出。
- 5.4 終端状態から出る辺がある等の構造矛盾。
- 5.5 glossary に `遷移可能先` があり、かつこの spec が該当 entity を触る場合、spec ローカル表の遷移が glossary と矛盾しないかを整合チェック（オラクルが在るときだけ発火）。

**カバレッジ基準は辺（既定）**
- 全パスは要求しない。臨界パス（正常完了 + 主要な差し戻し1本）だけ path 観点を `${CLAUDE_EFFORT}` high 以上で追加。

### (C) dormant 発火ゲート（noise 抑制）

bdd-spec は既に4観点あり重い。stateless CRUD/query に第5観点を出すとノイズになるため、状態遷移表が空なら観点5 を起動しない。判定は表セルの非空を grep で機械化。

### コスト×精度10原則への対応（CLAUDE.md 規約）

- 原則1 ファネル: 辺のリンク解決（機械）を先頭、巡回辺欠落の判定（意味）を後段 — 採用。
- 原則8 外部オラクル + fail-closed: `Given/When/Then` からの辺再構成は決定的。パース不能な曖昧 spec は stateless 扱いに倒さず「要確認で保留」に — 採用。
- 原則2/10 2軸スコア + 確信度フィールド: 既存 severity×confidence にそのまま乗る — 採用。
- 全パス網羅・別グラフ管理: あえて捨てる（パス爆発 / drift 回避）。辺カバレッジ + Scenario 再構成で代替。

## 検討した代替案

| 観点 | 案 A（採用）bdd-spec 第5観点 | 案 B 独立プラグイン flow-coverage | 案 C feature-dev smoke test 拡張 |
|------|------|------|------|
| 変更量 | 小（表 scaffold + 観点1つ） | 大（新プラグイン一式） | 中（Phase 5.5 + ui-verify 連携） |
| 機構再利用 | 高（双方向トレース流用） | 低（機構を再実装） | 低（実行時系は別機構） |
| drift リスク | 極小（Scenario から再構成） | 高（別モデルを保守） | 高（実行時モデル保守） |
| ノイズ | 小（dormant 発火） | 中 | 中 |
| スコープ | 静的 spec レビューに閉じる | フロー全般に拡張 | 実行時 E2E に拡張 |

- **案 B 却下**: component-addition-advisor 原則に反し、双方向トレース機構を二重実装する。別モデル保守で drift する。
- **案 C 却下**: 実行時フロー辿りはモデル保守コストとスコープが跳ね、静的レビューの安さを失う。依存 DAG による対象選定は将来の別テーマとして分離。

## 設計判断ログ

- [→ADR候補] アプリのワークフローのテスト網羅は DAG ではなく FSM（巡回可）でモデル化する。巡回辺（差し戻し・再編集・リトライ）はバグの温床であり、DAG は原理的にこれを表現できない。カバレッジ基準は辺（全 transition を最低1回）を既定とし、全パスは臨界パスに限定する。
- [→ADR候補] フローモデルは別成果物として保守せず、各 Scenario から機械再構成する。別管理のグラフは必ず drift して死ぬ（doc-freshness が存在する理由と同じ問題）。宣言（期待辺 = 状態遷移表）と再構成（実カバー辺 = Scenario の構造化注記「カバーする辺」）を突き合わせて未カバー辺を落とす。**再構成を決定的にするため注記を必須化する**（自由文 prose からの辺抽出は意味判定になるため。design-review BLOCKER F1）。
- [local] 状態の「種別」（前方/巡回/自己）は手書きせず evaluate が再構成グラフから導出する（自己 = 遷移元==遷移先、巡回 = 後退辺）。手動列は drift 源のため置かない（design-review F5）。
- [local] 状態遷移の宣言は spec ローカル自完結（状態遷移表を spec.md に置く）。glossary の `遷移可能先` は任意の整合オラクルとして、該当 entity を触る spec でだけ矛盾チェックに使う。既存の同値分割表が spec ローカルであることと対称。
- [local] 第5観点は stateful spec（状態遷移表が非空）でのみ dormant 発火。stateless では起動せず noise を出さない。
- [local] 未カバー巡回辺は 🟡 advisory に留め 🔴 にしない。stateless spec への誤検知コストを避けるため（fail 方向を noise 側でなく見逃し許容側に倒す判断）。

## 未解決事項 (open)

- **stateful 判定の偽陰性ゲート**（design-review MAJOR F2）【実装で部分対応・follow-up 残】: dormant 発火ゲートは「状態遷移表が非空か」で stateful を判定するため、stateful なのに書き手が表を空のままにすると第5観点が entity 単位で丸ごと skip され、巡回辺の抜けを永久に見逃す。
  - v0.3.0 実装: 基本ゲート（表が空 / 不在なら skip）のみ実装した。「stateful なのに空」を検出する外部シグナル（glossary の `遷移可能先` entity 名が spec 本文に出現するか等）のバックストップは**未実装**。
  - 残タスク（follow-up）: 軽量版バックストップ（glossary entity 名の出現検出）を追加するか、空振りリスクを「受容」として明記するかを別途判断する。現状は後者（見逃し許容）で運用。
- **feature-dev Phase 1.4 への波及**【実装で解決 = 無変更】: feature-dev Phase 1.4 は evaluate-spec の出力を受けるだけで観点数をハードコードしていないことを確認（grep で `4 観点` 参照なし。CHANGELOG の履歴記述のみ）。(a) 無変更を採用。
- **状態遷移表と glossary の記法統一**【実装で解決 = (b) 採用】: rubric 観点 5.5 を「glossary は `遷移可能先` のまま、evaluate が (遷移元, 遷移先) ペアだけ突き合わせる」で実装した。prose↔表の名寄せ（旧 design-review F3）は構造化注記「カバーする辺」を正規形で書かせることで解消済み。

## 実装ブリッジ (Implementation Bridge)

1. 実装着手の単位（Issue 分解案）:
   - (1) create-spec: `spec-template.md` に状態遷移表（遷移元/action/遷移先/カバー Scenario）を dormant scaffold として追記 + Scenario への構造化注記「カバーする辺」の必須化を scaffold ガイドに明記。
   - (2) evaluate-spec: `evaluation-rubric.md` に観点5「遷移カバレッジ」を追記（5.1-5.5）+ `SKILL.md` の Phase 構成と `${CLAUDE_EFFORT}` 分岐に組み込み。dormant 発火ゲート（表非空判定）を実装。
   - (3) **「4観点→5観点」の SSoT 文言更新**（design-review MAJOR F4）: 観点数を明記している箇所を一括で 4→5 に更新する。対象 = `evaluate-spec/SKILL.md` description（「4 観点」）/ `create-spec/SKILL.md`（description + Phase 5 の scaffold 列挙に状態遷移表・「カバーする辺」注記を追加）/ `bdd-spec/.claude-plugin/plugin.json` description / `.claude-plugin/marketplace.json` の bdd-spec 行 / `.claude-plugin/INDEX.md` / ルート `CLAUDE.md` のプラグイン一覧表 bdd-spec 行。SSoT 同期は pre-commit の `validate-ssot.sh` が拾う。
   - (4) feature-dev Phase 1.4 のドキュメント整合を確認（open の有力案どおり無変更なら確認のみ）。
   - (5) bdd-spec の version バンプ（MINOR: 機能追加）+ CHANGELOG.md 更新 + `.claude-plugin/marketplace.json` 同期。
   - feature-dev 起動引数（実装を一気通貫でやる場合）: `/feature-dev bdd-spec に状態遷移カバレッジ第5観点を追加 spec=null`
2. 検証方法:
   - stateful な実例 spec（例: `draft→review→approved/rejected` を持つ spec）を用意し、わざと1辺の Scenario を欠いて evaluate-spec が未カバー辺を 🟡 で検出するか確認。
   - stateless spec で第5観点が発火しない（noise ゼロ）ことを確認。
   - **evals 要否の再判定（F4）**: 「4観点→5観点」は SKILL.md description の変更に該当するため（CLAUDE.md 規約「description/トリガー変更時は evals/runner.py で回帰テスト」）、当初の「description 変更が無ければ evals 不要」前提は反転する。トリガーフレーズ自体を変えないなら影響は小さいが、description 変更を理由に `evals/runner.py` を1回流してスキル選択のデグレが無いか確認する。`/quality-check` で SSoT 同期（4→5 の波及漏れ）も検証。
3. 実装完了時の doc 更新手順:
   - frontmatter の `phase: target` → `current`、`last-validated` を更新。
   - 実装で辞書記法（open 2件）が確定したら本文に追記。方式が変わったら supersede。

## 関連

- 関連 Issue: なし
- 関連 spec: なし
- 関連 ADR: （Phase 6 で `[→ADR候補]` 2件を切り出し予定）
- 関連 design doc: なし
- 参照コード: `bdd-spec/skills/create-spec/references/spec-template.md:76-98`, `bdd-spec/skills/evaluate-spec/references/evaluation-rubric.md:70-99`, `bdd-spec/.../glossary-ssot.md:28-36`, `feature-dev/commands/feature-dev.md:564-604`
