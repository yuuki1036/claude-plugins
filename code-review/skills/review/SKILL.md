---
name: review
description: >
  Phase 0 トリアージ + 動的エージェント構成の PR コードレビュー。
  diff → explorer(sonnet) → reviewer(opus) を動的構成、severity×confidence マトリクスでフィルタ。
  トリガー: 「レビューして」「/review」「コードレビュー」
  引数: [PR番号] [--emergency] (省略時は現在ブランチのPRを自動取得。--emergency は本番ホットフィックス向けの最小構成レビュー)
effort: high
allowed-tools:
  - Bash
  - Read
  - Write
  - Agent
  - EnterWorktree
  - ExitWorktree
  - AskUserQuestion
  - Skill
---

<!-- 正本依存（SSoT pin）。「前提」の節の effort の 2 つのつまみ（frontmatter の effort と実行時の `${CLAUDE_EFFORT}`）の説明は orchestration-guide.md `## 5` の effort 設計意図を要約したもの。正本が変わったら「前提」を確認して pin を打ち直す。
同じ箇所の「規模キャップが先に効くと体数が変わらない」は triage-guide.md `## 7` の実効上限（effort 上限と規模キャップの小さい方）を言い換えたもの -->
<!-- SSOT: code-review/references/orchestration-guide.md#5 @88f608c4 -->
<!-- SSOT: code-review/references/triage-guide.md#7 @d465ee72 -->

# Review

> **各 Step の手順は Step ごとのファイルにある**（`skills/review/references/step-<番号>.md`）。Step の見出しに来たら Read の行が指すファイルを最初に読み、スキップの条件もそのファイルで判定する。読んだら手順を終え、SKILL.md に戻ってファイル末尾の「次は」が指す Step の見出しへ進む（本文の分岐が戻り先を書いている回はそちらに従う）。見出しだけを見て、本文を読まずに進めない（Step 7 のレポートの定型を読まないまま締めた回は定型を出さなかった / GitHub issue #250・#447）。Step ファイルの中の `${CLAUDE_PLUGIN_ROOT}` は、この SKILL.md を Read したパスのプラグインのルートに読み替える

## 前提

- 現在のブランチに PR が存在すること（PR がなければ終了）
- 実行時 effort = `${CLAUDE_EFFORT}` を Phase 3 / 4 の reviewer 構成に反映する（後述の Phase 3 / 4 を参照）
- **effort のつまみは 2 つあり、別物**（GitHub issue #106）:
  - **skill frontmatter の `effort`** — オーケストレーター（メインループ）専用。**reviewer にも動的ラウンドにも効かない**
  - **実行時 `${CLAUDE_EFFORT}`** — reviewer / specialist の effort と、動的ラウンド（meta-reviewer / 冷や読み skeptic / 反証ゲート / Round 2 の段数）の**起動条件を支配する**
  - frontmatter を見て「high 運用のつもり」でいると、セッション effort が xhigh のときに meta-reviewer・skeptic・反証の拡大が全部走ってコストが想定と食い違う。**規模キャップが先に効くケースでは体数が変わらないぶん気づきにくい**（正本: effort の役割は orchestration-guide.md `## 5`、
    実効上限が effort 上限と規模キャップの小さい方になることは triage-guide.md `## 7`）

## コスト×精度パイプライン設計（採用/不採用）

ルート CLAUDE.md「コスト×精度パイプライン設計指針」の 10 原則のうち **採用: 1（ファネル = Phase 0 triage で高コスト reviewer を通過分に絞る）/ 2（2 軸スコア化 = confidence × severity マトリクス）/ 3（段階予算 = `${CLAUDE_EFFORT}` → explorer/reviewer 体数）/ 4（モデルルーティング = explorer:sonnet / reviewer:opus / meta:opus / 反証:opus）/ 7（敵対的独立検証 = Phase 5.9 反証レイヤー、recall 側は Phase 5.8 冷や読み skeptic）**。**捨てた**: 5（暴走ガード）は反復・起票を持たない単発レビューのため不要、6（証拠ラダー）は指摘蓄積・昇格の責務を failure-journal に委ね、8（外部オラクル）は PR diff レビューが対象で型/テスト実行は feature-dev Phase 5.3 の役割と分離した。

## 実行手順

実行フェーズの共通詳細の正本 → Read `${CLAUDE_PLUGIN_ROOT}/references/orchestration-guide.md`（以下「orchestration-guide」）

**分冊されている。必要になった分冊だけをその時点で Read する**（全スキップなら読まない）:

| 分冊 | Read するタイミング |
|---|---|
| `orchestration-dynamic-rounds.md` | 動的ラウンド（Round 2 / meta-reviewer / skeptic / 反証）の**いずれかを実行すると決まったとき** |
| `orchestration-measurement.md` | **publish の直前**（締めフロー 4） |
| `orchestration-optional-flows.md` | Issue 必読 / Vault 照合 / 訂正の伝播前ガード / embed mode の**適用条件を満たしたとき** |
| `design-review-guide.md` | ダイジェストの `## decision-docs` に**doc の行があるとき**（Step 3。決定系 doc の design-review 委譲） |

同じく `triage-guide.md` も Phase 0 用の中核だけを持ち、動的ラウンドの起動ゲートは `triage-dynamic-gates.md` にある（**起動可否を判断する段で Read する**）。

### 0. Worktree への移動

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review/references/step-0.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 1. PR の取得と前提確認

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review/references/step-1.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 2. diff の保存とシグナルダイジェストの取得

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review/references/step-2.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 2.4. 直近レビューとの重複検出（skill 跨ぎ / 常時実行・agent なし）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review/references/step-2.4.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 2.5. PR コンテキストの扱い

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review/references/step-2.5.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 2.6. Vault 照合（過去の指摘・落とし穴の retrieval / 任意・後方互換）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review/references/step-2.6.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 3. Phase 0: トリアージ

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review/references/step-3.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 4. 探索フェーズ（explorer 並列起動）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review/references/step-4.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 4.9 AGENTS.md 階層動的選択（reviewer 起動前）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review/references/step-4.9.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 5. レビューフェーズ（reviewer 並列起動）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review/references/step-5.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 5.5 Adaptive deepening: Round 2（unmet_information 起点 / 動的）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review/references/step-5.5.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

Step 5.5 の後は実行順に 5.8 → 5.6 + 5.9（同じメッセージで発行）→ 5.7 と並べている（番号の順ではない）。

### 5.8 冷や読み skeptic ラウンド（recall 補強 / 動的）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review/references/step-5.8.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 5.6 Meta-reviewer ラウンド（v2.12.0 / 動的・**5.9 反証と同一 wave**。実行順は `5.5 → 5.8 の skeptic 統合 → 5.6 meta + 5.9 反証を同一メッセージで一括発行 → mark wave → [meta 由来の追加反証バッチ] → 5.7 → Step 6`。両者は互いの出力に依存しないので直列に置かない / **片方がスキップでも他方はそのまま発行する** / #122）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review/references/step-5.6.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 5.9 反証レイヤー（adversarial verification / 動的・**meta-reviewer(5.6) と同一 wave**）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review/references/step-5.9.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 5.7 観点カバレッジ・事後突合（メインコンテキスト / 常時実行・agent 追加起動なし）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review/references/step-5.7.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 6. スコアリングとフィルタリング（2軸: confidence × severity）

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review/references/step-6.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。

### 7. レポート出力

入ったら最初に `${CLAUDE_PLUGIN_ROOT}/skills/review/references/step-7.md` を Read する（手順・分岐・次の Step はそのファイルにある。見出しだけで進めない）。
