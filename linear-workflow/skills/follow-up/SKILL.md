---
name: follow-up
description: >
  開発中に発生した follow-up タスクの記録・一覧・Issue昇格を管理する。
  トリガー: 「follow-up」「後でやる」「別タスク」「切り出し」「todo メモ」
  「フォローアップ記録」「/follow-up」「/follow-up list」「/follow-up promote」
effort: medium
allowed-tools:
  - mcp__linear__save_issue
  - mcp__linear__get_issue
  - Read
  - Write
  - Edit
  - Glob
  - Bash
  - AskUserQuestion
---

# Follow-up タスク管理

## 概要

開発中に発生した follow-up タスクを低摩擦で記録し、後から Issue に昇格できる仕組み。
follow-up ファイルは `.claude/linear/{slug}/follow-ups/` に配置する。

## コマンド

| コマンド | 動作 |
|----------|------|
| `/follow-up` | 新規 follow-up を作成 |
| `/follow-up new` | 新規 follow-up を作成 |
| `/follow-up list` | open な follow-up 一覧を表示 |
| `/follow-up promote [FILE]` | 指定した follow-up を Issue に昇格 |

---

## ファイルフォーマット

### 配置先

`.claude/linear/{slug}/follow-ups/{YYYYMMDD}-{kebab-slug}.md`

ファイル名の `{kebab-slug}` はタイトルの kebab-case 短縮（例: `20260403-fix-null-pointer.md`）。
同日に同名ファイルが存在する場合は `-2`, `-3` のサフィックスを付加する。

### フロントマター

```yaml
---
title: "タイトル"
status: open              # open / promoted / backlog / dismissed
type: bug                 # bug / feature / debt / investigation / idea
priority: medium          # high / medium / low
source_issue: TEAM-123    # 元 Issue（必須）
linear_issue: ""          # 既存 Linear Issue への紐づけ（任意）
created: YYYY-MM-DD
---
```

### 本文構造

```markdown
## 内容

{問題・アイデア・やることの説明}

## 発生コンテキスト

{どんな作業中に気づいたか。コード箇所への参照があれば記載}

## 対応メモ

{対応方針の検討メモ。空欄でもよい}
```

---

## Phase 0: サブコマンド判定

1. 引数を確認する
2. `new` または引数なし → **Phase N** へ
3. `list` → **Phase L** へ
4. `promote [ファイル名]` → **Phase P** へ
5. 引数が不明な場合 → AskUserQuestion でサブコマンドを選択:
   - question: "どの操作を実行しますか？"
   - header: "Follow-up 操作"
   - options:
     1. label: "new" / description: "新規 follow-up を作成"
     2. label: "list" / description: "未処理の follow-up 一覧を表示"
     3. label: "promote" / description: "follow-up を Issue に昇格"

---

## Phase N: New（follow-up 作成）

### N1: コンテキスト特定

1. `git branch --show-current` でブランチ名を取得する（Bash）
2. ブランチ名から Issue ID を抽出する（正規表現: `[A-Z]+-\d+`）
3. Issue ID が取れない場合はユーザーに `source_issue` を入力させる
4. Issue ID プレフィックスを小文字化して slug を特定する
5. `.claude/linear/{slug}/` の存在を確認。存在しない場合は `/init` への誘導で中断

### N2: 内容ヒアリング

1. ユーザーが既に説明している場合はそれを使う（重複して聞かない）
2. タイトルを確認する
3. type を自動判定し、確信が低い場合のみ AskUserQuestion:
   - question: "このタスクのタイプは？"
   - header: "タイプ"
   - options: bug / feature / debt / investigation / idea

### N3: priority 確認

- 会話から明らかな場合はスキップ
- 不明な場合は AskUserQuestion:
  - question: "優先度は？"
  - header: "優先度"
  - options: high / medium / low

### N4: Linear Issue 紐づけ確認

1. AskUserQuestion:
   - question: "既存の Linear Issue に紐づけますか？"
   - header: "Linear Issue 紐づけ"
   - options:
     1. label: "紐づけない" / description: "ローカルメモとして記録"
     2. label: "紐づける" / description: "Linear Issue ID を入力"
2. 「紐づける」選択時: Issue ID を入力させて `linear_issue` に設定

### N5: ファイル生成

1. ファイル名を生成: `{YYYYMMDD}-{kebab-slug}.md`
2. 同名ファイルの衝突チェック: Glob で `.claude/linear/{slug}/follow-ups/{YYYYMMDD}-{kebab-slug}*.md` を確認
3. 衝突がある場合はサフィックスを付加
4. frontmatter + 本文を生成
5. ユーザーに内容を提示して承認を得る
6. Write でファイルを書き込む

