# CLAUDE.md - claude-plugins

Claude Code プラグインのマーケットプレイスリポジトリ。

## リポジトリ構造

```
.claude-plugin/marketplace.json  # マーケットプレイスマニフェスト（plugin.json から派生）
.claude-plugin/lib/safe-hook.sh  # hook 共通ラッパー（正本）
.claude-plugin/lib/routing-axes.md # spec ルーティング 3 軸コア（正本。ROUTING-AXES 区間を消費サイトに複製）
.claude-plugin/schema/           # JSON Schema（plugin.json / marketplace.json / hooks.json）
.claude-plugin/scripts/          # validate-ssot.sh / validate_ssot.py（SSoT 同期検証）
                                 # validate_plugin_quality.py（品質検証。検査項目の正本は冒頭 docstring）
                                 # auto-quality-check.sh（Stop hook から上記 2 本 + CLI validate を自動実行）
                                 # bump-version.sh（バージョンバンプの 4 ファイル同時更新 + vNEXT 解決。
                                 #   pre-commit は検証のみで実行しない）
                                 # mutation-test.py（変更行の変異テスト。検証していない挙動を列挙）
.claude-plugin/scripts/tests/    # 回帰テスト（stdlib unittest・依存なし）。3 系統:
                                 #  ① 検証スクリプト自身（test_validate_plugin_quality.py / test_mutation_test.py）
                                 #  ② プラグイン同梱スクリプトを CLI 境界越しに叩く subprocess テスト
                                 #     （`test_<plugin>_*.py`。bats を入れず依存ゼロで 3 経路に載せる）
                                 #  ③ repo 直下スクリプトの CLI テスト（test_bump_version.py。
                                 #     使い捨ての git リポジトリを立てて本物の CLI を叩く）
                                 # python3 -m unittest discover -s .claude-plugin/scripts/tests
.githooks/pre-commit             # バージョンバンプ・CHANGELOG・SSoT 同期・プラグイン品質 (errors)・回帰テスト
.github/workflows/validate.yml   # CI。push / PR で SSoT・品質・回帰テスト・バージョンバンプを検証（evals は非対応）
.claude/                         # リポジトリローカル設定（プラグインではない。git 追跡下）
  settings.json                  # Stop hook（auto-quality-check.sh）等の設定
  commands/ skills/              # /quality-check の実体（マーケットプレイスに配布しない自前コマンド）
  adr/ designs/                  # 本リポジトリ自身の設計判断・設計書
docs/                            # 横断設計指針（pipeline-design / rule-placement / skill-writing / event-bus /
                                 # shared-state / issue-workflow-migration + session-reports/）
evals/                           # スキル起動回帰テスト（runner.py + cases/*.yaml。README に Gotchas）
INDEX.md                         # プラグイン詳細一覧（CLAUDE.md の表と同期検証される）
{plugin-name}/                   # 各プラグイン（独立したディレクトリ）
  .claude-plugin/plugin.json     # プラグインマニフェスト
  .mcp.json                      # 同梱 MCP サーバー定義（dev-workflow / notebooklm-workflow のみ）
  commands/                      # スラッシュコマンド定義（YAML frontmatter + markdown）
  skills/                        # スキル定義（SKILL.md + references/）
  agents/                        # エージェント定義（frontmatter付き markdown）
  references/                    # プラグイン共通の参照ドキュメント（skills/ 配下とは別。一部プラグインのみ）
    prompts/                     # agent プロンプト本体（1 観点 1 ファイル）。オーケストレーターは
                                 # Read せずパスだけ渡し、agent 自身に読ませる（本文をプロンプトへ
                                 # 転記すると同一テキストを起動体数ぶん書き出すことになる）
    design-notes/                # 設計の「なぜ」（実測値・失敗の履歴・却下した代替案・未実装案）。
                                 # **実行時には読まない** — 規範は各ガイド本体に置き、根拠はここへ分ける
  scripts/                       # 同梱スクリプト（一部プラグインのみ）。SKILL 本文に bash を書き下ろさず
                                 # ここへ寄せる。lib/ に共通処理を置いてよい（複製を作らない）
  hooks/                         # フック定義（hooks.json + scripts/）
    lib/safe-hook.sh             # 正本の byte-identical 複製（hook 持ちプラグインのみ）
  rules/                         # SessionStart 等で注入されるルール（一部プラグインのみ）
    project-rules.md             # プロジェクト全体の作業ルール（SessionStart hook で注入）
                                 # 別名もある: self-report-rule.md / advisor-rule.md
  CHANGELOG.md                   # 変更履歴（Keep a Changelog 形式）
  README.md
```

