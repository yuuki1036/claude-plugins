# CLAUDE.md - claude-plugins

Claude Code プラグインのマーケットプレイスリポジトリ。

## リポジトリ構造

```
.claude-plugin/marketplace.json  # マーケットプレイスマニフェスト（plugin.json から派生）
.claude-plugin/lib/safe-hook.sh  # hook 共通ラッパー（正本）
.claude-plugin/schema/           # JSON Schema（plugin.json / marketplace.json / hooks.json）
.claude-plugin/scripts/          # validate-ssot.sh / validate_ssot.py（SSoT 同期検証）
.githooks/pre-commit             # バージョンバンプ・CHANGELOG・SSoT 同期チェック
{plugin-name}/                   # 各プラグイン（独立したディレクトリ）
  .claude-plugin/plugin.json     # プラグインマニフェスト
  commands/                      # スラッシュコマンド定義（YAML frontmatter + markdown）
  skills/                        # スキル定義（SKILL.md + references/）
  agents/                        # エージェント定義（frontmatter付き markdown）
  hooks/                         # フック定義（hooks.json + scripts/）
    lib/safe-hook.sh             # 正本の byte-identical 複製（hook 持ちプラグインのみ）
  rules/                         # SessionStart 等で注入されるルール（一部プラグインのみ）
    project-rules.md             # プロジェクト全体の作業ルール（SessionStart hook で注入）
  CHANGELOG.md                   # 変更履歴（Keep a Changelog 形式）
  README.md
```

> LICENSE ファイルは不要（各プラグインに個別のライセンスファイルを置かない）

## プラグイン一覧

