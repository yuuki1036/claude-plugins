## Issue の保守（repo hub だけ）

lead に頼まれたときだけ、repo hub の Issue（Issue ファイルの進捗・状態）を整える。対象は Issue ごとに決め、作業中の sub がいる Issue は外す（sub が同じ Issue ファイルを書き換えている）。

1. status の 2・3 で取り込みと presence を回してから、`hub.py worktrees --project '<PJ>'` の `busy_issues`（この PJ の作業中の sub の Issue）と、`hub.py cross --project '<PJ>'` の `busy_issues`（同じ repo の別の PJ の作業中の sub の Issue）に入っている Issue を外す。どちらも hub.py が表記を揃えた形（github は `#12`、local / linear は前後の空白を除いた ID）なので、そのまま Issue ID と比べる（表記を自分で揃え直さない）
2. 残った Issue ごとに、issue-workflow の issue-maintain に Issue ID を渡して回すよう、lead が貼る 1 行（`/issue-workflow:issue-maintain <Issue ID>`）を出す。issue-workflow の maintain（全件を承認なしに書き換える）と follow-up の promote（起票の後にブランチを作る確認を出す）は hub のセッションでは回さない
