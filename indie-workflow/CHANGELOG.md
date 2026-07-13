# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.40.1] - 2026-07-13

### Fixed
- **未import knowledge 検知の `--project` 引数を修正**（issue #86 のセルフレビュー指摘）。vault 側 `unimported_scan.py` の `--project` は「巡回パス（`~/Projects` 等配下の `.claude/{indie,linear}/{slug}/{knowledge,concepts}` 絶対パス）に対する部分文字列フィルタ」で、cwd プロジェクトに絞る用途。旧実装は `.claude/indie/{slug}/knowledge` を渡していたため、単一 slug の knowledge のみ一致し他 slug・`concepts` の fresh を取りこぼして恒常的に過少カウントしていた。`basename "$PWD"`（プロジェクトのディレクトリ名）を渡す形に修正し、当該プロジェクト配下の全 slug の knowledge/concepts を集計する（linear-workflow 1.37.1 とミラー対称）

## [1.40.0] - 2026-07-12

### Added
- **indie-issue-maintain に「未import knowledge の検知」ステップを追加**（issue #86）。knowledge 切り出しの反映先である横断 vault への `/import-knowledge` は手動トリガーで忘れやすいため、切り出し直後（責務的に最も自然な発火位置）で未import件数を検知して促す:
  - feature-dev Phase 1.6 と同じ detect→skip パターン。`KNOWLEDGE_VAULT_ROOT` + vault 側検知 CLI（`_shared/scripts/unimported_scan.py`）の二段で存在確認し、いずれか欠けたら静かに skip（vault を持たないマシンで壊れない後方互換）
  - 現プロジェクトの knowledge dir を `--project` に、`--count` で fresh 件数だけ取得（frontmatter 突合のみで軽量・実測 0.4s）。N>0 のときだけ最終レポートで `/import-knowledge` を推奨（AskUserQuestion では止めない）
  - linear-workflow 1.37.0 とミラー対称

## [1.39.0] - 2026-07-10

### Added
- **indie-issue-create Phase 5.5 を「関連ナレッジの検索」に拡張**（issue #80）。knowledge のみだった検索対象を knowledge / ADR / 完了 Issue の 3 種に広げ、起票時に「この問題を過去に解いた・判断したことがないか」を grep で自動推奨する（蓄積→活用の導線を閉じる）:
  - **完了 Issue**: `issues/*.md` を grep し `status: completed` / `canceled` のものを類似判断として抽出（未完了 Issue の重複起票チェックとは目的が別なので completed / canceled に絞る）
  - **ADR**: adr-keeper 導入時のみ `.claude/adr/*.md` を grep（未導入なら skip・dormant）
  - 検索は grep ベースの安価な絞り込みのみで embedding・環境依存は持ち込まない（ファネル先頭）。見つからなければ何も追記せずノイズを出さない
  - feature-dev への引き継ぎ prompt の見出しも「関連ナレッジ（knowledge / ADR / 完了 Issue）」に更新

## [1.38.2] - 2026-07-08

### Changed
- `indie-issue-create` Phase 8 の判定表を再構成: WHAT/HOW/WHY の 3 軸コアを `ROUTING-AXES:START/END` マーカー区間として正本 `.claude-plugin/lib/routing-axes.md` と同期（quality-check が dedent 比較で Critical 検証）。type 別の追加判定（bugfix/investigation/debt → 不要）は区間外の「type 別の追加判定」表に分離（ワークフロー固有・同期対象外）。判定内容は不変・spec-advisor / linear-workflow とドリフトしない機械保証を追加（linear-workflow 1.35.2 とミラー対称。設計判断: `.claude/designs/20260708-spec-routing-ssot.md`）

## [1.38.1] - 2026-07-07

### Fixed
- `indie-issue-maintain` の writing-polish 連携節に `Skill` tool 呼び出しの明示を復帰。1.38.0 の references 分割で呼び出し詳細を writing-polish-integration.md に移した際、SKILL.md 本文から `Skill` の言及が消え、frontmatter の `Skill` 宣言が未使用候補として検出されていた（ツール自体は reference 経由で使用中）。本文に「`Skill` tool で `writing-polish:writing-polish` を呼ぶ」を戻して宣言と本文を整合

