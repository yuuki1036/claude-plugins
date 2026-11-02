---
id: 20261102144922
status: accepted
phase: current
last-validated: 2026-11-02
supersedes: []
superseded-by: null
append_only: true
tags: [project-hub, repo-hub, tracker]
---

# ADR-20261102144922: project-hub の repo hub では、どの tracker でも起票を hub のセッションに集め、sub には起票させない

## ステータス

accepted（2026-11-02）

## コンテキスト / 背景

- 起票の持ち主は、今は tracker によって分かれている:
  - local（issue-workflow の local backend）: 起票は「hub のセッションで lead が issue-workflow を呼んだときだけ」で、sub には起票させない（`project-hub/skills/hub/SKILL.md:72`）。hub 自身は `tracker_write` で書かない（ADR-20261027014506 の決定 5）
  - github / linear: sub が自分で起票してよい（`project-hub/skills/report/SKILL.md:36`）。hub は `tracker_write: with_approval` なら lead の承認を取って書く
- repo hub（ADR-20261102144843）の sub は、Issue が無いと report を置けない（`project-hub/scripts/hub.py:577`）。repo hub で作業を始めるたびに起票が要り、起票の回数が増える
- issue-create は採番を `counter.txt` の Read → +1 → Write で確定し、排他しない（`issue-workflow/skills/issue-create/SKILL.md` の Phase 3）。sub が各自で起票すると、同時の起票で番号がぶつかりうる
- issue-create は Phase 6 で書いた後、Phase 7 でブランチ作成・feature-dev 連携・次のアクションを扱い、feature-dev に引き継がなければ Phase 8 で spec の skill（bdd-spec / design-doc / adr-keeper）を起動しうる（同 :213-301）。hub のセッションでそのまま呼ぶと、hub の checkout でブランチを切るか、repo の仕様 docs を書くことになる。hub は repo の仕様 docs とコードを書かない（hub の SKILL.md:70）
- 利用者の決定（2026-11-02）: 起票は hub に一本化する。既にある Issue への着手は、直接開いたセッションからでもよい

## 決定

1. repo hub がある repo では、どの tracker でも起票を repo hub のセッションに集め、sub には起票させない。sub の follow_ups と利用者の依頼は、hub が起票の候補として lead に出す
2. github / linear の起票は、今の `tracker_write: with_approval` の手順（書くたびに全文を見せて承認を取る）で hub が書く
3. local の起票は、今の「起票の持ち主」（hub のセッションで lead が issue-workflow を呼ぶ）をそのまま使う。ADR-20261027014506 の決定 5（hub は local に書かない）は改めず、`hub.py` の `tracker_write` の検査も変えない。hub は、lead が貼るだけで済む issue-create の起動の 1 行を出す
4. issue-create に「起票だけ」の引数を issue-workflow 側で足す。契約は終わり方で決める（Phase 6 の書き込みで終え、Phase 7 の 2〜4 と Phase 8 に進まない）。承認は Phase 6 の 1 回だけにする。終わりに「起票だけで終えた」ことを 1 行出し、出ていなければ（issue-workflow が古い）hub はブランチ作成の確認を断るよう lead に伝える

## 影響 (Consequences)

- **良い影響**: repo hub の範囲では、起票するセッションが 1 つになり、同時の起票で番号がぶつからない。起票の持ち主が tracker によらず揃う。採番とテンプレートは issue-workflow の持ち物のまま。ADR-20261027014506 は改めずに済む
- **悪い影響**: 直接開いたセッションで Issue の無い作業を始めるには、利用者が hub の会話で起票を頼む往復が要る（hub が無ければ進めない）。issue-workflow に起票だけの引数を足す変更が要る。Issue ファイルを git で追跡している repo では、hub のセッションが書いた Issue ファイルが worktree の sub から見えないので、repo hub の init で gitignore を確かめて止める（design doc の未解決事項 7）。書き手を 1 つにする決まりは文面でしか守られず、利用者が別のセッションで issue-create を呼ぶ経路と discover の経路は塞がない（同 8）
- **トレードオフ**: 起票の手軽さ（どのセッションでも起票できる）と採番の一意性・起票の持ち主の一貫性を比べ、後者を取った

## 適用方法 (Enforcement)

- 「sub に起票させない」は sub 側の手順（紐付けの案内の文面と report の SKILL.md）で守る。sub が issue-create や gh issue create を呼ぶのを hook で止めると、repo hub の無い repo や通常の PJ の作業まで止まる。止めてよいかの判定には PJ の文脈が要るので、機械強制しない
- issue-create の「起票だけ」が Phase 7・8 に進まないことは、issue-workflow 側のテストか eval で確かめる（`.claude-plugin/scripts/tests/` で扱えなければ、その旨を Issue 2 に書く）
- 採番の衝突そのものは issue-create の排他の無さによる。この ADR は、起票するセッションを 1 つにすることで避ける。衝突を 1 回でも観測したら、issue-workflow 側で排他を入れる（design doc の未解決事項 8）

## 検討した代替案

- **sub が各自で起票する（今の github / linear と同じ）**: local では同時の起票で採番がぶつかる。tracker によって起票の持ち主が分かれたままになる
- **ADR-20261027014506 の決定 5 を repo hub に限って改め、hub.py の `tracker_write` で local にも書く**: hub.py は Issue ファイルを書かないので、その値は何も強制しない。local の起票は、既にある「起票の持ち主」の決まりで hub のセッションに集まっている（当初この案を採ったが、hub の SKILL.md:72 を読み落とした前提に立っていた）
- **`hub.py` が Issue ファイルと `counter.txt` を直接書く**: 採番とテンプレートを issue-workflow から複製することになる。CLAUDE.md は、プラグイン間の依存禁止の下で複製が出るのを、分割単位の誤りの合図としている
- **issue-create に排他を入れ、どのセッションでも起票できるようにする**: 採番を LLM の Read / Write から機械に移す大きな変更で、repo hub の範囲を超える。衝突を観測したら issue-workflow 側で扱う

## 関連

- 関連 ADR: ADR-20261027014506（tracker_write の opt-in。決定 5 はこの ADR でも有効のまま）、ADR-20261029191558（tracker_write の既定を with_approval にする）、ADR-20261102144843（repo hub は閉じない PJ）、ADR-20261102144903（1 セッション 1 PJ の登録）
- 関連 Issue: なし
- 関連 design doc: `.claude/designs/20261102-project-hub-repo-hub.md`
- 関連 knowledge: なし
