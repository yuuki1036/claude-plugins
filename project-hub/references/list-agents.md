# ListAgents の抜き出し（hub / report 共通）

宛先は名前で引き、送る直前に毎回 ListAgents を引き直す（セッション ID・ref・ソケットは宛先に使えない / ADR-20261021154740）。ListAgents の出力は人間向けの文で書式の契約が無いので、Claude が抜き出した結果を `hub.py` の自己検査に通してから使う。

## 出力の形（2026-10-21 の実測）

```
This session is PJ の hub [b6d4cf] — the name other sessions use to message it (...)

Subagents (1):
  a57678782cf01442c  ·  feature-dev:code-architect  ·  running  ·  started 1m ago

Peer sessions (3):
  my-repo-96 [f3183e]  ·  interactive  ·  waiting  ·  started 1h ago
  設計の相談 [1a6070]  ·  interactive  ·  idle  ·  Claude Desktop session  ·  started 2h ago
  ABC-12: 監査ログ [262901]  ·  interactive  ·  idle  ·  started 1m ago
```

- 名前は Desktop では会話の題、CLI では `-n` の表示名、どちらも無ければ `<dir>-<数字>` の既定名。hook の `sessionTitle` で付けた題もそのまま名前になる（2026-10-21 に実測）
- 利用者が改名すれば名前（＝宛先）も変わる。既定名は宛先の照合に使わない（開き直しで別のセッションが同じ番号を名乗りうる）
- ref は改名では変わらない（2026-10-25 に Desktop のセッションで実測）。report が登録に残した ref は、改名した後の行を登録に結び付ける照合にだけ使い、宛先には使わない（送るのは今の名前）。**開き直すと ref は変わる**（2026-10-26 に Desktop の archive → unarchive で実測。session_id は変わらない）。開き直したうえで改名し、題に Issue ID も無いセッションは、report を置き直すまで引けない
- プロセスが残っていないセッションは一覧に出ない（2026-10-26 に実測: archive 中は出ず、unarchive しただけでも出ない。次のメッセージで再開して初めて出る）。出ていない間は、どの照合でも引けない

## 抜き出すもの

1. **自分の名前と ref**: 1 行目 `This session is <name> [<ref>] — ...` の `<name>` と `<ref>`。名前は ` [<ref>]` の直前まで（空白・`#`・`:` を含みうる）
2. **件数 N**: 見出し `Peer sessions (N):` の N
   - 見出しが無いときは、出力が 1 行目（と空行・`Subagents` の節）だけなら N = 0
   - それ以外の行があるのに見出しが見つからないなら、書式が変わったとみなして**抜き出しをやめる**（送らない・書かない）。生の出力を利用者に見せる
3. **行**: `Peer sessions` の見出しの下の行だけを `{"name", "ref", "state"}` にする。`Subagents` など他の見出しの下の行は入れない
   - 区切りは `  ·  `（空白 2 つ・中黒・空白 2 つ）
   - name: 行頭の空白を除き、最初の区切りより前から末尾の ` [<ref>]` を除いた部分
   - ref: その `[` と `]` の中（英数字）
   - state: `says it was ` で始まる欄を除いてから、2 番目の区切りの後（`interactive` などの kind の次）。Desktop の行は `Claude Desktop session` が後ろに入って区切りが 1 つ多いので、後ろから数えない
   - 改名の直後だけ、名前の次に `says it was <前の名前> until <N>s ago` の欄が入る（2026-10-26 に実測。しばらくすると消える）。この欄を数えると state に `interactive` を取ってしまう。前の名前は照合に使わない（照合は登録した時の ref で行う）

## hub.py に渡す

抜き出した値は argv に載せず、JSON にして stdin で渡す（名前は他のセッションが付けた文字列で、`$`・`#`・バッククォートを含みうる）。heredoc の区切りは毎回その場で決める `PROJECT_HUB_<8 桁の乱数>` にしてクォートし、名前にその文字列が無いことを確かめる（固定の区切りは、名前がその 1 行を含むと後ろの行がシェルで実行される）。

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hub.py" resolve --project '<PJ>' --hub --peer-count 3 <<'PROJECT_HUB_<8 桁の乱数>'
[{"name": "my-repo-96", "ref": "f3183e", "state": "waiting"},
 {"name": "設計の相談", "ref": "1a6070", "state": "idle"},
 {"name": "ABC-12: 監査ログ", "ref": "262901", "state": "idle"}]
PROJECT_HUB_<8 桁の乱数>
```

## 結果で分岐する

stdout の JSON の `status` で分岐する。JSON が出ない回もある。

| 結果 | すること |
|---|---|
| `status: ok` | SendMessage の `to` には出力の `to` をそのまま使う（ふだんは名前だけ。同じ名前の行が他にもあるときだけ ` [ref]` が付く）。`warning`（登録名ではなく登録した時の ref で引いた・名前の中の Issue ID で引いた・前回の status で不在だった登録名で引いた）があれば、承認の画面に添える |
| `status: needs_lead`（hub → sub・auto の PJ） | **送らない**。warning の付く照合（名前の中の Issue ID・不在から戻った登録名・ref で引いた改名）で決まった宛先。`name`・`ref`・`warning` を lead に見せ、lead が選んだらその行の ref で引き直す（`--ref`） |
| `status: auto_limit`（hub → sub・auto の PJ） | **送らない**。lead の言葉の伝達を挟まずに、同じ sub へ hub の判断の連絡が続いた。hub の SKILL.md の「自動の連絡」のとおり lead に出す |
| `status: unresolved` | **送らない**。`reason` と `candidates`（名前と ref）を lead / 利用者に出す。候補が 1 つも無いときは抜き出した全行を見せる。lead が選んだら、その行の ref で引き直す（hub の relay の `--ref`） |
| `status: parse_failed`（exit 2） | **送らない・記録しない**。「ListAgents の出力を解析できなかった（宛先が見つからないのとは別）」と書き、ListAgents の生の出力を添えて出す。exit 2 でも入力の誤りではないので、手順の続きは呼び出し元の手順に従う（hub の status は 4 へ進む） |
| stdout に JSON が無い（exit 2 / 3 / 4） | **送らない**。stderr の `project-hub: ...` をそのまま出す（引数・状態ファイルの問題で、ListAgents の解析失敗ではない） |
