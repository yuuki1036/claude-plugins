---
id: 20261021154740
status: accepted
phase: current
last-validated: 2026-10-21
supersedes: ["20261021140738"]
superseded-by: null
append_only: true
tags: [architecture, multi-session, send-message, project-hub]
---

# ADR-20261021154740: project-hub の作業側 → hub の report は本文をファイルで置き、SendMessage は通知にだけ使う。宛先は送る直前に引き直し、1 件に決まらなければ送らない

## ステータス

accepted（2026-10-21）。ADR-20261021140738（向きを限らず、ほかのプラグインのセッション間の連絡まで同じ形で拘束していた）を、範囲を絞って supersede する。

## コンテキスト / 背景

- GitHub issue #308（project-hub の新設）: 1 セッションを hub にして作業セッション 3〜5 本を束ねた PJ で、作業セッションの改名・開き直しのあと名前宛ての SendMessage が `No agent named ... is reachable` で届かなかった（2 回）。状態はコンテキストにしか無く、報告も会話に流れるだけだった
- SendMessage のツール説明（CC 2.1.302）は、宛先を「the name IS the address; there is no separate address syntax」と定めている。` [ref]` は同名が 2 つあるときだけ付けるもので、「A ref you did not just read from a listing or an error will not resolve」とある。実測（2026-10-21）でも、生きている相手へのセッション ID 宛ては届かず、名前宛ては届いた
- 他セッションから届いたメッセージで、受信側の UserPromptSubmit は発火する（2026-10-21 に実測。入力待ち・API 呼び出しの合間・ツールの実行中のいずれでも発火。ツールの実行中はツールが終わるまで保留される）。ADR-20261021140738 の時点ではここが未確認だった
- design review（2026-10-21）で、ADR-20261021140738 の決定 1 が向きを限っていないのに、project-hub の採用案は hub → 作業側（brief / relay）で本文を SendMessage で送っており、自分の決定に反していると指摘された。ほかのプラグインまで拘束する一文には、2 例目の裏付けが無かった
- ListAgents の出力は人間向けの自然文で、書式の契約は見つかっていない

## 決定

1. project-hub の作業側 → hub の report は、本文を `~/.claude/project-hub/<project>/inbox/` にファイルで置く（一時名で書いてから rename する）。SendMessage は「置いた」の通知にだけ使い、hub は status でファイルを取り込む
2. hub → 作業側（brief / relay）は本文を SendMessage で送り、送った全文と解決した宛先・送信の結果を hub 側の journal に残す
3. 宛先は名前で引く。セッション ID・ref・`from`（ソケット）を保存して宛先に使わない。送る直前に毎回 ListAgents を引き、1 件に決まったときだけ送る。0 件・2 件以上・ListAgents の解析が自己検査に合わないときは送らずに人へ出す
4. この形はほかのプラグインを拘束しない。ほかのプラグインがセッション間の連絡を持つときは、2 例目としてこの ADR を見直す

## 影響 (Consequences)

- **良い影響**: 作業側の報告は、受け手の hook の発火・コンパクション・permission mode の承認待ちに左右されず落ちない。宛先が外れたときや曖昧なときは、黙って失敗したり別のセッションへ誤って送ったりせず、人に見える
- **悪い影響**: 送るたびに ListAgents の 1 往復が増える。hub が status を回すまで、報告は状態の表に反映されない。hub → 作業側は本文が作業側の会話を通るので、作業側のコンパクションで要約される（hub 側の journal には全文が残る）
- **トレードオフ**: 作業側 → hub は取りこぼさないことを、hub → 作業側は手順の少なさ（作業側に outbox を読む手順を持たせない）を取った。作業側にとって brief / relay は今読む指示で、ファイルにしても通知が保留されれば読まれない点は同じなので、ファイルにする利点が小さい

## 適用方法 (Enforcement)

- 宛先の照合（登録名の一致が 1 件 / Issue ID のトークン一致が 1 件 / それ以外は送らない / 既定名だけの一致は使わない）は project-hub の scripts に寄せ、ListAgents から抜き出した JSON を入力にした CLI テストで固定する（`.claude-plugin/scripts/tests/`）
- ListAgents からの抜き出しは Claude の手順（SKILL.md）で、見出しの件数と抜き出せた行数の一致などの自己検査を通らなければ送らない。書式の契約が無いので、ここは機械で固定できない
- 「report の本文を SendMessage に載せない」は、送る文面の判断を含むので hook では決定的に判定できない。report の skill がファイルを置く手順を先に持ち、通知文を固定の短い形にすることで守る
- 宛先を保存しないことは、登録ファイルのスキーマに名前だけを持たせる（宛先用の欄を持たせない）ことで構造的に防ぐ

## 検討した代替案

- **ADR-20261021140738 のまま（向きを限らず、ほかのプラグインも拘束する）**: hub → 作業側にも outbox を置くことになり、作業側に outbox を読む手順が要る。作業側では、ファイルにしても通知が保留されれば読まれない点は変わらない。ほかのプラグインを拘束する裏付けも無い
- **report も SendMessage の本文だけで受け、hub の UserPromptSubmit hook で記録する**: hook は発火するが、受信側が TUI / Desktop のときと承認待ちのときは未測定で、そこで記録が落ちる。本文が hub の会話を通るのでコンパクションで要約される
- **セッション ID か ref を登録して宛先に使う**: ツール説明が宛先を名前に限っており、実測でもセッション ID 宛ては届かなかった
- **名前を一度記録したら引き直さない / 部分一致で引く**: 改名・開き直しの不達が残る。部分一致は既定名（`<dir>-<数字>`）や `ABC-12` に当たり、別のセッションへ誤って送る

## 再評価のトリガー

- SendMessage が安定した宛先（セッション ID など）を受け付けるようになる、または ListAgents の出力が構造化されたとき（cc-catch-up で見つける）
- ほかのプラグインがセッション間の連絡を持つとき（決定 4）

## 関連

- 関連 ADR: ADR-20261021140738（この ADR が supersede した）
- 関連 Issue: GitHub issue #308
- 関連 design doc: `.claude/designs/20261021-project-hub-plugin.md`
- 関連 knowledge: なし
