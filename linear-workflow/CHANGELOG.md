# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.35.2] - 2026-07-08

### Changed
- `issue-create` Phase 5 の判定表を再構成: WHAT/HOW/WHY の 3 軸コアを `ROUTING-AXES:START/END` マーカー区間として正本 `.claude-plugin/lib/routing-axes.md` と同期（quality-check が dedent 比較で Critical 検証）。type 別の追加判定（bugfix/investigation/debt → 不要）は区間外の「type 別の追加判定」表に分離（ワークフロー固有・同期対象外）。判定内容は不変・spec-advisor / indie-workflow とドリフトしない機械保証を追加（設計判断: `.claude/designs/20260708-spec-routing-ssot.md`）

## [1.35.1] - 2026-07-07

### Fixed
- `issue-maintain` の writing-polish 連携節に `Skill` tool 呼び出しの明示を復帰（indie-workflow 1.38.1 とミラー対称）。1.35.0 の references 分割で SKILL.md 本文から `Skill` の言及が消え、frontmatter の `Skill` 宣言が未使用候補として検出されていた問題を解消

## [1.35.0] - 2026-07-07

### Added
- **深掘り系スキル 2 本に `${CLAUDE_EFFORT}` 実行時分岐を追加**（ルート CLAUDE.md「深掘り系スキルには effort 分岐必須」規約への準拠。indie-workflow 1.38.0 とミラー対称）:
  - `linear-maintain`: 走査深度の effort 適応（low/medium=同期・検出系のみ、high=全処理フル、xhigh/max=全チーム横断 + 品質整理の精読）。「起動＝実行確定・止まらない」は effort 不変
  - `issue-design`: grill の掘り下げの effort 適応。indie-workflow と byte-identical なミラー実装

### Changed
- **`issue-maintain` SKILL.md を references/ に分割**（449→280 行）。整理判定基準（cleanup-criteria.md）・検出ガード（detection-guards.md）・knowledge 管理（knowledge-guide.md）・writing-polish 連携手順（writing-polish-integration.md）を切り出し、本文は高レベルワークフローに絞った（indie-issue-maintain とミラー対称の references 構造）。挙動の変更なし
- `linear-maintain` に **writing-polish 連携を対象外とする設計判断を明記**（出力が機械的な status 遷移と実行後レポートのみで散文成果物を生成しないため。散文を生成する issue-maintain / issue-create 側は必須連携済み）

## [1.34.0] - 2026-07-02

### Added
- indie-workflow に先行実装されていた機能を移植し双子間 drift を解消:
  - **debt テンプレート**（`issue-create/references/debt.md`）と type ルーティング。follow-up の `debt → bugfix` ワークアラウンドを廃止
  - **Phase 2.4 コードベース現状確認**（手動入力起票時の重複起票防止。Glob/Grep で既存実装・既存 Issue を確認）
  - **即クローズパターンの検出**（`issue-maintain`。起票即クローズ Issue の経緯保全）
  - **feature-dev 引き継ぎの親 Issue セクション**（`issue-create`）

### Fixed
- **`last_active` 死にフィールドを解消**: dashboard の放置警告・context-agents が参照するのに誰も書いていなかった。テンプレ必須フィールド化 + `issue-maintain` の整理時に更新する仕組みを追加
- `doc-resolver` agent と `session-start/references/context-agents.md` に indie 側の改善を反映（`parent:` 空値スキップ / 関連 Issue 抽出で parent 参照済み ID 除外 / `related_knowledge:` 配列読み込み）
- concept frontmatter に `source` を追加し `kind/source/status/verified/updated/tags` に統一（SKILL.md テンプレと quality-checklist §6 の乖離を解消）
- `quality-checklist` §4 のフロントマター必須フィールドを実テンプレに同期（status に `canceled`、type に `debt`、`last_active` を追加）
- `linear-maintain` の allowed-tools に `Write` を追加（knowledge 切り出し＝新規ファイル作成に必要。skill/command 両方）
- `session-start` の allowed-tools に `Skill` を追加（Phase N4 で issue-create スキルを実行するため。skill/command 両方）
- `follow-up` frontmatter の `consumers` を `[linear-workflow]` に修正（排他運用の indie-workflow を除去）

## [1.33.1] - 2026-06-27

