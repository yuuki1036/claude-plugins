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
| PR コンテキストブロック（review skill のみ） | SKILL.md Step 2.5 で構築（説明・issue コメント・レビューサマリ・行単位 review comment） | review skill で PR ありの場合 |
| CLAUDE.md | プロジェクトルートから読み込み | 存在する場合 |
| session-context.md | 存在チェック + ブランチ一致チェック | 存在する場合 |
| Issue/knowledge ファイルの有無 | ファイル存在チェック | 存在する場合 |
| プロジェクト特性シグナル | `package.json` の主要依存 | 存在する場合 |

## 2.5. PR 種別分岐ルール（Stage 0 / Stage 1 の前段）

Phase 0 の本判定（Stage 1 / Stage 2）に入る前に、**diff の構成から PR 種別を判定** し、レビュー構成を絞り込む。doc-only / migration / lockfile / generated code 等の特殊 PR では、通常の reviewer 群を全部当てると空振り・即興構成に陥り skill のスキャフォールドを実質無視することになる（GitHub issue #43）。

### 判定手順

1. `gh pr diff <PR番号> --name-only` で変更ファイル一覧を取得
2. 拡張子・パスパターンで分類し、以下の表に従ってモードを決定
3. 該当モードがあれば本表の「推奨 agent 構成」を Stage 2 の上限・最小保証より優先して採用
4. 「default-mode」になった場合のみ通常の Stage 1 / Stage 2 に進む

### PR 種別分岐ルール表

| シグナル（Phase 0 観測） | モード | 推奨 agent 構成 |
|---|---|---|
| `*.md` 比率 ≥ 80% | `doc-review-mode` | **整合性 reviewer**（リンク健全性 / SQL・コード片の安全性 / 構造整合性）は必須。さらに **doc-substance reviewer**（内容妥当性）を下記「doc-substance の起動（重要度ゲート）」の条件を満たす場合のみ追加（typo・整形だけの doc PR には付けない）。1〜2 体。bug-detection の最小保証は **doc 文脈に読み替え** （リンク切れ・誤情報を bug 相当として扱う） |
| SQL migration ファイル含む（`*/migrations/*.sql`, `prisma/migrations/`, `db/migrate/` 等） | `dba-mode` | migration reviewer 必須 + specialist-destructive-op。idempotency / lock 影響 / rollback 可能性 / 既存データへの影響に特化 |
| lockfile（`package-lock.json` / `yarn.lock` / `pnpm-lock.yaml` / `Cargo.lock` / `Gemfile.lock` / `poetry.lock` 等）主体（ロックファイルが全変更行数の 70% 以上） | `supply-chain-mode` | dependency reviewer 1 体に絞る。diff の CVE 観点 / 追加された未知パッケージ / postinstall 危険性に集中、ロック内部のハッシュ差分は読まない |
| Vendor / generated code 主体（`vendor/`, `node_modules/`, `*.pb.go`, `*.gen.ts`, `dist/`, `build/`, OpenAPI/GraphQL 自動生成ファイル等が 80% 以上） | `skip-mode` | レビューを基本スキップ。AskUserQuestion で「生成物のため通常レビュー対象外。続行しますか？」を確認し、`spec-compliance` のみ起動して仕様整合性のみ検証 |
| 上記いずれでもない | `default-mode` | 通常の Stage 1 / Stage 2 トリアージへ |

### 適用モードの透明性

決定したモードは Phase 0 構成テーブル出力に必ず含めること（SKILL.md Step 3.3 / 7）:

```
## Phase 0 トリアージ結果

### 適用モード
- mode: doc-review-mode
- 理由: 変更ファイル 12 件中 11 件が `*.md`（91.7%）
- 起動観点: 整合性（リンク/構造/コード片安全性）+ doc-substance（内容妥当性）
- スキャフォールドの一部スキップ: bug-detection / claude-md-compliance の最小保証は doc 文脈に読み替え
```

レポート冒頭 (TL;DR) にも `[mode: doc-review, agents: [doc-reviewer]]` のような 1 行ヘッダを表示し、レビュー判断のコンテキストをユーザーに伝える。

### モード判定の判定基準（曖昧ケース）