| プラグイン | コマンド | スキル | agents | hooks | 説明 |
|-----------|---------|-------|--------|-------|------|
| code-review | 2 | 2 | - | SessionStart | Phase 0 トリアージ + 動的エージェント構成コードレビュー / セルフレビュー |
| dev-workflow | 3 | 5 | - | SessionStart, PreToolUse, PostToolUse | Git コミット・PR 作成・UI 動作確認の開発ワークフロー（chrome-devtools MCP 同梱。worktree-setup / worktree-teardown で並列開発環境の構築・破棄もサポート。pr-creator は PR 本文をユーザー提示前に writing-polish で必須推敲（インストール時）） |
| claude-meta | 2 | 5 | - | - | Claude Code 設定管理・CLAUDE.md 監査改善・CCアップデート追従・eval 回帰テスト・新コンポーネント追加前判断 |
| linear-workflow | 10 | 10 | 3 | SessionStart, PostCompact, UserPromptSubmit, FileChanged | Linear MCP 連携の Issue/プロジェクト管理（knowledge は source/concept 2層 + wikilink + lint。issue-design で 9 セクション設計 + open を grill で詰める。issue-create で着手前 spec 選択（WHAT/HOW/WHY を bdd-spec/design-doc/adr に dormant ルーティング）。issue/knowledge/follow-up 等の全散文成果物を確定前に writing-polish で必須推敲（インストール時）、code コメント・docs を含む広域ルールは project-rules.md に注入） |
| indie-workflow | 11 | 11 | 3 | SessionStart, PostCompact, UserPromptSubmit, FileChanged, PostToolUse | 個人開発向けローカル Issue 管理（linear-workflow と排他。knowledge は source/concept 2層 + wikilink + lint。issue-design で 9 セクション設計 + open を grill で詰める。indie-issue-create で着手前 spec 選択（WHAT/HOW/WHY を bdd-spec/design-doc/adr に dormant ルーティング）。indie-issue-discover で AI が多観点スキャン（バグ兆候・未実装・FE 改善・テスト欠落・既存シグナル）して課題を発見し issue を自動起票（起票上限・status:backlog・重複除外で暴走防止、起票は indie-issue-create 再利用。起票候補は Phase 4.5 で外部オラクル + 独立検証 agent discover-verifier により誤検知を起票前に落とす=fail-closed）。issue/knowledge/follow-up/retrospective 等の全散文成果物を確定前に writing-polish で必須推敲（インストール時）、code コメント・docs を含む広域ルールは project-rules.md に注入） |
| plugin-manager | 1 | - | - | SessionStart | インストール済みプラグインの一括更新 + ほぼ全部 install しているマーケットプレイスの後発追加取りこぼし通知 |
| plugin-feedback | 1 | 1 | - | SessionStart | プラグインへの改善要望・バグ報告を GitHub Issue 化 |
| feature-dev | 1 | - | 2 | SessionStart | 8 phase 機能開発ワークフロー（Phase 1.3 で bdd-spec から spec.md 生成 + Phase 1.4 で bdd-spec:evaluate-spec に品質ゲート委譲（dormant） + Phase 1.7 動的トリアージ + Phase 3 clarifying を grill 化（1問ずつ・推奨つき・コードで答えられる問いは自己解決）+ Phase 4.5 で採用設計を design-doc に export（dormant）+ Phase 6 G-V 自動 fix ループ + runtime smoke test 含む。code-explorer / code-architect 同梱。Phase 6 は code-review:self-review に委譲、code-review 未インストール時 fail-fast）。claude-plugins-official からフォーク |
| notebooklm-workflow | 2 | 2 | - | SessionStart | NotebookLM 連携ワークフロー（jacob-bd/notebooklm-mcp-cli を .mcp.json で同梱） |
| guardrail-protect | - | - | - | PreToolUse | git commit の hook 迂回（--no-verify/-n・git 省略形・-c core.hooksPath・変数間接・sh -c スクリプト内）を常時ブロック + lint/hook/static check 設定ファイルの骨抜き編集を opt-in でブロック（config 自己保護・fail-loud 付き） |
| doc-freshness | 1 | 1 | - | PostToolUse, SessionStart | last-validated / phase frontmatter による doc 鮮度機械強制。手動走査（command + skill）に加え、PostToolUse hook で frontmatter 必須の project doc（.claude/designs・.claude/adr）への frontmatter 欠落を非ブロッキング検知、SessionStart hook（opt-in）で stale を一括通知。プラグイン内部 doc（references/ 等）は対象外（version+CHANGELOG で鮮度管理） |
| bdd-spec | 2 | 2 | - | - | BDD spec 駆動の scaffold + 評価（user story dir + epic/spec 2ファイル + 階層化 + 同値分割表 + 状態遷移表（stateful のみ）を create で生成）。evaluate で構文/粒度/網羅性（同値分割表⇔Scenario 双方向トレース）/トレーサビリティ（epic AC⇔Scenario）/遷移カバレッジ（状態遷移表⇔Scenario、アプリのワークフローを FSM とみなし辺カバレッジで検証、stateful のみ dormant）の 5 観点を severity×confidence で静的レビュー。グラフは Scenario の「カバーする辺」注記から再構成し別管理しない（drift 回避）。機械判定（構文・リンク・表セル）をファネル第1段に置き意味判断を後段に回す。Generator(create) と Evaluator(evaluate) を責務分離。feature-dev Phase 1.4 に dormant 連携 |
| adr-keeper | 1 | 1 | - | - | 設計判断 (ADR) を append-only 蓄積。YYYYMMDDhhmmss 秒精度命名 + 適用方法セクション必須 + supersede 時の新規作成/旧 ADR 4フィールド更新（status/phase/superseded-by/last-validated）を機械化（append_only frontmatter で doc-freshness の stale 判定を免除し鮮度 lint を委譲） |
| failure-journal | 2 | 2 | - | SessionStart | 再発失敗の fingerprint 集計。JSON Lines journal に append、30日×3回閾値超で retro 還流提案、failure:logged を event bus に publish（indie-workflow:retrospective と責務分離） |
| writing-polish | 1 | 1 | - | - | 文章を語句レベルで推敲・添削する汎用スキル。最小差分 diff → 採否フロー、過剰修正(over-correction)抑制を中核原則化。校正ルール正本(tone-guide)に textlint 4 preset + Vale を統合、提示正本(presentation-guide)で確信度ラベル[確実]/[任意]/[要確認]・サマリ行・保全明示の採否 UX を規定（提示は軽く情報は厚く）、日英両対応。pr-creator/git-commit-helper/issue-design が --embed で soft 委譲（dormant 連携） |
| design-doc | 2 | 2 | 1 | - | 技術設計書 (design doc) を実装に入らず作成・永続化（grill で前提確定 → 代替案比較 → .claude/designs/ に保存。実装ブリッジ必須 + supersede 機械化で死に文書化を防ぐ。bdd-spec/adr-keeper/writing-polish と dormant 連携、doc-freshness に鮮度 lint を委譲。export 非対話 API で他プラグインから doc 化可能。design-review で 4 視点 agent の静的レビューを単体実行） |
| spec-advisor | 1 | 1 | - | SessionStart | 開発タスクの内容から適切な設計・計画系成果物（WHAT=bdd-spec / HOW=design-doc / WHY=adr-keeper / Issue粒度=issue-design / 実装一気通貫=feature-dev）を判断し実装着手前に提案（判定 SSoT を routing-rubric に一元化。SessionStart hook の ambient ルール注入＋spec-advise skill/command の明示起動の2経路。over-suggestion guard を先頭に置くファネルで軽微タスク（bugfix/typo/設定変更）には黙り、確信度が高い時のみ提案・迷う時のみ AskUserQuestion。dormant 判定で未導入プラグインは提案肢から除外、全連携先 optional でプラグイン独立。issue-create/feature-dev の既存 spec ルーティングとは別に raw chat のタスクを ambient に拾う） |