### Fixed
- `inject-rules.sh` の排他警告を `.claude/indie` ディレクトリ同居判定に変更（#74）。従来の `grep '"indie-workflow@' settings.json` はキー存在のみを見ており、無効化（`":false"`）でも文字列が残って誤検知し、project-scoped 有効化を取りこぼしていた。実際にトリガー衝突しうるのは両ワークフローのデータが同一プロジェクトに同居する時だけなので、ディレクトリ存在を唯一のシグナルにした

## [1.33.0] - 2026-06-27

### Changed
- maintain 系スキル（`linear-maintain` / `issue-maintain`）の実行前 AskUserQuestion を全廃し「起動＝実行確定」に統一。ユーザーが起動した時点で実行意思は確定しているとみなし、選択 UI で ChatTool を奪わず止まらず最後まで実行する（ストレスフリー設計）
  - `linear-maintain`: 起動時の実行可否確認（続行/中断）とスキャンモード選択を撤去し、**常時フルスキャン**で実行。Linear MCP 未検出時はフォールバックせず中断（MCP 同期が主機能のため意味がない）。承認待ちを廃し実行後レポートで一括報告
  - `issue-maintain`: レビューガード（完了マーク前）を非ブロッキング化（警告はレポートに出すが処理は止めない）、削除候補・knowledge/concept 切り出し・整理計画の事前承認を撤去し実行後報告に変更。スコープ外 follow-up 候補は副作用回避のため自動記録せずレポート列挙に留める
  - `issue-maintain` の allowed-tools から `AskUserQuestion` を除去（command 側も同期）
- Issue ファイルは git 管理下のため、無確認実行でも不要な変更は git で復元できる旨を各注意事項に明記

## [1.32.0] - 2026-06-26

### Added
- issue 作業の全散文成果物（issue-create / issue-design / issue-maintain・follow-up・knowledge 切り出し）に writing-polish embed 連携を必須化。`writing-polish` がインストールされていれば確定前に必ず `--embed --tone issue` で推敲を通す（未インストール時のみ skip。構造を壊す結果は破棄）。`Skill` を issue-maintain / follow-up の allowed-tools（command 側も同期）に追加
- `rules/project-rules.md` に「文章の推敲（writing-polish 必須）」セクションを追加し、`.claude/linear/` 配下の管理ファイルだけでなくコードコメント・README・設計ドキュメント等あらゆる散文を対象化（gitignore 対象かどうかは問わない）

### Changed
- `issue-design` の Phase 3.5（writing-polish 連携）を opt-in → 必須に強化

## [1.31.2] - 2026-06-25

### Added
- `hooks/scripts/inject-rules.sh`（SessionStart/PostCompact）に indie-workflow 共存検知を追加。両プラグインが同時に有効な場合、同名スキル（作業開始 / 知見 / プロジェクト整理 等）のトリガー衝突を警告する（settings.json を読むだけでプラグイン間依存はなし。排他運用を機械的にリマインド）

## [1.31.1] - 2026-06-25

### Fixed
- `issue-maintain` の Event Bus subscriber 手順が payload に存在しない `issue_id` / `file path` 前提で書かれていたのを、実 payload（`commit:created`=sha/type/files、`review:completed`=pr）から関連性を導出する記述に修正
- `init` のトリガーフレーズ「セットアップ」「init」が claude-code-setup / worktree-setup / 組込 `/init` と語幹衝突していたのを Linear 領域語で限定
- `issue-design` の bdd-spec 委譲キャプションの version 直書き（v0.1.0）を撤去

### Notes
- トリガーフレーズ変更のため `evals/runner.py` での回帰確認を推奨

## [1.31.0] - 2026-06-24

### Added
- **issue-create に spec 選択フェーズ（仕様化ルーティング）を追加（Phase 5・opt-in）**。Issue 作成後・実装着手前に「どの仕様を先に書くか」を type と Issue の性質から自動推奨し、確信度が高ければ根拠 1 文で進み、迷うときだけ AskUserQuestion で確認する（自動推奨 → 低確信時のみ手動）。WHAT=bdd-spec / HOW=design-doc / WHY=adr-keeper / 不要 の 4 択で、**導入済みの spec プラグインのみ選択肢化**し、選択を `Skill` tool で委譲する。仕様系プラグインが 1 つも無ければ完全に skip（dormant・後方互換 100%）、feature-dev 引き継ぎ経路は WHAT/HOW を feature-dev が内部生成するため到達しない。dormant 判定・`(Recommended)`・fallback は issue-design Phase 0.5 と同じパターン。session-start Phase N6 に着手時の spec 案内（案内のみ）を追記
- `issue-create` の allowed-tools に `Bash` / `Skill` を追加（command 側も同期）。`_requirements` / `check-deps.sh` に adr-keeper（required: false）を追加し、bdd-spec / design-doc の用途記述に issue-create spec 選択を追記