- ファイル比率は **変更ファイル数** で測る（行数比率ではない、巨大 lockfile に引っ張られすぎないため）
- 複数モードに該当する場合は **より厳しい絞り込み** を優先（`skip-mode` > `dba-mode` > `doc-review-mode` > `supply-chain-mode` > `default-mode`）
- モード判定で迷う場合は `default-mode` にフォールバック（保守的に振る舞う）

### 緊急レビューモード（`--emergency` 引数 / review skill のみ）

`--emergency` 引数が渡された場合（本番障害のホットフィックス等）、Google eng-practices "Emergencies" に従い **速度優先の最小構成** でレビューする。diff シグナルからの自動判定ではなく、人間が明示的に宣言する点が他モードと異なる（他のモード判定より優先する）。

- **起動**: reviewer-bugs + reviewer-security の最小 2 体のみ（specialist は red-flag 検出時のみ通常通り起動 — 緊急時こそインジェクション・破壊的操作の混入が危険なため）
- **スキップ**: explorer / 冗長ペア / Phase 5.5 (adaptive deepening) / Phase 5.6 (meta-reviewer)。速度と正しさのトレードオフをスコープ縮小で取る
- **レビューは省略しない**: 構成を絞るだけで「無レビュー」にはしない
- **レポート冒頭に必須バナー**: `⚠️ 緊急レビュー（最小構成）: マージ後に通常の /review を必ず実施すること`
- **緊急の定義**（eng-practices）: ロールバック回避 / 本番ユーザー影響のバグ修正 / 重大セキュリティ穴 / 法的緊急 等の **小さな** 変更に限る。soft deadline・疲労・タイムゾーンは緊急ではない（その場合は通常レビュー）
- mode 表記は `[mode: emergency, agents: [bug-detection, security]]`

---

## 3. Stage 1: タイプ判定

### explorer の必要性判定

以下のいずれかに該当する場合、explorer が必要:

- 変更ファイルに500行超のファイルがある
- 3関数以上に跨がる変更
- if-else/switch への条件追加がある
- **共通モジュール（`utils/`, `shared/`, `lib/`, `common/`, `helpers/`, `core/`）の変更** — **行数や関数数に関わらず必ず explorer 1 体（shared-module-impact）を起動**（v2.12.0 で緩和: 小規模変更でも依存元への波及を見落とさないため）
- 複数ファイル間でデータが流れる変更パターン（schema→domain→DB / FE→BE のような層跨ぎの値フローを含む場合は explorer に `value-flow-trace` focus を優先割り当てする）

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
| ui-quality | フロントエンド変更（`.tsx`/`.jsx`/`.vue`/`.svelte`/`components/`/`pages/`/`app/`）、または diff に `aria-`/`role=`/`<img`/`<button`/`tabindex`/`onClick`/`onKeyDown` 等のアクセシビリティ・インタラクション関連の変更がある |
| doc-substance | **高価値 doc**（`CLAUDE.md` / `AGENTS.md` / `CONTRIBUTING*` / `README*` / `.claude/adr/**` / `.claude/designs/**`）の prose 変更を含む、**または** 任意 `*.md` で実質 prose 変更（frontmatter / list マーカー / link-only 行を除いた追加・変更 prose 行が概ね 10 行以上）。混在 PR（`*.md` < 80%）で doc 内容が無観点で素通りするのを防ぐ。詳細・effort 制御は下記「doc-substance の起動（重要度ゲート）」 |

### doc-substance の起動（重要度ゲート）

doc の内容妥当性を **2 軸**（A 主張の真偽: コード整合・論理・規範・陳腐化・例の整合 ／ B 文書としての成立性: 完全性・doc 種別適合・読み手前提・WHY 根拠・ナビゲーション）で見る `doc-substance` 観点は、**変更ファイル数比率ではなく doc の意味的重要度**で起動する。ファイル数では小さいが意味的に重要な doc（CLAUDE.md 1 行 / ADR 1 件）を取りこぼさないため。

**起動条件（経路によらず共通）**: 次のいずれかを満たすとき起動する。満たさない doc 変更（typo 修正・整形・frontmatter のみ・link-only）には付けない。
- **高価値 doc**（`CLAUDE.md` / `AGENTS.md` / `CONTRIBUTING*` / `README*` / `.claude/adr/**` / `.claude/designs/**`）の prose 変更を含む
- **または** 任意 `*.md` で実質 prose 変更（frontmatter / list マーカー / link-only 行を除いた追加・変更 prose 行が概ね 10 行以上）

