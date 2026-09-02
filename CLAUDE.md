# CLAUDE.md - claude-plugins

Claude Code プラグインのマーケットプレイスリポジトリ。

## リポジトリ構造

```
.claude-plugin/marketplace.json  # マーケットプレイスマニフェスト（plugin.json から派生）
.claude-plugin/lib/safe-hook.sh  # hook 共通ラッパー（正本）
.claude-plugin/lib/routing-axes.md # spec ルーティング 3 軸コア（正本。ROUTING-AXES 区間を消費サイトに複製）
.claude-plugin/lib/comment-rule.md  # コードコメント規約 2 観点（正本。COMMENT-RULE 区間を消費サイトに複製）
.claude-plugin/schema/           # JSON Schema（plugin.json / marketplace.json / hooks.json）
.claude-plugin/scripts/          # validate-ssot.sh / validate_ssot.py（SSoT 同期検証）
                                 # validate_plugin_quality.py（品質検証。検査項目の正本は冒頭 docstring）
                                 # machine-layer.sh（検査の並びの正本。exit 0 緑 / 1 検出 / 2 判定不能。
                                 #   Stop hook・self-review 前段の両方がこれを呼ぶ）
                                 # auto-quality-check.sh（Stop hook。いつ走らせるかと hook 向け出力だけを持つ）
                                 # bump-version.sh（バージョンバンプの 4 ファイル同時更新 + vNEXT 解決。
                                 #   pre-commit は検証のみで実行しない）
                                 # mutation-test.py（変更行の変異テスト。検証していない挙動を列挙）
                                 # run-tests.py（回帰テストの起動口。新セッションで走らせ、
                                 #   終了後に残ったプロセスを検出・回収する。pre-commit / CI /
                                 #   machine-layer はここを呼ぶ）
.claude-plugin/scripts/tests/    # 回帰テスト（stdlib unittest・依存なし）。4 系統:
                                 #  ① 検証スクリプト自身（test_validate_plugin_quality.py / test_mutation_test.py）
                                 #  ② プラグイン同梱スクリプトを CLI 境界越しに叩く subprocess テスト
                                 #     （`test_<plugin>_*.py`。bats を入れず依存ゼロで 3 経路に載せる）
                                 #     `skills/*/scripts/` 配下も対象（test_claude_meta_scripts.py）
                                 #     evals/runner.py は判定部だけ純関数として見る（test_evals_runner.py）
                                 #  ③ repo 直下スクリプトの CLI テスト（使い捨てリポジトリを立てる）。
                                 #     ゲートの判断（何を止めるか / 判定不能を通すか）は stub を置いて
                                 #     exit code の契約だけを見る: test_machine_layer.py /
                                 #     test_auto_quality_check.py / test_pre_commit.py
                                 #     本物を使い捨てリポジトリに向けて走らせ生成物まで見る:
                                 #     test_bump_version.py / test_validate_ssot.py /
                                 #     test_run_tests.py（#139 / #140）
                                 #  git を叩くテストは git_env.py（GIT_HOOK_ENV スクラブの正本）を通す
                                 #  ④ hook スクリプト（hook_harness.py + test_<plugin>_hooks.py。
                                 #     stdin に JSON を流し「発火するか / 黙るか」を直接見る）
                                 # python3 .claude-plugin/scripts/run-tests.py
.githooks/pre-commit             # バージョンバンプ・CHANGELOG・SSoT 同期・プラグイン品質 (errors)・回帰テスト
.github/workflows/validate.yml   # CI。push / PR で SSoT・品質・回帰テスト・バージョンバンプを検証（evals は非対応）
                                 #   変異テストは `--max 5` のスモークだけ（深い検証は nightly）
.github/workflows/mutation-nightly.yml # 変異テストの深い方（03:00 JST / 直近 24h の変更行を
                                 #   --max 60）。生存があれば GitHub Issue を起票・追記する
.claude/                         # リポジトリローカル設定（プラグインではない。git 追跡下）
  settings.json                  # Stop hook（auto-quality-check.sh）等の設定
  review-oracles.sh              # self-review が agent 起動前に走らせる機械層の宣言
                                 #   （存在自体が opt-in。中身は machine-layer.sh を呼ぶだけ）
  commands/ skills/              # /quality-check の実体（マーケットプレイスに配布しない自前コマンド）
  adr/ designs/                  # 本リポジトリ自身の設計判断・設計書
docs/                            # 横断設計指針（pipeline-design / rule-placement / skill-writing / event-bus /
                                 # shared-state / testing-pitfalls / ssot-pin / issue-workflow-migration
                                 # + session-reports/）
evals/                           # スキル起動回帰テスト（runner.py + cases/*.yaml。README に Gotchas）
                                 # fixtures/recall/ は別ハーネス（code-review の見落とし回帰）
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
| issue-workflow | 13 | 13 | 4 | SessionStart, PostCompact, UserPromptSubmit, FileChanged, PostToolUse | Issue 管理（旧 linear/indie の統合後継。backend 自動判定） |
| plugin-manager | 1 | - | - | SessionStart | インストール済みプラグインの一括更新 + deprecated の自動移行（_superseded_by）+ 後発追加通知 |
| plugin-feedback | 1 | 1 | - | SessionStart | プラグインへの改善要望・バグ報告を GitHub Issue 化 |
| feature-dev | 1 | - | 2 | SessionStart | 8 phase 機能開発ワークフロー（spec 品質ゲート・G-V fix ループ・self-review 委譲） |
| notebooklm-workflow | 2 | 2 | - | SessionStart | NotebookLM 連携ワークフロー（notebooklm-mcp-cli を .mcp.json で同梱） |
| guardrail-protect | - | - | - | PreToolUse | git commit の hook 迂回・lint/hook 設定ファイルの骨抜き編集・隔離なしの hook スクリプト実行をブロック |
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

# SSoT 検査の前提（**必須**）。無いとスキーマ検証が実行できず、
# validate-ssot.sh が exit 2（判定不能）を返して pre-commit が止まる
pip install jsonschema
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
- scope はプラグイン名（例: `feat(issue-workflow): ...`）
- 複数プラグインにまたがる場合は scope 省略

## コードコメントの規約（2 観点のみ）

正本は `.claude-plugin/lib/comment-rule.md`。下の区間はその複製で、`validate_plugin_quality.py` の comment-rule 同期チェックが byte 一致を検証する（**この区間を直接編集しない**。正本を直して全消費サイトへ反映する）。

<!-- COMMENT-RULE:START -->
コードコメントは次の 2 観点だけで評価する。**他の軸を足さない**（「what ではなく why」のような二分法も使わない）。**適用範囲はコード内コメント（`//` `#` `/* */` と docstring）に限る** — md 散文（doc / SKILL.md / README / CHANGELOG）は対象外。

観点 1 — **読み手にとって必要な情報のみか**:
- コードを読めば即座に分かることを言い換えているだけではないか（`count++` に「カウンタを増やす」等）
- その行が無いと読み手が困るか。困らないなら書かない / 消す
- 主語・目的が曖昧で、結局何を伝えたいのか読み取れない記述になっていないか

観点 2 — **冗長表現の排除**:
- 同じ内容を 2 回言っていないか（1 コメント内 / 直前直後のコメントとの間）
- 前置き・修飾が長く結論が後ろに来ていないか
- 1 語で足りる箇所を句で書いていないか

**上の 2 観点に該当しないことを理由に、削除・短縮を求めてはならない。長さは違反の根拠にならない。** 非自明な why / TODO・FIXME の背景 / regex・算術・境界条件の意図 / 外部制約（API 仕様・互換性・既知バグの回避）への言及 / 実測値・却下した代替案・ハマりどころの警告は、長くても観点 1 を満たす。**判断に迷ったら残す側に倒す。**
<!-- COMMENT-RULE:END -->

- **機械が強制するのは経路だけ**（正本と複製の一致・reviewer への連結）。内容判定は決定的にできない（候補 4 案とも真陽性 0。根拠は正本の冒頭）。書いた後の内容チェックは `/code-review:self-review` のコメント推敲が全件出す（severity を持たない別枠出力。採否は人間が決める）
- 既存の表記規約（散文に比較演算子を書かない・版ラベルは `vNEXT`。どちらも Gotchas）は**表記の話であって本節の軸ではない**。3 つ目の観点として数えない
- 既存コメントの一括推敲はしない。対象は**その変更で追加・変更した行のみ**

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

- **モデルルーティング**: 探索・収集は `sonnet`、判断・検証・統合は `opus`。agent frontmatter か skill 本文で明示指定する（継承任せにしない)。**エイリアスは「最新世代」ではなく「親＝実行時に選択したメインモデルの世代」に解決される**（メインが Opus 4.8 なら `opus` の sub も 4.8。親世代にその tier が無ければ最新へ落ちるので `sonnet` は 4.8 親でも Sonnet 5）。これは**セッション単位でパイプライン全体の重さを選べる制御点**なので望ましい挙動として扱う（ただし**踏み下げには recall 側の代償がある** — 実測で報告 0 件率 42%→91% / `pre_adjust` MAJOR 中央値 7→0。`docs/pipeline-design.md`）。あわせて**モデル指定に具体 ID をピン留めしない**（ピン留めは実行時の選択を無視する。世代同定が目的の値 — cc-catch-up の `lastCatchUpModel`・evals の `--models` — は除く）。**世代を下げても単価は下がらない**（Opus 5 と 4.8 は同一単価。差は消費量に出る）。sub だけ固定する `CLAUDE_CODE_SUBAGENT_MODEL` は全 sub に一律でロール別ルーティングを潰すため既定では使わない。詳細は `docs/pipeline-design.md`
- **`fable` は使用しない**（プロジェクト方針）。独立性は「別コンテキスト起動 + 発見者の推論を渡さない」で担保する
- **subagent の事実主張は採用前に一次ソースへ当てる**: subagent が報告した外部仕様・既定値・バージョン・数値は、実装・起票・レポート記載の前に一次ソースで確認する。反証レイヤーは findings に働くが、指摘が前提として持ち出す事実にはゲートが無い（実測 3 回 / `misread-or-trusted-bad-output`）。**これは下の②「自分でダブルチェックせよ」とは別物**（他者の出力の典拠確認＝適用除外の「根拠強制の手順」）。詳細は `docs/pipeline-design.md`
- **Opus 5 世代で逆効果になる足場を書かない**（新規設計・既存 rules/skills 本文の両方に適用）: ①「積極的に委譲せよ」（委譲過剰を招く。体数上限を明示する）②「自分でダブルチェックせよ」（over-verification。検証は独立エージェント層に）③「重要な指摘だけ報告せよ」（recall 低下。全報告→下流フィルタに）。適用除外（根拠強制の手順・スコープ定義は残してよい）を含む詳細は `docs/pipeline-design.md` の Opus 5 節

## Event Bus 規約（Hook = Message Bus）

Claude Code の hook を **Pub/Sub Message Bus** として運用するための軽量規約。Classmethod「Claude Code マルチエージェントオーケストレーションパターン」記事の Message Bus パターンをローカル実装したもの。

### 永続化

- イベントログ: `.claude/events.jsonl`（プロジェクトローカル、gitignored、JSON Lines 形式）
- 1 行 = 1 イベント: `{"ts":"<ISO8601>","plugin":"<name>","event":"<name>","payload":<obj>}`
- `plugin` は `SAFE_HOOK_NAME` がそのまま入る。hook 系は `dev-workflow:on-commit` のような
  `<plugin>:<hook>` 複合値、skill / command 系は素のプラグイン名になる（書式は publisher 依存）。
  **subscriber 側はプラグイン名の完全一致で絞らない** — 前方一致か event 名で絞る

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
| `issue:completed` | Issue ファイルの status が completed に遷移 | issue-workflow | **issue-workflow:retrospective**（実装済） |
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
- **正本 → 消費サイトの伝播漏れ（SSoT pin）**: 言い換え・要約で複製されている関係は、消費サイトの冒頭に `<!-- SSOT: <path>#<anchor> @<hash8> -->` を宣言する。`validate_plugin_quality.py` の `check_ssot_pins` が正本の該当節をハッシュして突合し、ずれれば Critical（強制するのは内容の一致ではなく「正本が変わったら消費サイトを確認して打ち直す」手順）。打ち直しは `--update-ssot-pins`（**明示操作**・repo 全体を一括）。**記法と落とし穴の詳細は `docs/ssot-pin.md`**（新規 pin のダミー hash / 宣言位置 / md 限定 / 節の境界）
- **バージョンバンプ忘れ**: プラグインの内容を変更したら必ず plugin.json の version を上げ、CHANGELOG.md も同時更新する。上げないと使用側で更新が検知されない。どちらも pre-commit hook でブロックされる
- **_requirements の同期忘れ**: プラグインの依存先が変わったら plugin.json の `_requirements` と `check-deps.sh` の両方を更新する。pre-commit の `validate-ssot.sh` が `check_xxx "<name>"` 形式の一致を検証する
- **hook スクリプトは `hook_harness.py` でテストする**: hooks.json を経由せず直接叩き、**発火する条件より「黙る条件」を厚く**書く（暴発の blast radius が最大）。**rc だけを見ない** — 正常系も ERR trap も exit 0 なので、stderr の `Unexpected` の有無で見分ける。不正 JSON は `run_hook(raw=...)` で流す。詳細: `docs/testing-pitfalls.md`
- **`set -e` 下で「非ゼロが正常」なコマンドの結果を `VAR="$(...)"; RC=$?` と書かない**: 代入の終了コードは中のコマンドのもので、非ゼロならその行で `set -e`（safe-hook が張る）が発動し、**以降を実行せず ERR trap → exit 0** する。hook の正常系が silent exit 0 なので、呼び出し側からは「何も検出しなかった」と区別がつかない。`VAR="$(...)" && RC=0 || RC=$?` と `||` リストに入れる。実例: `auto-quality-check.sh` が機械層の exit 1 を受け取った瞬間に死に、**検出の通知（stderr / additionalContext）が丸ごと消えていた**（v2.69.0 の書き換えで混入し #139 のテスト追加で発覚）。同種: `VAR=$(... | grep ...)` の `|| true`（上のバレット）
- **`set -e` 下で `[ 条件 ] && コマンド` を関数 / `$( )` の最後に置かない**: 条件が偽なら AND リストは exit 1 で終わる。**ループ本体の途中なら `set -e` は発動しない**（実測: bash 3.2）が、それが**関数または `$( )` サブシェルの最終ステータスになると殺される** — `VAR="$( ... )"` の中なら **VAR は空のまま ERR trap → exit 0** で、呼び出し側からは「該当なし」と区別がつかない。`if [ 条件 ]; then コマンド; fi` は条件が偽でも 0 で終わるのでこちらを使う。実例: `auto-quality-check.sh` の指紋計算（`[ -f "$f" ] && cksum < "$f"`）。上の 2 バレット（`VAR=$(... | grep ...)` / `VAR="$(...)"; RC=$?`）と同じ family
- **日本語の直前の変数展開は `${VAR}` と波括弧で囲む**: `"$DIFF（重複検出をスキップ）"` は **UTF-8 ロケールの bash** が `（` の 1 バイト目まで変数名に取り込み、`set -u` 下で `DIFF<0xef>: unbound variable` を出して**そのメッセージを表示せず exit 1** する（`C.UTF-8` / `ja_JP.UTF-8` / `en_US.UTF-8` で再現、`C` / `POSIX` では再現しない = 開発機のロケール次第で見えない）。`validate_plugin_quality.py` の `shell-multibyte` 検査が errors で止める。実例: `detect-recent-review.sh` の WARN が丸ごと死んでいた（#138）
- **記録から現在の状態を断定しない**（実測 3 回 / `claimed-fact-without-source` は窓内 7 件で最多）: issue の title・コミットメッセージの参照番号・過去のコメントは**書かれた時点のスナップショット**であって現在値ではない。issue について述べる前に `gh issue view <N> --comments` で本文とコメントを読む。集計値を引用する前に集計を自分で回す。実例はどれも 1 コマンドで否定できた — 「実装済みの issue を未着手・最優先と推薦」「コメントの『サンプル待ち』を信じて判定不能と結論（実際は合算すれば判定可能だった）」「コミットメッセージの参照番号だけで issue の状態を断定（本文には逆の判断が明記されていた）」。**`gh-ref-guard` が塞ぐのは本文中の参照の実在性だけで、この型は本文に参照を書かないため掛からない**
- **未知のデータを集計・変換する前に 1 件ダンプして構造を確かめる**（実測 5 回 / issue #163）: キー名・行の粒度・欠測の表現を推測しない。**壊れ方が「全件 None」「全セッションが同じ判定」のように一様なので、出力を見ても異常に見えない**のが厄介で、個別の落とし穴を足す方式は新しいデータ形に効かない。**構造の正本があるなら先にそれを読む**（transcript / payload は `code-review/references/orchestration-measurement.md`）。有効性は実測済み — この手順を踏んだ回に`message.model` の `<synthetic>` 混入と main 世代の混在を**実装前に**見つけた（#169）
- **jq の `//` を真偽値の既定に使わない**: `//` は左辺が `false` でも「無い」扱いにするので、`jq -r '.flag // true'` は `flag: false` を `true` に化けさせる（doc-freshness の opt-out が効いていなかった実例）。素で読んで文字列比較する（キーが無ければ jq は `"null"` を返す）
- **hooks.json の if:/matcher に単独依存しない（注入・block 系 hook の自己判定必須）**: `if: "Bash(git push *)"`（CC 2.1.85+）や matcher のフィルタは**実行環境によって評価されない**ことが実測済み（2026-07: dev-workflow push-reminder が全 Bash 呼び出しで additionalContext を注入する暴発。配布・スキーマ・構文は正しかった）。PreToolUse/PostToolUse の hook スクリプトは `INPUT=$(safe_hook_input)` で tool_input を取得し発火条件を自己判定する二重ゲートにする（手本: `dev-workflow/hooks/scripts/on-commit.sh`）。`validate_plugin_quality.py` の hook-self-judge チェックが `safe_hook_input` 非参照を非ブロッキング warning で検知する。FileChanged の path-glob matcher も同型リスクだが tool_input が無いためチェック対象外（既知の残リスク）
- **hooks.json の args[] exec 形式 (CC 2.1.139+)**: 新規 hook は `command: "bash <path>"` ではなく `command: "bash", args: ["<path>"]` の exec 形式で書く。シェル解釈を経由せず直接 spawn するので安全＆高速。スキーマは `.claude-plugin/schema/hooks.schema.json` を参照
- **terminalSequence helpers (CC 2.1.141+)**: `safe-hook.sh` の `safe_hook_emit_bell` / `safe_hook_emit_window_title` は端末ベル / ウィンドウタイトルを JSON 出力で送る。`safe_hook_emit` (plain text) と**混在不可**（terminalSequence は単独 JSON 出力）。長時間処理の完了通知や警告アラートに opt-in で利用する
- **${CLAUDE_EFFORT} skill 適応分岐 (CC 2.1.120+)**: SKILL.md / コマンド本文に `${CLAUDE_EFFORT}` を書くと実行時 effort (low/medium/high/xhigh/max) が展開される。深掘り skill では `low/medium → 速度優先、xhigh/max → 多重 agent` のような条件分岐を入れる。frontmatter の `effort:` は宣言（既定値）、本文の `${CLAUDE_EFFORT}` は実行時値
- **Agent tool の background 既定 (CC 2.1.198+)**: fanout して結果を待つスキル（explorer/reviewer/verifier 等）では **①各 Agent call に `run_in_background: false` を明示**（省略＝background 起動で結果を取りこぼす）し、**②全 Agent call を同一メッセージ内で一括発行**する（1 体ずつ別メッセージだと実時間が体数分の合計になる）。**①は取りこぼし防止・②は並列性で、直交する独立の要件**（①だけでは並列にならない）。根拠と実測は `orchestration-guide.md ## 0`（正本・issue #95）。取り漏れは `validate_plugin_quality.py` の agent-sync チェックが非ブロッキング warning で検知する
- **command 名と skill 名が同名なら、スキル選択に載るのは `commands/*.md` の description**（`SKILL.md` 側は載らない / GitHub issue #206）。**description を直すときは commands と SKILL.md を必ず対で直す** — `SKILL.md` だけ直しても選択挙動は 1 ミリも変わらない。確認は router 本人に聞くのが早い: `claude -p '<plugin>:<skill> について、あなたに見えている description を一字一句そのまま引用して' --permission-mode plan`。該当は **9 プラグイン 26 スキル**（issue-workflow は 13/13 全部）で、`トリガー:` 必須規約（error 強制）はそこで**字面は通るが router には届かない**。実例: #205 は「description の leading words で負けている」と誤診したが、実際は逐語トリガーがそもそも視界に無く、効いた修正は `commands/*.md` の 1 行だけだった
- **eval を実行・修正する前に `evals/README.md` の Gotchas を読む**: スラッシュコマンドは headless で必ず落ちる（自然言語プロンプトで測る）/ fail は「プラグイン選択」と「skill id の綴り」を分けて読む（id 捏造は harness 側の性質）/ 判定は k=1 でなく pass^k=3 で行う — 詳細と実例は README 側に集約

