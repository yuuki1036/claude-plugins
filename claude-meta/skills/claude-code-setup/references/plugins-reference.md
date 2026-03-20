# Plugin推奨パターン

プラグインはskills, commands, agents, hooksのインストール可能なコレクション。
`/plugin install` でインストール。

## 公式プラグイン

### 開発・コード品質

| プラグイン | 用途 |
|-----------|------|
| plugin-dev | プラグイン開発 |
| pr-review-toolkit | PRレビューワークフロー |
| code-review | 自動コードレビュー |
| code-simplifier | コードリファクタリング |
| feature-dev | 機能開発ワークフロー |

### Git・ワークフロー

| プラグイン | 用途 |
|-----------|------|
| commit-commands | /commit, /commit-push-pr |
| hookify | 会話パターンからhook作成 |

### フロントエンド

| プラグイン | 用途 |
|-----------|------|
| frontend-design | プロダクション品質のUI開発 |

### 学習・ガイダンス

| プラグイン | 用途 |
|-----------|------|
| explanatory-output-style | コード選択の教育的説明 |
| learning-output-style | 判断ポイントでのインタラクティブ学習 |
| security-guidance | セキュリティ問題の警告 |

### 言語サーバー (LSP)

| プラグイン | 言語 |
|-----------|------|
| typescript-lsp | TypeScript/JavaScript |
| pyright-lsp | Python |
| gopls-lsp | Go |
| rust-analyzer-lsp | Rust |
| clangd-lsp | C/C++ |
| jdtls-lsp | Java |

## クイックリファレンス

| コードベースシグナル | 推奨プラグイン |
|-------------------|--------------|
| プラグイン開発 | plugin-dev |
| PR中心のワークフロー | pr-review-toolkit |
| Gitコミット | commit-commands |
| React/Vue/Angular | frontend-design |
| オートメーション | hookify |
| TypeScript | typescript-lsp |
| Python | pyright-lsp |
| セキュリティ重視 | security-guidance |
