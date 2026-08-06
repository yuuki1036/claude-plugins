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
| PR コンテキスト（review skill のみ） | SKILL.md Step 1 が `$PR_CTX_FILE` に保存した原本（説明・issue コメント・レビューサマリ・行単位 review comment）。Phase 0 はメインコンテキストが Read した内容を使う | review skill で PR ありの場合 |
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
- **スキップ**: explorer / 冗長ペア / Step 3.3 の起動前検算による構成追加（orchestration-guide `### 8a` のモード除外。検出は missing_coverage 記録のみ）/ Phase 5.5 (adaptive deepening) / Phase 5.6 (meta-reviewer) / Phase 5.7 (カバレッジ事後突合) / Phase 5.8 (冷や読み skeptic) / Phase 5.9 (反証レイヤー)。速度と正しさのトレードオフをスコープ縮小で取る
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
| comment-accuracy | diff にコメント（`//`, `/*`, `#`, `<!--` 等）の追加・変更がある。**self-review ではコメント推敲（B 系統）も同じ 1 体に相乗りさせる**（体数を増やさない。reviewer-prompts.md `### コメント推敲（B 系統）`） |
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
- 文字列マッチは false positive を伴うが、specialist の役割は「人間判断を促す」ことなので積極的に起動して問題ない。**トリガー感度（検出正規表現）は effort に関わらず変更しない**（recall 直撃のため）
- specialist は対応する Focus テンプレート（reviewer-prompts.md `## 5. Specialist テンプレート`）を使用
- specialist の指摘は **大半が BLOCKER または CRITICAL** になるため、低 confidence でも報告マトリクスで人間に届く
- specialist は reviewer 枠とは別カウント（specialist 起動で reviewer 枠を圧迫しない）。**体数は `## 7` の effort 適応表と `## 6.2` の規模キャップの min**（規模側は small 1 体 / medium 2 体）: high 以下では複数 red-flag ヒット時に 1〜2 体へ束ねて該当テンプレートを連結注入する（specialist-guardrail-bypass のみ単独 1 体を維持）。xhigh / max は個別起動・上限 6 体。束ね時の出力規約は reviewer-prompts.md `## 5` 冒頭を参照

### PR コンテキストによる観点追加・冗長化（review skill のみ）

SKILL.md Step 1 が保存した PR コンテキスト（`$PR_CTX_FILE`）の内容も判定シグナルとして使う:

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

- **上限**: `## 7` の effort 適応表と `## 6.2` の規模キャップの **min**（effort 側は high 4 体 / xhigh・max 6 体、規模側は small 0 体 / medium 2 体）

### reviewer の冗長度判定

同一観点を複数体（x2）にする条件:

- 対象コードの分岐の深さが3以上（ネストした if-else）
- 変更関数が500行超
- 状態変異が3箇所以上（同一変数への代入が散在）
- 複数モジュール間のデータフローに影響
- explorer が「複雑」と報告した領域

**冗長ペア（x2）の実起動は xhigh / max 専用**（`## 7`）。high 以下では上記条件を満たしても 1 体で起動し、Angle A / B を両方その 1 体のプロンプトに内挿する（reviewer-prompts.md `## 4`）。条件判定自体は全 effort で行う（angle 内挿の要否を決めるため）。

### 冗長ペアの angle（分析の切り口）

**bug-detection の場合:**
- A = 「データフローの正しさ（変数の定義→変更→参照、意図しない上書き・未初期化）」
- B = 「制御フローの正しさ（分岐の全パス検証、到達不能コード、else 副作用）」

**security の場合:**
- A = 「入力バリデーション・インジェクション」
- B = 「認証・認可・アクセス制御」

他の観点も必要に応じて angle を設定する。

- **reviewer 上限**: `## 7` の effort 適応表と `## 6.2` の規模キャップの **min**（effort 側は high 6 体 / xhigh・max 10 体、規模側は small 3 体 / medium 5 体。最小保証の 2 体は規模キャップより優先）

## 5. 出力フォーマット

Phase 0 の出力はエージェント構成テーブルとして表示する。

```
## Phase 0 トリアージ結果

### 変更特性
- 規模: {small|medium|large}（core {N} ファイル / {N} 行、全体 {N} ファイル / {N} 行）
- 実効上限: explorer {N} / reviewer {N} / specialist {N}（effort {値} 上限 {N}/{N}/{N} と規模キャップ {N}/{N}/{N} の min。`## 6.2`）
- 直列 wave: {下限}〜{上限}（{explorer → }reviewer+skeptic{ → [Round 2 ×{1|2}]}{ → [meta]}{ → [反証]}）／wave あたり目安 6〜16 min
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

### 5.1 直列 wave 数の見積もり（GitHub issue #100 B）

**体数はトークンコストのレバー、wave 数は壁時計のレバー**（`## 7`「体数を壁時計のレバーとして扱わない」の対）。並列発行が効いている限り 1 wave の実時間は「wave 内最長の 1 体」で決まるので、壁時計は体数ではなく**直列に積み上がる wave の本数**で決まる。ところが現状ユーザーに見えるのは体数だけで、wave 数は最後まで見えない。Phase 0 の出力に 1 行足して同じ切り分けをユーザーにも見せる。

