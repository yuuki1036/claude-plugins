---
description: BDD spec 駆動の user story を scaffold する（user story dir + epic.md + spec.md）
user_invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
---

create-spec スキルを使って、BDD spec 駆動の user story を scaffold してください。

## 引数

`$ARGUMENTS`:
- 未指定 → ヒアリングで {role} / {want} / {why} を聞き出す
- key=value 形式（例: `role=契約管理者 want=契約書を一括承認 why=月末処理短縮`） → 引数で渡された値を使い、ヒアリングをスキップ
- `shortPath=true` 付加で短縮モード（`{role}-{verb}-{object}`）に切替

## 実行

`create-spec` スキルの処理フローに従ってください:

1. Phase 0: `.claude/bdd-spec.json` 読み込み（または default）
2. Phase 1: {role} / {want} / {why} ヒアリング（引数で埋まっていればスキップ）
3. Phase 2: dir 名決定 + 衝突チェック（AskUserQuestion）
4. Phase 3: all_spec.md / common_spec.md 初期化（必要なら）
5. Phase 4: epic.md 生成
6. Phase 5: spec.md 生成
7. Phase 6: 用語整合チェック
8. Phase 7: 完了報告
