---
description: 再発しうる失敗を journal (JSON Lines) に append する
user_invocable: true
allowed-tools:
  - Read
  - Bash
---

log-failure スキルを使って、再発しうる失敗を journal に記録してください。

## 引数

`$ARGUMENTS`:
- 失敗の現象説明が含まれていればそれを起点に使う
- 未指定 → 直近の会話コンテキストから失敗現象を要約する

## 実行

`log-failure` スキルの処理フローに従ってください:

1. Phase 0: journal パス確認（`.claude/failure-journal/journal.jsonl`）
2. Phase 1: 再発性判定（「同じ状況で再発しうるか」の単一基準）
3. Phase 2: tag 生成・検証（kebab-case / 30 文字以内 / 固有名詞禁止 / 現象主体）
4. Phase 3: append（Bash + jq、valid JSON 保証・append-only）
5. Phase 4: `failure:logged` event publish
6. Phase 5: 完了報告
