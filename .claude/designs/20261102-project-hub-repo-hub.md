---
id: 20261102-project-hub-repo-hub
title: project-hub の repo hub — PJ を定義せず、1 つの repo を常設の hub で束ねる
status: draft
phase: current
last-validated: 2026-11-04
supersedes: []
superseded-by: null
issue: null
spec: null
adrs: [20261102144843, 20261102144903, 20261102144922, 20261105111324]
tags: [project-hub, repo-hub, orchestration]
---

# project-hub の repo hub — PJ を定義せず、1 つの repo を常設の hub で束ねる

## TL;DR

project-hub に、PJ を定義せずに 1 つの repo を範囲にする常設の hub（repo hub）を足す。repo hub は「範囲が repo 全体で閉じない PJ」（config の `repo_hub: true`）として今の仕組み（inbox・宛先の照合・start）に乗せ、同じ repo の PJ hub とは report の時点で Issue の範囲で振り分ける。1 つのセッションは 1 つの PJ にだけ登録させ、repo hub は上位の hub に進む条件の集計から外す。

## 背景 / 課題

project-hub は PJ（Issue 十数件・sub 3〜5 本）を前提にしている。個人開発のように PJ を切らずに 1 つの repo で作業を続けるときは、次の 4 か所で止まる。

1. init で PJ 名・tracker・repos・base を決めないと始められない
2. close で閉じる前提で、repo のように終わりの無い単位を想定していない。閉じた PJ を戻すには config.json を手で直す（hub の SKILL.md:41・:314）
3. tracker が issue-workflow の local backend だと、hub は `tracker_write` で書かない（ADR-20261027014506 の決定 5）。起票は「hub のセッションで lead が issue-workflow を呼んだときだけ」と決まっている（hub の SKILL.md:72）が、github / linear では sub が自分で起票してよい（report の SKILL.md:36）ので、起票の持ち主が tracker によって分かれている
4. 同じ repo を含む active な PJ が 2 つあると、`--project` を付けない report は PJ を決められず exit 1 になる（`hub.py` の `detect_project`）

一方で、milestone を付けずに init すれば status は repo の open Issue を集める（hub の SKILL.md の status 4）。sub の受け取り・宛先の照合・起動は PJ に固有の部分を持たないので、仕組みの大半は repo 単位でもそのまま動く。

PJ を束ねる上位の hub（ADR-20261029233229 の決定 3・4、`.claude/designs/20261029-project-hub-cross-project-view.md` の段 2）の構想もある。repo hub が PJ hub の sub まで抱えると、上位の hub が受け持つはずの役割（PJ をまたぐ調整）と重なる。

## ゴール / 非ゴール

- **ゴール**:
  - PJ を定義せずに、repo を常設の hub で束ねられる（起動時に聞くことを、決められないものだけにする）
  - repo hub の sub は、編集するならブランチの上で編集し、重なりの判定が働く
  - 同じ repo で PJ hub と共存でき、1 つのセッションがどの hub に属するかが一意に決まる
  - repo hub の無い repo では、今の挙動を変えない（例外: tracker local の PJ の `--milestone` を止める。「実装で決めたこと」）
  - 上位の hub の構想と役割を分ける
- **非ゴール**:
  - 上位の hub（段 2）を作ること。進む条件を満たしてから別の doc で設計する
  - repo hub を上位の hub の代わりに使うこと。PJ をまたぐ調整は上位の hub の受け持ちのまま
  - Issue の無い作業・base のブランチの上での編集を repo hub で扱うこと。強制で対象から外す
  - 複数のマシンで 1 つの repo hub を共有すること。今の project-hub と同じくデータはマシンごと
  - journal・登録が増え続ける問題の手当て。運用で症状が出てから入れる（未解決事項 1〜4）

## 確定した前提

コードと既存の決定から確かめたもの:

- `is_active` は `status == "active"` だけを見る（`project-hub/scripts/hub.py:341`）。closed の PJ は、注入・紐付けの案内・report・cross の数から外れる
- 閉じた PJ は、config.json の `status` を手で `active` に戻せば再開できる（hub の SKILL.md:41「closed から戻す」・:314）。CLI の reopen は無い
- PJ 名に使える文字は `[A-Za-z0-9][A-Za-z0-9._-]*`（`hub.py:91`）。`:` は使えない。同じ名前の config があると、init は takeover を案内して exit 3 になる（`hub.py:822-824`）
- `hub.py` が起動する外部コマンドは git だけで、gh は呼ばない（`hub.py:494-498`）。GitHub の Issue と PR は Claude が gh で取り、stdin で渡す。tracker を環境から決める処理（`gh repo view`・local の slug の選択・利用者への質問）は、init の手順 2 として SKILL の側にある（hub の SKILL.md:105-106）
- cwd の repo を含む active な PJ は git の共通ディレクトリで引き（`hub.py:2494` `active_projects_on`）、`--project` の無い report はそれが 1 件のときだけ PJ が決まる（`hub.py:2506` `detect_project`）
- 紐付けの案内（`hub.py:2731` `worker_hint`）は、SessionStart と PostCompact の hook からだけ呼ばれ、受け取るのは session_id と cwd だけ（`hub.py:2785`、`project-hub/hooks/hooks.json`）。この時点では Issue は決まっていない。未登録かは PJ ごとに判定する（`hub.py:2743`）ので、ある PJ に登録済みのセッションにも、同じ repo の別の PJ の案内が出る
- 宛先の照合は、active かどうかを問わず別の PJ の登録名を候補から外す（`hub.py:2330` `foreign_names`）。同じセッションが 2 つの PJ に登録されると、自分の sub の名前も候補から外れる
- 登録（`sessions/<sid>.json`）は report のたびに書かれ（`hub.py:2573-2581`）、消す処理は無い。close-sub は journal に記録するだけ（`hub.py:1540-1570`）
- report の `issue` は必須（`hub.py:577`）で、検査するのは形だけ（`hub.py:589`）。tracker に実在するかは見ない
- report は毎回、cwd のブランチと worktree を登録に書く（`hub.py:2578`）。base のブランチにいる登録と、別の登録と worktree を共有する登録は「重なり不明」の注記になる（`hub.py:1918`）。この注記は表示用で、書き込みを止めるものではない。作業中かの判定は、hub が取り込んだ journal と presence.json だけを見る（`hub.py:1894-1903`）ので、sub の側から見ると古いことがある
- report の失敗は、stdout の `status`（`parse_failed` など）と 0 以外の exit で返す形がある（`hub.py:2536` 付近）。exit の意味は 2 が入力の不正、3 が状態の前提の違い（`hub.py:33-36`）
- cross の `active_projects` は、repo を共有しない PJ も含めた active な PJ の数（`hub.py:1973`）。段 2 の進む条件 1 はこの値で数える。今は repo hub が 1 つも無いので、既存の行の値は「repo hub を除いた数」と同じ
- hub の start は `use_worktree: true` で sub を起動する（hub の SKILL.md の start 2）
- issue-create は採番を `counter.txt` の Read → +1 → Write で確定し、排他しない（`issue-workflow/skills/issue-create/SKILL.md` の Phase 3）。Phase 6 で本文を見せて承認を取ってから書く。その後、Phase 7 の 2 でブランチを作り、3 で feature-dev 連携を聞き、4 で次のアクションを案内する。Phase 7 で feature-dev に引き継がないと Phase 8 に進み、bdd-spec / design-doc / adr-keeper を起動しうる（同 :257-301）
- issue-workflow の maintain は起動した時点で実行が確定し、in-progress の全 Issue を承認なしに書き換える。範囲を絞る引数は slug だけ（`issue-workflow/skills/maintain/SKILL.md:37-58`）。issue-maintain は Issue ID を引数に取れる（`issue-maintain/SKILL.md:28-32`）。follow-up の promote は、起票の後にブランチを作る確認を出す（`follow-up/SKILL.md:257-263`）
- issue-workflow の local backend を使うこのマシンの repo のうち、nextjs-homepage・yatima・artist-portfolio は `.claude/` ごと gitignore している（2026-11-02 に確認）。worktree の中からは本体側の DATA_DIR を共有する（`.claude-plugin/lib/backend-detect.md` の手順 2）
- base は origin 側を前提にし、無ければ黙ってローカルに落とさず明示を求める（`hub.py:800` `default_base`。意図はその行のコメント）

