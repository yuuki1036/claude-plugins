# code-review

Phase 0 トリアージ + 動的エージェント構成のコードレビュープラグイン。diff を分析して explorer（探索）→ reviewer（レビュー）を動的に構成し、対象コードの複雑さに応じて冗長化する。explorer: sonnet、reviewer: opus。各指摘に severity × confidence の 2 軸スコアを付与し、報告マトリクスでフィルタする。

## 含まれるスキル

### review

PR ベースのコードレビュー。PR が必須（`gh pr diff` で差分を取得）。

**トリガー**: 「レビューして」「/review」「コードレビュー」

**引数**:
- `[PR番号]` — 省略時は現在のブランチに紐づく PR を自動取得
- `--emergency` — 本番ホットフィックス向けの最小構成レビュー（reviewer-bugs + reviewer-security の 2 体のみ。explorer / 冗長ペア / 動的ラウンドをスキップ。レポート冒頭に「マージ後に通常の /review を実施」バナーを表示）

### self-review

セルフレビュー。PR 不要でコミット前・PR 作成前に自分の変更をチェックする。base branch からの全差分（コミット済み + 未コミット）が対象。

**トリガー**: 「セルフレビュー」「/self-review」「自分の変更を確認」「コミット前にチェック」

**引数**:
- `[base branch]` — 省略時は自動検出、不明なら確認
- `--staged` — ステージ済みの変更（`git diff --cached`）のみを対象にする
- `--focus <観点>` — レビュー対象を特定の観点に絞る（最小保証 reviewer も focus に含まれない限り起動しない。カンマ区切りで複数指定可）
- `--exclude <観点1,観点2>` — 同一セッションで既に検証済みの観点をスキップする
- `--embed` — 他 plugin からの呼び出し用。終端の修正方針確認 AskUserQuestion を skip し、レポート + 機械可読 findings JSON を return する（feature-dev Phase 6 等で使用）

## 機械層の先行実行（self-review のみ / opt-in）

**agent の担当を「機械が決められないもの」に限る**ための前段。プロジェクトのリポジトリルートに `.claude/review-oracles.sh` を置くと、self-review は Phase 0 の**前に**それを実行する。置かなければ何も起きない（完全 no-op）。

```bash
#!/usr/bin/env bash
# .claude/review-oracles.sh — 存在自体が宣言
# exit 0 = 緑 / 1 = 検出あり（stdout に内容）/ 2 = 判定不能（緑と区別される）
npm run lint && npm run typecheck && npm test
```

- **`red` でも自動停止はしない**。「直してから」「このまま続行」を確認する（機械層が赤くても設計レビューを先に受けたいことがある）
- **`timeout`（既定 300 秒）/ `error` は緑と区別**して欠測として扱う。倒すと「機械層が死んでいる」と「通っている」が区別できなくなる
- 続行時は出力を reviewer に「既知」として渡すが、抑制は **同一 file:line × 同一ルール**に限る（同じ箇所の別欠陥は報告させる）
- コマンドはプラグイン側で推測しない（`package.json` からの推測は誤検出時に任意コマンドの実行になる）

設計判断と撤回条件: `.claude/adr/20260817170000-machine-layer-before-self-review-agents.md` / 運用の正本: `references/machine-layer.md`

## レビュー構成

### Phase 0: トリアージ（メインコンテキスト）

diff の特性を分析し、エージェント構成を動的に決定する。

- **Stage 0**: PR 種別分岐（doc-only / migration / lockfile / generated code 等の特殊 PR を先に判定）
- **Stage 1**: タイプ判定（explorer が必要か、どの reviewer 観点が必要か）
- **Stage 2**: 体数・フォーカス・冗長度決定（体数上限は effort 適応。冗長ペアの実起動と specialist の個別起動は xhigh/max のみ、high 既定は縮小構成 + 観点バンドルで吸収し、収まらない観点は欠損観点としてレポートに明示）

危険パターン（インジェクション・破壊的操作・シークレット漏洩・信頼境界・ガードレール骨抜き）を検出すると、対応する specialist reviewer を自動起動する。

### 探索フェーズ: explorer（0-6 体 / high 既定は上限 4）

事実収集に特化。問題の判定は行わず、コードフロー・依存関係・副作用を構造化サマリとして収集する。

| focus | 役割 |
|-------|------|
| function-flow | 関数の全フロー追跡（分岐・副作用含む） |
| dependency-trace | import/依存関係の追跡 |
| branch-impact | 条件分岐の既存動作と新条件の影響調査 |
| history-context | git blame/履歴による文脈収集 |
| shared-module-impact | 共通モジュールの影響範囲調査 |

### レビューフェーズ: reviewer（2-10 体 / high 既定は上限 6・冗長ペアなし）

問題検出 + 2 軸スコアリング。explorer 結果を入力として活用する。

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
| ui-quality | UI/フロントエンドの変更時 |

React/Next.js プロジェクトでは ui-quality に modern-web-checklist の観点が自動追加される。

### 冗長化（同一観点の複数体起動）

対象コードの複雑さが高い場合、同一観点の reviewer を異なる angle（分析の切り口）で複数体起動し、複数視点のマージで確度を向上させる。

