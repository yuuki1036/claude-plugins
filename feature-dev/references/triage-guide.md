# Phase 1.7 トリアージガイド（feature-dev）

Phase 1.7 は実装開始前にメインコンテキストで feature 要件・Issue context・プロジェクト特性を分析し、
explorer / architect の構成を動的に決定するフェーズ。Phase 6 の reviewer 構成はここでは決めない（Section 6）。

## 1. Phase 1.7 概要

- **メインコンテキストで実行する**（Agent ツールは使わない）
- 2 段階判定: Stage 1（タイプ判定）→ Stage 2（体数・フォーカス・冗長度決定）
- 出力はエージェント構成テーブル
- code-review の Phase 0 トリアージと同じ思想だが、「実装前なので diff がない」差分に適応

**code-review との違い:**

| 観点 | code-review Phase 0 | feature-dev Phase 1.7 |
|---|---|---|
| 入力 | diff + PR コンテキスト | feature 要件 + Issue context + プロジェクト特性 |
| Agent 種 | 2（explorer / reviewer） | 2（explorer / architect） |

## 2. 入力情報

Phase 1.7 実行前に以下の情報を収集する:

| 情報 | 取得方法 | 必須 |
|---|---|---|
| feature 要望 | `$ARGUMENTS` + Phase 1 Discovery の確認結果 | Yes |
| Issue context | Phase 1.5 で検出した Issue ファイル（あれば） | 任意 |
| `feature_dev_plan:` frontmatter | Issue ファイルから抽出（あれば） | 任意 |
| CLAUDE.md | プロジェクトルートから読み込み | 存在する場合 |
| プロジェクト特性シグナル | `package.json` 主要依存、ディレクトリ構造 | 存在する場合 |
| 実行時 effort | `${CLAUDE_EFFORT}` | Yes |

## 3. Stage 1: タイプ判定

### feature タイプ判定

要望文と Issue context から以下のタイプを判定する（複数該当可）:

| タイプ | シグナル |
|---|---|
| **bugfix** | 「修正」「直す」「fix」「バグ」「動かない」 |
| **extension** | 「追加」「拡張」「〜にも対応」既存機能の延長 |
| **new-feature** | 「新しい」「新規」「導入」既存に類似のないもの |
| **refactor** | 「リファクタ」「整理」「分割」機能変更なし |
| **migration** | 「移行」「アップグレード」「v2 → v3」など |
| **cross-cutting** | 認証・ログ・エラー処理・i18n など横断的関心事 |

### explorer の必要性判定

以下のいずれかに該当する場合、explorer が必要:

- 既存コードベースに **似た機能が存在**（参照すべきパターンあり）
- 変更対象が **複数モジュールに跨がる** 可能性
- **共通モジュール**（`utils/`, `shared/`, `lib/`, `common/`, `helpers/`）への影響あり
- **migration / refactor タイプ**（既存実装の完全理解が必須）
- Issue context が **不在 or 不十分**（`feature_dev_plan:` がない or 内容が薄い）

以下に該当する場合、explorer をスキップ可能:

- Issue context に **完備された `feature_dev_plan:`** が存在
- 単純な **typo / コピペ修正** レベルの bugfix
- 完全に **隔離されたモジュール** への isolated 追加

### architect の観点判定

architect は常に最低 1 体必要。複数観点を起動する条件:

| 観点 | 起動条件 |
|---|---|
| **minimal-changes** | 常時必須（最小変更案を必ず 1 つ提示） |
| **clean-architecture** | new-feature / refactor タイプ、または cross-cutting（prompt に `Module design vocabulary: ${CLAUDE_PLUGIN_ROOT}/references/module-design.md` を渡す。本文は貼らず architect に Read させる） |
| **pragmatic-balance** | high effort 以上、かつ minimal vs clean のトレードオフが顕著 |
| **migration-strategy** | migration タイプ専用（段階移行・ロールバック戦略） |

### React/Next.js 判定

`package.json` に `react` / `next` が含まれる場合:
- architect に **vercel-best-practices** 観点を追加する

### 外部ライブラリ最新仕様の参照

新規・変更で外部ライブラリ（React, Next.js, Prisma, Vue, FastAPI 等）の利用が含まれる場合、
architect に公式 skill `context7` を経由した最新仕様確認を許可する
（モデル学習データの cutoff を越える破壊的変更の誤判定を避けるため）。

## 4. Stage 2: 体数・フォーカス決定

### explorer の体数と focus