利用者の決定（2026-11-02）:

1. 起票は hub に一本化する。既にある Issue への着手は、直接開いたセッション（issue-workflow の start など）からでもよい
2. 同じ repo に PJ hub があるときは、Issue の範囲で振り分ける
3. repo hub 自身が手を動かすのは、起票と Issue の保守まで。実装は sub
4. 止めるときは close、再開は reopen（設計レビューの後で決め直した。当初は「休止と再開」を選んだが、「閉じた PJ は作り直せない」という誤った前提で close を退けていた）
5. repo hub の sub には、Issue とブランチを強制してよい

## 採用案

### 位置付け

repo hub は、config に `repo_hub: true` を持つ PJ。範囲は 1 つの repo の open Issue のうち、同じ repo のどの PJ の範囲にも入らないもの。止めるときは今の close を使い、再開は reopen で行う。上位の hub ができたら、ほかの PJ と同列の子として登録する（上位の hub の代わりにはしない）。

```
            （段 2: 上位の hub — 条件を満たしてから）
                 │              │
           PJ hub「auth」     repo hub「repo-myapp」
           範囲: milestone     範囲: myapp の open Issue のうち
           「auth v2」         どの PJ にも入らないもの
             │                   │
           sub #12, #15        sub #31, #40
```

config の key を `kind` にしないのは、`hub.py` で既に tracker の種類（`tracker_kind`）・journal の種類（`JOURNAL_KINDS`）・`record --kind` が `kind` を使っているため。

### 起動（`hub repo`）

skill に `repo` サブコマンドを足す。引数なしの `init` を repo hub に割り当てない（PJ 名の言い忘れで repo hub ができるのを避ける）。役割は今の init と同じく分ける。

- **SKILL（Claude）がすること**: tracker を決める。今の init の手順 2（hub の SKILL.md:105-106）をそのまま使う（github は `gh repo view --json nameWithOwner`、local は slug が 1 つならそれ・複数なら聞く、linear は team / project を聞く）。milestone は付けない。決めた値を `--tracker*` で hub.py に渡す
- **`hub.py init --repo-hub` がすること**: 受け取った値の検証と記録だけで、gh も利用者への質問も持たない
  - repos: cwd ではなく、git の共通ディレクトリの親（メインのチェックアウト）を path にする。worktree から起動しても、worktree を消したときに切れない
  - PJ 名: `repo-<メインのチェックアウトの basename>`。PJ 名に使えない文字は `-` に置き換える。`--project` で明示もできる
  - 一意性: 同じ git の共通ディレクトリを持つ repo hub があれば exit 3。相手が active なら takeover、closed なら reopen を案内する。同じ名前の PJ があり、共通ディレクトリが違う（同じ basename の別の repo）なら、takeover を案内せず exit 3 にして、`--project` で別の名前を付けるよう案内する
  - 共存の検査（下の「共存の検査」）
  - tracker local では、`.claude/indie` が gitignore されているかを確かめる（`git check-ignore`）。されていなければ exit 3（未解決事項 7）
  - 既定値: `approval.mode` は `auto`、`tracker_write` は今と同じ（github / linear は `with_approval`、local は `never`）、`sidebar_group` は Desktop で `on`（グループ名は PJ 名なので `repo-<名前>`）、living spec は結ばない
- 会話の題は `hub repo-<名前>` を提案する（通常の PJ の hub と名前がぶつかって、sub の通知先が 2 件に当たるのを避ける）
- start の background には、PJ の目的の代わりに決まった文（「repo <名前> の常設の hub。範囲はどの PJ にも入らない open Issue」）を入れる

**共存の検査**: 同じ repo に「範囲を切っていない PJ」（github で milestone なし・linear で project なし・local で repo hub と同じ slug）があれば、repo hub の init を exit 3 で止める。逆に、repo hub がある repo で範囲を切らない通常の PJ を init するのも止める。範囲が同じ hub が 2 つあると、振り分けが決まらないため。数えるのは closed 以外の PJ（今は active だけ）で、reopen のときにも同じ検査を掛ける。

### close と reopen

- repo hub も通常の PJ と同じ `close` で止める（config の `status` を `closed` にする。データは消さない）
- `hub reopen`（`hub.py reopen`）を足し、すべての PJ で使えるようにする。今は手で config.json を直している「closed から戻す」（hub の SKILL.md:41）を CLI にしたもの
- reopen は、戻す前に次を確かめる:
  - 共存の検査（closed の間に、範囲を切らない PJ が同じ repo で init されていないか）。違反があれば exit 3
  - 二重登録: 戻す PJ の登録のうち、同じ repo の別の active な PJ にも同じ session_id の登録があるもの（closed の間に移ったセッション）は、戻す PJ の journal に close_sub を記録して作業中から外し、出力に並べる
- closed の repo hub がある repo は、振り分けの上では「repo hub の無い repo」として扱う（下の「振り分け」の 1）

### 振り分けと二重登録の禁止（report の中で決める）

宛先の PJ は report の中で決める。決める処理（`route`）は report の内部の関数とし、二重登録の検査も書き込む側の report に置く。紐付けの案内は宛先を決めない（hook の時点では Issue が決まっていない）。

1. **repo hub の無い repo では、今の挙動のまま**: cwd の repo を含む active な PJ に repo hub が無ければ、今の `detect_project` で決める（1 件ならそれ、それ以外は exit 1）
2. **登録を固定する**: 同じ git の共通ディレクトリを持つ active な PJ のどれかに、このセッションの登録が既にあれば、その PJ に置く。範囲が変わっていても付け替えない（作業の途中で Issue に milestone が付いた、同じ repo に PJ hub が後から init された、など）。範囲の食い違いは出力の `warnings` に出すだけにする
3. **`--project` があれば、それを使う**。ただし repo hub を指していて、Issue が active な通常の PJ の範囲に入ると判定できたら、stdout の `status: out_of_scope` と exit 3 で止める（repo hub から PJ の Issue を start した、など）
4. **初めての登録で `--project` が無いとき**、active な通常の PJ（`repo_hub` でないもの）について Issue の範囲を判定する。判定の材料が足りなければ「不明」とし、範囲外と同じには扱わない:
   - local: Issue ファイルが PJ の tracker dir（slug）の下にあるか。`hub.py` が直接読む
   - github: PJ の `tracker.repo` が repo hub の `tracker.repo` と同じなら、Issue の milestone と PJ の milestone を比べる。milestone は呼ぶ側が `gh issue view <番号> --repo <tracker.repo> --json milestone` で取り、`--milestone <名前>` か、milestone が無いことを示す `--no-milestone` で渡す。どちらも無ければ不明
   - linear: Issue の project を呼ぶ側が渡す。無ければ不明
   - tracker が別の repo の PJ（Issue ID だけでは、どちらの repo の Issue か決まらない）は不明
5. 結果:
   - 範囲に入る PJ が 1 件で、不明が無い → その PJ
   - 入る PJ が 0 件で、不明が無く、Issue が repo hub の tracker の範囲にある（local は repo hub の slug にファイルがある、github / linear は repo hub の tracker と同じ）→ repo hub
   - それ以外（2 件以上・不明がある・repo hub の範囲にも無い）→ stdout の `status: needs_project` と候補の PJ を返し、exit 1。SKILL は利用者に PJ を聞いて `--project` を付け直す
6. **二重登録の検査**: 書き込む前に、同じ git の共通ディレクトリを持つ別の active な PJ に同じ session_id の登録があれば、stdout の `status: registered_elsewhere` と登録先の PJ を返して exit 3。2 で固定するので、正しく動いていれば当たるのは版のずれなどの例外だけ
7. **宛先の照合**: `foreign_names` は、自分の PJ にも登録のある session_id の名前を外さない（closed の PJ から移ったセッションの名前が、移った先の候補から消えないようにする）

紐付けの案内（`worker_hint`）:

- 同じ repo の active な PJ のどれかに登録済みなら、どの PJ の案内も出さない
- 未登録なら、今と同じく PJ を並べる。そのうえで、active な repo hub がある repo では次を足す（文面は route の結果によらず 1 つ）:
  - 「`--project` を付けずに report を置けば、宛先は report が決める。`needs_project` が返ったら利用者に聞く」
  - 「repo を編集するなら、ブランチを切ってから編集する。Issue が無ければ、利用者に hub の会話で起票を頼むよう伝える（このセッションから hub へは送らない）」

### Issue とブランチの強制（repo hub に置く report だけ）

- 弾くのは「base のブランチの上で編集している」状態だけにする。判定は sub 自身が report の時点で確かめられる事実だけで行う: cwd のブランチが base のブランチか detached HEAD で、かつ未コミットの変更があるか、base より先のコミットがある
- 当たったら stdout の `status: needs_branch` と exit 3 を返し、report は置かない。SKILL は、変更をブランチに移す手順（ブランチを切る、または issue-workflow の start）を出す
- state によらず同じ判定を掛ける。ブランチを切る前の質問・blocked（作業ツリーがきれい）と、マージ後に base に戻ってからの done（作業ツリーがきれいで、base より先のコミットが無い）は通る
- worktree の共有は強制しない。今の「重なり不明」の注記のまま status で見せる（作業中かの判定が hub の取り込みに依存して古いので、ゲートには使わない）
- Issue は今どおり report で必須（`hub.py:577`）
- start は今のまま（`use_worktree: true`、Issue は引数で必須）
- 案内を無視して base のブランチで編集するセッションは、report で弾かれる。登録しなければ hub からは見えない。main へのコミットそのものは止めない（guardrail-protect の領分で、repo ごとの規約ともぶつかる）。そのため、main に直接コミットする規約の repo とは両立しない（README に書く）

### status の範囲

- repo hub の status の 4（Issue の取得）は、同じ repo の active な通常の PJ の範囲を除く:
  - github: `gh issue list` に `milestone` を含めて取り、hub.py の `snapshot --source tracker` に渡す。hub.py が、同じ repo の active な PJ の milestone に当たる Issue を除く
  - local: repo hub の slug だけを読む（今と同じ。同じ slug の PJ は共存の検査で弾いている）
  - linear: 同じく project で除く
