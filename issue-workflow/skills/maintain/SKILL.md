---
name: maintain
description: >
  全プロジェクトの棚卸し。放置 Issue の対処、技術的負債サマリー、
  frozen Issue の再評価、completed ファイルのクリーンアップを行う。
  トリガー: 「プロジェクト整理」「棚卸し」「メンテナンス」「/maintain」
effort: medium
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
---

# メンテナンス

## 概要

`{DATA_DIR}/` 内のプロジェクト管理ファイル群を棚卸しし、放置 Issue の検出・技術的負債の可視化・frozen Issue の再評価・completed ファイルのクリーンアップを行う。

## Phase 0: backend 検出（全スキル共通）

1. Glob で `.claude/indie/*/` と `.claude/linear/*/` を確認する。「dir が存在し、かつプロジェクト slug サブディレクトリを 1 つ以上持つ」場合のみ有効な backend とみなす（空 dir・残骸は無効）
2. `.claude/indie` のみ有効 → `BACKEND=local` / `DATA_DIR=.claude/indie`。`.claude/linear` のみ有効 → `BACKEND=linear` / `DATA_DIR=.claude/linear`。無効な残骸 dir がもう一方にある場合は警告を一言添えて継続する
3. **両方有効** → エラーとして停止する。両 dir の slug 一覧・issues 件数・最終更新日を並べて提示し、どちらを正とするか決めて他方を退避（rename）または削除する片寄せを案内する
4. **どちらも無効** → `/issue-workflow:init` の実行を案内して終了する

以後の `{DATA_DIR}` は検出したデータディレクトリ、`BACKEND` は判定結果を指す。

## コマンド

| コマンド | 動作 |
|----------|------|
| `/maintain` | 全プロジェクトを棚卸し |
| `/maintain {slug}` | 指定プロジェクトのみ棚卸し |

---

## 実行ポリシー（起動＝実行確定）

このスキルは**起動した時点で実行確定**とみなす。実行可否やスキャンモードを起動時に問い直さない（AskUserQuestion で止まらない／ストレスフリー設計）。スキャン範囲は常に全対象（処理 1〜8。slug 指定時はそのプロジェクトのみ）とし、**走査深度のみ**実行時 effort = `${CLAUDE_EFFORT}` で調整する（下表）。

### effort 適応（走査深度）

| effort | 走査深度 |
|--------|---------|
| low / medium | 検出・集計系（処理 1〜4・6・8）のみ実施。処理 5a/5b の品質整理（圧縮・knowledge 切り出し）と処理 7 の backlog 昇格候補の目利きは省略し、対象件数だけレポートに残す（速度優先） |
| high | 全処理（1〜8。5a/5b で全 Issue に issue-maintain の全処理フローを適用）を実施 |
| xhigh / max | 全処理に加え、knowledge 切り出し候補の重複排除を全プロジェクト横断で網羅し、5b の整理対象走査（削除/圧縮/統合）を全セクション精読で行う |

effort によらず「止まらず実行し切り、実行後レポートで報告する」方針は不変。省略した処理はレポートに `省略（effort: {値}）` と明記する。

判断が要る検出（放置 Issue・frozen Issue・follow-up の対処）は、**AskUserQuestion で止めずに最終レポートへ列挙**し、ユーザーがチャットで対処を指示できるようにする。ファイル更新（status 更新・圧縮・knowledge 切り出し・削除）は承認待ちせず実行し切り、結果をレポートで報告する。Issue ファイルは git 管理下のため、不要な変更は git で復元できる。

---

## 処理内容

### 1. プロジェクトサマリー生成

`{DATA_DIR}/` 内の全プロジェクトについて、Glob で `issues/*.md` を列挙、各ファイルを Read し、ステータス別・タイプ別の Issue 件数を集計して project.md を Edit で更新する。

- 各 Issue ファイルの frontmatter `status` を読み取り、ステータスサマリー（`backlog` / `in-progress` / `frozen` / `completed` / `canceled` の 5 値）に集計する
- frontmatter `type`（`feature` / `bugfix` / `investigation` / `debt`）はタイプ別サマリーに別集計する。`debt` は type であって status ではないため、ステータスサマリーには混ぜない
- 集計結果を各プロジェクトの `project.md` に反映

### 2. 放置 Issue 棚卸し

`status: in-progress` の Issue のうち、`last_active` が **7日以上前** のものを検出する。

- 検出した Issue を**最終レポートに列挙**する（経過日数つき）。継続 / 凍結（`status: frozen` + `frozen_date`）/ 破棄（`status: canceled`）の判断はユーザーがチャットで指示する。AskUserQuestion で止めない
- 破棄指示を受けたら「破棄時の却下記録」（処理 3 直後の共通ルール）を適用する

### 3. frozen Issue 再評価

`status: frozen` の Issue のうち、`frozen_date` が **30日以上前** のものを検出する。

- 検出した Issue を**最終レポートに列挙**する（凍結日数つき）。再開（`status: in-progress` + `last_active` 更新）/ 破棄（`status: canceled`）の判断はユーザーがチャットで指示する。AskUserQuestion で止めない

#### 破棄時の却下記録（処理 2・3・6・7 共通）

破棄（`status: canceled` / follow-up の `dismissed` / backlog 項目の破棄）を指示されたとき、それが「二度と取り組まない」性質の提案・課題なら、却下理由を `kind: rejected` の knowledge に記録する（書式・index.md 追記の正本: `${CLAUDE_PLUGIN_ROOT}/skills/discover/references/rejected-record.md`）。discover の再提案抑止がこの記録を照合する。

