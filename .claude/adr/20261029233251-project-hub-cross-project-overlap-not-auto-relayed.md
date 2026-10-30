---
id: 20261029233251
status: accepted
phase: current
last-validated: 2026-10-29
supersedes: []
superseded-by: null
append_only: true
tags: [project-hub, cross-project, approval]
---

# ADR-20261029233251: project-hub の hub は、別 PJ との重なりを自動の連絡で sub に送らず lead に出す（brief の「重なりに注意」には載せる）

## ステータス

accepted（2026-10-29）

## コンテキスト / 背景

- ADR-20261025152955 の決定 2 は、段取りの連絡（重なるファイルの注意・マージ順）を lead の承認なしに sub へ送ってよいものとした。hub の SKILL.md の「自動の連絡」の表は、段取りを「重なるファイルの注意（`worktrees`）…status が集めた事実から書く」としている（hub の SKILL.md:84）
- PJ 横断（ADR-20261029233229）で、status が別 PJ との重なりも集めるようになる。この行を字面どおりに読めば、別 PJ 由来の重なりも承認なしに自分の sub へ送ってよいことになる
- 別 PJ の在席は、その PJ の hub が最後に status を回した時点の記録で、自分の PJ より古いことがある（`presence.json` を書くのはその PJ の hub の `cmd_presence` だけで、require_hub を通る / `project-hub/scripts/hub.py`）。ADR-20261025152955 の決定 3 は「PJ の外への連絡」を、lead の判断を先取りする連絡として止めている

## 決定

1. 自動の連絡の「段取りの連絡」は、自分の PJ の `worktrees` から書くものに限る
2. 別 PJ との重なりは、自分の sub へも自動の連絡では送らない。status で lead に出し、調整が要るかは lead が決める（相手の hub に伝えるのも lead）
3. brief の「重なりに注意」には別 PJ との重なりも載せる。ただし、その行がある brief は、`auto` の PJ でも送る前に全文を lead に見せて承認を取る（start でも既にある sub への brief でも。`auto` の brief は本来承認なしに送るが、この行だけは PJ の外の状態に基づくので lead を通す）。載せるときは在席の記録の時点を添え（記録が無ければ「在席は未確認」）、判定できないものは「重なり不明」と書く。brief を受けた sub には、別の PJ の sub へ直接連絡せず、調整が要りそうなら needs_lead に書くよう伝える

## 影響 (Consequences)

- **良い影響**: 古い在席の記録による誤った警告が、lead の知らないうちに sub へ届かない。ADR-20261025152955 の決定 3（PJ の外への連絡を止める）との食い違いがなくなる
- **悪い影響**: 別 PJ との重なりの注意を、作業中の sub へ届けるには lead の一手が要る。`auto` の PJ でも、別 PJ との重なりの行がある brief は承認を待つ
- **トレードオフ**: 重なりを早く sub に届けることと、PJ の外の状態に基づく判断を lead に通すことを比べ、後者を取った。brief は渡す時点で lead が全文を見るので載せる

## 適用方法 (Enforcement)

- hub の SKILL.md の「自動の連絡」の表と brief の文言を、文言契約テストで固定する（`.claude-plugin/scripts/tests/test_project_hub_scripts.py` の `CrossProjectTextTest`。段取りの行が自分の PJ の `worktrees` に限られていること、別 PJ の行がある brief は `auto` でも承認を取ること、sub に直接連絡させないこと）
- 送るかの判断は Claude の手順で守る。relay の `--basis routine` の記録には、送った文面の出典（別 PJ か）が残らないので、hook で決定的には判定できない

## 検討した代替案

- **別 PJ の重なりも段取りとして自動で送る**: 重なりが早く届くが、古い在席の記録による誤った警告も承認なしに届く。ADR-20261025152955 の決定 3 の「PJ の外への連絡」に当たる
- **brief にも載せない（status で lead に出すだけ）**: 送る文面は自分の PJ の事実だけになるが、新しい sub が別 PJ と同じファイルを触り始めるのを防ぐ最初の機会を逃す
- **brief には載せ、`auto` なら承認なしに送る**: start の 4 で全文を見せるのは送った後で、既にある sub への brief には全文を見せる手順が無いので、古い在席の記録に基づく注意が lead を通らずに届く

## 関連

- 関連 ADR: ADR-20261025152955（自動の連絡。決定 2・3 の解釈をこの ADR が足す）、ADR-20261029233229（PJ 横断は読むだけ）
- 関連 Issue: なし
- 関連 design doc: `.claude/designs/20261029-project-hub-cross-project-view.md`
- 関連 knowledge: なし
