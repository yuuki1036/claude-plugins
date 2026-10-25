---
id: 20261021-project-hub-plugin
title: project-hub — 複数セッションを束ねて PJ を進める hub のプラグイン
status: draft
phase: current
last-validated: 2026-10-25
supersedes: []
superseded-by: null
issue: "GitHub issue #308"
spec: null
adrs: ["20261021140738", "20261021154740"]
tags: [project-hub, multi-session, hooks, send-message, new-plugin]
---

# project-hub — 複数セッションを束ねて PJ を進める hub のプラグイン

## TL;DR

1 つのセッションを hub にする。PJ の状態（作業セッション・PR・Issue・判断）は `~/.claude/project-hub/<project>/` の追記ログとスナップショットから作る表で持つ。作業側は決まった形の report をファイルで置き、SendMessage では「置いた」とだけ知らせる。hub から作業側へは本文を SendMessage で送り、全文を hub 側の journal に残す。宛先は名前で引き、送る直前に毎回引き直し、1 件に決まらなければ送らない。

## 背景 / 課題

業務リポジトリ A の PJ（Issue 十数件・作業セッション 3〜5 本が同時に動く）で、1 セッションを hub にして living spec と会話の文脈だけで回した。起きたことは次のとおり（#308 本文）。

- 進捗を living spec の決定ログに足し続けて膨らみ、living-spec-maintain が Critical を出した（数十行をタイムラインへ移した）
- 作業セッションが名前を変える・開き直すと、名前宛ての SendMessage が `No agent named ... is reachable` で届かない（2 回）
- hub の思い込み（デプロイの経路・監査ログの項目）が裏取りなしに作業側へ伝わり、後で訂正した
- 外部（デザイナー）へ渡した一覧への訂正が判断のたびに溜まり、まとめて 4 点になった
- 状態がコンテキストにしか無く、コンパクションのたびに要約頼みになる

既存のプラグインはどれもこの層を持たない。issue-workflow の dashboard / start は 1 リポジトリ・1 セッションの範囲で、データはその repo の `.claude/` 配下にある。PJ が複数の repo をまたぐ場合や、hub がどの repo にもいない場合を扱えない。living-spec-workflow は設計の収束を扱い、進捗は書かない。

## ゴール / 非ゴール

- **ゴール**:
  - hub の状態をコンテキストの外に置き、コンパクションと開き直しを越えて続けられる
  - 作業セッションの改名・開き直しで連絡が途切れない（途切れたら気づける）。別のセッションへ誤って送らない
  - 作業側へ渡す事実を、出典つきで確かめたものに限る
  - 作業側の報告を決まった形で受け、取りこぼさない
- **非ゴール**:
  - 判断の正本を持つこと — 正本は Issue トラッカーの本文とリポジトリの仕様 docs に置く（hub が持つと二重管理になる）
  - Issue トラッカーへの書き込み — 起票・更新は issue-workflow / 人間の領分
  - 作業セッションの起動・停止の自動化 — 起動手段がアプリ（Desktop の start_session）と CLI で違い、どちらにも寄せられない。新しいセッションへの最初の brief は、lead が最初のプロンプトとして貼る
  - マシンをまたいで 1 つの hub を共有すること — データはマシンごとに置き、git 同期の対象から外す（config の repos のパスもマシンごとに違う）
  - living spec との統合 — 進捗を living spec に書かない。連携は段階 ② の `decide` の受け渡しだけ
  - 段階 ② ③ の詳細設計 — 段階 ① を 1 PJ で使ってから、この doc の改訂で詰める

## 確定した前提

### ユーザーが確定したこと（2026-10-21）

- **新プラグインにする**（component-addition-advisor の判定）。blocker: PJ が複数の repo をまたぎ、hub がどの repo にもいないことがあるので、状態を repo の外に置き、セッションをまたいで持つ必要がある。issue-workflow のデータ置き場（repo の `.claude/` 配下・slug 単位）とは粒度が合わない。fallback: issue-workflow:dashboard と living spec を手で回す今のやり方
- **Issue トラッカーは hub が直接読む**。hub が要るのは状態・担当・紐づく PR の数列だけなので、`gh issue view --json` / Linear MCP を自前の短い呼び出しで読む。issue-workflow には依存せず、スクリプトの複製も作らない（CLAUDE.md「各プラグインは独立して動作すること」「複製は分割単位の誤りのシグナル」）
- **作業側 → hub の report はファイルで置き、SendMessage は通知にだけ使う**。理由は「検討した代替案」の SendMessage の項
- **置き場所は `~/.claude/project-hub/<project>/`**（design review の F1）。`~/.claude` は git リポジトリで、origin は private の GitHub リポジトリ。複数マシンで同期している。この場所は `.gitignore` のどのパターンにも当たらなかった（`~/.claude/hub/` で `git check-ignore` rc=1）。そこで init が `<root>/.gitignore`（中身 `*`）を置く。ディレクトリ名は plugin-manager の `~/.claude/plugin-manager/` にならってプラグイン名にした
  - `${CLAUDE_PLUGIN_DATA}` を採らない理由: 実体は `~/.claude/plugins/data/<plugin>-<marketplace>` と `<plugin>-inline` で、入れ方ごとに別の dir になる（`ls ~/.claude/plugins/data` で確認）。marketplace 版と inline 版のセッションが混ざると、hub と作業側で別の場所を見る。harness-keeper はこの場所から離れたことがある（再インストールで履歴が消えるため。`harness-keeper/CHANGELOG.md:248`）
- **段階 ① の範囲**（design review の F11）: 状態ファイル・hub の skill・report・注入 hook。report を段階 ① に入れるのは、inbox の方式では report が無いと status が取り込むものが無いため（#308 は段階 ② に置いていた）。作業側の登録は report が兼ね、登録用の hook は作らない。claim-verifier は段階 ③（送信前の検査と同じ段）へ送る
- **skill は 2 本**（design review の F10）: hub 側の `hub`（サブコマンド）と、作業側の `report`。`docs/skill-writing.md:12` の「独立した起動語が要るか、他の skill から呼ぶときだけ分ける」に従う。report は別のセッションで別の起動語を持つので分ける
- **hub → 作業側（brief / relay）は本文を SendMessage で送る**（design review の F2）。全文は hub 側の journal に残す。作業側にとっては今読む指示なので、ファイルに置いても、通知が保留されれば読まれない点は同じ。これに合わせ、ADR-20261021140738 の決定 1 の範囲を report の向きに絞って supersede した（ADR-20261021154740）