- **版ラベルは `vNEXT` と書く**（プラグイン配下の md / sh / py）。`bump-version.sh` が実版へ置換し、`validate_plugin_quality.py` が「bump 済みなのに残っている」を error にする。**具体的な版番号を手書きしない** — 書く時点では正しい値が確定しておらず、実測で 3 回再発した。**行内コード・フェンス内は置換も検出もされない**ので、規約の説明はそこに入れ、`references/prompts/*.md` のようにフェンスで丸ごと囲われた doc では版ラベルを使わずissue 番号で参照する。repo 直下の共通スクリプト・doc はプラグイン版に属さないので版ラベルを持たせない。経緯: `code-review/references/design-notes/pending-optimizations.md ## 9`
- **散文に `>=` / `<=` を書かない（変異テストが必ず等価変異として拾う）**: 変異ツールはコメント行（`#` 始まり）を除外するが、**`.sh` 内の python ヒアドキュメントの docstring** は `#` で始まらないので除外されず、説明文中の `v >= max(t0, lo)` のような表記がそのまま演算子として書き換えられる。挙動は変わらないので**必ず生存し、CI（`--strict`）が落ちる**。「`x` 以上」「`y` 以下」と日本語で書く（行内コードに入れても効かない — 除外はコメント判定であって markdown 記法の解釈ではない）。**`<` / `>` 単体も対象**（`mutation-test.py` の `RULES` 末尾に「緩める方向」として `>` → `>=` / `<` → `<=` が入っている）。比較演算子は 4 つとも散文に書かない。**`.py` は `tokenize` で docstring / コメントをマスクするので対象外**で、危ないのは行単位の近似しか持たない `.sh` 側。実例: #161 のセルフレビュー修正で `ok()` の docstring が CI を落とした
- **新しい lint / 検証ロジックを足すときは ①既存 repo での検出数を先に測って水準を決める ②変異テストで「実装を壊すと該当テストが落ちる」ことを確認する**。初回実行で偽陽性が出る warning は「⚠️ が出たときだけ行動する」契約を壊すので、入れない方がまし（実例: 版ラベルの追随漏れ検出は 6/6 が偽陽性で撤去）。手順と却下事例は`docs/rule-placement.md`。変異テストは `python3 .claude-plugin/scripts/mutation-test.py`（`__pycache__` の消去・モードの保存・中断時の復元はツール側にある。**実行中に対象ファイルを編集しないこと**、そして**実行中に別セッションでテストを走らせないこと** — 変異体は作業ツリーの実ファイルへ in-place で書かれ、1 変異ごとにフルスイートを回すので**ファイルはほぼ 100% の時間 mutant 状態**になる。そこで測った結果は緑にも赤にも化け、「テスト間の順序干渉」に見える（実測: 3 秒間隔 44 サンプルすべてが変異体。誤診でフルスイート 6 回を溶かした）。`run-tests.py` は journal の pid が生存していれば exit 2 で止めるが、**素の `python3 -m unittest` は素通りする**。待てないときは `git checkout-index -a --prefix=/tmp/clone/` で index から取り出して測る。**Ctrl-C で殺さないこと** — 復元が飛んで変異がツリーに残る）
- **テストは「環境の不在」に頼らない**: PATH を絞るときは引ける側を列挙する / 使い捨てリポジトリはリポジトリ側に author を設定する / `CLAUDE_PROJECT_DIR` を継承させない / `pgrep` は PATH から外さず stub にする / git を叩くテストは `git_env.scrub()` を通す。**どれも「テストが緑のまま壊れる」型**で、実測で CI 6 件・Stop hook 経由 3 件・CI 21 件が落ちた。**7 項目の詳細と実測は `docs/testing-pitfalls.md`**
- **実行を伴う検証を委譲したら、完了後に副作用の差分まで見る**（実測 4 件 / GitHub issue #194）: agent に「再現せよ」「動かして確かめよ」と指示する回は、**dispatch する前に** `.claude/events.jsonl` の行数と `git status --porcelain` を控え、完了後に突き合わせる。**指示ベースの隔離は守られない** — prompt に隔離を明記しても並列 agent の一部が実 `events.jsonl` を汚した実測がある。hook スクリプトの直接実行は `guardrail-protect` の `hook-isolation-guard` が block するようになったが、**Edit/Write でツリーを書き換える経路は機械的に判定できない**ので、この事後確認が唯一の網。**常時 Stop hook で「events.jsonl が増えた」を鳴らす案は採らなかった** — 実測で稼働日ほぼ毎日 3〜38 件の正当な publish があり、鳴りっぱなしになって「⚠️ が出たときだけ行動する」契約を壊す
- **移植性と環境差は CI でしか検出できない（push して CI を確認するまで完了ではない）**: pre-commit は開発機（macOS）でしか走らないので、**Linux 固有の失敗は原理的に push 前に検出できない**（Docker を pre-commit に入れるのは体感コストが見合わない）。機械層は同じコマンドを走らせるが**環境が違う**。前提ライブラリの差だけは塞いだ — `validate-ssot.sh` は jsonschema が無いと exit 2（判定不能）を返し、pre-commit がそこで止める（以前は warning を出しつつ「passed」と表示し、ローカル緑 / CI 赤の非対称が push まで見えなかった）。**OS 差は残るので、push 後に CI の結果を見るまで作業を完了と見なさない**（#140）
- **同梱スクリプトのテストは `.claude-plugin/scripts/tests/` に置く**（配布物にテストを混ぜない）。ハーネスは python の subprocess で外部依存を足さない。詳細: `docs/testing-pitfalls.md`
- **版ラベルは `vNEXT` で書く**: doc / コメントに「この挙動は vNEXT で入った」と書くと `bump-version.sh` がそのプラグイン配下だけを実版へ解決する（書く時点では版が確定しない構造的な race を消すため）。行内コード・フェンス内の `vNEXT` は規約の説明とみなして置換しない。**repo 直下の共通スクリプト（`.claude-plugin/scripts/` 等）はどのプラグイン版にも属さないので版ラベルを書かない** — issue 番号か設計ノートへのパスで参照する
- **判定は「変更ファイルの種類」で行う**: commit type が `docs` で変更が `*.md` + version/CHANGELOG のみなら PATCH。MINOR を当てると `plugin-manager:update-all` の利用者に「機能追加が入った」と誤ったシグナルを送る（pre-commit は bump の有無しか見ないので機械的には素通りする）

