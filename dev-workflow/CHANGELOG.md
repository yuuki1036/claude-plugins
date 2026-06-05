# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.19.1] - 2026-06-05

### Fixed
- `check-deps.sh` の `check_mcp` が user スコープ（`claude mcp add -s user` で `~/.claude.json` の `.mcpServers` に書かれる MCP）を検知できず、設定・接続済みでも「未設定」と誤検知していた問題を修正。既存の `~/.claude/mcp.json` / `.mcp.json` の grep 近似チェックの前に、`jq` で `~/.claude.json` の `.mcpServers` を厳密に確認する処理を前置（grep ではなく `has($n)` を使うのは、`~/.claude.json` に会話ログ等が含まれ単純 grep だと無関係箇所に誤マッチするため）。`~/.claude/mcp.json` 不在環境で chrome-devtools が WARN になる誤検知を解消

## [1.19.0] - 2026-06-03

### Added
- `git-commit-helper` の `staging-patterns.md` に **subject 行（description）の品質規約** を追加（Google eng-practices "Writing good CL descriptions"）。subject はそれ単体で変更内容が分かる完結文にする原則と、`fix: バグ修正` / `fix: build` / `chore: 対応` / `refactor: いろいろ整理` / `docs: 修正` などの曖昧 subject 禁止例カタログ（改善例つき）を明文化。git log / version history に単独で残る subject の検索性を高める

## [1.18.1] - 2026-06-03

### Changed
- `git-commit-helper` の分割判定（Step 2）に **コミット粒度と PR 粒度の 2 層モデル** を明記。コミットは原子分割（実装コミットとテストコミットを分ける）しつつ、レビュー単位（PR）の中では実装とテストを揃え、テストだけを別 PR に切り出さない self-contained 原則を追記（Google eng-practices "Small CLs: include related test code"）。`git-commit-helper`（「実装とテストを必ず分割」）と `pr-creator`（「テストだけ別 PR に切り出さない」）の見かけ上の不整合を解消

## [1.18.0] - 2026-06-03

### Added
- `pr-creator` / `git-commit-helper` に **writing-polish soft 連携**（opt-in）を追加。`pr-creator` Step 4.3 で PR 本文(description)を、`git-commit-helper` Step 4.2 でコミットメッセージ description を、ユーザー提示/コミット実行の直前に `writing-polish:writing-polish` へ `--embed` 委譲して推敲する（`--tone pr` / `--tone commit`）。`$HOME/.claude/settings.json` の `"writing-polish@` 有無で判定し、未導入時は本ステップを完全に skip して従来動作を維持（dormant・後方互換 100%）。推敲結果が各スキルの厳守ルール（PR テンプレート構造 / `<type>(<scope>):` prefix / AI 署名禁止 等）に違反する場合は破棄し元案を使う
- `pr-creator` / `git-commit-helper` の SKILL.md および対応 command（`commands/pr.md` / `commands/commit.md`）の `allowed-tools` に `Skill` を追加（上記委譲呼び出し用）

## [1.17.0] - 2026-05-29

### Added
- **PostToolUse 自動 lint チェーン**（#53）。`hooks/scripts/post-format-lint.sh` が Edit|Write|MultiEdit で発火し、`fmt-fix → lint-fix → check` の 3 段を実行。fix 段は黙って直し、check 段で残った違反だけを `decision:"block"` で Claude に返す。**opt-in**（`.claude/dev-workflow.json` の `lint.enabled=true` 時のみ動作、未設定は完全 dormant）
- `hooks/lib/json-block.sh`: `emit_block_json` 共通フォーマッタ。block 出力 JSON を一元化し、check 出力は `head -20` + 総行数注記で context 浪費を防止
- `hooks/lib/path-guard.sh`: `path_guard_is_excluded`（node_modules / dist / build / vendor / lock 等を早期除外）と `path_guard_ext`（拡張子抽出）
- `references/lint-config.md`: `.claude/dev-workflow.json` の lint 設定スキーマ・3 段チェーン・既知の制約を明記

### Changed
- `skills/pr-creator/SKILL.md` の厳守ルールに **本文量の bullet 上限を数値化**（概要 1〜2 文 / 変更点 1〜5 bullet / レビューポイント 1〜3 件）を追加。質的記述だけだと冗長化するため数値で制限（#53）