### 実測と一次ソースで確かめたこと

- **SendMessage の宛先は名前で、セッション ID は使えない**（要検証 (a)。2026-10-21）
  - ツール説明（SendMessage・CC 2.1.302）: 「the name IS the address; there is no separate address syntax」。` [ref]` は同名が 2 つあるときだけ付け、「A ref you did not just read from a listing or an error will not resolve」。raw の agentId（`a...-...`）は in-process の subagent 用
  - 実測: `--session-id 11111111-2222-4333-8444-555555555555 -n hubtest-worker` で起動したセッションは、ListAgents に `hubtest-worker [227051]` と出た。ref はセッション ID の先頭と一致しない。セッション ID 宛ての送信は `No agent named '11111111-…' is reachable` で失敗した（#308 で出たのと同じ文言）。この回は受信側が認証エラーで先に終了していた可能性があったので、受信側が ListAgents に `busy` と出ている間に測り直した（`22222222-…`）。結果は同じ文言での失敗だった。名前宛て（`hubtest-busy`）は同じ相手に届いた
  - `-n` で付けた表示名がそのまま ListAgents の名前になった。Desktop のセッションも会話の題に当たる名前で出ていた（題と同一であることは下の sessionTitle の項で確認済み）。名前を付けていないセッションは `claude-plugins-96` のような既定名で出る。どちらにせよ利用者が改名すると宛先が変わる
- **ListAgents の出力は人間向けの自然文で、書式の契約は見つかっていない**。例: `claude-plugins-96 [f3183e]  ·  interactive  ·  waiting  ·  started 1m ago`。名前は空白を含みうる
- **ListAgents / SendMessage / Linear MCP は Claude のツールで、hook やシェルスクリプトからは呼べない**
- **他セッションから届いたメッセージで、受信側の UserPromptSubmit は発火する**（要検証 (b)。2026-10-21 に実測）。受信側はヘッドレスの `claude`（haiku）で、UserPromptSubmit の stdin をファイルに追記するだけの hook を `--settings` で入れた。送信側はこのリポジトリの Desktop のセッション
  | 受信側の状態 | 届き方 | UserPromptSubmit |
  |---|---|---|
  | 入力待ち（`-p --input-format stream-json` で stdin を開いたまま、1 ターン目の後） | 新しいターンとして始まる | 発火（送信の直後） |
  | API 呼び出しの合間（`-p` の 1 ターン目の途中） | ターンの途中に入る | 発火（送信の直後） |
  | ツールの実行中（`python3 -c 'import time; time.sleep(60)'`） | transcript に `queue-operation: enqueue` と `queued_command` が残り、ツールが終わるまで保留された | 発火（ツールの終了時。送信から約 53 秒後） |
  - hook の `prompt` には、包みごとの全文が入る: `<cross-session-message from="uds:/tmp/cc-socks/<pid>.sock" from-session="local_<uuid>" from-name="<送信側の名前>" from-mode="prompting">` + 本文 + `</cross-session-message>`
  - `from` は送信側のプロセスごとのソケットで、ツール説明は返信の宛先にこれを使うよう指示している。プロセスが変われば変わるので、保存する宛先には使えない
  - `from-session` は送信側の `CLAUDE_CODE_HOST_SESSION_ID`（Desktop の `local_<uuid>`）と同じ値で、CLI のセッション ID とは別の値
  - 測っていないもの: 対話の TUI と Desktop のセッションが受信側のとき。受信側の permission mode が送信側と違うとき（ツール説明では、メッセージは受信側の利用者の承認待ちになり、期限切れもありうる）
- **skill が自分の session_id を得る手段**: Desktop のセッションの Bash 環境には `CLAUDE_CODE_SESSION_ID`（CLI のセッション ID）と `CLAUDE_CODE_HOST_SESSION_ID` がある（2026-10-21 に確認）。SKILL.md の本文では `${CLAUDE_SESSION_ID}` が展開される（`harness-keeper/skills/cc-catch-up/references/plugin-features.md:136`）。hook の stdin の `session_id` と `CLAUDE_CODE_SESSION_ID` を同じ ID として扱う前例は `code-review/hooks/scripts/publish-guard.sh`。この前例は「env に載ることは保証されていない」として stdin を優先している。CLI での値は下の「CLI でも session_id の 3 つの取り方は同じ値になる」で確認済み（同名の command と skill では `${CLAUDE_SESSION_ID}` が展開されるのは command の本文だけ）
- **hook の stdin に `session_id` がある**（上の実測で UserPromptSubmit の stdin に `session_id` / `transcript_path` / `cwd` が入っていた）
- **hook のイベントに SessionStart / PostCompact / UserPromptSubmit / SessionEnd がある**（`.claude-plugin/schema/hooks.schema.json` の enum）。SessionStart と PostCompact の stdout で注入する前例は `issue-workflow/hooks/scripts/inject-rules.sh`（`issue-workflow/hooks/hooks.json` で SessionStart の matcher `""` と PostCompact の両方につないでいる）
- **issue-workflow の set-session-title は、作業側の名前を決まった形にする前例としては弱い**。セッションのタイトルを `<ID>: <タイトル>` にするが、付くのは次をすべて満たすときだけ: ブランチ名に `[A-Z]+-[0-9]+` がある（`set-session-title.sh:13`）、feature ブランチにいる（`:11`）、issue-workflow の Issue ファイルがある（`:23-24`）。さらに `once: true` なので、main で始めて後からブランチを切るセッションには付かない。GitHub の数値の Issue ID には効かない。sessionTitle が ListAgents の名前になることは下の項で確認済み
- **hook_harness.py は HOME を隔離しない**（`CLAUDE_PROJECT_DIR` と `CLAUDE_CODE_SESSION_ID` は隔離する）。置き場所の root を変数で差し替えられないと、テストが開発機の実データを読み書きする
- **hook の `sessionTitle` で付けた題は、そのまま ListAgents の名前になる**（未解決事項 1 を決着。2026-10-21 に実測）。ヘッドレスの `claude -p`（CC 2.1.302・haiku）に、UserPromptSubmit で `{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","sessionTitle":"PHUB-7: probe title"}}` を出す hook を入れて起動し、別のセッションの ListAgents に `PHUB-7: probe title [262901]` と出た。Desktop のセッションも会話の題がそのまま名前になる（このセッションの `get_session` の `title` と ListAgents の「This session is …」が一致）。どちらも利用者が改名すれば変わるので、採用案（登録名を主・Issue ID を補助）のまま。brief で「会話の題に Issue ID を入れる」と頼めば 2 番目が効く
- **CLI でも session_id の 3 つの取り方は同じ値になる**（未解決事項 2 を決着。2026-10-21 に実測）。上と同じヘッドレスの `claude -p` で、Bash の `CLAUDE_CODE_SESSION_ID`・SessionStart / UserPromptSubmit の stdin の `session_id`・SKILL.md 本文の `${CLAUDE_SESSION_ID}` の展開がすべて同じ値だった。測っていないもの: ターミナルで対話の TUI として起動したとき（同じバイナリだが未確認。実装ブリッジの「実機」に入れた）
  - `CLAUDE_CODE_HOST_SESSION_ID` は、Desktop のセッションの Bash から起動した CLI に**起動元の値がそのまま継承されていた**（CLI 自身の値ではない）。段階 ② で `from-session` と結び付けるときは、この値を無条件には信じない
  - `${CLAUDE_SESSION_ID}` が展開されるのは、注入される本文（同名ペアなら command の本文）だけ。同名ペアの SKILL.md は Read で読むので展開されない。そこで commands の本文にこの変数を置き、`hub.py` は Bash の `CLAUDE_CODE_SESSION_ID` を先に使い、引数と両方あって違えば止める