## [1.38.0] - 2026-07-07

### Added
- **深掘り系スキル 3 本に `${CLAUDE_EFFORT}` 実行時分岐を追加**（ルート CLAUDE.md「深掘り系スキルには effort 分岐必須」規約への準拠）:
  - `indie-maintain`: 走査深度の effort 適応（low/medium=検出・集計系のみ、high=全処理フル、xhigh/max=knowledge 重複排除の全プロジェクト横断 + 品質整理の全セクション精読）。「起動＝実行確定・止まらない」は effort 不変
  - `retrospective`: 分析深度の effort 適応（low/medium=定量指標 + 前回比較のみ、high=全実施、xhigh/max=反復テーマの source 本文精読まで）
  - `issue-design`: grill の掘り下げの effort 適応（low/medium=充足確認中心で残 open は 1 回提示、high=依存順 1 問ずつ、xhigh/max=畳み直し周回増 + 決定事項の根拠再点検）。linear-workflow と byte-identical なミラー実装

### Changed
- **`indie-issue-maintain` SKILL.md を references/ に分割**（491→298 行）。整理判定基準（cleanup-criteria.md）・検出ガード（detection-guards.md）・knowledge 管理（knowledge-guide.md）・writing-polish 連携手順（writing-polish-integration.md）を切り出し、本文は高レベルワークフローに絞った。挙動の変更なし
- `indie-maintain` に **writing-polish 連携を対象外とする設計判断を明記**（出力が機械的な status 遷移と実行後レポートのみで散文成果物を生成しないため。散文を生成する indie-issue-maintain / indie-issue-create 側は必須連携済み）

## [1.37.0] - 2026-07-02

### Added
- **linear-workflow から `updated` 鮮度フィールド機構を移植**（双子 drift 解消）。knowledge の frontmatter に `updated`（最終更新日）を必須フィールドとして追加し、切り出し時は当日・編集時は必ず書き換える運用ルールを明文化（`indie-issue-maintain` SKILL.md / `references/quality-checklist.md §8`）。`indie-start` Phase F3.7 に stale 判定を追加し、`updated` が 60 日を超えた関連 knowledge に `⚠️ stale?` マーカーを付けて古い知見への引きずられを防ぐ。stale 判定の fallback chain を `knowledge-lint` の正本（`last-validated → updated → verified`）に統一（`knowledge` SKILL.md / `quality-checklist.md` の記述が `last-validated → verified` で `updated` を欠いていた矛盾を解消）
- **破壊的変更パターン検出を移植**。`indie-issue-maintain` の knowledge 切り出し手順の最優先ステップとして、破壊的変更 / API rename / 非推奨化 / バージョン跨ぎ移行 / 実機検知バグ / 衝突 / 仕様変更のキーワード検出を追加（`quality-checklist.md §7.1` にキーワード表・推奨 tags 対応表・🔴 報告フォーマット）。取りこぼしやすい高再利用価値の知見を通常基準より優先して切り出す。処理フローに検出ステップ（7.5）を追加
- **レビューガードの検出キーワード一覧を移植**（`quality-checklist.md §10`）。従来は「本文にキーワードが含まれていない」とだけ書かれ判定基準が曖昧だったのを、セルフレビュー / PR レビュー / Agent 起動のカテゴリ別キーワード表で明示
- **feature-dev 引き継ぎ prompt に「親 Issue」セクションを移植**。`indie-issue-create` Phase 7 の upfront 引き継ぎテンプレに、frontmatter の `parent:` がある場合の親 Issue サマリー引き継ぎ行を追加（linear-workflow と同等）
- `indie-init` / `project-doc-template.md` に **タイプ別サマリー**表を新設（feature / bugfix / investigation / debt を集計）
- `quality-checklist.md` のオプションフィールドに `frozen_date: YYYY-MM-DD` を定義（`indie-maintain` の frozen 再評価が参照するが未定義だった）