> LICENSE ファイルは不要（各プラグインに個別のライセンスファイルを置かない）

## プラグイン一覧

各プラグインの説明は 1 行要約のみ（このファイルは毎セッション常駐するため）。機能内訳・設計判断の詳細は INDEX.md・各プラグインの README / SKILL.md・`.claude/designs/` を参照。

| プラグイン | コマンド | スキル | agents | hooks | 説明 |
|-----------|---------|-------|--------|-------|------|
| code-review | 2 | 2 | - | SessionStart | Phase 0 トリアージ + 動的エージェント構成のコードレビュー / セルフレビュー |
| dev-workflow | 4 | 6 | - | SessionStart, PreToolUse, PostToolUse | Git コミット・PR 作成・UI 動作確認・バグ診断・worktree 並列開発（chrome-devtools MCP 同梱） |
| claude-meta | 2 | 5 | - | - | Claude Code 設定管理・CLAUDE.md 監査・CC アップデート追従・eval 回帰テスト・コンポーネント追加前判断 |
| linear-workflow | 10 | 10 | 3 | SessionStart, PostCompact, UserPromptSubmit, FileChanged | **deprecated** → issue-workflow へ移行（全マシン移行後に削除） |
| indie-workflow | 11 | 11 | 3 | SessionStart, PostCompact, UserPromptSubmit, FileChanged, PostToolUse | **deprecated** → issue-workflow へ移行（全マシン移行後に削除） |
| issue-workflow | 13 | 13 | 4 | SessionStart, PostCompact, UserPromptSubmit, FileChanged, PostToolUse | Issue 管理（linear/indie 統合後継。backend 自動判定・移行中） |
| plugin-manager | 1 | - | - | SessionStart | インストール済みプラグインの一括更新 + deprecated の自動移行（_superseded_by）+ 後発追加通知 |
| plugin-feedback | 1 | 1 | - | SessionStart | プラグインへの改善要望・バグ報告を GitHub Issue 化 |
| feature-dev | 1 | - | 2 | SessionStart | 8 phase 機能開発ワークフロー（spec 品質ゲート・G-V fix ループ・self-review 委譲） |
| notebooklm-workflow | 2 | 2 | - | SessionStart | NotebookLM 連携ワークフロー（notebooklm-mcp-cli を .mcp.json で同梱） |
| guardrail-protect | - | - | - | PreToolUse | git commit の hook 迂回と lint/hook 設定ファイルの骨抜き編集をブロック |
| doc-freshness | 1 | 1 | - | PostToolUse, SessionStart | frontmatter による project doc の鮮度機械強制（走査 + hook 検知 + stale 通知） |
| bdd-spec | 2 | 2 | - | - | BDD spec の scaffold（create）と 5 観点静的レビュー（evaluate）の責務分離ペア |
| adr-keeper | 1 | 1 | - | - | 設計判断 (ADR) の append-only 蓄積と supersede 機械化 |
| failure-journal | 2 | 2 | - | SessionStart, PostCompact | 再発失敗の fingerprint 集計と閾値超えの規約還流提案（自己訂正の candidates 自己申告つき） |
| writing-polish | 1 | 1 | - | - | 文章の語句レベル推敲（最小差分 diff → 採否、過剰修正抑制、日英対応） |
| design-doc | 2 | 2 | 1 | - | 技術設計書の作成・永続化・supersede・多視点レビュー（実装ブリッジ必須） |
| spec-advisor | 1 | 1 | - | SessionStart | タスク内容から設計系成果物（WHAT/HOW/WHY）を判断して実装前に提案 |
| living-spec-workflow | 2 | 2 | - | - | Issue 化前の設計収束ドキュメント (living spec) の作成・運用と 8 段ファネル検証 |

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