- 帯（mod）は issue-workflow の `hooks/issue-band.tsx` に前例がある（読むだけで書かない mod）。段階 ① では作らない

## 採用案

### 全体像

```
<root> = ${PROJECT_HUB_DIR:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/project-hub}
<root>/.gitignore              中身は `*`（init が置く。git 同期の対象から外す）
<root>/<project>/
  config.json                  PJ の設定（hub init が作る）
  hub.json                     いまの hub の session_id と名前（init / takeover / status が書く）
  journal.jsonl                起きたことの追記ログ（hub だけが書く）
  facts.jsonl                  確かめた事実（出典つき。brief はここからだけ引く）
  snapshot.json                status が集めた外部の状態（gh・トラッカー・ListAgents。取得時刻つき）
  state.md                     journal・sessions・snapshot から script が作る表（注入する）
  presence.json                ListAgents に名前が無かった登録と、改名した後の名前（hub だけが書く。実装で追加）
  sessions/<session_id>.json   作業側の登録（report だけが書く）
  inbox/<ts>-<session_id>.json 作業側の report（report が一時名で書いてから rename する）
  inbox/done/                  取り込み済みの report
```

```
作業側セッション                                         hub セッション
 report skill ── sessions/<id>.json（登録）──────────┐
             ── inbox/<ts>-<id>.json（本文）─────────┼──> hub status: inbox を取り込み journal に追記 → done/ へ移す
             └─ SendMessage「report を置いた」（通知）┘        外部の状態を集めて snapshot.json → script が state.md を作る
                                                          hub brief / relay: 宛先を引き直し、lead の承認の後に本文を送る。全文を journal へ
 （最初の brief は lead が最初のプロンプトとして貼る）      SessionStart / PostCompact hook: hub.json と一致すれば state.md を注入
```

### ファイルの形

- `config.json`: `{ "project", "status": "active|closed", "tracker": {"kind": "github|linear", "repo"|"team"/"project", "milestone"?}, "repos": [{"path", "base"}], "approval": {"prefix", "suffix"} }`。PJ 固有の決まり（PR のラベル・向き先）はここに置き、プラグイン本体に入れない。公開先での置き換えは guardrail-protect の設定が正本なので、ここには持たない
- `hub.json`: `{ "session_id", "name", "updated" }`。`name` は ListAgents の自分の行（「This session is X [ref]」）から取る
- `journal.jsonl`: 1 行 1 件 `{"ts", "kind", "subject", "body", "source"}`。`kind` は段階 ① では `relay | brief | report | fact | takeover | close` のどれか（段階 ② で `merged` / `decide` を足す）。relay と brief は送った全文と、解決した宛先・送信の結果（受理 / 失敗）を残す。送信の受理は「相手が読んだ」を意味しない。report は取り込んだファイル名を `source` に入れ、再取り込みの重複を防ぐキーにする
- `facts.jsonl`: `{"id", "ts", "claim", "source", "checked_by", "supersedes"?}`。`source` が無い行は書かない。`checked_by` は `hub`（hub が自分で確かめた）か `null`（作業側の主張をそのまま写したもの）。brief が引くのは `checked_by` が入った行だけ。訂正は新しい行で、`supersedes` に前の行の `id` を入れる（追記のみ）。訂正の正本は facts だけで、journal には `fact` の行で id を指すだけにする。出典が config の repo の中のファイルなら `repo` / `path` / `base_sha`（確かめた時点の base）を足す（実装で追加）
- `snapshot.json`: `{ "sources": { "<名前>": {"fetched_at", "ok", "data"} } }`。取得に失敗した source は前回の `data` を残し、`ok: false` と失敗時刻を書く。repo ごとに取る PR は `prs:<repo のパス>` を名前にする。取得の上限に届いた回は `truncated_at` を付ける（実装で追加）
- `state.md`: 冒頭に生成時刻と、journal の何行目までを反映したかを書く。report の自由文（`needs_lead` / `follow_ups` / `claims`）は写さず、件数・状態・ファイル名だけを載せる（作業側が読んだ外部の文面が、承認なしに hub のコンテキストへ入るのを防ぐ）。冒頭に「通知を受けたら取り込まず、未取り込みの件数を 1 行出すだけにする」を置く
- `sessions/<session_id>.json`: `{"session_id", "host_session_id"?, "name", "ref"?, "project", "issue", "branch", "worktree", "updated"}`（`absent_since` は実装で `presence.json` へ移した。「実装で決めたこと」。`ref` は report の時点の自分の ref で、改名した後の行を結び付ける照合にだけ使う / 2026-10-25 に追加）。書き手は report だけで、report のたびに丸ごと書き直す。`branch` / `worktree` は report の時点で git から取る。`host_session_id` は `CLAUDE_CODE_HOST_SESSION_ID`（あれば）で、段階 ② で通知の `from-session` と結び付けるのに使う
- `inbox/*.json`（report の形）: `{"session_id", "name", "project", "issue", "state": "hello|in_progress|blocked|ready_for_review|done", "pr"?, "needs_lead": [..], "follow_ups": [..], "claims": [{"text", "source"}]}`。`hello` は最初の brief を受けた直後の自己登録。`claims` の `source`（`path:line` 等）は必須

