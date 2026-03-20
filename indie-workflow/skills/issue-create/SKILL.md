---
name: issue-create
description: >
  Issue ファイルの新規作成。タスクの性質に応じて bugfix / feature /
  investigation / debt テンプレートを選択し、ローカルに Issue ファイルを生成する。
  トリガー: 「Issue作成」「タスク作成」「新しいタスク」「起票」「/issue-create」
allowed-tools:
  - Read
  - Write
  - Glob
  - Bash
---

# Issue Create

ユーザーからタスク情報をヒアリングし、テンプレートに基づいて Issue ファイルを新規作成する。

## ワークフロー

### Phase 1: プロジェクトスラッグの特定

1. コマンド引数で指定されていればそれを使う
2. 未指定なら現在のブランチ名から推定を試みる（`git branch --show-current`）
3. 推定できなければユーザーに確認する

### Phase 2: プロジェクトの存在確認

`.claude/indie/{slug}/` が存在しない場合、`/init {slug}` の実行を案内して処理を中止する。

### Phase 3: Issue ID の生成

1. `.claude/indie/{slug}/counter.txt` を Read で読み取る
2. `{SLUG大文字}-{番号}` 形式で Issue ID を生成する（例: `MYAPP-3`）

### Phase 4: テンプレート選択

タスクの性質に応じてテンプレートを自動判定する:

| type | 用途 | 判断基準 |
|------|------|----------|
| bugfix | 小規模な修正 | バグ修正、typo、設定変更など影響範囲が限定的 |
| feature | 機能開発・リファクタ | 新機能追加、既存機能の改修、リファクタリング |
| investigation | 調査・分析 | 原因調査、パフォーマンス分析、技術選定 |
| debt | 技術的負債の解消 | コード品質改善、依存関係更新、非推奨 API の移行 |

- 判断に迷う場合はユーザーに確認する
- feature テンプレートの場合、スコープサイズ（small / medium / large）をユーザーに確認する
- テンプレートは以下を Read で読み込む:
  - `${CLAUDE_PLUGIN_ROOT}/skills/issue-create/references/{type}.md`

### Phase 5: Issue 情報のヒアリング

1. ユーザーにタイトルを確認する
2. ユーザーに概要（説明）を確認する
3. 既にユーザーが説明している場合はそれを使い、重複して聞かない

### Phase 6: Issue ファイル生成

1. **配置先**
   - `.claude/indie/{slug}/issues/{ISSUE-ID}.md`

2. **frontmatter の記入**
   - `status: in-progress`
   - `id: {ISSUE-ID}`
   - `type: {選択したtype}`
   - `scope_size: {small|medium|large}`（feature の場合のみ）
   - `created: {今日の日付}`
   - `last_active: {今日の日付}`
   - `pr: ""` (空欄)

3. **本文の生成**
   - テンプレートの構造に従う
   - ユーザーから得た情報を「概要」セクションに反映する
   - プレースホルダはそのまま残し、ユーザーが後から埋められるようにする

4. **ユーザー承認**
   - 生成した Issue ファイルの内容をユーザーに提示する
   - 承認を得てからファイルを書き込む

### Phase 7: 後処理

1. `counter.txt` の値をインクリメントして書き込む
2. 作成したファイルの絶対パスを報告する
3. ブランチ作成を提案する（`{type}/{slug}-{N}` 形式、例: `feature/myapp-3`）
4. 次のアクションを案内する:
   - 計画の記入（feature の場合）
   - 調査の開始（investigation の場合）
   - 修正の着手（bugfix の場合）
   - 対応方針の検討（debt の場合）