## セットアップ

```bash
# pre-commit hook を有効化（初回のみ）
git config core.hooksPath .githooks
```

## コマンド

```bash
# プラグインのインストール（ローカル）
claude plugin install /path/to/claude-plugins/{plugin-name}

# マーケットプレイスからインストール
claude plugin install {plugin-name}@yuuki1036-claude-plugins

# プラグインのリリースタグ作成（v2.1.118+）
# plugin.json の version と git tag を整合チェックして release tag を作成
claude plugin tag {plugin-name}

# 孤立した自動インストール依存の掃除（v2.1.121+）
claude plugin prune
```

## コミット規約

- Conventional Commits: `<type>(<scope>): <日本語description>`
- scope はプラグイン名（例: `feat(linear-workflow): ...`）
- 複数プラグインにまたがる場合は scope 省略

## プラグイン開発ルール

- 各プラグインは独立して動作すること（プラグイン間の依存禁止）
- プロジェクト固有の情報（社名、チーム名、実際の Issue ID 等）を含めない
- パス参照は `${CLAUDE_PLUGIN_ROOT}` を使用してポータブルにする
- スキルの description にはトリガーフレーズを `トリガー:` キーワードで含める（例: `トリガー: 「作業開始」「セッション開始」「/session-start」`）
- commands/ と skills/ の allowed-tools は一致させる（コマンドとスキルがペアになっている場合のみ。独立したコマンドやスキルには適用されない。別名ペア（`commit`↔`git-commit-helper` 等）は `validate_plugin_quality.py` の `COMMAND_SKILL_ALIASES` に登録して検証対象に含める — 新しい別名ペアを作ったら対応表への追加も必須）
- 後から変えにくい判断を伴う方針確認は `AskUserQuestion` で選択 UI を提示する（SKILL.md のワークフロー内に呼び出し仕様を直接記述する）
  - **例外（起動＝実行確定なスキル）**: ユーザーがコマンド起動した時点で実行意思が確定しているメンテナンス系スキル（maintain 系等）では、起動時の実行可否確認・モード選択や実行中の承認を `AskUserQuestion` で問い直さない。選択 UI で通常のチャット入力が奪われる UX コストを避けるため、止まらず最後まで実行し**結果は実行後レポートで報告**する。判断が要る検出（削除・status 遷移等）は AskUserQuestion で止めず**レポートに列挙してチャットで指示**を受ける。前提は「操作対象が git 管理下で復元可能」かつ「実行後に全件レポートで可視化される」こと。この前提を満たさない不可逆操作（外部送信・本番影響等）は従来どおり `AskUserQuestion` で確認する
