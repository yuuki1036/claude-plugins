---
id: 20261026090521
status: accepted
phase: current
last-validated: 2026-10-26
supersedes: []
superseded-by: null
append_only: true
tags: [architecture, project-hub, living-spec, plugin-merge, deprecation]
---

# ADR-20261026090521: living-spec-workflow を project-hub に吸収し、living spec は repo に置いたまま hub の config から参照する

## ステータス

accepted（2026-10-26）

## コンテキスト / 背景

- project-hub は、living spec を hub の代わりに使って詰まったところ（状態が会話にしか無い・宛先が引けない・報告を取りこぼす）を切り出して生まれた（GitHub issue #308）。#308 では「living-spec-workflow とは統合しない」とした
- 実際の PJ で、確定した項目を Issue に切り分けた後にも決定が 12 件増え、うち 3 件は作業中のセッションの発見から生まれた。決定（living spec）と段取り（hub）が別々のセッションにあると、決定を作業へ届けるたびに連絡が要る（#322）
- living spec は 1 PJ に 1 本で、hub と 1 対 1 になる
- プラグイン間の依存は禁止で、複製が出たら分割単位の誤りとみなす（CLAUDE.md）。2 つのプラグインのまま hub が living spec の書式を読み書きすると、書式の正本が 2 つに分かれる
- 前例: issue-workflow が旧 linear-workflow / indie-workflow を吸収した（ADR-20260722164106）。旧プラグインに `_superseded_by` を付け、plugin-manager の `/update-all` が自動移行した

## 決定

1. living-spec-workflow の skill（`living-spec` / `living-spec-maintain`）と command を project-hub に移す。living-spec-workflow には `_superseded_by: project-hub` を付けて deprecated にする（全マシンの移行を確かめてからディレクトリを消す。issue-workflow のときと同じ）
2. living spec のファイルは今どおり repo の `.claude/living-specs/<slug>.md` に置き、commit する。hub の config に、その PJ の living spec のパスを持たせて結ぶ（任意）
3. hub の機能はオプトインのまま: 設計だけを詰める段階は living spec だけで使い、sub を起動するときに hub を init する。書式（format-spec）と living spec 単体の手順は変えない
4. 決定と段取りの間の決まり（決定を書くのは lead が決めたときだけ・確定を覆した決定の波及・sub の report を OQ の候補にする）は、project-hub の `hub-living-spec` skill が持つ

## 影響 (Consequences)

- **良い影響**: 1 つのセッション・1 つのプラグインで決定と段取りを扱える。決まりを書いた skill が別プラグインの版を名指ししなくてよくなる。書式の正本が 1 つのプラグインに収まる
- **悪い影響**: コマンドが `/project-hub:living-spec` / `/project-hub:living-spec-maintain` に変わる（旧 `/living-spec-workflow:*`）。living spec だけを使う利用者にも hub の部品（hook・スクリプト）が入る（hub の PJ が無ければ hook は何も注入しない）。全マシンの移行が済むまで、旧プラグインの中身が残る
- **トレードオフ**: 名前の分かりやすさ（living spec を名乗るプラグイン）より、書式の正本を 1 つにすることと、利用者の移行を 1 本で済ませることを取った

## 適用方法 (Enforcement)

- 移行は plugin-manager の `/update-all` が `_superseded_by` を見て機械で行う（旧を uninstall して後継を install）
- `_superseded_by` の plugin.json と marketplace.json の同期は `validate-ssot.sh`（pre-commit / CI）が検査する
- 「新旧を同時に install しない」は機械で止めない（自動移行がまとめて入れ替える。手で両方を入れた回はトリガーが重なるだけで、データは壊れない）

## 検討した代替案

- **新しい名前のプラグインに両方をまとめる**: 役割を名前で言い直せるが、利用者の移行が 2 本になり、コマンド名も全部変わる
- **2 つのプラグインのまま書式だけを共有する**: 移行は要らないが、書式の正本が 2 つのプラグインに分かれる（複製）
- **living spec を `~/.claude/project-hub/<PJ>/` に移す**: 複数 repo の PJ でも 1 か所になるが、決定の履歴が repo に残らず、worktree の sub・他の人・doc-freshness の走査から外れ、マシンごとのデータになる

## 関連

- 関連 ADR: ADR-20260722164106（issue-workflow への吸収）/ ADR-20261025152955（hub の自動の連絡）
- 関連 Issue: GitHub issue #322 / #320 / #308
- 関連 design doc: `.claude/designs/20261026-project-hub-living-spec-integration.md`
- 関連 knowledge: -
