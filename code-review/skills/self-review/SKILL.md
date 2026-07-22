---
name: self-review
description: >
  Phase 0 トリアージ + 動的エージェント構成のセルフレビュー。
  diff → explorer(sonnet) → reviewer(opus) を動的構成、severity×confidence マトリクスでフィルタ。
  トリガー: 「セルフレビュー」「/self-review」「自分の変更を確認」「コミット前にチェック」
  引数: [base branch] [--staged] [--focus <観点>] [--exclude <観点1,観点2>] [--embed] (省略時は自動検出)
effort: high
allowed-tools:
  - Bash
  - Read
  - Agent
  - AskUserQuestion
---

# Self Review

## review との違い

- PR 不要。ローカルのみで完結
- コミット前・PR 作成前の品質ゲートとして使用

## コスト×精度パイプライン設計（採用/不採用）

ルート CLAUDE.md「コスト×精度パイプライン設計指針」の 10 原則のうち **採用: 1（ファネル = Phase 0 triage で高コスト reviewer を通過分に絞る）/ 2（2 軸スコア化 = confidence × severity マトリクス）/ 3（段階予算 = `${CLAUDE_EFFORT}` → explorer/reviewer 体数）/ 4（モデルルーティング = explorer:sonnet / reviewer:opus / meta:opus / 反証:opus）/ 7（敵対的独立検証 = Phase 4.9 反証レイヤー、recall 側は Phase 4.8 冷や読み skeptic）**。**捨てた**: 5（暴走ガード）は反復・起票を持たない単発レビューのため不要、6（証拠ラダー）は指摘蓄積・昇格の責務を failure-journal に委ね、8（外部オラクル）は diff レビューが対象で型/テスト実行は feature-dev Phase 5.3 の役割と分離した。

## 設計原則: Generator と分離された Evaluator

self-review は `dev-workflow:git-commit-helper`（Generator: 変更を生成・コミットする側）から独立した Evaluator として機能する。同一コンテキストで生成と判定を行うと confirmation bias で見落としが増えるため、以下のフローを推奨する:

1. 実装・変更 → `/self-review` （別コンテキストで起動）
2. 指摘事項を修正
3. `/git-commit-helper` でコミット

Phase 0 の explorer/reviewer 並列起動も同じ思想で、reviewer は explorer の結果を「独立した観点として」受け取る（自分で diff を再探索させない）。

## 実行手順

実行フェーズの共通詳細（部分失敗耐性・auto-retry・動的ラウンドの実行手順・Vault 照合・訂正の伝播前ガード）の正本:
→ Read `${CLAUDE_PLUGIN_ROOT}/references/orchestration-guide.md`（以下「orchestration-guide」。self-review では `isolation: "worktree"` を使わない等の差分は同ガイド `## 0` を参照）

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

### 1.5 Vault 照合（過去の指摘・落とし穴の retrieval / 任意・後方互換）

レビュー局面は蓄積された知見が最も効く高 ROI な発火点。変更ファイルに関連する過去のレビュー指摘・落とし穴を vault から引いて reviewer に注入する（GitHub issue #68。feature-dev Phase 1.6 Vault Recall と同一の retrieval 基盤を呼ぶ対の改善）。

利用可否の検出（`kvault` / `/vault-recall` が無ければ skip の後方互換）・照合手順（クエリ構築 → similarity と gap で関連度判定 → reviewer プロンプトへの注入）・best-effort の注意事項:
→ orchestration-guide `## 11`

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
- 全エージェントに `run_in_background: false` を明示する（orchestration-guide `## 0`。省略すると background 起動になり結果を取りこぼす）

全 explorer の完了を待ち、結果を収集する。

**部分失敗耐性:** orchestration-guide `## 5` に従う（個別失敗で全体を中止せず `missing_coverage` に記録して続行）。

### 3.9 AGENTS.md 階層動的選択（reviewer 起動前）

