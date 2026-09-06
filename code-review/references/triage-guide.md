# Phase 0 トリアージガイド

Phase 0 はレビュー実行前にメインコンテキストで diff を分析し、エージェント構成を動的に決定するフェーズ。

**本ファイルは Phase 0（Stage 0〜2 のエージェント構成決定）で必要な範囲だけを持つ。** 動的ラウンド（Round 2 / meta-reviewer / 冷や読み skeptic / 反証レイヤー）の起動ゲートは `triage-dynamic-gates.md` に切り出してあり、**そのフェーズの起動可否を判断する段になってから Read する**。実行手順は `orchestration-dynamic-rounds.md`、設計判断の履歴は `design-notes/`。節番号は分割前のものを維持している。

## 1. Phase 0 概要

- メインコンテキストで実行する（Agent ツールは使わない）
- 2段階判定: Stage 1（タイプ判定）→ Stage 2（体数・フォーカス・冗長度決定）
- 出力はエージェント構成テーブル

## 2. 入力情報

Phase 0 実行前に以下の情報を収集する:

| 情報 | 取得方法 | 必須 |
|---|---|---|
| **シグナルダイジェスト** | `scripts/triage-signals.sh --pr <N>` / `--base <ref>`。規模・ファイル分類・hunk ヘッダ・観点判定シグナル・red-flag・surface・explorer シグナル・AGENTS.md・Issue ID を 1 回の Bash で取得 | Yes |
| diff 全文 | **メインコンテキストでは読まない**。ダイジェストの `## meta` の `diff_file=` に保存済みで、agent へはパスで渡す。Phase 0 で個別に必要になったときだけ `scripts/diff-slice.sh "$DIFF_FILE" <path>` で該当ファイルぶんを読む | No（原則読まない） |
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
- **共通モジュール（`utils/`, `shared/`, `lib/`, `common/`, `helpers/`, `core/`）の変更** — **行数や関数数に関わらず explorer 1 体（shared-module-impact）を起動**（v2.12.0 で緩和: 小規模変更でも依存元への波及を見落とさないため）。**ただし下記の規模下限に該当する場合のみ起動しない**
- 複数ファイル間でデータが流れる変更パターン（schema→domain→DB / FE→BE のような層跨ぎの値フローを含む場合は explorer に `value-flow-trace` focus を優先割り当てする）

上記いずれにも該当しない場合、explorer はスキップする。

#### 共通モジュール必須ルールの規模下限（v2.61.0 / GitHub issue #122）

**次を 3 つとも満たす共通モジュール変更では explorer を起動せず、reviewer（cross-cutting / bug-detection）の Read に委ねる**:

1. `## explorer-signals` の `importers` が **5 以下**（`?`＝数えられなかった場合は起動する側に倒す）
2. その共通モジュールの **export を削除・リネームしておらず、既存引数の必須化もしていない**（型引数の追加・内部実装のみの変更・後方互換な拡張は該当する）
3. **その変更ファイルが他の explorer 起動条件（500 行超 / 3 関数以上 / 条件分岐追加 / 層跨ぎ値フロー）に該当しない**

- 実測（issue #122）: 型引数を 1 つ足しただけ（`+5 -2` 行）の共通モジュール変更に explorer 1 体が **13.6 万 tokens・35 tool_uses** を費やして「問題なし・後方互換」と結論した。呼び出し元が数件なら reviewer 自身の Read で足り、explorer 1 体ぶんが丸ごと浮く
- **v2.12.0 の意図（小規模変更でも依存元への波及を見落とさない）は撤回していない**。下限が効くのは「波及先が数えられて少なく、かつ呼び出し側の書き換えを強制しない変更」だけで、破壊的変更・呼び出し元多数はこれまでどおり必ず起動する
- **`missing_coverage` には記録しない**（条件不成立の未起動は正常系。記録すると欠損観点の偏り集計が潰れる — self-review SKILL の `comment-accuracy` 欠損記録規則と同じ扱い）。代わりに Phase 0 構成テーブルの「リスク因子」行に `共通モジュール変更（importers N 件・explorer 下限で reviewer に委譲）` と出して可視化する
- **委譲先の reviewer には担当ファイルとして当該共通モジュールを必ず割り当てる**（委譲したのに誰も読まない状態を作らない）

