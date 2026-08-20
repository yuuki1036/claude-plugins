---
name: git-commit-helper
description: |
  原子性重視の高品質コミット作成。
  変更を分析し、論理的な作業単位に分割して、Conventional Commits準拠の日本語メッセージでコミットする。
  トリガー: ユーザーが「コミットして」「/git-commit-helper」「変更をコミット」と言った時。
  引数: --no-protect (Protected branchへの直接コミット許可), --with-push (コミット後に自動プッシュ)
effort: medium
allowed-tools:
  - Bash
  - Read
  - Skill
---

# Git Commit Helper

## 設計原則: Generator として動作する

このスキルは変更を生成・コミットする Generator 側を担う。コミット前の品質判定（バグ・セキュリティ・規約違反）は Evaluator 側である `code-review:self-review` を **別コンテキスト** で呼び出して行うことを推奨する。

- 推奨フロー: 実装 → `/self-review` → 修正 → `/git-commit-helper`
- 理由: 同一コンテキストで生成と判定を行うと confirmation bias で見落としが増える
- 自身では品質判定をしない（UI 変更の動作確認も持たない。`ui-verify-gate.sh` が commit 直前に非ブロッキングで通知する）

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

> **コミット粒度と PR 粒度は別レイヤー**: コミットは上記の通り原子分割する（実装コミットとテストコミットを分ける）が、**レビュー単位（PR）の中では実装とテストを揃える**。テストだけを別 PR に切り出さず、1 つの PR でレビュアーが変更の正しさを判断できる self-contained な状態を保つ（Google eng-practices "Small CLs: include related test code"）。pr-creator の Small CL 規約とこの 2 層モデルで整合する。

**分割単位を決める前に、変更全体を一度眺めてから段階的に検討すること:**

1. `git diff` 全体を俯瞰し、変更されたファイルの依存関係・役割を把握
2. 論理的な作業単位を identify（異なるコンポーネント・異なる目的で切る）
3. ステージング順序（後述）に沿って commit 計画を立てる

独立した変更が混在していると後のレビュー・revert が困難になるため、迷ったら分割を優先すること。

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

#### 4.2 writing-polish 連携（コミットメッセージ添削・opt-in）

`writing-polish` plugin が同居していれば、生成したコミットメッセージの description 部分をコミット実行の直前に writing-polish へ渡して推敲できる（冗長削減・曖昧語の具体化・トーン統一・AI っぽさ除去）。未インストール時は本ステップを完全に skip し、従来どおりコミットする（dormant・後方互換 100%）。1 行 subject が十分簡潔なら skip してよい。

1. インストール判定（check-deps.sh と同方式）:
   ```bash
   if grep -q '"writing-polish@' "$HOME/.claude/settings.json" 2>/dev/null; then
     WRITING_POLISH=1
   else
     WRITING_POLISH=0
   fi
   ```
   `WRITING_POLISH=0` → 本ステップを skip。
2. `WRITING_POLISH=1` のとき、`Skill` tool で `writing-polish:writing-polish` を呼ぶ。`--embed` を必ず付け、`--tone commit` を伝え、生成したコミットメッセージの description 部分を渡す。
3. 返ってきた推敲済みテキストを description の代わりに使う。ただし **`<type>(<scope>):` prefix 構造と言語設定は変更しない（description 文面のみ推敲）。絶対厳守ルール（AI・ツール関連の記述/Co-Authored-By/Generated with 禁止）を維持。違反する結果は破棄**。変更があれば「何を変えたか」を一言添える。
4. fallback: 呼び出し失敗時は warning を出し、添削前の本文で従来どおり完了する。

### 5. フック対応とプッシュ

- pre-commitフック失敗時: 原因を修正し、**新しいコミットを作成**（amendしない）
- `--with-push`指定時: コミット成功後に `git push`
- 最後に `git status` で結果報告

## 絶対厳守ルール

- AI・ツール関連の記述は一切禁止（Co-Authored-By, Generated with, AI-assisted等）
- 開発者が手動で作成したかのような自然なメッセージにする
- `--no-verify` は使用禁止
