---
description: journal を集計し 30日×3回閾値超えの失敗パターンを抽出して規約還流提案を出す
user_invocable: true
allowed-tools:
  - Read
  - Bash
  - AskUserQuestion
---

retro スキルを使って、再発する失敗パターンを集計し還流提案を生成してください。

## 引数

`$ARGUMENTS`:
- 未指定 → デフォルト窓（直近 30 日）・デフォルト閾値（同一 tag 3 回以上）で集計
- 数値指定（例: `60`） → 集計窓の日数を上書き

## 実行

`retro` スキルの処理フローに従ってください:

1. Phase 0: journal 読み込み（retro 実行中のみ参照可）
2. Phase 1: 窓・閾値の決定（30 日 / 3 回）
3. Phase 2: tag 別集計（Bash + jq、30 日境界フィルタ → group → count）
4. Phase 3: 閾値超え tag の抽出
5. Phase 4: 還流先提案（AGENTS.md/CLAUDE.md・hook・skill のどれに反映するか + 既存ガードレール未カバー理由）
6. Phase 5: レポート出力
7. Phase 6: 還流アクション確認（任意、AskUserQuestion）