| wave | 条件 | 本数 |
|---|---|:---:|
| explorer | explorer を 1 体以上配置した場合 | 0 / 1 |
| reviewer（+ 冷や読み skeptic の相乗り・`## 8.5`） | 常時 | 1 |
| Round 2（`## 8` Phase 5.5） | effort ≥ high かつ unmet_information あり | 0 / 1（high・規模キャップ帯）/ 2（xhigh・max の 2 段） |
| meta-reviewer（Phase 5.6） | effort が xhigh / max かつ BLOCKER/CRITICAL あり | 0 / 1 |
| 反証（`## 9` Phase 5.9） | effort ≥ high かつ対象指摘あり | 0 / 1 |

- **下限 = Phase 0 で確定している wave**（explorer の有無 + reviewer の 1 本）。**上限 = 上表の各行の最大値の総和**（例に依存せずこの算式で出す）
- 例（effort=xhigh / medium 帯 / explorer 2 体配置）: 下限 = 1（explorer）+ 1（reviewer）= 2、上限 = 2 + 2（Round 2）+ 1（meta）+ 1（反証）= 6 なので `直列 wave: 2〜6（explorer → reviewer+skeptic → [Round 2 ×2] → [meta] → [反証]）`
- **括弧内の列挙と上限の数を必ず突き合わせる**（`[Round 2 ×2]` は 2 本と数える）。ここがズレると wave 可視化の唯一の出力が誤った目安を提示する
- 実測が上限に張り付くようなら、削る候補は wave であって体数ではない（`## 8` の 1 段圧縮経路・`## 8.5` の相乗り・`## 8` Phase 5.5 のスキップ条件）

## 6. 規模判定と規模キャップ（体数上限の第 2 系統）

体数の実効上限は **effort 上限（`## 7`）と規模キャップ（本節）の min** で決まる。

effort だけで上限を決めると、小さな PR にも effort 上限いっぱいの体数が張り付く。実測（GitHub issue #96）: 9 ファイル / `+116 -22`（うち本番コードは 3 ファイル `+22 -13`、残りはテスト 5 + doc 1）の PR を xhigh で流したところ explorer 4 + reviewer 10 + specialist 1 + Round 2 explorer 2 = **17 体**が起動し、レポートまで 95 分・締めまで 130 分かかった。旧 `## 6` は「Phase 0 が明確な判断を下せない場合」限定のフォールバックだったため、diff シグナルが読めてしまうと規模が上限に一切効かなかった。

切り分けの原則: **effort は「1 体あたりどれだけ深く読むか」の指定であって、「何体並べるか」の指定ではない。** 規模キャップはこの切り分けを機械化する。

### 6.1 実質規模の数え方

`gh pr diff <PR番号> --name-only`（self-review は `git diff --name-only`）と行数から数える。**帯の判定は core 側で行う**:

- **除外**（どちらの系統にも数えない）: lock ファイル（`*.lock` / `package-lock.json` / `yarn.lock` / `pnpm-lock.yaml`）、生成物（`dist/` / `build/` / `*.snap` / `*.generated.*`）、vendor 配下
- **core**（帯の判定に使う）: 上記除外後から、さらにテスト（`*.test.*` / `*.spec.*` / `__tests__/` / `tests/`）とドキュメント（`*.md` / `docs/`）を除いた本番コード
- テスト・ドキュメントは観点判定（test-quality / doc-substance 等）の**起動根拠にはなる**が、**体数を押し上げる根拠にはしない**（1 観点 1 体で足り、fleet を要さないため）

core が 0（テスト・doc のみの PR）の場合は `## 2.5` のモード判定（doc-review-mode 等）に従い、本節の帯は **small** を使う。

### 6.2 規模キャップ

| 帯 | 条件（core 基準） | explorer | reviewer | specialist |
|---|---|:---:|:---:|:---:|
| small | ファイル ≤ 3 **かつ** 行数 ≤ 100 | 0 | 3 | 1 |
| medium | ファイル 4-10 **または** 行数 101-500 | 2 | 5 | 2 |
| large | ファイル > 10 **または** 行数 > 500 | キャップなし | キャップなし | キャップなし |

- **判定は large → medium → small の順**に上から当て、最初に条件を満たした帯を採る（条件が重なる場合は大きい帯が勝つ。例: 2 ファイル / 600 行は行数で large）
- **large 帯は規模キャップを課さない**（effort 上限がそのまま実効上限になる）
- **最小保証（reviewer-bugs + reviewer-claude-md の 2 体）は規模キャップより優先**する。small でもこの 2 体は必ず起動する
- キャップに収まらない観点は、effort 上限超過と同じ扱いで `missing_coverage` に「観点未起動: <focus>（規模キャップ: <帯>）」として**必ず記録**する（脱落を silent にしない）。近接観点のバンドル（`## 7`）による吸収を先に試みる
- 判定した帯と core の実数は Phase 0 の出力（`## 5`）とレポート冒頭・`review:completed` payload の `size_tier` に必ず出す（キャップが効いたことを事後に検証できるようにする）

