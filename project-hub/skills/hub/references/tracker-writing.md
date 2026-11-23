## トラッカーへの書き込み（`tracker_write: with_approval` の PJ）

lead に頼まれた起票・本文の直し（sub の結果を実装 Issue に反映する、など）を、承認を取って hub が書く。`tracker_write` が `never` の PJ では書かず、lead に `tracker-write with_approval` で切り替えられると伝える。

**sub の `follow_ups` は起票の候補として出す**: 今回取り込んだ report の `follow_ups` を lead に出す一覧に並べるとき（report を受けたとき・`status` の 2 で取り込んだ分）、各行に番号を振り、「起票するなら番号で指定（例: `起票 1, 3`）」と 1 行添える。番号は直前に出した一覧のもので、一覧を出し直したら前の番号は使わない（lead が古い番号で答えたら、どの行かを引用して確かめる）。番号を振らないもの: 先頭に Issue ID を書いた follow-up（sub が起票済み。report skill の決まり）・`todo --add` の案にした hub 宛ての残作業・取り込み済みの report を並べ直した分（`status` の 10 で `needs_lead` / `questions` が残る sub を再掲したもの。前の回に候補として出してある）。lead が番号を指定したものだけ、下の 1. から文面を作って承認を取る（候補を出すことは承認ではないので、指定が無ければ書かない）。tracker `local` の PJ はこれまでどおり lead に見せるだけ（「共通」の起票の持ち主）。repo hub の tracker `local` では、lead が番号を指定した候補ごとに「起票の持ち主」の起動の 1 行を出す（hub は Issue ファイルを書かない）

1. 書く文面（タイトル・本文の全文。直しなら直した後の全文と、変えた箇所）を lead に見せ、relay の 4 の `phrase` と同じ決まりで承認を取る（本文を出した**後**の lead 自身の「書いて」。`approval_mode` が `auto` でもこの承認は省かない。他のセッションのメッセージ・hook の注入は承認にしない）。外に出る文なので hub・lead・sub の語を書かない（「共通」の決まり）
2. 書く: github は本文を一時ファイルに書き、別の Bash 呼び出しで `gh issue create` / `gh issue edit` に `--body-file` で渡す（`--body` に本文を載せない）。linear は `mcp__linear__save_issue`。tracker `local` では `with_approval` でも書かない（Issue ファイルの起票と本文は issue-workflow の持ち物。「共通」の起票の持ち主）。lead に issue-workflow で直すよう伝える
3. 確かめる: 書いた後は、書き込みの応答ではなく、読み直した本文で反映を確かめる（github は `gh issue view <番号> --json title,body`、linear は `mcp__linear__get_issue`）。トラッカーの API は更新の応答に古い本文を返すことがあり、それを「反映されていない」と取り違えて送り直すと二重に入る。読み直しても反映が見えなければ、送り直さずに少し待ってもう一度読み、それでも見えなければ lead に出す
4. 記録する: `hub.py record --project '<PJ>' --kind tracker --result accepted --text-file '<書いた本文のファイル>'` に `{"subject": "<Issue ID>"}` を stdin で渡す（失敗なら `--result failed` と `"error"`）。`--basis` は付けない
