# code-review

Phase 0 トリアージ + 動的エージェント構成のコードレビュープラグイン。diff を分析して explorer（探索）→ reviewer（レビュー）を動的に構成し、対象コードの複雑さに応じて冗長化。全エージェント model: opus。Confidence scoring (0-100) で偽陽性をフィルタリングし、≥80 の指摘のみ報告。

## 含まれるスキル

### review

PR ベースのコードレビュー。PR が必須（`gh pr diff` で差分を取得）。

**トリガー**: 「レビューして」「/review」「コードレビュー」

**引数**: `[PR番号]` (省略時は現在のブランチに紐づく PR を自動取得)

### self-review

セルフレビュー。PR 不要でコミット前・PR 作成前に自分の変更を包括チェック。base branch からの全差分（コミット済み + 未コミット）が対象。

**トリガー**: 「セルフレビュー」「/self-review」「自分の変更を確認」「コミット前にチェック」

**引数**: `[base branch]` (省略時は自動検出、不明なら確認)

## レビュー構成

### Phase 0: トリアージ（メインコンテキスト）

diff の特性を分析し、エージェント構成を動的に決定する。

- **Stage 1**: タイプ判定（explorer が必要か、どの reviewer 観点が必要か）
- **Stage 2**: 体数・フォーカス・冗長度決定（対象コードの複雑さに応じて同一観点を複数体起動）

### 探索フェーズ: explorer（0-6 体）

事実収集に特化。問題の判定は行わず、コードフロー・依存関係・副作用を構造化サマリとして収集。

| focus | 役割 |
|-------|------|
| function-flow | 関数の全フロー追跡（分岐・副作用含む） |
| dependency-trace | import/依存関係の追跡 |
| branch-impact | 条件分岐の既存動作と新条件の影響調査 |
| history-context | git blame/履歴による文脈収集 |
| shared-module-impact | 共通モジュールの影響範囲調査 |

### レビューフェーズ: reviewer（2-10 体）

問題検出 + confidence スコアリング。explorer 結果を入力として活用。

| focus | 条件 |
|-------|------|
| bug-detection | 常時必須 |
| claude-md-compliance | 常時必須 |
| error-handling | エラー処理の変更時 |
| comment-accuracy | コメント変更時 |
| test-quality | テストファイル変更時 |
| type-design | 型定義変更時 |
| security | セキュリティ関連の変更時 |
| performance | DB/ループ/キャッシュ関連の変更時 |
| api-design | API/ルート変更時 |
| dependency | 依存関係ファイルの変更時 |
| migration | マイグレーションファイルの変更時 |
| config | 設定ファイルの変更時 |
| cross-cutting | 共通モジュールの変更時 |
| pattern-consistency | 変更ファイル数 ≥ 10 |
| spec-compliance | Issue/knowledge が存在する時 |

React/Next.js プロジェクトでは bug-detection に vercel-best-practices の観点が自動追加される。

### 冗長化（同一観点の複数体起動）

対象コードの複雑さが高い場合、同一観点の reviewer を異なる angle（分析の切り口）で複数体起動し、複数視点のマージで確度を向上させる。

## Confidence スコアリング

各指摘に 0-100 の confidence スコアを付与し、≥80 の指摘のみを報告する。冗長ペアの合意で +10、explorer の裏付けで +10 の加算。