### Changed
- **concept frontmatter スキーマを統一**。概念ページの frontmatter を `kind / source / status / verified / updated / tags` に揃え（`updated` を追加）、波及で既存 concept を編集したら `updated` を当日日付に更新する運用を明記（`indie-issue-maintain` SKILL.md / `quality-checklist.md §8.1`）
- **project.md ステータスサマリーから type の `debt` を分離**。`indie-init` / `indie-maintain`（SKILL.md の処理内容・出力レポート）/ `project-doc-template.md` のステータスサマリーを status 5 値（`backlog` / `in-progress` / `frozen` / `completed` / `canceled`）に揃え、`debt`（type）はタイプ別サマリーに分離
- `quality-checklist.md §4` の frontmatter `status` 列挙を `in-progress | completed` から正式 5 値に修正し、`scope_size` を feature テンプレ必須フィールドとして明記（テンプレは必須なのに checklist がオプション扱いだった矛盾を解消）
- **採番順序ルールを 3 スキルで統一**。`indie-issue-create`（Phase 3）・`indie-follow-up`（Phase P5）を discover と同じ「採番先確定（先に `counter.txt` を +1 して Write）」方式に揃え、中断時の ID 重複・上書きを防ぐ
- `check-deps.sh` を linear 版の errors / warnings 分離構造に揃え、`required=true` 分岐が `warnings` に `[ERROR]` を混ぜないようにした（将来 required 依存を追加した際に正しく分離される）

### Fixed
- `retrospective` の allowed-tools に `AskUserQuestion` を追加（Phase 2.5 の概念ページ化提案・Phase 3 の振り返りフレームで使用しているが未宣言だった。command 側も同期）
- `indie-issue-discover` Phase 5 の手順番号が `1,2,3,4,4,6` と重複・欠番していたのを `1〜6` に振り直し
- `inject-rules.sh` の放置 Issue 検知を、検出 0 件のときはセクションごと省略するよう変更（従来は 0 件でも「## 放置 Issue 検知 / (なし)」を毎回注入していた）。あわせて、`status:` 等の行を欠く不正な issue ファイルがあると `set -euo pipefail` 下で grep の exit 1 が代入に伝播しフック全体がサイレント終了していた潜在バグを修正（`status`/`last_active`/`id` 抽出に `|| true` を付与）
- `commands/indie-issue-discover.md` の余分な `name:` frontmatter を削除し、`argument-hint: "[PROJECT-SLUG]"` を追加
- `README.md` を実態に更新（スキル表 7 → 11 件、コマンド表 7 → 11 件、ディレクトリ構造に follow-ups/ ・knowledge/concepts/ ・retrospectives/ を追加、リポジトリ方針に反する MIT ライセンス表記を削除）

## [1.36.0] - 2026-07-01

### Added
- `indie-issue-discover` に **Phase 4.5「独立検証」**を新設し、誤検知起票を起票前に落とすようにした（Clearwing 原則 7 + 8）。起票候補（上位 N 件）だけを対象に、(1) 外部オラクル（型チェック / lint を候補ファイルに絞って実行し、赤なら証拠強度を昇格）と (2) 敵対的独立検証（新 agent `discover-verifier` を `model: opus` で起動。**発見者の rationale を渡さず** evidence だけ渡して REAL / NOT-INTENDED / NOT-HANDLED / IMPACTFUL の 4 軸で判定）を実施。4 軸すべて YES かつ確信度 ≥60 のときだけ起票し、それ以外・曖昧・agent 失敗時は起票せず backlog に降格する（fail-closed）。検証は上位 N 件限定・effort 傾斜（low/medium は上位のみ、high 以上は全 N 件）でコスト暴走を防ぐ
- 候補スキーマに `evidence_level`（suspected / static-confirmed / verified）を追加し、優先度・起票可否・自動起票注記に反映（証拠ラダー）
- 新 agent `discover-verifier`（Read/Grep、model: opus）を追加