- plugin 開発は plugin-dev plugin を用いて必要に応じて agent team を使用する
- 新 skill / agent / hook / command を追加する前は `claude-meta:component-addition-advisor` で退路確保（既存拡張で解けないか）を判定する
- **深掘り系スキルには `${CLAUDE_EFFORT}` 実行時分岐を必須とする**。深掘り系 = 走査・分析・レビュー・多段 agent など「かける深さで結果の質が変わる」スキル（maintain / discover / review / retrospective / design 系）。単純 CRUD・scaffold・単発記録系（init / follow-up / log-failure 等）には不要
- **linear-workflow / indie-workflow はミラー規約**: 共通機能（issue-create / issue-maintain / issue-design / follow-up / knowledge / knowledge-lint / maintain / session-start 系）は片方を変更したら必ず他方にも対称に反映する。**意図的な非対称**は次の 2 つのみ: `indie-issue-discover` と `retrospective`（いずれも「次に何をやるか・何を学んだか」を一人で回す個人開発特化の機能として indie のみに実装。linear 側への展開は必要が顕在化してから判断）。これ以外の片側だけの機能・改善は取り残しとみなす
- **プラグイン内部 doc（SKILL.md / references/ / README）には doc-freshness frontmatter を付けない**: これらの鮮度はバージョンバンプ + CHANGELOG + pre-commit hook で管理されており、`last-validated`（current=5 日閾値）を付けると恒常 stale 化して逆効果。doc-freshness の対象はプロジェクト側の doc（CLAUDE.md / `.claude/adr/` / `.claude/designs/` 等）

## ルール配置の意思決定（決定的 hook > LLM 判定）

新しいルール・制約を追加するときは、以下の優先順位で配置先を決める。決定的機械検証（lint/型/テスト/hook）は LLM 判定より ROI が高い（Thoughtworks Harness Engineering 参照）。Hook の遵守率 100% に対し CLAUDE.md は ~80% にとどまる前提で判断する。

### 意思決定フロー

```
ルールを追加したい
  │
  ▼
① 決定的検証で判定可能か？（文字列・ファイル存在・JSON スキーマ・exit code 等）
  ├─ YES → Hook（PreToolUse/PostToolUse/Stop 等）で強制する
  └─ NO  ↓
  ▼
② 文脈判断・自然言語理解が必要か？（コードレビュー・意図推定・要約等）
  ├─ YES → Skill（呼び出しタイミング明示）または Agent（自律実行）
  └─ NO  ↓
  ▼
③ 恒常的に参照したい規約・背景情報か？
  └─ CLAUDE.md（プロジェクト全体）or skill の references/（局所的）
```

### 配置先の判定表

| 特性 | Hook | Skill / Agent | CLAUDE.md |
|------|------|---------------|-----------|
| 遵守率 | 100%（決定的） | ~90%（呼び出せば確実） | ~80%（読み落としあり） |
| 自然言語判定 | 不可 | 可 | 可 |
| セッション外で強制 | 可 | 不可 | 不可 |
| 具体例・背景説明 | 不向き | 向く | 向く |
| 変更コスト | 中（スクリプト編集） | 中（SKILL.md 編集） | 低（文章修正） |
| 代表例 | バージョンバンプ忘れ検知 / 禁止コマンド遮断 | セルフレビュー / Issue 作成 | 命名規約 / 言語設定 |

### CLAUDE.md → Hook 昇格の判断基準

CLAUDE.md に書いたルールが守られていない事象が以下いずれかに該当したら、Hook 昇格を検討する。

- 同じ違反が 2 回以上発生している（履歴・コミットログから確認）
- 違反した場合の修復コストが高い（後から辿ると手戻りが大きい、データ損失、外部影響）
- 判定ロジックがルールベースで表現可能（if/grep/diff で書ける）

逆に、以下に該当する場合は CLAUDE.md / Skill に留める。

- 文脈依存で例外が多い（「基本は X、ただし Y のときは Z」）
- 違反してもリカバリが容易
- 判定に自然言語理解が必要

## コスト×精度パイプライン設計指針（多段 agent スキル/コマンド）

コスト（トークン・レイテンシ）と精度（偽陽性・偽陰性）を両立する多段 agent パイプラインを設計するときの共通指針。code-review / feature-dev / indie-issue-discover / failure-journal が独立に体現しているパターンを一般化したもの（元ネタ: Zenn「LLMエージェントのコスト×精度両立戦略：Clearwing に学ぶ設計原則」）。

新しい深掘り系スキル・コマンド・agent team を設計するときは、以下 10 原則のうち **どれを採用し・どれをあえて捨てたか** を SKILL.md に一言残す。全部入れる必要はない（対象規模に合わせる）。核心は「**弱いモデルの失敗モードをワークフローで囲い込む**」＝賢いモデル購買より先に「どこで絞り・どこで検証し・どこで止めるか」を設計すること。

