---
id: 20260817170000
status: accepted
phase: current
last-validated: 2026-08-17
supersedes: []
superseded-by: null
append_only: true
tags: [architecture, code-review, pipeline, cost]
---

# ADR-20260817170000: self-review の agent 起動前に「プロジェクトが宣言した機械層」を 1 本だけ走らせる（原則 8 の除外を部分撤回）

## ステータス

accepted（2026-08-17）

## コンテキスト / 背景

GitHub issue #137。3 回のセルフレビューで出た MAJOR 33 件を分類すると、**B（ガードの守備範囲が宣言と一致していない）15 件 / A（doc が事実を複製していて正本が変わると腐る）11 件 / C（テストがあるのに何も検証していない）7 件**で、**67% が「検証コードの検証が無い」という同じ根**を持っていた。C は変異テストランナー、A は SSoT pin と `vNEXT` プレースホルダで機械化済み。**B が残っている。**

デグレの実測（2026-08-17 / `fix`・`revert` 59 件が触った行の齢）: **同日 37 件 (64%) / 7 日以内 12 件 (21%) / 30 日以内 7 件 (12%) / それ以前 1 件**。時間経過による腐敗ではなく**投入時点の欠陥が主因**で、「commit 後に self-review が見つける」ループが回っているだけだった。

このリポジトリの機械層（`validate-ssot.sh` / `validate_plugin_quality.py` / unittest / `mutation-test.py`）は Stop hook と pre-commit では走るが、**self-review の起動前には走らない**。結果として:

1. 機械が決められる指摘に opus の reviewer 予算を使っている
2. 機械層が赤い状態でも agent が起動し、ノイズの多い差分をレビューする
3. 同じ指摘が「機械層の warning」と「agent の finding」で二重に出る

`docs/pipeline-design.md` 原則 8 は「**LLM レビューの手前に安いオラクルを差し込む**のが最も費用対効果が高い」としているが、**self-review SKILL.md は原則 8 を明示的に「捨てた」**と宣言している（理由: 「diff レビューが対象で型/テスト実行は feature-dev Phase 5.3 の役割と分離した」）。この判断を覆すなら理由を残す必要がある。

**制約**: self-review は任意のプロジェクトで動く汎用スキルで、プラグインにプロジェクト固有のコマンドを書けない（`CLAUDE.md`「プラグイン開発ルール」）。つまり「型チェックとテストを走らせる」を**プラグイン側の知識としては実装できない**。これが元の除外判断の実質的な中身であり、原則 8 そのものの否定ではなかった。

## 決定

**プロジェクトが宣言した実行可能ファイル `.claude/review-oracles.sh` を 1 本だけ、Phase 0 の手前で実行する。** 無ければ完全 no-op（後方互換）。実行と digest 化は `code-review/scripts/run-oracles.sh` が担い、SKILL は結果の 3 つの扱いだけを決める。

- **red（非 0 終了）で自動停止はしない。AskUserQuestion で続行/中止をユーザーに委ねる。**
  - 「lint は赤いが設計レビューを先に受けたい」を潰さないため（無条件 fail-fast は recall を下げる）
  - 隣接する Step 1.4（直近レビューの重複検出）が既に同じ形なので UX が一貫する
- **警告・エラーの出力は「既知」として reviewer に渡すが、抑制は `同一 file:line × 同一ルール` に限る。**
  - 抑制しすぎると「機械層が浅く検出した箇所の別の欠陥」を agent が報告しなくなる（#137 が明示した懸念）
- **reviewer プロンプトには「機械判定できる層は対象外」をスコープ定義として書く。**
  - `docs/pipeline-design.md` の Opus 5 節が禁じるのは**重要度・確度による発見段階の間引き**で、スコープによる除外は対象外なので可
- **機械層の結果を agent に再確認させない**（同節「自分でダブルチェックせよ」の禁止）
- **適用は self-review のみ。** review（他人の PR）は CI が既に回っており、赤くても直せる立場にないため入れない
- **縮退先は「green」ではなく「欠測」**: script が無い / タイムアウト / 実行エラーは `status=absent|timeout|error` として出し、**緑と区別できる形で**レポートに残す

## 検討した代替案

- **プラグイン側でコマンドを推測する**（`package.json` の `scripts.lint` 等を検出して実行）: 却下。誤検出時に任意のコマンドを走らせることになり、プロジェクト非依存の原則も壊れる。「何を安いオラクルとみなすか」はプロジェクトの判断でプラグインの判断ではない
- **userConfig に文字列でコマンドを持たせる**: 却下。userConfig は per-user なので**マシン間で散る**（複数マシン開発では宣言が片方にしか無い状態が普通に起きる）。宣言の正本はコミットされるプロジェクト側にあるべき
- **現状維持（Stop hook / pre-commit に任せる）**: 却下。どちらも**レビュー開始前には走らない**ため、上の 3 症状はそのまま残る
- **機械層が赤なら無条件に停止（純粋な fail-fast）**: 却下。#137 自身が挙げるリスクで、設計レビュー先行のユースケースを潰す。原則 8 の fail-closed は「曖昧なとき保守側に倒す」であって「赤なら人間の判断を奪う」ではない
- **機械層の結果を reviewer に渡さない（実行して止めるだけ）**: 却下。二重報告（症状 3）が残る

## 影響 (Consequences)

- **良い影響**: 機械が決められる層に opus を使わなくなる。機械層が赤い差分で fleet を起動しなくなる。二重報告が減る
- **悪い影響**: レビュー開始までの実時間が増える（本リポジトリの宣言では**実測 130 秒**、うち unittest 512 件が大半）。オラクル script のメンテがプロジェクト側に発生する
- **トレードオフ**: 「既知」の渡し方は緩いと重複が残り、厳しいと同一箇所の別欠陥を潰す。`同一 file:line × 同一ルール` という限定はこの中間を取ったもので、**実測で調整する前提**
- **既知の制約**: 宣言が無いプロジェクトでは完全に no-op なので、この改善は「宣言したプロジェクトにだけ効く」。宣言の書き方はプロジェクト側の裁量で、遅すぎる script（全ビルド等）を書かれると効果が反転する（timeout で欠測に倒れる）

## 適用方法 (Enforcement)

- **機械強制される**: `run-oracles.sh` の存在検出・実行・timeout・digest 出力（`status=` 行）。回帰テストは `.claude-plugin/scripts/tests/test_code_review_oracles.py`
- **機械強制されない（人手に残る）**: SKILL が Step 1.7 を実際に実行すること、reviewer が本当に機械層の層を避けること、「既知」の抑制の程度。いずれも LLM の文脈判断なので `docs/rule-placement.md` の意思決定フローに従い skill 規約止まりにする

## 計測と撤回条件

`review:completed` payload の `findings_class`（`lint` / `test` / `judgement`）を判定に使う（既存フィールドなので新規計測は不要）:

- **成功**: self-review の `lint` が減り、`judgement` が維持または増える
- **撤回**: `judgement` が減った（＝機械層の「既知」扱いが recall を削った）場合は「既知」の注入をやめ、実行と fail-fast の提示だけ残す
- サンプルが 5 回たまるまでは判断しない（#123 の集計と同じ下限）

## 関連

- 契機: GitHub issue #137（機械層を agent の前に出す）/ #138（同梱スクリプトのテスト網羅。機械層の信頼度そのもの）
- 原則の正本: `docs/pipeline-design.md`「外部オラクル + fail-closed（原則 8）の勘所」
- 配置判断の正本: `docs/rule-placement.md`
- 実装: `code-review/scripts/run-oracles.sh` / `code-review/skills/self-review/SKILL.md` Step 1.7
