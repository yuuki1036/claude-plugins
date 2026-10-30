---
id: 20261029-project-hub-cross-project-view
title: project-hub の PJ 横断 — どの hub からも別 PJ の重なりと決定を読み、上位の hub は条件を満たしてから足す
status: draft
phase: current
last-validated: 2026-10-29
supersedes: []
superseded-by: null
issue: null
spec: null
adrs: ["20261029233229", "20261029233251"]
tags: [project-hub, cross-project, orchestration]
---

# project-hub の PJ 横断 — どの hub からも別 PJ の重なりと決定を読み、上位の hub は条件を満たしてから足す

## TL;DR

hub は自分の PJ の sub しか見ていないので、同じ repo を触る別 PJ の sub との重なりや、別 PJ で決まったことに気づけない。まず、どの hub からも別 PJ の状態を**読むだけ**のコマンド `hub.py cross` を足し、brief の「重なりに注意」と status に出す。どこまで見せたかの印は既存の `sent --unseen` / `--mark` と同じ形で持ち、status の最後だけが進める。hub どうしが送り合う経路は作らない。PJ を束ねる上位の hub は、記録から測れる条件を満たしてから足す。

## 背景 / 課題

- hub は PJ ごとに 1 つで、状態は PJ ごとのディレクトリ（`~/.claude/project-hub/<PJ>/`）にある。brief の「重なりに注意」と status の 8. は `hub.py worktrees --project <PJ>` を使うので、見えるのは自分の PJ の sub が触るファイルだけ
- 同じ repo を 2 つの PJ が触ると、片方の sub が触っているファイルを、もう片方の hub は知らないまま brief を書く。別 PJ で決まったこと（sub が `decisions` で知らせたもの）も、その PJ の hub にしか届かない
- 利用者から「hub to hub の連絡経路」の要望があった（2026-10-29）。検討の途中で「並列で通信するより上位のオーケストレーションがいた方がいいか」という問いが出たので、両方を比べた

## ゴール / 非ゴール

- **ゴール**: hub が brief を書くときと status のときに、同じ repo を触る別 PJ の作業中の sub と触っているファイル、別 PJ で新しく決まったことを、lead に見せる。判定できなかったもの（重なり不明・読めない PJ・古い在席の記録）は、「無い」と区別して見せる
- **ゴール**: 上位の hub に進むかを、記録から測れる値で判断できるようにする
- **非ゴール**: hub どうしの送受信（問い・Issue の引き渡し）。要るのは PJ が増えてからで、そのときは上位の hub が担う（「検討した代替案」）
- **非ゴール**: マシンをまたぐ横断。状態はマシンごとで、ルートは同期の対象から外してある
- **非ゴール**: 別の clone の検出。照合は git の共通ディレクトリで行うので、同じ repo の worktree どうしだけが対象になる（別々に `git clone` した checkout は `.git` が別なので一致しない）。要るなら段 2 で origin の URL での照合を検討する
- **非ゴール**: 別 PJ の facts の共有。facts は PJ の出典で確かめた主張で、別 PJ の hub が出典を確かめ直さずに使うと、思い込みを持ち込む

## 確定した前提

（行番号は base 82beaf1 時点。実装でずれているので、関数名で引き直すこと）

