---
name: self-review
description: |
  2フェーズ構成のセルフレビュー。PR不要でコミット/PR作成前に自分の変更を包括チェックする。
  Phase 1: コアレビュー（常時6+条件2エージェント）で基本的な問題を検出。
  Phase 2: Phase 1の結果とdiff特性に基づき、専門エージェントを動的に追加起動。
  全エージェント model: opus で品質最大化。
  Confidence scoring (0-100) で偽陽性をフィルタリングし、≥80の指摘のみ報告。
  トリガー: ユーザーが「セルフレビュー」「/self-review」「自分の変更を確認」「コミット前にチェック」と言った時。
  引数: [base branch] (省略時は自動検出、不明なら確認)
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
  - AskUserQuestion
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

`--staged` 引数が指定されている場合は `git diff --cached` のみを対象とし、未ステージの変更は除外する。

CLAUDE.md・規約ファイルを自動収集: `CLAUDE.md`, `.github/CONTRIBUTING.md`, `.eslintrc.*`, `prettier.config.*`

### 1.5. セッションコンテキスト読み込み

1. `.claude/session-context.md` の存在を確認する（Read）
2. ファイルが存在する場合:
   - frontmatter の `branch` と現在のブランチ名を比較する
   - **一致**: コンテキストを有効とし、Phase 1/Phase 2 の各エージェントプロンプトに追加する
   - **不一致**: stale なコンテキストとして無視する（ログ出力のみ）
3. ファイルが存在しない場合: 何もしない（従来通りの動作）

### 2. Phase 1 条件判定

- **React/Next.js判定**: `package.json`に`react`/`next`が含まれる → Agent #3にvercel-best-practices観点を追加
- **テストファイル判定**: diffにテストファイル(`.test.`, `.spec.`, `__tests__/`)が含まれる → Agent #7を起動
- **型定義判定**: diffに`type `または`interface `の追加/変更が含まれる → Agent #8を起動

### 3. Phase 1: コアレビュー（並列エージェント）

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

エージェント起動前に、以下のファイルを Read ツールで読み込むこと:

- `${CLAUDE_PLUGIN_ROOT}/references/agent-prompts.md` - エージェントのプロンプト詳細
- `${CLAUDE_PLUGIN_ROOT}/references/scoring-guide.md` - スコアリング詳細

**エージェント設定:**

- 全エージェントを `model: opus` で起動する
- `isolation: "worktree"` は使用しない（セルフレビューは未コミット変更を含むため、worktree では変更が見えない）

### 4. Phase 2 起動判定

Phase 1 の結果を集約した後、Phase 2 の起動を判定する。

**Phase 2 スキップ条件（全て満たす場合スキップ）:**
1. diff パターンマッチに該当するエージェントがない（Step 4.1）
2. Phase 1 の指摘が全て confidence < 70（深刻な懸念なし）
3. Phase 1 の指摘件数が 3 件以下

#### 4.1. diff パターンマッチ（静的判定）

変更ファイルのパスと diff 内容から、該当する専門エージェントを判定する。
判定マトリクスは `${CLAUDE_PLUGIN_ROOT}/references/agent-prompts.md` の「Phase 2 起動判定」セクションを参照。

#### 4.2. Phase 1 結果からの動的判定

Phase 1 エージェントの指摘内容に以下のパターンが含まれる場合、対応する Phase 2 エージェントを追加起動する:

| Phase 1 の指摘内容 | 追加起動するエージェント |
|---|---|
| セキュリティ脆弱性、インジェクション、認証バイパスへの言及 | セキュリティ分析 (#9) |
| N+1、パフォーマンス劣化、メモリリークへの言及 | パフォーマンス分析 (#10) |
| 破壊的変更、API互換性への言及 | API設計分析 (#11) |
| モジュール境界違反、循環依存への言及 | クロスカッティング影響分析 (#15) |

### 5. Phase 2: 専門レビュー（並列エージェント）

Phase 2 が起動する場合、該当するエージェントを並列で実行する。

| Agent | 起動条件 | 役割 |
|-------|----------|------|
| #9 | セキュリティ関連の変更 or Phase 1 で検出 | セキュリティ分析（OWASP） |
| #10 | パフォーマンスクリティカルな変更 or Phase 1 で検出 | パフォーマンス分析 |
| #11 | API/スキーマの変更 or Phase 1 で検出 | API設計・後方互換性分析 |
| #12 | 依存関係ファイルの変更 | 依存関係・サプライチェーン分析 |
| #13 | DB マイグレーションファイルの変更 | マイグレーション・データ整合性分析 |
| #14 | 設定ファイルの変更 | 設定・環境変数分析 |
| #15 | 共通モジュールの変更 or Phase 1 で検出 | クロスカッティング影響分析 |
| #16 | 変更ファイル数 ≥ 10 | パターン統一・一貫性分析 |

**エージェント設定:**

- 全エージェントを `model: opus` で起動する
- Phase 1 の指摘サマリを各エージェントのプロンプトに含める（引き継ぎ情報として）

プロンプト詳細は `${CLAUDE_PLUGIN_ROOT}/references/agent-prompts.md` の Phase 2 セクションを参照。

### 6. Confidenceスコアリングとフィルタリング

Phase 1 + Phase 2 の全指摘を統合し、各指摘に0-100のconfidenceスコアを付与。≥80のみ報告。

スコアリング詳細は `${CLAUDE_PLUGIN_ROOT}/references/scoring-guide.md` を参照。

### 7. レポート出力

```
## セルフレビュー結果

**総合評価**: X/10点
**レビュー構成**: Phase 1 (N agents) + Phase 2 (M agents)

### 指摘事項 (confidence ≥80)

1. [confidence: 95][バグ] Missing null check...
   ファイル: src/utils.ts:42

2. [confidence: 82][セキュリティ] Hardcoded secret...
   ファイル: src/config.ts:15

### 総括
- 変更の概要
- コミット前に修正すべき項目
- 確認推奨の観点
```

### 8. 修正方針の確認

指摘事項が1件以上ある場合のみ実行する。指摘が0件なら「問題なし」で完了。

`${CLAUDE_PLUGIN_ROOT}/rules/self-review-interaction.md` を Read で読み込み、そのルールに従って AskUserQuestion で修正方針を確認する。
