---
id: 20261027014506
status: accepted
phase: current
last-validated: 2026-10-27
supersedes: []
superseded-by: null
append_only: true
tags: [project-hub, tracker, approval]
---

# ADR-20261027014506: project-hub の hub がトラッカーに書くかを PJ ごとの設定にし、書くときは毎回 lead の承認を取る

## ステータス

accepted（2026-10-27）

## コンテキスト / 背景

- hub の SKILL.md は「hub はトラッカーに書かない（起票・更新は issue-workflow か人間）」と決めていた。判断の正本（Issue 本文）を hub が直接書き換えると、hub の思い込みが正本に入るのを防げないため
- 実際の運用では、利用者が承認したうえで hub に Issue の起票・本文の直しを頼む（sub の結果を実装 Issue に反映する、など）。そのたびに SKILL.md の決まりと利用者の指示が食い違っていた（GitHub issue #331）
- トラッカーの API は、更新の応答に古い本文を返すことがある。それを「反映されていない」と取り違えて送り直すと、同じ内容が二重に入る（同 issue の補足）

## 決定

1. config に `tracker_write` を持つ。`never`（既定）は今までどおり書かない。`with_approval` は、hub が lead の承認を取ってトラッカーに書く。無い・読めない値は `never` として扱う（緩い側に倒さない）
2. `with_approval` でも、書くたびに文面の全文を lead に見せ、本文を出した**後**の lead 自身の発言で承認を取る。送る前の承認の方式（`approval.mode`）が `auto` でもこの承認は省かない。自動の連絡（sub への連絡）と違い、トラッカーは PJ の外の人も読む正本だから
3. 書いた後は、書き込みの応答ではなく、読み直した本文で反映を確かめる。反映が見えなくても送り直さず、もう一度読む
4. 書いた記録は journal に `tracker` の kind で残す（`hub.py record --kind tracker`）。`tracker_write` が `never` の PJ では記録も弾く
5. tracker `local`（issue-workflow の local backend）では `with_approval` でも書かない。起票の採番と Issue ファイルの本文は issue-workflow の持ち物で、複数のセッションが書くと番号がぶつかる

## 影響 (Consequences)

- **良い影響**: 利用者が hub に書かせたい PJ で、SKILL.md と指示の食い違いがなくなる。既定は `never` のままなので、設定しない PJ の挙動は変わらない
- **悪い影響**: hub が正本を書ける PJ では、hub の思い込みが正本に入りうる。毎回の承認と全文の提示でしか防げない
- **トレードオフ**: 運用の手間（書くのを issue-workflow や人間に回す）と、正本を hub が書くリスクを、PJ ごとに lead が選べるようにした

## 適用方法 (Enforcement)

- 設定の読み方（無い・読めない値は `never`）と、`never` の PJ・tracker `local` の PJ で `record --kind tracker` を弾くこと（`local` では `set-tracker-write --mode with_approval` も弾く）は `project-hub/scripts/hub.py` に置き、CLI テストで固定する（`.claude-plugin/scripts/tests/test_project_hub_scripts.py` の `TrackerWriteTest`）
- 承認の取り方・読み直しの確かめ方は Claude の手順（hub の SKILL.md の「トラッカーへの書き込み」）で守る。文面と承認の判断を含むので hook では決定的に判定できない

## 検討した代替案

- **SKILL.md の「書かない」のまま**: 利用者の運用と毎回食い違う
- **`with_approval` のときは `approval.mode` に従う（auto なら承認なし）**: トラッカーは PJ の外の人も読む正本で、sub への連絡と同じ扱いにできない
- **常に書けるようにする**: 設定しない PJ の挙動が変わる。正本を書く判断は PJ ごとに lead が選ぶべき

## 関連

- GitHub issue #331
- ADR-20261025152955（自動の連絡。sub への連絡の承認の扱い）
- `.claude/designs/20261021-project-hub-plugin.md`
