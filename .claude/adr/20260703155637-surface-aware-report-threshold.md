---
id: 20260703155637
status: accepted
phase: current
last-validated: 2026-07-03
supersedes: []
superseded-by: null
append_only: true
tags: [code-review, scoring, recall, precision, high-risk-surface]
---

# ADR-20260703155637: high-risk surface に限り code-review の報告閾値を surface 単位で可変にする（precision と recall の非対称扱い）

## ステータス

accepted（2026-07-03）

## コンテキスト / 背景

code-review の報告マトリクス（`scoring-guide.md`）は全 surface 一律で、CRITICAL は confidence 80+、MAJOR は 95+ を報告閾値とする precision 寄せの設計だった。この一律設計のもとで、xhigh フルパイプラインが high-risk な DB 書込 PR の実バグ（空文字が numeric 列へ INSERT され 500、GitHub issue #75 #1）を見落とした。high-risk surface（DB 書込 / 金銭計算 / 認可）では、CRITICAL 見落としのコストが nit 偽陽性のコストを大きく上回る。一方で全 surface で閾値を緩めると noise が爆発する。

## 決定

報告閾値を surface 単位で可変にする。**high-risk surface（DB 書込 / 金銭計算 / 認可、または PR 自己申告 D1-High）に限り** CRITICAL 80→70 / MAJOR 95→85 に緩め、それ以外の surface は従来の precision 寄せ閾値を維持する。precision の本丸（`≤40 好みクランプ`・`高 severity 非削除`・`[unverified] min75`・`specialist 反証除外`）は不変で、surface-aware 緩和はその後段（報告可否の閾値）にのみ効かせる。precision と recall を surface 単位で非対称に扱うことを code-review scoring の設計原則とする。

## 影響 (Consequences)

- **良い影響**: high-risk surface の recall が上がり、見落としコストが高い層で CRITICAL/MAJOR を拾える。低リスク surface の noise は据え置き。
- **悪い影響**: high-risk surface で偽陽性が増えうる。surface 判定ロジックの保守コストが増える。
- **トレードオフ**: high-risk surface の recall と precision を天秤にかけ、見落としコストが偽陽性コストを上回る層に限って recall を優先する。増えた偽陽性は後段の反証レイヤー（Phase 5.8）が独立検証で吸収する二段構え。

## 適用方法 (Enforcement)

- **部分的に機械強制可能**: 報告マトリクスのフィルタは `scoring-guide.md` に基づきオーケストレーターが Step 6 で機械適用する。surface フラグが立った指摘に緩和後の閾値を適用するのはコード分岐で決定的に書ける。
- **surface 判定は自然言語寄り**: 「この変更が DB 書込 / 認可を含むか」の判定は既存の red-flag pattern（正規表現）+ PR 自己申告で近似するが、完全な決定的判定は難しく LLM 判断が残る。→ 判定フローは triage-guide.md の規約 + red-flag 正規表現で担保し、hook 昇格はしない（surface の網羅は正規表現で拾いきれず例外が多いため）。
- **回帰検証**: #75 #1 を再現する fixture で、surface-aware 適用後に CRITICAL が報告されること（recall 回帰）、および既存の Fable 誤検出ケースが引き続き非報告になること（precision 回帰）を確認する。

## 検討した代替案

- **全 surface 一律で閾値を下げる**: recall は上がるが低リスク surface の noise が爆発し alert fatigue を招く。却下。
- **閾値は据え置き、meta-reviewer のゲートだけ変える**: meta-reviewer は findings 注入で非独立のため fleet 共通盲点を破れない。閾値問題と recall 機構問題は別で、閾値側の補正が必要。却下（機構側は独立 skeptic で別途対応）。
- **surface 判定を専用 detector として新設**: 既存の red-flag pattern / PR コンテキスト検出で足り、往復コストを増やすだけ。却下。

## 関連

- 関連 ADR:
- 関連 Issue: [GitHub issue #75](https://github.com/yuuki1036/claude-plugins/issues/75)
- 関連 design doc: [[20260703-code-review-recall-high-risk-surface]]（この判断を切り出した元 design doc）
- 関連 knowledge:
