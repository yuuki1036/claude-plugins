---
name: issue-create
description: >
  Issue ファイルの新規作成。タスクの性質に応じて bugfix / feature / investigation
  テンプレートを選択し、Linear MCP から情報を取得して Issue ファイルを生成する。
  トリガー: 「Issue作成」「Issueファイル作成」「新しいタスク」「Issueファイルを作って」「Linearの Issue をローカルに取り込む」「/issue-create」
effort: medium
allowed-tools:
  - mcp__linear__get_issue
  - Read
  - Write
  - Glob
  - Bash
  - Skill
  - AskUserQuestion
---

# Issue Create

Linear Issue の情報を取得し、テンプレートに基づいて Issue ファイルを新規作成する。

## ワークフロー

### Phase 0: Linear MCP 利用可能性チェック

1. Phase 1 の `get_issue` 呼び出しを試みる（Phase 1 と兼用）
2. ツールが見つからない・接続エラーの場合:
   - **AskUserQuestion** で続行/中断を確認する:
     - question: "Linear MCP が利用できません。MCP なしで続行する場合、Issue 情報は手動入力になります。"
     - header: "Linear MCP 未検出"
     - options:
       1. label: "続行" / description: "Issue 情報を手動入力して作成する"
       2. label: "中断" / description: "スキルを中断する"
   - 「中断」選択時: スキルを終了する
   - 「続行」選択時: Phase 1 の手動入力フローに進む
3. 正常に応答が返った場合: そのまま Phase 1 の通常フローに進む

### Phase 1: Issue 情報の取得

1. Issue ID をユーザーから受け取る（session-start から渡される場合もある）
2. Linear MCP `get_issue` でタイトル・説明・プロジェクト情報を取得する（Phase 0 で取得済みの場合は再利用する）
3. 取得できない場合はユーザーに手動入力を依頼する

### Phase 2: テンプレート選択

タスクの性質に応じてテンプレートを自動判定する:

| type | 用途 | 判断基準 |
|------|------|----------|
| bugfix | 小規模な修正 | バグ修正、typo、設定変更など影響範囲が限定的 |
| feature | 機能開発・リファクタ | 新機能追加、既存機能の改修、リファクタリング |
| investigation | 調査・分析 | 原因調査、パフォーマンス分析、技術選定 |
| debt | 技術的負債の解消 | コード品質改善、依存関係更新、非推奨 API の移行 |

- 確信度が高い場合（obvious な bugfix / investigation / debt）は判断根拠を1文で示してそのまま進む
- 判断に迷う場合は **AskUserQuestion** でテンプレートを確認する:
  - question: 「{type} テンプレートを推奨します（{根拠1行}）。使用するテンプレートを選択してください」
  - header: "テンプレート"
  - options:
    1. label: "bugfix" / description: "バグ修正・設定変更など影響範囲が限定的"
    2. label: "feature" / description: "新機能追加・既存機能の改修・リファクタリング"
    3. label: "investigation" / description: "原因調査・パフォーマンス分析・技術選定"
    4. label: "debt" / description: "コード品質改善・依存関係更新・非推奨 API の移行"
- テンプレートは以下を Read で読み込む:
  - `${CLAUDE_SKILL_DIR}/references/{type}.md`

### Phase 2.4: コードベース現状確認（手動入力起票時）

Phase 0 で Linear MCP 未検出のまま「続行」した手動入力起票経路では、Linear 側で重複がチェックされないため、対象コードの現状を軽く確認し「すでに実装済みの機能に対する Issue 起票」を防ぐ。**MCP から取得できた通常経路ではこの Phase をスキップしてよい**（Linear 側で重複が管理されるため）。

1. **キーワード抽出**: Issue のタイトル・概要から具体的な対象を示すキーワードを抽出する
   - 例: 「Home ページ実装」→ `Home`, `HeroSection`, `page.tsx`
   - 例: 「ユーザー認証の追加」→ `auth`, `login`, `signIn`
2. **コードベースの確認**:
   - Glob でファイルパスの存在確認（例: `src/app/**/page.tsx`, `**/*Auth*.{ts,tsx}`）
   - Grep でキーワードの実装有無を確認（例: `HeroSection`, `signIn(`）
   - あわせて `.claude/linear/{slug}/issues/*.md` を Glob/Grep で走査し、同一トピックの既存 Issue が無いかも確認する