### 6.3 規模キャップが削るもの・削らないもの

規模キャップが削るのは **breadth（並べる体数）だけ**。depth を担う層は帯に関わらず effort の指定どおり動かす。

- **削る**: explorer / reviewer / specialist の体数、冗長ペア、Round 2 の追加 explorer（**規模キャップが effort 上限を下回った帯では、Round 2 は effort に関わらず `## 8` の 1 段圧縮経路を使う**）
- **削らない**: reviewer 個々の effort（`## 7` の連動表どおり。xhigh 指定なら reviewer は `xhigh` のまま）、meta-reviewer（5.6）、冷や読み skeptic（5.8）、反証レイヤー（5.9）。いずれも 1〜数体で、小さな diff ほど 1 体あたりの費用対効果が高い

xhigh / max を明示指定したユーザーが求めているのは「小さな diff を深く読むこと」であって「小さな diff に 17 体並べること」ではない。

### 6.4 Phase 0 が判断できない場合のフォールバック構成

diff シグナルが読めず観点を決められない場合の既定構成（キャップではなく初期値。旧 `## 6` の内容）:

| 帯 | フォールバック構成 |
|---|---|
| small | reviewer 2（bug-detection, claude-md-compliance） |
| medium | explorer 1（history-context）+ reviewer 3（bug-detection, claude-md-compliance, error-handling） |
| large | explorer 2（history-context, dependency-trace）+ reviewer 4（bug-detection, claude-md-compliance, error-handling, cross-cutting） |

## 7. 最小保証とフェーズ上限（effort 適応 / effort 側上限の正本。実効上限は `## 6.2` との min）

- **最小保証**: reviewer-bugs（focus: bug-detection）+ reviewer-claude-md（focus: claude-md-compliance）の2体は Phase 0 の判断・規模キャップに関わらず常に起動
- **実効上限 = min(effort 上限（本表）, 規模キャップ（`## 6.2`))**。effort 上限は「深さの予算」、規模キャップは「広さの上限」で、両者は独立に効く。どちらか小さい方を採る（GitHub issue #96。effort 上限だけを見ると小 PR に上限いっぱいの体数が張り付く）
- effort 上限は実行時 effort = `${CLAUDE_EFFORT}` で決まる。**本表が effort 側上限の正本**（SKILL.md・他節の上限言及はここを参照する）:

| 枠 | low / medium | high（既定） | xhigh / max |
|---|:---:|:---:|:---:|
| explorer | 2 | 4 | 6 |
| reviewer | 4 | 6 | 10 |
| specialist | 3（束ね起動） | 3（束ね起動） | 6（個別起動） |
| 冗長ペア（x2） | なし | なし（angle 両内挿） | 積極投入 |

- **冗長ペアは xhigh / max 専用**。high 以下ではペア条件（`## 4` の冗長度判定）成立時も 1 体とし、Angle A / B を両方その 1 体のプロンプトに内挿する（reviewer-prompts.md `## 4`）
  - **補償の実態を正確に**: 反証レイヤーの `confirmed` は「複数エージェント検出 +15」と同じ発火源だが（scoring-guide.md）、反証対象は**報告マトリクス通過見込みの指摘に限られる**（`## 9`）。つまり **閾値直下の指摘（通常 surface の CRITICAL 70 台・MAJOR 80-94）をペアの +15 が報告側へ押し上げていた効果は補償されない**。この帯の recall 低下は縮小のコストとして許容し、severity 別件数（下記ロールバック条件）で監視する
  - **angle 内挿時の scoring**: 1 体内で両 angle が同一問題に到達しても「ペア合意 +10」は付けず、「片方のみ検出 -5」も適用しない（独立性が担保されないため。scoring-guide.md の両項は冗長ペア実起動時＝xhigh/max のみ発火する）
- **観点バンドル（high 以下）**: 起動条件を満たした観点数が reviewer 上限を超える場合、近接観点を 1 体に束ねて**可能な限り**吸収する（例: error-handling + comment-accuracy + type-design / config + dependency）。1 体あたり 3 観点まで。**bug-detection / security / spec-compliance / claude-md-compliance は束ねず単独を維持**する（指摘密度が高く attention 希釈の代償が大きい観点）。束ね時の出力規約（focus キーは原観点・観点ごとに独立列挙・自己フィルタ禁止）は reviewer-prompts.md `## 3` 冒頭を参照
  - **`comment-accuracy` が束ねられた場合も、self-review のコメント推敲（B 系統）の `## コメント推敲提案` ブロックは省略しない**（v2.45.0）。束ねは attention の配分の話であって出力契約の削減ではない。該当なしなら「該当なし」と明記する（Step 6 の見出しが silent に消えると、推敲ゼロが「提案が無かった」のか「観点が薄まって見なかった」のか区別できなくなる）。**バンドル相乗りでも `comment_polish.fired` は `true`** — 専任 reviewer の有無で切ると high 既定で常に false になる（orchestration-guide `## 16`）
  - **容量と超過時の扱い**: 吸収容量は「単独 4 観点 +（reviewer 上限 − 4）× 3」＝ high で最大 10 観点。観点判定表は 17 観点あるため、フルスタックな大型 PR では超過しうる。**超過分は `missing_coverage` に「観点未起動: <focus>（reviewer 上限超過）」として必ず記録**し、レポートの欠損観点セクションに明示する（脱落を silent にしない）。超過が常態化する PR は xhigh への明示 escalation を促す