### Notes
- #53 の「agent-neutral hook 化」は既に exec 形式 + bash 外出し済みのため対応不要（破壊的移行なし）。「worktree-setup / teardown skill」は v1.16.0 で実装済み。Codex 互換テンプレ配布は実需要が出るまで見送り

## [1.16.0] - 2026-05-28

### Added
- `worktree-setup` skill: git worktree ベースの並列開発環境セットアップ。3 状態マトリクス（main / worktree-ready / worktree-unconfigured）で分岐し、`GIT_DIR != GIT_COMMON_DIR` + env マーカー（`envs/.backend.env.worktree`）で冪等判定。DB 名 / port を worktree 名から動的割当。references に state-matrix / env-templates / port-allocation / db-naming を同梱（#50）
- `worktree-teardown` skill: worktree 破棄時の cleanup チェックリスト（プロセス停止 / DB drop / port 解放 / env 削除 / uncommitted 確認 / git worktree remove）を順次確認し、teardown 漏れ（DB drop 失敗・port leak）を WARNING で検知（#50）

### Changed
- `ui-verify` SKILL.md の「dev server ライフサイクル」セクションを issue #38 の構造に揃えて補強。セッション中の dev server 保持を明文化、検出ロジックを `lsof -i :$DEV_PORT -t` ベースで提示、検証ごとの再起動による HMR 断絶・認証再ハンドシェイク・port 競合ループ（1 セッションで 4 回再起動の実例）を防止（#38）

## [1.15.0] - 2026-05-26

### Added
- `skills/pr-creator/references/description-guide.md` に「変更の粒度を小さく保つ（Small CL）」セクションを追加（Google Engineering Practices の small-cls 由来）。単一目的・行数目安（~100 快適 / ~400 要注意 / 1000 超は過大）・リファクタと機能変更の分離・revert 可能性・許容される例外を明文化
- `skills/pr-creator/SKILL.md` Step 2 に diff の規模把握（`--shortstat`）と、目安超過時（400 行超 または 10 ファイル超）にレポート末尾へ分割検討の advisory を添える手順を追加。PR 作成自体は止めない non-blocking な扱い

## [1.14.0] - 2026-05-25

### Added
- `skills/pr-creator/SKILL.md` に Step 4.9「PR body の最終検証（gitignored パス検出）」を追加。`gh pr create` 直前に regex + `git check-ignore` で `.claude/` 等の gitignored パスを検出し、含まれていれば PR を作成せず除去を促す fail-fast 機構（GitHub issue #39）
- `skills/pr-creator/SKILL.md` Step 5 に「gh pr create / edit が失敗した場合のフォールバック」を追加。Projects (classic) 廃止に起因する `projectCards` GraphQL エラーで gh CLI が exit 1 する場合に github MCP（`create_pull_request` / `update_pull_request`）へフォールバックする手順を明記（GitHub issue #41）
- `skills/pr-creator/SKILL.md` / `commands/pr.md` の `allowed-tools` に `mcp__github__create_pull_request` / `mcp__github__update_pull_request` を追加（上記フォールバック用）
- `skills/ui-verify/SKILL.md` Step 2 に「dev server ライフサイクル（セッション中は保持する）」セクションを追加。タスク完了ごとの停止・再起動を禁止し、HMR 断・認証再ハンドシェイク・port 競合ループを防ぐ。絶対厳守ルールにも保持方針を明記（GitHub issue #38）

## [1.13.1] - 2026-05-22

### Changed
- `.mcp.json` の chrome-devtools サーバに `alwaysLoad: true` を追加 (CC v2.1.121+)。ToolSearch deferral をスキップしてプラグイン有効時に chrome-devtools ツール群を常時利用可能にする。ui-verify 起動時のツールロード往復を削減

## [1.13.0] - 2026-05-21

### Changed
- `skills/pr-creator/SKILL.md` 厳守ルールを刷新。「PR title に Issue ID prefix を含めない」「PR 本文にローカルパスを出力しない」「概要は `What / Why / Outcome` の三要素を満たす（実装手段 How は変更点セクションに書く）」を追加。箇条書きルールを「乱発を避ける、並列性のある情報には使ってよい」に緩和
- `skills/pr-creator/SKILL.md` Step 4 で description 生成方針に三要素（What / Why / Outcome）の定義を明記。title は Linear Issue のタイトル本文のみ使用（Issue ID prefix を含めない）に変更
- `skills/pr-creator/SKILL.md` Step 4.5 Screenshots アップロード失敗時のフォールバックを修正。`## Screenshots` セクションごと PR 本文から省略し、ユーザーには口頭で手動添付を案内する（従来は本文にローカルパスを記載していたが、GitHub からクリックできないため削除）
- `skills/pr-creator/references/description-guide.md` を全面改訂。「大事にしたいこと」「概要」セクションに三要素（What / Why / Outcome）を明示し良い例も更新。実装手段（How）は概要に書かず変更点セクションに任せる方針を明記。文体ガイドの箇条書き縛りを「2 項目でも並列なら箇条書き可」「並列変更・確認手順・レビュー観点には箇条書きが自然」と柔軟化。末尾折りたたみのテンプレ例からローカルパス参照を除去し、Linear URL や PR リンクなど GitHub から辿れるものに置換。失敗例にローカルパス出力のケースを追加
- `skills/pr-creator/references/linear-integration.md` を改訂。「タイトル生成」で Issue ID prefix（`TEAM-123:` 等）を含めない方針を明示。「タスク詳細ファイル」セクションで `.claude/plans/...` は Claude の参考用であり PR 本文に出力しないことを明示

## [1.12.0] - 2026-05-19

### Added
- `skills/pr-creator/references/description-guide.md` を全面リライト。PR description の本文を人間向けに保ち、末尾の `<details>` 折りたたみを AI やレビュー bot 向けの補足情報置き場として使う構成に変更
- 人間向け本文の書き方を散文中心で記述。各セクション（概要 / 変更点 / レビューしてほしいところ / 動作確認 / 備考）について良い例と避けたい例を添えた
- 折りたたみに入れてよいもの・本文に残すものの判断指針、PR 規模ごとの省略目安、ありがちな書き方の失敗、`<details>` タグ利用時の Markdown の注意点を追加

### Changed
- `skills/pr-creator/SKILL.md` step 4 を更新。本文の読みやすさを最優先にする方針と、AI 特有の文体（箇条書きの乱発、太字の乱用、装飾絵文字）を避けることを明記
- 厳守ルールに「文体は体言止め・常体に統一」「AI 特有の文体を避ける」「行動を変える情報を折りたたみに隠さない」を追加
- `skills/pr-creator/SKILL.md` と `commands/pr.md` の `allowed-tools` から実利用のない `Glob` と `Grep` を削除。Permission Pruning（過剰な権限宣言は判断精度を下げる）の観点で整理

## [1.11.0] - 2026-05-18

### Added
- `skills/ui-verify/references/chrome-devtools-cheatsheet.md` に「認証突破ガイド」セクションを追加。プロジェクト固有の認証（SSO / OAuth / form login / Cookie session / Bearer）に対する 4 パターン（`--browserUrl` + 専用プロファイル / `--userDataDir` / `--autoConnect` (Chrome 146+) / `--wsHeaders`）の `.mcp.json` 設定例と採用フローを明示
- Chrome 136+ で remote-debugging-port にデフォルトプロファイル attach 不可になった挙動変化を Gotchas に追記
- 「`.env` 等への平文 credentials 保存はせず、ログイン済みプロファイルを使い回す or macOS Keychain (`security find-generic-password`) で間接化する」原則を明文化

## [1.10.0] - 2026-05-18

