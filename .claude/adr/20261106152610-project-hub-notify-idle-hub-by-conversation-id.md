---
id: 20261106152610
status: accepted
phase: current
last-validated: 2026-11-06
supersedes: ["20261027002221"]
superseded-by: null
append_only: true
tags: [architecture, multi-session, send-message, project-hub]
---

# ADR-20261106152610: project-hub の sub → hub の通知は、hub が一覧に居なければ hub の会話の ID（local_…）へ送る

## ステータス

accepted（2026-11-06）。ADR-20261027002221 を supersede する。変えるのは決定 4（sub → hub の通知は名前で引く）だけで、決定 1〜3（hub → sub は、Desktop の hub と確かめた登録なら会話の ID へ送る・それ以外は名前で引く・会話の ID 宛てでも ListAgents を引く）はそのまま引き継ぐ。

## コンテキスト / 背景

- GitHub issue #373: hub のセッションが動いていない（アイドルで閉じている）間に sub が report を置くと、通知は毎回 `unresolved`（hub の名前に一致する行が 0 件）になり、hub に届かなかった。1 セッションで 4 回置いて 4 回とも届かず、利用者には「hub に連絡が入っていない」と見えた
- ListAgents は動いているセッションしか並べない。hub の名前は開き直しても変わらないが、止まっている間は一覧に出ないので、名前の規則（ADR-20261027002221 の決定 4）では引けない
- hub.json は hub の会話の ID（`host_session_id`）を持っている。init・takeover・開き直しの付け替えのどれも、Desktop の記録で確かめた値（`verified_host`）しか書かない
- ADR-20261027002221 に記録された 2026-10-27 の実測: プロセスの無い会話への `local_…` 宛ては届き、Desktop が会話を再開した。archive 中の会話には届かず、エラーが返る（黙って捨てられない）。素の CLI から `local_…` 宛ては届かない

## 決定

1. sub → hub の通知は、hub の名前に一致する行が 1 件ならその名前へ送る（今までどおり）
2. 一致する行が 0 件で、次の 2 つがそろうときは hub の会話の ID（`local_…`）へ送る（report の出力は `rule: host_session` と、hub の会話を再開させる旨の `warning`）
   - sub の会話の ID が、Desktop の記録で確かめられた（`verified_host`）
   - hub.json の `host_session_id` が `local_…` の形をしていて、このセッションの会話の ID と違う（hub の会話の中で report を走らせた回は自分宛てになるので送らない）
3. 0 件でどちらかが欠けるときは送らず、`status: absent` で返す。hub を改名した回も一致する行は 0 件で、改名後の行は当て推量しない（2 の条件がそろえば会話の ID へ送り、欠ければ absent）。2 件以上・既定名の `unresolved` とは分け、利用者には「hub の会話が止まっているので、置き直しても届かない。hub の会話を開けば取り込まれる」と伝える

## 影響 (Consequences)

- **良い影響**: hub が止まっていても、report を置くたびに hub に届く。hub の会話が再開して status で取り込める
- **悪い影響**: lead が閉じた hub の会話を、sub の report が再開させる（トークンを使う）。止まっている hub へ送るたびに、利用者にその旨の warning を見せる
- **トレードオフ**: 届くことと、閉じた会話を勝手に再開させないことを天秤にかけ、届く側を取った。report は節目でしか置かないので、再開の回数は report の数で上限が決まる

## 適用方法 (Enforcement)

- 宛先の決め方は `project-hub/scripts/hub.py` の `absent_hub_notify` に置き、CLI テストで固定する（`.claude-plugin/scripts/tests/test_project_hub_scripts.py` の `IdleHubNotifyTest`）。固定する条件: 確かめた Desktop の sub と、会話の ID を持つ hub なら `to` が `local_…` / 子の CLI の sub・会話の ID の無い hub.json・hub 自身の会話では `absent` / 一致する行が 2 件以上なら今までどおり `unresolved` / 一覧に hub が居れば名前へ送る
- SendMessage の `to` に report の出力以外の値を使わないことは、Claude の手順（report の SKILL.md の 5）で守る

## 検討した代替案

- **ADR-20261027002221 の決定 4 のまま（名前で引く）**: hub が止まっている間は、何度置いても届かない（#373 の実測）
- **sub を起動したセッションの ID（start_session のシステム説明に書かれる `local_…`）を宛先にする**: start_session で起動した sub でしか使えない。hub.json の `host_session_id` は、sub がどう起動されたかに関係なく引ける
- **0 件のときは常に会話の ID へ送る（sub が CLI でも）**: 素の CLI からは届かない（2026-10-27 の実測）。届かない宛先を返すより、`absent` で理由を返す
- **hub → sub と同じく、承認なしに送る PJ（`approval.mode: auto`）では送らずに lead に出す**: hub → sub で lead に出すのは、lead が知らないまま sub の会話が動くのを避けるため。sub → hub で再開するのは lead が束ねている hub の会話。送るのは「置いた」の通知だけ（再開した hub は status で取り込むだけ）なので、lead に出すと届かない状態に戻る
- **一覧に hub が居ても会話の ID へ送る**: 名前で届いている経路を変える理由が無い。変更を #373 の範囲（止まっている hub）に閉じた

## 関連

- 関連 ADR: ADR-20261027002221（この ADR が supersede した）/ ADR-20261021154740（report はファイルで置き、SendMessage は通知にだけ使う）
- 関連 Issue: GitHub issue #373
- 関連 design doc: `.claude/designs/20261021-project-hub-plugin.md`
- 関連 knowledge: なし