- status の別の PJ の節（cross）は今のまま出す（同じ repo の PJ hub の sub との重なりは、本物の調整の需要。未解決事項 6）

### 起票と Issue の保守

- repo hub がある repo では、どの tracker でも起票を repo hub のセッションに集め、sub には起票させない。sub の follow_ups と利用者の依頼は、hub が起票の候補として lead に出す
  - github / linear: 今の `tracker_write: with_approval` の手順（書くたびに全文を見せて承認を取る）
  - local: 今の「起票の持ち主」（hub の SKILL.md:72。hub のセッションで lead が issue-workflow を呼ぶ）をそのまま使う。hub は、lead が貼るだけで済む起動の 1 行（issue-create の「起票だけ」の引数つき）を出す。hub.py の `tracker_write` の検査は変えない（hub.py は Issue ファイルを書かない）
- issue-create に「起票だけ」の引数を issue-workflow 側で足す。契約は終わり方で決める: 「Phase 6 の書き込みで終え、ブランチ作成・feature-dev 連携・次のアクションの案内・spec の選択（Phase 7 の 2〜4・Phase 8）に進まない」。承認は issue-create の Phase 6 の 1 回だけにする（hub は先に全文を見せない）。終わりに「起票だけで終えた」ことを 1 行出す（書き込まずに終えた回は、どの Phase でやめても「起票せずに終えた」の 1 行を出す）。hub はこのどちらかで引数が効いたかを確かめる。どちらも出ていなければ（issue-workflow が古い）、ブランチ作成の確認を断るよう lead に伝え、issue-workflow の更新を勧める
- Issue の保守は、対象を Issue 単位で指定できる issue-maintain（Issue ID を渡す）に限る。maintain（全件・承認なし）と follow-up の promote（ブランチ作成の確認を出す）は、hub のセッションでは回さない
- 保守の前に status の取り込み（ingest と presence）を回し、作業中の sub がいる Issue を外す。作業中は、自分の sub の表と、cross が返す同じ repo の別の PJ の作業中の sub の両方で判定する
- hub の SKILL.md の「hub の役割」に、repo hub の例外として起票と Issue の保守を書く。コードの実装と調査は今までどおり sub に任せる

### PJ 横断と上位の hub

- cross の `active_projects` の定義を「`repo_hub` を除いた active な PJ の数」に変える。新しい欄は足さない。今は repo hub が 1 つも無いので、これまでの journal の cross の行の値は変わらない
- 段 2 の進む条件 1 は、この値でそのまま数える。閉じない repo hub を repo ごとに置くと、それだけで総数が 3 を超え、PJ が同時に動いているかと無関係に条件を満たすため
- 条件 2（新しい重なり・決定）はそのまま。同じ repo の PJ hub と repo hub の sub の重なりは、本物の調整の需要。条件は 1 つの PJ の journal で数えて合算しないので、両側から数えても水増しにならない。二重登録の禁止で、自分自身との重なりも出なくなる
- `.claude/designs/20261029-project-hub-cross-project-view.md` の段 2 に、条件 1 の数え方の変更を追記する
- repo hub から別の PJ の sub・hub へは送らない（今の決まりのまま）
- 後ろ盾: status で、自分の登録と同じ session_id が同じ repo の別の active な PJ にもあれば、lead に出す（版のずれで report の検査が掛からなかった回を拾う。cross が読む登録を使う）

### 版のずれと移行

- sub の report は sub 側の `hub.py` で動く（report の SKILL.md:47）。sub の project-hub が古いと、振り分け・二重登録・強制が掛からない。README と CHANGELOG に「更新後は作業中のセッションを開き直す」と書く。漏れは上の status の後ろ盾で拾う
- issue-workflow が古いと「起票だけ」の引数が効かない。上の終わりの 1 行（「起票だけで終えた」か「起票せずに終えた」）が無いことで見分け、ブランチ作成の確認を断る
- project-hub は issue-workflow に依存しない（起票だけの引数は、hub が lead に出す起動の 1 行に入るだけ）。`_requirements` と `check-deps.sh` は変えない

### 変更対象ファイル

| ファイル | 変更 |
|---|---|
| `project-hub/scripts/hub.py` | config の `repo_hub`、`init --repo-hub`（path と名前の導出・一意性・共存・gitignore の検査・既定値）、`reopen`（共存の検査・移ったセッションの close_sub）、report の中の `route`（今の挙動の維持・登録の固定・範囲の判定・`needs_project` / `out_of_scope` / `registered_elsewhere` / `needs_branch`）、`foreign_names` の session_id での除外、`worker_hint`（登録済みなら黙る・repo hub の文面）、cross の `active_projects` の定義、`snapshot --source tracker` の milestone での除外、status の二重登録の後ろ盾、argparse の登録 |
| `project-hub/skills/hub/SKILL.md` | `repo` / `reopen` サブコマンド、hub の役割の例外（起票と Issue の保守）、「hub が書かないもの」（:70）と「起票の持ち主」（:72）の repo hub での扱い、init の手順（:109・:113 の takeover の案内の分岐）、brief の「Issue は起票しない」（:184）を repo hub ではすべての tracker に、トラッカーへの書き込み（:269・:272）、status の 4 の範囲の除外、start の background、description のトリガー |
| `project-hub/commands/hub.md` | 引数と description（同名ペアなので SKILL.md と対で直す。allowed-tools は変えない — issue-create は lead が呼ぶ） |
| `project-hub/skills/report/SKILL.md` | `--project` なしの既定、github の milestone の取り方（`--milestone` / `--no-milestone`）、`needs_project` / `out_of_scope` / `registered_elsewhere` / `needs_branch` のそれぞれの手順、repo hub では github / linear でも sub は起票しない（:36） |
| `project-hub/README.md` | repo hub の節（ブランチで作業する運用になること・main に直接コミットする repo とは両立しないこと・更新後は作業中のセッションを開き直すこと）、reopen |
| `issue-workflow/skills/issue-create/SKILL.md` / `issue-workflow/commands/issue-create.md` | 起票だけで終える引数（終わり方での契約と、終えたことを示す 1 行） |
| `.claude/designs/20261029-project-hub-cross-project-view.md` | 段 2 の条件 1 の数え方（追記） |
| `.claude-plugin/scripts/tests/test_project_hub_scripts.py` / `test_project_hub_hooks.py` | 下の「検証方法」 |
| 各プラグインの `plugin.json` / `CHANGELOG.md`、`marketplace.json`、`INDEX.md` | バージョンバンプ（`bump-version.sh --sync`）。CLAUDE.md の一覧の説明行も必要なら |

## 検討した代替案

| 観点 | 案 A: project-hub に `repo_hub` を足す（採用） | 案 B: 新しいプラグイン（repo-steward など） | 案 C: issue-workflow の start / dashboard を広げる |
|---|---|---|---|
| 二重登録を止められるか | 止められる（両方の登録を 1 か所で読める） | 止められない（プラグイン間の依存が禁止で、project-hub の登録を読めない） | 止められない（案 B と同じ） |
| 複製 | 無い（tracker の判定は今の init の手順 2 を使う） | 宛先の照合・inbox・在席の確認（`hub.py` 約 3,000 行の中核）を複製する | セッション間の連絡（ListAgents・SendMessage・start_session・inbox）が無く、足すと案 B と同じ複製 |
| 変更量 | 中（`hub.py`・SKILL と command・issue-create） | 大 | 大 |
| 上位の hub との関係 | 上位の hub の子として PJ と同じ形で登録できる | 上位の hub が 2 種類の仕組みを束ねることになる | 同左 |

- **案 B を採らない理由**: 二重登録を止めるには両方の登録を 1 か所で読む必要があり、別プラグインでは原理的に作れない。CLAUDE.md は、プラグイン間の依存禁止の下で複製が出るのを分割単位の誤りの合図としている
- **案 C を採らない理由**: issue-workflow には repo の Issue の一覧はあるが、セッションをまたぐ連絡の仕組みが無い。足すと案 B と同じ複製になる

採用案の中の選択:

| 論点 | 採用 | 採らなかった案と理由 |
|---|---|---|
| 編集するセッションの入口 | 起票だけ hub に一本化 | start に一本化: 「hub を経ずに始めた sub も紐付く」流れ（GitHub issue #315 で直したもの）が repo hub で使えなくなる / 直接も自由に参加: 同時の起票で採番が競合する |
| PJ hub との振り分け | Issue の範囲で判定（report の中で） | PJ hub が渡した分だけ PJ: PJ の Issue を直接開いたセッションで始めると repo hub に入る / 毎回聞く: PJ hub がある間、hello のたびに聞かれる / 案内の時点で決める: hook では Issue が決まっていない |
| hub の仕事 | 起票と Issue の保守（issue-maintain を Issue 単位で） | 起票だけ: 「次に何をやるか」を hub で決められない / maintain も回す: 作業中の Issue を外す手段が無い |
| 寿命 | close と reopen（reopen はすべての PJ） | pause / resume を足す: paused と closed は実行時の働きが同じで、違いが名前だけになる / 止める手段なし: 止めると履歴も消える |
| 強制の範囲 | base のブランチの上での編集だけ | hello 以外をすべて弾く: ブランチを切る前の質問・blocked・base に戻った後の done も弾く / worktree の共有も弾く: 判定が hub の取り込みに依存して古く、開き直した sub を弾く |
| 上位の hub の進む条件 | `active_projects` の定義を変える | 新しい欄 `active_pj_hubs` を足す: 読む側がいない欄を残すことになる / 閾値を上げる: repo hub の数で閾値が動く |

## 設計判断ログ

- [→ADR候補 → ADR-20261102144843] repo hub は「範囲が repo 全体で閉じない PJ」で、上位の hub の代わりにしない。上位の hub ができたら、ほかの PJ と同列の子にする（ADR-20261029233229 の決定 3・4 を保つ）
- [→ADR候補 → ADR-20261102144843] 止めるのは close、再開は reopen（すべての PJ）。reopen で共存と二重登録を検査し直す
- [→ADR候補 → ADR-20261102144843] 段 2 の条件 1 は repo hub を除いた数で数える（`active_projects` の定義を変える）。条件 2 はそのまま
- [→ADR候補 → ADR-20261102144903] 1 つのセッションは、同じ repo の active な PJ のうち 1 つにだけ登録する。宛先は report の中で決め、登録があればそれに固定する。初めての登録は Issue の範囲で決め、判定できなければ利用者に聞く。repo hub の無い repo では今の挙動のまま
- [→ADR候補 → ADR-20261102144922] repo hub がある repo では、どの tracker でも起票を hub のセッションに集め、sub には起票させない。local は今の「起票の持ち主」の決まりを使い、hub.py の `tracker_write` は変えない
- [local] 強制は「base のブランチの上での編集」だけにし、sub 自身が確かめられる事実で判定する。理由は stdout の `status` と exit 3 で返す
- [local] 起動は `hub repo` の別のサブコマンドにし、引数なしの init には割り当てない。tracker の判定は SKILL、hub.py は検証と記録
- [local] config の key は `repo_hub`（既存の `kind` とぶつけない）、PJ 名はメインのチェックアウトの basename から作る
- [local] 既定値は auto / `tracker_write` は今と同じ / Desktop で sidebar on / living spec は結ばない / base は今のまま
- [local] issue-create の「起票だけ」は終わり方で契約し、承認は Phase 6 の 1 回にする。`hub.py` が Issue ファイルを書く案は、採番とテンプレートの複製になるので採らない
- [local] Issue の保守は issue-maintain を Issue 単位で回すだけにする

## 未解決事項 (open)

1. **journal と登録が増え続ける**（閉じない PJ では、注入の hook・取り込み・宛先の照合・表の生成が毎回全行を読む）
   - (a) journal を期間で切り替える — pros: 読む量の上限が決まる / cons: 見せた所までの印（行数）の持ち方を変える必要がある
   - (b) done・archive 済みの登録を `sessions/archive/` に退避する — pros: 表と照合の両方に効く / cons: journal は減らない
   - 方向性: (b) を先に入れる。確定タイミング: repo hub を 1 つの repo で 30 日使い、注入の hook の所要時間か表の「ほか N 件」が問題になったとき
