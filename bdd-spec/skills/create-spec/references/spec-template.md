# Spec Template

`spec.md` のテンプレート。BDD Feature / Scenario / Examples + 同値分割表を含む。想定サイズ 〜13KB。

`{PLACEHOLDER}` 形式は scaffold 時に置換される。

---

```markdown
---
last-validated: {CREATED_DATE}
phase: current
role: {ROLE}
epic: ./epic.md
---

# Feature: {WANT}

> User story: Userは、**{ROLE}** として、**{WANT}** したい
> Why: 詳細は [epic.md](./epic.md) を参照

## Background

- 共通仕様は [../common_spec.md](../common_spec.md) を参照（権限・閾値・エラーメッセージのデフォルト）
- 用語定義は [../all_spec.md](../all_spec.md) を参照（用語 SSoT）

このフィーチャー固有の前提:

```gherkin
Given {このフィーチャー固有の前提条件1}
And {このフィーチャー固有の前提条件2}
```

---

## Scenarios

### Scenario 1: {正常系の代表ケース}

> Trace: [epic.md AC-1](./epic.md#acceptance-criteria受入条件)

```gherkin
Given {前提}
When {操作}
Then {結果}
And {追加の結果}
```

**カバーする因子**: {同値分割表の参照、例: 因子1=A, 因子2=B}

---

### Scenario 2: {異常系 or 別パターン}

> Trace: [epic.md AC-2](./epic.md#acceptance-criteria受入条件)

```gherkin
Scenario Outline: {タイトル}
  Given {前提}
  When ユーザーが <input> を入力する
  Then 結果は <expected> になる

  #### Examples

  | input    | expected | 因子 |
  |----------|----------|------|
  | {value1} | {result1}| {正常境界} |
  | {value2} | {result2}| {境界外} |
  | {value3} | {result3}| {空入力} |
```

---

## 同値分割・境界値分析表

このフィーチャーで扱う入力因子と境界値:

| 因子 | 同値クラス | 代表値 | カバー Scenario |
|------|-----------|--------|------------------|
| {因子1} | 正常範囲（下限） | {value} | Scenario 2 |
| {因子1} | 正常範囲（中央） | {value} | Scenario 1 |
| {因子1} | 正常範囲（上限） | {value} | Scenario 2 |
| {因子1} | 異常範囲（下限外） | {value} | Scenario 3 |
| {因子1} | 異常範囲（上限外） | {value} | Scenario 3 |
| {因子1} | 空 / null | (empty) | Scenario 4 |

> 各因子の各同値クラスが **少なくとも 1 つの Scenario** からカバーされていることを `bdd-spec-evaluate`（Phase 2）で静的検証する。

## トレーサビリティ

| AC | Scenario | カバー因子 |
|----|----------|------------|
| AC-1 | Scenario 1 | 因子1（正常中央）, 因子2（A） |
| AC-2 | Scenario 2 | 因子1（境界）, 因子2（B） |

> AC → Scenario, Scenario → 因子の双方向リンクを維持する。

---

## エラーケース

`common_spec.md` のデフォルトエラーメッセージに該当しない、このフィーチャー固有のエラー:

| エラーID | 発生条件 | メッセージ | 対応 |
|----------|---------|-----------|------|
| {ERR-001} | {条件} | {メッセージ} | {ユーザー対応} |

## 用語

このフィーチャー固有の用語（`all_spec.md` 未登録）:

- {用語}: {意味}

> 確定したら `all_spec.md` に昇格させる。

## 関連

- 依存フィーチャー: {他 spec への参照}
- 後続フィーチャー: {このフィーチャー完了後の別 spec}
```

---

## テンプレ設計判断

### Scenario Outline + Examples テーブルを推奨する理由

- 単独 Scenario の羅列だと因子の組み合わせが見えづらく、網羅性検証が難しい
- Examples テーブルで「入力 × 期待値 × 因子」を表形式にすると、`bdd-spec-evaluate` が同値分割表との対応を静的検証しやすい

### 同値分割表を必須にした理由

- BDD spec の「網羅性」評価は同値分割 / 境界値分析が王道
- 表を spec.md 内に置くことで、Scenario 追加時に「どの同値クラスをカバーするか」を意識せざるを得ない構造になる

### トレーサビリティ表を spec.md に書く理由

- AC ↔ Scenario の対応が暗黙的だと、Scenario 削除時に未カバー AC を見落とす
- 表で明示しておけば `bdd-spec-evaluate` が双方向リンク検証できる

### Background を `common_spec.md` 参照にした理由

- 全 Scenario に共通する前提（ログイン状態、権限など）を story ごとに書くと重複が指数的に増える
- `common_spec.md` で SSoT 化することで、共通前提の変更が一箇所で済む

### エラーケース表を spec.md に持つ理由（`common_spec.md` ではなく）

- 共通エラー（401 Unauthorized など）は `common_spec.md`
- フィーチャー固有エラー（「契約書ステータスが draft でないと承認できない」など）は spec.md
- 重複させず責務分離する
