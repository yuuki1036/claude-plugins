---
id: 20260708-spec-routing-ssot
title: spec ルーティング rubric の SSoT 一元化方式
status: approved
phase: current
last-validated: 2026-07-08
supersedes: []
superseded-by: null
issue: null
spec: null
adrs: []
tags: [spec-advisor, routing, ssot, plugin-independence]
---

# spec ルーティング rubric の SSoT 一元化方式

## TL;DR

「開発タスク → 設計・計画系プラグイン」の軸→プラグイン対応が複数箇所に散在する。ドリフトしうる不変量は WHAT/HOW/WHY の3軸→プラグイン対応（~3行）だけ。これを **delimiter で区切った byte-identical 共有ブロックとして正本化し、複製を quality-check で Critical 検証する**（safe-hook.sh と同型）。当初は「文書化 + 昇格トリガー」（軽量案）を採ったが、design-review で昇格トリガーが機能不全（閾値矛盾・検知手段ゼロ）と判明し、機械強制の案B に転換した。

## 背景 / 課題

spec-advisor 追加時の敵対的レビュー（M2）で「routing-rubric.md が『SSoT』を名乗るが実体は4つ目のコピー」と指摘された。分布を調査した結果:

| サイト | 形態 | 状態 |
|---|---|---|
| `linear-workflow/skills/issue-create/SKILL.md` Phase 5 | **着手前 spec 選択表**（signal→bdd-spec/design-doc/adr-keeper/不要）。type keying（bugfix/debt→不要）も同じ表に混在。type テンプレ選択の表は別（Phase 2/4） | indie と byte-identical |
| `indie-workflow/skills/indie-issue-create/SKILL.md` Phase 8 | 同上（linear のミラー） | ミラー規約で同期済み |
| `feature-dev/commands/feature-dev.md` Phase 1.3 / 4.5 | **判定表ではない**。phase 埋め込みの dormant handoff（無条件に spec 生成を提案） | 表コピーではない |
| `spec-advisor/skills/spec-advise/references/routing-rubric.md` | 一般 signal ベースの5軸表（raw chat 向け） | 一般化版 |

重要な発見（design-review で裏取り済み）:
- **feature-dev は「表の重複」ではない**。分類ロジックを持たず、bdd-spec(Phase 1.3)/design-doc(Phase 4.5) を呼ぶ handoff にすぎない。**同期対象から外れる**。
- **issue-create ↔ indie は既に byte-identical ミラー**で、ミラー規約が同期を担保している。
- **実際に共有される不変量は WHAT/HOW/WHY の3軸コアだけ**。issue-create が routing するのはこの3プラグインのみ（Issue粒度=issue-design は姉妹、実装=feature-dev は handoff）。spec-advisor はこれに issue-design/feature-dev の2軸を独自拡張している。
- 現状の各サイトは軸対応と文脈特化（type keying / guard）を**同じ表に混在**させており、「どこまでが不変量か」が構造的に分離されていない。

## ゴール / 非ゴール

- **ゴール**: 共有不変量（WHAT/HOW/WHY→プラグイン対応）を delimiter で区切った byte-identical ブロックに切り出し、正本と複製の一致を quality-check で機械的に強制する。ドリフトをコミット前に必ず落とす。
- **非ゴール**: 各サイトの文脈特化部（type keying / guard / handoff）まで統一すること（正当な差異）。spec-advisor 固有の拡張2軸や feature-dev handoff を同期対象に含めること。runtime の cross-plugin 依存を作ること。

## 確定した前提