2. **Issue 50 件・表 30 行の上限に常に当たる**
   - (a) 表を「sub のいる Issue」と件数に絞り、全件は snapshot に置く — pros: 表が読める量に収まる / cons: 着手前の Issue が表から見えなくなる
   - (b) 上限を上げる — pros: 変更が小さい / cons: 注入の量が増える
   - 方向性: (a)。確定タイミング: 打ち切りの警告が毎回の status で出るようになったとき
3. **PR の照合に過去のブランチが残る**（`registered_branches` が done・不在の登録も含む）
   - (a) 作業中の登録に絞る — pros: 過去の merged PR が表から消える / cons: 通常の PJ の表の挙動も変わる
   - (b) 今のまま — pros: 変更なし / cons: 閉じない repo hub では表が過去の PR で埋まる
   - 方向性: (a)。確定タイミング: 実装時に通常の PJ への影響を見て決める
4. **古い決定・lead の発言が、いつまでも auto の答えの出典に使われる**
   - (a) 期間の窓で切る — pros: 単純 / cons: まだ有効な決定まで落ちる
   - (b) 決定に supersede を足す — pros: 有効な決定だけが残る / cons: 書く手順が増える
   - 方向性: (b)。確定タイミング: 古い決定を出典にした誤った auto の答えが出たとき
5. **（解決済み・2026-11-02）通常の PJ にも休止を使えるようにするか** — reopen をすべての PJ に足すことで解決した（「close と reopen」）
6. **同じ repo に PJ hub と repo hub がいると、PJ hub の status に「別の PJ」の節が常に出て、重なりのある brief は auto でも承認が要る**（ADR-20261029233251 の決定 3）
   - (a) そのまま — pros: 重なりは本物の調整の需要で、上位の hub に進む判断の材料にもなる / cons: 承認の手間が増える
   - (b) repo hub 由来の重なりだけ扱いを変える — pros: 手間が減る / cons: ADR-20261029233251 を改める必要がある
   - 方向性: (a)。確定タイミング: 運用で承認の手間が問題になったとき
7. **Issue ファイルを git で追跡している repo で、local の起票をどう扱うか**（hub のセッションが書いた Issue ファイルは本体の checkout に未コミットで残る。worktree の中では、その worktree にある `.claude/indie` の複製が使われるので、sub からは見えない）
   - (a) repo hub の init で `.claude/indie` が gitignore されていることを確かめ、されていなければ止める — pros: 機械で塞げる / cons: Issue ファイルを追跡している repo では、repo hub で local を使えない
   - (b) 起票の後に commit・push する — pros: 追跡している repo でも使える / cons: hub は repo を編集しない決まりに反し、base のブランチへの直接のコミットになる
   - 方向性: (a) を採用案に入れた。このマシンで local を使う repo（確認できた 3 件）はどれも gitignore している。確定タイミング: 追跡している repo で repo hub を使いたい要望が出たとき
8. **起票の書き手を 1 つにする決まりは、文面でしか守られない**（利用者が別のセッションで issue-create を直接呼ぶ経路と、discover が `counter.txt` を使う経路は塞がない）
   - (a) 今のまま（文面で守る） — pros: 変更なし / cons: 同時の起票で番号がぶつかりうる
   - (b) issue-create に排他を入れるか、discover と同じく既存のファイルの最大 ID と counter の大きい方を使う — pros: 書き手が複数でもぶつからない / cons: issue-workflow の採番を変える
   - 方向性: (a)。確定タイミング: 採番の衝突を 1 回でも観測したとき（(b) を issue-workflow 側で入れる）
9. **（解決済み・2026-11-04）fork の clone で、`gh repo view` が返す repo が upstream を指す**（tracker を upstream で記録すると、fork の Issue と食い違う）。gh 2.100.0 で確かめた: origin と upstream の両方の remote があり、既定の repo（`gh repo set-default`）を決めていない clone では upstream を返し、origin だけなら origin を返す。(b) を採り、SKILL の `repo` の手順で origin の owner/name と比べ、食い違えば利用者に聞く
   - (a) tracker の判定は `gh repo view` の既定に任せ、利用者が違えば `--tracker-repo` で直す — pros: 変更なし / cons: 気づかないと範囲の判定が外れる
   - (b) init のときに origin の owner/name と食い違えば利用者に聞く — pros: 気づける / cons: 手順が増える
   - 方向性: (b)。確定タイミング: Issue 1a の実装時に gh の挙動を確かめて決める
10. **linear の repo hub で、status の表から同じ repo の PJ の Issue（project）を除く**（1a は github の milestone だけを除く）
   - (a) 呼ぶ側が Issue の project を渡し、hub.py が PJ の project の Issue を除く — pros: github と同じ形 / cons: Linear MCP の出力の形に合わせる
   - (b) 今のまま（表に PJ の Issue も並ぶ）— pros: 変更なし / cons: repo hub の表が PJ の Issue で埋まる
   - 方向性: (a)。確定タイミング: linear の repo hub を使い始めたとき（1b の範囲には入れない）

## 実装で決めたこと（Issue 1a・2026-11-04）

採用案に書いていない細部を、Issue 1a（GitHub #356）の実装で次のように決めた。

