---
description: design doc を複数視点（minimal/clean/pragmatic/risk）で静的レビューする
user_invocable: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Edit
  - Agent
  - AskUserQuestion
---

`design-review` スキルを使って、design doc を静的レビューしてください。

## 引数

`$ARGUMENTS`:
- `[doc-id]` → 対象 doc の id（省略時は `.claude/designs/` の draft/approved な doc から自動選択）
- `--focus <minimal|clean|pragmatic|risk>` → 単一視点に絞る（effort 分岐を上書き）

## 実行

`design-review` スキルの処理フローに従ってください:

1. Phase 0: 対象 doc 特定
2. Phase 1: doc + 関連成果物（spec / ADR / Issue）読み込み
3. Phase 2: 視点トリアージ（effort: low/medium → メイン 2 視点 / high → agent ×3 / xhigh,max → agent ×4）
4. Phase 3: design-reviewer agent 並列レビュー（またはメインコンテキスト）
5. Phase 4: findings 集約（dedup → confidence フィルタ（<50 は MINOR 降格、BLOCKER は残す）→ severity × セクション表）
6. Phase 4.5: 反証（high 以上・BLOCKER/MAJOR を独立 design-reviewer agent で敵対的検証。反証された finding は severity を下げるか明示、BLOCKER は fail-closed で残す）
7. Phase 5: 採用 finding を doc に反映 + last-validated 更新
8. Phase 6: 完了報告
