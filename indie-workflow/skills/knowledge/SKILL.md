---
name: knowledge
description: >
  プロジェクトの蓄積された知見を検索・参照する。
  実装方針の検討時や過去に似た問題を解決した可能性がある時に自動的に使用する。
  トリガー: 「知見」「knowledge」「過去に似た」「前にもやった」「/knowledge」
effort: low
allowed-tools:
  - Read
  - Glob
  - Grep
---

# Knowledge

プロジェクトに蓄積された知見（knowledge）を検索・参照するスキル。
ユーザーの明示的な呼び出しだけでなく、実装方針の検討時や問題解決時に Claude が自律的に使用する。

**モード分岐:**
- 引数なし → 現プロジェクトの全 knowledge 一覧
- `search <keyword>` → tags/内容でキーワード検索
- `related` → 現在の Issue に関連する knowledge を表示

---

## Phase 0: プロジェクト特定

1. 現在のブランチ名から Issue ID プレフィックスを抽出する
   - `git branch --show-current` を実行
   - `{type}/{PROJECT-N}-{desc}` パターンからプロジェクト部分を小文字化
2. `.claude/indie/{slug}/knowledge/` の存在を確認する
3. ブランチから特定できない場合:
   - `.claude/indie/*/knowledge/` を Glob で全プロジェクト検索
   - 単一プロジェクトならそのスラッグを使用
   - 複数プロジェクトなら **AskUserQuestion** で選択:
     - question: "どのプロジェクトの knowledge を表示しますか？"
     - options: 各プロジェクト名

---

## モード A: 一覧表示（引数なし）

1. `knowledge/index.md` の存在を確認（Read）
2. **index.md が存在する場合:**
   - テーブル全体を表示する
3. **index.md が存在しない場合:**
   - `.claude/indie/{slug}/knowledge/*.md` を Glob で列挙
   - 各ファイルのフロントマター（tags, status, source）を Read して一覧化
4. knowledge が0件の場合:
   - 「このプロジェクトにはまだ knowledge がありません。`/indie-issue-maintain` で知見を切り出せます。」と表示

---

## モード B: キーワード検索（search <keyword>）

1. `knowledge/index.md` を Read する
2. **index.md がある場合:**
   - tags 列とキーワードを照合する
   - 概要列でもキーワードを照合する
   - ヒットした knowledge ファイルを Read して内容を表示する
3. **index.md がない場合:**
   - `.claude/indie/{slug}/knowledge/*.md` を Glob で列挙
   - 各ファイルを Grep でキーワード検索する
   - ヒットしたファイルを Read して内容を表示する
4. **ヒットなしの場合:**
   - 「'{keyword}' に関連する knowledge は見つかりませんでした」と表示
   - 全 tags を一覧表示して「これらのタグで再検索できます」と案内

---

## モード C: 関連 knowledge（related）

1. 現在の Issue ファイルを特定する:
   - ブランチ名から Issue ID を抽出
   - `.claude/indie/{slug}/issues/{ISSUE-ID}.md` を Read する
2. Issue のタイトル・概要・タスク内容からキーワードを抽出する
3. モード B と同じロジックでキーワード検索を実行する
4. さらに、Issue の「変更ファイル」セクションに記載されたファイルパスからもキーワードを抽出:
   - ディレクトリ名・ファイル名をキーワードとして追加
5. ヒットした knowledge を表示する

---

## 出力フォーマット

### 一覧表示

```
## Knowledge 一覧（{slug}）

| ファイル | tags | status | 概要 |
|---------|------|--------|------|
| api-patterns.md | api, rest, pagination | verified | REST API のページネーションパターン |

{N}件の knowledge が蓄積されています。
`/knowledge search <keyword>` で検索できます。
```

### 検索結果

```
## Knowledge 検索結果: "{keyword}"

### api-patterns.md
- tags: api, rest, pagination
- status: verified
- source: MYAPP-42

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