### session_id と PJ の決め方（report）

- session_id は Bash の `CLAUDE_CODE_SESSION_ID` から取る。空の環境だけ、command の本文で展開した `${CLAUDE_SESSION_ID}` を `--session-id` で渡す（同名の command と skill では SKILL.md は Read で読むので展開されない）。両方あって違えば止める。どちらも無ければ書かずに止まり、利用者に伝える
- 名前は ListAgents の自分の行から取る。解析が合わなければ（下の「ListAgents の扱い」）書かずに止まる
- PJ は brief が渡す `--project <name>` で決める。指定が無いときは、`status: active` の config のうち repos に cwd の git common dir を含むものが 1 つだけならそれにする。0 件か 2 件以上なら書かずに止まる

### 宛先の引き方

送る直前に毎回 ListAgents を引く。Claude が一覧を `[{name, ref, state}]` の JSON に抜き出して script に渡し、script は照合だけを持つ。

- **hub → 作業側**（brief / relay）
  1. 登録の `name` と完全一致する行が 1 つだけで、その登録が不在（`presence.json` の `absent_since`。ListAgents に名前が無かった最初の時刻）になっていない → それ
     - 登録が `ref`（report の時点の自分の ref）を持ち、その ref の行が今の一覧に 1 つだけあるときは、その行を同じセッションとみなす。名前の行と ref の行が同じならそれ、名前の行が無ければ ref の行（改名した。`warning` 付き）、名前の行が別にあれば送らずに 3 へ（実装で追加 / GitHub issue #316。ref は改名では変わらない）
  2. 無ければ、Issue ID がトークンとして一致する行が 1 つだけ → それ。トークンの形は tracker で決める: linear は `ABC-12` を語境界つきで、github は `#308` を語境界つきで照合する。既定名の形（`<dir>-<数字>`）の行は候補から外す
     - 不在の登録でも、登録名と完全一致する行が今の一覧に 1 つだけあり、その名前がほかの登録・ほかの PJ・hub のものでなければ、Issue ID の一致と並ぶ候補にする。候補を合わせて 1 行に決まればそれ（どちらも `warning` 付き）、2 行以上なら 3 へ（実装で変更 / GitHub issue #316。`presence.json` は前回の status の時点の値で、今の一覧に戻った名前を次の status まで捨てていた）
  3. それ以外（0 件・2 件以上）は送らず、lead に「宛先が決まらない（登録名 X / 候補 N 件）」と出す
  - 送る前の承認の画面に、解決した宛先の名前と ref を出す。lead はそこで宛先も確かめる
- **作業側 → hub**（report の通知）: `hub.json` の `name` と完全一致する行が 1 つだけならそれに送る。決まらなければ通知だけ省き、利用者に「report は置いた。hub への通知は送れなかった」と伝える（report のファイルは残るので、hub の次の status で取り込まれる）
- **最初の連絡**: 新しいセッションへの最初の brief は、lead が最初のプロンプトとして貼る。brief は冒頭で report の `hello` を出すよう指示し、作業側はそれで名前と session_id を登録する。それ以降の hub → 作業側は上の 1・2 で引ける。既にあるセッションへ最初に送るときは、lead が承認の画面で候補から選ぶ（選んだ行の ref で引き直す。実装で決めた）

### ListAgents の扱い

- 書式に契約が無いので、抜き出した結果を自己検査する: 見出しの `Peer sessions (N)` と抜き出せた行数が一致し、各行で name・ref・state がそろっていること。合わなければ「解析失敗」として送らず、生の出力を lead に出す（「見つからない」と区別する）
- script のテストは JSON の照合だけを固定する。抜き出しは SKILL.md の手順で、書式が変わったときに自己検査で止まることを確かめる

### hub の引き継ぎと PJ の終わり

- `hub init` は config が無いときだけ作る。既にあれば作らず、`hub takeover` を案内する
- `hub takeover` は config・journal・facts に触れず、`hub.json` を今のセッションに書き換え、journal に `takeover` を残す
- `hub status` は、`hub.json` の session_id が今のセッションと違えば、最初に「この hub は別のセッションで登録されている。引き継ぐなら takeover」と出す
- `hub close` は config の `status` を `closed` にする。closed の PJ は report の自動判定の対象から外れる

### 部品（段階 ①）

