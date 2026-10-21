---
id: 20261021-project-hub-plugin
title: project-hub — 複数セッションを束ねて PJ を進める hub のプラグイン
status: draft
phase: target
last-validated: 2026-10-21
supersedes: []
superseded-by: null
issue: "GitHub issue #308"
spec: null
adrs: ["20261021140738"]
tags: [project-hub, multi-session, hooks, send-message, new-plugin]
---

# project-hub — 複数セッションを束ねて PJ を進める hub のプラグイン

## TL;DR

1 つのセッションを hub にし、PJ の状態（作業セッション・PR・Issue・判断）を `~/.claude/hub/<project>/` の追記ログから作る表で持つ。作業側は決まった形の report をファイルで置き、SendMessage は届いたことの通知にだけ使う。宛先は名前で引き、送る直前に ListAgents で引き直す。

## 背景 / 課題

業務リポジトリ A の PJ（Issue 十数件・作業セッション 3〜5 本が同時に動く）で、1 セッションを hub にして living spec と会話の文脈だけで回した。起きたことは次のとおり（#308 本文）。

- 進捗を living spec の決定ログに足し続けて膨らみ、living-spec-maintain が Critical を出した（数十行をタイムラインへ移した）
- 作業セッションが名前を変える・開き直すと、名前宛ての SendMessage が `No agent named ... is reachable` で届かない（2 回）
- hub の思い込み（デプロイの経路・監査ログの項目）が裏取りなしに作業側へ伝わり、後で訂正した
- 外部（デザイナー）へ渡した一覧への訂正が判断のたびに溜まり、まとめて 4 点になった
- 状態がコンテキストにしか無く、コンパクションのたびに要約頼みになる

既存のプラグインはどれもこの層を持たない。issue-workflow の dashboard / start は 1 リポジトリ・1 セッションの範囲で、データは repo の `.claude/` 配下にあり worktree ごとに分かれる。living-spec-workflow は設計の収束を扱い、進捗は書かない。

## ゴール / 非ゴール

- **ゴール**:
  - hub の状態をコンテキストの外に置き、コンパクションと開き直しを越えて続けられる
  - 作業セッションの改名・開き直しで連絡が途切れない（途切れたら気づける）
  - 作業側へ渡す事実を、出典つきで確かめたものに限る
  - 作業側の報告を決まった形で受け、取りこぼさない
- **非ゴール**:
  - 判断の正本を持つこと — 正本は Issue トラッカーの本文とリポジトリの仕様 docs に置く（hub が持つと二重管理になる）
  - Issue トラッカーへの書き込み — 起票・更新は issue-workflow / 人間の領分
  - 作業セッションの起動・停止の自動化 — 起動手段がアプリ（Desktop の start_session）と CLI で違い、どちらにも寄せられない。brief は送る文面までを作る
  - living spec との統合 — 進捗を living spec に書かない。連携は段階 ② の `decide` の受け渡しだけ
  - 段階 ② ③ の詳細設計（`merged` / `decide` の波及 / 意見の台帳 / 送信前の検査）— 段階 ① の運用を見てから別 doc か改訂で詰める

## 確定した前提

