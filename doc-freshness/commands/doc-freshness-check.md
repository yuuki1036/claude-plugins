---
description: ドキュメント鮮度を機械的に検証する（frontmatter / phase stale / 行数 / link / superseded）
user_invocable: true
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - Edit
  - Write
  - AskUserQuestion
---

doc-freshness スキルを使って、ドキュメント鮮度を検証してください。

## 引数

`$ARGUMENTS`:
- 未指定 → プロジェクト全体走査
- ファイルパス指定（例: `CLAUDE.md`） → 単一ファイル走査

## 実行

`doc-freshness` スキルの処理フローに従ってください:

1. Phase 0: 設定ロード（`.claude/doc-freshness.json` または default）
2. Phase 1: 対象ファイル特定 + grace period 判定
3. Phase 2: frontmatter スキーマ検証
4. Phase 3: phase 別 stale 判定
5. Phase 4: harness doc 行数ガード
6. Phase 5: internal link 検証
7. Phase 6: superseded 参照禁止
8. Phase 7: レポート出力
9. Phase 8: 修正提案（任意、AskUserQuestion）
