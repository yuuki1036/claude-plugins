---
name: self-review
description: >
  Phase 0 トリアージ + 動的エージェント構成のセルフレビュー。
  diff → explorer(sonnet) → reviewer(opus) を動的構成、severity×confidence マトリクスでフィルタ。
  トリガー: 「セルフレビュー」「/self-review」「自分の変更を確認」「コミット前にチェック」
  引数: [base branch] [--staged] [--focus <観点>] [--exclude <観点1,観点2>] [--embed] (省略時は自動検出)
effort: xhigh
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---

# Self Review

## review との違い

- PR 不要。ローカルのみで完結
- コミット前・PR 作成前の品質ゲートとして使用

## 設計原則: Generator と分離された Evaluator

self-review は `dev-workflow:git-commit-helper`（Generator: 変更を生成・コミットする側）から独立した Evaluator として機能する。同一コンテキストで生成と判定を行うと confirmation bias で見落としが増えるため、以下のフローを推奨する:

1. 実装・変更 → `/self-review` （別コンテキストで起動）
2. 指摘事項を修正
3. `/git-commit-helper` でコミット

Phase 0 の explorer/reviewer 並列起動も同じ思想で、reviewer は explorer の結果を「独立した観点として」受け取る（自分で diff を再探索させない）。

## 実行手順

### 1. diff 収集とコンテキスト準備

```bash
# 引数で base branch が指定されていればそれを使用
# 指定がなければデフォルトブランチを自動検出
git remote show origin | grep "HEAD branch" | sed 's/.*: //'
```

base branch が特定できない場合はユーザーに確認する。

```bash
# base branch との全差分（コミット済み + 未コミット）
git diff "${BASE}..HEAD"
git diff
git diff --cached
git diff "${BASE}..HEAD" --name-only
git diff --name-only
git diff --cached --name-only

# 変更ファイルの行数
wc -l <changed_files>
```

変更がなければ終了。

`--staged` 引数が指定されている場合は `git diff --cached` のみを対象とし、未ステージの変更は除外する。

**`--embed`（他 plugin からの呼び出し）:**

`--embed` 引数が指定されている場合は、本 skill が他 plugin（例: feature-dev Phase 6）からプログラム的に呼び出されたと判断する。Step 7 の修正方針確認 AskUserQuestion を skip し、Step 6 のレポートをそのまま return する。呼び出し元側で findings を集約・後処理する前提。

embed mode 時の return 仕様（**dual format**: 人間可読 markdown ＋ 機械可読 JSON）:
- Step 6 のレポート全文（severity 別にグルーピングされた指摘リスト、欠損観点、総括）を出力
- **その直後に Step 6.5 の構造化 findings JSON ブロックを出力**（`<!-- FINDINGS_JSON_START -->` / `<!-- FINDINGS_JSON_END -->` で囲む）。呼び出し元はこの JSON を決定的にパースして findings を集約する（markdown の正規表現パースに依存させない）
- 末尾に `[embed-mode: findings-only, no-prompt]` の 1 行 marker を出す（JSON ブロックの**後ろ**）
- AskUserQuestion は呼ばない（呼び出し元の UX を阻害しない）
- 後方互換: `--embed` 指定なしの呼び出し（`/self-review` 単独実行等）は従来通り Step 7 まで完走し、JSON ブロックは出力しない

**`--focus` / `--exclude`（同一セッションでの重複レビュー回避）:**

同一セッションで既に reviewer agent を走らせた後（コミット前並列レビュー等）に self-review を再実行する場合、既検証の観点を再報告しないよう以下の引数でスコープを制御する:

- `--focus <観点>`: レビュー対象を特定の観点に絞る（例: `--focus "comment-conciseness"`, `--focus "type-safety"`）。複数指定はカンマ区切り
- `--exclude <観点1,観点2>`: 既に他 agent でカバー済みの観点をスキップする

適用先:
- **Phase 0 (Step 2)**: `--focus` 指定時は該当観点の reviewer のみ構成する（最小保証の reviewer-bugs / reviewer-claude-md も `--focus` に含まれない限り起動しない）。`--exclude` 指定時は該当観点の reviewer を構成から外す
- **reviewer 起動時 (Step 4)**: 各 reviewer プロンプトに以下を注入する

  ```
  review focus: {{ focus or "全件" }}
  already verified (do not re-report): {{ exclude or "none" }}
  ```