### 動的ラウンド（effort 適応）

- **Phase 5.5 Adaptive deepening**: reviewer の `unmet_information` 申告をトリガーに Round 2 を 1 回実行（high 既定は該当 reviewer 再起動のみの 1 段圧縮・再起動 reviewer が自力探索 / xhigh・max は追加 explorer → reviewer 再起動の 2 段）
- **Phase 5.6 Meta-reviewer**: BLOCKER / CRITICAL 検出時、または報告見込みの MAJOR が 3 件以上あるときに、他 reviewer の見落とし観点を探すメタレビューを 1 ラウンド実行（effort xhigh/max のみ）。**反証レイヤー (Phase 5.9) と同一 wave で発行**し、meta が足した指摘だけを上限 5 件の追加反証バッチに回す（v2.61.0）。MAJOR 経路は v2.62.0 で追加 — 高 severity の存在だけを条件にしていた旧ゲートは実測 14 件中 1 回しか起動せず、価値率を測るサンプルすら貯まらなかった

どちらも `plugin.json` の userConfig（`enable_adaptive_rounds` / `enable_meta_reviewer`）で無効化できる。

## severity × confidence の 2 軸スコアリング

各指摘に 2 つの独立した軸でスコアを付与し、その組み合わせで報告可否を決める。

- **confidence（確信度）** — 指摘が事実として正しい確率（0-100）。reviewer が diff・ファイル Read・explorer 結果でどれだけ裏付けられるか
- **severity（重大度）** — 指摘が当たっていた場合の影響の大きさ。BLOCKER / CRITICAL / MAJOR / MINOR の 4 段階

単一軸（confidence のみ）では「重大だが不確実」（race condition の疑い）と「軽微だが確実」（typo）を区別できなかった。2 軸化により、重大な疑いは不確実でも人間に届け、軽微な指摘はほぼ確実な時だけ出す非対称運用ができる。

### 報告マトリクス

| severity \ confidence | <60 | 60-79 | 80-94 | 95+ |
|---|:---:|:---:|:---:|:---:|
| **BLOCKER** | skip | 報告 | 報告 | 報告 |
| **CRITICAL** | skip | skip | 報告 | 報告 |
| **MAJOR** | skip | skip | skip | 報告 |
| **MINOR** | skip | skip | skip | 報告 |

- BLOCKER は confidence 60+ で報告（見落としの代償が大きいため不確実でも人間判断を促す）
- MAJOR / MINOR は confidence 95+ のみ報告（根拠の薄い nitpick を自動除外）

confidence は explorer の裏付け（+10）・冗長ペア合意（+10）・CLAUDE.md 記載（+20）等で加減算する。根拠が個人的好みのみの指摘は 40 で、repo で検証できない外部状態に依拠する指摘は 75 で上限クランプする。詳細は `references/scoring-guide.md` を参照。

### 総合判定

報告マトリクス通過後の残存指摘から、`Approve` / `Approve with nits` / `Needs work` を決定的に導出する（BLOCKER/CRITICAL 残 → Needs work、MAJOR/MINOR のみ → Approve with nits、ゼロ → Approve）。MINOR / nit の積み残しを理由に承認を保留しない。

### userConfig による閾値カスタマイズ

| キー | デフォルト | 説明 |
|------|-----------|------|
| `review_severity_threshold` | `MAJOR` | 報告対象の最低 severity（BLOCKER / CRITICAL / MAJOR / MINOR） |
| `review_confidence_threshold` | `80` | CRITICAL 以下の最低 confidence（後方互換のため残置） |
| `enable_adaptive_rounds` | `true` | Phase 5.5 Round 2（adaptive deepening）の有効化 |
| `enable_meta_reviewer` | `true` | Phase 5.6 meta-reviewer ラウンドの有効化 |

## Event Bus 連携

review / self-review は完了時に `review:completed` イベントを Event Bus（`.claude/events.jsonl`）に publish する。payload は `pr` / `missing_coverage` / `result_grid`（high/medium/low/skip/error の集計）等。後段の集計・PR コメント自動投稿の土台として使う。

### 振り返り集計（v2.62.0）

publish の直後に `scripts/review-retro.sh` が蓄積イベントを集計し、レポートの後ろに出す。effort × 規模帯の所要時間、体数と壁時計の相関、検出 → 報告の歩留まり、反証 verdict 分布、動的層の発火率、**トークン消費と体数の相関**（v2.65.0 / review のみ）、計測マーカーの欠測率を出し、**各層のロールバック条件・再監視条件に該当したときだけ ⚠️ シグナル行**を立てる。単体でも実行できる:

```bash
bash <plugin>/scripts/review-retro.sh              # 全期間 + 直近 30 日
bash <plugin>/scripts/review-retro.sh --last 20    # 直近 N 件
bash <plugin>/scripts/review-retro.sh --json       # 機械可読
bash <plugin>/scripts/review-retro.sh --logs ~/Projects/*/.claude/events.jsonl   # 複数リポジトリを合算
```

同一 diff への二重レビュー（self-review 直後に PR レビューを回す等）は `scripts/detect-recent-review.sh` が diff の内容ダイジェストで突合し、検出時に続行可否を確認する。
