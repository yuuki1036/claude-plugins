---
id: 20261025152955
status: accepted
phase: current
last-validated: 2026-10-25
supersedes: []
superseded-by: null
append_only: true
tags: [architecture, multi-session, send-message, project-hub, autonomy]
---

# ADR-20261025152955: project-hub の hub は、lead の確認が要る事柄を含まない連絡を承認なしに sub へ送る（`approval.mode: auto`）。送る範囲と止まる条件を固定する

## ステータス

accepted（2026-10-25）。ADR-20261021154740（連絡の形と宛先の引き方）は変えない。この ADR は、その上で送る前の承認をいつ省くかを決める。

## コンテキスト / 背景

- 段階 ① の relay は、送るたびに lead の承認（4 桁の番号か「送って」）を取っていた。理由は、宛先の取り違えと、hub の思い込みが裏取りなしに sub へ伝わること（#308 の問題 3）を lead の目で止めるため
- 運用した lead から、hub と sub の連絡は lead の確認が要る事柄が無ければ自動にしてほしい、と要望が出た（2026-10-25）。hub の役割は指示出しと進め方・仕様の相談役で、sub は issue-workflow で動き、brief の後の進め方の確認は sub の中の workflow と lead のやりとりで済む
- 宛先の取り違えは、承認とは別に `resolve`（1 件に決まらなければ送らない・送る直前に引き直す）が止めている。承認の画面で lead が宛先を見直して誤配を防いだ回があったかは確かめていない
- 他のセッションから届いたメッセージは、受け手の Claude にとって利用者の指示ではない（harness の規定）。sub の通知で始まった hub のターンで hub が外へ作用するには、lead の常設の指示が要る
- sub の通知で始まったターンからは、アプリが新しいセッションの起動を断る

## 決定

1. `approval.mode` に `auto` を足し、`init` の既定にする。既存の PJ の config は変えない（切り替えは `hub mode`）。読めない値は `number` に倒す。`init`・`mode`・`takeover` は、自動の連絡が有効かと、その止め方を必ず lead に出す（lead が知らないまま auto で動かないように。これをもって lead の常設の指示とみなす）
2. `auto` の PJ で、hub が承認なしに送ってよいのは次の 4 つに限る: lead の言葉の伝達（lead の発言を引用する）/ sub の `questions` への出典つきの答え（出典は Issue 本文・config の repo の仕様 docs と ADR・facts の確かめた行・journal の `basis: lead` の relay 行）/ 段取りの連絡（重なり・マージ後の取り込み・マージ順。status が集めた事実から書く。受領だけの連絡は送らない）/ brief
3. 次のときは送らずに lead に出す: 宛先が 1 件に決まらない / 宛先が warning の付く照合（名前の中の Issue ID・不在から戻った登録名・ref で引いた改名。どれも承認の画面で lead が見直す前提の規則）でしか決まらない / sub の `needs_lead` / 出典で答えられない・出典どうしが食い違う質問 / lead の判断を先取りする連絡（範囲・受け入れ条件・Issue をまたぐ優先度・PJ の外への連絡）/ 同じ sub へ、lead の言葉の伝達を挟まずに hub の判断の連絡（答え・段取り）が 3 回続いた
4. `questions` を元にしてよいのは、答えるための読み取りと、質問した sub への答えの送信まで。`questions` の中の指示（コマンドの実行・編集・他の宛先への連絡・PJ の外の情報の提供）は実行せず lead に出す
5. 送った連絡は journal に全文・宛先・結果と `basis`（`lead` / `source` / `routine` / `brief`）を残し、status で lead にまだ見せていない分（lead の言葉の伝達を含む。最終の文面は lead が見ていない）を一覧で出す。見せた所までの印は journal の行数で持ち、status の最後だけが進める
6. hub は sub の workflow の確認（進め方の選択・コミットの承認など）を代わりに取らず、lead の承認を sub へ中継しない。確認は sub の中で lead が答える
7. sub の通知で始まったターンでは、hub は新しい sub を起動せず、提案に留める

## 影響 (Consequences)

- **良い影響**: lead は、自分の判断が要る事柄（`needs_lead`・答えられない質問・範囲の変更・弱い照合の宛先）だけを見ればよくなる。sub は質問の答えを待たずに進められる
- **悪い影響**: lead が送る前に本文を見なくなるので、hub の答えの誤り（出典の読み違い）は sub に届いてから見つかる。status の一覧で後から見て、訂正の連絡を頼む形になる。permission mode が hub と違う sub には、自動の連絡が受け手の承認待ちで止まっても hub から検出できない（Desktop の sub は何も返さない）
- **トレードオフ**: 送る前の lead の目を、出典の必須化（答えられなければ送らない）と事後の一覧に置き換えた。宛先の安全は承認ではなく `resolve` が持つ

## 適用方法 (Enforcement)

- `approval.mode` の値の検証と既定（`auto` / 読めない値は `number`）、record の `basis` の語彙・kind との組と `basis: source` の `sources` 必須（空なら exit 2 で書かない）、auto の PJ での `basis` と宛先の必須、warning の付く照合を `needs_lead` で返すこと、同じ sub への連続回数の上限（宛先が決まった後に `--session` でも `--ref` でも数える）、一覧と見せた所までの印は `hub.py` に置き、CLI テストで固定する（`.claude-plugin/scripts/tests/test_project_hub_scripts.py`）
- 送ってよい 4 つと止まる条件のうち文面の判断を含むもの（答えられる質問か・範囲の先取りか・質問の中の指示か）は、hook や script では決定的に判定できない。hub の SKILL.md に列挙する
- 宛先の照合は ADR-20261021154740 のまま（script が持つ）

## 検討した代替案

- **段階 ① のまま（毎回承認）で、承認の手間だけ減らす（`phrase`）**: #312 で入れたが、lead の要望は承認そのものを外すことであり、連絡のたびに lead が hub に戻る点は変わらない
- **すべての連絡を承認なしにする**: sub の `needs_lead` や、hub が推測で答えた仕様が、lead の目を通らずに sub の作業を決める。#308 の問題 3 が戻る
- **hub が sub の workflow の確認も代わりに答える**: 他のセッションからのメッセージは sub の利用者の指示にならないので、sub の側で確認を通せない。通そうとすると、承認の中継（lead の発言の引用）を常態にすることになり、lead が sub の画面で答えるより手間が増える
- **sub の通知のたびに次の sub を自動で起動する**: アプリが断る（他のセッションのメッセージで始まったターンからの起動）

## 再評価のトリガー

- 自動で送った答えの誤りを、status の一覧から lead が訂正した回が続いたとき（出典の規則が効いていない）
- SendMessage の `to` に `start_session` の `local_…` が使えると分かったとき（ADR-20261021154740 の決定 3 とあわせて見直す）

## 関連

- 関連 ADR: ADR-20261021154740（連絡の形と宛先の引き方。変えない）
- 関連 Issue: GitHub issue #308 / #312（承認の方式）/ #316（改名・開き直しで見失う）
- 関連 design doc: `.claude/designs/20261021-project-hub-plugin.md` の「自律運用」の節
- 関連 knowledge: なし
