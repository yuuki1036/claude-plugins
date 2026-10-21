---
id: 20261021140738
status: superseded
phase: superseded
last-validated: 2026-10-21
supersedes: []
superseded-by: 20261021154740
append_only: true
tags: [architecture, multi-session, send-message, project-hub]
---

# ADR-20261021140738: セッション間の連絡は本文をファイルで置き、SendMessage は通知にだけ使い、宛先は送る直前に ListAgents で名前を引き直す

## ステータス

accepted（2026-10-21）

## コンテキスト / 背景

- GitHub issue #308（project-hub の新設）: 1 セッションを hub にして作業セッション 3〜5 本を束ねた PJ で、作業セッションの改名・開き直しのあと名前宛ての SendMessage が `No agent named ... is reachable` で届かなかった（2 回）。状態はコンテキストにしか無く、報告も会話に流れるだけだった
- SendMessage のツール説明（CC 2.1.302）は、宛先を「the name IS the address; there is no separate address syntax」と定めている。` [ref]` は同名が 2 つあるときだけ付けるもので、「A ref you did not just read from a listing or an error will not resolve」とある
- 実測（2026-10-21）: `--session-id <uuid> -n hubtest-worker` で起動したセッションは ListAgents に `hubtest-worker [227051]` と出て、ref はセッション ID の先頭と一致しなかった。セッション ID 宛ての送信は `No agent named '<uuid>' is reachable` で失敗した（受信側が先に終了していた可能性は残る）
- 他セッションから届いたメッセージで受信側の UserPromptSubmit hook が発火するかは未確認。ツール説明では、受信側が busy ならメッセージは「enqueue and drain at the receiver's next tool round」でターンの途中に入る

## 決定

1. 複数のセッションの間で内容を受け渡すときは、本文を共有の場所（project-hub なら `~/.claude/hub/<project>/inbox/`）にファイルで置く。SendMessage は「置いた」の通知にだけ使い、受け手はファイルを読んで取り込む
2. 宛先は名前で引く。セッション ID・ref を保存して宛先に使わない。送る直前に毎回 ListAgents を引き、記録してある名前と一致する行が無ければ別の手がかり（名前に含まれる Issue ID）で 1 件に絞る。絞れなければ送らずに人へ出す
3. 送った結果（成功・失敗）は記録に残す

## 影響 (Consequences)

- **良い影響**: 受け手の hook が発火しなくても、コンパクションで会話が要約されても、報告が落ちない。改名・開き直しで宛先が外れたときは、黙って失敗せず人に見える
- **悪い影響**: 送るたびに ListAgents の 1 往復が増える。受け手が通知を見てファイルを取り込むまでのあいだ、報告は反映されない。共有の場所（repo の外）を読み書きするので、そのプラグインの hook とテストが扱う範囲が広がる
- **トレードオフ**: 即時性（SendMessage の本文をそのまま使う）より、取りこぼさないことと宛先の外れに気づけることを取った

## 適用方法 (Enforcement)

- 宛先の解決（記録名と一致 / Issue ID で 1 件 / 0 件・2 件以上なら送らない）は、プラグインの scripts に寄せて、ListAgents の出力を stub にした CLI テストで固定する（`.claude-plugin/scripts/tests/`）
- 「SendMessage の本文に報告そのものを載せない」は、送る文面の判断（どこまでが通知か）を含むので hook では決定的に判定できない。report を書く skill が、ファイルを置く手順を先に持ち、通知文を固定の短い形にすることで守る
- セッション ID や ref を宛先に保存していないかは、登録ファイルのスキーマに宛先の欄を持たせない（名前だけを持つ）ことで構造的に防ぐ

## 検討した代替案

- **SendMessage の本文で報告を送り、受け手の UserPromptSubmit hook で記録する**: hook が他セッションからのメッセージで発火するかが未確認で、発火しなければ記録が落ちる。busy の受け手ではターンの途中に入るので、idle と busy で挙動が違う可能性もある
- **セッション ID か ref を登録して宛先に使う**: ツール説明が宛先を名前に限っており、ref は一覧から読んだ直後しか通じない。実測でもセッション ID 宛ては届かなかった
- **名前を一度記録したら引き直さない**: #308 で起きた改名・開き直しの不達がそのまま残る

## 関連

- 関連 ADR: なし
- 関連 Issue: GitHub issue #308
- 関連 design doc: `.claude/designs/20261021-project-hub-plugin.md`
- 関連 knowledge: なし