**コンテキスト収集（並列で実行）:**
- CLAUDE.md・規約ファイル: `CLAUDE.md`, `.github/CONTRIBUTING.md`, `.eslintrc.*`, `prettier.config.*`
- `.claude/session-context.md` の存在確認（存在する場合、frontmatter の `branch` と現在のブランチ名を比較。一致すれば有効）
- Issue/knowledge ファイルの探索
- プロジェクト特性シグナル（`package.json` の存在確認と主要依存の確認）

### 2. Phase 0: トリアージ

`${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` を Read で読み込み、そのロジックに従ってエージェント構成を決定する。

**Phase 0 はメインコンテキストで実行する（Agent ツールは使わない）。**

#### 2.1 Stage 1: タイプ判定

diff の特性を分析し、必要なエージェントタイプを判定する:
- **explorer**: 巨大ファイル、複数関数、条件分岐追加、共通モジュール変更のいずれかに該当するか
- **reviewer**: 常に必要。diff パターンマッチでどの観点が必要かを判定
- **spec-compliance**: session-context / Issue / knowledge が存在するか

#### 2.2 Stage 2: 体数・フォーカス・冗長度決定

各タイプの体数と各エージェントの具体的なフォーカスを決定する:
- explorer: 独立した探索対象の数に比例（上限 6 体）
- reviewer: 必要な観点数 × 対象コードの複雑さに応じた冗長度（上限 10 体）
- 冗長ペアには異なる angle（分析の切り口）を割り当てる
- 最小保証: reviewer-bugs + reviewer-claude-md の 2 体は常に起動

#### 2.3 構成テーブル出力

triage-guide.md の出力フォーマットに従い、エージェント構成テーブルを出力する。

### 3. 探索フェーズ（explorer 並列起動）

Phase 0 が explorer を 1 体以上配置した場合のみ実行。explorer が不要と判断された場合はスキップして Step 4 へ。

`${CLAUDE_PLUGIN_ROOT}/references/explorer-prompts.md` を Read で読み込む。

Phase 0 の構成テーブルに従い、各 explorer を `model: sonnet` で並列起動する:
- 各 explorer に Phase 0 が決定した focus と対象ファイル・関数を指示として渡す
- explorer-prompts.md の該当する Focus テンプレートをプロンプトに含める
- `isolation: "worktree"` は使用しない（セルフレビューは未コミット変更を含むため）

全 explorer の完了を待ち、結果を収集する。

**部分失敗耐性:** 個別 explorer が失敗しても全体を中止しない。失敗した explorer の type / focus / エラー要旨を `missing_coverage` リストに記録し、残った explorer の結果で続行する。該当 focus に依存する reviewer には、Step 4 で「探索結果なし（失敗理由）」を明示して渡す。

### 3.9 AGENTS.md 階層動的選択（reviewer 起動前）

変更ファイルパスから対応する `{dir}/AGENTS.md` を Glob で発見し、該当層だけを reviewer プロンプトに同梱する。リポジトリ全体の AGENTS.md / CLAUDE.md を毎回フルロードせず、変更があった層のみ拾うことで reviewer 入力 token を典型 30〜50% 削減する。

```bash
git diff "${BASE}..HEAD" --name-only | xargs -n1 dirname 2>/dev/null | sort -u | while read dir; do
  while [ "$dir" != "." ] && [ "$dir" != "/" ]; do
    [ -f "$dir/AGENTS.md" ] && echo "$dir/AGENTS.md"
    [ -f "$dir/CLAUDE.md" ] && echo "$dir/CLAUDE.md"
    dir=$(dirname "$dir")
  done
done | sort -u
```

ヒットしたファイルのみ Read で読み込み、各 reviewer のプロンプトに `## 該当層の AGENTS.md / CLAUDE.md` セクションとして注入する。AGENTS.md が無いリポジトリでは no-op（後方互換）。

### 4. レビューフェーズ（reviewer 並列起動）

`${CLAUDE_PLUGIN_ROOT}/references/reviewer-prompts.md` を Read で読み込む。

Phase 0 の構成テーブルに従い、各 reviewer を `model: opus`、`effort: max` で並列起動する:
- 各 reviewer に Phase 0 が決定した focus（と冗長ペアの場合は angle）を指示として渡す
- reviewer-prompts.md の該当する Focus テンプレートと共通指示をプロンプトに含める
- **explorer 結果の選択的注入**: 構成テーブルの「explorer 依存」列に記載された explorer の結果を、該当する reviewer のプロンプトに `## Explorer 結果` セクションとして注入する
- セッションコンテキストが有効な場合、reviewer-prompts.md のセッションコンテキスト注入テンプレートに従い全 reviewer に注入する
- diff 全文を各 reviewer に渡す
- `isolation: "worktree"` は使用しない