変更ファイルパスから対応する `{dir}/AGENTS.md` を Bash で探索し、該当層だけを reviewer プロンプトに同梱する（reviewer 入力 token を典型 30〜50% 削減）。

探索 bash・注入セクション名・no-op 条件（後方互換）の詳細: → orchestration-guide `## 4`

### 4. レビューフェーズ（reviewer 並列起動）

`${CLAUDE_PLUGIN_ROOT}/references/reviewer-prompts.md` を Read で読み込む。

Phase 0 の構成テーブルに従い、各 reviewer を `model: opus`、`effort: xhigh` で並列起動する:
- 各 reviewer に Phase 0 が決定した focus（と冗長ペアの場合は angle）を指示として渡す
- reviewer-prompts.md の該当する Focus テンプレートと共通指示をプロンプトに含める
- **explorer 結果の選択的注入**: 構成テーブルの「explorer 依存」列に記載された explorer の結果を、該当する reviewer のプロンプトに `## Explorer 結果` セクションとして注入する
- セッションコンテキストが有効な場合、reviewer-prompts.md のセッションコンテキスト注入テンプレートに従い全 reviewer に注入する
- **Vault 注入**: Step 1.5 で関連ありと判断した知見があれば、各 reviewer プロンプトに `## Vault prior findings（過去の関連指摘・落とし穴）` セクションとして注入する。reviewer には「過去に同種コードで指摘された観点を優先的に確認せよ。ただし現在の diff に該当しなければ無視してよい」と添える
- diff 全文を各 reviewer に渡す
- `isolation: "worktree"` は使用しない
- 全エージェントに `run_in_background: false` を明示する（orchestration-guide `## 0`）

全 reviewer の完了を待ち、結果を収集する。

reviewer 起動の共通詳細（effort 設計意図・diff-first 原則・出力形式の検証と auto-retry・部分失敗耐性・最小保証の閾値）: → orchestration-guide `## 5`

**最小保証の閾値のみ抜粋**: Phase 0 の最小保証（reviewer-bugs と reviewer-claude-md）が **両方とも失敗** した場合のみレビュー中止とし、ユーザーに再実行を促す。それ以外は欠損観点を明示しつつ Step 5 に進む。

### 4.5 Adaptive deepening: 追加 explorer ラウンド（v2.12.0 / 動的）

**スキップ条件**（いずれか満たせばこのフェーズ全体をスキップして Step 4.6 へ）:
- userConfig `enable_adaptive_rounds` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `low` または `medium`
- 全 reviewer の出力に `## unmet_information` セクションが 1 件もない

**実行する場合**: orchestration-guide `## 6` の手順に従う（unmet_information 集約 → 追加 explorer 最大 3 体 → 該当 reviewer 再起動 → 初回出力を置換。失敗時は初回結果のまま続行の best-effort）。レポートに「Round 2 trigger: <reason>」を記録（Step 6 で出力）。

### 4.6 Meta-reviewer ラウンド（v2.12.0 / 動的）

**スキップ条件**（いずれか満たせばスキップして Step 5 へ）:
- userConfig `enable_meta_reviewer` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `xhigh` または `max` **でない**
- Step 4.5 後の全指摘（フィルタリング前）に **BLOCKER も CRITICAL も 1 件もない**

**実行する場合**: orchestration-guide `## 7` の手順に従う（meta-reviewer を 1 体 `model: opus`, `effort: max` で起動 → 追加指摘を dedup して統合。失敗時は missing_coverage に追記して続行）。

### 4.7 観点カバレッジ・セルフチェック（メインコンテキスト / 常時実行）

Step 5 の直前に、**メインコンテキストで**（Agent は使わない・低コスト）起動 focus の妥当性を 1 回検査する。観点漏れは高 severity 指摘が無くても起こりうるため、meta-reviewer (4.6) の起動有無・effort・severity に依存せず **常時実行** する（GitHub issue #69）。