| 部品 | 種類 | 中身 |
|---|---|---|
| `hub` | skill（hub 側） | サブコマンド `init` / `status` / `brief <Issue>` / `relay` / `fact` / `takeover` / `close` |
| ├ `status` | | inbox を取り込み（journal に追記 → done/ へ移す。取り込めないファイルは inbox/invalid/ へ退避して lead に出す。実装で変更）、gh・トラッカー・ListAgents・`sessions/` を集めて snapshot.json を書き、script で state.md を作り直す。表・止まっている箇所・マージ順を出す |
| ├ `brief <Issue>` | | base の SHA、作業中のブランチとの重なり、`checked_by` の入った facts、溜まった注意点から文面を作る。重なりは `git diff --name-only <base>...<branch>` に加え、登録の worktree で `git status --porcelain`（未コミットの変更）も突き合わせる。冒頭に report の `hello` の指示と `--project` を入れる。新しいセッションには lead が貼り、既にあるセッションには relay の経路で送る |
| ├ `relay` | | config の前置きと締めを付け、宛先を引き直し、lead の承認の後に送り、全文を journal に残す |
| └ `fact` | | hub が自分で確かめた事実を出典つきで facts に足す（`checked_by: hub`）。#308 の問題 3（hub の思い込み）は、brief が facts からだけ引くことで塞ぐ |
| `report` | skill（作業側） | report を inbox に置き（一時名 → rename）、`sessions/<session_id>.json` を書き直し、hub に通知を送る。通知の文面は固定で「report を置いた（<ファイル名>）。hub の status で取り込む」 |
| 注入 | hook（SessionStart / PostCompact） | stdin の session_id が `hub.json` と一致したときだけ、state.md と、その生成時刻より後の journal の件数（kind 別）を注入する。一致しなければ黙る。SessionStart は startup / resume / compact のどれでも同じ判定 |

共通処理（journal の追記・inbox の取り込み・宛先の照合・state.md の生成）は `scripts/` に寄せ、SKILL.md に bash を書き下ろさない。scripts と hook は root を `PROJECT_HUB_DIR` で差し替えられるようにする。hub の skill は走査・分析の深掘り系ではないので、`${CLAUDE_EFFORT}` の分岐は持たない。

### 変更対象ファイル（段階 ①）

- 新規: `project-hub/.claude-plugin/plugin.json`（`_requirements` に gh）/ `commands/{hub,report}.md`（同名の skill を Read させる 1 行を置く）/ `skills/{hub,report}/SKILL.md` / `hooks/hooks.json` / `hooks/scripts/inject-state.sh` / `hooks/scripts/check-deps.sh` / `hooks/lib/safe-hook.sh`（正本の複製）/ `scripts/` / `README.md` / `CHANGELOG.md`
- 更新: `.claude-plugin/marketplace.json` / `INDEX.md` / `CLAUDE.md` のプラグイン一覧
- テスト: `.claude-plugin/scripts/tests/test_project_hub_hooks.py`（hook_harness で「黙る条件」を厚く）/ `test_project_hub_scripts.py`
- evals: `evals/cases/project-hub.yaml`。起動語は issue-workflow の dashboard（「プロジェクト状況」「進捗確認」）・init（「プロジェクト初期化」）と重ならないよう「hub」を含める

## 検討した代替案

| 観点 | 案 A（採用）新プラグイン + ファイル inbox | 案 B issue-workflow に hub スキルを足す | 案 C living spec を hub に使い続け、タイムラインを別ファイルに分ける |
|------|------------|------|------|
| 変更量 | 中（新プラグイン一式） | 中（13 → 14〜15 スキル） | 小 |
| 状態の置き場所 | repo の外（マシンごと）。複数の repo をまたげる | repo の `.claude/`。slug 単位 | living spec と同じ場所 |
| 宛先の改名・開き直し | 送る前に引き直す。決まらなければ送らない | 同じ仕組みを入れれば可 | 対処なし |
| コンパクション | state.md を hook で注入 | 同じ仕組みを入れれば可 | 要約頼みのまま |
| 他プラグインとの関係 | 依存も複製もなし | トラッカーの読み取りを共有できるが、データ置き場と粒度が既存と食い違う | living-spec の責務（収束）に進捗が混ざる |

- 案 B を採らない理由: 状態を repo の外に置くと、issue-workflow の `{DATA_DIR}` 規約・backend 判定（Phase 0）の前提から外れた別系統がプラグイン内にでき、hub 系だけが別の置き場所を持つ
- 案 C を採らない理由: 問題の 5 件のうち、膨張しか直らない
- **report を SendMessage の本文だけで受ける案**を採らない理由: UserPromptSubmit は発火する（確定した前提）。しかし本文が会話を通るので、コンパクションで要約される。ツール実行中の hub には、そのツールが終わるまで届かない。permission mode が違うと受信側の承認待ちになり、期限切れもありうる（ツール説明。未実測）
- **hub の UserPromptSubmit hook が包みを丸ごとファイルへ書く案**を採らない理由: コンパクションの問題は消える。ただ hub 側の hook が発火することに頼るので、受信側が TUI / Desktop のとき（未測定）と承認待ちのときに記録が落ちる。作業側がファイルを書く方式なら受信側に左右されない。段階 ② では、この hook を通知の受信の記録にだけ使う
- **hub → 作業側も outbox にファイルで置く案**を採らない理由: 作業側にとって brief / relay は今読む指示で、通知が保留されればファイルも読まれない点は同じ。記録は hub 側の journal に全文を残せば足りる。誤配したとき本文が漏れにくい利点はあるが、誤配は宛先の照合（1 件に決まらなければ送らない・承認画面で宛先を確かめる）で防ぐ
- **作業側の登録を SessionStart hook で書く案**を採らない理由: SessionStart の時点ではブランチも worktree もまだ決まっていないことが多い（issue-workflow:start は main で始めて後から切る）。名前も最初の report まで分からない。書き手が hook と report の 2 つになり、上書きの規則が要る
- **skill を 5 本に分ける案**を採らない理由: 分ける条件（`docs/skill-writing.md:12`）に当たらず、description が全セッションに常駐する

## 設計判断ログ