| feature 特性 | 体数 | focus の切り方 |
|---|---|---|
| Issue context 完備 + 単純追加 | 0 | スキップ |
| 単一モジュールへの isolated 追加 | 1 | 類似機能トレース |
| 既存機能の拡張（中規模） | 2 | 類似機能 + アーキ層マッピング |
| cross-cutting / 複数モジュール | 2-3 | + 共通モジュール影響範囲 |
| refactor / migration | 3-4 | + 履歴コンテキスト + 依存追跡 |
| 大規模 greenfield 機能 | 3-5 | レイヤー別（UI / API / DB） |

### architect の体数と focus

| feature 特性 | 体数 | focus の切り方 |
|---|---|---|
| Issue context に既存 `feature_dev_plan:` あり、または `design=` で design doc を受け取った | 1 | delta 提案（再設計しない） |
| 標準的な機能追加 | 1-2 | minimal-changes [+ clean-architecture] |
| トレードオフが顕著 | 2-3 | + pragmatic-balance |
| migration タイプ | 2 | migration-strategy + minimal-changes |

## 5. Effort 適応

実行時 effort = `${CLAUDE_EFFORT}` に応じて上限を調整する:

| effort | explorer 上限 | architect 上限 | 備考 |
|---|---|---|---|
| `low` | **0**（Phase 2 skip） | 1 | 速度優先。clarifying questions も最小化 |
| `medium` | 2 | 1 | 軽量だが explorer は許可 |
| `high`（既定） | 3 | 2 | 標準構成 |
| `xhigh` | 5 | 3 | 多角的検証 |
| `max` | 6 | 3 | 上限まで使い、深掘り優先 |

Phase 6 の reviewer 体数は、self-review が同じ `${CLAUDE_EFFORT}` で code-review の上限を当てて決める。

## 6. Phase 6 の reviewer 構成は code-review の triage に任せる

Phase 1.7 は reviewer の構成を決めない。Phase 6 の初回 self-review は `--focus` を付けずに呼び、観点の選定・体数・束ね方は self-review の Phase 0 triage（diff シグナル・規模・effort）が決める（GitHub issue #283）。

- **`--focus` を付けない理由**: self-review の `--focus` は「既に検証した観点の再評価を避ける」ための引数で、指定すると反証レイヤーと skeptic が `scope` でスキップされ、triage の `## focus-signals`（`layer-responsibility` など）も範囲外になる。Phase 6 の初回はその変更の最初のレビューなので、この前提が成り立たない。実測では feature-dev 経由の high 以上 5 回すべてで反証が `scope` でスキップされ、auto-fix 対象になる CRITICAL が反証を通らずに残った
- **feature-dev が持つ情報の渡し方**: BDD spec は `--spec=<path>` で渡す（self-review の triage が spec-compliance を起動する）。Issue ファイル・`.claude/session-context.md` は self-review 側が自分で読んで spec-compliance の起動条件に使う
- **`--focus` を使うのは G-V ループの再レビューだけ**（Section 10）。修正した指摘の観点を見直す回で、「既検証の再評価を避ける」本来の用途に当たる

## 7. 出力フォーマット

Phase 1.7 の出力はエージェント構成テーブルとして表示する。

```
## Phase 1.7 トリアージ結果

### 特性
- スコープ: {small|medium|large}
- 種別: {bugfix|extension|new-feature|refactor|migration|cross-cutting}
- リスク因子: [auth, migration, ...]
- Issue context: [available|absent|partial]
- React/Next.js: [yes|no]

### エージェント構成

#### Phase 2 探索（explorer）
| # | focus | 対象 | 指示 |
|---|---|---|---|
| E1 | similar-features | src/auth/ | OAuth ハンドラの既存実装トレース |
| E2 | architecture-mapping | - | 認証フロー全体の抽象層マッピング |

#### Phase 4 設計（architect）
| # | focus | 指示 |
|---|---|---|
| A1 | minimal-changes | 既存 middleware を再利用する最小案 |
| A2 | clean-architecture | 新規 Provider 抽象を導入したクリーン案 |
```

## 8. フォールバック構成

Phase 1.7 が明確な判断を下せない場合のデフォルト構成（effort=high 想定）:

### small（単一モジュール、単純追加）

- explorer: 1 体（similar-features）
- architect: 1 体（minimal-changes）

### medium（複数ファイル、標準的な機能）

- explorer: 2 体（similar-features, architecture-mapping）
- architect: 2 体（minimal-changes, clean-architecture）

