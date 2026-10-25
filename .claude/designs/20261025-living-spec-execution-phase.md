---
id: 20261025-living-spec-execution-phase
title: living spec を実行中も使い続ける — phase・先送り・関連 Issue
status: draft
phase: current
last-validated: 2026-10-25
supersedes: []
superseded-by: null
issue: "GitHub issue #320"
spec: null
adrs: []
tags: [living-spec-workflow, format-spec, phase, deferral]
---

# living spec を実行中も使い続ける — phase・先送り・関連 Issue

## TL;DR

仕様表に `phase` と `関連 Issue` の 2 列を足し、frontmatter の `current_phase` で今の phase を宣言する。今の phase より後の phase と `先送り` の行は「先送り」として、maintain 段 6 の塩漬け判定から外し、status は phase ごとの収束率と先送りの件数を出す。確定の項目を覆す Decision を書くときは、その項目の関連 Issue を出す。旧 4 列の表はそのまま読め、`spec --upgrade` で 6 列にする。

## 背景 / 課題

living spec は「Issue 化する前の設計収束ドキュメント」で、到達点に着いたら閉じる作りになっている。実際の PJ では、確定した項目を Issue に切り分けた後にも決定が 12 件増え、到達点に着いた後も使い続けた（#320 / #322）。

- 確定の項目が実装中に覆ったとき、その項目を元にした Issue を引く手段が無い（本文に Issue ID を書き添えるだけ）
- phase 2 へ回す項目を表せない。確度（3 値）でも「スコープ外」（やらないと決めた）でもない
- 先送りした `未定` / `方向性(仮)` の行を、maintain 段 6 が塩漬けとして出し続ける

## ゴール / 非ゴール

- ゴール: 仕様表の行が phase と関連 Issue を持てる。先送りを表せ、段 6 と status がそれを数え分ける。確定を覆す Decision から関連 Issue に辿れる
- 非ゴール: 関連 Issue を Issue の状態（仕掛中・未着手・完了）で分けること（トラッカーを読むのは project-hub。#322 の波及で扱う）。Issue の実在の検証（living spec はトラッカーを読まない）

## 確定した前提

- 仕様表のヘッダは段 1 が完全一致で検査している（`format-spec.md` 2 節・9 節）。列を足すと旧ファイルが段 1 の Critical になるので、旧 4 列のヘッダも受ける
- Decision log の bullet は固定順の 6 つで、append-only（4 節）。既存エントリに bullet を足すことはできない
- 凍結（#245 / 2.1 節）は表全体の宣言を frontmatter に置いた。同じ置き場所の流儀に揃える

## 採用案

### 仕様表（format-spec 2 節）

```
| 項目 | 内容 | 確度 | phase | 関連 Issue | since |
```

- `phase`: `-`（phase を分けていない）/ `P<n>`（n は 1 以上）/ `先送り`（phase を決めずに後へ回す）
- `関連 Issue`: `-` か、Issue ID のカンマ区切り（`ABC-12` か `#308` の形）。トラッカーは問わない
- 旧 4 列の表（`| 項目 | 内容 | 確度 | since |`）も有効。1 つの表の中で 2 つの形を混ぜない（混在は段 1 の Critical）。旧 4 列の表は、どの行も `phase` と `関連 Issue` が `-` とみなす
- 6 列にするのは `spec --upgrade`（全行に `-` を 2 つ挿す）。`spec --phase` / `--issue` は旧 4 列の表では拒否し、`--upgrade` を案内する。凍結中の表は upgrade も拒否する

### 今の phase（format-spec 10 節）

- frontmatter に `current_phase: P<n>` を置ける（任意。`sync` と凍結の 2 行の後ろ）。init は `current_phase: P1` で始める
- **先送りの行** = `phase` が `先送り`、または `current_phase` より大きい `P<n>`。`current_phase` が無いときは `先送り` の行だけ
- `-` の行は今の phase に含める（phase を分けない運用で、全行が `-` のまま使える）
- `current_phase` を進めるのは `spec --phase-advance D<n>`（次の phase へ。経緯の Decision を先に書く）。手で書き換えてもよいが、段 1 が形を検査する