### Changed
- Phase 3 のスキャン `Agent`（Explore）に `model: sonnet` 明示を推奨（モデルルーティング: 探索=安モデル / 検証=強モデル。ルート CLAUDE.md「コスト×精度パイプライン設計指針」準拠）
- Phase 7 レポートに「証拠強度」列と「検証で起票見送り」セクションを追加

## [1.35.1] - 2026-06-28

### Fixed
- `indie-issue-create` のテンプレート 4 ファイル（bugfix / feature / investigation / debt）の `status` コメントの値列挙を `indie-maintain` の正式定義（`backlog` / `in-progress` / `frozen` / `completed` / `canceled`）に揃えた。従来は `in-progress / completed / canceled` のみで `backlog` / `frozen` が欠落しており、`indie-issue-discover` が起票する `status: backlog` や `indie-maintain` が扱う `frozen` がテンプレ上は未定義の状態だった

## [1.35.0] - 2026-06-27

### Added
- `indie-issue-discover` スキル / コマンドを追加。プロジェクトを多観点（バグ兆候・未実装スタブ・FE 改善余地・テスト欠落・既存シグナル集約）でスキャンし、取り組むべき課題を AI が能動的に発見して indie issue を自動起票する。「次に何をやるか」を人間が考える負担を AI に移譲するのが狙い
  - 「起動＝実行確定」maintain 系に準拠。止まらずスキャン → 自動起票 → 実行後レポートまで進める（AskUserQuestion で止めない）
  - 暴走防止の三点セット: 起票上限 N（既定 5・`${CLAUDE_EFFORT}` で可変）/ `status: backlog` で起票（放置検知の誤爆防止 + 着手判断を人に残す）/ 既存 issue・backlog との重複除外
  - 起票は `indie-issue-create` のテンプレート・採番・writing-polish 連携を再利用、再発失敗の集計は failure-journal の `failure:logged` イベントを再利用（重複実装しない）。実装着手は feature-dev に接続
  - スキャン対象＝起票先＝起動したリポジトリ（クロスリポジトリ起票はしない）

## [1.34.1] - 2026-06-27

### Fixed
- `inject-rules.sh` の排他警告を `.claude/linear` ディレクトリ同居判定に変更（#74）。従来の `grep '"linear-workflow@' settings.json` はキー存在のみを見ており、無効化（`":false"`）でも文字列が残って誤検知し、project-scoped 有効化を取りこぼしていた。実際にトリガー衝突しうるのは両ワークフローのデータが同一プロジェクトに同居する時だけなので、ディレクトリ存在を唯一のシグナルにした

## [1.34.0] - 2026-06-27

### Changed
- maintain 系スキル（`indie-maintain` / `indie-issue-maintain`）の実行前 AskUserQuestion を全廃し「起動＝実行確定」に統一。ユーザーが起動した時点で実行意思は確定しているとみなし、選択 UI で ChatTool を奪わず止まらず最後まで実行する（ストレスフリー設計）
  - `indie-maintain`: 起動時のスキャンモード選択を撤去し、**常時フルスキャン**で実行。放置 Issue・frozen Issue・follow-up の対処は AskUserQuestion で止めず最終レポートに列挙し、判断はユーザーがチャットで指示。承認待ちを廃し実行後レポートで一括報告
  - `indie-issue-maintain`: スコープ超過警告・レビューガードを非ブロッキング化（レポート列挙に留める）、削除候補・knowledge/concept 切り出し・整理計画の事前承認を撤去し実行後報告に変更。スコープ外 follow-up 候補は副作用回避のため自動記録せずレポート列挙に留める
  - `indie-maintain` / `indie-issue-maintain` の allowed-tools から `AskUserQuestion` を除去（command 側も同期）
- Issue ファイルは git 管理下のため、無確認実行でも不要な変更は git で復元できる旨を各注意事項に明記

## [1.33.1] - 2026-06-26

