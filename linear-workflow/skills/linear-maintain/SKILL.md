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

## 実行ポリシー（起動＝実行確定）

このスキルは**起動した時点で実行確定**とみなす。実行可否やスキャンモードを起動時に問い直さない（AskUserQuestion で止まらない／ストレスフリー設計）。常に**フルスキャン**（処理 1〜5 + 6a + 6b で全 Issue に issue-maintain の全処理フローを適用）を実行し、結果は最終レポートにまとめて報告する。

## Phase 0: Linear MCP 利用可能性チェック

1. 軽量な Linear MCP 呼び出し（`mcp__linear__list_projects` など）を試みる
2. ツールが見つからない・接続エラーの場合: **Linear 同期がこのスキルの主機能であり MCP 抜きでは意味がないため、フォールバックせず中断する**。`「Linear MCP が利用できないため中断しました。MCP 接続を確認してから再実行してください」`と一言出して終了する（AskUserQuestion で続行可否を問い直さない＝起動時に止めない方針と整合）
3. 正常に応答が返った場合: そのまま通常フローに進む

---

## 処理内容

### 1. プロジェクト doc の更新

`linear/{slug}/projects/` 内の各プロジェクト doc を Linear MCP `get_project` で再取得・更新する。

- `last_updated` を今日の日付に更新
- 概要・ステータスを最新化
- **関連 Issue テーブルの更新**（後述）

> **プロジェクト doc テンプレート**: `${CLAUDE_SKILL_DIR}/references/project-doc-template.md` を Read で参照すること。

### 2. 関連 Issue テーブルの更新

Linear MCP `list_issues` でプロジェクト内の Issue 一覧を取得し、各プロジェクト doc の「関連 Issue」テーブルを更新する。

- 各 Issue の担当者・ステータスを最新化
- PR がある場合はリンクを追加
- Done の Issue はテーブルから削除（対応する issues/ ファイルがある場合はそちらで追跡）

### 3. Issue ステータス同期

`issues/` 内の `in-progress` ファイルを走査し、Linear MCP `get_issue` と `list_issue_statuses` を用いて、各 Issue の Linear 上ステータスとの整合性を確認する：

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

### 5. Follow-up 棚卸し

各プロジェクトの `.claude/linear/{slug}/follow-ups/*.md` を走査する:

- `status: open` のものを列挙する
- `created` から14日以上経過しているものを警告付きでハイライトする
- 結果をレポートに含める（個別の対処確認はせず、実行後レポートで一括報告する）

### 6. Issue メンテナンス

#### 6a. completed Issue の自動メンテナンス

issues/ 内のファイルを走査し、Linear MCP `get_issue` で取得したステータスを確認し、Done / Canceled になった Issue を検知したら、
**issue-maintain 相当の処理を自動実行**する。

##### 検知条件

| ローカル status | Linear ステータス | アクション |
|----------------|------------------|-----------|
| `in-progress` | Done | completed に更新 → メンテナンス実行 |
| `in-progress` | Canceled | canceled に更新 → メンテナンス実行 |
| `completed` | Done | 更新履歴に「メンテナンス:」記録がなければ実行 |

**メンテナンス済みの判定**: 更新履歴に `メンテナンス:` で始まるエントリがあればスキップ。

#### 6b. 全 Issue 品質整理

`status: in-progress` の全 Issue ファイルに対して、**issue-maintain の全処理フロー**を適用する。

##### 対象
- `status: in-progress` の全 Issue（6a で処理済みのものは除く）

##### 処理内容（issue-maintain SKILL.md の全ステップを適用）
1. テンプレート準拠チェック
2. 各セクション走査・整理対象の特定（削除/圧縮/統合）
3. 更新履歴のセッション単位統合
4. knowledge/ 切り出し候補の特定

##### knowledge 重複排除
複数 Issue から同一トピックの knowledge が候補に上がった場合、マージして1つの knowledge ファイルにする。全 Issue の候補を収集してから index.md と照合する。

#### メンテナンス処理（6a・6b 共通）

検知した各 Issue ファイルに対して、**issue-maintain の処理フロー**（整理対象の判定、圧縮、knowledge 切り出し、completed ファイルの削除）に従って処理する。詳細は issue-maintain SKILL.md を参照。

**実行フロー**: 起動＝実行確定のため、Issue メンテナンスは承認待ちせず実行し切る。実施内容（status 更新・圧縮・knowledge 切り出し・削除）は最終レポートにまとめて報告する。Issue ファイルは git 管理下のため、不要な変更は git で復元できる。

---

## 処理フロー

```
1. .claude/linear/ 内の全チームを列挙（常時フルスキャン）
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
   e. in-progress ファイルに issue-maintain の全処理フローを実行
5. follow-ups/ 内の全ファイルを走査
   a. status: open の follow-up を列挙
   b. 14日以上経過のものを警告付きでマーク
6. knowledge 切り出し候補の重複排除
7. すべて実行し切り、結果レポートをユーザーに報告
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

### Issue 品質整理
| Issue | テンプレート | 圧縮 | knowledge | 警告 |
|-------|------------|------|----------|------|
| TEAM-501 | 不足: 調査結果 | 3箇所 | - | - |
| TEAM-502 | OK | 1箇所 | API パターン | - |

### Issue ステータス同期
| Issue | ローカル | Linear | 提案 |
|-------|---------|--------|------|
| TEAM-449 | in-progress | Done | → completed + メンテナンス |

### follow_up 解消
| Issue | follow_up | Linear ステータス | 提案 |
|-------|-----------|------------------|------|
| TEAM-449 | TEAM-500 | Done | follow_up から削除 |

### Follow-up 棚卸し
| ファイル | タイトル | type | priority | source | 作成日 | 経過日数 |
|--------|---------|------|----------|--------|--------|---------|
| 20260320-fix-null.md | null チェック漏れ | bug | high | TEAM-123 | 2026-03-20 | 14日 ⚠️ |

### クリーンアップ
（対象なし）
```

---

## 注意事項

- 起動＝実行確定。承認待ちで止まらず実行し切り、**実行後にレポートで報告**する（AskUserQuestion で問い直さない）
- Issue ファイルは git 管理下のため、不要な変更は git で復元できる
- Linear API のレート制限に注意（大量の Issue がある場合はバッチ処理）
- knowledge/ は**いかなる場合も自動削除しない**