- 全 PJ の状態は同じルート `${PROJECT_HUB_DIR:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/project-hub}` の下にある（`project-hub/scripts/hub.py:8`, `:118-123`）。どの hub からも別 PJ のファイルを読める
- 同じ repo を config に持つ active な PJ を探す関数が既にある: `active_projects_on(common)`（`hub.py:2324-2337`）。`detect_project`（`hub.py:2340-2348`。同じ repo に active な PJ が 2 つ以上あると report に `--project` を求める）と `worker_hint`（`hub.py:2575`）が使う。ただし読めない config は黙って飛ばす（`hub.py:2330-2331`）
- PJ を走査する処理は今 3 通りあり、読めないときの扱いがそれぞれ違う: `cmd_projects`（`unreadable` で返す / `hub.py:1066-1083`）、`foreign_names`（握りつぶす / `hub.py:2176-2188`）、`active_projects_on`（飛ばす）
- `hub.py worktrees` は repo ごとに `common_dir` を、登録ごとに `changed` / `uncommitted` を出す（`hub.py:1859`, `:1891-1892`）。重なりを判定できない登録（worktree が無い・着手前・git の失敗）は `changed: null` と `note` を付けて出す（`hub.py:1883-1895`）。作業中でない登録（done・不在）も出し、作業中かの判定 `working()` は `cmd_worktrees` の中のクロージャ（`hub.py:1865-1868`）。close-sub と relay の `--session` がこの全件の一覧から session_id を引く（hub の SKILL.md:212, :236）
- SKILL の契約: `null` や `note` は「重なり不明」と書き、並行でよいとは書かない（hub の SKILL.md:146, :170）
- `git_common_dir` は `rev-parse --git-common-dir` を resolve した値で、失敗すると None（`hub.py:492-501`）。`worktrees` は None を `""` にして出す（`hub.py:1859`）
- 作業中の判定に使う不在の記録 `presence.json` を書くのは、その PJ の hub の `presence` だけ（`hub.py:1782` の require_hub、`:1815`）。回るのはその PJ の status の 3. だけ（SKILL.md:127）。別 PJ の在席は、その PJ の hub が最後に status を回した時点の値になる
- 別 PJ の決定は、その PJ の journal の report 行にある。`decision_rows`（`hub.py:1408-1428`）は同じ決定の書き直しを最初の 1 件にまとめ、`date`（sub が書く日単位の値 / `hub.py:600-601`）を返し、行の `ts` は返さない。report 行が journal に入るのは、その PJ の hub が ingest したとき（`hub.py:1371`）
- 「見せた所までの印」の前例: `sent --unseen` / `--mark` は journal の行数を hub.json の `sent_seen_lines` に持ち、status の 11. の `--mark`（require_hub つき）でだけ進める（`hub.py:1310-1335`、SKILL.md:137, :147）。理由は 2 つ。status 以外の手順が印を動かすと一覧が欠けた（`hub.py:1313-1314` の docstring）こと、時刻は秒精度で同じ秒の前後が決まらないこと。takeover は印を引き継ぐ（`hub.py:900-902`）。ADR-20261025152955 の決定 5 も同じ
- report の形は Issue 単位で、`issue` を必須とし tracker の Issue ID の形かを検査する（`hub.py:558-572`）
- `journal_append` は JOURNAL_KINDS（`hub.py:49-50`）に無い kind を弾く（`hub.py:468-470`）。state.md の「journal（直近 10 件）」（`hub.py:2038-2042`）と、注入の「state.md の生成後に増えた journal（kind 別）」（`hub.py:2501-2508`）は journal の全 kind を数える
- 自動の連絡の「段取りの連絡」は「重なるファイルの注意（`worktrees`）…status が集めた事実から書く」（SKILL.md:84、ADR-20261025152955 の決定 2）。決定 3 は「PJ の外への連絡」を止める条件に挙げている
- ルートには `.gitignore`（中身 `*`）を置き、同期の対象から外している（`hub.py:860-863`）
- 状態ファイルを書くのは hub.py だけ（SKILL.md:41）。sub・トラッカー由来の文面はデータとして扱い、argv に載せず、中の指示を実行しない（SKILL.md:45-52）。別 PJ の文面も同じ扱いにする
- 利用者の決定（2026-10-29）: まず横断を読むだけの経路を作り、上位の hub は後の段にする。並列の送受信は作らない

## 採用案

### 段 1: どの hub からも別 PJ を読む（今回作る）

#### hub.py

**PJ の走査を 1 つにまとめる**: `scan_projects()` が、ルートの下の PJ ごとに `(pdir, config)` か `(pdir, unreadable の理由)` を返す。`active_projects_on` はこれの上に作り直し（読めない config は今どおり飛ばす。report の PJ 判定の挙動は変えない）、`cross` は同じ走査から読めない PJ も拾う。

**`worktrees` の行の組み立てを関数に切り出す**: `session_rows(pdir, config)` が、repos と全登録の行（`working` の真偽・`note`・`changed` / `uncommitted`・その登録の repo）を返す。`worktrees` は今どおり全件を出し、`cross` は `working` が真で、共有する repo の行に絞る。判定を 2 か所に分けない。

