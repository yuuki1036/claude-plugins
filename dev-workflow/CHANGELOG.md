# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [1.27.3] - 2026-09-06

### Fixed

- **同名 command の本文に SKILL.md への Read 誘導を置いた**（GitHub issue #219）。command 名と skill 名が
  同名だと `Skill plugin:name` で呼んでも**注入されるのは command 本文**で、SKILL.md には到達しない
  （#206 の本文版）。本文が「X スキルを使って」だけだと model は記憶で手順を再現するか cache を
  `ls | head -1` で掴む — 実測（2026-09-06）では辞書順で旧版を掴み、publish まで丸ごと落ちた。
  `${CLAUDE_PLUGIN_ROOT}` が展開されていない場合の解決先（`installed_plugins.json` の `installPath`）も
  本文に書いた。`validate_plugin_quality.py` の `skill-hop-cmd` が error で強制する。対象: `diagnose` / `ui-verify`

## [1.27.2] - 2026-09-05

### Fixed

- **同名 command の description に `トリガー:` を複製した**（GitHub issue #206）。command 名と skill 名が
  同名だと、スキル選択の一覧に載るのは `commands/*.md` の description だけで **`SKILL.md` 側は
  router に届かない**。`トリガー:` 必須の規約は SKILL.md にだけ掛かっていたので、字面は通るが
  ルーティングには効いていなかった。対象: `diagnose` / `ui-verify`。
  - **移動ではなく複製**（SKILL.md 側は残す） — `check_router_trigger_drift` が SKILL.md の
    `トリガー:` を入力にしており、移動するとその機械ガードが沈黙する
  - 引用符なしの description に `トリガー:` を足すと YAML の `key: value` と解釈されて frontmatter が
    壊れるので、二重引用符で囲んだ（既存の書式に揃えた）
  - `validate_plugin_quality.py` が同名ペアの commands 側にも `トリガー:` 必須を error で強制する
    （`[trigger-cmd]`）

## [1.27.1] - 2026-09-02

### Fixed

- **`pr-creator` の Linear 連携でコメントも取得するようにした**（GitHub issue #202）。
  `get_issue` だけで description を生成していたため、実装中に決まった仕様変更・スコープ削減
  （Linear では本文に反映されずコメントに残る）が PR の説明に載らず、**実際の差分とずれた
  説明**が出ていた。`list_comments` をセットで呼んで description 生成の材料に含める。
  返却が上限に達した回は古いコメントを読めていないとレポートに添える。
  Linear MCP 未接続時のフォールバック（コミット履歴から生成）はそのまま

## [1.27.0] - 2026-08-31

### Fixed

- **`check-deps.sh` の chrome-devtools 検査が構造的に嘘をついていたのを直した**。
  `check_mcp` の探索対象に同梱 `${CLAUDE_PLUGIN_ROOT}/.mcp.json` が入っている（v1.23.1 で
  「同梱を検知できず常時 WARN」を直した際に追加）ため `found` が**恒真**で、`check_cli` は
  `required=false` の else が無く**完全に無言**だった。結果、npx を持たない機体で
  chrome-devtools が ENOENT で起動に失敗しているのに、SessionStart の依存チェックは
  **ERROR も WARN も 0 件**になっていた。設定の有無（`check_mcp`）と起動可能性を分離し、
  同梱 MCP の launcher が PATH から引けなければ警告する `check_bundled_mcp_launcher` を追加。
  あわせて `check_cli` に else を足してオプション依存の不在も報告する。
  検査は `.claude/.ui-verify-enabled` があるときだけ走らせる（node の無い機体で毎セッション
  鳴らすと「WARN が出たときだけ行動する」契約が壊れるため — `docs/rule-placement.md`）
- **`ui-verify` SKILL.md Step 2 の `wait_for` 誤用を修正**。「`wait_for` で HTTP が応答するまで
  待機」と書いていたが、実体は `waitForTextOnPage`（**ページ上のテキスト出現待ち**）で疎通待ちには
  使えない。dev server の起動待ちを Bash の curl ループに置き換えた
- **cheatsheet の `wait_for` 呼び出し例が schema 違反だったのを修正**。`text` は
  `array(string).min(1)` が必須で、初出時から誤って文字列単体を渡す例を載せていた