| # | 原則 | 一言 | 正本 / 参考実装 |
|---|------|------|----------------|
| 1 | ファネル | 安価な絞り込み（diff/scope/grep/AST/トリアージ）を先頭に置き、高コスト検証は通過分にだけ適用 | `code-review/references/triage-guide.md` |
| 2 | 2 軸スコア化 | 結論には confidence(0-100) と severity を独立フィールドで付与し、報告閾値をマトリクスで決める | `code-review/references/scoring-guide.md` |
| 3 | 段階予算 | `${CLAUDE_EFFORT}` → (agent 数 / 反復回数 / 起票数) をマッピング。low は速度優先・high 以上で多重化 | `feature-dev/references/triage-guide.md` |
| 4 | モデルルーティング | 探索=弱モデル / 判断・検証・独立検証=強モデル / 統合・メタレビュー=別系統モデル（下表） | 本節の下表 |
| 5 | 暴走ガード | 予算上限・最大反復・同一 fingerprint 再試行抑制の三点セットを PoC 段階から装備 | `indie-workflow/skills/indie-issue-discover` |
| 6 | 証拠ラダー | 単発の指摘は蓄積し、閾値超で下流の高コスト処理や規約/hook に昇格させる | `failure-journal` |
| 7 | 敵対的独立検証 | 高リスク結論は別モデル・別コンテキストで反証。**発見者の推論を検証者に見せない**（迎合防止） | `code-review` 反証レイヤー |
| 8 | 外部オラクル + fail-closed | 型/テスト/コンパイル/実行の**機械判定**で客観検証し、LLM に投げる前に落とす。曖昧・エラー時は保守側（不可/保留）に倒す | — |
| 9 | 構造化受け渡し | agent 間は最小 JSON（識別子・file:line）のみ渡してコンテキスト膨張を防ぐ | Event Bus / Shared State 規約 |
| 10 | 確信度フィールド化 | 不確実な主張は「未検証」タグで明示し、フィルタで自動除外。断定で高 severity を作らない | `code-review/references/scoring-guide.md` |

### モデルルーティング規約（原則 4）

agent / サブタスクのロールに応じて既定モデルを出し分ける。「**後から変えにくい判断を伴う結論には強モデル、絞り込み探索には弱モデル**」が原則。自動プローブはせず人手のルーティング表でハードコードする。

| ロール | 既定モデル | 理由 |
|--------|-----------|------|
| 探索・収集・機械的サマリ（read-only fan-out。code-context / explorer 等） | `sonnet` | 事実収集は弱モデルで足り、体数を稼げる |
| 判断・検証・レビュー（load-bearing な結論。reviewer 等） | `opus` + effort 引き上げ | 誤判定コストが高い段は精度優先 |
| 敵対的独立検証（発見者と別コンテキストで反証。code-review 反証 / discover-verifier / design-review 反証） | `opus` | 検証は精度が命なので強モデル。独立性は「発見者の推論を渡さない」+ 別コンテキストで担保する（モデルを弱める必要はない） |
| 統合・メタレビュー・設計 blueprint（meta-reviewer / architect 等） | `fable` | 別系統モデルで相関を切り、判定の偏りを平す |

- agent frontmatter か skill 本文で **明示指定**する（親からの継承任せにしない。指定漏れは `validate_plugin_quality.py` の warning で拾えるようにするのが望ましい）。
- 1 呼び出し内は単一モデル。ステージ間での切り替えは可。

### 外部オラクル + fail-closed（原則 8）の勘所

「正解を機械判定できる手段」を 1 つ持つかがパイプライン精度の上限を決める。**LLM レビューの手前に安いオラクルを差し込む**のが最も費用対効果が高い。

- コード領域: 型チェック（`tsc --noEmit` 等）・テスト・lint・ビルド・実行結果。**変更範囲・対象ファイルに絞って**実行する（全ビルド/全テストは重い）。
- 検出できない・実行不能なら結果を破棄せず「疑いのまま保留（backlog / 人手送り）」に倒す（fail-closed）。誤 OK 判定コストが高いドメインほど効く。
- 検証プラグイン（code-review 等）が未インストールなら品質ゲートは skip せず **fail-fast**（feature-dev Phase 6 が採用）。

