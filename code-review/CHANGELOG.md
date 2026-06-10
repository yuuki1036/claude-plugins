# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [2.24.0] - 2026-06-10

### Changed
- **meta-reviewer (Phase 5.6 / self-review Phase 4.6) を `model: opus` → `model: fable` に変更**。全 reviewer の指摘を統合して最終判断する単一インスタンスの判断スロットに、Opus 上位ティアの Fable 5（claude-fable-5）を割り当て、知能上限を最終判定に集中させる。入力は蒸留済み findings、出力は verdict のため Fable の出力単価 2 倍（$50/1M）はトークン量で bounded。並列起動する reviewer (opus) / explorer (sonnet) はコストがボリューム × 単価で効くため据え置き。`effort: max`（adaptive thinking 前提）は維持（Fable は `thinking:{type:"disabled"}` が 400 だが本スロットは該当しない）

## [2.23.0] - 2026-06-08

### Added
- **reviewer 非レビュー出力の検知 + auto-retry**（GitHub issue #69）。`review` Step 5 / `self-review` Step 4 で各 reviewer 出力を機械検証し、`### レビュー結果` 構造と（指摘ありの場合）`[confidence][severity]` タグを欠く非レビュー出力（空応答・system-reminder / skill 案内の断片・tool_use ゼロでの早期終了）を検出したら同一プロンプトで 1 回 auto-retry。retry も非レビュー出力なら `missing_coverage` に記録して欠損観点扱いにし、フィルタ素通りを防ぐ
- **観点カバレッジ・セルフチェックの常時化**（GitHub issue #69）。`review` Step 5.7 / `self-review` Step 4.7 を新設。meta-reviewer の厳しい起動条件（effort=xhigh/max かつ高 severity あり）に依存せず、`triage-guide.md` の観点判定表を実際の diff シグナルに対してメインコンテキストで再評価し、「条件を満たすのに未起動の focus」を検出して `missing_coverage` に追記する（high effort 以上なら 1 体だけ追加起動可）。`--emergency` / `skip-mode` / `--focus`・`--exclude` 指定時はスキップ
- **`self-review` Step 1.5「Vault 照合」**（GitHub issue #68）。`kvault recall` / `/vault-recall` skill を検出（未導入なら no-op skip / 後方互換）、変更ファイルのパス・識別子・技術語で過去のレビュー指摘・落とし穴を retrieval し、`similarity` + gap で関連判断して各 reviewer に `## Vault prior findings` セクションとして注入する。`--embed` 呼び出し（feature-dev Phase 6 等）でも動作。feature-dev Phase 1.6 Vault Recall と同一 retrieval 基盤を呼ぶ対の改善

### Fixed
- **EnterWorktree 配下での `isolation:worktree` agent の二重 checkout 衝突**（GitHub issue #69）。`explorer-prompts.md` / `reviewer-prompts.md` の開始時セットアップを、`{{HEAD_REF}}` と現在 HEAD を比較して一致時は `gh pr checkout` をスキップする形に変更。親 review worktree が PR を checkout 済みのとき、子 worktree での再 checkout が "already checked out at <親worktree>" で失敗する問題を解消（fallback の `git log` 確認に頼らず衝突自体を回避）。`review` SKILL Step 4/5 のプレースホルダ注入に `{{HEAD_REF}}` を追加

### Changed
- **退行（regression）指摘の invariant 検算**（GitHub issue #69）。`reviewer-prompts.md` 共通指示に「退行指摘の invariant 検算」を追加。「旧挙動が失われた → 退行」と判断する前に、その挙動が隣接コード経路（類似関数・兄弟ハンドラ）でも一貫強制される invariant か検算し、特定経路だけの偶発的副作用（incidental）なら confidence / severity を下げる。`scoring-guide.md` の severity 調整に incidental 退行の 1 段階降格ルールを追加。単一経路の旧挙動を invariant とみなして severity を過大評価する誤判定を抑制

## [2.22.1] - 2026-06-05

### Fixed
- `check-deps.sh` の `check_mcp` が user スコープ（`claude mcp add -s user` で `~/.claude.json` の `.mcpServers` に書かれる MCP）を検知できず、設定・接続済みでも「未設定」と誤検知していた問題を修正。既存の `~/.claude/mcp.json` / `.mcp.json` の grep 近似チェックの前に、`jq` で `~/.claude.json` の `.mcpServers` を厳密に確認する処理を前置（grep ではなく `has($n)` を使うのは、`~/.claude.json` に会話ログ等が含まれ単純 grep だと無関係箇所に誤マッチするため）。github を user スコープ追加済み環境で ERROR になる誤検知を解消

## [2.22.0] - 2026-06-04

