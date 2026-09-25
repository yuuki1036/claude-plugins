# Event Bus 規約 — 詳細（責務・デバッグ・設計判断）

CLAUDE.md「Event Bus 規約」の詳細版。イベント命名規約とイベント表（機械照合対象）は CLAUDE.md 側が正本。永続化フォーマットと API はここが正本（CLAUDE.md の常駐量を減らすため移した）。

## 永続化

- イベントログ: `.claude/events.jsonl`（プロジェクトローカル、gitignored、JSON Lines 形式）
- 1 行 = 1 イベント: `{"ts":"<ISO8601>","plugin":"<name>","event":"<name>","payload":<obj>}`
- `plugin` は `SAFE_HOOK_NAME` がそのまま入る。hook 系は `dev-workflow:on-commit` のような
  `<plugin>:<hook>` 複合値、skill / command 系は素のプラグイン名になる（書式は publisher 依存）。
  **subscriber 側はプラグイン名の完全一致で絞らない** — 前方一致か event 名で絞る

## API（`safe-hook.sh` に含まれる）

```bash
# 発行
event_bus_publish "<event-name>" '<json-payload>'

# 直近 N 件取得（オプションで event 名フィルタ）
event_bus_tail "<event-name>" 10
event_bus_tail "" 20  # 全イベント

# ログクリア（テスト用）
event_bus_clear
```

## Publisher の責務

- 自プラグインから `event_bus_publish` を呼ぶ。**呼び出し元は hook とは限らない**（GitHub issue #185）:
  現在の 5 publisher のうち hook は 2 つで、残りは skill（`failure-journal:log-failure`）・
  command（`feature-dev`）・同梱スクリプト（`code-review/scripts/publish-review-event.sh`）
- payload は最小限の JSON（issue_id / file path / 識別子のみ。本文は含めない）
- 副作用がある場合は payload に冪等性キーを含める
- **`plugin` 欄の書式は publisher 側が決める**。hook 系は `SAFE_HOOK_NAME` をそのまま入れるので
  `dev-workflow:on-commit` のような `<plugin>:<hook>` 複合値になり、skill / command 系は素の
  プラグイン名になる。**subscriber はプラグイン名の完全一致で絞らない**（前方一致か event 名で絞る）
- **skill / command から呼ぶときは `safe_hook_init` を通さない**。あれは hook の stdin を消費する
  初期化で、stdin の来ない文脈で呼ぶとハングする。`SAFE_HOOK_NAME` を直接設定して
  `event_bus_publish` だけを使う（手本: `failure-journal/skills/log-failure/SKILL.md`）

## Subscriber の責務

- `event_bus_tail` で読み出し、自前で dedup（ts + event 名 + payload のハッシュ等）
- イベントログのフォーマットが将来変わる可能性があるので JSON Lines パーサ前提で実装
- Hook 内での重い処理は禁止（必要なら別 skill / agent に委譲）
- **`tail`/`grep` で直接読む経路を作らない**。`event_bus_tail` は `${CLAUDE_PROJECT_DIR:-$PWD}`
  を解決するので、worktree 内で実行したときの読み先が揃う。相対パスで直読みすると worktree と
  メインリポジトリで別のログを見る（`code-review/references/orchestration-measurement.md` に同型の実測）

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