- **プラグイン間依存禁止**（CLAUDE.md）。他プラグインが spec-advisor のファイルを runtime で Read するのは不可。→ 共有は「byte-identical 複製 + 検証」で行う（runtime 参照しない）。
- **byte-identical 複製 + quality-check 検証の前例**: `safe-hook.sh`（正本 `.claude-plugin/lib/`、各プラグインに複製、quality-check が Critical 同期検証）。本方式はこの機構を routing 不変ブロックに転用する。
- **design-review で棄却された前提**: 当初案の「不変量は安定・ドリフト実測ゼロなので機構は先行投資しない」は、昇格トリガー自体が機能しないため成立しない（下記代替案 A の棄却理由）。安定でも「変更契機（新軸追加・軸統廃合）が来たとき手動規律 ~90% では取りこぼす」ため、機械強制が妥当と判断。
- **共有不変量は3軸コア**（WHAT→bdd-spec / HOW→design-doc / WHY→adr-keeper）。issue-create/indie が持つのはこの3軸のみ（design-review pragmatic/risk が裏取り: `issue-create/SKILL.md:206-213` は3プラグイン subset）。

## 採用案（design-review により案B へ転換）

**delimiter 付き byte-identical 共有ブロック + quality-check Critical 検証。**

1. **不変ブロックの定義**: 全ルーティングサイトで一致させる最小ブロック = WHAT/HOW/WHY の3軸→プラグイン対応（~3行）:
   `WHAT → bdd-spec / HOW → design-doc / WHY → adr-keeper`
   Issue粒度=issue-design と 実装=feature-dev は spec-advisor 固有の拡張軸（同期対象外）。feature-dev は handoff で表を持たない（対象外）。
2. **正本 + 複製**: この3行ブロックを正本化し、消費サイト（spec-advisor rubric・issue-create Phase 5・indie Phase 8）に byte-identical で埋め込む。各サイトは不変ブロックの**外側**に文脈特化（spec-advisor=guard+拡張2軸、issue-create=type keying）を持つ。
3. **境界の明示（F-C 対応）**: 不変ブロックを delimiter コメント（例: `<!-- ROUTING-AXES:START -->` … `<!-- ROUTING-AXES:END -->`）で囲む。quality-check はこの区間だけを byte-identical 比較し、区間外の特化部は比較しない。これで「どこまでが不変量か」を機械的に確定し、semantic 判断を排除する。
4. **quality-check 検証**: `validate_plugin_quality.py` に routing-axes 同期チェックを追加（safe-hook.sh 同期チェックと同型・Critical）。正本と各複製の delimiter 区間が byte-identical でなければ fail。pre-commit / auto-quality-check でドリフトを機械的にブロック。

この機構で **F-A（閾値矛盾）・F-B（死んだトリガー）は昇格トリガー自体を廃するため消滅**、**F-C（境界曖昧）は delimiter 区間で確定**する。

## 検討した代替案

| 観点 | 案B: byte-identical 共有ブロック+quality-check（採用） | 案A: 文書化+昇格トリガー | 案C: runtime 委譲（dormant） | 案0: 現状維持 |
|------|-----------------------------------------------|------------------------|---------------------------|--------------|
| ドリフト防止 | 機械的（Critical 検証、100%） | 規律（~90%）+ 昇格トリガー | 実行時に単一化（100%） | なし |
| 実装コスト | 中（ブロック抽出 + validator + 複製） | 低 | 高 | 0 |
| 恒常コスト | 複製同期（機械検証あり） | ほぼ0 | 逆依存 + fallback コピー | 0 |
| プラグイン独立性 | 保つ | 保つ | 逆依存が増える | 保つ |

- **案A 不採用（design-review で転換）**: 昇格トリガーが機能不全。閾値「2回」と乗せ先 failure-journal「3回/30日窓」が矛盾（F-A）、かつ軸ずれを突き合わせて観測する主体が居ないため記録されず永久に昇格しない「死んだトリガー」（F-B）。軽量さの根拠が崩れた。
- **案C 不採用**: fallback 用 inline コピーが結局残り重複が消えず、逆方向 dormant 依存で結合度だけ上がる。
- **案0 不採用**: reference-of-record が存在せず（routing-rubric は逆に「唯一の正本ではない」と明示否認）、M2 が指摘した gap が残る。

## 設計判断ログ