- **cheatsheet の「既定で headless Chrome を起動」を訂正**。`--headless` は既定 false で
  実際には画面に Chrome ウィンドウが開く。プロファイルも `--isolated` 既定 false のため
  `$HOME/.cache/chrome-devtools-mcp/chrome-profile` に永続し、「毎回まっさらで安全」ではない

### Added

- **`emulate` を `ui-verify` の allowed-tools に復帰**（skill / command 同時。12 → 13）。
  v1.10.0 の Permission Pruning（28 → 15）で落としていたが、`--viewports=light,dark` の
  テーマ撮影は `emulate(colorScheme:)` が唯一のプロジェクト非依存な経路で、
  撮影機能が「UI トグルを操作できる場合のみ動く」degraded 状態になっていた。
  SKILL.md のテーマ撮影手順と cheatsheet の `emulate` 節（`colorScheme` / `viewport`）も具体化
- `check-deps.sh` の ui-verify 依存検査に回帰テストを追加
  （`test_dev_workflow_hooks.py::CheckDepsUiVerifyTest`。黙る条件 2 本 + 鳴る条件 3 本）

## [1.26.2] - 2026-08-28

### Changed

- **`plugin.json` の description を 624 → 173 字に圧縮した**（GitHub issue #183 /
  設計 `.claude/designs/20260610-plugin-description-diet.md`）。description は「これは何の
  プラグインか」を伝える 1〜2 文だが、バージョンアップごとに機能詳細を積層してリリースノート化
  していた。落とした詳細は CHANGELOG / README / SKILL.md に既出で情報は失われない。
  あわせて `validate_plugin_quality.py` に 400 字の上限検査（非ブロッキング warning）を追加し、
  再発を機械強制に寄せた

## [1.26.1] - 2026-08-27

### Fixed

- **`tdd-phase-gate` の恒常的な誤警告を消した**（GitHub issue #180）。テストファイルの
  探索候補が手書きの 9 通りで「場所 × 命名」の直積になっておらず、`tests/` 配下は
  `.test.` と `test_` しか探していなかった。そのため **`tests/foo.spec.ts` 構成の
  プロジェクトはテストが実在しても常に警告**が出ていた（README は直積を宣言しており、
  実装だけが狭かった）。恒常的な偽警告は「⚠️ が出たときだけ行動する」契約を壊す
  （`docs/rule-placement.md`）
- **`jq` 不在時の fallback で自己判定が死んでいたのを直した**（同 issue）。jq 分岐は
  `|| true` 済みだったが grep fallback 側に無く、対象キーを欠く payload
  （**まさに自己判定二重ゲートが受け持つべきケース**）で grep の exit 1 が safe-hook の
  ERR trap を踏み、以降を実行せず exit 0 していた。対象は `on-commit.sh` /
  `push-reminder.sh` / `ui-verify-gate.sh` / `tdd-phase-gate.sh` / `ui-change-reminder.sh`
  の 5 本。`doc-freshness` の同型 fallback は `|| true` 済みで、書き方が割れていた

## [1.26.0] - 2026-08-20

### Removed
- **`git-commit-helper` の Step 4.5「UI 変更時の自動確認」を削除**。UI 差分を検知して AskUserQuestion（desktop 1 枚 / 複数 viewport / ローカル目視済み / スキップ）で撮影を確認していたが、コミットのたびに選択 UI が通常のチャット入力を奪うコストに撮影の価値が見合わない。commit 直前の通知は PreToolUse の `ui-verify-gate.sh`（非ブロッキング・additionalContext）だけに一本化する。撮影自体は `/ui-verify snap` と `pr-creator` Step 4.5（PR body への添付）に残る
- 上記に伴い `git-commit-helper` skill / `commit` command の allowed-tools から `AskUserQuestion` を削除（本スキルでの唯一の用途だったため）

### Changed
- **pending flag（`.claude/.ui-verify-pending`）3 値仕様の正本を `ui-verify/SKILL.md` に移設**（旧正本は削除した git-commit-helper Step 4.5）。`verified-local` の書き込み主体を「git-commit-helper のユーザー選択」から「手動（撮影せず黙らせたいとき）」に変更し、コマンド例を明記
- `ui-verify-gate.sh` の reminder 文言から git-commit-helper Step 4.5 への案内を削除し、`verified-local` の手動書き込み / flag 削除の 2 経路に変更