手順の詳細（観点判定表の再評価 → 未起動 focus 検出 → missing_coverage 追記 → high 以上での補完起動）: → orchestration-guide `## 8`

**スキップ条件**: `--focus` / `--exclude` 指定時は意図的にスコープを絞り込んでいるため、その範囲外の観点漏れは missing_coverage に記録するのみで追加起動はしない。

### 4.8 冷や読み skeptic ラウンド（recall 補強 / 動的）

観点カバレッジ self-check の後・反証レイヤーの前に、**high-risk surface を含む変更に限り**、reviewer の findings も推論も渡さない独立 skeptic を 1 体起動し、fleet 共通の盲点（層跨ぎ値フロー等）を冷や読みで探す（`${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` `## 8.5 冷や読み skeptic ラウンド`）。反証レイヤー(4.9)が偽陽性を潰す係なのに対し、本フェーズは見落とし（false negative）を独立読み直しで足す係。self-review は PR を持たないため surface 判定は diff 正規表現 + reviewer の `[surface:high-risk]` フラグで行う（PR 自己申告 D1-High は無い）。

**スキップ条件**（いずれか満たせばスキップして 4.9 へ）:
- userConfig `enable_recall_skeptic` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `xhigh` または `max` **でない**（high 既定は当面スキップ、計測後に昇格を検討＝既存 4.6/4.9 と対称の fail-safe）
- `--focus` / `--exclude` でスコープを絞り込んでいる
- high-risk surface（triage-guide.md `## 8.5` の surface 判定）を含まない

**スキップ時も surface 判定は必ず実施（silent skip 防止・issue #85）**: 上記スキップ条件（effort / config / scope）に該当して skeptic agent を起動しない場合でも、surface 判定（triage-guide.md `## 8.5` の正規表現。diff への grep で安価）だけは Phase 0 の構成判断（縮退構成・小 diff）と **独立に必ず実施** する。surface=true なら skeptic 未起動の事実と skip_reason（`effort` / `config` / `scope`）を Step 6 レポートの「動的ラウンド」行に必ず出す（`--embed` の有無に依存しない human レポート契約。JSON payload の `recall_skeptic` 記録と対を成す）。

**実行する場合**: orchestration-guide `## 9` の手順に従う（surface 判定 → skeptic を 1 体 `model: opus`, `effort: max` で起動。**findings / reviewer の推論は渡さない**のが独立性の核 → `[recall-skeptic]` タグ付き指摘を dedup して統合し、反証レイヤー(4.9)の対象にも含める）。

**失敗時 / スキップ時**: skeptic の失敗は `missing_coverage` に追記して続行。**起動条件（high-risk surface）を満たしたのに未実行だった事実は、失敗・effort/config/scope スキップのいずれでも Step 6 レポートに必ず出す**（silent skip で「守ったつもり」の偽の安心を防ぐ）。

### 4.9 反証レイヤー（adversarial verification / 動的）

冷や読み skeptic の後・スコアリングの前に、reviewer の指摘を独立エージェントが反証する。偽陽性を先回りして摘出するフェーズ（`${CLAUDE_PLUGIN_ROOT}/references/triage-guide.md` `## 9 反証レイヤー`）。meta-reviewer (4.6) / skeptic (4.8) が見落とし（false negative）を足す係なのに対し、本フェーズは偽陽性を独立に潰す鏡像。skeptic が足した指摘も本レイヤーの対象。

**スキップ条件**（いずれか満たせばスキップして Step 5 へ）:
- userConfig `enable_adversarial_verify` が `false`
- 実行時 effort = `${CLAUDE_EFFORT}` が `low` または `medium`
- `--focus` / `--exclude` でスコープを絞り込んでいる（既検証の再評価を避ける）
- 反証対象（triage-guide.md `## 9` のゲート）に合致する指摘が 0 件

