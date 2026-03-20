---
name: git-commit-helper
description: |
  Git専門エージェントによる原子性重視の高品質コミット作成。
  変更を分析し、論理的な作業単位に分割して、Conventional Commits準拠の日本語メッセージでコミットする。
  使用タイミング: ユーザーが「コミットして」「/git-commit-helper」「変更をコミット」と言った時。
  引数: --no-protect (Protected branchへの直接コミット許可), --with-push (コミット後に自動プッシュ)
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

# Git Commit Helper

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

同一ファイル内に複数作業がある場合は、関連するファイルを `git add <file>` で個別にステージングする。
全ファイルをまとめてステージングする場合は `git add .` を使用する。
注意: `git add -p` は対話的操作のためClaude Codeでは使用不可。ファイル単位でのステージングで代替すること。

分割の詳細パターンは [references/staging-patterns.md](references/staging-patterns.md) を参照。

### 4. コミットメッセージ

フォーマット: `<type>[(scope)]: <日本語description>`

- リポジトリの直近のコミットスタイルに合わせる
- 日本語表現: 追加→「を追加」、修正→「を修正」、リファクタ→「を整理/最適化」

### 5. フック対応とプッシュ

- pre-commitフック失敗時: 原因を修正し、**新しいコミットを作成**（amendしない）
- `--with-push`指定時: コミット成功後に `git push`
- 最後に `git status` で結果報告

## 絶対厳守ルール

- AI・ツール関連の記述は一切禁止（Co-Authored-By, Generated with, AI-assisted等）
- 開発者が手動で作成したかのような自然なメッセージにする
- `--no-verify` は使用禁止