## [1.30.0] - 2026-06-15

### Changed
- **共通 skill の description に作用範囲を明記（トリガー衝突解消）**。linear-workflow と indie-workflow は排他だが両方インストール可能なため、共通 skill（knowledge / knowledge-lint / issue-design）の description 冒頭に「Linear 連携プロジェクトの」という弁別語を追加し、スキル選択の弁別性を高めた。command 側の同名コマンドの description も command↔skill ペア一致規約に従って揃えた（既存トリガーフレーズは維持）
- **session shared_state の consumers 宣言を実態に修正**。session-start の `.claude/session-context.md` 雛形 frontmatter の `consumers` を `[code-review, feature-dev, dev-workflow]` から、実際に読み出す実装がある `[code-review]` のみに修正
- **FileChanged 通知を additionalContext 化**。on-issue-change.sh / on-knowledge-change.sh の FileChanged hook で Claude に届けたい指示を plain stdout（`safe_hook_emit`）から `safe_hook_emit_context "FileChanged" ...`（v2.1.163+ の `hookSpecificOutput.additionalContext`）に置き換え、到達保証を高めた。stderr ログ・`event_bus_publish` は従来どおり維持

## [1.29.0] - 2026-06-11

### Added
- **issue-design に design doc への昇格判断を追加（design-doc 連携・opt-in）**。Phase 2 の open 仕分けで、タスク 1 件を超えた設計判断（複数 Issue にまたがる方式選定、Issue 本文で持ちきれないトレードオフ比較）を検知したら、design-doc プラグインへの切り出しを AskUserQuestion で提案する。切り出した doc のリポジトリ内パスを「参考資料」に記録し、該当 open は「確定タイミング: design doc で確定」に書き換える。未インストール時は従来どおり Issue 内 grill に dormant（後方互換 100%、indie-workflow と同一実装）
- `_requirements` / `check-deps.sh` に design-doc（required: false）を追加

## [1.28.1] - 2026-06-05

### Fixed
- `check-deps.sh` の `check_mcp` が user スコープ（`claude mcp add -s user` で `~/.claude.json` の `.mcpServers` に書かれる MCP）を検知できず、設定・接続済みでも「未設定」と誤検知していた問題を修正。既存の `~/.claude/mcp.json` / `.mcp.json` の grep 近似チェックの前に、`jq` で `~/.claude.json` の `.mcpServers` を厳密に確認する処理を前置（grep ではなく `has($n)` を使うのは、`~/.claude.json` に会話ログ等が含まれ単純 grep だと無関係箇所に誤マッチするため）。dev-workflow / code-review / notebooklm-workflow と共通の修正

## [1.28.0] - 2026-06-03

### Added
- **issue-design の open 仕分けに grill プロセス（design-rules.md ルール5）を追加**。Phase 2 で open を独断列挙して終えず、コミット前に 1 つずつ詰める: ①既存 ADR / 他 Issue / コードで決着済みかを `Grep` / `knowledge` /（adr-keeper があれば）`adr` で自己確認し決着済みは決定事項へ移す ②残った open を依存順に `AskUserQuestion` で 1 問ずつ・「現時点の方向性」を推奨案として `(Recommended)` 付きで確認 ③「おまかせ」は推奨で確定。open が 1〜2 個かつ方向性明確なら圧縮（過剰質問抑制）。Matt Pocock "grill-me" / Brooks『The Design of Design』の design tree に由来
- `references/design-rules.md` に「ルール5: open は grill で詰める」を追加（linear/indie byte-identical 複製）。まとめを 3 点 → 4 点に更新

## [1.27.0] - 2026-06-03

