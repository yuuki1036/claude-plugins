# CLAUDE.md - claude-plugins

Claude Code プラグインのマーケットプレイスリポジトリ。

## リポジトリ構造

```
.claude-plugin/marketplace.json  # マーケットプレイスマニフェスト（plugin.json から派生）
.claude-plugin/lib/safe-hook.sh  # hook 共通ラッパー（正本）
.claude-plugin/schema/           # JSON Schema（plugin.json / marketplace.json / hooks.json）
.claude-plugin/scripts/          # validate-ssot.sh / validate_ssot.py（SSoT 同期検証）
.githooks/pre-commit             # バージョンバンプ・CHANGELOG・SSoT 同期チェック
{plugin-name}/                   # 各プラグイン（独立したディレクトリ）
  .claude-plugin/plugin.json     # プラグインマニフェスト
  commands/                      # スラッシュコマンド定義（YAML frontmatter + markdown）
  skills/                        # スキル定義（SKILL.md + references/）
  agents/                        # エージェント定義（frontmatter付き markdown）
  hooks/                         # フック定義（hooks.json + scripts/）
    lib/safe-hook.sh             # 正本の byte-identical 複製（hook 持ちプラグインのみ）
  rules/                         # SessionStart 等で注入されるルール（一部プラグインのみ）
    project-rules.md             # プロジェクト全体の作業ルール（SessionStart hook で注入）
  CHANGELOG.md                   # 変更履歴（Keep a Changelog 形式）
  README.md
```

> LICENSE ファイルは不要（各プラグインに個別のライセンスファイルを置かない）

## プラグイン一覧

| プラグイン | コマンド | スキル | agents | hooks | 説明 |
|-----------|---------|-------|--------|-------|------|
| code-review | 2 | 2 | - | SessionStart | Phase 0 トリアージ + 動的エージェント構成コードレビュー / セルフレビュー |
| dev-workflow | 3 | 3 | - | SessionStart, PreToolUse, PostToolUse | Git コミット・PR 作成・UI 動作確認の開発ワークフロー（chrome-devtools MCP 同梱） |
| claude-meta | 2 | 5 | - | - | Claude Code 設定管理・CLAUDE.md 監査改善・CCアップデート追従・eval 回帰テスト・新コンポーネント追加前判断 |
| linear-workflow | 10 | 10 | 3 | SessionStart, PostCompact, UserPromptSubmit, FileChanged | Linear MCP 連携の Issue/プロジェクト管理（knowledge は source/concept 2層 + wikilink + lint。issue-design で 9 セクション設計） |
| indie-workflow | 10 | 10 | 2 | SessionStart, PostCompact, UserPromptSubmit, FileChanged, PostToolUse | 個人開発向けローカル Issue 管理（linear-workflow と排他。knowledge は source/concept 2層 + wikilink + lint。issue-design で 9 セクション設計） |
| plugin-manager | 1 | - | - | - | インストール済みプラグインの一括更新 |
| plugin-feedback | 1 | 1 | - | SessionStart | プラグインへの改善要望・バグ報告を GitHub Issue 化 |
| feature-dev | 1 | - | 3 | - | 8 phase 機能開発ワークフロー（Phase 1.7 動的トリアージ + Phase 6 G-V 自動 fix ループ + runtime smoke test 含む。code-explorer / code-architect / code-reviewer 同梱）。claude-plugins-official からフォーク |
| notebooklm-workflow | 2 | 2 | - | SessionStart | NotebookLM 連携ワークフロー（jacob-bd/notebooklm-mcp-cli を .mcp.json で同梱） |

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
- commands/ と skills/ の allowed-tools は一致させる（コマンドとスキルが同名でペアになっている場合のみ。独立したコマンドやスキルには適用されない）
- 後から変えにくい判断を伴う方針確認は `AskUserQuestion` で選択 UI を提示する（SKILL.md のワークフロー内に呼び出し仕様を直接記述する）
- plugin 開発は plugin-dev plugin を用いて必要に応じて agent team を使用する
- 新 skill / agent / hook / command を追加する前は `claude-meta:component-addition-advisor` で退路確保（既存拡張で解けないか）を判定する

## ルール配置の意思決定（決定的 hook > LLM 判定）

新しいルール・制約を追加するときは、以下の優先順位で配置先を決める。決定的機械検証（lint/型/テスト/hook）は LLM 判定より ROI が高い（Thoughtworks Harness Engineering 参照）。Hook の遵守率 100% に対し CLAUDE.md は ~80% にとどまる前提で判断する。

