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
status: backlog | in-progress | frozen | completed | canceled
id: {ISSUE-ID}                       # BACKEND=local。linear では代わりに linear: {ISSUE-ID}
type: bugfix | feature | investigation | debt
created: YYYY-MM-DD
last_active: YYYY-MM-DD
scope_size: small | medium | large   # 必須（全 type）
---
```

- `status` の値は `maintain` の正式定義（`backlog` / `in-progress` / `frozen` / `completed` / `canceled`）に揃える。`debt` は type であって status ではない（混同しない）
- `scope_size` は全 type で必須（テンプレ既定値: bugfix / debt は `small`）。未設定の既存 Issue はスコープ超過チェック（§6）がスキップされるため、整理時に付与する

#### オプションフィールド
```yaml
project: {プロジェクト名}
linear_status: {Linear上のステータス}   # BACKEND=linear のみ
frozen_date: YYYY-MM-DD   # status: frozen のとき必須。frozen からの経過日数判定（maintain の frozen 再評価）に使用
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

**debt:**
- 概要、影響範囲、放置リスク、対応方針、進捗、変更ファイル、更新履歴

### 5. last_active の更新チェック

- 整理実行時にフロントマターの `last_active` が今日の日付に更新されているか確認
- `last_active` フィールドが存在しない場合は追加する
- 日付形式は `YYYY-MM-DD`

### 6. スコープ超過チェック

- フロントマターに `scope_size` が設定されている場合、進捗セクション内のタスク数（`- [ ]` と `- [x]` の合計）と比較
- 閾値:
  - `small`: 3個以下
  - `medium`: 7個以下
  - `large`: 15個以下
- 超過時は警告を出力し、Issue 分割を提案
- `scope_size` が未設定の場合はスキップ

### 7. knowledge 切り出し判断基準

切り出すべき知見:
- 複数 Issue で再利用できるパターンや設計判断
- コードベースの構造的な知識（API パターン、データフローなど）
- トラブルシューティング手法（特定の問題カテゴリへの対処法）

切り出さない:
- Issue 固有の修正内容
- 一時的な回避策
- まだ検証されていない仮説

### 7.1 破壊的変更パターンの自動検出（最重要）

Issue 本文・進捗・更新履歴・会話ログから以下キーワードを検出した場合、knowledge 切り出し候補として **必ず** 切り出しまで実行する（起動＝実行確定のため止めて確認しない）。
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

**報告フォーマット（レポートに🔴マーカー付きで先頭表示）:**

```
🔴 破壊的変更パターンを検出しました（{Issue 内の該当箇所}）。
   knowledge/{topic-slug}.md に切り出しました。
   付与 tags: [library-compat, breaking-change, migration]
```

検出は機械的に行う。起動＝実行確定のため切り出しまで実行し、内容と格納先はレポートに列挙する。

### 8. knowledge の status フロントマター仕様

knowledge ファイルのフロントマターには `status` と `tags` を必須で記載する：

| フィールド | 必須 | 意味 |
|-----------|------|------|
| `kind` | 任意 | `source`（個別知見、省略時のデフォルト）または `concept`（横断統合の概念ページ） |
| `source` | 必須 | 元の Issue ID や調査元 |
| `status` | 必須 | `verified`（実装済み）または `planned`（設計案） |
| `verified` | 条件付き | status: verified の場合のみ。検証日 `YYYY-MM-DD` |
| `updated` | 必須 | 最終更新日 `YYYY-MM-DD`。新規切り出し時は当日、編集時は必ず更新する |
| `tags` | 必須 | 検索用キーワードのリスト（3〜7個目安） |
| `last-validated` | 任意 | 内容検証日 `YYYY-MM-DD`。記入時は `/knowledge-lint` stale 判定の第一基準（未記入時は `updated` → `verified` の順で fallback）。doc-freshness プラグインと共通スキーマ |
| `phase` | 任意 | `current` / `target` / `superseded`。未記入時は `status` から推定（`verified`→current / `planned`→target） |
| `subkind` | 任意 | `concept` のサブ分類。`glossary` を付けると用語 SSoT ページとして glossary 重複検査（knowledge-lint 項目 9）の対象になる |

**transitional period**: `last-validated` / `phase` / `subkind` は任意。未記入でも error にならず、`/knowledge-lint` では warn / info に留まる。既存の `verified` / `updated` / `status` はそのまま維持する。

**tags の付与ルール:**
- 技術用語・ライブラリ名・パターン名を優先する（例: `react`, `pagination`, `caching`）
- ドメイン用語も含める（例: `auth`, `billing`, `search`）
- 抽象的すぎるタグは避ける（`code`, `fix` などは不可）
- 既存 knowledge の tags と語彙を揃える（新規タグを追加する前に既存タグを確認）

**フォーマット例:**

```yaml
---
source: MYAPP-42
status: verified
verified: 2026-03-20
updated: 2026-03-20
last-validated: 2026-03-20   # 任意。鮮度判定の第一基準
phase: current               # 任意。未記入なら status から推定
tags: [react, memo, rendering, performance]
---
```

