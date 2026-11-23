## reopen `<PJ>`

closed の PJ（repo hub を含む）を active に戻す。lead が頼んだときだけ行う。

1. ListAgents から自分の名前を取り、`hub.py reopen --project '<PJ>' --name '<名前>'`。hub のセッションが前と違えば takeover も兼ねる（journal に takeover を残し、出力の `previous` に前の hub の名前が出る）
2. exit 3 なら `reason` を伝えて終える。stdout の `status` は、`not_closed`（closed ではない。active なら何もしない）/ `scope_conflict`（closed の間に同じ repo に範囲が重なる PJ ができている。その PJ を close するか範囲を切るまで戻せない）/ `config_unreadable`（config が読めない PJ がある。その config.json を直す）/ `not_initialized`（その名前の PJ が無い。PJ 名を確かめる）
3. 出力を伝える。`mode_notice` は**必ずそのまま**伝える。`moved`（closed の間に同じ repo の別の PJ へ移ったので、この PJ の作業中から外した sub。名前・Issue・移った先の PJ）と `unknown`（config が読めず、移ったかを確かめられなかった PJ）があれば並べる。続けて `status` を回す