## [1.25.1] - 2026-08-17

### Fixed
- **`on-commit.sh` が Conventional Commits 形式でないメッセージで `commit:created` を publish していなかった**。type 抽出の `grep` が非マッチで exit 1 を返し、safe-hook の ERR trap が発火して publish 前に exit 0 していた（`[ -z "$TYPE" ] && TYPE="other"` のフォールバックに到達しない）。`|| true` を追加
- **同 hook が最初のコミット（親なし）で invalid JSON を event log に書いていた**。`grep -c` は 0 件でも `0` を出力したうえで exit 1 するため `|| echo 0` が二重に効き `"files":00` になっていた。event log の 1 行が壊れると読み手が丸ごとパースできなくなる。`|| true` + 数値検証に変更
- 同 hook が最初のコミットの変更ファイル数を 0 と数えていた（`diff-tree` に `--root` が無く親なしコミットで空になる）

## [1.25.0] - 2026-07-29

### Added
- **diagnose スキル / コマンドを新規追加**（mattpocock/skills の diagnosing-bugs を翻案）。厄介なバグ・性能劣化を feedback loop 駆動の 6 Phase 規律（loop 構築 → 再現+最小化 → ランク付き反証可能仮説 3〜5 → `[DEBUG-xxxx]` タグ付き計装 → 正しい seam での回帰テスト+修正 → 後始末+post-mortem）で診断する。「red-capable な 1 コマンドが存在するまで仮説フェーズに進まない」を進入条件として強制。`${CLAUDE_EFFORT}` で loop 投資・仮説数を段階化。post-mortem は failure-journal（candidates.jsonl 追記）と issue-workflow（follow-up / issue 起票提案）へ dormant 還流。多段 agent は不採用（状態を引き継ぐ逐次規律のため — pipeline-design 採否注記を SKILL.md に明記）。新規追加の根拠（component-addition-advisor 判定）: 既存 5 skill のいずれともトリガーが意味的に重ならず、リポジトリ全体にも診断系 skill が存在しない（隣接は ui-verify の console/network 監視のみ）

## [1.24.0] - 2026-07-28

### Added
- **pr-creator に PR 作成前のユーザー承認ゲートを追加（Step 4.95・必須）**: `gh pr create` の直前に最終版の title / body 全文・draft 種別を提示し、AskUserQuestion（作成する / 修正したい / 中止）で明示承認を得る。承認なしの PR 作成は禁止（厳守ルールにも明記）。省略できる唯一の例外は、ユーザーが同一セッション内で承認プロセスの省略を明示した場合のみ（曖昧・包括的な指示は例外にしない）。修正時は修正内容に応じて再入点を分岐（本文修正 → 推敲 4.3 → 三要素 4.7 → 機械検証 4.9 → 再確認 / Screenshots 変更 → 4.5 / title・draft のみ → 4.9）し再確認を通す。中止時はアップロード済み screenshots の残存を開示し削除を確認する。gh 失敗かつ github MCP 未設定のフォールバックは最小 body 作成をやめ、承認済み body の手動作成案内（または再承認）に変更
- **pr-creator に作業リポジトリの PR 作成ルール遵守を追加（Step 1 拡張）**: PR テンプレートに加えて CONTRIBUTING.md / リポジトリの CLAUDE.md / docs 配下の PR 関連 doc（grep で最大 3 件に決定的に絞り込み）から PR 規約を収集し、本スキル既定と矛盾する場合はリポジトリ側を優先する。優先できるのはタイトル形式・本文言語 / 構成・base・draft 可否・ラベル / レビュアー・マージ方式の限定列挙のみで、承認ゲート・ローカルパス非出力・機密チェック・AI 署名禁止は上書き不可の floor。上書きした点は承認時に明示（黙って上書きしない）

### Changed
- **pr-creator の writing-polish 推敲タイミングを「body 最終形の確定後（Step 4.7 の後・4.9 の前）」に明確化**: 承認ゲート導入に伴い、Screenshots 追記（4.5）や三要素書き直し（4.7）の後の本文にも推敲が効くよう実行位置を規定（未推敲の本文を承認提示しない）
- **pr-creator の draft 種別を提示連動に変更**: `gh pr create --draft` / MCP `draft: true` の固定をやめ、Step 4.95 で提示した種別どおりに作成する（リポジトリ規約が非 draft を指定するケースに対応）