- [local] hub のログの名前は `journal.jsonl`（#308 本文の `events.jsonl` から変更）。Event Bus の `.claude/events.jsonl` と同じ名前だと、規約（`event_bus_tail` で読む）の対象と取り違える
- [local] project-hub のファイルは project-hub だけが読み書きするので、Shared State の frontmatter（docs/shared-state.md）は付けない。他プラグインが読むようになったら付ける
- [local] facts は追記のみ。訂正は新しい行で前の行の id を指す（hub の思い込みが作業側へ渡った経緯を後から辿れるように）。訂正の正本は facts だけにする
- [local] inbox は取り込んだら `inbox/done/` へ移す（消さない）。順番は「journal に追記 → 移す」。途中で落ちても、journal に同じファイル名があれば取り込みを飛ばすので、取り込み直しても結果が変わらない
- [local] 注入 hook は stdin の `session_id` で自己判定する（CLAUDE.md の「hooks.json の if:/matcher に単独依存しない」）
- [local] state.md には report の自由文を写さない（作業側経由の文面を承認なしに hub へ注入しない）
- [local] journal の kind と config の欄は、段階 ① に書き手か読み手がいるものだけにする。`merged` / `decide` は段階 ② で足す
- [local] 宛先の方式の根拠は CC 2.1.302 のツール説明と 2026-10-21 の実測。SendMessage が安定した宛先（セッション ID など）を受け付けるようになる、または ListAgents の出力が構造化されたら見直す（cc-catch-up で SendMessage / ListAgents の変更を見つけたとき）
- [local] ADR-20261021140738 のコンテキストにある「UserPromptSubmit が発火するかは未確認」は、2026-10-21 の実測で「発火する」と決着した。範囲は ADR-20261021154740 で report の向きに絞った
- [→ADR候補] 作業側 → hub の report は本文をファイルで置き、SendMessage は通知にだけ使う。宛先は名前で引き、送る直前に ListAgents で引き直し、1 件に決まらなければ送らない（ADR-20261021154740 として切り出し済み）

## 実装で決めたこと（段階 ①・2026-10-21）

採用案から変えた・足した点。宛先の引き方と inbox の方式は変えていない（supersede ではなく追記）。

- **不在は hub 専用の `presence.json`（`{session_id: {absent_since}}`）に持つ**。「ファイルの形」の `sessions/<session_id>.json` の `absent_since?` を移した。hub の status と作業側の report が同じ登録ファイルを書き直すと、作業側の新しい名前を古い内容で上書きしうる（書き手をファイルごとに 1 つにする）。不在の後に report が来たセッションは不在として扱わない（`absent_since` と登録の `updated` を比べる。どちらもマイクロ秒の時刻）
- **hub 側で書くサブコマンドは、今のセッションが `hub.json` の hub でなければ exit 3 で書かない**（fact / record / ingest / presence / snapshot / render / close / refresh-hub）。takeover の後に古い hub が書き続けるのを防ぐ。status の冒頭の確認は `refresh-hub` が兼ね、名前が変わっていれば hub.json に反映する
- **Linear の Issue ID の照合は大文字小文字を区別する**（送らない側に倒す）。既定名（`<dir>-<数字>`）を照合から外すとき、名前がちょうど Issue ID のセッションは外さない
- **report に `schema: 1` を入れる**。hub と作業側で入っている project-hub の版がずれうる（marketplace 版と inline 版）ので、違う版は取り込まずに lead に出す
- **inject は「state.md の生成時刻より後」ではなく「state.md が反映した journal の行数より後」を数える**（state.md の先頭の機械用の行に行数を持つ）。あわせて未取り込みの inbox の件数を出し、closed の PJ は注入しない
- **ingest は今回取り込んだ report の中身（`needs_lead` / `follow_ups` / `claims`）を出力に含める**。status が lead に見せるため。state.md には引き続き写さない
- **brief の材料は `worktrees`（base の SHA・登録済みセッションの `changed` / `uncommitted`）と `facts --checked-only`（訂正で置き換わった行と未確認の行を除く）**。facts には作業側の主張を確かめずに控える `--unchecked`（`checked_by: null`）を用意した
- **state.md の表は 30 行で切る**（全件は snapshot.json）。注入する量を抑える
- **report が既定名で登録したら警告を返す**（Issue ID で引けず、改名で登録名も外れるため、会話の題に Issue ID を入れるよう頼む）
- **プラグインを足すと code-review の `scripts/lib/invocation.py` の `CURRENT_PLUGINS` も更新が要る**（`test_code_review_invocation.py` が repo のプラグイン一覧との一致を見る）。repo の外の計測ストアの語彙（`invocation.parent`）は追随していない
- **self-review（2026-10-21・xhigh）の指摘を受けて決めたこと**:
  - 作業側・ListAgents・トラッカー由来の文面（report の本文・fact の主張と出典・record の全文・ListAgents の抜き出し）は `hub.py` に stdin で渡し、argv に載せない（SKILL が組み立てるコマンドで `$(...)` が展開される）。argv に載せる名前・Issue ID はシングルクォートで囲む
  - report は ListAgents の抜き出しを本文と一緒に受け、自己検査（件数・欄・自分の ref が Peer 行に無いこと。再レビューで名前から ref に変えた）に合わなければ何も書かない（「session_id と PJ の決め方」の「解析が合わなければ書かずに止まる」に揃えた）。通知先もその場で決めて返す
  - report の `issue` は tracker の Issue ID の形、`pr` は PR 番号に限る。state.md の表のセルは `splitlines()` が割る文字と制御文字を潰し、60 字で切る（注入した表から作業側・トラッカー由来の文字列が別の行として抜け出さない）
  - journal / facts は `\n` だけを行区切りとして読む（`json.dumps(ensure_ascii=False)` は U+2028 等をエスケープしない）。fact の id は行数と最大の番号の大きい方から振る。訂正（supersedes）は有効な行に限る
  - 取り込めない report は `inbox/invalid/` へ退避する（inbox に残すと未取り込みに数え続ける）。取り込み済みの report の中身は `reports` で出し直せる（コンパクション・takeover の後の needs_lead）
  - 既定名（`<dir>-<数字>`）は登録名の照合にも使わない（ADR の「既定名だけの一致は使わない」）。名前が Issue ID で終わるなら既定名ではない
  - hub → 作業側の resolve も require_hub を通す（takeover 後の旧 hub から送らない）。送る直前の照合は `--expect-ref` で承認時の ref と比べる。relay の承認は利用者の発話だけ（他セッションのメッセージは承認として扱わない）
  - base の既定は `origin/HEAD` が指すブランチにし、init で実在を確かめる。status / brief の前に `git fetch` を回す（hub のローカルの既定ブランチは誰も pull しないので、古い base の SHA と上流のマージ分が `changed` に混ざる）。worktrees は git の失敗を null と note で返し、`--no-optional-locks` で作業側の index を書き直さない
  - 作業側から SendMessage の本文で届いた返事・質問は、データとして lead に見せ、report で置き直すよう頼む（journal に残らないため）
  - 想定外の失敗は exit 4