**実行する場合**: orchestration-guide `## 10` の手順に従う（triage-guide `## 9` の選定ルールで対象を選び、反証エージェントを `model: opus`, `effort: max` で並列起動。**reviewer の理由文は渡さない**＝アンカリング防止 → verdict を Step 5 のスコアリングに渡す。失敗した指摘は verdict なしのまま続行の best-effort）。レポートに「反証: 対象 N 件 / 係争 M 件 / 取り下げ K 件」を記録（Step 6 で出力）。

### 5. スコアリングとフィルタリング（2軸: confidence × severity）

全 reviewer の指摘を統合し、`${CLAUDE_PLUGIN_ROOT}/references/scoring-guide.md` を Read で読み込んでスコアリングを実施する。

1. **各指摘の base confidence と severity を取得**
   - reviewer 出力の `[confidence: XX]` と `[severity: BLOCKER|CRITICAL|MAJOR|MINOR]` をパース
   - severity が欠落している指摘は **CRITICAL とみなす**（後方互換 / 安全側デフォルト）
2. **反証 verdict の反映**（Phase 4.9 が動いた場合のみ。scoring-guide.md `## 反証レイヤーの verdict 反映` に従う）
   - **BLOCKER / CRITICAL の `refuted` は confidence / severity を据え置き**、指摘本文先頭に `⚠️ 反証メモ: <軸>（<根拠 file:line>、要確認）` を付与（**報告から消さない**）
   - **MAJOR / MINOR の `refuted`** は confidence −40（取り下げ理由を付録に記録）、`confirmed` は既存「複数エージェント +15」の発火源（二重計上しない）、`uncertain` は −10
   - verdict が無い指摘（対象外・反証失敗）は no-op
3. **confidence への加算・減算ルールを適用**して 0-100 にクランプ
4. **severity 調整**: `[scope:out]` / `[resolved: ...]` タグ付きは severity を 1 段階下げる（self-review では PR タグは通常出ない。反証 `severity-inflated` もこのルールに統合し二重降格しない）
5. **報告マトリクスでフィルタ**:

   | severity \ confidence | <60 | 60-79 | 80-94 | 95+ |
   |---|:---:|:---:|:---:|:---:|
   | BLOCKER | skip | 報告 | 報告 | 報告 |
   | CRITICAL | skip | skip | 報告 | 報告 |
   | MAJOR | skip | skip | skip | 報告 |
   | MINOR | skip | skip | skip | 報告 |

6. **userConfig 適用**: `review_severity_threshold` (default: `MAJOR`) より低い severity は除外

### 6. レポート出力

`missing_coverage` リストが空でない場合は「⚠️ 欠損観点」セクションを追加する（空なら省略）。

**冷や読み skeptic の観測可能性（issue #85）**: high-risk surface を含む変更では、冷や読み skeptic（Phase 4.8）の起動有無を「動的ラウンド」行に **必ず** 出す（起動＝追加件数 / 未起動＝skip 理由）。surface HIT かつ未起動の silent skip を作らない。

**skeptic 由来の帰属をレポートまで保つ（`findings_added` の計測妥当性）**: Phase 4.8 の skeptic 指摘に付いた由来タグは、**レポート本文の指摘行にもそのまま残す**（`[confidence][severity]` の後・カテゴリの前に置く）。タグを落とすと **Step 6.4** の publish 時点で由来を再構成できず、`findings_added` が記憶頼みになって系統的に 0 へ潰れる（＝ skeptic の価値率が実態より低く出る）。**由来タグはレポート契約の一部**であり、任意の装飾ではない。

タグは 2 種（正本: orchestration-guide `## 9`）。**重複の有無で意味が正反対**になるため混ぜない:

- `[recall-skeptic]` — skeptic 単独由来（reviewer 指摘と重複しなかった）。**fleet 共通盲点を実際に破った＝ skeptic の価値**
- `[recall-skeptic:dup]` — 重複 survivor（reviewer も到達していた）。独立到達の記録としては残すが**盲点でなかった事例で recall の足し前はゼロ**