- **新プラグインにする**（2026-10-21 にユーザーが確定。component-addition-advisor の判定）。blocker: 状態を repo の外に置き、セッションをまたいで持つ必要がある。issue-workflow のデータ置き場（repo の `.claude/` 配下・worktree ごとに分かれる）とは粒度が合わない。fallback: issue-workflow:dashboard と living spec を手で回す今のやり方
- **Issue トラッカーは hub が直接読む**（2026-10-21 にユーザーが確定）。hub が要るのは状態・担当・紐づく PR の数列だけなので、`gh issue view --json` / Linear MCP を自前の短い呼び出しで読む。issue-workflow には依存せず、スクリプトの複製も作らない（CLAUDE.md「各プラグインは独立して動作すること」「複製は分割単位の誤りのシグナル」）
- **report はファイルで置き、SendMessage は通知にだけ使う**（2026-10-21 にユーザーが確定）。確定時は要検証 (b) が未決だったため。決着した後も変えない理由は「検討した代替案」の最後の項
- **SendMessage の宛先は名前で、セッション ID は使えない**（要検証 (a)。2026-10-21 に確認）
  - ツール説明（SendMessage・CC 2.1.302）: 「the name IS the address; there is no separate address syntax」。` [ref]` は同名が 2 つあるときだけ付け、「A ref you did not just read from a listing or an error will not resolve」。raw の agentId（`a...-...`）は in-process の subagent 用
  - 実測: `--session-id 11111111-2222-4333-8444-555555555555 -n hubtest-worker` で起動したセッションは、ListAgents に `hubtest-worker [227051]` と出た。ref はセッション ID の先頭と一致しない。セッション ID 宛ての送信は `No agent named '11111111-…' is reachable` で失敗した（#308 で出たのと同じ文言）。この回は受信側が認証エラーで先に終了していた可能性があったので、受信側が ListAgents に `busy` と出ている間に測り直した（`22222222-…`）。結果は同じ文言での失敗だった。名前宛て（`hubtest-busy`）は同じ相手に届いた
  - `-n` で付けた表示名がそのまま ListAgents の名前になった（上の実測）。Desktop のセッションも会話の題に当たる名前で出ていた（タイトルと同一かは未確認）。どちらにせよ利用者が改名すると宛先が変わる
- **他セッションから届いたメッセージで、受信側の UserPromptSubmit は発火する**（要検証 (b)。2026-10-21 に実測）。受信側はヘッドレスの `claude`（haiku）で、UserPromptSubmit の stdin をファイルに追記するだけの hook を `--settings` で入れた。送信側はこのリポジトリの Desktop のセッション
  | 受信側の状態 | 届き方 | UserPromptSubmit |
  |---|---|---|
  | 入力待ち（`-p --input-format stream-json` で stdin を開いたまま、1 ターン目の後） | 新しいターンとして始まる | 発火（送信の直後） |
  | API 呼び出しの合間（`-p` の 1 ターン目の途中） | ターンの途中に入る | 発火（送信の直後） |
  | ツールの実行中（`python3 -c 'import time; time.sleep(60)'`） | transcript に `queue-operation: enqueue` と `queued_command` が残り、ツールが終わるまで保留された | 発火（ツールの終了時。送信から約 53 秒後） |
  - hook の `prompt` には、包みごとの全文が入る: `<cross-session-message from="uds:/tmp/cc-socks/<pid>.sock" from-session="local_<uuid>" from-name="<送信側の名前>" from-mode="prompting">` + 本文 + `</cross-session-message>`。送り手の名前とセッションを hook が決定的に読める
  - `from` は送信側のプロセスごとのソケットで、ツール説明は返信の宛先にこれを使うよう指示している。プロセスが変われば変わるので、保存する宛先には使えない
  - 測っていないもの: 対話の TUI と Desktop のセッションが受信側のとき。受信側の permission mode が送信側と違うとき（ツール説明では、メッセージは受信側の利用者の承認待ちになり、期限切れもありうる）
- **置き場所は `~/.claude/hub/<project>/`**（#308 本文）。repo の `.claude/` は worktree ごとに分かれ、hub と作業側で共有できない
- **hook が受け取る stdin に `session_id` がある**（上の実測で UserPromptSubmit の stdin に `session_id` / `transcript_path` / `cwd` が入っていた）。hub のセッションかどうかは、登録した hub の session_id との一致で決定的に判定できる
- **hook のイベントに SessionStart / PostCompact / UserPromptSubmit がある**（`.claude-plugin/schema/hooks.schema.json` の enum）
- 帯（mod）は issue-workflow の `hooks/issue-band.tsx` に前例がある（読むだけで書かない mod）。段階 ① では作らない

## 採用案

### 全体像

```
~/.claude/hub/<project>/
  config.json            PJ の設定（init が作る）
  journal.jsonl          起きたことの追記ログ（hub だけが書く）
  facts.jsonl            確かめた事実（出典つき。brief はここからだけ引く）
  state.md               journal から作る状態の表（status が書き直す。コンパクション後に注入する）
  hub-session            hub の session_id（1 行）
  sessions/<session_id>.json   作業側の登録（作業側の SessionStart hook が書く）
  inbox/<ts>-<session_id>.json  作業側の report（作業側の report が書く）
```

```
作業側セッション                                  hub セッション
 SessionStart hook ── sessions/<id>.json ──┐
 report skill ────── inbox/<ts>-<id>.json ─┼──> status: inbox を取り込み journal に追記 → state.md を作り直す
     └─ SendMessage「report を置いた」 ─────┘      relay / brief: 送る直前に ListAgents で宛先を引き直す
                                                   SessionStart(compact) / PostCompact hook: state.md を注入
```

### ファイルの形

- `config.json`: `{ "project", "tracker": {"kind": "github|linear", "repo"|"team"/"project", "milestone"?}, "repos": [{"path", "base"}], "approval": {"prefix", "suffix"}, "public_write_rules"? }`。PJ 固有の決まり（PR のラベル・向き先・公開先での置き換え）はここに置き、プラグイン本体に入れない
- `journal.jsonl`: 1 行 1 件 `{"ts", "kind", "subject", "body", "source"}`。`kind` は `relay | brief | report | decide | correct | external | merged` のどれか。`source` は出典（URL・`path:line`・コミット SHA・report のファイル名）。Event Bus（repo の `.claude/events.jsonl`）とは別物なので、名前を変えて取り違えを防ぐ
- `facts.jsonl`: `{"ts", "claim", "source", "checked_by"}`。`source` が無い行は書かない。訂正は新しい行で `supersedes` に前の行の `ts` を入れる（追記のみ）
- `sessions/<session_id>.json`: `{"session_id", "name"?, "issue"?, "branch", "worktree", "updated"}`。`name` は report のときに作業側が ListAgents の自分の行（「This session is X [ref]」）から書き足す
- `inbox/*.json`（report の形）: `{"session_id", "name", "issue", "state": "in_progress|blocked|ready_for_review|done", "pr"?, "needs_lead": [..], "follow_ups": [..], "claims": [{"text", "source"}]}`。`claims` は作業側が主張する事実で、出典（`path:line` 等）を必須にする。hub はこれを裏取りしてから facts に移す

### 宛先の引き方（改名・開き直しへの対処）

送る直前に毎回 ListAgents を引き、次の順で宛先を決める。

1. 登録の `name` と一致する行があればそれ
2. 無ければ、名前に Issue ID を含む行が 1 つだけならそれ（作業側のタイトルは issue-workflow の set-session-title が `ISSUE: タイトル` にする前例がある）
3. どちらでも決まらなければ送らず、lead に「宛先が見つからない（登録名 X / 候補 N 件）」と出す

送った結果（成功・失敗）は journal に `relay` として残す。

### 部品（段階 ①）

| 部品 | 種類 | 中身 |
|---|---|---|
| `init` | skill | config.json と hub-session を作る。今のセッションを hub として登録する |
| `status` | skill | inbox を取り込み（取り込んだファイルは `inbox/done/` へ移す）、gh・トラッカー・ListAgents・`sessions/` を集めて state.md を作り直し、表・止まっている箇所・マージ順を出す |
| `brief <Issue>` | skill | base の SHA、作業中のブランチとの重なり（`git diff --name-only <base>...<branch>` の突き合わせ）、facts のうち関係するもの、溜まった注意点から文面を作る。送るのは lead の承認の後（relay と同じ経路） |
| `relay` | skill | config の前置きと締めを付け、宛先を引き直して送り、journal に残す |
| `report` | skill（作業側） | report を inbox に置き、hub に通知を送る |
| hub の注入 | hook（SessionStart の compact / PostCompact） | stdin の session_id が hub-session と一致したときだけ state.md を注入する。一致しなければ黙る |
| 作業側の登録 | hook（SessionStart） | cwd の git common dir が config の repos のどれかに当たるときだけ `sessions/<session_id>.json` を書く。当たらなければ黙る。hub 自身のセッションでは書かない |
| 裏取り | agent（読み取りのみ） | report の claims を `path:line` で確かめ、`支持 / 反証 / 保留` を返す。段階 ① では status から任意で呼ぶ |