### 先送りは Decision で残す

- `spec <項目> --phase <P<n>|先送り|-> D<n>`。先送りの行になる変更（`先送り` か `current_phase` より後の `P<n>`）には D# を要し、D# の実在を確かめる。今の phase へ戻す・`-` にする変更は D# なしでよい
- D# は表に書かない（表は現在値の一覧で、経緯は Decision log が持つ）。Decision の見出しに項目名を入れるよう案内する

### 関連 Issue

- 行の `関連 Issue` は `spec <項目> --issue <ID,…|->` で置き換える（追記ではなく置き換え。現在値の一覧なので）
- Decision に任意の 7 番目の bullet `- 関連 Issue: (-|ID(, ID)*)` を足す（`関連 OQ` の後ろ。旧エントリは 6 bullet のままで有効）
- `decision` は、確定の行が 1 つ以上あれば「この決定が覆す確定の項目」を選ばせる（multiSelect。先頭は「なし」）。選んだ行の `関連 Issue` を和集合にして D の `関連 Issue` に書き、報告に「覆した項目と関連 Issue」を並べ、各項目を `spec` で直すよう案内する（Issue の状態で分けて lead に出すのは #322）

### status / maintain

- status: phase ごとに収束率（`確定` ÷ その phase の項目数）を出す。`-` の行は今の phase に入れる。先送りの行は「先送り N 件（先送り a / P3 以降 b）」で別に数え、全体の収束率の分母から外す。凍結中は今どおり収束率を出さない
- 段 1: 6 列の行の正規表現・`current_phase` の形・D の 7 番目の bullet を受ける
- 段 6: 先送りの行を塩漬け判定から外し、「段 6: 先送りの N 行を対象外（先送り a / P<n> 以降 b）」を skip した段に出す
- 段 8: 現在地サマリに今の phase と、その phase の到達点が書かれているかを見る

### 寿命（template と SKILL）

- 「到達点に着いたら閉じる」を「phase ごとに到達点を持ち、着いたら `current_phase` を進める。全 phase を終えたら閉じる」に書き換える。現在地サマリの 1 行目は「今の phase の到達点」
- 「進め方フェーズ」に phase ごとの到達点を書く（P1 / P2 …）

## 検討した代替案

- **表の外で phase と関連 Issue を宣言する**（新しい節「## 実行」に項目名をキーにした表）: 表の契約に触れないが、項目名の書き換えで対応が切れ、行の状態が 2 か所に分かれる。利用者に確認して採らなかった
- **確度に 4 つ目の値（先送り）を足す**: #245 と同じ理由で採らない（3 値の契約と段 1 の正規表現を変え、先送りした時点の確度が失われる）
- **D# を表のセルに残す**（`P2 (D12)` のように）: セルの正規表現が複雑になり、現在値と経緯が混ざる

## 未解決事項 (open)

- 先送りの D# は表に残らないので、どの Decision で先送りしたかは Decision log を読んで辿る（段 3 の相互参照の対象にはならない）。確定タイミング: #322 の統合で、決定と経緯を ID で紐付けるときに見直す

## 実装ブリッジ (Implementation Bridge)

1. `format-spec.md`: 2 節（6 列・旧 4 列・混在禁止）、4 節（任意の 7 番目の bullet）、9 節（正規表現・段 1 の適用範囲）、10 節（`current_phase`）
2. `template.md`: 6 列の表・`current_phase: P1`・現在地サマリと進め方フェーズのコメント
3. `living-spec/SKILL.md`: 寿命の記述、Phase 5（覆す確定の項目と関連 Issue）、Phase 6（`--phase` / `--issue` / `--upgrade` / `--phase-advance`）、Phase 7（phase ごとの収束率・先送り）
4. `living-spec-maintain`: check-rules の段 1・段 6・段 8、SKILL のレポート例
5. README・CHANGELOG・バンプ（minor）

## 関連

- GitHub issue #320 / #322（project-hub との統合）/ #245（仕様表の凍結）
