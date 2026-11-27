---
id: 20261109-split-skill-phases
title: feature-dev と self-review の SKILL.md を phase ごとに分ける
status: draft
phase: current
last-validated: 2026-11-27
supersedes: []
superseded-by: null
issue: "GitHub #426"
spec: null
adrs: []
tags: [feature-dev, code-review, skill-writing, validate]
---

# feature-dev と self-review の SKILL.md を phase ごとに分ける

## TL;DR

feature-dev（93 KB）と self-review（103 KB）の SKILL.md は Read 1 回（約 42 KB で切れる）で読み切れず、続きを読まずに phase を飛ばした実例がある（#350 / #250）。phase（self-review は Step）ごとに本文を `skills/<skill>/references/` へ分け、SKILL.md には全 phase に効く節（適用範囲・原則）と、並び・入口の条件・Read の 1 行だけを残す。上限・「phase の鎖」・どこからも Read されない phase の置き場（既定は references/）の md は `validate_plugin_quality.py` の `SPLIT_SKILLS` で error にする。

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

**置き場と粒度**: `<plugin>/skills/<skill>/references/` に、1 phase（self-review・review・review-guide・pr-creator は 1 Step）につき 1 ファイルを置く。references/ に phase でない参照文書を前から持つ skill（pr-creator・start・living-spec・ui-verify）は下のディレクトリ（pr-creator は `references/steps/`、start と ui-verify は `references/modes/`、living-spec は `references/subcommands/`）に置き、`SPLIT_SKILL_PHASE_DIRS` に載せる。feature-dev は `phase-<番号>.md` を 19 本作る。参照は `${CLAUDE_PLUGIN_ROOT}/skills/<skill>/references/<file>.md` の形で書く。

**SKILL.md に残すもの**（feature-dev の見積もりは 16〜18 KB）:

- frontmatter、適用範囲、原則
- 各 phase の見出し（今の番号・文言のまま）
- 入口の条件。前の phase で決まった値か利用者の依頼だけで判定できるものに限る（feature-dev では 1.4 / 2 / 4.5 / 6.7、review-guide では Step 6）
- `入ったら最初に `${CLAUDE_PLUGIN_ROOT}/…` を Read する` の 1 行

**phase ファイルの型**:

- 先頭の見出しは SKILL.md の見出しと同じにする
- 末尾は `**次は Phase X**`（self-review・review・review-guide・pr-creator は `**次は Step X**`）にし、最後の phase だけ `**ここで終わり**` にする。括弧で注記を添えてよい。節を順に踏まない skill（`UNCHAINED_SPLIT_SKILLS`。今は hub・start・living-spec・ui-verify）は末尾の「次は」を置かない
- 鎖が表すのは既定の並び（線形）だけにする。skip は次の見出しの入口の条件で表し、後戻り（Fix Mode・5.3 が赤・5.5 が fail・doc-sync）は本文の分岐で表す

**検査**（`validate_plugin_quality.py`）: 一覧 `SPLIT_SKILLS` に、SKILL.md・phase 見出しの正規表現・次の名前の書式を並べ、`check_split_skills` で次のどれかに当たれば `[split-skill]` の error にする。

- SKILL.md か phase ファイルが 30,000 B を超える
- 1 つの見出しの下に Read の行が 1 本でない
- Read 先が、その skill の phase の置き場（既定は `references/`。`SPLIT_SKILL_PHASE_DIRS` に載せた skill はその下）の外にあるか、実在しない
- 2 つの phase が同じファイルを Read している
- ファイルの最初の見出しが SKILL.md の見出しと違う
- 末尾の「次は」が、SKILL.md の並びの次と一致しない（`UNCHAINED_SPLIT_SKILLS` の skill は見ない）
- その skill の phase の置き場に、どの見出しからも Read されない md がある（他の検査に渡す phase ファイルの集合は Read 先から作る）

あわせて次のように直す:

- `READ_CUT_NOTES` と `check_read_cut_position` は撤去する
- `check_references`・`check_doc_anchors`・`prompt-path`・allowed-tools の最小性・`EVENT_PUBLISHER_GLOBS`・comment-polish の連結（COMMENT-POLISH マーカーの数）の対象に、分けたファイルを足す。`skills/*/references` 全体には広げない（harness-keeper の例示パスで偽陽性が約 8 件出る見込み）

