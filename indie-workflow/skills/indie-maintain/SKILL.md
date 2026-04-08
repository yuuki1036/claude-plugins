---
name: indie-maintain
description: >
  全プロジェクトの棚卸し。放置 Issue の対処、技術的負債サマリー、
  frozen Issue の再評価、completed ファイルのクリーンアップを行う。
  トリガー: 「プロジェクト整理」「棚卸し」「メンテナンス」「/indie-maintain」
effort: medium
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
---

# Indie メンテナンス

## 概要

ローカルの `.claude/indie/` 内のプロジェクト管理ファイル群を棚卸しし、放置 Issue の検出・技術的負債の可視化・frozen Issue の再評価・completed ファイルのクリーンアップを行う。

## コマンド

| コマンド | 動作 |
|----------|------|
| `/indie-maintain` | 全プロジェクトを棚卸し |
| `/indie-maintain {slug}` | 指定プロジェクトのみ棚卸し |

---

## Phase 0: スキャンモード選択

**AskUserQuestion** でスキャンモードを選択する:

- question: "メンテナンスのスキャンモードを選択してください。"
- header: "スキャンモード"
- options:
  1. label: "通常" / description: "プロジェクトサマリー + 放置検知 + completed メンテナンス"
  2. label: "フルスキャン" / description: "通常 + 全 Issue（in-progress 含む）の品質整理"

- **通常**: 既存の処理フロー（1〜8）をそのまま実行
- **フルスキャン**: 処理 1〜4 を実行後、5 を拡張して全 Issue に indie-issue-maintain の全処理フローを適用し、6〜8 を実行

---

## 処理内容

### 1. プロジェクトサマリー生成

`.claude/indie/` 内の全プロジェクトについて、`issues/` 内のファイルを走査し、ステータス別の Issue 件数を集計する。

- 各 Issue ファイルの frontmatter `status` を読み取り（`backlog` / `in-progress` / `frozen` / `completed`）
- frontmatter `type: debt` の Issue は debt としてもカウント
- 集計結果を各プロジェクトの `project.md` に反映

### 2. 放置 Issue 棚卸し

`status: in-progress` の Issue のうち、`last_active` が **7日以上前** のものを検出する。

- 検出した Issue をユーザーに提示し、以下の対処を確認:
  - **継続**: `last_active` を今日に更新して作業を続行
  - **凍結**: `status: frozen` に変更、`frozen_date` を記録
  - **破棄**: `status: canceled` に変更

### 3. frozen Issue 再評価

`status: frozen` の Issue のうち、`frozen_date` が **30日以上前** のものを検出する。

- 検出した Issue をユーザーに提示し、以下の対処を確認:
  - **再開**: `status: in-progress` に変更、`last_active` を今日に更新
  - **破棄**: `status: canceled` に変更

### 4. debt サマリー

`type: debt` の Issue 一覧を表示する。

- 作成日（`created`）からの経過日数を算出
- 経過日数の長い順にソート

### 5. Issue メンテナンス

#### 5a. completed Issue メンテナンス（通常・フルスキャン共通）

`issues/` 内の `status: completed` ファイルを走査し、**indie-issue-maintain の処理フロー**に従って品質整理を行う。

- Issue ファイルの圧縮（冗長な記録の整理）
- knowledge への切り出し（再利用可能な知見の抽出）
- 整理済みファイルの削除提案

**メンテナンス済みの判定**: 更新履歴に `メンテナンス:` で始まるエントリがあればスキップ。

#### 5b. 全 Issue 品質整理（フルスキャンのみ）

`status: in-progress` の全 Issue ファイルに対して、**indie-issue-maintain の全処理フロー**を適用する。

##### 対象
- `status: in-progress` の全 Issue（5a で処理済みのものは除く）

##### 処理内容（indie-issue-maintain SKILL.md の全ステップを適用）
1. last_active を今日の日付に更新
2. スコープ超過チェック
3. テンプレート準拠チェック
4. 各セクション走査・整理対象の特定（削除/圧縮/統合）
5. 更新履歴のセッション単位統合
6. knowledge/ 切り出し候補の特定