### Added
- **issue-design に writing-polish soft 連携（Phase 3.5）を追加**。`writing-polish` plugin が同居する場合のみ active。Phase 1〜3 で設計した 9 セクション本文の散文部分を、ユーザー提示（Phase 4）の直前に `Skill writing-polish:writing-polish` へ `--embed --tone issue` で委譲して推敲（冗長削減・曖昧語の具体化・トーン統一・AI っぽさ除去）。9 セクション構造・Linear collapsible（`+++`）・Issue リンクは保持し、構造を壊す結果は破棄して元案を使う。bdd-spec bilayer の AI 層 spec.md は添削対象外。未インストール時は本 Phase を完全に skip し従来動作（dormant・後方互換 100%）。bdd-spec dormant 連携（Phase 0.5）と同じパターン

## [1.26.1] - 2026-05-29

### Changed
- **剪定 (Opus 4.7→4.8)**: `rules/project-rules.md` の「Agent Team の活用」を緩和。「大きなタスクを単一エージェントで処理することを禁止する」という強い禁止表現を「単一エージェントで抱え込まず…分割することを推奨する」に変更。Opus 4.8 は並列 tool/agent 起動を自然にデフォルト採用するため、旧モデル向けの並列化リマインダ（C-1 Model-Behavior Guard）を強制から推奨に降格（cc-catch-up Phase P 剪定レビュー）

## [1.26.0] - 2026-05-29