# バージョンバンプ（plugin.json / marketplace.json / INDEX.md / CHANGELOG.md を同時更新）
# CHANGELOG のエントリを書いてから --sync するのが主経路（CHANGELOG が版の正本）
bash .claude-plugin/scripts/bump-version.sh {plugin-name} --sync
bash .claude-plugin/scripts/bump-version.sh {plugin-name} patch   # 次版を計算して見出しだけ挿入
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
- スキルの description・SKILL.md 本文を新規作成・大きく改稿するときは `docs/skill-writing.md` を読む（description の branch 設計・情報階層 / progressive disclosure・leading words・no-op 剪定・失敗モードカタログ）
- commands/ と skills/ の allowed-tools は一致させる（コマンドとスキルがペアになっている場合のみ。独立したコマンドやスキルには適用されない。別名ペア（`commit`↔`git-commit-helper` 等）は `validate_plugin_quality.py` の `COMMAND_SKILL_ALIASES` に登録して検証対象に含める — 新しい別名ペアを作ったら対応表への追加も必須）
- 後から変えにくい判断を伴う方針確認は `AskUserQuestion` で選択 UI を提示する（SKILL.md のワークフロー内に呼び出し仕様を直接記述する）
  - **例外（起動＝実行確定なスキル）**: ユーザーがコマンド起動した時点で実行意思が確定しているメンテナンス系スキル（maintain 系等）では、起動時の実行可否確認・モード選択や実行中の承認を `AskUserQuestion` で問い直さない。選択 UI で通常のチャット入力が奪われる UX コストを避けるため、止まらず最後まで実行し**結果は実行後レポートで報告**する。判断が要る検出（削除・status 遷移等）は AskUserQuestion で止めず**レポートに列挙してチャットで指示**を受ける。前提は「操作対象が git 管理下で復元可能」かつ「実行後に全件レポートで可視化される」こと。この前提を満たさない不可逆操作（外部送信・本番影響等）は従来どおり `AskUserQuestion` で確認する
- 新 skill / agent / hook / command を追加する前は `claude-meta:component-addition-advisor` で退路確保（既存拡張で解けないか）を判定する
- **深掘り系スキルには `${CLAUDE_EFFORT}` 実行時分岐を必須とする**。深掘り系 = 走査・分析・レビュー・多段 agent など「かける深さで結果の質が変わる」スキル（maintain / discover / review / retrospective / design 系）。単純 CRUD・scaffold・単発記録系（init / follow-up / log-failure 等）には不要
- **issue-workflow の backend 分岐規約**: 旧 linear-workflow / indie-workflow のミラー規約は廃止した（ADR-20260722164106）。共通機能は issue-workflow 内の backend 分岐（`BACKEND=local|linear` / `{DATA_DIR}` 変数化 / 「BACKEND=linear のときのみ」の条件付き Phase）で表現する。backend 判定述語は「データ dir が存在し、かつ slug サブディレクトリを 1 つ以上持つ」で SKILL（Phase 0）と hook（`hooks/lib/detect-backend.sh`）を統一する。プラグイン間依存禁止の制約下で複製が発生したら、それは分割単位の誤りを示すシグナルとして扱う
- **プラグイン内部 doc（SKILL.md / references/ / README）には doc-freshness frontmatter を付けない**: これらの鮮度はバージョンバンプ + CHANGELOG + pre-commit hook で管理されており、`last-validated`（current 閾値）を付けると恒常 stale 化して逆効果。doc-freshness の対象はプロジェクト側の doc（CLAUDE.md / `.claude/adr/` / `.claude/designs/` 等）

## ルール配置の意思決定（決定的 hook > LLM 判定）

新しいルール・制約を追加するときは **Hook（決定的検証可能）> Skill/Agent（文脈判断）> CLAUDE.md（恒常参照の規約）** の優先順位で配置先を決める。遵守率は Hook 100% / Skill ~90% / CLAUDE.md ~80%。CLAUDE.md のルールが 2 回以上破られた・修復コストが高い・if/grep/diff で判定できる、のいずれかに該当したら Hook 昇格を検討する。判定フロー・判定表・昇格基準の詳細は `docs/rule-placement.md` を読むこと。

## コスト×精度パイプライン設計指針（多段 agent スキル/コマンド）

**新しい深掘り系スキル・コマンド・agent team を設計するときは、着手前に `docs/pipeline-design.md` を読むこと。** 10 原則（ファネル / 2軸スコア / 段階予算 / モデルルーティング / 暴走ガード / 証拠ラダー / 敵対的独立検証 / 外部オラクル / 構造化受け渡し / 確信度フィールド化）のどれを採用しどれを捨てたかを SKILL.md に一言残す。常時適用する要点のみ以下に残す:

