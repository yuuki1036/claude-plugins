---
name: linear-maintain
description: >
  Linear MCP と同期してローカルの Issue/プロジェクト管理ファイルを最新化する。
  プロジェクト doc（projects/*.md）の更新、関連 Issue テーブルの同期、
  Issue ファイルの linear_status 更新、新規プロジェクト doc の作成を行う。
  1日1回程度の実行を想定。
  使用タイミング: ユーザーが「/linear-maintain」「Linear同期」「ステータス更新」
  「プロジェクト整理」と言った時。
  引数: [プロジェクトスラッグ（省略時は .claude/linear/ 配下の全スラッグ対象）]
allowed-tools: mcp__linear__list_issues, mcp__linear__list_projects, mcp__linear__get_issue, mcp__linear__get_project, mcp__linear__list_issue_statuses, Read, Write, Edit, Glob, Grep, Bash
---

# Linear Maintain

Linear MCP を使ってローカルの管理ファイル群を最新状態に同期する。

## 前提

- Linear MCP ツール（`list_issues`, `list_projects`, `get_issue`, `get_project`）が利用可能であること
- `.claude/linear/{slug}/` ディレクトリ構造が存在すること

## ワークフロー

### Phase 1: スコープ特定

1. 引数でスラッグが指定されていればそのディレクトリのみ対象
2. 指定がなければ `.claude/linear/` 配下の全スラッグディレクトリを対象
3. 各スラッグの `projects/` と `issues/` を列挙

### Phase 2: プロジェクト同期

各プロジェクト doc（`projects/*.md`）について:

1. frontmatter の `project_id` で Linear MCP `get_project` を呼び出し
2. ステータス、description の差分を検出
3. `list_issues` でプロジェクト配下の Issue 一覧を取得
4. 関連 Issue テーブルを更新（[project-doc-template.md](references/project-doc-template.md) 参照）
5. `last_updated` を今日の日付に更新

**新規プロジェクト検出**: `list_projects` で取得したプロジェクトのうち、対応する doc がないものがあれば新規作成を提案。

### Phase 3: Issue ファイル同期

各 Issue ファイル（`issues/*.md`）について:

1. frontmatter の `linear` フィールドで Linear MCP `get_issue` を呼び出し
2. `linear_status` を Linear 上の最新ステータスで更新
3. **不整合検出**: Linear が `Done` なのに Issue ファイルの `status` が `in-progress` → ユーザーに確認を促す

### Phase 4: 同期レポート

変更のサマリーを報告:

```
## Linear 同期レポート（YYYY-MM-DD）

### プロジェクト更新
| プロジェクト | 変更内容 |
|-------------|---------|
| {名前} | Issue テーブル: +2件追加、3件ステータス更新 |

### Issue ステータス更新
| Issue | 旧ステータス | 新ステータス |
|-------|-------------|-------------|
| CFP-XXX | In Progress | In Review |

### 要確認事項
- CFP-YYY: Linear=Done だが Issue ファイルは in-progress（完了処理が必要？）
- 新規プロジェクト「ZZZ」の doc 作成が必要
```

## 注意事項

- Linear MCP の呼び出し回数を最小化するため、`list_issues` はプロジェクト単位でまとめて取得
- `status`（手動管理）と `linear_status`（自動同期）は別フィールド。混同しない
- プロジェクト doc の「備考」セクションは手動管理のため自動更新しない
