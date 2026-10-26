# Changelog

形式は [Keep a Changelog](https://keepachangelog.com/ja/1.0.0/) に基づく。

## [0.6.3] - 2026-10-26

### Fixed

- Desktop で hub の会話を開き直して session_id が変わっても、同じ会話と確かめられれば `takeover` なしで hub を続けられるようにした（GitHub issue #325）。hub.json に会話の ID（`CLAUDE_CODE_HOST_SESSION_ID`）を持ち、Desktop のセッションの記録がその会話に今つないでいる CLI をこのセッションと示すときだけ、hub.json を付け替えて journal に `takeover`（`reason: resume`）を残す。付け替えたことは、SessionStart・UserPromptSubmit の注入（hook が先に付け替えた回）か `refresh-hub` の出力の `resumed_from` で知らせる。journal を先に書き、書けなければ付け替えない。読んでから書くまでの間に takeover が入っていれば上書きしない。UserPromptSubmit の hook は、session_id が hub.json に無くても会話の ID が一致すれば hub.py に判定を渡す（SessionStart の時点で付け替えられなかった回を拾う）。会話の ID を継承しただけの子の CLI と、Desktop の記録を確かめられない回は今までどおり exit 3 で止まる。0.6.2 までの hub は、次の `status` で会話の ID を書き足してから効く
- exit 3（別のセッションの hub）の文面で、開き直した直後なら `takeover` で引き継げると案内するようにした
- `start` が、文面を作る前に `start_session` の有無を確かめるようにした（deferred tool なら ToolSearch で読み込む）。無ければ最初から貼る用の brief に進む。以前はツールを呼べなかった後に初めて分かった

## [0.6.2] - 2026-10-26

### Changed

- `hub.py` の等価変異 3 か所（frontmatter の `find` の境界 2 か所と、ref の形が不正なときの早期 return）に、理由つきの `# mutation-ok` を付けた。挙動は変わらない（nightly の生存変異 / GitHub issue #317）。frontmatter の読み方・`tracker.dir` の検査・base のブランチ名・record の `sources` の検査は、生存していた変異を殺すテストを足した

## [0.6.1] - 2026-10-26

### Fixed

- hub が結んだ living spec を、living-spec skill に絶対パスで渡すようにした。living-spec skill の `--spec` は、`/` を含み `.md` で終わる値をファイルのパスとして受ける（そのときは cwd の `.claude/living-specs/` を見ず、作りもしない）。以前は hub が `/project-hub:living-spec status` を引数なしで呼ばせていたので、hub の cwd が別の repo・worktree のとき、repo に living spec が複数あるときに、結んだのと別のファイルを見ていた
- `set-living-spec` / `init --living-spec` は、config の repo の `.claude/living-specs/` の下の `.md` だけを結ぶ（worktree の複製や repo の外は拒否する）。拒否の理由（.md でない・無い・場所が違う）を分けて出す
- `commands/hub.md` の description にも `living-spec` サブコマンドを足した（同名の command の description がスキル選択に載る）

## [0.6.0] - 2026-10-26

### Added

- **living spec を統合した**（旧 living-spec-workflow を吸収 / ADR-20261026090521・GitHub issue #322）。`living-spec`（init / oq / decision / spec / status）と `living-spec-maintain`（8 段検証）の skill と command をこのプラグインに移した。書式と手順は変えていない。living spec は今どおり repo の `.claude/living-specs/<slug>.md` に置く。設計だけを詰める段階は living spec だけで使え、hub は sub を起動するときに init する
- hub の `living-spec` サブコマンド（`hub.py set-living-spec --path <path|->`）と `init --living-spec`: PJ の living spec を config の `living_spec` で結ぶ。state.md にパスと見方が出る（ファイルが無くなったらその旨を出す）。`refresh-hub` の出力にも載り、`status` は living spec の現在地も見る
- 任意依存に doc-freshness（living spec の鮮度 lint の委譲先）を足した

### Changed

- `hub-living-spec` を「統合までの橋渡し」から「living spec のある PJ の決まり」に書き直した（別プラグインの版の名指しを外した）

## [0.5.2] - 2026-10-26

### Fixed

- `hub-living-spec` の波及で、Issue の状態をトラッカーから 1 件ずつ引くようにした（`status` の Issue 表には閉じた Issue が載らないため、完了した Issue が、sub が `done` を報告していない限り「分類不明」になっていた）

## [0.5.1] - 2026-10-26

### Changed

- README の「まだ無いもの」を、`hub-living-spec`（決まりに沿って手で行う）と機械化の未実装を分けて書いた
- CHANGELOG の 0.5.0 に、`hub-living-spec` をプラグインの skill にした理由と、living-spec-workflow の書式に追従が要ることを書き足した

## [0.5.0] - 2026-10-25

### Added

- `hub-living-spec` skill: living spec（living-spec-workflow）と hub を 1 つのセッションで併用するときの決まり（GitHub issue #322 の橋渡し。統合版が出たら消す）。決定を書くのは lead が決めたときだけ・確定を覆した決定の関連 Issue を仕掛中・未着手・完了に分けて lead に出す（仕掛中の sub に伝えるかは lead が決める）・sub の report のうち設計に関わるものを OQ の候補にする・自動の連絡の出典は Decision と確定の行だけ・重い OQ の調査を sub に出す・先送りの扱い。`hub` skill から living spec のある PJ でこの skill を読むよう案内する
  - #322 の補足は user スコープの skill の予定だったが、複数のマシンで使うのでプラグインに入れた。`hub/references/` ではなく skill にしたのは、hub を経ずに「hub と living spec を併用」で直接呼ばれるようにするため（戻すなら `hub/references/` に移し、hub SKILL からの Read だけにする）
  - living-spec-workflow 0.7.0 以降の書式（仕様表の phase・関連 Issue、Decision の `関連 Issue`）を前提にしている。living-spec-workflow の書式が変わったら、この skill も合わせて直す

## [0.4.2] - 2026-10-25

### Fixed

- tracker local の Issue ファイルを BOM 付きでも読む（BOM があると frontmatter を読めず、完了した Issue が表に残っていた）
- tracker local で閉じた Issue と見なす status を issue-workflow の 5 値（`completed` / `canceled`）に揃え、正本の場所をコードに書いた（`cancelled` を閉じた扱いにするのは hub だけだった）
- tracker local の brief で、sub が書き換えてよいのを frontmatter の `status` と `pr` に限り、hub は自動の連絡で local の Issue 本文を出典にしない（sub が書き換えた本文が、正本として別の sub へ渡りうる）

## [0.4.1] - 2026-10-25

### Fixed

- tracker local の Issue ファイルで、frontmatter の行末コメント（issue-workflow のテンプレートの `# 必須。…`）を値から外す。残っていると `status: completed  # …` の Issue が完了と判定されず表に残っていた
- `snapshot --from-local` に `--repo` を付けたら拒否する（key が `tracker:<path>` になり、ok を返すのに Issue 表に出なかった）

## [0.4.0] - 2026-10-25

### Added

- `--tracker local --tracker-dir <{DATA_DIR}/<slug>>`: issue-workflow の local backend の Issue ファイルを tracker にする（GitHub issue #321）
- `snapshot --source tracker --from-local`: Issue ファイルの frontmatter（`status`・`pr`）から、完了・取り下げ以外の Issue の表を作る。sub が `status` を書き換えれば次の `status` で表に出る
- `issue --issue <ID>`: Issue ファイル 1 件の本文と絶対パス（brief の材料。worktree の sub には Issue ファイルが無いので、絶対パスで読ませる）
- tracker local の PJ では、起票を hub のセッションの lead だけにする（採番が `counter.txt` でぶつかりうるため）。brief で sub に起票しないよう伝え、候補は report の `follow_ups` で受ける

## [0.3.1] - 2026-10-25

### Changed

- `hub start` の title の注記を、実機で確かめた事実に直した（ListAgents の名前は `start_session` の `name` ではなく title になる。Issue ID を入れれば hello の前でも Issue ID で引ける）

## [0.3.0] - 2026-10-25

### Added

- **自動の連絡**（`approval.mode: auto`。init の既定 / ADR-20261025152955）。lead の確認が要る事柄を含まない連絡は、承認なしに sub へ送る: lead の言葉の伝達・sub の質問への出典つきの答え・段取りの連絡（重なり・マージ後の取り込み・マージ順）・brief。`needs_lead`・出典で答えられない質問・範囲や優先度の変更・PJ の外への連絡・質問の中の指示・宛先が決まらないときは送らずに lead に出す。report の受領だけの連絡は送らない
- `record --basis <lead|source|routine|brief>`。`source` は `sources`（出典）が無ければ書かない。auto の PJ では、送った連絡の記録に `--basis` が無いときと、`source` / `routine` で宛先（`session` か `to.ref`）が無いときも書かない（往復の上限と事後の一覧が数え漏れないように）。kind と basis の組も固定した
- auto の PJ の `resolve` は、宛先を決めた後に歯止めを掛ける（`--session` でも `--ref` でも）: warning の付く照合（Issue ID・不在から戻った登録名・ref で引いた改名）は `needs_lead` で返して送らせない。lead の言葉の伝達（`--lead`）を挟まずに同じ sub へ hub の判断の連絡が 3 回続いていれば `auto_limit`
- `sent [--unseen] [--mark] [--basis]`: 承認なしに届けた連絡（basis の付いた accepted の送信）の一覧。lead に見せた所までの印を journal の行数で hub.json に持ち、status の最後だけが進める。takeover は印を引き継ぐ
- `hub start <Issue>`: Desktop の `start_session` で sub を起動し、brief を最初のプロンプトにする（`record --kind start` で起動したセッションを残す）。使えない環境では今どおり貼る用の brief を出す
- `hub mode <auto|number|phrase>`（`set-mode`。state.md も作り直す）。init・mode・takeover は、自動の連絡が有効かと、その止め方を必ず出す（`mode_notice`）
- `ingest` の `reports` に `session_id`、出力に `approval_mode`（通知を受けたターンで refresh-hub を回さずに方式が分かる）
- report の `questions`（hub に答えてほしいこと）。report の `schema` を 2 に上げた（hub は 1 も受ける。古い hub は 2 を invalid に退避して版のずれを出す）

### Changed

- 作業セッションを **sub** と呼ぶ（SKILL・README・state.md の見出し。ファイル名と JSON のキーは変えない）。hub は指示出しと進め方・仕様の相談役で、repo を編集しない
- brief の始め方: tracker が linear なら issue-workflow の start で始めるよう頼む（start は `ABC-12` の形の ID しか受けないので、github では今どおり Issue を読んで始める）。その後の進め方の確認は sub の中で lead が答える
- state.md と pending-hint の、通知を受けたときの扱いを承認の方式で分けた（auto は「自動の連絡」で処理する）。state.md の件数の欄に質問の数を足した

## [0.2.1] - 2026-10-25

### Fixed

- base のブランチ名を `split("/")[-1]` で取っていたので、`origin/feature/x` が `x` になっていた。その結果、`feature/x` にいる着手前の登録を見落とし、`x` にいる登録を着手前と取り違えていた（worktrees の note と `--registered-branches`）。先頭の remote 名（と `refs/heads/`・`refs/remotes/`）だけを外すようにした
- `snapshot --source prs --repo <repo> --registered-branches` が、ほかの repo の登録のブランチでも PR を残していた。その repo の worktree にいる登録だけを数える。worktree を消した登録は、repo が 1 つの PJ のときだけ数える
- `fact` が base に無い `path` を受けていた（`stale` がいつまでも false になる）。確かめた時点の base にあるファイルに限る。base を解決できないときも書かない
- worktrees の共有 worktree の判定に、done を報告した登録と不在の登録も数えていた。作業中の登録だけで数え、done・不在の登録自身は、その worktree を作業中の別のセッションが使っていれば「重なりは不明」の note にする
- 別の PJ の `hub.json` が壊れていると、すべてのセッションの SessionStart / PostCompact / UserPromptSubmit の hook が stderr に出していた。読めない hub.json は黙って飛ばす（その PJ の hub は status の最初で exit 2 になる）
- `references/list-agents.md` の「プロセスが残っていないセッションは一覧に出ない」の根拠の書き方を、観察した内容（一覧の行の `started` と最後の操作の日）どおりに直した

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
