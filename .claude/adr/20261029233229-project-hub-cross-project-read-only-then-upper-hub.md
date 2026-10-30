---
id: 20261029233229
status: accepted
phase: current
last-validated: 2026-10-29
supersedes: []
superseded-by: null
append_only: true
tags: [project-hub, cross-project, orchestration]
---

# ADR-20261029233229: project-hub で PJ をまたぐ連絡は、hub どうしの送受信ではなく、読むだけの横断と、条件を満たした後の上位の hub で扱う

## ステータス

accepted（2026-10-29）

## コンテキスト / 背景

- hub は PJ ごとに 1 つで、自分の PJ の sub しか見ていない。同じ repo を触る別 PJ の sub との重なりや、別 PJ で決まったことに気づけない
- 利用者から「hub to hub の連絡経路」の要望があり、検討の途中で「並列で通信するより上位のオーケストレーションがいた方がいいか」という問いが出た（2026-10-29）
- 全 PJ の状態は同じルート（`~/.claude/project-hub/`）の下にあり、どの hub からも別 PJ のファイルを読める（`project-hub/scripts/hub.py` の `root()`）
- 同時に動く PJ の数は、このマシンの記録だけでは測れない（主に使うマシンが別）

## 決定

1. hub どうしが直接送り合う経路（相手の inbox に置いて知らせる・SendMessage で hub に送る）は作らない
2. まず、どの hub からも別 PJ の状態を読むだけのコマンド（`hub.py cross`）を足し、同じ repo を触る別 PJ の重なりと新しい決定を、brief と status で lead に見せる。どこまで見せたかの印は、`sent` と同じく journal の行数で持ち、status の最後だけが進める
3. PJ を束ねる上位の hub（PJ の hub を sub として扱う）は、記録から測れる進む条件（active な PJ の数・横断で新しい重なりか決定が出た回数・lead が手で伝えた回数）を満たしてから設計する
4. 上位の hub を作るときは、PJ をまたぐ問い・引き渡しはそこが担い、並列の経路は足さない

## 影響 (Consequences)

- **良い影響**: 重なりの警告と決定の共有が、セッションを増やさずに手に入る。経路が PJ の数の 2 乗で増えない。hub どうしの往復が lead の知らないところで続く経路が無い
- **悪い影響**: PJ をまたぐ問い・Issue の引き渡しは、上位の hub ができるまで lead の手作業のまま。別 PJ の在席は、その PJ の hub が最後に status を回した時点の記録なので、古いことがある
- **トレードオフ**: すぐに全部の場面を解くこと（上位の hub を今作る）と、PJ が 2 つまでの間に増えるセッション・伝言の段数を比べ、読むだけで解ける場面を先にした

## 適用方法 (Enforcement)

- `hub.py cross` が何も書かないこと（自分と別 PJ のディレクトリの中身が呼ぶ前後で変わらない）と、`--mark` だけが require_hub を通って印を進めることは、`project-hub/scripts/hub.py` に置き、CLI テストで固定する（`.claude-plugin/scripts/tests/test_project_hub_scripts.py`。実装は design doc の実装ブリッジ）
- 「hub から別 PJ の sub・hub へ送らない」は Claude の手順（hub の SKILL.md）で守る。送信は SendMessage / relay の判断を含むので、hook で決定的には判定できない。`hub.py resolve` の `--session`（Issue ID で引き直す経路）は別の PJ の名前を候補から外すが、`--ref`（lead が ListAgents の候補から選ぶ経路）は別の PJ の sub も候補に出す。そこで別の PJ の sub を選ばないのは lead の判断で守る
- 上位の hub に進む判断は、`cross` の行を jq で集計して行う（集計の手順は design doc の段 2）

## 検討した代替案

- **上位の hub を今作る**: 重なり・決定・問い・引き渡し・マージ順をまとめて解けるが、常駐するセッションが 1 つ増え、伝言の段数が増える（sub → hub → 上位 → hub → sub）。PJ が 2 つまでの間は見合わない。report は Issue 単位で、PJ の hub 向けの形も要る
- **hub どうしの送受信（並列）**: 問い・引き渡しも解けるが、経路が PJ の数の 2 乗で増え、上位の hub を作るときに二重になる
- **何もしない（lead が手で伝える）**: 変更は要らないが、重なりの警告は lead が両方の hub を見比べないと出ない

## 関連

- 関連 ADR: ADR-20261025152955（自動の連絡。見せた所までの印）、ADR-20261027002221（Desktop の hub は sub の会話の ID へ送る）
- 関連 Issue: なし
- 関連 design doc: `.claude/designs/20261029-project-hub-cross-project-view.md`
- 関連 knowledge: なし
