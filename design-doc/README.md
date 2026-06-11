# design-doc

技術設計書 (design doc / RFC 相当) を**実装に入らず**作成・永続化するプラグイン。grill で前提を確定し、代替案のトレードオフ比較から採用案を `.claude/designs/` に保存する。実装ブリッジ (Implementation Bridge) セクションの必須化と supersede の機械化で死に文書化を防ぐ。

## 使い方

```
/design-doc 決済リトライ基盤の設計      # 新規作成（grill → 代替案比較 → 永続化）
/design-doc list                        # 一覧表示（id 降順）
/design-doc supersede <old-id> <title>  # 方式転換（旧 doc は superseded として残す）
/design-doc export title=... content=... # 他プラグイン連携用の非対話書き出し
/design-review [doc-id] [--focus <視点>] # 複数視点の静的レビュー（実装前の品質ゲート）
```

自然言語でも起動する: 「設計書作って」「実装せず設計だけ詰めたい」「設計書をレビュー」など。

### design-review（v0.2.0+）

design doc を minimal（過剰設計）/ clean（構造・責務）/ pragmatic（実装可能性）/ risk（障害モード）の 4 視点で静的レビューする。doc の前提はコードベースと突き合わせて裏取りし（evidence-first）、severity 付き findings を集約 → 採用分を doc に反映（open 追記・設計判断ログ追記・本文修正）する。

視点構成は実行時 effort で変わる: low/medium → メインコンテキストで 2 視点（minimal + risk）、high → design-reviewer agent ×3 並列、xhigh/max → ×4 並列。`--focus` で単一視点に絞れる。

## 成果物

`.claude/designs/<YYYYMMDD>-<kebab-slug>.md`（committed 前提）

```yaml
---
id: 20260611-payment-retry-architecture
title: 決済リトライ基盤の設計
status: draft            # draft | approved | superseded（合意状態）
phase: target            # target(未実装) → current(実装済) → superseded（ライフサイクル）
last-validated: 2026-06-11
supersedes: []
superseded-by: null
issue: null              # 関連 Issue
spec: null               # bdd-spec の spec.md パス
adrs: []                 # 切り出した ADR id
tags: []
---
```

本文 10 セクション: TL;DR / 背景・課題 / ゴール・非ゴール / 確定した前提 / 採用案 / 検討した代替案 / 設計判断ログ（`[→ADR候補]` / `[local]` マーカー必須）/ 未解決事項 (open) / **実装ブリッジ（空欄禁止）** / 関連。

## 隣接プラグインとの棲み分け

| プラグイン | 境界 |
|---|---|
| `indie-workflow:issue-design` | Issue = タスク 1 件の作業設計。design doc = **タスクを跨ぐ技術設計**（複数 Issue に分解される粒度） |
| `bdd-spec` | spec.md = WHAT（振る舞い仕様）。design doc = **HOW**（実現方式）。spec があれば入力として読むだけで Scenario は生成しない |
| `adr-keeper` | ADR = 単一決定の WHY を**点**で記録。design doc = 設計全体を**面**で記述。`[→ADR候補]` から切り出して相互リンク |
| `feature-dev` | feature-dev = 設計 + 実装の一気通貫。design-doc = **実装フェーズを持たない**（Write 先は `.claude/designs/` のみ） |
| `doc-freshness` | 鮮度 lint は doc-freshness に委譲（frontmatter 互換）。本プラグインは作成・命名・supersede 整合のみ |

## dormant 連携（すべて optional、未インストールでも完全動作）

| 相手 | 内容 | 未インストール時 |
|---|---|---|
| bdd-spec | spec.md を WHAT 入力に。無ければ作成を提案（非対話 API 呼び出し） | 会話文脈から要求を grill |
| adr-keeper | `[→ADR候補]` を ADR として切り出し + 相互リンク | マーカーを doc に残すのみ |
| writing-polish | 提示直前に散文を `--embed --tone rfc` で推敲 | 推敲なしで提示 |

## export 非対話 API（他プラグインからの呼び出し）

`Skill design-doc:design-doc` に `mode=export title=... content=...` を渡すと、grill / 設計フェーズを skip して doc 化のみ実行する（AskUserQuestion 不発火）。feature-dev Phase 4 の architect 出力（揮発するトレードオフ比較）の永続化先を想定。

## 設計判断

- **hook は持たない**: superseded doc への Edit 警告等の hook は需要が顕在化してから（component-addition-advisor の退路確保原則）
- **作成時は agent を使わない**: design-doc スキルの設計フェーズは単一コンテキストの軽量版。多視点が必要になるのはレビュー時で、そこは design-review が担う。広範な探索が必要なら feature-dev を案内する
- **レビューは再設計ではない**: design-reviewer は findings を返すだけで代替設計を書かない（Generator と Evaluator の分離）
- **ファイル名は日付精度 + slug**: ADR の秒精度と違い、design doc は機能名で参照される面記録なので可読 slug を主キーにする
- **`phase: target` の間は生きた文書**: append-only 原則が禁じるのは supersede 時の旧 doc 削除であって日常の編集ではない。方式転換だけ supersede にする（基準は `references/naming.md`）
- **grill-protocol.md は feature-dev 正本の byte-identical 複製**: プラグイン間依存禁止のため（safe-hook.sh と同じ運用）

## 構成

| 種別 | 名前 | 説明 |
|------|------|------|
| コマンド | `/design-doc` | new / list / supersede / export |
| コマンド | `/design-review` | doc の複数視点静的レビュー |
| スキル | `design-doc` | grill → 代替案比較 → 永続化 → ADR 切り出しのロジック |
| スキル | `design-review` | 視点トリアージ → 並列レビュー → findings 集約 → doc 反映 |
| エージェント | `design-reviewer` | 1 視点担当の静的レビュアー（evidence-first、read-only） |