### large（cross-cutting / migration）

- explorer: 3 体（+ cross-cutting / history-context）
- architect: 2-3 体（+ pragmatic-balance or migration-strategy）

## 9. 最小保証とフェーズ上限

- **最小保証（全 effort 共通）**:
  - architect: ≥ 1 体
  - explorer: 0 体 OK（Issue context 完備時）
- **上限**: Section 5 の effort 別上限に従う

## 10. Generator-Verifier ループ予算（Phase 6 自動 fix）

v2.0.0 で Phase 6 のレビューは `code-review:self-review` skill に委譲されたため、トリガー判定は self-review の **severity × confidence 2 軸出力** に基づく。
Phase 5 (Implementation) に自動差し戻して修正を試行する点は変わらない。

### effort 別ループ予算

| effort | max_iterations | 動作 |
|---|---|---|
| `low` | **0** | 自動 fix を行わない。critical 指摘もユーザに即提示し判断を仰ぐ（速度・透明性優先） |
| `medium` | 1 | 最大 1 回まで自動 fix 試行 |
| `high`（既定） | 2 | 最大 2 回まで自動 fix |
| `xhigh` | 3 | 最大 3 回まで自動 fix |
| `max` | 3 | 最大 3 回（深掘り優先） |

### Auto-fix トリガー（severity × confidence マッピング）

| self-review 出力 | feature-dev 扱い |
|---|---|
| `BLOCKER` (any confidence) | **auto-fix 対象**（最高優先度。security/data-loss class なので confidence を問わず即修正） |
| `CRITICAL && confidence ≥ 90` | **auto-fix 対象**（従来の高 confidence 閾値を維持して誤検知防止） |
| `CRITICAL && confidence < 90` | 報告のみ（Step 4 でユーザー判断） |
| `MAJOR` / `MINOR` (any confidence) | 報告のみ |

self-review 内部の confidence しきい値（BLOCKER は 60+、CRITICAL は 80+ で報告される）は v2.0.0 では尊重し、feature-dev 側で再フィルタしない。

### Regression 検知

無限ループ防止のため、`/tmp/feature-dev-loop-state.json` に各 iteration の指摘 fingerprint を記録:

```json
{
  "run_id": "<uuid>",
  "max_iterations": 2,
  "current_iteration": 1,
  "iterations": [
    {
      "iter": 0,
      "fingerprints": ["src/auth.ts:67:bug-detection", "src/db.ts:23:security"]
    },
    {
      "iter": 1,
      "fingerprints": ["src/auth.ts:67:bug-detection"]
    }
  ]
}
```

fingerprint は `file:line:focus` のタプル。**同一 fingerprint が連続 2 iteration で残存した場合は「自動 fix 不能」と判定し、即座にループを break してユーザに提示**する（再帰的に同じ修正を試みても無駄なため）。

### ループ終了条件

以下のいずれかでループを終了し Step 4（Final consolidation）へ進む:

1. auto-fix 対象（`BLOCKER` または `CRITICAL && conf ≥ 90`）が 0 件になった（成功）
2. `current_iteration == max_iterations` に到達（予算切れ）
3. Regression 検知（同一 fingerprint が連続 2 回残存）
4. メインスレッドが「修正不能」と判断（複雑すぎる、設計再考が必要等）

### Fix の責務分離

- **メインスレッドが直接修正**（Edit ツール）: reviewer が `file:line` + 修正サジェスチョンを明示している場合の標準パス
- **code-architect agent を起動して再設計**: メインスレッドが「修正には設計変更が必要」と判断した場合の逃げ道。設計変更後は Phase 5 で再実装、loop budget は **1 回分消費**

### Phase 5 Fix Mode

Phase 5 は通常モードと Fix Mode の 2 形態を持つ:

| モード | 起動元 | 動作 |
|---|---|---|
| 通常 | Phase 4 完了後 | architect の設計に従い feature を実装 |
| Fix Mode | Phase 6 G-V ループから | Phase 6 が指定した critical 指摘リストのみを対象に修正。**スコープ拡大禁止**、reviewer の指摘した範囲のみ |

Fix Mode では:
- 元の architect 設計（Phase 4 で user が選んだ approach）は維持
- 修正は ピンポイント（reviewer が指摘した file:line ベース）
- 修正後 Phase 5.5 (Smoke Test) は skip（既に通過済みのため）— ただし `low` 以外の effort で修正が runtime-sensitive なら再実行を推奨