### reviewer の観点判定

diff パターンマッチで各観点の必要性を判定する。

| 観点 | 条件 |
|---|---|
| bug-detection | **常時必須** |
| claude-md-compliance | **常時必須** |
| error-handling | try-catch/catch ブロック/エラー処理の変更がある |
| comment-accuracy | diff にコメント（`//`, `/*`, `#`, `<!--` 等）の追加・変更がある。**self-review ではコメント推敲（B 系統）も同じ 1 体に相乗りさせる**（体数を増やさない。`prompts/focus/comment-polish.md`） |
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

diff に外部ライブラリ（React, Next.js, Prisma, Vue, FastAPI 等）の API 利用変更が含まれ、その API の廃止・推奨パターン変更が指摘の核心となる場合、reviewer に公式 skill `context7` を経由した最新仕様確認を許可する（モデル学習データの cutoff を越える破壊的変更の誤判定を避けるため）。詳細は `prompts/reviewer-common.md` を参照。

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
- specialist は対応する Focus テンプレート（`prompts/specialist/<key>.md`）を使用
- specialist の指摘は **大半が BLOCKER または CRITICAL** になるため、低 confidence でも報告マトリクスで人間に届く
- specialist は reviewer 枠とは別カウント（specialist 起動で reviewer 枠を圧迫しない）。**体数は `## 7` の effort 適応表と `## 6.2` の規模キャップの min**（規模側は small 1 体 / medium 2 体）: high 以下では複数 red-flag ヒット時に 1〜2 体へ束ねて該当テンプレートを連結注入する（specialist-guardrail-bypass のみ単独 1 体を維持）。xhigh / max は個別起動・上限 6 体。束ね時の出力規約は `prompts/bundle-rules.md`を参照

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

**冗長ペア（x2）の実起動は xhigh / max 専用**（`## 7`）。high 以下では上記条件を満たしても 1 体で起動し、Angle A / B を両方その 1 体のプロンプトに内挿する（`prompts/angles.md`）。条件判定自体は全 effort で行う（angle 内挿の要否を決めるため）。

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
- 直列 wave: {下限}〜{上限}（{explorer → }reviewer+skeptic{ → [Round 2 ×{1|2}]}{ → [meta+反証]}{ → [追加反証]}）／目安 explorer wave 約 6 min・以降の wave 14〜34 min
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
| reviewer（+ 冷や読み skeptic の相乗り・triage-dynamic-gates.md `## 8.5`） | 常時 | 1 |
| Round 2（triage-dynamic-gates.md `## 8` Phase 5.5） | effort ≥ high かつ unmet_information あり | 0 / 1（high・規模キャップ帯）/ 2（xhigh・max の 2 段） |
| **meta-reviewer + 反証（Phase 5.6 / 5.9 を同一 wave で一括発行**・v2.61.0） | いずれかが起動条件を満たす（meta: effort が xhigh / max かつ BLOCKER/CRITICAL あり（**`small` 帯は BLOCKER 有りのみ**・`## 6.3`）／反証: effort ≥ high かつ対象指摘あり） | 0 / 1 |
| 追加反証バッチ（meta 由来指摘が反証ゲートに該当したときのみ・triage-dynamic-gates.md `## 9`） | meta が起動し、かつ meta 単独由来の指摘が反証ゲートに該当 | 0 / 1 |

