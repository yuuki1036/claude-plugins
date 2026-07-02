---
description: 技術設計書 (design doc) を作成・一覧・supersede・export する
user_invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - Skill
  - AskUserQuestion
---

`design-doc` スキルを使って、技術設計書 (design doc) を管理してください。

## 引数

`$ARGUMENTS`:
- `new [title]`（または未指定） → 新規 design doc を作成（grill → 代替案比較 → 永続化）
- `list` → `.claude/designs/*.md` を一覧表示（id 降順）
- `supersede <old-id> <new-title>` → 新 doc を作成し、旧 doc を superseded に更新
- `mode=export title=... content=...` → 他プラグイン連携用の非対話書き出し（grill / 設計フェーズを skip。先頭語 `export ...` でも受理）

## 実行

`design-doc` スキルの処理フローに従ってください:

1. Phase 0: 保存先確認（`.claude/designs/`、無ければ作成）+ サブコマンド判定
2. Phase 1: 入力収集（Issue / spec.md / 既存 doc の検出）
3. Phase 2: read-only コードベース探索
4. Phase 3: grill（自己解決 → 依存順 1 問ずつ・推奨つき）
5. Phase 4: 代替案 2〜3 + トレードオフ比較表 → 採用案確定
6. Phase 5: template から書き出し（実装ブリッジ必須・writing-polish dormant）
7. Phase 6: [→ADR候補] の adr-keeper 切り出し（dormant）
8. Phase 7: 完了報告