- **モデルルーティング**: 探索・収集は `sonnet`、判断・検証・統合は `opus`。agent frontmatter か skill 本文で明示指定する（継承任せにしない)。エイリアスは最新世代（現行: Opus 5 / Sonnet 5）に自動解決されるため**モデル指定**に具体 ID をピン留めしない（世代同定が目的の値 — cc-catch-up の `lastCatchUpModel`・evals の `--models` — は除く）
- **`fable` は使用しない**（プロジェクト方針）。独立性は「別コンテキスト起動 + 発見者の推論を渡さない」で担保する
- **Opus 5 世代で逆効果になる足場を書かない**（新規設計・既存 rules/skills 本文の両方に適用）: ①「積極的に委譲せよ」（委譲過剰を招く。体数上限を明示する）②「自分でダブルチェックせよ」（over-verification。検証は独立エージェント層に）③「重要な指摘だけ報告せよ」（recall 低下。全報告→下流フィルタに）。適用除外（根拠強制の手順・スコープ定義は残してよい）を含む詳細は `docs/pipeline-design.md` の Opus 5 節

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
| `issue:completed` | Issue ファイルの status が completed に遷移 | issue-workflow（移行中は旧 linear/indie-workflow も） | **issue-workflow:retrospective**（実装済） |
| `feature:implemented` | feature-dev Phase 7 完了 | **feature-dev**（実装済） | -（fire-and-forget） |
| `commit:created` | git commit 成功（PostToolUse Bash matcher で検知） | **dev-workflow**（実装済） | **issue-workflow:issue-maintain**（実装済） |
| `review:completed` | code-review Step 7（レポート出力後） | **code-review**（実装済） | **issue-workflow:issue-maintain**（実装済） |
| `failure:logged` | 再発しうる失敗を journal に記録 | **failure-journal**（実装済） | **issue-workflow:retrospective**（実装済） |

### Publisher / Subscriber の責務（要点）

- Publisher: payload は最小限の JSON（識別子のみ、本文を含めない）。副作用がある場合は冪等性キーを含める
- Subscriber: `event_bus_tail` で読み出し自前で dedup。Hook 内での重い処理は禁止（別 skill / agent に委譲）
- publish / subscribe を実装・変更するときは `docs/event-bus.md`（責務の詳細・デバッグ手順・設計判断）を読むこと

## Shared State 規約（cross-plugin な永続ファイル）

複数プラグインが読み書きする shared state ファイル（session-context / follow-up / knowledge）には **producer / consumer を明示する frontmatter** を必須化する（`shared_state_type` / `producer` / `consumers` / `schema_version` / `last_updated`）。Event Bus（時系列イベント通知）と shared state（現在値の参照）は使い分ける。**shared state ファイルを新設・変更するときは `docs/shared-state.md` を読むこと**（frontmatter フォーマット・type 一覧・producer/consumer の責務・後方互換ルール）。

## CHANGELOG 規約

- 各プラグインに `CHANGELOG.md` を配置（Keep a Changelog 形式）。バージョンバンプとの同時更新が必須な点は Gotchas「バージョンバンプ忘れ」を参照
- Conventional Commits type との対応: `feat` → Added / `fix` → Fixed / `refactor` → Changed / `chore` → 原則省略

## Gotchas