- **下限 = Phase 0 で確定している wave**（explorer の有無 + reviewer の 1 本）。**上限 = 上表の各行の最大値の総和**（例に依存せずこの算式で出す）
- 例（effort=xhigh / medium 帯 / explorer 2 体配置）: 下限 = 1（explorer）+ 1（reviewer）= 2、上限 = 2 + 2（Round 2）+ 1（meta+反証）+ 1（追加反証）= 6 なので `直列 wave: 2〜6（explorer → reviewer+skeptic → [Round 2 ×2] → [meta+反証] → [追加反証]）`
- **括弧内の列挙と上限の数を必ず突き合わせる**（`[Round 2 ×2]` は 2 本と数える）。ここがズレると wave 可視化の唯一の出力が誤った目安を提示する
- **wave 単価は層で分けて出す**（explorer wave 約 6 min / 以降の wave 14〜34 min）。**単一の「wave あたり N 分」では表せない** — explorer wave だけが安く、reviewer → 反証 の間が 2 倍以上かかる。**実測値の正本は orchestration-measurement.md `## 15`** で、本節と Phase 0 出力は提示に留める（数値を両方に書かない）。「以降の wave」の値は agent 実行時間とオーケストレーターの統合作業の**合算**で、内訳は分離済み（`orchestration-measurement.md ## 15` の 2 行。実測では約 9 割が前 wave の agent 実行）
- 実測が上限に張り付くようなら、削る候補は wave であって体数ではない（triage-dynamic-gates.md `## 8` の 1 段圧縮経路・triage-dynamic-gates.md `## 8.5` の相乗り・triage-dynamic-gates.md `## 8` Phase 5.5 のスキップ条件）

### 5.2 `models=`（実行世代の表示 / v2.108.0 / GitHub issue #210）

`## meta` に **実行中のメイン世代**を 1 行出す。踏み下げた世代で回した回は検出が落ちるが
（実測: opus-4-8 の 18 レビューで真の空振り 44% / `pre_adjust` MAJOR 中央値 0）、
**それが分かるのは publish 後の集計まで待たないといけなかった**。回す前に見えれば、
そのレビューにコストを払うかを人が決められる。

- **中止も確認もしない。警告だけ出す**（v2.110.0 / #210 候補 1a）。`models=` が **4 系世代**
  （`claude-opus-4-8` 等）なら stderr に `WARN: ⚠️ 世代:` を 1 行出す。**オーケストレーターは
  その 1 行を Phase 0 のレポート冒頭に転記する**（publish の `⚠️ 計測:` と同じ慣例）。
  回すかどうかは依然として利用者の判断 — 警告は「81% が報告 0 件になる世代で回す」という
  コストを選択の瞬間に見えるようにするだけ
  - 述語は「ベースラインと違う」ではなく **4 系世代**。「5 系でない」にすると、より新しい
    世代（`fable-5-1` 等）で回した回まで鳴る。混在は現在どちらで走っているか決められないので
    鳴らさない。5 系が踏み下げになる日が来たら**黙る側に倒れる**（誤爆しない）
  - 実測（gist 集約 n=183 / 2026-09-05）: opus-4-8 で報告 0 件率 **81%**（17/21）・真の空振り
    **43%**（9/21）・`pre_adjust` MAJOR 中央値 **0**。#212 の欠測ゲート後も同水準
- **`models=` は agent へ渡さない。** 世代を伝えるとレビュー挙動が変わりうるので、
  `## meta` の他のキーとは扱いが違う
- **`sub` 側は出さない。** Phase 0 では fleet がまだ起動していないので、値が入るのは
  **前回の fleet の世代**であって、これから起動する世代ではない
- 混在セッション（途中で `/model` を切り替えた回）は単一世代に倒さず `混在（A/B）` と出す（#169）

**誤値を出さないための縮退が 3 段**（`orchestration-measurement.md ## 13.1`
「縮退先は欠測であって誤値ではない」）。どれかに当たれば**行ごと出ない**:

| # | 条件 | なぜ黙るか |
|---|---|---|
| ① | `CLAUDE_CODE_SESSION_ID` が無い | セッションを特定できない |
| ② | その id の transcript を引けない | **`--session` を省いて `ls -t` の最新に倒さない** — 同一リポジトリで並行セッションがあると他セッションの世代を出す |
| ③ | main 側の実モデル名が 1 つも引けない | `<synthetic>` 等のプレースホルダは `measure-tokens.sh` が既に除外する |

