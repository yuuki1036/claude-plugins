# Feature Development Plugin

コードベース理解・アーキテクチャ設計・runtime smoke test・品質レビューを 8 phase で進める機能開発ワークフロー。専用 agent（code-explorer / code-architect）を内包し、bdd-spec / design-doc / code-review の各プラグインと連携する。

## Overview

`/feature-dev` コマンドで起動する 8 phase のワークフロー。いきなりコードを書き始めるのではなく、コードベース理解 → 要件の grill → アーキテクチャ設計 → 実装 → runtime 検証 → 品質レビューの順で進めることで、既存コードに馴染む設計を作る。

各 phase は `${CLAUDE_EFFORT}`（実行時 effort）と feature の特性に応じて動的に構成される。Phase 1.7 のトリアージが explorer / architect / reviewer の体数と focus を決め、低 effort では phase を圧縮し、高 effort では多角的に検証する。

## Philosophy

機能を作るにはコードを書く以上のことが要る。

- **理解してから動く**: 変更前に既存のパターンを読んで把握する
- **曖昧さを潰す**: 要件の曖昧点を grill（1 問ずつ依存順）で解決する
- **設計してから実装する**: 複数案を比較してから 1 案にコミットする
- **品質を検証する**: 実装後に runtime smoke test とレビューゲートを通す

これらを構造化したワークフローに埋め込み、`/feature-dev` で自動的に走らせる。

## Command: `/feature-dev`

8 phase の機能開発ワークフローを起動する。

```bash
/feature-dev Add user authentication with OAuth
```

引数なしでも起動でき、対話的に要件を詰めていく。

```bash
/feature-dev
```

## Phase 構成

| Phase | 名前 | 役割 |
|---|---|---|
| 1 | Discovery | 何を作るかを把握する |
| 1.3 | BDD Spec Creation | bdd-spec 連携。spec.md を architect の入力契約として生成（dormant） |
| 1.5 | Issue Context Detection | linear-workflow / indie-workflow からの引き継ぎ context を検出 |
| 1.6 | Vault Recall | 外部 kvault CLI から横断知見を recall し architect に advisory 注入（dormant） |
| 1.7 | Triage | explorer / architect / reviewer の体数・focus を動的決定 |
| 2 | Codebase Exploration | code-explorer で既存コードとパターンを把握 |
| 3 | Clarifying Questions (Grill) | 曖昧点を 1 問ずつ依存順で解決 |
| 4 | Architecture Design | code-architect で複数案を設計・比較 |
| 4.5 | Design Doc Export | design-doc 連携。採用案 + 代替案比較を永続化（dormant） |
| 5 | Implementation | 採用案に沿って実装（Normal Mode / Fix Mode） |
| 5.5 | Runtime Smoke Test | 静的チェックで取れない runtime 初期化バグを検出 |
| 6 | Quality Review | code-review:self-review に委譲 + 致命指摘を自動 fix |
| 7 | Summary | 成果のサマリ + イベント発行 |

> Phase 1.3 / 1.6 / 4.5 は連携先プラグイン（または外部 CLI）が無ければ完全に skip される dormant な連携。後方互換を壊さない。

### Phase 1: Discovery

何を作るかを把握する。feature が不明確なら「解決したい問題」「機能の振る舞い」「制約・要件」を聞き、理解をまとめて確認する。

### Phase 1.3: BDD Spec Creation（bdd-spec 連携 / dormant）

`bdd-spec` プラグインがインストールされている場合のみ、Phase 1 直後に BDD `spec.md`（Feature / Scenario / Examples / 同値分割表）を生成し、Phase 4 architect の **authoritative requirements** として使う。`bdd-spec:create-spec` を非対話 API（`role` / `want` / `why` / `shortPath`）で呼ぶ。未インストール時は skip し、既存の Issue 解釈フローに fallback する。

### Phase 1.5: Issue Context Detection（linear / indie 連携）

`Issue ファイル:` パスや `feature_dev_plan:` frontmatter を検出すると、linear-workflow / indie-workflow からの引き継ぎ context を読み込む。Issue context が完備なら Phase 1.7 に「explorer 0 体」を信号して Phase 2 を実質 skip し、context を Phase 4 architect に直接渡す。

### Phase 1.6: Vault Recall（外部 kvault CLI 連携 / dormant）

外部 app の `kvault` CLI と vault ディレクトリが揃っている場合のみ、過去プロジェクト横断の知見（落とし穴・設計判断・移行ノウハウ）を recall し、Phase 4 architect に **advisory（参考情報）** として注入する。注入知見は authoritative ではなく、現コードベースのパターンと矛盾する場合は現コードベースを優先する。CLI / vault dir のいずれかが欠けたら skip する。

