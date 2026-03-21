# CLAUDE.md - claude-plugins

Claude Code プラグインのマーケットプレイスリポジトリ。

## リポジトリ構造

```
.claude-plugin/marketplace.json  # マーケットプレイスマニフェスト
{plugin-name}/                   # 各プラグイン（独立したディレクトリ）
  .claude-plugin/plugin.json     # プラグインマニフェスト
  commands/                      # スラッシュコマンド定義（YAML frontmatter + markdown）
  skills/                        # スキル定義（SKILL.md + references/）
  hooks/                         # フック定義（hooks.json + scripts/）
  rules/                         # SessionStart 等で注入されるルール
  README.md
```

> LICENSE ファイルは不要（各プラグインに個別のライセンスファイルを置かない）

## プラグイン一覧

| プラグイン | コマンド | スキル | hooks | 説明 |
|-----------|---------|-------|-------|------|
| instinct-memory | 3 | 1 | Stop | セッション中のパターン学習と auto memory 管理 |
| code-review | 2 | 2 | - | 並列エージェントによる PR レビュー / セルフレビュー |
| dev-workflow | 2 | 2 | - | Git コミット・PR 作成の開発ワークフロー |
| claude-meta | 1 | 2 | - | Claude Code 設定管理・CLAUDE.md 監査改善 |
| linear-workflow | 5 | 5 | SessionStart | Linear MCP 連携の Issue/プロジェクト管理 |
| indie-workflow | 6 | 6 | SessionStart | 個人開発向けローカル Issue 管理（linear-workflow と排他） |
| plugin-manager | 1 | - | - | インストール済みプラグインの一括更新 |

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
- スキルの description にはトリガーフレーズを含める
- commands/ と skills/ の allowed-tools は一致させる

## Gotchas

- **marketplace.json の同期忘れ**: plugin.json の version/description を更新したら `.claude-plugin/marketplace.json` も必ず同期する
- **hooks の stdin 消費**: hook スクリプトは必ず `cat > /dev/null` で stdin を消費してから処理を開始する。消費しないとハングする
- **hooks の stdout**: hook スクリプトの stdout が Claude のコンテキストに注入される。条件付き注入は exit 0 で空出力にする
- **バージョンバンプ忘れ**: プラグインの内容を変更したら必ず plugin.json の version を上げる。上げないと使用側で更新が検知されない。pre-commit hook でブロックされる

## バージョニング規約

- MAJOR: 破壊的変更（スキル/コマンドの削除・リネーム）
- MINOR: 機能追加（新スキル/コマンド、既存機能拡張）
- PATCH: 修正（バグ修正、ドキュメント、リファクタ）
- plugin.json と marketplace.json の version は必ず同期する

## 品質チェック

プラグインの新規作成・変更時は以下を実行:
- `/quality-check` で全プラグインの品質バリデーション
- `plugin-dev:plugin-validator` でバリデーション
- `plugin-dev:skill-reviewer` でスキル品質レビュー

## ブランチ運用

- main に直接コミット
