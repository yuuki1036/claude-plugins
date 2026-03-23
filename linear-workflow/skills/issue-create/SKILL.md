---
name: issue-create
description: >
  Issue ファイルの新規作成。タスクの性質に応じて bugfix / feature / investigation
  テンプレートを選択し、Linear MCP から情報を取得して Issue ファイルを生成する。
  トリガー: 「Issue作成」「Issueファイル作成」「新しいタスク」「Issueファイルを作って」「Linearの Issue をローカルに取り込む」「/issue-create」
allowed-tools:
  - mcp__linear__get_issue
  - Read
  - Write
  - Glob
  - AskUserQuestion
---

# Issue Create

Linear Issue の情報を取得し、テンプレートに基づいて Issue ファイルを新規作成する。

## ワークフロー

### Phase 1: Issue 情報の取得

1. Issue ID をユーザーから受け取る（session-start から渡される場合もある）
2. Linear MCP `get_issue` でタイトル・説明・プロジェクト情報を取得する
3. 取得できない場合はユーザーに手動入力を依頼する

### Phase 2: テンプレート選択

タスクの性質に応じてテンプレートを自動判定する:

| type | 用途 | 判断基準 |
|------|------|----------|
| bugfix | 小規模な修正 | バグ修正、typo、設定変更など影響範囲が限定的 |
| feature | 機能開発・リファクタ | 新機能追加、既存機能の改修、リファクタリング |
| investigation | 調査・分析 | 原因調査、パフォーマンス分析、技術選定 |

- 確信度が高い場合（obvious な bugfix / investigation）は判断根拠を1文で示してそのまま進む
- 判断に迷う場合は `rules/issue-create-interaction.md` のテンプレート選択ルールに従い、AskUserQuestion でユーザーに確認する
- テンプレートは以下を Read で読み込む:
  - `${CLAUDE_PLUGIN_ROOT}/skills/issue-create/references/{type}.md`

### Phase 2.5: 関連 Knowledge の検索

Issue の情報が確定した段階で、既存の knowledge を検索する。

1. `.claude/linear/{slug}/knowledge/index.md` の存在を確認（Read）
2. **index.md が存在する場合:**
   - index.md を Read で読み込む
   - Issue のタイトル・説明からキーワードを抽出する
   - index.md の tags 列とキーワードを照合し、関連する knowledge を特定する
3. **index.md が存在しない場合:**
   - `.claude/linear/{slug}/knowledge/*.md` を Glob で列挙する
   - knowledge ファイルが存在すれば、各ファイルのフロントマター（tags）と照合する
4. **関連 knowledge が見つかった場合:**
   - ユーザーに提示する:
     ```
     関連する knowledge が見つかりました:
     - `knowledge/{topic}.md` — {概要}（tags: {tags}）
     参照しますか？
     ```
   - ユーザーが参照を希望した場合、Read で内容を表示する
   - Issue ファイルの「備考」セクションに関連 knowledge へのリンクを記載する

### Phase 3: Issue ファイル生成

1. **配置先の決定**
   - `.claude/linear/{slug}/issues/{ISSUE-ID}.md`
   - slug は Issue ID のプレフィックス（チーム識別子）を小文字化する（例: `TEAM-123` → `team`）

2. **frontmatter の記入**
   - `status: in-progress`
   - `linear: {ISSUE-ID}`
   - `type: {選択したtype}`
   - `created: {今日の日付}`
   - `pr: ` (空欄)
   - Linear のプロジェクト情報があれば `project:` も記入

3. **本文の生成**
   - テンプレートの構造に従う
   - Linear の description があれば「概要」セクションに反映する
   - プレースホルダはそのまま残し、ユーザーが後から埋められるようにする

4. **ユーザー承認**
   - 生成した Issue ファイルの内容をユーザーに提示する
   - 承認を得てからファイルを書き込む

### Phase 4: 確認

1. 作成したファイルの絶対パスを報告する
2. **feature-dev 連携確認**: `rules/issue-create-interaction.md` の feature-dev 連携ルールを参照
3. 次のアクションを案内する:
   - 計画の記入（feature の場合）
   - 調査の開始（investigation の場合）
   - 修正の着手（bugfix の場合）