## 品質チェック

プラグインの新規作成・変更時は `/quality-check` で全プラグインの品質バリデーションを実行する。
個別のスキル開発時は `docs/skill-writing.md` の観点（description の branch 設計・情報階層・no-op 剪定・失敗モードカタログ）で自己点検し、description / トリガーフレーズを変えたら evals で回帰を確認する。

**自動チェック（Stop hook）**: プラグイン関連ファイル（`*/plugin.json` / `*/skills/` / `*/commands/` / `*/hooks/` / `*/agents/` / `*/references/` / `*/scripts/` / `marketplace.json` / `*/CHANGELOG.md`）を変更した状態でターン終了を迎えると、`.claude-plugin/scripts/auto-quality-check.sh` が以下を自動実行し、問題を stderr（ユーザー向け）と `hookSpecificOutput.additionalContext`（Claude 向け、CC 2.1.163）の両方に通知する（Stop はブロックしない）。`.claude/settings.json` で設定。

- `validate-ssot.sh`: スキーマ準拠 / marketplace 同期 / _requirements ↔ check-deps.sh / INDEX.md・CLAUDE.md 一覧の同期
- `validate_plugin_quality.py`: allowed-tools / safe-hook.sh 同期 / references 参照整合性 / トリガーフレーズ / Event Bus 同期 / hook 自己判定 / コンテキスト予算ほか — **検査項目の正本はスクリプト冒頭 docstring**（ここに列挙を複製しない）
- `claude plugin validate`: CLI スキーマ（`_requirements` 警告は除外）
- `python3 .claude-plugin/scripts/run-tests.py`: 回帰テスト（検証スクリプト自身 + プラグイン同梱スクリプトの CLI テスト）。**起動口をこのラッパに寄せてある** — テストを新しいセッションで走らせ、終了後に残ったプロセスを検出・回収する（テストは緑のまま 12 本が 4 時間回り続けた実例 / #140）。素の `python3 -m unittest discover -s .claude-plugin/scripts/tests` でも走るが、その経路には残留の検出が無い。**検証機構の期待値をその機構自身で生成すると、壊れていても全件 pass する**（SSoT pin の初期ハッシュを未テストの `_slice_section` で作り、節の 46% が無保護なまま 14 pin 全部が ok に見えた実例が v2.63.1）。**期待値をテスト側で独立に構築すること**（`test_digest_matches_independently_computed_expectation`）。検証ロジックを足すときは同じ原則でテストを添える

LLM 判定が必要な項目（CLAUDE.md 品質、allowed-tools 最小性、プロジェクト固有情報検出等）は手動 `/quality-check` 側に残る。

スキルの description / トリガーフレーズを変更した場合は `evals/runner.py` で回帰テストを実行する（`claude-meta:eval-runner` スキル経由も可）。pass^k=3 基準でスキル選択の安定性を検証できる。**evals だけはローカル実行のみ**（`.github/workflows/validate.yml` は SSoT・品質・回帰テスト・バージョンバンプを検証するが evals は回さない。通常セッション枠を消費するため）。

## ブランチ運用

- main に直接コミット
