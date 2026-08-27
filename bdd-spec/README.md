# bdd-spec

BDD spec 駆動の scaffold プラグイン。user story ディレクトリ + epic / spec 2 ファイル粒度 + BDD 階層化 + 同値分割表テンプレを生成する。

## 使い方

```
/bdd-spec-create                                                    # 対話ヒアリング
/bdd-spec-create role=契約管理者 want=契約書を一括承認 why=月末処理短縮   # 非対話（ヒアリング skip）
```

ヒアリングで `{role}` / `{want}` / `{why}` を入力すると（または上の key=value で渡すと）、以下が生成される:

```
features/
  Userは、{role}として、{want}したい/       # 日本語パス（短縮モードあり）
    epic.md                                  # Why/What（散文、〜2KB）
    spec.md                                  # BDD Feature/Scenario/Examples + 同値分割表
```

## ディレクトリ命名

デフォルトは **日本語フルパス**（`ls features/` で機能カタログになる）。
Windows MAX_PATH や CI 環境向けに **短縮モード**を切り替え可能:

```json
// .claude/bdd-spec.json
{
  "shortPath": true,
  "featuresDir": "features",
  "language": "ja"
}
```

`featuresDir` は spec の配置先（既定 `features`）、`language` は生成言語（既定 `ja`）。

- `shortPath: false`（デフォルト）: `features/Userは、{role}として、{want}したい/`
- `shortPath: true`: `features/{role}-{verb}-{object}/`

詳細は `skills/create-spec/references/story-naming.md` を参照。

## ファイル構造

| ファイル | 役割 | 想定サイズ |
|---|---|---|
| `features/{story}/epic.md` | Why / What を散文で記述 | 〜2KB |
| `features/{story}/spec.md` | BDD Feature / Scenario / Examples / 同値分割表 | 〜13KB |
| `features/all_spec.md` | **用語 SSoT**（全ストーリー横断） | プロジェクトに 1 つ |
| `features/common_spec.md` | 共通仕様（権限・閾値・エラーメッセージのデフォルト） | プロジェクトに 1 つ |

## BDD 階層

```
features/
├ all_spec.md          # Layer 1: 用語 SSoT（別名禁止メタルール込み）
├ common_spec.md       # Layer 2: 横断 Background / 共通閾値
└ {story}/
    ├ epic.md          # Why/What
    └ spec.md          # Layer 3: Feature / Scenario
                       # Layer 4: #### Examples テーブル + 同値分割表
```

## 品質検証

scaffold した spec を埋めた後、`bdd-spec-evaluate` で 5 観点の静的レビューをかけられる:

```
/bdd-spec-evaluate                          # features/*/spec.md を選択して評価
/bdd-spec-evaluate features/{story}/spec.md # 対象を明示
/bdd-spec-evaluate spec=features/{story}/spec.md --embed  # 他プラグインからの非対話委譲（feature-dev Phase 1.4）
```

- **Gherkin 構文妥当性**（機械・ファネル第 1 段）: Feature / Scenario の Given-When-Then 構造・Scenario Outline の Examples・プレースホルダ対応
- **粒度一貫性**（意味）: When の単一アクション性・Then が実装詳細に踏み込んでいないか・1 Scenario 1 振る舞い
- **網羅性**: 同値分割表 ⇔ Scenario の**双方向トレース**（表にあるのに未カバーの同値クラス / 表にない orphan scenario を検出）
- **トレーサビリティ**: epic の AC ⇔ Scenario のリンク解決・未カバー AC の検出・Why が Scenario 群で満たされるか
- **遷移カバレッジ**（stateful のみ・dormant）: 状態遷移表 ⇔ Scenario の**双方向トレース**（未カバー辺 / orphan transition を検出）。アプリのワークフローを FSM とみなし巡回辺（差し戻し・再編集・リトライ）の網羅を辺カバレッジで検証。状態遷移表が無ければ発火しない

severity（🔴/🟡/🔵）× confidence（機械判定は 100、意味判断は不確実性に応じて）でフィルタし、修正は confidence 100 の機械確定分のみ承認後に自動化する（over-correction 抑制）。

## スコープ

### v0.1.0 (Phase 1)

- ✅ `bdd-spec-create` で user story dir + epic.md + spec.md scaffold
- ✅ `all_spec.md` / `common_spec.md` テンプレ提供
- ✅ 短縮モード切替

### v0.2.0 (Phase 2)

- ✅ `bdd-spec-evaluate` で BDD 構文 / 粒度 / 網羅性 / トレーサビリティの 4 観点静的レビュー
- ✅ 同値分割表 ↔ Scenario の双方向 trace 検証

### v0.3.0 (Phase 3)

- ✅ `bdd-spec-evaluate` に遷移カバレッジ観点（第 5 観点）を追加。状態遷移表 ⇔ Scenario の双方向トレース（stateful spec のみ dormant 発火）
- ✅ アプリのワークフローを DAG ではなく巡回する FSM としてモデル化し、巡回辺の網羅を辺カバレッジで検証（グラフは Scenario の「カバーする辺」注記から再構成し別管理しない）

動的検証（実際に Scenario を実行する）はスコープ外。

## 既存 plugin との関係

- `feature-dev` から `Skill bdd-spec:create-spec`（Phase 1.3 scaffold）と `Skill bdd-spec:evaluate-spec`（Phase 1.4 品質ゲート）の呼び出しを前提に API を安定化
- create-spec（Generator）と evaluate-spec（Evaluator）は責務分離。生成時の思い込みに引きずられず独立に穴を見つける設計

## 構成

| 種別 | 名前 | 説明 |
|------|------|------|
| コマンド | `/bdd-spec-create` | user story dir + epic/spec scaffold |
| コマンド | `/bdd-spec-evaluate` | 埋めた spec を 5 観点で静的レビュー |
| スキル | `create-spec` | scaffold ロジック + template 流し込み |
| スキル | `evaluate-spec` | 5 観点評価（構文/粒度/網羅性/トレーサビリティ/遷移カバレッジ） |