- **specialist の束ね起動（high 以下）**: 複数 red-flag 同時ヒット時、specialist-guardrail-bypass のみ単独 1 体を維持し、残りを 1〜2 体に束ねて該当テンプレートを連結注入する（`## 3` Red-flag 節）。トリガー感度は変更しない
- **縮小のロールバック条件（v2.39.0 の high 既定縮小）**: 効果は `review:completed` の `agents` / `duration_min` / blocker+critical 件数で監視する。**判定に使えるのは `agents` フィールドを持つサンプルのみ**（= v2.39.0 以降の publish。フィールド存在が publish 側の自己申告版マーカーであり、配布ラグに耐える。旧サンプルは `effort` を持たず high 実行と xhigh 実行を層別できないため、「縮小前との比較」の基準側には使えない — `## 8.5` の「日付では切らない」と同じ流儀）。悪化の検証は旧データ比ではなく、**xhigh/max の明示実行（フル構成）を対照群にした縮小後サンプル内の比較**で行う:

  ```bash
  # effort=high（縮小構成）のレビュー 1 件あたり blocker+critical 平均と fleet 区間の中央値
  # 所要時間は duration_fleet_min で見る（duration_min は締めフローの人間待ちを含む）
  grep '"event":"review:completed"' .claude/events.jsonl | \
    jq -s '[.[] | select(.payload.agents != null and .payload.effort == "high")] |
      if length == 0 then "no data" else
        {n: length,
         hi_avg: (([.[] | .payload.blocker_count + .payload.critical_count] | add) / length),
         fleet_med: ([.[] | .payload.duration_fleet_min // -1 | select(. >= 0)] | sort | .[(length/2|floor)] // "no data")}
      end'
  # 対照群は .payload.effort == "xhigh" or "max" に置き換えて同じ式で出す
  # 帯を揃えるときは select(...) に and .payload.size_tier == "small" 等を足す
  ```

  縮小後 30 日で high 群の hi_avg が対照群比で明確に低い状態が続いたら、まず冗長ペアの high 復帰（次に reviewer 上限 10 復帰）を検討する。サンプルが `no data` のうちは判断しない。印象や単発の見落とし報告だけで戻さない（壊れた・不足した計測を根拠に不可逆な判断をしない。skeptic の high 昇格判断 `## 8.5` と同じ流儀）

  **所要時間は `duration_fleet_min` で見る**（v2.41.0 で payload に追加。正本: orchestration-guide `## 14`）。`duration_min`（全体）は締めフローの人間待ちを含み（かつ publisher 間で意味が非対称）、人間の都合で 10 倍振れるため体数調整の効果測定には使えない。体数が効くのは fleet 区間だけ。**比較は `size_tier` を揃えて行う**（v2.40.0 追加）— 所要時間は規模と体数の両方に効かれるため、帯を混ぜた中央値は規模キャップの効果と PR 規模の分布変化を分離できない。

  **体数を壁時計のレバーとして扱わない（v2.41.0）**: 並列発行が効いている限り fleet 区間の実時間は「wave 内最長の 1 体」で決まるため、**体数削減の効果は線形ではない**。そして**体数削減が壁時計に効いた証拠は現時点で存在しない** — v2.39.0 / v2.40.0 の縮小を評価できる区間別サンプルが無く、唯一あった 210 分のサンプルも `duration_min`（内訳不明）だったため判定不能だった。`duration_fleet_min` が貯まるまでは、**体数を壁時計の打ち手として動かさない**（体数削減が確実に効くのはトークンコスト）。壁時計を縮めたい場合にまず触るのは ①1 体あたりの探索量（reviewer-prompts.md `## 1` の探索予算）②直列 wave 数（`## 5.1` で可視化・skeptic 相乗り `## 8.5`・Round 2 の repo 外スキップ `## 8`。実測は `duration_explore_min` が wave 単価を示す）③メインコンテキストのプロンプト複製量（PR コンテキスト等のファイル経由渡し・orchestration-guide `## 3.5`）。**③は `duration_triage_min` では観測できない** — プロンプトを書く行為と Agent call の発行が同一なのでマーカーで分離できず、コストは `duration_fleet_min` に含まれる（orchestration-guide `## 14`）。③の効果は `duration_fleet_min` を `size_tier` × `agents.reviewer` × `effort` で層別して見る。recall だけ落ちて時間が変わらない改悪を避けるため、**この節のロールバック判断に「時間が長いから体数を減らす」を混ぜない**。

  **`review` 由来サンプルは v2.40.0 より前は 1 件も存在しない**（GitHub issue #96 B）。publish が EnterWorktree 配下の cwd 相対パスで行われていたため、`review:completed` は worktree 側の `.claude/events.jsonl` に書かれ、直後の `ExitWorktree(remove)` で worktree ごと消えていた。v2.40.0 で publish 先をメインリポジトリのルートに固定（orchestration-guide `## 13`）するまで、蓄積されていたのは worktree を使わない self-review 由来のみ。**したがって v2.39.0 の high 既定縮小は review 経路については測定できていない** — 判断は v2.40.0 以降のサンプルが貯まってから行う