### あえて入れない（このリポジトリでの判断）

- **70/25/5 の予算配分＋繰越**: Claude Code は直列トークン予算でなく並列 agent＋体数上限モデル。effort→体数マッピングで十分。繰越は管理コストに見合わない。
- **finding schema の全面統一**: 共通化はコア 3 点（severity 語彙 / confidence 0-100 / evidence 必須）に留め、報告マトリクスは scoring-guide.md を soft 参照。ドメイン粒度を壊さない。
- **暴走ガード・モデルルーティングの hook 強制**: effort やループ回数は LLM の文脈判断で決まり決定的検証できない。意思決定フロー②に従い CLAUDE.md 規約止まりが正解。

## Event Bus 規約（Hook = Message Bus）

Claude Code の hook を **Pub/Sub Message Bus** として運用するための軽量規約。Classmethod「Claude Code マルチエージェントオーケストレーションパターン」記事の Message Bus パターンをローカル実装したもの。

### 永続化

- イベントログ: `.claude/events.jsonl`（プロジェクトローカル、gitignored、JSON Lines 形式）
- 1 行 = 1 イベント: `{"ts":"<ISO8601>","plugin":"<name>","event":"<name>","payload":<obj>}`

### API（`safe-hook.sh` に含まれる）

```bash
# 発行
event_bus_publish "<event-name>" '<json-payload>'

# 直近 N 件取得（オプションで event 名フィルタ）
event_bus_tail "<event-name>" 10
event_bus_tail "" 20  # 全イベント

# ログクリア（テスト用）
event_bus_clear
```

### イベント命名規約

`<domain>:<verb-past>` の snake_case。プラグインプレフィックスは **付けない**（subscriber が publisher を意識しない疎結合設計）。

| イベント | 発火タイミング | publisher | 主な subscriber |
|---|---|---|---|
| `issue:completed` | Issue ファイルの status が completed に遷移 | linear-workflow / indie-workflow | **indie-workflow:retrospective**（実装済） |
| `feature:implemented` | feature-dev Phase 7 完了 | **feature-dev**（実装済） | -（fire-and-forget） |
| `commit:created` | git commit 成功（PostToolUse Bash matcher で検知） | **dev-workflow**（実装済） | **linear-workflow / indie-workflow:issue-maintain**（実装済） |
| `review:completed` | code-review Step 7（レポート出力後） | **code-review**（実装済） | **linear-workflow / indie-workflow:issue-maintain**（実装済） |
| `failure:logged` | 再発しうる失敗を journal に記録 | **failure-journal**（実装済） | **indie-workflow:retrospective**（実装済） |

### Publisher の責務

- 自プラグインの hook 内で `event_bus_publish` を呼ぶ
- payload は最小限の JSON（issue_id / file path / 識別子のみ。本文は含めない）
- 副作用がある場合は payload に冪等性キーを含める

### Subscriber の責務

- `event_bus_tail` で読み出し、自前で dedup（ts + event 名 + payload のハッシュ等）
- イベントログのフォーマットが将来変わる可能性があるので JSON Lines パーサ前提で実装
- Hook 内での重い処理は禁止（必要なら別 skill / agent に委譲）

### デバッグ

```bash
# 直近 10 件
tail -n 10 .claude/events.jsonl

# 特定イベントを追う
grep '"event":"issue:completed"' .claude/events.jsonl | jq .
```

### 設計判断: なぜ JSON Lines + ファイル？

- Claude Code はローカル CLI なので EventBridge / Redis Pub/Sub は過剰
- 記事の「デバッグ困難」リスクは `tail` / `grep` でカバー
- セッション跨ぎで参照可能（git にコミットしないが project-local には残る）
- 全プラグインに既に配布されている `safe-hook.sh` に乗せられるので追加配布物なし

## Shared State 規約（cross-plugin な永続ファイル）

複数プラグインが読み書きする shared state ファイルに **producer / consumer を明示する frontmatter** を必須化する。Classmethod「Claude Code マルチエージェントオーケストレーションパターン」記事の Shared State パターンを軽量実装したもの。