## [1.23.4] - 2026-07-23

### Changed
- **git-commit-helper の allowed-tools から未使用の Glob / Grep を削除**（skill / command の両方。対象特定は全て git コマンド（Bash 経由）で行い、ツールとしてのファイル探索・内容検索フローがない。/quality-check の最小性チェックで検出）

## [1.23.3] - 2026-07-22

### Fixed
- **ui-verify の chrome-devtools MCP ツール名を実行時の実名に修正**（プラグイン同梱 MCP は `mcp__chrome-devtools__*` でなく `mcp__plugin_dev-workflow_chrome-devtools__*` として公開される。旧表記だと allowed-tools の allowlist が空振りして permission プロンプトが増え、本文のツール名も実在名と不一致だった。SKILL.md / commands / cheatsheet の 34 箇所を更新）
- **ui-verify-gate.sh / tdd-phase-gate.sh の注入方式を additionalContext に統一**（push-reminder.sh が実測済みの「PreToolUse の plain stdout は到達保証が弱い」問題に対し、同一プラグイン内で plain stdout のまま残っていた 2 本を `safe_hook_emit_context` へ移行）
- **safe-hook.sh: `event_bus_publish` の payload 省略時デフォルトが壊れた JSON になるバグを修正**（`${2:-{\}}` が `{}` でなく文字列 `{\}` に展開され invalid JSON 行が書かれていた。正本 `.claude-plugin/lib/safe-hook.sh` の修正を全プラグインへ同期）

## [1.23.2] - 2026-07-16

### Fixed
- `push-reminder.sh` が全 Bash 呼び出しで reminder を注入する暴発を修正。hooks.json の `if: "Bash(git push *)"` が実行環境によって評価されないことが実測されたため、スクリプト内で `tool_input.command` から `git push` を自己判定する二重ゲートを追加（`on-commit.sh` と同方式）
- `ui-verify-gate.sh` にも同様の `git commit` 自己判定を追加（`if:` 不発時に UI 検証有効プロジェクトで全 Bash に reminder を撒く潜在暴発の予防）
- push reminder の文言を `/self-review` から `/code-review:self-review` に修正（名前空間なしだと旧グローバル skill に解決される衝突の回避）
- command 自己判定の精度を強化（push-reminder / ui-verify-gate / on-commit の 3 スクリプト共通）: クオート内文字列を除去してから判定（コミットメッセージ中の "git push" / "--amend" 言及での誤発火・誤除外を防止）し、`git -C <dir> push` 等グローバルオプション経由の形式も判定対象に追加

## [1.23.1] - 2026-07-02

### Fixed
- git push reminder hook を インライン `echo` から safe-hook 経由スクリプト（`hooks/scripts/push-reminder.sh`）に置き換え。stdin を消費し `additionalContext`（`safe_hook_emit_context`）で reminder を注入する形に統一（PreToolUse の plain stdout は Claude への到達保証が弱いため）
- `hooks/scripts/check-deps.sh` の chrome-devtools MCP チェックが同梱 `.mcp.json`（`${CLAUDE_PLUGIN_ROOT}/.mcp.json`、alwaysLoad 配布）を検知できず常時 WARN していた問題を修正。`check_mcp` の探索対象に同梱 `.mcp.json` を追加
- `git-commit-helper` の description から「Git専門エージェント」の含意を除去（実装はメインコンテキストで完結し Agent を起動しない）

### Changed
- writing-polish 連携を `_requirements`（`type: plugin, required: false`）と `check-deps.sh`（`check_plugin "writing-polish"`）に宣言。未インストール時は SessionStart で WARN、pr-creator / git-commit-helper の推敲連携は skip（従来通り）
- `worktree-setup` / `worktree-teardown` の allowed-tools を実使用（Bash / Read のみ）に最小化。本文で未使用の Write / Edit / Glob / Grep を削除（処理はすべて Bash コマンド経由）

## [1.23.0] - 2026-06-26

### Changed
- pr-creator Step 4.3 の writing-polish 連携を opt-in → 必須に強化（インストール時は PR 本文をユーザー提示前に必ず推敲。未インストール時のみ skip）