**effort 設計意図**: reviewer は `max` で深い推論を優先（overthinking による偽陽性は Confidence ≥80 フィルタで刈り取る）。オーケストレーター（skill frontmatter）は `xhigh`。Opus 4.8 は `high` が既定 effort のため、demanding task 向けに一段引き上げた設定。

**diff-first 原則:** 各エージェントには diff の出力を渡す。エージェントのファイル Read は共通ユーティリティの仕様確認など、diff だけでは判断できない文脈把握に限定する。ただし、変更箇所を含む関数の全体確認は積極的に行うこと。

全 reviewer の完了を待ち、結果を収集する。

**部分失敗耐性:** 個別 reviewer が失敗しても成功した reviewer の結果で合成継続する。失敗した reviewer の focus / angle / エラー要旨を `missing_coverage` リストに追記する。

**最小保証の閾値:** Phase 0 の最小保証（reviewer-bugs と reviewer-claude-md）が **両方とも失敗** した場合のみレビュー中止とし、ユーザーに再実行を促す。それ以外は欠損観点を明示しつつ Step 5 に進む。

### 4.5 Adaptive deepening: 追加 explorer ラウンド（v2.12.0 / 動的）

**スキップ条件**（いずれか満たせばこのフェーズ全体をスキップして Step 4.6 へ）:
- userConfig `enable_adaptive_rounds` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `low` または `medium`
- 全 reviewer の出力に `## unmet_information` セクションが 1 件もない

**実行する場合**:

1. 全 reviewer 出力をパースし、`## unmet_information` セクションを集約する
2. 集約結果から **最大 3 件** の追加探索ターゲットを選ぶ（BLOCKER 候補に関わる unmet を優先）
3. `${CLAUDE_PLUGIN_ROOT}/references/explorer-prompts.md` の `re-explore` テンプレートで追加 explorer を `model: sonnet` で並列起動する
   - 各 explorer に対応する unmet_information を指示として渡す
   - `isolation: "worktree"` は使用しない（self-review は未コミット変更を含むため）
4. 追加 explorer 完了後、unmet を申告した reviewer のみ（最大 3 体）を `model: opus`, `effort: max` で再起動
   - 初回指摘 + 追加 explorer 結果を context として渡し、「初回 confidence を再評価せよ」と指示
   - 再起動 reviewer の出力は初回出力を置換
5. レポートに「Round 2 trigger: <reason>」を記録（Step 6 で出力）

**失敗時**: 追加 explorer / 再起動 reviewer が失敗した場合は初回結果のままで続行（best-effort）

### 4.6 Meta-reviewer ラウンド（v2.12.0 / 動的）

**スキップ条件**（いずれか満たせばスキップして Step 5 へ）:
- userConfig `enable_meta_reviewer` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `xhigh` または `max` **でない**
- Step 4.5 後の全指摘（フィルタリング前）に **BLOCKER も CRITICAL も 1 件もない**

**実行する場合**:

1. `${CLAUDE_PLUGIN_ROOT}/references/reviewer-prompts.md` の `## 6. Meta-reviewer テンプレート` を使用
2. meta-reviewer agent を 1 体、`model: opus`, `effort: max` で起動
   - 入力: diff、全 reviewer の指摘リスト（フィルタ前）、起動された focus 一覧、explorer 結果
   - `isolation: "worktree"` は使用しない
3. meta-reviewer の出力（追加指摘）を既存指摘に統合
   - 重複は dedup（同一ファイル ±5 行 + 類似内容）
   - meta-reviewer の指摘も通常のスコアリング・フィルタリング対象

**失敗時**: meta-reviewer が失敗した場合は missing_coverage に `meta-reviewer: <failure reason>` を追記して続行

### 5. スコアリングとフィルタリング（2軸: confidence × severity）

全 reviewer の指摘を統合し、`${CLAUDE_PLUGIN_ROOT}/references/scoring-guide.md` を Read で読み込んでスコアリングを実施する。

1. **各指摘の base confidence と severity を取得**
   - reviewer 出力の `[confidence: XX]` と `[severity: BLOCKER|CRITICAL|MAJOR|MINOR]` をパース
   - severity が欠落している指摘は **CRITICAL とみなす**（後方互換 / 安全側デフォルト）