### 未解決の観測: review 経路の MAJOR がゼロに張り付いている（2026-08-06 / 判定は v2.44.0 サンプル待ち）

蓄積済み 43 件（`review` 12 / `self-review` 31）を集計したところ、**publisher 間で MAJOR の分布が極端に非対称**だった:

| publisher | n | `major_count`=0 の回 | b / c / major / minor 合計 | `severity_inflated`（1 回あたり） |
|---|--:|--:|---|--:|
| `code-review:review` | 12 | **12 / 12** | 0 / 1 / **0** / 27 | 9 件（**0.82**） |
| `code-review:self-review` | 31 | 10 / 31 | 2 / 7 / **78** / 59 | 7 件（0.30） |

- **「PR が綺麗だった」では説明できない**: MAJOR と MINOR は報告マトリクス上どちらも confidence 95+ の同一閾値なのに、review では MINOR が 27 件通って MAJOR が 0 件
- **緩和側がゼロ**: review は `recall_skeptic.surface` が 10/10 で true（= 全件 high-risk surface 判定）。surface-aware 閾値により **MAJOR は 85+ に緩和されている状態で 0 件**。緩和していない self-review が 78 件
- 両 SKILL の scoring 手順（review Step 6 / self-review Step 5）は severity 処理の規約が**同一**であることを確認済み。仕様差では説明がつかない

**考えられる経路**（いずれも出口が MINOR なので `minor_count` に合流する）: ① `severity-inflated` 降格 ② `[scope:out]` 降格（他人の PR は「既存の問題」判定が出やすい）③ confidence 95 未満での skip ④ そもそも reviewer が MAJOR を出していない。

**判定手順**: v2.44.0 で追加した `pre_adjust_counts` が貯まったら orchestration-guide `## 16` の jq を回す。`pre_adjust_counts.major` が **0 に近ければ ④（検出由来）**、**post との差が大きければ ①〜③（調整由来）**。

**それまで scoring 規約を変えない。** 特に「MAJOR/MINOR の `severity-inflated` を無条件降格から保護する」（scoring-guide の不変条件を MAJOR へ拡張する）は precision を直接下げる不可逆な変更であり、**降格由来だと確認できていない段階で入れてはならない**。壊れた・不足した計測を根拠に不可逆な判断をしない（`## 8.5` と同じ流儀）。

## 8. 動的ラウンド（Phase 5.5 / 5.6 / v2.12.0 追加）

### Phase 5.5: Adaptive deepening (Round 2 / unmet_information 起点)

**起動条件**: 全 reviewer 完了後、reviewer の出力に `unmet_information` フィールドが 1 件以上あり、**かつ target の少なくとも 1 件が repo 内で到達可能**な場合に起動

**目的**: reviewer が「この観点を確定するには追加の context が必要」と自覚した領域を 1 round だけ深掘りする適応的再評価

**repo 外 target による全件スキップ（GitHub issue #100 C）**: unmet の target が**全件 repo 外情報**なら、追加探索は構造的に空振りするため wave を 1 本まるごと省く。target の分類は文字列を読めば決まるのでメインコンテキストで判定でき、agent を要さない。

- **repo 外**（到達不能）: DB / 本番環境の実データ、外部サービスの実挙動（デザインツール・実機描画・ブラウザ実測）、このリポジトリに存在しないコード（他リポジトリ・削除済みの旧実装）、意図的にスキップした実行結果（lint / テスト / ビルドの実走）
- **repo 内**（到達可能）: ソース・型定義・設定・マイグレーション・doc・コミット履歴など、Read / Grep / Glob / git で届くもの
- **1 件でも repo 内があれば通常どおり起動する。無条件スキップは有害** — 実測では unmet 8 件中 7 件が到達不能だったが、残り 1 件（DB 制約）を Round 2 が repo 内 doc で解決した結果、指摘 1 件の severity が MAJOR → MINOR に変わった。判定に迷う target は repo 内側に倒す
- スキップした場合は `missing_coverage` に「Round 2 スキップ: unmet 全件が repo 外（<target 要旨>）」として記録し、レポートの「動的ラウンド」行にも理由を出す（silent に落とさない）