実行コストは transcript 1 本の走査で **0.06 秒**（Phase 0 全体で 0.31 秒）。

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
- キャップに収まらない観点は、effort 上限超過と同じ扱いで `missing_coverage` に識別子 `<focus>` を**必ず記録**する（脱落を silent にしない。**規模キャップで落ちた旨はレポート本文へ**）。近接観点のバンドル（`## 7`）による吸収を先に試みる
- 判定した帯と core の実数は Phase 0 の出力（`## 5`）とレポート冒頭・`review:completed` payload の `size_tier` に必ず出す（キャップが効いたことを事後に検証できるようにする）

### 6.3 規模キャップが削るもの・削らないもの

規模キャップが削るのは **breadth（並べる体数）だけ**。depth を担う層は帯に関わらず effort の指定どおり動かす。

- **削る**: explorer / reviewer / specialist の体数、冗長ペア、Round 2 の追加 explorer（**規模キャップが effort 上限を下回った帯では、Round 2 は effort に関わらず triage-dynamic-gates.md `## 8` の 1 段圧縮経路を使う**）
- **削らない**: reviewer 個々の effort（`## 7` の連動表どおり。xhigh 指定なら reviewer は `xhigh` のまま）、冷や読み skeptic（5.8）、反証レイヤー（5.9）。いずれも 1〜数体で、小さな diff ほど 1 体あたりの費用対効果が高い
- **例外 1 つだけ: meta-reviewer（5.6）は `small` 帯かつ BLOCKER 不在のときスキップする**（v2.60.0 / triage-dynamic-gates.md `## 8`）。**この原則に対する唯一の例外**であり、根拠が n=1 と弱いためロールバック条件つきの暫定措置として入れてある（`design-notes/triage-rationale.md`）。**他の depth 層へ横展開しないこと** — skeptic / 反証は帯連動させない

xhigh / max を明示指定したユーザーが求めているのは「小さな diff を深く読むこと」であって「小さな diff に 17 体並べること」ではない。**ただし meta-reviewer は「深く読む」層ではなく「他の reviewer の見落としを探す」層**で、reviewer の体数が規模キャップで 3 体まで絞られた帯では**探す相手そのものが小さい**（実測: `small` 帯で meta が出した 4 件は報告マトリクスを 1 件も通らなかった）。上の例外はこの非対称に基づく。

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

- **冗長ペアは xhigh / max 専用**。high 以下ではペア条件（`## 4` の冗長度判定）成立時も 1 体とし、Angle A / B を両方その 1 体のプロンプトに内挿する（`prompts/angles.md`）
  - **補償の実態を正確に**: 反証レイヤーの `confirmed` は「複数エージェント検出 +15」と同じ発火源だが（scoring-guide.md）、反証対象は**報告マトリクス通過見込みの指摘に限られる**（triage-dynamic-gates.md `## 9`）。つまり **閾値直下の指摘（通常 surface の CRITICAL 70 台・MAJOR 80-94）をペアの +15 が報告側へ押し上げていた効果は補償されない**。この帯の recall 低下は縮小のコストとして許容し、severity 別件数（下記ロールバック条件）で監視する
  - **angle 内挿時の scoring**: 1 体内で両 angle が同一問題に到達しても「ペア合意 +10」は付けず、「片方のみ検出 -5」も適用しない（独立性が担保されないため。scoring-guide.md の両項は冗長ペア実起動時＝xhigh/max のみ発火する）