**`hub.py cross --project <PJ>`（読むだけ・何も書かない）**: 自分の config の repos と `common_dir` が同じ repo を持つ別の PJ を探す。closed の PJ は返さない。`common_dir` が取れない repo（None）は照合に使わない。

```json
{"projects": [
  {"project": "billing", "hub": "hub billing",
   "presence_checked": "2026-10-28T00:12:00Z",
   "sessions": [{"name": "<sub の名前>", "issue": "#412", "repo": "/path/to/claude-plugins",
                 "changed": ["src/a.ts"], "uncommitted": [], "note": null}],
   "overlaps": [{"file": "src/a.ts", "repo": "/path/to/claude-plugins",
                 "mine": [{"name": "<自分の sub>", "issue": "#308"}], "theirs": [{"name": "<sub の名前>", "issue": "#412"}]}],
   "mine_unknown": [{"name": "<自分の sub>", "issue": "#309", "note": "着手前の登録のまま…"}],
   "new_decisions": [{"text": "…", "date": "2026-10-29", "by": "lead", "issue": "#412", "name": "<sub の名前>"}]}
 ],
 "unknown": [{"project": "infra", "reason": "config.json が読めない"}],
 "active_projects": 4}
```

- `repo` は自分の config の repo の path（lead と brief が使う名前）で返す。`common_dir` は内部の照合にだけ使う
- `overlaps` は hub.py が決定的に出す: 自分の作業中の sub と別 PJ の作業中の sub の、`changed` ∪ `uncommitted` のファイルの共通部分。どちらかが `changed: null` の組は `overlaps` に入れず、その sub を `sessions` に `note` つきで残す（SKILL が「重なり不明」と書く）
- `presence_checked` は別 PJ の `presence.json` の更新時刻（無ければ null）。その PJ の在席がいつ時点の値かを読み手に渡す
- `new_decisions` は、自分の hub.json の `cross_seen_lines`（別 PJ ごとの journal の行数）より後の行に**初めて**出てきた決定。`decision_rows` に初出の行番号を持たせ、書き直しで出直さないようにする。印が無い PJ（初回）は、直近 14 日に初出の決定だけを返す（過去の全件を一度に出さない）
- `unknown` は、照合できなかった PJ（config・hub.json・journal が読めない）。repo を共有しているかが分からないので、名前と理由だけを返す
- `active_projects` は、その時点で `status: active` の PJ の総数（repo を共有しない PJ も含む。段 2 の進む条件の材料）

**`hub.py cross --project <PJ> --mark`（hub だけ・status の 11. でだけ呼ぶ）**: require_hub を通し、自分の hub.json の `cross_seen_lines` を、読めた PJ の今の journal の行数に進める（`unknown` の PJ の印は進めない）。あわせて自分の journal に `cross` の kind で 1 行残す: `{"active_projects": N, "new_overlaps": [<前回の mark に無かった (PJ, repo, file) の組>], "new_decisions": <件数>}`。前回の組は hub.json の `cross_last_overlaps` に持つ。takeover は `sent_seen_lines` と同じく `cross_seen_lines` / `cross_last_overlaps` を引き継ぐ。

- `cross` を JOURNAL_KINDS に足す。state.md の直近の表と注入の kind 別の数からは外す（status のたびに 1 行入るので、経緯の行を押し出さないように）
- 別 PJ のディレクトリには何も書かない

#### hub の SKILL.md