##### knowledge 重複排除
複数 Issue から同一トピックの knowledge が候補に上がった場合、マージして1つの knowledge ファイルにする。全 Issue の候補を収集してから index.md と照合する。

**承認フロー**: Issue メンテナンスの結果は他の変更と合わせてレポートに含め、**一括でユーザー承認を得る**。個別の Issue ごとに承認は求めない。

### 6. Follow-up 棚卸し

各プロジェクトの `.claude/indie/{slug}/follow-ups/*.md` を走査する:

- `status: open` のものを列挙する
- `created` から14日以上経過しているものを警告付きでハイライトする
- 各 follow-up について対処を確認（AskUserQuestion）:
  - **昇格**: `/indie-follow-up promote` を実行
  - **backlog 移動**: `status` を `backlog` に更新し、`backlog.md` に追記
  - **削除**: `status` を `dismissed` に更新
- 結果をレポートに含める

### 7. backlog.md 整理

各プロジェクトの `backlog.md` を確認し、Issue ファイルに昇格すべき項目がないかユーザーに提示する。

- 優先度や緊急性が高そうな項目をハイライト
- 昇格する場合は Issue ファイルを作成し、backlog.md から削除

### 8. project.md 更新

ステータスサマリー（件数テーブル）と関連 Issue テーブルを最新化する。

> **プロジェクト doc テンプレート**: `${CLAUDE_SKILL_DIR}/references/project-doc-template.md` を Read で参照すること。

---

## 処理フロー

```
1. .claude/indie/ 内の全プロジェクトを列挙（slug 指定時はそれだけ）
2. スキャンモードを選択（通常 / フルスキャン）
3. 各プロジェクトについて:
   a. issues/ 内の全ファイルを走査しステータス集計
   b. 放置 Issue（in-progress + 7日以上未更新）を検出
   c. frozen Issue（30日以上凍結）を検出
   d. debt Issue を収集
   e. completed Issue にメンテナンス処理を実行
   f. [フルスキャン] in-progress Issue に indie-issue-maintain の全処理フローを実行
   g. follow-ups/ 内の open ファイルを走査し、14日以上経過のものを警告付きでマーク
   h. backlog.md を確認
   i. project.md のステータスサマリー・関連 Issue テーブルを更新
4. [フルスキャン] knowledge 切り出し候補の重複排除
5. 結果レポートをユーザーに提示
6. 承認を得てから実行
```

## 出力レポート形式

```md
## Indie Maintain レポート

### プロジェクトサマリー
| プロジェクト | backlog | in-progress | frozen | debt | completed |
|-------------|---------|-------------|--------|------|-----------|

### 放置 Issue (7日以上未更新)
| Issue | 最終更新 | 経過日数 |
|-------|---------|---------|

### 技術的負債
| Issue | 作成日 | 経過日数 |
|-------|--------|---------|

### frozen Issue (30日以上)
| Issue | 凍結日 | 経過日数 |
|-------|--------|---------|

### completed Issue メンテナンス
| Issue | 処理 | knowledge 切り出し | 削除提案 |
|-------|------|-------------------|---------|

### Issue 品質整理（フルスキャンのみ）
| Issue | スコープ | テンプレート | 圧縮 | knowledge | 警告 |
|-------|---------|------------|------|----------|------|
| MYAPP-5 | OK | 不足: 調査結果 | 3箇所 | - | - |
| MYAPP-7 | 超過 ⚠️ | OK | 1箇所 | キャッシュ戦略 | スコープ超過 |

### Follow-up 棚卸し
| ファイル | タイトル | type | priority | source | 作成日 | 経過日数 |
|--------|---------|------|----------|--------|--------|---------|
| 20260320-fix-null.md | null チェック漏れ | bug | high | MYAPP-3 | 2026-03-20 | 14日 ⚠️ |

### backlog.md 確認
| プロジェクト | 昇格候補 |
|-------------|---------|

### project.md 更新
| プロジェクト | 更新内容 |
|-------------|---------|
```

---

## 注意事項

- 全ての変更はレポート提示後、**ユーザーの承認を得てから実行**する
- knowledge/ は**いかなる場合も自動削除しない**
- `last_active` の更新は Issue ファイルの frontmatter を直接編集する