## [1.22.0] - 2026-06-26

### Changed
- **スクリーンショットのホスト先を GitHub Release から専用ブランチに変更**（`hooks/scripts/upload-screenshots.sh`）。従来は `gh release create cc-screenshots --prerelease` で画像をホストしていたが、**GitHub Release は必ず git tag を伴う**ため `cc-screenshots` タグが生成され、リリース運用の tag 一覧・`claude plugin tag` と混ざる問題があった
  - tag を一切作らず、Contents API（`gh api -X PUT repos/{repo}/contents/...`）で専用ブランチ `cc-screenshots`（orphan・リポジトリソースを含まない）に画像を push し、`raw.githubusercontent.com` の URL を返す方式に変更
  - branch が無ければ orphan branch を初回自動作成（idempotent）。同名ファイルは既存 sha を引いて上書き
  - 出力契約（`<filename><TAB><url>`）は据え置きのため `pr-creator` 側の利用は非破壊。第2引数を `[release-tag]` から `[branch]` にリネーム（デフォルト `cc-screenshots`）
  - `pr-creator` SKILL の Screenshots 添付セクション・機密チェックリストの文言を release → ブランチに更新。raw URL は **public repo でのみ** PR 上に描画される旨を明記（private repo では release download URL と同様に認証が要りインライン描画されない＝従来同等）
  - 既存のアップロード失敗フォールバック（手動ドラッグ&ドロップ案内）は据え置き

## [1.21.2] - 2026-06-25

### Fixed
- `hooks/scripts/on-commit.sh` の変更ファイル数カウントがマージコミットで 0 になっていたのを、`git diff-tree -m --first-parent` で第一親との差分を数えるよう修正（`commit:created` payload の `files` 精度向上）

## [1.21.1] - 2026-06-15

### Changed
- README を全 command / skill（ui-verify / worktree-setup / worktree-teardown 含む）構成に同期、Version 行を撤去

## [1.21.0] - 2026-06-08

### Added
- `pr-creator` に **Step 4.7「概要の三要素セルフチェック」** を追加。`gh pr create` の前に概要が What / Why / Outcome を各々明示しているか自己点検し、欠けていれば `git diff` / コミット履歴 / Linear Issue から補って書き直す（埋まらなければ `AskUserQuestion`）。brevity 優先で 3 要素が暗黙化される事故を生成後に機械的に拾う

### Changed
- `pr-creator` の Step 4 と厳守ルールに **字数制約（1〜2 文）と三要素の両立** を明記。「概要は 1〜2 文」という上限が「概要は What/Why/Outcome の 3 要素を満たす」要件と運用上ぶつかり、エージェントが brevity を優先して Why / Outcome を暗黙化・省略し What 中心の 1 文に畳む事象（複数回再発）への対応。1〜2 文に収めつつ 3 要素を各々明示する両立を必須化し、3 要素が収まらない場合は概要が長いのではなく PR が大きすぎるサインとして分割を促す
- `description-guide.md`「概要」セクションに **brevity と三要素の両立** の小節を追加。3 要素を 1〜2 文に畳むテンプレ（`〜で〜できなかった(Why)ので、〜を〜して修正し(What)、〜になる(Outcome)`）と、字数を優先して Why / Outcome を省略した避けたい例 / 3 要素を明示した良い例を併記

## [1.20.0] - 2026-06-05

### Added
- `pr-creator` の Step 4.9 PR body 検証に **ローカル限定ドキュメント参照の advisory 検出**（非 fail-fast）を追加。既存の gitignored パス検出（regex + `git check-ignore`）はパス文字列前提のため、「knowledge に詳細」「設計メモ参照」のようなパスを伴わない自然言語の誘導をすり抜けていた。レビュアーが開けないローカルドキュメント（`.claude/` 配下の knowledge / plans / issues 等）への言及語を拾い、要点のインライン要約を促す warning を出す。一般語としての `knowledge` / `plan` での誤検知を避けるため PR 作成は止めない advisory に留めた

### Changed
- `pr-creator` の厳守ルールと `description-guide.md`（「情報の集め方」「ありがちな書き方の失敗」）に、**パス文字列の有無に関わらずローカル限定ドキュメントを本文参照しない**原則を明記。参照させるのではなく必要な情報を本文へインライン要約する方針を追記

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
