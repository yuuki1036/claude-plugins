# Event Bus 規約 — 詳細（責務・デバッグ・設計判断）

CLAUDE.md「Event Bus 規約」の詳細版。永続化フォーマット・API・イベント命名規約・イベント表（機械照合対象）は CLAUDE.md 側が正本。

## Publisher の責務

- 自プラグインの hook 内で `event_bus_publish` を呼ぶ
- payload は最小限の JSON（issue_id / file path / 識別子のみ。本文は含めない）
- 副作用がある場合は payload に冪等性キーを含める

## Subscriber の責務

- `event_bus_tail` で読み出し、自前で dedup（ts + event 名 + payload のハッシュ等）
- イベントログのフォーマットが将来変わる可能性があるので JSON Lines パーサ前提で実装
- Hook 内での重い処理は禁止（必要なら別 skill / agent に委譲）

## デバッグ

```bash
# 直近 10 件
tail -n 10 .claude/events.jsonl

# 特定イベントを追う
grep '"event":"issue:completed"' .claude/events.jsonl | jq .
```

## 設計判断: なぜ JSON Lines + ファイル？

- Claude Code はローカル CLI なので EventBridge / Redis Pub/Sub は過剰
- 記事の「デバッグ困難」リスクは `tail` / `grep` でカバー
- セッション跨ぎで参照可能（git にコミットしないが project-local には残る）
- 全プラグインに既に配布されている `safe-hook.sh` に乗せられるので追加配布物なし
