# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [0.2.0] - 2026-10-25

### Added

- hub のセッションに UserPromptSubmit hook（`hooks/scripts/notify-pending.sh` → `hub.py pending-hint`）を足した。inbox に未取り込みの report があるときだけ、取り込みのコマンドを注入する。作業側の通知でも lead の発言でも発火するので、通知が届かなかった回（hub の名前が既定名など）も次の発言で拾う。hook は件数を見るだけで、report の文面は読まない。このセッションの id を含む `hub.json` が無ければ python を起動しない（GitHub issue #314）
- brief を経ずに始めた作業セッション（issue-workflow の `start` など）への紐付けの案内を足した。SessionStart / PostCompact の `inject` は、hub でないセッションの cwd の repo が active な PJ に入っていて、そのセッションがまだ登録されていなければ、Issue の作業を始めたら `report` で `hello` を置くよう案内する。issue-workflow には手を入れない（プラグイン間の依存を作らない / GitHub issue #315）
- relay の承認の方式を選べるようにした（`init --approval-mode`・config.json の `approval.mode`）。`number`（既定。今までの 4 桁の番号）か `phrase`（本文を見せた後の lead 自身の「送って」）。mode の無い config と読めない値は `number` にする。`refresh-hub` が `approval_mode` を返す（GitHub issue #312）

### Changed

- hub は「report を置いた」の通知を受けたら、`status` を待たずにその場で `ingest` して中身（needs_lead・follow_ups・claims）を lead に見せる。ListAgents・トラッカー・PR の集め直しは今までどおり `status` で行う（GitHub issue #314）

### Fixed

- 改名した作業セッションを見失っていた（GitHub issue #316）。report が登録に自分の ref を残し、名前で引けないときはその ref の行に結び付ける（ref は改名では変わらないことを 2026-10-25 に実測）。
  `resolve` はその行の今の名前で引き（`rule: registered_ref`・`warning` 付き）、登録名の行が ref の行と別にあれば送らない（改名の後に別のセッションが元の名前を付けた可能性）。
  `presence` は改名したセッションを不在にせず `renamed` で返し、state.md の名前の欄に `登録名 → 今の名前` で出す。送る宛先は今までどおり今の一覧の名前で、ref は照合にだけ使う（ADR-20261021154740）。
  ref の無い登録（0.1.x の report）と、開き直して ref が変わったセッションは、今までどおり登録名と Issue ID で引く

## [0.1.3] - 2026-10-25

### Fixed

- 前回の `status` で不在になった作業セッションが開き直して一覧に戻っても、次の `status` まで登録名で引けなかった（`resolve` が前回の `presence.json` を見て登録名の照合を飛ばしていた / GitHub issue #316）。
  今の ListAgents に登録名が 1 行だけ戻っていて、その名前がほかの登録・ほかの PJ・hub のものでなければ、Issue ID の一致と並ぶ候補にする。
  候補を合わせて 1 行に決まれば `warning` を付けて返し（同じ名前の別のセッションかもしれないので、承認の画面で lead が確かめる）、Issue ID で当たる別の行もあれば送らずに両方を候補に出す

## [0.1.2] - 2026-10-22

### Changed

- `scripts/hub.py` の変異テストで生存した変異のうち、等価な 4 件（登録名の一致が 2 件以上の分岐・`--session-id` を受けない読み取り専用の 3 サブコマンド）に `# mutation-ok:` で理由を付けた。挙動は変わらない。残りの 57 件は回帰テスト（配布物の外）で殺した（GitHub issue #311）

## [0.1.1] - 2026-10-21

### Fixed

- `resolve` の出力に SendMessage の `to` を足した。同じ名前の行が他にもあるときは ` [ref]` を付ける（名前だけでは届け先が決まらない）
- Issue ID での宛先の照合から、同じ PJ の別のセッションの登録名と hub の名前を外した（「#310: #308 の残り」のような名前の別のセッションに当たらない）
- report は自分の名前も stdin の JSON（`name`）で受け、`--name` を外した。作業側の名前はトラッカーの題を写したものになりうるので、argv に載せない

## [0.1.0] - 2026-10-21

### Added