2. **confidence への加算・減算ルールを適用**して 0-100 にクランプ
3. **severity 調整**: `[scope:out]` / `[resolved: ...]` タグ付きは severity を 1 段階下げる（self-review では PR タグは通常出ない）
4. **報告マトリクスでフィルタ**:

   | severity \ confidence | <60 | 60-79 | 80-94 | 95+ |
   |---|:---:|:---:|:---:|:---:|
   | BLOCKER | skip | 報告 | 報告 | 報告 |
   | CRITICAL | skip | skip | 報告 | 報告 |
   | MAJOR | skip | skip | skip | 報告 |
   | MINOR | skip | skip | skip | 報告 |

5. **userConfig 適用**: `review_severity_threshold` (default: `MAJOR`) より低い severity は除外

### 6. レポート出力

`missing_coverage` リストが空でない場合は「⚠️ 欠損観点」セクションを追加する（空なら省略）。

```
## セルフレビュー結果

**総合評価**: X/10 点
**レビュー構成**: Phase 0 (triage) → 探索 (N 起動 / M 成功) → レビュー (N 起動 / M 成功)
**動的ラウンド**: Round 2 探索 N 体起動 / Meta-reviewer {実行 | スキップ理由}
**指摘件数**: BLOCKER N 件 / CRITICAL N 件 / MAJOR N 件 / MINOR N 件

### 🚨 BLOCKER 指摘

1. [confidence: 70][severity: BLOCKER][セキュリティ] Hardcoded secret の疑い
   ファイル: src/config.ts:15
   影響: コミット時にシークレット漏洩

### ⚠️ CRITICAL 指摘

2. [confidence: 95][severity: CRITICAL][バグ] Missing null check
   ファイル: src/utils.ts:42
   影響: 特定入力で関数が落ちる

### 📋 MAJOR 指摘

3. [confidence: 95][severity: MAJOR][設計] ...

### ⚠️ 欠損観点（Agent 失敗による未カバー領域）
- reviewer-security: ネットワーク I/O エラーで失敗 → 認証まわりの観点は未検査
- explorer-<focus>: timeout → 依存していた reviewer-<focus> には探索結果なしで実行

### 総括
- 変更の概要
- コミット前に修正すべき項目（特に BLOCKER）
- 確認推奨の観点
```

### 6.4. Event Bus publish（`review:completed` / 計測用）

レポート出力後、集計結果を `.claude/events.jsonl` に追記する fire-and-forget の publisher。**embed / 非 embed の両モードで実行する**（LLM 駆動 fan-out の「観点取りこぼし」「severity/confidence のパース安定性」を後から定量化するための計測データを蓄積する目的。review skill と同じ `review:completed` イベントで集計を揃える）。

副作用のみで標準出力にレポート文字を足さないため、embed mode の出力フォーマット（Step 6.5 の JSON ブロック → marker の順序）には影響しない。self-review は PR を持たないため `pr` は `"local"` 固定とする。

```bash
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib/safe-hook.sh" 2>/dev/null && \
  SAFE_HOOK_NAME="code-review:self-review" event_bus_publish "review:completed" \
  "{\"pr\":\"local\",\"blocker_count\":<n>,\"critical_count\":<n>,\"major_count\":<n>,\"minor_count\":<n>,\"missing_coverage\":[<json-array of focus names>],\"result_grid\":{\"high\":<n>,\"medium\":<n>,\"low\":<n>,\"skip\":<n>,\"error\":<n>}}"
```

payload 規約（review skill と同一。subscriber が publisher を区別せず集計できるよう揃える）:
- `pr`: self-review は常に `"local"`
- `blocker_count` / `critical_count` / `major_count` / `minor_count`: severity 別件数（Step 6 報告マトリクス通過後）
- `missing_coverage`: 欠損観点の focus 名配列（空なら `[]`）
- `result_grid`: `high`=BLOCKER+CRITICAL / `medium`=MAJOR / `low`=MINOR / `skip`=severity フィルタ除外件数 / `error`=Agent 失敗数（`missing_coverage` の length と一致）
- 失敗してもレビュー自体は成功扱い（best-effort）。`SAFE_HOOK_NAME` を `code-review:self-review` に上書きして publisher を識別する

### 6.5. 構造化 findings JSON（embed mode のみ）