- **marketplace.json の同期忘れ**: plugin.json の version/description を更新したら `.claude-plugin/marketplace.json` も必ず同期する。pre-commit の `validate-ssot.sh` がブロックする
- **hooks の stdin 消費**: hook スクリプトは必ず stdin を消費してから処理を開始する。消費しないとハングする。`safe-hook.sh` の `safe_hook_init` が自動で消費するため、全 hook は `source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"` 経由で書く
- **hooks の stdout**: hook スクリプトの stdout が Claude のコンテキストに注入される。条件付き注入は `safe_hook_error <category>` で silent exit 0（Validation/Dependency/Auth/NotFound はサイレント、Unexpected のみ stderr に通知）
- **safe-hook.sh の同期**: 正本は `.claude-plugin/lib/safe-hook.sh`。各プラグインの `hooks/lib/safe-hook.sh` は byte-identical な複製。`/quality-check` で同期を検証する（不一致は Critical）
- **routing-axes の同期**: spec ルーティングの 3 軸コア（WHAT→bdd-spec / HOW→design-doc / WHY→adr-keeper）の正本は `.claude-plugin/lib/routing-axes.md`。`ROUTING-AXES:START/END` マーカー区間が spec-advisor routing-rubric / issue-workflow の issue-create に複製されており、`validate_plugin_quality.py` が dedent 比較で同期を検証する（不一致は Critical）。区間を編集するときは正本と全消費サイトを同時更新する。区間外の type 別判定・拡張軸は各サイトの文脈特化で同期対象外（設計判断: `.claude/designs/20260708-spec-routing-ssot.md`）
- **正本 → 消費サイトの伝播漏れ（SSoT pin）**: doc が実行手順そのものになるプラグインでは consumer が別の doc なので、正本を直しても伝播漏れが見えにくい（code-review v2.63.0 のセルフレビューで検出した欠陥 11 件中 6 件がこの型）。**言い換え・要約で複製されている関係**は、消費サイトの冒頭に `<!-- SSOT: <repo ルート相対の md パス>#<見出し前方一致 anchor> @<hash8> -->` を置いて宣言する。`validate_plugin_quality.py` の `check_ssot_pins` が正本の該当節をハッシュして突合し、ずれていれば Critical。**要求するのは内容の一致ではなく「正本が変わったら消費サイトを確認して pin を打ち直す」手順**（routing-axes 同期は「同一テキストであること自体が仕様」の関係を扱う別の仕組みで、両者は併存する）。打ち直しは `python3 .claude-plugin/scripts/validate_plugin_quality.py --update-ssot-pins`（**明示操作**。pre-commit では自動更新しない — 自動化すると確認の強制力が消える。**repo 全体の pin を一括で打ち直す**ので、全消費サイトを確認してから使う）。**新規 pin の打ち方**: hash を手計算せず `@00000000` のダミーで宣言し、`--update-ssot-pins` で確定させる（初期値も検証も同じ切り出しを通るのでこれが正規経路）。**hash は 8 桁の小文字 hex**で、外すと `pin 記法が不正で検証されない` の Critical になる（黙って無効化はしない）。**pin 宣言はファイル冒頭＝最初の見出しより前に置く**（pin した節の中に pin があると打ち直しが収束せず、これも Critical）。**doc に記法例を書くときはフェンスか行内コードに入れる**（生きた pin として拾われない）。**正本・消費サイトとも md のみ対応**（スクリプトを正本にはできず、非 md に pin を書いても警告なく無効化される）。**節の区切りは見出しレベルで決まるので `#8` は同レベルの `## 8.5` を含まない**（別 pin を打つ。anchor `8` は `## 8.5` に吸着せず、一致が 2 件以上なら曖昧として Critical）。現在の適用範囲は code-review のみ。設計判断: `.claude/adr/20260813223000-ssot-pin-over-marker-sync.md`
- **バージョンバンプ忘れ**: プラグインの内容を変更したら必ず plugin.json の version を上げ、CHANGELOG.md も同時更新する。上げないと使用側で更新が検知されない。どちらも pre-commit hook でブロックされる
- **_requirements の同期忘れ**: プラグインの依存先が変わったら plugin.json の `_requirements` と `check-deps.sh` の両方を更新する。pre-commit の `validate-ssot.sh` が `check_xxx "<name>"` 形式の一致を検証する
- **hooks.json の if:/matcher に単独依存しない（注入・block 系 hook の自己判定必須）**: `if: "Bash(git push *)"`（CC 2.1.85+）や matcher のフィルタは**実行環境によって評価されない**ことが実測済み（2026-07: dev-workflow push-reminder が全 Bash 呼び出しで additionalContext を注入する暴発。配布・スキーマ・構文は正しかった）。PreToolUse/PostToolUse の hook スクリプトは `INPUT=$(safe_hook_input)` で tool_input を取得し発火条件を自己判定する二重ゲートにする（手本: `dev-workflow/hooks/scripts/on-commit.sh`）。`validate_plugin_quality.py` の hook-self-judge チェックが `safe_hook_input` 非参照を非ブロッキング warning で検知する。FileChanged の path-glob matcher も同型リスクだが tool_input が無いためチェック対象外（既知の残リスク）
- **hooks.json の args[] exec 形式 (CC 2.1.139+)**: 新規 hook は `command: "bash <path>"` ではなく `command: "bash", args: ["<path>"]` の exec 形式で書く。シェル解釈を経由せず直接 spawn するので安全＆高速。スキーマは `.claude-plugin/schema/hooks.schema.json` を参照
- **terminalSequence helpers (CC 2.1.141+)**: `safe-hook.sh` の `safe_hook_emit_bell` / `safe_hook_emit_window_title` は端末ベル / ウィンドウタイトルを JSON 出力で送る。`safe_hook_emit` (plain text) と**混在不可**（terminalSequence は単独 JSON 出力）。長時間処理の完了通知や警告アラートに opt-in で利用する
- **${CLAUDE_EFFORT} skill 適応分岐 (CC 2.1.120+)**: SKILL.md / コマンド本文に `${CLAUDE_EFFORT}` を書くと実行時 effort (low/medium/high/xhigh/max) が展開される。深掘り skill では `low/medium → 速度優先、xhigh/max → 多重 agent` のような条件分岐を入れる。frontmatter の `effort:` は宣言（既定値）、本文の `${CLAUDE_EFFORT}` は実行時値
- **Agent tool の background 既定 (CC 2.1.198+)**: fanout して結果を待つスキル（explorer/reviewer/verifier 等）では **①各 Agent call に `run_in_background: false` を明示**（省略＝background 起動で結果を取りこぼす）し、**②全 Agent call を同一メッセージ内で一括発行**する（1 体ずつ別メッセージだと実時間が体数分の合計になる）。**①は取りこぼし防止・②は並列性で、直交する独立の要件**（①だけでは並列にならない）。根拠と実測は `orchestration-guide.md ## 0`（正本・issue #95）。取り漏れは `validate_plugin_quality.py` の agent-sync チェックが非ブロッキング warning で検知する
- **eval を実行・修正する前に `evals/README.md` の Gotchas を読む**: スラッシュコマンドは headless で必ず落ちる（自然言語プロンプトで測る）/ fail は「プラグイン選択」と「skill id の綴り」を分けて読む（id 捏造は harness 側の性質）/ 判定は k=1 でなく pass^k=3 で行う — 詳細と実例は README 側に集約