### Added
- **knowledge-lint に freshness 検査（項目 8: stale knowledge）を追加** (#54)。`last-validated` / `phase` の任意 frontmatter を検証し、phase 別 stale 判定（current 90日 / target 180日、superseded は対象外）を行う。fallback chain（`last-validated` → `updated` → `verified` / `phase` → `status` 推定）で既存 knowledge も判定可能。未記入は warn / info に留め error にしない（transitional period）
- **knowledge-lint に glossary 用語重複検査（項目 9）を追加** (#54)。`kind: concept` + `subkind: glossary` ページ間で同一用語が複数定義される用語 SSoT 単一性違反を検出（提案のみ）。テーブル記法 / 見出し記法の 2 記法から用語エントリを抽出。既存の tags 表記ゆれ（項目 6）・重複概念（項目 7）とは対象フィールド・粒度が異なり衝突しない
- `knowledge` SKILL / `issue-maintain` の `quality-checklist.md` の frontmatter スキーマに `last-validated` / `phase` / `subkind` を任意フィールドとして追記
- **issue-design に BDD bilayer モード（Phase 0.5）を追加** (#54 段階B)。`bdd-spec` plugin が同居する場合のみ active。human 層（9 セクション散文）+ AI 層（bdd-spec の `spec.md`）の二重化を opt-in で選択でき、`Skill bdd-spec:create-spec` を非対話 API（role/want/why/shortPath）で呼んで spec.md を生成。未インストール時は完全 dormant（後方互換 100%）。feature-dev Phase 1.3 と同じ連携パターン
- `_requirements` と `check-deps.sh` に `bdd-spec`（optional）を追加
- **issue-maintain に Event Bus subscribe（セッションシグナル取り込み）を追加** (#54 段階C)。`.claude/events.jsonl` から `commit:created`（dev-workflow publish）・`review:completed`（code-review publish）を読み、対象 Issue に未反映の commit / レビューを反映候補として提示。Hook ではなく skill 内軽量読み出しで実装（Event Bus 規約準拠、dedup は subscriber 責務）

### Notes
- GitHub Issue #54 を段階A（freshness + glossary）/ 段階B（bilayer 連携）/ 段階C（event subscribe）に分割して実装。bdd-spec が既にカバーする user story dir / 用語 SSoT は bdd-spec 側に委譲
- **doc-freshness との住み分け**: knowledge-lint は鮮度の最小コア（`last-validated` / `phase` 検証 + stale 判定）のみ担当。行数ガード・Markdown 相対リンク検証・superseded 参照追跡は doc-freshness プラグインに委譲。閾値の外部設定は段階Aでは持たずデフォルト固定
- 段階B の bilayer は AI ハーネスの Read 制御（AI 層のみ読ませる）を AGENTS.md / CLAUDE.md 運用に委ね、plugin は spec.md 生成のみ担う

## [1.25.0] - 2026-05-29

### Added
- **Shared State 規約に準拠した frontmatter を `session-context.md` と follow-up ファイルに付与** (#35)。`shared_state_type` / `producer` / `consumers` / `schema_version` / `last_updated` を必須化し、cross-plugin で読み書きされる永続ファイルの producer-consumer 関係を明示化
- `session-start` の Phase CTX で `.claude/session-context.md` 書き出し時に `shared_state_type: session` / `producer: linear-workflow` / `consumers: [code-review, feature-dev, dev-workflow]` を付与
- `follow-up` の N5（ファイル生成）で `shared_state_type: follow-up` / `producer: linear-workflow` を付与
- consumer 側は frontmatter 不在のファイルも読める後方互換を維持（既存ファイルは段階移行）

### Notes
- Classmethod「Claude Code マルチエージェントオーケストレーションパターン」記事の Shared State パターンを軽量実装。flat な `.claude/shared/` への移行は slug-scoped 構造との衝突回避のため見送り、配置はそのままで frontmatter のみで producer/consumer を明示するアプローチを採用
- 規約定義は `CLAUDE.md` の「Shared State 規約」セクションを参照

## [1.24.0] - 2026-05-26

### Added
- **`issue-design` スキル / コマンドを新設**。Issue 本文を 9 セクションテンプレ（Why / 成果物 / 対応内容 / 完了条件 / 依存・ブロッカー / 決定事項 / 判断ポイント(open) / 参考資料 / スコープ外）と設計判断ルール（決定 vs open の境界、現時点の方向性マーカー、後続の双方向記述、確定タイミング明示）に沿って設計・構造化・リライトする。新規起票（`issue-create`）・品質チェック（`issue-maintain`）と責務分離し、トリガーは規範・設計系に限定して create との誤起動を回避
- `references/template-9sections.md`（9 セクション定義・コピペ雛形）/ `references/design-rules.md`（設計判断ルール）を普遍 references として追加。両者は indie-workflow と byte-identical で共有する正本
- `references/linear-syntax.md`（collapsible `+++` / `<issue id>` リンク / インライン pros/cons）を Linear 固有 references として追加

## [1.23.1] - 2026-05-26

### Changed
- `knowledge` / `knowledge-lint` の description を「検索・参照（読み取り専用）」と「点検・修復（lint）」に分離し、トリガー精度を改善。`knowledge` の単独トリガー「knowledge」を外して検索文脈に限定、`knowledge-lint` に「リンク切れ」「孤立した知見」「knowledge を整理」を追加。eval（pass^k=3）で knowledge-lint を狙うプロンプトが検索用 knowledge に誤誘導される問題（2/6 → 6/6）を解消

## [1.23.0] - 2026-05-25

### Added
- **概念ページ（concept）と wikilink** を knowledge に導入。複数の個別知見（source）を `[[name]]` で横断統合する `knowledge/concepts/*.md`（`kind: concept`）を追加し、繋いで初めて見える構造を蓄積できるようにした
- **`knowledge-lint` スキル / コマンドを新設**。broken wikilink・index 不整合（stale / 未登録）・orphan concept・isolated source・tags 表記ゆれ・重複概念の 7 項目を検出し、機械的に直せるもの（index 同期・確定 broken link 張替）を承認制で修正する。意味の統合は提案に留める
- `issue-maintain` に**概念ページへの波及（concept 統合）**を追加。source 切り出し後、同テーマの source が 2 件以上あれば concept の新規作成 / 既存 concept への `[[ ]]` 追加を提案する
- `knowledge` スキルを concept 対応に拡張（一覧の concept/source 分離、検索・関連の `concepts/` 走査、関連表示の `[[ ]]` 1 ホップ辿り）
- `quality-checklist.md` §6 frontmatter 表に `kind` を追加、§6.1「概念ページ（concept）と wikilink」を新設
- FileChanged hook に `.claude/linear/*/knowledge/concepts/*.md` matcher を追加（concept ファイルの外部変更検知）
- `init` の生成ディレクトリに `knowledge/concepts/` を追加

### Changed
- `issue-maintain` 処理フローを 12 → 13 ステップに拡張（概念ページ波及判定を追加）

## [1.22.0] - 2026-05-18

### Added
- `hooks/scripts/on-issue-change.sh` を Event Bus パターンに対応。FileChanged hook payload から変更ファイルを抽出し、`.claude/linear/*/issues/*.md` に `status: completed` が立った瞬間に `issue:completed` イベントを Event Bus（`.claude/events.jsonl`）に発行する
- `hooks/lib/safe-hook.sh` を v2026-05-18+ に同期。`event_bus_publish` / `event_bus_tail` / `event_bus_clear` API を取得（正本 `.claude-plugin/lib/safe-hook.sh` 由来）

### Notes
- Classmethod「Claude Code マルチエージェントオーケストレーションパターン」記事の Message Bus パターンをローカル実装する PoC publisher。将来 `retrospective` / `instinct-memory` 等の subscriber を追加できる土台

## [1.21.1] - 2026-05-15

### Changed
- `hooks/hooks.json` を `args[]` exec 形式へ移行（CC 2.1.139+）
- `safe-hook.sh` に `safe_hook_emit_bell` / `safe_hook_emit_window_title` を追加（CC 2.1.141+ terminalSequence 対応）

## [1.21.0] - 2026-05-12

### Added
- `issue-maintain` に**レビューガード**を追加 (#31 C)。Issue を `in-progress` → `completed` に遷移させる時、または完了サブタスク `[x]` が 3 件以上ある時に、本文・更新履歴に `self-review` / `code-review` 等のキーワードが含まれていない場合は `/self-review` 起動を提案する。feature-dev を経由しないケースでのレビュー素通り防止。type が `investigation` の Issue は実装を伴わないためスキップ
- `issue-maintain` に**スコープ外差分検出**を追加 (#31 D)。`git diff` で「スコープ外」「後続 Issue 候補」「やらないこと」セクションの追加箇条書き行を検出し、`/follow-up new` 候補として一括 / 個別 / スキップの 3 択で提示する。既存の follow-up 自動検知（会話中シグナル）とは独立した Issue ファイル更新タイミングでの差分検出軸
- `quality-checklist.md` §8「レビューガード」と §9「スコープ外差分検出」を新規追加（発火条件、検出キーワード、提示フォーマット、注意事項）

### Changed
- `issue-maintain` SKILL.md の処理フローを 11 → 12 ステップに拡張（スコープ外差分検出ステップを knowledge 切り出し直後に追加、タスク完了時フローにレビューガード適用判定を追記）
- `issue-maintain` SKILL.md / `commands/issue-maintain.md` の allowed-tools に `AskUserQuestion` を追加（レビューガード / スコープ外差分検出のユーザー提示のため）

## [1.20.0] - 2026-05-05

### Added
- `issue-maintain` の knowledge 切り出しに**破壊的変更パターン検出**を追加 (#31 A)。Issue 本文・進捗・更新履歴から「破壊的変更 / breaking change」「rename された / renamed to」「deprecated / 非推奨」「v\d+ → v\d+」「dead element / 空振り / lint は通るが」「衝突する / 配列順序」「実機テストで判明 / ランタイムで発覚」を Grep ベースで検出し、tags 候補（`library-compat`, `breaking-change`, `migration`, `gotcha`, `runtime-only`, `static-check-blind-spot` など）と共に y/n 提案する。ライブラリのバージョン跨ぎや実機検知バグといった再利用価値の高い知見の取りこぼしを防ぐ
- `quality-checklist.md` §5.1「破壊的変更パターンの自動検出」を新規追加（検出キーワード一覧、tags 対応表、ユーザー提示フォーマット）
- knowledge frontmatter に `updated: YYYY-MM-DD` フィールドを必須化 (#31 B 前提)。新規切り出し時は当日、編集時は必ず書き換える運用ルールを `quality-checklist.md` §6 に明記
- `session-start` Phase N3.7 に**鮮度判定（stale チェック）**を追加 (#31 B)。関連 knowledge の `updated` フィールドを読み取り、60 日以上経過していれば `⚠️ stale?` マーカーを付与して報告する。古い knowledge に引きずられて誤った設計を採るリスクを下げる（自動除外はせず、最終判断はユーザー）

### Changed
- `issue-maintain` SKILL.md の knowledge 切り出しフローを 6 ステップ → 7 ステップに拡張（破壊的変更検出を最優先ステップとして追加）。処理フローも 10 → 11 ステップに更新
- `quality-checklist.md` §6 の knowledge frontmatter 仕様に `updated` フィールドを追加。既存ファイルに `updated` がない場合は次回編集時に追加するルールに統一（遡及修正は不要）

## [1.19.0] - 2026-04-25

### Added
- Issue frontmatter に `related_knowledge:` / `feature_dev_plan:` フィールドを追加（feature / bugfix / investigation の 3 テンプレート、`feature_dev_plan:` は feature のみ）。Phase 2.5 で参照した knowledge と feature-dev が生成した計画ファイルへの逆リンクを保持する
- `issue-create` Phase 4 の feature-dev 連携を upfront 化。「はい」選択時に Issue メタデータ + Linear URL + Phase 2.5 関連 knowledge + 親 Issue サマリーを feature-dev に明示的に引き継ぐ prompt テンプレートを定義（Opus 4.7 の upfront specification 原則に整合）

## [1.18.4] - 2026-04-25

### Changed
- `session-start` Phase N3.5: Context Recovery Agent Team の起動指示を imperative 化（Opus 4.7 対応）。「同一メッセージ内で 3 エージェントを並列起動（逐次起動は禁止）」を明示し、各エージェントの入力も箇条書きで明示化

## [1.18.3] - 2026-04-20

### Changed
- Permission Pruning に基づく allowed-tools 削減 (#28)
  - `session-start`: 9 → 8（`mcp__linear__list_comments` を除去。該当処理は Agent subagent 側で完結）
  - `linear-maintain`: 11 → 10（`Write` を除去。既存ファイル更新のみで新規作成なし）
  - `linear-maintain`: 本文に `get_issue` / `list_issue_statuses` の明示参照を追加（14b 検証のため）

## [1.18.2] - 2026-04-19

### Changed
- hook スクリプト全般を `safe-hook.sh` 共通ラッパー経由に移行（check-deps / set-session-title / inject-rules / on-issue-change / on-knowledge-change） (#21)

## [1.18.1] - 2026-04-19

### Fixed
- `dashboard` スキル/コマンドの `allowed-tools` に `AskUserQuestion` を追加（本文で使用しているが未宣言だった）
- `knowledge` スキル/コマンドの `allowed-tools` に `AskUserQuestion` と `Bash` を追加（`git branch --show-current` と選択 UI のため）

## [1.18.0] - 2026-04-09

### Added
- knowledge スキル/コマンドを新規追加（`/knowledge [search <kw> | related]`）
- inject-rules.sh: SessionStart/PostCompact で knowledge/index.md をコンテキストに自動注入
- FileChanged hook: knowledge ファイルの変更を検知して通知
- project-rules.md に knowledge 活用ガイドを追加

## [1.17.0] - 2026-04-08

### Added
- UserPromptSubmit hook: feature ブランチから Issue タイトルを取得しセッション名に自動設定
- FileChanged hook: `.claude/linear/*/issues/*.md` の外部変更を検知して通知

## [1.16.0] - 2026-04-08

### Added
- linear-maintain: スキャンモード選択機能を追加（通常 / フルスキャン）
- フルスキャンモード: in-progress 含む全 Issue に issue-maintain の全処理フローを一括適用
- knowledge 重複排除ロジック（複数 Issue からの同一トピック候補をマージ）
- レポートに「Issue 品質整理」セクションを追加

## [1.15.1] - 2026-04-04

### Fixed
- session-start/issue-maintain スキルの description を 250 文字以内に短縮（v2.1.86 の上限対応）
- init スキルのパス参照を `${CLAUDE_PLUGIN_ROOT}` → `${CLAUDE_SKILL_DIR}` に最適化

## [1.15.0] - 2026-04-03

### Added
- follow-up スキル/コマンドを新規追加（`/follow-up new|list|promote`）
- 開発中の follow-up タスクを低摩擦で記録し、後から Issue に昇格する仕組み
- project-rules.md に follow-up 自動検知ルールを追加
- session-start: Quick Pick モードに follow-up 件数表示を追加
- dashboard: Phase D2.5 Follow-up サマリーを追加
- issue-maintain: タスク完了時に follow-up 棚卸し通知を追加
- linear-maintain: Follow-up 棚卸しフェーズを追加（14日以上放置の警告）

## [1.14.1] - 2026-03-31

### Changed
- SessionStart check-deps.sh に `once: true` 追加（セッション中1回のみ実行）
- 全エージェント（code-context, doc-resolver, linear-sync）に `maxTurns: 15` 追加（暴走防止）
- スキル内パス参照を `${CLAUDE_PLUGIN_ROOT}/skills/*/references/` → `${CLAUDE_SKILL_DIR}/references/` に最適化（7箇所）

## [1.14.0] - 2026-03-30

### Added
- 全 Linear MCP 使用スキル（init, dashboard, linear-maintain, issue-create, session-start）に Phase 0: MCP 利用可能性チェックを追加
- MCP 未検出時に AskUserQuestion で「続行 / 中断」を提示し、ユーザーが選択できるように

## [1.13.1] - 2026-03-30

### Changed
- doc-resolver, code-context, linear-sync エージェントのモデルを opus → sonnet に変更（情報収集タスクの effort 最適化）
- doc-resolver, code-context の effort を high → medium に変更

## [1.13.0] - 2026-03-29

### Changed
- issue-create: AskUserQuestion の呼び出し仕様を SKILL.md に直接埋め込み（テンプレート選択・feature-dev 連携）

### Removed
- rules/issue-create-interaction.md を削除（間接参照では LLM が AskUserQuestion を呼ばない問題の修正）
- inject-rules.sh から interaction.md の注入を削除

## [1.12.1] - 2026-03-29

### Fixed
- plugin.json から無効な agents フィールドを削除し manifest バリデーションエラーを修正

## [1.12.0] - 2026-03-29

### Added
- 全スキルに effort frontmatter を追加（session-start: high, dashboard: low, init: low, 他: medium）
- PostCompact hook: コンテキスト圧縮後にプロジェクトルールを再注入
- agents/ ディレクトリ: Context Recovery Agent Team を独立エージェント定義ファイルとして抽出（doc-resolver, code-context, linear-sync）
- plugin.json に agents フィールドを追加

## [1.11.0] - 2026-03-25

### Added
- dashboard: 新規スキル/コマンドとして切り出し（フルダッシュボード + スコープドダッシュボード）
- session-start: main ブランチ用 Quick Pick モード（軽量タスク選択）
- session-start: 親 Issue 軽量サマリーモード（詳細は `/dashboard` に委譲）

### Changed
- session-start: ダッシュボード機能を `/dashboard` に分離し、session-start を軽量化
- session-start: Context Recovery Agent Team に model: opus を明示指定

## [1.10.0] - 2026-03-24

### Added
- session-start: セッションコンテキスト書き出し（Phase CTX）を追加。Issue の設計判断を `.claude/session-context.md` に書き出し、code-review との連携を実現

## [1.9.0] - 2026-03-24

### Added
- session-start: Context Recovery Agent Team を追加（既存 Issue 再開時の深いコンテキスト復元）
- session-start: Doc Resolver エージェント（親 Issue・関連 Issue・Knowledge 参照解決）
- session-start: Code Context エージェント（ソースファイル参照解決 + Git 状態取得）
- session-start: Linear Sync エージェント（Linear API 最新状態との差分検出）
- session-start: allowed-tools に Agent, mcp__linear__list_comments を追加

## [1.8.0] - 2026-03-23

### Added
- SessionStart hook で外部依存チェック（Linear MCP、feature-dev プラグイン）を実行
- plugin.json に `_requirements` フィールドを追加（依存メタデータ宣言）

## [1.7.1] - 2026-03-23

### Fixed
- Linear API の書き込み（save_issue 等）をユーザーの明示的な指示なしに実行しないようルールを追加
- 「Issue更新」がローカル Issue ファイルの更新を意味することをスキル説明に明記

## [1.7.0] - 2026-03-23

### Added
- issue-create: テンプレート選択を AskUserQuestion による選択 UI に変更
- issue-create: feature-dev 連携案内を AskUserQuestion による選択 UI に変更
- rules/issue-create-interaction.md を新規追加（SessionStart hook で注入）

## [1.6.0] - 2026-03-23

### Added
- session-start: ダッシュボードモードを追加（フル / スコープド）
- session-start: Next Issue ピック機能を追加
- session-start: allowed-tools に mcp__linear__list_issues を追加

## [1.5.0] - 2026-03-22

### Added
- knowledge retrieval フローを追加
- feature-dev 連携案内と Agent Team ルールを追加

## [1.4.0] - 2026-03-21

### Added
- init コマンドを追加

## [1.3.0] - 2026-03-20

### Added
- SessionStart hook によるプロジェクト管理ルール自動注入を追加

## [1.2.0] - 2026-03-20

### Added
- CLAUDE.md 軽量化に向けたスキル強化

### Fixed
- プラグイン品質改善
- プロジェクト固有の情報を汎用的な例に置換
- スキルのトリガーフレーズを改善
- 全プラグインの品質問題を一括修正

## [1.0.0] - 2026-03-20

### Added
- linear-workflow プラグインを新規作成
- Linear MCP 連携の Issue/プロジェクト管理機能
