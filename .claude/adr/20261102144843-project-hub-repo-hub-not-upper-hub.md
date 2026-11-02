---
id: 20261102144843
status: accepted
phase: current
last-validated: 2026-11-02
supersedes: []
superseded-by: null
append_only: true
tags: [project-hub, repo-hub, orchestration]
---

# ADR-20261102144843: project-hub の repo hub は閉じない PJ として扱い、上位の hub の代わりにしない

## ステータス

accepted（2026-11-02）

## コンテキスト / 背景

- 個人開発のように PJ を切らずに 1 つの repo で作業を続けるとき、PJ を前提にした project-hub は init・close・起票の持ち主・PJ の自動判定の 4 か所で止まる。そこで、PJ を定義せずに repo を束ねる常設の hub（repo hub）を足す（`.claude/designs/20261102-project-hub-repo-hub.md`）
- PJ を束ねる上位の hub は、記録から測れる進む条件を満たしてから設計すると決めてある（ADR-20261029233229 の決定 3）。PJ をまたぐ問い・引き渡しは上位の hub が担い、並列の経路は足さない（同じ ADR の決定 4）
- repo hub が同じ repo の PJ hub の sub まで抱えると、1 repo 版の上位の hub になる。上位の hub の一部を条件より先に作ることになり、決定 4 が避けた並列の経路が sub の段で生まれる
- cross の `active_projects` は、repo を共有しない PJ も含めた active な PJ の数（`project-hub/scripts/hub.py:1973`）。段 2 の進む条件 1 はこの値で数えるので、閉じない repo hub を repo ごとに置くと、PJ が同時に動いているかと無関係に条件を満たす
- 閉じた PJ は、config.json の `status` を手で `active` に戻せば再開できる（`project-hub/skills/hub/SKILL.md:41`・`:314`）。`is_active` は `status == "active"` だけを見る（`hub.py:341`）ので、「休止」の状態を別に足しても、実行時の働きは closed と同じになる

## 決定

1. repo hub は、config に `repo_hub: true` を持つ PJ とする。範囲は 1 つの repo の open Issue のうち、同じ repo のどの PJ の範囲にも入らないもの
2. repo hub も通常の PJ と同じ `close` で止める。新しい status の値は足さない。再開は、今の手での「closed から戻す」を CLI にした `reopen` で行い、すべての PJ で使えるようにする。reopen は、戻す前に共存の検査（決定 5）を掛け、closed の間に別の PJ へ移ったセッションの登録を作業中から外す
3. repo hub は PJ をまたぐ調整（別の PJ の sub・hub への連絡、マージ順の調整、Issue の引き渡し）を受け持たない。上位の hub ができたら、repo hub もほかの PJ と同列の子として登録する
4. cross の `active_projects` の定義を「`repo_hub` を除いた active な PJ の数」に変え、段 2 の進む条件 1 はこの値で数える。新しい欄は足さない（今は repo hub が 1 つも無いので、これまでの journal の cross の行の値は変わらない）。条件 2（新しい重なり・決定）は変えない
5. 範囲を切っていない通常の PJ（github で milestone なし・linear で project なし・local で repo hub と同じ slug）と repo hub は、同じ repo に共存させない。init でも reopen でも、後から有効にする方を止める

## 影響 (Consequences)

- **良い影響**: repo hub は今の仕組み（inbox・宛先の照合・start）にそのまま乗る。上位の hub を設計するとき、repo hub を PJ と同じ形で扱える。段 2 に進むかの判断が、repo hub の数に引っ張られない。通常の PJ も CLI で再開できるようになる
- **悪い影響**: 同じ repo の PJ hub と repo hub の sub の重なりは、上位の hub ができるまで lead が手で調整する。範囲を切らない PJ は repo hub と共存できず、milestone などで範囲を切る必要がある。`active_projects` を総数として読む人がいたら、定義の変更に気づかない
- **トレードオフ**: repo hub に 1 repo 内の PJ をまたぐ調整まで持たせて今すぐ解くことと、上位の hub の構想（条件を満たしてから作る）と役割を分けておくことを比べ、後者を選んだ

## 適用方法 (Enforcement)

- 次は `project-hub/scripts/hub.py` で機械強制し、CLI テスト（`.claude-plugin/scripts/tests/test_project_hub_scripts.py`）で固定する: 範囲を切らない PJ と repo hub の共存を init と reopen で exit 3 にする / reopen が移ったセッションを作業中から外す / cross の `active_projects` が `repo_hub` を数えない
- 「repo hub から別の PJ の sub・hub へ送らない」は、今の PJ hub と同じく hub の SKILL.md の手順で守る。送信は SendMessage と relay の判断を含み、hook で決定的に判定できない（ADR-20261029233229 の適用方法と同じ）。repo hub が別の PJ の sub を自分の sub として持つ経路は、二重登録の禁止（ADR-20261102144903）で塞ぐ
- 段 2 に進むかの集計は、今と同じく cross の行を jq で数える（欄の名前は変わらない）

## 検討した代替案

- **repo hub を 1 repo 版の上位の hub にする**（同じ repo の PJ hub を束ねる）: 段 2 の条件を満たす前に上位の hub の一部を作ることになり、ADR-20261029233229 の決定 3 に反する。上位の hub が repo 版と全体版の 2 種類に割れる
- **repo hub を別のプラグインにする**: プラグイン間の依存が禁止で project-hub の登録を読めず、二重登録を止められない。宛先の照合・inbox・在席の確認を複製することになる
- **repo hub だけに pause / resume（新しい status）を足し、close を拒む**: paused と closed は実行時の働きが同じで、違いが名前だけになる。close を拒む理由にしていた「閉じると作り直せない」は誤りだった（config を手で戻せる）
- **`active_pj_hubs` を新しい欄として足す**: 読む側がいない `active_projects` を互換のために残すことになる
- **`active_projects` の数え方を変えず、条件 1 の閾値を上げる**: 閾値が repo hub を置いた repo の数で動き、条件の意味（PJ が同時に何本動いているか）が崩れる

## 関連

- 関連 ADR: ADR-20261029233229（PJ 横断は読むだけ → 上位の hub は条件を満たしてから）、ADR-20261029233251（別の PJ との重なりは自動の連絡に入れない）、ADR-20261102144903（1 セッション 1 PJ の登録と Issue の範囲での振り分け）
- 関連 Issue: なし
- 関連 design doc: `.claude/designs/20261102-project-hub-repo-hub.md`、`.claude/designs/20261029-project-hub-cross-project-view.md`
- 関連 knowledge: なし