```
## セルフレビュー結果

**総合判定**: {Approve | Approve with nits | Needs work}（scoring-guide.md「レビュー結論（総合判定）」の表に従う。コミット前ゲートとして「このままコミットしてよいか」の指針）
**総合評価**: X/10 点
**レビュー構成**: Phase 0 (triage) → 探索 (N 起動 / M 成功) → レビュー (N 起動 / M 成功)
**動的ラウンド**: Round 2 探索 N 体起動 / Meta-reviewer {実行 | スキップ理由} / 冷や読み skeptic {実行（N 件追加）| skip（理由: effort/config/scope）| 非該当（surface なし）} / 反証 {対象 N 件 | スキップ理由}
**指摘件数**: BLOCKER N 件 / CRITICAL N 件 / MAJOR N 件 / MINOR N 件
**反証**: 対象 N 件 / 係争 M 件（BLOCKER/CRITICAL、本文に反証メモ）/ 取り下げ K 件（MAJOR以下、付録に理由）{反証スキップ時はこの行を省略}

### 🚨 BLOCKER 指摘

1. [confidence: 70][severity: BLOCKER][セキュリティ] Hardcoded secret の疑い
   ファイル: src/config.ts:15
   影響: コミット時にシークレット漏洩

### ⚠️ CRITICAL 指摘

2. [confidence: 95][severity: CRITICAL][バグ] Missing null check
   ファイル: src/utils.ts:42
   影響: 特定入力で関数が落ちる

3. [confidence: 85][severity: CRITICAL][recall-skeptic][バグ] 空文字の draft が numeric 列へ素通りする
   ファイル: src/repo.ts:88
   影響: 22P02 で INSERT が落ちる
   {由来タグ: skeptic 単独由来は `[recall-skeptic]` / reviewer と重複した survivor は `[recall-skeptic:dup]`。Step 6.4 の publish で `findings_added` / `findings_overlap` を数える唯一の根拠なので落とさない。番号は他の指摘と通し連番にする}

### 📋 MAJOR 指摘

4. [confidence: 95][severity: MAJOR][設計] ...

### ⚠️ 欠損観点（Agent 失敗による未カバー領域）
- reviewer-security: ネットワーク I/O エラーで失敗 → 認証まわりの観点は未検査
- explorer-<focus>: timeout → 依存していた reviewer-<focus> には探索結果なしで実行

### 🔁 反証で取り下げた指摘（参考・人間が覆せる）
{反証レイヤーが MAJOR/MINOR を refuted で取り下げた場合のみ。0 件なら省略}
- [取り下げ前: confidence XX / severity MAJOR] xxx の指摘
  ファイル: path/to/file:行番号
  取り下げ理由: <軸>（反証根拠 file:line）
  ※ 反証が誤りと思えばこの指摘は有効。再評価してよい

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
  "{\"pr\":\"local\",\"blocker_count\":<n>,\"critical_count\":<n>,\"major_count\":<n>,\"minor_count\":<n>,\"missing_coverage\":[<json-array of focus names>],\"result_grid\":{\"high\":<n>,\"medium\":<n>,\"low\":<n>,\"skip\":<n>,\"error\":<n>},\"adversarial_verify\":{\"confirmed\":<n>,\"refuted\":<n>,\"uncertain\":<n>,\"contested\":<n>},\"recall_skeptic\":{\"attribution_schema\":2,\"surface\":<bool>,\"fired\":<bool>,\"skip_reason\":<string|null>,\"findings_added\":<n>,\"findings_overlap\":<n>}}"
```

