---
id: 20261109-split-skill-phases
title: feature-dev と self-review の SKILL.md を phase ごとに分ける
status: draft
phase: target
last-validated: 2026-11-09
supersedes: []
superseded-by: null
issue: "GitHub #426"
spec: null
adrs: []
tags: [feature-dev, code-review, skill-writing, validate]
---

# feature-dev と self-review の SKILL.md を phase ごとに分ける

## TL;DR

feature-dev（93 KB）と self-review（103 KB）の SKILL.md は Read 1 回（約 42 KB で切れる）で読み切れず、続きを読まずに phase を飛ばした実例がある（#350 / #250）。phase（self-review は Step）ごとに本文を `skills/<skill>/references/` へ分け、SKILL.md には全 phase に効く節（適用範囲・原則）と、並び・入口の条件・Read の 1 行だけを残す。上限・「phase の鎖」・どこからも Read されない references/ の md は `validate_plugin_quality.py` の `SPLIT_SKILLS` で error にする。

## 背景 / 課題

- `feature-dev/commands/feature-dev.md` は「Read 1 回では Phase 5.3 の手前で切れる」と書き、`offset` / `limit` で末尾まで分けて読むよう指示している。続きを読まずに進めた回は、Phase 6 の self-review を手順を通さずに呼び、Phase 6.9 と Phase 7 を飛ばした（#350）。self-review も同じ指示を持つ（#250）
- 分けて読む指示は散文なので、守られなければ同じことが起きる。全文を読めば、その回に使わない phase の本文まで毎回コンテキストに入る
- AI-DLC v2 の比較評価（#415）から取り込む原則のひとつ（エージェントへの指示をその段の中身に絞って短く保つ）

## ゴール / 非ゴール

- **ゴール**: 2 つの SKILL.md を 30,000 B 以下にし、各 phase の始めにその本文を Read させる。上限と phase の並びの整合を CI で強制する
- **非ゴール**: 他の大きい SKILL.md（review 84 KB・hub 79 KB ほか、42 KB を超えるもの 7 本）の分割。範囲が広がりすぎるので follow-up にする。モデルが実際に Read するかの挙動の測定（plugin eval）もしない

## 確定した前提

- feature-dev / code-review に plugin eval のケースは無く、pre-commit の鮮度ゲートは掛からない（`.githooks/pre-commit` は `<plugin>/evals/` にケースがあるプラグインだけを見る）
- `check_references` が実在を検査するのは `${CLAUDE_PLUGIN_ROOT}/…` と `{{PLUGIN_ROOT}}/…` の参照だけ（`validate_plugin_quality.py` の `REF_RE`）。`${CLAUDE_SKILL_DIR}` は検査されない
- 他のファイルから phase / Step の番号で約 110 行が参照している。番号と見出しの文言は保つ
- references に分けても、後続の phase の見出しは隠れない（`docs/skill-writing.md` の失敗モード premature completion）。目的は、SKILL.md を Read 1 回で読み切らせ、各 phase の始めに本文を読ませること
- 利用者の決定（2026-11-09）: phase の飛ばしの確かめ方は決定的スクリプトにする / 上限は分けた 2 本だけを一覧で持ち、30,000 B を超えたら error

## 採用案

**置き場と粒度**: `<plugin>/skills/<skill>/references/` に、1 phase（self-review は 1 Step）につき 1 ファイルを置く。feature-dev は `phase-<番号>.md` を 19 本作る。参照は `${CLAUDE_PLUGIN_ROOT}/skills/<skill>/references/<file>.md` の形で書く。

**SKILL.md に残すもの**（feature-dev の見積もりは 16〜18 KB）:

- frontmatter、適用範囲、原則
- 各 phase の見出し（今の番号・文言のまま）
- 入口の条件。前の phase で決まった値だけで判定できるものに限る（feature-dev では 1.4 / 2 / 4.5 / 6.7）
- `入ったら最初に `${CLAUDE_PLUGIN_ROOT}/…` を Read する` の 1 行

**phase ファイルの型**:

- 先頭の見出しは SKILL.md の見出しと同じにする
- 末尾は `**次は Phase X**` にし、最後の phase だけ `**ここで終わり**` にする。括弧で注記を添えてよい
- 鎖が表すのは既定の並び（線形）だけにする。skip は次の見出しの入口の条件で表し、後戻り（Fix Mode・5.3 が赤・5.5 が fail・doc-sync）は本文の分岐で表す

**検査**（`validate_plugin_quality.py`）: 一覧 `SPLIT_SKILLS` に、SKILL.md・phase 見出しの正規表現・次の名前の書式を並べ、`check_split_skills` で次のどれかに当たれば `[split-skill]` の error にする。

- SKILL.md か phase ファイルが 30,000 B を超える
- 1 つの見出しの下に Read の行が 1 本でない
- Read 先が、その skill の `references/` の外にあるか、実在しない
- 2 つの phase が同じファイルを Read している
- ファイルの最初の見出しが SKILL.md の見出しと違う
- 末尾の「次は」が、SKILL.md の並びの次と一致しない
- その skill の `references/` に、どの見出しからも Read されない md がある（他の検査に渡す phase ファイルの集合は Read 先から作る）