- `init --repo-hub` の repo は `--repo`（1 つまで）か `--cwd` か cwd から取り、メインのチェックアウトに直す。submodule・`--separate-git-dir`・bare の repo は、メインのチェックアウトを決められないので exit 2。PJ 名の既定は `repo-<basename>` で、`--project` は repo hub のときだけ省ける
- 共存の検査の「範囲が重なる」（決定 5 のとおり）: 同じ git の共通ディレクトリにある closed 以外の通常の PJ のうち、github は同じ repo で milestone なし、local は同じ slug の dir、linear は project なしで同じ team（repo hub が team を持たなければ project なしのすべて）か、repo hub と同じ project のもの（linear の範囲は project で切る。milestone は見ない）。local の PJ には `--milestone` を付けられない。読めない config の PJ は飛ばすが、repo hub の init だけは、読めない config があれば止める（同じ repo の repo hub かを確かめられず、2 つ目を作りうる）
- repo hub の init で PJ 名がぶつかったときは、相手が同じ repo の通常の PJ か別の repo の PJ かを文面で分け、どちらも takeover を案内しない
- tracker local の検査は `.claude/indie` ではなく `--tracker-dir` で行い、`git check-ignore` に加えて `git ls-files` で追跡中のファイルが無いかも見る（ignore したパスを force-add したファイルは check-ignore に出ない）。repo の外の dir は見ない。worktree の中の dir は止める（本体の check-ignore では `.claude/worktrees/` の ignore に当たって通り、worktree を消すと tracker が切れる）
- reopen は hub のセッションが違えば takeover を兼ねる（閉じた PJ を戻すのはたいてい新しい会話。journal の takeover の行に `reason: reopen`）。移ったセッションは journal の `close_sub` に `{"result": "moved", "to_project": …, "at": …}` で残し、その後にこの PJ で report を置くまで作業中から外す（`worktrees` の `working`・cross・サイドバーのグループ・`waiting`・state.md の sub 表と待っている PR・PR の照合）。「その後に report を置いた」は inbox に置いた時刻と `at` で比べる（close の時点で inbox に残っていた report を reopen の後に取り込んでも、作業中に戻さない）。移ったとみなすのは、別の PJ の登録が close より後に更新されたものだけ（close より前からあった登録は、その PJ の作業を終えてから来たセッション）。repo hub の reopen は、init と同じく読めない config があれば止める。別の PJ の登録が読めなければ、止めずに `unknown` に出す
- `snapshot --source tracker` の milestone での除外は github だけ。除く対象は、tracker の repo が repo hub と同じで milestone を持つ、同じ repo の active な通常の PJ。除く PJ があるのに milestone の無い行があれば warning を出す。linear の project での除外は後に回す（下の未解決事項 10）
- README の「main に直接コミットする repo とは両立しない」「更新後は作業中のセッションを開き直す」は、強制と振り分けの説明なので Issue 1b で書く（#357 の本文には無いので、1b に着手するときに範囲へ入れる）
- 1b が入るまでの間、同じ repo に repo hub と PJ hub がどちらも active だと、`--project` の無い report は PJ が決まらず exit 1 で止まる（今の `detect_project`。誤った宛先には置かない）
- tracker local の PJ に `--milestone` を付けると、repo hub の有無によらず止める。ゴールの「repo hub の無い repo では今の挙動を変えない」の例外で、値は以前から読まれていなかった（local の範囲は slug で決まり、milestone では切れない）
- GitHub の repo の比較は大文字と小文字を区別しない

## 実装で決めたこと（Issue 1b・2026-11-04）

採用案に書いていない細部を、Issue 1b（GitHub #357）の実装で次のように決めた。

- repo hub の無い repo では、登録の固定・`registered_elsewhere`・`needs_branch`・status の後ろ盾を掛けない（2026-11-04 決定 / ADR-20261105111324。ゴールの「今の挙動を変えない」に合わせた。`--project` を切り替えて 2 つの PJ に置くセッションを止めない）。どの repo にも効かせるのは、`foreign_names` と、登録済みなら紐付けの案内を出さない `worker_hint` だけ
- 範囲の材料は report の引数で渡す: github は `--milestone <名前>` / `--no-milestone`、linear は `--issue-project <名前>` / `--no-issue-project`。Issue ID の形が PJ の tracker と合わなければ「範囲外」で、不明にはしない
- 登録の固定では、reopen が「移った」と journal に記録した登録（`close_sub` の `result: moved`）を数えない（紐付けの案内の「登録済みなら黙る」も同じ）。`--project` が固定した PJ と違えば `registered_elsewhere`。2 つ以上の PJ に登録済み（版のずれ・repo hub を後から作った repo）のときは、`--project` で登録済みの 1 つを選べば warning 付きで置ける（止めたままだと、登録を外す手段が無いので抜け出せない）
- `foreign_names` で外さないのは、宛先を引いているセッション自身がこの PJ にも登録を持つときの、そのセッションの名前だけにした。この PJ の別のセッションがほかの PJ で名乗る名前は、そのセッションのものなので外す（設計どおり「自分の PJ にも登録のある session_id」をどれも外さないことにすると、別のセッションの名前に当たる）
- `needs_branch` の base のブランチは config の `repos[].base` から remote 名を外したもの（`base_branch`）。未コミットの変更には gitignore されていない untracked のファイルも数える。base がローカルのブランチ（`main` / `refs/heads/main`）なら `main..HEAD` は main の上で常に 0 なので、その upstream と比べる。git でブランチを取れないときは止めずに `warning` に出す。未コミットの変更と base との差のどちらかを取れないときは、取れた側で当たれば止め、当たらなければ `warning` に出す
- status の後ろ盾は `cross` の `double_registered` に出し、hub の SKILL.md の status の 10 で lead に出す。数えるのは route と同じ単位で、登録の worktree の repo に active な repo hub があるもの（repo hub でない PJ どうしの組も含む。worktree を消した登録は PJ が共有する repo で見る）。登録を外す CLI はまだ無いので、どちらの PJ で続けるかは lead が決める

## 実装で決めたこと（GitHub #382〜#384・2026-11-07）

- 二重登録の欄に出た登録は `hub.py unregister --project <PJ> --session <id> --keep <残す PJ>` で外す。書くのは外す側の PJ の journal だけ（`close_sub` の `result: moved` に `by: "unregister"` を付ける）で、残す PJ の journal には書かない（2026-11-07 決定）。外した登録は route・二重登録の欄・working から外れる。上の Issue 1b の「登録を外す CLI はまだ無い」は、この CLI で解消した
- Issue の保守で外す作業中の Issue は、`worktrees` と `cross` の出力の `busy_issues`（github は `#12` に揃え、ほかは前後の空白を除いた ID）で照合する
- init / reopen / set-tracker-write / set-sidebar-group の設定値を理由にした exit 3 は、stdout にも理由のコード（`status`）と文面（`reason`）を出す。分岐はコードで決める
- 送る前に `refresh-hub` で hub.json の名前を今の題に直し、受ける側は受けるたびに `hub-name` で今の名前を引いて照合する。既定名（`default_name: true`）の名前は照合に使わない
- `resolve --hub` は外した（通知先は report が決めており、使い道が無かった）

## 実装ブリッジ (Implementation Bridge)

