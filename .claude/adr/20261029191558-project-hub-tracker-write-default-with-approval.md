---
id: 20261029191558
status: accepted
phase: current
last-validated: 2026-10-29
supersedes: ["20261027014506"]
superseded-by: null
append_only: true
tags: [project-hub, tracker, approval]
---

# ADR-20261029191558: project-hub の hub init の tracker_write の既定を with_approval にする（書くたびの承認と local の扱いは据え置く）

## ステータス

accepted（2026-10-29）

## コンテキスト / 背景

- ADR-20261027014506 は、hub がトラッカーに書くかを config の `tracker_write` にし、既定を `never` にした。設定しない PJ の挙動を変えないためと、正本を書く判断を PJ ごとに lead が選ぶため
- lead から、hub の既定を、トラッカー（Linear など）に起票できる側にしたいと要望があった（2026-10-29）。既定が `never` だと、hub に書かせる PJ は作るたびに `tracker-write with_approval` へ切り替える必要がある
- 同時に、sub の `follow_ups` を起票の候補として lead に出す手順を足した（`.claude/designs/20261021-project-hub-plugin.md` の「実装で決めたこと（init の既定と follow-up の起票の候補・2026-10-29）」）。既定が `never` のままだと、新しく作った PJ ではこの手順が動かない

## 決定

1. `hub init` で `--tracker-write` を指定しなかったときの既定を `with_approval` にする。tracker `local` の PJ だけは `never` にする（`local` に `with_approval` を指定した init は exit 3 で止める）
2. config に `tracker_write` が無い・読めない値のときは、これまでどおり `never` として扱う（既にある PJ の挙動は変えない。緩い側に倒さない）
3. ADR-20261027014506 の決定 2〜5 は変えない。`with_approval` でも書くたびに全文を lead に見せ、本文を出した**後**の lead 自身の発言で承認を取る（`approval.mode` が `auto` でも省かない）。書いた後は読み直して確かめ、journal に `tracker` の kind で残し、tracker `local` では書かない
4. lead が hub に書かせたくない PJ は、init の `--tracker-write never` か、後から `tracker-write never` で切り替える

## 影響 (Consequences)

- **良い影響**: 新しく作った PJ で、lead が設定を切り替えずに hub へ起票や本文の直しを頼める。follow-up を起票の候補として出す手順が、既定のまま動く
- **悪い影響**: 新しい PJ では、hub が正本を書ける状態から始まる。hub の思い込みが正本に入るのを防ぐのは、書くたびの全文の提示と lead の承認だけになる（旧 ADR の「悪い影響」が、設定しない PJ にも及ぶ）
- **トレードオフ**: 「PJ ごとに lead が書かせるかを選ぶ」（旧 ADR の却下理由）と、切り替え忘れの手間を比べた。書くたびの承認は残るので、lead が知らないまま書かれる経路は増えない。選ぶ機会は init の時点から、書く時点の承認へ移る

## 適用方法 (Enforcement)

- 既定の決め方（未指定なら `with_approval`、tracker `local` は `never`、`local` に `with_approval` は exit 3）と、config に値が無い・読めないときの `never` は `project-hub/scripts/hub.py` に置き、CLI テストで固定する（`.claude-plugin/scripts/tests/test_project_hub_scripts.py` の `TrackerWriteTest.test_init_defaults_to_with_approval_except_for_a_local_tracker` / `test_an_unknown_value_falls_back_to_never` / `test_init_can_forbid_writing`）
- 書くたびの承認・読み直しの確かめ方は、旧 ADR と同じく Claude の手順（hub の SKILL.md の「トラッカーへの書き込み」）で守る。文面と承認の判断を含むので hook では決定的に判定できない

## 検討した代替案

- **既定を `never` のままにする（ADR-20261027014506 の決定 1）**: 設定しない PJ の挙動は変わらないが、hub に書かせる PJ は作るたびに切り替えが要り、切り替えていない PJ では follow-up の起票の候補が動かない
- **config に値が無い既存の PJ も `with_approval` に倒す**: 既にある PJ の挙動が lead の知らないまま変わる。旧 ADR の「緩い側に倒さない」に反する
- **init で毎回 lead に聞く**: 後から `tracker-write` で直せる値で、init の確認を増やすほどの判断ではない。書くたびの承認で lead は内容を見る

## 関連

- 関連 ADR: ADR-20261027014506（この ADR で置き換えた。決定 2〜5 は引き継ぐ）、ADR-20261025152955（自動の連絡。sub への連絡の承認の扱い）
- 関連 Issue: GitHub issue #331（トラッカーへの書き込みを PJ ごとの設定にした元の issue）
- 関連 design doc: `.claude/designs/20261021-project-hub-plugin.md`
- 関連 knowledge: なし