**`--embed` が指定されている場合のみ**、Step 6 の markdown レポート直後に機械可読な findings ブロックを出力する（非 embed 実行では出力しない）。呼び出し元（feature-dev Phase 6 等）はこの JSON を決定的にパースし、markdown の正規表現パースに依存しない。

出力フォーマット（マーカーで厳密に囲む。前後に余計な文字を入れない）:

~~~
<!-- FINDINGS_JSON_START -->
```json
{
  "schema_version": 1,
  "summary": {"score": 7, "blocker": 1, "critical": 2, "major": 1, "minor": 0},
  "findings": [
    {
      "id": 1,
      "severity": "BLOCKER",
      "confidence": 70,
      "focus": "security",
      "file": "src/config.ts",
      "line": 15,
      "title": "Hardcoded secret の疑い",
      "impact": "コミット時にシークレット漏洩",
      "suggested_fix": "process.env.X 経由に置換する"
    }
  ],
  "missing_coverage": ["reviewer-security: timeout で未検査"]
}
```
<!-- FINDINGS_JSON_END -->
~~~

フィールド契約（**schema_version: 1**。変更時は bump して consumer に通知）:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `schema_version` | int | yes | 契約バージョン。フィールド追加/変更時に bump |
| `summary.score` | int | yes | 総合評価 (0-10) |
| `summary.{blocker,critical,major,minor}` | int | yes | severity 別件数（Step 6 報告マトリクス通過後の件数） |
| `findings[].id` | int | yes | Step 6 の連番と一致させる |
| `findings[].severity` | enum | yes | `BLOCKER` \| `CRITICAL` \| `MAJOR` \| `MINOR`（Step 5 でスコアリング後の最終値） |
| `findings[].confidence` | int | yes | 0-100（Step 5 で加減算後の最終値） |
| `findings[].focus` | string | yes | **発生元 reviewer の安定 focus キー**（`bug-detection` / `security` / `claude-md-compliance` / `error-handling` / `spec-compliance` / `performance` 等。triage-guide の focus 語彙）。表示用の日本語カテゴリ（`[セキュリティ]` 等）ではなく、**この英語キーを使う**。呼び出し元の fingerprint (`file:line:focus`) と `--focus` / `--exclude` の語彙に揃える |
| `findings[].file` | string | yes | リポジトリ相対パス |
| `findings[].line` | int | yes | 主たる行番号（範囲なら開始行） |
| `findings[].title` | string | yes | 1 行要約 |
| `findings[].impact` | string | no | 影響説明 |
| `findings[].suggested_fix` | string | no | 修正方針（呼び出し元の auto-fix が利用。不明なら省略可） |
| `missing_coverage` | string[] | yes | 欠損観点（空配列可） |

- **findings は Step 6 で報告された指摘と 1:1**（報告マトリクスで skip されたものは含めない）。`id` は Step 6 のレポート連番に一致させる
- JSON として valid であること（末尾カンマ禁止、ダブルクオート、改行は文字列内で `\n`）
- このブロックの**後**に `[embed-mode: findings-only, no-prompt]` marker を置く

### 7. 修正方針の確認

**embed mode skip**: 引数で `--embed` が指定されている場合は本ステップ全体を skip する。Step 6 の markdown レポート → **Step 6.5 の構造化 JSON ブロック** → `[embed-mode: findings-only, no-prompt]` の 1 行 marker、の順で出力して完了。AskUserQuestion を呼ばないことで呼び出し元 plugin の UX を阻害しない。

指摘事項が 1 件以上ある場合のみ実行する。指摘が 0 件なら「問題なし」で完了。

レポート全文を出力し終えた直後に **AskUserQuestion** で修正方針を確認する:
- question: "指摘事項への対応方針を選択してください（コミット前の作業優先度を整理します）"
- header: "修正方針"
- options:
  1. label: "すべて修正" / description: "指摘事項をすべて今すぐ修正する"
  2. label: "BLOCKER/CRITICAL のみ" / description: "severity BLOCKER または CRITICAL の指摘だけ修正する"
  3. label: "このまま" / description: "修正はせず、このままコミットする"

各選択肢の後処理:
- **すべて修正**: 全指摘を一覧化し、ファイルごとにまとめて修正を実施する
- **BLOCKER/CRITICAL のみ**: 該当 severity の指摘のみ再表示し、ファイルごとにまとめて修正を実施する
- **このまま**: 完了（BLOCKER 指摘が 1 件以上残っている場合は「BLOCKER 指摘を残したままコミットしますか？」と AskUserQuestion で再確認する）
