---
name: git-commit-helper
description: |
  Git専門エージェントによる原子性重視の高品質コミット作成。
  変更を分析し、論理的な作業単位に分割して、Conventional Commits準拠の日本語メッセージでコミットする。
  トリガー: ユーザーが「コミットして」「/git-commit-helper」「変更をコミット」と言った時。
  引数: --no-protect (Protected branchへの直接コミット許可), --with-push (コミット後に自動プッシュ)
effort: medium
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
  - AskUserQuestion
---

# Git Commit Helper

## 設計原則: Generator として動作する

このスキルは変更を生成・コミットする Generator 側を担う。コミット前の品質判定（バグ・セキュリティ・規約違反）は Evaluator 側である `code-review:self-review` を **別コンテキスト** で呼び出して行うことを推奨する。

- 推奨フロー: 実装 → `/self-review` → 修正 → `/git-commit-helper`
- 理由: 同一コンテキストで生成と判定を行うと confirmation bias で見落としが増える
- 自身では品質判定をしない（UI 変更時の snap のみ Step 4.5 で扱う）

## 実行手順

### 1. 安全性チェック

```bash
git branch --show-current
git status
git diff
git diff --cached
git log --oneline -10
```

- Protected branch (main/staging/production/develop) の場合、`--no-protect`がなければ即中止
- 変更がなければ終了

### 2. コミット分割判定

**1コミット = 1作業単位。** 以下は必ず分割:
- 実装とテスト
- 機能追加とリファクタリング
- 異なるコンポーネントの変更
- 設定変更と機能変更
- バグ修正と機能改善
- フォーマット修正と実質的変更

判定: 「変更理由を1文で説明できるか？」→ できなければ分割。

### 3. ステージングと実行

ステージング順: 設定/インポート → 型定義 → ユーティリティ → コア実装 → テスト(別コミット) → ドキュメント(別コミット)

- ファイル単位: `git add <file>` で個別にステージング
- 全ファイル: `git add .` でまとめてステージング
- **同一ファイル内の分割**: `git add -p` は対話的操作のため使用不可。代わりにパッチベースのステージングを使用する

同一ファイル内の hunk 分割手順は [references/staging-patterns.md](references/staging-patterns.md) を参照。

### 4. コミットメッセージ

フォーマット: `<type>[(scope)]: <description>`

コミットメッセージ言語: **${user_config.commit_language}**
- ja: 日本語で記述。追加→「を追加」、修正→「を修正」、リファクタ→「を整理/最適化」
- en: 英語の命令形で記述（Add, Fix, Refactor 等）
- リポジトリの直近のコミットスタイルに合わせる

### 4.5 UI 変更時の自動確認（条件付き）

以下すべてを満たす場合のみ実行する:

- `.claude/.ui-verify-enabled` が存在（SessionStart の detect-web-project.sh が設定）
- 変更差分に UI 拡張子ファイル（tsx/jsx/vue/svelte/css/scss/html/astro/mdx）が含まれる
- `.claude/.ui-verify-pending` が存在 OR `.claude/screenshots/` に直近5分以内の snap がない
- ユーザー引数に `--no-ui-verify` が含まれない

手順:

1. ユーザーに「UI 変更を検知したので snap を撮る？」と `AskUserQuestion` で確認（選択肢: 撮る / スキップ / 撤回）
2. 「撮る」選択時は ui-verify スキルを呼び出して `snap` モードを実行、保存先は `.claude/screenshots/commit-$(date +%s)/`
3. snap 完了後に `rm -f .claude/.ui-verify-pending` でフラグクリア
4. 「スキップ」なら `rm -f .claude/.ui-verify-pending` でフラグのみクリアしてコミット続行

この分岐をスキップした場合でも、PreToolUse gate hook が `git commit` 実行時に reminder を出す点に注意する。

### 5. フック対応とプッシュ

- pre-commitフック失敗時: 原因を修正し、**新しいコミットを作成**（amendしない）
- `--with-push`指定時: コミット成功後に `git push`
- 最後に `git status` で結果報告

## 絶対厳守ルール

- AI・ツール関連の記述は一切禁止（Co-Authored-By, Generated with, AI-assisted等）
- 開発者が手動で作成したかのような自然なメッセージにする
- `--no-verify` は使用禁止