### N6: 完了報告

- ファイルパスを報告
- 「`/follow-up list` で一覧確認、`/follow-up promote {filename}` で Issue 昇格できます」と案内

---

## Phase L: List（一覧表示）

1. `git branch --show-current` でブランチ名を取得する（Bash）
2. ブランチ名から slug を特定する。特定できない場合は全プロジェクトをスキャン
3. `.claude/linear/{slug}/follow-ups/*.md` を Glob で列挙
   - slug 不明時は `.claude/linear/*/follow-ups/*.md`
4. 各ファイルを Read し frontmatter を取得
5. `status: open` の follow-up を priority 降順、created 降順でソート
6. 表示形式:
   ```
   **Follow-up 一覧（{N}件）**

   | ファイル | タイトル | type | priority | source | 作成日 |
   |--------|---------|------|----------|--------|--------|
   | 20260402-fix-null.md | null チェック漏れ | bug | high | TEAM-123 | 2026-04-02 |
   ```
7. `status: promoted` / `status: backlog` / `status: dismissed` の件数をフッターに表示
8. 件数が0の場合は「open な follow-up はありません」と表示

---

## Phase P: Promote（Issue 昇格）

### P1: 対象ファイルの特定

1. 引数でファイル名が指定されていればそれを使う
2. 未指定の場合は Phase L の一覧を表示して AskUserQuestion で選択させる

### P2: 対象ファイルの読み込み

1. Read で内容を確認し、ユーザーに表示する

### P3: 昇格先の確認

- AskUserQuestion:
  - question: "Issue の作成先は？"
  - header: "Issue 昇格先"
  - options:
    1. label: "ローカルのみ" / description: "ローカル Issue ファイルのみ作成（Linear には起票しない）"
    2. label: "Linear にも作成" / description: "save_issue で Linear にも起票する"

- 「Linear にも作成」選択時: Linear MCP の利用可能性を確認する
  - `mcp__linear__get_issue` を軽量に呼び出してテスト
  - 失敗した場合は AskUserQuestion:
    - question: "Linear MCP が利用できません。"
    - header: "Linear MCP 未検出"
    - options:
      1. label: "ローカルのみに変更" / description: "ローカル Issue ファイルのみ作成する"
      2. label: "中断" / description: "promote を中断する"

### P4: テンプレート選択

1. follow-up の `type` から Issue テンプレートを推定する:
   - bug → bugfix
   - feature → feature
   - debt → bugfix（linear には debt テンプレートなし）
   - investigation → investigation
   - idea → feature
2. 確信が低い場合のみ AskUserQuestion

### P5: Issue 情報の確認

1. follow-up の「内容」と「対応メモ」を元に Issue の概要を生成
2. ユーザーに提示して承認を得る

### P5.5: 関連 Knowledge の検索

1. `.claude/linear/{slug}/knowledge/index.md` の存在を確認（Read）
2. 存在する場合: follow-up のタイトル・内容からキーワードを抽出し、index.md の tags と照合
3. 関連する knowledge があれば Issue ファイル生成時に「関連 Knowledge」として参照を含める

### P6: Issue 作成の実行

- **「ローカルのみ」の場合**:
  1. P4 で選択したテンプレート（`${CLAUDE_SKILL_DIR}/../issue-create/references/{type}.md`）を Read する
  2. follow-up の「内容」を概要セクション、「対応メモ」を計画セクションに反映してIssue ファイルを生成
  3. 配置先: `.claude/linear/{slug}/issues/{ISSUE-ID}.md`
  4. `linear_issue` フィールドがあれば、その ID を Issue ファイルの `linear` frontmatter に設定
  5. ユーザーに Issue ファイル内容を提示し、承認を得てから Write
- **「Linear にも作成」の場合**:
  1. `mcp__linear__save_issue` で Linear Issue を作成する
     - title: follow-up の title
     - description: 「内容」+「対応メモ」セクションの内容
  2. 返却された Issue ID を使って上記「ローカルのみ」と同じ手順でローカル Issue ファイルも生成する

### P7: follow-up ファイルの更新

1. `status: promoted` に更新
2. frontmatter に昇格先を追記:
   ```yaml
   promoted_to: TEAM-789
   promoted_date: YYYY-MM-DD
   ```

### P8: 完了報告

- 作成した Issue ファイルのパスと（Linear の場合）Issue ID を報告

---

## 注意事項

- follow-up は軽量なメモ。Issue のような厳密な構造は求めない
- Linear API の書き込み（`save_issue`）はユーザーが Phase P3 で「Linear にも作成」を明示選択した場合のみ
- follow-ups/ ディレクトリは初回 Write 時に自動作成される
