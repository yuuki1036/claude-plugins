---
description: BDD spec (spec.md / epic.md) を 5 観点で静的レビューする品質ゲート
user_invocable: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Edit
  - AskUserQuestion
---

evaluate-spec スキルを使って、埋めた BDD spec を静的レビューしてください。

## 引数

`$ARGUMENTS`:
- 未指定 → `features/*/spec.md` を Glob して対象を選択（1 件なら自動、複数なら AskUserQuestion）
- パス指定（例: `features/{dirname}/spec.md` または story ディレクトリ）→ その spec を対象
- `spec=<path>` 形式 → 非対話で対象を確定（feature-dev embed 用途）

## 実行

`evaluate-spec` スキルの処理フローに従ってください:

1. Phase 0: 対象 spec.md / epic.md 特定 + scaffold ゲート
2. Phase 1: 観点1 Gherkin 構文妥当性（機械・ファネル第1段）
3. Phase 2: 観点2 粒度一貫性（意味）
4. Phase 3: 観点3 網羅性（同値分割表 ⇔ Scenario 双方向トレース）
5. Phase 4: 観点4 トレーサビリティ（epic ⇔ spec）
6. Phase 4.5: 観点5 遷移カバレッジ（状態遷移表 ⇔ Scenario・stateful のみ / 表が空なら skip）
7. Phase 5: severity×confidence でフィルタしてレポート
8. Phase 6: 修正提案（任意・AskUserQuestion 承認後のみ）
