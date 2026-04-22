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
| instinct-memory | 3 | 1 | - | Stop, PostCompact | セッション中のパターン学習と auto memory 管理 |
| code-review | 2 | 2 | - | SessionStart | Phase 0 トリアージ + 動的エージェント構成コードレビュー / セルフレビュー |
| dev-workflow | 3 | 3 | - | SessionStart, PreToolUse, PostToolUse | Git コミット・PR 作成・UI 動作確認の開発ワークフロー（chrome-devtools MCP 同梱） |
| claude-meta | 2 | 4 | - | - | Claude Code 設定管理・CLAUDE.md 監査改善・CCアップデート追従・eval 回帰テスト |
| linear-workflow | 8 | 8 | 3 | SessionStart, PostCompact, UserPromptSubmit, FileChanged | Linear MCP 連携の Issue/プロジェクト管理 |
| indie-workflow | 8 | 8 | 2 | SessionStart, PostCompact, UserPromptSubmit, FileChanged | 個人開発向けローカル Issue 管理（linear-workflow と排他） |
| plugin-manager | 1 | - | - | - | インストール済みプラグインの一括更新 |
| plugin-feedback | 1 | 1 | - | SessionStart | プラグインへの改善要望・バグ報告を GitHub Issue 化 |

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

## バージョニング規約

- MAJOR: 破壊的変更（スキル/コマンドの削除・リネーム）
- MINOR: 機能追加（新スキル/コマンド、既存機能拡張）
- PATCH: 修正（バグ修正、ドキュメント、リファクタ）

## 品質チェック

プラグインの新規作成・変更時は `/quality-check` で全プラグインの品質バリデーションを実行する。
個別のスキル開発時は plugin-dev の agent team（plugin-validator, skill-reviewer）を活用する。

**自動チェック（Stop hook）**: プラグイン関連ファイル（`*/plugin.json` / `*/skills/` / `*/commands/` / `*/hooks/` / `marketplace.json` / `*/CHANGELOG.md`）を変更した状態でターン終了を迎えると、`.claude-plugin/scripts/auto-quality-check.sh` が validate-ssot.sh + claude plugin validate を自動実行し、問題を stderr に通知する（Stop はブロックしない）。`.claude/settings.json` で設定。

スキルの description / トリガーフレーズを変更した場合は `evals/runner.py` で回帰テストを実行する（`claude-meta:eval-runner` スキル経由も可）。pass^k=3 基準でスキル選択の安定性を検証できる。ローカル実行のみ（CI 非対応、通常セッション枠を消費）。

## ブランチ運用

- main に直接コミット