### Added
- **`modern-web-checklist.md` 同梱 reference**（Chrome [Modern Web Guidance](https://developer.chrome.com/docs/modern-web-guidance) を [Baseline](https://web.dev/baseline) ベースで照合可能にしたチェックリスト）。`ui-quality` Focus に「自前実装 → ネイティブ API 置き換え」（自前モーダル→`<dialog>`、自前ツールチップ→Popover API + Anchor Positioning、viewport メディアクエリ→Container queries 等）と **Baseline ゲート判定**（Limited availability 機能のフォールバックなし本番投入を MAJOR で検出 / widely available 化で不要になった polyfill 削除提案）を追加。ネイティブ API 化の任意改善は `Optional:` prefix・confidence ≤ 60 に抑え、好み抑制ルール（reviewer-prompts.md「好みではなく原則」+ scoring-guide の confidence クランプ）と整合させた。a11y / セマンティック HTML は既存 ui-quality 本体が担当し二重指摘しない棲み分けを明記

### Changed
- **`web-design-guidelines` 公式 skill 参照のローカル化**。`reviewer-prompts.md`（ui-quality Focus）と `triage-guide.md`（React/Next.js 判定）が参照していた `~/.agents/skills/web-design-guidelines/SKILL.md`（現環境に存在しない dangling 参照・WebFetch 前提）を、同梱の `${CLAUDE_PLUGIN_ROOT}/references/modern-web-checklist.md` に差し替え。外部 fetch 依存と参照切れを解消し、`${CLAUDE_PLUGIN_ROOT}` でポータブル化
- **`context7` の dangling skill 参照を MCP 参照に修正**。`reviewer-prompts.md`（外部ライブラリ最新仕様の確認）が参照していた `~/.agents/skills/context7/SKILL.md`（同じく現環境に存在しない dangling 参照）を、context7 MCP（`resolve-library-id` → `query-docs`）経由の記述に差し替え

## [2.21.0] - 2026-06-03

### Added
- **`--emergency` 緊急レビューモード**（Google eng-practices "Emergencies"）。`review` skill に `--emergency` 引数を追加し、本番ホットフィックス向けに reviewer-bugs + reviewer-security の最小 2 体のみで実行（explorer / 冗長ペア / Phase 5.5 / 5.6 をスキップ、specialist は red-flag 検出時のみ起動）。レポート冒頭に `⚠️ 緊急レビュー（最小構成）: マージ後に通常の /review を必ず実施すること` バナーを必須化。`triage-guide.md` に緊急モード定義（緊急の定義 / 他モードより優先 / レビューは省略しない原則）を追記
- **`self-review` の修正指針「Fix the code, not the reviewer」**（eng-practices "Handling reviewer comments"）。Step 7 の修正フローに、「分かりにくい / 誤解を招く」系の指摘は説明コメントで取り繕わずコード・命名・型・構造そのものを直して解消する原則を追加（将来の読み手も同じ箇所でつまずくため）。feature-dev Phase 6 の自動 fix にも委譲経由で波及

## [2.20.0] - 2026-06-03

### Added
- **総合判定（レビュー結論）の導出**（Google eng-practices "The Standard of Code Review" の continuous improvement 原則）。`scoring-guide.md` に「レビュー結論（総合判定）」セクションを追加し、報告マトリクス通過後の残存指摘から `Approve` / `Approve with nits` / `Needs work` を決定的に導出する（BLOCKER/CRITICAL 残 → Needs work、MAJOR/MINOR のみ → Approve with nits、ゼロ → Approve）。`review` / `self-review` のレポート冒頭に `総合判定` 行を追加。「完璧でなくともコード健全性が向上すれば Approve」とし、nit の積み残しで承認を保留しない（LGTM with comments）
- **severity プレフィックス規約**（`Nit:` / `Optional:` / `FYI:`、eng-practices "How to write code review comments"）。`reviewer-prompts.md` の出力フォーマットに、必須指摘と任意改善を著者が一目で区別できる文面マーカーを定義。MINOR 非ブロッキング → `Nit:`、任意改善 → `Optional:`、focus 外の教育的共有 → `FYI:`（related-observations に最大 2 件）。BLOCKER/CRITICAL/MAJOR の必須指摘には付けない

### Changed
- **好みベース指摘の confidence 上限クランプ**（eng-practices "principles over personal preference"）。`reviewer-prompts.md` の評価原則を 5 → 6 原則に拡張し「好みではなく原則」を追加。`scoring-guide.md` の適用順序に、CLAUDE.md / style guide / 計測データ / file:line のいずれの根拠も伴わない個人的スタイル選好は confidence を `min(値, 40)` に制限するルールを追加。LLM レビューの偽陽性（根拠なき好み指摘）を半機械的に刈り取る

## [2.19.0] - 2026-06-02

### Added
- `self-review` に **`review:completed` Event Bus publish（Step 6.4）** を追加（Workflow 監査 2026-06-01 の rollout Step3-C 計測仕込み）。embed / 非 embed の両モードで `.claude/events.jsonl` に集計を fire-and-forget で追記し、review skill と同じ `review:completed` イベントで集計を揃える。LLM 駆動 fan-out の「観点取りこぼし」「severity / confidence のパース安定性」を後から定量化するための計測データ蓄積が目的
  - `SAFE_HOOK_NAME=code-review:self-review` で publisher を識別、`pr` は `"local"` 固定。payload 規約（`missing_coverage` / `result_grid`）は review skill と同一
  - 副作用のみで標準出力にレポート文字を足さないため、embed mode の出力フォーマット（Step 6.5 の findings JSON → marker の順序）に影響しない

## [2.18.0] - 2026-06-01

### Added
- **self-review `--embed` の構造化 findings JSON 出力（schema_version: 1）**。embed mode 時に Step 6 の markdown レポート直後へ、`<!-- FINDINGS_JSON_START -->` / `<!-- FINDINGS_JSON_END -->` で囲んだ機械可読な findings ブロックを出力する（dual format）。呼び出し元（feature-dev Phase 6 等）が `severity` / `confidence` / `focus`（安定 focus キー）/ `file` / `line` / `suggested_fix` を決定的にパースでき、markdown の正規表現パース依存を解消する
  - Step 6.5 として SKILL.md にフィールド契約を明文化（findings は Step 6 報告と 1:1、`focus` は triage-guide の英語 focus キーを使用）
  - 後方互換: 非 embed 実行（`/self-review` 単独）では JSON ブロックを出力せず従来通り

## [2.17.1] - 2026-05-29

### Changed
- **剪定 (Opus 4.7→4.8)**: review / self-review SKILL.md の effort 設計意図にあった「Opus 4.7 のコーディング向け推奨設定」という stale な世代参照を更新。Opus 4.8 では `high` が既定 effort のため、オーケストレーターの `xhigh` を「demanding task 向けに一段引き上げた設定」と明記し直した。reviewer の `effort: max`（Confidence ≥80 フィルタで偽陽性を刈る意図的設計）は維持（cc-catch-up Phase P 剪定レビューで「文言更新のみ」を選択）

## [2.17.0] - 2026-05-29

### Added
- `self-review` skill に **`--embed` フラグ** を追加（GitHub issue #57）。他 plugin（feature-dev Phase 6 等）からプログラム的に呼び出される場合に、Step 7 の修正方針確認 AskUserQuestion を skip して findings をそのまま return するモード
  - `commands/self-review.md` の `argument-hint` と本文に `--embed` を反映
  - SKILL.md Step 1 の引数解説に embed mode の return 仕様（Step 6 レポート + 末尾 marker `[embed-mode: findings-only, no-prompt]`）を明文化
  - SKILL.md Step 7 冒頭に embed mode 分岐を追加（指定時は本ステップを skip）
  - 後方互換: `--embed` 未指定の `/self-review` 単独実行は従来通り Step 7 まで完走

### Notes
- 動機: feature-dev v2.0.0 (#52, commit 655987d) で Phase 6 が self-review 呼び出しに変わった際、self-review の Phase 7 AskUserQuestion がユーザー操作を 1 回追加してしまう UX 負債が残っていた。本変更で feature-dev / 将来の linear-workflow / indie-workflow 等が同じ汎用 IF で findings を集約できる

## [2.16.0] - 2026-05-28

### Fixed
- **worktree branch 継承バグ修正**（GitHub issue #56, Critical）。`isolation: "worktree"` で起動された子 worktree は親 branch を継承せず origin/default-branch から派生していたため、explorer / reviewer が古い main を見て深刻な偽陽性を量産していた（Vue プロジェクトで BLOCKER 3 件 + CRITICAL 1 件の偽陽性が観測済み）
  - `references/explorer-prompts.md` / `references/reviewer-prompts.md` の共通指示先頭に「開始時の必須セットアップ」セクションを追加。worktree 起動時は最初の Bash 呼び出しで `gh pr checkout {{PR_NUMBER}}` を実行し、`git rev-parse --abbrev-ref HEAD` で PR ブランチ名と一致することを確認する
  - `skills/review/SKILL.md` Step 4 / 5 / 5.5 / 5.6 で agent 起動箇所に PR_NUMBER と head ref の prompt 注入を必須化（`{{PR_NUMBER}}` プレースホルダを実数値に置換）
  - `skills/self-review/SKILL.md` は `isolation: "worktree"` を使わないため修正不要

### Added
- **PR 種別分岐ルール表**（GitHub issue #43, High）を `references/triage-guide.md` に追加。Stage 1 より先に `## 2.5 PR 種別分岐ルール` で doc-only / migration / lockfile / generated code 等の特殊 PR を判定し、即興構成での skill スキャフォールド無視を防ぐ
  - `doc-review-mode`: `*.md` 比率 ≥ 80% → リンク健全性・コード片安全性・構造整合性に絞った 1〜2 reviewer
  - `dba-mode`: SQL migration ファイル含む → migration reviewer + specialist-destructive-op
  - `supply-chain-mode`: lockfile 主体 → dependency reviewer 1 体に絞る
  - `skip-mode`: vendor / generated code 主体 → AskUserQuestion で確認後 spec-compliance のみ
  - `default-mode`: 上記いずれでもない場合のみ通常の Stage 1 / Stage 2 へ
- **Issue ファイル必読フロー**（GitHub issue #43, High）を `skills/review/SKILL.md` Step 1 に追加。PR head / base branch 名から `[A-Z]+-\d+` パターンで Issue ID を抽出し、`.claude/linear/` / `.claude/indie/` 配下の Issue ファイルを探索して spec-compliance reviewer の prompt に同梱する。親 Issue リンクは 1 段だけ追跡（深い再帰禁止）
- **適用モードのレポートヘッダ表示**（GitHub issue #43, Low）。レビュー結果冒頭に `[mode: doc-review, agents: [doc-reviewer]]` 形式の 1 行ヘッダを表示し、レビュー判断のコンテキストをユーザーに透明化

### Changed
- `skills/review/SKILL.md` Step 3 に Stage 0（PR 種別分岐の先行判定）を追加し、triage-guide.md `## 2.5` の参照を明示
- `plugin.json` の description を 2.16 機能反映に更新

### Notes
- issue #56 の 🟡 High 項目（既存バグ自動除外 / effort 動的調整）および 🟢 Medium 各種は本リリースのスコープ外（別 issue として残置）
- issue #43 の Medium / Low 項目のうち「出力テンプレート標準化」「gh コメント投稿フラグ」は scope creep のため別 issue として残置
- `plugin.json` の userConfig 追加（`force_checkout_pr_branch` 等）は今回スコープ外

## [2.15.0] - 2026-05-28

### Added
- `reviewer-prompts.md` の共通指示節に **評価 5 原則** を追加（GitHub issue #51）。PASS が証明されるまで FAIL / 自己交渉禁止 / 証拠ファースト / spec が真実 / 関心の分離。reviewer・specialist・meta-reviewer 全てに共通の判断基準として明文化
- `reviewer-prompts.md` に **静的検査優先の自己問い** を追加。指摘出力前に「linter / ast-grep / 型検査に落とせるか」を自問する原則を明記
- `triage-guide.md` Red-flag pattern table に **ガードレール骨抜き検出**（lint/hook/static check 設定の削除・無効化・severity 降格・適用範囲縮小・ブロック判定反転）を追加。BLOCKER 固定で `specialist-guardrail-bypass` を自動起動
- `reviewer-prompts.md` §5 Specialist テンプレートに **specialist-guardrail-bypass** を新規追加
- `review/SKILL.md` Step 4.9 と `self-review/SKILL.md` Step 3.9 に **AGENTS.md 階層動的選択** を追加。変更ファイルパスから対応する `{dir}/AGENTS.md` / `{dir}/CLAUDE.md` を遡って Glob で発見し、該当層だけを reviewer プロンプトに同梱（入力 token 30〜50% 削減）
- `review:completed` event payload に **`result_grid`** フィールドを追加（high/medium/low/skip/error の 5 値集計）。後段 hook / PR コメント自動投稿の dispatch ロジックが分岐爆発しない標準スキーマ

## [2.14.0] - 2026-05-26

### Added
- `skills/review/SKILL.md` のレポートに「良かった点」セクションを追加（Google Engineering Practices の looking-for「Good things」由来）。著者が意図的に良くした箇所を 0〜2 件、該当ファイル:行つきで具体的に挙げ、指摘偏重を避けてメンタリング効果を持たせる。中身のない称賛はノイズになるため禁止、特筆点がなければ省略。PR レビュー専用（self-review は品質ゲート用途のため対象外）

## [2.13.0] - 2026-05-25

### Added
- `self-review` skill に `--focus <観点>` / `--exclude <観点1,観点2>` 引数を追加（GitHub issue #40）。同一セッションで既に reviewer agent を走らせた後の再実行時に、既検証の観点を再報告しないようレビュー対象を絞り込み・除外できる
  - `--focus`: Phase 0 で該当観点の reviewer のみ構成（最小保証も focus に含まれない限り起動しない）
  - `--exclude`: 該当観点の reviewer を構成から外す
  - reviewer プロンプトに `review focus:` / `already verified (do not re-report):` を注入
- `commands/self-review.md` の `argument-hint` と本文に `--focus` / `--exclude` を反映

## [2.12.0] - 2026-05-19

### Added
- **Red-flag pattern による specialist 自動起動**（Idea 3-a）。triage-guide.md の `## 3 Red-flag pattern による specialist 自動起動` で diff の危険パターンを検出し、対応する specialist reviewer を Phase 0 で自動追加起動する
  - `specialist-injection`: `eval(` / `child_process` / `exec(` / `subprocess.run` / `shell=True` 等のコード/コマンドインジェクション
  - `specialist-destructive-op`: `fs.unlink` / `rm -rf` / `DROP TABLE` / `TRUNCATE` / WHERE 句なし DELETE/UPDATE 等の破壊的操作
  - `specialist-secret-handling`: `password =` / `BEGIN PRIVATE KEY` / `Bearer` / `console.log(.*token)` 等のシークレット漏洩
  - `specialist-input-validation`: `JSON.parse(req.*)` / `RegExp(user_input)` 等の信頼境界
  - specialist の指摘は大半が BLOCKER/CRITICAL になる前提で、2軸マトリクスにより低 confidence でも人間に届く設計
- **Phase 5.5 Adaptive deepening (追加 explorer ラウンド)**（Idea 1）。reviewer の `unmet_information` 申告をトリガーに、対応する re-explore explorer を 1 ラウンドだけ起動して該当 reviewer のみ再実行する
  - reviewer-prompts.md 共通指示に `## unmet_information` 出力フィールド仕様を追加。「BLOCKER 候補で context 不足」「呼び出し元全件確認が必要」等のケースのみ申告
  - explorer-prompts.md に `re-explore` フォーカステンプレートを追加。元 reviewer の why に直接回答する形式
  - 上限 3 体ずつ。失敗時は best-effort で続行
- **Phase 5.6 Meta-reviewer ラウンド**（Idea 1+3 統合）。BLOCKER または CRITICAL 検出時に、別 reviewer が「他の reviewer の見落とし観点」を探すメタレビューを 1 ラウンド実行
  - 観点の偏り検出、指摘の盲点、複合リスク、正常系の見落としを重点的に検証
  - 重複指摘禁止、追加指摘なしも健全
- **explorer 配置条件の緩和**（Idea 3-b）。共通モジュール（`utils/` / `shared/` / `lib/` / `common/` / `helpers/` / `core/`）の変更は **行数・関数数に関わらず必ず shared-module-impact explorer を 1 体起動**。小規模変更で依存元への波及を見落とすリスクを構造的に解消
- `plugin.json` の userConfig に `enable_adaptive_rounds` (boolean, default: true) と `enable_meta_reviewer` (boolean, default: true) を追加。トークンコスト・レイテンシを抑えたい場合は false に

### Changed
- `triage-guide.md` の `## 7 最小保証とフェーズ上限` に specialist 上限 6 体を追加（reviewer 枠 10 体とは別カウント）
- `triage-guide.md` に `## 8 動的ラウンド (Phase 5.5 / 5.6)` セクションを新設、effort 適応ルール表 (low/medium はスキップ、high は 5.5 のみ条件付き、xhigh/max は両方) を明文化
- `review` skill / `self-review` skill にレポート出力時の動的ラウンド可観測性を追加 (`Round 2 探索 N 体起動 / Meta-reviewer {実行 | スキップ理由}`)
- skill description / `marketplace.json` の説明を 2.12 機能反映に更新

### Notes
- effort 適応により、デフォルト effort=high では Phase 5.5 (unmet 起動時のみ) のみ動作し、Phase 5.6 はスキップ。深掘りが必要な場合は effort=xhigh / max で実行
- 動的ラウンド全体のトークンコスト増分は「unmet 申告がない場合 0」「申告ありでも追加 explorer 最大 3 + 再 reviewer 最大 3」「meta-reviewer +1」のため、保守的設計
- 本リリースは Phase B (Idea 1 + Idea 3 統合) に該当。Phase A (2軸スコアリング) は v2.11.0

## [2.11.0] - 2026-05-19

### Added
- **2 軸スコアリング** (confidence × severity) を導入。`scoring-guide.md` を全面改訂し、severity 4 段階 (BLOCKER / CRITICAL / MAJOR / MINOR) と報告マトリクスを定義。「重大だが不確実」(race condition 疑い 等) と「軽微だが確実」(typo 等) を従来の単一軸 confidence では区別できなかった構造的ジレンマを解消
  - 報告マトリクス: BLOCKER は confidence ≥ 60 で報告、CRITICAL は ≥ 80、MAJOR / MINOR は ≥ 95
  - これにより「疑わしい重大問題は人間判断を促す」「ノイズ的 nitpick は自動除外される」の非対称運用が可能に
- `reviewer-prompts.md` の共通指示に severity 必須付与を追加、出力フォーマットに `[severity: XXX]` ラベルを追加。各 Focus テンプレート (bug-detection / security / migration / performance / api-design / cross-cutting 等) に severity 目安を追加
- `plugin.json` の userConfig に `review_severity_threshold` を追加 (デフォルト: `MAJOR`)。ユーザーが報告閾値を `BLOCKER` (厳しめ) / `MINOR` (緩め) に変更可能

### Changed
- `review` skill / `self-review` skill の Phase 6 / 5 のフィルタリングロジックを 2 軸マトリクスベースに変更
- `review` skill の Step 7 出力フォーマットを severity 別グルーピング (🚨 BLOCKER / ⚠️ CRITICAL / 📋 MAJOR) に変更
- `review:completed` event payload に `blocker_count` / `major_count` / `minor_count` を追加。`critical_count` は subscriber 互換のため維持
- `self-review` skill の修正方針 AskUserQuestion を「BLOCKER/CRITICAL のみ」に変更 (旧: `confidence >= 90 のみ`)。BLOCKER 指摘を残したままコミットしようとした場合は再確認
- `review` skill の返答ドラフト生成の「重要のみ」を severity ベース (BLOCKER または CRITICAL) に変更
- `review` / `self-review` skill の description を 2 軸スコアリング対応に更新

### Notes
- **後方互換性**: severity が付与されていない reviewer 出力は CRITICAL とみなして処理されるため、移行期間中も既存挙動が維持される (旧 confidence ≥ 80 と等価)
- userConfig の `review_confidence_threshold` は後方互換のため残置 (CRITICAL severity 以下のフィルタに使用)
- 本リリースは Phase A (スコア再定義) に該当。Phase B (Idea 1+3 統合: 動的ラウンド + 検出ミス対策) は別リリース予定

## [2.10.0] - 2026-05-19

### Added
- `references/reply-tone-guide.md` を新規追加 (#37 軽量版)。レビュー後の返答ドラフトのトーン・テンプレ・禁則・パターン別ガイド（完全対応/部分対応/据置/意図確認/反証/レビュアー再返信）を集約
- `review` skill の Step 7 にレポート出力後の **返答ドラフト生成** ステップを追加（AskUserQuestion で `不要 / 重要のみ / 全件 / 個別選択` を選択、reply-tone-guide.md に従いドラフトのみ生成、投稿は手動）
- `review` skill と `commands/review.md` の allowed-tools に `AskUserQuestion` を追加

### Notes
- Issue #37 の thread skill 構想（check / reply / status）からスコープを大幅に縮小。状態管理・GitHub 投稿自動化・未対応スレッド一覧は本リリースに含めず、将来 skill 化が必要になった時点で再検討する（退路確保）
- `self-review` skill は PR コメントの返答対象がないため変更なし

## [2.9.0] - 2026-05-18

### Added
- `review` skill の Step 7（レポート出力後）に `review:completed` イベント発行を追加 (#33)。payload は `{"pr":"<number>","critical_count":<n>,"warning_count":<n>,"missing_coverage":[...]}`
  - publisher は `safe-hook.sh` の `event_bus_publish` を `SAFE_HOOK_NAME="code-review:review"` 上書きで呼び出す形式（fire-and-forget、失敗してもレポートは成功扱い）
  - retrospective / instinct-memory 等の subscriber がレビュー傾向（critical 数推移・missing_coverage の偏り）を集計できるようにするための土台

## [2.8.1] - 2026-05-18

### Changed
- `hooks/lib/safe-hook.sh` を v2026-05-18+ に同期。`event_bus_publish` / `event_bus_tail` / `event_bus_clear` API を取得（正本由来、内部ライブラリ拡張）。code-review 自身は現時点で event を発行しないが、将来 `review:completed` イベント発行用の土台として整備

## [2.8.0] - 2026-05-15

### Added
- 公式 skill 連携を 2 系統追加。
  - `ui-quality` reviewer Focus を新設し、`web-design-guidelines` 公式 skill（`~/.agents/skills/web-design-guidelines/`）のチェックリストに準拠した WCAG 違反 / セマンティック HTML 違反 / フォーカス管理 / 状態フィードバック欠落の指摘を confidence ≥ 80 で報告
  - `triage-guide.md` に UI/フロントエンド観点判定ルールを追加（`.tsx`/`.jsx`/`.vue`/`.svelte`/`components/`/`pages/`/`app/` の変更、または diff の `aria-`/`role=`/`tabindex`/`<button`/`onClick`/`onKeyDown` を検出）
- reviewer 共通指示に外部ライブラリ最新仕様確認（公式 skill `context7` 経由）を opt-in で追加。モデル学習データ cutoff を越える破壊的変更による誤判定を防止し、裏付け不能な仕様ベース指摘は confidence ≤ 75 に下げて自動除外させる

## [2.7.0] - 2026-05-15

### Added
- review SKILL.md に `${CLAUDE_EFFORT}` 適応分岐を追加（CC 2.1.120+）。実行時 effort に応じて explorer/reviewer の上限体数を自動調整（low/medium: 速度優先、high: 既定、xhigh/max: 深掘り）

### Changed
- `hooks/hooks.json` を `args[]` exec 形式へ移行（CC 2.1.139+）。シェル解釈なしでスクリプトを直接 spawn し、起動オーバーヘッドとパース起因のエッジケースを削減
- `safe-hook.sh` に `safe_hook_emit_bell` / `safe_hook_emit_window_title` を追加（CC 2.1.141+ terminalSequence 対応、opt-in 利用）

## [2.6.2] - 2026-05-13

### Added
- `code-review/scripts/fetch-pr-context.sh` を追加。PR メタ・issue コメント・レビューサマリ・行単位 review コメント（返信チェーン込み）を一括取得し、SKILL.md Step 2.5 の構造化フォーマットで markdown 出力する

### Changed
- review SKILL.md Step 1 を更新: PR 会話コンテキスト取得を `fetch-pr-context.sh` の **必須実行** に変更。LLM が個別 `gh` コマンドで組み立てる方式を禁止し、PR コメントの取りこぼしを防止
- review SKILL.md Step 2.5 を更新: スクリプト出力をそのまま PR コンテキストブロックとして使用するよう簡略化（LLM による再構築・要約・編集を禁止）

### Fixed
- review スキルで PR コメント取得がスキップされるケースを解消（取得手順をスクリプトに集約することで決定的に取得保証）

### Removed
- review / self-review の allowed-tools から未使用ツールを削除（Permission Pruning 原則に基づく最小化）
  - review: `Glob`, `Grep`, `mcp__github__pull_request_read`
  - self-review: `Glob`, `Grep`
  - 対応する commands/*.md の allowed-tools も同期

## [2.6.1] - 2026-04-25

### Changed
- `reviewer-prompts.md` の Confidence スコアリングに段階的思考誘導を追加（Opus 4.7 対応）。境界値（75-85）や他 reviewer との矛盾時に diff 意図確認・既存問題誤検知チェック・証拠裏付け確認の 3 ステップを明記

## [2.6.0] - 2026-04-24

### Added
- review スキルに PR 会話コンテキストの reviewer プロンプト注入を追加
  - `gh api repos/{owner}/{repo}/pulls/<PR>/comments` で行単位レビューコメントを取得
  - `gh pr view --json reviews` でレビューサマリを取得
  - PR 説明・issue コメントと合わせて PR コンテキストブロックとして構造化（SKILL.md Step 2.5）
- reviewer-prompts.md に「PR コンテキスト注入テンプレート」(#2.5) を追加
  - 検出ルールはタグベース: `[re-flag: @<user>]` / `[resolved: @<user>]` / `[intent-conflict]` / `[scope:out]`
  - 重複指摘の回避（既指摘かつ diff で修正済みは出力除外）
  - 著者意図の尊重（PR 説明のスコープ・意図と照合）
- scoring-guide.md にタグベースの加減算ルールを追加（正本）
  - `[re-flag: ...]`: +15（既指摘かつ diff で未修正の押し戻し）
  - `[intent-conflict]`: -20（spec-compliance の仕様違反は対象外）
  - `[resolved: ...]`: -30（PR 会話で LGTM/resolved）
  - `[scope:out]`: -50（PR 説明で明示されたスコープ外）
  - 行単位 review comment で既指摘 かつ diff で修正済み: 報告対象外
- triage-guide.md の Stage 1 に PR コンテキストによる観点追加・冗長化ロジックを追記（review skill のみ）

### Changed
- scoring-guide.md と reviewer-prompts.md の責務分離を明確化: reviewer は検出・タグ付けに集中、confidence 数値の加減算は scoring-guide.md を正本として Step 6 で適用

## [2.5.0] - 2026-04-22

### Added
- review / self-review スキルに部分失敗耐性ロジックを追加。explorer / reviewer が並列実行中に失敗しても成功した結果で合成継続し、欠損観点を最終レポートに明示する（最小保証 reviewer-bugs + reviewer-claude-md の両方失敗時のみ中止） (#25)
- self-review スキルに「Generator と分離された Evaluator」設計原則セクションを追加。dev-workflow:git-commit-helper との連携フローを明示 (#27)

## [2.4.2] - 2026-04-19

### Changed
- `check-deps.sh` を `safe-hook.sh` 共通ラッパー経由に移行（stdin 消費・エラー分類・名前付きログの統一） (#21)

## [2.4.1] - 2026-04-17

### Changed
- review/self-review の skill frontmatter effort を `max` → `xhigh` に変更（Opus 4.7 のコーディング向け新推奨設定）
- reviewer subagent の起動を `effort: max` 明示指定に変更（深い推論を優先、偽陽性は Confidence ≥80 フィルタで除去）
- effort 設計意図を SKILL.md に明文化（orchestrator: xhigh、reviewer: max の役割分担）

## [2.4.0] - 2026-04-13

### Added
- review: EnterWorktree/ExitWorktree による worktree 分離実行（レビュー中の並行作業を可能に）

### Changed
- review: `gh pr checkout` を worktree 内で実行するよう変更（作業ブランチへの影響を排除）

## [2.3.3] - 2026-04-04

### Fixed
- review/self-review スキルの description を 250 文字以内に短縮（v2.1.86 の上限対応）

## [2.3.2] - 2026-03-31

### Changed
- SessionStart check-deps.sh に `once: true` 追加（セッション中1回のみ実行）

## [2.3.1] - 2026-03-30

### Changed
- explorer のモデルを opus → sonnet に変更（情報収集タスクの effort 最適化、reviewer は opus 維持）

## [2.3.0] - 2026-03-29

### Changed
- self-review: AskUserQuestion の呼び出し仕様を SKILL.md に直接埋め込み（修正方針選択 + 後処理）

### Removed
- rules/self-review-interaction.md を削除（間接参照では LLM が AskUserQuestion を呼ばない問題の修正）

## [2.2.1] - 2026-03-29

### Fixed
- userConfig.review_confidence_threshold に type/title を追加し manifest バリデーションエラーを修正

## [2.2.0] - 2026-03-29

### Added
- 全スキルに effort frontmatter を追加（review/self-review: max）
- userConfig: review_confidence_threshold でレビュー閾値をカスタマイズ可能に

## [2.1.0] - 2026-03-26

### Added
- Phase 0 トリアージ: diff 分析による動的エージェント構成決定（Stage 1 タイプ判定 → Stage 2 体数・フォーカス・冗長度決定）
- explorer エージェントタイプ: 事実収集特化（function-flow, dependency-trace, branch-impact, history-context, shared-module-impact）、上限 6 体
- reviewer 冗長化: 対象コードの複雑さに応じて同一観点を複数体（angle 違い）で起動、上限 10 体
- spec-compliance 観点: session-context / Issue / knowledge との仕様整合性チェック
- references/triage-guide.md: Phase 0 判定ロジック・パターンマトリクス・フォールバック構成
- references/explorer-prompts.md: explorer プロンプトテンプレート集
- references/reviewer-prompts.md: 観点別 reviewer プロンプトテンプレート集（現行 #1-#16 から移行・再構成）
- scoring-guide: explorer 裏付け (+10)、冗長ペア合意 (+10)、冗長ペア片方のみ (-5) ルール追加

### Changed
- 固定2フェーズ構成（Phase 1 固定6+条件2 → Phase 2 動的8）を廃止し、Phase 0 トリアージ → 探索 → レビューの動的3フェーズ構成に移行
- CLAUDE.md 準拠チェック: 冗長2体 → Phase 0 判断で 1-2 体（複雑さに応じた冗長化）
- diff-first 原則を改訂: 変更箇所を含む関数の全体確認・類似名称の確認を Read 許可用途に追加

### Removed
- references/agent-prompts.md: 3ファイル（triage-guide, explorer-prompts, reviewer-prompts）に分割移行

## [2.0.0] - 2026-03-25

### Added
- 2フェーズレビュー構成: Phase 1 (コアレビュー) → Phase 2 (専門レビュー動的起動)
- Phase 2 専門エージェント8種: セキュリティ(OWASP)、パフォーマンス、API設計、依存関係、マイグレーション、設定、クロスカッティング影響、パターン統一
- Phase 2 起動判定: diff パターンマッチ（静的）+ Phase 1 結果からの動的判定
- Phase 2 スキップ条件: 小規模かつ懸念なしの場合は Phase 1 のみで完了

### Changed
- 全エージェントを `model: opus` で起動（品質最大化）
- scoring-guide: 複数エージェント同一指摘の加算を +10 → +15 に引き上げ
- scoring-guide: Phase 2 専門エージェント関連のスコアリングルールを追加

## [1.5.0] - 2026-03-25

### Changed
- review: diff 取得を `git diff` から `gh pr diff` に変更（ローカル状態に依存しない）
- review: 全エージェントを `isolation: "worktree"` で起動（PR ブランチの正しい状態でファイルを読む）
- review: diff-first 原則を追加（diff が真のソース、ファイル Read はコンテキスト確認のみ）
- Agent #3: ファイル全文分析→依存先の仕様確認のみに限定

## [1.4.0] - 2026-03-24

### Added
- self-review/review: セッションコンテキスト読み込み（Step 2.5）を追加。`.claude/session-context.md` から Issue の設計判断を取得し、エージェントプロンプトに注入
- scoring-guide: セッションコンテキストによるスコア減算ルールを追加（設計判断一致: -30、スコープ外: -50）

## [1.3.0] - 2026-03-23

### Added
- SessionStart hook で外部依存チェック（GitHub MCP）を実行
- plugin.json に `_requirements` フィールドを追加（依存メタデータ宣言）

## [1.2.0] - 2026-03-23

### Added
- self-review: レポート出力後に修正方針選択ステップ（Phase 6）を追加
- rules/self-review-interaction.md を新規追加

## [1.1.1] - 2026-03-23

### Fixed
- スキル description のトリガーフレーズを「トリガー:」形式に統一

## [1.1.0] - 2026-03-21

### Fixed
- プラグイン品質改善
- 全プラグインの品質問題を一括修正

## [1.0.0] - 2026-03-20

### Added
- code-review プラグインを新規作成
- 並列エージェントによる PR レビュー / セルフレビュー機能
