# bdd-spec

BDD spec 駆動の scaffold プラグイン。user story ディレクトリ + epic / spec 2 ファイル粒度 + BDD 階層化 + 同値分割表テンプレを生成する。

## 使い方

```
/bdd-spec-create
```

ヒアリングで `{role}` / `{want}` / `{why}` を入力すると、以下が生成される:

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
  "shortPath": true
}
```

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

## スコープ

### v0.1.0 (Phase 1)

- ✅ `bdd-spec-create` で user story dir + epic.md + spec.md scaffold
- ✅ `all_spec.md` / `common_spec.md` テンプレ提供
- ✅ 短縮モード切替

### Phase 2 候補（別 Issue）

- ⏸ `bdd-spec-evaluate` で BDD 構文 / 粒度 / 網羅性 / トレーサビリティの 4 観点静的レビュー
- ⏸ 同値分割表 ↔ Scenario の双方向 trace 検証

## 既存 plugin との関係

- `feature-dev` から `Skill bdd-spec:create-spec` 呼び出しを前提に API を安定化（Phase 1 仕様確定済）
- 既存の評価系 skill（spec-evaluator など）とは責務分離（本 plugin は **scaffold + 静的構文レビュー**に絞り、動的検証は対象外）

## 構成

| 種別 | 名前 | 説明 |
|------|------|------|
| コマンド | `/bdd-spec-create` | user story dir + epic/spec scaffold |
| スキル | `create-spec` | scaffold ロジック + template 流し込み |
