# Linear プロジェクト管理ルール

このプロジェクトは `.claude/linear/` で Linear Issue を管理している。以下のルールに従うこと。

## セッション開始時

1. `/session-start` を実行して作業コンテキストを読み込む
2. ブランチ名から Issue ID を自動特定し、関連ファイルを読み込む

## ブランチ命名規則

- `{type}/{TEAM-ID}-{description}` 形式を使う
- 例: `feat/TEAM-123-add-login`, `fix/TEAM-456-null-check`

## Issue ファイル管理

- Issue ファイル: `.claude/linear/{slug}/issues/{ISSUE-ID}.md`
- プロジェクト doc: `.claude/linear/{slug}/projects/*.md`
- 作業の進捗は Issue ファイルのチェックリストに反映する
- セッション終了前に `/issue-maintain` で Issue ファイルを更新する

## Linear MCP 連携

- **Linear API は読み取り専用**: `get_issue`, `list_issues`, `get_project` 等の読み取りのみ使用する。`save_issue` 等の書き込み API は、ユーザーが「Linear の Issue を更新して」等と明示的に指示した場合のみ使用する
- 「Issue 更新」「Issue 整理」はローカルの Issue ファイル（`.claude/linear/*/issues/*.md`）の更新を意味する。Linear API の更新ではない
- `/linear-maintain` で Linear → ローカルの一方向同期を実行する（プロジェクト doc、Issue ステータスの取得・更新）
- Linear 側のステータス変更は Linear UI で行う

## Agent Team の活用

- タスクに取り掛かる際は Agent team（複数エージェントの並列起動）を積極的に使う
- 大きなタスクを単一エージェントで処理することを禁止する。調査・実装・テストなど独立した作業は並列エージェントに分割する
- エージェントの起動に確認は不要。必要なだけ立ち上げてよい

## Follow-up タスクの検知

作業中に以下のシグナルを検知した場合、follow-up タスクとして記録することを提案する:

**検知パターン:**
- 「これは別タスクで」「後でやる」「スコープ外だけど気になる」
- 「今は触らないけど」「技術的負債として残す」「TODO: 後で直す」
- ユーザーが作業を意図的に中断・保留する発言
- コードの TODO コメントを書いた・発見した
- Issue の「スコープ外」セクションに項目を追加した

**提案フォーマット:**

```
follow-up を記録しますか？
タイトル: 「{検知した内容の要約}」
type: {推定タイプ}

→ `/follow-up new` で記録
```

**重要:** 提案は1回のみ行う。ユーザーが断った場合は再提案しない。
作業の流れを止めないことを優先する。

## Knowledge の活用

- セッション開始時・コンパクション後に knowledge インデックスが自動注入される
- 実装方針の検討時や問題解決時に、関連する knowledge を Read して活用する
- `/knowledge` で一覧表示、`/knowledge search <キーワード>` で検索できる
- 新しい知見は `/issue-maintain` の実行時に自動的に切り出される

## 作業フロー

1. セッション開始 → `/session-start`
2. 新規 Issue 作成が必要 → `/issue-create`
3. 作業中の進捗更新 → Issue ファイルのチェックリストを更新
4. 作業中に follow-up 発生 → `/follow-up new` で記録
5. セッション終了前 → `/issue-maintain` で Issue ファイルを整理
6. follow-up の確認 → `/follow-up list` で一覧、`/follow-up promote` で Issue 昇格
7. 定期的な同期 → `/linear-maintain` でプロジェクト doc を最新化