この条件を 2 つの起動経路の両方に適用する:

1. **doc-review-mode 経路**（`*.md` ≥ 80%）: 整合性 reviewer は必須。doc-substance は上記条件を満たす場合のみ追加（typo・整形だけの doc PR では整合性 reviewer のみ）
2. **混在 PR 経路**（`*.md` < 80%、default-mode）: 上の観点判定表の `doc-substance` 行（条件は上記と同一）で起動

**effort 別の起動制御**（反証レイヤーが効かない effort では偽陽性が素通りするため、起動自体を絞る）:

| 実行時 effort = `${CLAUDE_EFFORT}` | doc-substance 起動 |
|---|---|
| `low` | skip（反証も効かないため抑制） |
| `medium` | 高価値 doc パスを含む PR のみ |
| `high`（既定）/ `xhigh` / `max` | 重要度ゲート全面 |

**grounding（裏取り）**: 2 軸で裏取りの相手が異なる。
- **A 軸（主張 vs コード）**: 対象コードを読む。専用 explorer は必須化せず、既存の explorer 条件付き起動判定（本節「explorer の必要性判定」）に乗せ、対象コードが大きい / 分散する場合のみ起動する。単一ファイルの主張は reviewer 自身の Read で裏取りする（small PR フォールバック 0 体と非衝突）。explorer が読む対象は **diff で変更された doc が参照するコード ∩ リポジトリ実在パス**に限定し、doc 本文（＝レビュー対象＝信頼できない入力）の任意パス記述を鵜呑みにしない。
- **B 軸（文書としての成立性）**: 裏取りの相手は**コードではなく doc 種別の期待構造**（完全性 / doc 種別適合 / 読み手前提 / WHY / ナビ）なので、**コード grounding explorer は不要**。reviewer は doc:line（欠落・誤配置・孤立の発生箇所）＋ 破られた期待を示す。**例外: 「コードに新 API / フラグを追加したのに doc 更新が無い」完全性指摘**は、追加された API の所在確認に A 軸と同じコード読みを使う。

**design-review への soft 委譲（dormant）**: 決定系 doc（`.claude/adr/**` / `.claude/designs/**`）は `design-doc` プラグイン導入時のみ、doc-substance プロンプトに design-review の minimal / risk チェックリストを内挿して借りる。判定は `grep -q '"design-doc@' "$HOME/.claude/settings.json"`。未導入なら doc-substance が内製で代替する（スキル間呼び出しには依存しない）。

**境界**: frontmatter / link の鮮度は `doc-freshness`、**語句・トーン・冗長（最小差分の言い換えで直るもの）は `writing-polish`**、**doc 本文の主張の真偽・論理 ＋ 文書としての構造的成立性（完全性・doc 種別適合・読み手前提・WHY・ナビ。内容の追加・再配置・根拠補完が要るもの）は doc-substance**。判別線は「**語句を最小差分で言い換えれば済むか**」: 済む → writing-polish、内容・構造の変更が要る → doc-substance。決定系 doc（`.claude/adr/**` / `.claude/designs/**`）の設計妥当性は前述の design-review soft 委譲が優先。表現の好みは reviewer が自己削除せず低 confidence で申告し、scoring の ≤40 クランプが機械的に除外する（scoring-guide.md。B 軸の構造指摘は doc:line + 破られた期待を示せばクランプ対象外）。

### React/Next.js 判定

`package.json` に `react` / `next` が含まれる場合、bug-detection に **vercel-best-practices** 観点を追加する。
さらに UI 変更を検出した場合は ui-quality 観点も併用し、内部で同梱 reference `${CLAUDE_PLUGIN_ROOT}/references/modern-web-checklist.md`（Chrome Modern Web Guidance を Baseline ベースで照合可能にしたチェックリスト）に準拠させる。

### 外部ライブラリ最新仕様の参照