### 意思決定フロー

```
ルールを追加したい
  │
  ▼
① 決定的検証で判定可能か？（文字列・ファイル存在・JSON スキーマ・exit code 等）
  ├─ YES → Hook（PreToolUse/PostToolUse/Stop 等）で強制する
  └─ NO  ↓
  ▼
② 文脈判断・自然言語理解が必要か？（コードレビュー・意図推定・要約等）
  ├─ YES → Skill（呼び出しタイミング明示）または Agent（自律実行）
  └─ NO  ↓
  ▼
③ 恒常的に参照したい規約・背景情報か？
  └─ CLAUDE.md（プロジェクト全体）or skill の references/（局所的）
```

### 配置先の判定表

| 特性 | Hook | Skill / Agent | CLAUDE.md |
|------|------|---------------|-----------|
| 遵守率 | 100%（決定的） | ~90%（呼び出せば確実） | ~80%（読み落としあり） |
| 自然言語判定 | 不可 | 可 | 可 |
| セッション外で強制 | 可 | 不可 | 不可 |
| 具体例・背景説明 | 不向き | 向く | 向く |
| 変更コスト | 中（スクリプト編集） | 中（SKILL.md 編集） | 低（文章修正） |
| 代表例 | バージョンバンプ忘れ検知 / 禁止コマンド遮断 | セルフレビュー / Issue 作成 | 命名規約 / 言語設定 |

### CLAUDE.md → Hook 昇格の判断基準

CLAUDE.md に書いたルールが守られていない事象が以下いずれかに該当したら、Hook 昇格を検討する。

- 同じ違反が 2 回以上発生している（履歴・コミットログから確認）
- 違反した場合の修復コストが高い（後から辿ると手戻りが大きい、データ損失、外部影響）
- 判定ロジックがルールベースで表現可能（if/grep/diff で書ける）

逆に、以下に該当する場合は CLAUDE.md / Skill に留める。

- 文脈依存で例外が多い（「基本は X、ただし Y のときは Z」）
- 違反してもリカバリが容易
- 判定に自然言語理解が必要

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
| `issue:completed` | Issue ファイルの status が completed に遷移 | linear-workflow / indie-workflow | **indie-workflow:retrospective**（実装済） |
| `feature:implemented` | feature-dev Phase 7 完了 | **feature-dev**（実装済） | - |
| `commit:created` | git commit 成功（PostToolUse Bash matcher で検知） | **dev-workflow**（実装済） | - |
| `review:completed` | code-review Step 7（レポート出力後） | **code-review**（実装済） | - |

### Publisher の責務

- 自プラグインの hook 内で `event_bus_publish` を呼ぶ
- payload は最小限の JSON（issue_id / file path / 識別子のみ。本文は含めない）
- 副作用がある場合は payload に冪等性キーを含める

### Subscriber の責務

- `event_bus_tail` で読み出し、自前で dedup（ts + event 名 + payload のハッシュ等）
- イベントログのフォーマットが将来変わる可能性があるので JSON Lines パーサ前提で実装
- Hook 内での重い処理は禁止（必要なら別 skill / agent に委譲）

### デバッグ

```bash
# 直近 10 件
tail -n 10 .claude/events.jsonl

# 特定イベントを追う
grep '"event":"issue:completed"' .claude/events.jsonl | jq .
```

### 設計判断: なぜ JSON Lines + ファイル？

- Claude Code はローカル CLI なので EventBridge / Redis Pub/Sub は過剰
- 記事の「デバッグ困難」リスクは `tail` / `grep` でカバー
- セッション跨ぎで参照可能（git にコミットしないが project-local には残る）
- 全プラグインに既に配布されている `safe-hook.sh` に乗せられるので追加配布物なし

## CHANGELOG 規約

- 各プラグインに `CHANGELOG.md` を配置（Keep a Changelog 形式）
- バージョンバンプ時は CHANGELOG.md の更新必須（pre-commit hook で強制）
- Conventional Commits type との対応: `feat` → Added / `fix` → Fixed / `refactor` → Changed / `chore` → 原則省略

## Gotchas

