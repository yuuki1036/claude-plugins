# Phase 0 トリアージガイド

Phase 0 はレビュー実行前にメインコンテキストで diff を分析し、エージェント構成を動的に決定するフェーズ。

## 1. Phase 0 概要

- メインコンテキストで実行する（Agent ツールは使わない）
- 2段階判定: Stage 1（タイプ判定）→ Stage 2（体数・フォーカス・冗長度決定）
- 出力はエージェント構成テーブル

## 2. 入力情報

Phase 0 実行前に以下の情報を収集する:

| 情報 | 取得方法 | 必須 |
|---|---|---|
| diff 全文 | `git diff` / `gh pr diff` | Yes |
| 変更ファイルリスト + 各ファイルの行数 | `--name-only` + `wc -l` | Yes |
| CLAUDE.md | プロジェクトルートから読み込み | 存在する場合 |
| session-context.md | 存在チェック + ブランチ一致チェック | 存在する場合 |
| Issue/knowledge ファイルの有無 | ファイル存在チェック | 存在する場合 |
| プロジェクト特性シグナル | `package.json` の主要依存 | 存在する場合 |

## 3. Stage 1: タイプ判定

### explorer の必要性判定

以下のいずれかに該当する場合、explorer が必要:

- 変更ファイルに500行超のファイルがある
- 3関数以上に跨がる変更
- if-else/switch への条件追加がある
- 共通モジュール（`utils/`, `shared/`, `lib/`, `common/`, `helpers/`）の変更
- 複数ファイル間でデータが流れる変更パターン

上記いずれにも該当しない場合、explorer はスキップする。

### reviewer の観点判定

diff パターンマッチで各観点の必要性を判定する。

| 観点 | 条件 |
|---|---|
| bug-detection | **常時必須** |
| claude-md-compliance | **常時必須** |
| error-handling | try-catch/catch ブロック/エラー処理の変更がある |
| comment-accuracy | diff にコメント（`//`, `/*`, `#`, `<!--` 等）の追加・変更がある |
| test-quality | テストファイル（`.test.`, `.spec.`, `__tests__/`）の変更がある |
| type-design | 型定義（`type`, `interface`, `enum`）の追加・変更がある |
| security | セキュリティ関連ファイル（`auth/`, `security/`, `crypto/`, `middleware/auth*`）の変更、または diff 内に `password`, `secret`, `token`, `api_key`, `eval(`, `innerHTML`, `dangerouslySetInnerHTML`, `` sql` ``, `query(` がある |
| performance | DB 関連ファイル、キャッシュ、キュー、ワーカーの変更、または diff 内に `SELECT`/`INSERT`/`UPDATE`/`DELETE`, `.find(`, `.findMany(`, `Promise.all`, ループ内の `await` がある |
| api-design | API/ルート/コントローラ/GraphQL/proto の変更、または `router.get`/`post`/`put`/`delete`, `@Get`/`@Post` 等がある |
| dependency | `package.json`, `*lock*`, `Gemfile*`, `requirements.txt`, `go.mod`, `Cargo.toml` の変更 |
| migration | マイグレーションファイル（`migrations/`, `prisma/migrations/`, `db/migrate/`）の変更 |
| config | `.env*`, `*.config.*`, `Dockerfile`, `docker-compose.*`, `.github/workflows/**` の変更 |
| cross-cutting | 共通モジュール（`utils/`, `helpers/`, `shared/`, `common/`, `lib/`）の変更 |
| pattern-consistency | 変更ファイル数 >= 10 |
| spec-compliance | `session-context.md` / Issue ファイル / knowledge ファイルが存在する |

### React/Next.js 判定

`package.json` に `react` / `next` が含まれる場合、bug-detection に **vercel-best-practices** 観点を追加する。

## 4. Stage 2: 体数・フォーカス決定

### explorer の体数

| diff 特性 | 体数 | focus の切り方 |
|---|---|---|
| 1ファイル、1関数フロー | 1 | その関数の全フロー |
| 1ファイル（巨大）、複数関数 | 関数フロー数（2-3） | 関数フロー単位 |
| 複数ファイル、1パイプライン | 1-2 | データフローパイプライン単位 |
| 複数ファイル、複数モジュール | 2-4 | モジュール境界ごと |
| 大規模リファクタ（10+ファイル） | 3-5 | アーキテクチャレイヤー単位 |
| 共通モジュールの変更 | +1 | 呼び出し元の影響範囲調査 |

- **上限: 6体**

### reviewer の冗長度判定

同一観点を複数体（x2）にする条件:

- 対象コードの分岐の深さが3以上（ネストした if-else）
- 変更関数が500行超
- 状態変異が3箇所以上（同一変数への代入が散在）
- 複数モジュール間のデータフローに影響
- explorer が「複雑」と報告した領域

### 冗長ペアの angle（分析の切り口）

**bug-detection の場合:**
- A = 「データフローの正しさ（変数の定義→変更→参照、意図しない上書き・未初期化）」
- B = 「制御フローの正しさ（分岐の全パス検証、到達不能コード、else 副作用）」

**security の場合:**
- A = 「入力バリデーション・インジェクション」
- B = 「認証・認可・アクセス制御」

他の観点も必要に応じて angle を設定する。

- **reviewer 上限: 10体**

## 5. 出力フォーマット

Phase 0 の出力はエージェント構成テーブルとして表示する。

```
## Phase 0 トリアージ結果

### 変更特性
- 規模: {small|medium|large}
- リスク因子: [巨大ファイル, 条件分岐追加, 共通モジュール変更, ...]
- コンテキスト: [session-context, issue-files, knowledge, ...]

### エージェント構成

#### 探索フェーズ（explorer）
| # | focus | 対象 | 指示 |
|---|---|---|---|
| E1 | function-flow | src/components/add.vue | savetree() の全フロー追跡 |
| E2 | branch-impact | src/components/add.vue | saveTreeTemp() の else ブランチ副作用調査 |

#### レビューフェーズ（reviewer）
| # | focus | angle | explorer依存 | 指示 |
|---|---|---|---|---|
| R1 | bug-detection | data-flow | E1, E2 | 変数ライフサイクル整合性チェック |
| R2 | bug-detection | control-flow | E1, E2 | 分岐副作用・データ破壊パターン検出 |
| R3 | claude-md-compliance | - | - | CLAUDE.md ルール照合 |
| R4 | spec-compliance | - | E1 | Issue 仕様との整合性検証 |
```

## 6. フォールバック構成

Phase 0 が明確な判断を下せない場合のデフォルト構成:

### small（変更ファイル <= 3, 変更行数 <= 100）

- explorer: 0体
- reviewer: 2体（bug-detection, claude-md-compliance）

### medium（変更ファイル 4-10, 変更行数 101-500）

- explorer: 1体（history-context）
- reviewer: 3体（bug-detection, claude-md-compliance, error-handling）

### large（変更ファイル > 10, 変更行数 > 500）

- explorer: 2体（history-context, dependency-trace）
- reviewer: 4体（bug-detection, claude-md-compliance, error-handling, cross-cutting）

## 7. 最小保証とフェーズ上限

- **最小保証**: reviewer-bugs + reviewer-claude-md の2体は Phase 0 の判断に関わらず常に起動
- **explorer 上限**: 6体
- **reviewer 上限**: 10体