### Fixed
- `indie-issue-maintain` の follow-up 一括/個別記録時の参照を `indie-follow-up` の Phase N5（完了報告）から Phase N4（ファイル生成）に修正（ファイル生成手順を指すべき箇所が誤って完了報告フェーズを指していた既存の参照ズレ）

## [1.33.0] - 2026-06-26

### Added
- issue 作業の全散文成果物（indie-issue-create / issue-design / indie-issue-maintain・indie-follow-up・retrospective・knowledge 切り出し）に writing-polish embed 連携を必須化。各 skill の本文確定・ユーザー提示の直前に `Skill` tool で `writing-polish:writing-polish` を `--embed --tone {issue|review}` で通す（`writing-polish` 未インストール時のみ skip。frontmatter / 見出し階層 / wikilink / テンプレート構造は保全）。indie-issue-maintain・indie-follow-up・retrospective の allowed-tools に `Skill` を追加（command 側も同期）
- `rules/project-rules.md` に「文章の推敲（writing-polish 必須）」セクションを追加し、`.claude/indie/` 配下の管理ファイルだけでなくコードコメント・README・設計ドキュメント等あらゆる散文を確定前推敲の対象とする広域ルールを明文化

### Changed
- `issue-design` の Phase 3.5 writing-polish 連携を opt-in から必須に強化（`writing-polish` がインストールされていれば必ず通し、未インストール時のみ skip）

## [1.32.2] - 2026-06-25

### Added
- `hooks/scripts/inject-rules.sh`（SessionStart/PostCompact）に linear-workflow 共存検知を追加。両プラグインが同時に有効な場合、同名スキル（作業開始 / 知見 / プロジェクト整理 等）のトリガー衝突を警告する（settings.json を読むだけでプラグイン間依存はなし。排他運用を機械的にリマインド）

## [1.32.1] - 2026-06-25

### Fixed
- `hooks/scripts/inject-rules.sh` の stale Issue 判定が `date -j`（BSD/macOS 専用）依存で、Linux では全 in-progress Issue を「7日以上未更新」と誤検知していたのを修正。GNU date フォールバック（`date -d`）を追加し、パース不能な `last_active` は判定スキップ
- `indie-issue-maintain` の Event Bus subscriber 手順が payload に存在しない `issue_id` / `file path` 前提で書かれていたのを、実 payload（`commit:created`=sha/type/files、`review:completed`=pr）から関連性を導出する記述に修正
- `indie-issue-maintain` が参照する `references/feature.md` のパスが解決不能だったのを、実在する `indie-issue-create` 側への相対パスに修正
- `issue-design` の bdd-spec 委譲キャプションの version 直書き（v0.1.0）を撤去

## [1.32.0] - 2026-06-24

### Added
- **indie-issue-create に spec 選択フェーズ（仕様化ルーティング）を追加（Phase 8・opt-in）**。Issue 作成・ブランチ作成後、実装着手前に「どの仕様を先に書くか」を type と Issue の性質から自動推奨し、確信度が高ければ根拠 1 文で進み、迷うときだけ AskUserQuestion で確認する（自動推奨 → 低確信時のみ手動）。WHAT=bdd-spec / HOW=design-doc / WHY=adr-keeper / 不要 の 4 択（debt は「不要 or 移行が大きいなら design-doc」）で、**導入済みの spec プラグインのみ選択肢化**し、選択を `Skill` tool で委譲する。仕様系プラグインが 1 つも無ければ完全に skip（dormant・後方互換 100%）、feature-dev 引き継ぎ経路は WHAT/HOW を feature-dev が内部生成するため到達しない。dormant 判定・`(Recommended)`・fallback は issue-design Phase 0.5 と同じパターン。indie-start Phase F7 に着手時の spec 案内（案内のみ）を追記
- `indie-issue-create` の allowed-tools に `Skill` を追加（command 側も同期）。`_requirements` / `check-deps.sh` に adr-keeper（required: false）を追加し、bdd-spec / design-doc の用途記述に indie-issue-create spec 選択を追記

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