payload 規約（review skill と同一。subscriber が publisher を区別せず集計できるよう揃える）:
- `pr`: self-review は常に `"local"`
- `blocker_count` / `critical_count` / `major_count` / `minor_count`: severity 別件数（Step 6 報告マトリクス通過後）
- `missing_coverage`: 欠損観点の focus 名配列（空なら `[]`）
- `result_grid`: `high`=BLOCKER+CRITICAL / `medium`=MAJOR / `low`=MINOR / `skip`=severity フィルタ除外件数 / `error`=Agent 失敗数（`missing_coverage` の length と一致）
- `adversarial_verify`: 反証レイヤー（Phase 4.9）の verdict 集計（`confirmed` / `refuted` / `uncertain` / `contested`=高 severity の係争件数）。反証スキップ時は全 0。**review skill と同一フィールド名**（subscriber が publisher を区別せず偽却下率を集計できるよう揃える）
- `recall_skeptic`: 冷や読み skeptic（Phase 4.8）の実行記録（review skill と同一フィールド名）。skeptic の high 昇格判断の計測データ:
  - `surface`: high-risk surface 判定の結果（bool）。**Phase 4.8 が effort / userConfig でスキップされた場合も、正規表現部分の surface 判定（triage-guide.md `## 8.5`。diff への grep で安価）だけは payload 構築時に必ず実施して記録する**
  - `fired`: skeptic agent が実際に起動したか（bool）
  - `skip_reason`: `fired=false` のときの理由。`"effort"` / `"config"` / `"no-surface"` / `"scope"`（`--focus`/`--exclude` 指定）のいずれか。`fired=true` なら `null`
  - `attribution_schema`: 由来帰属の規約バージョン。**常に `2` を入れる**（2 = 由来タグがレポート書式に規定され dedup のタグ生存も定義された版 = 2.35.1 以降）。マーカー無しの旧サンプルは `findings_added` が信用できないため下流の集計は本フィールドで濾す（triage-guide `## 8.5`）。日付では切れない（配布ラグで未更新マシンが修正日以降も schema 1 を publish するため）
  - `findings_added`: **skeptic 単独由来**（`[recall-skeptic]` タグ。reviewer 指摘と重複しなかった）の指摘のうち報告マトリクスを通過した件数。**「動的ラウンド」行の `実行（N 件追加）` の N と同値**（本文確定後に数えてヘッダへ反映する。二重管理にしない）。**skeptic の価値率の分子はこれのみ**（重複分は `findings_overlap` へ。混ぜると重複が常態のため価値率が 100% に張り付き、縮小分岐が原理的に発火しなくなる）
  - `findings_overlap`: **重複 survivor**（`[recall-skeptic:dup]` タグ）の件数。独立到達の記録として残すが**価値率には算入しない**
  - 両フィールドとも **Step 6 で出力したレポート本文のタグ付き指摘を数えて求める**（Phase 4.8 の記憶から再構成しない。記憶依存にすると系統的に 0 へ潰れる）。計測点は報告マトリクス通過時点
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
- **反証レイヤー（Phase 4.9）の効果は `severity` / `confidence` に反映済み**（Step 5 で verdict 反映を適用してから報告するため、JSON には最終値が入る）。`refuted` で取り下げた MAJOR/MINOR は findings に含まれない。**係争中の BLOCKER/CRITICAL は通常通り findings に残り、`title` または `impact` に `⚠️ 反証メモ:` を含める**（schema_version は据え置き 1。新フィールドは追加しない＝consumer 後方互換）
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

**訂正の伝播前ガード（over-correction 防止 / GitHub issue #71）**: findings をコード/文書本文に**反映する前に**、その修正が依拠する load-bearing な事実主張を一次ソースで再確認する。判定ルール（repo で確認できる/できない主張の扱い・暫定入力の非伝播・1 箇所先行確認・複数観点の独立一致）の詳細: → orchestration-guide `## 12`

**修正の指針（Fix the code, not the reviewer）**: 「分かりにくい」「誤解を招く」「意図が読めない」系の指摘に対しては、説明コメントを足して取り繕うのではなく、**コード・命名・型・構造そのものを直して解消する**ことを優先する。将来の読み手（半年後の自分・別コンテキストの Claude）も同じ箇所でつまずくため（Google eng-practices "Handling reviewer comments: fix the code, not the reviewer"）。