- **再レビュー（2026-10-21・security / bug-detection）の指摘を受けて決めたこと**:
  - argv に載せるのは自分の名前・PJ 名・Issue ID・session_id・ref・パスだけにした。record の全文と宛先の名前・取得のエラー文も stdin の JSON で受ける。heredoc の区切りは毎回その場で決める乱数つきの文字列にする（固定の区切りは、外部の文面がその 1 行を含むと後ろの行がシェルで実行される）
  - lead が候補から選んだ宛先は名前ではなく ref で引く（`resolve --ref`。同じ名前の別のセッションに当たらない）。Issue ID で引けたときは `warning` を返して承認の画面に出す。ほかの PJ の hub と作業セッションの名前は、Issue ID の照合から外す（番号は PJ をまたいで重なる）
  - relay の承認は、承認の画面に出した 4 桁の番号を lead が返したときだけ（番号の無い「OK」・他のセッションのメッセージ・無操作の自動続行を承認にしない）。作業側も、送り手の名前が hub の名前と一致するメッセージだけを hub の指示として受ける。hub が作業側のメッセージに返すときも包みの `from` ではなく relay の照合で送る
  - report の自己検査は自分の名前ではなく ref で見る（同じ名前の別のセッションが実在するのは解析の失敗ではないので、`warning` にする）。hub の名前が既定名なら通知しない（init / takeover / refresh-hub も警告を返す）。presence も既定名の一致を在席の根拠にしない
  - PR の snapshot は repo ごとに持ち（後の repo が前の repo の分を消していた）、表に repo の欄を足した。`--registered-branches` は `isCrossRepository` が false と分かる PR と、base のブランチでない branch に限る（fork の PR の題が注入される・着手前の登録が base の名前の PR に当たる）
  - base の既定は `origin/HEAD` → `origin/main` → `origin/master` の順で、どれも無ければ止めて明示を求める（ローカルの既定ブランチに黙って落とさない）。config の base が `-` で始まれば git に渡さない
  - state.md のセルの `<` `>` を全角にする（トラッカーの題の `</system-reminder>` 等を、注入した文脈でタグとして読ませない）
  - brief の事実の鮮度は facts の `stale`（確かめた時点の base と今の base のあいだで出典のファイルが変わったか）で見る。worktrees は base のブランチにいる登録と、他のセッションと同じ worktree の登録を「着手前の登録のまま・重なりは不明」として返す。brief は branch / worktree を作ったら report を置き直すよう指示する
  - 取得の上限（`--limit`）に届いた snapshot は打ち切りの可能性を表に出す
  - 細部: name の末尾の行区切りを弾く / refresh-hub などが exit 3 で止まるとき state.md の場所を stderr に出す / journal の末尾が改行で終わっていなければ改行を足してから追記する / git の出力は不正な UTF-8 を置き換えて読む / inject は hub の照合を先にし、hub でない PJ の config は読まない / `--repo` の `=` は最後のものを区切りにする

## 実装で決めたこと（運用の手間と見失いへの対応・2026-10-25）

GitHub issue #312 / #314 / #315 / #316 への対応。宛先の方式（名前で引き、送る直前に引き直す）と inbox の方式は変えていない（追記）。

- **改名は登録した時の ref で追う**（#316）。Desktop のセッションの題を変えても ListAgents の ref は変わらなかった（2026-10-25 に実測: 題の変更の前後で同じ ref）。report は登録に `ref` を残し、`resolve` と `presence` は名前で引けないときにその ref の行を同じセッションとみなす。送る宛先は今の一覧のその行の名前で、ref は照合にだけ使う（ADR-20261021154740 の「ref を保存して宛先に使わない」の範囲内）。改名した後の名前は hub 専用の `presence.json` に `current_name` で持つ（登録の書き手は report だけのまま）。名前の行と ref の行が別なら送らない（改名の後に別のセッションが元の名前を付けた可能性）
  - 却下: lead が候補から選んだ行（`--ref`）の名前で登録を書き直す案。登録の書き手が 2 つになり、作業側の新しい名前を古い内容で上書きしうる（段階 ① で presence.json を分けた理由と同じ）
- **通知はその場で取り込む**（#314）。`ingest` / `render` はファイルだけで動くので、通知を受けた時点で回し、中身を lead に見せる。ListAgents・トラッカー・PR の集め直しは `status` に残す。state.md の冒頭の手順もこれに合わせた
- **UserPromptSubmit hook は件数を見て取り込みを促すだけ**（#314）。hook から ListAgents は呼べず、report の文面を hook で注入すると承認なしに作業側の文面が入るので、注入するのは件数と取り込みのコマンドだけにした。通知（cross-session message）でも lead の発言でも発火するので、通知が届かなかった回も次の発言で拾う。すべての発言で走るので、このセッションの id を含む `hub.json` があるときだけ python を起動する
- **作業セッションへの紐付けは project-hub の SessionStart で案内する**（#315）。issue-workflow の `start` には手を入れない（プラグイン間の依存を作らない）。`inject` は、hub でないセッションの cwd（stdin の `cwd`）の repo が active な PJ に入っていて、そのセッションがまだ登録されていなければ、Issue の作業を始めたら `report hello` を置くよう案内する。SessionStart の時点では Issue ID が決まっていない回がある（`start` の中でブランチを作る）ので、hook が登録まではしない。hello を置くのは Claude で、利用者には確かめない（PJ の Issue か分からないときだけ確かめる）
  - 却下: `start` が `plugin-enabled.sh` で project-hub の有効を見て案内する案。issue-workflow 側に project-hub の手順の知識が入る。project-hub 側の hook なら、`start` 以外の始め方（素のセッション）でも同じ案内になる
