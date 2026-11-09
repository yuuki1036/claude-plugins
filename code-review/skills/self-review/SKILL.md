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
  - Write
  - Edit
  - Agent
  - AskUserQuestion
  - Skill
---

# Self Review

> **各 Step の手順は Step ごとのファイルにある**（`skills/self-review/references/step-<番号>.md`）。Step の見出しに来たら Read の行が指すファイルを最初に読み、スキップの条件もそのファイルで判定する。読んだら手順を終え、SKILL.md に戻ってファイル末尾の「次は」が指す Step の見出しへ進む（本文の分岐が戻り先を書いている回はそちらに従う）。見出しだけを見て、本文を読まずに進めない（Step 6 の定型と 6.4 の publish を読まずに締めた回は定型を出さなかった / GitHub issue #250・#426）。Step ファイルの中の `${CLAUDE_PLUGIN_ROOT}` は、この SKILL.md を Read したパスのプラグインのルートに読み替える

## review との違い

- PR 不要。ローカルのみで完結
- コミット前・PR 作成前の品質ゲートとして使用
- **コメント推敲（B 系統）を出すのは self-review だけ**（v2.45.0）。diff で追加・変更したコメントを**コードコメント規約の 2 観点**（正本: `.claude-plugin/lib/comment-rule.md` / 連結先の複製: `${CLAUDE_PLUGIN_ROOT}/references/prompts/focus/comment-polish.md`）で推敲し、severity マトリクスを通さない別枠セクションに before→after で出す。他人の PR に文面の推敲を投稿するのは越権になりやすいため review 側には入れない（**観点をここに書き下ろさない** — 軸の複製が増えると「2 観点のみ」が崩れる）
- **Markdown 推敲を出すのも self-review だけ**（v2.131.0 / GitHub issue #243）。diff で追加・変更した md の散文を writing-polish（未導入なら skip）に通す推敲 agent を reviewer wave に 1 体足し、B 系統と同じく severity マトリクスの外に before→after で出す。review に入れない理由は B 系統と同じ。起動条件・結果の扱い・適用の正本は `${CLAUDE_PLUGIN_ROOT}/references/md-polish-guide.md`（**推敲の基準はここにも guide にも書かない** — writing-polish の規約が正本）

## コスト×精度パイプライン設計（採用/不採用）

ルート CLAUDE.md「コスト×精度パイプライン設計指針」の 10 原則のうち **採用: 1（ファネル = Phase 0 triage で高コスト reviewer を通過分に絞る）/ 2（2 軸スコア化 = confidence × severity マトリクス。**ただしコメント推敲（B 系統）と Markdown 推敲は 2 軸を持たずマトリクスを通さない別枠経路** / v2.45.0・v2.131.0）/ 3（段階予算 = `${CLAUDE_EFFORT}` → explorer/reviewer 体数）/ 4（モデルルーティング = explorer:sonnet / reviewer:opus / meta:opus / 反証:opus / Markdown 推敲:opus）/ 7（敵対的独立検証 = Phase 4.9 反証レイヤー、recall 側は Phase 4.8 冷や読み skeptic）/ 8（外部オラクル = Step 1.7 の機械層先行実行。**プロジェクトが `.claude/review-oracles.sh` で宣言したときのみ**。宣言が無ければ no-op で、コマンドはプラグイン側で推測しない / v2.69.0・ADR-20260817170000）**。**捨てた**: 5（暴走ガード）は反復・起票を持たない単発レビューのため不要、6（証拠ラダー）は指摘蓄積・昇格の責務を failure-journal に委ねた。

## 設計原則: Generator と分離された Evaluator

self-review は `dev-workflow:git-commit-helper`（Generator: 変更を生成・コミットする側）から独立した Evaluator として機能する。同一コンテキストで生成と判定を行うと confirmation bias で見落としが増えるため、以下のフローを推奨する:

1. 実装・変更 → `/self-review` （別コンテキストで起動）
2. 指摘事項を修正
3. `/git-commit-helper` でコミット

Phase 0 の explorer/reviewer 並列起動も同じ思想で、reviewer は explorer の結果を「独立した観点として」受け取る（自分で diff を再探索させない）。

## 前提

