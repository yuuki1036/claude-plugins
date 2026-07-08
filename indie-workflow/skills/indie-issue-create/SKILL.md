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
  - Skill
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

### Phase 3: Issue ID の生成（採番先確定）

1. `.claude/indie/{slug}/counter.txt` を Read で読み取る
2. `{SLUG大文字}-{番号}` 形式で Issue ID を生成する（例: `MYAPP-3`）
3. **先に `counter.txt` を +1 して Write（採番を確定）**。issue ファイル Write より前に確定することで、途中中断時に同じ番号が再採番されてファイルを上書きするのを防ぐ（discover / follow-up と同一方式）

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

4. **writing-polish 推敲 → ユーザー承認**
   - 提示前に Phase 6.5（writing-polish 連携）を実行し、本文を推敲済みにする
   - 推敲済みの Issue ファイル内容をユーザーに提示する
   - 承認を得てからファイルを書き込む

### Phase 6.5: writing-polish 連携（本文添削・必須）

Phase 6 ステップ3 で本文を生成した後、ステップ4（ユーザー提示・書き込み）の前に writing-polish へ渡して推敲する。`writing-polish` がインストールされていれば**必ず**実行する。未インストール時のみ skip（プラグイン独立性のため。後方互換）。

1. インストール判定（check-deps.sh と同方式）:
   ```bash
   if grep -q '"writing-polish@' "$HOME/.claude/settings.json" 2>/dev/null; then
     WRITING_POLISH=1
   else
     WRITING_POLISH=0
   fi
   ```
   `WRITING_POLISH=0` → 本 Phase を skip。
2. `WRITING_POLISH=1` のとき、`Skill` tool で `writing-polish:writing-polish` を `--embed --tone issue` で呼び、本文の散文部分を渡す。
3. 返ってきた推敲済みテキスト（`POLISH_RESULT_START`〜`POLISH_RESULT_END` マーカー間のみ抽出。サマリ・変更点リストは本文に含めない）を本文の代わりに使う。ただし **9 セクション構造（テンプレートの見出し階層）・frontmatter・プレースホルダ・相対パスリンクは変更しない（構造を壊す結果は破棄し元案を使う）**。変更があれば何を変えたか一言添える。
4. fallback: 呼び出し失敗時は warning を出し、添削前の本文で完了する。

### Phase 7: 後処理

1. 作成したファイルの絶対パスを報告する（採番は Phase 3 で確定済みのため、ここでは `counter.txt` を触らない）
2. **ブランチ自動作成**: **AskUserQuestion** で確認してから `git checkout -b {type}/{SLUG-N}-{description}` を実行する:
   - question: "ブランチ `{type}/{SLUG-N}-{description}` を作成しますか？"
   - header: "ブランチ"
   - options:
     1. label: "作成する" / description: "ブランチを作成してチェックアウト"
     2. label: "スキップ" / description: "ブランチは自分で作る"
   - `description` はタイトルから kebab-case で自動生成（短く、英語）
   - 例: `feat/MYAPP-3-add-auth`, `fix/BLOG-2-fix-typo`
   - type マッピング: bugfix → `fix`, feature → `feat`, investigation → `investigate`, debt → `chore`
3. **feature-dev 連携確認**: **AskUserQuestion** で確認する:
   - question: "feature-dev で実装計画を立てますか？（ブランチを切った直後が最もコンテキストがそろっています）"
   - header: "feature-dev"
   - options:
     1. label: "はい" / description: "feature-dev で実装計画を立てる"
     2. label: "いいえ" / description: "後で自分でやる"

   **「はい」選択時の upfront 引き継ぎ**（Phase 5.4-5.5 の調査結果を feature-dev 側で再走査させないため、以下を必ず prompt に含めて呼び出す）:

   ```
   /feature-dev {ISSUE-ID}: {タイトル}

   ## Issue コンテキスト
   - Issue ファイル: `.claude/indie/{slug}/issues/{ISSUE-ID}.md`
   - type: {type}, scope_size: {scope_size}
   - 概要: {Phase 5 で収集した概要}

   ## Phase 5.4 コードベース調査結果
   - 確認済みファイル: {パス一覧}
   - 既存実装の有無: {あれば該当箇所のサマリー}

   ## Phase 5.5 関連 Knowledge
   - {参照済み knowledge ファイル名と tags}

   ## 親 Issue（frontmatter の parent: に値がある場合）
   - [{PARENT-ID}] {タイトル} — 背景・計画のサマリー

   上記の context を前提に、実装計画を策定してください。
   ```

   feature-dev 実行後、`feature_dev_plan:` frontmatter に生成された計画ファイルのパスを記載することをユーザーに案内する（手動更新、または `/indie-issue-maintain` で反映）。
4. 次のアクションを案内する:
   - 計画の記入（feature の場合）
   - 調査の開始（investigation の場合）
   - 修正の着手（bugfix の場合）
   - 対応方針の検討（debt の場合）

