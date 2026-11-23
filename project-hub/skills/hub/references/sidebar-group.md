## sidebar-group `<on|off>`

hub と、後から sub にしたセッションを、サイドバーのグループにまとめるかを切り替える（Desktop だけ）。lead が頼んだときだけ切り替える。`hub.py set-sidebar-group --project '<PJ>' --mode <on|off>` を実行し、出力の `notice` を**そのまま** lead に伝える（サイドバーの表示が切り替わることを、lead が知らないまま動かさない）。

- on: 続けて「サイドバーのグループ」の手順を回す。exit 3（hub が Desktop でない）は stderr の文面を伝えて終える
- off: まとめたセッションとグループは動かさない。lead がグループも消してと言えば、`mcp__ccd_sidebar__list_groups` で `previous_group_id`（null なら PJ 名と同じ名前）のグループを確かめてから、`mcp__ccd_sidebar__delete_group` に渡す（中のセッションは Ungrouped に戻る）