- [→ADR候補] spec ルーティングの WHAT/HOW/WHY 軸対応を delimiter 付き byte-identical 共有ブロックとし、正本+複製を quality-check で Critical 検証する（safe-hook.sh と同型）。当初の「文書化+昇格トリガー」案は design-review で昇格トリガーの機能不全（F-A/F-B）が判明し転換した。
- [local] 共有不変量は3軸コア（WHAT/HOW/WHY）。Issue粒度/実装は spec-advisor 固有拡張・feature-dev は handoff で同期対象外。
- [local] issue-create↔indie の既存ミラー規約は維持し、不変ブロックの正本同期を上乗せする。
- [local] feature-dev は分類表を持たない handoff なので一元化対象から除外する。
- [local]（実装時確定）比較は「dedent 後の厳密一致」とした。消費サイトはリスト内で一様なインデント（3 スペース）を付けるため、厳密 byte-identical だと正本かサイトのどちらかのレンダリングを壊す。textwrap.dedent は決定的なのでドリフト検知の強度は落ちない。
- [local]（実装時確定）open だった正本配置は (a) `.claude-plugin/lib/routing-axes.md` に確定（safe-hook.sh と同居する repo-level 中立配置）。delimiter 形式も (a) SKILL 本文内コメント囲みで確定（PoC: テーブル前後の HTML コメントはレンダリングを壊さない・validator が安定抽出できることを pass/drift/marker-tamper/restore の 4 ケースで確認）。

## 未解決事項 (open)

なし（実装時に全 open を確定済み。確定内容は設計判断ログの「実装時確定」2 行を参照）:

- ~~正本の配置~~ → (a) `.claude-plugin/lib/routing-axes.md` に確定。
- ~~delimiter 形式~~ → (a) SKILL 本文内コメント囲みに確定（PoC で検証済み）。
- ~~issue-create の3軸 subset 再構成~~ → 3軸コアを delimiter 区間・type 別判定を「type 別の追加判定」表に分離（linear/indie 対称に実装済み）。

## 実装ブリッジ (Implementation Bridge)

1. **実装着手の単位**（PoC → 展開の順。1〜2 Issue 相当）:
   - **PoC**: delimiter コメントで囲んだ markdown 表が SKILL.md のパース/レンダリングを壊さないか、quality-check が区間を安定抽出できるかを1サイトで検証（open 2 の確定）。
   - 正本 `.claude-plugin/lib/routing-axes.md`（or 確定した配置）を作成。
   - `spec-advisor/skills/spec-advise/references/routing-rubric.md`・`linear-workflow/skills/issue-create/SKILL.md` Phase 5・`indie-workflow/skills/indie-issue-create/SKILL.md` Phase 8 に delimiter 区間 + byte-identical ブロックを埋め込み（linear/indie は対称に = ミラー規約）。
   - `validate_plugin_quality.py` に routing-axes 同期チェックを追加（Critical、safe-hook.sh 同期チェックのロジックを流用）。`/quality-check` skill の項目にも追記。
   - `CLAUDE.md` の Gotchas に「routing-axes 正本の同期忘れ」を追記（safe-hook.sh の項と対称）。
   - 各プラグイン version bump + CHANGELOG（spec-advisor / linear-workflow / indie-workflow）。feature-dev は対象外（handoff）。
2. **検証方法**: `/quality-check` で routing-axes 区間の byte-identical を Critical 検証。正本を意図的に1文字ずらして各複製が fail する（＝検知が効く）ことを確認。linear↔indie が対称であることを目視。
3. **実装完了時の doc 更新手順**: 本 doc の `phase: target → current`、`last-validated` 更新。機構の形が変わったら supersede。

## 関連

- 関連 Issue: なし（follow-up chip task_6646f8c1 由来）
- 関連 spec: なし
- 関連 ADR: なし（[→ADR候補] は未切り出し）
- 関連 design doc: なし
- 関連実装: `.claude-plugin/lib/routing-axes.md`（正本・新規）、`spec-advisor/skills/spec-advise/references/routing-rubric.md`、`linear-workflow/skills/issue-create/SKILL.md` Phase 5、`indie-workflow/skills/indie-issue-create/SKILL.md` Phase 8、`.claude-plugin/scripts/validate_plugin_quality.py`、`.claude-plugin/lib/safe-hook.sh`（同期機構の前例）
