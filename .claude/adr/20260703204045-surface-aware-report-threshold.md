---
id: 20260703204045
status: accepted
phase: current
last-validated: 2026-07-03
supersedes: [20260703155637]
superseded-by: null
append_only: true
tags: [code-review, scoring, recall, precision, high-risk-surface]
---

# ADR-20260703204045: high-risk surface に限り code-review の報告閾値を surface 単位で可変にする（surface 判定は新規実装で担保・改訂版）

## ステータス

accepted（2026-07-03）。[ADR-20260703155637](20260703155637-surface-aware-report-threshold.md) を supersede する。決定（surface-aware 閾値）は同一で、**Enforcement（surface 判定の担保方法）を訂正**するための改訂。

## コンテキスト / 背景

code-review の報告マトリクス（`scoring-guide.md`）は全 surface 一律で、CRITICAL は confidence 80+、MAJOR は 95+ を報告閾値とする precision 寄せの設計だった。この一律設計のもとで、xhigh フルパイプラインが high-risk な DB 書込 PR の実バグ（空文字が numeric 列へ INSERT され 500、GitHub issue #75 #1）を見落とした。high-risk surface（DB 書込 / 金銭計算 / 認可）では、CRITICAL 見落としのコストが nit 偽陽性のコストを大きく上回る。一方で全 surface で閾値を緩めると noise が爆発する。

**旧 ADR からの訂正点（F2）**: 旧 ADR-20260703155637 は Enforcement / 代替案却下理由で「surface 判定は既存の red-flag pattern（正規表現）+ PR コンテキスト検出で足りる」と述べていた。しかし design doc のレビュー（F2）で、既存 red-flag 正規表現（`triage-guide.md` §157）は `DROP TABLE` / `TRUNCATE` / `DELETE FROM .* WHERE` など**破壊的操作のみ**が対象で、#1 の対象である通常の `INSERT` / `UPDATE`（DB 書込）は specialist 自動起動対象に**含まれない**こと、「PR 自己申告 D1-High」の検出はコードベースに**存在しない**ことが判明した。よって surface 判定は「既存の再利用で足りる」のではなく**新規実装が要る**。

## 決定

報告閾値を surface 単位で可変にする。**high-risk surface（DB 書込 / 金銭計算 / 認可、または PR 自己申告 D1-High）に限り** CRITICAL 80→70 / MAJOR 95→85 に緩め、それ以外の surface は従来の precision 寄せ閾値を維持する。precision の本丸（`≤40 好みクランプ`・`高 severity 非削除`・`[unverified] min75`・`specialist 反証除外`）は不変で、surface-aware 緩和はその後段（報告可否の閾値＝適用順序 手順 7）にのみ効かせる。precision と recall を surface 単位で非対称に扱うことを code-review scoring の設計原則とする。

## 影響 (Consequences)

- **良い影響**: high-risk surface の recall が上がり、見落としコストが高い層で CRITICAL/MAJOR を拾える。低リスク surface の noise は据え置き。
- **悪い影響**: high-risk surface で偽陽性が増えうる。surface 判定ロジックの新規実装・保守コストが増える。
- **トレードオフ**: high-risk surface の recall と precision を天秤にかけ、見落としコストが偽陽性コストを上回る層に限って recall を優先する。増えた偽陽性は後段の反証レイヤー（Phase 5.9）が独立検証で吸収する二段構え。surface-aware で新規報告化する CRITICAL 70-79 / MAJOR 85-94 帯は high でも反証対象に含める例外ゲート（`triage-guide.md` §9）で吸収を成立させる。

## 適用方法 (Enforcement)

- **surface 判定は新規実装で担保する（訂正）**: 既存 red-flag 正規表現では通常の INSERT/UPDATE・D1-High を拾えないため、以下を新規実装する:
  1. **performance 観点の INSERT/UPDATE 正規表現を surface 判定に転用**（`triage-guide.md` §108 の既存正規表現を §8.5 surface 判定に流用）+ ORM 書込 API（`.create(` / `.update(` / `.save(` / `.upsert(` 等）
  2. **D1-High 検出を PR コンテキスト検出に新規追加**（`reviewer-prompts.md` §2.5 に `[surface:high-risk]` 検出ルールを追加。review skill のみ）
- **報告マトリクスのフィルタは機械強制**: surface フラグが立った指摘に緩和後の閾値を適用するのは `scoring-guide.md` 適用順序 手順 7 でオーケストレーターがコード分岐で決定的に適用する。
- **偽陰性の保険（reviewer フラグ）**: 正規表現は ORM 抽象の深い経由を取り逃しうるため、reviewer が focus 内で DB 書込 / 金 / 認可と判断したら `[surface:high-risk]` フラグを返す経路を OR で持つ。surface 偽陰性は recall 補強が丸ごと不発になるため網羅を正規表現に依存しきらない。
- **hook 昇格はしない**: surface の網羅は正規表現・LLM フラグの混成で例外が多く決定的判定に馴染まないため、判定フローは `triage-guide.md` の規約 + 正規表現 + reviewer フラグで担保し hook には昇格しない。
- **回帰検証**: #75 #1 を再現する fixture で、surface-aware 適用後に CRITICAL が報告されること（recall 回帰）、および既存の Fable 誤検出ケースが引き続き非報告になること（precision 回帰）を確認する。

## 検討した代替案

- **全 surface 一律で閾値を下げる**: recall は上がるが低リスク surface の noise が爆発し alert fatigue を招く。却下。
- **閾値は据え置き、meta-reviewer のゲートだけ変える**: meta-reviewer は findings 注入で非独立のため fleet 共通盲点を破れない。閾値問題と recall 機構問題は別で、閾値側の補正が必要。却下（機構側は独立 skeptic = Phase 5.8/4.8 で別途対応）。
- **surface 判定を専用の重い detector として新設**: performance 正規表現の転用 + D1-High 検出の追加 + reviewer フラグ保険で足り、専用 detector は往復コストを増やすだけ。却下（ただし「既存 red-flag で足りる」という旧 ADR の主張は F2 で誤りと判明したため、"最小の新規実装" に訂正）。

## 関連

- 関連 ADR: [ADR-20260703155637](20260703155637-surface-aware-report-threshold.md)（この ADR が supersede する旧版。Enforcement が「既存 red-flag で足りる」旧前提に依拠していた）
- 関連 Issue: [GitHub issue #75](https://github.com/yuuki1036/claude-plugins/issues/75)
- 関連 design doc: [[20260703-code-review-recall-high-risk-surface]]（この判断を切り出した元 design doc）
- 関連 knowledge:
