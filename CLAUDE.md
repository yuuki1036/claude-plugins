# CLAUDE.md - claude-plugins

Claude Code プラグインのマーケットプレイスリポジトリ。

## リポジトリ構造

```
.claude-plugin/marketplace.json  # マーケットプレイスマニフェスト
.githooks/pre-commit             # バージョンバンプ・CHANGELOG 必須チェック
{plugin-name}/                   # 各プラグイン（独立したディレクトリ）
  .claude-plugin/plugin.json     # プラグインマニフェスト
  commands/                      # スラッシュコマンド定義（YAML frontmatter + markdown）
  skills/                        # スキル定義（SKILL.md + references/）
  agents/                        # エージェント定義（frontmatter付き markdown）
  hooks/                         # フック定義（hooks.json + scripts/）
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
| dev-workflow | 2 | 2 | - | SessionStart, PreToolUse | Git コミット・PR 作成の開発ワークフロー |
| claude-meta | 2 | 3 | - | - | Claude Code 設定管理・CLAUDE.md 監査改善・CCアップデート追従 |
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

## CHANGELOG 規約

- 各プラグインに `CHANGELOG.md` を配置（Keep a Changelog 形式）
- バージョンバンプ時は CHANGELOG.md の更新必須（pre-commit hook で強制）
- Conventional Commits type との対応: `feat` → Added / `fix` → Fixed / `refactor` → Changed / `chore` → 原則省略

## Gotchas

- **marketplace.json の同期忘れ**: plugin.json の version/description を更新したら `.claude-plugin/marketplace.json` も必ず同期する
- **hooks の stdin 消費**: hook スクリプトは必ず `cat > /dev/null` で stdin を消費してから処理を開始する。消費しないとハングする
- **hooks の stdout**: hook スクリプトの stdout が Claude のコンテキストに注入される。条件付き注入は exit 0 で空出力にする
- **バージョンバンプ忘れ**: プラグインの内容を変更したら必ず plugin.json の version を上げる。上げないと使用側で更新が検知されない。pre-commit hook でブロックされる
- **CHANGELOG 未更新**: バージョンバンプ時は CHANGELOG.md も更新必須。pre-commit hook でブロックされる
- **_requirements の同期忘れ**: プラグインの依存先が変わったら plugin.json の `_requirements` と `check-deps.sh` の両方を更新する

## バージョニング規約

- MAJOR: 破壊的変更（スキル/コマンドの削除・リネーム）
- MINOR: 機能追加（新スキル/コマンド、既存機能拡張）
- PATCH: 修正（バグ修正、ドキュメント、リファクタ）

## 品質チェック

プラグインの新規作成・変更時は `/quality-check` で全プラグインの品質バリデーションを実行する。
個別のスキル開発時は plugin-dev の agent team（plugin-validator, skill-reviewer）を活用する。

## ブランチ運用

- main に直接コミット
