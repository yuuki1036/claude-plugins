# claude-meta

Claude Code 自体の設定管理・改善を支援するプラグイン。コードベース分析によるセットアップ推奨、CLAUDE.md の品質監査・改善、セッション学習の反映を行う。

## 含まれるスキル

### claude-code-setup

コードベースを分析し、ユーザーレイヤー（`~/.claude/`）の既存設定を考慮した上で Claude Code オートメーション（Hooks, Skills, MCP Servers, Subagents, Plugins）を推奨する。読み取り専用で、分析と推奨のみ行う。

**トリガー例**: 「セットアップ推奨」「recommend automations」「Claude Codeのセットアップ」「どんなhookを使うべき?」

**参照ファイル**:
- `references/hooks-patterns.md` - Hook 設定パターン
- `references/mcp-servers.md` - MCP サーバー推奨パターン
- `references/skills-reference.md` - スキル推奨パターン
- `references/subagent-templates.md` - サブエージェントテンプレート
- `references/plugins-reference.md` - プラグイン一覧

### claude-md-improver

リポジトリ内の CLAUDE.md ファイルを検出し、品質基準に基づいて評価・改善する。品質レポートを出力した後、ユーザーの承認を得て改善を適用する。

**トリガー例**: 「CLAUDE.md を監査して」「CLAUDE.md を改善して」「project memory optimization」

**参照ファイル**:
- `references/quality-criteria.md` - 品質評価ルーブリック
- `references/templates.md` - プロジェクトタイプ別テンプレート
- `references/update-guidelines.md` - 更新時のガイドライン

## 含まれるコマンド

### revise-claude-md

セッション中の学習内容を CLAUDE.md に反映するスラッシュコマンド。セッションで発見したコマンド、コードスタイル、テスト手法、設定の注意点などを簡潔にまとめ、ユーザーの承認を得て CLAUDE.md を更新する。

## 使い方

1. プラグインをインストールする
2. スキルは会話中に自動的にトリガーされるか、スラッシュコマンドで呼び出せる
3. `/revise-claude-md` でセッションの学習内容を CLAUDE.md に反映できる
