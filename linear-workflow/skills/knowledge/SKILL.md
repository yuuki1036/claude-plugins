---
name: knowledge
description: >
  Linear 連携プロジェクトの蓄積された知見を検索・参照する（一覧 / キーワード検索 / 関連表示。読み取り専用）。
  実装方針の検討時や過去に似た問題を解決した可能性がある時に自動的に使用する。
  リンク切れ・孤立・重複の点検や修復は knowledge-lint に任せる（このスキルは閲覧のみ）。
  トリガー: 「知見」「過去に似た」「前にもやった」「ナレッジを検索」「/knowledge」
effort: low
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
---

# Knowledge

プロジェクトに蓄積された知見（knowledge）を検索・参照するスキル。
ユーザーの明示的な呼び出しだけでなく、実装方針の検討時や問題解決時に Claude が自律的に使用する。

**モード分岐:**
- 引数なし → 現プロジェクトの全 knowledge 一覧
- `search <keyword>` → tags/内容でキーワード検索
- `related` → 現在の Issue に関連する knowledge を表示

> 健全性チェック（broken link / orphan / 表記ゆれ / 重複概念の検出と修正）は別スキル `/knowledge-lint` で実行する。

---

## knowledge の種類（source / concept）

knowledge は 2 種類ある。frontmatter の `kind` で区別する。

| kind | 配置 | 役割 |
|------|------|------|
| `source`（省略時のデフォルト） | `knowledge/*.md` | 個別知見。1 つの Issue / 調査から切り出した単一トピックの知見 |
| `concept` | `knowledge/concepts/*.md` | 概念ページ。複数の source を横断して統合した知見（共通パターン・矛盾・全体構造） |

`kind` が無いファイルは `source` として扱う（後方互換）。概念ページの本質は「複数ソースを繋いで初めて見える構造」を蓄積することにある。

`concept` には任意のサブ分類 `subkind: glossary` を付けられる。用語の SSoT（単一定義ページ）として扱われ、複数 glossary 間で同一用語が重複定義されていないかを `/knowledge-lint`（項目 9）が検出する。

鮮度フィールド `last-validated`（検証日 `YYYY-MM-DD`）と `phase`（`current` / `target` / `superseded`）も任意で付けられる。記入すると `/knowledge-lint`（項目 8）の stale 判定に使われる（未記入なら既存 `updated` / `verified` を fallback に使う。doc-freshness プラグインと共通スキーマ）。

## wikilink 記法

knowledge 同士は `[[name]]` 記法でリンクする（`name` は拡張子なしの basename）。

- 解決対象: `.claude/linear/{slug}/knowledge/` 配下（`concepts/` を含む）の `.md` ファイルの basename
- 例: `[[api-patterns]]` は `knowledge/api-patterns.md` を、`[[data-fetching]]` は `knowledge/concepts/data-fetching.md` を指す
- concept ページの「関連ソース」セクションで、統合元の source を `[[name]] — 観点` の形で列挙する
- リンク切れ・孤立は `/knowledge-lint` が検出する

---

## Phase 0: プロジェクト特定

1. 現在のブランチ名から Issue ID プレフィックスを抽出する
   - `git branch --show-current` を実行
   - `{type}/{SLUG-N}-{desc}` パターンからスラッグ部分を小文字化
2. `.claude/linear/{slug}/knowledge/` の存在を確認する
3. ブランチから特定できない場合:
   - `.claude/linear/*/knowledge/` を Glob で全プロジェクト検索
   - 単一プロジェクトならそのスラッグを使用
   - 複数プロジェクトなら **AskUserQuestion** で選択:
     - question: "どのプロジェクトの knowledge を表示しますか？"
     - options: 各プロジェクト名

---

## モード A: 一覧表示（引数なし）

1. `knowledge/index.md` の存在を確認（Read）
2. **index.md が存在する場合:**
   - テーブル全体を表示する（concept 行と source 行を分けて見せる）
3. **index.md が存在しない場合:**
   - `.claude/linear/{slug}/knowledge/**/*.md` を Glob で列挙（`concepts/` 配下も含む。`index.md` は除外）
   - 各ファイルのフロントマター（kind, tags, status, source）を Read して一覧化
4. **概念ページ（concept）を先に、個別知見（source）を後に**表示する。concept は横断的に俯瞰するエントリポイントになるため上位に置く
5. knowledge が0件の場合:
   - 「このプロジェクトにはまだ knowledge がありません。`/issue-maintain` で知見を切り出せます。」と表示

---

## モード B: キーワード検索（search <keyword>）

1. `knowledge/index.md` を Read する
2. **index.md がある場合:**
   - tags 列とキーワードを照合する
   - 概要列でもキーワードを照合する
   - ヒットした knowledge ファイルを Read して内容を表示する
3. **index.md がない場合:**
   - `.claude/linear/{slug}/knowledge/**/*.md` を Glob で列挙（`concepts/` 配下も含む）
   - 各ファイルを Grep でキーワード検索する
   - ヒットしたファイルを Read して内容を表示する
4. **概念ページへの誘導**: ヒットした source を `[[name]]` で参照している concept があれば、「関連する概念ページ」として併記する（個別知見から横断知見へ辿れるようにする）
5. **ヒットなしの場合:**
   - 「'{keyword}' に関連する knowledge は見つかりませんでした」と表示
   - 全 tags を一覧表示して「これらのタグで再検索できます」と案内

---

## モード C: 関連 knowledge（related）

1. 現在の Issue ファイルを特定する:
   - ブランチ名から Issue ID を抽出
   - `.claude/linear/{slug}/issues/{ISSUE-ID}.md` を Read する
2. Issue のタイトル・概要・タスク内容からキーワードを抽出する
3. モード B と同じロジックでキーワード検索を実行する
4. さらに、Issue の「変更ファイル」セクションに記載されたファイルパスからもキーワードを抽出:
   - ディレクトリ名・ファイル名をキーワードとして追加
5. **wikilink を 1 ホップ辿る**: ヒットした knowledge 本文の `[[name]]` 参照先を解決し、関連 knowledge として併せて提示する（concept ↔ source の繋がりを 1 段階展開する）
6. ヒットした knowledge を表示する（concept を優先的に上位に置く）

---

## 出力フォーマット

### 一覧表示

```
## Knowledge 一覧（{slug}）

### 概念ページ（横断統合）
| ファイル | tags | status | 概要 |
|---------|------|--------|------|
| concepts/data-fetching.md | data-fetching, cache, pagination | verified | データ取得戦略の横断知見 |

### 個別知見
| ファイル | tags | status | 概要 |
|---------|------|--------|------|
| api-patterns.md | api, rest, pagination | verified | REST API のページネーションパターン |

concept {M}件 / source {N}件。
`/knowledge search <keyword>` で検索、`/knowledge-lint` で健全性チェックができます。
```

### 検索結果

```
## Knowledge 検索結果: "{keyword}"

### api-patterns.md
- tags: api, rest, pagination
- status: verified
- source: TEAM-42

{knowledge の内容}

---
{N}件ヒット
```

### 関連表示

```
## 関連 Knowledge（{ISSUE-ID}）

### api-patterns.md — REST API のページネーションパターン
マッチ理由: Issue タイトルの "API" + tags [api, rest]

{knowledge の内容サマリー}

---
{N}件の関連 knowledge
```