- **relay の承認の方式を選べるようにした**（#312）。`approval.mode` が `number`（既定。今までの番号）か `phrase`（本文を見せた後の lead 自身の「送って」）。mode の無い config と読めない値は `number` にする（緩い側に倒さない）。どちらでも、他のセッションのメッセージ・hook の注入・無操作の自動続行は承認にしない

## 未解決事項 (open)

- **issue-workflow の local backend の Issue を tracker にするか**（段階 ②）: 紐付けの導線は入れた（下の「実装で決めたこと（2026-10-25）」）。残りは、issue-workflow の local backend の Issue（`TEAM-123` の形）を hub の tracker として扱う種類が要るか（段階 ① では `--tracker linear` で照合はできるが、status の Issue 一覧は Linear MCP でしか取らない）。確定タイミング: 段階 ② の詳細設計
- **3 回目の self-review（2026-10-21・security / bug-detection）で残した指摘**（G-V ループの上限に達し、BLOCKER だけ直す方針にしたため未修正）。確定タイミング: 段階 ① を 1 PJ で使う前
  - MAJOR 3 件（同名の宛先の `to`・同じ PJ の別の登録のトークン照合・report の `--name`）は同じ日に直した（CHANGELOG の次の版）
  - MINOR: base のブランチ名を `split("/")[-1]` で取る / `--registered-branches` が repo ごとでない / fact の `path` が base に実在するかを確かめない / 共有 worktree の判定に done・不在の登録も数える / 別の PJ の hub.json が壊れていると全セッションの hook で stderr が出る
  - 付録（閾値未満）: 注入する表の前に「外部の文面」の断りが無い / 作業側が送り手の名前だけで hub を認める / relay の承認番号を包みの無い send_message で返されうる ほか 10 件

- **受信の journal への記録と `from-session` の結び付け**（段階 ②）: UserPromptSubmit hook は入れた（下の「実装で決めたこと（2026-10-25）」）が、受信を journal に 1 行残すことと、包みの `from-session` を `sessions/` の `host_session_id` と結び付けることはしていない。後者は Desktop の SendMessage が `local_…` を宛先に取れるかも含めて未確認（GitHub issue #316 の残り）。確定タイミング: 段階 ② の詳細設計
- **開き直して名前も変えたセッション**: ref は開き直しで変わりうる（未確認）。開き直したうえで改名し、題に Issue ID も無いセッションは、作業側が report を置き直すまでどの照合でも引けない。プロセスが残っていないセッションは ListAgents に出ない（2026-10-25 の観察）。確定タイミング: 段階 ① の運用で同じことが起きたとき

## 実装ブリッジ (Implementation Bridge)

1. **実装着手の単位**（段階 ①）。CLI テストで閉じる部分と、実機でしか確かめられない部分を分けて、次の順に進める:
   1. scripts（journal の追記・inbox の取り込み・宛先の照合・state.md の生成）と注入 hook、テスト。root は `PROJECT_HUB_DIR` で使い捨ての dir に向ける
   2. `hub` の `init` / `status` / `takeover` / `close` / `fact` と `report`、プラグインの外枠（plugin.json・commands・README・CHANGELOG・marketplace・INDEX・CLAUDE.md・evals）
   3. `hub` の `brief` / `relay`、ListAgents の抜き出しと自己検査、実機の確認
   - 起動: `/feature-dev project-hub の段階 ①（上の 1〜3） design=.claude/designs/20261021-project-hub-plugin.md`。1 回で重ければ 1〜3 を別の Issue に分ける
   - 段階 ②（`merged`・`decide` の波及と living-spec への受け渡し・hub 側で通知を受ける UserPromptSubmit hook）と段階 ③（意見の台帳・送信前の検査・claim-verifier）は、段階 ① を 1 PJ で使った後にこの doc を改訂して詰める（確定タイミング: 段階 ① の運用 1 PJ 目の後）
2. **検証方法**:
   - hook: `hook_harness.py` で「hub 以外のセッションでは注入しない」「hub.json が無い・壊れているときは黙る」「壊れた JSON の stdin で黙る」を厚く書く。root は必ず `PROJECT_HUB_DIR` で使い捨ての dir に向ける
   - scripts: 宛先の照合（登録名の一致が 1 件 / absent の登録は使わない / Issue ID のトークン一致が 1 件 / 0 件・2 件以上・既定名だけの一致で送らない / `ABC-1` が `ABC-12` に当たらない / `#30` が `#308` に当たらない）と、inbox の取り込み（書きかけ・壊れた JSON・取り込み直し）を CLI テストで固定する
   - 置き場所: `git -C ~/.claude check-ignore` で `<root>` 配下が ignore されることを確かめる
   - 実機: 作業セッション 2 本と hub 1 本で、改名・開き直しの後に relay が届くか（決まらないときは送らないか）、コンパクションの後と hub の開き直し + takeover の後に state.md が注入されるかを確かめる。あわせて、コンパクションの後に SessionStart（source=compact）と PostCompact の両方で二重に注入されないか、ターミナルの対話 TUI で `CLAUDE_CODE_SESSION_ID`・hook の stdin・command 本文の `${CLAUDE_SESSION_ID}` が一致するかを確かめる
3. **実装完了時の doc 更新手順**:
   - frontmatter の `phase: target` → `current`、`last-validated` を更新
   - 実装と食い違った箇所（ファイルの形・部品の分け方）を追記する。宛先の引き方や inbox の方式ごと変わったら supersede

## 関連

- 関連 Issue: GitHub issue #308
- 関連 spec: なし
- 関連 ADR: ADR-20261021154740（作業側 → hub の連絡の形。ADR-20261021140738 を範囲を絞って supersede）/ ADR-20261021140738（superseded）/ ADR-20260722164106（issue-workflow の backend 分岐。案 B を採らない理由のデータ置き場の規約）
- 関連 design doc: `.claude/designs/20260715-living-spec-workflow.md`（living spec。進捗を書かない方針）
- 規約: `docs/event-bus.md`（journal を Event Bus と分ける理由）/ `docs/shared-state.md` / `docs/skill-writing.md`（skill を分ける条件）
- design review（2026-10-21・4 視点 + 反証）: BLOCKER 1 / MAJOR 13 / MINOR 9 をすべて反映した