- **新プラグイン**（GitHub issue #308 の段階 ①）。1 つのセッションを hub にして、複数の作業セッションで進める PJ の状態を `~/.claude/project-hub/<PJ>/` のファイルで持つ
- `hub` skill / command: `init` / `status` / `brief` / `relay` / `fact` / `takeover` / `close`
- `report` skill / command: 作業側の report を inbox にファイルで置き、hub には「置いた」とだけ知らせる
- `scripts/hub.py`: journal の追記・inbox の取り込み・宛先の照合・state.md の生成。ListAgents から抜き出した JSON の自己検査（見出しの件数と行数・欄の形）に合わなければ送らない
- SessionStart / PostCompact hook（`inject-state.sh`）: hub のセッションにだけ state.md を注入する
- design doc からの差分（実装時に決めたこと）:
  - 不在（`absent_since`）は作業側の登録ファイルではなく、hub だけが書く `presence.json` に持つ。同じファイルを両側が書き直すと、作業側の新しい名前を古い内容で上書きしうるため。不在の後に report が来ればそのセッションは不在として扱わない
  - hub 側で書くサブコマンドは、今のセッションが `hub.json` の hub でなければ書かない（takeover の後に古い hub が書き続けるのを防ぐ）
  - Linear の Issue ID の照合は大文字小文字を区別する。名前がちょうど Issue ID のセッションは既定名として外さない
  - report に `schema: 1` を入れ、違う版の report は取り込まずに `inbox/invalid/` へ退避して lead に出す（inbox に残すと未取り込みに数え続ける）
  - report は ListAgents の抜き出しを本文と一緒に受け、自己検査に合わなければ何も書かない。通知先（hub の名前）もその場で決めて返す
  - report の `issue` は tracker の Issue ID の形、`pr` は PR 番号に限る（state.md の表に載って hub に注入されるため）。state.md の表のセルは改行・制御文字（`\r`・U+2028 等）を潰して 60 字で切る
  - fact の主張・出典は stdin の JSON で受ける（argv に載せると作業側の文面がシェルで展開される）。訂正は有効な行に限る
  - journal / facts は `\n` だけを行区切りとして読む（U+2028 等を含む行が割れて消えないように）
  - 既定名（`<dir>-<数字>`）のセッションは、登録名でも Issue ID でも宛先にしない。名前が Issue ID で終わる（`fix-ABC-12`）なら既定名ではない
  - hub → 作業側の宛先の照合（resolve の `--session` / `--name`）も、今のセッションが hub でなければ止める。送る直前の照合は `--expect-ref` で承認時の ref と比べる
  - base の既定は `origin/HEAD` が指すブランチで、init で実在を確かめる。worktrees は git が失敗したら「変更なし」ではなく null と note を返し、作業側の index を書き直さない（`--no-optional-locks`）
  - 取り込み済みの report の中身を出し直す `reports` を足した（コンパクション・takeover の後に needs_lead を見直す）
  - 想定外の失敗は exit 4（「決まらない」の 1 と分ける）
  - argv に載せるのは自分の名前・PJ 名・Issue ID・session_id・ref・パスだけ。record の全文と宛先・取得のエラー文も stdin の JSON で受け、heredoc の区切りは毎回乱数つきにする
  - lead が候補から選んだ宛先は ref で引く（`resolve --ref`）。Issue ID で引けたときは警告を返す。ほかの PJ のセッションの名前は Issue ID の照合から外す
  - relay の承認は、承認の画面に出した 4 桁の番号を lead が返したときだけ。作業側は送り手の名前が hub の名前と一致するメッセージだけを hub の指示として受ける
  - PR の snapshot は repo ごとに持ち、fork の PR と base のブランチの PR を `--registered-branches` で落とす。取得の上限に届いたら打ち切りの可能性を表に出す
  - base の既定は `origin/HEAD` → `origin/main` → `origin/master`。どれも無ければ止めて明示を求める
  - facts は出典の repo のファイルが確かめた後に変わったかを `stale` で返す（brief が古い事実を渡さない）
  - state.md のセルの `<` `>` を全角にする（注入した文脈でタグとして読ませない）