- **版ラベルは `vNEXT` と書く**（プラグイン配下の md / sh / py）。`bump-version.sh` が bump 時に実版へ置換し、`validate_plugin_quality.py` が「bump 済みなのに `vNEXT` が残っている」を error にする。**具体的な版番号を手書きしない** — 書く時点では正しい値が確定しておらず（bump は後）、実測で 3 回再発した。検出側の機械化は 2 度失敗している（履歴参照と区別できない / Claude Code の版と表記が衝突する）ので、**確定していない値を書かせない**方で解いた。repo 直下の共通スクリプト・doc は**プラグイン版に属さない**ので版ラベルを持たせず issue 番号で参照する。**規約そのものを説明するときは行内コードかフェンスに入れる**（SSoT pin と同じ扱い — 生きたプレースホルダとして置換・検出の対象にならない。実測でこの説明文ごと実版に書き換えた）。経緯: `code-review/references/design-notes/pending-optimizations.md ## 9`
- **新しい lint / 検証ロジックを足すときは ①既存 repo での検出数を先に測って error / warning の水準を決める ②変異テストで「実装を壊すと該当テストが落ちる」ことを確認する**: 初回実行で偽陽性が出る warning は「⚠️ が出たときだけ行動する」契約を壊すので、入れない方がまし（実例: 版ラベルの追随漏れ検出は 6/6 が偽陽性で撤去した → `code-review/references/design-notes/pending-optimizations.md ## 9`）。変異テストは **`python3 .claude-plugin/scripts/mutation-test.py`** で自動化してある（変更行だけを対象に比較演算子・境界・真偽値・打ち切りを機械的に反転し、テストが落ちない＝**検証していない挙動**を列挙する）。`__pycache__` の消去・元バイト列での復元・**モードの保存**・並行編集の検知は**ツール側に入っている**（どれも手動でやって事故った）。**実行中に対象ファイルを編集しないこと**。中断されても変異が残らないよう原本は `.mutation-test-journal.json` に退避され、次回起動時に自動で戻る（所有者 pid と `MUTATION_TEST_OWNER_PID` で、実行中の run の変異は横取りしない）
- **同梱スクリプトのテストは `.claude-plugin/scripts/tests/` に置く**（プラグイン配下に置かない — 配布物にテストが混ざる）。ハーネスは python の subprocess で、bats 等の外部依存を足さない。判断の経緯: `code-review/CHANGELOG.md` v2.68.0