### Added
- `hooks/scripts/on-commit.sh`（PostToolUse Bash matcher）を追加 (#33)。`git commit *` が成功した直後に `commit:created` イベントを Event Bus へ発行する。payload は `{"sha":"<short>","type":"<conventional commit type>","files":<count>}`。`--amend` / `--dry-run` / `--help` 系は除外、git リポジトリ外は no-op
- `hooks/hooks.json` の `PostToolUse` に `Bash` matcher + `if: "Bash(git commit *)"` 条件を追加し、上記スクリプトを駆動

## [1.9.3] - 2026-05-18

### Changed
- `hooks/lib/safe-hook.sh` を v2026-05-18+ に同期。`event_bus_publish` / `event_bus_tail` / `event_bus_clear` API を取得（正本由来、内部ライブラリ拡張）。将来 `commit:created` / `pr:created` イベント発行用の土台として整備

## [1.9.2] - 2026-05-15

### Changed
- `ui-verify` SKILL.md に「E2E への昇格（webapp-testing 委譲）」セクションを追加。複数ページ跨ぎシナリオ / 認証フロー / データ永続化テスト / 既存 Playwright プロジェクトでは公式 skill `webapp-testing`（`~/.claude/plugins/marketplaces/anthropic-agent-skills/skills/webapp-testing/`）を採用する判定基準を明示。`ui-verify` は単一ページ smoke test に責務を絞る

## [1.9.1] - 2026-05-15

### Changed
- `hooks/hooks.json` を `args[]` exec 形式へ移行（CC 2.1.139+）。シェル解釈なしでスクリプトを直接 spawn し、起動オーバーヘッドとパース起因のエッジケースを削減
- `safe-hook.sh` に `safe_hook_emit_bell` / `safe_hook_emit_window_title` を追加（CC 2.1.141+ terminalSequence 対応、opt-in 利用）

## [1.9.0] - 2026-05-12

### Changed
- **`ui-verify` snap モードのデフォルトを desktop 1 枚に変更** (#32 最優先 1)。従来は mobile/tablet/desktop の 3 viewport 一括撮影だったが、検証 PR で過剰だったため。複数 viewport が必要な場合は `--viewports=mobile,desktop` 等の opt-in 引数で指定する
- **PR タイプ別ガイドラインを `ui-verify` SKILL.md に追加** (#32 最優先 2)。検証 PR / リファクタ / UI 新機能 / レイアウト変更 / Theme 変更 / バグ修正の 6 タイプについて推奨枚数・viewport を明示
- **`git-commit-helper` Step 4.5 AskUserQuestion を 4 択化** (#32 次優先 3)。「撮る / スキップ」二択を「desktop 1 枚 / 複数 viewport / ローカル目視済み / スキップ」の 4 択に拡張
- **`.claude/.ui-verify-pending` を 3 値仕様に拡張** (#32 次優先 3)。`unverified` / `verified-local` / `verified-snap` の 3 値で verify 状態を表現する。`ui-change-reminder.sh` は `unverified` を書き込み、`ui-verify-gate.sh` は `verified-*` の場合 reminder をスキップ、ui-verify スキルは `verified-snap` で上書き
- **`pr-creator` に PR タイプ判定ロジックを追加** (#32 最優先 2)。ブランチ名・コミット message・差分シグナル（`@media`, breakpoint utility, `theme` トークン等）から PR タイプを推定し、`ui-verify` の `--viewports=...` 引数を組み立てて撮影枚数を最適化
- **`pr-creator` Screenshots の 1 枚レイアウトを追加**。1 枚のみの場合は table 形式ではなく単独画像で添付する

### Added
- **`git-commit-helper` probe / spike fast path** (#32 次優先 4)。ブランチ名に `probe|spike|stage1|compat|verify|poc|experiment` を含む場合、AskUserQuestion の default 選択肢を「ローカル目視済み」に倒す（撮影せずに verified-local としてマーク）
- **`pr-creator` 機密 UI チェックリスト** (#32 🟢 6)。`cc-screenshots` release は public のため、ログイン画面 / 顧客データ / 社内 URL / 機密 UI / 環境変数値が撮影に含まれていないかを撮影前にチェック。判定不能時は AskUserQuestion で「アップロード / ローカルパスのみ / Screenshots 省略」の 3 択
- `pr-creator` SKILL.md / `commands/pr.md` の allowed-tools に `AskUserQuestion` を追加（機密チェック・撮影方針確認のため）

## [1.8.1] - 2026-04-25

### Changed
- `git-commit-helper` コミット分割判定に段階的思考誘導を追加（Opus 4.7 対応）。分割単位決定前に `git diff` 全体の俯瞰・依存関係把握・論理的作業単位の identify を経由するステップを明記

## [1.8.0] - 2026-04-23

### Added
- opt-in の TDD Phase Gate hook を追加（`hooks/scripts/tdd-phase-gate.sh`）。`.claude/.tdd-phase-gate-enabled` 有効化時に PreToolUse (Edit|Write|MultiEdit) で実装ファイルに対応するテストファイルの存在をチェックし、Red phase 逸脱を警告（ブロックなし）(#26)
- README に「TDD Phase Gate（opt-in）」セクションを追加し有効化/無効化方法と検知ロジックを記載

## [1.7.4] - 2026-04-22

### Changed
- git-commit-helper スキルに「Generator として動作する」設計原則セクションを追加。品質判定は code-review:self-review を別コンテキストで実行する推奨フローを明示 (#27)

## [1.7.3] - 2026-04-20

### Changed
- ui-verify: allowed-tools を 28 → 15 に削減（Permission Pruning）。本文で使用されていない chrome-devtools MCP ツール（select_page / list_pages / close_page / get_console_message / get_network_request / emulate / fill_form / type_text / evaluate_script / handle_dialog）と未使用 Write / Glob / Grep を除去 (#28)

## [1.7.2] - 2026-04-19

### Changed
- hook スクリプト全般を `safe-hook.sh` 共通ラッパー経由に移行（check-deps / detect-web-project / ui-change-reminder / ui-verify-gate） (#21)

## [1.7.1] - 2026-04-19

### Fixed
- `git-commit-helper` スキルおよび `/commit` コマンドの `allowed-tools` に `AskUserQuestion` を追加（本文で使用しているが未宣言だったため実行時拒否の可能性があった）
- `check-deps.sh` に `chrome-devtools` MCP と `node` CLI のチェックを追加（`_requirements` との不整合を解消）

## [1.7.0] - 2026-04-19

### Added
- `hooks/scripts/upload-screenshots.sh` を追加。`.claude/screenshots/` 内の画像を GitHub Release（`cc-screenshots` タグ）に一括アップロードし public URL を返す
- `git-commit-helper` スキルに UI 統合セクション追加。UI 差分時に ui-verify snap を対話的に実行し `.claude/.ui-verify-pending` をクリア
- `pr-creator` スキルに Screenshots 添付セクション追加。UI PR で最新 snap を upload-screenshots.sh で GitHub Release にアップロード後、PR body に `## Screenshots` テーブルを自動埋め込み
- PR Screenshots のフォールバック対応（gh 未認証・アップロード失敗時はローカルパス記載）

## [1.6.0] - 2026-04-19

### Added
- SessionStart hook に `detect-web-project.sh` を追加。Web フレームワーク依存を検出してプロジェクト単位で ui-verify 連携を有効化（`.claude/.ui-verify-enabled` フラグ）
- PostToolUse hook（Edit/Write/MultiEdit）に `ui-change-reminder.sh` を追加。UI 関連ファイル（tsx/jsx/vue/svelte/css/scss/html/astro/mdx）の変更時に ui-verify 利用を促すリマインダーを注入
- PreToolUse hook の `git commit` 前 gate を追加。UI 変更後に動作確認が記録されていない場合に reminder を表示
- ui-verify スキル実行後の後処理に `.claude/.ui-verify-pending` フラグクリアを追加

### Changed
- Web プロジェクト以外では UI 自動化 hook が一切発火しない設計（非 Web プロジェクトでのノイズゼロ）

## [1.5.0] - 2026-04-18

### Added
- `ui-verify` スキルを追加。chrome-devtools MCP を使った Web UI の動作確認・スタイル調整・スクリーンショット取得を自動化（verify / tune / snap の3モード）
- `/ui-verify` スラッシュコマンドを追加
- `.mcp.json` で chrome-devtools-mcp を同梱配布（プラグインインストールで自動的に MCP サーバーが有効化）
- plugin.json の `_requirements` に chrome-devtools MCP と node を追加

## [1.4.0] - 2026-04-08

### Added
- `userConfig` でコミットメッセージ言語を設定可能に（`commit_language`: ja/en、デフォルト: ja）
- README に `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS` 環境変数の案内を追加

## [1.3.1] - 2026-03-31

### Changed
- SessionStart check-deps.sh に `once: true` 追加（セッション中1回のみ実行）

## [1.3.0] - 2026-03-29

### Added
- 全スキルに effort frontmatter を追加（git-commit-helper/pr-creator: medium）
- PreToolUse conditional hook: git push 前にセルフレビューを推奨

## [1.2.1] - 2026-03-25

### Added
- 同一ファイル内の hunk 分割ステージング手法を追加（git diff + パッチ編集 + git apply --cached）

## [1.2.0] - 2026-03-23

### Added
- SessionStart hook で外部依存チェック（gh CLI、Linear MCP）を実行
- plugin.json に `_requirements` フィールドを追加（依存メタデータ宣言）

## [1.1.1] - 2026-03-23

### Fixed
- スキル description のトリガーフレーズを「トリガー:」形式に統一

## [1.1.0] - 2026-03-21

### Fixed
- プラグイン品質改善
- プロジェクト固有の情報を汎用的な例に置換
- 全プラグインの品質問題を一括修正

## [1.0.0] - 2026-03-20

### Added
- dev-workflow プラグインを新規作成
- Git コミット・PR 作成の開発ワークフロー
