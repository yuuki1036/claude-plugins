# Epic Template

`epic.md` のテンプレート。Why / What を散文で書く。想定サイズ 〜2KB。

`{PLACEHOLDER}` 形式は scaffold 時に置換される。

---

```markdown
---
last-validated: {CREATED_DATE}
phase: current
role: {ROLE}
---

# Epic: {WANT}

## User Story

Userは、**{ROLE}** として、**{WANT}** したい。

## Why（動機）

{WHY}

## What（成果物の輪郭）

このエピックが完了した時、以下が達成されている:

- [ ] {成果物1}
- [ ] {成果物2}
- [ ] {成果物3}

## Acceptance Criteria（受入条件）

以下の Scenario が `spec.md` で定義され、全て pass する:

- [ ] AC-1: {scenario タイトル} → `spec.md:#scenario-1`
- [ ] AC-2: {scenario タイトル} → `spec.md:#scenario-2`

> AC は `spec.md` の Scenario と **双方向リンク** する。spec.md 側からも epic.md の AC 番号を参照する。

## スコープ外

このエピックで **やらないこと** を明示:

- {対象外1}
- {対象外2}

## 関連 epic

- 依存: {他 epic への参照}
- 後続: {このエピック完了後に着手する別 epic}

## 用語

このエピック内で使う固有語のうち、`all_spec.md` の用語 SSoT に未登録のもの:

- {用語1}: {意味}
- {用語2}: {意味}

> 用語が確定したら `all_spec.md` に昇格させる。
```

---

## テンプレ設計判断

### `acceptance criteria` を箇条書きで `spec.md` の Scenario にリンクする理由

- 散文で書くと「どの Scenario が AC をカバーするか」が暗黙的になり、`bdd-spec-evaluate`（Phase 2）でトレーサビリティ検証ができない
- AC-N → `spec.md:#scenario-N` の機械的対応により、Scenario 削除時に未カバー AC を即検出できる

### `スコープ外` セクションを必須にした理由

- BDD spec 駆動でも、最初に「やらないこと」を書いておかないと scope creep が起きやすい
- スコープ外は別エピック化候補として `epic.md` の最後に残す

### 用語セクションを epic.md に持つ理由

- 新規エピックでは独自用語が増えるが、いきなり `all_spec.md` に追加すると polluted になる
- epic.md 内で「ローカル用語」として扱い、確定後に `all_spec.md` へ昇格させる二段階運用

### `last-validated` / `phase` frontmatter

- `doc-freshness` プラグインと互換。BDD spec ファイルも鮮度管理の対象
- 新規 scaffold 時は `phase: current` で開始
