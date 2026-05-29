# Changelog

All notable changes to feature-dev plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-05-28

### ⚠️ BREAKING CHANGES

- **`code-reviewer` agent を削除し、Phase 6 を `code-review:self-review` skill 呼び出しに置換** (#52)。同一リポジトリ内で reviewer ロジックが二重化していた DRY 違反を解消し、品質基準を `code-review` plugin の 2 軸スコアリング × 15 観点 × specialist × meta-reviewer 構造に一本化
  - **MIGRATION**: `code-review` plugin が **事実上の必須依存** になった。`plugin.json` の `_requirements` では `required: false`（プラグイン間の強制依存は claude-plugins 規約で避けるため）だが、未インストール環境では Phase 6 が **fail-fast** で停止する。先に `claude plugin install code-review@yuuki1036-claude-plugins` を実行
  - SessionStart hook (`hooks/scripts/check-deps.sh`) で code-review 未インストール時に強い warning を表示
  - 削除ファイル: `agents/code-reviewer.md`
  - 追加ファイル: `hooks/hooks.json`, `hooks/scripts/check-deps.sh`, `hooks/lib/safe-hook.sh`
  - 内蔵 agent: 3 → 2（code-explorer / code-architect のみ）

### Changed

- **Phase 6 Step 2 を self-review 呼び出しに変更**: 従来 N 体の `code-reviewer` agent を並列起動していた箇所を `Skill code-review:self-review --focus <list>` 1 回の呼び出しに集約。self-review 内部で Phase 0 triage → Phase 3/4 並列 reviewer → Phase 4.5 adaptive deepening → Phase 4.6 meta-reviewer → Phase 5 2 軸スコアリングが走る
- **Phase 6 Step 3 G-V loop の auto-fix トリガーを再定義**: 従来 `confidence ≥ 90` 単独判定だったところを、self-review の severity × confidence 出力に合わせて以下にマップ
  - `BLOCKER` (any confidence) → auto-fix 対象（最高優先度）
  - `CRITICAL && confidence ≥ 90` → auto-fix 対象（従来閾値を維持）
  - `CRITICAL && confidence < 90` / `MAJOR` / `MINOR` → 報告のみ
  - **Rationale**: BLOCKER は security/data-loss class なので confidence を問わず即修正。CRITICAL は誤検知防止のため従来の高 confidence 閾値を維持
- **Phase 6 Step 3.2 re-review** を `Skill code-review:self-review --focus <persisting> --exclude <resolved>` に変更。`--exclude` で既に解決した観点をスキップしてコスト削減
- **README.md の Agents セクションから `code-reviewer` 記述を削除**、Phase 6 説明を self-review 呼び出しベースに更新

### Migration Guide

#### v1.x → v2.0.0

**必須対応**:
1. `code-review` plugin を install: `claude plugin install code-review@yuuki1036-claude-plugins`
   - 未インストール時、SessionStart hook が warning を出す
   - Phase 6 冒頭で existence check し、未インストール時は fail-fast（Phase 5 までは正常動作）
2. Phase 6 の挙動が変わることを確認:
   - 従来: N 体 reviewer 並列起動 → confidence ≥ 90 で auto-fix
   - v2.0.0: self-review 1 回呼び出し → BLOCKER 全部 + (CRITICAL && conf ≥ 90) で auto-fix

**カスタムシナリオへの影響**:
- 手動で `code-reviewer` agent を呼んでいたコード（`Agent` tool subagent_type）は動作しなくなる → 代わりに `Skill code-review:self-review` を呼ぶ
- feature-dev の Phase 6 出力フォーマットが変わる（confidence のみ → severity × confidence）。下流で出力を parse している自動化があれば修正必要

**既知の制約**:
- self-review skill は Phase 7 で AskUserQuestion (修正方針確認) を出す設計。feature-dev からの呼び出し時は **「skip — feature-dev 側で集約します」相当の選択肢** を選んで findings を返してもらう必要あり。将来的に self-review 側へ embed mode 引数を追加する想定（別 Issue で議論）

## [1.6.1] - 2026-05-22

### Changed
- `commands/feature-dev.md` Step 3.2 の re-review launch 設定記述を修正。`effort: max` ハードコード表記を Step 2 の動的 effort (`${CLAUDE_EFFORT}`) と整合する表現に変更。Step 2 自体は元々動的展開で max ハードコードはしておらず、再 review 時の記述ミスを是正

## [1.6.0] - 2026-05-18

### Added

- **Phase 7 で `feature:implemented` イベントを発行** (#33)。`.claude/events.jsonl` に JSON Lines 1 行を直接追記する fire-and-forget publisher。payload は `{"feature":"<desc>","files_changed":<n>,"phases_completed":[...]}`
  - feature-dev は hooks/lib を持たないため、Classmethod 記事の Message Bus パターンに沿ったまま safe-hook.sh を経由せず Phase 7 内の Bash で直接書き込む方式を採用
  - subscriber がいなくても無害（既存挙動を一切変えない）。失敗しても Phase 7 全体は成功扱い

## [1.5.0] - 2026-05-17

### Added

- **Phase 6 Generator-Verifier ループ** を Step 3 として追加。reviewer が confidence ≥ 90 で出した致命指摘を自動的に Phase 5 Fix Mode に差し戻して修正、再 review、収束まで（または予算切れまで）反復する
  - Classmethod「Claude Code マルチエージェントオーケストレーションパターン」記事の Generator-Verifier パターンを「reviewer の confidence スコア」という客観基準で gate して実装
  - **effort 別ループ予算**: `low` = 0（skip）/ `medium` = 1 / `high` = 2 / `xhigh` = 3 / `max` = 3 iteration
  - **Regression 検知**: `fingerprint = file:line:focus` を `/tmp/feature-dev-loop-state.json` に蓄積し、連続 2 iteration で同一 fingerprint が残存したら自動 fix 不能と判定してループを break、ユーザに引き渡し（無限ループ防止）
  - **修正不能時の逃げ道**: メインスレッドが Edit で直接修正できない場合、`code-architect` を `delta-proposal` focus で起動して設計レベルの delta を取得（1 iteration 消費）
  - **再 review の選択性**: critical 指摘を出した reviewer focus のみを re-launch、他は再実行しない（コスト削減）
- **Phase 5 Fix Mode** を追加。Phase 6 ループから起動された場合、Phase 4 で選んだ architect 設計を維持しつつ reviewer 指摘の file:line のみピンポイント修正（スコープ拡大禁止）
- **Phase 7 G-V loop summary**: ループ実行履歴を `/tmp/feature-dev-loop-state.json` から読み取り、iteration 数 / termination reason / auto-fixed count / persisting issues を最終サマリに含める
- `references/triage-guide.md` に Section 10「Generator-Verifier ループ予算」を追加。effort 別 max_iterations / confidence 閾値 / regression 検知 / 終了条件 / fix の責務分離 / Phase 5 Fix Mode 仕様を一元的に定義

### Notes

- v1.4.0 の Phase 1.7 動的トリアージ（Orchestrator-Subagent パターンの拡張）と組み合わせて、Classmethod 記事の 2 つのパターン（Orchestrator-Subagent + Generator-Verifier）のハイブリッド構成が feature-dev でも完成。code-review プラグインが先行実装した思想を機能開発側にも展開
- `low` / `medium` effort では従来通り「critical 指摘もユーザ判断」を維持しつつ、`high` 以上で自動 fix が有効化される段階的設計

## [1.4.0] - 2026-05-17

### Added

- **Phase 1.7: Triage（動的エージェント構成決定）** を Phase 1.5 と Phase 2 の間に追加。code-review プラグインの Phase 0 トリアージパターンを移植・3 種 agent（explorer / architect / reviewer）に拡張
  - メインコンテキストで feature 要件・Issue context・プロジェクト特性（`package.json` / CLAUDE.md）を分析し、explorer / architect / reviewer の体数・focus・angle を動的決定
  - Stage 1: タイプ判定（bugfix / extension / new-feature / refactor / migration / cross-cutting）と各 agent の必要観点判定
  - Stage 2: 体数・focus・冗長度決定。effort 別上限（low/medium/high/xhigh/max）に従いキャップ
  - Phase 6 で **mini-triage 再判定**：Phase 1.7 暫定構成を実装後の diff ベースで refine（try-catch 追加で error-handling 追加、認証関連変更で security 昇格 等）
- `references/triage-guide.md` 新規作成。Phase 1.7 のロジック・体数ルール・effort 適応・フォールバック構成・最小保証を定義
- Phase 2 / 4 / 6 を「Phase 1.7 構成テーブルに従う」形式に書き換え。固定 2-3 体起動から動的体数へ移行
- Phase 2 / 4 に **partial failure tolerance** 追加。個別 agent 失敗時も成功した結果で続行、`missing_coverage` リストに記録

### Changed

- `Effort Adaptation` セクションを再構成。低レベルな「何 phase 圧縮するか」記述から、triage-guide.md Section 5 の effort 別上限テーブルへのポインタに変更
- Phase 1.5 の「Skip Phase 2」directive を「Phase 1.7 への信号送信」に変更（Phase 1.7 が 0 explorer 判定すれば結果的に Phase 2 skip）

### Notes

- Classmethod「Claude Code マルチエージェントオーケストレーションパターン」記事の `Orchestrator-Subagent` パターンに「動的トリアージ」と「mini Generator-Verifier ループ準備」を組み合わせた構成。code-review が達成済みのパターンを feature-dev に展開し、プラグイン横断で同じオーケストレーション思想を確立する第一歩
- explorer の固定 2-3 体起動 → 0-6 体動的化により、単純 bugfix では Phase 2 完全 skip で 30 秒〜1 分短縮、複雑な refactor では 5-6 体起動で多角的検証

## [1.3.0] - 2026-05-15

### Added

- `feature-dev` command に `${CLAUDE_EFFORT}` 適応分岐を追加（CC 2.1.120+）。実行時 effort に応じて 8-phase flow を圧縮・展開（low/medium: 4-phase 圧縮、high: 既定、xhigh/max: 多重 explorer + 二重 reviewer）

## [1.2.0] - 2026-05-12

### Added

- **Phase 5.5: Runtime Smoke Test** を Phase 5 (Implementation) と Phase 6 (Quality Review) の間に追加。tsc / lint / build では検知できない runtime 初期化バグ（Prisma client 初期化、env var 読み込み、middleware 設定ミス、proxy lazy-init 等）を Quality Review 前に検出する
  - Step 1: 決定的検出 — `git diff` から DB client / env var / middleware / 新規 route のパターンを grep し、smoke test が必須か任意かを判定（CLAUDE.md「決定的検証 > LLM 判定」方針に整合）
  - Step 2: `AskUserQuestion` で実行可否を確認（REQUIRED 時は実行推奨、OPTIONAL 時は skip 推奨）
  - Step 3: 既存の `dev-workflow:ui-verify` skill を呼び出して dev server 起動 + console error / network 4xx-5xx を検査（component-addition-advisor の「退路確保」原則に従い新 agent 追加せず既存資産を再利用）
  - Step 4: 失敗時は Phase 6 に進ませず修正を促す。chrome-devtools MCP 未設定時は手動確認にフォールバック（hard fail しない）
- `code-architect` agent の出力フォーマットに **Runtime Smoke Test Targets** セクションを追加。Phase 5.5 が叩く URL / route を architect 段階で明示。runtime surface に触れない変更では `none (static-only change)` を明示してスキップ判断を支援
- `commands/feature-dev.md` の `allowed-tools` に `Skill` を追加（`dev-workflow:ui-verify` 呼び出しのため）

### Notes

- Issue #29 の Prisma v7 adapter 必須化のような「全静的チェックを通過したのに初回 runtime アクセスで死ぬ」事故を構造的に予防する
- description を「7 phase」→「8 phase」に更新

## [1.1.1] - 2026-05-01

### Changed

- 全 3 agent (code-explorer / code-architect / code-reviewer) の `tools` を 10 個から 7 個に最小化。削除: `NotebookRead`（Jupyter 用途は本プラグインの主流ではない）、`KillShell`（Phase 内シーケンシャル実行で非同期タスク不要）、`BashOutput`（agent は Bash を保持しないため呼び出せず無効）。Permission Pruning の原則（claude-plugins CLAUDE.md の Hook > LLM 判定とも整合）に従い、宣言ツールを必要最小限に絞ることで判定精度を上げる

## [1.1.0] - 2026-05-01

### Changed

- `code-architect` agent のモデルを `sonnet` → `opus` に変更。設計推論・複数案比較で adaptive thinking の深さを活用する
- `code-reviewer` agent のモデルを `sonnet` → `opus` に変更。confidence ≥80 フィルタの判定精度を上げ、誤検知を最小化する
- `code-explorer` は `sonnet` 維持（並列 2-3 起動・量重視・コスト効率）

### Added

- `code-architect` system prompt に **Issue Context Injection** セクション追加。linear-workflow / indie-workflow から upfront 引き渡された Issue メタ・親 Issue サマリー・関連 knowledge・既存の `feature_dev_plan:` を設計の起点として使用する
- `code-architect` system prompt に **Hook-First Rule Placement** セクション追加。新ルール提案時に Hook → Skill/Agent → CLAUDE.md の優先順位で配置先を判定する（CLAUDE.md の決定的検証優先ルールに整合）
- `commands/feature-dev.md` に **Phase 1.5: Issue Context Detection** 追加。`Issue ファイル:` パスや `feature_dev_plan:` frontmatter を検出すると Phase 2 (Codebase Exploration) をスキップし、context を Phase 4 architect に直接引き渡す
- `commands/feature-dev.md` の frontmatter に `allowed-tools`（Bash, Read, Glob, Grep, TodoWrite, AskUserQuestion）を明示宣言（command はオーケストレーター責務、低レベル探索は agent 側に委譲）

## [1.0.1] - 2026-05-01

### Fixed

- `README.md` の Author セクションに残っていた本家元著者の連絡先を内製化後の表記に修正（quality-check の固有情報混入チェックで検出）。元著者情報は `CHANGELOG.md` の fork 経緯記述で参照する形に変更

## [1.0.0] - 2026-05-01

### Added

- claude-plugins-official/feature-dev からフォークし、yuuki1036-claude-plugins マーケットプレイス配下に取り込み
- `/feature-dev` コマンド（7 phase ワークフロー: Discovery → Codebase Exploration → Clarifying Questions → Architecture Design → Implementation → Quality Review → Summary）
- `code-explorer` agent（実行パス追跡・抽象層マッピング・依存関係分析）
- `code-architect` agent（既存パターン分析・実装ブループリント設計）
- `code-reviewer` agent（信頼度 ≥80 のみ報告するバグ・規約レビュー）

### Notes

- 本リリースは無改造の fork。本家はメタデータ未整備（version フィールド無し）のため、内製化により version 管理・linear-workflow との深い連携・モデル切り替え自由度を確保する
- 後続マイルストーンで code-reviewer と code-review プラグインの責務整理、Linear Issue メタの agent prompt 反映、モデル選択の柔軟化を検討予定
