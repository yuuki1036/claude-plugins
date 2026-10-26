---
id: 20261027002221
status: accepted
phase: current
last-validated: 2026-10-27
supersedes: ["20261021154740"]
superseded-by: null
append_only: true
tags: [architecture, multi-session, send-message, project-hub]
---

# ADR-20261027002221: project-hub の hub → sub は、Desktop の hub なら sub の会話の ID（local_…）へ送る

## ステータス

accepted（2026-10-27）。ADR-20261021154740 を supersede する。変えるのは決定 3（宛先は名前で引き、セッション ID・ref を宛先に使わない）の hub → sub の部分だけで、決定 1・2・4（report はファイルで置く・hub → sub は本文を SendMessage で送り journal に残す・ほかのプラグインを拘束しない）はそのまま引き継ぐ。

## コンテキスト / 背景

- GitHub issue #316: 作業セッション（sub）を改名したうえで開き直すと、hub が宛先を引けなくなる。2026-10-26 に Desktop で実測した結果は次のとおり
  - 改名だけなら ref は変わらず、登録した時の ref で今の名前を引けた
  - 開き直すと（archive → unarchive）、CLI の session_id は変わらないが ListAgents の ref が変わる。題に Issue ID も無いと、report を置き直すまでどの照合でも引けず `unresolved` になった
- 同じ日に、Desktop のセッションから sub の会話の ID（`local_…`）宛てに SendMessage を送ると、改名・開き直しの後も同じ ID で届いた。Desktop の `send_message` ツールの説明も「Prefer `SendMessage` with `to` set to the target's `local_...` session id」に変わっている。ADR-20261021154740 の「セッション ID 宛ては届かない」は CLI の session_id（uuid）で測った結果で、`local_…` には当たらない。これは旧 ADR の再評価のトリガー（SendMessage が安定した宛先を受け付けるようになる）に当たる
- 2026-10-27 の実測:
  - 環境変数を空にした素の CLI（`claude -p`）からの `local_…` 宛ては `No agent named ... is reachable` で届かない
  - archive 中の会話への `local_…` 宛ては `session ... is archived; unarchive it first` で届かない（黙って捨てられない）
  - unarchive した後、プロセスの無い会話への `local_…` 宛ては届き、Desktop が会話を再開した
- `CLAUDE_CODE_HOST_SESSION_ID`（会話の ID）は Desktop の Bash から起動した子の CLI にも継承される。env の値をそのまま登録に書くと、子の CLI の sub が親の会話の ID を名乗り、別の会話へ届きうる

## 決定

1. hub → sub（brief / relay）の宛先は、次の 2 つがそろうときだけ sub の会話の ID（`local_…`）にする
   - hub が Desktop のセッションだと、Desktop の記録（`claude-code-sessions/<account>/<org>/<local_…>.json` の `cliSessionId`）で確かめられた
   - sub の登録が、report の時点で同じく Desktop の記録で確かめた会話の ID を持つ（`host_verified: true`）
2. それ以外（CLI の hub・CLI の sub・確かめられない登録・0.6.4 までの登録）は、ADR-20261021154740 の決定 3 のとおり名前で引き、1 件に決まらなければ送らない
3. 会話の ID 宛てでも ListAgents は引く。行は表示と往復の上限の数え方にだけ使い、宛先は決めない。登録した時の ref の行が今の一覧に無いときは、送ると Desktop がその会話を再開するので warning を付ける。承認なしに送る PJ（`approval.mode: auto`）では送らずに lead に出し、lead が送ってよいと言えば送る
4. sub → hub の通知は今までどおり名前で引く（sub が CLI のことがあり、hub は開き直しても名前が変わらない）

## 影響 (Consequences)

- **良い影響**: 改名・開き直しの後も、report を置き直させずに hub から sub へ届く。同じ名前を付けた別のセッションへ誤って送ることも、会話の ID 宛てでは起きない（ID は入れ替わらない）
- **悪い影響**: 判定が Desktop の内部の記録ファイル（形の契約が無い）に依存する。形が変わると会話の ID を確かめられなくなり、名前の規則へ戻る（別の会話へは送らない側に倒れる）。一覧に見えない sub へ送ると、Desktop がその会話を再開してトークンを使う
- **トレードオフ**: 宛先の安定と、Desktop の内部ファイルへの依存を天秤にかけた。依存は「確かめられなければ使わない」に閉じ込め、壊れたときの挙動を旧 ADR と同じにした

## 適用方法 (Enforcement)

- 宛先の決め方は `project-hub/scripts/hub.py` の `resolve`（`registered_host` / `resolved_host`）に置き、CLI テストで固定する（`.claude-plugin/scripts/tests/test_project_hub_scripts.py` の `HostSessionTest`）。固定する条件: Desktop の hub と確かめた登録なら `rule: host_session` で `to` が `local_…` / CLI の hub・子の CLI の hub・確かめていない登録では名前の規則 / 一覧に見えない sub は warning、auto の PJ では `needs_lead` / 往復の上限は会話の ID 宛てでも数える / record は `to.host` に `local_…` の形だけを受ける
- 登録に会話の ID を書くのは report の 1 か所だけで、`verified_host` を通した値しか書かない（`host_verified` を同時に書く）。env の値をそのまま書かないことも同じテストで見る
- SendMessage の `to` に resolve の出力以外の値を使わないことは、Claude の手順（hub の SKILL.md の relay）で守る。送る文面と宛先の判断を含むので hook では決定的に判定できない

## 検討した代替案

- **ADR-20261021154740 のまま（名前で引く）**: 改名したうえで開き直した sub は、report を置き直すまで引けない。#316 の実測で再現した
- **会話の ID を env から無条件に登録して使う**: 子の CLI が親の会話の ID を継承するので、別の会話へ届きうる
- **CLI の hub でも会話の ID を使う**: 素の CLI からは届かない（2026-10-27 の実測）。届かない宛先を返すより、名前で引いて決まらなければ lead に出す方がよい
- **ListAgents の行を引かずに会話の ID だけで送る**: 一覧に見えない（閉じている）sub を黙って再開させてしまう。auto の PJ では lead が知らないまま会話が動く
- **sub → hub も会話の ID にする**: sub が CLI のときに届かない。hub の名前は開き直しでは変わらないので、今の名前の規則で足りる

## 関連

- 関連 ADR: ADR-20261021154740（この ADR が supersede した）/ ADR-20261025152955（承認なしに送る範囲。warning の付く宛先は lead に出す）
- 関連 Issue: GitHub issue #316 / GitHub issue #325（会話の ID と Desktop の記録で同じ会話を確かめる仕組み）
- 関連 design doc: `.claude/designs/20261021-project-hub-plugin.md`
- 関連 knowledge: なし
