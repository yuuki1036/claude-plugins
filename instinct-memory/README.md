# instinct-memory

Claude Code の auto memory を活用した軽量 instinct 学習システム。

everything-claude-code の Continuous Learning v2 からコンセプトを借用し、
外部スクリプト・追加 API コストなしで、Claude 自身の判断のみで動作する。

## 仕組み

1. セッション中に Claude がユーザーの訂正・好み・繰り返しパターンを検知
2. `memory/instincts.md` に候補パターン（instinct）として記録
3. 複数セッションで繰り返し確認されたら confidence を昇格
4. high confidence になったら `MEMORY.md` に昇格（セッション横断で永続化）

## コマンド

- `/learn` — セッションからパターンを手動抽出
- `/instinct-status` — 現在の instinct 一覧を表示
- `/instinct-promote` — high confidence の instinct を MEMORY.md に昇格

## Confidence ルール

| レベル | 条件 | 扱い |
|---|---|---|
| low | 1回観測 | 記録のみ |
| medium | 2-3回観測 | 確認を取って適用 |
| high | 4回以上 or 明示的依頼 | MEMORY.md に昇格、自動適用 |
