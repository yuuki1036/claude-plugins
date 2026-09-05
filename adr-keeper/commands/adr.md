---
description: "設計判断 (ADR) を append-only で記録・一覧・supersede する トリガー: 「ADR作成」「設計判断記録」「アーキテクチャ決定記録」「ADR supersede」「ADR一覧」 「決定の理由を残す」「/adr」「architecture decision record」"
user_invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Bash
  - AskUserQuestion
---

`adr` スキルを使って、Architecture Decision Record (ADR) を管理してください。

## 引数

`$ARGUMENTS`:
- `list`（または未指定） → `.claude/adr/*.md` を一覧表示（id 降順）
- `new <title>` → 新規 ADR を作成（status は既定 `accepted`）
- `supersede <old-id> <new-title>` → 新 ADR を作成し、旧 ADR を superseded に更新

## 実行

`adr` スキルの処理フローに従ってください:

1. Phase 0: 保存先確認（`.claude/adr/`、無ければ作成）
2. Phase 1: サブコマンド判定（list / new / supersede）
3. Phase 2 (list): frontmatter を解析して id / title / status / phase / last-validated の表を id 降順で表示
4. Phase 3 (new): 記録価値 3 条件ゲート（supersede 経由は除外）→ Bash で `date +%Y%m%d%H%M%S` → kebab タイトル生成 → template から Write
5. Phase 4 (supersede): 新 ADR 作成 + 旧 ADR 4 フィールド更新（status / phase / superseded-by / last-validated）+ 両方を Read で確認
6. Phase 5: 完了報告