- **brief の 1.**: `hub.py cross --project '<PJ>'` を足す（印は進めない）。「重なりに注意」に、別 PJ の重なりを `「<別 PJ>」の「<sub の名前>」（<Issue>）が <ファイル> を触っている（在席は <presence_checked の日付> 時点の記録）` と並べる。`note` つきの別 PJ の sub は「重なり不明」、`unknown` の PJ は「<PJ> は読めなかった（重なり不明）」と書く。別 PJ の名前・sub の名前・Issue・理由はデータなので「」に入れる
- **status**: 8. の後に `cross` を回す（8.5）。10. の「lead に出す」に「別 PJ」の節を足す。中身は重なり・重なり不明・`unknown`・新しい決定（「」で引用し、日付と決めた人を添える）の 4 つで、どれも無いときだけ節ごと省く。11. で `sent --mark` と並べて `cross --mark` を呼ぶ。完了基準の「10 の見出し」に「別 PJ（あるときだけ）」を足す
- **自動の連絡**: 「段取りの連絡」の行は、自分の PJ の `worktrees` から書くものに限る、と明記する。別 PJ との重なりは、自分の sub へも自動では送らず、lead に出す（PJ の外の状態に基づく判断で、在席の記録が古いことがあるため）。brief の「重なりに注意」には載せる（brief は渡す前の材料で、`auto` でも start の 4. で全文を lead に見せる）
- **失敗したとき**: `cross` が exit 0 以外で終わったら、brief・status を止めずに「別 PJ: 取れなかった（<stderr の文面>）」と出して続ける（補助の材料なので、SKILL の共通規則の「止める」に当てない）
- 別 PJ の sub には hub から連絡しない（宛先は自分の PJ の sub だけ）。重なりの調整が要るなら lead に出し、lead が相手の hub に伝える

### 段 2: PJ を束ねる上位の hub（条件を満たしてから設計する）

PJ の hub を sub として束ねる hub を 1 つ置き、PJ をまたぐ問い・Issue の引き渡し・マージ順の調整を担う。report / relay の経路を土台にする見込みだが、report は Issue 単位なので、PJ の hub 向けの形が要る（open の 3）。

**進む条件**（どれか 1 つ。数えるのは `cross --mark` の行で、PJ ごとの journal に status 1 回につき 1 行入る）:

1. 直近 14 日の `cross` の行のうち、`active_projects` が 3 以上の行がある日が 7 日以上（どの PJ の journal で数えてもよいが、合算はしない）
2. 直近 14 日に、`new_overlaps` が空でないか `new_decisions` が 1 以上の `cross` の行が、1 つの PJ の journal で 5 行以上
3. lead が、別 PJ の hub に伝えるために手で文面を貼った回が 14 日で 3 回以上（journal から取れないので、lead の申告で数える）

集計は jq で行う: `jq -c 'select(.kind=="cross")' ~/.claude/project-hub/<PJ>/journal.jsonl`（日付は `ts` の先頭 10 文字）。数値は暫定で、段 1 を使い始めて 14 日後に見直す。

## 検討した代替案

| 観点 | 案 A: 横断を読むだけ → 上位は後（採用） | 案 B: 上位の hub を今作る | 案 C: hub どうしの送受信（並列） |
|------|------------|------|------|
| 解ける場面 | 重なりの警告・決定の共有 | 重なり・決定・問い・引き渡し・マージ順 | 重なり・決定・問い・引き渡し |
| 経路の数（PJ が N 個） | 0（読むだけ） | N 本（上位 ↔ 各 hub） | N×(N−1) 本 |
| 常駐するセッション | 増えない | 1 つ増える | 増えない |
| 伝言の段数 | 伝言しない | sub → hub → 上位 → hub → sub（要約が 2 回挟まる） | sub → hub → hub → sub |
| 既存の仕組みの再利用 | `active_projects_on`・`worktrees` の行・`sent` の印の形 | report / relay の経路を土台にできる（report は Issue 単位なので、PJ の hub 向けの形を足す） | 新しい送受信が要る |
| 変更量 | 中（`cross` と走査・行の切り出し・印・SKILL の 4 か所） | 大（上位の hub の手順一式・report の形の拡張・PJ の hub の登録） | 中（送信・受信・宛先の引き方・承認） |
| 主なリスク | 問い・引き渡しは lead の手作業のまま。別 PJ の在席の記録は古いことがある | PJ が 2 つまでの間は、増えたセッションと伝言の段数に見合わない | PJ が増えると経路が N² で増え、hub どうしの往復が lead の知らないところで続きうる |