### Phase 1.7: Triage（動的エージェント構成決定）

feature の特性（種別・スコープ・リスク因子）× `${CLAUDE_EFFORT}` を分析し、後続 phase で起動する explorer / architect / reviewer の体数・focus・冗長度を決める。メインコンテキストで実行し（Agent tool は使わない）、構成テーブルを出力する。後続 phase はこのテーブルを直接参照する。

最小保証: architect ≥ 1、reviewer ≥ 1（bug-detection 必須）、explorer は 0 可（Issue context 完備時）。

### Phase 2: Codebase Exploration

Phase 1.7 が指定した N 体の `code-explorer` agent を並列起動する。各 agent は割り当てられた focus（similar-features / architecture-mapping / shared-modules / history-context / dependency-trace / layer-mapping）と対象スコープを受け取り、読むべき主要ファイル 5-10 件を返す。agent 完了後、特定されたファイルを読んで理解を深める。

個別 explorer が失敗しても残りの結果で続行し、失敗分は `missing_coverage` として Phase 7 で報告する。Phase 1.7 が 0 explorer と判定した場合はこの phase を skip する。

### Phase 3: Clarifying Questions（Grill）

曖昧点を **フラットな質問リストではなく grill** で潰す。`references/grill-protocol.md` が正本。

1. 候補となる曖昧点を列挙
2. コードで答えられる問い（Phase 2 explorer 結果 / Grep / BDD spec / Issue context）は自己解決し、質問から落とす
3. 残りを design tree の依存順にソート（上流の決定を先に）
4. `AskUserQuestion` で 1 問ずつ確認。各問いに推奨案を先頭に `(Recommended)` 付きで提示
5. 確定した前提 + ユーザー決定を design contract として集約

残り 1-2 問で方向が明らかな場合は 1 回の質問にまとめる（過剰質問の抑制）。

### Phase 4: Architecture Design

Phase 1.7 が指定した N 体の `code-architect` agent を並列起動する。各 agent は focus（minimal-changes / clean-architecture / pragmatic-balance / migration-strategy / delta-proposal）を受け取る。Phase 1.3 の `BDD_SPEC_PATH` があれば各 architect に注入し、spec を真実として読ませる。Phase 1.6 の `VAULT_KNOWLEDGE` があれば advisory として注入する。

全案をレビューして推奨案を形成し、各案のトレードオフ比較 + 推奨理由をユーザーに提示し、どの案で進めるかを聞く。全 architect 失敗時は `minimal-changes` focus で単体起動して fallback する。

### Phase 4.5: Design Doc Export（design-doc 連携 / dormant）

`design-doc` プラグインがインストールされている場合のみ、Phase 4 の architect 比較とユーザー採用決定（プロンプト内で揮発する）を `.claude/designs/` に永続化する opt-in ステップ。`design-doc:design-doc` を export 非対話 API（`mode=export`）で呼び、`spec=`（Phase 1.3）/ `issue=`（Phase 1.5）を frontmatter に転記する。後続の同領域開発の参照元・実装後の as-built 記録として再利用できる。未インストール時は skip、呼び出し失敗時も warning のみで実装フローを止めない。

### Phase 5: Implementation

2 つのモードを持つ。

- **Normal Mode**: Phase 4 完了から起動。ユーザー承認を待ってから、採用したアーキテクチャに沿って実装する。既存コードの規約に従う。
- **Fix Mode**: Phase 6 の Generator-Verifier ループから起動。reviewer が指摘した file:line だけをピンポイント修正する（スコープ拡大・無関係なリファクタ禁止、Phase 4 の設計を維持）。

### Phase 5.5: Runtime Smoke Test

tsc / lint / build では検知できない runtime 初期化バグ（DB client 初期化、env var 読み込み、middleware 設定ミス、proxy lazy-init 等）を Quality Review 前に検出する。

- Step 0: TTL ベースの self-lock guard（将来 PostToolUse hook を導入した際の重複起動・無限ループ予防 template）
- Step 1: `git diff` から DB client / env var / middleware / 新規 route のパターンを grep し、smoke test が必須か任意かを決定的に判定
- Step 2: `AskUserQuestion` で実行可否を確認
- Step 3: `dev-workflow:ui-verify` skill を呼んで dev server 起動 + console error / network 4xx-5xx を検査。chrome-devtools MCP 未設定時は手動確認に fallback（hard fail しない）
- Step 4: エラー検出時は Phase 6 に進ませず、ユーザー判断（今修正 / 受け入れて続行）を仰ぐ