3. **判定と提示**:
   - 確認結果が空 or 関連薄: そのまま Phase 2.5 へ進む
   - **既存実装・既存 Issue が見つかった場合**: ヒット箇所（ファイルパス + 1行サマリー）をユーザーに提示し、**AskUserQuestion** で確認する:
     - question: 「該当機能がすでに実装済み、または既存 Issue が存在する可能性があります。Issue 起票を続けますか？」
     - header: "起票判断"
     - options:
       1. label: "続行" / description: "別の観点での Issue として起票する"
       2. label: "スコープ変更" / description: "タイトル・概要を調整してから起票する"
       3. label: "中止" / description: "Issue 起票を取りやめる"
4. **軽量運用**:
   - 確認は 3〜5 回以内の Glob/Grep に留める（全網羅ではない）
   - bugfix / investigation / debt は対象コードが明確なことが多いので、この Phase はスキップしてよい（feature 時に特に有効）

### Phase 2.5: 関連ナレッジの検索（knowledge / ADR / 完了 Issue）

Issue の情報が確定した段階で、過去の蓄積から「この問題を過去に解いた・判断したことがないか」を検索し、関連するものを起票フローで提示する（蓄積→活用の導線を閉じる）。検索は grep ベースの安価な絞り込みのみとし、embedding 等の高コスト処理・環境依存は持ち込まない（ファネル先頭の絞り込み）。

まず Issue のタイトル・説明から検索キーワードを 2〜4 個抽出する（固有名詞・機能名・エラー語・ドメイン語を優先）。以降の grep は Bash で実行する（例: `grep -rliE "<kw1>|<kw2>" <dir> 2>/dev/null`）。

**1. knowledge**
1. `.claude/linear/{slug}/knowledge/index.md` があれば Read し、tags 列とキーワードを照合する
2. index.md が無ければ `.claude/linear/{slug}/knowledge/*.md` を Glob し、各フロントマター（tags）と照合する
3. 併せてキーワードで `.claude/linear/{slug}/knowledge/` を grep し、tags に載らない本文一致も拾う

**2. 完了 Issue**
- `.claude/linear/{slug}/issues/` をキーワードで grep し、ヒットしたファイルのうち frontmatter が `status: completed`（または `canceled`）のものを「過去に解いた/判断した類似 Issue」として抽出する（未完了 Issue との重複起票チェックとは目的が別なので、ここでは過去に解決・判断済み＝completed / canceled に絞る）

**3. ADR（dormant・adr-keeper 導入時のみ）**
- `.claude/adr/` が存在する場合のみ `.claude/adr/*.md` をキーワードで grep し、関連する設計判断を抽出する。ディレクトリが無ければ skip（未導入時は完全にスキップ・後方互換）

**関連が 1 件以上見つかった場合:**
- 種別ラベル付きでまとめて提示する（取捨選択できる形で）:
  ```
  過去の関連ナレッジが見つかりました（取捨選択できます）:
  - [knowledge] `knowledge/{topic}.md` — {概要}（tags: {tags}）
  - [完了Issue] `issues/{ID}.md` — {タイトル}
  - [ADR] `adr/{file}.md` — {タイトル}
  参照・引用しますか？
  ```
- ユーザーが選んだものを Read で内容表示し、Issue ファイルの「備考」セクションに種別ラベル付きで関連リンクを記載する
- 1 件も見つからなければ何も追記せず次 Phase へ進む（ノイズを出さない）

### Phase 2.7: writing-polish 連携（本文添削・必須）

生成した Issue 本文をユーザー提示（Phase 3 の承認）の直前に writing-polish へ渡して推敲する。`writing-polish` がインストールされていれば**必ず**実行する。未インストール時のみ skip（プラグイン独立性のため。後方互換）。

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
3. 返ってきた推敲済みテキスト（`POLISH_RESULT_START`〜`POLISH_RESULT_END` マーカー間のみ抽出。サマリ・変更点リストは本文に含めない）を本文の代わりに使う。ただし **9 セクション構造・frontmatter・Linear collapsible（`+++`）・Issue リンクは変更しない（構造を壊す結果は破棄し元案を使う）**。変更があれば何を変えたか一言添える。
4. fallback: 呼び出し失敗時は warning を出し、添削前の本文で完了する。