> Event Bus（時系列イベント）と shared state（最新状態の永続）は使い分ける。シグナル通知は events.jsonl、現在値の参照は shared state frontmatter を読む。

### frontmatter フォーマット

shared state markdown の冒頭に YAML frontmatter を置く。各 type のドメイン固有フィールドは別途追加してよい（衝突しない限り）。

```yaml
---
shared_state_type: session | follow-up | knowledge | event-cache
producer: <plugin-name>           # 主な書き込み元
consumers: [<plugin>, ...]        # 読み出し側プラグイン
schema_version: 1                 # フィールド変更時に bump
last_updated: <ISO8601>           # 書き込み時に更新（producer が責任を持つ）
---
```

### type 一覧

| type | 配置 | producer | 主な consumers | 永続性 |
|---|---|---|---|---|
| `session` | `.claude/session-context.md` | linear-workflow / indie-workflow | code-review / feature-dev / dev-workflow | セッション単位（gitignored） |
| `follow-up` | `.claude/{linear\|indie}/{slug}/follow-ups/*.md` | linear-workflow / indie-workflow | dashboard / issue-maintain | 永続（committed） |
| `knowledge` | `.claude/{linear\|indie}/{slug}/knowledge/**/*.md` | linear-workflow / indie-workflow | knowledge / knowledge-lint / session-start (related mode) | 永続（committed）。knowledge は共通契約フィールドではなくドメイン固有 frontmatter（kind/status/verified/updated/tags）で代替し、consumer 側も契約フィールド（shared_state_type 等）を読まない |
| `event-cache` | （予約。events.jsonl の集計結果キャッシュ用） | - | - | - |

### Producer の責務

- 書き込み時に **必ず frontmatter を更新**する（`last_updated` の更新を含む）
- `schema_version` を変える場合は consumers 側の対応を確認してから bump する
- ファイル削除時は frontmatter を消すのではなく**ファイル自体を削除**する

### Consumer の責務

- frontmatter 不在のファイルも読める実装にする（**後方互換**: 既存ファイルが移行されるまで warning に留める）
- `shared_state_type` が想定外なら処理をスキップして warning 出力
- `last_updated` が極端に古い場合は stale 判定の判断材料に使ってよい

### 設計判断: なぜ frontmatter？なぜ flat な `.claude/shared/` に移行しない？

- 既存ファイルは **slug-scoped** な構造（`.claude/{workflow}/{slug}/knowledge/`）を持っており、flat 移行は 30+ 箇所のパス参照書き換えが必要でリスク高
- frontmatter 規約だけなら配置はそのままで producer/consumer を明示でき、移行コストが極小
- 必要性が顕在化したタイミング（例: cross-plugin で同名ファイル衝突が頻発したら）に flat 移行を再検討する

### Gotcha

- session-context.md は **gitignored** なので frontmatter 不在のまま動くケースがある。consumer は frontmatter 必須を前提にしない
- follow-up / knowledge は **committed** なので新規ファイルは frontmatter 付き必須。既存ファイルは移行されるまで knowledge-lint で warning

## CHANGELOG 規約

- 各プラグインに `CHANGELOG.md` を配置（Keep a Changelog 形式）
- バージョンバンプ時は CHANGELOG.md の更新必須（pre-commit hook で強制）
- Conventional Commits type との対応: `feat` → Added / `fix` → Fixed / `refactor` → Changed / `chore` → 原則省略

## Gotchas