diff に外部ライブラリ（React, Next.js, Prisma, Vue, FastAPI 等）の API 利用変更が含まれ、その API の廃止・推奨パターン変更が指摘の核心となる場合、reviewer に公式 skill `context7` を経由した最新仕様確認を許可する（モデル学習データの cutoff を越える破壊的変更の誤判定を避けるため）。詳細は `reviewer-prompts.md` の共通指示を参照。

### Red-flag pattern による specialist 自動起動（v2.12.0 追加）

diff に以下の **危険パターン** が検出された場合、対応する specialist reviewer を **自動的に追加起動** する（行数・PR コンテキストに関わらず、Phase 0 で必ず起動）。検出ミスの構造的対策。

| パターン（diff 内文字列マッチ） | 起動する specialist | severity 目安 |
|---|---|---|
| `eval(`, `new Function(`, `vm.runIn`, `child_process`, `exec(`, `execSync`, `subprocess.run`, `os.system`, `` shell=True `` | **specialist-injection**（コード/コマンドインジェクション） | 大半 BLOCKER |
| `fs.unlink`, `fs.rm`, `rmSync`, `rm -rf`, `DROP TABLE`, `TRUNCATE`, `DELETE FROM .* WHERE` （WHERE 句なしの DELETE/UPDATE 含む）, `db.collection(...).drop()` | **specialist-destructive-op**（破壊的操作の意図確認） | BLOCKER または CRITICAL |
| `password =`, `secret =`, `api_key =`, `apiKey =`, `private_key`, `BEGIN PRIVATE KEY`, `Bearer .+`, `Authorization:` （ハードコード）, `console.log(.*password)`, `console.log(.*token)` | **specialist-secret-handling**（シークレット漏洩） | BLOCKER |
| `JSON.parse(.*req\.`, `parseInt(.*req\.`, `RegExp(.*user`, ユーザー入力の正規表現直接利用 | **specialist-input-validation**（信頼境界） | CRITICAL または BLOCKER |
| **ガードレール骨抜き** — lint / hook / static check 設定ファイル（`.golangci.yml`, `.eslintrc*`, `lefthook.yml`, `pre-commit*`, `redocly.yaml`, `tsconfig.json`, `ruff.toml`, `.rubocop.yml` 等）からの **ルール削除・無効化・severity 降格（error→warn）・適用範囲縮小**、または `--no-verify` / `--no-gpg-sign` / `disable_*` フラグの新規追加 | **specialist-guardrail-bypass**（骨抜き検出） | **BLOCKER 固定**（commit body に明示的 justify がない限り） |

**判定の原則**:
- 文字列マッチは false positive を伴うが、specialist の役割は「人間判断を促す」ことなので積極的に起動して問題ない
- specialist は対応する Focus テンプレート（reviewer-prompts.md `## 5. Specialist テンプレート`）を使用
- specialist の指摘は **大半が BLOCKER または CRITICAL** になるため、低 confidence でも報告マトリクスで人間に届く
- specialist は上限 6 体（reviewer 上限 10 体とは別枠、specialist 起動で reviewer 枠を圧迫しない）

### PR コンテキストによる観点追加・冗長化（review skill のみ）

SKILL.md Step 2.5 で構築した PR コンテキストブロックの内容も判定シグナルとして使う:

- PR 説明に「セキュリティ修正」「認可」「脆弱性」等の言及 → security 観点を追加
- PR 説明に「パフォーマンス改善」「最適化」「N+1」等の言及 → performance 観点を追加・冗長化
- PR 説明に「マイグレーション」「スキーマ変更」等の言及 → migration 観点を追加
- 行単位 review comment で特定観点（認可・エラーハンドリング等）が議論されている → 該当 reviewer を追加または冗長化
- 行単位 review comment が多数（10+）ある複雑な PR → reviewer を 1-2 体追加（押し戻しの重要性を踏まえた独立検証）

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
- **specialist 上限**: 6体（reviewer 枠とは別カウント、red-flag pattern 検出時のみ起動）

## 8. 動的ラウンド（Phase 5.5 / 5.6 / v2.12.0 追加）

### Phase 5.5: Adaptive deepening (追加 explorer ラウンド)

**起動条件**: 全 reviewer 完了後、reviewer の出力に `unmet_information` フィールドが 1 件以上ある場合のみ起動