あわせて次のように直す:

- `READ_CUT_NOTES` と `check_read_cut_position` は撤去する
- `check_references`・`check_doc_anchors`・`prompt-path`・allowed-tools の最小性・`EVENT_PUBLISHER_GLOBS` の対象に、分けたファイルを足す。`skills/*/references` 全体には広げない（harness-keeper の例示パスで偽陽性が約 8 件出る見込み）

**テスト**: `SplitSkillTest` を足す。期待値はテスト側で独立に組む。`tests/skill_flow.py` の `flow_text` は、SKILL.md の Read の行の位置に本文を差し込み、分ける前の順に戻す。これで既存の見出し切り出しテストはそのまま動く。分けた skill か・どれが Read の行か・どれが最初の見出しかは、検査と同じ関数（`split_skill_entry` / `split_skill_phases` / `first_heading_index`）で決める（判定基準の持ち主を 1 つにする）。

**pin**: 移した本文を要約している SSoT pin は、本文と一緒に新ファイルの冒頭へ移す（hash は変わらない）。

**本文の修正**: 古い「次へ」3 か所を直す。どれも後に足した phase を飛ばす向きになっている。

- 4.5 の「skip して Phase 5 へ」は 4.8 へ
- 6 Step 4 の success の「Phase 7 へ」は 6.7 へ
- 6.7 の失敗時の「Phase 7 へ」は 6.9 へ

## 検討した代替案

| 観点 | 案 A（採用）: 1 phase 1 ファイル + 決定的な鎖の検査 | 案 B: 小さい phase を束ねる | 案 C: plugin eval で読むかを測る |
|------|------------|------|------|
| 検査の規則 | 「見出し 1 ↔ Read 1 ↔ ファイル 1」で例外なし | 束ねた単位の例外規則が要る | 鎖は検査しない |
| Read の回数 | 全部回すと約 19 回（読む byte 数は分ける前と同じ） | 減る | A と同じ |
| 挙動の測定 | しない（構造だけ） | しない | 直接測れる |
| コスト | 無料・CI に載る | 無料 | paid（1 ケース 5〜15 USD）・pre-commit の鮮度ゲートが掛かる |

- 案 B は、規則の例外が self-review に広げるときの負担になるので採らない
- 案 C は、利用者が決定的スクリプトを選んだ（2026-11-09）ので採らない

## 設計判断ログ

- [local] 上限 30,000 B は、今の 3 分の 1（31 KB / 34 KB）より少し下で、Read 1 回の切れ目（実測 42,129 B）に余白を残す値
- [local] 入口の条件を SKILL.md に上げるのは、前の phase で決まった値だけで判定できるものに限る（bash を走らせないと判定できない条件は本文に残す）
- [local] 末尾の行に `## Phase` の文字列を書かない（`flow_text` で戻した本文の見出し切り出しに当たる）
- [→ADR候補] 大きい SKILL.md は phase ごとに references へ分け、`SPLIT_SKILLS` に載せて上限と鎖を強制する（他の skill を分けるときもこの形に揃える）

## 未解決事項 (open)

- 残りの大きい SKILL.md（42 KB 超の 7 本）を分けるか。(a) 1 本ずつ分けて `SPLIT_SKILLS` に足す: 読み切れない問題が消えるが作業量が大きい / (b) 上限だけ緩く全体に掛ける: 分けなくても通る。方向性は (a)。確定タイミング: #426 の 2 本目のマージ後に follow-up の Issue で決める

## 実装ブリッジ (Implementation Bridge)

1. 実装着手の単位:
   - PR 1（feature-dev。`Refs #426`）: C1 では、検査・テスト・`skill_flow.py` を足し、`SPLIT_SKILLS` は空にしておく。C2 では、feature-dev を分けて `SPLIT_SKILLS` に足し、pin を移し、3 か所を直し、commands・README を直して bump する（PATCH）
   - PR 2（self-review。`Closes #426`）: `SPLIT_SKILLS` に `("code-review/skills/self-review/SKILL.md", r"^### (?P<num>\d+(?:\.\d+)?)\.?\s", "Step {num}")` を足し、Step ごとに分ける。feature-dev 側の pin `code-review/skills/self-review/SKILL.md#1`・`#6`（`feature-dev/references/review-loop.md` と phase ファイル）を新しい Step ファイルへ向け直し、feature-dev の版も上げる
2. 検証方法: `check_split_skills` が分割後の repo で error 0 件になること（分割前の feature-dev を一覧に載せると 20 件）。`SplitSkillTest` が独立に組んだ期待値と一致すること。既存の見出し切り出しテストが `flow_text` を通して緑のままであること
3. 実装完了時の doc 更新手順:
   - frontmatter の `phase: target` を `current` にし、`last-validated` を更新する
   - 実装と乖離した箇所があれば追記し、方式ごと変わったなら supersede する

## 関連

- 関連 Issue: GitHub #426（#350 / #250 / #415）
- 関連 spec: なし
- 関連 ADR: `.claude/adr/20261108182901-adopt-aidlc-v2-principles-incrementally.md`
- 関連 design doc: なし