- **marketplace.json の同期忘れ**: plugin.json の version/description を更新したら `.claude-plugin/marketplace.json` も必ず同期する。pre-commit の `validate-ssot.sh` がブロックする
- **hooks の stdin 消費**: hook スクリプトは必ず stdin を消費してから処理を開始する。消費しないとハングする。`safe-hook.sh` の `safe_hook_init` が自動で消費するため、全 hook は `source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"` 経由で書く
- **hooks の stdout**: hook スクリプトの stdout が Claude のコンテキストに注入される。条件付き注入は `safe_hook_error <category>` で silent exit 0（Validation/Dependency/Auth/NotFound はサイレント、Unexpected のみ stderr に通知）
- **safe-hook.sh の同期**: 正本は `.claude-plugin/lib/safe-hook.sh`。各プラグインの `hooks/lib/safe-hook.sh` は byte-identical な複製。`/quality-check` で同期を検証する（不一致は Critical）
- **バージョンバンプ忘れ**: プラグインの内容を変更したら必ず plugin.json の version を上げる。上げないと使用側で更新が検知されない。pre-commit hook でブロックされる
- **CHANGELOG 未更新**: バージョンバンプ時は CHANGELOG.md も更新必須。pre-commit hook でブロックされる
- **_requirements の同期忘れ**: プラグインの依存先が変わったら plugin.json の `_requirements` と `check-deps.sh` の両方を更新する。pre-commit の `validate-ssot.sh` が `check_xxx "<name>"` 形式の一致を検証する
- **hooks.json の args[] exec 形式 (CC 2.1.139+)**: 新規 hook は `command: "bash <path>"` ではなく `command: "bash", args: ["<path>"]` の exec 形式で書く。シェル解釈を経由せず直接 spawn するので安全＆高速。スキーマは `.claude-plugin/schema/hooks.schema.json` を参照
- **terminalSequence helpers (CC 2.1.141+)**: `safe-hook.sh` の `safe_hook_emit_bell` / `safe_hook_emit_window_title` は端末ベル / ウィンドウタイトルを JSON 出力で送る。`safe_hook_emit` (plain text) と**混在不可**（terminalSequence は単独 JSON 出力）。長時間処理の完了通知や警告アラートに opt-in で利用する
- **${CLAUDE_EFFORT} skill 適応分岐 (CC 2.1.120+)**: SKILL.md / コマンド本文に `${CLAUDE_EFFORT}` を書くと実行時 effort (low/medium/high/xhigh/max) が展開される。深掘り skill では `low/medium → 速度優先、xhigh/max → 多重 agent` のような条件分岐を入れる。frontmatter の `effort:` は宣言（既定値）、本文の `${CLAUDE_EFFORT}` は実行時値

## バージョニング規約

- MAJOR: 破壊的変更（スキル/コマンドの削除・リネーム）
- MINOR: 機能追加（新スキル/コマンド、既存機能拡張）
- PATCH: 修正（バグ修正、ドキュメント、リファクタ）

## 品質チェック

プラグインの新規作成・変更時は `/quality-check` で全プラグインの品質バリデーションを実行する。
個別のスキル開発時は plugin-dev の agent team（plugin-validator, skill-reviewer）を活用する。

**自動チェック（Stop hook）**: プラグイン関連ファイル（`*/plugin.json` / `*/skills/` / `*/commands/` / `*/hooks/` / `*/references/` / `marketplace.json` / `*/CHANGELOG.md`）を変更した状態でターン終了を迎えると、`.claude-plugin/scripts/auto-quality-check.sh` が以下を自動実行し、問題を stderr（ユーザー向け）と `hookSpecificOutput.additionalContext`（Claude 向け、CC 2.1.163）の両方に通知する（Stop はブロックしない）。`.claude/settings.json` で設定。

- `validate-ssot.sh`: スキーマ準拠 / marketplace 同期 / _requirements ↔ check-deps.sh / INDEX.md・CLAUDE.md 一覧の同期（INDEX の version 列・記載漏れ・余分行、CLAUDE.md の一覧表記載漏れ）
- `validate_plugin_quality.py`: allowed-tools 存在・command↔skill ペア一致 / hooks.json 参照スクリプトの safe_hook_init / safe-hook.sh 同期 / references 参照整合性 / トリガーフレーズ存在 / allowed-tools 最小性 #14b（SKILL.md・agents の未使用ツール検出、非ブロッキング warning。commands はペア一致ルールのため対象外）
- `claude plugin validate`: CLI スキーマ（`_requirements` 警告は除外）

LLM 判定が必要な項目（CLAUDE.md 品質、allowed-tools 最小性、プロジェクト固有情報検出等）は手動 `/quality-check` 側に残る。

スキルの description / トリガーフレーズを変更した場合は `evals/runner.py` で回帰テストを実行する（`claude-meta:eval-runner` スキル経由も可）。pass^k=3 基準でスキル選択の安定性を検証できる。ローカル実行のみ（CI 非対応、通常セッション枠を消費）。

## ブランチ運用

- main に直接コミット