**目的**: reviewer が「この観点を確定するには追加の context が必要」と自覚した領域に対して、追加 explorer を 1 round だけ走らせ、該当 reviewer のみ再実行する適応的深掘り

**動作**:
1. `unmet_information` を集約し、対象ファイル/フォーカスごとに追加 explorer を起動
2. 追加 explorer は `re-explore` フォーカス（explorer-prompts.md 参照）で起動
3. 該当 reviewer のみ再起動（他は再実行しない、コスト抑制）
4. 結果を初回 reviewer 結果と統合（重複指摘は dedup）

**上限**: 1 round のみ（多段化禁止）。追加 explorer 上限 3 体、再起動 reviewer 上限 3 体

### Phase 5.6: Meta-reviewer round

**起動条件**: Phase 5.5 完了後、フィルタリング前の指摘に **BLOCKER または CRITICAL** が 1 件以上ある場合のみ起動

**目的**: 高 severity 指摘が出た = 高リスク変更と判定し、別 reviewer に「ここまでの結果を踏まえて、他の reviewer が見落としている観点はないか」を問うメタレビュー

**動作**:
1. meta-reviewer agent (reviewer-prompts.md `## 6. Meta-reviewer テンプレート`) を 1 体起動
2. 入力: 全 reviewer の指摘リスト（フィルタ前）、diff、explorer 結果
3. 出力: 追加指摘（あれば。なくても OK）
4. meta-reviewer の指摘も通常のスコアリング・フィルタリング対象に含める

**上限**: 1 round のみ。meta-reviewer 1 体のみ

### effort 適応

| effort | Phase 5.5 (adaptive deepening) | Phase 5.6 (meta-reviewer) |
|---|---|---|
| low | スキップ | スキップ |
| medium | スキップ | スキップ |
| high (default) | unmet_information があれば起動 | スキップ |
| xhigh | 起動 | 起動 |
| max | 起動 | 起動 |

### userConfig による無効化

- `enable_adaptive_rounds: false` → Phase 5.5 を強制スキップ
- `enable_meta_reviewer: false` → Phase 5.6 を強制スキップ

両方デフォルト true。トークンコスト・レイテンシが気になる場合は false にする。

## 8.5. 冷や読み skeptic ラウンド（Phase 5.8 / 4.8 / recall 補強）

high-risk surface を含む変更に限り、事前所見と無関係に **findings 非注入の独立 skeptic を 1 体**起動し、fleet 共通の盲点（層跨ぎ値フロー等）を冷や読みで破る recall 補強フェーズ。反証レイヤー（false-positive 潰し）の鏡像＝ false-negative hunter として、**観点カバレッジ self-check の後・反証レイヤーの前**に挿入する（review=Phase 5.8 / self-review=Phase 4.8）。meta-reviewer（Phase 5.6）が findings 注入で非独立なため fleet 共通盲点を引きずるのに対し、skeptic は独立読み直しで盲点を破る。

### high-risk surface 判定

以下のいずれかを含む変更を high-risk surface とみなす（事前所見・severity と無関係に判定）:

1. **DB 書込**: `INSERT` / `UPDATE` / `DELETE` を含む生 SQL、または ORM の書込 API（`.create(` / `.update(` / `.save(` / `.insert(` / `.upsert(` 等）。performance 観点の起動条件（`## 3` の `INSERT|UPDATE` 正規表現）を surface 判定に転用する
2. **金銭・数量計算**: `amount` / `price` / `balance` / `quantity` / `stock` / 通貨・丸め・課金に関わる numeric 演算
3. **認可・認証**: 権限チェック / セッション / トークン / ロール判定に関わる変更
4. **PR 自己申告 D1-High**: PR 本文・ラベルで著者が「高リスク」「D1-High」「要注意」と申告した変更（reviewer-prompts.md `## 2.5` の D1-High 検出で拾う。review skill のみ）

**偽陰性の保険**: 正規表現は ORM 抽象の深い経由（動的メソッド・ラッパー越しの書込）を取り逃しうる。reviewer はコード読解で high-risk surface に触れると判断したら `[surface:high-risk]` を申告する（`reviewer-prompts.md ## 1 共通指示` の「high-risk surface フラグ」で全 reviewer に指示。PR 自己申告 `## 2.5` とは独立経路）。オーケストレーターは **正規表現ヒット ∨ reviewer フラグ ∨ PR 自己申告 D1-High で OR 判定**する。surface 偽陰性は recall 補強が丸ごと不発になるため、網羅は正規表現に依存しきらない。