**動作（effort で経路が分かれる。実行手順の正本は orchestration-guide `## 6`）**:
- **high（既定）— 1 段圧縮**: 追加 explorer は起動しない。unmet を申告した reviewer のみ再起動し、**unmet ターゲットを自力探索（Read / Grep / Glob）してから初回 confidence を再評価**させる。直列 wave を 2 → 1 に減らし、sonnet 経由の要約受け渡しも省く（的の絞れた追加探索は opus 自身が掘る方が受け渡しロスがない）
- **xhigh / max — 2 段**: `re-explore` フォーカス（explorer-prompts.md 参照）の追加 explorer → 該当 reviewer 再起動。探索を広めに撒く価値がある明示 escalation 時のみ 2 段を使う
- いずれの経路も他の reviewer は再実行しない（コスト抑制）。結果は初回 reviewer 結果と統合（重複指摘は dedup）

**上限**: 1 round のみ（多段化禁止）。再起動 reviewer 上限 3 体（xhigh/max の追加 explorer も上限 3 体）

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
| high (default) | unmet_information があれば起動（1 段圧縮） | スキップ |
| xhigh | 起動（2 段） | 起動 |
| max | 起動（2 段） | 起動 |

### userConfig による無効化

- `enable_adaptive_rounds: false` → Phase 5.5 を強制スキップ
- `enable_meta_reviewer: false` → Phase 5.6 を強制スキップ

両方デフォルト true。トークンコスト・レイテンシが気になる場合は false にする。

## 8.5. 冷や読み skeptic ラウンド（Phase 5.8 / 4.8 / recall 補強）

high-risk surface を含む変更に限り、事前所見と無関係に **findings 非注入の独立 skeptic を 1 体**起動し、fleet 共通の盲点（層跨ぎ値フロー等）を冷や読みで破る recall 補強フェーズ。反証レイヤー（false-positive 潰し）の鏡像＝ false-negative hunter。meta-reviewer（Phase 5.6）が findings 注入で非独立なため fleet 共通盲点を引きずるのに対し、skeptic は独立読み直しで盲点を破る。

### 起動タイミング: reviewer wave に相乗り（v2.41.0）

**skeptic は reviewer と同一メッセージで一括発行する**（review Step 5 / self-review Step 4 の reviewer 一括発行に相乗り）。結果の統合・dedup だけを従来位置（review=Phase 5.8 / self-review=Phase 4.8）で行う。

根拠: **findings 非注入がこのレイヤーの設計の核**であり、skeptic は reviewer の出力に一切依存しない。にもかかわらず reviewer の後に直列配置されていたため、依存関係が無いのに 1 wave 分の実時間（opus 1 体の全所要）を積み増していた。同時発火なら壁時計への追加はゼロ（wave 内最長が伸びない限り）。

**例外（fallback / 従来どおり直列）**: surface 判定が **reviewer の `[surface:high-risk]` フラグ由来**で事後に true になった場合のみ、reviewer 完了後の 5.8 位置で単独起動する。この経路だけは reviewer 出力に依存するため同時発火できない（正規表現・PR 自己申告で事前に HIT していれば相乗り済みなので、fallback が走るのは正規表現が取り逃した ORM 抽象越えのケースに限られる）。

### high-risk surface 判定

以下のいずれかを含む変更を high-risk surface とみなす（事前所見・severity と無関係に判定）:

1. **DB 書込**: `INSERT` / `UPDATE` / `DELETE` を含む生 SQL、または ORM の書込 API（`.create(` / `.update(` / `.save(` / `.insert(` / `.upsert(` 等）。performance 観点の起動条件（`## 3` の `INSERT|UPDATE` 正規表現）を surface 判定に転用する
2. **金銭・数量計算**: `amount` / `price` / `balance` / `quantity` / `stock` / 通貨・丸め・課金に関わる numeric 演算
3. **認可・認証**: 権限チェック / セッション / トークン / ロール判定に関わる変更
4. **PR 自己申告 D1-High**: PR 本文・ラベルで著者が「高リスク」「D1-High」「要注意」と申告した変更（reviewer-prompts.md `## 2.5` の D1-High 検出で拾う。review skill のみ）

**偽陰性の保険**: 正規表現は ORM 抽象の深い経由（動的メソッド・ラッパー越しの書込）を取り逃しうる。reviewer はコード読解で high-risk surface に触れると判断したら `[surface:high-risk]` を申告する（`reviewer-prompts.md ## 1 共通指示` の「high-risk surface フラグ」で全 reviewer に指示。PR 自己申告 `## 2.5` とは独立経路）。オーケストレーターは **正規表現ヒット ∨ reviewer フラグ ∨ PR 自己申告 D1-High で OR 判定**する。surface 偽陰性は recall 補強が丸ごと不発になるため、網羅は正規表現に依存しきらない。

### 起動ゲート（暴走ガード）

