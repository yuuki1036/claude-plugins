---
name: self-review
description: |
  git diffベースのセルフレビュー。PR不要でコミット/PR作成前に自分の変更を包括チェックする。
  最大8つの専門エージェントを並列起動し、reviewと同等の品質でレビュー。
  Confidence scoring (0-100) で偽陽性をフィルタリングし、≥80の指摘のみ報告。
  使用タイミング: ユーザーが「セルフレビュー」「/self-review」「自分の変更を確認」「コミット前にチェック」と言った時。
  引数: [base branch] (省略時は自動検出、不明なら確認)
---

# Self Review

## reviewとの違い

- PR不要。ローカルのみで完結
- コミット前・PR作成前の品質ゲートとして使用

## 実行手順

### 1. base branchの特定と差分収集

```bash
# 引数でbase branchが指定されていればそれを使用
# 指定がなければデフォルトブランチを自動検出
git remote show origin | grep "HEAD branch" | sed 's/.*: //'
```

base branchが特定できない場合はユーザーに確認する。

```bash
# base branchとの全差分（コミット済み + 未コミット）
git diff "${BASE}..HEAD"
git diff
git diff --cached
git diff "${BASE}..HEAD" --name-only
git diff --name-only
git diff --cached --name-only
```

変更がなければ終了。

CLAUDE.md・規約ファイルを自動収集: `CLAUDE.md`, `.github/CONTRIBUTING.md`, `.eslintrc.*`, `prettier.config.*`

### 2. 条件判定

- **React/Next.js判定**: `package.json`に`react`/`next`が含まれる → Agent #3にvercel-best-practices観点を追加
- **テストファイル判定**: diffにテストファイル(`.test.`, `.spec.`, `__tests__/`)が含まれる → Agent #7を起動
- **型定義判定**: diffに`type `または`interface `の追加/変更が含まれる → Agent #8を起動

### 3. エージェント並列レビュー

| Agent | 起動条件 | 役割 |
|-------|----------|------|
| #1 | 常時 | CLAUDE.md準拠チェック (1/2) |
| #2 | 常時 | CLAUDE.md準拠チェック (2/2) |
| #3 | 常時 | バグ・ロジックエラー検出 |
| #4 | 常時 | git blame/履歴コンテキスト分析 |
| #5 | 常時 | サイレント失敗・エラーハンドリング分析 |
| #6 | 常時 | コメント正確性・陳腐化分析 |
| #7 | テストファイル変更時 | テストカバレッジ・品質分析 |
| #8 | 型定義変更時 | 型設計・不変条件分析 |

エージェントのプロンプト詳細は [../../references/agent-prompts.md](../../references/agent-prompts.md) を参照。
スコアリング詳細は [../../references/scoring-guide.md](../../references/scoring-guide.md) を参照。

### 4. Confidenceスコアリングとフィルタリング

各指摘に0-100のconfidenceスコアを付与。≥80のみ報告。

### 5. レポート出力

```
## セルフレビュー結果

**総合評価**: X/10点

### 指摘事項 (confidence ≥80)

1. [confidence: 95][バグ] Missing null check...
   ファイル: src/utils.ts:42

2. [confidence: 82][サイレント失敗] Empty catch block...
   ファイル: src/api.ts:23-25

### 総括
- 変更の概要
- コミット前に修正すべき項目
- 確認推奨の観点
```