- **観点バンドル（high 以下）**: 起動条件を満たした観点数が reviewer 上限を超える場合、近接観点を 1 体に束ねて**可能な限り**吸収する（例: error-handling + comment-accuracy + type-design / config + dependency）。1 体あたり 3 観点まで。**bug-detection / security / spec-compliance / claude-md-compliance は束ねず単独を維持**する（指摘密度が高く attention 希釈の代償が大きい観点）。束ね時の出力規約（focus キーは原観点・観点ごとに独立列挙・自己フィルタ禁止）は `prompts/bundle-rules.md`を参照
  - **`comment-accuracy` が束ねられた場合も、self-review のコメント推敲（B 系統）の `## コメント推敲提案` ブロックは省略しない**（v2.45.0）。束ねは attention の配分の話であって出力契約の削減ではない。該当なしなら「該当なし」と明記する（Step 6 の見出しが silent に消えると、推敲ゼロが「提案が無かった」のか「観点が薄まって見なかった」のか区別できなくなる）。**バンドル相乗りでも `comment_polish.fired` は `true`** — 専任 reviewer の有無で切ると high 既定で常に false になる（orchestration-measurement.md `## 16`）
  - **容量と超過時の扱い**: 吸収容量は「単独 4 観点 +（reviewer 上限 − 4）× 3」＝ high で最大 10 観点。観点判定表は 17 観点あるため、フルスタックな大型 PR では超過しうる。**超過分は `missing_coverage` に「観点未起動: <focus>（reviewer 上限超過）」として必ず記録**し、レポートの欠損観点セクションに明示する（脱落を silent にしない）。超過が常態化する PR は xhigh への明示 escalation を促す
- **specialist の束ね起動（high 以下）**: 複数 red-flag 同時ヒット時、specialist-guardrail-bypass のみ単独 1 体を維持し、残りを 1〜2 体に束ねて該当テンプレートを連結注入する（`## 3` Red-flag 節）。トリガー感度は変更しない
- **縮小のロールバック条件（v2.39.0 の high 既定縮小）**: 効果は `review:completed` の `agents` / `duration_fleet_min` / blocker+critical 件数で監視する。**判定に使えるのは `agents` フィールドを持つサンプルのみ**（フィールドの有無が版マーカー。日付では切らない）。悪化の検証は旧データ比ではなく **xhigh/max の明示実行を対照群にした縮小後サンプル内の比較**で行い、`size_tier` を揃える。サンプルが無いうちは判断しない。→ 監視の jq・観測ログ・`review` 由来サンプルが v2.40.0 より前に存在しない理由: `design-notes/triage-rationale.md`
- **体数を壁時計のレバーとして扱わない**。並列発行が効いている限り fleet 区間の実時間は「wave 内最長の 1 体」で決まるため体数削減の効果は線形ではない。**支配的なのは effort（= 直列 wave 数）**（review 13 件。`size_tier` を medium に揃えると high 平均 32 分 / xhigh 平均 61 分と **1.9 倍**なのに、体数レンジは 6〜10 と 6〜11 でほぼ重なる。`73 分 / 6 体` と `19 分 / 7 体` が併存する。GitHub issue #116 / 内訳: `design-notes/triage-rationale.md`）。**この節はかつて「体数と `duration_fleet_min` は無相関」を根拠にしていたが、その事実主張は取り下げた**（v2.116.0 / GitHub issue #217）— サンプルが増えると `small` / `large` で相関が出る（実測 n=213: medium/unrecorded 0.16 / large/unrecorded 0.67 / small/opus-4-8 0.69）。**規範は残る。根拠が変わった**: ①相関は因果ではない（tier・世代・effort・wave 数の統制・synthesis の減算のどれでも消えず、体数と一緒に動く未観測の変数 — diff の難しさ・1 体あたりの探索量 — が両方を押していると読む）②**体数削減は recall を削る**（`## 5.2` の実測: 踏み下げで報告 0 件率 42% → 91%）。**「相関があるから体数を減らせば速くなる」と読まないこと** — 因果の向きが確かめられていないうえ、削るのは recall の側になる。体数削減が確実に効くのは**トークンコスト**。壁時計を縮めたいときにまず触るのは ①1 体あたりの探索量（`prompts/reviewer-common.md` の探索予算）②直列 wave 数（`## 5.1`）③メインコンテキストの複製量（orchestration-guide.md `## 3.5`）。**この節のロールバック判断に「時間が長いから体数を減らす」を混ぜない**（recall だけ落ちて時間が変わらない改悪になる）