### Phase 3: Issue ファイル生成

1. **配置先の決定**
   - `.claude/linear/{slug}/issues/{ISSUE-ID}.md`
   - slug は Issue ID のプレフィックス（チーム識別子）を小文字化する（例: `TEAM-123` → `team`）

2. **frontmatter の記入**
   - `status: in-progress`
   - `linear: {ISSUE-ID}`
   - `type: {選択したtype}`
   - `created: {今日の日付}`
   - `last_active: {今日の日付}`
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
2. **feature-dev 連携確認**（feature type の場合のみ）: **AskUserQuestion** で確認する:
   - question: "feature-dev で実装計画を立てますか？（作業の流れを途切れさせずに次のフェーズに移れます）"
   - header: "feature-dev"
   - options:
     1. label: "はい" / description: "feature-dev で実装計画を立てる"
     2. label: "いいえ" / description: "後で自分でやる"

   **「はい」選択時の upfront 引き継ぎ**（Phase 2.5 の調査結果を feature-dev 側で再走査させないため、以下を必ず prompt に含めて呼び出す）:

   ```
   /feature-dev {ISSUE-ID}: {タイトル}

   ## Issue コンテキスト
   - Issue ファイル: `.claude/linear/{slug}/issues/{ISSUE-ID}.md`
   - type: {type}
   - Linear URL: {Linear の URL（get_issue から取得）}
   - 概要: {Linear description の要約}

   ## Phase 2.5 関連ナレッジ（knowledge / ADR / 完了 Issue）
   - {参照済み knowledge / ADR / 完了 Issue のファイル名と種別ラベル}

   ## 親 Issue（frontmatter の parent: に値がある場合）
   - [{PARENT-ID}] {タイトル} — 背景・計画のサマリー

   上記の context を前提に、実装計画を策定してください。
   ```

   feature-dev 実行後、`feature_dev_plan:` frontmatter に生成された計画ファイルのパスを記載することをユーザーに案内する（手動更新、または `/issue-maintain` で反映）。
3. 次のアクションを案内する:
   - 計画の記入（feature の場合）
   - 調査の開始（investigation の場合）
   - 修正の着手（bugfix の場合）
   - 対応方針の検討（debt の場合）

### Phase 5: spec 選択（着手前の仕様化ルーティング）

実装に入る前に「どの仕様 (spec) を先に書くか」を判定する。仕様系プラグイン（bdd-spec / design-doc / adr-keeper）が 1 つも入っていなければ完全に skip（dormant・後方互換 100%）。feature-dev に引き継ぐ場合（Phase 4 で「はい」）は WHAT/HOW を feature-dev が内部 Phase で生成するため、この Phase には実質到達しない（自分で実装する経路でのみ働く）。

1. **dormant 判定**（check-deps.sh / issue-design Phase 0.5 と同方式）:
   ```bash
   SPEC_BDD=0; SPEC_DD=0; SPEC_ADR=0
   grep -q '"bdd-spec@'   "$HOME/.claude/settings.json" 2>/dev/null && SPEC_BDD=1
   grep -q '"design-doc@' "$HOME/.claude/settings.json" 2>/dev/null && SPEC_DD=1
   grep -q '"adr-keeper@' "$HOME/.claude/settings.json" 2>/dev/null && SPEC_ADR=1
   ```
   - 3 つとも 0（いずれの spec プラグインも未導入）→ 本 Phase を skip

2. **自動推奨（判定表）**: type と Issue の性質から推奨を 1 つ決める。WHAT / HOW / WHY は排他ではない（大きめの feature は bdd-spec で WHAT を固めてから design-doc で HOW、のように併用してよい）。推奨が未導入の spec を指す場合（例: design-doc 推奨だが `SPEC_DD=0`）は導入済みの次点か「不要」にフォールバックする。

   共有 3 軸コア（正本: `.claude-plugin/lib/routing-axes.md`。spec-advisor / indie-workflow と同期・quality-check が検証。**編集時は正本と全消費サイトを同時更新**）:

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
