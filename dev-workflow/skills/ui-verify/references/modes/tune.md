#### tune モード

スタイル調整の対話ループ。

1. 初回の `take_screenshot` を `.claude/screenshots/tune-{timestamp}/before.png` に保存
2. ユーザーに調整内容を確認（例: 「ヘッダーの余白を広げたい」「ボタンの色を primary に」）
3. 直す場所を `get_css_styles` で特定してから Edit で修正する。`take_snapshot` で対象要素の uid を取り、`get_css_styles(pageId, uid)` で**効いているルールと定義位置（ファイル:行）・上書きされたプロパティ**を読む（source map が効くので dev server ではソースのファイル名が出る）。grep でクラス名を探して当たりを付けない — 上書きされて効いていないルールを直す手戻りになる
4. dev server の HMR 反映を待つ（`wait_for` + 短い sleep）
5. `take_screenshot` で after.png を保存
6. 差分をユーザーに提示し、OK なら終了、NG ならループ

**HMR が効かない場合:**
- `navigate_page` で再読み込み
- ビルドエラーなら `list_console_messages` で原因特定
