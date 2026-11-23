## mode `<auto|number|phrase>`

送る前の承認の方式を切り替える。`hub.py set-mode --project '<PJ>' --mode <方式>` を実行し、出力の `mode_notice` をそのまま lead に伝える（state.md の通知の扱いも set-mode が作り直す）。lead が頼んだときだけ切り替える。
