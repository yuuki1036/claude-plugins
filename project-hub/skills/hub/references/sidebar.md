## サイドバーのグループ（`sidebar_group` が `on` の PJ）

Desktop のサイドバーでは、hub から起動した sub は hub の下に並ぶ。hub の外で始めて後から sub にしたセッション（貼った brief・hello で登録したもの）は、独立のセッションのまま並ぶ。既にあるセッションを別のセッションの下に結び付けるツールは無い（`detach_session` は外すだけ）ので、代わりに PJ ごとのサイドバーのグループに hub とそのセッションをまとめる（GitHub issue #339）。`sidebar_group` が `off` の PJ（init で `on` を選ばなかった PJ・CLI で作った hub・lead が off にした PJ・v0.11.0 より前に作って `sidebar-group on` にしていない PJ）ではこの手順を回さない。

1. `hub.py sidebar --project '<PJ>'`。`note` があれば（hub が Desktop でない）何もしない。`hub.filed` が true で `pending` が空なら終える。`no_host`（会話の ID を確かめられない登録。CLI・0.6.4 までの登録）は動かせない（lead に出すのは `sidebar-group on` の直後だけ）
2. `pending` の各行の `host` を `mcp__ccd_session_mgmt__get_session` に渡す。`parentSessionId` があって `detached` が true でなければ、起動したセッション（hub か、別のセッション）の下に並んでいるので動かさず nested にする。取れなければ failed（`error` に理由）
3. 動かすもの（nested でない `pending` と、`hub.filed` が false なら hub 自身）があれば、グループを決める。`mcp__ccd_sidebar__list_groups` を引き、失敗したら作らずにこの手順を終える（アプリの画面がまだグループを知らせていないだけで、空とは限らない / ツール定義。次の status でやり直す）
   - `group_id` があり一覧にある → それを使う
   - `group_id` があり一覧に無い（lead が消した）→ 作り直さない。「PJ のグループが見つからないので、まとめていない。作り直すなら `hub sidebar-group on`」と lead に 1 行で伝えて終える
   - `group_id` が null → 一覧に `group_name`（PJ 名）と同じ名前のグループがあればそれを、無ければ `mcp__ccd_sidebar__create_group` に `name: <group_name>` を渡して作る
4. `mcp__ccd_sidebar__move_sessions` に `group_id` と `session_ids`（動かす sub の `host` と、hub 自身なら `"self"`）を 1 回で渡す。permission mode が default なら、hub 以外を動かすときにアプリが確認を出す。断られたら declined、それ以外の失敗は failed
5. `hub.py sidebar --project '<PJ>' --record` に `{"group_id": "<id>", "filed": [...], "nested": [...], "declined": [...], "failed": [{"host": "<会話の ID>", "error": "<理由>"}]}` を stdin で渡す（hub 自身は `"self"` ではなく 1 の `hub.host` を入れる。nested だけの回は `group_id` を省いてよい）。filed・nested・declined の会話は次から `pending` に出ない（declined を出し直すと、断った確認を status のたびに出すことになる）。failed は次の回にやり直す
6. lead に 1 行で伝える（動かした sub の名前とグループ名・断られた・失敗した）。nested だけの回は書かない

PJ を `close` してもグループは残る。グループを消すのは lead が頼んだときだけ（下の `sidebar-group`）。