```yaml
---
source: MYAPP-15
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

### 8.1 概念ページ（concept）と wikilink

knowledge は 2 種類ある。

| kind | 配置 | 役割 |
|------|------|------|
| `source`（省略時デフォルト） | `knowledge/{slug}.md` | 個別知見。1 つの Issue / 調査から切り出した単一トピック |
| `concept` | `knowledge/concepts/{slug}.md` | 概念ページ。複数 source を横断統合した知見（共通パターン・矛盾・全体構造） |

**concept ページの必須セクション:**

- 概要 / 横断的知見 / 未解決の問い / 関連ソース
- 「横断的知見」が concept の核。単一 source の要約に留まるなら concept にせず source のままにする
- 「関連ソース」は統合元の source を `[[name]] — 観点` の形で列挙する

**concept ページの frontmatter:**

- source と同じ `kind` / `source` / `status` / `verified`（verified 時のみ）/ `updated` / `tags`。`kind: concept` を足すのが source との差分
- `updated` は source と同様に必須（波及で既存 concept を編集したら当日日付に更新する）
- フォーマット例:

```yaml
---
kind: concept
source: MYAPP-42, MYAPP-58
status: verified
verified: 2026-03-20
updated: 2026-03-20
tags: [data-fetching, cache, pagination]
---
```

**wikilink 記法:**

- knowledge 同士は `[[name]]`（拡張子なしの basename）でリンクする
- 解決対象は `knowledge/` 配下（`concepts/` を含む）の `.md` の basename
- 例: `[[api-patterns]]` → `knowledge/api-patterns.md`、`[[data-fetching]]` → `knowledge/concepts/data-fetching.md`
- リンク切れ・孤立・表記ゆれ・重複概念は `/knowledge-lint` で検出する

**concept の作り方（波及）:**

source を切り出した後、同じテーマの source が 2 件以上あれば concept への統合を検討する。既存 concept があれば「関連ソース」に `[[新 source]]` を追加し「横断的知見」を更新する。詳細は issue-maintain スキルの「概念ページへの波及」節を参照。

### 9. knowledge 切り出し時の照合ルール

切り出しを行う前に、以下の照合を必ず実施する：

1. **コードベースとの照合** — Grep/Read で実装コードを確認し、記載内容が現在のコードベースと一致しているか検証
2. **関連 Issue との照合** — 他の Issue で同じトピックが扱われていないか確認し、矛盾や重複がないか検証
3. **status の判定** — 実装済みなら `verified`、設計案・移行計画なら `planned` を付与
4. **正確性に疑問がある場合** — 切り出しを保留し、ユーザーに確認を求める

### 10. レビューガード（完了マーク前のレビュー実施確認）

`/issue-maintain` で Issue を `completed` に遷移させる前、または完了サブタスクが多い場合、コードレビューが実施されたかを確認する。feature-dev 経由を通らないケースでのレビュー素通りを防ぐ。

**発火条件:**

1. status が `in-progress` → `completed` に遷移する **または** 完了サブタスク `[x]` の合計が 3 件以上
2. Issue 本文（特に更新履歴・進捗）に以下のキーワードが含まれていない:
   - `self-review` / `セルフレビュー` / `/self-review`
   - `code-review` / `/review` / `コードレビュー実施`
   - `code-reviewer` agent / `reviewer agent`
3. type が `investigation` の場合は発火しない

**選択肢（AskUserQuestion）:**

| 選択肢 | 動作 |
|--------|------|
| `/self-review` を起動 | 本スキルを中断し、ユーザーに `/self-review` 起動を促す |
| レビュー済み | 更新履歴に `\| YYYY-MM-DD \| レビュー実施: {説明} \|` を追記して継続 |
| スキップ | レビューせずに完了マーク（推奨されない旨を表示） |

**検出キーワード一覧:**

| カテゴリ | キーワード |
|---------|----------|
| セルフレビュー | `self-review`, `セルフレビュー`, `/self-review` |
| PR レビュー | `code-review`, `/review`, `コードレビュー実施` |
| Agent 起動 | `code-reviewer`, `reviewer agent` |

上記いずれかのキーワードが Issue 本文（特に更新履歴・進捗）に含まれていればレビュー実施済みとみなしガードをスキップする。検出は機械的に行い、最終判断はユーザーに委ねる。

### 11. スコープ外差分検出（follow-up 自動提示）

Issue ファイルの「スコープ外」「後続 Issue 候補」「やらないこと」セクションの**前回コミット以降の追加行**を検出し、`/follow-up new` 候補として提示する。

**検出手順:**

1. `git log -1 --format=%H -- {issue-file-path}` で直近コミット hash を取得
2. `git diff {hash}..HEAD -- {issue-file-path}` で差分取得
3. 「スコープ外」「後続 Issue 候補」「やらないこと」見出しを含むセクション内の追加箇条書き行（`+- `）を抽出

**選択肢:**

| 選択肢 | 動作 |
|--------|------|
| 一括記録 | 全件を follow-up ファイルとして記録 |
| 個別選択 | 1 件ずつ記録するか確認 |
| スキップ | follow-up 化せず Issue ファイルにのみ残す |

**注意事項:**

- 既存の follow-up 自動検知（会話中シグナル検出）とは独立した別軸
- 検出対象セクションが Issue ファイルに無い場合はスキップ
- 未コミットの新規 Issue ファイルの場合もスキップ
