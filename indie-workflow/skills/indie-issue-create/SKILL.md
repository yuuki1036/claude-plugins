---
name: indie-issue-create
description: >
  Issue ファイルの新規作成。テンプレート選択、ブランチ自動作成、feature-dev への接続まで
  一貫サポート。
  トリガー: 「タスク作成」「Issue起票」「新しいタスク」「/indie-issue-create」
effort: medium
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
---

# Issue Create

ユーザーからタスク情報をヒアリングし、テンプレートに基づいて Issue ファイルを新規作成する。

## ワークフロー

### Phase 1: プロジェクトスラッグの特定

1. コマンド引数で指定されていればそれを使う
2. 未指定なら現在のブランチ名から推定を試みる（`git branch --show-current`）
3. 推定できなければユーザーに確認する

### Phase 2: プロジェクトの存在確認

`.claude/indie/{slug}/` が存在しない場合、`/indie-init {slug}` の実行を案内して処理を中止する。

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

- 確信度が高い場合（obvious な bugfix / debt）は判断根拠を1文で示してそのまま進む
- 判断に迷う場合は **AskUserQuestion** でテンプレートを確認する:
  - question: 「{type} テンプレートを推奨します（{根拠1行}）。使用するテンプレートを選択してください」
  - header: "テンプレート"
  - options:
    1. label: "bugfix" / description: "バグ修正・typo・設定変更など影響範囲が限定的"
    2. label: "feature" / description: "新機能追加・既存機能の改修・リファクタリング"
    3. label: "investigation" / description: "原因調査・パフォーマンス分析・技術選定"
    4. label: "debt" / description: "コード品質改善・依存関係更新・非推奨 API の移行"
- テンプレート選択の回答が feature だった場合、続けて **AskUserQuestion** でスコープサイズを確認する:
  - question: "この feature の実装規模は？（タスク数上限と見積もり基準に使用）"
  - header: "スコープ"
  - options:
    1. label: "small" / description: "3タスク以下（1-2日で完了）"
    2. label: "medium" / description: "7タスク以下（数日〜1週間）"
    3. label: "large" / description: "15タスク以下（1週間以上）"
- テンプレートは以下を Read で読み込む:
  - `${CLAUDE_SKILL_DIR}/references/{type}.md`

### Phase 5: Issue 情報のヒアリング

1. ユーザーにタイトルを確認する
2. ユーザーに概要（説明）を確認する
3. 既にユーザーが説明している場合はそれを使い、重複して聞かない

### Phase 5.4: コードベース現状確認

Issue の内容が確定した段階で、対象コードの現状を軽く確認し「すでに実装済みの機能に対する Issue 起票」を防ぐ。

1. **キーワード抽出**: Issue のタイトル・概要から具体的な対象を示すキーワードを抽出する
   - 例: 「Home ページ実装」→ `Home`, `HeroSection`, `page.tsx`
   - 例: 「ユーザー認証の追加」→ `auth`, `login`, `signIn`
2. **コードベースの確認**:
   - Glob でファイルパスの存在確認（例: `src/app/**/page.tsx`, `**/*Auth*.{ts,tsx}`）
   - Grep でキーワードの実装有無を確認（例: `HeroSection`, `signIn(`）
3. **判定と提示**:
   - 確認結果が空 or 関連薄: そのまま Phase 5.5 へ進む
   - **既存実装が見つかった場合**: ヒット箇所（ファイルパス + 1行サマリー）をユーザーに提示し、**AskUserQuestion** で確認する:
     - question: 「該当機能がすでに実装されている可能性があります。Issue 起票を続けますか？」
     - header: "起票判断"
     - options:
       1. label: "続行" / description: "別の観点での Issue として起票する"
       2. label: "スコープ変更" / description: "タイトル・概要を調整してから起票する"
       3. label: "中止" / description: "Issue 起票を取りやめる"
4. **軽量運用**:
   - 確認は 3〜5 回以内の Glob/Grep に留める（全網羅ではない）
   - bugfix / investigation / debt は対象コードが明確なことが多いので、この Phase はスキップしてよい（feature 時に特に有効）

### Phase 5.5: 関連 Knowledge の検索

Issue の内容が確定した段階で、既存の knowledge を検索する。

1. `.claude/indie/{slug}/knowledge/index.md` の存在を確認（Read）
2. **index.md が存在する場合:**
   - index.md を Read で読み込む
   - Issue のタイトル・概要からキーワードを抽出する
   - index.md の tags 列とキーワードを照合し、関連する knowledge を特定する
3. **index.md が存在しない場合:**
   - `.claude/indie/{slug}/knowledge/*.md` を Glob で列挙する
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
3. **ブランチ自動作成**: **AskUserQuestion** で確認してから `git checkout -b {type}/{SLUG-N}-{description}` を実行する:
   - question: "ブランチ `{type}/{SLUG-N}-{description}` を作成しますか？"
   - header: "ブランチ"
   - options:
     1. label: "作成する" / description: "ブランチを作成してチェックアウト"
     2. label: "スキップ" / description: "ブランチは自分で作る"
   - `description` はタイトルから kebab-case で自動生成（短く、英語）
   - 例: `feat/MYAPP-3-add-auth`, `fix/BLOG-2-fix-typo`
   - type マッピング: bugfix → `fix`, feature → `feat`, investigation → `investigate`, debt → `chore`
4. **feature-dev 連携確認**: **AskUserQuestion** で確認する:
   - question: "feature-dev で実装計画を立てますか？（ブランチを切った直後が最もコンテキストがそろっています）"
   - header: "feature-dev"
   - options:
     1. label: "はい" / description: "feature-dev で実装計画を立てる"
     2. label: "いいえ" / description: "後で自分でやる"
5. 次のアクションを案内する:
   - 計画の記入（feature の場合）
   - 調査の開始（investigation の場合）
   - 修正の着手（bugfix の場合）
   - 対応方針の検討（debt の場合）