- **marketplace.json の同期忘れ**: plugin.json の version/description を更新したら `.claude-plugin/marketplace.json` も必ず同期する。pre-commit の `validate-ssot.sh` がブロックする
- **hooks の stdin 消費**: hook スクリプトは必ず stdin を消費してから処理を開始する。消費しないとハングする。`safe-hook.sh` の `safe_hook_init` が自動で消費するため、全 hook は `source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh"` 経由で書く
- **hooks の stdout**: hook スクリプトの stdout が Claude のコンテキストに注入される。条件付き注入は `safe_hook_error <category>` で silent exit 0（Validation/Dependency/Auth/NotFound はサイレント、Unexpected のみ stderr に通知）
- **safe-hook.sh の同期**: 正本は `.claude-plugin/lib/safe-hook.sh`。各プラグインの `hooks/lib/safe-hook.sh` は byte-identical な複製。`/quality-check` で同期を検証する（不一致は Critical）
- **バージョンバンプ忘れ**: プラグインの内容を変更したら必ず plugin.json の version を上げる。上げないと使用側で更新が検知されない。pre-commit hook でブロックされる
- **CHANGELOG 未更新**: バージョンバンプ時は CHANGELOG.md も更新必須。pre-commit hook でブロックされる
- **_requirements の同期忘れ**: プラグインの依存先が変わったら plugin.json の `_requirements` と `check-deps.sh` の両方を更新する。pre-commit の `validate-ssot.sh` が `check_xxx "<name>"` 形式の一致を検証する
- **hooks.json の args[] exec 形式 (CC 2.1.139+)**: 新規 hook は `command: "bash <path>"` ではなく `command: "bash", args: ["<path>"]` の exec 形式で書く。シェル解釈を経由せず直接 spawn するので安全＆高速。スキーマは `.claude-plugin/schema/hooks.schema.json` を参照
- **terminalSequence helpers (CC 2.1.141+)**: `safe-hook.sh` の `safe_hook_emit_bell` / `safe_hook_emit_window_title` は端末ベル / ウィンドウタイトルを JSON 出力で送る。`safe_hook_emit` (plain text) と**混在不可**（terminalSequence は単独 JSON 出力）。長時間処理の完了通知や警告アラートに opt-in で利用する
- **${CLAUDE_EFFORT} skill 適応分岐 (CC 2.1.120+)**: SKILL.md / コマンド本文に `${CLAUDE_EFFORT}` を書くと実行時 effort (low/medium/high/xhigh/max) が展開される。深掘り skill では `low/medium → 速度優先、xhigh/max → 多重 agent` のような条件分岐を入れる。frontmatter の `effort:` は宣言（既定値）、本文の `${CLAUDE_EFFORT}` は実行時値

## バージョニング規約

- MAJOR: 破壊的変更（スキル/コマンドの削除・リネーム）
- MINOR: 機能追加（新スキル/コマンド、既存機能拡張）
- PATCH: 修正（バグ修正、ドキュメント、リファクタ）

## 品質チェック

プラグインの新規作成・変更時は `/quality-check` で全プラグインの品質バリデーションを実行する。
個別のスキル開発時は plugin-dev の agent team（plugin-validator, skill-reviewer）を活用する。

**自動チェック（Stop hook）**: プラグイン関連ファイル（`*/plugin.json` / `*/skills/` / `*/commands/` / `*/hooks/` / `*/references/` / `marketplace.json` / `*/CHANGELOG.md`）を変更した状態でターン終了を迎えると、`.claude-plugin/scripts/auto-quality-check.sh` が以下を自動実行し、問題を stderr に通知する（Stop はブロックしない）。`.claude/settings.json` で設定。

- `validate-ssot.sh`: スキーマ準拠 / marketplace 同期 / _requirements ↔ check-deps.sh
- `validate_plugin_quality.py`: allowed-tools 存在・command↔skill ペア一致 / hooks.json 参照スクリプトの safe_hook_init / safe-hook.sh 同期 / references 参照整合性 / トリガーフレーズ存在
- `claude plugin validate`: CLI スキーマ（`_requirements` 警告は除外）

LLM 判定が必要な項目（CLAUDE.md 品質、allowed-tools 最小性、プロジェクト固有情報検出等）は手動 `/quality-check` 側に残る。

スキルの description / トリガーフレーズを変更した場合は `evals/runner.py` で回帰テストを実行する（`claude-meta:eval-runner` スキル経由も可）。pass^k=3 基準でスキル選択の安定性を検証できる。ローカル実行のみ（CI 非対応、通常セッション枠を消費）。

## ブランチ運用

- main に直接コミット