### 起動ゲート（暴走ガード）

- **effort 適応**: **xhigh / max 起点**で起動。low / medium はスキップ。high（既定）は当面スキップし、`review:completed` の頻度計測後に昇格を検討する（既存 5.6/5.8 と対称の fail-safe。今回の見落としは xhigh で発生したため xhigh を直せば当面の再発を防げる）
- **上限**: **PR あたり skeptic 1 体・1 round のみ**（per-surface 起動ではない）。skeptic の指摘も通常の scoring・報告マトリクス・反証レイヤーの対象
- **surface 非該当ならスキップ**: high-risk surface を含まない変更では起動しない（noise 爆発を避け high-risk に限定）
- **計測（skip 時も surface 判定は記録する）**: effort / userConfig / scope でスキップした場合も、正規表現部分の surface 判定（diff への grep で安価）だけは Phase 0 の構成判断（縮退構成・小 diff）と独立に必ず実施し、`review:completed` payload の `recall_skeptic` に記録する（SKILL.md Step 7 / Step 6 の payload 規約参照）。加えて surface=true なら、`--embed` / event 発火の有無に依存しない **human レポート（Step 7 / Step 6 の「動的ラウンド」行）にも skeptic の起動有無（未起動時は skip_reason）を必ず出す**（headless 通常実行での silent skip を防ぐ・issue #85）

### high 昇格の判断基準（計測後）

effort=high での起動昇格は、`review:completed` の `recall_skeptic` 集計で判断する:

```bash
# surface=true なのに effort ゲートで skeptic が走らなかった件数（昇格の需要）
grep '"event":"review:completed"' .claude/events.jsonl | \
  jq -s '[.[] | select(.payload.recall_skeptic.surface == true and .payload.recall_skeptic.skip_reason == "effort")] | length'

# skeptic の価値率（fired のうち findings_added > 0 の割合。昇格の価値）
grep '"event":"review:completed"' .claude/events.jsonl | \
  jq -s '[.[] | select(.payload.recall_skeptic.fired == true)] | if length == 0 then "no data" else ([.[] | select(.payload.recall_skeptic.findings_added > 0)] | length) / length end'
```

目安（厳密な閾値でなく判断材料）: 直近 30 日で `skip_reason="effort"` の surface ヒットが**継続的に発生**し（≒ high 実行でも high-risk 変更を日常的にレビューしている）、かつ xhigh 実績の価値率（findings_added > 0 率）が**明確に非ゼロ**なら、high 昇格のコスト（opus 1 体/PR）に見合うとみなして effort 適応表の high を「起動」に変更する。逆に xhigh でほぼ findings_added=0 が続くなら、skeptic の縮小（Tier2 で足りる判定）を先に検討する。

### model / 作法（反証レイヤーと対称）

| 項目 | 冷や読み skeptic | 反証レイヤー（既存） |
|---|---|---|
| 係 | false-negative を足す | false-positive を潰す |
| findings 注入 | **非注入（独立）** | 主張のみ |
| focus 分割 | 無し（generalist 一頭） | 指摘単位 |
| 契約注入 | 薄め（冷や読み） | 通常 |
| model | **opus**（独立検証は強モデル: ルーティング表） | opus |
| 起動ゲート | high-risk surface（事前所見・severe 非依存） | 非対称ゾーン |

skeptic テンプレートは reviewer-prompts.md `## 8 冷や読み skeptic テンプレート`。findings / reviewer 推論は渡さず、diff と最小 focus のみ渡す。#1（層跨ぎ値フロー）を独立でも捕捉できるよう、敵対的入力逆算の核（受理入力の端点を末端の永続層制約まで前進させる）をテンプレートに内挿し、独立性に「破り方」を持たせる。

### userConfig / 失敗時