- **案 B を今は採らない理由**: 重なりの警告と決定の共有は読むだけで済み、上位のセッションは要らない。上位の hub が効くのは、PJ が 3 つ以上同時に動くときや、PJ をまたぐ引き渡しが頻繁なとき。その状況になっているかは、このマシンの記録だけでは測れない（主に使うマシンが別）ので、記録から測れる進む条件を置いて後に回す
- **案 C を採らない理由**: 上位の hub ができれば、送受信はその hub が担う。並列の経路を先に作ると、上位の hub を作るときに二重になる

## 設計判断ログ

- [→ADR候補 → ADR-20261029233229] PJ をまたぐ連絡は、hub どうしの直接の送受信ではなく、読むだけの横断と、条件を満たした後の上位の hub で扱う（並列の経路は作らない）
- [→ADR候補 → ADR-20261029233251] 別 PJ との重なりは、自動の連絡（ADR-20261025152955 の段取り）には入れず、lead に出す。brief の「重なりに注意」には載せる（ADR-20261025152955 の決定 2・3 の範囲の解釈）
- [local] どこまで見せたかの印は、`sent` と同じく journal の行数で hub.json に持ち、status の 11. の `--mark` だけが進める（時刻で比べると同じ秒の前後が決まらず、日付で比べると取りこぼす）
- [local] 「同じ repo か」は git の共通ディレクトリで判定する（worktree どうしで一致する。別の clone は対象外）
- [local] `overlaps` は hub.py が決定的に出す（`changed` ∪ `uncommitted` の共通部分）。brief で Issue の範囲と突き合わせる判断は今までどおり Claude が行う
- [local] 判定できなかったもの（`note` つきの sub・読めない PJ）は「無い」と区別して出し、「別 PJ」の節を省かない
- [local] 別 PJ の facts は横断に載せない
- [local] サブコマンドの名前は `cross`（`peer` は ListAgents の「Peer sessions」と `--peer-count` が既に使っている）

## 実装で決めたこと（段 1・2026-10-29）

- サブコマンドは `cross`（読むだけ）と `cross --mark`（hub だけ）。`presence_checked` は別の PJ の `presence.json` の更新時刻（無ければ null）
- `cross` の `active_projects` は、自分の PJ を含む active な PJ の総数。読めない config の PJ は数えない
- 作業中の登録のうち、worktree の git の共通ディレクトリが取れないもの（worktree が消えた）は、共有する repo のものかが分からないので `sessions` に `repo: null`・`note` つきで残す（重なり不明）。worktree が実在して相手の config の repos に当たらないものは返さない
- 自分の側で重なりを判定できない作業中の sub（`changed: null`）は、相手に同じ repo の作業中の sub がいるときだけ `mine_unknown` で返し、SKILL は「別の PJ」の節に「重なり不明」と出す（`sessions` には相手の sub しか入らないので、別の欄にした）
- 別 PJ の hub.json・journal・config の中身が壊れているとき（不正な UTF-8・`repos` が配列でない など）も、その PJ を `unknown` に回し、ほかの PJ は出す
- `--mark` は、読めなかった PJ の前回の重なりを `cross_last_overlaps` に残す（次に読めた回に、続いている重なりを新しいと数えない）。journal より長い印（同じ名前で作り直した PJ など）は使わず、印の無い PJ と同じく直近 14 日の窓で出す
- 初回の決定の出し方は (a)（直近 14 日）で確定した。14 日は、決定が初めて出てきた journal の行の `ts`（その PJ の hub が ingest した時刻）で測る。sub が書く `date` では測らない
- 別の PJ との重なりの行がある brief は、`auto` の PJ でも送る前に全文を見せて承認を取る（ADR-20261029233251 の決定 3。self-review で、既にある sub への brief が承認なしに届く経路が見つかったため）
- `decision_rows` は `decision_entries`（初出の行番号つき）の上に作り直した。`cross` の新しい決定は「初出の行が印以上」で決め、書き直しでは出直さない

## 未解決事項 (open)