**テスト**: `SplitSkillTest` を足す。期待値はテスト側で独立に組む。`tests/skill_flow.py` の `flow_text` は、SKILL.md の Read の行の位置に本文を差し込み、分ける前の順に戻す。これで既存の見出し切り出しテストはそのまま動く。分けた skill か・どれが Read の行か・どれが最初の見出しかは、検査と同じ関数（`split_skill_entry` / `split_skill_phases` / `first_heading_index`）で決める（判定基準の持ち主を 1 つにする）。

**pin**: 移した本文を要約している SSoT pin は、本文と一緒に新ファイルの冒頭へ移す（hash は変わらない）。どのファイルに配るかは `docs/ssot-pin.md`「SKILL.md を分けるとき」に従う（review と self-review の配り漏れは GitHub #473 で直した）。

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
- [local] 入口の条件を SKILL.md に上げるのは、前の phase で決まった値か利用者の依頼だけで判定できるものに限る（bash を走らせないと判定できない条件は本文に残す。利用者の依頼は review-guide の Step 6 で足した / 2026-11-24）
- [local] 末尾の行に `## Phase` の文字列を書かない（`flow_text` で戻した本文の見出し切り出しに当たる）
- [local] self-review の 4.5〜4.9 は、SKILL.md の見出しを実行の順（4.5 → 4.8 → 4.6 → 4.9 → 4.7）に並べ、並べ替えた見出しの直前の Step の下にそう並べたことを 1 行添える（`docs/skill-writing.md` にも同じ規則を書いた）。鎖は SKILL.md の並びを辿るので、番号の順に並べると 4.8 の skeptic 統合を飛ばして 4.6 へ進む（2026-11-09）
- [local] self-review は `step-<番号>.md` を 19 本作り、入口の条件を SKILL.md に上げず、スキップの条件は Step ファイルで判定する（Step の見出しが条件を括弧書きで持ち、前の Step の値だけで決まる条件が少ないため / 2026-11-09）
- [local] self-review の SSoT pin（orchestration-guide `0`・`3.5`、orchestration-measurement `16`、scoring-guide の報告閾値の節）は、要約している本文と一緒に Step 3・4・5・6・6.4 のファイルへ移す。COMMENT-POLISH マーカーの検査は phase ファイルを含めた本文で数える
- [local] review（84 KB）も self-review と同じ形で `step-<番号>.md` を 17 本作り、`SPLIT_SKILLS` に足した（GitHub #447 / 2026-11-19）。5.5〜5.9 は self-review の 4.5〜4.9 と同じく実行の順（5.5 → 5.8 → 5.6 + 5.9 → 5.7）に並べた。Step 3 の `#### 3.0`〜`3.4` は Step 3 のファイルにまとめ、レポートの定型と締めフローを持つ Step 7 は分けずに 1 ファイルにした（22 KB で上限に収まり、7 の中に `###` の見出しが無い）。SSoT pin は要約している Step 1・4・5・6・7 のファイルへ移した
- [local] project-hub の hub（81 KB）も分けた（GitHub #447 / 2026-11-23）。#447 は「段の区切りがはっきりしない skill（段を順に踏まない作り）は、分けない理由を残す」としていたが、hub は段を順に踏まない一方で、節の区切り（サブコマンドの見出し）ははっきりしており、呼ばれたサブコマンドの節しか使わないので、使わない節の本文を毎回読ませない分割の効き目がむしろ大きい。そこで分けない側には入れず、どのサブコマンドでも要る「hub の役割」「共通」「自動の連絡」を SKILL.md に残して、ほかの 19 節を 1 節 1 ファイル（`skills/hub/references/<節>.md`）にした。並びに意味が無いので末尾の「次は」は置かず、`UNCHAINED_SPLIT_SKILLS` に載せて鎖の検査だけを外した（上限・Read の行・最初の見出し・孤立ファイルの検査は掛かる）。本文がほかの節を番号で引くときは、その節のファイルも読むよう SKILL.md の冒頭に書いた。残りの skill も、区切りがはっきりしていれば順に踏むかどうかに関わらず分けられる
- [local] code-review の review-guide（47 KB）も review と同じ形で `step-<番号>.md` を 9 本作り、`SPLIT_SKILLS` に足した（GitHub #447 / 2026-11-24）。Step 6 の入口の条件（`WALKTHROUGH=1` の回か、利用者がレポートの後に精読の解説を頼んだ回）は Step 0 の値と利用者の依頼だけで決まるので SKILL.md に上げ、Step 5 の末尾の「次は Step 6」に同じ条件を添えた。分ける前の SKILL.md は pin を持たなかったので、分けたファイルが引く正本の節を pin の有無に関わらず洗い、言い換えている Step に pin を置いた。orchestration-guide の `0`（Step 3）・`3.5`（Step 0・3）・`5`（Step 3）、review-guide-format の `4`（Step 4・6）・「レビュー観点（確かめた結果）」「修正」「置き場所」「関連ファイル」「コード」（Step 6）・「回し直すかの判断」（Step 7）・「変異テストの提案」（Step 0・7）、explorer-common の「diff の取得」（Step 2・3・5・6）、explorer-prompts の「プロンプトの組み立て方」（Step 3）。review-guide-format の「ガイド非表示の開始行」「精読の解説」「読み合わせの締め」「ガイド非表示の締めの前置き」も Step 5〜7 が言い換えているが、見出しの anchor では引けない。anchor には空白も行内コードも書けない（行内コードは pin の検査が取り除く）。「精読の解説（Step 6 / …）」「読み合わせの締め（Step 7）」は空白の前で切ると直後が数字になり、番号の anchor の吸着を防ぐ規則で当たらない。ほかの 2 つは見出しに行内コードがある。代わりに、開始行と締めの 2 節を言い換えている Step 5・7 には review-guide-format の全体（anchor なし）を pin し、精読の解説は子の見出し（「置き場所」「関連ファイル」「コード」）で Step 6 に pin した
- [local] dev-workflow の pr-creator（45 KB）も review-guide と同じ形で `step-<番号>.md` を 12 本作り、`SPLIT_SKILLS` に足した（GitHub #447 / 2026-11-25）。`references/` には phase でない参照文書が 3 本（`description-guide.md`・`diagram-guide.md`・`linear-integration.md`）あり、そのまま載せると孤立の検査に当たるので、Step のファイルは `references/steps/` に置き、`SPLIT_SKILL_PHASE_DIRS` に置き場を持たせて、Read 先の内外と孤立の検査をその置き場で見るようにした（参照文書を references/ の外へ移す案は、この repo の references/ の慣例から外れるので採らなかった / 利用者の決定 2026-11-25）。4.3（writing-polish）は本文が「4.7 の後・4.9 の前に行う」と書いていたので、self-review の 4.5〜4.9 と同じく見出しを実行の順（4.7 → 4.3 → 4.9）に並べ、4.7 の下にそう並べたことを 1 行添えた。4.5（Screenshots）・4.6（説明図）の入口の条件は bash の判定（`--attach` の対応・権限）が要るので SKILL.md に上げず Step のファイルに残した。分ける前の SKILL.md は pin を持たなかった。Step 4・4.5 は ui-verify の本文（verification.md の形・「PR タイプ別ガイドライン」の表）を言い換えているが、分ける前から pin が無い。表は見出しでなく太字の行の下にあって anchor で引けず、ui-verify も #447 の分割の対象に残っているので、pin を置くかはこの PR の外で決める
- [local] issue-workflow の start（42,760 B）を、モードごとに 5 本のファイルへ分け、`SPLIT_SKILLS` と `UNCHAINED_SPLIT_SKILLS` に足した（GitHub #447 / 2026-11-26）。start は Phase 0〜1.5 でモードを 1 つ決め、そのモードの節だけを通すので、hub と同じく鎖を見ない型にした。SKILL.md には「ワークフロー」（Phase 0〜1.5。BACKEND-DETECT の区間は検査が SKILL.md から探すので動かせない）と各モードの見出し・Read の行を残し、本文は `references/modes/` に置いた（references/ には context-agents.md・existing-work.md・lightweight-flow.md があり、直下に置くと孤立の検査に当たる）。Feature ブランチモード（25 KB）は上限に収まるので Phase ごとには分けなかった（利用者の決定 2026-11-26）。Phase CTX は Feature ブランチモードの F7 より前に要る（F7 は feature-dev・軽量フローに処理を渡して start に戻らない）ので、Feature ブランチモードの見出しに「F7 に入る前に Phase CTX のファイルも読む」と 1 文添えた。分ける前の SKILL.md は pin を持たなかったので、分けたファイルが引く正本の節を洗い、existing-work.md の `1`〜`5` を言い換えている Feature ブランチモードと、`2` を言い換えている Phase CTX に pin を置いた。Phase CTX は shared-state の frontmatter の形、F3.5 は orchestration-guide の `## 0`（code-review 側）も言い換えているが、プラグインをまたぐ正本で、分ける前から pin が無く、今回の分割で確認の範囲から外れたものではないので、pin を置くかはこの PR の外で決める
- [local] project-hub の living-spec（43,087 B）を、サブコマンドごとに 6 本のファイル（init・oq・decision・spec・status・timeline）へ分け、`SPLIT_SKILLS`・`UNCHAINED_SPLIT_SKILLS`・`SPLIT_SKILL_PHASE_DIRS` に足した（GitHub #447 / 2026-11-26）。Phase 0 でサブコマンドを 1 つ決め、その節だけを通すので、hub・start と同じく鎖を見ない型にした。SKILL.md には Phase 0・共通手順（W1〜W5。書き込む 4 つのサブコマンドが毎回従う）・maintain の案内・処理フロー・注意事項と、各 Phase の見出しと Read の行を残した（共通手順を SKILL.md に残すのは利用者の決定 2026-11-26）。init は Phase 1〜3 を 1 本にまとめ、SKILL.md には Phase 1 の見出しだけを残して、Phase 2・3 の見出しは init のファイルの中に置いた（見出しを SKILL.md に残すと Read の行が無い error になる。サブコマンド単位にするのも利用者の決定 2026-11-26）。references/ には format-spec.md と template.md があり直下に置くと孤立の検査に当たるので `references/subcommands/` に置き、前から Phase 8 の手順を持っていた timeline.md もここへ移して最初の見出しを SKILL.md の Phase 8 の見出しに揃えた。凍結の判定と壊れた宣言の定義は spec のファイルの冒頭に残し、decision と status が引くときは spec のファイルも読むよう SKILL.md の冒頭に書いた。分ける前の SKILL.md は pin を持たなかった。移した本文は format-spec.md の節を言い換えているが、同じ言い換えは SKILL.md に残した W2 と living-spec-maintain の check-rules.md にもあり、project-hub は `docs/ssot-pin.md` の適用範囲の外なので、pin を置くかはこの PR の外で決める（未解決事項に残した）
- [local] dev-workflow の ui-verify（42,673 B）を、Step 3 のモードごとに 3 本のファイル（verify・tune・snap）へ分け、`SPLIT_SKILLS`・`UNCHAINED_SPLIT_SKILLS`・`SPLIT_SKILL_PHASE_DIRS` に足した（GitHub #447 / 2026-11-27）。Step 3 は呼ばれたモードの節だけを通るので、hub・start・living-spec と同じく鎖を見ない型にした。SKILL.md には、どのモードでも通る節（3 つのモード・事前判定・Step 0〜2・Step 4・MCP Tool の使い方・絶対厳守ルール）と、Step 3 の各モードの見出しと Read の行を残した（モード単位にするのは利用者の決定 2026-11-27）。Step 4 は pending flag の 3 値の正本で 3 モードとも通るので SKILL.md に残した。references/ には chrome-devtools-cheatsheet.md があり直下に置くと孤立の検査に当たるので `references/modes/` に置いた。SKILL.md に残した本文は verify の (a)〜(f) を記号で引くので、SKILL.md の冒頭に、それが verify モードのファイルの節を指すことと、Step 3 より前にそれを使う回（`--caller` で Step 1・2 から (f) を返して終える回）も先にそのファイルを読むことを書いた。分ける前の SKILL.md は pin を持たなかった。pr-creator の Step 4・4.5 が言い換えている verification.md の形（verify の (e)）と「PR タイプ別ガイドライン」の表に、この PR で pin を置いた（GitHub #539 を同じ PR で扱うのは利用者の決定 2026-11-27）。表は太字の行の下にあって anchor で引けなかったので、snap のファイルで `##### PR タイプ別ガイドライン` の見出しにし、続く「手順」「テーマ撮影」も同じ深さの見出しにして節の範囲を表だけに絞った
- [local] review-guide の Step 5・6・7 の pin を、review-guide-format の節の pin に置き換えた（GitHub #538 / 2026-11-27）。SSoT pin の anchor の区切りに全角括弧「（」が入り、上の review-guide の行で「見出しの anchor では引けない」とした節を括弧の前で切って引けるようになったため（区切りを広げるのは利用者の決定 2026-11-27）。Step 5 は全体の pin を「レポートテンプレート」「ガイド非表示の開始行」の 2 本に、Step 7 は全体の pin を「読み合わせの締め」に、Step 6 は子の見出し 5 本の pin を親の「精読の解説」1 本にした
- [local] 分けた skill の手順の置き場所を「SKILL.md Step N」と呼ぶ参照（code-review の下の 13 行と、番号の無い 3 行）を、「<skill> の Step N（`skills/<skill>/references/step-<番号>.md`）」の形で Step ごとのファイルを指すように直した（GitHub #537 / 2026-11-27 決定）。SKILL.md に見出しと Read の行が残るので辿れば着くが、project-hub を分けたときに同じ呼び方を節ごとのファイルの場所に直した形にそろえた。SKILL.md に残したもの（入口の条件・見出し）を指す行は数えない
- [→ADR候補] 大きい SKILL.md は phase ごとに references へ分け、`SPLIT_SKILLS` に載せて上限と鎖を強制する（他の skill を分けるときもこの形に揃える）