### Phase 8: spec 選択（着手前の仕様化ルーティング）

実装に入る前に「どの仕様 (spec) を先に書くか」を判定する。仕様系プラグイン（bdd-spec / design-doc / adr-keeper）が 1 つも入っていなければ完全に skip（dormant・後方互換 100%）。feature-dev に引き継ぐ場合（Phase 7 で「はい」）は WHAT/HOW を feature-dev が内部 Phase で生成するため、この Phase には実質到達しない（自分で実装する経路でのみ働く）。

1. **dormant 判定**（check-deps.sh / issue-design Phase 0.5 と同方式）:
   ```bash
   SPEC_BDD=0; SPEC_DD=0; SPEC_ADR=0
   grep -q '"bdd-spec@'   "$HOME/.claude/settings.json" 2>/dev/null && SPEC_BDD=1
   grep -q '"design-doc@' "$HOME/.claude/settings.json" 2>/dev/null && SPEC_DD=1
   grep -q '"adr-keeper@' "$HOME/.claude/settings.json" 2>/dev/null && SPEC_ADR=1
   ```
   - 3 つとも 0（いずれの spec プラグインも未導入）→ 本 Phase を skip

2. **自動推奨（判定表）**: type と Issue の性質から推奨を 1 つ決める。WHAT / HOW / WHY は排他ではない（大きめの feature は bdd-spec で WHAT を固めてから design-doc で HOW、のように併用してよい）。推奨が未導入の spec を指す場合（例: design-doc 推奨だが `SPEC_DD=0`）は導入済みの次点か「不要」にフォールバックする。

   共有 3 軸コア（正本: `.claude-plugin/lib/routing-axes.md`。spec-advisor / linear-workflow と同期・quality-check が検証。**編集時は正本と全消費サイトを同時更新**）:

   <!-- ROUTING-AXES:START -->
   | 軸 | シグナル | 委譲先 | 出力先 |
   |---|---|---|---|
   | **WHAT** | ユーザー可視な振る舞い・受け入れ条件が中心（新機能・仕様変更） | `bdd-spec:create-spec` | Scenario/Examples を `features/` に |
   | **HOW** | 技術方式の選定・代替案比較・複数 Issue/コンポーネントに波及 | `design-doc:design-doc` | トレードオフ比較を `.claude/designs/` に |
   | **WHY** | 単一の重要な設計判断（ライブラリ・方針）を理由ごと残す | `adr-keeper:adr` | 決定を `.claude/adr/` に append-only |
   <!-- ROUTING-AXES:END -->

   type 別の追加判定（このワークフロー固有・同期対象外）:

   | type / シグナル | 推奨 |
   |---|---|
   | 影響範囲が限定的な修正・typo・設定変更（bugfix） | **不要** — 仕様化コストが見合わない → 直接実装 |
   | 原因調査・分析（investigation） | **不要**（結論で方針が決まれば adr）— 調査は Issue 本文で十分 |
   | 技術的負債の解消（debt） | **不要**（移行方式が大きいなら design-doc）— 小さな改善は直接着手、大きな移行は HOW を design-doc に |

3. **提示（自動推奨 → 低確信時のみ質問）**:
   - **確信度が高い**（bugfix / debt → 不要、明確な新機能 → bdd-spec 等）: 推奨と根拠を 1 文で示してそのまま進む（「不要」なら何も起動しない）
   - **迷う**: **AskUserQuestion** で確認する（**導入済みの spec のみ** option 化、推奨を先頭に `(推奨)`、「不要」を必ず含める）:
     - question: 「着手前に仕様を書きますか？{推奨} を推奨します（{根拠1行}）」
     - header: "spec 選択"
     - options（導入済みのもののみ提示。例）:
       1. label: "bdd-spec (推奨)" / description: "振る舞い仕様 (WHAT) を Scenario で先に固める"
       2. label: "design-doc" / description: "技術設計 (HOW)・代替案比較を永続化"
       3. label: "adr-keeper" / description: "単一の設計判断 (WHY) を記録"
       4. label: "不要" / description: "仕様化せず直接実装に入る"

4. **委譲（dormant・失敗時 fallback）**: 選択された spec skill を `Skill` tool で起動する:
   - bdd-spec → `bdd-spec:create-spec`（Issue から role/want/why を渡せれば非対話 API、不足なら通常起動）
   - design-doc → `design-doc:design-doc`（new モードで代替案比較を grill）
   - adr-keeper → `adr-keeper:adr`（new モード。export 非対話 API は無いので通常起動。生成された ADR パスを Issue の「参考資料」に記録）
   - 「不要」→ 起動せず完了
   - fallback: 起動失敗時は warning を出し、Issue ファイルのまま完了する（spec 化は任意機能・フローを止めない）