## バージョニング規約

- MAJOR: 破壊的変更（スキル/コマンドの削除・リネーム）
- MINOR: 機能追加（新スキル/コマンド、既存機能拡張）
- PATCH: 修正（バグ修正、ドキュメント、リファクタ）
- **版ラベルは `vNEXT` で書く**: doc / コメントに「この挙動は vNEXT で入った」と書くと `bump-version.sh` がそのプラグイン配下だけを実版へ解決する（書く時点では版が確定しない構造的な race を消すため）。行内コード・フェンス内の `vNEXT` は規約の説明とみなして置換しない。**repo 直下の共通スクリプト（`.claude-plugin/scripts/` 等）はどのプラグイン版にも属さないので版ラベルを書かない** — issue 番号か設計ノートへのパスで参照する
- **判定は「変更ファイルの種類」で行う**: commit type が `docs` で変更が `*.md` + version/CHANGELOG のみなら PATCH。MINOR を当てると `plugin-manager:update-all` の利用者に「機能追加が入った」と誤ったシグナルを送る（pre-commit は bump の有無しか見ないので機械的には素通りする）

## 品質チェック

プラグインの新規作成・変更時は `/quality-check` で全プラグインの品質バリデーションを実行する。
個別のスキル開発時は `docs/skill-writing.md` の観点（description の branch 設計・情報階層・no-op 剪定・失敗モードカタログ）で自己点検し、description / トリガーフレーズを変えたら evals で回帰を確認する。

**自動チェック（Stop hook）**: プラグイン関連ファイル（`*/plugin.json` / `*/skills/` / `*/commands/` / `*/hooks/` / `*/agents/` / `*/references/` / `*/scripts/` / `marketplace.json` / `*/CHANGELOG.md`）を変更した状態でターン終了を迎えると、`.claude-plugin/scripts/auto-quality-check.sh` が以下を自動実行し、問題を stderr（ユーザー向け）と `hookSpecificOutput.additionalContext`（Claude 向け、CC 2.1.163）の両方に通知する（Stop はブロックしない）。`.claude/settings.json` で設定。

- `validate-ssot.sh`: スキーマ準拠 / marketplace 同期 / _requirements ↔ check-deps.sh / INDEX.md・CLAUDE.md 一覧の同期
- `validate_plugin_quality.py`: allowed-tools / safe-hook.sh 同期 / references 参照整合性 / トリガーフレーズ / Event Bus 同期 / hook 自己判定 / コンテキスト予算ほか — **検査項目の正本はスクリプト冒頭 docstring**（ここに列挙を複製しない）
- `claude plugin validate`: CLI スキーマ（`_requirements` 警告は除外）
- `python3 -m unittest discover -s .claude-plugin/scripts/tests`: 回帰テスト（検証スクリプト自身 + プラグイン同梱スクリプトの CLI テスト）。**検証機構の期待値をその機構自身で生成すると、壊れていても全件 pass する**（SSoT pin の初期ハッシュを未テストの `_slice_section` で作り、節の 46% が無保護なまま 14 pin 全部が ok に見えた実例が v2.63.1）。**期待値をテスト側で独立に構築すること**（`test_digest_matches_independently_computed_expectation`）。検証ロジックを足すときは同じ原則でテストを添える

LLM 判定が必要な項目（CLAUDE.md 品質、allowed-tools 最小性、プロジェクト固有情報検出等）は手動 `/quality-check` 側に残る。

スキルの description / トリガーフレーズを変更した場合は `evals/runner.py` で回帰テストを実行する（`claude-meta:eval-runner` スキル経由も可）。pass^k=3 基準でスキル選択の安定性を検証できる。**evals だけはローカル実行のみ**（`.github/workflows/validate.yml` は SSoT・品質・回帰テスト・バージョンバンプを検証するが evals は回さない。通常セッション枠を消費するため）。

## ブランチ運用

- main に直接コミット
