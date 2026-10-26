---
id: 20261026-project-hub-living-spec-integration
title: project-hub に living spec を統合する
status: approved
phase: current
last-validated: 2026-10-26
supersedes: []
superseded-by: null
issue: "GitHub issue #322"
spec: null
adrs: ["20261026090521"]
tags: [project-hub, living-spec, plugin-merge]
---

# project-hub に living spec を統合する

## TL;DR

living-spec-workflow の 2 つの skill と command を project-hub に移し、living-spec-workflow を deprecated（`_superseded_by: project-hub`）にする。living spec は repo の `.claude/living-specs/` に置いたまま、hub の config の `living_spec` でその PJ の 1 本を指し、state.md に出す。決定と段取りの間の決まりは `hub-living-spec` skill（#322 の橋渡しで入れたもの）がそのまま持つ。

## 背景 / 課題

ADR-20261026090521 を参照。living spec がある PJ では、決定（living spec）と段取り（hub）を 1 つのセッションで扱いたい。2 つのプラグインのままだと、決まりを書いた skill が別プラグインの版を名指しすることになり、書式の正本も分かれる。

## ゴール / 非ゴール

- ゴール: 1 つのプラグインで living spec と hub の両方を使える。living spec 単体（hub なし）の使い方は今のまま。既存のマシンは `/update-all` で移れる
- 非ゴール（後の段）: 確定を覆した決定の波及の機械化（`decide`。今は `hub-living-spec` の決まりで hub が手で行う）、hub の status に living spec の数字（収束率・open OQ）を機械で出すこと

## 確定した前提

- plugin-manager の `/update-all` は、marketplace のエントリの `_superseded_by` を見て、旧プラグインを uninstall して後継を install する（plugin-manager の README・`hooks/update-all-lib.ts`）
- eval の runner はケースファイルの `plugin:` を見るので、1 つのプラグインに複数のケースファイルを持てる（`evals/runner.py`）

## 採用案

1. **移す**: `living-spec-workflow/skills/{living-spec,living-spec-maintain}` と `commands/{living-spec,living-spec-maintain}.md` を project-hub へ。中身は変えない（プラグイン名の言及と、command の `installed_plugins.json` のキーだけ直す）。CHANGELOG の履歴は living-spec-workflow 側に残す
2. **deprecated**: living-spec-workflow の plugin.json と marketplace に `_superseded_by: project-hub`、description の先頭に deprecated の旨。README の冒頭に移行先と手順。中身は全マシンの移行を確かめるまで残す
3. **hub から参照する**: `hub.py init --living-spec <path>` と `hub.py set-living-spec --path <path|->`。config に `living_spec`（repo の中のファイルの絶対パス）を持ち、state.md に 1 行（パスと `/project-hub:living-spec status` で現在地を見ること）を出す。パスが無い・ファイルが無いときは state.md にその旨を出す（hub は living spec を書かない）
4. **決まり**: `hub-living-spec` を「統合までの橋渡し」から「living spec のある PJ の決まり」に書き直す（別プラグインの版の名指しを外す）。hub の status の手順に、config に `living_spec` があれば `/project-hub:living-spec status` も見ることを足す
5. **周辺**: eval のケース（`evals/cases/living-spec-workflow.yaml` → `project-hub-living-spec.yaml`、`expected_skill` を `project-hub:*` に）、doc-freshness の説明（living spec の持ち主の名前）、一覧（CLAUDE.md・INDEX.md）

## 検討した代替案

ADR-20261026090521 を参照。

## 未解決事項 (open)

- 全マシンの移行を確かめた後に living-spec-workflow のディレクトリと marketplace のエントリを消す。確定タイミング: 会社 PC（m2）で `/update-all` を回した後
- 確定を覆した決定の波及（`decide`）を hub.py で機械化するか。確定タイミング: `hub-living-spec` の決まりを実際の PJ で使ってから
- eval（スキル選択の回帰）は回していない（paid）。トリガーの文言は変えていないが、プラグイン名が変わるので、回すときは `--plugin project-hub`

## 実装ブリッジ (Implementation Bridge)

1. skill・command を移し、プラグイン名の言及を直す
2. `hub.py` の `living_spec`（init・set-living-spec・render）とテスト
3. hub SKILL（init・status）と `hub-living-spec`
4. living-spec-workflow の deprecated
5. eval・doc-freshness・一覧・README・CHANGELOG・バンプ（project-hub は minor、living-spec-workflow は patch、doc-freshness は patch）

## 関連

- GitHub issue #322 / #320 / #308
- ADR-20261026090521 / ADR-20260722164106（issue-workflow への吸収）
- `.claude/designs/20260715-living-spec-workflow.md` / `.claude/designs/20261021-project-hub-plugin.md`