skill 間の共通処理（journal の追記・宛先の解決・state.md の生成）は `scripts/` に寄せ、SKILL.md に bash を書き下ろさない。

### 変更対象ファイル（段階 ①）

- 新規: `project-hub/.claude-plugin/plugin.json` / `commands/` / `skills/{init,status,brief,relay,report}/SKILL.md` / `agents/claim-verifier.md` / `hooks/hooks.json` / `hooks/scripts/{inject-state.sh,register-session.sh}` / `hooks/lib/safe-hook.sh`（正本の複製）/ `scripts/` / `README.md` / `CHANGELOG.md`
- 更新: `.claude-plugin/marketplace.json` / `INDEX.md` / `CLAUDE.md` のプラグイン一覧
- テスト: `.claude-plugin/scripts/tests/test_project_hub_hooks.py`（hook_harness で「黙る条件」を厚く）/ `test_project_hub_scripts.py`

## 検討した代替案

| 観点 | 案 A（採用）新プラグイン + ファイル inbox | 案 B issue-workflow に hub スキルを足す | 案 C living spec を hub に使い続け、タイムラインを別ファイルに分ける |
|------|------------|------|------|
| 変更量 | 中（新プラグイン一式） | 中（13 → 18 スキル前後） | 小 |
| 状態の置き場所 | repo の外。worktree をまたいで共有できる | repo の `.claude/`。worktree ごとに分かれる | living spec と同じ場所 |
| 宛先の改名・開き直し | 送る前に引き直す。決まらなければ lead に出す | 同じ仕組みを入れれば可 | 対処なし |
| コンパクション | state.md を hook で注入 | 同じ仕組みを入れれば可 | 要約頼みのまま |
| 他プラグインとの関係 | 依存も複製もなし | トラッカーの読み取りを共有できるが、データ置き場と粒度が既存と食い違う | living-spec の責務（収束）に進捗が混ざる |

- 案 B を採らない理由: 状態を repo の外に置くと、issue-workflow の `{DATA_DIR}` 規約・backend 判定（Phase 0）の前提から外れた別系統がプラグイン内にでき、13 スキルのうち hub 系だけが別の置き場所を持つ
- 案 C を採らない理由: 問題の 5 件のうち、膨張しか直らない
- report を SendMessage だけで受ける案を採らない理由: UserPromptSubmit は発火する（確定した前提）が、本文が会話を通るのでコンパクションで要約される。ツール実行中の hub には、そのツールが終わるまで届かない。permission mode が違うと受信側の承認待ちになり、期限切れもありうる（ツール説明）。ファイルならどれにも左右されない

## 設計判断ログ

- [local] hub のログの名前は `journal.jsonl`（#308 本文の `events.jsonl` から変更）。Event Bus の `.claude/events.jsonl` と同じ名前だと、規約（`event_bus_tail` で読む）の対象と取り違える
- [local] project-hub のファイルは project-hub だけが読み書きするので、Shared State の frontmatter（docs/shared-state.md）は付けない。他プラグインが読むようになったら付ける
- [local] facts は追記のみ。訂正は新しい行で前の行を指す（hub の思い込みが作業側へ渡った経緯を後から辿れるように）
- [local] inbox は取り込んだら `inbox/done/` へ移す（消さない）。取り込みの重複は report のファイル名で防ぐ
- [local] hook はどちらも stdin の `session_id` と cwd で自己判定する（CLAUDE.md の「hooks.json の if:/matcher に単独依存しない」）
- [local] ADR-20261021140738 のコンテキストにある「UserPromptSubmit が発火するかは未確認」は、2026-10-21 の実測で「発火する」と決着した。決定（本文はファイル・SendMessage は通知だけ）は変えない（理由は「検討した代替案」の最後の項）。ADR は append-only なので本文は書き換えない
- [→ADR候補] 複数セッションの間の連絡は、本文をファイルで置き SendMessage は通知にだけ使う。宛先は名前で引き、送る直前に ListAgents で引き直す（セッション ID・ref を保存して使わない）。ほかのプラグインがセッション間の連絡を持つときも、この形を拘束する