- **effort 適応**: **xhigh / max 起点**で起動。low / medium はスキップ。high（既定）は当面スキップし、`review:completed` の頻度計測後に昇格を検討する（既存 5.6/5.9 と対称の fail-safe。今回の見落としは xhigh で発生したため xhigh を直せば当面の再発を防げる）
  - **surface 判定は Phase 0 で先に行う**（相乗り発火の可否を reviewer 起動前に決めるため）。正規表現 + PR 自己申告 D1-High は Phase 0 で判定でき、effort ゲートを通過していれば reviewer 一括発行に skeptic を混ぜる
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
# attribution_schema >= 2 で絞るのは必須（schema 1 相当＝マーカー無しは帰属が壊れており findings_added が信用できない。後述の注記）
# 分子は findings_added（skeptic 単独由来）のみ。findings_overlap（reviewer と重複＝盲点でなかった事例）は算入しない
grep '"event":"review:completed"' .claude/events.jsonl | \
  jq -s '[.[] | select(.payload.recall_skeptic.fired == true and (.payload.recall_skeptic.attribution_schema // 1) >= 2)] | if length == 0 then "no data" else ([.[] | select(.payload.recall_skeptic.findings_added > 0)] | length) / length end'
```

目安（厳密な閾値でなく判断材料）: 直近 30 日で `skip_reason="effort"` の surface ヒットが**継続的に発生**し（≒ high 実行でも high-risk 変更を日常的にレビューしている）、かつ xhigh 実績の価値率（findings_added > 0 率）が**明確に非ゼロ**なら、high 昇格のコスト（opus 1 体/PR）に見合うとみなして effort 適応表の high を「起動」に変更する。逆に xhigh でほぼ findings_added=0 が続くなら、skeptic の縮小（Tier2 で足りる判定）を先に検討する。

**⚠️ `attribution_schema` が無い（＝ schema 1 相当）サンプルの `findings_added` は判断に使えない**: code-review 2.35.1 より前は由来タグ `[recall-skeptic]` がレポート書式に規定されておらず、dedup 時のタグ生存も未規定だったため、publish（Phase 5.8 から 200 行以上離れ、間に精査・解説・ドラフト生成を挟む）時点で由来を再構成できず、`findings_added` が記憶依存で系統的に 0 へ潰れていた。実際に `fired=true` 4 件すべてが `findings_added=0` だが、これは「価値ゼロ」と「帰属の喪失」を**区別できない** `[unverified: gist 集約 69 件。project-local events.jsonl は gitignored のため repo からは検証不能]`。

**縮小・撤去の判断は `attribution_schema >= 2` のサンプルのみで行う**（上の jq がこのフィルタを内蔵している）。**日付では切らないこと** — マーケットプレイス配布のため、未更新マシンは修正日以降も schema 1 の payload を publish し続ける（`plugin-manager` による一括更新が前提＝ラグは常態）。`ts` で切っても汚染が混入する。publish 側が自己申告する版マーカーだけが配布ラグに耐える。壊れた計測を根拠に不可逆な撤去をしない。

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
| high（既定） | 非対称ゾーンのみ: BLOCKER 60-94 / CRITICAL 80-94 | `ceil(対象件数 / 5)` 体・上限 3 体 |
| xhigh / max | 上記 + BLOCKER/CRITICAL 95+ + MAJOR | 同上 |

**バッチ化（v2.41.0）**: 反証は **1 体あたり最大 5 件**をまとめて渡す（旧: 指摘ごと 1 体）。反証に必要な独立性は「指摘を出した reviewer と別コンテキスト」であって「指摘同士が別コンテキスト」ではないため、同一 diff の読み直しを N 体で重複させる意味がない。反証は**かつて指摘数に比例する唯一の変動費**（`## 7` の体数表で reviewer / specialist は上限が効くのに対し、旧構成の反証だけは指摘が増えるほど体数が増えた）であり、既定パスのコストの主要項だった。**本節のバッチ化で上限 3 体・15 件に頭打ちになり、他層と同じく上限で止まる**。バッチ内の相互汚染（1 件の verdict を別件の根拠にする）は reviewer-prompts.md `## 7` の鉄則で禁止する。

**対象が 15 件（3 体 × 5 件）を超えた場合**: severity → confidence の順で優先度を付け、上位 15 件のみ反証する。溢れた指摘は verdict なし（＝反証スキップ）として元の confidence / severity のまま続行し、**レポートの反証行に予算超過件数を明記する**（silent に落とさない）。レポート行の書式の正本は orchestration-guide `## 10` 手順 4。

**縮小のロールバック条件（v2.41.0 のバッチ化 + effort 引き下げ）**: 2 つの縮小を同時適用しているため、誤却下が増えていないかを `review:completed` の `adversarial_verify` で監視する。`duration_triage_min` フィールドの有無で v2.41.0 前後を層別し（日付では切らない）、**`uncertain` 比率**（＝根拠を出せず判定できなかった割合）と **MAJOR/MINOR の `refuted` 比率**を比較する。uncertain が明確に増えていれば effort を `max` に戻す、refuted が明確に増えていればバッチサイズを 5 → 3 に下げるか個別起動に戻す。サンプルが貯まるまでは判断しない（`## 7` のロールバック条件と同じ流儀）。

