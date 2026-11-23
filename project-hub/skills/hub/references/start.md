## start `<Issue>`

sub を起動して、その Issue を任せる。lead が start を頼んだターンでだけ起動する（sub の通知など他のセッションのメッセージで始まったターンでは、アプリが起動を断る。そのときは `start_session` を `initiation: own_initiative` で提案し、lead がカードから始める）。

0. 起動の手段を、文面を作る前に決める。このセッションのツールに `mcp__ccd_session__start_session` があるかを見る。名前だけの deferred tool として載っていれば、`ToolSearch` に `select:mcp__ccd_session__start_session` を単独で渡して読み込む。ツールにも ToolSearch の結果にも無ければ起動できない（CLI のほか、Desktop でも出ない回があった。出る条件は未確認 / GitHub issue #325）。そのときは lead に「このセッションでは sub を起動するツールが使えないので、貼る用の brief を出す」と 1 行伝え、下の `brief <Issue>` の手順で進める（3 は「新しいセッション（lead が貼る）」）。1〜4 は通らない
1. 下の `brief` の 1〜2 で文面を作る。`approval_mode`（`refresh-hub`）が `number` / `phrase` なら、または文面に「別の PJ との重なりに注意」の行があれば（`auto` でも / ADR-20261029233251）、relay の 4 と同じく全文を出して承認を取ってから 2 へ進む（brief には Issue 本文の引用が入り、起動したセッションの最初のタスク本文になる）
2. Desktop で `mcp__ccd_session__start_session` が使えるとき、それで起動する:
   - `initiation: user_asked` / `context: fresh` / `use_worktree: true`
   - `title`: `<Issue ID> <英語の短い要約>`（例 `#308 hub-relay-raw`・`ABC-12 audit-log`。60 字以内。Issue のタイトルをそのまま入れない — 日本語の長い文になって一覧で見分けにくい。ListAgents の名前は `name` ではなく title になる（2026-10-25 に実測）ので、Issue ID を入れると hello の前でも Issue ID で引ける）
   - `prompt`: brief の全文。`background`: PJ 名・hub の名前・PJ の目的（config と state.md から 2〜3 文。80 字以上）。repo hub は PJ の目的の代わりに「repo <repo の名前> の常設の hub。範囲はどの PJ にも入らない open Issue。Issue の起票は hub が受け持つ」と書く
   - `cwd`: このセッションの cwd が config の repos のどれでもなければ、Issue の repo のパス（repos が複数で決まらなければ lead に聞く）
   - `permission_mode` は渡さない（hub と同じ mode を引き継ぐ。mode が違う sub には、メッセージが受け手の承認待ちで止まる）
   - `effort`: `medium` を渡す（hub の effort を sub に引き継がせない / GitHub issue #343）。`start_session` は hub の effort より上を断るので、hub の effort が `low` なら渡さずに引き継がせる。hub の effort は起動の直前に Bash の `echo "$CLAUDE_EFFORT"` で読み、空なら command 本文が示した値を使う（この節のファイルも SKILL.md も Read で読むので、ここに `${CLAUDE_EFFORT}` と書いても展開されない）
3. 結果を記録する: 1 で作った brief の全文を、要約せずにそのまま一時ファイルに書き（heredoc の区切りは「シェルに読ませない」の決まり）、`hub.py record --project '<PJ>' --kind start --result accepted --text-file '<そのファイル>'`（`auto` の PJ だけ `--basis brief`）に `{"subject": "<Issue>", "to": null, "started": {"id": "<結果のセッションの id>", "name": "<結果の名前>", "effort": "<2 で渡した effort。渡さなかったら鍵ごと省く>"}}` を stdin で渡す。`prompt` に渡した文面と同じものを残す（要約だけを残すと、記録の趣旨から外れる）。断られた・失敗した・ツールが無い（CLI）なら、`brief` の 3 の「新しいセッション」へ進む（貼る用の全文を出す）
4. lead に、起動した sub（名前・リンク・effort）を伝える。`auto` の PJ では送った brief の全文もここで見せ（lead が読まないまま送った文面を残さない）、sub が hello を置けば以後は自動で連絡すると添える
