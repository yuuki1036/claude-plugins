---
name: linear-maintain
description: >
  Linear MCP と同期してローカルの Issue/プロジェクト管理ファイルを最新化する。
  トリガー: 「/linear-maintain」「Linear同期」「Linearステータス同期」「プロジェクトdoc最新化」「プロジェクト整理」
  引数: [プロジェクトスラッグ（省略時は .claude/linear/ 配下の全スラッグ対象）]
effort: medium
allowed-tools:
  - mcp__linear__list_issues
  - mcp__linear__list_projects
  - mcp__linear__get_issue
  - mcp__linear__get_project
  - mcp__linear__list_issue_statuses
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
---

# Linear メンテナンス

## 概要

Linear MCP と連携し、`.claude/linear/` 内のプロジェクト管理ファイル群を最新状態に同期する。

## コマンド

| コマンド | 動作 |
|----------|------|
| `/linear-maintain` | 全チームをメンテナンス |
| `/linear-maintain {slug}` | 指定チームのみメンテナンス |

---

## 処理内容

### 1. プロジェクト doc の更新

`linear/{slug}/projects/` 内の各プロジェクト doc を Linear MCP `get_project` で再取得・更新する。

- `last_updated` を今日の日付に更新
- 概要・ステータスを最新化
- **関連 Issue テーブルの更新**（後述）

> **プロジェクト doc テンプレート**: `${CLAUDE_PLUGIN_ROOT}/skills/linear-maintain/references/project-doc-template.md` を Read で参照すること。

### 2. 関連 Issue テーブルの更新

Linear MCP `list_issues` でプロジェクト内の Issue 一覧を取得し、各プロジェクト doc の「関連 Issue」テーブルを更新する。

- 各 Issue の担当者・ステータスを最新化
- PR がある場合はリンクを追加
- Done の Issue はテーブルから削除（対応する issues/ ファイルがある場合はそちらで追跡）

### 3. Issue ステータス同期

`issues/` 内の `in-progress` ファイルを走査し、ステータスの整合性を確認する：

| ローカル状態 | 判定 | アクション |
|-------------|------|-----------|
| 進捗チェックリストが全完了 | completed 候補 | `status: completed` への変更を提案 |
| `follow_up` に記載された Issue が Linear 上で Done | 解消済み | follow_up から削除を提案 |

### 4. 完了プロジェクトのクリーンアップ

Linear 上でプロジェクトが Done の場合：

| 対象 | アクション |
|------|-----------|
| `projects/{project-name}.md` | 削除 |
| 関連する `issues/` 内ファイル | 削除 |
| `knowledge/` | **保持**（リポジトリの知見として永続的に有効） |

### 5. completed Issue の自動メンテナンス

issues/ 内のファイルを走査し、Linear 上で Done / Canceled になった Issue を検知したら、
**issue-maintain 相当の処理を自動実行**する。

#### 検知条件

| ローカル status | Linear ステータス | アクション |
|----------------|------------------|-----------|
| `in-progress` | Done | completed に更新 → メンテナンス実行 |
| `in-progress` | Canceled | canceled に更新 → メンテナンス実行 |
| `completed` | Done | 更新履歴に「メンテナンス:」記録がなければ実行 |

**メンテナンス済みの判定**: 更新履歴に `メンテナンス:` で始まるエントリがあればスキップ。

#### メンテナンス処理

検知した各 Issue ファイルに対して、**issue-maintain の処理フロー**（整理対象の判定、圧縮、knowledge 切り出し、completed ファイルの削除）に従って処理する。詳細は issue-maintain SKILL.md を参照。

**承認フロー**: completed Issue メンテナンスの結果は他の変更と合わせてレポートに含め、**一括でユーザー承認を得る**。個別の Issue ごとに承認は求めない。

---

## 処理フロー

```
1. .claude/linear/ 内の全チームを列挙
2. 各チームの projects/ 内のプロジェクト doc を列挙
3. 各プロジェクトについて:
   a. Linear MCP でプロジェクト情報を取得
   b. プロジェクトが Done → クリーンアップ候補としてマーク
   c. プロジェクトが Active → プロジェクト doc を更新
   d. 関連 Issue テーブルを更新
4. issues/ 内の全ファイルを走査
   a. Linear MCP でステータスを確認
   b. Done / Canceled を検知 → status を更新
   c. completed / canceled ファイルに issue-maintain の処理フローを実行
   d. in-progress ファイルの follow_up 解消チェック
5. 結果レポートをユーザーに提示
6. 承認を得てから実行
```

## 出力レポート形式

```md
## Linear Maintain レポート

### プロジェクト doc 更新
| プロジェクト | 前回更新 | ステータス |
|-------------|---------|-----------|
| project-alpha | 2026-03-12 → 2026-03-15 | In Progress |
| project-beta | 2026-03-10 → 2026-03-15 | In Progress |

### 関連 Issue テーブル更新
- project-alpha: 3件更新（TEAM-500: In Progress, TEAM-501: Done → 削除, TEAM-502: 新規追加）

### completed Issue メンテナンス
| Issue | 処理 | knowledge 切り出し | 削除提案 |
|-------|------|-------------------|---------|
| TEAM-404 | 圧縮（358行→45行） | 仕様ドキュメント → knowledge/ | 削除可 |
| TEAM-578 | 重複削除 | 切り出し済み | 削除可 |

### Issue ステータス同期
| Issue | ローカル | Linear | 提案 |
|-------|---------|--------|------|
| TEAM-449 | in-progress | Done | → completed + メンテナンス |

### follow_up 解消
| Issue | follow_up | Linear ステータス | 提案 |
|-------|-----------|------------------|------|
| TEAM-449 | TEAM-500 | Done | follow_up から削除 |

### クリーンアップ
（対象なし）
```

---

## 注意事項

- 全ての変更はレポート提示後、**ユーザーの承認を得てから実行**する
- Linear API のレート制限に注意（大量の Issue がある場合はバッチ処理）
- knowledge/ は**いかなる場合も自動削除しない**
