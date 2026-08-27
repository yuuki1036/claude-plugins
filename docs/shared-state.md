# Shared State 規約（cross-plugin な永続ファイル）

複数プラグインが読み書きする shared state ファイルに **producer / consumer を明示する frontmatter** を必須化する。Classmethod「Claude Code マルチエージェントオーケストレーションパターン」記事の Shared State パターンを軽量実装したもの。

> Event Bus（時系列イベント）と shared state（最新状態の永続）は使い分ける。シグナル通知は events.jsonl、現在値の参照は shared state frontmatter を読む。

## frontmatter フォーマット

shared state markdown の冒頭に YAML frontmatter を置く。各 type のドメイン固有フィールドは別途追加してよい（衝突しない限り）。

```yaml
---
shared_state_type: session | follow-up | knowledge | event-cache
producer: <plugin-name>           # 主な書き込み元
consumers: [<plugin>, ...]        # 読み出し側プラグイン
schema_version: 1                 # フィールド変更時に bump
last_updated: <ISO8601>           # 書き込み時に更新（producer が責任を持つ）
---
```

## type 一覧

| type | 配置 | producer | 主な consumers | 永続性 |
|---|---|---|---|---|
| `session` | `.claude/session-context.md` | issue-workflow | code-review | セッション単位（gitignored） |
| `follow-up` | `{DATA_DIR}/{slug}/follow-ups/*.md` | issue-workflow | issue-workflow（dashboard / issue-maintain） | 永続（committed） |
| `knowledge` | `{DATA_DIR}/{slug}/knowledge/**/*.md` | issue-workflow | issue-workflow（knowledge / knowledge-lint / start） | 永続（committed）。knowledge は共通契約フィールドではなくドメイン固有 frontmatter（kind/status/verified/updated/tags）で代替し、consumer 側も契約フィールド（shared_state_type 等）を読まない |
| `event-cache` | （予約。events.jsonl の集計結果キャッシュ用） | - | - | - |

`{DATA_DIR}` は backend で決まる（local: `.claude/indie` / linear: `.claude/linear`）。
issue-workflow の backend 分岐規約に合わせた表記で、consumers は**プラグイン名**で書く
（frontmatter の `consumers` がプラグイン名を取るため。括弧内は主に読む skill）。

## Producer の責務

- 書き込み時に **必ず frontmatter を更新**する（`last_updated` の更新を含む）
- `schema_version` を変える場合は consumers 側の対応を確認してから bump する
- ファイル削除時は frontmatter を消すのではなく**ファイル自体を削除**する

## Consumer の責務

- frontmatter 不在のファイルも読める実装にする（**後方互換**: 既存ファイルが移行されるまで warning に留める）
- `shared_state_type` が想定外なら処理をスキップして warning 出力
- `last_updated` が極端に古い場合は stale 判定の判断材料に使ってよい

## 設計判断: なぜ frontmatter？なぜ flat な `.claude/shared/` に移行しない？

- 既存ファイルは **slug-scoped** な構造（`.claude/{workflow}/{slug}/knowledge/`）を持っており、flat 移行は 100+ 箇所のパス参照書き換えが必要でリスク高（2026-08 実測 114 箇所）
- frontmatter 規約だけなら配置はそのままで producer/consumer を明示でき、移行コストが極小
- 必要性が顕在化したタイミング（例: cross-plugin で同名ファイル衝突が頻発したら）に flat 移行を再検討する

## Gotcha

- session-context.md は **gitignored** なので frontmatter 不在のまま動くケースがある。consumer は frontmatter 必須を前提にしない
- follow-up は **committed** なので新規ファイルは frontmatter 付き必須
- **knowledge に共通契約フィールドの検査は無い**（GitHub issue #185）。`knowledge-lint` の 9 項目は
  broken link / 孤立知見 / index 不整合 / tags 表記ゆれ / 重複概念を見るもので、`shared_state_type` 等は
  対象外。上表のとおり knowledge はドメイン固有 frontmatter で代替する設計なので、これは欠落ではなく仕様