1. **実装着手の単位**: 3 つの Issue に分け、Issue 2 → Issue 1a → Issue 1b の順に入れる
   - Issue 2（issue-workflow）: issue-create に、Phase 6 の書き込みで終える「起票だけ」の引数を足す
     ```
     /feature-dev issue-workflow の issue-create に、Phase 6 の書き込みで終えてブランチ作成・feature-dev 連携・次のアクション・spec の選択に進まない「起票だけ」の引数を足す design=.claude/designs/20261102-project-hub-repo-hub.md
     ```
   - Issue 1a（project-hub）: repo hub の器（`repo_hub` / `init --repo-hub` / `reopen` / cross の `active_projects` の定義 / status の範囲の除外 / SKILL の `repo`・`reopen`・起票と保守 / README / cross-view doc の追記）
     ```
     /feature-dev project-hub に repo hub の器（init --repo-hub・reopen・cross の active_projects の定義・status の範囲の除外・起票と保守の手順）を足す design=.claude/designs/20261102-project-hub-repo-hub.md
     ```
   - Issue 1b（project-hub）: 宛先と強制（report の中の `route`・登録の固定・二重登録・強制・`foreign_names`・`worker_hint`・status の後ろ盾・report の SKILL）
     ```
     /feature-dev project-hub の report に repo hub への振り分け（登録の固定・Issue の範囲・二重登録の禁止）と、base のブランチの上での編集の強制を足す design=.claude/designs/20261102-project-hub-repo-hub.md
     ```
2. **検証方法**:
   - CLI テスト（`test_project_hub_scripts.py`。`PROJECT_HUB_DIR` を使い捨ての dir に向ける）:
     - init: worktree から起動しても path がメインのチェックアウト / 同じ共通ディレクトリの repo hub で exit 3（active なら takeover、closed なら reopen を案内）/ 同じ名前で共通ディレクトリが違えば takeover を案内しない / 範囲を切らない PJ との共存はどちらの順でも後の方が exit 3 / local で gitignore されていなければ exit 3
     - reopen: closed の間に範囲を切らない PJ ができていれば exit 3 / 移ったセッションは close_sub を記録して作業中から外れる / 通常の PJ でも使える
     - route: repo hub の無い repo では今の `detect_project` と同じ結果 / 登録済みなら範囲が変わっても同じ PJ（`warnings` に出る）/ local の slug・github の milestone で PJ に決まる / `--no-milestone` で repo hub / milestone の指定が無ければ `needs_project` / tracker が別の repo の PJ があれば `needs_project` / repo hub の slug にも無い Issue は `needs_project` / `--project` に repo hub を指して PJ の範囲の Issue なら `out_of_scope`
     - 二重登録: 別の active な PJ に同じ session_id があれば `registered_elsewhere`
     - 強制: base のブランチで作業ツリーがきれいなら通る（hello・questions・blocked・done）/ base のブランチで未コミットの変更か先のコミットがあれば `needs_branch` / detached HEAD でも同じ / 通常の PJ では弾かない
     - `foreign_names`: closed の PJ から移ったセッションの名前が、移った先の候補に残る
     - cross の `active_projects` は `repo_hub` を数えない / snapshot が同じ repo の PJ の milestone の Issue を除く
   - hook テスト（`test_project_hub_hooks.py`）: 同じ repo のどこかに登録済みなら、どの PJ の案内も出ない / repo hub がある repo の未登録のセッションに repo hub の行が出る / repo hub の無い repo では今の文面のまま。発火する条件より黙る条件を厚く書く
   - 期待値はテスト側で独立に組み立てる（検証する仕組み自身で期待値を作らない）
   - 実機:
     - 個人の repo 1 つで repo hub を立て、起票（issue-create の起票だけ）→ start → report（hello → in_progress）→ status を 1 周する
     - milestone 付きの PJ hub と repo hub を同じ repo に並べ、直接開いたセッション（issue-workflow の start）で hello を置き、milestone の有無でそれぞれに振り分けられることを確かめる
     - repo hub を close → reopen し、元の状態から続くことを確かめる
3. **実装完了時の doc 更新手順**:
   - frontmatter の `phase: target` を `current` に、`last-validated` を更新する
   - cross-view doc の段 2 の追記がこの doc と合っているかを確かめる
   - 実装と乖離した箇所があれば追記し、方式ごと変わったなら supersede する

## 関連

- 関連 Issue: なし（実装ブリッジの 3 件を起票する）
- 関連 spec: なし
- 関連 ADR: ADR-20261102144843（repo hub は閉じない PJ で、上位の hub の代わりにしない）、ADR-20261102144903（1 セッション 1 PJ の登録と Issue の範囲での振り分け）、ADR-20261102144922（repo hub では起票を hub のセッションに集める）、ADR-20261029233229（PJ 横断は読むだけ → 上位の hub）、ADR-20261029233251（別の PJ との重なりは自動の連絡に入れない）、ADR-20261027014506（tracker_write の opt-in と local の扱い）、ADR-20261021154740（report のファイル inbox と名前の照合）、ADR-20261025152955（自動の連絡）
- 関連 design doc: `.claude/designs/20261021-project-hub-plugin.md`、`.claude/designs/20261029-project-hub-cross-project-view.md`

## 設計レビュー（2026-11-02）

minimal / clean / pragmatic / risk の 4 視点でレビューし、MAJOR 14 件を独立の反証にかけた（14 件とも支持）。BLOCKER は 0 件。MAJOR 14 件・MINOR 10 件をすべて反映した。主な変更:

- tracker の判定を hub.py から SKILL に戻した（hub.py は gh を呼ばない）
- 宛先は紐付けの案内ではなく report の中で決め、登録に固定する。判定できないときは利用者に聞く。repo hub の無い repo では今の挙動のまま
- 強制を「base のブランチの上での編集」だけにし、sub 自身が確かめられる事実で判定する
- 寿命を「休止と再開」から「close と reopen」に改めた（close を退けた理由が誤りだった）
- local の起票は既にある「起票の持ち主」の決まりで足りるので、ADR-20261027014506 の決定 5 は改めない
- issue-create の「起票だけ」を終わり方で契約し、Phase 8 まで止める。保守は issue-maintain を Issue 単位で回すだけにした
- PJ 名をメインのチェックアウトから作り、別の repo との名前の衝突で takeover を案内しない