## 未解決事項 (open)

- **hub 側で通知を受ける UserPromptSubmit hook を何に使うか**（要検証 (b) が「発火する」で決着したので生じた問い）: (a) 受信を journal に 1 行残し、未取り込みの report の件数を注入するだけ — Pros: hook が軽い（Event Bus 規約の「hook 内で重い処理をしない」に沿う）。report の取り込みは `status` に一本化される / Cons: 取り込みは hub の Claude が `status` を回すまで遅れる (b) hook が inbox を取り込み state.md まで作り直す — Pros: 通知と同時に状態が最新になる / Cons: hook で gh・トラッカーを呼ぶことになり重い。失敗すると黙る。現時点の方向性: (a)。`prompt` が `<cross-session-message` で始まり、かつ stdin の `session_id` が hub-session と一致するときだけ動かす。確定タイミング: 段階 ② の詳細設計（段階 ① の運用 1 PJ 目の後）
- **作業側の登録 hook をどのセッションで有効にするか**: (a) project-hub を user スコープで有効にし、config の repos に当たるときだけ書く — Pros: 作業側の設定が要らない / Cons: 全セッションで SessionStart が走る（当たらなければ黙る） (b) 作業側の repo の project スコープでだけ有効にする — Pros: 走る範囲が狭い / Cons: worktree ごとに settings.local.json が無く、有効化が漏れる。現時点の方向性: (a)（判定は git common dir の比較だけで軽い）。確定タイミング: 段階 ① の実装時
- **作業側の名前を決まった形にするか**: (a) brief に「セッションのタイトルを `<Issue ID>: …` にする」を含める — Pros: 宛先の引き直し 2 番目が効く / Cons: 利用者が改名すれば崩れる (b) 何もしない — Pros: 手間なし / Cons: 引き直しが登録名頼みになる。現時点の方向性: (a)。確定タイミング: 段階 ① の運用 1 PJ 目の後

## 実装ブリッジ (Implementation Bridge)

1. **実装着手の単位**（段階 ①）:
   - `/feature-dev project-hub の段階 ①（状態ファイル・status・brief・relay・report・compact の注入 hook・作業側の登録 hook） design=.claude/designs/20261021-project-hub-plugin.md`
   - 段階 ②（`merged`・`decide` の波及と living-spec への受け渡し・hub 側で通知を受ける UserPromptSubmit hook）と段階 ③（意見の台帳・送信前の検査）は、段階 ① を 1 PJ で使った後にこの doc を改訂して詰める（確定タイミング: 段階 ① の運用 1 PJ 目の後）
2. **検証方法**:
   - hook: `hook_harness.py` で「hub 以外のセッションでは注入しない」「config の repos に当たらない cwd では登録しない」「壊れた JSON で黙る」を厚く書く
   - scripts: 宛先の解決（登録名一致 / Issue ID 一致が 1 件 / 0 件・2 件で送らない）を ListAgents の出力を stub にした CLI テストで固定する
   - 実機: 作業セッション 2 本と hub 1 本で、改名・開き直しの後に relay が届くか、コンパクションの後に state.md が注入されるかを確かめる
3. **実装完了時の doc 更新手順**:
   - frontmatter の `phase: target` → `current`、`last-validated` を更新
   - 実装と食い違った箇所（ファイルの形・部品の分け方）を追記する。宛先の引き方や inbox の方式ごと変わったら supersede

## 関連

- 関連 Issue: GitHub issue #308
- 関連 spec: なし
- 関連 ADR: ADR-20261021140738（設計判断ログの [→ADR候補] を切り出したもの。セッション間の連絡の形）/ ADR-20260722164106（issue-workflow の backend 分岐。案 B を採らない理由のデータ置き場の規約）
- 関連 design doc: `.claude/designs/20260715-living-spec-workflow.md`（living spec。進捗を書かない方針）
- 規約: `docs/event-bus.md`（journal を Event Bus と分ける理由）/ `docs/shared-state.md`