**除外（全 effort 共通）**:

- **specialist 由来（specialist-injection / -secret-handling / -destructive-op / -input-validation / -guardrail-bypass）の指摘は反証対象外**。これらは「断定できなくても BLOCKER + 低 confidence で人間判断を促す」前提（`## 5 Specialist テンプレート` / reviewer-prompts.md）であり、誤反証で人間の警戒度を下げる代償が非対称に大きい
- 95+ の高確証指摘は high では対象外（取り下がりにくい層）

**high-risk surface 例外ゲート（surface-aware 閾値との吸収整合 / F4）**:

surface-aware 報告閾値（scoring-guide.md `## 報告マトリクス`）が high-risk surface に限り CRITICAL 80→70 / MAJOR 95→85 に緩めることで**新規に報告化する CRITICAL 70-79 / MAJOR 85-94 帯**は、上表の high ゲート（BLOCKER 60-94 / CRITICAL 80-94）の対象外に落ちる。これを放置すると「recall で緩めた指摘が反証の二段構えを素通りする」ため、**high-risk surface の指摘に限り high でもこの帯を反証対象に含める**（CRITICAL 70-79 / MAJOR 85-94 を high の非対称ゾーンに追加）。surface 非該当の変更では従来ゲートのまま（noise を増やさない）。緩めた recall を反証レイヤーが independently 吸収する二段構えを high でも成立させる。

### 動作

1. 上表のゲートで対象指摘を選ぶ
2. 対象指摘を 5 件ずつのバッチに分け、バッチごとに反証エージェント（reviewer-prompts.md `## 7 Adversarial-verify テンプレート`）を `model: opus`, `effort: high` で起動。指摘の主張のみ渡し reviewer 推論は渡さない
   - **effort は v2.41.0 で `max` → `high`**。effort 方針の正本は orchestration-guide `## 5`（「下げるのは『全レビューで走る』または『指摘数に比例する』レイヤー、据え置くのは 1 体固定の検証レイヤー」）。反証は誤判定コストの非対称性を **verdict の扱い側**（高 severity は `refuted` でも `severity-inflated` でも消さず係争注記 = scoring-guide の不変条件）で吸収しているため、effort での二重の保険は要らない
3. `pre-existing` / `intended` の鮮度は LLM 前に `git show <base>:<file>` / `git blame` で機械判定
4. verdict を scoring（scoring-guide.md `## 反証レイヤーの verdict 反映`）に渡す。**高 severity は消さず注記**、MAJOR/MINOR のみ取り下げ可（理由は付録に記録）
5. 1 体が複数 verdict を返す（バッチ）。**全 finding_id 分の verdict が揃っているか突合し、欠落は verdict なし扱い**にする（欠落を confirmed とも refuted とも解釈しない）

### effort 適応（5.5/5.6 とは別ゲート）

| effort | 反証レイヤー |
|---|---|
| low / medium | スキップ |
| high (default) | 非対称ゾーンのみ起動 |
| xhigh / max | 報告ゾーン全体 + MAJOR まで起動 |

> adaptive(5.5) は high で起動・meta-reviewer(5.6) は xhigh+ のみ。反証レイヤーは「非対称ゾーンを high から狙う」独自ゲートで、5.6 とは起動条件が異なる。

**xhigh / max ゲートと非対称ゾーン論の緊張（据え置きの明示 / GitHub issue #100 補足）**: 本節冒頭は反証対象の設計思想を「詰めると取り下がるのは**不確実だが報告される非対称ゾーン**」と述べているが、xhigh / max のゲートは「報告ゾーン全体 + MAJOR」なので **confidence 95+ の MAJOR / BLOCKER / CRITICAL が全件対象**になる。これは**最も取り下がりにくい層に、直列 wave 1 本（`## 5.1` の目安で 6〜16 min）を使う**ことを意味し、非対称ゾーン論からはみ出す。実測例: 52 分のレビューで最終的に残った反証対象が MAJOR 3 件（conf 95 / 99 / 100）だけという構成になった。

それでも据え置くのは、xhigh / max が**明示 escalation**（「小さな diff を深く読む」の意思表示）であり、この帯で偽陽性を 1 件通すコストが wave 1 本より大きいと判断しているため。ただし**この緊張とコストは記録しておく** — 壁時計を縮める必要が出たとき、xhigh の反証ゲートを「非対称ゾーン + BLOCKER/CRITICAL 95+」に狭める（MAJOR 95+ を外す）のが最初の候補になる。判断は `adversarial_verify` の `refuted` 内訳（95+ MAJOR の取り下げ実績）が貯まってから行う。

### userConfig による無効化

- `enable_adversarial_verify: false` → 反証レイヤーを強制スキップ（デフォルト true）。誤却下が多い・コストを抑えたい場合に false
