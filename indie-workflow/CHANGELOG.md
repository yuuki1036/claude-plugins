# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.31.0] - 2026-06-15

### Added
- **failure-journal の `failure:logged` イベントを retrospective が subscribe**。Phase 1 のデータ収集に「Source 3: failure:logged（再発失敗、任意）」を追加し、`event_bus_tail "failure:logged" 200` で取得して期間フィルタする（events.jsonl / イベントが無い場合は graceful に skip。failure-journal 未導入でも壊れない）。Phase 2 に指標 8「再発失敗パターン」を追加し、期間内の failure:logged を tag 別集計して 3 回以上再発した tag を振り返りの素材として提示する。規約還流提案は `failure-journal:retro` の責務として委ね、retrospective 側は重複しない（提示のみ）

### Changed
- 共通 skill（knowledge / knowledge-lint / issue-design）の description 冒頭に作用範囲「ローカル (.claude/indie) プロジェクトの」を明記し、linear-workflow との同時インストール時のトリガー衝突を解消（対応する commands/ の description も同期）
- session shared_state frontmatter 雛形（indie-start）の `consumers` を実態に合わせて `[code-review]` に修正（feature-dev / dev-workflow は session-context.md を読む実装が無いため削除）
- FileChanged hook（on-issue-change.sh / on-knowledge-change.sh）と PostToolUse の scope 超過警告（check-scope-size.sh）の Claude 向け通知を `safe_hook_emit` から `safe_hook_emit_context`（additionalContext, CC 2.1.163+）へ置き換え、到達保証を向上（stderr ログ / event_bus_publish はそのまま維持）

## [1.30.0] - 2026-06-11

### Added
- **issue-design に design doc への昇格判断を追加（design-doc 連携・opt-in）**。Phase 2 の open 仕分けで、タスク 1 件を超えた設計判断（複数 Issue にまたがる方式選定、Issue 本文で持ちきれないトレードオフ比較）を検知したら、design-doc プラグインへの切り出しを AskUserQuestion で提案する。切り出した doc のパスを「参考資料」にリンクし、該当 open は「確定タイミング: design doc で確定」に書き換える。未インストール時は従来どおり Issue 内 grill に dormant（後方互換 100%）
- `_requirements` / `check-deps.sh` に design-doc（required: false）を追加

## [1.29.0] - 2026-06-03

### Added
- **issue-design の open 仕分けに grill プロセス（design-rules.md ルール5）を追加**。Phase 2 で open を独断列挙して終えず、コミット前に 1 つずつ詰める: ①既存 ADR / 他 Issue / コードで決着済みかを `Grep` / `knowledge` /（adr-keeper があれば）`adr` で自己確認し決着済みは決定事項へ移す ②残った open を依存順に `AskUserQuestion` で 1 問ずつ・「現時点の方向性」を推奨案として `(Recommended)` 付きで確認 ③「おまかせ」は推奨で確定。open が 1〜2 個かつ方向性明確なら圧縮（過剰質問抑制）。Matt Pocock "grill-me" / Brooks『The Design of Design』の design tree に由来
- `references/design-rules.md` に「ルール5: open は grill で詰める」を追加（linear/indie byte-identical 複製）。まとめを 3 点 → 4 点に更新

## [1.28.0] - 2026-06-03

### Added
- **issue-design に writing-polish soft 連携（Phase 3.5・--embed 委譲・opt-in・未導入時 dormant）を追加**。`writing-polish` plugin 同居時のみ active。Phase 1〜3 で設計した 9 セクション本文の散文部分を Phase 4 提示直前に `Skill writing-polish:writing-polish` へ `--embed --tone issue` で渡して推敲（冗長削減・曖昧語の具体化・トーン統一・AI っぽさ除去）。9 セクション構造・`<details>` collapsible・相対パス Issue リンクは保持し、構造を壊す結果は破棄。未インストール時は完全 skip（後方互換 100%）、呼び出し失敗時は warning を出して添削前本文で完了する fallback 付き。bdd-spec bilayer の AI 層 spec.md は添削対象外

## [1.27.1] - 2026-05-29

