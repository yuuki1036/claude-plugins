# design doc 本文テンプレ

新規 design doc 作成時にこのテンプレを Read し、`{...}` プレースホルダを置換して Write する。

## プレースホルダ一覧

| プレースホルダ | 置換値 | 取得方法 |
|---|---|---|
| `{ID}` | `<YYYYMMDD>-<kebab-slug>`（ファイル名から `.md` を除いた値） | Bash `date +%Y%m%d` + slug 生成 |
| `{TITLE}` | doc のタイトル（原文ママ、日本語可） | 引数 `<title>` |
| `{STATUS}` | `draft` / `approved` / `superseded` | 既定 `draft` |
| `{PHASE}` | `target` / `current` / `superseded` | 既定 `target`（未実装の設計） |
| `{TODAY}` | 本日（`YYYY-MM-DD`） | Bash `date +%Y-%m-%d` |
| `{SUPERSEDES}` | 置き換える doc の id 配列 | 通常 `[]`、supersede 時 `["<old-id>"]` |
| `{SUPERSEDED_BY}` | この doc を置き換えた doc の id | 通常 `null` |
| `{ISSUE}` | 関連 Issue の相対パス / ID | Phase 1 で検出（無ければ `null`） |
| `{SPEC}` | bdd-spec の spec.md 相対パス | Phase 1 で検出（無ければ `null`） |

---

## テンプレ本体（ここから下を書き出す）

```markdown
---
id: {ID}
title: {TITLE}
status: {STATUS}
phase: {PHASE}
last-validated: {TODAY}
supersedes: {SUPERSEDES}
superseded-by: {SUPERSEDED_BY}
issue: {ISSUE}
spec: {SPEC}
adrs: []
tags: []
---

# {TITLE}

## TL;DR

<!-- 3 行以内。この設計が「何を・どう解くか」を初見の読者に伝える -->

## 背景 / 課題

<!-- なぜこの設計が必要になったか。現状の問題・制約・きっかけ -->

## ゴール / 非ゴール

- **ゴール**: <!-- この設計で達成すること -->
- **非ゴール**: <!-- 意図的にスコープ外とすること。やらない理由も 1 行 -->

## 確定した前提

<!-- grill Phase で自己解決した事項（コード・既存 ADR・spec.md から決着済みのもの）と
     ユーザーが確定した要求・制約。出典（ファイルパス / ADR id）を添える -->

## 採用案

<!-- アーキテクチャ・データフロー・変更対象ファイル一覧・移行手順。
     図が必要なら mermaid / ASCII で。「なぜこの案か」は代替案セクションの比較表に委ねる -->

## 検討した代替案

<!-- 2〜3 案のトレードオフ比較表 + 各案を採用しなかった理由 1 行ずつ。
     feature-dev からの export 時は architect 比較出力をここに収める -->

| 観点 | 案 A（採用） | 案 B | 案 C |
|------|------------|------|------|
|      |            |      |      |

## 設計判断ログ

<!-- この doc 内で下した個々の判断。各行に必ずマーカーを付ける:
     [→ADR候補] = プロジェクト全体に効く決定。adr-keeper への切り出し対象
     [local]    = この設計の中でだけ意味を持つ判断 -->

- [local] <!-- 例: リトライ上限はキューの可視性タイムアウトに合わせて 3 回 -->
- [→ADR候補] <!-- 例: 非同期処理は Pub/Sub ではなくジョブテーブル方式に統一 -->

## 未解決事項 (open)

<!-- 各 open には必ず: (a)(b) の選択肢 + pros/cons、現時点の方向性（有力案 + 理由）、
     確定タイミング（いつ・どこで確定するか）を添える。issue-design の open ルールと同じ -->

## 実装ブリッジ (Implementation Bridge)

<!--
必須・空欄禁止。design doc の死に文書化（書いたが実装に接続されず腐る）を防ぐための欄。
書けない場合は「書けない理由 + 確定タイミング」を残す。

1. 実装着手の単位:
   - Issue 分解案（タイトル列挙）、または
   - feature-dev 起動引数: `/feature-dev <要約> spec=<spec パス>` （コピペ可能な形式で）
2. 検証方法: 実装とこの doc の一致をどう確認するか（テスト / smoke / レビュー観点）
3. 実装完了時の doc 更新手順:
   - frontmatter の `phase: target` → `current` に更新、`last-validated` を更新
   - 実装と乖離した箇所があれば追記、方式ごと変わったなら supersede
-->

## 関連

<!-- Issue / spec.md / ADR / 他 design doc へのリンク。wikilink [[...]] も可 -->
- 関連 Issue:
- 関連 spec:
- 関連 ADR:
- 関連 design doc:
```