## 未解決事項 (open)

- 解決済み（2026-11-27。#447 の表の 7 本をすべて (a) で分けた）: 残りの大きい SKILL.md（42 KB 超の 7 本）を分けるか。(a) 1 本ずつ分けて `SPLIT_SKILLS` に足す: 読み切れない問題が消えるが作業量が大きい / (b) 上限だけ緩く全体に掛ける: 分けなくても通る。方向性は (a)。確定タイミング: #426 の 2 本目のマージ後に follow-up の Issue で決める
  - 2026-11-19: follow-up は GitHub #447。(a) で 1 本ずつ別の PR にして進め、1 本目の review は分けた（設計判断ログの review の行）。残りの 6 本は #447 で 1 本ずつ決める
  - 2026-11-23: 2 本目の hub を分けた（設計判断ログの hub の行）。残りは 5 本
  - 2026-11-24: 3 本目の review-guide を分けた（設計判断ログの review-guide の行）。残りは 4 本
  - 2026-11-25: 4 本目の pr-creator を分けた（設計判断ログの pr-creator の行）。残りは 3 本
  - 2026-11-26: 5 本目の start を分けた（設計判断ログの start の行）。残りは 2 本
  - 2026-11-26: 6 本目の living-spec を分けた（設計判断ログの living-spec の行）。残りは ui-verify の 1 本
  - 2026-11-27: 7 本目の ui-verify を分けた（設計判断ログの ui-verify の行）。#447 の表の 7 本はすべて分け終えた
- living-spec の `references/subcommands/*.md` と SKILL.md の W2・Phase 0、living-spec-maintain の check-rules.md が言い換えている format-spec.md の節に SSoT pin を置くか（project-hub を `docs/ssot-pin.md` の適用範囲に入れるかも含む）。分ける前から pin は 0 本で、分割で確認の範囲から外れた言い換えは無い。確定タイミング: 未定（GitHub #447 の PR では決めない / 2026-11-26）

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