### Changed
- **剪定 (Opus 4.7→4.8)**: `rules/project-rules.md` の「Agent Team の活用」を緩和。「大きなタスクを単一エージェントで処理することを禁止する」という強い禁止表現を「単一エージェントで抱え込まず…分割することを推奨する」に変更。Opus 4.8 は並列 tool/agent 起動を自然にデフォルト採用するため、旧モデル向けの並列化リマインダ（C-1 Model-Behavior Guard）を強制から推奨に降格（cc-catch-up Phase P 剪定レビュー）

## [1.27.0] - 2026-05-29

### Added
- **knowledge-lint に freshness 検査（項目 8: stale knowledge）を追加** (#54)。`last-validated` / `phase` の任意 frontmatter を検証し、phase 別 stale 判定（current 90日 / target 180日、superseded は対象外）を行う。fallback chain（`last-validated` → `verified` / `phase` → `status` 推定）で既存 knowledge も判定可能。未記入は warn / info に留め error にしない（transitional period）
- **knowledge-lint に glossary 用語重複検査（項目 9）を追加** (#54)。`kind: concept` + `subkind: glossary` ページ間で同一用語が複数定義される用語 SSoT 単一性違反を検出（提案のみ）。テーブル記法 / 見出し記法の 2 記法から用語エントリを抽出。既存の tags 表記ゆれ（項目 6）・重複概念（項目 7）とは対象フィールド・粒度が異なり衝突しない
- `knowledge` SKILL / `indie-issue-maintain` の `quality-checklist.md` の frontmatter スキーマに `last-validated` / `phase` / `subkind` を任意フィールドとして追記
- **issue-design に BDD bilayer モード（Phase 0.5）を追加** (#54 段階B)。`bdd-spec` plugin が同居する場合のみ active。human 層（9 セクション散文）+ AI 層（bdd-spec の `spec.md`）の二重化を opt-in で選択でき、`Skill bdd-spec:create-spec` を非対話 API（role/want/why/shortPath）で呼んで spec.md を生成。未インストール時は完全 dormant（後方互換 100%）。feature-dev Phase 1.3 と同じ連携パターン
- `_requirements` と `check-deps.sh` に `bdd-spec`（optional）を追加
- **indie-issue-maintain に Event Bus subscribe（セッションシグナル取り込み）を追加** (#54 段階C)。`.claude/events.jsonl` から `commit:created`（dev-workflow publish）・`review:completed`（code-review publish）を読み、対象 Issue に未反映の commit / レビューを反映候補として提示。Hook ではなく skill 内軽量読み出しで実装（Event Bus 規約準拠、dedup は subscriber 責務）

### Notes
- GitHub Issue #54 を段階A（freshness + glossary）/ 段階B（bilayer 連携）/ 段階C（event subscribe）に分割して実装。bdd-spec が既にカバーする user story dir / 用語 SSoT は bdd-spec 側に委譲
- **doc-freshness との住み分け**: knowledge-lint は鮮度の最小コア（`last-validated` / `phase` 検証 + stale 判定）のみ担当。行数ガード・Markdown 相対リンク検証・superseded 参照追跡は doc-freshness プラグインに委譲。閾値の外部設定は段階Aでは持たずデフォルト固定
- 段階B の bilayer は AI ハーネスの Read 制御（AI 層のみ読ませる）を AGENTS.md / CLAUDE.md 運用に委ね、plugin は spec.md 生成のみ担う

## [1.26.0] - 2026-05-29

### Added
- **Shared State 規約に準拠した frontmatter を `session-context.md` と follow-up ファイルに付与** (#35)。`shared_state_type` / `producer` / `consumers` / `schema_version` / `last_updated` を必須化し、cross-plugin で読み書きされる永続ファイルの producer-consumer 関係を明示化
- `indie-start` の Phase CTX で `.claude/session-context.md` 書き出し時に `shared_state_type: session` / `producer: indie-workflow` / `consumers: [code-review, feature-dev, dev-workflow]` を付与
- `indie-follow-up` の N5（ファイル生成）で `shared_state_type: follow-up` / `producer: indie-workflow` を付与
- consumer 側は frontmatter 不在のファイルも読める後方互換を維持（既存ファイルは段階移行）

### Notes
- Classmethod「Claude Code マルチエージェントオーケストレーションパターン」記事の Shared State パターンを軽量実装。flat な `.claude/shared/` への移行は slug-scoped 構造との衝突回避のため見送り、配置はそのままで frontmatter のみで producer/consumer を明示するアプローチを採用
- 規約定義は `CLAUDE.md` の「Shared State 規約」セクションを参照

## [1.25.0] - 2026-05-26

### Added
- **`issue-design` スキル / コマンドを新設**。Issue 本文を 9 セクションテンプレ（Why / 成果物 / 対応内容 / 完了条件 / 依存・ブロッカー / 決定事項 / 判断ポイント(open) / 参考資料 / スコープ外）と設計判断ルール（決定 vs open の境界、現時点の方向性マーカー、後続の双方向記述、確定タイミング明示）に沿って設計・構造化・リライトする。新規起票（`indie-issue-create`）・品質チェック（`indie-issue-maintain`）と責務分離
- `references/template-9sections.md` / `references/design-rules.md` を普遍 references として追加（linear-workflow と byte-identical で共有）。記法は標準 Markdown（`<details>` 折りたたみ / 相対パス Issue 参照）を採用し Linear 固有記法は持たない

## [1.24.1] - 2026-05-26

### Changed
- `knowledge` / `knowledge-lint` の description を「検索・参照（読み取り専用）」と「点検・修復（lint）」に分離し、トリガー精度を改善。`knowledge` の単独トリガー「knowledge」を外して検索文脈に限定、`knowledge-lint` に「リンク切れ」「孤立した知見」「knowledge を整理」を追加。eval（pass^k=3）で knowledge-lint を狙うプロンプトが検索用 knowledge に誤誘導される問題（2/6 → 6/6）を解消

## [1.24.0] - 2026-05-25

### Added
- **概念ページ（concept）と wikilink** を knowledge に導入。複数の個別知見（source）を `[[name]]` で横断統合する `knowledge/concepts/*.md`（`kind: concept`）を追加
- **`knowledge-lint` スキル / コマンドを新設**。broken wikilink・index 不整合・orphan concept・isolated source・tags 表記ゆれ・重複概念の 7 項目を検出し、機械的に直せるものを承認制で修正する
- `indie-issue-maintain` に**概念ページへの波及（concept 統合）**を追加。source 切り出し後、同テーマの source が 2 件以上あれば concept の新規作成 / 既存 concept への `[[ ]]` 追加を提案する
- `retrospective` に**概念ページ化の提案（Phase 2.5）**を追加。反復テーマ（複数 source に跨る共通タグ）を concept 統合の候補として提示し、承認時はドラフトを作成する
- `knowledge` スキルを concept 対応に拡張（一覧の concept/source 分離、検索・関連の `concepts/` 走査、関連表示の `[[ ]]` 1 ホップ辿り）
- `quality-checklist.md` §8 frontmatter 表に `kind` を追加、§8.1「概念ページ（concept）と wikilink」を新設
- FileChanged hook に `.claude/indie/*/knowledge/concepts/*.md` matcher を追加
- `indie-init` の生成ディレクトリに `knowledge/concepts/` を追加

### Changed
- `indie-issue-maintain` 処理フローに概念ページ波及判定を追加
- `retrospective` 処理フローに概念ページ化提案ステップ（Phase 2.5）を追加

## [1.23.0] - 2026-05-18

### Added
- `skills/retrospective/SKILL.md` の Phase 1 を Event Bus subscriber 化 (#34)。`.claude/events.jsonl` の `issue:completed` を優先入力源として使い、`event_bus_tail "issue:completed" 200` で直近の完了イベントを期間フィルタで収集。payload の `file` 経由で Issue ファイルの詳細を Read する
- 既存の「`.claude/indie/` 走査」は **Source 2** として残し、Event Bus に流れていない古い Issue や canceled の補完に使用する。events.jsonl が空でもフォールバックで動くため後方互換

### Notes
- v1.22.0 で発行を始めた `issue:completed` イベントの最初の subscriber 統合。instinct-memory の learning prompt は「Issue 完了直後」、retrospective は「週次・月次の集計」と粒度を分けて責務分離

## [1.22.0] - 2026-05-18

### Added
- `hooks/scripts/on-issue-change.sh` を Event Bus パターンに対応。FileChanged hook payload から変更ファイルを抽出し、`.claude/indie/*/issues/*.md` に `status: completed` が立った瞬間に `issue:completed` イベントを Event Bus（`.claude/events.jsonl`）に発行する
- `hooks/lib/safe-hook.sh` を v2026-05-18+ に同期。`event_bus_publish` / `event_bus_tail` / `event_bus_clear` API を取得（正本 `.claude-plugin/lib/safe-hook.sh` 由来）

### Notes
- Classmethod「Claude Code マルチエージェントオーケストレーションパターン」記事の Message Bus パターンをローカル実装する PoC publisher。将来 `retrospective` / `instinct-memory` 等の subscriber を追加できる土台

## [1.21.1] - 2026-05-15

### Changed
- `hooks/hooks.json` を `args[]` exec 形式へ移行（CC 2.1.139+）
- `safe-hook.sh` に `safe_hook_emit_bell` / `safe_hook_emit_window_title` を追加（CC 2.1.141+ terminalSequence 対応）

## [1.21.0] - 2026-05-12

### Added
- `indie-issue-maintain` に**レビューガード**を追加 (#31 C 同等)。Issue を `in-progress` → `completed` に遷移させる時、または完了サブタスク `[x]` が 3 件以上ある時に、本文・更新履歴に `self-review` / `code-review` 等のキーワードが含まれていない場合は `/self-review` 起動を提案する。feature-dev を経由しないケースでのレビュー素通り防止。type が `investigation` の Issue は実装を伴わないためスキップ
- `indie-issue-maintain` に**スコープ外差分検出**を追加 (#31 D 同等)。`git diff` で「スコープ外」「後続 Issue 候補」「やらないこと」セクションの追加箇条書き行を検出し、`/indie-follow-up new` 候補として一括 / 個別 / スキップの 3 択で提示する
- `quality-checklist.md` §10「レビューガード」と §11「スコープ外差分検出」を新規追加（発火条件、検出キーワード、選択肢、注意事項）

### Changed
- `indie-issue-maintain` SKILL.md の処理フローを 13 → 14 ステップに拡張（スコープ外差分検出ステップを knowledge 切り出し直後に追加、タスク完了時フローにレビューガード適用判定を追記）
- `indie-issue-maintain` SKILL.md / `commands/indie-issue-maintain.md` の allowed-tools に `Bash` を追加（git log / git diff でスコープ外差分を検出するため）

## [1.20.0] - 2026-04-25

### Added
- `doc-resolver` agent に親 Issue 読み込みロジックを追加。frontmatter の `parent:` を辿って親 Issue の「概要」「計画」「スコープ外」「全体進捗」を収集し、`indie-start` Phase F6 の報告に含める（linear-workflow と同等パターン）
- Issue frontmatter に `parent:` / `related_knowledge:` / `feature_dev_plan:` フィールドを追加（全4テンプレート、任意フィールドのため既存 Issue ファイルは未記入のまま動作）
- `indie-issue-create` Phase 7 の feature-dev 連携を upfront 化。「はい」選択時に Issue メタデータ + Phase 5.4 コードベース調査結果 + Phase 5.5 関連 knowledge を feature-dev に明示的に引き継ぐ prompt テンプレートを定義

### Changed
- `indie-start` Phase F3.5 の Context Recovery Agent Team 起動指示を imperative 化（Opus 4.7 対応）。「同一メッセージ内で 2 エージェント並列起動（逐次起動は禁止）」を明示
- `indie-start` Phase F6 の報告項目に「親 Issue コンテキスト」を追加

## [1.19.0] - 2026-04-23

### Added
- scope_size 超過のリアルタイム警告 hook を追加（`hooks/scripts/check-scope-size.sh`）。PostToolUse (Edit|Write|MultiEdit) で `.claude/indie/*/issues/*.md` の進捗チェックリスト数をカウントし、scope_size 上限（small:3 / medium:7 / large:15）を超過したら警告を注入。セッション末の `/indie-issue-maintain` 膨張閾値（5/8/16）とは別軸のリアルタイム初動通知 (#30)

## [1.18.3] - 2026-04-20

### Changed
- Permission Pruning に基づく allowed-tools 削減 (#28)
  - `indie-init`: 4 → 2（Read, Bash を除去。テンプレートはインラインで Write のみで完結）
  - `indie-issue-create`: 7 → 6（Agent を除去。並列起動の記述なし）
  - `indie-issue-maintain`: 7 → 6（Bash を除去。シェルコマンド未使用）
  - `retrospective`: 5 → 4（Grep を除去。本文で未使用）
  - `indie-maintain`: 本文に Glob / Grep / Edit / Write / Bash の明示参照を追加（14b PASS）
  - `indie-start`: Phase F3.7 に Grep の明示参照を追加

## [1.18.2] - 2026-04-19

### Changed
- hook スクリプト全般を `safe-hook.sh` 共通ラッパー経由に移行（check-deps / set-session-title / inject-rules / on-issue-change / on-knowledge-change） (#21)

## [1.18.1] - 2026-04-19

### Fixed
- `knowledge` スキル/コマンドの `allowed-tools` に `AskUserQuestion` と `Bash` を追加（本文で使用しているが未宣言だった）
- `indie-maintain` スキル/コマンドの `allowed-tools` に `AskUserQuestion` を追加（Phase 0/6 の選択 UI で使用）

## [1.18.0] - 2026-04-17

### Added
- retrospective Phase 2: 前回 retro との比較（最新 1 件の Try を今回の Good/Problem と照合）(#15)
- retrospective Phase 2: 反復テーマ検出（knowledge tags 集計で 2 件以上のタグを警告）(#16)
- retrospective テンプレートに「反復警告」「前回比較」セクションを追加

## [1.17.0] - 2026-04-17

### Changed
- indie-issue-maintain スコープ超過チェックを強化: 閾値（small 5+, medium 8+, large 16+）で膨張を検知し、AskUserQuestion で scope_size 更新 / タスク分割 / 現状維持を選択可能に。警告は整理計画の冒頭で最優先表示 (#13)
- indie-issue-create / indie-issue-maintain の allowed-tools を同期（Grep / AskUserQuestion 追加）

## [1.16.0] - 2026-04-17

### Changed
- indie-start ダッシュボード Phase D2: 未昇格 follow-up を件名・滞留日数付きで表示（最新 5 件）、合計 5 件超で棚卸し警告を表示 (#12)

## [1.15.0] - 2026-04-17

### Added
- indie-issue-create: Phase 5.4 コードベース現状確認ステップを追加（起票前に既存実装を Glob/Grep で確認し、実装済みなら AskUserQuestion で続行確認）(#11)
- indie-issue-create references/feature.md: 即クローズケースの書き方（結論・スコープ外・備考）を例示 (#14)
- indie-issue-maintain: 即クローズパターン検出（completed && created == last_active && [x]タスク 0 件）と経緯セクション補完提案 (#14)

## [1.14.0] - 2026-04-09

### Added
- knowledge スキル/コマンドを新規追加（`/knowledge [search <kw> | related]`）
- inject-rules.sh: SessionStart/PostCompact で knowledge/index.md をコンテキストに自動注入
- FileChanged hook: knowledge ファイルの変更を検知して通知
- project-rules.md に knowledge 活用ガイドを追加

## [1.13.0] - 2026-04-08

### Added
- UserPromptSubmit hook: feature ブランチから Issue タイトルを取得しセッション名に自動設定
- FileChanged hook: `.claude/indie/*/issues/*.md` の外部変更を検知して通知

## [1.12.0] - 2026-04-08

### Added
- indie-maintain: スキャンモード選択機能を追加（通常 / フルスキャン）
- フルスキャンモード: in-progress 含む全 Issue に indie-issue-maintain の全処理フローを一括適用
- knowledge 重複排除ロジック（複数 Issue からの同一トピック候補をマージ）
- レポートに「Issue 品質整理」セクションを追加

## [1.11.0] - 2026-04-03

### Added
- indie-follow-up スキル/コマンドを新規追加（`/indie-follow-up new|list|promote`）
- 開発中の follow-up タスクを低摩擦で記録し、後から Issue に昇格する仕組み
- project-rules.md に follow-up 自動検知ルールを追加
- indie-start: ダッシュボードモードに follow-up 件数表示を追加
- indie-start: Feature ブランチモードに follow-up 通知を追加
- indie-issue-maintain: タスク完了時に follow-up 棚卸し通知を追加
- indie-maintain: Follow-up 棚卸しフェーズを追加（14日以上放置の警告）

## [1.10.2] - 2026-03-31

### Changed
- SessionStart check-deps.sh に `once: true` 追加（セッション中1回のみ実行）
- 全エージェント（code-context, doc-resolver）に `maxTurns: 15` 追加（暴走防止）
- スキル内パス参照を `${CLAUDE_PLUGIN_ROOT}/skills/*/references/` → `${CLAUDE_SKILL_DIR}/references/` に最適化（6箇所）

## [1.10.1] - 2026-03-30

### Changed
- doc-resolver, code-context エージェントのモデルを opus → sonnet、effort を high → medium に変更（情報収集タスクの effort 最適化）

## [1.10.0] - 2026-03-29

### Changed
- indie-issue-create: AskUserQuestion の呼び出し仕様を SKILL.md に直接埋め込み（テンプレート選択・scope_size・feature-dev 連携）

### Removed
- rules/issue-create-interaction.md を削除（間接参照では LLM が AskUserQuestion を呼ばない問題の修正）
- inject-rules.sh から interaction.md の注入を削除

## [1.9.1] - 2026-03-29

### Fixed
- plugin.json から無効な agents フィールドを削除し manifest バリデーションエラーを修正

## [1.9.0] - 2026-03-29

### Added
- 全スキルに effort frontmatter を追加（indie-start/retrospective: high, indie-init: low, 他: medium）
- PostCompact hook: コンテキスト圧縮後にプロジェクトルールを再注入
- agents/ ディレクトリ: Context Recovery Agent Team を独立エージェント定義ファイルとして抽出（doc-resolver, code-context）
- plugin.json に agents フィールドを追加

## [1.8.1] - 2026-03-25

### Changed
- indie-start: Context Recovery Agent Team に model: opus を明示指定

## [1.8.0] - 2026-03-24

### Added
- indie-start: セッションコンテキスト書き出し（Phase CTX）を追加。Issue の設計判断を `.claude/session-context.md` に書き出し、code-review との連携を実現

## [1.7.0] - 2026-03-24

### Added
- indie-start: Context Recovery Agent Team を追加（既存 Issue 再開時の深いコンテキスト復元）
- indie-start: Doc Resolver エージェント（関連 Issue・Knowledge 参照解決）
- indie-start: Code Context エージェント（ソースファイル参照解決 + Git 状態取得）
- indie-start: allowed-tools に Agent を追加

## [1.6.0] - 2026-03-23

### Added
- SessionStart hook で外部依存チェック（feature-dev プラグイン）を実行
- plugin.json に `_requirements` フィールドを追加（依存メタデータ宣言）

## [1.5.0] - 2026-03-23

### Added
- indie-issue-create: テンプレート選択を AskUserQuestion による選択 UI に変更
- indie-issue-create: scope_size 選択を AskUserQuestion による選択 UI に変更
- indie-issue-create: feature-dev 連携案内を AskUserQuestion による選択 UI に変更
- rules/issue-create-interaction.md を新規追加（SessionStart hook で注入）

## [1.4.0] - 2026-03-22

### Added
- knowledge retrieval フローを追加
- feature-dev 連携案内と Agent Team ルールを追加

## [1.3.0] - 2026-03-21

### Added
- init コマンドを追加

## [1.2.0] - 2026-03-21

### Changed
- スキル名をリネームし linear-workflow との競合を解消

## [1.0.0] - 2026-03-20

### Added
- indie-workflow プラグインを新規作成
- 個人開発向けローカル Issue 管理機能