- **在席の記録が古いときの扱い**: (a) 日付を添えるだけ（採用案）— pros: 単純 / cons: 古い警告が残る。(b) N 日より古い PJ の重なりは「在席不明」に倒す — pros: 誤った警告が減る / cons: 本物の重なりを不明にする。方向性は (a)。確定タイミング: 段 1 を使い始めて 14 日後、進む条件の見直しと一緒に
- **進む条件の数値**: 上の 3 つは暫定。確定タイミング: 段 1 を使い始めて 14 日後に `cross` の行を集計して見直す（担当: lead）
- **上位の hub の形**: PJ の hub を上位の hub の sub として登録する方法。方向性: report に PJ の hub 向けの形（`issue` の代わりに `project`）を足し、relay はそのまま使う。確定タイミング: 進む条件を満たしたとき、この doc を supersede する新しい doc で決める

## 実装ブリッジ (Implementation Bridge)

1. 実装着手の単位: 段 1 を 1 Issue で実装する。
   - `/feature-dev project-hub の PJ 横断（hub.py cross と brief・status の別 PJ の節） design=.claude/designs/20261029-project-hub-cross-project-view.md`
   - 変更対象:
     - `project-hub/scripts/hub.py`: `scan_projects` と `active_projects_on` の作り直し、`session_rows` の切り出し（`worktrees` はこれを使う）、`decision_rows` の初出の行番号、`cross` / `cross --mark`、JOURNAL_KINDS、hub.json の `cross_seen_lines` / `cross_last_overlaps` と takeover の引き継ぎ、state.md の直近の表と注入の数から `cross` を外す、argparse の登録
     - `project-hub/skills/hub/SKILL.md`: brief の 1. と「重なりに注意」、status の 8.5・10.・11.・完了基準、「自動の連絡」の段取りの行、`cross` が失敗したときの扱い
     - `.claude-plugin/scripts/tests/test_project_hub_scripts.py`、`project-hub/README.md`、`project-hub/CHANGELOG.md`
   - 段 2 は、進む条件を満たしたときに新しい design doc で設計する（この doc では Issue に分けない）
2. 検証方法:
   - CLI テスト（同じ repo の worktree を持つ 2 つの PJ と、持たない 1 つの PJ を作る）:
     - `cross` が前者だけを返す。closed の PJ・作業中でない sub（done・不在）を返さない
     - `overlaps` が `changed` ∪ `uncommitted` の共通部分を返す。`changed: null` の sub は `overlaps` に入らず、`note` つきで残る
     - 別 PJ の config が壊れていると `unknown` で返し、止まらない
     - `cross` は何も書かない（呼ぶ前後で、自分と別 PJ のディレクトリのファイルの中身が変わらない）
     - `--mark` の後は、その後に初出の決定だけを返す。書き直された同じ決定は出直さない。`unknown` の PJ の印は進まない
     - `--mark` は hub でないセッションから呼ぶと exit 3。takeover の後も印が残る
     - `active_projects_on` の挙動（report の PJ 判定）が変わらない（既存のテストが通る）
   - 「黙る条件」を厚くする: 別 PJ が 0 件・repo を共有しない・closed のときは `projects` と `unknown` が空で、SKILL が節を省く。`unknown` か重なり不明があるときは節を省かない
   - SKILL の文言契約テスト: brief の「重なりに注意」と status の 10. に別 PJ の節があり、別 PJ の名前が「」に入る。段取りの連絡の行が自分の PJ の `worktrees` に限られている
3. 実装完了時の doc 更新手順:
   - frontmatter の `phase: target` → `current` に更新し、`last-validated` を更新する
   - 実装で決めたこと（初回の決定の出し方など）を「実装で決めたこと」の節に追記する。方式ごと変わったら supersede する
   - 段 2 に進むときは、この doc を supersede する新しい doc を作る

## 関連

- 関連 Issue: なし（起票は実装ブリッジの 1.）
- 関連 spec: なし
- 関連 ADR: ADR-20261029233229（PJ 横断は読むだけ→上位）、ADR-20261029233251（別 PJ の重なりは自動の連絡に入れない）、ADR-20261025152955（自動の連絡。sub への連絡の承認の扱いと、見せた所までの印）、ADR-20261027002221（Desktop の hub は sub の会話の ID へ送る）
- 関連 design doc: `.claude/designs/20261021-project-hub-plugin.md`（project-hub の全体設計）
