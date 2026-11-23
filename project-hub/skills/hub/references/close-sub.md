## close-sub `<Issue>`

done を報告した sub のセッションを閉じる（Desktop の archive）。自分の PR のマージを知らせたのに done が来ない sub も、lead が閉じると決めたら閉じる（1 の例外）。lead が頼んだときだけ行う。

1. `hub.py worktrees --project '<PJ>'` の `sessions` から Issue で session_id を探し、`hub.py close-sub --project '<PJ>' --session <session_id>` で確かめる。exit 3（最新の report が done でない）なら閉じずに、その旨を lead に伝える。`ingest` していない done の report があれば、先に取り込む。例外は status の 10 に出た「マージを知らせたのに done が来ない sub」を lead が閉じると決めた回で、確かめに `--force` を付ける（出力の `state` に最新の report の state が出る。その sub に `waiting` の `own: true` かつ `notified: true` の行が無ければ、`--force` でも exit 3）。閉じた記録（4）で `waiting` から外れ、その後にその sub が report を置けば戻る
2. 出力の `host` が null なら（`note` の理由）hub からは閉じられない。lead に手で閉じてもらうよう伝えて終える
3. `mcp__ccd_session_mgmt__archive_session` に `session_id: <host>`・`reason: "<Issue> の done を受けて hub から閉じる"`（`--force` で確かめた回は `"<Issue> のマージを知らせたが done が来ず、lead の判断で hub から閉じる"`）を渡す（deferred tool なら ToolSearch で読み込む。ツールが無ければ 2 と同じく lead に頼む）。アプリが承認を求めることがある。作業中・画面に開いている sub は閉じられないと返る
4. `hub.py close-sub --project '<PJ>' --session <session_id> --result accepted`（閉じられなかったら `--result failed --error '<返ってきた理由の要旨>'`）で記録し、lead に結果を 1 行で伝える

サイドバーのグループにまとめた sub も、グループから外す操作はしない。archive した会話は Archived の一覧から開き直す扱いになり（`archive_session` のツール定義）、閉じた sub は `hub.py sidebar` の `pending` にも出ない。