「全静的チェックを通過したのに初回 runtime アクセスで死ぬ」事故（Issue #29）を構造的に予防する。

### Phase 6: Quality Review

`code-review:self-review` skill に委譲して品質ゲートを通し、致命指摘を Generator-Verifier ループで自動 fix する。v2.0.0 で feature-dev 内蔵の `code-reviewer` agent を廃止し、品質基準を code-review プラグインに一本化した（DRY 違反の解消 + 2 軸スコアリング × 多観点 × specialist × meta-reviewer 構造への統一）。

- Step 0: code-review プラグインの存在確認。未インストール時は **fail-fast**（Phase 5 までの成果物は維持。`_requirements` では `required: false` 宣言だが Phase 6 では事実上必須）
- Step 1: 実装 diff を読んで reviewer focus list を refine（mini-triage）
- Step 2: `Skill code-review:self-review --focus <list> --embed` を 1 回呼ぶ（`--embed` で self-review 終端の AskUserQuestion を skip）。出力は構造化 findings JSON ブロックを優先パース、無ければ markdown フォールバック（dual format）
- Step 3: Generator-Verifier ループ。`BLOCKER`（any confidence）/ `CRITICAL && confidence ≥ 90` を auto-fix 対象とし、effort 別 max_iterations で fix → 再 review を反復。regression 検知（同一 fingerprint）/ budget で終了
- Step 4: 集約結果を `[auto-fixed]` / `[persisting]` タグ付きで提示し、残課題はユーザー判断

### Phase 7: Summary

全 todo を完了にし、成果（作ったもの / 主要な決定 / 変更ファイル / 次の一手）をまとめる。Phase 4.5 で design doc を export した場合は `phase: target → current` 更新を案内する。Phase 6 で G-V ループが走った場合は iteration 数 / termination reason / auto-fixed count / persisting issues を報告する。最後に `.claude/events.jsonl` へ `feature:implemented` イベントを fire-and-forget で追記する。

## Agents

### `code-explorer`（model: sonnet）

既存のコードベース機能を、実行パスを entry point からデータ保存まで追跡し、抽象層・パターン・依存関係をマッピングして分析する。Phase 2 で並列起動される。出力は entry point の file:line 参照、ステップごとの実行フロー、主要コンポーネントの責務、アーキテクチャの知見、読むべき必須ファイルのリスト。

### `code-architect`（model: fable）

既存パターンを分析し、実装 blueprint を設計する。Phase 4 で起動される。BDD Spec Injection / Issue Context Injection / Vault Knowledge Injection / Hook-First Rule Placement の各セクションを持つ。出力は発見したパターン、アーキテクチャ決定と根拠、コンポーネント設計、実装マップ、データフロー、build sequence、critical details、Runtime Smoke Test Targets（Phase 5.5 が叩く URL / route）。

> v2.0.0 で `code-reviewer` agent は削除。Phase 6 のレビューは `code-review:self-review` skill に委譲され、品質基準が一本化された。詳細は code-review プラグインの README 参照。

## Usage Patterns

### フルワークフロー（新機能向け推奨）

```bash
/feature-dev Add rate limiting to API endpoints
```

8 phase に沿って進める。

### Agent の手動起動

- コードの追跡: 「code-explorer で認証の動きを追って」
- 設計: 「code-architect でキャッシュ層を設計して」
- レビュー: `code-review:self-review` skill を直接呼ぶ

## When to Use This Plugin

**使う:**
- 複数ファイルに触れる新機能
- アーキテクチャ判断が必要な機能
- 既存コードとの統合が複雑な機能
- 要件がやや不明確な機能

**使わない:**
- 1 行のバグ修正
- 些細な変更
- 定義が明確で単純なタスク
- 緊急のホットフィックス

## Requirements

- Claude Code
- Git リポジトリ（品質レビュー・diff 検出に必要）
- 既存コードベースのあるプロジェクト（探索 phase が既存コードからの学習を前提とする）

連携プラグイン（いずれも optional。`_requirements` 参照）:

- `code-review`（Phase 6 委譲先。未インストール時は Phase 6 が fail-fast）
- `bdd-spec`（Phase 1.3 入力契約。未インストール時は skip）
- `design-doc`（Phase 4.5 export 先。未インストール時は skip）

## Author

yuki (yuuki1036-claude-plugins)

## Origin

claude-plugins-official/feature-dev からフォークした内製版。元著者・元バージョンの情報は `CHANGELOG.md` を参照。
