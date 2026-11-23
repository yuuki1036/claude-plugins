## todo

hub 自身の残作業（sub から引き継いだ作業・lead に頼まれた確認など）を持つ。会話の中にだけ置くと、コンパクションや開き直しで落ちる。

- 足す: `hub.py todo --project '<PJ>' --add` に `{"text": "<1 行の残作業>", "source": "<report のファイル名か null>"}` を stdin で渡す。text は hub の言葉で書く（sub の文面をそのまま写さない。state.md に載って注入される）。sub の report から取ったなら source にそのファイル名を入れる
- 終える: `hub.py todo --project '<PJ>' --done <id>`。一覧: `hub.py todo --project '<PJ>'`（終えたものも見るなら `--all`）
- 未完了の残作業は state.md の「hub の残作業」に出て、status の 10 で lead に見せる