- **effort のつまみは 2 つあり、別物**（GitHub issue #106）:
  - **skill frontmatter の `effort`** — オーケストレーター（メインループ）専用。**reviewer にも動的ラウンドにも効かない**
  - **実行時 `${CLAUDE_EFFORT}`** — reviewer / specialist の effort と、動的ラウンド（meta-reviewer / 冷や読み skeptic / 反証ゲート / Round 2 の段数）の**起動条件を支配する**（正本: orchestration-guide.md `## 5`）

## 実行手順

実行フェーズの共通詳細の正本:
→ Read `${CLAUDE_PLUGIN_ROOT}/references/orchestration-guide.md`（以下「orchestration-guide」）

**orchestration-guide は分冊されている。冒頭の「この分割の読み方」に従い、必要になった分冊だけをその時点で Read する**（条件付きフェーズを全部スキップするなら分冊は読まない）:

| 分冊 | Read するタイミング |
|---|---|
| `orchestration-dynamic-rounds.md` | 動的ラウンド（Round 2 / meta-reviewer / skeptic / 反証）の**いずれかを実行すると決まったとき** |
| `orchestration-measurement.md` | **publish の直前**（Step 6.4） |
| `orchestration-optional-flows.md` | Issue 必読 / Vault 照合 / 訂正の伝播前ガード / embed mode の**適用条件を満たしたとき** |
| `md-polish-guide.md` | Markdown 推敲を**起動すると決まったとき**（Step 2。self-review 限定） |
| `design-review-guide.md` | ダイジェストの `## decision-docs` に**doc の行があるとき**（Step 2。決定系 doc の design-review 委譲） |

同じく `triage-guide.md` も Phase 0 用の中核だけを持ち、動的ラウンドの起動ゲートは `triage-dynamic-gates.md` にある（**起動可否を判断する段で Read する**）。

self-review では `isolation: "worktree"` を使わない等の差分は orchestration-guide `## 0` を参照。

### 1. diff 収集とコンテキスト準備

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-1.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 1.4 直近レビューとの重複検出（skill 跨ぎ / 常時実行・agent なし。`--embed` ではスキップ）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-1.4.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 1.5 Vault 照合（過去の指摘・落とし穴の retrieval / 任意・後方互換）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-1.5.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 1.7 機械層の先行実行（原則 8 / `.claude/review-oracles.sh` を置いたプロジェクトのみ・`--embed` では skip）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-1.7.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 2. Phase 0: トリアージ

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-2.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 3. 探索フェーズ（explorer 並列起動）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-3.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 3.9 AGENTS.md 階層動的選択（reviewer 起動前）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-3.9.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 4. レビューフェーズ（reviewer 並列起動）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-4.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 4.5 Adaptive deepening: Round 2（unmet_information 起点 / 動的）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-4.5.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

Step 4.5 の後は実行順に 4.8 → 4.6 + 4.9（同じメッセージで発行）→ 4.7 と並べている（番号の順ではない）。

### 4.8 冷や読み skeptic ラウンド（recall 補強 / 動的）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-4.8.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 4.6 Meta-reviewer ラウンド（v2.12.0 / 動的・**4.9 反証と同一 wave**。実行順は `4.5 → 4.8 の skeptic 統合 → 4.6 meta + 4.9 反証を同一メッセージで一括発行 → mark wave → [meta 由来の追加反証バッチ] → 4.7 → Step 5`。両者は互いの出力に依存しないので直列に置かない / **片方がスキップでも他方はそのまま発行する** / #122）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-4.6.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 4.9 反証レイヤー（adversarial verification / 動的・**meta-reviewer(4.6) と同一 wave**）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-4.9.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 4.7 観点カバレッジ・事後突合（メインコンテキスト / 常時実行・agent 追加起動なし）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-4.7.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 5. スコアリングとフィルタリング（2軸: confidence × severity）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-5.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 6. レポート出力

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-6.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 6.4. Event Bus publish（`review:completed` / 計測用）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-6.4.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 6.5. 構造化 findings JSON（embed mode のみ）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-6.5.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 7. 修正方針の確認

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-7.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 8. worktree teardown 連携（非 embed のみ）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/self-review/references/step-8.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。
