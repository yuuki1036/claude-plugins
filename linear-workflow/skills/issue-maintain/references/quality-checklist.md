# Issue ファイル品質チェックリスト

## チェック項目

### 1. 完了サブタスクの圧縮

**問題パターン:**
```md
## 進捗
- [x] 根本原因の特定（renderHeader 内の9,516個の el-option + IntensityName）
- [x] 対策1: ローディング追加（showPageLoading + tableData = []）
- [x] 対策2: 遅延レンダリング（ideaNamePopoverOpen フラグ）
...
```
上記のように全サブタスク完了済みの場合、本文の詳細セクションを1行サマリーに圧縮する。
進捗チェックリスト自体は残してOK（完了の記録として有用）。

**圧縮対象:** 完了サブタスクの「詳細説明セクション」（手順、調査過程、試行錯誤）
**圧縮しない:** 進捗チェックリスト、最終的な修正内容のサマリー、再利用可能な知見

### 2. 重複記載の除去

よくある重複パターン:
- 「概要」と「計画」で同じ内容を繰り返している
- 「調査結果」と「進捗」の説明が重複
- 更新履歴で既にセクション本文に書かれた内容を再度記述

対処: 情報の正本を1箇所に決め、他は参照 or 削除。

### 3. 不採用アプローチ・解決済み疑問の除去

- 試したが不採用になったアプローチの詳細 → 削除（knowledge に汎用性があれば切り出し）
- 「要確認」「TODO」で既に解決済みのもの → 削除 or 結論に置換
- デバッグ過程の詳細ログ → 削除

### 4. テンプレート準拠チェック

#### フロントマター必須フィールド
```yaml
---
status: in-progress | completed
linear: {ISSUE-ID}
type: bugfix | feature | investigation
created: YYYY-MM-DD
---
```

#### オプションフィールド
```yaml
linear_status: {Linear上のステータス}
project: {プロジェクト名}
pr: #{PR番号}
follow_up:
  - {後続Issue}
```

#### type 別セクション構成

**bugfix:**
- 概要、進捗、変更ファイル、更新履歴

**feature:**
- 概要、計画、進捗、変更ファイル、更新履歴
- 推奨（省略可）: 調査結果、スコープ外、備考

**investigation:**
- 概要、調査結果、根本原因、提案、関連ファイル、更新履歴

### 5. knowledge 切り出し判断基準

切り出すべき知見:
- 複数 Issue で再利用できるパターンや設計判断
- コードベースの構造的な知識（API パターン、データフローなど）
- トラブルシューティング手法（特定の問題カテゴリへの対処法）

切り出さない:
- Issue 固有の修正内容
- 一時的な回避策
- まだ検証されていない仮説

### 5.1 破壊的変更パターンの自動検出（最重要）

Issue 本文・進捗・更新履歴・会話ログから以下キーワードを検出した場合、knowledge 切り出し候補として **必ず** ユーザーに y/n で提示する。
将来再利用価値が高く取りこぼしやすいため、通常の判断基準より優先する。

**検出キーワード（日本語 / 英語）:**

| カテゴリ | キーワード例 |
|---------|-------------|
| 破壊的変更 | 「破壊的変更」「breaking change」「BREAKING CHANGE」 |
| API rename | 「rename された」「renamed to」「名前が変わった」「→ 名称変更」 |
| 非推奨化 | 「deprecated」「非推奨」「廃止された」 |
| バージョン跨ぎ移行 | `v\d+ ?→ ?v\d+`、「v5 → v6」「Prisma 6 → 7」「Next.js 14 → 15」等 |
| 実機検知バグ | 「dead element」「機能していない」「空振り」「lint は通るが」「実機テストで判明」「ランタイムで発覚」 |
| 衝突パターン | 「衝突する」「conflict with」「競合する」「順序バグ」「配列順序」 |
| 仕様変更 | 「adapter 必須」「規約が変わった」「ファイル規約が rename」 |

**tags 候補（検出時に提案）:**

| キーワードカテゴリ | 推奨 tags |
|------------------|----------|
| 破壊的変更 / バージョン跨ぎ | `library-compat`, `breaking-change`, `migration` |
| API rename / 非推奨化 | `library-compat`, `deprecation`, `api-change` |
| 実機検知バグ / 衝突 | `gotcha`, `runtime-only`, `static-check-blind-spot` |
| 仕様変更 | `library-compat`, `convention-change` |

**ユーザー提示フォーマット:**

```
🔴 破壊的変更パターンを検出しました（{Issue 内の該当箇所}）。
   knowledge として切り出しますか？

   提案 tags: [library-compat, breaking-change, migration]
   提案ファイル名: knowledge/{topic-slug}.md

   [y] 切り出す  [n] 切り出さない  [edit] tags を編集
```

検出と提案は機械的に行い、最終判断はユーザーに委ねる。

### 6. knowledge の status フロントマター仕様

knowledge ファイルのフロントマターには `status` と `tags` を必須で記載する：

| フィールド | 必須 | 意味 |
|-----------|------|------|
| `source` | 必須 | 元の Issue ID や調査元 |
| `status` | 必須 | `verified`（実装済み）または `planned`（設計案） |
| `verified` | 条件付き | status: verified の場合のみ。検証日 `YYYY-MM-DD` |
| `updated` | 必須 | 最終更新日 `YYYY-MM-DD`。新規切り出し時は当日、編集時は必ず更新する |
| `tags` | 必須 | 検索用キーワードのリスト（3〜7個目安） |

**tags の付与ルール:**
- 技術用語・ライブラリ名・パターン名を優先する（例: `react`, `pagination`, `caching`）
- ドメイン用語も含める（例: `auth`, `billing`, `search`）
- 抽象的すぎるタグは避ける（`code`, `fix` などは不可）
- 既存 knowledge の tags と語彙を揃える（新規タグを追加する前に既存タグを確認）

**フォーマット例:**

```yaml
---
source: TEAM-42
status: verified
verified: 2026-03-20
updated: 2026-03-20
tags: [react, memo, rendering, performance]
---
```

```yaml
---
source: TEAM-15
status: planned
updated: 2026-04-15
tags: [cache, redis, ttl, session]
---
```

**`updated` 運用ルール:**

- 新規切り出し時: 当日の日付を記載
- 既存 knowledge を編集した場合: **必ず** `updated` を編集日に書き換える（鮮度判定の根拠になるため）
- frontmatter 以外の本文修正のみでも更新する（typo 修正等の極小変更は任意）
- 既存ファイルに `updated` がない場合は、次回編集時に追加する（遡及修正は不要）

### 7. knowledge 切り出し時の照合ルール

切り出しを行う前に、以下の照合を必ず実施する：

1. **コードベースとの照合** — Grep/Read で実装コードを確認し、記載内容が現在のコードベースと一致しているか検証
2. **関連 Issue との照合** — 他の Issue で同じトピックが扱われていないか確認し、矛盾や重複がないか検証
3. **status の判定** — 実装済みなら `verified`、設計案・移行計画なら `planned` を付与
4. **正確性に疑問がある場合** — 切り出しを保留し、ユーザーに確認を求める