- ユーザーの破棄指示に理由が含まれていればそれを使い、無ければ「理由も残しますか（discover の再提案抑止に使われます）」と一言だけチャットで確認する
- 単なる中断・優先度低下・時期尚早は却下ではないので記録しない（canceled にするだけでよい）

### 4. debt サマリー

`type: debt` の Issue 一覧を表示する。

- 作成日（`created`）からの経過日数を算出
- 経過日数の長い順にソート

### 5. Issue メンテナンス

#### 5a. completed Issue メンテナンス

`issues/` 内の `status: completed` ファイルを走査し、**issue-maintain の処理フロー**に従って品質整理を行う。

- Issue ファイルの圧縮（Edit で冗長な記録を整理）
- knowledge への切り出し（Write で再利用可能な知見を新規ファイルに抽出）
- 整理済みファイルの削除提案（Bash `rm` で削除）

**メンテナンス済みの判定**: 更新履歴に `メンテナンス:` で始まるエントリがあれば（Grep で検出）スキップ。

#### 5b. 全 Issue 品質整理

`status: in-progress` の全 Issue ファイルに対して、**issue-maintain の全処理フロー**を適用する。

##### 対象
- `status: in-progress` の全 Issue（5a で処理済みのものは除く）

##### 処理内容（issue-maintain SKILL.md の全ステップを適用）
1. last_active を今日の日付に更新
2. スコープ超過チェック
3. テンプレート準拠チェック
4. 各セクション走査・整理対象の特定（削除/圧縮/統合）
5. 更新履歴のセッション単位統合
6. knowledge/ 切り出し候補の特定

##### knowledge 重複排除
複数 Issue から同一トピックの knowledge が候補に上がった場合、マージして1つの knowledge ファイルにする。全 Issue の候補を収集してから index.md と照合する。

**実行フロー**: 起動＝実行確定のため、Issue メンテナンスは承認待ちせず実行し切る。実施内容は最終レポートにまとめて報告する。

### 6. Follow-up 棚卸し

各プロジェクトの `{DATA_DIR}/{slug}/follow-ups/*.md` を走査する:

- `status: open` のものを列挙する
- `created` から14日以上経過しているものを警告付きでハイライトする
- 検出した follow-up を**最終レポートに列挙**する。対処（昇格 `/follow-up promote` / backlog 移動 / 削除 `dismissed`）はユーザーがチャットで指示する。AskUserQuestion で止めない
- `dismissed` 指示が「二度とやらない」判断なら、「破棄時の却下記録」（処理 3 直後の共通ルール）に従い `kind: rejected` に記録する

### 7. backlog.md 整理

各プロジェクトの `backlog.md` を確認し、Issue ファイルに昇格すべき項目がないかユーザーに提示する。

- 優先度や緊急性が高そうな項目をハイライト
- 昇格する場合は Issue ファイルを作成し、backlog.md から削除
- 項目の破棄（削除）指示が「二度とやらない」判断なら「破棄時の却下記録」（処理 3 直後の共通ルール）を適用する。単なる整理・陳腐化による削除は記録不要

### 8. project.md 更新

ステータスサマリー（件数テーブル）と関連 Issue テーブルを最新化する。

> **プロジェクト doc テンプレート**: `${CLAUDE_SKILL_DIR}/references/project-doc-template.md` を Read で参照すること。

---

## 処理フロー

```
1. {DATA_DIR}/ 内の全プロジェクトを列挙（slug 指定時はそれだけ／常時フルスキャン）
2. 各プロジェクトについて:
   a. issues/ 内の全ファイルを走査しステータス集計
   b. 放置 Issue（in-progress + 7日以上未更新）を検出 → レポートに列挙
   c. frozen Issue（30日以上凍結）を検出 → レポートに列挙
   d. debt Issue を収集
   e. completed Issue にメンテナンス処理を実行
   f. in-progress Issue に issue-maintain の全処理フローを実行
   g. follow-ups/ 内の open ファイルを走査し、14日以上経過のものを警告付きでマーク → レポートに列挙
   h. backlog.md を確認
   i. project.md のステータスサマリー・関連 Issue テーブルを更新
3. knowledge 切り出し候補の重複排除
4. すべて実行し切り、結果レポートをユーザーに報告
```

## 出力レポート形式

```md
## Indie Maintain レポート

### プロジェクトサマリー（ステータス別）
| プロジェクト | backlog | in-progress | frozen | completed | canceled |
|-------------|---------|-------------|--------|-----------|----------|

### タイプ別サマリー
| プロジェクト | feature | bugfix | investigation | debt |
|-------------|---------|--------|---------------|------|

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

### Issue 品質整理
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

- 起動＝実行確定。承認待ちで止まらず実行し切り、**実行後にレポートで報告**する（AskUserQuestion で問い直さない）
- 判断が要る検出（放置 / frozen / follow-up の対処）はレポートに列挙し、ユーザーがチャットで指示する
- Issue ファイルは git 管理下のため、不要な変更は git で復元できる
- knowledge/ は**いかなる場合も自動削除しない**
- `last_active` の更新は Issue ファイルの frontmatter を直接編集する
- **writing-polish 連携は対象外**（設計判断）: このスキルの出力は機械的な status 遷移と実行後レポートのみで、Issue 本文のような散文成果物を新規生成しないため推敲を通さない（散文を生成する issue-maintain / issue-create 側は必須連携済み）