- **userConfig**: `enable_recall_skeptic: false` で強制スキップ（既定 true）。計測前の暴走はこの config と effort での明示スキップで即時停止できる
- **失敗時**: skeptic が失敗 / タイムアウトした場合は `missing_coverage` に `recall-skeptic: <failure reason>` を追記して best-effort 続行する。**起動条件（high-risk surface）を満たしたのに未実行だった事実はレポートに必ず出す**（silent 失敗で「守ったつもり」の偽の安心を防ぐ）

## 9. 反証レイヤー（Phase 5.9 / 4.9 / 動的）

reviewer の指摘を独立エージェントが反証し、偽陽性の prominence を下げるフェーズ。**冷や読み skeptic の後・scoring の前**に挿入する（review=Phase 5.9 / self-review=Phase 4.9）。meta-reviewer / skeptic が「見落とし（false negative）」を足す係なのに対し、反証レイヤーは「偽陽性（false positive）を独立に潰す」鏡像の係。skeptic が足した指摘も本レイヤーの反証対象に含める。

### 対象指摘の選定（非対称ゾーン優先 + specialist 除外）

「詰めると取り下がる」のは **不確実だが報告される非対称ゾーン**。そこを狙い撃ちして既定パスのコストを抑える。

| effort | 反証対象（報告マトリクス通過見込みの指摘のうち） | 反証体数 |
|---|---|---|
| low / medium | スキップ | 0 |
| high（既定） | 非対称ゾーンのみ: BLOCKER 60-94 / CRITICAL 80-94 | 指摘ごと 1 体 |
| xhigh / max | 上記 + BLOCKER/CRITICAL 95+ + MAJOR | 指摘ごと 1 体 |

**除外（全 effort 共通）**:

- **specialist 由来（specialist-injection / -secret-handling / -destructive-op / -input-validation / -guardrail-bypass）の指摘は反証対象外**。これらは「断定できなくても BLOCKER + 低 confidence で人間判断を促す」前提（`## 5 Specialist テンプレート` / reviewer-prompts.md）であり、誤反証で人間の警戒度を下げる代償が非対称に大きい
- 95+ の高確証指摘は high では対象外（取り下がりにくい層）

**high-risk surface 例外ゲート（surface-aware 閾値との吸収整合 / F4）**:

surface-aware 報告閾値（scoring-guide.md `## 報告マトリクス`）が high-risk surface に限り CRITICAL 80→70 / MAJOR 95→85 に緩めることで**新規に報告化する CRITICAL 70-79 / MAJOR 85-94 帯**は、上表の high ゲート（BLOCKER 60-94 / CRITICAL 80-94）の対象外に落ちる。これを放置すると「recall で緩めた指摘が反証の二段構えを素通りする」ため、**high-risk surface の指摘に限り high でもこの帯を反証対象に含める**（CRITICAL 70-79 / MAJOR 85-94 を high の非対称ゾーンに追加）。surface 非該当の変更では従来ゲートのまま（noise を増やさない）。緩めた recall を反証レイヤーが independently 吸収する二段構えを high でも成立させる。

### 動作

1. 上表のゲートで対象指摘を選ぶ
2. 対象指摘ごとに反証エージェント（reviewer-prompts.md `## 7 Adversarial-verify テンプレート`）を `model: opus`, `effort: max` で起動。指摘の主張のみ渡し reviewer 推論は渡さない
3. `pre-existing` / `intended` の鮮度は LLM 前に `git show <base>:<file>` / `git blame` で機械判定
4. verdict を scoring（scoring-guide.md `## 反証レイヤーの verdict 反映`）に渡す。**高 severity は消さず注記**、MAJOR/MINOR のみ取り下げ可（理由は付録に記録）
5. 初版は 1 指摘 1 体（パネルは将来拡張）

### effort 適応（5.5/5.6 とは別ゲート）

| effort | 反証レイヤー |
|---|---|
| low / medium | スキップ |
| high (default) | 非対称ゾーンのみ起動 |
| xhigh / max | 報告ゾーン全体 + MAJOR まで起動 |

> adaptive(5.5) は high で起動・meta-reviewer(5.6) は xhigh+ のみ。反証レイヤーは「非対称ゾーンを high から狙う」独自ゲートで、5.6 とは起動条件が異なる。

### userConfig による無効化

- `enable_adversarial_verify: false` → 反証レイヤーを強制スキップ（デフォルト true）。誤却下が多い・コストを抑えたい場合に false
